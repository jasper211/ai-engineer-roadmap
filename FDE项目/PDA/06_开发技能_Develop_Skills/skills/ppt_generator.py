#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ppt_generator.py — 从 template.pptx + S1-S9新版CSV 生成周业绩汇报PPT。

架构说明（详见 03_规划项目结构_Plan_Project_Structure/PPT生成_旧流水线映射与
新架构设计_v0.1.md）：
  - 每次运行都从干净的 template.pptx 重新生成，不是"修改上一份已生成的PPT"，
    所以可以放心用固定的段落原文做精确匹配替换（旧版update_ppt.py的SLIDE*_SUBS
    表是针对"已经被上一版脚本patch过的deck"写的，原文假设经常对不上pristine
    模板——已在开发本文件时验证过，不能直接照抄那些表，必须从当前这份
    template.pptx里重新读出真实段落文本）。
  - 图表统一用 ppt_chart_patch.patch_chart() 直接改写chart XML的numCache/
    strCache，不用python-pptx的chart.replace_data()（对本模板部分图表的
    grouping='none'类型会直接报错，chart1即是一例，已验证）。
  - So What文案本阶段不在这里生成：build_slideN()只负责把计算好的关键数字
    以外的一切补齐，So What文本框原样保留模板占位文字，留给单独的
    sowhat文案生成步骤（走LLM，见 08_设计提示词_Design_Prompts/）去二次patch。

当前进度：build_slide1() 已完整实现并用真实数据核验（模块A/B文本、模块C/D
两张图表、月度明细网格动态扩展到当前数据的全部月份）。build_slide2..11
待续，是下一阶段的工作范围。
"""
import re
from pathlib import Path

from pptx import Presentation

from skills.ppt_data_loader import num
from skills.ppt_monthly_bucket import derive_monthly_buckets
import skills.ppt_helpers as H
import skills.ppt_chart_patch as CP


MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _ym_to_label(ym: str) -> str:
    """'2026-07' -> '26-Jul'，跟模板月度趋势图现有类别标签格式一致。"""
    yr, mm = ym.split("-")
    return f"{yr[-2:]}-{MONTHS_EN[int(mm) - 1]}"


def build_slide1(prs: Presentation, s1: dict) -> dict:
    """全维度业绩分析仪表盘。s1 = ppt_data_loader.load_sheet(S1_总览仪表盘/)。
    返回一份stats字典，供后续So What生成步骤使用（数字口径跟本函数算出来的
    保持一致，避免So What另起一套计算逻辑导致文案和页面数字对不上）。"""
    slide = prs.slides[0]

    A = s1["A"]
    B = s1["B"]
    G = s1["G"]

    def a_row(key):
        r = A[A["指标"] == key].iloc[0]
        return num(r["目标APE"]), num(r["已达成APE"]), num(r["目标达成率"])

    full_target, full_achv, full_rate = a_row("2026全业务目标")
    sun_target, sun_achv, sun_rate = a_row("2026永明业务目标")
    full_gap = full_target - full_achv
    sun_gap = sun_target - sun_achv

    def b_row(key):
        r = B[B["指标行"] == key].iloc[0]
        return int(num(r["件数"])), num(r["APE"])

    issued_cnt, issued_ape = b_row("批核(2026)")
    unbat_cnt, unbat_ape = b_row("未批核(跨年)")
    pend_cnt, pend_ape = b_row("待签(跨年)")
    lost_cnt, lost_ape = b_row("流失(2026)")
    pipe_total = issued_ape + unbat_ape + pend_ape + lost_ape

    subs = [
        ("31.5%", f"{full_rate * 100:.1f}%"),
        ("350M", f"{full_achv / 1e6:.0f}M"),
        ("533 件", f"{issued_cnt:,} 件"),
        ("-763M", f"-{full_gap / 1e6:.0f}M"),
        ("已批 350M / 剩余缺口 763M", f"已批 {full_achv / 1e6:.0f}M / 剩余缺口 {full_gap / 1e6:.0f}M"),
        ("永明业务目标（976M）", f"永明业务目标（{sun_target / 1e6:,.0f}M）"),
        ("全业务目标（1,113M）", f"全业务目标（{full_target / 1e6:,.0f}M）"),
        ("30.4%", f"{sun_rate * 100:.1f}%"),
        ("已批 297M / 剩余缺口679M", f"已批 {sun_achv / 1e6:.0f}M / 剩余缺口{sun_gap / 1e6:.0f}M"),
        ("批核（生效）", "批核（生效）"),
        ("350.4M", f"{issued_ape / 1e6:.1f}M"),
        ("533 件  |  占比 66.5%", f"{issued_cnt:,} 件  |  占比 {issued_ape / pipe_total * 100:.1f}%"),
        ("167.9M", f"{unbat_ape / 1e6:.1f}M"),
        ("242 件  |  占比 30.2%", f"{unbat_cnt:,} 件  |  占比 {unbat_ape / pipe_total * 100:.1f}%"),
        ("3.9M", f"{pend_ape / 1e6:.1f}M"),
        ("12 件  |  占比 1.5%", f"{pend_cnt:,} 件  |  占比 {pend_ape / pipe_total * 100:.1f}%"),
        ("6.4M", f"{lost_ape / 1e6:.1f}M"),
        ("14 件  |  占比 1.7%", f"{lost_cnt:,} 件  |  占比 {lost_ape / pipe_total * 100:.1f}%"),
    ]
    hits, misses = H.apply_substitutions(slide, subs, tag="Slide1")

    # --- Chart 0（业务类型堆叠，经代/代理人/KA 三类 × 批核/未批核/待签） ---
    g_row = {r["业务类型"]: r for _, r in G.iterrows()}
    cat_order = ["经代业务", "代理人业务", "KA业务"]  # 对应图表类别 经代/代理人/'KA 业务'
    chart0_series = [
        [num(g_row[c]["2026批核APE"]) / 1e6 for c in cat_order],
        [num(g_row[c]["未批核APE"]) / 1e6 for c in cat_order],
        [num(g_row[c]["待签APE"]) / 1e6 for c in cat_order],
    ]
    chart0_shape = next(sh for sh in slide.shapes if sh.has_chart and sh.shape_id == 81)
    CP.patch_chart(chart0_shape.chart.part, chart0_series)

    # --- Chart 1（预约/签单/批核 月度三线趋势，2025-01至当前最新月） ---
    C, D, E = s1["C"], s1["D"], s1["E"]
    months = sorted(C["年月"].tolist())
    cat_labels = [_ym_to_label(m) for m in months]

    def monthly_series(df):
        by_month = {r["年月"]: num(r["APE"]) / 1e6 for _, r in df.iterrows()}
        return [round(by_month.get(m, 0.0), 1) for m in months]

    chart1_series = [monthly_series(C), monthly_series(D), monthly_series(E)]
    chart1_shape = next(sh for sh in slide.shapes if sh.has_chart and sh.shape_id == 86)
    CP.patch_chart(chart1_shape.chart.part, chart1_series, categories=cat_labels)

    # --- 月度明细网格（2026年各月 预约/签单/批核 APE+件数），动态列数 ---
    months_2026 = [m for m in months if m.startswith("2026-")]
    _extend_s1_monthly_grid(slide, s1, months_2026)

    stats = {
        "full_target": full_target, "full_achv": full_achv, "full_rate": full_rate, "full_gap": full_gap,
        "sun_target": sun_target, "sun_achv": sun_achv, "sun_rate": sun_rate, "sun_gap": sun_gap,
        "issued_ape": issued_ape, "issued_cnt": issued_cnt,
        "unbat_ape": unbat_ape, "unbat_cnt": unbat_cnt,
        "pend_ape": pend_ape, "pend_cnt": pend_cnt,
        "lost_ape": lost_ape, "lost_cnt": lost_cnt,
        "pipe_total": pipe_total,
        "business_type": {c: {"batch": g_row[c]["2026批核APE"], "unbat": g_row[c]["未批核APE"], "pend": g_row[c]["待签APE"]} for c in cat_order},
        "months_2026": months_2026,
        "subs_hits": hits, "subs_misses": sorted(misses),
    }
    return stats


# 月度明细网格：Jan/Feb/Mar是模板原生列（shape_id 92/93/94为月份header,
# 100/106/113/119/126/132等为数值），Mar列的7个shape（月份header + 预约APE/件数 +
# 签单APE/件数 + 批核APE/件数）共享同一个left=9621774 EMU、width=566928 EMU——
# 这个width正好等于Jan→Feb→Mar的列间距(Jan=8487918, Feb=9054846, Mar=9621774)，
# 用它做克隆偏移量能让新列跟原生列严丝合缝对齐。
# ⚠️ col_lefts必须从JAN_LEFT起算，不能从MAR_LEFT起算——首版实现在这里犯过一次
# 索引错位bug（整体列位置右移2格，Jan/Feb原生列没被写入，Jun/Jul列没被克隆），
# 已用真实输出核验发现并修正，记录在此避免回归。
_GRID_JAN_LEFT = 8487918
_GRID_MAR_LEFT = 9621774  # 克隆源列（唯一保证7个shape完整对齐的原生列）
_GRID_COL_PITCH = 566928
_GRID_TOP_MIN = 3900000
_GRID_TOP_MAX = 6000000
_GRID_ROW_LABELS = ["预约 APE", "预约 件数", "签单 APE", "签单 件数", "批核 APE", "批核 件数"]


def _extend_s1_monthly_grid(slide, s1: dict, months_2026: list):
    """把月度明细网格扩展/重建到跟months_2026等长的列数。
    先清空base列(Jan-Mar)右侧此前克隆出来的全部列（这份template.pptx自带的
    历史遗留Apr列间距是错的，不能沿用，必须整体重新克隆），再按正确间距
    逐列克隆并写入真实数据。"""
    base_months = ["2026-01", "2026-02", "2026-03"]  # 模板原生3列
    extra_months = [m for m in months_2026 if m not in base_months]

    # 清空Mar列右侧、网格Y范围内此前克隆出来的列
    to_remove = [
        sh for sh in slide.shapes
        if sh.left is not None and sh.top is not None
        and sh.left > _GRID_MAR_LEFT + 30000
        and _GRID_TOP_MIN <= sh.top <= _GRID_TOP_MAX
    ]
    spTree = slide.shapes._spTree
    for sh in to_remove:
        spTree.remove(sh._element)

    # 重新克隆extra_months列（相对Mar偏移，落在Mar右侧第1/2/3/4列）
    for i, _ in enumerate(extra_months, start=1):
        H.clone_column_right(slide, _GRID_MAR_LEFT, x_offset=_GRID_COL_PITCH * i)

    # 写入全部2026月份（含Jan-Mar原生列 + 新克隆列）的真实数据——col_lefts从
    # JAN_LEFT起算，第0/1/2项分别对应原生Jan/Feb/Mar列，第3项起对应新克隆列
    # （新克隆列left = Mar + pitch*k，跟JAN_LEFT + pitch*(2+k)代数上相等）。
    col_lefts = [_GRID_JAN_LEFT + _GRID_COL_PITCH * i for i in range(len(months_2026))]
    # 需要重新从slide.shapes里按当前(克隆后)的left分组，因为克隆前拿到的shape引用
    # 在spTree.append之后python-pptx的shapes集合已经变化，统一reload。
    by_left = {}
    for sh in slide.shapes:
        if sh.left is None or sh.top is None:
            continue
        if not (col_lefts[0] - 30000 <= sh.left <= col_lefts[-1] + 30000):
            continue
        if not (_GRID_TOP_MIN <= sh.top <= _GRID_TOP_MAX):
            continue
        key = min(col_lefts, key=lambda L: abs(L - sh.left))
        by_left.setdefault(key, []).append(sh)

    C, D, E = s1["C"], s1["D"], s1["E"]
    row_sources = [
        ("预约 APE", C, "APE", "/1e6:.1f"),
        ("预约 件数", C, "件数", "件"),
        ("签单 APE", D, "APE", "/1e6:.1f"),
        ("签单 件数", D, "件数", "件"),
        ("批核 APE", E, "APE", "/1e6:.1f"),
        ("批核 件数", E, "件数", "件"),
    ]

    def month_val(df, ym, col):
        sub = df[df["年月"] == ym]
        if sub.empty:
            return 0.0
        return num(sub.iloc[0][col])

    for col_idx, ym in enumerate(months_2026):
        left = col_lefts[col_idx]
        shapes_here = sorted(by_left.get(left, []), key=lambda s: s.top)
        # shapes_here顺序应为 [header, 预约APE, 预约件数, 签单APE, 签单件数, 批核APE, 批核件数]
        if len(shapes_here) < 7:
            continue  # 该列shape不全（异常情况），跳过而不是报错中断整页
        header_sh = shapes_here[0]
        _set_shape_text(header_sh, _ym_to_label(ym))
        for row_i, (label, df, col, fmt) in enumerate(row_sources, start=1):
            v = month_val(df, ym, col)
            if fmt == "件":
                text = f"{int(v):,}件"
            else:
                text = f"{v / 1e6:.1f}"
            _set_shape_text(shapes_here[row_i], text)


def _set_shape_text(shape, new_text):
    """兼容python-pptx Shape对象和clone_column_right产出的原始lxml元素。"""
    if hasattr(shape, "text_frame"):
        H.set_tf(shape.text_frame, new_text)
    else:
        H.set_shape_text_xml(shape, new_text)


def _to_w(v):
    """APE原始金额（元）转万，四舍五入2位小数，跟旧版chart_updates.py::to_w同规则。"""
    return round(num(v) / 10_000, 2)


def _fmt_ape_m(v, decimals=2):
    v = num(v)
    return f"{v / 1e6:.{decimals}f}" if v > 0 else "—"


def _fmt_cnt(v):
    v = int(num(v))
    return str(v) if v > 0 else "—"


def _avg_w(ape_yuan, cnt):
    """件均（万），跟旧版update_ppt.py::_avg_w同规则：APE(元)/件数/10000。"""
    cnt = int(num(cnt))
    if cnt == 0:
        return 0.0
    return round(num(ape_yuan) / cnt / 10_000, 1)


def build_slide8(prs: Presentation, s2: dict) -> dict:
    """同行业绩 第1部分。s2 = ppt_data_loader.load_sheet(S2_业务端视角/)，需要J、K。
    对照映射报告：旧版"残差补齐算法"(_build_peer_ka_table_data)是为了从月度L-APE
    反推那些在K块里完全不存在的0批核同行KA——但新版K.csv（s2_business_view.py::
    section_k）本身就是按total_count(批核+未批核+待签件数)>0筛选、不是按批核>0
    筛选，已经是完整口径（含只有未批核/待签、没有批核的KA），残差补齐算法在新
    pipeline下没有必要，也没有对应的月度L-APE数据源可用（新版S2没有L）。"""
    slide = prs.slides[7]
    J, K = s2["J"], s2["K"]

    k_total = K[K["KEY ACCOUNT"] == "合计"].iloc[0]
    issued_ape, issued_cnt = num(k_total["2026批核APE"]), int(num(k_total["批核件数"]))
    unbat_ape, unbat_cnt = num(k_total["未批核APE"]), int(num(k_total["未批核件数"]))
    pend_ape, pend_cnt = num(k_total["待签APE"]), int(num(k_total["待签件数"]))

    subs = [
        ("136.8M", f"{issued_ape / 1e6:.1f}M"),
        ("296件  |  件均46.2万", f"{issued_cnt}件  |  件均{_avg_w(issued_ape, issued_cnt):.1f}万"),
        ("64.4M", f"{unbat_ape / 1e6:.1f}M"),
        ("121件  |  件均53.2万", f"{unbat_cnt}件  |  件均{_avg_w(unbat_ape, unbat_cnt):.1f}万"),
        ("1.5M", f"{pend_ape / 1e6:.1f}M"),
        ("5件  |  件均29.6万", f"{pend_cnt}件  |  件均{_avg_w(pend_ape, pend_cnt):.1f}万"),
    ]
    hits, misses = H.apply_substitutions(slide, subs, tag="Slide8")

    j_rows = J[J["推荐人"] != "合计"].copy()
    j_rows["_sort"] = j_rows["2026批核APE"].apply(num)
    j_rows = j_rows.sort_values("_sort", ascending=False)
    cats0 = j_rows["推荐人"].tolist()
    chart0_series = [
        [_to_w(v) for v in j_rows["2026批核APE"]],
        [_to_w(v) for v in j_rows["未批核APE"]],
        [_to_w(v) for v in j_rows["待签APE"]],
    ]
    chart0_shape = next(sh for sh in slide.shapes if sh.has_chart and sh.shape_id == 8)
    CP.patch_chart(chart0_shape.chart.part, chart0_series, categories=cats0)

    k_rows = K[K["KEY ACCOUNT"] != "合计"].copy()
    k_rows["_sort"] = k_rows["2026批核APE"].apply(num)
    k_rows = k_rows.sort_values("_sort", ascending=False)
    top10 = k_rows.head(10)
    cats1 = top10["KEY ACCOUNT"].tolist()
    chart1_series = [
        [_to_w(v) for v in top10["2026批核APE"]],
        [_to_w(v) for v in top10["未批核APE"]],
        [_to_w(v) for v in top10["待签APE"]],
    ]
    chart1_shape = next(sh for sh in slide.shapes if sh.has_chart and sh.shape_id == 17)
    CP.patch_chart(chart1_shape.chart.part, chart1_series, categories=cats1)

    table = H.find_table_by_header(slide, "KEY ACCOUNT", min_cols=9)
    data_rows = H.set_table_row_count(table, len(k_rows), header_rows=1, protect_tail_rows=1, template_row_idx=1)
    for row_obj, (_, rec) in zip(data_rows, k_rows.iterrows()):
        cells = row_obj.cells
        H.set_cell(cells[0], str(rec["KEY ACCOUNT"]))
        H.set_cell(cells[1], _fmt_ape_m(rec["2026批核APE"]))
        H.set_cell(cells[2], _fmt_cnt(rec["批核件数"]))
        H.set_cell(cells[3], _fmt_ape_m(rec["未批核APE"]))
        H.set_cell(cells[4], _fmt_cnt(rec["未批核件数"]))
        H.set_cell(cells[5], _fmt_ape_m(rec["待签APE"]))
        H.set_cell(cells[6], _fmt_cnt(rec["待签件数"]))
        H.set_cell(cells[7], _fmt_ape_m(rec["总APE"]))
        H.set_cell(cells[8], _fmt_cnt(rec["总件数"]))

    total_row = list(table.rows)[-1]
    H.set_cell(total_row.cells[0], "合计")
    H.set_cell(total_row.cells[1], _fmt_ape_m(k_total["2026批核APE"]))
    H.set_cell(total_row.cells[2], _fmt_cnt(k_total["批核件数"]))
    H.set_cell(total_row.cells[3], _fmt_ape_m(k_total["未批核APE"]))
    H.set_cell(total_row.cells[4], _fmt_cnt(k_total["未批核件数"]))
    H.set_cell(total_row.cells[5], _fmt_ape_m(k_total["待签APE"]))
    H.set_cell(total_row.cells[6], _fmt_cnt(k_total["待签件数"]))
    H.set_cell(total_row.cells[7], _fmt_ape_m(k_total["总APE"]))
    H.set_cell(total_row.cells[8], _fmt_cnt(k_total["总件数"]))

    return {
        "issued_ape": issued_ape, "issued_cnt": issued_cnt,
        "unbat_ape": unbat_ape, "unbat_cnt": unbat_cnt,
        "pend_ape": pend_ape, "pend_cnt": pend_cnt,
        "n_ka_rows": len(k_rows), "top10_ka": cats1,
        "referrer_cats": cats0,
        "subs_hits": hits, "subs_misses": sorted(misses),
    }


def _week_cols(df):
    return [c for c in df.columns if re.match(r"2026W\d+$", c)]


def _total_row(df, key_col="KEY ACCOUNT"):
    return df[df[key_col] == "合计"].iloc[0]


def _safe_val(row, col):
    """某些S3周度CSV的周列并不连续（该周全渠道0活动时,_weekly_by_ka产出的DataFrame
    干脆不含那一列，不是补0）——M/N/O_ape/_count各自缺的周不一定相同（比如O_ape
    缺W28但M_ape有），跨表按同一份周列表取值必须用这个安全访问，缺列按0处理，
    不能直接row[col]（会KeyError）。"""
    if col not in row.index:
        return 0.0
    return num(row[col])


def build_slide9(prs: Presentation, s3: dict) -> dict:
    """同行业绩 第2部分。s3 = ppt_data_loader.load_sheet(S3_执行管理端/)，需要
    J_ape/J_count（同行预约）、K_ape/K_count（同行签单）、L_ape/L_count（同行批核）。
    旧版第9页"W同行月度分析"表读的是S2的月度L-APE/M-APE/N-APE块（按KA的月度
    预约/签单/批核），新版S2没有这几个板块（映射报告第3节缺口#1），改用
    ppt_monthly_bucket把S3周度"合计"行按%U周三规则聚合成月，只能拿到"同行整体
    月度合计"，拿不到按KA拆分的月度明细——这是本函数相对旧版的口径降级，
    已记录在案（如需要按KA的月度明细，需要Jasper确认是否要重新反推一个新
    S板块）。"""
    slide = prs.slides[8]
    J_ape, J_cnt = s3["J_ape"], s3["J_count"]
    K_ape, K_cnt = s3["K_ape"], s3["K_count"]
    L_ape, L_cnt = s3["L_ape"], s3["L_count"]

    weeks = _week_cols(J_ape)
    current_week = max(weeks, key=lambda w: int(w.replace("2026W", "")))
    week_short = current_week.replace("2026", "")

    j_tot, k_tot, l_tot = _total_row(J_ape), _total_row(K_ape), _total_row(L_ape)
    j_cnt_tot, k_cnt_tot, l_cnt_tot = _total_row(J_cnt), _total_row(K_cnt), _total_row(L_cnt)

    w_app_m, w_sgn_m, w_apr_m = num(j_tot[current_week]) / 1e6, num(k_tot[current_week]) / 1e6, num(l_tot[current_week]) / 1e6
    w_app_cnt, w_sgn_cnt, w_apr_cnt = int(num(j_cnt_tot[current_week])), int(num(k_cnt_tot[current_week])), int(num(l_cnt_tot[current_week]))

    buckets = derive_monthly_buckets(weeks)
    monthly_rows = []
    for month_label, weeks_in_month in buckets:
        v1 = sum(num(j_tot[w]) for w in weeks_in_month)
        v2 = sum(num(j_cnt_tot[w]) for w in weeks_in_month)
        v3 = sum(num(k_tot[w]) for w in weeks_in_month)
        v4 = sum(num(k_cnt_tot[w]) for w in weeks_in_month)
        v5 = sum(num(l_tot[w]) for w in weeks_in_month)
        v6 = sum(num(l_cnt_tot[w]) for w in weeks_in_month)
        monthly_rows.append((month_label, v1, v2, v3, v4, v5, v6))

    cur_month = monthly_rows[-1]
    app_m_month, app_cnt_month = cur_month[1] / 1e6, int(cur_month[2])
    sgn_m_month, sgn_cnt_month = cur_month[3] / 1e6, int(cur_month[4])
    apr_m_month, apr_cnt_month = cur_month[5] / 1e6, int(cur_month[6])

    def avg_w(ape_m, cnt):
        return round(ape_m * 1e6 / cnt / 10_000, 1) if cnt else 0.0

    subs = [
        ("Y  W13 本周快报  |  同行", f"Y  {week_short} 本周快报  |  同行"),
        ("X  W01–W12 同行 预约/签单/批核 趋势（M）", f"X  W01–{week_short} 同行 预约/签单/批核 趋势（M）"),
        ("同行W13预约", f"同行{week_short}预约"),
        ("同行W13签单", f"同行{week_short}签单"),
        ("同行W13批核", f"同行{week_short}批核"),
        ("3.6M", f"{w_app_m:.2f}M"),
        ("7.5M", f"{w_sgn_m:.2f}M"),
        ("10.0M", f"{w_apr_m:.2f}M"),
        ("0.11M", f"{app_m_month:.2f}M"),
        ("0.86M", f"{sgn_m_month:.2f}M"),
        ("3.51M", f"{apr_m_month:.2f}M"),
        ("2件 | 件均5.7W", f"{app_cnt_month}件 | 件均{avg_w(app_m_month, app_cnt_month):.1f}W"),
        ("3件 | 件均28.6W", f"{sgn_cnt_month}件 | 件均{avg_w(sgn_m_month, sgn_cnt_month):.1f}W"),
        ("8件 | 件均43.8W", f"{apr_cnt_month}件 | 件均{avg_w(apr_m_month, apr_cnt_month):.1f}W"),
        ("12件| 件均29.8W", f"{w_app_cnt}件| 件均{avg_w(w_app_m, w_app_cnt):.1f}W"),
        ("21件| 件均35.94W", f"{w_sgn_cnt}件| 件均{avg_w(w_sgn_m, w_sgn_cnt):.1f}W"),
        ("32件| 件均31.39W", f"{w_apr_cnt}件| 件均{avg_w(w_apr_m, w_apr_cnt):.1f}W"),
    ]
    hits, misses = H.apply_substitutions(slide, subs, tag="Slide9")

    # --- Chart 0：X 同行周度预约/签单/批核趋势(M)，grouping=none，必须走XML直接patch ---
    cats0 = [w.replace("2026", "") for w in weeks]
    chart0_series = [
        [round(num(j_tot[w]) / 1e6, 2) for w in weeks],
        [round(num(k_tot[w]) / 1e6, 2) for w in weeks],
        [round(num(l_tot[w]) / 1e6, 2) for w in weeks],
    ]
    chart0_shape = next(sh for sh in slide.shapes if sh.has_chart)
    CP.patch_chart(chart0_shape.chart.part, chart0_series, categories=cats0)

    # --- Y 本周快报表：union(J/K/L当周>0的KA)，按当周(预约+签单+批核)合计降序，
    # 固定10行(模板原生行数)，合计=全部符合条件KA之和(不止显示的10个)，跟旧版
    # apply_w14_patches.py::patch_weekly_deck 的Y表逻辑一致 ---
    def week_col_map(df, cnt=False):
        return {str(r["KEY ACCOUNT"]).strip(): num(r[current_week]) for _, r in df.iterrows() if str(r["KEY ACCOUNT"]).strip() != "合计"}

    j_w, k_w, l_w = week_col_map(J_ape), week_col_map(K_ape), week_col_map(L_ape)
    kas = {k for d in (j_w, k_w, l_w) for k, v in d.items() if v > 0}
    ordered = sorted(kas, key=lambda k: j_w.get(k, 0) + k_w.get(k, 0) + l_w.get(k, 0), reverse=True)

    y_table = H.find_table_exact_cols(slide, "KEY ACCOUNT", 4)
    body = len(y_table.rows) - 2
    for i in range(body):
        row = y_table.rows[i + 1]
        if i < len(ordered):
            k = ordered[i]
            H.set_cell(row.cells[0], k)
            H.set_cell(row.cells[1], H.fmt_m(j_w.get(k, 0), 2))
            H.set_cell(row.cells[2], H.fmt_m(k_w.get(k, 0), 2))
            H.set_cell(row.cells[3], H.fmt_m(l_w.get(k, 0), 2))
        else:
            for c in range(4):
                H.set_cell(row.cells[c], "")
    tj, tk, tl = (sum(d.get(k, 0) for k in ordered) for d in (j_w, k_w, l_w))
    last = len(y_table.rows) - 1
    H.set_cell(y_table.rows[last].cells[0], "合计")
    H.set_cell(y_table.rows[last].cells[1], H.fmt_m(tj, 2))
    H.set_cell(y_table.rows[last].cells[2], H.fmt_m(tk, 2))
    H.set_cell(y_table.rows[last].cells[3], H.fmt_m(tl, 2))

    # --- W 同行月度分析表：动态行数=月份桶数量 ---
    w_table = H.find_table_by_header(slide, "月份", min_cols=7)
    data_rows = H.set_table_row_count(w_table, len(monthly_rows), header_rows=1, protect_tail_rows=1, template_row_idx=1)
    totals6 = [0.0] * 6
    for row_obj, (month_label, v1, v2, v3, v4, v5, v6) in zip(data_rows, monthly_rows):
        cells = row_obj.cells
        H.set_cell(cells[0], _month_label_en(month_label))
        H.set_cell(cells[1], f"{v1 / 1e6:.2f}")
        H.set_cell(cells[2], str(int(v2)))
        H.set_cell(cells[3], f"{v3 / 1e6:.2f}")
        H.set_cell(cells[4], str(int(v4)))
        H.set_cell(cells[5], f"{v5 / 1e6:.2f}")
        H.set_cell(cells[6], str(int(v6)))
        for i, v in enumerate([v1, v2, v3, v4, v5, v6]):
            totals6[i] += v
    total_row = list(w_table.rows)[-1]
    H.set_cell(total_row.cells[0], "合计")
    H.set_cell(total_row.cells[1], f"{totals6[0] / 1e6:.2f}")
    H.set_cell(total_row.cells[2], str(int(totals6[1])))
    H.set_cell(total_row.cells[3], f"{totals6[2] / 1e6:.2f}")
    H.set_cell(total_row.cells[4], str(int(totals6[3])))
    H.set_cell(total_row.cells[5], f"{totals6[4] / 1e6:.2f}")
    H.set_cell(total_row.cells[6], str(int(totals6[5])))

    return {
        "current_week": current_week, "week_short": week_short,
        "w_app_m": w_app_m, "w_sgn_m": w_sgn_m, "w_apr_m": w_apr_m,
        "monthly_rows": monthly_rows, "y_table_kas": ordered,
        "subs_hits": hits, "subs_misses": sorted(misses),
    }


def build_slide10(prs: Presentation, s2: dict, s3: dict) -> dict:
    """BK业务 第1部分。s2=load_sheet(S2_业务端视角/)需要A、O；s3=load_sheet(
    S3_执行管理端/)需要M_ape/M_count(银行预约)、N_ape/N_count(银行签单)、
    O_ape/O_count(银行批核)。
    银行月度走势×3(预约/签单/批核，按银行堆叠)用ppt_monthly_bucket对S3周度数据
    分银行聚合补齐（跟build_slide9同样的口径降级：新S2没有P/Q/R月度板块）。
    ⚠️已发现的数据口径差异：S2-O(按issue事件全量口径)合计批核APE=231.14M，
    S3-O_ape(按周聚合、周定义%U)合计=228.02M，两者相差约3.1M——推测是S3周度
    聚合口径下某些跨周边界的批核事件跟S2直接统计口径有细微差异（例如批核日期
    落在年初%U week=0会被S3的_weekly_by_ka过滤掉，S2口径不受影响）。本函数
    KPI卡片/目标对比/KA图统一用S2-O（跟旧版口径一致，S2是"准确的全量聚合"），
    月度趋势图/本周快报类走势数据用S3（唯一有时间序列的来源），这是新架构
    固有的双源设计，不是bug，但两个数字不会100%对平，已记录在案供Jasper知悉。"""
    slide = prs.slides[9]
    A, O = s2["A"], s2["O"]
    M_ape, M_cnt = s3["M_ape"], s3["M_count"]
    N_ape, N_cnt = s3["N_ape"], s3["N_count"]
    O_ape, O_cnt = s3["O_ape"], s3["O_count"]

    bk_row = A[A["业务细分"] == "BK业务"].iloc[0]
    target = num(bk_row["目标APE"])
    rate = num(bk_row["达成率"])
    o_tot = _total_row(O)
    issued_ape, issued_cnt = num(o_tot["2026批核APE"]), int(num(o_tot["批核件数"]))
    unbat_ape, unbat_cnt = num(o_tot["未批核APE"]), int(num(o_tot["未批核件数"]))
    pend_ape, pend_cnt = num(o_tot["待签APE"]), int(num(o_tot["待签件数"]))

    def month_current(df_ape, df_cnt):
        weeks = _week_cols(df_ape)
        tot_ape, tot_cnt = _total_row(df_ape), _total_row(df_cnt)
        buckets = derive_monthly_buckets(weeks)
        month_label, weeks_in_month = buckets[-1]
        ape = sum(num(tot_ape[w]) for w in weeks_in_month)
        cnt = sum(num(tot_cnt[w]) for w in weeks_in_month)
        return ape, int(cnt)

    app_m_ape, app_m_cnt = month_current(M_ape, M_cnt)
    sgn_m_ape, sgn_m_cnt = month_current(N_ape, N_cnt)
    apr_m_ape, apr_m_cnt = month_current(O_ape, O_cnt)

    def avg_w(ape_yuan, cnt):
        return round(ape_yuan / cnt / 10_000, 1) if cnt else 0.0

    # ⚠️ 顶部6张KPI卡片里有两张(BK本月预约/BK本月批核)当前恰好都显示"0.0M"，
    # 用apply_substitutions这种"旧文本→新文本"字典映射会撞key（两条规则都命中
    # 同一段落文本，后一条覆盖前一条，写错卡片）——改用旧版apply_w14_patches.py
    # 处理这一整页时就用过的"按标签文字找其正下方值框"几何定位法
    # (find_shapes_below)，按标签逐张卡片精确定位，不走文本字典匹配。
    card_specs = [
        ("BK批核", f"{issued_ape / 1e6:.1f}M", f"{issued_cnt}件 | 达成率{rate * 100:.1f}%"),
        ("BK未批核", f"{unbat_ape / 1e6:.1f}M", f"{unbat_cnt}件 |件均{avg_w(unbat_ape, unbat_cnt):.1f}W"),
        ("BK待签", f"{pend_ape / 1e6:.2f}M", f"{pend_cnt}件 | 件均{avg_w(pend_ape, pend_cnt):.1f}W"),
        ("BK 本月预约", f"{app_m_ape / 1e6:.1f}M", f"{app_m_cnt}件| 件均{avg_w(app_m_ape, app_m_cnt):.1f}W"),
        ("BK 本月签单", f"{sgn_m_ape / 1e6:.2f}M", f"{sgn_m_cnt}件| 件均{avg_w(sgn_m_ape, sgn_m_cnt):.1f}W"),
        ("BK 本月批核", f"{apr_m_ape / 1e6:.1f}M", f"{apr_m_cnt}件 | 件均{avg_w(apr_m_ape, apr_m_cnt):.1f}W"),
    ]
    hits = 0
    misses = []
    for label_text, value_text, detail_text in card_specs:
        label_sh = next((sh for sh in slide.shapes if sh.has_text_frame and sh.text_frame.text.strip() == label_text), None)
        if label_sh is None:
            misses.append(f"label:{label_text}")
            continue
        below = H.find_shapes_below(slide, label_sh, max_count=2)
        if len(below) >= 1:
            H.set_tf(below[0].text_frame, value_text)
            hits += 1
        if len(below) >= 2:
            H.set_tf(below[1].text_frame, detail_text)
            hits += 1

    # --- 月度走势×3（按银行堆叠，各自用该df自己实际存在的周列分桶） ---
    def monthly_by_bank(df_ape, shape_id):
        weeks = _week_cols(df_ape)
        buckets = derive_monthly_buckets(weeks)
        cats = [f"{int(m.split('-')[1])}月" for m, _ in buckets]
        banks = [str(n).strip() for n in df_ape["KEY ACCOUNT"] if str(n).strip() not in ("", "合计")]
        series, names = [], []
        for bank in banks:
            row = df_ape[df_ape["KEY ACCOUNT"] == bank].iloc[0]
            vals = [round(sum(num(row[w]) for w in ws) / 1e6, 2) for _, ws in buckets]
            series.append(vals)
            names.append(bank)
        sh = next(s for s in slide.shapes if s.has_chart and s.shape_id == shape_id)
        CP.patch_chart(sh.chart.part, series, categories=cats, series_names=names)
        return cats, names

    cats_app, banks_app = monthly_by_bank(M_ape, 99)
    monthly_by_bank(N_ape, 105)
    monthly_by_bank(O_ape, 114)

    # --- Chart 1：AA 银行KEY ACCOUNT分析（M单位，非万——跟chart_updates.py对
    # 照template实测确认，本页跟page8的"万"单位不同） ---
    o_rows = O[O["KEY ACCOUNT"] != "合计"].copy()
    o_rows["_sort"] = o_rows["2026批核APE"].apply(num)
    o_rows = o_rows.sort_values("_sort", ascending=False)
    cats1 = o_rows["KEY ACCOUNT"].tolist()
    chart1_series = [
        [round(num(v) / 1e6, 4) for v in o_rows["2026批核APE"]],
        [round(num(v) / 1e6, 4) for v in o_rows["未批核APE"]],
        [round(num(v) / 1e6, 4) for v in o_rows["待签APE"]],
    ]
    chart1_shape = next(sh for sh in slide.shapes if sh.has_chart and sh.shape_id == 53)
    CP.patch_chart(chart1_shape.chart.part, chart1_series, categories=cats1)

    # --- Chart 0：AB 目标达成分析（甜甜圈，已批核/目标剩余。BK若已超额完成
    # 目标(本数据集达成率115.6%>100%)，"目标剩余"不能为负——甜甜圈裁剪到0，
    # 已批核裁剪到不超过target，避免出现负数扇区这种无意义的图形） ---
    achv_m = min(issued_ape, target) / 1e6
    remain_m = max(target - issued_ape, 0) / 1e6
    donut_shape = next(sh for sh in slide.shapes if sh.has_chart and sh.shape_id == 95)
    CP.patch_chart(donut_shape.chart.part, [[round(achv_m, 1), round(remain_m, 1)]])

    # --- 民生/平安已批核 卡片 + 目标/达成率/目标缺口 卡片 ---
    def bank_row(name):
        sub = O[O["KEY ACCOUNT"] == name]
        return sub.iloc[0] if not sub.empty else None

    minsheng = bank_row("民生银行")
    pingan = bank_row("平安银行")
    subs2 = []
    if minsheng is not None:
        subs2 += [("142.1M", f"{num(minsheng['2026批核APE']) / 1e6:.1f}M"),
                   ("121件  ", f"{int(num(minsheng['批核件数']))}件  ")]
    if pingan is not None:
        subs2 += [("28.8M", f"{num(pingan['2026批核APE']) / 1e6:.1f}M"),
                   ("13件  ", f"{int(num(pingan['批核件数']))}件  ")]
    gap = target - issued_ape
    subs2 += [
        ("200M", f"{target / 1e6:.0f}M"),
        ("达成率 85.4%", f"达成率 {rate * 100:.1f}%"),
        ("29.1M", f"{gap / 1e6:.1f}M" if gap >= 0 else f"-{abs(gap) / 1e6:.1f}M"),
    ]
    hits2, misses2 = H.apply_substitutions(slide, subs2, tag="Slide10b")

    return {
        "issued_ape": issued_ape, "issued_cnt": issued_cnt, "target": target, "rate": rate,
        "unbat_ape": unbat_ape, "pend_ape": pend_ape,
        "month_app": (app_m_ape, app_m_cnt), "month_sgn": (sgn_m_ape, sgn_m_cnt), "month_apr": (apr_m_ape, apr_m_cnt),
        "monthly_cats": cats_app, "banks": banks_app,
        "o_total_s2": num(o_tot["2026批核APE"]), "o_total_s3": num(_total_row(O_ape)["合计"]),
        "subs_hits": hits + hits2, "subs_misses": sorted(set(misses) | set(misses2)),
    }


def build_slide11(prs: Presentation, s2: dict, s3: dict) -> dict:
    """BK业务 第2部分。s2=load_sheet(S2_业务端视角/)需要S(批核业绩—银行各分行APE，
    含月度+合计列，直接可用，不需要走ppt_monthly_bucket)；s3=load_sheet(
    S3_执行管理端/)需要M_ape/M_count/N_ape/N_count/O_ape/O_count(银行周度)。"""
    slide = prs.slides[10]
    S = s2["S"]
    M_ape, M_cnt = s3["M_ape"], s3["M_count"]
    N_ape, N_cnt = s3["N_ape"], s3["N_count"]
    O_ape, O_cnt = s3["O_ape"], s3["O_count"]

    # M/N/O_ape各自的周列不连续、也互不相同（某周全渠道0活动时那一周整列都不
    # 存在，不是补0——见s3_execution_view.py::_weekly_by_ka），这里取三者的
    # 并集作为图表横轴/当前周判定依据，缺列的表用_safe_val按0处理。
    weeks = sorted(set(_week_cols(M_ape)) | set(_week_cols(N_ape)) | set(_week_cols(O_ape)),
                   key=lambda w: int(w.replace("2026W", "")))
    current_week = weeks[-1]
    week_short = current_week.replace("2026", "")

    m_tot, n_tot, o_tot = _total_row(M_ape), _total_row(N_ape), _total_row(O_ape)
    m_cnt_tot, n_cnt_tot, o_cnt_tot = _total_row(M_cnt), _total_row(N_cnt), _total_row(O_cnt)
    w_app_m, w_sgn_m, w_apr_m = _safe_val(m_tot, current_week) / 1e6, _safe_val(n_tot, current_week) / 1e6, _safe_val(o_tot, current_week) / 1e6
    w_app_cnt, w_sgn_cnt, w_apr_cnt = int(_safe_val(m_cnt_tot, current_week)), int(_safe_val(n_cnt_tot, current_week)), int(_safe_val(o_cnt_tot, current_week))

    def avg_w(ape_m, cnt):
        return round(ape_m * 1e6 / cnt / 10_000, 1) if cnt else 0.0

    card_specs = [
        (" BK W13预约", f" BK {week_short}预约", f"{w_app_m:.2f}M", f"{w_app_cnt}件| 件均{avg_w(w_app_m, w_app_cnt):.1f}W"),
        ("BK W13签单", f"BK {week_short}签单", f"{w_sgn_m:.2f}M", f"{w_sgn_cnt}件| 件均{avg_w(w_sgn_m, w_sgn_cnt):.1f}W"),
        ("BK W13批核", f"BK {week_short}批核", f"{w_apr_m:.2f}M", f"{w_apr_cnt}件 | 件均{avg_w(w_apr_m, w_apr_cnt):.1f}W"),
    ]
    hits, misses = 0, []
    for label_old, label_new, value_text, detail_text in card_specs:
        label_sh = next((sh for sh in slide.shapes if sh.has_text_frame and sh.text_frame.text.strip() == label_old.strip()), None)
        if label_sh is None:
            misses.append(f"label:{label_old}")
            continue
        H.set_tf(label_sh.text_frame, label_new)
        below = H.find_shapes_below(slide, label_sh, max_count=2)
        if len(below) >= 1:
            H.set_tf(below[0].text_frame, value_text)
            hits += 1
        if len(below) >= 2:
            H.set_tf(below[1].text_frame, detail_text)
            hits += 1

    # --- Chart 1：AB 银行周度预约/签单/批核趋势(M)，grouping=none ---
    subs_title = [("AB  W01–W13 银行 预约/签单/批核  APE趋势（M）", f"AB  W01–{week_short} 银行 预约/签单/批核  APE趋势（M）")]
    hits_t, misses_t = H.apply_substitutions(slide, subs_title, tag="Slide11-title")
    hits += hits_t
    misses += sorted(misses_t)

    cats1 = [w.replace("2026", "") for w in weeks]
    chart1_series = [
        [round(_safe_val(m_tot, w) / 1e6, 2) for w in weeks],
        [round(_safe_val(n_tot, w) / 1e6, 2) for w in weeks],
        [round(_safe_val(o_tot, w) / 1e6, 2) for w in weeks],
    ]
    chart1_shape = next(sh for sh in slide.shapes if sh.has_chart and sh.shape_id == 41)
    CP.patch_chart(chart1_shape.chart.part, chart1_series, categories=cats1)

    # --- Table 1：AC 银行KA本周业绩详情(M)，固定2家银行+合计，不需要动态扩行 ---
    table = H.find_table_exact_cols(slide, "KEY ACCOUNT", 7)

    def week_val(df, name):
        sub = df[df["KEY ACCOUNT"] == name]
        return _safe_val(sub.iloc[0], current_week) if not sub.empty else 0.0

    banks = ["民生银行", "平安银行"]
    totals7 = [0.0] * 6
    for row_idx, bank in enumerate(banks, start=1):
        vals = [
            week_val(M_ape, bank), week_val(M_cnt, bank),
            week_val(N_ape, bank), week_val(N_cnt, bank),
            week_val(O_ape, bank), week_val(O_cnt, bank),
        ]
        row = table.rows[row_idx]
        H.set_cell(row.cells[0], bank)
        H.set_cell(row.cells[1], f"{vals[0] / 1e6:.2f}M")
        H.set_cell(row.cells[2], str(int(vals[1])))
        H.set_cell(row.cells[3], f"{vals[2] / 1e6:.2f}M")
        H.set_cell(row.cells[4], str(int(vals[3])))
        H.set_cell(row.cells[5], f"{vals[4] / 1e6:.2f}M")
        H.set_cell(row.cells[6], str(int(vals[5])))
        for i, v in enumerate(vals):
            totals7[i] += v
    last = list(table.rows)[-1]
    H.set_cell(last.cells[0], "银行合计")
    H.set_cell(last.cells[1], f"{totals7[0] / 1e6:.2f}M")
    H.set_cell(last.cells[2], str(int(totals7[1])))
    H.set_cell(last.cells[3], f"{totals7[2] / 1e6:.2f}M")
    H.set_cell(last.cells[4], str(int(totals7[3])))
    H.set_cell(last.cells[5], f"{totals7[4] / 1e6:.2f}M")
    H.set_cell(last.cells[6], str(int(totals7[5])))

    # --- Chart 0：AD 各分行2026年批核APE业绩排名(M)。直接用S2-S(批核业绩—银行
    # 各分行APE，已含月度+合计列)的"合计"列，过滤>0、降序——旧版
    # apply_w14_patches.py同样直接读S-APE块的合计列、不做任何分行名归并/聚合，
    # 新版S.csv的分行粒度比旧模板存档数据更细(平安香港拆到具体银行经理)，
    # 是数据本身的自然演变，不是需要修的口径问题。 ---
    s_rows = S[S["合作伙伴(分行)"] != "合计"].copy()
    s_rows["_tot"] = s_rows["合计"].apply(num)
    s_rows = s_rows[s_rows["_tot"] > 0].sort_values("_tot", ascending=False)
    cats0 = s_rows["合作伙伴(分行)"].tolist()
    chart0_series = [[round(v / 1e6, 2) for v in s_rows["_tot"]]]
    chart0_shape = next(sh for sh in slide.shapes if sh.has_chart and sh.shape_id == 8)
    CP.patch_chart(chart0_shape.chart.part, chart0_series, categories=cats0)

    return {
        "current_week": current_week, "week_short": week_short,
        "w_app_m": w_app_m, "w_sgn_m": w_sgn_m, "w_apr_m": w_apr_m,
        "n_branches": len(cats0), "top_branch": cats0[0] if cats0 else None,
        "subs_hits": hits, "subs_misses": sorted(set(misses)),
    }


def _month_label_en(ym: str) -> str:
    yr, mm = ym.split("-")
    return f"{MONTHS_EN[int(mm) - 1]}-{yr[-2:]}"


def generate(template_path, data_root, out_path, sheets: list = None) -> dict:
    """从template_path + data_root(07_接入记忆_Integrate_Memory/data/)生成PPT，
    存到out_path。返回{slide_name: stats}供上层打印摘要/后续So What生成使用。
    sheets: 需要加载的S{n}文件夹名列表，None表示全部加载（当前只有build_slide1
    实现了，加载全部S1-S9只是为了给后续build_slide2..11留好数据入口）。"""
    from skills.ppt_data_loader import load_all

    prs = Presentation(str(template_path))
    data = load_all(data_root, sheets=sheets)

    all_stats = {}
    if "S1_总览仪表盘" in data:
        all_stats["slide1"] = build_slide1(prs, data["S1_总览仪表盘"])
    if "S2_业务端视角" in data:
        all_stats["slide8"] = build_slide8(prs, data["S2_业务端视角"])
    if "S3_执行管理端" in data:
        all_stats["slide9"] = build_slide9(prs, data["S3_执行管理端"])
    if "S2_业务端视角" in data and "S3_执行管理端" in data:
        all_stats["slide10"] = build_slide10(prs, data["S2_业务端视角"], data["S3_执行管理端"])
        all_stats["slide11"] = build_slide11(prs, data["S2_业务端视角"], data["S3_执行管理端"])

    prs.save(str(out_path))
    return all_stats
