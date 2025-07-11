import streamlit as st
import pandas as pd
import plotly.express as px
from scraper import get_all_bills, load_config

# --- 页面配置 ---
st.set_page_config(page_title="校园一卡通消费分析", page_icon="💳", layout="wide")

# --- 核心数据处理与分析函数 ---
def run_analysis(start_date, end_date):
    """根据日期范围加载数据并执行所有分析和图表渲染"""
    try:
        with st.spinner(f"正在获取 {start_date} 到 {end_date} 的账单数据..."):
            result = get_all_bills(st.session_state.config, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))

        # 首先检查返回的是否为 DataFrame，如果不是，则说明是错误信息
        if not isinstance(result, pd.DataFrame):
            st.error(f"获取数据失败：{result}")
            if "Cookie" in str(result):
                st.warning(
                    """
                    **如何解决 Cookie 失效问题？**

                    1.  **重新登录**：在您的浏览器（如 Chrome）中，重新登录 [西安石油大学统一身份认证平台](https://my.xsyu.edu.cn/sopcb/)。
                    2.  **获取新 Cookie**：严格按照 `README.md` 文件中 “**如何使用**” -> “**2. 获取并配置 Cookie**” 的步骤，获取新的 Cookie 值。
                        - 关键点：**先在其他页面打开开发者工具（F12），再将账单页地址粘贴进去**，以绕过检测。
                    3.  **更新配置**：将新复制的 Cookie 字符串粘贴到 `config.json` 文件中并保存。
                    4.  **重新分析**：回到本页面，再次点击上方的 “🚀 开始分析” 按钮即可。
                    """
                )
            return

        df = result
        if df.empty:
            st.warning("在选定时间范围内没有找到任何账单记录。")
            return

        # --- 数据类型强制转换 (防御性编程) ---
        df['交易金额(元)'] = pd.to_numeric(df['交易金额(元)'], errors='coerce')
        df['交易时间'] = pd.to_datetime(df['交易时间'], errors='coerce')
        df.dropna(subset=['交易金额(元)', '交易时间'], inplace=True)

        # --- 数据筛选与预处理：只保留支出项 ---
        df_expenses = df[df['交易内容'] == '消费'].copy()
        
        if df_expenses.empty:
            st.success("数据加载完毕！")
            st.warning("在选定时间范围内没有找到任何【消费】记录，所有分析图表将为空。")
            return

        # 将交易金额转为正数，便于计算
        df_expenses['消费金额(元)'] = df_expenses['交易金额(元)'].abs()
        df_expenses['小时'] = df_expenses['交易时间'].dt.hour
        df_expenses['星期'] = df_expenses['交易时间'].dt.day_name()

        st.success("数据加载与处理完毕！")
        
        # --- 渲染分析模块 ---
        render_summary_metrics(df_expenses)
        render_charts(df_expenses)
        render_fun_facts(df_expenses)

    except Exception as e:
        st.error(f"分析过程中出现错误: {e}")

def render_summary_metrics(df):
    """渲染顶部的核心指标"""
    st.header("📈 消费总览")
    total_expense = df['消费金额(元)'].sum()
    days_span = (df['交易时间'].max() - df['交易时间'].min()).days + 1
    avg_daily_expense = total_expense / days_span if days_span > 0 else 0
    
    col1, col2, col3 = st.columns(3)
    col1.metric("总支出", f"¥ {total_expense:,.2f}")
    col2.metric("日均消费", f"¥ {avg_daily_expense:,.2f}")
    col3.metric("总消费次数", f"{len(df)} 笔")

def render_charts(df):
    """渲染所有数据图表"""
    st.header("📊 图表分析")

    # --- 月度消费趋势 ---
    st.subheader("月度消费趋势")
    # 使用 'ME' (Month End) 替代已弃用的 'M'
    df_monthly = df.set_index('交易时间').resample('ME').agg({'消费金额(元)': 'sum'}).reset_index()
    fig_monthly = px.line(df_monthly, x='交易时间', y='消费金额(元)', title="每月总支出变化", markers=True, labels={'交易时间':'月份', '消费金额(元)':'消费总额(元)'})
    fig_monthly.update_layout(title_x=0.5)
    st.plotly_chart(fig_monthly, use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        # --- 干饭能量分布图 ---
        st.subheader("干饭能量分布")
        hourly_counts = df['小时'].value_counts().sort_index()
        fig_hourly = px.bar(hourly_counts, x=hourly_counts.index, y=hourly_counts.values, title="一天中的消费高频时段", labels={'index':'小时', 'y':'消费次数'})
        fig_hourly.update_layout(title_x=0.5, xaxis_title="小时（24小时制）", yaxis_title="消费笔数")
        st.plotly_chart(fig_hourly, use_container_width=True)

    with col2:
        # --- 一周消费热力图 ---
        st.subheader("一周消费热力图")
        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekly_spending = df.groupby('星期')['消费金额(元)'].sum().reindex(days_order)
        fig_weekly = px.bar(weekly_spending, x=weekly_spending.index, y=weekly_spending.values, title="周消费习惯分析", labels={'index':'星期', 'y':'消费总额(元)'})
        fig_weekly.update_layout(title_x=0.5, xaxis_title="星期", yaxis_title="消费总额(元)")
        st.plotly_chart(fig_weekly, use_container_width=True)

def render_fun_facts(df):
    """渲染趣味数据统计"""
    st.header("💡 趣味数据洞察")
    
    col1, col2, col3 = st.columns(3)

    # --- 卷王时刻 ---
    df_morning = df[df['小时'].between(5, 9)] # 假设早餐时间 5-9点
    if not df_morning.empty:
        earliest_record = df_morning.loc[df_morning['交易时间'].idxmin()]
        earliest_time_str = earliest_record['交易时间'].strftime('%Y-%m-%d %H:%M:%S')
        col1.metric("🥇 卷王时刻", earliest_record['交易时间'].strftime('%H:%M:%S'), help=f"记录于 {earliest_time_str}，又是为梦想早起的一天！")
    else:
        col1.metric("🥇 卷王时刻", "暂无记录", help="看起来您是个从容不迫的早餐享用者。")

    # --- 夜食之神 ---
    df_evening = df[df['小时'].between(18, 23)] # 假设晚餐/夜宵 18-23点
    if not df_evening.empty:
        latest_record = df_evening.loc[df_evening['交易时间'].idxmax()]
        latest_time_str = latest_record['交易时间'].strftime('%Y-%m-%d %H:%M:%S')
        col2.metric("🌙 夜食之神", latest_record['交易时间'].strftime('%H:%M:%S'), help=f"记录于 {latest_time_str}，是知识的海洋让你忘记了时间吗？")
    else:
        col2.metric("🌙 夜食之神", "暂无记录", help="看来您的作息相当规律，值得点赞！")

    # --- 豪横瞬间 ---
    biggest_purchase = df.loc[df['消费金额(元)'].idxmax()]
    biggest_purchase_time = biggest_purchase['交易时间'].strftime('%Y-%m-%d')
    col3.metric("💸 豪横瞬间", f"¥ {biggest_purchase['消费金额(元)']:.2f}", help=f"在 {biggest_purchase_time} 发生了一笔“巨款”消费！")


# --- 主函数与页面渲染 ---
def main():
    st.title("💳 校园一卡通消费分析看板")

    if 'config' not in st.session_state:
        try:
            st.session_state.config = load_config()
        except FileNotFoundError:
            st.error("错误：`config.json` 文件未找到。请确保您已根据 `config.json.example` 创建并正确配置了该文件。")
            st.info("请参考 `README.md` 中的说明完成配置。")
            return
        except Exception as e:
            st.error(f"加载配置文件时出错: {e}")
            return

    # --- 日期选择 ---
    st.sidebar.header("🔍 查询设置")
    today = pd.to_datetime('today')
    default_start = today - pd.DateOffset(months=1)
    
    start_date = st.sidebar.date_input("开始日期", default_start)
    end_date = st.sidebar.date_input("结束日期", today)

    if start_date > end_date:
        st.sidebar.error("错误：开始日期不能晚于结束日期。")
        return

    if st.sidebar.button("🚀 开始分析", use_container_width=True, type="primary"):
        run_analysis(start_date, end_date)

if __name__ == "__main__":
    main() 