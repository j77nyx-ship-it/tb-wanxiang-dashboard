import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

st.set_page_config(page_title="万相台无界｜精细化投放工作台", layout="wide")
st.title("📊万相台无界推广数据分析 & 自动优化策略")

# ----------------------侧边栏参数配置（运营自定义阈值）----------------------
with st.sidebar:
    st.header("⚙️投放阈值设置")
    roi_target = st.number_input("保本目标ROI", min_value=0.1, value=2.5, step=0.1, help="根据毛利率算出保本ROI")
    min_cost = st.number_input("最小有效消耗(元)", min_value=0, value=30, step=5, help="低于该消耗的数据不参与策略判定")
    upload_file = st.file_uploader("上传万相台Excel/Csv报表", type=["xlsx","xls","csv"])

# ----------------------工具函数：生成单条策略建议----------------------
def get_optimize_suggest(row, target_roi, min_spend):
    cost = row["消耗"]
    roi = row["ROI"] if ("ROI" in row and not np.isinf(row["ROI"])) else 0
    click = row.get("点击量",0)

    if cost < min_spend:
        return {"等级":"🟡样本不足","策略":"消耗太少，继续观察，暂不操作","执行":"无操作"}
    if click <=0:
        return {"等级":"🟡零点击","策略":"有展现无点击，检查创意/选词/人群精准度","执行":"优化素材，或降低出价"}

    # 优质：ROI大于目标
    if roi >= target_roi:
        return {"等级":"✅优质可放大","策略":"投产达标，建议逐步提升预算/出价，放大拿量","执行":"+10%~20%预算，小幅提高出价"}
    # 高消耗，严重不达标
    elif roi>0 and roi < target_roi*0.6 and cost> min_spend*3:
        return {"等级":"🔻高消耗低ROI","策略":"花钱多投产差，浪费预算","执行":"降低出价30% 或直接暂停"}
    # 中等待优化
    elif roi>0 and roi < target_roi:
        return {"等级":"⚠️观察待优化","策略":"投产略低于目标，小幅压出价观察2‑3天","执行":"出价下调10‑20%，继续观察数据"}
    else:
        return {"等级":"🔴无成交","策略":"有消耗完全没产出","执行":"优先降价，无改善直接暂停"}

# ----------------------读取文件----------------------
if upload_file is not None:
    if upload_file.name.endswith(".csv"):
        df = pd.read_csv(upload_file)
    else:
        df = pd.read_excel(upload_file)

    st.subheader("原始数据预览")
    st.dataframe(df.head(6), hide_index=True)

    # 万相台原生字段映射：【消耗】而不是花费
    map_dict = {
        "消耗":"消耗",
        "展现量":"展现量",
        "点击量":"点击量",
        "成交金额":"成交金额",
        "成交笔数":"成交笔数",
        "推广类型":"推广类型",
        "关键词":"关键词",
        "人群包名称":"人群包名称",
        "商品名称":"商品名称"
    }
    exist_cols = [c for c in map_dict.keys() if c in df.columns]
    df = df[exist_cols].copy()

    # 计算衍生指标
    df["消耗"] = pd.to_numeric(df["消耗"], errors="coerce").fillna(0)
    df["展现量"] = pd.to_numeric(df["展现量"], errors="coerce").fillna(0)
    df["点击量"] = pd.to_numeric(df["点击量"], errors="coerce").fillna(0)
    df["成交金额"] = pd.to_numeric(df["成交金额"], errors="coerce").fillna(0)
    df["成交笔数"] = pd.to_numeric(df["成交笔数"], errors="coerce").fillna(0)

    df["CPC"] = np.where(df["点击量"]>0, df["消耗"]/df["点击量"],0)
    df["ROI"] = np.where(df["消耗"]>0, df["成交金额"]/df["消耗"],0)
    df["CTR"] = np.where(df["展现量"]>0, df["点击量"]/df["展现量"],0)

    # 生成优化策略
    suggest_list = []
    for _,row in df.iterrows():
        s = get_optimize_suggest(row, roi_target, min_cost)
        suggest_list.append(s)
    df_suggest = pd.DataFrame(suggest_list)
    df_out = pd.concat([df.reset_index(drop=True), df_suggest], axis=1)

    # ----------------------大盘总览指标----------------------
    st.markdown("---")
    st.subheader("📈大盘核心指标")
    total_cost = df["消耗"].sum()
    total_sale = df["成交金额"].sum()
    total_click = df["点击量"].sum()
    total_order = df["成交笔数"].sum()
    total_roi = total_sale / total_cost if total_cost>0 else 0

    c1,c2,c3,c4,c5 = st.columns(5)
    with c1:st.metric("总消耗",f"{total_cost:.2f}元")
    with c2:st.metric("总成交GMV",f"{total_sale:.2f}元")
    with c3:st.metric("整体ROI",f"{total_roi:.2f}",delta=f"目标{roi_target}")
    with c4:st.metric("总点击",f"{int(total_click):,}")
    with c5:st.metric("成交订单",f"{int(total_order)}单")

    # 如果存在推广类型，做渠道对比
    if "推广类型" in df.columns:
        st.markdown("---")
        st.subheader("📌分渠道对比【关键词 / 人群运营 / 全站推广】")
        group = df.groupby("推广类型").agg({
            "消耗":"sum",
            "成交金额":"sum",
            "点击量":"sum"
        }).reset_index()
        group["ROI"] = group["成交金额"]/group["消耗"]
        st.dataframe(group.round(2), hide_index=True)
        fig_bar = px.bar(group, x="推广类型", y="ROI", text_auto=".2f", title="各渠道ROI对比")
        fig_bar.add_hline(y=roi_target, line_dash="dash", line_color="red",annotation_text="保本ROI")
        st.plotly_chart(fig_bar, use_container_width=True)

    # ----------------------自动优化策略清单【核心新增】----------------------
    st.markdown("---")
    st.subheader("🎯投放自动优化执行清单（直接照着万相台后台操作）")
    filter_level = st.multiselect("筛选策略等级",options=["✅优质可放大","⚠️观察待优化","🔻高消耗低ROI","🟡样本不足","🔴无成交"],
                                  default=["✅优质可放大","⚠️观察待优化","🔻高消耗低ROI","🔴无成交"])
    df_view = df_out[df_out["等级"].isin(filter_level)]

    show_cols = ["推广类型","关键词","人群包名称","商品名称","消耗","成交金额","ROI","CPC","等级","策略","执行"]
    real_show = [x for x in show_cols if x in df_view.columns]
    st.dataframe(df_view[real_show].round(2), use_container_width=True, hide_index=True)

    # 导出优化清单
    csv_data = df_view.to_csv(index=False,encoding="utf‑8‑sig")
    st.download_button("📥下载优化执行清单CSV",data=csv_data,file_name="万相台_优化执行清单.csv")

    # 分级统计看板
    st.markdown("#### 各等级数量统计")
    stat_df = df_out["等级"].value_counts().reset_index()
    stat_df.columns=["等级","条目数"]
    st.dataframe(stat_df, hide_index=True)

    st.markdown("""
> 💡策略逻辑说明：
> 1. ✅优质可放大：ROI≥保本ROI，消耗达标 → 预算+10‑20%，小幅抬高出价放量
> 2. ⚠️观察待优化：ROI略低于保本线 → 出价下调10‑20%，观察2‑3天数据再动
> 3. 🔻高消耗低ROI：消耗大，ROI远低于保本 → 大幅降价或者直接暂停，释放预算给优质单元
> 4. 🔴无成交：有消耗完全没订单 → 优先降价，无改善直接关停
> 5. 🟡样本不足：消耗低于阈值，数据太少，不做任何操作，继续积累数据
""")

else:
    st.info("👈左侧上传万相台导出报表，支持关键词/人群/全站明细，无需手动修改Excel表头")
