import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

st.set_page_config(page_title="万相台投放工作台", layout="wide")
st.title("📊万相台推广数据分析 & 优化策略")

#侧边栏
with st.sidebar:
    st.header("阈值设置")
    roi_target = st.number_input("保本ROI", min_value=0.1, value=2.5, step=0.1)
    min_cost = st.number_input("最小有效花费(元)", min_value=0, value=30, step=5)
    max_cpc_warn = st.number_input("CPC过高预警(元)", min_value=0.0, value=2.0, step=0.1)
    min_ctr_warn = st.number_input("CTR过低预警", min_value=0.001, value=0.02, step=0.001)
    upload_file = st.file_uploader("上传Excel报表", type=["xlsx","xls","csv"])

#策略函数
def get_suggest(row, target_roi, min_spend):
    cost = row.get("花费",0)
    roi = row.get("ROI",0)
    if np.isinf(roi) or np.isnan(roi):
        roi = 0
    click = row.get("点击量",0)

    if cost < min_spend:
        return {"等级":"🟡样本不足","策略":"花费少继续观察","执行":"无操作"}
    if click <=0:
        return {"等级":"🟡零点击","策略":"无点击，检查素材人群","执行":"降出价或优化素材"}
    if roi >= target_roi:
        return {"等级":"✅优质可放大","策略":"投产达标放大","执行":"预算+10~20%，小幅抬高出价"}
    elif roi>0 and roi < target_roi*0.6 and cost> min_spend*3:
        return {"等级":"🔻高花费低ROI","策略":"花费高投产差","执行":"降价30%或暂停"}
    elif roi>0 and roi < target_roi:
        return {"等级":"⚠️观察待优化","策略":"略低于目标","执行":"出价下调10-20%观察"}
    else:
        return {"等级":"🔴无成交","策略":"有花费无订单","执行":"降价，无效就暂停"}

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
    else:
        return {"预警标记":"✅正常","预警说明":"无异常"}

if upload_file is not None:
    if upload_file.name.endswith(".csv"):
        df_raw = pd.read_csv(upload_file)
    else:
        df_raw = pd.read_excel(upload_file)

    st.subheader("原始预览")
    st.dataframe(df_raw.head(5), hide_index=True)

    keep_cols = ["花费","展现量","点击量","成交金额","成交笔数","推广类型","关键词","人群包名称","商品名称","商品ID"]
    exist_cols = [c for c in keep_cols if c in df_raw.columns]
    df = df_raw[exist_cols].copy()

    # 只对实际存在的列做数值转换，防止KeyError
    num_cols = ["花费","展现量","点击量","成交金额","成交笔数"]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 衍生指标，安全读取
    df["CPC"] = np.where(df["点击量"]>0, df["花费"]/df["点击量"],0)
    if "成交金额" in df.columns and "花费" in df.columns:
        df["ROI"] = np.where(df["花费"]>0, df["成交金额"]/df["花费"],0)
    else:
        df["ROI"] = 0
    df["CTR"] = np.where(df["展现量"]>0, df["点击量"]/df["展现量"],0)

    #生成明细策略+预警
    suggest_out = [get_suggest(r, roi_target, min_cost) for _,r in df.iterrows()]
    warn_out = [get_warn(r, max_cpc_warn, min_ctr_warn) for _,r in df.iterrows()]
    df_s = pd.DataFrame(suggest_out)
    df_w = pd.DataFrame(warn_out)
    df_detail = pd.concat([df.reset_index(drop=True), df_s, df_w], axis=1)

    # =========按商品ID/商品名称【合并汇总表】核心新增=========
    group_keys = []
    if "商品ID" in df.columns:
        group_keys.append("商品ID")
    if "商品名称" in df.columns:
        group_keys.append("商品名称")

    df_product_summary = pd.DataFrame()
    if len(group_keys)>=1:
        df_product_summary = df.groupby(group_keys, dropna=False).agg(
            总花费=("花费","sum"),
            总成交金额=("成交金额","sum"),
            总点击=("点击量","sum"),
            总展现=("展现量","sum"),
            总成交笔数=("成交笔数","sum")
        ).reset_index()
        df_product_summary["整体ROI"] = np.where(df_product_summary["总花费"]>0, df_product_summary["总成交金额"]/df_product_summary["总花费"],0)
        df_product_summary["平均CPC"] = np.where(df_product_summary["总点击"]>0, df_product_summary["总花费"]/df_product_summary["总点击"],0)
        df_product_summary["平均CTR"] = np.where(df_product_summary["总展现"]>0, df_product_summary["总点击"]/df_product_summary["总展现"],0)

        #给【商品汇总行】生成整体优化策略
        product_suggest = []
        for _,row in df_product_summary.iterrows():
            d = {
                "花费":row["总花费"],
                "ROI":row["整体ROI"],
                "点击量":row["总点击"]
            }
            s = get_suggest(d, roi_target, min_cost)
            product_suggest.append(s)
        df_ps_sug = pd.DataFrame(product_suggest)
        df_product_summary = pd.concat([df_product_summary, df_ps_sug],axis=1)

    #大盘指标
    st.markdown("---")
    tc = df["花费"].sum() if "花费" in df.columns else 0
    tgmv = df["成交金额"].sum() if "成交金额" in df.columns else 0
    troi = tgmv/tc if tc>0 else 0
    total_click = df["点击量"].sum() if "点击量" in df.columns else 0

    c1,c2,c3,c4 = st.columns(4)
    with c1:st.metric("总花费",f"{tc:.2f}元")
    with c2:st.metric("总GMV",f"{tgmv:.2f}元")
    with c3:st.metric("整体ROI",f"{troi:.2f}", delta=f"目标{roi_target}")
    with c4:st.metric("总点击",f"{int(total_click):,}")

    #分渠道
    if "推广类型" in df.columns and "花费" in df.columns and "成交金额" in df.columns:
        st.markdown("---")
        st.subheader("📌分渠道对比")
        g = df.groupby("推广类型").agg({"花费":"sum","成交金额":"sum"}).reset_index()
        g["ROI"] = g["成交金额"]/g["花费"]
        st.dataframe(g.round(2), hide_index=True)
        fig = px.bar(g, x="推广类型", y="ROI", text_auto=".2f")
        fig.add_hline(y=roi_target, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

    # =========选项卡：【商品汇总总表】 和 【明细执行清单】=========
    st.markdown("---")
    tab1, tab2 = st.tabs(["📦按商品汇总总表（合并同一个产品全部渠道）","🎯原始明细执行清单（关键词/人群/渠道）"])

    with tab1:
        if len(df_product_summary)>0:
            st.subheader("每个商品全部投放合并汇总，直接看单品整体表现")
            show_prod_cols = group_keys + ["总花费","总成交金额","整体ROI","总点击","平均CPC","等级","策略","执行"]
            real_prod_show = [c for c in show_prod_cols if c in df_product_summary.columns]
            st.dataframe(df_product_summary[real_prod_show].round(2), use_container_width=True, hide_index=True)
            csv_prod = df_product_summary.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("📥下载商品汇总CSV", data=csv_prod, file_name="万相台_商品汇总表.csv")
        else:
            st.info("⚠️缺少商品ID/商品名称列，无法生成商品汇总表，导出报表时勾选商品ID和商品名称")

    with tab2:
        st.subheader("明细清单：关键词、人群包、商品原始行数据，含预警")
        show_cols = ["推广类型","关键词","人群包名称","商品ID","商品名称","花费","成交金额","ROI","CPC","预警标记","等级","策略","执行"]
        real_show = [c for c in show_cols if c in df_detail.columns]
        st.dataframe(df_detail[real_show].round(2), use_container_width=True, hide_index=True)
        csv_detail = df_detail.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📥下载明细优化清单CSV（含商品ID）", data=csv_detail, file_name="万相台_优化清单_明细.csv")

else:
    st.info("👈上传Excel，表头【花费】；下载全站报表记得勾选导出【商品ID、商品名称】，可以生成商品汇总总表")
