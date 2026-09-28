import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

st.set_page_config(page_title="淘宝万象推广数据分析台", layout="wide")
st.title("📊 淘宝万象推广 | 人群/关键词/全站 数据分析工作台")

# 上传文件组件
upload_file = st.file_uploader("上传万象推广导出Excel报表", type=["xlsx","xls"])

if upload_file is not None:
    df = pd.read_excel(upload_file)
    st.subheader("原始数据预览")
    st.dataframe(df.head(10))

    # 万象报表常用字段，和你的Excel表头对应
    needed_cols = ["推广类型","花费","展现量","点击量","点击率","成交金额","成交笔数","投产比","点击成本","加购数","收藏数"]
    exist_cols = [c for c in needed_cols if c in df.columns]
    df = df[exist_cols]

    # 侧边筛选
    st.sidebar.header("🔍筛选面板")
    if "推广类型" in df.columns:
        promo_type = st.sidebar.multiselect("推广类型（人群/关键词/全站）", df["推广类型"].unique(), default=df["推广类型"].unique())
        df_filter = df[df["推广类型"].isin(promo_type)]
    else:
        df_filter = df

    # 计算汇总指标
    st.subheader("📈核心汇总指标")
    total_cost = df_filter["花费"].sum() if "花费" in df_filter.columns else 0
    total_click = df_filter["点击量"].sum() if "点击量" in df_filter.columns else 0
    total_sale = df_filter["成交金额"].sum() if "成交金额" in df_filter.columns else 0
    total_order = df_filter["成交笔数"].sum() if "成交笔数" in df_filter.columns else 0
    avg_roi = total_sale / total_cost if total_cost>0 else 0

    col1,col2,col3,col4,col5 = st.columns(5)
    with col1:
        st.metric("总花费",f"{total_cost:.2f}")
    with col2:
        st.metric("总点击",f"{total_click:.0f}")
    with col3:
        st.metric("成交金额",f"{total_sale:.2f}")
    with col4:
        st.metric("成交笔数",f"{total_order:.0f}")
    with col5:
        st.metric("整体ROI",f"{avg_roi:.2f}")

    # 按推广类型分组统计
    st.subheader("📌按推广类型对比")
    if "推广类型" in df_filter.columns:
        group_df = df_filter.groupby("推广类型").agg({
            "花费":"sum",
            "点击量":"sum",
            "成交金额":"sum",
            "成交笔数":"sum"
        }).reset_index()
        group_df["ROI"] = group_df["成交金额"] / group_df["花费"]
        st.dataframe(group_df)

        fig1 = px.bar(group_df, x="推广类型", y="花费", title="各推广类型花费对比", text_auto=True)
        st.plotly_chart(fig1, use_container_width=True)
        fig2 = px.bar(group_df, x="推广类型", y="ROI", title="各推广类型ROI投产对比", text_auto=True)
        st.plotly_chart(fig2, use_container_width=True)

    # 明细表格
    st.subheader("明细数据")
    st.dataframe(df_filter)
    csv = df_filter.to_csv(index=False,encoding="utf-8-sig")
    st.download_button("📥导出筛选后数据csv", data=csv, file_name="万象推广筛选数据.csv")

else:
    st.info("请上传从淘宝万象后台导出的推广报表，报表最好包含【推广类型】列用来区分人群/关键词/全站")
