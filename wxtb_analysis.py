import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime

st.set_page_config(page_title="万相台投放工作台V8", layout="wide")
st.title("📊万相台推广数据分析 & 自动优化策略V8")

if "action_log" not in st.session_state:
    st.session_state.action_log = pd.DataFrame(columns=["操作时间","推广类型","对象名称","执行动作","调整内容","备注"])

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
    upload_file = st.file_uploader("上传万相台Excel/Csv报表，可多选", type=["xlsx","xls","csv"], accept_multiple_files=True)

def get_suggest(row, target_roi, min_spend):
    cost = row.get("花费",0); roi = row.get("ROI",0); click = row.get("点击量",0)
    if np.isinf(roi) or np.isnan(roi): roi = 0
    if cost < min_spend: return {"等级":"🟡样本不足","策略":"花费少继续观察","执行":"无操作"}
    if click <=0: return {"等级":"🟡零点击","策略":"有展现无点击","执行":"降出价或优化素材"}
    if roi >= target_roi: return {"等级":"✅优质可放大","策略":"投产达标可放大","执行":"预算+10~20%，小幅抬高出价"}
    elif roi>0 and roi < target_roi*0.6 and cost>min_spend*3: return {"等级":"🔻高花费低ROI","策略":"花费高投产差","执行":"降价30%或暂停"}
    elif roi>0 and roi < target_roi: return {"等级":"⚠️观察待优化","策略":"略低于目标","执行":"出价下调10-20%观察"}
    else: return {"等级":"🔴无成交","策略":"有花费无订单","执行":"降价，无改善暂停"}

def get_warn(row, wmax, wmin):
    warns=[]
    cpc=row.get("CPC",0); ctr=row.get("CTR",0)
    if cpc>wmax: warns.append(f"CPC过高{cpc:.2f}")
    if 0<ctr<wmin: warns.append(f"CTR过低{ctr:.2%}")
    if warns: return {"预警标记":"🚨异常","预警说明":"；".join(warns)}
    return {"预警标记":"✅正常","预警说明":"无异常"}

def resolve_col(df, aliases):
    for a in aliases:
        if a in df.columns: return a
    return None

frames=[]
if upload_file:
    for f in upload_file:
        try:
            tmp = pd.read_csv(f) if f.name.endswith(".csv") else pd.read_excel(f)
            tmp.columns=[str(c).strip() for c in tmp.columns]
            frames.append(tmp)
        except Exception as e:
            st.warning(f"文件{f.name}读取失败:{e}")
if frames:
    df_raw = pd.concat(frames, ignore_index=True)
    st.subheader("📄原始文件概览")
    st.metric("合并总行数", f"{len(df_raw):,}")
    st.markdown("识别字段：`"+", ".join(list(df_raw.columns))+"`")
    st.dataframe(df_raw.head(8), hide_index=True)

    out = pd.DataFrame()
    out["日期"] = df_raw[resolve_col(df_raw,["日期"])] if resolve_col(df_raw,["日期"]) else ""
    out["商品ID"] = df_raw[resolve_col(df_raw,["主体ID","商品ID"])] if resolve_col(df_raw,["主体ID","商品ID"]) else ""
    out["商品名称"] = df_raw[resolve_col(df_raw,["主体名称","商品名称","宝贝名称"])] if resolve_col(df_raw,["主体名称","商品名称","宝贝名称"]) else ""
    out["计划名称"] = df_raw[resolve_col(df_raw,["计划名字","计划名称","推广计划名称"])] if resolve_col(df_raw,["计划名字","计划名称","推广计划名称"]) else ""
    out["场景名称"] = df_raw[resolve_col(df_raw,["场景名字","场景名称"])] if resolve_col(df_raw,["场景名字","场景名称"]) else ""
    out["关键词"] = df_raw[resolve_col(df_raw,["关键词","词"])] if resolve_col(df_raw,["关键词","词"]) else ""
    out["人群包名称"] = df_raw[resolve_col(df_raw,["人群包名称"])] if resolve_col(df_raw,["人群包名称"]) else ""

    c_cost=resolve_col(df_raw,["花费"]); c_gmv=resolve_col(df_raw,["总成交金额","成交金额","净成交金额"])
    c_order=resolve_col(df_raw,["总成交笔数","成交笔数"]); c_click=resolve_col(df_raw,["点击量"])
    c_show=resolve_col(df_raw,["展现量"]); c_cart=resolve_col(df_raw,["总购物车数","加购数"])
    c_fav=resolve_col(df_raw,["收藏宝贝数","收藏数"])
    c_roi=resolve_col(df_raw,["投入产出比","实际投产比","投产比","ROI"])
    c_cpc=resolve_col(df_raw,["平均点击花费"]); c_ctr=resolve_col(df_raw,["点击率"])

    out["花费"]=pd.to_numeric(df_raw[c_cost],errors="coerce").fillna(0) if c_cost else 0
    out["成交金额"]=pd.to_numeric(df_raw[c_gmv],errors="coerce").fillna(0) if c_gmv else 0
    out["成交笔数"]=pd.to_numeric(df_raw[c_order],errors="coerce").fillna(0) if c_order else 0
    out["点击量"]=pd.to_numeric(df_raw[c_click],errors="coerce").fillna(0) if c_click else 0
    out["展现量"]=pd.to_numeric(df_raw[c_show],errors="coerce").fillna(0) if c_show else 0
    out["加购数"]=pd.to_numeric(df_raw[c_cart],errors="coerce").fillna(0) if c_cart else 0
    out["收藏数"]=pd.to_numeric(df_raw[c_fav],errors="coerce").fillna(0) if c_fav else 0

    if c_roi:
        out["ROI"]=pd.to_numeric(df_raw[c_roi],errors="coerce").fillna(0).replace([float("inf")],0)
    else:
        out["ROI"]=np.where(out["花费"]>0,out["成交金额"]/out["花费"],0)
    if c_cpc: out["CPC"]=pd.to_numeric(df_raw[c_cpc],errors="coerce").fillna(0)
    else: out["CPC"]=np.where(out["点击量"]>0,out["花费"]/out["点击量"],0)
    if c_ctr: out["CTR"]=pd.to_numeric(df_raw[c_ctr],errors="coerce").fillna(0)
    else: out["CTR"]=np.where(out["展现量"]>0,out["点击量"]/out["展现量"],0)

    df = out.reset_index(drop=True)
    if not c_gmv: st.warning("⚠️未识别成交金额列(总成交金额)，成交/ROI为0")
    if not c_cost: st.warning("⚠️未识别花费列")

    df_detail = pd.concat([df.reset_index(drop=True),
        pd.DataFrame([get_suggest(r,roi_target,min_cost) for _,r in df.iterrows()]),
        pd.DataFrame([get_warn(r,max_cpc_warn,min_ctr_warn) for _,r in df.iterrows()])], axis=1)

    def group_sum(grp_keys, name_roi, name_cpc):
        agg={}
        if "花费" in df.columns: agg["总花费"]=("花费","sum")
        if "成交金额" in df.columns: agg["总成交金额"]=("成交金额","sum")
        if "点击量" in df.columns: agg["总点击"]=("点击量","sum")
        if "展现量" in df.columns: agg["总展现"]=("展现量","sum")
        if "加购数" in df.columns: agg["总加购"]=("加购数","sum")
        if "收藏数" in df.columns: agg["总收藏"]=("收藏数","sum")
        if not agg or not grp_keys: return pd.DataFrame()
        g = df.groupby(grp_keys,dropna=False).agg(**agg).reset_index()
        if "总花费" in g.columns and "总成交金额" in g.columns:
            g[name_roi]=np.where(g["总花费"]>0,g["总成交金额"]/g["总花费"],0)
        if "总点击" in g.columns and "总花费" in g.columns:
            g[name_cpc]=np.where(g["总点击"]>0,g["总花费"]/g["总点击"],0)
        sug=[get_suggest({"花费":r["总花费"],"ROI":r[name_roi],"点击量":r["总点击"]},roi_target,min_cost) for _,r in g.iterrows()]
        return pd.concat([g,pd.DataFrame(sug)],axis=1)

    df_prod_sum = group_sum([k for k in ["商品ID","商品名称"] if k in df.columns], "整体ROI","平均CPC")
    df_plan_sum = group_sum([k for k in ["计划名称","场景名称"] if k in df.columns], "整体ROI","平均CPC")
    df_kw_sum = group_sum([k for k in ["关键词"] if k in df.columns and df["关键词"].astype(str).str.strip().ne("").any()], "ROI","CPC")
    df_crowd_sum = group_sum([k for k in ["人群包名称"] if k in df.columns and df["人群包名称"].astype(str).str.strip().ne("").any()], "ROI","CPC")
    pk_keys=[k for k in ["商品名称","商品ID"] if k in df.columns]
    df_item_kw = pd.DataFrame()
    if pk_keys and "关键词" in df.columns and df["关键词"].astype(str).str.strip().ne("").any():
        df_item_kw = group_sum(pk_keys+["关键词"], "ROI","CPC")

    # 大盘
    tc=df["花费"].sum(); tg=df["成交金额"].sum(); troi=tg/tc if tc>0 else 0; tclk=df["点击量"].sum()
    st.markdown("---")
    c1,c2,c3,c4=st.columns(4)
    with c1: st.metric("总花费",f"{tc:.2f}元")
    with c2: st.metric("总GMV",f"{tg:.2f}元")
    with c3: st.metric("整体ROI",f"{troi:.2f}",delta=f"目标{roi_target}")
    with c4: st.metric("总点击",f"{int(tclk):,}")
    st.markdown("#### 🚨单元等级统计")
    stat=df_detail["等级"].value_counts().reset_index(); stat.columns=["等级","数量"]
    st.dataframe(stat, hide_index=True)
    gc=len(df_detail[df_detail["等级"]=="✅优质可放大"]); bc=len(df_detail[df_detail["等级"]=="🔻高花费低ROI"]); nc=len(df_detail[df_detail["等级"]=="🔴无成交"])
    if troi>=roi_target: diag=f"✅整体ROI({troi:.2f})达标。优质{gc}个可放大；关注{bc}个高花费低投产。"
    else: diag=f"⚠️整体ROI({troi:.2f})低于{roi_target}。优先处理{bc}个高花费低ROI；优质{gc}个可放大；{nc}个无成交建议关停。"
    st.info(diag)

    # ===== 需要调整的等级（默认展示） =====
    need_levels = ["🔻高花费低ROI","🔴无成交","⚠️观察待优化","🟡零点击"]

    tab1,tab2,tab3,tab4,tab5,tab6,tab7,tab8 = st.tabs([
        "🚨待调整商品(默认)","📦商品优化(图)","📋计划优化(图)","🎯商品×关键词",
        "🔑关键词优化(图)","👥人群优化(图)","明细清单","时间趋势/记录"])

    # ----- tab1 待调整商品（用户核心诉求：把需要调整的商品展现出来） -----
    with tab1:
        st.info("💡默认展示【需要调整】的商品：高花费低ROI、无成交、观察待优化、零点击。优质可放大也算调整，可手动勾选。")
        if len(df_prod_sum)>0:
            avail_levels = [l for l in df_prod_sum["等级"].unique() if l in need_levels+["✅优质可放大"]]
            sel = st.multiselect("展示等级（默认=需要调整）", avail_levels,
                                 default=[l for l in need_levels if l in avail_levels])
            view = df_prod_sum[df_prod_sum["等级"].isin(sel)] if sel else df_prod_sum
            st.markdown(f"#### 当前展示 {len(view)} 个商品")
            if len(view)>0:
                # 图：需要调整商品的ROI对比
                f=px.bar(view.sort_values("总花费",ascending=False).head(20),x="商品名称",y="整体ROI",
                         title="待调整商品 ROI 对比(红=保本)",text_auto=".2f",color="等级",
                         color_discrete_map={"🔻高花费低ROI":"#e74c3c","🔴无成交":"#c0392b","⚠️观察待优化":"#f39c12","🟡零点击":"#95a5a6","✅优质可放大":"#2ecc71"})
                f.add_hline(y=roi_target,line_dash="dash",line_color="red"); f.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(f,use_container_width=True)
                # 高花费低ROI+无成交 重点图
                key = view[view["等级"].isin(["🔻高花费低ROI","🔴无成交"])]
                if len(key)>0:
                    st.markdown("#### ⚠️重点：高花费低ROI + 无成交（优先处理）")
                    st.plotly_chart(px.bar(key.sort_values("总花费",ascending=False),x="总花费",y="商品名称",orientation="h",
                                           title="高花费低ROI/无成交商品花费",text_auto=".1f",color="等级",
                                           color_discrete_map={"🔻高花费低ROI":"#e74c3c","🔴无成交":"#c0392b"}),use_container_width=True)
            show=[c for c in ["商品ID","商品名称","总花费","总成交金额","整体ROI","总点击","总加购","等级","策略","执行"] if c in view.columns]
            st.dataframe(view[show].round(2),use_container_width=True,hide_index=True)
            st.download_button("📥下载待调整商品清单",data=view.to_csv(index=False,encoding="utf-8-sig"),file_name="待调整商品清单.csv")
        else: st.info("未识别商品列(主体名称/商品名称)")

    # ----- tab2 商品优化（全部+图） -----
    with tab2:
        st.info("全部商品按等级筛选查看。")
        if len(df_prod_sum)>0:
            all_levels=list(df_prod_sum["等级"].unique())
            sel2=st.multiselect("展示等级", all_levels, default=all_levels)
            view2=df_prod_sum[df_prod_sum["等级"].isin(sel2)] if sel2 else df_prod_sum
            if len(view2)>0:
                pe=view2[view2["总花费"]>=min_cost]
                if len(pe)>0:
                    st.plotly_chart(px.bar(pe.nlargest(15,"总花费"),x="总花费",y="商品名称",orientation="h",title="TOP15商品花费",text_auto=".1f"),use_container_width=True)
                    f2=px.bar(pe.sort_values("整体ROI",ascending=False).head(20),x="商品名称",y="整体ROI",title="商品ROI(红=保本)",text_auto=".2f",color="整体ROI",color_continuous_scale="RdYlGn")
                    f2.add_hline(y=roi_target,line_dash="dash",line_color="red"); f2.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(f2,use_container_width=True)
            show=[c for c in ["商品ID","商品名称","总花费","总成交金额","整体ROI","总点击","总加购","等级","策略","执行"] if c in df_prod_sum.columns]
            st.dataframe(df_prod_sum[show].round(2),use_container_width=True,hide_index=True)
            st.download_button("📥下载全部商品清单",data=df_prod_sum.to_csv(index=False,encoding="utf-8-sig"),file_name="全部商品清单.csv")
        else: st.info("未识别商品列")

    # ----- tab3 计划优化 -----
    with tab3:
        st.info("计划报表按计划汇总，看哪个计划烧钱、哪个计划ROI差。")
        if len(df_plan_sum)>0:
            pe=df_plan_sum[df_plan_sum["总花费"]>=min_cost].copy()
            if len(pe)>0:
                st.plotly_chart(px.bar(pe.nlargest(15,"总花费"),x="总花费",y="计划名称",orientation="h",title="TOP15计划花费",text_auto=".1f"),use_container_width=True)
                f2=px.bar(pe.sort_values("整体ROI",ascending=False).head(20),x="计划名称",y="整体ROI",title="计划ROI(红=保本)",text_auto=".2f",color="整体ROI",color_continuous_scale="RdYlGn")
                f2.add_hline(y=roi_target,line_dash="dash",line_color="red"); f2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(f2,use_container_width=True)
            show=[c for c in ["计划名称","场景名称","总花费","总成交金额","整体ROI","总点击","等级","策略","执行"] if c in df_plan_sum.columns]
            st.dataframe(df_plan_sum[show].round(2),use_container_width=True,hide_index=True)
            st.download_button("📥下载计划优化清单",data=df_plan_sum.to_csv(index=False,encoding="utf-8-sig"),file_name="计划优化清单.csv")
        else: st.info("未识别计划列(计划名字/推广计划名称)")

    # ----- tab4 商品×关键词 -----
    with tab4:
        st.info("关键词数据明细报表用这个：每个商品×关键词一行，最细的优化。需导出「关键词数据明细」(含计划+商品+关键词)。")
        if len(df_item_kw)>0:
            pe=df_item_kw[df_item_kw["总花费"]>=min_cost].copy()
            if len(pe)>0:
                f2=px.bar(pe.sort_values("ROI",ascending=False).head(20),x="关键词",y="ROI",title="商品×关键词ROI(红=保本)",text_auto=".2f",color="ROI",color_continuous_scale="RdYlGn")
                f2.add_hline(y=roi_target,line_dash="dash",line_color="red"); f2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(f2,use_container_width=True)
                st.plotly_chart(px.bar(pe.nlargest(15,"总花费"),x="总花费",y="关键词",orientation="h",title="TOP15商品×关键词花费",text_auto=".1f"),use_container_width=True)
            show=[c for c in ["商品名称","商品ID","关键词","总花费","总成交金额","ROI","CPC","等级","策略","执行"] if c in df_item_kw.columns]
            st.dataframe(df_item_kw[show].round(2),use_container_width=True,hide_index=True)
            st.download_button("📥下载商品×关键词优化清单",data=df_item_kw.to_csv(index=False,encoding="utf-8-sig"),file_name="商品关键词优化清单.csv")
        else: st.info("需要同时有【商品】和【关键词】列(来自关键词数据明细)。当前报表缺其一。")

    # ----- tab5 关键词 -----
    with tab5:
        if len(df_kw_sum)>0:
            pe=df_kw_sum[df_kw_sum["总花费"]>=min_cost].copy()
            if len(pe)>0:
                st.plotly_chart(px.bar(pe.nlargest(15,"总花费"),x="总花费",y="关键词",orientation="h",title="TOP15关键词花费",text_auto=".1f"),use_container_width=True)
                f2=px.bar(pe.sort_values("ROI",ascending=False).head(20),x="关键词",y="ROI",title="关键词ROI(红=保本)",text_auto=".2f")
                f2.add_hline(y=roi_target,line_dash="dash",line_color="red"); f2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(f2,use_container_width=True)
            show=[c for c in ["关键词","总花费","总成交金额","ROI","CPC","等级","策略","执行"] if c in df_kw_sum.columns]
            st.dataframe(df_kw_sum[show].round(2),use_container_width=True,hide_index=True)
            st.download_button("📥下载关键词清单",data=df_kw_sum.to_csv(index=False,encoding="utf-8-sig"),file_name="关键词清单.csv")
        else: st.info("报表无【关键词】列")

    # ----- tab6 人群 -----
    with tab6:
        if len(df_crowd_sum)>0:
            pe=df_crowd_sum[df_crowd_sum["总花费"]>=min_cost].copy()
            if len(pe)>0:
                st.plotly_chart(px.bar(pe.sort_values("总花费",ascending=False).head(15),x="人群包名称",y=["总花费","总成交金额"],barmode="group",title="TOP15人群花费vs成交").update_layout(xaxis_tickangle=-45),use_container_width=True)
                f2=px.bar(pe.sort_values("ROI",ascending=False).head(20),x="人群包名称",y="ROI",title="人群ROI(红=保本)",text_auto=".2f")
                f2.add_hline(y=roi_target,line_dash="dash",line_color="red"); f2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(f2,use_container_width=True)
            show=[c for c in ["人群包名称","总花费","总成交金额","ROI","CPC","等级","策略","执行"] if c in df_crowd_sum.columns]
            st.dataframe(df_crowd_sum[show].round(2),use_container_width=True,hide_index=True)
            st.download_button("📥下载人群清单",data=df_crowd_sum.to_csv(index=False,encoding="utf-8-sig"),file_name="人群清单.csv")
        else: st.info("报表无【人群包名称】列")

    # ----- tab7 明细 + 时间趋势 + 记录 -----
    with tab7:
        st.markdown("### 🎯明细清单")
        dv=df_detail[df_detail["等级"].isin(filter_level_list)]
        show=[c for c in ["日期","商品ID","商品名称","计划名称","关键词","人群包名称","花费","成交金额","ROI","CPC","加购数","预警标记","等级","策略","执行"] if c in dv.columns]
        st.dataframe(dv[show].round(2),use_container_width=True,hide_index=True)
        st.download_button("📥下载筛选明细",data=dv.to_csv(index=False,encoding="utf-8-sig"),file_name="筛选明细.csv")

        st.markdown("### 📈日度时间趋势")
        st.info("需报表含【日期】列；多份日报一起上传画多日趋势。")
        if "日期" in df.columns and pd.notna(df["日期"]).any():
            df["日期"]=pd.to_datetime(df["日期"],errors="coerce")
            day_agg={"花费":("花费","sum")}
            if "成交金额" in df.columns: day_agg["成交金额"]=("成交金额","sum")
            if "点击量" in df.columns: day_agg["点击量"]=("点击量","sum")
            dd=df.groupby("日期").agg(**day_agg).reset_index()
            if "花费" in dd.columns and "成交金额" in dd.columns:
                dd["ROI"]=np.where(dd["花费"]>0,dd["成交金额"]/dd["花费"],0)
            st.plotly_chart(px.line(dd,x="日期",y="花费",markers=True,title="每日花费"),use_container_width=True)
            if "ROI" in dd.columns:
                f2=px.line(dd,x="日期",y="ROI",markers=True,title="每日ROI")
                f2.add_hline(y=roi_target,line_dash="dash",color="red")
                st.plotly_chart(f2,use_container_width=True)
        else: st.warning("报表缺少【日期】列")

        st.markdown("### 📝投放操作记录")
        st.info("记录后台调整，刷新网页会丢失，请及时导出。")
        with st.form("log_form"):
            f1,f2,f3=st.columns(3)
            with f1:
                t1=st.text_input("推广类型"); t2=st.text_input("对象名称")
            with f2:
                act=st.selectbox("执行动作",["提升预算","降低预算","提高出价","降低出价","暂停单元","开启单元","修改创意","其他"])
            with f3:
                adj=st.text_input("调整内容"); note=st.text_input("备注")
            if st.form_submit_button("✅保存记录"):
                st.session_state.action_log=pd.concat([st.session_state.action_log,pd.DataFrame([{"操作时间":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"推广类型":t1,"对象名称":t2,"执行动作":act,"调整内容":adj,"备注":note}])],ignore_index=True)
                st.success("已保存!")
        st.dataframe(st.session_state.action_log,hide_index=True,use_container_width=True)
        st.download_button("📥导出操作记录",data=st.session_state.action_log.to_csv(index=False,encoding="utf-8-sig"),file_name="操作记录.csv")

else:
    st.info("👈上传万相台报表：商品报表看【待调整商品】；货品报表看【商品优化】；计划报表看【计划优化】；关键词明细看【商品×关键词】。字段自动识别。")
