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
from pathlib import Path

from pptx import Presentation

from skills.ppt_data_loader import num
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

    prs.save(str(out_path))
    return all_stats
