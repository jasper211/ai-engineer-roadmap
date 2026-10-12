#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mark_standard_report.py — Mark标准报表（18页）程序化复刻，本轮范围第1-9页。

背景：业务方同事Mark基于2026-10-09批次数据做了一份18页PDF标准报表（见`raw_data/
Mark标准报表_W40_20261009.pdf`，文本已提取到`raw_data/Mark标准报表_文本提取/p01.txt`...
`p18.txt`），Jasper 10-12指示"把Mark这份定为标准，通过我们的自动化1:1显示"。架构设计见
`03_规划项目结构_Plan_Project_Structure/Mark标准报表_页面映射与架构设计_v0.1.md`。

跟multiview_dashboard.py（9视角tab切换深色主题）是两套独立产出：这里走"18页打印页面"
形态（白底+深藏青标题栏，`<section class="page" data-page="N">`配合`page-break-after:
always`，用浏览器"打印为PDF"导出真实多页PDF），CSS变量完全独立、不跟multiview_dashboard
共用`:root`。

数据层策略：
1. 能直接复用multiview_dashboard.py已验证的build_s1_view()/build_s2_view()/
   build_s3_view()/build_s4_view()/build_peer_view()/build_sunlife_view()计算结果的，
   直接复用，不重新读CSV重新算。
2. 逐页核对p01.txt-p09.txt原文后，发现若干处Mark的真实计算口径**不同于**我们现有
   build_*_view()的实现（不是简单复用就能对上数字），均已用独立pandas核对，详见各
   build_pageN()函数的docstring。主要有：
   - 第7页"T签批时效表"+新增"分档分布"：Mark的签批样本排除了1条TAT<0异常值
     （policy PI108585，sign晚于issue），分母=1646而不是1647。build_s3_view()的
     `timeliness`字段（对应s3_execution_view.py::section_g()）没有做这个排除，会跟
     Mark页面上的"合计1646"对不上——已用PDF渲染截图肉眼确认Mark页面显示的是1646/552，
     本模块为第7页重新计算（排除规则复用s3_execution_view.py::section_h()已有的
     TAT<0排除逻辑，不重新发明）。
   - 第6页"P KEY ACCOUNT TOP10"、第8/9页"V同行TOP10"：Mark的KA排名覆盖全量三阶段
     记录（含MGA拆分），不是S2-I/S2-K的"TOP20截断"口径——改用S6-A/B/C（KA×业务细分
     交叉表，`agent.py --s6`需先跑一遍确保数据是最新批次）的"合计"列重新聚合，
     独立核对TOP10/其他/总体三行数字精确匹配p06.txt/p08.txt原文。
   - 第3页"I永明产品排名"：Mark把SQ_rate缺失的记录标成"未提供"参与排名，不是像
     S4-B/C那样把SQ_rate缺失的记录整体排除在外——改用独立分组逻辑（复用
     s4_product_view.normalize_sq_rate()，缺失值填"未提供"而不是丢弃）。
   - 第9页"W同行月度分析"：Mark按自然日历月（res_date/sign_date/issue_date.dt.month）
     统计，不是build_peer_view()里"周→月"的derive_monthly_buckets()桶算法——两者在
     2026-01/2026-10均有1条记录级别的差异（经核对是周边界与月边界不重合导致），
     已改用自然月直接统计，逐月核对跟p09.txt原文精确匹配。
   以上均为"产出数字必须跟底层数据100%对得上"这条硬性要求下的必要修正，不是我自己
   猜测加的口径，每一处都有独立pandas脚本核对过（见执行记录.md v0.20.0）。
3. 第1-9页里确实可以直接复用的模块（如S1月度明细表格、S2业务线月度趋势、S3周度
   趋势/本周快报、同行referrer分析、永明月度趋势/牌照明细/批核路径等），已用真实数据
   逐项核对跟Mark原文一致，详见各build_pageN()。
"""
import datetime as dt
from pathlib import Path

import pandas as pd

from skills.ppt_data_loader import load_sheet, num
from skills.multiview_dashboard import (
    build_s1_view, build_s2_view, build_s3_view, build_s4_view,
    build_peer_view, build_sunlife_view, build_bank_view, build_agent_view, build_ka_view,
    current_week_from_labels, wow_pct, _ym_label, MONTHS_EN,
    _VENDOR_CHART_JS,
)
from skills.s2_business_view import SEGMENT_GROUPS, PEER_SEGMENTS, LAPSE_STATUSES, UNAPPROVED_STATUSES
from skills.s4_product_view import normalize_sq_rate, LAPSE_STATUSES as S4_LAPSE_STATUSES
from skills.ppt_config import SEGMENT_ORDER
from skills.report_enricher import TERM_BUCKET_EDGES, TERM_BUCKET_LABELS
from skills.cleaner import ENTITY_ALIAS_MAP

SUNLIFE_CARRIER = "香港永明金融有限公司"


# ======================================================================
# 格式化工具
# ======================================================================

def fmt_m(v, nd=1) -> str:
    """APE/保费类数字，统一'X.XM'格式（Mark标准：批核APE类数字2位小数+M；
    但KPI大卡片是1位小数，调用方按场景传nd）。"""
    try:
        return f"{float(v) / 1e6:.{nd}f}M"
    except (TypeError, ValueError):
        return "—"


def fmt_pct(v, nd=1) -> str:
    try:
        return f"{float(v) * 100:.{nd}f}%"
    except (TypeError, ValueError):
        return "—"


def fmt_cnt(v) -> str:
    try:
        return f"{int(round(float(v)))}"
    except (TypeError, ValueError):
        return "—"


def fmt_wan(v) -> str:
    """件均等"万"口径整数（Mark：'件均108.6万'）。"""
    try:
        return f"{float(v) / 1e4:.1f}万"
    except (TypeError, ValueError):
        return "—"


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ======================================================================
# 数据加载
# ======================================================================

def _load_views(data_root: Path):
    """加载S1/S2/S3/S4/S9已有CSV（build_*_view()口径）+ 清洗后底表df（新计算用）。
    S5/S6/S7本轮需要S6（第6/8/9页KA排名）——如果S6目录下文件比S1/S2/S3/S4/S9旧
    （换底表后忘了跑--s6），在render()里会提醒先跑`agent.py --s6`。"""
    from skills.data_loader import DataLoader
    from skills.cleaner import Cleaner

    data_root = Path(data_root)
    s1 = load_sheet(data_root / "S1_总览仪表盘")
    s2 = load_sheet(data_root / "S2_业务端视角")
    s3 = load_sheet(data_root / "S3_执行管理端")
    s4 = load_sheet(data_root / "S4_产品端视角")
    s9_dir = data_root / "S9_代理人与KA业务"
    s9 = load_sheet(s9_dir) if s9_dir.exists() else None
    s6_dir = data_root / "S6_市场与交叉视角"
    s6 = load_sheet(s6_dir) if s6_dir.exists() else None

    raw_data_dir = data_root.parent / "raw_data"
    load_result = DataLoader(raw_data_dir).load()
    df = Cleaner().clean(load_result.df, load_result.export_date)

    return {
        "s1": s1, "s2": s2, "s3": s3, "s4": s4, "s9": s9, "s6": s6,
        "df": df, "export_date": load_result.export_date,
        "raw_df": load_result.df,  # Phase2第14页数据质量披露需要清洗前的原始值（ape/premium的NaN
                                    # 会被cleaner.py fillna(0)，issuing_entity简繁别名会被替换，
                                    # 必须用这份pre-clean df才能独立统计"缺失""归一化影响记录数"等。
    }


# ======================================================================
# 第7页专用：签批时效（排除TAT<0异常值的口径，跟Mark原文"排除1件"一致）
# ======================================================================

def _timeliness_corrected(df: pd.DataFrame) -> dict:
    """复刻Mark页7"T签批时效综合分析"表+新增"签批时效分档分布"模块，population口径：
    status=生效 AND issue_year=2026 AND TAT(issue_date-sign_date)>=0。
    排除规则直接复用s3_execution_view.py::section_h()已有的bucket()函数判断
    （t<0返回None不入档），这里只是把同一条排除规则也应用到"分母"和"合计"行上——
    build_s3_view()现有的timeliness字段（对应section_g()）没有做这个排除，
    合计显示1647/同行经代553，用built-in browser截图肉眼核对Mark PDF原文后
    确认实际显示的是1646/552，必须用这个口径重算才能跟Mark页面对上。"""
    base = df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)].copy()
    base["_tat"] = (base["issue_date"] - base["sign_date"]).dt.days
    excluded_count = int((base["_tat"] < 0).sum())
    valid = base[base["_tat"] >= 0].copy()

    rows = []
    for label, codes in SEGMENT_GROUPS.items():
        g = valid[valid["segment_code"].isin(codes)]
        if len(g) == 0:
            rows.append({"业务细分": label, "件数": 0, "件均APE": None, "平均时效": None,
                         "P90时效": None, "中位时效": None, "最长时效": None, "SLA达标率": None})
            continue
        tat = g["_tat"]
        rows.append({
            "业务细分": label, "件数": int(len(g)), "件均APE": float(g["ape"].mean()),
            "平均时效": round(float(tat.mean()), 1), "P90时效": round(float(tat.quantile(0.9)), 1),
            "中位时效": round(float(tat.median()), 1), "最长时效": int(tat.max()),
            "SLA达标率": float((tat <= 60).mean()),
        })
    total_count = int(len(valid))
    total_ape = float(valid["ape"].sum())
    tat_all = valid["_tat"]
    rows.append({
        "业务细分": "合计", "件数": total_count, "件均APE": total_ape / total_count if total_count else 0.0,
        "平均时效": round(float(tat_all.mean()), 1), "P90时效": round(float(tat_all.quantile(0.9)), 1),
        "中位时效": round(float(tat_all.median()), 1), "最长时效": int(tat_all.max()),
        "SLA达标率": float((tat_all <= 60).mean()),
    })

    def bucket(t):
        if t < 0:
            return None
        if t <= 7:
            return "≤7天"
        if t <= 14:
            return "8-14天"
        if t <= 30:
            return "15-30天"
        if t <= 60:
            return "31-60天"
        if t <= 90:
            return "61-90天"
        return ">90天"

    valid["_bucket"] = valid["_tat"].apply(bucket)
    bucket_rows = []
    for label in ["≤7天", "8-14天", "15-30天", "31-60天", "61-90天", ">90天"]:
        g = valid[valid["_bucket"] == label]
        bucket_rows.append({
            "分档": label, "件数": int(len(g)),
            "占比": len(g) / total_count if total_count else 0.0,
        })
    sla60_count = sum(r["件数"] for r in bucket_rows if r["分档"] in ("≤7天", "8-14天", "15-30天", "31-60天"))

    return {
        "segment_rows": rows,
        "bucket_rows": bucket_rows,
        "total_valid": total_count,
        "excluded_count": excluded_count,
        "sla60_count": sla60_count,
        "sla60_rate": sla60_count / total_count if total_count else 0.0,
    }


# ======================================================================
# 第3页专用：永明未批核/待签KPI + 内部牌照明细(按issuing_entity，非S1-H的牌照映射)
#            + 签单产品排名(SQ_rate缺失计入"未提供",不整体排除)
# ======================================================================

def _sunlife_pipeline_kpi(df: pd.DataFrame) -> dict:
    """永明(carrier口径)未批核/待签APE+件数+件均——S1-A没有这两个字段，独立计算。
    排除/口径规则复用s2_business_view.UNAPPROVED_STATUSES(未批核4态)+"排期"(待签)，
    跟s1_dashboard.py::section_h()永明牌照明细用同一个carrier过滤条件
    （carrier_code==香港永明金融有限公司），保证跟build_s1_view()的sun_achv等
    是同一个population的不同切片。"""
    sl = df[df["carrier_code"] == SUNLIFE_CARRIER]
    unbat = sl[sl["policy_status"].isin(UNAPPROVED_STATUSES)]
    pend = sl[sl["policy_status"] == "排期"]
    unbat_ape, unbat_cnt = float(unbat["ape"].sum()), int(len(unbat))
    pend_ape, pend_cnt = float(pend["ape"].sum()), int(len(pend))
    return {
        "unbat_ape": unbat_ape, "unbat_cnt": unbat_cnt,
        "unbat_avg": unbat_ape / unbat_cnt if unbat_cnt else 0.0,
        "pend_ape": pend_ape, "pend_cnt": pend_cnt,
        "pend_avg": pend_ape / pend_cnt if pend_cnt else 0.0,
    }


def _sunlife_entity_table(df: pd.DataFrame, export_date) -> dict:
    """page3 "G 永明内部牌照明细"——跟S1-H的"牌照"(JF/UNIWIN/DW Bank/...)映射口径
    不同，Mark这里是直接用issuing_entity原始值分组（最近4个2026月份批核+未批核
    快照+当月已递交）。我们的cleaner.py v0.19.0已把issuing_entity简繁别名
    （怡泰/九富/众和恒富等5对）归一化合并，所以这里展示的是归一化后的实体
    （行数比Mark原文少，因为Mark选择"保留源名称"不合并——这是本项目v0.19.0的既定
    决策，归一化前后总量不变，已独立验证，见执行记录.md v0.19.0/v0.20.0），
    月度合计金额不受影响（归一化只改变行的切分方式，不改变总量）。"""
    sl = df[df["carrier_code"] == SUNLIFE_CARRIER]
    entities = sorted(sl["issuing_entity"].dropna().unique().tolist())
    all_issue_months = sorted(sl[sl["policy_status"] == "生效"]["issue_date"].dt.strftime("%Y-%m").dropna().unique())
    months = all_issue_months[-4:] if len(all_issue_months) >= 4 else all_issue_months
    report_month = export_date.strftime("%Y-%m") if export_date is not None else months[-1]

    rows = []
    for ent in entities:
        g = sl[sl["issuing_entity"] == ent]
        row = {"entity": ent}
        for m in months:
            sub = g[(g["policy_status"] == "生效") & (g["issue_date"].dt.strftime("%Y-%m") == m)]
            row[m] = float(sub["ape"].sum())
        unapp = g[g["policy_status"].isin(UNAPPROVED_STATUSES)]
        row["未批核"] = float(unapp["ape"].sum())
        submitted = g[g["submit_date"].dt.strftime("%Y-%m") == report_month]
        row["当月递交"] = float(submitted["ape"].sum())
        rows.append(row)

    total = {"entity": "内部合计"}
    for m in months + ["未批核", "当月递交"]:
        total[m] = sum(r[m] for r in rows)
    rows.append(total)
    return {
        "months": [_ym_label(m) for m in months], "months_raw": months, "rows": rows,
        "report_month": _ym_label(report_month),
        "last_month_batch": total[months[-1]] if months else 0.0,
    }


def _sunlife_product_ranking(df: pd.DataFrame) -> dict:
    """page3 "I 永明2026年签单产品排名"——population=carrier(永明)+sign_year=2026+
    非流失(3态LAPSE_STATUSES，不含拒保，复用s4_product_view.LAPSE_STATUSES跟B/C节
    同一口径)；联合主键=产品名称+年期+SQ_rate标准化——但跟S4-B/C不同的是，SQ_rate
    缺失的记录这里不整体排除，标成"未提供"独立参与排名（已用全量数据核对：
    Top1/2正是"未提供"组，378件156.19M/385件73.13M，若按S4-B/C规则排除会直接漏掉
    这两组，TOP10/其他/总体三级数字也会错——这是本页专属规则，不能照搬S4-B/C）。"""
    sub = df[
        (df["carrier_code"] == SUNLIFE_CARRIER)
        & (df["sign_date"].dt.year == 2026)
        & (~df["policy_status"].isin(S4_LAPSE_STATUSES))
    ].copy()
    sub["_sq"] = sub["SQ_rate"].apply(normalize_sq_rate).fillna("未提供")

    rows = []
    for (product, term, sq), g in sub.groupby(["product_id", "premium_term", "_sq"], dropna=False, observed=True):
        rows.append({
            "产品名称": product, "年期": term, "首年折扣": sq,
            "件数": int(len(g)), "APE": float(g["ape"].sum()),
        })
    rows.sort(key=lambda r: r["APE"], reverse=True)
    top10, rest = rows[:10], rows[10:]
    return {
        "top10": top10,
        "rest_cnt": sum(r["件数"] for r in rest), "rest_ape": sum(r["APE"] for r in rest),
        "total_cnt": sum(r["件数"] for r in rows), "total_ape": sum(r["APE"] for r in rows),
    }


# ======================================================================
# 第6/8/9页专用：KA排名（全量三阶段，MGA拆分——复用S6-A/B/C"合计"列，不用S2-I/K的TOP20截断）
# ======================================================================

def _ka_rank_from_s6(s6: dict, prefix_ape: tuple, prefix_cnt: tuple, top_n: int = 10) -> dict:
    """prefix_ape=('A-APE','B-APE','C-APE')对应(批核,未批核,待签)三张APE表，
    prefix_cnt同理对应件数表。取各表"合计"列(=该KA跨8个业务细分的汇总)，按批核APE
    降序取TOP N+其他+总体。用p06.txt"P KEY ACCOUNT TOP10"/p08.txt"V同行TOP10 KEY
    ACCOUNT"两处真实数字逐行核对过，S6-A/B/C(ka维度)口径下精确匹配。"""
    def _map(key):
        d = s6[key]
        out = {}
        for _, r in d.iterrows():
            ka = str(r["KA"]).strip()
            if ka and ka != "合计":
                out[ka] = num(r["合计"])
        return out

    A, B, C = (_map(k) for k in prefix_ape)
    AC, BC, CC = (_map(k) for k in prefix_cnt)
    kas = sorted(set(A) | set(B) | set(C))
    rows = []
    for ka in kas:
        rows.append({
            "ka": ka,
            "batch": A.get(ka, 0.0), "batch_c": int(AC.get(ka, 0)),
            "unbat": B.get(ka, 0.0), "unbat_c": int(BC.get(ka, 0)),
            "pend": C.get(ka, 0.0), "pend_c": int(CC.get(ka, 0)),
        })
    rows.sort(key=lambda r: r["batch"], reverse=True)
    top, rest = rows[:top_n], rows[top_n:]

    def _sum(key, lst):
        return sum(r[key] for r in lst)

    def _totals(lst):
        return {
            "batch": _sum("batch", lst), "batch_c": _sum("batch_c", lst),
            "unbat": _sum("unbat", lst), "unbat_c": _sum("unbat_c", lst),
            "pend": _sum("pend", lst), "pend_c": _sum("pend_c", lst),
        }

    return {"top": top, "rest": _totals(rest), "total": _totals(rows)}


def _ka_rank_from_s2(df_batch, top_n: int = 10) -> dict:
    """同行视角(S2-K)专用——S2-K本身已是"同行业绩"scope(含MGA拆分)下的KA全量明细
    （不是TOP20截断），直接用它的APE+未批核+待签字段即可，不需要像P模块那样
    重新从S6拼。用p08.txt"V同行TOP10 KEY ACCOUNT分析"逐行核对精确匹配。"""
    rows = []
    for _, r in df_batch.iterrows():
        ka = str(r["KEY ACCOUNT"]).strip()
        if not ka or ka == "合计":
            continue
        rows.append({
            "ka": ka,
            "batch": num(r["2026批核APE"]), "batch_c": int(num(r["批核件数"])),
            "unbat": num(r["未批核APE"]), "unbat_c": int(num(r["未批核件数"])),
            "pend": num(r["待签APE"]), "pend_c": int(num(r["待签件数"])),
        })
    rows.sort(key=lambda r: r["batch"], reverse=True)
    top, rest = rows[:top_n], rows[top_n:]

    def _totals(lst):
        return {k: sum(r[k] for r in lst) for k in ("batch", "batch_c", "unbat", "unbat_c", "pend", "pend_c")}

    return {"top": top, "rest": _totals(rest), "total": _totals(rows)}


# ======================================================================
# 第9页专用：同行月度分析（自然日历月，不是derive_monthly_buckets的周→月桶算法）
# ======================================================================

def _peer_calendar_monthly(df: pd.DataFrame) -> list:
    """page9 "W 同行月度分析"——独立核对发现Mark用自然日历月统计（res_date/sign_date/
    issue_date各自的.dt.month），不是build_peer_view()里"周→月"的derive_monthly_
    buckets()桶算法；两者在2026-01（签单56件vs桶算法的55件）、2026-10等月份有1条
    记录级别的差异（%U周三所在月跟日历月边界不完全重合导致），已用p09.txt"W同行月度
    分析"全部10个月+"同行本月预约/签单/批核APE"三个KPI卡片逐一核对，自然月口径
    精确匹配，周桶算法不匹配——所以本页改用自然月重新统计，不能直接复用
    build_peer_view()['monthly_rows']。population跟S2-K同一套（PEER_SEGMENTS=
    永明经代/同行经代/MGA业务，含MGA；预约排除流失、签单排除流失+排期、批核仅生效，
    跟S3-J/K/L同一套三态规则）。"""
    pop = df[df["segment_code"].isin(PEER_SEGMENTS)]
    res = pop[~pop["policy_status"].isin(LAPSE_STATUSES)]
    sign = pop[~pop["policy_status"].isin(LAPSE_STATUSES + ["排期"])]
    issue = pop[pop["policy_status"] == "生效"]

    months = sorted(set(
        res.loc[res["res_date"].dt.year == 2026, "res_date"].dt.strftime("%Y-%m")
    ) | set(
        sign.loc[sign["sign_date"].dt.year == 2026, "sign_date"].dt.strftime("%Y-%m")
    ) | set(
        issue.loc[issue["issue_date"].dt.year == 2026, "issue_date"].dt.strftime("%Y-%m")
    ))
    rows = []
    for m in months:
        r_sub = res[(res["res_date"].dt.year == 2026) & (res["res_date"].dt.strftime("%Y-%m") == m)]
        s_sub = sign[(sign["sign_date"].dt.year == 2026) & (sign["sign_date"].dt.strftime("%Y-%m") == m)]
        i_sub = issue[(issue["issue_date"].dt.year == 2026) & (issue["issue_date"].dt.strftime("%Y-%m") == m)]
        rows.append({
            "month": _ym_label(m),
            "预约APE": float(r_sub["ape"].sum()), "预约件数": int(len(r_sub)),
            "签单APE": float(s_sub["ape"].sum()), "签单件数": int(len(s_sub)),
            "批核APE": float(i_sub["ape"].sum()), "批核件数": int(len(i_sub)),
        })
    return rows


# ======================================================================
# 第10-18页专用（Phase2新增）：银行/代理人/KA"本月"KPI、热力矩阵完整表格、
# 永明产品保费排名+完整年期分布、同行完整渠道/推荐人、未批渠道TOP10、
# 第14页数据质量披露+8线x4事件当周表。全部已用独立pandas逐项核对
# （见执行记录.md v0.22.0），不是凑数。
# ======================================================================

def _segment_calendar_current_month(df: pd.DataFrame, codes: list) -> tuple:
    """银行/代理人业务页面的"本月"KPI卡——跟第9页_peer_calendar_monthly()同一套
    自然日历月统计规则（预约排除流失、签单排除流失+排期、批核仅生效），只是population
    从PEER_SEGMENTS换成调用方传入的codes（BK业务/天领业务+成事家办等）。当前月=
    这组segment的res/sign/issue三态日期并集里最新出现的2026年月份，不是日历今天。"""
    pop = df[df["segment_code"].isin(codes)]
    res = pop[~pop["policy_status"].isin(LAPSE_STATUSES)]
    sign = pop[~pop["policy_status"].isin(LAPSE_STATUSES + ["排期"])]
    issue = pop[pop["policy_status"] == "生效"]
    months = sorted(set(
        res.loc[res["res_date"].dt.year == 2026, "res_date"].dt.strftime("%Y-%m")
    ) | set(
        sign.loc[sign["sign_date"].dt.year == 2026, "sign_date"].dt.strftime("%Y-%m")
    ) | set(
        issue.loc[issue["issue_date"].dt.year == 2026, "issue_date"].dt.strftime("%Y-%m")
    ))
    if not months:
        return None, {"预约": {"ape": 0.0, "cnt": 0}, "签单": {"ape": 0.0, "cnt": 0}, "批核": {"ape": 0.0, "cnt": 0}}
    cur_month = months[-1]

    def _sub(g, col):
        s = g[(g[col].dt.year == 2026) & (g[col].dt.strftime("%Y-%m") == cur_month)]
        return {"ape": float(s["ape"].sum()), "cnt": int(len(s))}

    return _ym_label(cur_month), {
        "预约": _sub(res, "res_date"), "签单": _sub(sign, "sign_date"), "批核": _sub(issue, "issue_date"),
    }


def _heat_table(df_section: pd.DataFrame, weeks: list) -> dict:
    """第16-18页Q/R/S周度热力矩阵——数据源=s3["B"]/["C"]/["D"]（业务细分×周，跟
    build_s3_view()的full_week_table同一个取数方式），独立重写成"APE+件数同格"的
    Mark单元格样式（不是build_s3_view().full_week_table那种只取APE的纯数字表）。
    weeks传入的是已经按当前周截到最近15周的窗口（见_recent_weeks()），已用真实数据
    逐格核对跟p16/p17/p18.txt原文100%匹配（见执行记录.md v0.22.0）。"""
    row_by_seg = {r["业务细分"]: r for _, r in df_section.iterrows()}
    rows = []
    for seg in SEGMENT_ORDER:
        r = row_by_seg.get(seg)
        vals = []
        for w in weeks:
            if r is not None and f"{w}_APE" in r.index:
                vals.append({"ape": num(r[f"{w}_APE"]), "cnt": int(num(r[f"{w}_件数"]))})
            else:
                vals.append({"ape": 0.0, "cnt": 0})
        rows.append({"segment": seg, "vals": vals})
    tot_row = row_by_seg.get("合计")
    totals = []
    for i, w in enumerate(weeks):
        if tot_row is not None and f"{w}_APE" in tot_row.index:
            totals.append({"ape": num(tot_row[f"{w}_APE"]), "cnt": int(num(tot_row[f"{w}_件数"]))})
        else:
            totals.append({
                "ape": sum(r["vals"][i]["ape"] for r in rows),
                "cnt": sum(r["vals"][i]["cnt"] for r in rows),
            })
    return {"weeks": [w.replace("2026W", "W") for w in weeks], "rows": rows, "total": totals}


def _recent_weeks(df_section: pd.DataFrame, n: int = 15) -> list:
    """取df_section全部周列里最近n周（原始'2026W40'格式，升序）——用于第16-18页窗口。
    用真实数据核对过：取最近15周时，窗口恰好落在W26-W40，逐格数字跟Mark原文
    p16/p17/p18.txt100%匹配（Mark原始PDF页面本身只展示最近15周，不是展示全年40周），
    这里用"取最后N列"而不是硬编码'W26'，保证以后周数往前滚动时窗口自动跟着滑动。"""
    weeks = [c[:-4] for c in df_section.columns if c.endswith("_APE")]
    return weeks[-n:] if len(weeks) > n else weeks


def _page14_event_table(s3: dict, cur_week_raw: str) -> dict:
    """第14页"2026W40完整八线／四事件"表——预约/签单/批核来自S3-B/C/D当前周这一列
    （跟S3business_line_this_week同一个取数方式，独立重写为同时取APE+件数），"递交"
    按Jasper指示留空（S3-A只有递交总量，没有按业务细分拆分的递交周度数据源，详见
    模块级docstring和known_limitations，不新增反推逻辑凑数据）。"""
    def _seg_vals(df_section):
        row_by_seg = {r["业务细分"]: r for _, r in df_section.iterrows()}
        out = {}
        for seg in SEGMENT_ORDER:
            r = row_by_seg.get(seg)
            if r is not None and f"{cur_week_raw}_APE" in r.index:
                out[seg] = {"ape": num(r[f"{cur_week_raw}_APE"]), "cnt": int(num(r[f"{cur_week_raw}_件数"]))}
            else:
                out[seg] = {"ape": 0.0, "cnt": 0}
        return out

    res, sign, issue = _seg_vals(s3["B"]), _seg_vals(s3["C"]), _seg_vals(s3["D"])
    rows = [{"segment": seg, "res": res[seg], "sign": sign[seg], "issue": issue[seg]} for seg in SEGMENT_ORDER]
    totals = {
        "res": {"ape": sum(res[s]["ape"] for s in SEGMENT_ORDER), "cnt": sum(res[s]["cnt"] for s in SEGMENT_ORDER)},
        "sign": {"ape": sum(sign[s]["ape"] for s in SEGMENT_ORDER), "cnt": sum(sign[s]["cnt"] for s in SEGMENT_ORDER)},
        "issue": {"ape": sum(issue[s]["ape"] for s in SEGMENT_ORDER), "cnt": sum(issue[s]["cnt"] for s in SEGMENT_ORDER)},
    }
    return {"rows": rows, "totals": totals}


def _data_quality_disclosure(raw_df: pd.DataFrame, df: pd.DataFrame, negative_tat_count: int) -> dict:
    """第14页"数据与解释边界+异常保留清单"——每一项都独立用pandas重算自本批数据，
    不是照抄p14.txt里Mark那次(10-09批次)跑出来的具体数字（我们可能是同一批数据但经过
    v0.19.0实体归一化/v0.21.0负时效排除口径修正，数字不一定完全一样，必须重新算）。
    用raw_df（DataLoader产出、cleaner.clean()之前）才能看到ape/premium真实的NaN
    （cleaner会fillna(0)）和issuing_entity的原始简繁写法（cleaner会归一化替换）。"""
    n_rows = int(len(df))
    # "缺批核日期"：population=policy_status==生效（应该有issue_date但没有，是真异常；
    # 未批核/排期/流失等状态issue_date本来就该是空，不计入这个异常口径）。
    missing_issue_date = int(((df["policy_status"] == "生效") & df["issue_date"].isna()).sum())
    ape_missing = int(pd.to_numeric(raw_df["ape"], errors="coerce").isna().sum())
    premium_missing = int(pd.to_numeric(raw_df["premium"], errors="coerce").isna().sum())
    future_dated = int(df["future_dated"].sum())
    declined = int((df["policy_status"] == "拒保").sum())

    entity_alias_records = int(raw_df["issuing_entity"].isin(ENTITY_ALIAS_MAP.keys()).sum())
    entity_alias_pairs = int(sum(1 for k in ENTITY_ALIAS_MAP if (raw_df["issuing_entity"] == k).any()))

    return {
        "n_rows": n_rows, "missing_issue_date": missing_issue_date,
        "ape_missing": ape_missing, "premium_missing": premium_missing,
        "future_dated": future_dated, "declined": declined,
        "negative_tat": negative_tat_count,
        "entity_alias_records": entity_alias_records, "entity_alias_pairs": entity_alias_pairs,
    }


def _sunlife_premium_ranking(df: pd.DataFrame, top_n: int = 10) -> dict:
    """第13页"永明产品保费TOP10+其他"——population跟第3页I模块(_sunlife_product_ranking)
    完全同一个(carrier=永明,sign_year=2026,排除3态流失不含拒保)、联合主键也同一个
    (产品名称+年期+SQ_rate标准化'未提供'不丢弃)，唯一区别是本页按保费(premium)降序
    排名，不是按APE——用真实数据核对过TOP10逐行跟p13.txt精确匹配，总体1171件/951.42M
    保费(跟第3页I模块总体1171件/444.41M APE是同一组1171条记录的两个不同金额口径，
    不能互相替代)。"""
    sub = df[
        (df["carrier_code"] == SUNLIFE_CARRIER)
        & (df["sign_date"].dt.year == 2026)
        & (~df["policy_status"].isin(S4_LAPSE_STATUSES))
    ].copy()
    sub["_sq"] = sub["SQ_rate"].apply(normalize_sq_rate).fillna("未提供")

    rows = []
    for (product, term, sq), g in sub.groupby(["product_id", "premium_term", "_sq"], dropna=False, observed=True):
        rows.append({
            "产品名称": product, "年期": term, "首年折扣": sq,
            "件数": int(len(g)), "保费": float(g["premium"].sum()), "APE": float(g["ape"].sum()),
        })
    rows.sort(key=lambda r: r["保费"], reverse=True)
    top, rest = rows[:top_n], rows[top_n:]
    return {
        "top": top,
        "rest_cnt": sum(r["件数"] for r in rest), "rest_premium": sum(r["保费"] for r in rest),
        "total_cnt": sum(r["件数"] for r in rows), "total_premium": sum(r["保费"] for r in rows),
    }


def _sunlife_term_distribution(df: pd.DataFrame) -> list:
    """第13页"完整年期分布"——population跟_sunlife_premium_ranking()/第3页I模块同一个
    (1171条记录)，按premium_term分6类：report_enricher.py既有的TERM_BUCKET_LABELS
    4档(短期/中期/长期/终身)只覆盖"数字"值，真实数据premium_term还有NaN(年期缺失)和
    文本值如'至100岁'(文本年期)两种_term_bucket()本身返回None、未细分的情况——这里
    把这两种None拆成独立的"年期缺失"/"文本年期"两档，不是report_enricher.py的bug，
    是那个函数本来就没打算区分、本页Mark原文需要区分才新增的独立分类逻辑。
    已用真实数据逐档核对跟p13.txt"完整年期分布"表6行+总体精确匹配。"""
    sub = df[
        (df["carrier_code"] == SUNLIFE_CARRIER)
        & (df["sign_date"].dt.year == 2026)
        & (~df["policy_status"].isin(S4_LAPSE_STATUSES))
    ].copy()

    def _classify(v):
        if pd.isna(v):
            return "年期缺失"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            for edge, label in zip(TERM_BUCKET_EDGES, TERM_BUCKET_LABELS):
                if v <= edge:
                    return label
            return TERM_BUCKET_LABELS[-1]
        return "文本年期"

    sub["_cls"] = sub["premium_term"].apply(_classify)
    order = [TERM_BUCKET_LABELS[1], TERM_BUCKET_LABELS[0], TERM_BUCKET_LABELS[2], TERM_BUCKET_LABELS[3],
             "年期缺失", "文本年期"]
    rows = []
    for label in order:
        g = sub[sub["_cls"] == label]
        rows.append({
            "年期类别": label, "件数": int(len(g)),
            "APE": float(g["ape"].sum()), "保费": float(g["premium"].sum()),
        })
    return rows


def _peer_partner_full(df: pd.DataFrame, top_n: int = 10) -> dict:
    """第15页"合作渠道"——按partner_code分组（不是key_account/referral_code），
    population=PEER_SEGMENTS(同第8页V模块/build_peer_view同一个'同行'范围)，三态口径
    跟_stage_agg()(s2_business_view.py)同规则独立重写。已用真实数据核对TOP10逐行
    （含排名顺序）跟p15.txt"合作渠道"表精确匹配，总体399.63M/1072件(批核)+
    51.61M/126件(未批核)+7.07M/14件(待签)。"""
    pop = df[df["segment_code"].isin(PEER_SEGMENTS)].copy()

    def _stat(g):
        b26 = g[(g["policy_status"] == "生效") & (g["issue_date"].dt.year == 2026)]
        unapp = g[g["policy_status"].isin(UNAPPROVED_STATUSES)]
        pend = g[g["policy_status"] == "排期"]
        return {
            "batch": float(b26["ape"].sum()), "batch_c": int(len(b26)),
            "unbat": float(unapp["ape"].sum()), "unbat_c": int(len(unapp)),
            "pend": float(pend["ape"].sum()), "pend_c": int(len(pend)),
        }

    rows = []
    for p, g in pop.groupby("partner_code", observed=True, dropna=False):
        s = _stat(g)
        if s["batch_c"] + s["unbat_c"] + s["pend_c"] == 0:
            continue
        rows.append({"partner": p, **s})
    rows.sort(key=lambda r: r["batch"], reverse=True)
    top, rest = rows[:top_n], rows[top_n:]

    def _tot(lst):
        return {k: sum(r[k] for r in lst) for k in ("batch", "batch_c", "unbat", "unbat_c", "pend", "pend_c")}

    return {"top": top, "rest": _tot(rest), "total": _tot(rows)}


def _peer_referrer_full(df: pd.DataFrame) -> dict:
    """第15页"推荐人"——population同_peer_partner_full()(PEER_SEGMENTS)，按
    referral_code分组；S2-J板块(section_j)只硬编码了6个具名推荐人，这里额外独立
    重算"其他/未提供"= 总体 - 6个具名推荐人之和（不是遗漏，是S2-J本身设计上就只
    展示6个具名推荐人，第15页要求"完整总体"必须补上这一档）。已用真实数据核对
    6个具名行+其他/未提供行跟p15.txt"推荐人"表精确匹配。"""
    pop = df[df["segment_code"].isin(PEER_SEGMENTS)]
    names = ["姜通", "战略合作", "高瑶", "白博文", "Mark", "魏子璐"]

    def _stat(g):
        b26 = g[(g["policy_status"] == "生效") & (g["issue_date"].dt.year == 2026)]
        unapp = g[g["policy_status"].isin(UNAPPROVED_STATUSES)]
        pend = g[g["policy_status"] == "排期"]
        return {
            "batch": float(b26["ape"].sum()), "unbat": float(unapp["ape"].sum()), "pend": float(pend["ape"].sum()),
            "cnt": int(len(b26) + len(unapp) + len(pend)),
        }

    named = [{"name": n, **_stat(pop[pop["referral_code"] == n])} for n in names]
    all_stat = _stat(pop)
    other = {k: all_stat[k] - sum(r[k] for r in named) for k in all_stat}
    return {"named": named, "other": other, "total": all_stat}


def _bank_weekly_detail_with_count(s3: dict) -> dict:
    """第10页"AC本周银行KA业绩详情"表专用——跟build_bank_view()现有的weekly_detail
    （只取APE，复用multiview_dashboard._weekly_detail_table()）不同，Mark这张表
    每个指标都要同时展示APE(M)和件数两列，这里独立重写一版"同时取数"的版本，
    不改动multiview_dashboard.py。已用真实数据核对三家银行×预约/签单/批核六个
    单元格跟p10.txt"AC"表精确匹配（平安银行全0、民生银行预约0.78M/1件、
    浦发银行批核0.78M/1件）。"""
    M_ape, N_ape, O_ape = s3["M_ape"], s3["N_ape"], s3["O_ape"]
    M_cnt, N_cnt, O_cnt = s3["M_count"], s3["N_count"], s3["O_count"]
    pairs = {"预约": (M_ape, M_cnt), "签单": (N_ape, N_cnt), "批核": (O_ape, O_cnt)}
    weeks = sorted(
        {c for df_, _ in pairs.values() for c in df_.columns if c.startswith("2026W")},
        key=lambda w: int(w.replace("2026W", "")),
    )
    cur_week, _ = current_week_from_labels(weeks)
    entities, seen = [], set()
    for ape_df, _ in pairs.values():
        for ka in ape_df["KEY ACCOUNT"]:
            ka = str(ka).strip()
            if ka and ka != "合计" and ka not in seen:
                seen.add(ka)
                entities.append(ka)
    rows = []
    for ka in entities:
        vals = {}
        for name, (ape_df, cnt_df) in pairs.items():
            sub_a = ape_df[ape_df["KEY ACCOUNT"] == ka]
            sub_c = cnt_df[cnt_df["KEY ACCOUNT"] == ka]
            ape = num(sub_a.iloc[0][cur_week]) if not sub_a.empty and cur_week and cur_week in sub_a.columns else 0.0
            cnt = int(num(sub_c.iloc[0][cur_week])) if not sub_c.empty and cur_week and cur_week in sub_c.columns else 0
            vals[name] = {"ape": ape, "cnt": cnt}
        rows.append({"ka": ka, "vals": vals, "_sort": sum(v["ape"] for v in vals.values())})
    rows.sort(key=lambda r: r["_sort"], reverse=True)
    total = {
        name: {"ape": sum(r["vals"][name]["ape"] for r in rows), "cnt": sum(r["vals"][name]["cnt"] for r in rows)}
        for name in pairs
    }
    return {
        "cur_week": cur_week.replace("2026W", "W") if cur_week else None,
        "rows": [{"ka": r["ka"], "vals": r["vals"]} for r in rows], "total": total,
    }


def _bank_monthly_issue_total(s3: dict) -> dict:
    """第10页"银行月度已批核APE趋势"图专用——复用build_bank_view()::monthly_by_bank()
    同一个ppt_monthly_bucket.derive_monthly_buckets()周→月分桶算法，应用在O_ape/
    O_count的"合计"行上得到跨银行汇总的月度批核APE+件数（不重新发明分桶规则，
    只是取数对象从"各银行"换成"合计"行）。"""
    from skills.ppt_monthly_bucket import derive_monthly_buckets

    O_ape, O_cnt = s3["O_ape"], s3["O_count"]
    weeks = [c for c in O_ape.columns if c.startswith("2026W")]
    buckets = derive_monthly_buckets(weeks)
    o_tot_ape = O_ape[O_ape["KEY ACCOUNT"] == "合计"].iloc[0]
    o_tot_cnt = O_cnt[O_cnt["KEY ACCOUNT"] == "合计"].iloc[0]
    labels, ape_vals, cnt_vals = [], [], []
    for m, ws in buckets:
        labels.append(m)
        ape_vals.append(sum(num(o_tot_ape.get(w, 0)) for w in ws))
        cnt_vals.append(sum(num(o_tot_cnt.get(w, 0)) for w in ws))
    return {"labels": labels, "ape": ape_vals, "cnt": cnt_vals}


def _unapproved_channel_top10(df: pd.DataFrame, top_n: int = 10) -> dict:
    """第14页"在途推进·按未批APE排序TOP10"——渠道=key_account(MGA业务拆分成
    'XX(MGA)'独立行，跟S2-K/O等既有KA排名同一个拆分规则)，population=全部业务线
    (不限segment)里policy_status在未批核4态(UNAPPROVED_STATUSES)的记录，按APE降序。
    已用真实数据核对TOP10逐行(含排名顺序，混合了BK/同行/代理人多个业务线的渠道)
    跟p14.txt"未批渠道TOP10"精确匹配，其他8.70M/27件、总体87.07M/171件。"""
    unb = df[df["policy_status"].isin(UNAPPROVED_STATUSES)].copy()
    is_mga = unb["segment_code"] == "MGA业务"
    unb["_label"] = unb["key_account"].where(~is_mga, unb["key_account"] + "(MGA)")
    rows = []
    for ka, g in unb.groupby("_label", observed=True):
        rows.append({"ka": ka, "ape": float(g["ape"].sum()), "cnt": int(len(g))})
    rows.sort(key=lambda r: r["ape"], reverse=True)
    top, rest = rows[:top_n], rows[top_n:]
    return {
        "top": top,
        "rest": {"ape": sum(r["ape"] for r in rest), "cnt": sum(r["cnt"] for r in rest)},
        "total": {"ape": sum(r["ape"] for r in rows), "cnt": sum(r["cnt"] for r in rows)},
    }


# ======================================================================
# 页脚/当前周
# ======================================================================

def _current_week_full(s3: dict) -> str:
    week_cols = [c for c in s3["A"].columns if c.endswith("_APE")]
    weeks = [c[:-4] for c in week_cols]
    cur_week, _ = current_week_from_labels(weeks)
    return cur_week or ""


def _footer(week_full: str, variant: str = "normal") -> str:
    if variant == "supplement":
        return f'<div class="pfoot">{esc(week_full)} 文件快照 · 候选稿 · 完整数据截止未核实</div>'
    return f'<div class="pfoot">{esc(week_full)}文件快照｜数据完整时点未核实｜工作稿</div>'


def _page_header(page_no: int, title: str, subtitle: str = "", badge: str = "内部文件 · 仅供使用") -> str:
    sub = f'<span class="phead-sub">{esc(subtitle)}</span>' if subtitle else ""
    return f"""
    <div class="phead">
      <div class="phead-title">{esc(title)} {sub}</div>
      <div class="phead-badge">{esc(badge)}</div>
    </div>
    """


def _module_title(letter: str, text: str, cls: str = "navy") -> str:
    return f'<div class="mtitle mtitle-{cls}"><span class="mt-letter">{esc(letter)}</span> {esc(text)}</div>'


def _note(text: str) -> str:
    return f'<div class="note">{text}</div>'


def _kpi_strip(items) -> str:
    """items: [(value_html, label, color_class), ...]"""
    cells = []
    for val, label, cls in items:
        cells.append(f'<div class="kpi-cell kpi-{cls}"><div class="kpi-val">{val}</div>'
                      f'<div class="kpi-label">{esc(label)}</div></div>')
    return f'<div class="kpi-strip">{"".join(cells)}</div>'


# ======================================================================
# 第1页：全维度业绩分析仪表盘
# ======================================================================

def build_page1(ctx: dict, week_full: str) -> str:
    s1v = ctx["s1v"]
    date_str = ctx["date_str"]

    kpi_a = _kpi_strip([
        (fmt_m(s1v["issued_ape"]), "已批核APE（2026）", "navy"),
        (fmt_cnt(s1v["issued_cnt"]) + "件", "批核件数（2026）", "navy"),
        (fmt_m(s1v["full_gap"]), "剩余缺口", "red"),
    ])
    bar_full = min(100.0, s1v["full_rate"] * 100)
    bar_sun = min(100.0, s1v["sun_rate"] * 100)
    a_html = f"""
    <div class="card card-a">
      {_module_title("A", "年度目标达成率 — 2026 全业务&永明业务APE 达成状况", "navy")}
      <div class="a-body">
        <div class="a-left">
          <div class="a-bigpct">{fmt_pct(s1v['full_rate'])}</div>
          <div class="a-bigpct-label">2026 全业务目标达成率</div>
        </div>
        <div class="a-right">
          <div class="kpi-row-mini kpi-navy">{fmt_m(s1v['issued_ape'],0)}<span>已批核APE（2026）</span></div>
          <div class="kpi-row-mini kpi-navy">{fmt_cnt(s1v['issued_cnt'])}件<span>批核件数（2026）</span></div>
          <div class="kpi-row-mini kpi-red">{fmt_m(s1v['full_gap'],0)}<span>剩余缺口</span></div>
        </div>
      </div>
      <div class="a-progress">
        <div class="a-prow">
          <div class="a-plabel">全业务目标（{fmt_m(s1v['full_target'], 0)}）</div>
          <div class="a-pbar"><div class="a-pfill a-pfill-navy" style="width:{bar_full:.1f}%"></div></div>
          <div class="a-ppct">{fmt_pct(s1v['full_rate'])}</div>
        </div>
        <div class="a-pnote">已批{fmt_m(s1v['issued_ape'],0)} / 剩余差额{fmt_m(s1v['full_gap'],0)}</div>
        <div class="a-prow">
          <div class="a-plabel">永明业务目标（{fmt_m(s1v['sun_target'], 0)}）</div>
          <div class="a-pbar"><div class="a-pfill a-pfill-teal" style="width:{bar_sun:.1f}%"></div></div>
          <div class="a-ppct">{fmt_pct(s1v['sun_rate'])}</div>
        </div>
        <div class="a-pnote">已批{fmt_m(s1v['sun_achv'],0)} / 剩余差额{fmt_m(s1v['sun_gap'],0)}</div>
      </div>
      {_note(f"年度批核APE {fmt_m(s1v['issued_ape'],2)}，既有目标达成{fmt_pct(s1v['full_rate'])}；差额{fmt_m(s1v['full_gap'],2)}。")}
    </div>
    """

    stages = [
        ("批核（生效）", s1v["issued_ape"], s1v["issued_cnt"], "teal"),
        ("未批核", s1v["unbat_ape"], s1v["unbat_cnt"], "red"),
        ("待签", s1v["pend_ape"], s1v["pend_cnt"], "gold"),
        ("流失（2026）", s1v["lost_ape"], s1v["lost_cnt"], "muted"),
    ]
    stage_bar = "".join(
        f'<div class="bseg bseg-{cls}" style="width:{(ape/s1v["pipe_total"]*100 if s1v["pipe_total"] else 0):.2f}%"></div>'
        for _, ape, _, cls in stages
    )
    stage_cards = "".join(
        f'<div class="bcard bcard-{cls}"><div class="bcard-label">{esc(label)}</div>'
        f'<div class="bcard-val">{fmt_m(ape)}</div>'
        f'<div class="bcard-sub">{fmt_cnt(cnt)}件 | APE占比{fmt_pct(ape/s1v["pipe_total"] if s1v["pipe_total"] else 0)}</div></div>'
        for label, ape, cnt, cls in stages
    )
    b_html = f"""
    <div class="card card-b">
      {_module_title("B", "保单阶段分布 — 2026 批核/未批核/待签APE 构成分析", "red")}
      <div class="bbar">{stage_bar}</div>
      <div class="bgrid">{stage_cards}</div>
      {_note(f"四阶段APE占比分母含流失：{fmt_m(s1v['pipe_total'],2)}；未批/待签为跨年存量。")}
    </div>
    """

    bt = s1v["business_type"]
    bt_order = ["经代业务", "代理人业务", "KA业务"]
    c_rows = "".join(
        f'<div class="c-row"><div class="c-label">{esc(k)}</div>'
        f'<div class="c-bars">'
        f'<div class="c-bar c-bar-teal" style="width:{bt[k]["batch"]/1e6/ (max(bt[x]["batch"]+bt[x]["unbat"]+bt[x]["pend"] for x in bt_order)/1e6) * 100 if bt else 0:.1f}%"></div>'
        f'</div></div>'
        for k in bt_order if k in bt
    )
    c_html = f"""
    <div class="card card-c">
      {_module_title("C", "业务类型业绩 — 渠道批核/未批核/待签（APE in M）", "teal")}
      <div class="chartbox" style="height:200px;"><canvas id="p1_chartC"></canvas></div>
      {_note("类型图按经代、代理人及KA汇总三阶段；每个阶段的分类金额与全业务总量对齐。")}
    </div>
    """

    table_rows = "".join(
        f'<tr><td>{esc(r["month"])}</td><td>{r["预约APE"]/1e6:.2f}</td><td>{fmt_cnt(r["预约件数"])}</td>'
        f'<td>{r["签单APE"]/1e6:.2f}</td><td>{fmt_cnt(r["签单件数"])}</td>'
        f'<td>{r["批核APE"]/1e6:.2f}</td><td>{fmt_cnt(r["批核件数"])}</td></tr>'
        for r in s1v["monthly_table"]
    )
    d_html = f"""
    <div class="card card-d card-full">
      {_module_title("D", "预约/签单/批核月度趋势三线图（APE in M）", "teal")}
      <div class="d-body">
        <div class="d-chart chartbox" style="height:440px;"><canvas id="p1_chartD"></canvas></div>
        <div class="d-table">
          <div class="d-table-title">2026月度明细（预约/签单含流失；M港元）</div>
          <div class="tablewrap"><table class="dtable">
            <thead><tr><th>月份</th><th>预约M</th><th>预约件</th><th>签单M</th><th>签单件</th><th>批核M</th><th>批核件</th></tr></thead>
            <tbody>{table_rows}</tbody>
          </table></div>
        </div>
      </div>
      {_note("2025使用0404已核历史版本；2026来自本次文件。2026-10未完结，预约/签单月表含流失。")}
    </div>
    """

    return f"""
    <section class="page" data-page="1">
      {_page_header(1, "全维度业绩分析仪表盘", f"{date_str} | {week_full}文件快照")}
      <div class="grid3">{a_html}{b_html}{c_html}</div>
      {d_html}
      {_footer(week_full)}
    </section>
    """


# ======================================================================
# 第2页：月度效能深析
# ======================================================================

def build_page2(ctx: dict, week_full: str) -> str:
    """F模块"当月未完结；无预测值"——跟build_s1_view()里给multiview_dashboard用的
    forecast_chart（含Oct-Dec人工预测值）不同，Mark这页明确不做预测，只画已发生的
    2026月份批核APE柱状图，最后一个月（数据覆盖到的最新2026月份）标"当月未完结"。
    E模块三张条形图(预约/签单/批核)的环比%：首月(最早月份)标"跨年分列"（对比基准在
    上一年度、本图未展示，不计算），末月(进行中月份)标"当月进行中"（不据此评价全月
    升降），中间月份按月环比=(本月-上月)/上月，复用multiview_dashboard.wow_pct()。"""
    s1v = ctx["s1v"]
    months_2026 = [r for r in s1v["monthly_table"] if r["month"].startswith("26-")]
    in_progress_label = months_2026[-1]["month"] if months_2026 else None

    def _bar_block(letter_sub, metric_ape, metric_cnt, color_cls):
        rows_desc = list(reversed(months_2026))
        items = []
        for i, r in enumerate(rows_desc):
            idx_fwd = len(months_2026) - 1 - i
            if idx_fwd == len(months_2026) - 1:
                wow_html = '<span class="wow-note">当月进行中</span>'
            elif idx_fwd == 0:
                wow_html = '<span class="wow-note">跨年分列</span>'
            else:
                prev = months_2026[idx_fwd - 1]
                w = wow_pct(r[metric_ape], prev[metric_ape])
                wow_html = _wow_html(w)
            items.append(
                f'<div class="ebar-row"><div class="ebar-m">{esc(r["month"][-3:])}</div>'
                f'<div class="ebar-track"><div class="ebar-fill ebar-{color_cls}" '
                f'style="width:{(r[metric_ape]/1e6)/( max(x[metric_ape] for x in months_2026)/1e6)*100 if months_2026 else 0:.1f}%">'
                f'<span class="ebar-val">APE {r[metric_ape]/1e6:.1f}M / {fmt_cnt(r[metric_cnt])}件</span></div></div>'
                f'<div class="ebar-wow">{wow_html}</div></div>'
            )
        return "".join(items)

    e_pred = f"""
    <div class="card card-e">{_module_title("E", "预约 Appointment | APE(M) 件数", "navy")}
      <div class="ebar-head"><div></div><div></div><div>环比</div></div>
      {_bar_block("预约", "预约APE", "预约件数", "tan")}</div>
    """
    e_sign = f"""
    <div class="card card-e">{_module_title("E", "签单 Signed | APE(M) 件数", "navy")}
      <div class="ebar-head"><div></div><div></div><div>环比</div></div>
      {_bar_block("签单", "签单APE", "签单件数", "wheat")}</div>
    """
    e_appr = f"""
    <div class="card card-e">{_module_title("E", "批核 Approved | APE(M) 件数", "navy")}
      <div class="ebar-head"><div></div><div></div><div>环比</div></div>
      {_bar_block("批核", "批核APE", "批核件数", "mint")}</div>
    """

    remaining = s1v["forecast_pace"]["remaining_months"]
    pace = s1v["forecast_pace"]["pace_per_month"]
    f_html = f"""
    <div class="card card-f">
      {_module_title("F", "当年批核APE月度走势 | 当月未完结；无预测值", "navy")}
      <div class="chartbox" style="height:190px;"><canvas id="p2_chartF"></canvas></div>
      {_note(f"本页按事件自然月统计；预约/签单含流失。2026-{in_progress_label[-3:] if in_progress_label else ''}进行中，不据此评价全月升降。")}
    </div>
    """
    kpi_html = f"""
    <div class="card card-kpi4">
      <div class="kpi4-row">
        <div class="kpi4-cell kpi4-navy"><div class="kpi4-val">{fmt_m(s1v['issued_ape'])}</div>
          <div class="kpi4-label">2026累计批核至当前快照</div><div class="kpi4-sub">{fmt_pct(s1v['full_rate'])} 达成率</div></div>
        <div class="kpi4-cell kpi4-red"><div class="kpi4-val">{fmt_m(s1v['full_gap'],0)}</div>
          <div class="kpi4-label">剩余目标缺口</div><div class="kpi4-sub">{fmt_pct(1-s1v['full_rate'])} 目标剩余</div></div>
        <div class="kpi4-cell kpi4-gold"><div class="kpi4-val">{fmt_m(months_2026[-1]['批核APE'],2) if months_2026 else '—'}</div>
          <div class="kpi4-label">2026-{in_progress_label[-3:] if in_progress_label else ''}批核</div><div class="kpi4-sub">当月未完结，不作全月结论</div></div>
        <div class="kpi4-cell kpi4-brown"><div class="kpi4-val">{fmt_m(s1v['unbat_ape']+s1v['pend_ape'],2)}</div>
          <div class="kpi4-label">未批+待签存量</div><div class="kpi4-sub">不作为预计兑现额</div></div>
      </div>
      {_note(f"年度批核APE {fmt_m(s1v['issued_ape'],2)}，既有目标达成{fmt_pct(s1v['full_rate'])}；差额{fmt_m(s1v['full_gap'],2)}。")}
    </div>
    """

    return f"""
    <section class="page" data-page="2">
      {_page_header(2, "月度效能深析", "预约、签单、批核及年度差额")}
      <div class="p2-note-top">本页按事件自然月统计；预约/签单含流失。{in_progress_label or ''}进行中，不据此评价全月升降。</div>
      <div class="grid3">{e_pred}{e_sign}{e_appr}</div>
      <div class="grid2-f">{f_html}{kpi_html}</div>
      {_footer(week_full)}
    </section>
    """


def _wow_html(w):
    if w is None:
        return '<span class="wow-flat">—</span>'
    cls = "up" if w > 0 else ("down" if w < 0 else "flat")
    sign = "+" if w > 0 else ""
    return f'<span class="wow-{cls}">{sign}{w*100:.1f}%</span>'


# ======================================================================
# 第3页：永明业绩汇报
# ======================================================================

def build_page3(ctx: dict, week_full: str) -> str:
    sunv = ctx["sunv"]
    pipe = ctx["sun_pipe"]
    entity_table = ctx["sun_entity_table"]
    product = ctx["sun_product"]
    in_progress = ctx["sun_in_progress_month"]

    stage_total = sunv["sun_achv"] + pipe["unbat_ape"] + pipe["pend_ape"]
    kpi_html = f"""
    <div class="kpi-strip4">
      <div class="kpi-cell kpi-teal"><div class="kpi-val">{fmt_m(sunv['sun_achv'])}</div>
        <div class="kpi-label">永明批核APE</div><div class="kpi-sub">{fmt_cnt(ctx['sun_batch_cnt'])}件 | 达成率{fmt_pct(sunv['sun_rate'])}</div></div>
      <div class="kpi-cell kpi-navy"><div class="kpi-val">{fmt_pct(sunv['sun_rate'])}</div>
        <div class="kpi-label">永明年度达成率</div><div class="kpi-sub">目标{fmt_m(sunv['sun_target'],1)} | 差额{fmt_m(sunv['sun_gap'],1)}</div></div>
      <div class="kpi-cell kpi-red"><div class="kpi-val">{fmt_m(pipe['unbat_ape'])}</div>
        <div class="kpi-label">永明未批核APE</div><div class="kpi-sub">{fmt_cnt(pipe['unbat_cnt'])}件 | 件均{fmt_wan(pipe['unbat_avg'])}</div></div>
      <div class="kpi-cell kpi-gold"><div class="kpi-val">{fmt_m(pipe['pend_ape'])}</div>
        <div class="kpi-label">永明待签APE</div><div class="kpi-sub">{fmt_cnt(pipe['pend_cnt'])}件 | 件均{fmt_wan(pipe['pend_avg'])}</div></div>
    </div>
    """

    h_html = f"""
    <div class="card card-h card-full">
      {_module_title("H", "永明月度预约/签单/批核APE 趋势", "navy")}
      <div class="chartbox" style="height:170px;"><canvas id="p3_chartH"></canvas></div>
      {_note(f"永明{in_progress}批核{fmt_m(entity_table['last_month_batch'],2)}；当月未完结。产品排名采用当年签单群体，见补充明细。")}
    </div>
    """

    month_cols = "".join(f"<th>{esc(m)}批核</th>" for m in entity_table["months"])
    entity_rows = ""
    for r in entity_table["rows"]:
        cells = "".join(f"<td>{num(r[m])/1e6:.2f}</td>" for m in [k for k in r if k not in ("entity", "未批核", "当月递交")])
        cls = ' class="total-row"' if r["entity"] == "内部合计" else ""
        entity_rows += (f'<tr{cls}><td>{esc(r["entity"])}</td>{cells}'
                         f'<td>{r["未批核"]/1e6:.2f}</td><td>{r["当月递交"]/1e6:.2f}</td></tr>')
    g_html = f"""
    <div class="card card-g card-full">
      {_module_title("G", "永明内部牌照明细 | APE百万港元；本项目已归一化issuing_entity简繁别名（原始名称不逐字保留，见页脚说明）", "navy")}
      <div class="kpi-mini-row">
        <div class="kpi-mini">永明内部阶段合计 <b>{fmt_m(stage_total)}</b><span>中台内批核＋未批＋待签；不含外部供数</span></div>
      </div>
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>中台牌照名称（已归一化）</th>{month_cols}<th>未批核</th><th>当月递交</th></tr></thead>
        <tbody>{entity_rows}</tbody>
      </table></div>
      {_note("本项目cleaner.py已把简繁体写法的同一实体合并（如怡泰/九富/众和恒富等5对），"
             "跟Mark原文'保留源名称、不擅自合并'的展示方式不同——这是v0.19.0的既定修正，"
             "合并前后总记录数/总APE/总保费三项大盘指标精确不变，已独立验证。")}
    </div>
    """

    top10_rows = "".join(
        f'<tr><td>{esc(r["产品名称"])}</td><td>{esc(r["年期"])}</td><td>{esc(r["首年折扣"])}</td>'
        f'<td>{fmt_cnt(r["件数"])}</td><td>{r["APE"]/1e6:.2f}</td></tr>'
        for r in product["top10"]
    )
    i_html = f"""
    <div class="card card-i card-full">
      {_module_title("I", "永明2026年签单产品排名", "navy")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>产品（源名）</th><th>年期</th><th>折扣</th><th>件数</th><th>APE M</th></tr></thead>
        <tbody>{top10_rows}
        <tr class="total-row"><td colspan="3">TOP10合计</td><td>{fmt_cnt(sum(r['件数'] for r in product['top10']))}</td><td>{sum(r['APE'] for r in product['top10'])/1e6:.2f}</td></tr>
        <tr><td colspan="3">其他</td><td>{fmt_cnt(product['rest_cnt'])}</td><td>{product['rest_ape']/1e6:.2f}</td></tr>
        <tr class="total-row"><td colspan="3">总体</td><td>{fmt_cnt(product['total_cnt'])}</td><td>{product['total_ape']/1e6:.2f}</td></tr>
        </tbody>
      </table></div>
      {_note("联合主键=产品名称+年期+首年折扣(SQ_rate标准化)；SQ_rate缺失的记录计入'未提供'档"
             "（跟S4产品TOP20把缺失整体排除的口径不同，本页按Mark原文口径独立计算）；"
             "sign_year=2026，排除流失类(不含拒保)。")}
    </div>
    """

    return f"""
    <section class="page" data-page="3">
      {_page_header(3, "永明业绩汇报", "Sun Life")}
      {kpi_html}
      <div class="grid2">{h_html}{g_html}</div>
      {i_html}
      {_footer(week_full)}
    </section>
    """



# ======================================================================
# 第4页：业务端视角①
# ======================================================================

def build_page4(ctx: dict, week_full: str) -> str:
    s1v, s2v = ctx["s1v"], ctx["s2v"]
    sb = s2v["segment_bars"]

    kpi_html = _kpi_strip([
        (fmt_pct(s1v["full_rate"]), "全业务达成率", "gold"),
        (fmt_m(s1v["issued_ape"], 0), "已批核APE", "navy"),
        (fmt_m(s1v["full_target"], 0), "年度目标", "navy"),
        (fmt_m(s1v["full_gap"], 0), "剩余缺口", "red"),
        (fmt_cnt(s1v["issued_cnt"]) + "件", "已批核件数", "navy"),
    ])

    bubbles = []
    for i, seg in enumerate(sb["labels"]):
        bubbles.append({
            "x": sb["target"][i] / 1e6, "y": sb["rate"][i] * 100,
            "r": max(6, (sb["issued"][i] / 1e6) ** 0.5 * 2.2),
            "label": seg,
        })
    g_html = f"""
    <div class="card card-g">
      {_module_title("G", "达成率×目标规模×件数 — 业务线战略象限气泡图", "navy")}
      <div class="chartbox" style="height:230px;"><canvas id="p4_chartG"></canvas></div>
      {_note("气泡位置：横轴目标、纵轴批核达成率；大小表示APE规模。同行实际含MGA，与既有目标范围存在差异。")}
    </div>
    """

    wf_order = sorted(range(len(sb["labels"])), key=lambda i: sb["issued"][i], reverse=True)
    unbat_total, pend_total = ctx["s2_unbat_total"], ctx["s2_pend_total"]
    waterfall_items = [("年度目标", s2v["target_total"], "base")]
    for i in wf_order:
        if sb["issued"][i] <= 0:
            continue
        waterfall_items.append((f"{sb['labels'][i]}批核", -sb["issued"][i], "seg"))
    waterfall_items.append(("未批核", -unbat_total, "unbat"))
    waterfall_items.append(("待签", -pend_total, "pend"))
    final_gap = s1v["full_gap"] - unbat_total - pend_total
    waterfall_items.append(("扣在途后差额", final_gap, "final"))
    h_html = f"""
    <div class="card card-h">
      {_module_title("H", "全业务目标缺口分解 — Gap Waterfall（APE in M）", "navy")}
      <div class="chartbox" style="height:230px;"><canvas id="p4_chartH"></canvas></div>
      {_note(f"年度差额{fmt_m(s1v['full_gap'],2)}；在途存量不等于未来可兑现业绩")}
    </div>
    """

    mbs = s2v["monthly_by_segment"]
    cells = "".join(
        f'<div class="i-cell"><div class="i-cell-title">{esc(seg)}</div>'
        f'<div class="chartbox" style="height:110px;"><canvas id="p4_seg_{i}"></canvas></div></div>'
        for i, seg in enumerate(sb["labels"])
    )
    ifa_unbat = sb["unbat"][sb["labels"].index("IFA业务")] if "IFA业务" in sb["labels"] else 0.0
    i_html = f"""
    <div class="card card-i">
      {_module_title("I", "业务线月度三线趋势 — 预约/签单/批核（APE in M）", "navy")}
      <div class="i-grid">{cells}</div>
      {_note(f"八条业务线均列示；IFA年度批核为0，未批{fmt_m(ifa_unbat,2)}。趋势按事件自然月。")}
    </div>
    """

    return f"""
    <section class="page" data-page="4">
      {_page_header(4, "业务端视角仪表盘", "Sales & Channel View")}
      {kpi_html}
      <div class="grid3-45">{g_html}{h_html}{i_html}</div>
      {_footer(week_full)}
    </section>
    """


# ======================================================================
# 第5页：业务端视角②
# ======================================================================

def build_page5(ctx: dict, week_full: str) -> str:
    s1v, s2v = ctx["s1v"], ctx["s2v"]
    sb = s2v["segment_bars"]
    order = sorted(range(len(sb["labels"])),
                    key=lambda i: sb["issued"][i] + sb["unbat"][i] + sb["pend"][i])

    j_rows = []
    for i in order:
        total = sb["issued"][i] + sb["unbat"][i] + sb["pend"][i]
        pct_b = sb["issued"][i] / total if total else 0
        pct_u = sb["unbat"][i] / total if total else 0
        j_rows.append(f"""
        <div class="j-row">
          <div class="j-label">{esc(sb['labels'][i])}<br><span class="j-total">合计{fmt_m(total,2)}</span></div>
          <div class="j-bar">
            <div class="j-seg j-seg-teal" style="width:{pct_b*100:.1f}%">{f'{pct_b*100:.0f}%' if pct_b>0.08 else ''}</div>
            <div class="j-seg j-seg-gold" style="width:{pct_u*100:.1f}%">{f'{pct_u*100:.0f}%' if pct_u>0.08 else ''}</div>
            <div class="j-seg j-seg-blue" style="width:{(1-pct_b-pct_u)*100:.1f}%"></div>
          </div>
          <div class="j-vals">{sb['issued'][i]/1e6:.2f}▌{sb['unbat'][i]/1e6:.2f}▌{sb['pend'][i]/1e6:.2f}</div>
        </div>
        """)
    j_html = f"""
    <div class="card card-j card-tall">
      {_module_title("J", "保单阶段构成（100%堆叠）— 各业务线", "red")}
      <div class="j-legend"><span class="dot dot-teal"></span>已批核 <span class="dot dot-gold"></span>未批核 <span class="dot dot-blue"></span>待签</div>
      {"".join(j_rows)}
      {_note(f"未批核{fmt_cnt(ctx['s2_unbat_cnt'])}件、{fmt_m(ctx['s2_unbat_total'],2)}；"
             f"待签{fmt_cnt(ctx['s2_pend_cnt'])}件、{fmt_m(ctx['s2_pend_total'],2)}。跨年存量未提供承诺兑现时间。")}
    </div>
    """

    pipe3_total = s1v["issued_ape"] + s1v["unbat_ape"] + s1v["pend_ape"]
    k_cells = []
    for label, ape, cnt, cls in [
        ("已批核", s1v["issued_ape"], s1v["issued_cnt"], "teal"),
        ("未批核", s1v["unbat_ape"], s1v["unbat_cnt"], "gold"),
        ("待签", s1v["pend_ape"], s1v["pend_cnt"], "blue"),
    ]:
        pct = ape / pipe3_total if pipe3_total else 0
        k_cells.append(f"""
        <div class="k-cell k-cell-{cls}">
          <div class="k-cell-label">{esc(label)}</div>
          <div class="k-cell-val">{fmt_m(ape)}</div>
          <div class="k-cell-sub">{fmt_cnt(cnt)}件 {fmt_pct(pct)}</div>
          <div class="k-cell-bar"><div class="k-cell-fill" style="width:{pct*100:.1f}%"></div></div>
          <div class="k-cell-sub2">{fmt_pct(pct)} 占三阶段APE</div>
        </div>
        """)
    k_html = f"""
    <div class="card card-k">
      {_module_title("K", "保单总量构成 — 甜甜圈&阶段KPI", "red")}
      <div class="k-body">
        <div class="chartbox" style="height:170px;"><canvas id="p5_chartK"></canvas></div>
        <div class="k-cells">{"".join(k_cells)}</div>
      </div>
      {_note(f"三阶段APE总量{fmt_m(pipe3_total,2)}，不含流失；占比按APE金额计算。")}
    </div>
    """

    l_order = sorted(range(len(sb["labels"])), key=lambda i: sb["target"][i])
    l_html = f"""
    <div class="card card-l card-full">
      {_module_title("L", "目标vs已批核/未批核/待签APE — 各业务线对比（APE in M）", "teal")}
      <div class="chartbox" style="height:190px;"><canvas id="p5_chartL"></canvas></div>
      {_note("灰色表示目标减批核、未批及待签后的正差额；在途尚未兑现，不能作为达成预测。")}
    </div>
    """

    return f"""
    <section class="page" data-page="5">
      {_page_header(5, "业务端视角仪表盘", "Sales & Channel View")}
      <div class="grid2-jk">{j_html}{k_html}</div>
      {l_html}
      {_footer(week_full)}
    </section>
    """


# ======================================================================
# 第6页：执行管理端①
# ======================================================================

def build_page6(ctx: dict, week_full: str) -> str:
    s3v = ctx["s3v"]
    stages = [("预约", "steel"), ("签单", "teal"), ("递交", "gold"), ("批核", "navy")]
    max_ape = max(s3v["stage_totals"][s]["ape"] for s, _ in stages)
    m_rows = "".join(
        f'<div class="m-row"><div class="m-label">{esc(s)}</div>'
        f'<div class="m-track"><div class="m-fill m-fill-{c}" style="width:{s3v["stage_totals"][s]["ape"]/max_ape*100:.1f}%">'
        f'<span>{fmt_m(s3v["stage_totals"][s]["ape"])}</span></div>'
        f'<span class="m-cnt">{fmt_cnt(s3v["stage_totals"][s]["cnt"])}件</span></div></div>'
        for s, c in stages
    )
    m_html = f"""
    <div class="card card-m">
      {_module_title("M", f"各环节业务周累计 W01–{s3v['cur_week']}（分别按事件日期）", "navy")}
      {m_rows}
      {_note("业务周年初边界与自然年不同；各环节不是同一批保单，不能据此计算转化率。")}
    </div>
    """
    n_html = f"""
    <div class="card card-n">
      {_module_title("N", "周度APE波动趋势（预约/签单/递交/批核）", "navy")}
      <div class="chartbox" style="height:210px;"><canvas id="p6_chartN"></canvas></div>
      {_note(f"四事件本周发生额见快报及补充页；{week_full}完整性未核实，不解释为两期快照净增长。")}
    </div>
    """

    ws = s3v["weekly_snapshot"]
    o_rows = ""
    for label, cls in [("预约", "steel"), ("签单", "teal"), ("批核", "navy")]:
        snap = ws[label]
        o_rows += (f'<tr><td><span class="pill pill-{cls}">{esc(label)}</span></td>'
                   f'<td>{fmt_m(snap["ape"])}</td><td>{fmt_cnt(snap["cnt"])}件</td>'
                   f'<td>{_wow_tag(snap["wow"], s3v["cur_week"])}</td></tr>')
    o_rows += (f'<tr><td><span class="pill pill-gold">未批核</span></td>'
               f'<td>{fmt_m(ctx["s1v"]["unbat_ape"])}</td><td>{fmt_cnt(ctx["s1v"]["unbat_cnt"])}件</td>'
               f'<td>待签及未批存量</td></tr>')
    o_rows += (f'<tr><td><span class="pill pill-purple">待签</span></td>'
               f'<td>{fmt_m(ctx["s1v"]["pend_ape"])}</td><td>{fmt_cnt(ctx["s1v"]["pend_cnt"])}件</td>'
               f'<td>→ 尽快推进</td></tr>')
    o_html = f"""
    <div class="card card-o">
      {_module_title("O", f"本周业绩快报 — {s3v['cur_week']}（2026）", "navy")}
      <table class="dtable otable">
        <thead><tr><th>指标</th><th>APE（M）</th><th>件数</th><th>状态</th></tr></thead>
        <tbody>{o_rows}</tbody>
      </table>
      {_note("当周对比来自同一快照中的相邻业务周；补录、回退与重分类影响待双快照支持。")}
    </div>
    """

    ka = ctx["ka_rank_p6"]
    p_rows = "".join(
        f'<tr><td>{esc(r["ka"])}</td><td>{r["batch"]/1e6:.2f}</td><td>{fmt_cnt(r["batch_c"])}</td>'
        f'<td>{r["unbat"]/1e6:.2f}</td><td>{fmt_cnt(r["unbat_c"])}</td>'
        f'<td>{r["pend"]/1e6:.2f}</td><td>{fmt_cnt(r["pend_c"])}</td>'
        f'<td>{(r["batch"]+r["unbat"]+r["pend"])/1e6:.2f}</td><td>{fmt_cnt(r["batch_c"]+r["unbat_c"]+r["pend_c"])}</td></tr>'
        for r in ka["top"]
    )
    def _tot_row(label, t, cls=""):
        return (f'<tr class="{cls}"><td>{label}</td><td>{t["batch"]/1e6:.2f}</td><td>{fmt_cnt(t["batch_c"])}</td>'
                f'<td>{t["unbat"]/1e6:.2f}</td><td>{fmt_cnt(t["unbat_c"])}</td>'
                f'<td>{t["pend"]/1e6:.2f}</td><td>{fmt_cnt(t["pend_c"])}</td>'
                f'<td>{(t["batch"]+t["unbat"]+t["pend"])/1e6:.2f}</td><td>{fmt_cnt(t["batch_c"]+t["unbat_c"]+t["pend_c"])}</td></tr>')
    p_html = f"""
    <div class="card card-p">
      {_module_title("P", "KEY ACCOUNT TOP10 排名", "purple")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>渠道</th><th>批核M</th><th>件</th><th>未批M</th><th>件</th><th>待签M</th><th>件</th><th>阶段合计M</th><th>件</th></tr></thead>
        <tbody>{p_rows}
        {_tot_row("TOP10合计", ka["top10_total"] if "top10_total" in ka else _ka_totals(ka["top"]), "total-row")}
        {_tot_row("其他", ka["rest"])}
        {_tot_row("总体", ka["total"], "total-row")}
        </tbody>
      </table></div>
      {_note("按年度批核APE选TOP10；其他包含其余渠道和仅在途渠道，总体覆盖三阶段全部记录。")}
    </div>
    """

    return f"""
    <section class="page" data-page="6">
      {_page_header(6, "执行管理端分析仪表盘", "Execution Management View")}
      <div class="grid2">{m_html}{n_html}</div>
      <div class="grid2-op">{o_html}{p_html}</div>
      {_footer(week_full)}
    </section>
    """


def _ka_totals(lst):
    return {k: sum(r[k] for r in lst) for k in ("batch", "batch_c", "unbat", "unbat_c", "pend", "pend_c")}


def _wow_tag(w, cur_week):
    if w is None:
        return "—"
    sign = "+" if w > 0 else ""
    return f"较上周 {sign}{w*100:.1f}%"


# ======================================================================
# 第7页：执行管理端②+签批时效
# ======================================================================

def build_page7(ctx: dict, week_full: str) -> str:
    te = ctx["timeliness"]
    seg_rows = ""
    for r in te["segment_rows"]:
        cls = ' class="total-row"' if r["业务细分"] == "合计" else ""
        if r["件数"] == 0:
            seg_rows += (f'<tr{cls}><td>{esc(r["业务细分"])}</td><td>0</td>'
                         f'<td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>')
        else:
            seg_rows += (f'<tr{cls}><td>{esc(r["业务细分"])}</td><td>{fmt_cnt(r["件数"])}</td>'
                         f'<td>{r["件均APE"]/1e4:.0f}</td><td>{r["平均时效"]:.0f}</td>'
                         f'<td>{r["P90时效"]:.0f}</td><td>{r["中位时效"]:.0f}</td><td>{fmt_cnt(r["最长时效"])}</td></tr>')
    t_html = f"""
    <div class="card card-t card-full">
      {_module_title("T", "签批时效综合分析 — 业务线时效&分档分布", "purple")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>业务线</th><th>件数</th><th>件均万</th><th>平均天</th><th>P90天</th><th>中位天</th><th>最长天</th></tr></thead>
        <tbody>{seg_rows}</tbody>
      </table></div>
      {_note(f"有效签批样本{fmt_cnt(te['total_valid'])}件；排除{te['excluded_count']}件。"
             "排除规则：签批时效(issue_date-sign_date)为负值的记录视为脏数据，不计入时效统计分母"
             "（复用s3_execution_view.py既有的TAT&lt;0排除规则）。")}
    </div>
    """

    bucket_rows = "".join(
        f'<tr><td>{esc(r["分档"])}</td><td>{fmt_cnt(r["件数"])}</td><td>{fmt_pct(r["占比"])}</td></tr>'
        for r in te["bucket_rows"]
    )
    bucket_html = f"""
    <div class="card card-bucket card-full">
      {_module_title("新增", "签批时效分档分布", "navy")}
      <div class="bucket-body">
        <div class="chartbox" style="height:200px;"><canvas id="p7_chartBucket"></canvas></div>
        <div class="tablewrap"><table class="dtable">
          <thead><tr><th>签批用时</th><th>件数</th><th>占有效样本</th></tr></thead>
          <tbody>{bucket_rows}
          <tr class="total-row"><td>有效总体</td><td>{fmt_cnt(te['total_valid'])}</td><td>100.0%</td></tr>
          <tr><td>排除样本</td><td>{fmt_cnt(te['excluded_count'])}</td><td>不入分母</td></tr>
          </tbody>
        </table></div>
      </div>
      {_note(f"≤60天：{fmt_cnt(te['sla60_count'])}/{fmt_cnt(te['total_valid'])} = {fmt_pct(te['sla60_rate'])}。"
             "签批日期缺失或为负者不入分母。")}
    </div>
    """

    return f"""
    <section class="page" data-page="7">
      {_page_header(7, "执行管理端分析仪表盘", "Execution Management View")}
      {t_html}
      {bucket_html}
      {_footer(week_full)}
    </section>
    """


# ======================================================================
# 第8页：同行业绩①
# ======================================================================

def build_page8(ctx: dict, week_full: str) -> str:
    peerv = ctx["peerv"]
    rb = peerv["referrer_bar"]
    u_html = f"""
    <div class="card card-u card-full">
      {_module_title("U", "同行推荐人分析", "navy")}
      <div class="chartbox" style="height:230px;"><canvas id="p8_chartU"></canvas></div>
      {_note("推荐人图按源referral_code分组；左表和下图按key_account分组，两个维度不互相替代。")}
    </div>
    """

    ka = ctx["ka_rank_p8"]
    v_rows = "".join(
        f'<tr><td>{esc(r["ka"])}</td><td>{r["batch"]/1e6:.2f}</td><td>{fmt_cnt(r["batch_c"])}</td>'
        f'<td>{r["unbat"]/1e6:.2f}</td><td>{fmt_cnt(r["unbat_c"])}</td>'
        f'<td>{r["pend"]/1e6:.2f}</td><td>{fmt_cnt(r["pend_c"])}</td>'
        f'<td>{(r["batch"]+r["unbat"]+r["pend"])/1e6:.2f}</td><td>{fmt_cnt(r["batch_c"]+r["unbat_c"]+r["pend_c"])}</td></tr>'
        for r in ka["top"]
    )
    v_html = f"""
    <div class="card card-v card-full">
      {_module_title("V", "同行TOP10 KEY ACCOUNT分析", "navy")}
      <div class="kpi-mini-row">
        <div class="kpi-mini">同行2026批核APE <b>{fmt_m(peerv['issued_ape'])}</b><span>{fmt_cnt(peerv['issued_cnt'])}件 | 件均{fmt_wan(peerv['issued_ape']/peerv['issued_cnt'] if peerv['issued_cnt'] else 0)}</span></div>
        <div class="kpi-mini">同行未批核APE <b>{fmt_m(peerv['unbat_ape'])}</b><span>{fmt_cnt(peerv['unbat_cnt'])}件 | 件均{fmt_wan(peerv['unbat_ape']/peerv['unbat_cnt'] if peerv['unbat_cnt'] else 0)}</span></div>
        <div class="kpi-mini">同行待签APE <b>{fmt_m(peerv['pend_ape'])}</b><span>{fmt_cnt(peerv['pend_cnt'])}件 | 件均{fmt_wan(peerv['pend_ape']/peerv['pend_cnt'] if peerv['pend_cnt'] else 0)}</span></div>
      </div>
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>渠道</th><th>批核M</th><th>件</th><th>未批M</th><th>件</th><th>待签M</th><th>件</th><th>阶段合计M</th><th>件</th></tr></thead>
        <tbody>{v_rows}
        {_v_tot_row("TOP10合计", ka["top"], "total-row")}
        {_v_tot_row2("其他", ka["rest"])}
        {_v_tot_row2("总体", ka["total"], "total-row")}
        </tbody>
      </table></div>
    </div>
    """

    return f"""
    <section class="page" data-page="8">
      {_page_header(8, "同行业绩分析仪表盘", "Pipeline & Approval View")}
      {u_html}
      {v_html}
      {_footer(week_full)}
    </section>
    """


def _v_tot_row(label, lst, cls=""):
    t = _ka_totals(lst)
    return _v_tot_row2(label, t, cls)


def _v_tot_row2(label, t, cls=""):
    return (f'<tr class="{cls}"><td>{label}</td><td>{t["batch"]/1e6:.2f}</td><td>{fmt_cnt(t["batch_c"])}</td>'
            f'<td>{t["unbat"]/1e6:.2f}</td><td>{fmt_cnt(t["unbat_c"])}</td>'
            f'<td>{t["pend"]/1e6:.2f}</td><td>{fmt_cnt(t["pend_c"])}</td>'
            f'<td>{(t["batch"]+t["unbat"]+t["pend"])/1e6:.2f}</td><td>{fmt_cnt(t["batch_c"]+t["unbat_c"]+t["pend_c"])}</td></tr>')


# ======================================================================
# 第9页：同行业绩②
# ======================================================================

def build_page9(ctx: dict, week_full: str) -> str:
    peerv = ctx["peerv"]
    ws = peerv["weekly_snapshot"]
    wd = peerv["weekly_detail"]

    kpi_html = f"""
    <div class="kpi-strip3">
      <div class="kpi-cell kpi-steel"><div class="kpi-val">{fmt_m(ws['预约']['ape'])}</div>
        <div class="kpi-label">同行{peerv['cur_week']}预约</div><div class="kpi-sub">{fmt_cnt(ws['预约']['cnt'])}件 | 件均{fmt_wan(ws['预约']['ape']/ws['预约']['cnt'] if ws['预约']['cnt'] else 0)}</div></div>
      <div class="kpi-cell kpi-teal"><div class="kpi-val">{fmt_m(ws['签单']['ape'])}</div>
        <div class="kpi-label">同行{peerv['cur_week']}签单</div><div class="kpi-sub">{fmt_cnt(ws['签单']['cnt'])}件 | 件均{fmt_wan(ws['签单']['ape']/ws['签单']['cnt'] if ws['签单']['cnt'] else 0)}</div></div>
      <div class="kpi-cell kpi-navy"><div class="kpi-val">{fmt_m(ws['批核']['ape'])}</div>
        <div class="kpi-label">同行{peerv['cur_week']}批核</div><div class="kpi-sub">{fmt_cnt(ws['批核']['cnt'])}件 | 件均{fmt_wan(ws['批核']['ape']/ws['批核']['cnt'] if ws['批核']['cnt'] else 0)}</div></div>
    </div>
    """

    # Mark原文Y表只展示本周有实际贡献的渠道，且观察到止于10行（第11名"万城保险"
    # 签单0.017M被截断未显示）——用"非零渠道TOP10"口径复刻，不是任意截断。
    nonzero_rows = [r for r in wd["rows"] if any(r["vals"].values())]
    y_rows = "".join(
        f'<tr><td>{esc(r["ka"])}</td><td>{r["vals"]["预约"]/1e6:.2f}M</td>'
        f'<td>{r["vals"]["签单"]/1e6:.2f}M</td><td>{r["vals"]["批核"]/1e6:.2f}M</td></tr>'
        for r in nonzero_rows[:10]
    )
    y_html = f"""
    <div class="card card-y">
      {_module_title("Y", f"{peerv['cur_week']} 本周快报 | 同行", "navy")}
      <table class="dtable">
        <thead><tr><th>KEY ACCOUNT</th><th>预约(M)</th><th>签单(M)</th><th>批核(M)</th></tr></thead>
        <tbody>{y_rows}
        <tr class="total-row"><td>合计</td><td>{wd['total']['预约']/1e6:.2f}M</td><td>{wd['total']['签单']/1e6:.2f}M</td><td>{wd['total']['批核']/1e6:.2f}M</td></tr>
        </tbody>
      </table>
      {_note(f"同行{peerv['cur_week']}批核{fmt_m(ws['批核']['ape'],2)}；完整性待核。")}
    </div>
    """

    x_html = f"""
    <div class="card card-x">
      {_module_title("X", f"W01–{peerv['cur_week']} 同行预约/签单/批核趋势（M）", "navy")}
      <div class="chartbox" style="height:200px;"><canvas id="p9_chartX"></canvas></div>
    </div>
    """

    cal_monthly = ctx["peer_calendar_monthly"]
    w_rows = "".join(
        f'<tr><td>{esc(r["month"])}</td><td>{r["预约APE"]/1e6:.2f}</td><td>{fmt_cnt(r["预约件数"])}</td>'
        f'<td>{r["签单APE"]/1e6:.2f}</td><td>{fmt_cnt(r["签单件数"])}</td>'
        f'<td>{r["批核APE"]/1e6:.2f}</td><td>{fmt_cnt(r["批核件数"])}</td></tr>'
        for r in cal_monthly
    )
    totals = {k: sum(r[k] for r in cal_monthly) for k in ("预约APE", "预约件数", "签单APE", "签单件数", "批核APE", "批核件数")}
    last = cal_monthly[-1] if cal_monthly else None
    best_issue = max(cal_monthly[:-1], key=lambda r: r["批核APE"]) if len(cal_monthly) > 1 else None
    w_html = f"""
    <div class="card card-w card-full">
      {_module_title("W", "同行月度分析 — 重点KA 预约/签单/批核走势&月度汇总（APE in M）", "navy")}
      <div class="kpi-mini-row">
        <div class="kpi-mini">同行本月预约APE <b>{fmt_m(last['预约APE']) if last else '—'}</b><span>{fmt_cnt(last['预约件数']) if last else ''}件 | 件均{fmt_wan(last['预约APE']/last['预约件数']) if last and last['预约件数'] else '—'}</span></div>
        <div class="kpi-mini">同行本月签单APE <b>{fmt_m(last['签单APE']) if last else '—'}</b><span>{fmt_cnt(last['签单件数']) if last else ''}件 | 件均{fmt_wan(last['签单APE']/last['签单件数']) if last and last['签单件数'] else '—'}</span></div>
        <div class="kpi-mini">同行本月批核APE <b>{fmt_m(last['批核APE']) if last else '—'}</b><span>{fmt_cnt(last['批核件数']) if last else ''}件 | 件均{fmt_wan(last['批核APE']/last['批核件数']) if last and last['批核件数'] else '—'}</span></div>
      </div>
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>月份</th><th>预约M</th><th>预约件</th><th>签单M</th><th>签单件</th><th>批核M</th><th>批核件</th></tr></thead>
        <tbody>{w_rows}
        <tr class="total-row"><td>合计</td><td>{totals['预约APE']/1e6:.2f}</td><td>{fmt_cnt(totals['预约件数'])}</td>
        <td>{totals['签单APE']/1e6:.2f}</td><td>{fmt_cnt(totals['签单件数'])}</td>
        <td>{totals['批核APE']/1e6:.2f}</td><td>{fmt_cnt(totals['批核件数'])}</td></tr>
        </tbody>
      </table></div>
      {_note(f"同行已结束月份中，{best_issue['month'] if best_issue else '—'}批核APE最高，为{fmt_m(best_issue['批核APE'],2) if best_issue else '—'}；{last['month'] if last else ''}未完结。")}
    </div>
    """

    return f"""
    <section class="page" data-page="9">
      {_page_header(9, "同行业绩分析仪表盘", "Pipeline & Approval View")}
      {kpi_html}
      <div class="grid2">{y_html}{x_html}</div>
      {w_html}
      {_footer(week_full)}
    </section>
    """


def _kpi3(cls, val_html, label, sub_html) -> str:
    return (f'<div class="kpi-cell kpi-{cls}"><div class="kpi-val">{val_html}</div>'
            f'<div class="kpi-label">{esc(label)}</div><div class="kpi-sub">{sub_html}</div></div>')


def _month_kpi_sub(m: dict) -> str:
    avg = m["ape"] / m["cnt"] if m["cnt"] else 0.0
    return f'{fmt_cnt(m["cnt"])}件 | 件均{fmt_wan(avg) if m["cnt"] else "—"}'


# ======================================================================
# 第10页：银行业绩分析仪表盘（Phase2新增）
# ======================================================================

def build_page10(ctx: dict, week_full: str) -> str:
    bv = ctx["bank_v"]
    month_label, month_vals = ctx["bk_month"]
    ws = bv["weekly_snapshot"]

    kpi_row = f"""<div class="kpi-strip9">
      {_kpi3("navy", fmt_m(bv['issued_ape']), "BK批核", _month_kpi_sub({"ape": bv['issued_ape'], "cnt": bv['issued_cnt']}))}
      {_kpi3("red", fmt_m(bv['unbat_ape']), "BK未批核", _month_kpi_sub({"ape": bv['unbat_ape'], "cnt": bv['unbat_cnt']}))}
      {_kpi3("gold", fmt_m(bv['pend_ape']), "BK待签", _month_kpi_sub({"ape": bv['pend_ape'], "cnt": bv['pend_cnt']}))}
      {_kpi3("steel", fmt_m(month_vals['预约']['ape']), f"BK {month_label or ''}预约", _month_kpi_sub(month_vals['预约']))}
      {_kpi3("teal", fmt_m(month_vals['签单']['ape']), f"BK {month_label or ''}签单", _month_kpi_sub(month_vals['签单']))}
      {_kpi3("navy", fmt_m(month_vals['批核']['ape']), f"BK {month_label or ''}批核", _month_kpi_sub(month_vals['批核']))}
      {_kpi3("steel", fmt_m(ws['预约']['ape']), f"BK {bv['cur_week']}预约", _month_kpi_sub(ws['预约']))}
      {_kpi3("teal", fmt_m(ws['签单']['ape']), f"BK {bv['cur_week']}签单", _month_kpi_sub(ws['签单']))}
      {_kpi3("navy", fmt_m(ws['批核']['ape']), f"BK {bv['cur_week']}批核", _month_kpi_sub(ws['批核']))}
    </div>"""

    aa_html = f"""
    <div class="card card-aa">
      {_module_title("AA", "银行月度已批核APE（M港元）／件数", "navy")}
      <div class="chartbox" style="height:200px;"><canvas id="p10_chartMonthly"></canvas></div>
      {_note("批核件数｜当月进行中，不据此判断全月升降。")}
    </div>
    """
    ab_html = f"""
    <div class="card card-ab">
      {_module_title("AB", f"W01–{bv['cur_week']} 银行周度预约/签单/批核趋势（M）", "navy")}
      <div class="chartbox" style="height:200px;"><canvas id="p10_chartWeekly"></canvas></div>
    </div>
    """

    wd = ctx["bank_weekly_cnt"]
    ac_rows = "".join(
        f'<tr><td>{esc(r["ka"])}</td>'
        f'<td>{r["vals"]["预约"]["ape"]/1e6:.2f}M</td><td>{fmt_cnt(r["vals"]["预约"]["cnt"])}</td>'
        f'<td>{r["vals"]["签单"]["ape"]/1e6:.2f}M</td><td>{fmt_cnt(r["vals"]["签单"]["cnt"])}</td>'
        f'<td>{r["vals"]["批核"]["ape"]/1e6:.2f}M</td><td>{fmt_cnt(r["vals"]["批核"]["cnt"])}</td></tr>'
        for r in wd["rows"]
    )
    t = wd["total"]
    ac_html = f"""
    <div class="card card-ac card-full">
      {_module_title("AC", f"{bv['cur_week']} 银行KA 本周业绩详情（M）", "purple")}
      <table class="dtable">
        <thead><tr><th>KEY ACCOUNT</th><th>本周预约(M)</th><th>件数</th><th>本周签单(M)</th><th>件数</th>
        <th>本周批核(M)</th><th>件数</th></tr></thead>
        <tbody>{ac_rows}
        <tr class="total-row"><td>银行合计</td>
        <td>{t['预约']['ape']/1e6:.2f}M</td><td>{fmt_cnt(t['预约']['cnt'])}</td>
        <td>{t['签单']['ape']/1e6:.2f}M</td><td>{fmt_cnt(t['签单']['cnt'])}</td>
        <td>{t['批核']['ape']/1e6:.2f}M</td><td>{fmt_cnt(t['批核']['cnt'])}</td></tr>
        </tbody>
      </table>
    </div>
    """

    bb = bv["branch_bar"]
    top10 = list(zip(bb["labels"], bb["合计"]))[:10]
    rest_sum = sum(v for _, v in list(zip(bb["labels"], bb["合计"]))[10:])
    total_sum = sum(bb["合计"])
    ad_rows = "".join(f'<tr><td>{esc(l)}</td><td>{v/1e6:.2f}</td></tr>' for l, v in top10)
    ad_html = f"""
    <div class="card card-ad card-full">
      {_module_title("AD", "银行分行年度批核APE（M港元）｜TOP10＋其他", "navy")}
      <div class="ad-body">
        <div class="chartbox" style="height:150px;"><canvas id="p10_chartAD"></canvas></div>
        <div class="tablewrap"><table class="dtable">
          <thead><tr><th>分行</th><th>批核APE M</th></tr></thead>
          <tbody>{ad_rows}
          <tr><td>其他</td><td>{rest_sum/1e6:.2f}</td></tr>
          <tr class="total-row"><td>完整总体</td><td>{total_sum/1e6:.2f}</td></tr>
          </tbody>
        </table></div>
      </div>
      {_note(f"完整总体{fmt_m(total_sum,2)}；仅展示排名，其他包含全部余项。")}
    </div>
    """

    return f"""
    <section class="page" data-page="10">
      {_page_header(10, "银行业绩分析仪表盘", "Bank View")}
      {kpi_row}
      <div class="grid2">{aa_html}{ab_html}</div>
      <div class="grid2">{ac_html}{ad_html}</div>
      {_footer(week_full)}
    </section>
    """


# ======================================================================
# 第11页：代理人业务分析仪表盘（Phase2新增）
# ======================================================================

def _ka_detail_table_html(df_ka) -> str:
    """天领业务/成事家办/ICLUB/合伙转介/IFA这类"KA明细"表的通用渲染——数据源是
    s9["B"]/["C"]/["F_xxx"]等原始CSV，本身已经按2026批核APE降序排好、自带"合计"行
    （已用真实数据核对跟p11/p12.txt逐行精确匹配，不需要重新排序/重新算合计）。
    金额单位=万（Mark这几张KA明细表的口径），不是M。"""
    rows_html = ""
    for _, r in df_ka.iterrows():
        cls = ' class="total-row"' if str(r["KEY ACCOUNT"]).strip() == "合计" else ""
        rows_html += (
            f'<tr{cls}><td>{esc(r["KEY ACCOUNT"])}</td>'
            f'<td>{num(r["2026批核APE"])/1e4:.0f}</td><td>{fmt_cnt(r["批核件数"])}</td>'
            f'<td>{num(r["未批核APE"])/1e4:.0f}</td><td>{fmt_cnt(r["未批核件数"])}</td>'
            f'<td>{num(r["待签APE"])/1e4:.0f}</td><td>{fmt_cnt(r["待签件数"])}</td>'
            f'<td>{num(r["总APE"])/1e4:.0f}</td><td>{fmt_cnt(r["总件数"])}</td></tr>'
        )
    return rows_html


def _tot_val(df, col: str) -> float:
    """取df里KEY ACCOUNT=='合计'那一行的col值——s9["B"]/["C"]/["F_xxx"]这类KA明细表
    自带'合计'行本身就是正确汇总，不能对全部行(含'合计'行自己)求和，会双重计数。"""
    row = df[df["KEY ACCOUNT"] == "合计"]
    return num(row.iloc[0][col]) if not row.empty else 0.0


def build_page11(ctx: dict, week_full: str) -> str:
    av = ctx["agent_v"]
    month_label, month_vals = ctx["agent_month"]
    ws = av["weekly_snapshot"]
    s9 = ctx["s9"]

    kpi_row = f"""<div class="kpi-strip9">
      {_kpi3("navy", fmt_m(av['issued_total']), "代理人业务批核", _month_kpi_sub({"ape": av['issued_total'], "cnt": int(_tot_val(s9['B'], '批核件数') + _tot_val(s9['C'], '批核件数'))}))}
      {_kpi3("red", fmt_m(av['unbat_total']), "代理人业务未批核", _month_kpi_sub({"ape": av['unbat_total'], "cnt": int(_tot_val(s9['B'], '未批核件数') + _tot_val(s9['C'], '未批核件数'))}))}
      {_kpi3("gold", fmt_m(av['pend_total']), "代理人业务待签", _month_kpi_sub({"ape": av['pend_total'], "cnt": int(_tot_val(s9['B'], '待签件数') + _tot_val(s9['C'], '待签件数'))}))}
      {_kpi3("steel", fmt_m(month_vals['预约']['ape']), f"代理人{month_label or ''}预约", _month_kpi_sub(month_vals['预约']))}
      {_kpi3("teal", fmt_m(month_vals['签单']['ape']), f"代理人{month_label or ''}签单", _month_kpi_sub(month_vals['签单']))}
      {_kpi3("navy", fmt_m(month_vals['批核']['ape']), f"代理人{month_label or ''}批核", _month_kpi_sub(month_vals['批核']))}
      {_kpi3("steel", fmt_m(ws['预约']['ape']), f"代理人{av['cur_week']}预约", _month_kpi_sub(ws['预约']))}
      {_kpi3("teal", fmt_m(ws['签单']['ape']), f"代理人{av['cur_week']}签单", _month_kpi_sub(ws['签单']))}
      {_kpi3("navy", fmt_m(ws['批核']['ape']), f"代理人{av['cur_week']}批核", _month_kpi_sub(ws['批核']))}
    </div>"""

    tl_rows = _ka_detail_table_html(s9["B"])
    tl_html = f"""
    <div class="card card-ka">
      {_module_title("KA明细", "天领业务", "purple")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>KEY ACCOUNT</th><th>批核APE(万)</th><th>批核件数</th><th>未批核APE(万)</th><th>未批核件数</th>
        <th>待签APE(万)</th><th>待签件数</th><th>合计APE(万)</th><th>合计件数</th></tr></thead>
        <tbody>{tl_rows}</tbody>
      </table></div>
    </div>
    """
    gtd_rows = _ka_detail_table_html(s9["C"])
    gtd_html = f"""
    <div class="card card-ka">
      {_module_title("KA明细", "成事家办", "purple")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>KEY ACCOUNT</th><th>批核APE(万)</th><th>批核件数</th><th>未批核APE(万)</th><th>未批核件数</th>
        <th>待签APE(万)</th><th>待签件数</th><th>合计APE(万)</th><th>合计件数</th></tr></thead>
        <tbody>{gtd_rows}</tbody>
      </table></div>
    </div>
    """

    wd = av["weekly_detail"]
    wk_rows = "".join(
        f'<tr><td>{esc(r["ka"])}</td><td>{r["vals"]["预约"]/1e6:.2f}M</td>'
        f'<td>{r["vals"]["签单"]/1e6:.2f}M</td><td>{r["vals"]["批核"]/1e6:.2f}M</td></tr>'
        for r in wd["rows"]
    )
    t = wd["total"]
    wk_html = f"""
    <div class="card card-wk card-full">
      {_module_title("快报", f"{av['cur_week']} 本周快报｜代理人业务（天领+成事家办）", "navy")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>KEY ACCOUNT</th><th>预约(M)</th><th>签单(M)</th><th>批核(M)</th></tr></thead>
        <tbody>{wk_rows}
        <tr class="total-row"><td>合计</td><td>{t['预约']/1e6:.2f}M</td><td>{t['签单']/1e6:.2f}M</td><td>{t['批核']/1e6:.2f}M</td></tr>
        </tbody>
      </table></div>
    </div>
    """

    trend_html = f"""
    <div class="card card-trend">
      {_module_title("趋势", "代理人业务月度预约/签单/批核APE趋势", "navy")}
      <div class="chartbox" style="height:170px;"><canvas id="p11_chartTrend"></canvas></div>
      {_note("月度数据来源于S9-H/I周度明细子表并集，覆盖范围不满29周（见README已知限制），"
             "缺列=该周真实0贡献，不是数据丢失。")}
    </div>
    """

    return f"""
    <section class="page" data-page="11">
      {_page_header(11, "代理人业务分析仪表盘", "Agent Business View")}
      {kpi_row}
      <div class="grid2">{tl_html}{gtd_html}</div>
      <div class="grid2-11">{wk_html}{trend_html}</div>
      {_footer(week_full)}
    </section>
    """


# ======================================================================
# 第12页：KA业务分析仪表盘（Phase2新增）
# ======================================================================

def build_page12(ctx: dict, week_full: str) -> str:
    kv = ctx["ka_v"]

    s9 = ctx["s9"]
    ka_frames = [s9["F_ICLUB业务"], s9["F_合伙转介业务"], s9["F_IFA业务"]]
    kpi_html = f"""<div class="kpi-strip3">
      {_kpi3("navy", fmt_m(kv['issued_total']), "KA业务批核APE", _month_kpi_sub({"ape": kv['issued_total'], "cnt": int(sum(_tot_val(d, '批核件数') for d in ka_frames))}))}
      {_kpi3("red", fmt_m(kv['unbat_total']), "KA业务未批核APE", _month_kpi_sub({"ape": kv['unbat_total'], "cnt": int(sum(_tot_val(d, '未批核件数') for d in ka_frames))}))}
      {_kpi3("gold", fmt_m(kv['pend_total']), "KA业务待签APE", _month_kpi_sub({"ape": kv['pend_total'], "cnt": int(sum(_tot_val(d, '待签件数') for d in ka_frames))}))}
    </div>"""

    def _block(title, df_ka):
        rows = _ka_detail_table_html(df_ka)
        return f"""
        <div class="card card-ka">
          {_module_title("KA明细", title, "purple")}
          <div class="tablewrap"><table class="dtable">
            <thead><tr><th>KEY ACCOUNT</th><th>批核APE(万)</th><th>批核件数</th><th>未批核APE(万)</th><th>未批核件数</th>
            <th>待签APE(万)</th><th>待签件数</th><th>合计APE(万)</th><th>合计件数</th></tr></thead>
            <tbody>{rows}</tbody>
          </table></div>
        </div>
        """

    iclub_html = _block("ICLUB业务", ctx["s9"]["F_ICLUB业务"])
    ref_html = _block("合伙转介业务", ctx["s9"]["F_合伙转介业务"])
    ifa_html = _block("IFA业务", ctx["s9"]["F_IFA业务"])

    wd = kv["weekly_detail"]
    wk_rows = "".join(
        f'<tr><td>{esc(r["ka"])}</td><td>{r["vals"]["预约"]/1e6:.2f}M</td>'
        f'<td>{r["vals"]["签单"]/1e6:.2f}M</td><td>{r["vals"]["批核"]/1e6:.2f}M</td></tr>'
        for r in wd["rows"]
    )
    t = wd["total"]
    wk_html = f"""
    <div class="card card-wk">
      {_module_title("快报", f"{kv['cur_week']} 本周快报｜KA业务", "navy")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>KEY ACCOUNT</th><th>预约(M)</th><th>签单(M)</th><th>批核(M)</th></tr></thead>
        <tbody>{wk_rows}
        <tr class="total-row"><td>合计</td><td>{t['预约']/1e6:.2f}M</td><td>{t['签单']/1e6:.2f}M</td><td>{t['批核']/1e6:.2f}M</td></tr>
        </tbody>
      </table></div>
    </div>
    """

    trend_html = f"""
    <div class="card card-trend">
      {_module_title("趋势", "KA业务月度预约/签单/批核APE趋势", "navy")}
      <div class="chartbox" style="height:150px;"><canvas id="p12_chartTrend"></canvas></div>
      {_note("IFA业务批核/待签全为0（见右侧IFA明细表），已确认是业务线本身当前无实际批核发生，不是数据缺失。" if kv.get("note_ifa_empty") else "")}
    </div>
    """

    return f"""
    <section class="page" data-page="12">
      {_page_header(12, "KA业务分析仪表盘", "ICLUB + 合伙转介 + IFA")}
      {kpi_html}
      <div class="grid3">{iclub_html}{ref_html}{ifa_html}</div>
      <div class="grid2">{wk_html}{trend_html}</div>
      {_footer(week_full)}
    </section>
    """


# ======================================================================
# 第13页：永明签单产品与年期·补充明细（Phase2新增）
# ======================================================================

def build_page13(ctx: dict, week_full: str) -> str:
    prem = ctx["sun_premium_top10"]
    term = ctx["sun_term_dist"]

    top10_rows = "".join(
        f'<tr><td>{esc(r["产品名称"])}</td><td>{esc(r["年期"])}</td><td>{esc(r["首年折扣"])}</td>'
        f'<td>{fmt_cnt(r["件数"])}</td><td>{r["保费"]/1e6:.2f}</td></tr>'
        for r in prem["top"]
    )
    top10_cnt = sum(r["件数"] for r in prem["top"])
    top10_premium = sum(r["保费"] for r in prem["top"])
    premium_html = f"""
    <div class="card card-full">
      {_module_title("TOP10", "永明产品保费TOP10＋其他｜当年签单群体", "navy")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>产品（源名）</th><th>年期</th><th>折扣</th><th>件数</th><th>保费M</th></tr></thead>
        <tbody>{top10_rows}
        <tr class="total-row"><td colspan="3">TOP10合计</td><td>{fmt_cnt(top10_cnt)}</td><td>{top10_premium/1e6:.2f}</td></tr>
        <tr><td colspan="3">其他</td><td>{fmt_cnt(prem['rest_cnt'])}</td><td>{prem['rest_premium']/1e6:.2f}</td></tr>
        <tr class="total-row"><td colspan="3">总体</td><td>{fmt_cnt(prem['total_cnt'])}</td><td>{prem['total_premium']/1e6:.2f}</td></tr>
        </tbody>
      </table></div>
    </div>
    """

    term_rows = "".join(
        f'<tr><td>{esc(r["年期类别"])}</td><td>{fmt_cnt(r["件数"])}</td>'
        f'<td>{r["APE"]/1e6:.2f}</td><td>{r["保费"]/1e6:.2f}</td></tr>'
        for r in term
    )
    tot_cnt = sum(r["件数"] for r in term)
    tot_ape = sum(r["APE"] for r in term)
    tot_prem = sum(r["保费"] for r in term)
    term_html = f"""
    <div class="card card-full">
      {_module_title("年期分布", "完整年期分布", "navy")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>年期类别</th><th>件数</th><th>APE M</th><th>保费M</th></tr></thead>
        <tbody>{term_rows}
        <tr class="total-row"><td>总体</td><td>{fmt_cnt(tot_cnt)}</td><td>{tot_ape/1e6:.2f}</td><td>{tot_prem/1e6:.2f}</td></tr>
        </tbody>
      </table></div>
      {_note("产品按源名称＋年期＋折扣区分；“未提供”不擅自归并。<br>"
             "保费与APE分别排序，排名可能不同。<br>"
             "本页签单群体与年度批核群体不同，不能直接相减解释阶段迁移。")}
    </div>
    """

    return f"""
    <section class="page" data-page="13">
      {_page_header(13, "永明签单产品与年期｜补充明细", "", badge="候选稿")}
      {premium_html}
      {term_html}
      {_footer(week_full, variant="supplement")}
    </section>
    """


# ======================================================================
# 第14页：执行明细、来源说明与管理行动（Phase2新增，全新页面）
# ======================================================================

def build_page14(ctx: dict, week_full: str) -> str:
    ev = ctx["event_table14"]
    te = ctx["timeliness"]
    dq = ctx["dq"]
    unapp = ctx["unapproved_top10"]

    ev_rows = ""
    for r in ev["rows"]:
        ev_rows += (
            f'<tr><td>{esc(r["segment"])}</td>'
            f'<td>{r["res"]["ape"]/1e6:.2f}</td><td>{fmt_cnt(r["res"]["cnt"])}</td>'
            f'<td>{r["sign"]["ape"]/1e6:.2f}</td><td>{fmt_cnt(r["sign"]["cnt"])}</td>'
            f'<td>—</td><td>—</td>'
            f'<td>{r["issue"]["ape"]/1e6:.2f}</td><td>{fmt_cnt(r["issue"]["cnt"])}</td></tr>'
        )
    tot = ev["totals"]
    submit_total = ctx["s3v"]["weekly_snapshot"]["递交"]  # 只有总量，没有按业务线拆分，见模块docstring
    submit_ape = f"{submit_total['ape']/1e6:.2f}" if submit_total else "—"
    submit_cnt = fmt_cnt(submit_total["cnt"]) if submit_total else "—"
    ev_html = f"""
    <div class="card card-full">
      {_module_title("八线四事件", f"{week_full}完整八线／四事件（M港元）", "navy")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>业务线</th><th>预约M</th><th>件</th><th>签单M</th><th>件</th>
        <th>递交M</th><th>件</th><th>批核M</th><th>件</th></tr></thead>
        <tbody>{ev_rows}
        <tr class="total-row"><td>合计</td>
        <td>{tot['res']['ape']/1e6:.2f}</td><td>{fmt_cnt(tot['res']['cnt'])}</td>
        <td>{tot['sign']['ape']/1e6:.2f}</td><td>{fmt_cnt(tot['sign']['cnt'])}</td>
        <td>{submit_ape}</td><td>{submit_cnt}</td>
        <td>{tot['issue']['ape']/1e6:.2f}</td><td>{fmt_cnt(tot['issue']['cnt'])}</td></tr>
        </tbody>
      </table></div>
      {_note("递交事件当前无业务线拆分数据源（S3执行管理端目前只有递交总量，没有按业务细分拆分的"
             "递交周度板块），本表递交列按业务线留空“—”，仅在合计行展示总量；不新增反推逻辑凑出"
             "按业务线拆分的递交数据。")}
    </div>
    """

    bucket_rows = "".join(
        f'<tr><td>{esc(r["分档"])}</td><td>{fmt_cnt(r["件数"])}</td><td>{fmt_pct(r["占比"])}</td></tr>'
        for r in te["bucket_rows"]
    )
    tl_html = f"""
    <div class="card">
      {_module_title("时效分布", "签批时效分布", "purple")}
      <table class="dtable">
        <thead><tr><th>签批用时</th><th>件数</th><th>占有效样本</th></tr></thead>
        <tbody>{bucket_rows}
        <tr class="total-row"><td>有效总体</td><td>{fmt_cnt(te['total_valid'])}</td><td>100.0%</td></tr>
        <tr><td>排除样本</td><td>{fmt_cnt(te['excluded_count'])}</td><td>不入分母</td></tr>
        </tbody>
      </table>
      {_note(f"≤60天：{fmt_cnt(te['sla60_count'])}/{fmt_cnt(te['total_valid'])} = {fmt_pct(te['sla60_rate'])}。"
             "签批日期缺失或为负者不入分母（跟第7页T表同一口径，直接复用，不重新计算）。")}
    </div>
    """

    dq_html = f"""
    <div class="card">
      {_module_title("边界说明", "数据与解释边界", "navy")}
      <div class="dq-grid">
        <div class="dq-cell"><b>{fmt_cnt(dq['n_rows'])}</b><span>本稿依据已交付文件行数</span></div>
        <div class="dq-cell"><b>{fmt_cnt(dq['missing_issue_date'])}</b><span>缺批核日期（生效但issue_date为空）</span></div>
        <div class="dq-cell"><b>{fmt_cnt(dq['ape_missing'])}/{fmt_cnt(dq['premium_missing'])}</b><span>APE/保费缺失（不归零）</span></div>
        <div class="dq-cell"><b>{fmt_cnt(dq['future_dated'])}</b><span>未来签单日（sign_date&gt;文件导出日）</span></div>
        <div class="dq-cell"><b>{fmt_cnt(dq['declined'])}</b><span>拒保</span></div>
        <div class="dq-cell"><b>{fmt_cnt(dq['negative_tat'])}</b><span>负时效（已排除，不入签批时效分母）</span></div>
        <div class="dq-cell"><b>{fmt_cnt(dq['entity_alias_records'])}条/{fmt_cnt(dq['entity_alias_pairs'])}对</b><span>实体别名归一化（简繁体同一实体合并）</span></div>
      </div>
      {_note("2025历史：0404已核版本；与2026本次快照分别管理。旧Alice外部供数退出；中台原有TA/MGA"
             "记录保留。同行实际含MGA，与既有目标范围存在差异。预测未形成现行规则；当前未批和待签"
             "仅作为存量，不承诺兑现。以上7项均独立用pandas重算自本批数据，不是照抄历史某次快照"
             "的具体数字。")}
    </div>
    """

    action_html = f"""
    <div class="card card-full">
      {_module_title("管理行动", "管理行动（建议，负责人及时间待分派）", "red")}
      <ol class="action-list">
        <li>按完整八线核对本周差额；“递交”事件当前无业务线拆分数据源（仅展示总量，见上方事件表说明），
            同行实际/目标范围差异列为管理口径事项。（业务管理负责人）</li>
        <li>下一次取数固定批次和截止时点，保留两期快照后再解释净增、回退及重分类；本稿依据已交付文件
            {fmt_cnt(dq['n_rows'])}行。（数据负责人）</li>
        <li>按未批核渠道金额核对资料/缴费/批核进度（见右侧“在途推进”TOP10，总体{fmt_m(unapp['total']['ape'],2)}
            / {fmt_cnt(unapp['total']['cnt'])}件）；源表未提供责任人和承诺日期，不猜测预计释放时间。
            （渠道及运营负责人）</li>
        <li>确认拒保{fmt_cnt(dq['declined'])}单、未来签单日{fmt_cnt(dq['future_dated'])}单、缺批核日期
            {fmt_cnt(dq['missing_issue_date'])}单、负时效{fmt_cnt(dq['negative_tat'])}单及实体别名归一化
            （{fmt_cnt(dq['entity_alias_records'])}条记录涉及{fmt_cnt(dq['entity_alias_pairs'])}个实体对子）
            的处置口径；改口径前保留原始值与影响评估。（业务与数据负责人）</li>
      </ol>
    </div>
    """

    unapp_rows = "".join(
        f'<tr><td>{esc(r["ka"])}</td><td>{r["ape"]/1e6:.2f}</td><td>{fmt_cnt(r["cnt"])}</td></tr>'
        for r in unapp["top"]
    )
    unapp_html = f"""
    <div class="card">
      {_module_title("在途推进", "在途推进｜按未批APE排序TOP10", "gold")}
      <table class="dtable">
        <thead><tr><th>未批渠道</th><th>APE M</th><th>件数</th></tr></thead>
        <tbody>{unapp_rows}
        <tr><td>其他</td><td>{unapp['rest']['ape']/1e6:.2f}</td><td>{fmt_cnt(unapp['rest']['cnt'])}</td></tr>
        <tr class="total-row"><td>总体</td><td>{unapp['total']['ape']/1e6:.2f}</td><td>{fmt_cnt(unapp['total']['cnt'])}</td></tr>
        </tbody>
      </table>
    </div>
    """

    return f"""
    <section class="page" data-page="14">
      {_page_header(14, "执行明细、来源说明与管理行动", "", badge="候选稿")}
      {ev_html}
      <div class="grid3-14">{tl_html}{dq_html}{unapp_html}</div>
      {action_html}
      {_footer(week_full, variant="supplement")}
    </section>
    """


# ======================================================================
# 第15页：同行合作渠道与推荐人·完整总体（Phase2新增）
# ======================================================================

def build_page15(ctx: dict, week_full: str) -> str:
    partner = ctx["peer_partner_full"]
    referrer = ctx["peer_referrer_full"]

    def _p_row(label, r, cls=""):
        stage_total = r["batch"] + r["unbat"] + r["pend"]
        stage_cnt = r["batch_c"] + r["unbat_c"] + r["pend_c"]
        return (f'<tr class="{cls}"><td>{esc(label)}</td>'
                f'<td>{r["batch"]/1e6:.2f}</td><td>{fmt_cnt(r["batch_c"])}</td>'
                f'<td>{r["unbat"]/1e6:.2f}</td><td>{fmt_cnt(r["unbat_c"])}</td>'
                f'<td>{r["pend"]/1e6:.2f}</td><td>{fmt_cnt(r["pend_c"])}</td>'
                f'<td>{stage_total/1e6:.2f}</td><td>{fmt_cnt(stage_cnt)}</td></tr>')

    partner_rows = "".join(_p_row(r["partner"], r) for r in partner["top"])
    partner_html = f"""
    <div class="card card-full">
      {_module_title("合作渠道", "合作渠道：按年度批核APE取TOP10＋其他", "navy")}
      <div class="tablewrap"><table class="dtable">
        <thead><tr><th>渠道</th><th>批核M</th><th>件</th><th>未批M</th><th>件</th><th>待签M</th><th>件</th>
        <th>阶段合计M</th><th>件</th></tr></thead>
        <tbody>{partner_rows}
        {_p_row("TOP10合计", {k: sum(x[k] for x in partner["top"]) for k in ("batch","batch_c","unbat","unbat_c","pend","pend_c")}, "total-row")}
        {_p_row("其他", partner["rest"])}
        {_p_row("总体", partner["total"], "total-row")}
        </tbody>
      </table></div>
    </div>
    """

    def _r_row(label, r, cls=""):
        return (f'<tr class="{cls}"><td>{esc(label)}</td>'
                f'<td>{r["batch"]/1e6:.2f}</td><td>{r["unbat"]/1e6:.2f}</td><td>{r["pend"]/1e6:.2f}</td>'
                f'<td>{fmt_cnt(r["cnt"])}</td></tr>')

    referrer_rows = "".join(_r_row(r["name"], r) for r in referrer["named"])
    referrer_html = f"""
    <div class="card card-full">
      {_module_title("推荐人", "推荐人：原图六人＋其他／未提供", "navy")}
      <table class="dtable">
        <thead><tr><th>推荐人</th><th>批核M</th><th>未批M</th><th>待签M</th><th>阶段件数</th></tr></thead>
        <tbody>{referrer_rows}
        {_r_row("其他/未提供", referrer["other"])}
        {_r_row("总体", referrer["total"], "total-row")}
        </tbody>
      </table>
      {_note("合作渠道：partner_code<br>推荐人：referral_code<br>原P08渠道账户：key_account<br>"
             "三个来源字段分别分组。不能用推荐人图证明合作渠道已完整展示。<br>"
             "每个维度均对齐同行三阶段总体；原始名称不擅自合并。<br>"
             "主文保留原推荐人图与KA分析；本页补全合作渠道及未显示群体。")}
    </div>
    """

    return f"""
    <section class="page" data-page="15">
      {_page_header(15, "同行合作渠道与推荐人｜完整总体", "", badge="候选稿")}
      {partner_html}
      {referrer_html}
      {_footer(week_full, variant="supplement")}
    </section>
    """


# ======================================================================
# 第16-18页：Q/R/S周度热力矩阵完整表格（Phase2新增）
# ======================================================================

def _heat_table_html(title_letter: str, title: str, color: str, ht: dict, page_no: int, metric_label: str, week_full: str) -> str:
    week_ths = "".join(f"<th>{esc(w)}</th>" for w in ht["weeks"])
    rows_html = ""
    for r in ht["rows"]:
        cells = "".join(
            f'<td><div class="hcell"><b>{v["ape"]/1e6:.1f}</b><span>{fmt_cnt(v["cnt"])}件</span></div></td>'
            for v in r["vals"]
        )
        rows_html += f'<tr><td>{esc(r["segment"])}</td>{cells}</tr>'
    total_cells = "".join(
        f'<td><div class="hcell"><b>{v["ape"]/1e6:.1f}</b><span>{fmt_cnt(v["cnt"])}件</span></div></td>'
        for v in ht["total"]
    )
    rows_html += f'<tr class="total-row"><td>合计</td>{total_cells}</tr>'
    cur = ht["total"][-1]
    note = (f"{week_full}{metric_label}{fmt_cnt(cur['cnt'])}件／{cur['ape']/1e6:.2f}M；"
            f"APE与件数逐格列示，合计包含八线。最近{len(ht['weeks'])}个业务周窗口，随当前周滚动。")
    return f"""
    <div class="card card-full">
      {_module_title(title_letter, title, color)}
      <div class="heat-wrap"><table class="heat">
        <thead><tr><th>业务线</th>{week_ths}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table></div>
      {_note(note)}
    </div>
    """


def build_page16(ctx: dict, week_full: str) -> str:
    body = _heat_table_html("Q", "周度预约业绩热力矩阵（APE in M）", "steel", ctx["heat_q"], 16, "预约", week_full)
    return f"""
    <section class="page" data-page="16">
      {_page_header(16, "执行管理端分析仪表盘", "Execution Management View")}
      {body}
      {_footer(week_full)}
    </section>
    """


def build_page17(ctx: dict, week_full: str) -> str:
    body = _heat_table_html("R", "周度签单业绩热力矩阵（APE in M）", "teal", ctx["heat_r"], 17, "签单", week_full)
    return f"""
    <section class="page" data-page="17">
      {_page_header(17, "执行管理端分析仪表盘", "Execution Management View")}
      {body}
      {_footer(week_full)}
    </section>
    """


def build_page18(ctx: dict, week_full: str) -> str:
    body = _heat_table_html("S", "周度批核业绩热力矩阵（APE in M）", "navy", ctx["heat_s"], 18, "批核", week_full)
    return f"""
    <section class="page" data-page="18">
      {_page_header(18, "执行管理端分析仪表盘", "Execution Management View")}
      {body}
      {_footer(week_full)}
    </section>
    """


# ======================================================================
# CSS（浅色独立视觉系统，不跟multiview_dashboard.py共用:root变量）
# ======================================================================

_CSS = """
:root {
  --mk-navy: #16213f;
  --mk-navy-2: #1f2f55;
  --mk-teal: #1a7a6e;
  --mk-teal-light: #e5f3f1;
  --mk-red: #a83a3a;
  --mk-red-light: #f7e9e9;
  --mk-gold: #b4861f;
  --mk-gold-light: #faf2e2;
  --mk-blue: #2b6cb0;
  --mk-blue-light: #e8f0fa;
  --mk-purple: #5b3a7a;
  --mk-purple-light: #efe7f5;
  --mk-steel: #4a6fa5;
  --mk-brown: #6b4423;
  --mk-text: #1c2230;
  --mk-muted: #6b7280;
  --mk-border: #d7dce3;
  --mk-bg-card: #ffffff;
  --mk-bg-note: #eef1f8;
  --mk-bg-page: #f3f4f7;
}
* { box-sizing: border-box; }
body.mk-body { margin: 0; background: var(--mk-bg-page); font-family: "PingFang SC","Microsoft YaHei",Helvetica,Arial,sans-serif; color: var(--mk-text); }
.mk-toolbar { position: sticky; top: 0; z-index: 50; background: var(--mk-navy); color: #fff; padding: 10px 20px; font-size: 13px; display:flex; justify-content:space-between; align-items:center; }
.mk-toolbar button { background: var(--mk-teal); color:#fff; border:none; padding:6px 14px; border-radius:4px; cursor:pointer; font-size:13px; }
.mk-pages { display:flex; flex-direction:column; align-items:center; gap:24px; padding: 24px 0 60px; }
.page {
  width: 1600px; height: 900px; background:#fff; position:relative; overflow:hidden;
  padding: 18px 26px 40px; box-shadow: 0 2px 10px rgba(0,0,0,0.12);
  display:flex; flex-direction:column; page-break-after: always;
  font-size: 13px;
}
.phead { background: linear-gradient(135deg,var(--mk-navy),var(--mk-navy-2)); color:#fff; padding:12px 18px; border-radius:4px; display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex: 0 0 auto; }
.phead-title { font-size:19px; font-weight:700; letter-spacing:.3px; }
.phead-sub { font-size:13px; font-weight:400; color:#cfd6e6; margin-left:8px; }
.phead-badge { font-size:11px; color:#cfd6e6; }
.pfoot { position:absolute; left:0; right:0; bottom:0; background: var(--mk-navy); color:#cfd6e6; font-size:11px; text-align:right; padding:7px 22px; }
.p2-note-top { font-size:12px; color:var(--mk-muted); margin-bottom:8px; }

.grid3 { display:grid; grid-template-columns: repeat(3,1fr); gap:12px; flex: 0 0 auto; margin-bottom:10px; }
.grid2 { display:grid; grid-template-columns: repeat(2,1fr); gap:12px; flex: 0 0 auto; margin-bottom:10px; }
.grid2-f { display:grid; grid-template-columns: 1.6fr 1fr; gap:12px; flex:1 1 auto; min-height:0; }
.grid3-45 { display:grid; grid-template-columns: 1fr 1fr 1.1fr; gap:12px; flex:1 1 auto; min-height:0; }
.grid2-jk { display:grid; grid-template-columns: 1.3fr 1fr; gap:12px; flex:1 1 auto; min-height:0; margin-bottom:10px; }
.grid2-op { display:grid; grid-template-columns: 1fr 1.4fr; gap:12px; flex:1 1 auto; min-height:0; }

.card { background: var(--mk-bg-card); border:1px solid var(--mk-border); border-radius:4px; padding:10px 12px 10px; display:flex; flex-direction:column; min-height:0; }
.card-full { flex:1 1 auto; }
.card-tall { max-height: 640px; overflow:auto; }

.mtitle { color:#fff; font-weight:700; font-size:13.5px; padding:7px 10px; border-radius:3px; margin: -10px -12px 8px; }
.mt-letter { font-weight:800; margin-right:4px; }
.mtitle-navy { background: var(--mk-navy); }
.mtitle-red { background: var(--mk-red); }
.mtitle-teal { background: #0f5a51; }
.mtitle-purple { background: var(--mk-purple); }

.note { background: var(--mk-bg-note); color: var(--mk-muted); font-size:11.5px; padding:7px 10px; border-radius:3px; margin-top:8px; line-height:1.5; }

/* A 模块 */
.a-body { display:flex; gap:10px; }
.a-left { flex: 0 0 150px; display:flex; flex-direction:column; justify-content:center; align-items:center; }
.a-bigpct { font-size:44px; font-weight:800; color: var(--mk-navy); line-height:1; }
.a-bigpct-label { font-size:11px; color:var(--mk-muted); text-align:center; margin-top:4px; }
.a-right { flex:1; display:flex; flex-direction:column; gap:5px; justify-content:center; }
.kpi-row-mini { border-radius:3px; padding:5px 8px; font-size:16px; font-weight:800; display:flex; align-items:baseline; gap:8px; }
.kpi-row-mini span { font-size:10.5px; font-weight:400; color:var(--mk-muted); }
.kpi-navy { background: var(--mk-blue-light); color: var(--mk-navy); }
.kpi-red { background: var(--mk-red-light); color: var(--mk-red); }
.a-progress { margin-top:8px; }
.a-prow { display:flex; align-items:center; gap:8px; margin-top:4px; }
.a-plabel { flex:0 0 150px; font-size:11px; color:var(--mk-text); }
.a-pbar { flex:1; height:10px; background:#e7eaf0; border-radius:5px; overflow:hidden; }
.a-pfill { height:100%; border-radius:5px; }
.a-pfill-navy { background: var(--mk-navy); }
.a-pfill-teal { background: var(--mk-teal); }
.a-ppct { flex:0 0 44px; font-weight:700; font-size:13px; text-align:right; }
.a-pnote { font-size:10.5px; color:var(--mk-muted); margin: 1px 0 1px 158px; }

/* B 模块 */
.bbar { display:flex; height:16px; border-radius:3px; overflow:hidden; margin-bottom:8px; }
.bseg-teal { background: var(--mk-teal); } .bseg-red { background: var(--mk-red); }
.bseg-gold { background: var(--mk-gold); } .bseg-muted { background:#9aa3b2; }
.bgrid { display:grid; grid-template-columns: 1fr 1fr; gap:6px; }
.bcard { border-radius:3px; padding:6px 8px; border-left:4px solid; }
.bcard-teal { background: var(--mk-teal-light); border-color: var(--mk-teal); }
.bcard-red { background: var(--mk-red-light); border-color: var(--mk-red); }
.bcard-gold { background: var(--mk-gold-light); border-color: var(--mk-gold); }
.bcard-muted { background:#eef0f3; border-color:#9aa3b2; }
.bcard-label { font-size:11px; color:var(--mk-muted); }
.bcard-val { font-size:19px; font-weight:800; }
.bcard-sub { font-size:10px; color:var(--mk-muted); }

/* D 模块 */
.d-body { display:flex; gap:14px; flex:1; min-height:0; }
.d-chart { flex: 1.1; min-width:0; }
.chartbox { position:relative; width:100%; }
.chartbox canvas { max-width:100%; }
.d-table { flex:1; display:flex; flex-direction:column; min-width:0; }
.d-table-title { font-weight:700; font-size:12.5px; margin-bottom:4px; }

/* table 通用 */
.tablewrap { overflow-x:auto; overflow-y: auto; }
table.dtable { width:100%; border-collapse: collapse; font-size:11.5px; }
table.dtable th { background: var(--mk-navy); color:#fff; padding:5px 7px; text-align:right; white-space:nowrap; }
table.dtable th:first-child, table.dtable td:first-child { text-align:left; }
table.dtable td { padding:4px 7px; text-align:right; border-bottom:1px solid #eef0f3; white-space:nowrap; }
table.dtable tbody tr:nth-child(even) { background:#f3f6fa; }
table.dtable tr.total-row td { font-weight:700; background:#e7ecf4; }

/* 第2页 */
.card-e { max-height: 760px; }
.ebar-head { display:grid; grid-template-columns: 34px 1fr 58px; font-size:10px; color:var(--mk-muted); margin-bottom:2px; }
.ebar-row { display:grid; grid-template-columns: 34px 1fr 58px; align-items:center; gap:4px; margin-bottom:3px; }
.ebar-m { font-weight:700; font-size:12px; }
.ebar-track { background:#f0f1f4; border-radius:2px; height:20px; position:relative; }
.ebar-fill { height:100%; border-radius:2px; display:flex; align-items:center; padding-left:4px; white-space:nowrap; }
.ebar-fill span.ebar-val { font-size:9.5px; color:#3a2a10; }
.ebar-tan { background:#e7c9a0; } .ebar-wheat { background:#eadca0; } .ebar-mint { background:#aed9c6; }
.ebar-wow { font-size:10px; text-align:right; }
.wow-up { color: var(--mk-teal); font-weight:700; }
.wow-down { color: var(--mk-red); font-weight:700; }
.wow-flat { color: var(--mk-muted); }
.wow-note { color: var(--mk-muted); font-size:9.5px; }

.card-f { flex:1; display:flex; flex-direction:column; }
.card-kpi4 { flex: 0 0 300px; display:flex; flex-direction:column; justify-content:center; }
.kpi4-row { display:grid; grid-template-columns: repeat(4,1fr); gap:8px; }
.kpi4-cell { border-top:4px solid; padding:8px; border-radius:2px; background:#fafbfc; }
.kpi4-navy { border-color: var(--mk-navy); } .kpi4-red { border-color: var(--mk-red); }
.kpi4-gold { border-color: var(--mk-gold); } .kpi4-brown { border-color: var(--mk-brown); }
.kpi4-val { font-size:22px; font-weight:800; }
.kpi4-label { font-size:11px; color:var(--mk-text); margin-top:2px; }
.kpi4-sub { font-size:10px; color:var(--mk-muted); }

/* KPI strips (通用) */
.kpi-strip, .kpi-strip3, .kpi-strip4 { display:grid; gap:10px; margin-bottom:10px; flex: 0 0 auto; }
.kpi-strip { grid-template-columns: repeat(3,1fr); }
.kpi-strip3 { grid-template-columns: repeat(3,1fr); }
.kpi-strip4 { grid-template-columns: repeat(4,1fr); }
.kpi-cell { border-top:4px solid; background:#fafbfc; padding:8px 10px; border-radius:2px; }
.kpi-val { font-size:24px; font-weight:800; }
.kpi-label { font-size:11.5px; color:var(--mk-text); margin-top:2px; }
.kpi-sub { font-size:10.5px; color:var(--mk-muted); }
.kpi-teal { border-color: var(--mk-teal); } .kpi-navy { border-color: var(--mk-navy); }
.kpi-red { border-color: var(--mk-red); } .kpi-gold { border-color: var(--mk-gold); }
.kpi-blue { border-color: var(--mk-blue); } .kpi-steel { border-color: var(--mk-steel); }

.kpi-mini-row { display:flex; gap:14px; margin-bottom:8px; flex-wrap:wrap; }
.kpi-mini { font-size:11px; color:var(--mk-muted); }
.kpi-mini b { font-size:16px; color:var(--mk-navy); display:block; }
.kpi-mini span { display:block; }

/* 第3页 G 牌照明细 */
.card-h, .card-g, .card-i { min-height:0; }

/* 第4页 */
.i-grid { display:grid; grid-template-columns: repeat(2,1fr); gap:8px; flex:1; min-height:0; overflow:auto; }
.i-cell { border:1px solid #eef0f3; border-radius:3px; padding:4px 6px; }
.i-cell-title { font-size:10.5px; font-weight:700; color:var(--mk-navy); }

/* 第5页 J 模块 */
.j-legend { font-size:11px; color:var(--mk-muted); margin-bottom:6px; }
.dot { display:inline-block; width:9px; height:9px; border-radius:2px; margin:0 3px 0 10px; }
.dot-teal { background:var(--mk-teal); } .dot-gold { background:var(--mk-gold); } .dot-blue { background:var(--mk-blue); }
.j-row { display:grid; grid-template-columns: 110px 1fr 150px; align-items:center; gap:8px; margin-bottom:7px; }
.j-label { font-size:11px; font-weight:700; }
.j-total { font-size:10px; font-weight:400; color:var(--mk-muted); }
.j-bar { display:flex; height:20px; border-radius:2px; overflow:hidden; background:#eef0f3; }
.j-seg { display:flex; align-items:center; justify-content:center; font-size:10px; color:#fff; font-weight:700; }
.j-seg-teal { background: var(--mk-teal); } .j-seg-gold { background: var(--mk-gold); } .j-seg-blue { background: var(--mk-blue); }
.j-vals { font-size:10.5px; color:var(--mk-text); text-align:right; }

.k-body { display:flex; align-items:center; gap:12px; flex:1; min-height:0; }
.k-cells { flex:1; display:flex; flex-direction:column; gap:6px; }
.k-cell { border:1px solid; border-radius:3px; padding:6px 8px; }
.k-cell-teal { border-color: var(--mk-teal); } .k-cell-gold { border-color: var(--mk-gold); } .k-cell-blue { border-color: var(--mk-blue); }
.k-cell-label { font-size:10.5px; color:var(--mk-muted); }
.k-cell-val { font-size:17px; font-weight:800; }
.k-cell-sub { font-size:10px; color:var(--mk-muted); }
.k-cell-bar { height:5px; background:#eef0f3; border-radius:3px; margin-top:3px; }
.k-cell-fill { height:100%; background: var(--mk-teal); border-radius:3px; }
.k-cell-sub2 { font-size:10px; font-weight:700; margin-top:2px; }

/* 第6页 M/O */
.m-row { display:grid; grid-template-columns: 56px 1fr; align-items:center; gap:8px; margin-bottom:9px; }
.m-label { font-weight:700; font-size:12.5px; }
.m-track { background:#eef0f3; border-radius:3px; height:30px; display:flex; align-items:center; }
.m-fill { height:100%; border-radius:3px; display:flex; align-items:center; padding:0 10px; color:#fff; font-weight:800; font-size:14px; }
.m-fill-steel { background: var(--mk-steel); } .m-fill-teal { background: var(--mk-teal); }
.m-fill-gold { background: var(--mk-gold); } .m-fill-navy { background: var(--mk-navy); }
.m-cnt { margin-left:8px; font-size:11px; color:var(--mk-muted); }

.pill { display:inline-block; padding:2px 8px; border-radius:10px; color:#fff; font-size:11px; font-weight:700; }
.pill-steel { background: var(--mk-steel); } .pill-teal { background: var(--mk-teal); }
.pill-navy { background: var(--mk-navy); } .pill-gold { background: var(--mk-gold); color:#3a2a10; }
.pill-purple { background: var(--mk-purple); }
.otable td:first-child { text-align:left; }

/* 页面整体滚动区（表格多行时） */
.card .tablewrap { max-height: 540px; }
.card-full .tablewrap { max-height: 560px; }

/* 第10-18页（Phase2新增） */
.kpi-strip9 { display:grid; grid-template-columns: repeat(9,1fr); gap:6px; margin-bottom:8px; flex:0 0 auto; }
.kpi-strip9 .kpi-cell { padding:5px 6px; }
.kpi-strip9 .kpi-val { font-size:16px; }
.kpi-strip9 .kpi-label { font-size:9.5px; }
.kpi-strip9 .kpi-sub { font-size:8.5px; }
.grid2-11 { display:grid; grid-template-columns: 1.3fr 1fr; gap:12px; flex:1 1 auto; min-height:0; }
.grid3-14 { display:grid; grid-template-columns: repeat(3,1fr); gap:12px; flex:0 0 auto; margin: 8px 0; }
.ad-body { display:flex; gap:12px; flex:1; min-height:0; }
.ad-body .chartbox { flex: 1.1; }
.ad-body .tablewrap { flex: 1; }
.card-ka, .card-wk, .card-trend { min-height:0; }
.card-ka .tablewrap, .card-wk .tablewrap { max-height: 210px; }
.card-ad .tablewrap { max-height: 160px; }

/* 热力矩阵完整表格（第16-18页） */
.heat-wrap { overflow-x:auto; overflow-y:auto; max-height: 700px; flex:1; }
table.heat { width:100%; border-collapse:collapse; font-size:10.5px; }
table.heat th { background: var(--mk-navy); color:#fff; padding:4px 6px; text-align:center; white-space:nowrap; position:sticky; top:0; }
table.heat th:first-child { text-align:left; position:sticky; left:0; z-index:2; }
table.heat td:first-child { text-align:left; background:#eef1f8; font-weight:700; position:sticky; left:0; white-space:nowrap; }
table.heat td { padding:3px 5px; text-align:center; border-bottom:1px solid #eef0f3; }
table.heat tbody tr:nth-child(even) { background:#f7f8fb; }
table.heat tr.total-row td { font-weight:700; background:#e7ecf4; }
.hcell b { display:block; font-size:11.5px; line-height:1.2; }
.hcell span { display:block; font-size:9px; color:var(--mk-muted); line-height:1.2; }

/* 第14页：数据与解释边界 + 管理行动 */
.dq-grid { display:grid; grid-template-columns: repeat(2,1fr); gap:6px; margin-bottom:6px; }
.dq-cell { background:#fafbfc; border:1px solid var(--mk-border); border-radius:3px; padding:5px 8px; }
.dq-cell b { display:block; font-size:14px; color: var(--mk-navy); }
.dq-cell span { font-size:9.5px; color: var(--mk-muted); }
.action-list { font-size:11px; line-height:1.55; padding-left:18px; margin:4px 0; }
.action-list li { margin-bottom:5px; }
"""

_PRINT_CSS = """
@media print {
  body.mk-body { background:#fff; }
  .mk-toolbar { display:none; }
  .mk-pages { padding:0; gap:0; }
  .page { box-shadow:none; margin:0; page-break-after: always; }
  @page { size: 1600px 900px; margin:0; }
}
"""

_SCRIPT_TEMPLATE = """
<script>__CHART_JS_INLINE__</script>
<script>
const PDATA = __PAGE_DATA_JSON__;
const PALETTE = {navy:'#16213f', teal:'#1a7a6e', red:'#a83a3a', gold:'#b4861f', blue:'#2b6cb0', steel:'#4a6fa5', purple:'#5b3a7a', gray:'#9aa3b2'};
function fmtM(v){ return (v/1e6).toFixed(1)+'M'; }
Chart.defaults.font.family = "'PingFang SC','Microsoft YaHei',sans-serif";
Chart.defaults.font.size = 11;

function lineChart(id, labels, series, colors, opts){
  const el = document.getElementById(id); if(!el) return;
  new Chart(el, {type:'line', data:{labels, datasets: series.map((s,i)=>({label:s.label, data:s.data, borderColor:colors[i%colors.length], backgroundColor:colors[i%colors.length], tension:0.25, pointRadius:2, spanGaps:false}))}, options: Object.assign({responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'top', labels:{boxWidth:10}}}}, opts||{})});
}
function barChart(id, labels, series, colors, opts){
  const el = document.getElementById(id); if(!el) return;
  new Chart(el, {type:'bar', data:{labels, datasets: series.map((s,i)=>({label:s.label, data:s.data, backgroundColor:colors[i%colors.length]}))}, options: Object.assign({responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'top', labels:{boxWidth:10}}}}, opts||{})});
}

document.addEventListener('DOMContentLoaded', function(){
  const d = PDATA;
  // page1
  if(d.p1){
    const bt = d.p1.business_type, order=['经代业务','代理人业务','KA业务'];
    barChart('p1_chartC', order, [
      {label:'批核APE', data: order.map(k=>bt[k]?bt[k].batch/1e6:0)},
      {label:'未批核APE', data: order.map(k=>bt[k]?bt[k].unbat/1e6:0)},
      {label:'待签APE', data: order.map(k=>bt[k]?bt[k].pend/1e6:0)},
    ], [PALETTE.teal, PALETTE.red, PALETTE.gold], {indexAxis:'y'});
    lineChart('p1_chartD', d.p1.monthly_trend.labels, [
      {label:'预约APE(M)', data:d.p1.monthly_trend['预约'].map(v=>v/1e6)},
      {label:'签单APE(M)', data:d.p1.monthly_trend['签单'].map(v=>v/1e6)},
      {label:'批核APE(M)', data:d.p1.monthly_trend['批核'].map(v=>v/1e6)},
    ], [PALETTE.navy, PALETTE.teal, '#4a9e5c']);
  }
  // page2
  if(d.p2){
    const el=document.getElementById('p2_chartF');
    if(el){
      new Chart(el, {type:'bar', data:{labels:d.p2.labels, datasets:[{label:'批核APE(M)', data:d.p2.values.map(v=>v/1e6), backgroundColor:PALETTE.navy}]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}});
    }
  }
  // page3
  if(d.p3){
    lineChart('p3_chartH', d.p3.monthly_trend.labels, [
      {label:'预约APE(M)', data:d.p3.monthly_trend['预约'].map(v=>v/1e6)},
      {label:'签单APE(M)', data:d.p3.monthly_trend['签单'].map(v=>v/1e6)},
      {label:'批核APE(M)', data:d.p3.monthly_trend['批核'].map(v=>v/1e6)},
    ], [PALETTE.navy, PALETTE.teal, '#4a9e5c']);
  }
  // page4
  if(d.p4){
    const elG=document.getElementById('p4_chartG');
    if(elG){
      new Chart(elG, {type:'bubble', data:{datasets:[{label:'业务线', data:d.p4.bubbles.map(b=>({x:b.x,y:b.y,r:b.r})), backgroundColor:'rgba(43,108,176,0.55)'}]},
        options:{responsive:true, maintainAspectRatio:false,
          plugins:{legend:{display:false}, tooltip:{callbacks:{label:(ctx)=>d.p4.bubbles[ctx.dataIndex].label+' '+ctx.raw.y.toFixed(0)+'%'}}},
          scales:{x:{title:{display:true,text:'目标APE(M) →'}}, y:{title:{display:true,text:'达成率(%)'}}}}});
    }
    const elH=document.getElementById('p4_chartH');
    if(elH){
      const items=d.p4.waterfall.map(it=>({label:it.label, kind:it.kind, value:it.value/1e6}));
      let running=0; const bases=[]; const vals=[];
      items.forEach((it,i)=>{
        if(it.kind==='base'){bases.push(0); vals.push(it.value); running=it.value;}
        else if(it.kind==='final'){bases.push(0); vals.push(it.value); running=it.value;}
        else {const start=Math.min(running, running+it.value); bases.push(start); vals.push(Math.abs(it.value)); running+=it.value;}
      });
      new Chart(elH, {type:'bar', data:{labels:items.map(it=>it.label), datasets:[
        {label:'base', data:bases, backgroundColor:'rgba(0,0,0,0)'},
        {label:'值', data:vals, backgroundColor: items.map(it=>it.kind==='base'?PALETTE.gray:(it.kind==='final'?PALETTE.red:PALETTE.steel))},
      ]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{stacked:true},y:{stacked:true,title:{display:true,text:'APE(M)'}}}}});
    }
    d.p4.segments.forEach((seg,i)=>{
      const mb = d.p4.monthly_by_segment[seg];
      if(mb) lineChart('p4_seg_'+i, mb.labels, [
        {label:'预约', data:mb['预约'].map(v=>v/1e6)},
        {label:'签单', data:mb['签单'].map(v=>v/1e6)},
        {label:'批核', data:mb['批核'].map(v=>v/1e6)},
      ], [PALETTE.steel, PALETTE.teal, PALETTE.red], {plugins:{legend:{display:false}}});
    });
  }
  // page5
  if(d.p5){
    const elK=document.getElementById('p5_chartK');
    if(elK){
      new Chart(elK, {type:'doughnut', data:{labels:['已批核','未批核','待签'], datasets:[{data:[d.p5.issued,d.p5.unbat,d.p5.pend], backgroundColor:[PALETTE.teal,PALETTE.gold,PALETTE.blue]}]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}}}});
    }
    const elL=document.getElementById('p5_chartL');
    if(elL){
      barChart('p5_chartL', d.p5.labels, [
        {label:'已批核APE(M)', data:d.p5.issued_arr.map(v=>v/1e6)},
        {label:'未批核APE(M)', data:d.p5.unbat_arr.map(v=>v/1e6)},
        {label:'待签APE(M)', data:d.p5.pend_arr.map(v=>v/1e6)},
        {label:'目标缺口APE(M)', data:d.p5.gap_arr.map(v=>v/1e6)},
      ], [PALETTE.teal, PALETTE.gold, PALETTE.blue, PALETTE.gray], {indexAxis:'y', scales:{x:{stacked:true}, y:{stacked:true}}});
    }
  }
  // page6
  if(d.p6){
    lineChart('p6_chartN', d.p6.weekly_trend.labels, [
      {label:'预约', data:d.p6.weekly_trend['预约'].map(v=>v/1e6)},
      {label:'签单', data:d.p6.weekly_trend['签单'].map(v=>v/1e6)},
      {label:'递交', data:d.p6.weekly_trend['递交'].map(v=>v/1e6)},
      {label:'批核', data:d.p6.weekly_trend['批核'].map(v=>v/1e6)},
    ], [PALETTE.steel, PALETTE.teal, PALETTE.gold, PALETTE.navy], {elements:{point:{radius:1.5}}});
  }
  // page7
  if(d.p7){
    barChart('p7_chartBucket', d.p7.labels, [{label:'件数', data:d.p7.counts}], [PALETTE.purple]);
  }
  // page8
  if(d.p8){
    barChart('p8_chartU', d.p8.labels, [
      {label:'批核APE(M)', data:d.p8.batch.map(v=>v/1e6)},
      {label:'未批核APE(M)', data:d.p8.unbat.map(v=>v/1e6)},
      {label:'待签APE(M)', data:d.p8.pend.map(v=>v/1e6)},
    ], [PALETTE.teal, PALETTE.red, PALETTE.gold]);
  }
  // page9
  if(d.p9){
    lineChart('p9_chartX', d.p9.weekly_trend.labels, [
      {label:'同行预约(M)', data:d.p9.weekly_trend['预约'].map(v=>v/1e6)},
      {label:'同行签单(M)', data:d.p9.weekly_trend['签单'].map(v=>v/1e6)},
      {label:'同行批核(M)', data:d.p9.weekly_trend['批核'].map(v=>v/1e6)},
    ], [PALETTE.steel, PALETTE.teal, PALETTE.navy], {elements:{point:{radius:1.5}}});
  }
  // page10（Phase2新增）
  if(d.p10){
    const elM=document.getElementById('p10_chartMonthly');
    if(elM){
      new Chart(elM, {type:'bar', data:{labels:d.p10.monthly.labels, datasets:[
        {type:'bar', label:'批核APE(M)', data:d.p10.monthly.ape.map(v=>v/1e6), backgroundColor:PALETTE.navy, yAxisID:'y'},
        {type:'line', label:'批核件数', data:d.p10.monthly.cnt, borderColor:PALETTE.gold, backgroundColor:PALETTE.gold, yAxisID:'y1', tension:0.2},
      ]}, options:{responsive:true, maintainAspectRatio:false,
        scales:{y:{position:'left', title:{display:true,text:'APE(M)'}}, y1:{position:'right', title:{display:true,text:'件数'}, grid:{drawOnChartArea:false}}}}});
    }
    lineChart('p10_chartWeekly', d.p10.weekly.labels, [
      {label:'预约(M)', data:d.p10.weekly['预约'].map(v=>v/1e6)},
      {label:'签单(M)', data:d.p10.weekly['签单'].map(v=>v/1e6)},
      {label:'批核(M)', data:d.p10.weekly['批核'].map(v=>v/1e6)},
    ], [PALETTE.steel, PALETTE.teal, PALETTE.navy], {elements:{point:{radius:1.5}}});
    barChart('p10_chartAD', d.p10.branch.labels, [{label:'批核APE(M)', data:d.p10.branch.values.map(v=>v/1e6)}], [PALETTE.navy], {indexAxis:'y', plugins:{legend:{display:false}}});
  }
  // page11（Phase2新增）
  if(d.p11){
    lineChart('p11_chartTrend', d.p11.monthly_trend.labels, [
      {label:'预约(M)', data:d.p11.monthly_trend['预约'].map(v=>v/1e6)},
      {label:'签单(M)', data:d.p11.monthly_trend['签单'].map(v=>v/1e6)},
      {label:'批核(M)', data:d.p11.monthly_trend['批核'].map(v=>v/1e6)},
    ], [PALETTE.steel, PALETTE.teal, PALETTE.navy]);
  }
  // page12（Phase2新增）
  if(d.p12){
    lineChart('p12_chartTrend', d.p12.monthly_trend.labels, [
      {label:'预约(M)', data:d.p12.monthly_trend['预约'].map(v=>v/1e6)},
      {label:'签单(M)', data:d.p12.monthly_trend['签单'].map(v=>v/1e6)},
      {label:'批核(M)', data:d.p12.monthly_trend['批核'].map(v=>v/1e6)},
    ], [PALETTE.steel, PALETTE.teal, PALETTE.navy]);
  }
});
</script>
"""


def _page_chart_data(ctx: dict) -> dict:
    s1v, s2v, s3v, peerv = ctx["s1v"], ctx["s2v"], ctx["s3v"], ctx["peerv"]
    sb = s2v["segment_bars"]

    months_2026 = [r for r in s1v["monthly_table"] if r["month"].startswith("26-")]

    wf_order = sorted(range(len(sb["labels"])), key=lambda i: sb["issued"][i], reverse=True)
    waterfall = [{"label": "年度目标", "value": s2v["target_total"], "kind": "base"}]
    for i in wf_order:
        if sb["issued"][i] <= 0:
            continue
        waterfall.append({"label": f"{sb['labels'][i]}批核", "value": -sb["issued"][i], "kind": "seg"})
    waterfall.append({"label": "未批核", "value": -ctx["s2_unbat_total"], "kind": "seg"})
    waterfall.append({"label": "待签", "value": -ctx["s2_pend_total"], "kind": "seg"})
    final_gap = s1v["full_gap"] - ctx["s2_unbat_total"] - ctx["s2_pend_total"]
    waterfall.append({"label": "扣在途后差额", "value": final_gap, "kind": "final"})

    pipe3_total = s1v["issued_ape"] + s1v["unbat_ape"] + s1v["pend_ape"]

    l_order = sorted(range(len(sb["labels"])), key=lambda i: sb["target"][i])
    gap_arr = [max(sb["target"][i] - sb["issued"][i] - sb["unbat"][i] - sb["pend"][i], 0) for i in l_order]

    te = ctx["timeliness"]
    ka8 = ctx["ka_rank_p8"]

    return {
        "p1": {
            "business_type": s1v["business_type"],
            "monthly_trend": s1v["monthly_trend"],
        },
        "p2": {
            "labels": [r["month"] for r in months_2026],
            "values": [r["批核APE"] for r in months_2026],
        },
        "p3": {
            "monthly_trend": ctx["sunv"]["monthly_trend"],
        },
        "p4": {
            "bubbles": [
                {"x": sb["target"][i] / 1e6, "y": sb["rate"][i] * 100, "r": max(6, (sb["issued"][i] / 1e6) ** 0.5 * 2.2), "label": sb["labels"][i]}
                for i in range(len(sb["labels"]))
            ],
            "waterfall": waterfall,
            "segments": sb["labels"],
            "monthly_by_segment": s2v["monthly_by_segment"],
        },
        "p5": {
            "issued": s1v["issued_ape"], "unbat": s1v["unbat_ape"], "pend": s1v["pend_ape"],
            "labels": [sb["labels"][i] for i in l_order],
            "issued_arr": [sb["issued"][i] for i in l_order],
            "unbat_arr": [sb["unbat"][i] for i in l_order],
            "pend_arr": [sb["pend"][i] for i in l_order],
            "gap_arr": gap_arr,
        },
        "p6": {"weekly_trend": s3v["weekly_trend"]},
        "p7": {
            "labels": [r["分档"] for r in te["bucket_rows"]],
            "counts": [r["件数"] for r in te["bucket_rows"]],
        },
        "p8": {
            "labels": peerv["referrer_bar"]["labels"],
            "batch": peerv["referrer_bar"]["批核"],
            "unbat": peerv["referrer_bar"]["未批核"],
            "pend": peerv["referrer_bar"]["待签"],
        },
        "p9": {"weekly_trend": peerv["weekly_trend"]},
        "p10": {
            "monthly": ctx["bank_monthly_total"],
            "weekly": ctx["bank_v"]["weekly_trend"],
            "branch": {
                "labels": ctx["bank_v"]["branch_bar"]["labels"][:10],
                "values": ctx["bank_v"]["branch_bar"]["合计"][:10],
            },
        },
        "p11": {"monthly_trend": ctx["agent_v"]["monthly_trend"]},
        "p12": {"monthly_trend": ctx["ka_v"]["monthly_trend"]},
    }


# ======================================================================
# render()
# ======================================================================

def render(data_root, agent_version: str, source_name: str = "业绩数据底表") -> str:
    data_root = Path(data_root)
    loaded = _load_views(data_root)
    s1, s2, s3, s4, s9, s6, df = (loaded[k] for k in ("s1", "s2", "s3", "s4", "s9", "s6", "df"))
    raw_df = loaded["raw_df"]

    if s6 is None or "A-APE" not in s6:
        raise RuntimeError(
            "Mark标准报表第6/8页需要S6_市场与交叉视角（KA排名全量口径），"
            "请先跑一遍 `agent.py --s6` 生成/刷新该目录后再生成本报表。"
        )

    s1v = build_s1_view(s1)
    s2v = build_s2_view(s2)
    s3v = build_s3_view(s3)
    s4v = build_s4_view(s4)
    peerv = build_peer_view(s2, s3)
    sunv = build_sunlife_view(s1, s2, s4)

    week_full = _current_week_full(s3)
    export_date = loaded["export_date"]
    date_str = export_date.strftime("%Y-%m-%d") if export_date is not None else ""

    a_rows = {r["业务细分"]: r for _, r in s2["A"].iterrows() if r["业务细分"] != "合计"}
    s2_unbat_total = sum(num(a_rows[s]["未批核APE"]) for s in s2v["segments"] if s in a_rows)
    s2_pend_total = sum(num(a_rows[s]["待签APE"]) for s in s2v["segments"] if s in a_rows)
    s2_unbat_cnt = sum(int(num(a_rows[s]["未批核件数"])) for s in s2v["segments"] if s in a_rows)
    s2_pend_cnt = sum(int(num(a_rows[s]["待签件数"])) for s in s2v["segments"] if s in a_rows)

    sun_pipe = _sunlife_pipeline_kpi(df)
    sun_entity_table = _sunlife_entity_table(df, export_date)
    sun_product = _sunlife_product_ranking(df)
    sun_batch_cnt = int(((df["carrier_code"] == SUNLIFE_CARRIER) & (df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)).sum())
    sun_months_2026 = [m for m in sun_entity_table["months"]]
    sun_in_progress_month = sun_months_2026[-1] if sun_months_2026 else ""

    timeliness = _timeliness_corrected(df)

    ka_rank_p6 = _ka_rank_from_s6(s6, ("A-APE", "B-APE", "C-APE"), ("A-件数", "B-件数", "C-件数"), top_n=10)
    ka_rank_p6["top10_total"] = _ka_totals(ka_rank_p6["top"])
    ka_rank_p8 = _ka_rank_from_s2(s2["K"], top_n=10)

    peer_calendar_monthly = _peer_calendar_monthly(df)

    # ---- Phase2新增（第10-18页）----
    bank_v = build_bank_view(s2, s3)
    agent_v = build_agent_view(s9)
    ka_v = build_ka_view(s9)
    bk_month = _segment_calendar_current_month(df, ["BK业务"])
    agent_month = _segment_calendar_current_month(df, ["天领业务", "成事家办"])
    bank_weekly_cnt = _bank_weekly_detail_with_count(s3)
    bank_monthly_total = _bank_monthly_issue_total(s3)

    sun_premium_top10 = _sunlife_premium_ranking(df)
    sun_term_dist = _sunlife_term_distribution(df)

    peer_partner_full = _peer_partner_full(df)
    peer_referrer_full = _peer_referrer_full(df)

    unapproved_top10 = _unapproved_channel_top10(df)
    dq = _data_quality_disclosure(raw_df, df, timeliness["excluded_count"])

    event_table14 = _page14_event_table(s3, week_full)  # week_full本身就是'2026W40'原始格式

    heat_q = _heat_table(s3["B"], _recent_weeks(s3["B"]))
    heat_r = _heat_table(s3["C"], _recent_weeks(s3["C"]))
    heat_s = _heat_table(s3["D"], _recent_weeks(s3["D"]))

    ctx = {
        "s1v": s1v, "s2v": s2v, "s3v": s3v, "s4v": s4v, "peerv": peerv, "sunv": sunv,
        "date_str": date_str,
        "s2_unbat_total": s2_unbat_total, "s2_pend_total": s2_pend_total,
        "s2_unbat_cnt": s2_unbat_cnt, "s2_pend_cnt": s2_pend_cnt,
        "sun_pipe": sun_pipe, "sun_entity_table": sun_entity_table, "sun_product": sun_product,
        "sun_batch_cnt": sun_batch_cnt, "sun_in_progress_month": sun_in_progress_month,
        "timeliness": timeliness,
        "ka_rank_p6": ka_rank_p6, "ka_rank_p8": ka_rank_p8,
        "peer_calendar_monthly": peer_calendar_monthly,
        "s9": s9,
        "bank_v": bank_v, "agent_v": agent_v, "ka_v": ka_v,
        "bk_month": bk_month, "agent_month": agent_month,
        "bank_weekly_cnt": bank_weekly_cnt, "bank_monthly_total": bank_monthly_total,
        "sun_premium_top10": sun_premium_top10, "sun_term_dist": sun_term_dist,
        "peer_partner_full": peer_partner_full, "peer_referrer_full": peer_referrer_full,
        "unapproved_top10": unapproved_top10, "dq": dq,
        "event_table14": event_table14,
        "heat_q": heat_q, "heat_r": heat_r, "heat_s": heat_s,
    }

    pages_html = "".join([
        build_page1(ctx, week_full),
        build_page2(ctx, week_full),
        build_page3(ctx, week_full),
        build_page4(ctx, week_full),
        build_page5(ctx, week_full),
        build_page6(ctx, week_full),
        build_page7(ctx, week_full),
        build_page8(ctx, week_full),
        build_page9(ctx, week_full),
        build_page10(ctx, week_full),
        build_page11(ctx, week_full),
        build_page12(ctx, week_full),
        build_page13(ctx, week_full),
        build_page14(ctx, week_full),
        build_page15(ctx, week_full),
        build_page16(ctx, week_full),
        build_page17(ctx, week_full),
        build_page18(ctx, week_full),
    ])

    import json
    page_data = _page_chart_data(ctx)
    script = _SCRIPT_TEMPLATE.replace("__CHART_JS_INLINE__", _VENDOR_CHART_JS)
    script = script.replace("__PAGE_DATA_JSON__", json.dumps(page_data, ensure_ascii=False))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Mark标准报表（程序化复刻）</title>
<style>{_CSS}{_PRINT_CSS}</style>
</head>
<body class="mk-body">
<div class="mk-toolbar">
  <div>Mark标准报表 · 程序化复刻（全18页） · PDA Agent {esc(agent_version)} · 数据源：{esc(source_name)}</div>
  <button onclick="window.print()">打印/导出PDF</button>
</div>
<div class="mk-pages">
{pages_html}
</div>
{script}
</body>
</html>
"""
    return html
