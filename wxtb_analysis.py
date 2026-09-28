import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime

st.set_page_config(page_title="万相台投放工作台V6｜字段自动适配", layout="wide")
st.title("📊万相台推广数据分析 & 自动优化策略V6")

# 会话存储：投放操作记录
if "action_log" not in st.session_state:
    st.session_state.action_log = pd.DataFrame(
        columns=["操作时间","推广类型","对象名称","执行动作","调整内容","备注"]
    )

# ----------------------侧边栏配置 ----------------------
with st.sidebar:
    st.header("⚙️阈值设置")
    roi_target = st.number_input("保本目标ROI", min_value=0.1, value=2.5, step=0.1)
    min_cost = st.number_input("最小有效花费(元)", min_value=0, value=30, step=5)
    max_cpc_warn = st.number_input("CPC过高预警(元)", min_value=0.0, value=2.0, step=0.1)
    min_ctr_warn = st.number_input("CTR过低预警", min_value=0.001, value=0.02, step=0.001)

    st.divider()
    st.header("🔍明细表格筛选")
    filter_level_list = st.multiselect("筛选策略等级",
        ["✅优质可放大","⚠️观察待优化","🔻高花费低ROI","🟡样本不足","🔴无成交"],
        default=["✅优质可放大","⚠️观察待优化","🔻高花费低ROI","🔴无成交"])

    upload_file = st.file_uploader("上传万相台Excel/Csv报表，多日请多选文件", type=["xlsx","xls","csv"], accept_multiple_files=True)

# ----------------------工具函数 ----------------------
def get_suggest(row, target_roi, min_spend):
    cost = row.get("花费",0)
    roi = row.get("ROI",0)
    if np.isinf(roi) or np.isnan(roi):
        roi = 0
    click = row.get("点击量",0)

    if cost < min_spend:
        return {"等级":"🟡样本不足","策略":"花费少继续观察","执行":"无操作"}
    if click <=0:
        return {"等级":"🟡零点击","策略":"有展现无点击，检查素材/人群","执行":"降出价或优化素材"}
    if roi >= target_roi:
        return {"等级":"✅优质可放大","策略":"投产达标，可以放大拿量","执行":"预算+10~20%，小幅抬高出价"}
    elif roi>0 and roi < target_roi*0.6 and cost> min_spend*3:
        return {"等级":"🔻高花费低ROI","策略":"花费高投产差，浪费预算","执行":"降价30%或直接暂停"}
    elif roi>0 and roi < target_roi:
        return {"等级":"⚠️观察待优化","策略":"略低于保本目标，小幅压价观察","执行":"出价下调10-20%观察2-3天"}
    else:
        return {"等级":"🔴无成交","策略":"有花费无订单产出","执行":"优先降价，无改善直接暂停"}

def get_warn(row, warn_max_cpc, warn_min_ctr):
    warns = []
    cpc = row.get("CPC",0)
    ctr = row.get("CTR",0)
    if cpc>warn_max_cpc:
        warns.append(f"CPC过高{cpc:.2f}")
    if 0<ctr<warn_min_ctr:
        warns.append(f"CTR过低{ctr:.2%}")
    if warns:
        return {"预警标记":"🚨异常","预警说明":"；".join(warns)}
    return {"预警标记":"✅正常","预警说明":"无异常"}

# ----------------------字段自动映射 ----------------------
def resolve_col(df, aliases):
    for a in aliases:
        if a in df.columns:
            return a
    return None

def read_all_files(uploaded_files):
    frames = []
    for f in uploaded_files:
        try:
            if f.name.endswith(".csv"):
                tmp = pd.read_csv(f)
            else:
                tmp = pd.read_excel(f)
            tmp.columns = [str(c).strip() for c in tmp.columns]
            frames.append(tmp)
        except Exception as e:
            st.warning(f"文件{f.name}读取失败:{e}")
    if frames:
        return pd.concat(frames, ignore_index=True)
    return None

# ----------------------主流程 ----------------------
df_raw = read_all_files(upload_file) if upload_file else None

if df_raw is not None:
    st.subheader("📄原始文件概览")
    st.metric("合并总行数", f"{len(df_raw):,}")
    st.markdown("识别到的全部字段：`" + ", ".join(list(df_raw.columns)) + "`")
    st.markdown("原始数据预览（最多8行）")
    st.dataframe(df_raw.head(8), hide_index=True)

    # =========字段映射成标准名 =========
    out = pd.DataFrame()
    out["日期"] = df_raw[resolve_col(df_raw, ["日期"])] if resolve_col(df_raw, ["日期"]) else pd.NA
    out["商品ID"] = df_raw[resolve_col(df_raw, ["主体ID","商品ID"])] if resolve_col(df_raw, ["主体ID","商品ID"]) else ""
    out["商品名称"] = df_raw[resolve_col(df_raw, ["主体名称","商品名称"])] if resolve_col(df_raw, ["主体名称","商品名称"]) else ""
    out["推广类型"] = df_raw[resolve_col(df_raw, ["推广类型"])] if resolve_col(df_raw, ["推广类型"]) else ""
    out["关键词"] = df_raw[resolve_col(df_raw, ["关键词"])] if resolve_col(df_raw, ["关键词"]) else ""
    out["人群包名称"] = df_raw[resolve_col(df_raw, ["人群包名称"])] if resolve_col(df_raw, ["人群包名称"]) else ""

    c_cost = resolve_col(df_raw, ["花费"])
    c_gmv = resolve_col(df_raw, ["总成交金额","成交金额","净成交金额"])
    c_order = resolve_col(df_raw, ["总成交笔数","成交笔数","净成交笔数"])
    c_click = resolve_col(df_raw, ["点击量"])
    c_show = resolve_col(df_raw, ["展现量"])
    c_cart = resolve_col(df_raw, ["总购物车数","加购数","购物车数"])
    c_fav = resolve_col(df_raw, ["收藏宝贝数","收藏数"])
    c_roi = resolve_col(df_raw, ["实际投产比","投产比"])
    c_cpc = resolve_col(df_raw, ["平均点击花费"])
    c_ctr = resolve_col(df_raw, ["点击率"])

    out["花费"] = pd.to_numeric(df_raw[c_cost], errors="coerce").fillna(0) if c_cost else 0
    out["成交金额"] = pd.to_numeric(df_raw[c_gmv], errors="coerce").fillna(0) if c_gmv else 0
    out["成交笔数"] = pd.to_numeric(df_raw[c_order], errors="coerce").fillna(0) if c_order else 0
    out["点击量"] = pd.to_numeric(df_raw[c_click], errors="coerce").fillna(0) if c_click else 0
    out["展现量"] = pd.to_numeric(df_raw[c_show], errors="coerce").fillna(0) if c_show else 0
    out["加购数"] = pd.to_numeric(df_raw[c_cart], errors="coerce").fillna(0) if c_cart else 0
    out["收藏数"] = pd.to_numeric(df_raw[c_fav], errors="coerce").fillna(0) if c_fav else 0

    # 衍生指标：报表自带ROI/CPC/CTR则直接用，没有则计算
    if c_roi:
        out["ROI"] = pd.to_numeric(df_raw[c_roi], errors="coerce").fillna(0)
        out["ROI"] = out["ROI"].replace([float("inf")], 0)
    else:
        out["ROI"] = np.where(out["花费"]>0, out["成交金额"]/out["花费"], 0)

    if c_cpc:
        out["CPC"] = pd.to_numeric(df_raw[c_cpc], errors="coerce").fillna(0)
    else:
        out["CPC"] = np.where(out["点击量"]>0, out["花费"]/out["点击量"], 0)

    if c_ctr:
        out["CTR"] = pd.to_numeric(df_raw[c_ctr], errors="coerce").fillna(0)
    else:
        out["CTR"] = np.where(out["展现量"]>0, out["点击量"]/out["展现量"], 0)

    df = out.reset_index(drop=True)

    # 提示：缺失关键字段
    if not c_gmv:
        st.warning("⚠️未识别到成交金额列（总成交金额/成交金额），成交和ROI将显示为0")
    if not c_cost:
        st.warning("⚠️未识别到【花费】列，无法计算")
    if not df["商品名称"].astype(str).str.strip().eq("").any():
        pass

    # 明细策略+预警
    suggest_out = [get_suggest(r, roi_target, min_cost) for _,r in df.iterrows()]
    warn_out = [get_warn(r, max_cpc_warn, min_ctr_warn) for _,r in df.iterrows()]
    df_detail = pd.concat([df.reset_index(drop=True), pd.DataFrame(suggest_out), pd.DataFrame(warn_out)], axis=1)

    # =========按商品汇总（主体=商品，一行一个商品） =========
    df_prod_sum = pd.DataFrame()
    group_keys = [k for k in ["商品ID","商品名称"] if k in df.columns]
    if len(group_keys)>=1:
        df_prod_sum = df.groupby(group_keys, dropna=False).agg(
            总花费=("花费","sum"),总成交金额=("成交金额","sum"),总点击=("点击量","sum"),
            总展现=("展现量","sum"),总成交笔数=("成交笔数","sum"),总加购=("加购数","sum"),总收藏=("收藏数","sum")
        ).reset_index()
        df_prod_sum["整体ROI"] = np.where(df_prod_sum["总花费"]>0, df_prod_sum["总成交金额"]/df_prod_sum["总花费"],0)
        df_prod_sum["平均CPC"] = np.where(df_prod_sum["总点击"]>0, df_prod_sum["总花费"]/df_prod_sum["总点击"],0)
        prod_sug = [get_suggest({"花费":r["总花费"],"ROI":r["整体ROI"],"点击量":r["总点击"]},roi_target,min_cost) for _,r in df_prod_sum.iterrows()]
        df_prod_sum = pd.concat([df_prod_sum, pd.DataFrame(prod_sug)],axis=1)

    # =========关键词汇总 =========
    df_kw_sum = pd.DataFrame()
    if "关键词" in df.columns and df["关键词"].astype(str).str.strip().ne("").any():
        df_kw_sum = df.groupby("关键词",dropna=False).agg(
            总花费=("花费","sum"),总成交金额=("成交金额","sum"),总点击=("点击量","sum"),总展现=("展现量","sum")
        ).reset_index()
        df_kw_sum["ROI"] = np.where(df_kw_sum["总花费"]>0, df_kw_sum["总成交金额"]/df_kw_sum["总花费"],0)
        kw_sug = [get_suggest({"花费":r["总花费"],"ROI":r["ROI"],"点击量":r["总点击"]},roi_target,min_cost) for _,r in df_kw_sum.iterrows()]
        df_kw_sum = pd.concat([df_kw_sum,pd.DataFrame(kw_sug)],axis=1)

    # =========人群汇总 =========
    df_crowd_sum = pd.DataFrame()
    if "人群包名称" in df.columns and df["人群包名称"].astype(str).str.strip().ne("").any():
        df_crowd_sum = df.groupby("人群包名称",dropna=False).agg(
            总花费=("花费","sum"),总成交金额=("成交金额","sum"),总点击=("点击量","sum"),总展现=("展现量","sum")
        ).reset_index()
        df_crowd_sum["ROI"] = np.where(df_crowd_sum["总花费"]>0, df_crowd_sum["总成交金额"]/df_crowd_sum["总花费"],0)
        crowd_sug = [get_suggest({"花费":r["总花费"],"ROI":r["ROI"],"点击量":r["总点击"]},roi_target,min_cost) for _,r in df_crowd_sum.iterrows()]
        df_crowd_sum = pd.concat([df_crowd_sum,pd.DataFrame(crowd_sug)],axis=1)

    # =========大盘指标 =========
    total_cost = df["花费"].sum()
    total_gmv = df["成交金额"].sum()
    total_roi = total_gmv/total_cost if total_cost>0 else 0
    total_click = df["点击量"].sum()

    st.markdown("---")
    c1,c2,c3,c4 = st.columns(4)
    with c1:st.metric("总花费",f"{total_cost:.2f}元")
    with c2:st.metric("总GMV",f"{total_gmv:.2f}元")
    with c3:st.metric("整体ROI",f"{total_roi:.2f}",delta=f"目标{roi_target}")
    with c4:st.metric("总点击",f"{int(total_click):,}")

    # 等级统计
    st.markdown("#### 🚨单元等级统计")
    stat_df = df_detail["等级"].value_counts().reset_index()
    stat_df.columns=["等级","数量"]
    st.dataframe(stat_df, hide_index=True)

    # 大盘诊断
    st.markdown("#### 📋投放大盘自动诊断")
    good_cnt = len(df_detail[df_detail["等级"]=="✅优质可放大"])
    bad_highcost = len(df_detail[df_detail["等级"]=="🔻高花费低ROI"])
    no_sale = len(df_detail[df_detail["等级"]=="🔴无成交"])
    if total_roi >= roi_target:
        diag = f"✅整体ROI({total_roi:.2f})达到保本目标{roi_target}。优质单元{good_cnt}个可放大；重点关注{bad_highcost}个高花费低投产单元控制预算。"
    else:
        diag = f"⚠️整体ROI({total_roi:.2f})低于保本目标{roi_target}。优先处理{bad_highcost}个高花费低ROI单元；优质{good_cnt}个可放大；{no_sale}个无成交建议降价或关停。"
    st.info(diag)

    # =========选项卡 =========
    tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs([
        "📦商品优化(图)",
        "🔑关键词优化(图)",
        "👥人群优化(图)",
        "🎯明细清单",
        "📈时间趋势",
        "📝操作记录"
    ])

    with tab1:
        st.subheader("📦商品维度优化（主体=商品，一行一个商品）")
        st.info("报表勾选了主体ID/主体名称才显示ID；这已经是按商品合并的正确维度，直接看哪个商品值得放大/暂停。")
        if len(df_prod_sum)>0:
            prod_eff = df_prod_sum[df_prod_sum["总花费"]>=min_cost].copy() if "总花费" in df_prod_sum.columns else df_prod_sum
            # 图1 花费TOP
            if len(prod_eff)>0 and "总花费" in prod_eff.columns:
                fig_p1 = px.bar(prod_eff.nlargest(15,"总花费"), x="总花费", y="商品名称", orientation="h", title="TOP15商品花费排行", text_auto=".1f")
                st.plotly_chart(fig_p1, use_container_width=True)
            # 图2 ROI
            if len(prod_eff)>0 and "整体ROI" in prod_eff.columns:
                fig_p2 = px.bar(prod_eff.sort_values("整体ROI",ascending=False).head(20), x="商品名称", y="整体ROI", title="商品ROI对比(红虚线=保本)", text_auto=".2f", color="整体ROI", color_continuous_scale="RdYlGn")
                fig_p2.add_hline(y=roi_target, line_dash="dash", line_color="red")
                fig_p2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_p2, use_container_width=True)
            # 图3 加购收藏潜力
            if len(prod_eff)>0 and "总加购" in prod_eff.columns:
                fig_p3 = px.bar(prod_eff.nlargest(15,"总加购"), x="商品名称", y=["总加购","总收藏"], barmode="group", title="TOP15商品加购/收藏(潜力款参考)")
                fig_p3.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_p3, use_container_width=True)
            # 表格
            show_p = group_keys + ["总花费","总成交金额","整体ROI","总点击","总加购","等级","策略","执行"]
            real_p = [x for x in show_p if x in df_prod_sum.columns]
            st.markdown("#### 商品优化执行清单")
            st.dataframe(df_prod_sum[real_p].round(2), use_container_width=True, hide_index=True)
            st.download_button("📥下载商品优化清单CSV", data=df_prod_sum.to_csv(index=False, encoding="utf-8-sig"), file_name="万相台_商品优化清单.csv")
        else:
            st.info("未识别到商品字段(主体名称/商品名称)，无法汇总")

    with tab2:
        if len(df_kw_sum)>0:
            st.subheader("🔑关键词优化")
            kw_eff = df_kw_sum[df_kw_sum["总花费"]>=min_cost].copy() if "总花费" in df_kw_sum.columns else df_kw_sum
            if len(kw_eff)>0:
                fig_k1 = px.bar(kw_eff.nlargest(15,"总花费"), x="总花费", y="关键词", orientation="h", title="TOP15关键词花费", text_auto=".1f")
                st.plotly_chart(fig_k1, use_container_width=True)
                fig_k2 = px.bar(kw_eff.sort_values("ROI",ascending=False).head(20), x="关键词", y="ROI", title="关键词ROI(红虚线=保本)", text_auto=".2f")
                fig_k2.add_hline(y=roi_target, line_dash="dash", line_color="red")
                fig_k2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_k2, use_container_width=True)
            st.markdown("#### 关键词优化清单")
            kw_show = ["关键词","总花费","总成交金额","ROI","CPC","等级","策略","执行"]
            kw_real = [c for c in kw_show if c in df_kw_sum.columns]
            st.dataframe(df_kw_sum[kw_real].round(2), use_container_width=True, hide_index=True)
            st.download_button("📥下载关键词清单", data=df_kw_sum.to_csv(index=False, encoding="utf-8-sig"), file_name="万相台_关键词.csv")
        else:
            st.info("报表无【关键词】列，请上传关键词推广报表")

    with tab3:
        if len(df_crowd_sum)>0:
            st.subheader("👥人群优化")
            crowd_eff = df_crowd_sum[df_crowd_sum["总花费"]>=min_cost].copy() if "总花费" in df_crowd_sum.columns else df_crowd_sum
            if len(crowd_eff)>0:
                fig_c1 = px.bar(crowd_eff.sort_values("总花费",ascending=False).head(15), x="人群包名称", y=["总花费","总成交金额"], barmode="group", title="TOP15人群花费vs成交")
                fig_c1.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_c1, use_container_width=True)
                fig_c2 = px.bar(crowd_eff.sort_values("ROI",ascending=False).head(20), x="人群包名称", y="ROI", title="人群ROI(红虚线=保本)", text_auto=".2f")
                fig_c2.add_hline(y=roi_target, line_dash="dash", line_color="red")
                fig_c2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_c2, use_container_width=True)
            st.markdown("#### 人群优化清单")
            cr_show = ["人群包名称","总花费","总成交金额","ROI","CPC","等级","策略","执行"]
            cr_real = [c for c in cr_show if c in df_crowd_sum.columns]
            st.dataframe(df_crowd_sum[cr_real].round(2), use_container_width=True, hide_index=True)
            st.download_button("📥下载人群清单", data=df_crowd_sum.to_csv(index=False, encoding="utf-8-sig"), file_name="万相台_人群.csv")
        else:
            st.info("报表无【人群包名称】列，请上传人群运营报表")

    with tab4:
        df_filter_view = df_detail[df_detail["等级"].isin(filter_level_list)]
        show_d = ["日期","商品ID","商品名称","推广类型","关键词","人群包名称","花费","成交金额","ROI","CPC","CTR","加购数","收藏数","预警标记","等级","策略","执行"]
        d_real = [x for x in show_d if x in df_filter_view.columns]
        st.dataframe(df_filter_view[d_real].round(2), use_container_width=True, hide_index=True)
        st.download_button("📥下载筛选后明细", data=df_filter_view.to_csv(index=False, encoding="utf-8-sig"), file_name="万相台_筛选明细.csv")

    with tab5:
        st.subheader("📈日度时间趋势")
        if "日期" in df.columns and pd.notna(df["日期"]).any():
            df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
            day_agg = {}
            day_agg["花费"]=("花费","sum")
            if "成交金额" in df.columns: day_agg["成交金额"]=("成交金额","sum")
            if "点击量" in df.columns: day_agg["点击量"]=("点击量","sum")
            if "展现量" in df.columns: day_agg["展现量"]=("展现量","sum")
            df_day = df.groupby("日期").agg(**day_agg).reset_index()
            if "花费" in df_day.columns and "成交金额" in df_day.columns:
                df_day["ROI"] = np.where(df_day["花费"]>0, df_day["成交金额"]/df_day["花费"],0)
            fig_t1 = px.line(df_day, x="日期", y="花费", markers=True, title="每日花费")
            st.plotly_chart(fig_t1, use_container_width=True)
            if "ROI" in df_day.columns:
                fig_t2 = px.line(df_day, x="日期", y="ROI", markers=True, title="每日ROI(红虚线=保本)")
                fig_t2.add_hline(y=roi_target, line_dash="dash", line_color="red")
                st.plotly_chart(fig_t2, use_container_width=True)
        else:
            st.warning("报表缺少【日期】字段，无法绘制趋势")

    with tab6:
        st.markdown("### 📝投放操作记录")
        st.info("记录你在后台做的调整，刷新网页会丢失，请及时导出。")
        with st.form("action_log_form"):
            f1,f2,f3 = st.columns(3)
            with f1:
                t1 = st.text_input("推广类型")
                t2 = st.text_input("对象名称（商品/关键词/人群）")
            with f2:
                act = st.selectbox("执行动作",["提升预算","降低预算","提高出价","降低出价","暂停单元","开启单元","修改创意","其他"])
            with f3:
                adj = st.text_input("调整内容，例：出价-20%")
                note = st.text_input("备注")
            sub = st.form_submit_button("✅保存操作记录")
            if sub:
                new_log = {"操作时间":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"推广类型":t1,"对象名称":t2,"执行动作":act,"调整内容":adj,"备注":note}
                st.session_state.action_log = pd.concat([st.session_state.action_log, pd.DataFrame([new_log])], ignore_index=True)
                st.success("已保存！")
        st.dataframe(st.session_state.action_log, hide_index=True, use_container_width=True)
        st.download_button("📥导出全部操作记录", data=st.session_state.action_log.to_csv(index=False, encoding="utf-8-sig"), file_name="万相台_操作记录.csv")

else:
    st.info("👈上传万相台导出的Excel/Csv报表，代码会自动识别主体ID/总成交金额/实际投产比等万相台真实字段，无需手动改表头。")
