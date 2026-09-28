import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime

# ===================== 页面初始化 & 会话状态初始化 =====================
st.set_page_config(page_title="万相台无界｜精细化投放工作台V2", layout="wide")

# 初始化会话存储：优化动作记录表（网页内存，刷新清空，可以导出保存）
if "optimize_log" not in st.session_state:
    st.session_state["optimize_log"] = pd.DataFrame(
        columns=["记录时间","推广类型","对象名称","执行动作","调整内容","备注"]
    )

st.title("📊万相台无界推广数据分析 & 自动优化策略V2")

# ----------------------侧边栏参数配置----------------------
with st.sidebar:
    st.header("⚙️投放阈值设置")
    roi_target = st.number_input("保本目标ROI", min_value=0.1, value=2.5, step=0.1, help="根据毛利率算出保本ROI")
    min_cost = st.number_input("最小有效花费(元)", min_value=0, value=30, step=5, help="低于该花费的数据不参与策略判定")

    st.divider()
    st.subheader("🚨异常预警阈值")
    max_cpc_warn = st.number_input("CPC过高预警(元)", min_value=0.0, value=2.0, step=0.1, help="单次点击成本超过该值标记预警")
    min_ctr_warn = st.number_input("CTR过低预警(小数)", min_value=0.001, value=0.02, step=0.001, help="点击率低于该值标记预警，一般搜索2%-5%")

    st.divider()
    st.subheader("📂多文件上传（支持多日报表做趋势）")
    upload_files = st.file_uploader(
        "上传万相台Excel/Csv报表（可多选多份日期报表）",
        type=["xlsx","xls","csv"],
        accept_multiple_files=True
    )

# ----------------------工具函数1：投产优化策略----------------------
def get_optimize_suggest(row, target_roi, min_spend):
    cost = row["花费"]
    roi = row["ROI"] if ("ROI" in row and not np.isinf(row["ROI"])) else 0
    click = row.get("点击量",0)

    if cost < min_spend:
        return {"等级":"🟡样本不足","策略":"花费太少，继续观察，暂不操作","执行":"无操作"}
    if click <=0:
        return {"等级":"🟡零点击","策略":"有展现无点击，检查创意/选词/人群精准度","执行":"优化素材，或降低出价"}

    if roi >= target_roi:
        return {"等级":"✅优质可放大","策略":"投产达标，建议逐步提升预算/出价，放大拿量","执行":"+10%~20%预算，小幅提高出价"}
    elif roi>0 and roi < target_roi*0.6 and cost> min_spend*3:
        return {"等级":"🔻高花费低ROI","策略":"花钱多投产差，浪费预算","执行":"降低出价30% 或直接暂停"}
    elif roi>0 and roi < target_roi:
        return {"等级":"⚠️观察待优化","策略":"投产略低于目标，小幅压出价观察2-3天","执行":"出价下调10-20%，继续观察数据"}
    else:
        return {"等级":"🔴无成交","策略":"有花费完全没产出","执行":"优先降价，无改善直接暂停"}

# ----------------------工具函数2：CPC&CTR异常预警----------------------
def get_warn_info(row, warn_max_cpc, warn_min_ctr):
    warn_list = []
    cpc = row.get("CPC",0)
    ctr = row.get("CTR",0)
    if cpc > warn_max_cpc:
        warn_list.append(f"CPC过高{cpc:.2f}元")
    if 0<ctr < warn_min_ctr:
        warn_list.append(f"CTR过低{ctr:.2%}")
    if len(warn_list)>0:
        return {"预警标记":"🚨异常","预警说明":"；".join(warn_list)}
    else:
        return {"预警标记":"✅正常","预警说明":"无异常"}

# ----------------------读取全部上传文件合并----------------------
df_all_list = []
if upload_files:
    for f in upload_files:
        try:
            if f.name.endswith(".csv"):
                df_tmp = pd.read_csv(f)
            else:
                df_tmp = pd.read_excel(f)
            df_all_list.append(df_tmp)
        except Exception as e:
            st.warning(f"文件{f.name}读取失败：{str(e)}")

if len(df_all_list)>0:
    df_raw = pd.concat(df_all_list, ignore_index=True)
    st.subheader("原始数据预览")
    st.dataframe(df_raw.head(6), hide_index=True)

    # 字段映射：全部改为【花费】
    map_dict = {
        "日期":"日期",
        "花费":"花费",
        "展现量":"展现量",
        "点击量":"点击量",
        "成交金额":"成交金额",
        "成交笔数":"成交笔数",
        "推广类型":"推广类型",
        "关键词":"关键词",
        "人群包名称":"人群包名称",
        "商品名称":"商品名称"
    }
    exist_cols = [c for c in map_dict.keys() if c in df_raw.columns]
    df = df_raw[exist_cols].copy()

    # 数值清洗
    df["花费"] = pd.to_numeric(df["花费"], errors="coerce").fillna(0)
    df["展现量"] = pd.to_numeric(df["展现量"], errors="coerce").fillna(0)
    df["点击量"] = pd.to_numeric(df["点击量"], errors="coerce").fillna(0)
    df["成交金额"] = pd.to_numeric(df["成交金额"], errors="coerce").fillna(0)
    df["成交笔数"] = pd.to_numeric(df["成交笔数"], errors="coerce").fillna(0)

    df["CPC"] = np.where(df["点击量"]>0, df["花费"]/df["点击量"],0)
    df["ROI"] = np.where(df["花费"]>0, df["成交金额"]/df["花费"],0)
    df["CTR"] = np.where(df["展现量"]>0, df["点击量"]/df["展现量"],0)

    # 生成投产策略
    suggest_list = []
    warn_list_out = []
    for _,row in df.iterrows():
        s = get_optimize_suggest(row, roi_target, min_cost)
        w = get_warn_info(row, max_cpc_warn, min_ctr_warn)
        suggest_list.append(s)
        warn_list_out.append(w)
    df_suggest = pd.DataFrame(suggest_list)
    df_warn = pd.DataFrame(warn_list_out)
    df_out = pd.concat([df.reset_index(drop=True), df_suggest, df_warn], axis=1)

    # =========大盘总览指标=========
    st.markdown("---")
    st.subheader("📈大盘核心指标")
    total_cost = df["花费"].sum()
    total_sale = df["成交金额"].sum()
    total_click = df["点击量"].sum()
    total_order = df["成交笔数"].sum()
    total_roi = total_sale / total_cost if total_cost>0 else 0

    c1,c2,c3,c4,c5 = st.columns(5)
    with c1:st.metric("总花费",f"{total_cost:.2f}元")
    with c2:st.metric("总成交GMV",f"{total_sale:.2f}元")
    with c3:st.metric("整体ROI",f"{total_roi:.2f}",delta=f"目标{roi_target}")
    with c4:st.metric("总点击",f"{int(total_click):,}")
    with c5:st.metric("成交订单",f"{int(total_order)}单")

    # =========日度趋势分析（多日报表）=========
    st.markdown("---")
    st.subheader("📉日度趋势分析（花费 / ROI / CPC / CTR）")
    if "日期" in df.columns:
        # 日期转换
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
        df_day = df.groupby("日期").agg({
            "花费":"sum",
            "成交金额":"sum",
            "点击量":"sum",
            "展现量":"sum"
        }).reset_index()
        df_day["ROI"] = np.where(df_day["花费"]>0, df_day["成交金额"]/df_day["花费"],0)
        df_day["CPC"] = np.where(df_day["点击量"]>0, df_day["花费"]/df_day["点击量"],0)
        df_day["CTR"] = np.where(df_day["展现量"]>0, df_day["点击量"]/df_day["展现量"],0)

        fig_trend = make_subplots(
            rows=2, cols=2,
            subplot_titles=("日花费","日ROI","平均CPC","点击率CTR"),
            shared_xaxes=True
        )
        fig_trend.add_trace(go.Scatter(x=df_day["日期"], y=df_day["花费"], mode="lines+markers", name="花费"), row=1, col=1)
        fig_trend.add_trace(go.Scatter(x=df_day["日期"], y=df_day["ROI"], mode="lines+markers", name="ROI"), row=1, col=2)
        fig_trend.add_hline(y=roi_target, line_dash="dash", line_color="red", row=1, col=2)
        fig_trend.add_trace(go.Scatter(x=df_day["日期"], y=df_day["CPC"], mode="lines+markers", name="CPC"), row=2, col=1)
        fig_trend.add_trace(go.Scatter(x=df_day["日期"], y=df_day["CTR"], mode="lines+markers", name="CTR"), row=2, col=2)
        fig_trend.update_layout(height=600)
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("⚠️你的报表缺少【日期】字段，无法绘制日趋势；导出报表时勾选导出日期列")

    # =========分渠道对比=========
    if "推广类型" in df.columns:
        st.markdown("---")
        st.subheader("📌分渠道对比【关键词 / 人群运营 / 全站推广】")
        group = df.groupby("推广类型").agg({
            "花费":"sum",
            "成交金额":"sum",
            "点击量":"sum"
        }).reset_index()
        group["ROI"] = group["成交金额"]/group["花费"]
        st.dataframe(group.round(2), hide_index=True)
        fig_bar = px.bar(group, x="推广类型", y="ROI", text_auto=".2f", title="各渠道ROI对比")
        fig_bar.add_hline(y=roi_target, line_dash="dash", line_color="red",annotation_text="保本ROI")
        st.plotly_chart(fig_bar, use_container_width=True)

    # =========自动优化执行清单（带预警）=========
    st.markdown("---")
    st.subheader("🎯投放自动优化执行清单（含CPC/CTR异常预警）")
    filter_level = st.multiselect("筛选策略等级",options=["✅优质可放大","⚠️观察待优化","🔻高花费低ROI","🟡样本不足","🔴无成交"],
                                  default=["✅优质可放大","⚠️观察待优化","🔻高花费低ROI","🔴无成交"])
    df_view = df_out[df_out["等级"].isin(filter_level)]

    show_cols = ["推广类型","关键词","人群包名称","商品名称","花费","成交金额","ROI","CPC","CTR","预警标记","预警说明","等级","策略","执行"]
    real_show = [x for x in show_cols if x in df_view.columns]
    st.dataframe(df_view[real_show].round(2), use_container_width=True, hide_index=True)

    csv_data = df_view.to_csv(index=False,encoding="utf-8-sig")
    st.download_button("📥下载优化执行清单CSV",data=csv_data,file_name="万相台_优化执行清单.csv")

    st.markdown("#### 各等级数量统计")
    stat_df = df_out["等级"].value_counts().reset_index()
    stat_df.columns=["等级","条目数"]
    st.dataframe(stat_df, hide_index=True)

    # =========【新增】优化动作记录模块=========
    st.markdown("---")
    st.subheader("📝优化动作记录（记录你后台做的调整，用于跟踪效果）")
    with st.form("log_form"):
        f1,f2,f3 = st.columns(3)
        with f1:
            log_promo_type = st.text_input("推广类型（关键词/人群/全站）")
            log_obj_name = st.text_input("调整对象名称（关键词/人群包/商品）")
        with f2:
            action_select = st.selectbox("执行动作",["提升预算","降低出价","提高出价","降低预算","暂停单元","开启单元","修改创意","其他"])
        with f3:
            adjust_text = st.text_input("调整内容，例：出价-20%，预算+150")
            note_text = st.text_input("备注，例：预计观察3天数据")
        submitted = st.form_submit_button("✅保存本次操作记录")
        if submitted:
            new_row = {
                "记录时间":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "推广类型":log_promo_type,
                "对象名称":log_obj_name,
                "执行动作":action_select,
                "调整内容":adjust_text,
                "备注":note_text
            }
            st.session_state["optimize_log"] = pd.concat([
                st.session_state["optimize_log"],
                pd.DataFrame([new_row])
            ], ignore_index=True)
            st.success("操作记录已写入会话！注意页面刷新记录会丢失，请及时导出！")

    st.dataframe(st.session_state["optimize_log"], hide_index=True, use_container_width=True)
    log_csv = st.session_state["optimize_log"].to_csv(index=False,encoding="utf-8-sig")
    st.download_button("📥导出全部操作记录CSV", data=log_csv, file_name="万相台_投放操作记录.csv")

    st.markdown("""
> 💡策略&预警逻辑说明：
> 1. ✅优质可放大：ROI≥保本ROI，花费达标 → 预算+10-20%，小幅抬高出价放量
> 2. ⚠️观察待优化：ROI略低于保本线 → 出价下调10-20%，观察2-3天
> 3. 🔻高花费低ROI：花费大ROI远低于保本 → 大幅降价或直接暂停
> 4. 🔴无成交：有花费无订单 → 优先降价，无效关停
> 5. 🟡样本不足：花费低于阈值，不操作
> 6. 🚨异常预警：CPC过高 / CTR过低自动标记，检查出价、素材、人群精准度
> 7. 📉趋势图需要报表自带【日期】列，多份不同日期报表一起上传生成日度走势
> 8. 📝操作记录保存在网页内存，**页面刷新全部清空，务必随时导出CSV做本地保存**
""")

else:
    st.info("👈左侧上传万相台导出报表，支持多选多份报表做时间趋势，Excel表头列名必须为：花费")
