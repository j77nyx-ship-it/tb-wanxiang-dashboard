import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime

st.set_page_config(page_title="万相台投放工作台V3", layout="wide")
st.title("📊万相台推广数据分析 & 自动优化策略V3")

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

    upload_file = st.file_uploader("上传万相台Excel/Csv报表", type=["xlsx","xls","csv"], accept_multiple_files=True)

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

# ----------------------读取文件 ----------------------
df_raw_list = []
if upload_file:
    for f in upload_file:
        try:
            if f.name.endswith(".csv"):
                tmp = pd.read_csv(f)
            else:
                tmp = pd.read_excel(f)
            # 表头去空格容错
            tmp.columns = [str(c).strip() for c in tmp.columns]
            df_raw_list.append(tmp)
        except Exception as e:
            st.warning(f"文件{f.name}读取失败:{e}")

if len(df_raw_list)>0:
    df_raw = pd.concat(df_raw_list, ignore_index=True)
    st.subheader("原始数据预览")
    st.dataframe(df_raw.head(6), hide_index=True)

    keep_cols = ["日期","花费","展现量","点击量","成交金额","成交笔数","加购数","收藏数","推广类型","关键词","人群包名称","商品名称","商品ID"]
    exist_cols = [c for c in keep_cols if c in df_raw.columns]
    df = df_raw[exist_cols].copy()

    num_cols = ["花费","展现量","点击量","成交金额","成交笔数","加购数","收藏数"]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    #衍生指标
    df["CPC"] = np.where(df["点击量"]>0, df["花费"]/df["点击量"],0)
    if "成交金额" in df.columns and "花费" in df.columns:
        df["ROI"] = np.where(df["花费"]>0, df["成交金额"]/df["花费"],0)
    else:
        df["ROI"] = 0
    df["CTR"] = np.where(df["展现量"]>0, df["点击量"]/df["展现量"],0)

    #明细策略+预警
    suggest_out = [get_suggest(r, roi_target, min_cost) for _,r in df.iterrows()]
    warn_out = [get_warn(r, max_cpc_warn, min_ctr_warn) for _,r in df.iterrows()]
    df_s = pd.DataFrame(suggest_out)
    df_w = pd.DataFrame(warn_out)
    df_detail = pd.concat([df.reset_index(drop=True), df_s, df_w], axis=1)

    # =========商品汇总 =========
    group_keys_prod = []
    if "商品ID" in df.columns:
        group_keys_prod.append("商品ID")
    if "商品名称" in df.columns:
        group_keys_prod.append("商品名称")
    df_prod_sum = pd.DataFrame()
    if len(group_keys_prod)>=1:
        agg_dict = {}
        if "花费" in df.columns:
            agg_dict["总花费"]=("花费","sum")
        if "成交金额" in df.columns:
            agg_dict["总成交金额"]=("成交金额","sum")
        if "点击量" in df.columns:
            agg_dict["总点击"]=("点击量","sum")
        if "展现量" in df.columns:
            agg_dict["总展现"]=("展现量","sum")
        if "成交笔数" in df.columns:
            agg_dict["总成交笔数"]=("成交笔数","sum")
        if agg_dict:
            df_prod_sum = df.groupby(group_keys_prod, dropna=False).agg(**agg_dict).reset_index()
            if "总花费" in df_prod_sum.columns and "总成交金额" in df_prod_sum.columns:
                df_prod_sum["整体ROI"] = np.where(df_prod_sum["总花费"]>0, df_prod_sum["总成交金额"]/df_prod_sum["总花费"],0)
            if "总点击" in df_prod_sum.columns and "总花费" in df_prod_sum.columns:
                df_prod_sum["平均CPC"] = np.where(df_prod_sum["总点击"]>0, df_prod_sum["总花费"]/df_prod_sum["总点击"],0)
            prod_sug = []
            for _,r in df_prod_sum.iterrows():
                d = {
                    "花费":r.get("总花费",0),
                    "ROI":r.get("整体ROI",0),
                    "点击量":r.get("总点击",0)
                }
                prod_sug.append(get_suggest(d,roi_target,min_cost))
            df_prod_sum = pd.concat([df_prod_sum, pd.DataFrame(prod_sug)],axis=1)

    # =========关键词汇总 =========
    df_kw_sum = pd.DataFrame()
    if "关键词" in df.columns:
        agg_kw = {}
        if "花费" in df.columns: agg_kw["总花费"]=("花费","sum")
        if "成交金额" in df.columns: agg_kw["总成交金额"]=("成交金额","sum")
        if "点击量" in df.columns: agg_kw["总点击"]=("点击量","sum")
        if "展现量" in df.columns: agg_kw["总展现"]=("展现量","sum")
        if agg_kw:
            df_kw_sum = df.groupby("关键词",dropna=False).agg(**agg_kw).reset_index()
            if "总花费" in df_kw_sum.columns and "总成交金额" in df_kw_sum.columns:
                df_kw_sum["ROI"] = np.where(df_kw_sum["总花费"]>0, df_kw_sum["总成交金额"]/df_kw_sum["总花费"],0)
            if "总点击" in df_kw_sum.columns and "总花费" in df_kw_sum.columns:
                df_kw_sum["CPC"] = np.where(df_kw_sum["总点击"]>0, df_kw_sum["总花费"]/df_kw_sum["总点击"],0)
            kw_sug = []
            for _,r in df_kw_sum.iterrows():
                d={"花费":r.get("总花费",0),"ROI":r.get("ROI",0),"点击量":r.get("总点击",0)}
                kw_sug.append(get_suggest(d,roi_target,min_cost))
            df_kw_sum = pd.concat([df_kw_sum,pd.DataFrame(kw_sug)],axis=1)

    # =========人群汇总 =========
    df_crowd_sum = pd.DataFrame()
    if "人群包名称" in df.columns:
        agg_crowd = {}
        if "花费" in df.columns: agg_crowd["总花费"]=("花费","sum")
        if "成交金额" in df.columns: agg_crowd["总成交金额"]=("成交金额","sum")
        if "点击量" in df.columns: agg_crowd["总点击"]=("点击量","sum")
        if "展现量" in df.columns: agg_crowd["总展现"]=("展现量","sum")
        if agg_crowd:
            df_crowd_sum = df.groupby("人群包名称",dropna=False).agg(**agg_crowd).reset_index()
            if "总花费" in df_crowd_sum.columns and "总成交金额" in df_crowd_sum.columns:
                df_crowd_sum["ROI"] = np.where(df_crowd_sum["总花费"]>0, df_crowd_sum["总成交金额"]/df_crowd_sum["总花费"],0)
            if "总点击" in df_crowd_sum.columns and "总花费" in df_crowd_sum.columns:
                df_crowd_sum["CPC"] = np.where(df_crowd_sum["总点击"]>0, df_crowd_sum["总花费"]/df_crowd_sum["总点击"],0)
            crowd_sug = []
            for _,r in df_crowd_sum.iterrows():
                d={"花费":r.get("总花费",0),"ROI":r.get("ROI",0),"点击量":r.get("总点击",0)}
                crowd_sug.append(get_suggest(d,roi_target,min_cost))
            df_crowd_sum = pd.concat([df_crowd_sum,pd.DataFrame(crowd_sug)],axis=1)

    # =========大盘指标【修复：全部做列存在判断】 =========
    total_cost = df["花费"].sum() if "花费" in df.columns else 0
    total_gmv = df["成交金额"].sum() if "成交金额" in df.columns else 0
    total_roi = total_gmv / total_cost if total_cost>0 else 0
    total_click = df["点击量"].sum() if "点击量" in df.columns else 0

    st.markdown("---")
    c1,c2,c3,c4 = st.columns(4)
    with c1:st.metric("总花费",f"{total_cost:.2f}元")
    with c2:st.metric("总GMV",f"{total_gmv:.2f}元")
    with c3:st.metric("整体ROI",f"{total_roi:.2f}",delta=f"目标{roi_target}")
    with c4:st.metric("总点击",f"{int(total_click):,}")

    # 异常等级统计卡片
    st.markdown("#### 🚨单元等级统计")
    stat_df = df_detail["等级"].value_counts().reset_index()
    stat_df.columns=["等级","数量"]
    st.dataframe(stat_df, hide_index=True)

    # 大盘自动诊断文字
    st.markdown("#### 📋投放大盘自动诊断")
    good_cnt = len(df_detail[df_detail["等级"]=="✅优质可放大"])
    bad_highcost = len(df_detail[df_detail["等级"]=="🔻高花费低ROI"])
    no_sale = len(df_detail[df_detail["等级"]=="🔴无成交"])
    if total_roi >= roi_target:
        diag_text = f"✅整体ROI({total_roi:.2f})达到保本目标{roi_target}。优质单元{good_cnt}个，可以适度放大；重点关注{bad_highcost}个高花费低投产单元控制预算。"
    else:
        diag_text = f"⚠️整体ROI({total_roi:.2f})低于保本目标{roi_target}。优先处理{bad_highcost}个高花费低ROI单元，减少无效消耗；优质单元{good_cnt}个可放大；{no_sale}个单元有花费无成交建议降价或关停。"
    st.info(diag_text)

    #分渠道图表
    if "推广类型" in df.columns and "花费" in df.columns and "成交金额" in df.columns:
        st.markdown("---")
        st.subheader("📌分渠道对比")
        df_channel = df.groupby("推广类型").agg({"花费":"sum","成交金额":"sum"}).reset_index()
        df_channel["ROI"] = df_channel["成交金额"]/df_channel["花费"]
        st.dataframe(df_channel.round(2), hide_index=True)
        fig_chan = px.bar(df_channel, x="推广类型", y="ROI", text_auto=".2f")
        fig_chan.add_hline(y=roi_target, line_dash="dash", line_color="red")
        st.plotly_chart(fig_chan, use_container_width=True)

    # =========选项卡 =========
    tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs([
        "📊大盘&诊断",
        "📦商品汇总",
        "🔑关键词优化(图)",
        "👥人群优化(图)",
        "🎯明细清单",
        "📈时间趋势"
    ])

    with tab1:
        st.markdown("本页面为大盘总览，上方已展示核心指标、等级统计、投放诊断、分渠道图表。")

    with tab2:
        if len(df_prod_sum)>0:
            show_p = group_keys_prod + ["总花费","总成交金额","整体ROI","总点击","平均CPC","等级","策略","执行"]
            show_p_real = [x for x in show_p if x in df_prod_sum.columns]
            st.dataframe(df_prod_sum[show_p_real].round(2), use_container_width=True, hide_index=True)
            st.download_button("📥下载商品汇总CSV",data=df_prod_sum.to_csv(index=False,encoding="utf-8-sig"),file_name="万相台_商品汇总.csv")
        else:
            st.info("缺少商品ID/商品名称，无法生成商品汇总")

    with tab3:
        if len(df_kw_sum)>0:
            kw_eff = df_kw_sum[df_kw_sum["总花费"]>=min_cost].copy() if "总花费" in df_kw_sum.columns else df_kw_sum
            st.subheader("🔑关键词优化分析")
            if len(kw_eff)>0 and "总花费" in kw_eff.columns:
                fig_k1 = px.bar(kw_eff.nlargest(15,"总花费"), x="总花费", y="关键词", orientation="h", title="TOP15关键词花费排行",text_auto=".1f")
                st.plotly_chart(fig_k1,use_container_width=True)
            if len(kw_eff)>0 and "ROI" in kw_eff.columns:
                fig_k2 = px.bar(kw_eff.sort_values("ROI",ascending=False).head(20),x="关键词",y="ROI",title="关键词ROI对比",text_auto=".2f")
                fig_k2.add_hline(y=roi_target,line_dash="dash",line_color="red")
                fig_k2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_k2,use_container_width=True)
            st.markdown("关键词优化清单")
            kw_show = ["关键词","总花费","总成交金额","ROI","CPC","等级","策略","执行"]
            kw_real = [c for c in kw_show if c in df_kw_sum.columns]
            st.dataframe(df_kw_sum[kw_real].round(2),use_container_width=True,hide_index=True)
            st.download_button("📥下载关键词清单",data=df_kw_sum.to_csv(index=False,encoding="utf-8-sig"),file_name="万相台_关键词.csv")
        else:
            st.info("报表无【关键词】列，请上传关键词推广报表")

    with tab4:
        if len(df_crowd_sum)>0:
            crowd_eff = df_crowd_sum[df_crowd_sum["总花费"]>=min_cost].copy() if "总花费" in df_crowd_sum.columns else df_crowd_sum
            st.subheader("👥人群包优化分析")
            if len(crowd_eff)>0 and "总花费" in crowd_eff.columns:
                fig_c1 = px.bar(crowd_eff.sort_values("总花费",ascending=False).head(15),x="人群包名称",y=["总花费","总成交金额"],barmode="group",title="TOP15人群花费vs成交")
                fig_c1.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_c1,use_container_width=True)
            if len(crowd_eff)>0 and "ROI" in crowd_eff.columns:
                fig_c2 = px.bar(crowd_eff.sort_values("ROI",ascending=False).head(20),x="人群包名称",y="ROI",title="人群包ROI对比",text_auto=".2f")
                fig_c2.add_hline(y=roi_target,line_dash="dash",line_color="red")
                fig_c2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_c2,use_container_width=True)
            st.markdown("人群包优化清单")
            cr_show = ["人群包名称","总花费","总成交金额","ROI","CPC","等级","策略","执行"]
            cr_real = [c for c in cr_show if c in df_crowd_sum.columns]
            st.dataframe(df_crowd_sum[cr_real].round(2),use_container_width=True,hide_index=True)
            st.download_button("📥下载人群清单",data=df_crowd_sum.to_csv(index=False,encoding="utf-8-sig"),file_name="万相台_人群.csv")
        else:
            st.info("报表无【人群包名称】列，请上传人群运营报表")

    with tab5:
        df_filter_view = df_detail[df_detail["等级"].isin(filter_level_list)]
        show_d = ["推广类型","关键词","人群包名称","商品ID","商品名称","花费","成交金额","ROI","CPC","预警标记","等级","策略","执行"]
        d_real = [x for x in show_d if x in df_filter_view.columns]
        st.dataframe(df_filter_view[d_real].round(2), use_container_width=True, hide_index=True)
        st.download_button("📥下载筛选后明细",data=df_filter_view.to_csv(index=False,encoding="utf-8-sig"),file_name="万相台_筛选明细.csv")

    with tab6:
        st.subheader("📈日度时间趋势（需要报表包含【日期】列，支持多文件上传）")
        if "日期" in df.columns and "花费" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
            day_agg = {}
            day_agg["花费"]=("花费","sum")
            if "成交金额" in df.columns: day_agg["成交金额"]=("成交金额","sum")
            if "点击量" in df.columns: day_agg["点击量"]=("点击量","sum")
            if "展现量" in df.columns: day_agg["展现量"]=("展现量","sum")
            df_day = df.groupby("日期").agg(**day_agg).reset_index()
            if "花费" in df_day.columns and "成交金额" in df_day.columns:
                df_day["ROI"] = np.where(df_day["花费"]>0, df_day["成交金额"]/df_day["花费"],0)
            if "点击量" in df_day.columns and "花费" in df_day.columns:
                df_day["CPC"] = np.where(df_day["点击量"]>0, df_day["花费"]/df_day["点击量"],0)
            fig_t1 = px.line(df_day, x="日期", y="花费", markers=True, title="每日花费")
            st.plotly_chart(fig_t1, use_container_width=True)
            if "ROI" in df_day.columns:
                fig_t2 = px.line(df_day, x="日期", y="ROI", markers=True, title="每日ROI")
                fig_t2.add_hline(y=roi_target, line_dash="dash", color="red")
                st.plotly_chart(fig_t2, use_container_width=True)
        else:
            st.info("⚠️报表缺少【日期】字段，无法绘制趋势；导出报表勾选日期字段，多份日报表一起上传。")

    # =========投放操作记录表单 =========
    st.markdown("---")
    st.subheader("📝投放操作记录（记录后台调整动作，刷新网页数据丢失，请及时导出）")
    with st.form("action_log_form"):
        f1,f2,f3 = st.columns(3)
        with f1:
            t1 = st.text_input("推广类型")
            t2 = st.text_input("对象名称（关键词/人群/商品ID）")
        with f2:
            act = st.selectbox("执行动作",["提升预算","降低预算","提高出价","降低出价","暂停单元","开启单元","修改创意","其他"])
        with f3:
            adj = st.text_input("调整内容，例：出价-20%")
            note = st.text_input("备注，例：观察3天")
        sub = st.form_submit_button("✅保存本次操作记录")
        if sub:
            new_log = {
                "操作时间":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "推广类型":t1,
                "对象名称":t2,
                "执行动作":act,
                "调整内容":adj,
                "备注":note
            }
            st.session_state.action_log = pd.concat([st.session_state.action_log, pd.DataFrame([new_log])], ignore_index=True)
            st.success("已保存操作记录！")
    st.dataframe(st.session_state.action_log, hide_index=True, use_container_width=True)
    st.download_button("📥导出全部操作记录", data=st.session_state.action_log.to_csv(index=False,encoding="utf-8-sig"), file_name="万相台_投放操作记录.csv")

else:
    st.info("👈上传报表，Excel表头【花费】，建议勾选：商品ID、商品名称；关键词、人群报表分别导出，可获得完整分析图表")
