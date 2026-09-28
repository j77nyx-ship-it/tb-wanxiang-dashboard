import io
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="万相台投放工作台 V9", layout="wide")
st.title("📊 万相台推广数据分析 & 自动优化策略 V9")

# ---------------- Session State ----------------
if "action_log" not in st.session_state:
    st.session_state.action_log = pd.DataFrame(
        columns=["操作时间", "推广类型", "对象名称", "执行动作", "调整内容", "备注"]
    )

# ---------------- 列名别名 ----------------
COL_ALIASES = {
    "日期":       ["日期", "date", "Date"],
    "商品ID":     ["主体ID", "商品ID", "宝贝ID"],
    "商品名称":   ["主体名称", "商品名称", "宝贝名称"],
    "计划名称":   ["计划名字", "计划名称", "推广计划名称"],
    "场景名称":   ["场景名字", "场景名称"],
    "关键词":     ["关键词", "词"],
    "人群包名称": ["人群包名称"],
    "花费":       ["花费", "消耗"],
    "成交金额":   ["总成交金额", "成交金额", "净成交金额"],
    "成交笔数":   ["总成交笔数", "成交笔数"],
    "点击量":     ["点击量"],
    "展现量":     ["展现量"],
    "加购数":     ["总购物车数", "加购数"],
    "收藏数":     ["收藏宝贝数", "收藏数"],
    "ROI":        ["投入产出比", "实际投产比", "投产比", "ROI"],
    "CPC":        ["平均点击花费", "CPC"],
    "CTR":        ["点击率", "CTR"],
}

def resolve_col(df, key):
    for a in COL_ALIASES.get(key, []):
        if a in df.columns:
            return a
    return None

# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.header("⚙️ 阈值设置")
    roi_target   = st.number_input("保本目标 ROI",      min_value=0.1,   value=3.0,   step=0.1)
    min_cost     = st.number_input("最小有效花费(元)",  min_value=0,     value=15,    step=5)
    max_cpc_warn = st.number_input("CPC 过高预警(元)",  min_value=0.0,   value=0.3,   step=0.05, format="%.2f")
    min_ctr_warn = st.number_input("CTR 过低预警",      min_value=0.001, value=0.02,  step=0.001, format="%.3f")
    st.caption(
        f"当前策略：ROI目标 {roi_target} ｜ 最小花费 ¥{min_cost} "
        f"｜ CPC预警 ¥{max_cpc_warn} ｜ CTR预警 {min_ctr_warn:.1%}"
    )
    st.divider()
    st.header("🔍 全局筛选")
    filter_levels = st.multiselect(
        "策略等级（作用于明细与待调整清单）",
        ["✅优质可放大", "⚠️观察待优化", "🔻高花费低ROI",
         "🟡样本不足", "🟡零点击", "🔴无成交"],
        default=["✅优质可放大", "⚠️观察待优化", "🔻高花费低ROI", "🔴无成交"],
    )
    top_n = st.slider("排行榜 Top N", 5, 50, 15, step=5)
    st.divider()
    st.header("📁 数据源")
    upload_files = st.file_uploader(
        "上传万相台 Excel/CSV 报表，可多选",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
    )

# ---------------- 缓存：读取 ----------------
@st.cache_data(show_spinner="正在读取文件...")
def load_raw(files_data):
    """files_data: tuple[(name, bytes), ...]"""
    frames = []
    for name, data in files_data:
        try:
            if name.lower().endswith(".csv"):
                tmp = pd.read_csv(io.BytesIO(data))
            else:
                tmp = pd.read_excel(io.BytesIO(data))
            tmp.columns = [str(c).strip() for c in tmp.columns]
            frames.append(tmp)
        except Exception as e:
            st.warning(f"文件 {name} 读取失败: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ---------------- 缓存：清洗 ----------------
@st.cache_data(show_spinner="正在清洗数据...")
def build_normalized(df_raw):
    if df_raw.empty:
        return pd.DataFrame()
    n = len(df_raw)
    out = pd.DataFrame(index=range(n))
    # 日期
    c = resolve_col(df_raw, "日期")
    out["日期"] = pd.to_datetime(df_raw[c], errors="coerce") if c else pd.NaT
    # 文本类
    for key in ["商品ID", "商品名称", "计划名称", "场景名称", "关键词", "人群包名称"]:
        c = resolve_col(df_raw, key)
        out[key] = df_raw[c].astype(str).str.strip() if c else ""
    # 数值类
    for key, new_col in [
        ("花费", "花费"), ("成交金额", "成交金额"), ("成交笔数", "成交笔数"),
        ("点击量", "点击量"), ("展现量", "展现量"),
        ("加购数", "加购数"), ("收藏数", "收藏数"),
    ]:
        c = resolve_col(df_raw, key)
        out[new_col] = pd.to_numeric(df_raw[c], errors="coerce").fillna(0) if c else 0.0
    # ROI / CPC / CTR
    c = resolve_col(df_raw, "ROI")
    out["ROI"] = (pd.to_numeric(df_raw[c], errors="coerce")
                  .fillna(0).replace([np.inf, -np.inf], 0)) if c else \
                 np.where(out["花费"] > 0, out["成交金额"] / out["花费"], 0)
    c = resolve_col(df_raw, "CPC")
    out["CPC"] = pd.to_numeric(df_raw[c], errors="coerce").fillna(0) if c else \
                 np.where(out["点击量"] > 0, out["花费"] / out["点击量"], 0)
    c = resolve_col(df_raw, "CTR")
    out["CTR"] = pd.to_numeric(df_raw[c], errors="coerce").fillna(0) if c else \
                 np.where(out["展现量"] > 0, out["点击量"] / out["展现量"], 0)
    return out

# ---------------- 向量化：策略 ----------------
def add_suggestions(df, target_roi, min_spend,
                    cost_col="花费", roi_col="ROI", click_col="点击量"):
    """用 np.select 向量化生成 [等级/策略/执行] 三列。"""
    if df.empty:
        df["等级"] = df["策略"] = df["执行"] = ""
        return df
    cost  = pd.to_numeric(df[cost_col],  errors="coerce").fillna(0).values
    roi   = pd.to_numeric(df[roi_col],   errors="coerce").fillna(0).replace(
                [np.inf, -np.inf], 0).values
    click = pd.to_numeric(df[click_col], errors="coerce").fillna(0).values
    c_samp   = cost < min_spend
    c_click0 = (~c_samp) & (click <= 0)
    c_good   = (~c_samp) & (click > 0) & (roi >= target_roi)
    c_bad    = (~c_samp) & (click > 0) & (roi > 0) & (roi < target_roi * 0.6) \
               & (cost > min_spend * 3)
    c_warn   = (~c_samp) & (click > 0) & (roi > 0) & (roi < target_roi) & (~c_bad)
    c_none   = (~c_samp) & (click > 0) & (roi <= 0)
    conds = [c_samp, c_click0, c_good, c_bad, c_warn, c_none]
    lvls  = ["🟡样本不足", "🟡零点击", "✅优质可放大", "🔻高花费低ROI",
             "⚠️观察待优化", "🔴无成交"]
    strs  = ["花费少继续观察", "有展现无点击", "投产达标可放大",
             "花费高投产差", "略低于目标", "有花费无订单"]
    acts  = ["无操作", "降出价或优化素材", "预算 +10~20%",
             "降价 30% 或暂停", "出价下调 10-20% 观察", "降价，无改善暂停"]
    df["等级"] = np.select(conds, lvls, default="🔴无成交")
    df["策略"] = np.select(conds, strs, default="有花费无订单")
    df["执行"] = np.select(conds, acts, default="降价，无改善暂停")
    return df

# ---------------- 分级预警 ----------------
def add_warnings(df, cpc_max, ctr_min):
    """分级预警：
       CPC  > cpc_max*3            -> 🚨CPC严重超标
       CPC  > cpc_max              -> ⚠️CPC偏高
       CTR  < ctr_min*0.5          -> 🚨CTR严重过低
       CTR  < ctr_min (且>0)       -> ⚠️CTR偏低
       标记：无异常 -> ✅正常；含🚨 -> 🚨严重；其余 -> ⚠️预警
    """
    if df.empty:
        df["预警标记"] = df["预警说明"] = ""
        return df
    cpc = pd.to_numeric(df["CPC"], errors="coerce").fillna(0).values
    ctr = pd.to_numeric(df["CTR"], errors="coerce").fillna(0).values
    msgs, tags = [], []
    cpc_severe = cpc_max * 3
    ctr_severe = ctr_min * 0.5
    for c, t in zip(cpc, ctr):
        w = []
        if c > cpc_severe:
            w.append(f"🚨CPC严重超标 {c:.2f}")
        elif c > cpc_max:
            w.append(f"⚠️CPC偏高 {c:.2f}")
        if 0 < t < ctr_severe:
            w.append(f"🚨CTR严重过低 {t:.2%}")
        elif 0 < t < ctr_min:
            w.append(f"⚠️CTR偏低 {t:.2%}")
        if not w:
            msgs.append("无异常")
            tags.append("✅正常")
        else:
            msgs.append("；".join(w))
            tags.append("🚨严重" if any("🚨" in x for x in w) else "⚠️预警")
    df["预警说明"] = msgs
    df["预警标记"] = tags
    return df

# ---------------- 分组汇总 ----------------
def group_sum(df, grp_keys, target_roi, min_spend):
    if df.empty or not grp_keys:
        return pd.DataFrame()
    grp_keys = [k for k in grp_keys
                if k in df.columns and df[k].astype(str).str.strip().ne("").any()]
    if not grp_keys:
        return pd.DataFrame()
    agg = {}
    for src, dst in [("花费", "总花费"), ("成交金额", "总成交金额"),
                     ("点击量", "总点击"), ("展现量", "总展现"),
                     ("加购数", "总加购"), ("收藏数", "总收藏")]:
        if src in df.columns:
            agg[dst] = (src, "sum")
    if not agg:
        return pd.DataFrame()
    g = df.groupby(grp_keys, dropna=False).agg(**agg).reset_index()
    g["整体ROI"] = (np.where(g["总花费"] > 0, g["总成交金额"] / g["总花费"], 0)
                    if {"总花费", "总成交金额"} <= set(g.columns) else 0)
    g["平均CPC"] = (np.where(g["总点击"] > 0, g["总花费"] / g["总点击"], 0)
                    if {"总点击", "总花费"} <= set(g.columns) else 0)
    g = add_suggestions(g, target_roi, min_spend,
                        cost_col="总花费", roi_col="整体ROI", click_col="总点击")
    return g

# ==============================================================
#                       主流程
# ==============================================================
if not upload_files:
    st.info("👈 上传万相台报表：商品报表看【待调整商品】；计划报表看【计划优化】；"
            "关键词明细看【商品×关键词】。字段会自动识别。")
    st.stop()
files_data = tuple((f.name, f.getvalue()) for f in upload_files)
df_raw = load_raw(files_data)
if df_raw.empty:
    st.error("未读取到任何数据。")
    st.stop()
st.subheader("📄 原始文件概览")
st.caption(f"合并总行数：{len(df_raw):,} ｜ 字段数：{len(df_raw.columns)}")
with st.expander("查看识别到的原始字段"):
    st.markdown("`" + "`, `".join(df_raw.columns) + "`")
    st.dataframe(df_raw.head(8), hide_index=True, use_container_width=True)
df = build_normalized(df_raw)
if df.empty:
    st.error("数据为空，请检查报表格式。")
    st.stop()
# ---- 全局筛选 ----
with st.sidebar:
    st.divider()
    st.header("🗓 日期 & 关键词筛选")
    if df["日期"].notna().any():
        dmin, dmax = df["日期"].min().date(), df["日期"].max().date()
        date_range = st.date_input("日期范围", value=(dmin, dmax),
                                   min_value=dmin, max_value=dmax)
    else:
        date_range = None
    kw = st.text_input("商品名称包含关键词", "")
dff = df.copy()
if date_range and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    dff = dff[(dff["日期"].isna()) | ((dff["日期"] >= start) & (dff["日期"] <= end))]
if kw:
    dff = dff[dff["商品名称"].str.contains(kw, case=False, na=False)]
# ---- 生成带建议 / 预警的明细 ----
df_detail = add_suggestions(dff.copy(), roi_target, min_cost)
df_detail = add_warnings(df_detail, max_cpc_warn, min_ctr_warn)
# ---- 分组 ----
df_prod_sum  = group_sum(dff, ["商品ID", "商品名称"], roi_target, min_cost)
df_plan_sum  = group_sum(dff, ["计划名称", "场景名称"], roi_target, min_cost)
df_kw_sum    = group_sum(dff, ["关键词"], roi_target, min_cost)
df_crowd_sum = group_sum(dff, ["人群包名称"], roi_target, min_cost)
df_item_kw   = group_sum(dff, ["商品名称", "商品ID", "关键词"], roi_target, min_cost) \
               if (dff["关键词"].astype(str).str.strip().ne("").any()
                   and dff["商品名称"].astype(str).str.strip().ne("").any()) else pd.DataFrame()

# ==============================================================
#                       大盘 KPI
# ==============================================================
tc   = dff["花费"].sum()
tg   = dff["成交金额"].sum()
tclk = dff["点击量"].sum()
troi = tg / tc if tc > 0 else 0
st.markdown("---")
c1, c2, c3, c4 = st.columns(4)
c1.metric("总花费",   f"¥{tc:,.2f}")
c2.metric("总 GMV",   f"¥{tg:,.2f}")
c3.metric("整体 ROI", f"{troi:.2f}", delta=f"目标 {roi_target}",
          delta_color="normal" if troi >= roi_target else "inverse")
c4.metric("总点击",   f"{int(tclk):,}")
gc = int((df_detail["等级"] == "✅优质可放大").sum())
bc = int((df_detail["等级"] == "🔻高花费低ROI").sum())
nc = int((df_detail["等级"] == "🔴无成交").sum())
sc = int((df_detail["预警标记"] == "🚨严重").sum())
if troi >= roi_target:
    diag = (f"✅ 整体 ROI ({troi:.2f}) 达标。优质 {gc} 个可放大；"
            f"关注 {bc} 个高花费低投产；严重预警 {sc} 个。")
else:
    diag = (f"⚠️ 整体 ROI ({troi:.2f}) 低于 {roi_target}。"
            f"优先处理 {bc} 个高花费低ROI；优质 {gc} 个可放大；"
            f"{nc} 个无成交建议关停；严重预警 {sc} 个。")
st.info(diag)

# ==============================================================
#                       分页签
# ==============================================================
need_levels = ["🔻高花费低ROI", "🔴无成交", "⚠️观察待优化", "🟡零点击"]
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🚨待调整商品(默认)", "📦商品优化", "📋计划优化", "🎯商品×关键词", "🔑关键词优化", "👥人群优化", "明细 / 趋势 / 记录"])

COLOR_MAP = {
    "🔻高花费低ROI": "#e74c3c", "🔴无成交": "#c0392b",
    "⚠️观察待优化":  "#f39c12", "🟡零点击": "#95a5a6",
    "🟡样本不足":    "#bdc3c7", "✅优质可放大": "#2ecc71",
}

def render_group_tab(df_group, entity_name, key_col, info_text, filename, default_levels):
    st.info(info_text)
    if df_group.empty:
        st.warning(f"未识别【{entity_name}】列，请上传对应类型的报表。")
        return
    all_levels = list(df_group["等级"].unique())
    sel = st.multiselect(
        "展示等级", all_levels,
        default=[l for l in default_levels if l in all_levels],
        key=f"sel_{key_col}",
    )
    view = df_group[df_group["等级"].isin(sel)] if sel else df_group
    if view.empty:
        st.info("当前筛选下没有数据。")
        return
    pe = view[view["总花费"] >= min_cost]
    if not pe.empty:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(
                pe.nlargest(top_n, "总花费"), x="总花费", y=key_col,
                orientation="h", title=f"TOP{top_n} {entity_name} 花费",
                text_auto=".1f",
            )
            fig.update_layout(yaxis=dict(autorange="reversed"), height=420)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig2 = px.bar(
                pe.sort_values("整体ROI", ascending=False).head(top_n),
                x=key_col, y="整体ROI", color="等级",
                color_discrete_map=COLOR_MAP,
                title=f"{entity_name} ROI（红=保本 {roi_target}）",
                text_auto=".2f",
            )
            fig2.add_hline(y=roi_target, line_dash="dash", line=dict(color="red"))
            fig2.update_layout(xaxis_tickangle=-45, height=420)
            st.plotly_chart(fig2, use_container_width=True)
    show = [c for c in [key_col, "总花费", "总成交金额", "整体ROI", "平均CPC",
                        "总点击", "总加购", "等级", "策略", "执行"]
            if c in view.columns]
    st.dataframe(
        view[show].round(2),
        use_container_width=True,
        hide_index=True,
        column_config={
            "总花费":     st.column_config.NumberColumn(format="¥%.2f"),
            "总成交金额": st.column_config.NumberColumn(format="¥%.2f"),
            "整体ROI":   st.column_config.NumberColumn(format="%.2f"),
            "平均CPC":   st.column_config.NumberColumn(format="¥%.3f"),
        },
    )
    st.download_button(
        f"📥 下载{entity_name}清单",
        data=view.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename, mime="text/csv", key=f"dl_{key_col}",
    )

# ---------- Tab 1: 待调整商品 ----------
with tab1:
    st.markdown("默认展示【需要调整】的商品（高花费低ROI / 无成交 / 观察 / 零点击）。")
    st.info("💡AI分析方式：下载「待调整商品清单.csv」，上传豆包网页版粘贴提示词即可得到优化报告。")
    if df_prod_sum.empty:
        st.warning("未识别【商品名称】列。")
    else:
        view = df_prod_sum[df_prod_sum["等级"].isin(need_levels)]
        st.markdown(f"#### 共 {len(view)} 个待调整商品")
        if not view.empty:
            f = px.bar(
                view.sort_values("总花费", ascending=False).head(top_n),
                x="商品名称", y="整体ROI", color="等级",
                color_discrete_map=COLOR_MAP, text_auto=".2f",
                title=f"待调整商品 ROI（红=保本 {roi_target}）",
            )
            f.add_hline(y=roi_target, line_dash="dash", line=dict(color="red"))
            f.update_layout(xaxis_tickangle=-45, height=460)
            st.plotly_chart(f, use_container_width=True)
            key = view[view["等级"].isin(["🔻高花费低ROI", "🔴无成交"])]
            if not key.empty:
                fk = px.bar(
                    key.sort_values("总花费", ascending=False).head(top_n),
                    x="总花费", y="商品名称", orientation="h",
                    color="等级", color_discrete_map=COLOR_MAP, text_auto=".1f",
                    title="⚠️ 高花费低ROI / 无成交商品（优先处理）",
                )
                fk.update_layout(yaxis=dict(autorange="reversed"), height=460)
                st.plotly_chart(fk, use_container_width=True)
        show = [c for c in ["商品ID", "商品名称", "总花费", "总成交金额",
                            "整体ROI", "总点击", "总加购", "等级", "策略", "执行"]
                if c in view.columns]
        st.dataframe(
            view[show].round(2),
            use_container_width=True, hide_index=True,
            column_config={
                "总花费":     st.column_config.NumberColumn(format="¥%.2f"),
                "总成交金额": st.column_config.NumberColumn(format="¥%.2f"),
                "整体ROI":   st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.download_button("📥 下载待调整商品清单",
                           data=view.to_csv(index=False).encode("utf-8-sig"),
                           file_name="待调整商品清单.csv", mime="text/csv")

# ---------- Tab 2: 商品优化 ----------
with tab2:
    render_group_tab(
        df_prod_sum, "商品", "商品名称",
        "全部商品按等级筛选查看。",
        "全部商品清单.csv",
        default_levels=list(COLOR_MAP.keys()),
    )

# ---------- Tab 3: 计划优化 ----------
with tab3:
    render_group_tab(
        df_plan_sum, "计划", "计划名称",
        "计划报表按计划 / 场景汇总，看哪个计划烧钱、哪个计划 ROI 差。",
        "计划优化清单.csv",
        default_levels=list(COLOR_MAP.keys()),
    )

# ---------- Tab 4: 商品 × 关键词 ----------
with tab4:
    render_group_tab(
        df_item_kw, "商品×关键词", "关键词",
        "最细粒度：每个商品 × 关键词一行。需要导出【关键词数据明细】报表。",
        "商品关键词优化清单.csv",
        default_levels=list(COLOR_MAP.keys()),
    )

# ---------- Tab 5: 关键词优化 ----------
with tab5:
    render_group_tab(
        df_kw_sum, "关键词", "关键词",
        "关键词维度汇总。需报表含【关键词】列。",
        "关键词清单.csv",
        default_levels=list(COLOR_MAP.keys()),
    )

# ---------- Tab 6: 人群优化 ----------
with tab6:
    render_group_tab(
        df_crowd_sum, "人群包", "人群包名称",
        "人群包维度汇总。需报表含【人群包名称】列。",
        "人群清单.csv",
        default_levels=list(COLOR_MAP.keys()),
    )

# ---------- Tab 7: 明细 / 趋势 / 记录 ----------
with tab7:
    st.markdown("### 🎯 明细清单")
    # 预警级别多选
    warn_filter = st.multiselect(
        "预警级别筛选",
        ["🚨严重", "⚠️预警", "✅正常"],
        default=["🚨严重", "⚠️预警", "✅正常"],
        key="warn_filter",
    )
    dv = df_detail.copy()
    if filter_levels:
        dv = dv[dv["等级"].isin(filter_levels)]
    if warn_filter and "预警标记" in dv.columns:
        dv = dv[dv["预警标记"].isin(warn_filter)]
    show = [c for c in ["日期", "商品ID", "商品名称", "计划名称", "关键词", "人群包名称",
                        "花费", "成交金额", "ROI", "CPC", "CTR", "加购数",
                        "预警标记", "预警说明", "等级", "策略", "执行"]
            if c in dv.columns]
    st.dataframe(
        dv[show].round(3),
        use_container_width=True, hide_index=True,
        column_config={
            "花费":     st.column_config.NumberColumn(format="¥%.2f"),
            "成交金额": st.column_config.NumberColumn(format="¥%.2f"),
            "ROI":     st.column_config.NumberColumn(format="%.2f"),
            "CPC":     st.column_config.NumberColumn(format="¥%.3f"),
            "CTR":     st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    st.download_button("📥 下载筛选明细",
                       data=dv.to_csv(index=False).encode("utf-8-sig"),
                       file_name="筛选明细.csv", mime="text/csv")
    st.markdown("### 📈 日度时间趋势")
    if df_detail["日期"].notna().any():
        dd = df_detail.dropna(subset=["日期"]).groupby("日期").agg(
            花费=("花费", "sum"),
            成交金额=("成交金额", "sum"),
            点击量=("点击量", "sum"),
        ).reset_index()
        dd["ROI"] = np.where(dd["花费"] > 0, dd["成交金额"] / dd["花费"], 0)
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(
                px.line(dd, x="日期", y=["花费", "成交金额"], markers=True,
                        title="每日花费 vs 成交金额"),
                use_container_width=True,
            )
        with c2:
            f2 = px.line(dd, x="日期", y="ROI", markers=True, title="每日 ROI")
            f2.add_hline(y=roi_target, line_dash="dash", line=dict(color="red"))
            st.plotly_chart(f2, use_container_width=True)
    else:
        st.warning("报表缺少【日期】列或日期均无效。")
    st.markdown("### 📝 投放操作记录")
    st.caption("仅当前会话保存，刷新网页会丢失，请及时导出。")
    with st.form("log_form"):
        f1, f2, f3 = st.columns(3)
        with f1:
            t1 = st.text_input("推广类型")
            t2 = st.text_input("对象名称")
        with f2:
            act = st.selectbox("执行动作",
                               ["提升预算", "降低预算", "提高出价", "降低出价",
                                "暂停单元", "开启单元", "修改创意", "其他"])
        with f3:
            adj = st.text_input("调整内容")
            note = st.text_input("备注")
        if st.form_submit_button("✅ 保存记录"):
            new_row = {
                "操作时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "推广类型": t1, "对象名称": t2,
                "执行动作": act, "调整内容": adj, "备注": note,
            }
            st.session_state.action_log = pd.concat(
                [st.session_state.action_log, pd.DataFrame([new_row])],
                ignore_index=True,
            )
            st.success("已保存！")
    st.dataframe(st.session_state.action_log, hide_index=True, use_container_width=True)
    st.download_button(
        "📥 导出操作记录",
        data=st.session_state.action_log.to_csv(index=False).encode("utf-8-sig"),
        file_name="操作记录.csv", mime="text/csv",
    )
