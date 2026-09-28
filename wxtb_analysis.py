import io
import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import requests


# ============================================================
# 0. 页面基础设置
# ============================================================

st.set_page_config(
    page_title="淘宝投放军师 V10",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧠 淘宝投放军师 V10")
st.caption("数据分析 → 问题诊断 → 今日决策 → 执行清单 → 复盘")


# ============================================================
# 1. Session State
# ============================================================

if "action_log" not in st.session_state:
    st.session_state.action_log = pd.DataFrame(
        columns=[
            "操作时间",
            "推广类型",
            "对象名称",
            "执行动作",
            "建议值",
            "实际值",
            "操作结果",
            "备注",
        ]
    )

if "last_ai_report" not in st.session_state:
    st.session_state.last_ai_report = ""

if "manual_api_key" not in st.session_state:
    st.session_state.manual_api_key = ""


# ============================================================
# 2. 全局样式
# ============================================================

COLOR_MAP = {
    "🔴立即处理": "#e74c3c",
    "🟠重点观察": "#e67e22",
    "🟡样本不足": "#f1c40f",
    "🟢可以放量": "#27ae60",
    "⚪暂不操作": "#95a5a6",
}

LEVEL_ORDER = [
    "🔴立即处理",
    "🟠重点观察",
    "🟡样本不足",
    "🟢可以放量",
    "⚪暂不操作",
]


# ============================================================
# 3. 字段别名
# ============================================================

COL_ALIASES = {
    "日期": [
        "日期",
        "date",
        "Date",
        "统计日期",
    ],

    "商品ID": [
        "主体ID",
        "商品ID",
        "宝贝ID",
        "商品id",
        "item_id",
    ],

    "商品名称": [
        "主体名称",
        "商品名称",
        "宝贝名称",
        "商品",
        "宝贝",
    ],

    "计划名称": [
        "计划名字",
        "计划名称",
        "推广计划名称",
        "计划",
    ],

    "场景名称": [
        "场景名字",
        "场景名称",
        "推广场景",
        "场景",
    ],

    "关键词": [
        "关键词",
        "词",
        "搜索词",
        "词名字/词包名字",
        "词名字",
        "词包名字",
        "词ID/词包ID",
    ],

    "人群包名称": [
        "人群包名称",
        "人群包",
        "人群",
    ],

    "花费": [
        "花费",
        "消耗",
        "总花费",
        "推广花费",
    ],

    "成交金额": [
        "总成交金额",
        "成交金额",
        "净成交金额",
        "支付金额",
        "成交额",
    ],

    "成交笔数": [
        "总成交笔数",
        "成交笔数",
        "订单数",
        "成交订单数",
    ],

    "点击量": [
        "点击量",
        "点击数",
        "点击",
    ],

    "展现量": [
        "展现量",
        "曝光量",
        "展现",
        "曝光",
    ],

    "加购数": [
        "总购物车数",
        "加购数",
        "加购人数",
        "购物车数",
    ],

    "收藏数": [
        "收藏宝贝数",
        "收藏数",
        "收藏人数",
    ],

    "ROI": [
        "投入产出比",
        "实际投产比",
        "投产比",
        "ROI",
        "投产",
    ],

    "CPC": [
        "平均点击花费",
        "CPC",
        "平均点击成本",
    ],

    "CTR": [
        "点击率",
        "CTR",
    ],
}


def resolve_col(df, key):
    aliases = COL_ALIASES.get(key, [])

    for col in aliases:
        if col in df.columns:
            return col

    # 模糊匹配
    for actual in df.columns:
        actual_str = str(actual).strip().lower()

        for alias in aliases:
            alias_str = str(alias).strip().lower()

            if alias_str == actual_str:
                return actual

    return None


# ============================================================
# 4. 工具函数
# ============================================================

def safe_div(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)

    return np.where(
        b > 0,
        a / b,
        0
    )


def pct_change(current, previous):
    if previous is None or previous == 0:
        return 0

    return (current - previous) / abs(previous)


def format_money(x):
    return f"¥{x:,.2f}"


def format_pct(x):
    return f"{x:.2%}"


def clean_numeric(series):
    return (
        pd.to_numeric(
            series.astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("¥", "", regex=False)
            .str.replace("%", "", regex=False),
            errors="coerce",
        )
        .fillna(0)
    )


# ============================================================
# 5. 数据读取
# ============================================================

@st.cache_data(show_spinner="正在读取报表...")
def load_raw(files_data):

    frames = []

    for name, data in files_data:

        try:

            if name.lower().endswith(".csv"):

                try:
                    tmp = pd.read_csv(
                        io.BytesIO(data),
                        encoding="utf-8-sig"
                    )
                except Exception:
                    tmp = pd.read_csv(
                        io.BytesIO(data),
                        encoding="gb18030"
                    )

            else:

                tmp = pd.read_excel(
                    io.BytesIO(data)
                )

            tmp.columns = [
                str(c).strip()
                for c in tmp.columns
            ]

            tmp["__来源文件"] = name

            frames.append(tmp)

        except Exception as e:

            st.error(
                f"文件 {name} 读取失败：{e}"
            )

    if not frames:
        return pd.DataFrame()

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False
    )


# ============================================================
# 6. 数据标准化
# ============================================================

@st.cache_data(show_spinner="正在标准化数据...")
def build_normalized(df_raw):

    if df_raw.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=df_raw.index)

    # 日期
    c = resolve_col(df_raw, "日期")

    if c:
        out["日期"] = pd.to_datetime(
            df_raw[c],
            errors="coerce"
        )
    else:
        out["日期"] = pd.NaT

    # 文本字段
    text_fields = [
        "商品ID",
        "商品名称",
        "计划名称",
        "场景名称",
        "关键词",
        "人群包名称",
    ]

    for key in text_fields:

        c = resolve_col(df_raw, key)

        if c:

            out[key] = (
                df_raw[c]
                .astype(str)
                .replace("nan", "")
                .str.strip()
            )

        else:

            out[key] = ""

    # 数值字段
    numeric_fields = [
        "花费",
        "成交金额",
        "成交笔数",
        "点击量",
        "展现量",
        "加购数",
        "收藏数",
    ]

    for key in numeric_fields:

        c = resolve_col(df_raw, key)

        if c:

            out[key] = clean_numeric(
                df_raw[c]
            )

        else:

            out[key] = 0.0

    # ROI
    c = resolve_col(df_raw, "ROI")

    if c:

        roi = clean_numeric(
            df_raw[c]
        )

        # 如果原始 ROI 是百分比形式，例如 300%
        if roi.max() > 100:
            roi = roi / 100

        out["ROI"] = (
            roi
            .replace(
                [np.inf, -np.inf],
                0
            )
            .fillna(0)
        )

    else:

        out["ROI"] = safe_div(
            out["成交金额"],
            out["花费"]
        )

    # CPC
    c = resolve_col(df_raw, "CPC")

    if c:

        out["CPC"] = clean_numeric(
            df_raw[c]
        )

    else:

        out["CPC"] = safe_div(
            out["花费"],
            out["点击量"]
        )

    # CTR
    c = resolve_col(df_raw, "CTR")

    if c:

        ctr = clean_numeric(
            df_raw[c]
        )

        # 如果是 2.5 代表 2.5%
        if ctr.max() > 1:
            ctr = ctr / 100

        out["CTR"] = ctr

    else:

        out["CTR"] = safe_div(
            out["点击量"],
            out["展现量"]
        )

    # CVR
    out["CVR"] = safe_div(
        out["成交笔数"],
        out["点击量"]
    )

    # 加购率
    out["加购率"] = safe_div(
        out["加购数"],
        out["点击量"]
    )

    # 收藏率
    out["收藏率"] = safe_div(
        out["收藏数"],
        out["点击量"]
    )

    # 平均成交客单
    out["客单价"] = safe_div(
        out["成交金额"],
        out["成交笔数"]
    )

    return out


# ============================================================
# 7. 账户参数
# ============================================================

with st.sidebar:

    st.header("🎯 店铺目标")

    roi_target = st.number_input(
        "目标 ROI",
        min_value=0.1,
        value=3.0,
        step=0.1,
    )

    min_spend = st.number_input(
        "最小有效花费",
        min_value=0.0,
        value=30.0,
        step=5.0,
    )

    min_clicks = st.number_input(
        "最小有效点击",
        min_value=1,
        value=30,
        step=5,
    )

    min_orders = st.number_input(
        "高可信最低成交",
        min_value=1,
        value=3,
        step=1,
    )

    st.divider()

    st.header("📉 风险阈值")

    high_cpc_warn = st.number_input(
        "CPC 预警",
        min_value=0.0,
        value=0.30,
        step=0.05,
    )

    low_ctr_warn = st.number_input(
        "CTR 预警",
        min_value=0.0001,
        value=0.02,
        step=0.001,
        format="%.3f",
    )

    st.divider()

    st.header("⚙️ 自动调整幅度")

    scale_up_pct = st.slider(
        "优质商品放量",
        5,
        30,
        15,
        5,
    )

    reduce_bid_pct = st.slider(
        "低效商品降出价",
        5,
        40,
        15,
        5,
    )

    pause_spend_multiplier = st.slider(
        "高花费无成交倍数",
        1,
        10,
        3,
    )

    st.divider()

    st.header("📁 数据上传")

    upload_files = st.file_uploader(
        "上传万相台 Excel / CSV，可多选",
        type=[
            "xlsx",
            "xls",
            "csv",
        ],
        accept_multiple_files=True,
    )


# ============================================================
# 8. 无数据页面
# ============================================================

if not upload_files:

    st.info(
        "👈 上传万相台报表后，系统会自动生成："
        "今日军师、问题诊断、执行清单、商品/计划/关键词/人群分析。"
    )

    st.markdown(
        """
        ### V10 的核心不是“看报表”

        而是回答 5 个问题：

        **① 今天哪里有问题？**

        **② 为什么有问题？**

        **③ 哪些值得放大？**

        **④ 今天具体应该怎么调？**

        **⑤ 昨天调整以后有没有变好？**
        """
    )

    st.stop()


# ============================================================
# 9. 加载数据
# ============================================================

files_data = tuple(
    (
        f.name,
        f.getvalue()
    )
    for f in upload_files
)

df_raw = load_raw(files_data)

if df_raw.empty:

    st.error(
        "没有读取到有效数据。"
    )

    st.stop()

df = build_normalized(df_raw)

if df.empty:

    st.error(
        "标准化数据为空。"
    )

    st.stop()


# ============================================================
# 10. 全局筛选
# ============================================================

with st.sidebar:

    st.header("🗓 数据筛选")

    if df["日期"].notna().any():

        dmin = df["日期"].min().date()
        dmax = df["日期"].max().date()

        date_range = st.date_input(
            "日期范围",
            value=(dmin, dmax),
            min_value=dmin,
            max_value=dmax,
        )

    else:

        date_range = None

    product_keyword = st.text_input(
        "商品名称关键词",
        ""
    )

    plan_keyword = st.text_input(
        "计划名称关键词",
        ""
    )


dff = df.copy()

if date_range and len(date_range) == 2:

    start = pd.to_datetime(
        date_range[0]
    )

    end = (
        pd.to_datetime(
            date_range[1]
        )
        + pd.Timedelta(days=1)
    )

    dff = dff[
        (dff["日期"].isna())
        |
        (
            (dff["日期"] >= start)
            &
            (dff["日期"] < end)
        )
    ]

if product_keyword:

    dff = dff[
        dff["商品名称"]
        .str.contains(
            product_keyword,
            case=False,
            na=False
        )
    ]

if plan_keyword:

    dff = dff[
        dff["计划名称"]
        .str.contains(
            plan_keyword,
            case=False,
            na=False
        )
    ]


# ============================================================
# 11. 核心诊断引擎
# ============================================================

def calculate_confidence(
    spend,
    clicks,
    orders,
    min_spend,
    min_clicks,
    min_orders,
):

    score = 0

    if spend >= min_spend:
        score += 30

    if clicks >= min_clicks:
        score += 30

    if orders >= min_orders:
        score += 40

    if score >= 80:

        return (
            "🟢高可信",
            score
        )

    if score >= 50:

        return (
            "🟡中可信",
            score
        )

    return (
        "⚪样本不足",
        score
    )


def diagnose_row(
    row,
    roi_target,
    min_spend,
    min_clicks,
    min_orders,
    high_cpc_warn,
    low_ctr_warn,
    scale_up_pct,
    reduce_bid_pct,
    pause_spend_multiplier,
):

    spend = float(row["总花费"])
    revenue = float(row["总成交金额"])
    clicks = float(row["总点击"])
    impressions = float(row["总展现"])
    orders = float(row["总成交笔数"])
    add_cart = float(row["总加购"])

    roi = revenue / spend if spend > 0 else 0
    ctr = clicks / impressions if impressions > 0 else 0
    cpc = spend / clicks if clicks > 0 else 0
    cvr = orders / clicks if clicks > 0 else 0
    add_rate = add_cart / clicks if clicks > 0 else 0

    confidence, score = calculate_confidence(
        spend,
        clicks,
        orders,
        min_spend,
        min_clicks,
        min_orders,
    )

    # --------------------------------------------------------
    # 先判断样本
    # --------------------------------------------------------

    if confidence == "⚪样本不足":

        level = "🟡样本不足"

        action = "暂不操作"

        reason = (
            f"当前花费 {format_money(spend)}，"
            f"点击 {int(clicks)}，"
            f"成交 {int(orders)}，"
            "数据量不足以支持激进调整。"
        )

        return pd.Series(
            {
                "整体ROI": roi,
                "CTR": ctr,
                "CPC": cpc,
                "CVR": cvr,
                "加购率": add_rate,
                "置信度": confidence,
                "置信度分": score,
                "等级": level,
                "诊断": reason,
                "建议动作": action,
                "建议幅度": "0%",
                "优先级": 5,
            }
        )

    # --------------------------------------------------------
    # 漏斗诊断
    # --------------------------------------------------------

    problems = []

    if ctr > 0 and ctr < low_ctr_warn:

        problems.append(
            "CTR偏低：优先检查素材/人群匹配"
        )

    if cpc > high_cpc_warn:

        problems.append(
            "CPC偏高：流量获取成本偏高"
        )

    if clicks >= min_clicks and cvr == 0:

        problems.append(
            "点击后无成交：重点检查商品转化"
        )

    if add_rate < 0.03 and clicks >= min_clicks:

        problems.append(
            "加购率偏低：商品承接可能偏弱"
        )

    # --------------------------------------------------------
    # 核心决策
    # --------------------------------------------------------

    if (
        roi >= roi_target * 1.20
        and orders >= min_orders
    ):

        level = "🟢可以放量"

        action = (
            f"预算 +{scale_up_pct}%"
        )

        reason = (
            f"ROI {roi:.2f} 高于目标 "
            f"{roi_target:.2f}，"
            f"且已有 {int(orders)} 笔成交，"
            "具备一定放量基础。"
        )

        if problems:

            reason += (
                "；"
                + "；".join(problems)
            )

        priority = 2

    elif (
        roi < roi_target * 0.60
        and spend >= min_spend * 2
    ):

        level = "🔴立即处理"

        if clicks >= min_clicks and orders == 0:

            action = (
                f"高风险：降低出价 {reduce_bid_pct}%"
                "；必要时暂停低效单元"
            )

        else:

            action = (
                f"降低出价 {reduce_bid_pct}%"
            )

        reason = (
            f"花费 {format_money(spend)}，"
            f"ROI 仅 {roi:.2f}，"
            f"明显低于目标 {roi_target:.2f}。"
        )

        if problems:

            reason += (
                "主要问题："
                + "；".join(problems)
            )

        priority = 1

    elif (
        orders == 0
        and spend >= min_spend * pause_spend_multiplier
    ):

        level = "🔴立即处理"

        action = (
            "降低出价 / 暂停低效单元"
        )

        reason = (
            f"累计花费 {format_money(spend)}，"
            "仍然没有成交，"
            "已经超过无成交风险阈值。"
        )

        priority = 1

    elif roi < roi_target:

        level = "🟠重点观察"

        action = (
            f"降低出价 {max(5, reduce_bid_pct // 2)}%"
        )

        reason = (
            f"ROI {roi:.2f} 低于目标 "
            f"{roi_target:.2f}，"
            "但暂未达到强制处理阈值。"
        )

        if problems:

            reason += (
                "；"
                + "；".join(problems)
            )

        priority = 3

    else:

        level = "⚪暂不操作"

        action = "保持当前策略"

        reason = (
            f"ROI {roi:.2f} 已达到目标 "
            f"{roi_target:.2f}，"
            "当前没有明确需要调整的信号。"
        )

        priority = 4

    return pd.Series(
        {
            "整体ROI": roi,
            "CTR": ctr,
            "CPC": cpc,
            "CVR": cvr,
            "加购率": add_rate,
            "置信度": confidence,
            "置信度分": score,
            "等级": level,
            "诊断": reason,
            "建议动作": action,
            "建议幅度": (
                f"+{scale_up_pct}%"
                if level == "🟢可以放量"
                else (
                    f"-{reduce_bid_pct}%"
                    if level in [
                        "🔴立即处理",
                        "🟠重点观察",
                    ]
                    else "0%"
                )
            ),
            "优先级": priority,
        }
    )


# ============================================================
# 12. 汇总函数
# ============================================================

def group_summary(
    data,
    group_cols,
):

    if data.empty:
        return pd.DataFrame()

    valid_cols = [
        c
        for c in group_cols
        if c in data.columns
        and data[c]
        .astype(str)
        .str.strip()
        .ne("")
        .any()
    ]

    if not valid_cols:
        return pd.DataFrame()

    agg = {
        "总花费": ("花费", "sum"),
        "总成交金额": ("成交金额", "sum"),
        "总成交笔数": ("成交笔数", "sum"),
        "总点击": ("点击量", "sum"),
        "总展现": ("展现量", "sum"),
        "总加购": ("加购数", "sum"),
        "总收藏": ("收藏数", "sum"),
    }

    g = (
        data
        .groupby(
            valid_cols,
            dropna=False
        )
        .agg(**agg)
        .reset_index()
    )

    diagnostics = g.apply(
        lambda row: diagnose_row(
            row,
            roi_target,
            min_spend,
            min_clicks,
            min_orders,
            high_cpc_warn,
            low_ctr_warn,
            scale_up_pct,
            reduce_bid_pct,
            pause_spend_multiplier,
        ),
        axis=1,
    )

    g = pd.concat(
        [g, diagnostics],
        axis=1,
    )

    g["平均客单"] = safe_div(
        g["总成交金额"],
        g["总成交笔数"],
    )

    return g.sort_values(
        ["优先级", "总花费"],
        ascending=[True, False],
    )


# ============================================================
# 13. 建立各层数据
# ============================================================

df_product = group_summary(
    dff,
    ["商品ID", "商品名称"]
)

df_plan = group_summary(
    dff,
    ["计划名称", "场景名称"]
)

df_keyword = group_summary(
    dff,
    ["关键词"]
)

df_crowd = group_summary(
    dff,
    ["人群包名称"]
)

df_product_keyword = group_summary(
    dff,
    [
        "商品ID",
        "商品名称",
        "关键词",
    ]
)


# ============================================================
# 14. 大盘指标
# ============================================================

total_spend = dff["花费"].sum()
total_gmv = dff["成交金额"].sum()
total_orders = dff["成交笔数"].sum()
total_clicks = dff["点击量"].sum()
total_impressions = dff["展现量"].sum()
total_cart = dff["加购数"].sum()

overall_roi = (
    total_gmv / total_spend
    if total_spend > 0
    else 0
)

overall_ctr = (
    total_clicks / total_impressions
    if total_impressions > 0
    else 0
)

overall_cpc = (
    total_spend / total_clicks
    if total_clicks > 0
    else 0
)

overall_cvr = (
    total_orders / total_clicks
    if total_clicks > 0
    else 0
)


# ============================================================
# 15. 顶部 KPI
# ============================================================

st.markdown("---")

k1, k2, k3, k4, k5, k6 = st.columns(6)

k1.metric(
    "总花费",
    format_money(total_spend)
)

k2.metric(
    "GMV",
    format_money(total_gmv)
)

k3.metric(
    "整体 ROI",
    f"{overall_roi:.2f}",
    delta=(
        f"{overall_roi - roi_target:+.2f}"
        " vs目标"
    )
)

k4.metric(
    "成交",
    f"{int(total_orders):,}"
)

k5.metric(
    "CTR",
    format_pct(overall_ctr)
)

k6.metric(
    "CPC",
    format_money(overall_cpc)
)


# ============================================================
# 16. 军师首页
# ============================================================

st.markdown("---")

st.header("🧠 今日运营军师")

if df_product.empty:

    st.warning(
        "没有识别到商品维度，无法生成商品级军师建议。"
    )

else:

    urgent = df_product[
        df_product["等级"]
        == "🔴立即处理"
    ].copy()

    scale = df_product[
        df_product["等级"]
        == "🟢可以放量"
    ].copy()

    observe = df_product[
        df_product["等级"]
        == "🟠重点观察"
    ].copy()

    sample = df_product[
        df_product["等级"]
        == "🟡样本不足"
    ].copy()

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "🔴必须处理",
        len(urgent)
    )

    c2.metric(
        "🟢可以放量",
        len(scale)
    )

    c3.metric(
        "🟠重点观察",
        len(observe)
    )

    c4.metric(
        "🟡样本不足",
        len(sample)
    )

    # --------------------------------------------------------
    # 今日一句话判断
    # --------------------------------------------------------

    if (
        overall_roi >= roi_target
        and len(urgent) == 0
    ):

        st.success(
            f"🟢 今天的核心任务不是救火，而是寻找可以继续放量的商品。"
            f"当前整体 ROI {overall_roi:.2f}，目标 {roi_target:.2f}。"
        )

    elif len(urgent) > 0:

        st.error(
            f"🔴 今天优先处理低效流量。"
            f"当前有 {len(urgent)} 个商品进入立即处理名单，"
            f"不要先急着扩大预算。"
        )

    else:

        st.warning(
            f"🟠 当前投放处于观察阶段。"
            f"整体 ROI {overall_roi:.2f}，目标 {roi_target:.2f}。"
        )


# ============================================================
# 17. 今日执行清单
# ============================================================

st.markdown("---")

st.subheader("🎯 今天你只需要做这些")

if not df_product.empty:

    execute_cols = [
        "商品名称",
        "总花费",
        "总成交金额",
        "总成交笔数",
        "整体ROI",
        "CTR",
        "CPC",
        "CVR",
        "置信度",
        "等级",
        "诊断",
        "建议动作",
        "建议幅度",
    ]

    execute_cols = [
        c
        for c in execute_cols
        if c in df_product.columns
    ]

    execute_df = df_product[
        df_product["等级"].isin(
            [
                "🔴立即处理",
                "🟢可以放量",
                "🟠重点观察",
            ]
        )
    ][execute_cols].copy()

    if execute_df.empty:

        st.info(
            "目前没有明确需要执行的调整。"
        )

    else:

        st.dataframe(
            execute_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "总花费":
                    st.column_config.NumberColumn(
                        format="¥%.2f"
                    ),

                "总成交金额":
                    st.column_config.NumberColumn(
                        format="¥%.2f"
                    ),

                "整体ROI":
                    st.column_config.NumberColumn(
                        format="%.2f"
                    ),

                "CTR":
                    st.column_config.NumberColumn(
                        format="%.2%"
                    ),

                "CPC":
                    st.column_config.NumberColumn(
                        format="¥%.3f"
                    ),

                "CVR":
                    st.column_config.NumberColumn(
                        format="%.2%"
                    ),
            }
        )


# ============================================================
# 18. 漏斗诊断
# ============================================================

st.markdown("---")

st.header("🔬 大盘漏斗诊断")

funnel_df = pd.DataFrame(
    {
        "阶段": [
            "曝光",
            "点击",
            "加购",
            "成交",
        ],
        "数量": [
            total_impressions,
            total_clicks,
            total_cart,
            total_orders,
        ],
    }
)

fig_funnel = go.Figure(
    go.Funnel(
        y=funnel_df["阶段"],
        x=funnel_df["数量"],
        textinfo="value+percent initial",
    )
)

fig_funnel.update_layout(
    height=430,
    margin=dict(
        l=20,
        r=20,
        t=30,
        b=20,
    ),
)

st.plotly_chart(
    fig_funnel,
    use_container_width=True
)

fc1, fc2, fc3, fc4 = st.columns(4)

fc1.metric(
    "CTR",
    format_pct(overall_ctr)
)

fc2.metric(
    "CPC",
    format_money(overall_cpc)
)

fc3.metric(
    "加购率",
    format_pct(
        total_cart / total_clicks
        if total_clicks > 0
        else 0
    )
)

fc4.metric(
    "点击成交率",
    format_pct(overall_cvr)
)

funnel_problems = []

if overall_ctr < low_ctr_warn:

    funnel_problems.append(
        "CTR偏低：优先检查素材、商品首图、人群匹配。"
    )

if overall_cpc > high_cpc_warn:

    funnel_problems.append(
        "CPC偏高：检查竞争环境、出价以及低效流量。"
    )

if overall_cvr < 0.01 and total_clicks >= min_clicks:

    funnel_problems.append(
        "点击后成交率偏低：重点检查商品承接、价格、详情页和评价。"
    )

if not funnel_problems:

    st.success(
        "🟢 当前没有发现明显的漏斗级异常。"
    )

else:

    for p in funnel_problems:

        st.warning(
            "• " + p
        )


# ============================================================
# 19. 商品优先级
# ============================================================

st.markdown("---")

st.header("🚨 商品优先级")

if not df_product.empty:

    priority_df = df_product[
        df_product["等级"].isin(
            [
                "🔴立即处理",
                "🟢可以放量",
                "🟠重点观察",
            ]
        )
    ].copy()

    if not priority_df.empty:

        fig = px.bar(
            priority_df.head(20),
            x="总花费",
            y="商品名称",
            color="等级",
            color_discrete_map=COLOR_MAP,
            orientation="h",
            title="按优先级排列",
        )

        fig.update_layout(
            yaxis=dict(
                autorange="reversed"
            ),
            height=550,
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )


# ============================================================
# 20. 变化检测
# ============================================================

st.markdown("---")

st.header("📈 数据变化检测")

if (
    dff["日期"].notna().any()
    and dff["日期"].nunique() >= 2
):

    daily = (
        dff
        .dropna(subset=["日期"])
        .groupby("日期")
        .agg(
            花费=("花费", "sum"),
            成交金额=("成交金额", "sum"),
            成交笔数=("成交笔数", "sum"),
            点击量=("点击量", "sum"),
        )
        .reset_index()
    )

    daily["ROI"] = safe_div(
        daily["成交金额"],
        daily["花费"]
    )

    daily["CPC"] = safe_div(
        daily["花费"],
        daily["点击量"]
    )

    daily = daily.sort_values(
        "日期"
    )

    if len(daily) >= 2:

        latest = daily.iloc[-1]
        previous = daily.iloc[-2]

        roi_change = pct_change(
            latest["ROI"],
            previous["ROI"]
        )

        spend_change = pct_change(
            latest["花费"],
            previous["花费"]
        )

        order_change = pct_change(
            latest["成交笔数"],
            previous["成交笔数"]
        )

        cc1, cc2, cc3 = st.columns(3)

        cc1.metric(
            "ROI变化",
            format_pct(roi_change),
        )

        cc2.metric(
            "花费变化",
            format_pct(spend_change),
        )

        cc3.metric(
            "成交变化",
            format_pct(order_change),
        )

        if roi_change <= -0.20:

            st.error(
                "🔴 最近一天 ROI 较上一天明显下降，建议优先检查低效商品和计划。"
            )

        elif roi_change >= 0.20:

            st.success(
                "🟢 最近一天 ROI 明显改善，可以重点检查哪些商品贡献了增长。"
            )

        else:

            st.info(
                "🟡 最近一天 ROI 没有出现剧烈变化。"
            )

        trend_col1, trend_col2 = st.columns(2)

        with trend_col1:

            fig = px.line(
                daily,
                x="日期",
                y=[
                    "花费",
                    "成交金额",
                ],
                markers=True,
                title="花费 / GMV趋势",
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        with trend_col2:

            fig = px.line(
                daily,
                x="日期",
                y="ROI",
                markers=True,
                title="ROI趋势",
            )

            fig.add_hline(
                y=roi_target,
                line_dash="dash",
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )


# ============================================================
# 21. 标签页
# ============================================================

tabs = st.tabs(
    [
        "🚨立即处理",
        "🟢放量机会",
        "📦商品",
        "📋计划",
        "🔑关键词",
        "👥人群",
        "📝操作复盘",
        "🤖AI军师",
    ]
)


# ============================================================
# Tab 1 立即处理
# ============================================================

with tabs[0]:

    st.subheader(
        "🚨 今天优先处理"
    )

    if df_product.empty:

        st.info(
            "暂无商品数据。"
        )

    else:

        urgent_df = df_product[
            df_product["等级"]
            == "🔴立即处理"
        ].copy()

        if urgent_df.empty:

            st.success(
                "🟢 当前没有进入立即处理名单的商品。"
            )

        else:

            st.dataframe(
                urgent_df[
                    [
                        "商品名称",
                        "总花费",
                        "总成交金额",
                        "总成交笔数",
                        "整体ROI",
                        "CTR",
                        "CPC",
                        "CVR",
                        "置信度",
                        "诊断",
                        "建议动作",
                        "建议幅度",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "总花费":
                        st.column_config.NumberColumn(
                            format="¥%.2f"
                        ),
                    "总成交金额":
                        st.column_config.NumberColumn(
                            format="¥%.2f"
                        ),
                    "整体ROI":
                        st.column_config.NumberColumn(
                            format="%.2f"
                        ),
                    "CTR":
                        st.column_config.NumberColumn(
                            format="%.2%"
                        ),
                    "CPC":
                        st.column_config.NumberColumn(
                            format="¥%.3f"
                        ),
                    "CVR":
                        st.column_config.NumberColumn(
                            format="%.2%"
                        ),
                }
            )


# ============================================================
# Tab 2 放量
# ============================================================

with tabs[1]:

    st.subheader(
        "🟢 可以放量"
    )

    if df_product.empty:

        st.info(
            "暂无商品数据。"
        )

    else:

        scale_df = df_product[
            df_product["等级"]
            == "🟢可以放量"
        ].copy()

        if scale_df.empty:

            st.info(
                "目前没有达到放量条件的商品。"
            )

        else:

            st.success(
                f"共发现 {len(scale_df)} 个具备一定放量基础的商品。"
            )

            st.dataframe(
                scale_df[
                    [
                        "商品名称",
                        "总花费",
                        "总成交金额",
                        "总成交笔数",
                        "整体ROI",
                        "CTR",
                        "CPC",
                        "CVR",
                        "置信度",
                        "诊断",
                        "建议动作",
                        "建议幅度",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )


# ============================================================
# Tab 3 商品
# ============================================================

with tabs[2]:

    st.subheader(
        "📦 商品经营诊断"
    )

    if df_product.empty:

        st.warning(
            "没有识别到商品字段。"
        )

    else:

        level_filter = st.multiselect(
            "等级筛选",
            LEVEL_ORDER,
            default=LEVEL_ORDER,
            key="product_level_filter",
        )

        view = df_product[
            df_product["等级"].isin(
                level_filter
            )
        ]

        st.dataframe(
            view,
            hide_index=True,
            use_container_width=True,
        )

        st.download_button(
            "📥 下载商品诊断",
            data=view.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="商品诊断.csv",
            mime="text/csv",
        )


# ============================================================
# Tab 4 计划
# ============================================================

with tabs[3]:

    st.subheader(
        "📋 计划诊断"
    )

    if df_plan.empty:

        st.warning(
            "没有识别到计划字段。"
        )

    else:

        st.dataframe(
            df_plan,
            hide_index=True,
            use_container_width=True,
        )

        st.download_button(
            "📥 下载计划诊断",
            data=df_plan.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="计划诊断.csv",
            mime="text/csv",
        )


# ============================================================
# Tab 5 关键词
# ============================================================

with tabs[4]:

    st.subheader(
        "🔑 关键词诊断"
    )

    if df_keyword.empty:

        st.warning(
            "没有识别到关键词字段。"
        )

    else:

        st.dataframe(
            df_keyword,
            hide_index=True,
            use_container_width=True,
        )

        st.download_button(
            "📥 下载关键词诊断",
            data=df_keyword.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="关键词诊断.csv",
            mime="text/csv",
        )


# ============================================================
# Tab 6 人群
# ============================================================

with tabs[5]:

    st.subheader(
        "👥 人群诊断"
    )

    if df_crowd.empty:

        st.warning(
            "没有识别到人群字段。"
        )

    else:

        st.dataframe(
            df_crowd,
            hide_index=True,
            use_container_width=True,
        )

        st.download_button(
            "📥 下载人群诊断",
            data=df_crowd.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="人群诊断.csv",
            mime="text/csv",
        )


# ============================================================
# Tab 7 操作复盘
# ============================================================

with tabs[6]:

    st.subheader(
        "📝 操作记录与复盘"
    )

    st.caption(
        "这里记录你实际执行了什么，下一次上传数据后可以对照观察效果。"
    )

    with st.form(
        "action_log_form"
    ):

        c1, c2 = st.columns(2)

        with c1:

            action_type = st.selectbox(
                "推广类型",
                [
                    "商品",
                    "计划",
                    "关键词",
                    "人群",
                    "创意",
                    "其他",
                ]
            )

            object_name = st.text_input(
                "对象名称"
            )

            action = st.selectbox(
                "执行动作",
                [
                    "预算增加",
                    "预算降低",
                    "提高出价",
                    "降低出价",
                    "暂停",
                    "开启",
                    "修改创意",
                    "暂不操作",
                    "其他",
                ]
            )

        with c2:

            suggested_value = st.text_input(
                "系统建议值"
            )

            actual_value = st.text_input(
                "实际执行值"
            )

            result = st.selectbox(
                "操作结果",
                [
                    "待观察",
                    "有效",
                    "无明显变化",
                    "恶化",
                ]
            )

            note = st.text_input(
                "备注"
            )

        submit = st.form_submit_button(
            "保存操作"
        )

        if submit:

            new_row = {
                "操作时间":
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),

                "推广类型":
                    action_type,

                "对象名称":
                    object_name,

                "执行动作":
                    action,

                "建议值":
                    suggested_value,

                "实际值":
                    actual_value,

                "操作结果":
                    result,

                "备注":
                    note,
            }

            st.session_state.action_log = pd.concat(
                [
                    st.session_state.action_log,
                    pd.DataFrame(
                        [new_row]
                    ),
                ],
                ignore_index=True,
            )

            st.success(
                "操作已记录。"
            )

    if not st.session_state.action_log.empty:

        st.dataframe(
            st.session_state.action_log,
            hide_index=True,
            use_container_width=True,
        )

        st.download_button(
            "📥 导出操作记录",
            data=st.session_state.action_log.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="投放操作记录.csv",
            mime="text/csv",
        )


# ============================================================
# 22. AI 军师
# ============================================================

with tabs[7]:

    st.subheader(
        "🤖 AI 投放军师"
    )

    st.info(
        "规则引擎负责计算事实和判断风险；AI 负责把这些结果整理成运营语言。"
    )

    # --------------------------------------------------------
    # 获取 API Key
    # --------------------------------------------------------

    secret_key = ""

    try:

        if "DOUBAO_API_KEY" in st.secrets:

            secret_key = st.secrets[
                "DOUBAO_API_KEY"
            ]

    except Exception:

        secret_key = ""

    if secret_key:

        st.success(
            "🔐 已读取服务器 Secrets 中的 API Key。"
        )

        api_key = secret_key

    else:

        api_key = st.text_input(
            "临时 API Key",
            type="password",
            value=st.session_state.manual_api_key,
            help="仅当前会话使用。长期部署建议放入 Streamlit Secrets。",
        )

        st.session_state.manual_api_key = api_key

    st.divider()

    if df_product.empty:

        st.warning(
            "没有商品级数据，AI 军师暂时无法工作。"
        )

    else:

        urgent_ai = df_product[
            df_product["等级"]
            == "🔴立即处理"
        ].head(10)

        scale_ai = df_product[
            df_product["等级"]
            == "🟢可以放量"
        ].head(10)

        observe_ai = df_product[
            df_product["等级"]
            == "🟠重点观察"
        ].head(10)

        ai_payload = {
            "店铺目标": {
                "目标ROI": roi_target,
                "最小有效花费": min_spend,
                "最小有效点击": min_clicks,
            },

            "大盘": {
                "总花费": round(
                    total_spend,
                    2
                ),

                "GMV": round(
                    total_gmv,
                    2
                ),

                "ROI": round(
                    overall_roi,
                    3
                ),

                "CTR": round(
                    overall_ctr,
                    4
                ),

                "CPC": round(
                    overall_cpc,
                    3
                ),

                "成交": int(
                    total_orders
                ),
            },

            "立即处理": urgent_ai[
                [
                    "商品名称",
                    "总花费",
                    "整体ROI",
                    "总成交笔数",
                    "诊断",
                    "建议动作",
                ]
            ].to_dict(
                orient="records"
            ),

            "放量机会": scale_ai[
                [
                    "商品名称",
                    "总花费",
                    "整体ROI",
                    "总成交笔数",
                    "诊断",
                    "建议动作",
                ]
            ].to_dict(
                orient="records"
            ),

            "重点观察": observe_ai[
                [
                    "商品名称",
                    "总花费",
                    "整体ROI",
                    "总成交笔数",
                    "诊断",
                    "建议动作",
                ]
            ].to_dict(
                orient="records"
            ),
        }

        if st.button(
            "✨ 生成今日 AI 军师报告",
            type="primary",
        ):

            if not api_key:

                st.warning(
                    "请先配置 API Key。"
                )

            else:

                prompt = f"""
你现在是一名淘宝万相台资深运营军师。

你的任务不是重新计算数据，而是基于下面已经经过程序计算的数据，
帮助运营人员做出今天可以执行的决策。

【重要原则】

1. 不要编造数据。
2. 不要因为一个商品 ROI 高就直接断言一定可以无限放量。
3. 样本不足必须明确告诉运营人员“不要急着调整”。
4. 每一个建议都要解释原因。
5. 区分：
   - 必须处理
   - 可以放量
   - 重点观察
   - 暂不操作
6. 如果数据不足，宁可建议观察，不要强行给结论。
7. 不要把所有问题都归因于出价。
8. 要根据 CTR、CPC、CVR、加购率和 ROI 判断问题发生在哪一层。
9. 最后给出一份“今天照着做”的执行清单。

【店铺参数】

{json.dumps(
    ai_payload["店铺目标"],
    ensure_ascii=False,
    indent=2
)}

【大盘】

{json.dumps(
    ai_payload["大盘"],
    ensure_ascii=False,
    indent=2
)}

【立即处理】

{json.dumps(
    ai_payload["立即处理"],
    ensure_ascii=False,
    indent=2
)}

【放量机会】

{json.dumps(
    ai_payload["放量机会"],
    ensure_ascii=False,
    indent=2
)}

【重点观察】

{json.dumps(
    ai_payload["重点观察"],
    ensure_ascii=False,
    indent=2
)}

请按照下面结构输出：

# 今日军师结论

用3-5句话总结今天整个账户。

# 一、今天必须处理

最多5个。

每个按照：

商品：
当前情况：
问题：
建议动作：
建议幅度：
为什么：

# 二、今天可以放量

最多5个。

说明为什么值得测试放量，以及放量后的风险。

# 三、今天不要动

列出样本不足或者没有明确问题的商品。

# 四、问题到底发生在哪一层

从：

曝光 → CTR → CPC → 点击 → 加购 → 成交 → ROI

解释主要问题。

# 五、今天执行顺序

只给运营人员最实际的操作顺序。

例如：

1. ...
2. ...
3. ...

# 六、明天重点看什么

告诉运营人员明天重新上传数据以后，
应该重点比较哪些指标。

语言简洁，不要写空话。
"""

                try:

                    headers = {
                        "Authorization":
                            f"Bearer {api_key}",

                        "Content-Type":
                            "application/json",
                    }

                    payload = {
                        "model":
                            "doubao-pro-4k",

                        "messages": [
                            {
                                "role":
                                    "user",

                                "content":
                                    prompt,
                            }
                        ],

                        "temperature":
                            0.2,
                    }

                    response = requests.post(
                        "https://open.doubao.com/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=60,
                    )

                    if response.status_code == 200:

                        result = response.json()

                        report = (
                            result
                            .get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )

                        st.session_state.last_ai_report = report

                    else:

                        st.error(
                            f"AI接口调用失败：{response.status_code}"
                        )

                        st.code(
                            response.text
                        )

                except Exception as e:

                    st.error(
                        f"AI调用异常：{e}"
                    )

        if st.session_state.last_ai_report:

            st.markdown("---")

            st.markdown(
                st.session_state.last_ai_report
            )

            st.download_button(
                "📥 下载今日军师报告",
                data=st.session_state.last_ai_report,
                file_name="今日淘宝投放军师报告.txt",
                mime="text/plain",
            )


# ============================================================
# 23. 原始数据调试区
# ============================================================

st.markdown("---")

with st.expander(
    "🔧 数据源 / 字段识别 / 调试"
):

    st.write(
        f"原始数据：{len(df_raw):,} 行 × "
        f"{len(df_raw.columns)} 列"
    )

    st.write(
        f"标准化数据：{len(df):,} 行"
    )

    st.write(
        "识别到的字段："
    )

    detected = {}

    for key in COL_ALIASES:

        detected[key] = resolve_col(
            df_raw,
            key
        )

    st.json(
        detected
    )

    st.dataframe(
        df_raw.head(20),
        hide_index=True,
        use_container_width=True,
    )


# ============================================================
# 24. 页面底部
# ============================================================

st.markdown("---")

st.caption(
    "🧠 淘宝投放军师 V10｜"
    "规则引擎负责数据判断，AI负责解释与运营表达。"
)
