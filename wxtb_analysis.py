# app.py
import io
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(
    page_title="商品报表分析看板",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- 1. 数据加载与缓存 ----------
@st.cache_data(show_spinner="正在解析报表...")
def load_data(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0)
    return df

@st.cache_data(show_spinner=False)
def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # 日期
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")

    # 把所有可能的数值列统一处理
    num_cols = [
        "展现量", "点击量", "花费", "点击率", "平均点击花费", "千次展现花费",
        "总预售成交金额", "总预售成交笔数", "直接预售成交金额", "直接预售成交笔数",
        "间接预售成交金额", "间接预售成交笔数",
        "直接成交金额", "间接成交金额", "总成交金额", "总成交笔数",
        "直接成交笔数", "间接成交笔数", "点击转化率", "投入产出比", "含预售投产比",
        "总成交成本", "总购物车数", "直接购物车数", "间接购物车数", "加购率",
        "收藏宝贝数", "收藏店铺数", "店铺收藏成本", "总收藏加购数", "总收藏加购成本",
        "宝贝收藏加购数", "宝贝收藏加购成本", "总收藏数", "宝贝收藏成本", "宝贝收藏率",
        "加购成本", "拍下订单笔数", "拍下订单金额", "直接收藏宝贝数", "间接收藏宝贝数",
        "优惠券领取量", "购物金充值笔数", "购物金充值金额", "旺旺咨询量",
        "引导访问量", "引导访问人数", "引导访问潜客数", "引导访问潜客占比",
        "入会率", "入会量", "引导访问率", "深度访问量", "平均访问页面数",
        "成交新客数", "成交新客占比", "会员首购人数", "会员成交金额", "会员成交笔数",
        "成交人数", "人均成交笔数", "人均成交金额",
        "自然流量转化金额", "自然流量曝光量",
        "平台助推总成交", "平台助推直接成交", "平台助推点击",
        "平台补贴金额", "补贴引导成交金额", "发券补贴商品个数", "补贴引导成交人数",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 文本列清理
    for col in ["主体ID", "主体类型", "主体名称"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


def fmt_pct(x):
    try:
        return f"{x*100:.2f}%"
    except Exception:
        return "-"


# ---------- 2. 侧边栏上传 ----------
st.sidebar.header("📁 数据源")
uploaded = st.sidebar.file_uploader("上传商品报表 Excel", type=["xlsx", "xls"])

# 若没有上传,尝试用同目录下的默认文件
if uploaded is not None:
    raw = uploaded.getvalue()
else:
    default_path = "商品报表_20260928_112241.xlsx"
    try:
        with open(default_path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        st.warning("请先在左侧上传 Excel 文件。")
        st.stop()

df_raw = load_data(raw)
df = clean_data(df_raw)

# ---------- 3. 侧边栏筛选 ----------
st.sidebar.header("🔎 筛选条件")

if "日期" in df.columns:
    min_d, max_d = df["日期"].min(), df["日期"].max()
    date_range = st.sidebar.date_input(
        "日期范围",
        value=(min_d.date(), max_d.date()),
        min_value=min_d.date(),
        max_value=max_d.date(),
    )
else:
    date_range = None

keyword = st.sidebar.text_input("商品名称关键词", "")
only_spend = st.sidebar.checkbox("只看有花费的商品", value=False)
only_deal  = st.sidebar.checkbox("只看有成交的商品", value=False)

top_n = st.sidebar.slider("排行榜 Top N", 5, 50, 10)

# 应用筛选
dff = df.copy()
if date_range and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    dff = dff[(dff["日期"] >= start) & (dff["日期"] <= end)]
if keyword:
    dff = dff[dff["主体名称"].str.contains(keyword, case=False, na=False)]
if only_spend and "花费" in dff.columns:
    dff = dff[dff["花费"] > 0]
if only_deal and "总成交金额" in dff.columns:
    dff = dff[dff["总成交金额"] > 0]

# ---------- 4. 顶部 KPI ----------
st.title("📊 商品报表分析看板")
st.caption(f"当前筛选后共 {len(dff):,} 行 · 商品数 {dff['主体ID'].nunique() if '主体ID' in dff.columns else '-'}")

def safe_sum(col):
    return dff[col].sum() if col in dff.columns else 0

total_spend = safe_sum("花费")
total_gmv   = safe_sum("总成交金额")
total_click = safe_sum("点击量")
total_imp   = safe_sum("展现量")
total_orders= safe_sum("总成交笔数")
roi = (total_gmv / total_spend) if total_spend > 0 else 0
ctr = (total_click / total_imp) if total_imp > 0 else 0

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("总花费", f"¥{total_spend:,.2f}")
c2.metric("总成交金额", f"¥{total_gmv:,.2f}")
c3.metric("整体 ROI", f"{roi:.2f}")
c4.metric("总展现量", f"{int(total_imp):,}")
c5.metric("总点击量", f"{int(total_click):,}")
c6.metric("总成交笔数", f"{int(total_orders):,}")

st.divider()

# ---------- 5. 趋势图 ----------
if "日期" in dff.columns and dff["日期"].notna().any():
    daily = (
        dff.groupby("日期", as_index=False)[["花费", "总成交金额", "点击量", "展现量"]]
        .sum()
    )
    daily["ROI"] = np.where(daily["花费"] > 0, daily["总成交金额"] / daily["花费"], 0)

    tab1, tab2, tab3 = st.tabs(["💰 花费 / 成交", "📈 ROI 趋势", "👀 展现 / 点击"])

    with tab1:
        fig = px.line(daily, x="日期", y=["花费", "总成交金额"], markers=True,
                      title="每日花费与成交金额")
        st.plotly_chart(fig, use_container_width=True)
    with tab2:
        fig = px.line(daily, x="日期", y="ROI", markers=True, title="每日 ROI")
        st.plotly_chart(fig, use_container_width=True)
    with tab3:
        fig = px.bar(daily, x="日期", y=["展现量", "点击量"], barmode="group",
                     title="每日展现量与点击量")
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------- 6. 商品排行榜 ----------
st.subheader("🏆 商品排行榜")

metric_options = {
    "花费": "花费",
    "总成交金额": "总成交金额",
    "总成交笔数": "总成交笔数",
    "点击量": "点击量",
    "展现量": "展现量",
}
rank_metric = st.selectbox("按哪个指标排序?", list(metric_options.keys()), index=0)
rank_col = metric_options[rank_metric]

if rank_col in dff.columns and "主体名称" in dff.columns:
    rank_df = (
        dff.groupby(["主体ID", "主体名称"], as_index=False)[rank_col]
        .sum()
        .sort_values(rank_col, ascending=False)
        .head(top_n)
    )
    rank_df["短名"] = rank_df["主体名称"].str.slice(0, 20)
    fig = px.bar(rank_df, x=rank_col, y="短名", orientation="h",
                 title=f"Top {top_n} · 按{rank_metric}")
    fig.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------- 7. 明细表 ----------
st.subheader("📋 商品明细")

default_cols = [c for c in [
    "日期", "主体ID", "主体名称",
    "展现量", "点击量", "点击率", "花费", "平均点击花费",
    "总成交金额", "总成交笔数", "点击转化率", "投入产出比",
    "总购物车数", "加购率", "总收藏加购数", "拍下订单笔数", "拍下订单金额",
    "引导访问量", "成交新客数", "会员成交金额",
] if c in dff.columns]

selected_cols = st.multiselect(
    "选择要展示的列", options=list(dff.columns), default=default_cols
)

show_df = dff[selected_cols] if selected_cols else dff

st.dataframe(
    show_df,
    use_container_width=True,
    height=520,
    column_config={
        "花费": st.column_config.NumberColumn("花费", format="¥%.2f"),
        "总成交金额": st.column_config.NumberColumn("总成交金额", format="¥%.2f"),
        "平均点击花费": st.column_config.NumberColumn("平均点击花费", format="¥%.4f"),
        "点击率": st.column_config.NumberColumn("点击率", format="%.2f%%"),
        "点击转化率": st.column_config.NumberColumn("点击转化率", format="%.2f%%"),
        "加购率": st.column_config.NumberColumn("加购率", format="%.2f%%"),
        "投入产出比": st.column_config.NumberColumn("投入产出比", format="%.2f"),
    },
)

# 下载
csv = show_df.to_csv(index=False).encode("utf-8-sig")
st.download_button("⬇️ 下载当前筛选结果 CSV", csv, "filtered_report.csv", "text/csv")
