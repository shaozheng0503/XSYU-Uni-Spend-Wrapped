import json
import math
import os
import time
from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup

# 全局变量
CONFIG_FILE = 'config.json'
CONFIG_TEMPLATE = {
    "cookie": "请在这里填入您从浏览器获取的 Cookie",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}


def load_config():
    """加载配置文件，如果不存在或配置不正确则返回 None。"""
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(CONFIG_TEMPLATE, f, indent=4, ensure_ascii=False)
        return None

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError:
            return None
            
    if not config.get('cookie') or config.get('cookie') == CONFIG_TEMPLATE['cookie']:
        return None

    return config


def fetch_bill_data(config, start_date, end_date, page=1):
    """
    获取指定页码的账单数据

    Args:
        config (dict): 配置字典
        start_date (str): 开始日期 (YYYY-MM-DD)
        end_date (str): 结束日期 (YYYY-MM-DD)
        page (int): 页码

    Returns:
        dict: 包含 'soup' (BeautifulSoup 对象) 和 'total_records' (总记录数) 的字典
    """
    url = "https://ykt.xsyu.edu.cn/easytong_portal/integrate/bill"
    headers = {
        'Cookie': config['cookie'],
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Referer': 'https://ykt.xsyu.edu.cn/easytong_portal/integrate/bill',
        'Origin': 'https://ykt.xsyu.edu.cn',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    payload = {
        'timeInterval': '',
        'typeFlag': '',
        'startdealTime': start_date,
        'enddealTime': end_date,
        'payepId': '',
        'eWalletId': '',
        'cardaccNum': '',
        'currentPage': page
    }

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=30)
        response.raise_for_status()

        if 'login' in response.url or "统一身份认证" in response.text:
            return "Cookie失效"

        return BeautifulSoup(response.content, 'html.parser')

    except requests.exceptions.RequestException as e:
        print(f"网络请求出错 (第 {page} 页)：{e}")
        return None


def parse_data_to_dataframe(soup):
    """
    解析 BeautifulSoup 对象，提取当前页的账单数据并转换为 Pandas DataFrame。
    """
    table = soup.find('table', {'class': 'table-hover'})
    if not table:
        return pd.DataFrame(), None, None

    headers = ["使用单位", "交易时间", "交易内容", "交易金额(元)", "状态"]
    rows = []
    tbody = table.find('tbody')
    if not tbody:
        return pd.DataFrame(), None, None

    for tr in tbody.find_all('tr'):
        cells = tr.find_all('td')
        if len(cells) < 5:
            continue

        unit = cells[0].text.strip()
        time_cell = cells[1]
        date_part = time_cell.contents[0].strip()
        time_part_tag = time_cell.find('p', {'class': 'text-muted'})
        time_part = time_part_tag.text.strip() if time_part_tag else ''
        full_time = f"{date_part} {time_part}"
        content = cells[2].text.strip()
        amount_tag = cells[3].find('strong', {'class': 'price'})
        amount = amount_tag.text.strip() if amount_tag else cells[3].text.strip()
        status_tag = cells[4].find('span')
        status = status_tag.text.strip() if status_tag else cells[4].text.strip()

        rows.append([unit, full_time, content, amount, status])
    
    # 提取分页信息
    total_count_input = soup.find('input', {'id': 'totalCount'})
    page_size_text = soup.find('li', {'class': 'list-num'})

    # --- 数据清洗和类型转换 ---
    # 转换交易时间为 datetime 对象
    df = pd.DataFrame(rows, columns=['使用单位', '交易时间', '交易内容', '交易金额(元)', '状态'])

    # 转换交易金额为数值类型，非数值的将变为 NaN
    df['交易金额(元)'] = pd.to_numeric(df['交易金额(元)'], errors='coerce')
    
    # 删除任何因转换失败而产生空值的行
    df.dropna(subset=['交易时间', '交易金额(元)'], inplace=True)

    return df, total_count_input, page_size_text


def get_all_bills(config, start_date, end_date, progress_callback=None):
    """
    获取所有页的账单数据并合并。
    """
    # 1. 获取第一页并确定总页数
    print("正在获取第 1 页数据...")
    if progress_callback:
        progress_callback(0, "正在获取第 1 页...")
        
    result = fetch_bill_data(config, start_date, end_date, page=1)
    if result is None:
        return None # 网络错误
    if result == "Cookie失效":
        return "Cookie失效"
    
    soup_page1 = result
    df_page1, total_count_input, page_size_text = parse_data_to_dataframe(soup_page1)

    if df_page1.empty:
        print("第一页没有查询到任何数据。")
        return pd.DataFrame()
    
    all_dfs = [df_page1]

    if not total_count_input or not page_size_text:
        print("警告：无法找到分页信息，只返回第一页的结果。")
        return df_page1

    total_count = int(total_count_input.get('value', 0))
    page_size = 20
    
    try:
        page_size_str = page_size_text.text.split(',')[0].split('-')[1].replace('条','').strip()
        page_size = int(page_size_str)
    except (ValueError, IndexError):
        print(f"无法从 '{page_size_text.text}' 解析每页条数，将使用默认值 {page_size}。")

    if total_count == 0 or page_size == 0:
        return df_page1

    total_pages = math.ceil(total_count / page_size)
    print(f"发现总共 {total_count} 条记录，分为 {total_pages} 页。")

    # 2. 循环获取剩余页的数据
    if total_pages > 1:
        for page in range(2, total_pages + 1):
            if progress_callback:
                progress_callback(page / total_pages, f"正在获取第 {page}/{total_pages} 页...")
            
            print(f"正在获取第 {page} 页数据...")
            result_page_n = fetch_bill_data(config, start_date, end_date, page=page)

            if result_page_n is None:
                print(f"获取第 {page} 页失败，将跳过此页。")
                continue
            if result_page_n == "Cookie失效":
                return "Cookie失效"
            
            soup_page_n = result_page_n
            df_page_n, _, _ = parse_data_to_dataframe(soup_page_n)
            if not df_page_n.empty:
                all_dfs.append(df_page_n)
            
            time.sleep(0.5)

    # 3. 合并所有数据
    final_df = pd.concat(all_dfs, ignore_index=True)
    print(f"所有页面数据获取完毕，共得到 {len(final_df)} 条记录。")
    if progress_callback:
        progress_callback(1, "数据获取完毕！")
    return final_df 