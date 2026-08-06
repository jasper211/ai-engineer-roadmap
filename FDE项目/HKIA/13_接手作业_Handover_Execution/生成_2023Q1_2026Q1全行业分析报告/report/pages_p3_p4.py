#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pages_p3_p4.py —— Part 2 口径合同 + Part 3 全行业总览 + Part 4 三大业务类"""
from report_lib import (pg, H1, H2, H3, P, LEAD, INS, SPEC, WARN, NOTE,
                        CHART, BAR, TAG, table, fmt_hkd, fmt_int, fmt_rate, yi,
                        mval, series, yval, rankings_for, increments_for)

# 基准期间
Q = ["2023Q1", "2024Q1", "2025Q1", "2026Q1"]

# ---------- Part 2 · 口径合同 ----------
def p09_time():
    return pg("口径合同 · 时间与 Baseline", H1("数据与口径（一）时间合同：Baseline 八字段锁定") + LEAD(
        "模板要求 Baseline 一次锁定八个字段，边际概念才有业务含义。本报告窗口 <b>2023Q1→2026Q1</b>，主证据线为<b>同季同比</b>。") +
        table(["字段","本报告锁定值"],
              [["起点 / 终点","2023Q1（疫情后恢复期起点） / 2026Q1（最新同季）"],
               ["频率","季度（1–3 月）· 不用于年化"],
               ["同期规则","Q1 只比 Q1（2023Q1→24Q1→25Q1→26Q1）"],
               ["对象集","香港长期保险三大类（个人/团体/退休）市场层"],
               ["分母","市场总额（分口径）"],
               ["口径","NOP 与 APE 并列（个人）"],
               ["断点","2024 起表式/公司范围变化（RBC 断点），双链处理"],
               ["反事实","维持起点结构下的假想路径（量价分解用）"]]) +
        WARN("严禁将 2026Q1 除以其前一全年或混用跨期口径作为增长；本报告一切增长均在<b>同季同比</b>下定义。"),
        tag="p")

def p10_breakpoint():
    return pg("口径合同 · 断点双链", H1("数据与口径（二）断点控制：2024 监管表式变化须保留双链") + LEAD(
        "模板指出 2024 起香港实施新的财务报告标准（RBC 相关表式/公司范围变化），制造非经营性断点。<b>官方市场链</b>与<b>公司加总链</b>需并列，不能强行合成一个“唯一数字”。") +
        SPEC("对账边界：2023 前两链可严格对账；2024–2025 存在系统差（NOP +12–13%、annualized +3.2–3.6%），公司比较仍可用但不可声称零偏差。") +
        table(["时期","官方市场链","公司加总链","处理"],
              [["2023Q1","市场总量（本报告主链）","公司逐家加总","两链一致，用于规模与份额"],
               ["2024Q1–2026Q1","市场总量（主链）","公司比较（捕获主链）","并列呈现差异，不做平滑掩盖"]]) +
        INS("本报告以<b>市场总量为主链</b>判断规模，以<b>公司层</b>判断捕获；断点差异如实声明，不掩盖。"),
        tag="p")

def p11_measure():
    return pg("口径合同 · 多口径 NOP/APE", H1("数据与口径（三）口径合同：NOP 看现金规模，APE 看持续化价值") + LEAD(
        "模板：NOP（年度化+整付）看现金规模，APE（年度化+10%×整付）看持续化价值代理。两者分工，不二选一。") +
        table(["口径","公式","回答的问题","对整付敏感度"],
              [["NOP","annualized + single","市场吸收多少新造保费（现金规模）","高"],
               ["APE","annualized + 10% × single","可比较的持续化价值代理","低"]]) +
        SPEC("当整付贡献高时，NOP 与 APE 方向可能分歧；标题必须主动写出“规模强、价值弱”或相反，不能只报其中一个。") +
        INS("同一增量在 NOP 口径可能占七成、在 APE 口径不足两成（模板 70.1% vs 19.0% 案例）——本报告个人业务将<b>双口径并列</b>呈现。"),
        tag="p")

def p12_source():
    return pg("口径合同 · 数据来源与认证", H1("数据与口径（四）数据来源与认证状态") + LEAD(
        "全部数据来自 <b>HKIA（香港保险业监管局）长期业务临时统计</b>，经接手前标准化为认证资产。") +
        table(["资产","期间","角色","认证"],
              [["市场核心事实","2023Q1–2026Q1","市场总量（个人/团体/退休）","provisional"],
               ["公司事实层","2023Q1–2026Q1","18 指标 × 公司级","provisional · 公司事实"],
               ["同比表","2023Q1→26Q1","同季同比、量价","calculable"],
               ["排名/增量","2025Q1→26Q1","2026Q1 公司排名与增量贡献","formula-verified"]]) +
        NOTE("2013–2023 官方市场链与公司加总链零偏差；2024 后存在 RBC 断点（见 P10）。2025Q4 提供 2025 全年 provisional 视图，本报告主证据线以同季为主。") +
        INS("本报告每个数字均可回源到标准化事实层；缺失值保留为空、绝不补零（见数据子库 missing_policy）。"),
        tag="p")

# ---------- Part 3 · 全行业总览 ----------
def _overview_market_series():
    """计算三大类在市场层的代表指标序列（亿HK$）。"""
    nb_ind_single = series("NB_IND_TOTAL_SINGLE_PREMIUM")
    nb_ind_ape = series("NB_IND_TOTAL_ANNUALIZED_PREMIUM")
    nb_group_ape = series("NB_GROUP_ANNUALIZED_PREMIUM")
    ret_single = series("IF_RETIREMENT_SINGLE_CONTRIBUTIONS")
    ret_nonsingle = series("IF_RETIREMENT_NON_SINGLE_CONTRIBUTIONS")
    return (nb_ind_single, nb_ind_ape, nb_group_ape, ret_single, ret_nonsingle)

def p13_total():
    single, ape, gape, rsingle, rns = _overview_market_series()
    # KPI 卡
    kpis = "".join([
        f"<div class='kpi'><div class='k'>个人新造整付保费 · 2026Q1</div><div class='v'>{fmt_hkd(single['2026Q1'])}</div><div class='d up'>{fmt_rate(yval('2025Q1','2026Q1','NB_IND_TOTAL_SINGLE_PREMIUM')['growth_rate'])} YoY</div></div>",
        f"<div class='kpi'><div class='k'>个人新造年度化保费 · 2026Q1</div><div class='v'>{fmt_hkd(ape['2026Q1'])}</div><div class='d up'>{fmt_rate(yval('2025Q1','2026Q1','NB_IND_TOTAL_ANNUALIZED_PREMIUM')['growth_rate'])} YoY</div></div>",
        f"<div class='kpi'><div class='k'>退休供款合计 · 2026Q1</div><div class='v'>{fmt_hkd((rsingle['2026Q1'] or 0)+(rns['2026Q1'] or 0))}</div></div>",
    ])
    rows = []
    for mname, mkey in [("个人整付 NOP","NB_IND_TOTAL_SINGLE_PREMIUM"),
                        ("个人年度化 APE","NB_IND_TOTAL_ANNUALIZED_PREMIUM"),
                        ("团体年度化 APE","NB_GROUP_ANNUALIZED_PREMIUM"),
                        ("退休单项供款","IF_RETIREMENT_SINGLE_CONTRIBUTIONS"),
                        ("退休非单项供款","IF_RETIREMENT_NON_SINGLE_CONTRIBUTIONS")]:
        s = series(mkey)
        yr = yval("2025Q1","2026Q1",mkey)
        rows.append([mname,
                     fmt_hkd(s["2023Q1"]), fmt_hkd(s["2024Q1"]), fmt_hkd(s["2025Q1"]), fmt_hkd(s["2026Q1"]),
                     fmt_rate(yr["growth_rate"]) if yr else "—"])
    return pg("全行业总览 · 市场规模", H1("全行业总览（一）市场规模：三大类同季序列") + LEAD(
        "香港长期保险 2023Q1 至 2026Q1 市场总量在个人业务上显著扩张，退休计划的供款体量亦具规模。下表为市场层五条代表指标线的同季序列。") +
        H2("关键概览 KPI") + f"<div class='kpis'>{kpis}</div>" +
        H2("市场层指标序列（同上季）") +
        table(["指标","2023Q1","2024Q1","2025Q1","2026Q1","25→26Q1 同比"], rows) +
        INS("个人整付保费 2026Q1 达 {}，同比 +{}；同季序列显示 2024→2026 市场扩张明显加速。".format(
            fmt_hkd(single["2026Q1"]), fmt_rate(yval("2025Q1","2026Q1","NB_IND_TOTAL_SINGLE_PREMIUM")["growth_rate"]))) +
        NOTE("2025Q4 提供全年 provisional 视图，但本报告主证据线为同季同比，不作年化外推。"),
        tag="p")

def p14_structure():
    single = series("NB_IND_TOTAL_SINGLE_PREMIUM")
    ape = series("NB_IND_TOTAL_ANNUALIZED_PREMIUM")
    b23 = single["2023Q1"] or 0
    b26 = single["2026Q1"] or 0
    cap_ratio = f"{b26/b23:.1f} 倍" if b23 else "—"
    return pg("全行业总览 · 结构", H1("全行业总览（二）结构：三大类在整体中的位置") + LEAD(
        "监管数据以“个人/团体/退休”为统计主干。个人新造业务为长期保险主力；整付（NOP）口径规模在 2023–2026Q1 间扩张最显著。") +
        CHART("个人新造整付保费（NOP）：2023Q1 vs 2026Q1",
              BAR("2023Q1", 100, fmt_hkd(b23)) + BAR("2026Q1", 100*min(b26/(b23 or 1),3.0), fmt_hkd(b26)),
              "左条 100 基准，右条按 2026/2023 相对比例绘制，绝对额以右侧数值为准。") +
        table(["期间","个人整付 NOP","累计增幅"],
              [["2023Q1", fmt_hkd(b23), "—"],
               ["2026Q1", fmt_hkd(b26), cap_ratio]]) +
        SPEC("本屏结构判断仅覆盖三大类可用口径：个人（整付/年度化/有效）、团体（保单/受保人/年度化）、退休（基金/供款）。不在维度内强加产品/渠道结构。") +
        INS("从 2023Q1 的 {} 到 2026Q1 的 {}，个人整付保费累计约 {}，是全期规模扩张的核心变量；完整结构读法见各业务类篇。".format(
            fmt_hkd(b23), fmt_hkd(b26), cap_ratio)),
        tag="p")

def p15_yoy():
    rows = []
    pairs = [("2023Q1","2024Q1"),("2024Q1","2025Q1"),("2025Q1","2026Q1")]
    for mkey, mlabel in [("NB_IND_TOTAL_SINGLE_PREMIUM","个人整付 NOP"),
                         ("NB_IND_TOTAL_ANNUALIZED_PREMIUM","个人年度化 APE"),
                         ("IF_RETIREMENT_SINGLE_CONTRIBUTIONS","退休单项供款")]:
        r = []
        for fr,to in pairs:
            y = yval(fr,to,mkey)
            r.append(fmt_rate(y["growth_rate"]) if y else "—")
        rows.append([mlabel]+r)
    return pg("全行业总览 · 同季同比全景", H1("全行业总览（三）同季同比全景") + LEAD(
        "三大类代表指标的三段一年期同比（2023→24、24→25、25→26），观察增长节奏。") +
        table(["指标","23→24Q1","24→25Q1","25→26Q1"], rows) +
        H3("增长解读") + INS("个人整付增速逐年抬升（24→25 与 25→26 提速），年度化 APE 增速明显低于整付，提示<b>增长质量偏向现金规模</b>、由整付驱动。") +
        SPEC("同比仅在同季口径下可比较；NOP/APE 分歧本身是结构信号，见个人业务篇。") ,
        tag="p")

# ---------- Part 4 · 个人业务 ----------
def p16_ind_total():
    single = series("NB_IND_TOTAL_SINGLE_PREMIUM")
    ape = series("NB_IND_TOTAL_ANNUALIZED_PREMIUM")
    pol = series("IF_IND_TOTAL_POLICIES")
    rows = [
        ["新造整付 NOP", fmt_hkd(single["2023Q1"]), fmt_hkd(single["2026Q1"]),
         fmt_rate((single["2026Q1"]/single["2023Q1"]-1) if single["2023Q1"] else None),
         fmt_rate(yval("2025Q1","2026Q1","NB_IND_TOTAL_SINGLE_PREMIUM")["growth_rate"])],
        ["新造年度化 APE", fmt_hkd(ape["2023Q1"]), fmt_hkd(ape["2026Q1"]),
         fmt_rate((ape["2026Q1"]/ape["2023Q1"]-1) if ape["2023Q1"] else None),
         fmt_rate(yval("2025Q1","2026Q1","NB_IND_TOTAL_ANNUALIZED_PREMIUM")["growth_rate"])],
    ]
    return pg("个人业务 · 总量与双口径", H1("个人业务（一）新造总量：NOP 与 APE 双口径") + LEAD(
        "个人业务是长期保险核心。2023Q1→2026Q1 新造整付（NOP）从 {} 升至 {}，年度化（APE）从 {} 升至 {}；双口径升幅差异显著。".format(
            fmt_hkd(single["2023Q1"]), fmt_hkd(single["2026Q1"]), fmt_hkd(ape["2023Q1"]), fmt_hkd(ape["2026Q1"]))) +
        table(["指标","2023Q1","2026Q1","累计增幅","25→26Q1同比"], rows) +
        SPEC("NOP 对整付高度敏感，APE 用年度化+10%×整付削弱整付放大；双口径分歧即现金规模与持续化价值的落差。") +
        INS("从 NOP 看规模做了 {} 倍、从 APE 看价值仅做 {} 倍 —— 个人增长主要靠<b>整付现金扩张</b>（规模强、价值弱）。".format(
            (single["2026Q1"]/single["2023Q1"]) if single["2023Q1"] else 0,
            (ape["2026Q1"]/ape["2023Q1"]) if ape["2023Q1"] else 0)) ,
        tag="p")

def p17_ind_measure():
    single = series("NB_IND_TOTAL_SINGLE_PREMIUM")
    ape = series("NB_IND_TOTAL_ANNUALIZED_PREMIUM")
    # NOP增量 vs APE增量
    dnop = (single["2026Q1"] or 0) - (single["2023Q1"] or 0)
    dape = (ape["2026Q1"] or 0) - (ape["2023Q1"] or 0)
    rows = [[ "新造整付贡献", fmt_hkd(single["2023Q1"]), fmt_hkd(single["2026Q1"]), fmt_hkd(dnop)],
            [ "新造年度化贡献", fmt_hkd(ape["2023Q1"]), fmt_hkd(ape["2026Q1"]), fmt_hkd(dape)]]
    return pg("个人业务 · 双口径落差", H1("个人业务（二）NOP 增量的现金与价值读法") + LEAD(
        "模板案例：同一现金增量在价值标准化后权重显著下降（70.1% vs 19.0%）。本报告个人整付口径的规模价值落差与此一致。") +
        table(["分项","2023Q1","2026Q1","期间增量"], rows) +
        WARN("此处的“增量贡献”仅就个人新造两条口径描述，不构成产品/渠道归因；价值判断仍需利润、资本与持续率验证（C 级）。") +
        INS("个人整付口径现金增量 {}，但价值（APE）视角明显小于现金视角——凡讨论“增长质量”，必须把整付与期交分开读。".format(fmt_hkd(dnop))),
        tag="p")

def p18_ind_quantity_price():
    # 用整付保费 ÷ 保单数近似件均（个人新造整付 vs 全保单）——说明量价分解的机械框架
    single = series("NB_IND_TOTAL_SINGLE_PREMIUM")
    pol = series("IF_IND_TOTAL_POLICIES")
    row = [[ "2023Q1", fmt_hkd(single["2023Q1"]), fmt_int(pol["2023Q1"])],
           [ "2026Q1", fmt_hkd(single["2026Q1"]), fmt_int(pol["2026Q1"])]]
    return pg("个人业务 · 量价分解", H1("个人业务（三）量价分解：数量 vs 件均（机械分解框架）") + LEAD(
        "模板用 Shapley 机械分解展示增长来自<b>保单数量</b>还是<b>件均</b>。本报告个人数据仅能提供保费与保单总量的机械近似，不作严格 Shapley（需保单数与整付保单匹配口径）。") +
        table(["期间","新造整付 NOP","有效保单数（近似量）"], row) +
        SPEC("跨 2023 到 2026 的保单数与整付保费非同一颗粒（有效存量 vs 新造流量），此处仅作<b>趋势方向</b>参照，不作精确量价贡献。") +
        WARN("模板严格量价分解（保单 +77.1bn / 件均 +33.8bn）要求整付保单数口径；当前资产未落整付保单数，记为 B/C 待补，绝不以有效保单替代计算贡献。") +
        INS("新造整付保费增速显著快于有效保单存量增速，方向上更接近“件均推动”，但精确分解需整付保单数据（待补齐）。"),
        tag="p")

def p19_ind_trend():
    pairs = [("2023Q1","2024Q1"),("2024Q1","2025Q1"),("2025Q1","2026Q1")]
    seq = [yval(a,b,"NB_IND_TOTAL_SINGLE_PREMIUM")["growth_rate"] for a,b in pairs]
    seq2 = [yval(a,b,"NB_IND_TOTAL_ANNUALIZED_PREMIUM")["growth_rate"] for a,b in pairs]
    tbl = [["整付 NOP同比"]+[fmt_rate(x) for x in seq],
           ["年度化 APE同比"]+[fmt_rate(x) for x in seq2]]
    return pg("个人业务 · 趋势", H1("个人业务（四）趋势与断点：同季同比节奏") + LEAD("个人新造三段一年期同比，观察增长节奏与口径分歧随时间的演变。") +
        table(["同比段","23→24Q1","24→25Q1","25→26Q1"], tbl) +
        INS("整付 NOP 同比自 24→25 起维持在 70%+，而 APE 同比仅 9–22%，提示<b>整付主导的现金扩张在 2024 后成为常态</b>。") +
        NOTE("季度信号只用于验证方向，不替代全年结论；2025 全年为 provisional 状态，待完整确认。"),
        tag="p")
