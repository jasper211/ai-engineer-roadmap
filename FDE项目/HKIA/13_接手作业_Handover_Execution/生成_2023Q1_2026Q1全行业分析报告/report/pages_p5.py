#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pages_p5.py —— Part 5 公司层：谁捕获"""
from report_lib import (pg, H1, H2, H3, P, LEAD, INS, SPEC, WARN, NOTE,
                        CHART, BAR, TAG, table, fmt_hkd, fmt_int, fmt_rate, yi,
                        mval, series, yval, rankings_for, increments_for)

def _rank_table(metric, limit=10, add_growth=True):
    rs = rankings_for(metric)[:limit]
    rows = []
    for r in rs:
        if add_growth:
            rows.append([r["rank"], r["entity_name"], fmt_hkd(r["current_value"]),
                         fmt_rate(r["market_share"]) if r["market_share"] else "—",
                         fmt_rate(r["growth"]) if r["growth"] else "—", r["gate"] or "—"])
        else:
            rows.append([r["rank"], r["entity_name"], fmt_hkd(r["current_value"]),
                         fmt_rate(r["market_share"]) if r["market_share"] else "—",
                         fmt_rate(r["growth"]) if r["growth"] else "—"])
    hdr = ["#","公司","2026Q1 规模","市场占比","同比","gate"] if add_growth else ["#","公司","2026Q1 规模","市场占比","同比"]
    return table(hdr, rows)

def _rank_bars(metric, n=5):
    rs = rankings_for(metric)[:n]
    maxv = max((r["current_value"] or 0) for r in rs) or 1
    out = ""
    for r in rs:
        out += BAR(r["entity_name"], (r["current_value"] or 0)/maxv*100, fmt_hkd(r["current_value"]))
    return out

def p26_rank_single():
    return pg("公司层 · 个人整付 NOP 排名", H1("公司层（一）个人新造整付（NOP）2026Q1 排名") + LEAD(
        "整付口径下，2026Q1 前 3 家合计占市场约 55.5%（HSBC Life / FWD Bermuda / Manulife International），HSBC Life 居首（27.3%）。") +
        H2("2026Q1 整付 NOP Top10") +
        CHART("个人新造整付 Top5", _rank_bars("NB_IND_TOTAL_SINGLE_PREMIUM", 5), "绝对值（亿HK$）见右栏。") +
        _rank_table("NB_IND_TOTAL_SINGLE_PREMIUM", 10) +
        WARN("Chubb Life 整付同比 +44.9 倍（基数 4,786 万→21.9 亿）、BOC LIFE +148.6 倍——均属<b>基数过小/单笔事件</b>，必须按 C 级复核，不以同比作为增长证明（见 P31）。") +
        INS("整付由少数公司高度集中：Top3 超五成。HSBC Life 占市场增量贡献 34%（见 P29），是整付扩张最大推手。"),
        tag="p")

def p27_rank_ape():
    return pg("公司层 · 个人年度化 APE 排名", H1("公司层（二）个人新造年度化（APE）2026Q1 排名") + LEAD(
        "年度化口径下，规模结构较整付不同——HSBC Life（25.4%）与 BOC LIFE（21.1%）领先，AIA International 第三（9.4%）。Top3 合计约 55.8%。") +
        H2("2026Q1 年度化 APE Top10") +
        CHART("个人新造年度化 Top5", _rank_bars("NB_IND_TOTAL_ANNUALIZED_PREMIUM", 5), "绝对值（亿HK$）见右栏。") +
        _rank_table("NB_IND_TOTAL_ANNUALIZED_PREMIUM", 10) +
        SPEC("整付 vs 年度化<b>双口径并列读排名</b>：HSBC Life 双口径都领先，BOC LIFE 在年度化跃升至第二、但整付仅第七——不同口径回答不同竞争力问题。") +
        INS("年度化领先者（HSBC/BOC/AIA）反映持续期缴能力，与整付大户（HSBC/FWD/Manulife）部分重叠但不完全一致，构成“价值型”公司画像。"),
        tag="p")

def p28_rank_inforce():
    return pg("公司层 · 个人有效保单数排名", H1("公司层（三）个人有效保单数 2026Q1 排名") + LEAD(
        "有效存量视角，AIA International（第一）、Prudential（第二）、Manulife（第三）居前——存量格局由<b>期缴/历史积累</b>主导，与整付新造格局不同。") +
        H2("2026Q1 有效保单数 Top10") +
        CHART("个人有效保单数 Top5", _rank_bars("IF_IND_TOTAL_POLICIES", 5), "保单数（张）见右栏。") +
        _rank_table("IF_IND_TOTAL_POLICIES", 10, add_growth=True) +
        INS("有效保单数代表<b>承保人口基础</b>；其与整付新造格局的反差说明：新造整付集中户并不一定持有最大存量，存量与增量是两个维度。"),
        tag="p")

def p29_increment():
    return pg("公司层 · 增量贡献分解", H1("公司层（四）增量贡献分解：2025Q1→2026Q1 谁捕获了增长") + LEAD(
        "贡献定义为 <b>公司绝对变化 ÷ 市场绝对变化</b>；正值公司可合计 >100%（当其他公司下滑）。HSBC 是整付与年度化增量的共同最大贡献者。") +
        H2("个人新造整付 NOP · 增量贡献") +
        _increment_table("NB_IND_TOTAL_SINGLE_PREMIUM") +
        H2("个人新造年度化 APE · 增量贡献") +
        _increment_table("NB_IND_TOTAL_ANNUALIZED_PREMIUM") +
        INS("HSBC Life 占整付增量 34%、年度化增量 62%——是本期扩张<b>收敛于一家</b>的信号；增量高度集中放大了单家公司的市场影响力与集中风险。"),
        tag="p")

def _increment_table(metric, limit=8):
    rs = increments_for(metric)[:limit]
    rows = []
    for r in rs:
        contrib = r["contribution"]
        rows.append([r["rank"], r["entity_name"], fmt_hkd(r["prior_value"]), fmt_hkd(r["current_value"]),
                     fmt_hkd(r["absolute_change"]), (fmt_rate(contrib) if contrib is not None else "—")])
    return table(["#","公司","2025Q1","2026Q1","绝对变化","贡献占比"], rows)

def p30_transfer():
    return pg("公司层 · 转移事件与连续", H1("公司层（五）公司转移事件：2026Q1 连续性桥接") + LEAD(
        "2026Q1 Canada Life（两家法人）将香港长期业务转移至 MyPace Life——任何公司级增长解读必须先做转移桥，否则会把<b>重组迁移误读为有机增长</b>。") +
        table(["公司","2025Q1→2026Q1 指标","增长","处理"],
              [["Canada Life→MyPace","有效保单数","-5.8%","转移桥：口径/范围事件，非经营退坡"],
               ["Canada Life→MyPace","保额/年金","-26.5%","转移桥：同上"],
               ["Canada Life→MyPace","整付保费应收","-25.6%","转移桥：同上"],
               ["Canada Life→MyPace","非整付保费应收","-13.8%","转移桥：同上"]]) +
        SPEC("转移事件在排名/gate 中已标记；凡涉 Canada/MyPace 的同比必须注明转移桥，禁止当作有机经营变化。") +
        INS("此类碎片化既有法人（两 Canada Life）合并入单体的行为，会令单个法人同比失真——报告全篇以<b>lineage 桥接后的口径</b>解读公司层。"),
        tag="p")

def p31_outlier():
    return pg("公司层 · 异常复核清单", H1("公司层（六）异常复核清单：不把异常当趋势") + LEAD(
        "凡出现极端同比，本报告一律列出并标注复核级别，不自动纳入“增长”叙事。") +
        table(["公司","指标","2026Q1 同比","复核说明","证据级别"],
              [["Chubb Life HK","个人整付 NOP","+44.9 倍","基数 4,786万→21.9亿，单笔事件","C · 待背景"],
               ["BOC LIFE","个人整付 NOP","+148.6 倍","基数极低","C · 待背景"],
               ["Canada→MyPace","多项有效指标","-13.8%～-26.5%","转移桥事件","A · 已桥接"],
               ["团体受保人(市场)","NB_GROUP_LIVES","-84.9%","2025 异常峰值回落","需范围复核"]]) +
        WARN("这些异常存在于监管统计中，真实但口径敏感；在取得外部事件证据/公司公告前，一律只作<a>级量值</a>描述、不做经营结论。") +
        INS("对 KPI 异常公司的最佳态度：承认可见、标注风险、等待外部证据——这是对接手前“A9 重大公司变动背景待接入”一事的如实承接。"),
        tag="p")
