import os
from datetime import date, timedelta

import pandas as pd

# 从新的 scraper 模块导入核心功能
from scraper import get_all_bills, load_config

OUTPUT_DIR = 'output'


def main():
    """主函数，负责命令行执行流程"""
    config = load_config()
    if not config:
        # 如果配置加载失败，直接退出
        return

    # 设置查询的起止日期，默认为最近一年
    end_date = date.today()
    start_date = end_date - timedelta(days=365)
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    # 获取所有账单数据
    bill_df = get_all_bills(config, start_date_str, end_date_str)

    # 处理返回结果
    if bill_df is None:
        print("程序因网络问题中断。")
        return
    if isinstance(bill_df, str) and bill_df == "Cookie失效":
        print("获取数据失败，请检查并更新您的 Cookie。")
        return

    if not bill_df.empty:
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        # 数据清洗和转换
        bill_df['交易金额(元)'] = pd.to_numeric(bill_df['交易金额(元)'], errors='coerce')
        bill_df['交易时间'] = pd.to_datetime(bill_df['交易时间'], errors='coerce')
        bill_df.dropna(subset=['交易金额(元)', '交易时间'], inplace=True)
        
        output_path = os.path.join(OUTPUT_DIR, f'xsyu_bill_{start_date_str}_to_{end_date_str}.xlsx')
        bill_df.to_excel(output_path, index=False, sheet_name='消费总览')
        print(f"\n账单数据已成功保存到：{output_path}")
    else:
        print("在指定时间范围内没有找到任何消费记录。")


if __name__ == '__main__':
    main() 