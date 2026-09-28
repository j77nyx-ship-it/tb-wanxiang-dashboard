import io
import json
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import requests

from datetime import datetime, timedelta


# ============================================================
# 页面配置
# ============================================================

st.set_page_config(
    page_title="淘宝 AI 运营军师 V10",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧠 淘宝 AI 运营军师 V10")
st.caption("不是让你看更多数据，而是每天告诉你：发生了什么、为什么、今天该做什么。")


# ============================================================
# Session State
# ============================================================

if "action_log" not in st.session_state:
    st.session_state.action_log = pd.DataFrame(
        columns=[
            "操作时间",
            "优先级",
            "对象类型",
            "对象名称",
            "问题",
            "执行动作",
            "调整内容",
            "调整前指标",
            "调整后指标",
            "观察指标",
            "观察周期",
            "结果",
            "备注",
        ]
    )

if "dismissed_tasks" not in st.session_state:
    st.session_state.dismissed_tasks = set()


# ============================================================
# 字段别名
# ============================================================

COL_ALIASES = {
    "日期": ["日期", "date", "Date", "统计日期", "数据日期"],

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
        "投放场景",
        "场景",
    ],

    "关键词": [
        "关键词",
        "词",
        "搜索词",
        "投放词",
    ],

    "人群包名称": [
        "人群包名称",
        "人群名称",
        "人群包",
        "定向人群",
    ],

    "花费": [
        "花费",
        "消耗",
        "总花费",
        "推广花费",
        "广告花费",
    ],

    "成交金额": [
        "总成交金额",
        "成交金额",
        "净成交金额",
        "支付金额",
        "GMV",
    ],

    "成交笔数": [
        "总成交笔数",
        "成交笔数",
        "支付订单数",
        "订单数",
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
        "加购",
        "购物车数",
    ],

    "收藏数": [
        "收藏宝贝数",
        "收藏数",
        "收藏",
    ],

    "ROI": [
        "投入产出比",
        "实际投产比",
        "投产比",
        "ROI",
        "roi",
    ],

    "CPC": [
        "平均点击花费",
        "CPC",
        "平均点击成本",
    ],

    "CTR": [
        "点击率",
        "CTR",
        "点击率%",
    ],
}


def resolve_col(df, key):
    for name in COL_ALIASES.get(key, []):
        if name in df.columns:
            return name
    return None


# ============================================================
# 工具函数
# ============================================================

def safe_div(a, b):
    if isinstance(a, pd.Series):
        return np.where(b > 0, a / b, 0)
    return a / b if b else 0


def pct_change(current, previous):
    if previous is None or previous == 0:
        return 0
    return (current - previous) / abs(previous)


def fmt_money(x):
    return f"¥{x:,.2f}"


def fmt_pct(x):
    return f"{x:.2%}"


def normalize_percent(series):
    """
    兼容：
    0.035 = 3.5%
    3.5 = 3.5%
    3.5%字符串
    """
    s = series.astype(str).str.replace("%", "", regex=False)
    s = pd.to_numeric(s, errors="coerce").fillna(0)

    if s.max() > 1:
        s = s / 100

    return s


# ============================================================
# 数据读取
# ============================================================

@st.cache_data(show_spinner="正在读取报表...")
def load_raw(files_data):

    frames = []

    for name, data in files_data:

        try:

            if name.lower().endswith(".csv"):

                try:
                    tmp = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")
                except Exception:
                    tmp = pd.read_csv(io.BytesIO(data), encoding="gbk")

            else:
                tmp = pd.read_excel(io.BytesIO(data))

            tmp.columns = [str(c).strip() for c in tmp.columns]

            tmp["_来源文件"] = name

            frames.append(tmp)

        except Exception as e:

            st.warning(f"文件 {name} 读取失败：{e}")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ============================================================
# 数据标准化
# ============================================================

@st.cache_data(show_spinner="正在标准化数据...")
def build_normalized(df_raw):

    if df_raw.empty:
        return pd.DataFrame()

    n = len(df_raw)

    out = pd.DataFrame(index=range(n))

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
    text_keys = [
        "商品ID",
        "商品名称",
        "计划名称",
        "场景名称",
        "关键词",
        "人群包名称",
    ]

    for key in text_keys:

        c = resolve_col(df_raw, key)

        if c:

            out[key] = (
                df_raw[c]
                .fillna("")
                .astype(str)
                .str.strip()
            )

        else:

            out[key] = ""

    # 数值字段
    numeric_keys = [
        "花费",
        "成交金额",
        "成交笔数",
        "点击量",
        "展现量",
        "加购数",
        "收藏数",
    ]

    for key in numeric_keys:

        c = resolve_col(df_raw, key)

        if c:

            out[key] = pd.to_numeric(
                df_raw[c],
                errors="coerce"
            ).fillna(0)

        else:

            out[key] = 0.0

    # ROI
    c = resolve_col(df_raw, "ROI")

    if c:

        out["ROI"] = pd.to_numeric(
            df_raw[c],
            errors="coerce"
        ).fillna(0)

    else:

        out["ROI"] = safe_div(
            out["成交金额"],
            out["花费"]
        )

    # CPC
    c = resolve_col(df_raw, "CPC")

    if c:

        out["CPC"] = pd.to_numeric(
            df_raw[c],
            errors="coerce"
        ).fillna(0)

    else:

        out["CPC"] = safe_div(
            out["花费"],
            out["点击量"]
        )

    # CTR
    c = resolve_col(df_raw, "CTR")

    if c:

        out["CTR"] = normalize_percent(
            df_raw[c]
        )

    else:

        out["CTR"] = safe_div(
            out["点击量"],
            out["展现量"]
        )

    # CVR
    out["点击转化率"] = safe_div(
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

    return out


# ============================================================
# 聚合
# ============================================================

def group_sum(
    df,
    grp_keys,
    target_roi,
    min_spend
):

    if df.empty:
        return pd.DataFrame()

    grp_keys = [
        x for x in grp_keys
        if x in df.columns
        and df[x].astype(str).str.strip().ne("").any()
    ]

    if not grp_keys:
        return pd.DataFrame()

    agg = {}

    fields = [
        ("花费", "总花费"),
        ("成交金额", "总成交金额"),
        ("成交笔数", "总成交笔数"),
        ("点击量", "总点击"),
        ("展现量", "总展现"),
        ("加购数", "总加购"),
        ("收藏数", "总收藏"),
    ]

    for src, dst in fields:

        if src in df.columns:
            agg[dst] = (src, "sum")

    if not agg:
        return pd.DataFrame()

    g = (
        df.groupby(
            grp_keys,
            dropna=False
        )
        .agg(**agg)
        .reset_index()
    )

    g["整体ROI"] = safe_div(
        g["总成交金额"],
        g["总花费"]
    )

    g["平均CPC"] = safe_div(
        g["总花费"],
        g["总点击"]
    )

    g["CTR"] = safe_div(
        g["总点击"],
        g["总展现"]
    )

    g["点击转化率"] = safe_div(
        g["总成交笔数"],
        g["总点击"]
    )

    g["加购率"] = safe_div(
        g["总加购"],
        g["总点击"]
    )

    return g


# ============================================================
# 基础策略
# ============================================================

def classify_base(
    row,
    target_roi,
    min_spend
):

    spend = row.get("总花费", 0)
    roi = row.get("整体ROI", 0)
    clicks = row.get("总点击", 0)
    ctr = row.get("CTR", 0)
    cpc = row.get("平均CPC", 0)

    if spend < min_spend:
        return "🟡样本不足"

    if clicks <= 0:
        return "🟡零点击"

    if roi >= target_roi * 1.15:
        return "✅优质可放大"

    if roi < target_roi * 0.6 and spend >= min_spend * 3:
        return "🔻高花费低ROI"

    if roi <= 0:
        return "🔴无成交"

    return "⚠️观察待优化"


# ============================================================
# 诊断引擎
# ============================================================

def diagnose_row(
    row,
    store_avg_roi,
    store_avg_ctr,
    store_avg_cpc,
    target_roi,
    min_spend,
    cpc_warn,
    ctr_warn
):

    spend = row.get("总花费", 0)
    roi = row.get("整体ROI", 0)
    ctr = row.get("CTR", 0)
    cpc = row.get("平均CPC", 0)
    clicks = row.get("总点击", 0)
    cvr = row.get("点击转化率", 0)
    add_rate = row.get("加购率", 0)

    problems = []
    reasons = []
    actions = []

    # 样本不足
    if spend < min_spend:

        return {
            "问题类型": "样本不足",
            "诊断": "当前数据量不足，不建议过早调整。",
            "建议动作": "继续观察",
            "动作理由": "避免因为小样本导致误判。",
            "优先级": "P2",
        }

    # 没有点击
    if clicks <= 0:

        problems.append("无点击")

        if ctr < ctr_warn:
            reasons.append("展现存在但没有形成有效点击")
            actions.append("优先检查创意、主图、关键词与人群匹配")

    # CTR问题
    if 0 < ctr < ctr_warn:

        problems.append("CTR偏低")

        reasons.append(
            f"CTR {ctr:.2%} 低于预警线 {ctr_warn:.2%}"
        )

        actions.append(
            "优先检查创意/主图/关键词与人群匹配，不建议直接加预算"
        )

    # CPC问题
    if cpc > cpc_warn:

        problems.append("CPC偏高")

        reasons.append(
            f"CPC ¥{cpc:.2f} 高于预警线 ¥{cpc_warn:.2f}"
        )

        actions.append(
            "检查出价及高成本流量来源，优先控制无效点击"
        )

    # ROI问题
    if roi < target_roi:

        problems.append("ROI未达目标")

        if spend >= min_spend * 3:

            reasons.append(
                f"已经积累较多花费，但ROI仅 {roi:.2f}"
            )

            actions.append(
                "优先降低低效投放强度，不建议盲目继续放量"
            )

    # 加购不错但成交差
    if add_rate > 0 and cvr < 0.03:

        problems.append("成交承接偏弱")

        reasons.append(
            "存在点击/加购，但最终成交效率偏低"
        )

        actions.append(
            "检查价格、优惠、SKU、评价、详情页及商品承接"
        )

    # 优质
    if roi >= target_roi * 1.15:

        problems.append("具备放量潜力")

        reasons.append(
            f"ROI {roi:.2f} 明显高于目标 {target_roi:.2f}"
        )

        actions.append(
            "可小幅增加预算或曝光，建议逐步放量并观察边际ROI"
        )

    # 和店铺比较
    if store_avg_roi > 0:

        if roi > store_avg_roi * 1.2:

            reasons.append(
                f"ROI高于店铺平均 {store_avg_roi:.2f}"
            )

        elif roi < store_avg_roi * 0.7:

            reasons.append(
                f"ROI明显低于店铺平均 {store_avg_roi:.2f}"
            )

    # 没有问题
    if not problems:

        problems.append("暂无明显异常")

    # 优先级
    if spend >= min_spend * 5 and roi < target_roi * 0.6:

        priority = "P0"

    elif roi < target_roi or ctr < ctr_warn or cpc > cpc_warn:

        priority = "P1"

    else:

        priority = "P2"

    return {
        "问题类型": " / ".join(dict.fromkeys(problems)),
        "诊断": "；".join(dict.fromkeys(reasons)) or "当前未发现明显异常。",
        "建议动作": "；".join(dict.fromkeys(actions)) or "继续观察。",
        "动作理由": (
            "系统根据ROI、流量效率、点击成本、转化及店铺基准综合判断。"
        ),
        "优先级": priority,
    }


# ============================================================
# 商品生命周期
# ============================================================

def lifecycle(row, target_roi, min_spend):

    spend = row.get("总花费", 0)
    roi = row.get("整体ROI", 0)
    clicks = row.get("总点击", 0)

    if spend < min_spend:
        return "测试期"

    if clicks <= 0:
        return "待观察"

    if roi >= target_roi * 1.2:
        return "放量期"

    if roi >= target_roi:
        return "潜力期"

    if roi >= target_roi * 0.7:
        return "稳定观察"

    return "衰退/救援"


# ============================================================
# 自动策略
# ============================================================

def add_strategy(
    df,
    target_roi,
    min_spend,
    cpc_warn,
    ctr_warn
):

    if df.empty:
        return df

    store_roi = (
        df["总成交金额"].sum()
        / df["总花费"].sum()
        if df["总花费"].sum() > 0
        else 0
    )

    store_ctr = (
        df["总点击"].sum()
        / df["总展现"].sum()
        if df["总展现"].sum() > 0
        else 0
    )

    store_cpc = (
        df["总花费"].sum()
        / df["总点击"].sum()
        if df["总点击"].sum() > 0
        else 0
    )

    levels = []
    diagnoses = []
    actions = []
    reasons = []
    priorities = []
    lifecycles = []

    for _, row in df.iterrows():

        level = classify_base(
            row,
            target_roi,
            min_spend
        )

        d = diagnose_row(
            row,
            store_roi,
            store_ctr,
            store_cpc,
            target_roi,
            min_spend,
            cpc_warn,
            ctr_warn,
        )

        levels.append(level)
        diagnoses.append(d["诊断"])
        actions.append(d["建议动作"])
        reasons.append(d["动作理由"])
        priorities.append(d["优先级"])

        lifecycles.append(
            lifecycle(
                row,
                target_roi,
                min_spend
            )
        )

    df["等级"] = levels
    df["问题诊断"] = diagnoses
    df["建议动作"] = actions
    df["动作理由"] = reasons
    df["优先级"] = priorities
    df["生命周期"] = lifecycles

    return df


# ============================================================
# 历史趋势
# ============================================================

def build_history(df):

    if df.empty or "日期" not in df.columns:
        return pd.DataFrame()

    tmp = df.dropna(subset=["日期"]).copy()

    if tmp.empty:
        return pd.DataFrame()

    daily = (
        tmp.groupby("日期")
        .agg(
            花费=("花费", "sum"),
            成交金额=("成交金额", "sum"),
            点击量=("点击量", "sum"),
            展现量=("展现量", "sum"),
            成交笔数=("成交笔数", "sum"),
            加购数=("加购数", "sum"),
        )
        .reset_index()
    )

    daily["ROI"] = safe_div(
        daily["成交金额"],
        daily["花费"]
    )

    daily["CTR"] = safe_div(
        daily["点击量"],
        daily["展现量"]
    )

    daily["CPC"] = safe_div(
        daily["花费"],
        daily["点击量"]
    )

    daily["CVR"] = safe_div(
        daily["成交笔数"],
        daily["点击量"]
    )

    return daily


# ============================================================
# 异常检测
# ============================================================

def detect_anomalies(
    df,
    target_roi,
    min_spend
):

    tasks = []

    if df.empty:
        return pd.DataFrame()

    # ---------------- 店铺整体 ----------------

    dates = sorted(
        df["日期"].dropna().dt.date.unique()
    )

    if len(dates) >= 4:

        latest = dates[-1]
        previous = dates[-2]

        cur = df[
            df["日期"].dt.date == latest
        ]

        prev = df[
            df["日期"].dt.date == previous
        ]

        cur_spend = cur["花费"].sum()
        prev_spend = prev["花费"].sum()

        cur_gmv = cur["成交金额"].sum()
        prev_gmv = prev["成交金额"].sum()

        cur_roi = (
            cur_gmv / cur_spend
            if cur_spend > 0
            else 0
        )

        prev_roi = (
            prev_gmv / prev_spend
            if prev_spend > 0
            else 0
        )

        roi_change = pct_change(
            cur_roi,
            prev_roi
        )

        if roi_change <= -0.2:

            tasks.append({
                "优先级": "P0",
                "对象类型": "店铺",
                "对象名称": "全店",
                "问题": "店铺ROI明显下降",
                "异常指标": f"ROI {prev_roi:.2f} → {cur_roi:.2f}",
                "变化": f"{roi_change:.1%}",
                "建议": "优先检查高花费低ROI商品及计划，不建议继续盲目增加预算。",
            })

        if (
            prev_gmv > 0
            and cur_gmv < prev_gmv * 0.8
        ):

            tasks.append({
                "优先级": "P0",
                "对象类型": "店铺",
                "对象名称": "全店",
                "问题": "成交金额明显下降",
                "异常指标": f"GMV {prev_gmv:.0f} → {cur_gmv:.0f}",
                "变化": f"{pct_change(cur_gmv, prev_gmv):.1%}",
                "建议": "拆解流量、点击、加购和成交漏斗，确认问题发生在哪一层。",
            })

    # ---------------- 商品异常 ----------------

    if "商品名称" in df.columns:

        product_daily = (
            df.groupby(
                ["日期", "商品ID", "商品名称"],
                dropna=False
            )
            .agg(
                花费=("花费", "sum"),
                成交金额=("成交金额", "sum"),
                点击量=("点击量", "sum"),
            )
            .reset_index()
        )

        product_daily["ROI"] = safe_div(
            product_daily["成交金额"],
            product_daily["花费"]
        )

        products = (
            product_daily["商品名称"]
            .dropna()
            .astype(str)
            .unique()
        )

        for product in products:

            x = product_daily[
                product_daily["商品名称"].astype(str) == str(product)
            ].sort_values("日期")

            if len(x) < 4:
                continue

            recent = x.tail(2)
            old = x.iloc[:-2]

            recent_spend = recent["花费"].sum()
            old_spend = old["花费"].sum()

            recent_gmv = recent["成交金额"].sum()
            old_gmv = old["成交金额"].sum()

            recent_roi = (
                recent_gmv / recent_spend
                if recent_spend > 0
                else 0
            )

            old_roi = (
                old_gmv / old_spend
                if old_spend > 0
                else 0
            )

            if (
                recent_spend >= min_spend
                and old_roi > 0
                and recent_roi < old_roi * 0.7
            ):

                tasks.append({
                    "优先级": "P0",
                    "对象类型": "商品",
                    "对象名称": product,
                    "问题": "商品ROI趋势明显恶化",
                    "异常指标": f"ROI {old_roi:.2f} → {recent_roi:.2f}",
                    "变化": f"{pct_change(recent_roi, old_roi):.1%}",
                    "建议": "先检查成本、点击、转化和主要投放来源，再决定是否降低投放强度。",
                })

    return pd.DataFrame(tasks)


# ============================================================
# 今日作战任务
# ============================================================

def build_tasks(
    product_df,
    anomalies
):

    tasks = []

    # 异常任务
    if not anomalies.empty:

        for _, r in anomalies.iterrows():

            tasks.append({
                "优先级": r["优先级"],
                "对象": r["对象名称"],
                "任务": r["问题"],
                "为什么": r["异常指标"],
                "建议": r["建议"],
                "类型": "异常",
            })

    # 商品任务
    if not product_df.empty:

        sorted_df = product_df.copy()

        priority_order = {
            "P0": 0,
            "P1": 1,
            "P2": 2,
        }

        sorted_df["_sort"] = sorted_df["优先级"].map(
            priority_order
        ).fillna(9)

        sorted_df = sorted_df.sort_values(
            ["_sort", "总花费"],
            ascending=[True, False]
        )

        for _, r in sorted_df.iterrows():

            if len(tasks) >= 15:
                break

            if r["优先级"] == "P0":

                tasks.append({
                    "优先级": "P0",
                    "对象": r.get("商品名称", ""),
                    "任务": r.get("问题类型", "高优先级问题"),
                    "为什么": r.get("诊断", ""),
                    "建议": r.get("建议动作", ""),
                    "类型": "商品",
                })

            elif (
                r["优先级"] == "P1"
                and r.get("整体ROI", 0) < 999
            ):

                tasks.append({
                    "优先级": "P1",
                    "对象": r.get("商品名称", ""),
                    "任务": r.get("问题类型", "需要优化"),
                    "为什么": r.get("诊断", ""),
                    "建议": r.get("建议动作", ""),
                    "类型": "商品",
                })

    if not tasks:
        return pd.DataFrame(
            columns=[
                "优先级",
                "对象",
                "任务",
                "为什么",
                "建议",
                "类型",
            ]
        )

    return pd.DataFrame(tasks)


# ============================================================
# 侧边栏
# ============================================================

with st.sidebar:

    st.header("⚙️ 运营策略")

    roi_target = st.number_input(
        "目标 ROI",
        min_value=0.1,
        value=3.0,
        step=0.1,
    )

    min_cost = st.number_input(
        "最小有效花费",
        min_value=0.0,
        value=15.0,
        step=5.0,
    )

    max_cpc_warn = st.number_input(
        "CPC预警",
        min_value=0.0,
        value=0.30,
        step=0.05,
        format="%.2f",
    )

    min_ctr_warn = st.number_input(
        "CTR预警",
        min_value=0.001,
        value=0.02,
        step=0.001,
        format="%.3f",
    )

    st.caption(
        f"ROI目标 {roi_target:.2f} ｜ "
        f"有效花费 ¥{min_cost:.0f} ｜ "
        f"CPC ¥{max_cpc_warn:.2f} ｜ "
        f"CTR {min_ctr_warn:.2%}"
    )

    st.divider()

    st.header("📁 数据源")

    upload_files = st.file_uploader(
        "上传万相台 Excel / CSV",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
    )


# ============================================================
# 没数据
# ============================================================

if not upload_files:

    st.info(
        """
👈 请先上传万相台报表。

建议至少上传：
1. 商品报表
2. 计划报表
3. 关键词报表
4. 人群报表

V10会自动把数据转换成：
数据 → 异常 → 诊断 → 今日任务 → 执行 → 复盘
"""
    )

    st.stop()


# ============================================================
# 读取数据
# ============================================================

files_data = tuple(
    (f.name, f.getvalue())
    for f in upload_files
)

df_raw = load_raw(files_data)

if df_raw.empty:

    st.error("没有成功读取数据。")

    st.stop()


df = build_normalized(df_raw)

if df.empty:

    st.error("标准化后没有数据。")

    st.stop()


# ============================================================
# 日期筛选
# ============================================================

with st.sidebar:

    st.divider()

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

    keyword_filter = st.text_input(
        "商品名称关键词",
        "",
    )


dff = df.copy()

if (
    date_range
    and len(date_range) == 2
):

    start = pd.Timestamp(date_range[0])
    end = (
        pd.Timestamp(date_range[1])
        + pd.Timedelta(days=1)
        - pd.Timedelta(seconds=1)
    )

    dff = dff[
        dff["日期"].isna()
        | (
            (dff["日期"] >= start)
            & (dff["日期"] <= end)
        )
    ]


if keyword_filter:

    dff = dff[
        dff["商品名称"]
        .str.contains(
            keyword_filter,
            case=False,
            na=False
        )
    ]


# ============================================================
# 汇总
# ============================================================

df_product = group_sum(
    dff,
    ["商品ID", "商品名称"],
    roi_target,
    min_cost,
)

df_plan = group_sum(
    dff,
    ["计划名称", "场景名称"],
    roi_target,
    min_cost,
)

df_keyword = group_sum(
    dff,
    ["关键词"],
    roi_target,
    min_cost,
)

df_crowd = group_sum(
    dff,
    ["人群包名称"],
    roi_target,
    min_cost,
)


# ============================================================
# 策略
# ============================================================

for frame_name in [
    "df_product",
    "df_plan",
    "df_keyword",
    "df_crowd",
]:

    frame = locals()[frame_name]

    if not frame.empty:

        frame = add_strategy(
            frame,
            roi_target,
            min_cost,
            max_cpc_warn,
            min_ctr_warn,
        )

        locals()[frame_name] = frame


# 重新赋值
df_product = locals()["df_product"]
df_plan = locals()["df_plan"]
df_keyword = locals()["df_keyword"]
df_crowd = locals()["df_crowd"]


# ============================================================
# 大盘数据
# ============================================================

total_spend = dff["花费"].sum()
total_gmv = dff["成交金额"].sum()
total_click = dff["点击量"].sum()
total_impression = dff["展现量"].sum()
total_orders = dff["成交笔数"].sum()
total_add = dff["加购数"].sum()

total_roi = (
    total_gmv / total_spend
    if total_spend > 0
    else 0
)

total_ctr = (
    total_click / total_impression
    if total_impression > 0
    else 0
)

total_cpc = (
    total_spend / total_click
    if total_click > 0
    else 0
)

total_cvr = (
    total_orders / total_click
    if total_click > 0
    else 0
)


# ============================================================
# 异常
# ============================================================

anomalies = detect_anomalies(
    dff,
    roi_target,
    min_cost,
)

tasks = build_tasks(
    df_product,
    anomalies,
)


# ============================================================
# 页面导航
# ============================================================

tabs = st.tabs(
    [
        "🧠 今日作战",
        "🚨 异常中心",
        "🏪 店铺诊断",
        "📦 商品作战室",
        "🎯 流量作战室",
        "🤖 AI运营军师",
        "📋 执行 & 复盘",
        "📊 原始数据",
    ]
)


# ============================================================
# TAB 1 今日作战
# ============================================================

with tabs[0]:

    st.subheader("🧠 今日运营作战")

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric(
        "总花费",
        fmt_money(total_spend),
    )

    c2.metric(
        "成交金额",
        fmt_money(total_gmv),
    )

    c3.metric(
        "整体 ROI",
        f"{total_roi:.2f}",
        delta=f"目标 {roi_target:.2f}",
    )

    c4.metric(
        "CTR",
        fmt_pct(total_ctr),
    )

    c5.metric(
        "CPC",
        fmt_money(total_cpc),
    )

    st.divider()

    # ---------------- 总结 ----------------

    if total_roi >= roi_target:

        st.success(
            f"""
### 🟢 当前店铺整体投放达标

整体 ROI {total_roi:.2f}，目标 {roi_target:.2f}。

当前重点不是盲目削减，而是寻找：
**哪些商品值得继续放量、哪些流量正在浪费预算。**
"""
        )

    else:

        st.error(
            f"""
### 🔴 当前店铺整体投放未达目标

整体 ROI {total_roi:.2f}，目标 {roi_target:.2f}。

**第一原则：先控制低效花费，再考虑放量。**
"""
        )

    st.divider()

    # ---------------- 任务 ----------------

    st.subheader("🎯 今天值得处理的事情")

    if tasks.empty:

        st.success(
            "目前没有发现需要立即处理的重大问题，建议继续观察。"
        )

    else:

        for idx, task in tasks.head(12).iterrows():

            priority = task["优先级"]

            if priority == "P0":
                box = st.error
            elif priority == "P1":
                box = st.warning
            else:
                box = st.info

            with st.container(border=True):

                col1, col2 = st.columns([1, 7])

                with col1:

                    st.markdown(
                        f"## {priority}"
                    )

                with col2:

                    st.markdown(
                        f"### {task['对象']}｜{task['任务']}"
                    )

                    st.markdown(
                        f"**为什么：** {task['为什么']}"
                    )

                    st.markdown(
                        f"**建议：** {task['建议']}"
                    )

                    b1, b2, b3 = st.columns(3)

                    with b1:

                        if st.button(
                            "✅ 已处理",
                            key=f"done_{idx}",
                        ):

                            st.session_state.action_log = pd.concat(
                                [
                                    st.session_state.action_log,
                                    pd.DataFrame(
                                        [{
                                            "操作时间": datetime.now().strftime(
                                                "%Y-%m-%d %H:%M:%S"
                                            ),
                                            "优先级": priority,
                                            "对象类型": task["类型"],
                                            "对象名称": task["对象"],
                                            "问题": task["任务"],
                                            "执行动作": task["建议"],
                                            "调整内容": "",
                                            "调整前指标": task["为什么"],
                                            "调整后指标": "",
                                            "观察指标": "",
                                            "观察周期": "3天",
                                            "结果": "待复盘",
                                            "备注": "",
                                        }]
                                    ),
                                ],
                                ignore_index=True,
                            )

                            st.success("已记录，进入复盘。")

                    with b2:

                        if st.button(
                            "⏸ 稍后处理",
                            key=f"later_{idx}",
                        ):

                            st.info("已标记为稍后处理。")

                    with b3:

                        if st.button(
                            "❌ 忽略",
                            key=f"ignore_{idx}",
                        ):

                            st.session_state.dismissed_tasks.add(
                                str(idx)
                            )

    # ---------------- 今天不要做 ----------------

    st.divider()

    st.subheader("🛑 今天不要急着做的事情")

    dont_do = []

    if total_roi < roi_target:

        dont_do.append(
            "不要因为整体ROI低，就给所有商品统一降价。"
        )

    if not df_product.empty:

        good_count = (
            df_product["整体ROI"] >= roi_target * 1.15
        ).sum()

        if good_count > 0:

            dont_do.append(
                f"不要因为大盘ROI低，就暂停全部优质商品；当前至少有 {good_count} 个商品具备放量条件。"
            )

    if total_click == 0:

        dont_do.append(
            "不要直接根据ROI做判断，目前没有足够点击样本。"
        )

    if not dont_do:

        dont_do.append(
            "没有明显的高风险误操作，建议优先处理系统标记的P0/P1任务。"
        )

    for x in dont_do:

        st.markdown(
            f"- 🚫 {x}"
        )


# ============================================================
# TAB 2 异常中心
# ============================================================

with tabs[1]:

    st.subheader("🚨 异常中心")

    if anomalies.empty:

        st.success(
            "当前没有检测到明显趋势异常。"
        )

    else:

        st.dataframe(
            anomalies,
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    st.subheader("📈 店铺历史趋势")

    history = build_history(dff)

    if history.empty:

        st.info(
            "需要包含多个日期的数据才能分析趋势。"
        )

    else:

        c1, c2 = st.columns(2)

        with c1:

            fig = px.line(
                history,
                x="日期",
                y=["花费", "成交金额"],
                markers=True,
                title="花费 vs 成交金额",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        with c2:

            fig = px.line(
                history,
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
                use_container_width=True,
            )


# ============================================================
# TAB 3 店铺诊断
# ============================================================

with tabs[2]:

    st.subheader("🏪 店铺诊断")

    # 漏斗
    funnel_df = pd.DataFrame({
        "阶段": [
            "展现",
            "点击",
            "加购",
            "成交",
        ],
        "数量": [
            total_impression,
            total_click,
            total_add,
            total_orders,
        ],
    })

    fig = px.funnel(
        funnel_df,
        x="数量",
        y="阶段",
        title="投放成交漏斗",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

    st.divider()

    st.subheader("🔍 系统诊断")

    diagnosis_items = []

    if total_ctr < min_ctr_warn:

        diagnosis_items.append(
            (
                "🔴 点击层",
                f"CTR {total_ctr:.2%} 低于 {min_ctr_warn:.2%}",
                "优先检查创意、主图、关键词和人群匹配。",
            )
        )

    if total_cpc > max_cpc_warn:

        diagnosis_items.append(
            (
                "🟠 成本层",
                f"CPC ¥{total_cpc:.2f} 高于 ¥{max_cpc_warn:.2f}",
                "检查高成本计划、关键词和出价。",
            )
        )

    if total_roi < roi_target:

        diagnosis_items.append(
            (
                "🔴 投产层",
                f"ROI {total_roi:.2f} 低于目标 {roi_target:.2f}",
                "先控制低效花费，不建议全店统一降价。",
            )
        )

    if total_cvr < 0.03 and total_click > 0:

        diagnosis_items.append(
            (
                "🟠 成交层",
                f"点击转化率 {total_cvr:.2%}",
                "检查商品价格、优惠、SKU、评价和详情页。",
            )
        )

    if not diagnosis_items:

        diagnosis_items.append(
            (
                "🟢 当前状态",
                "暂未发现明显结构性问题",
                "继续观察趋势，并寻找可以放量的商品。",
            )
        )

    for title, problem, action in diagnosis_items:

        with st.container(border=True):

            st.markdown(f"### {title}")

            st.write(
                f"**发现：** {problem}"
            )

            st.write(
                f"**建议：** {action}"
            )


# ============================================================
# TAB 4 商品作战室
# ============================================================

with tabs[3]:

    st.subheader("📦 商品作战室")

    if df_product.empty:

        st.warning("没有识别到商品数据。")

    else:

        # 生命周期统计
        lifecycle_count = (
            df_product["生命周期"]
            .value_counts()
            .reset_index()
        )

        lifecycle_count.columns = [
            "生命周期",
            "商品数",
        ]

        c1, c2 = st.columns([1, 2])

        with c1:

            st.dataframe(
                lifecycle_count,
                hide_index=True,
                use_container_width=True,
            )

        with c2:

            fig = px.bar(
                lifecycle_count,
                x="生命周期",
                y="商品数",
                title="商品生命周期分布",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        st.divider()

        # ROI矩阵
        matrix = df_product[
            df_product["总花费"] >= min_cost
        ].copy()

        if not matrix.empty:

            fig = px.scatter(
                matrix,
                x="整体ROI",
                y="总花费",
                size="总点击",
                hover_name="商品名称",
                color="生命周期",
                title="商品作战矩阵",
            )

            fig.add_vline(
                x=roi_target,
                line_dash="dash",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        st.divider()

        # 商品清单
        show_cols = [
            "商品ID",
            "商品名称",
            "总花费",
            "总成交金额",
            "整体ROI",
            "CTR",
            "平均CPC",
            "点击转化率",
            "总加购",
            "等级",
            "生命周期",
            "优先级",
            "问题类型",
            "问题诊断",
            "建议动作",
            "动作理由",
        ]

        show_cols = [
            x for x in show_cols
            if x in df_product.columns
        ]

        st.dataframe(
            df_product[show_cols].round(4),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "📥 下载商品作战清单",
            data=df_product.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="商品作战清单.csv",
            mime="text/csv",
        )


# ============================================================
# TAB 5 流量作战室
# ============================================================

with tabs[4]:

    st.subheader("🎯 流量作战室")

    sub_tabs = st.tabs(
        [
            "计划",
            "关键词",
            "人群",
        ]
    )

    # 计划
    with sub_tabs[0]:

        if df_plan.empty:

            st.warning("没有计划数据。")

        else:

            st.dataframe(
                df_plan[
                    [
                        x for x in [
                            "计划名称",
                            "场景名称",
                            "总花费",
                            "总成交金额",
                            "整体ROI",
                            "CTR",
                            "平均CPC",
                            "等级",
                            "优先级",
                            "问题诊断",
                            "建议动作",
                        ]
                        if x in df_plan.columns
                    ]
                ].round(4),
                use_container_width=True,
                hide_index=True,
            )

    # 关键词
    with sub_tabs[1]:

        if df_keyword.empty:

            st.warning("没有关键词数据。")

        else:

            low_kw = df_keyword[
                (
                    df_keyword["总花费"] >= min_cost
                )
                & (
                    df_keyword["整体ROI"] < roi_target
                )
            ].sort_values(
                "总花费",
                ascending=False
            )

            st.markdown(
                f"### 🔴 当前值得关注的低效关键词：{len(low_kw)} 个"
            )

            st.dataframe(
                low_kw[
                    [
                        x for x in [
                            "关键词",
                            "总花费",
                            "总成交金额",
                            "整体ROI",
                            "CTR",
                            "平均CPC",
                            "优先级",
                            "问题诊断",
                            "建议动作",
                        ]
                        if x in low_kw.columns
                    ]
                ].round(4),
                use_container_width=True,
                hide_index=True,
            )

    # 人群
    with sub_tabs[2]:

        if df_crowd.empty:

            st.warning("没有人群数据。")

        else:

            st.dataframe(
                df_crowd[
                    [
                        x for x in [
                            "人群包名称",
                            "总花费",
                            "总成交金额",
                            "整体ROI",
                            "CTR",
                            "平均CPC",
                            "等级",
                            "优先级",
                            "问题诊断",
                            "建议动作",
                        ]
                        if x in df_crowd.columns
                    ]
                ].round(4),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# TAB 6 AI运营军师
# ============================================================

with tabs[5]:

    st.subheader("🤖 AI运营军师")

    st.caption(
        "AI负责理解系统已经计算出来的问题，而不是代替规则引擎计算基础指标。"
    )

    # API Key
    try:
        secret_key = st.secrets.get(
            "DOUBAO_API_KEY",
            ""
        )
    except Exception:
        secret_key = ""

    if secret_key:

        st.success(
            "已检测到服务器端 API Key。"
        )

        doubao_api_key = secret_key

    else:

        doubao_api_key = st.text_input(
            "临时 API Key",
            type="password",
            help="正式部署建议使用 Streamlit Secrets，而不是让用户输入。",
        )

    st.divider()

    ai_prompt = f"""
你现在是这家淘宝店铺的运营负责人。

你的任务不是复述数据，而是帮助运营人员做决定。

必须严格基于提供的数据，不得编造不存在的数据。

【店铺数据】

总花费：{total_spend:.2f}
成交金额：{total_gmv:.2f}
整体ROI：{total_roi:.2f}
目标ROI：{roi_target:.2f}
CTR：{total_ctr:.2%}
CPC：{total_cpc:.2f}
点击转化率：{total_cvr:.2%}

【系统检测到的异常】

{anomalies.to_csv(index=False) if not anomalies.empty else "暂无明显异常"}

【商品作战数据】

{
    df_product[
        [
            x for x in [
                "商品ID",
                "商品名称",
                "总花费",
                "总成交金额",
                "整体ROI",
                "CTR",
                "平均CPC",
                "点击转化率",
                "等级",
                "生命周期",
                "优先级",
                "问题类型",
                "问题诊断",
                "建议动作",
            ]
            if x in df_product.columns
        ]
    ]
    .sort_values("总花费", ascending=False)
    .head(30)
    .to_csv(index=False)
    if not df_product.empty
    else "暂无商品数据"
}

请严格按照下面结构输出：

# 今日运营结论

用3-5句话说明当前店铺最重要的问题。

# P0：现在必须处理

列出最多3个。

每个必须包含：

对象：
异常：
为什么：
具体动作：
为什么这样处理：
执行后观察什么：
观察多久：

# P1：今天可以处理

列出最多5个。

# 可以放大的商品

列出最多5个，并说明为什么。

# 今天不要做什么

列出最多3个容易误操作的事情。

# 未来3天观察

告诉运营接下来应该盯哪些指标。

要求：

1. 不要只说“优化”“调整”。
2. 尽量给出具体动作。
3. 不要因为ROI低就默认建议降价。
4. 不要因为ROI高就直接大幅加预算。
5. 所有预算调整都采用小步试验思路。
6. 如果数据不足，明确告诉运营“样本不足”。
7. 不要编造商品数据。
"""

    if st.button(
        "✨ 生成今日运营军师报告",
        disabled=not bool(doubao_api_key),
        type="primary",
    ):

        with st.spinner(
            "AI正在结合店铺诊断、商品状态和异常趋势进行分析..."
        ):

            try:

                headers = {
                    "Authorization": f"Bearer {doubao_api_key}",
                    "Content-Type": "application/json",
                }

                payload = {
                    "model": "doubao-pro-4k",
                    "messages": [
                        {
                            "role": "user",
                            "content": ai_prompt,
                        }
                    ],
                    "temperature": 0.2,
                }

                response = requests.post(
                    "https://open.doubao.com/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=90,
                )

                result = response.json()

                if response.status_code == 200:

                    report = (
                        result["choices"][0]
                        ["message"]["content"]
                    )

                    st.session_state["ai_report"] = report

                else:

                    st.error(
                        f"API调用失败：{result}"
                    )

            except Exception as e:

                st.error(
                    f"AI调用异常：{e}"
                )

    if st.session_state.get("ai_report"):

        st.divider()

        st.markdown(
            st.session_state["ai_report"]
        )

        st.download_button(
            "📥 下载AI运营报告",
            data=st.session_state["ai_report"],
            file_name="今日AI运营军师报告.txt",
            mime="text/plain",
        )


# ============================================================
# TAB 7 执行 & 复盘
# ============================================================

with tabs[6]:

    st.subheader("📋 执行记录")

    st.caption(
        "记录的不只是“做了什么”，还要记录“为什么做”和“做完有没有变好”。"
    )

    with st.form("action_form"):

        c1, c2, c3 = st.columns(3)

        with c1:

            priority = st.selectbox(
                "优先级",
                ["P0", "P1", "P2"],
            )

            object_type = st.selectbox(
                "对象类型",
                [
                    "商品",
                    "计划",
                    "关键词",
                    "人群",
                    "店铺",
                    "其他",
                ],
            )

            object_name = st.text_input(
                "对象名称"
            )

        with c2:

            problem = st.text_input(
                "为什么要调整"
            )

            action = st.selectbox(
                "执行动作",
                [
                    "提升预算",
                    "降低预算",
                    "提高出价",
                    "降低出价",
                    "暂停单元",
                    "开启单元",
                    "修改创意",
                    "修改关键词",
                    "调整人群",
                    "检查价格",
                    "检查优惠",
                    "检查详情页",
                    "其他",
                ],
            )

            adjustment = st.text_input(
                "具体调整内容"
            )

        with c3:

            before = st.text_input(
                "调整前指标"
            )

            observe = st.text_input(
                "观察指标"
            )

            period = st.selectbox(
                "观察周期",
                [
                    "1天",
                    "2天",
                    "3天",
                    "7天",
                ],
            )

            note = st.text_input(
                "备注"
            )

        submit = st.form_submit_button(
            "✅ 保存执行记录"
        )

        if submit:

            new_row = {
                "操作时间": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "优先级": priority,
                "对象类型": object_type,
                "对象名称": object_name,
                "问题": problem,
                "执行动作": action,
                "调整内容": adjustment,
                "调整前指标": before,
                "调整后指标": "",
                "观察指标": observe,
                "观察周期": period,
                "结果": "待复盘",
                "备注": note,
            }

            st.session_state.action_log = pd.concat(
                [
                    st.session_state.action_log,
                    pd.DataFrame([new_row]),
                ],
                ignore_index=True,
            )

            st.success(
                "执行记录已保存。"
            )

    st.divider()

    st.subheader("🔄 历史执行")

    if st.session_state.action_log.empty:

        st.info(
            "还没有执行记录。"
        )

    else:

        st.dataframe(
            st.session_state.action_log,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "📥 导出执行记录",
            data=st.session_state.action_log.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="运营执行记录.csv",
            mime="text/csv",
        )


# ============================================================
# TAB 8 原始数据
# ============================================================

with tabs[7]:

    st.subheader("📊 原始数据")

    st.caption(
        f"合并数据：{len(df_raw):,} 行 × {len(df_raw.columns):,} 列"
    )

    with st.expander(
        "查看原始字段"
    ):

        st.write(
            list(df_raw.columns)
        )

    st.dataframe(
        df_raw.head(500),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("标准化数据")

    st.dataframe(
        dff.head(500),
        use_container_width=True,
        hide_index=True,
    )
