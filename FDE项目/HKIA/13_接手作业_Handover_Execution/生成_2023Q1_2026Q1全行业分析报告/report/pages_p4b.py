#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pages_p4b.py —— Part 4 团体业务 + 退休计划"""
from report_lib import (pg, H1, H2, H3, P, LEAD, INS, SPEC, WARN, NOTE,
                        CHART, BAR, TAG, table, fmt_hkd, fmt_int, fmt_rate, yi,
                        mval, series, yval, rankings_for, increments_for)

Q = ["2023Q1", "2024Q1", "2025Q1", "2026Q1"]

# ---------- 团体业务 ----------
def p20_group_new():
    pol = series("NB_GROUP_POLICIES")
    lives = series("NB_GROUP_LIVES")
    ape = series("NB_GROUP_ANNUALIZED_PREMIUM")
    rows = [
        ["新造保单数", fmt_int(pol["2023Q1"]), fmt_int(pol["2026Q1"]),
         fmt_rate((pol["2026Q1"]/pol["2023Q1"]-1) if pol["2023Q1"] else None),
         fmt_rate(yval("2025Q1","2026Q1","NB_GROUP_POLICIES")["growth_rate"])],
        ["新造受保人数", fmt_int(lives["2023Q1"]), fmt_int(lives["2026Q1"]),
         fmt_rate((lives["2026Q1"]/lives["2023Q1"]-1) if lives["2023Q1"] else None),
         fmt_rate(yval("2025Q1","2026Q1","NB_GROUP_LIVES")["growth_rate"])],
        ["新造年度化保费", fmt_hkd(ape["2023Q1"]), fmt_hkd(ape["2026Q1"]),
         fmt_rate((ape["2026Q1"]/ape["2023Q1"]-1) if ape["2023Q1"] else None),
         fmt_rate(yval("2025Q1","2026Q1","NB_GROUP_ANNUALIZED_PREMIUM")["growth_rate"])],
    ]
    return pg("团体业务 · 新造", H1("团体业务（一）新造：保单 / 受保人 / 年度化保费") + LEAD(
        "团体新造以<b>保单数与受保人数</b>为量，年度化保费体量极小（亿HK$ 级，非十亿级）。2025Q1 受保人数出现异常峰值（20.2 万），2026Q1 回落至 3.0 万，需按异常复核。") +
        table(["指标","2023Q1","2026Q1","累计增幅","25→26Q1同比"], rows) +
        WARN("团体新造受保人数 2025Q1 达 201,727、2026Q1 骤降至 30,430（同比 -84.9%）——已标&quot;held for outlier context&quot;，多为口径/范围事件而非经营断崖，见 P22 注解。") +
        INS("团体新造保单数稳定（约 470 张），保费体量占比极小；团体长期保险的体量主要在<b>有效存量</b>（P21），而非新造流量。"),
        tag="p")

def p21_group_inforce():
    pol = series("IF_GROUP_NON_RETIREMENT_POLICIES")
    lives = series("IF_GROUP_NON_RETIREMENT_LIVES")
    nsp = series("IF_GROUP_NON_RETIREMENT_NON_SINGLE_PREMIUM_RECEIVABLE")
    rows = [
        ["有效保单数（非退休）", fmt_int(pol["2023Q1"]), fmt_int(pol["2026Q1"]),
         fmt_rate((pol["2026Q1"]/pol["2023Q1"]-1) if pol["2023Q1"] else None)],
        ["有效受保人数（非退休）", fmt_int(lives["2023Q1"]), fmt_int(lives["2026Q1"]),
         fmt_rate((lives["2026Q1"]/lives["2023Q1"]-1) if lives["2023Q1"] else None)],
        ["有效非整付保费", fmt_hkd(nsp["2023Q1"]), fmt_hkd(nsp["2026Q1"]),
         fmt_rate((nsp["2026Q1"]/nsp["2023Q1"]-1) if nsp["2023Q1"] else None)],
    ]
    return pg("团体业务 · 有效存量", H1("团体业务（二）有效存量：保单 / 受保人 / 非整付保费") + LEAD(
        "团体（非退休）有效存量保单数约 1.6 万张、受保人约 123–149 万人。2023Q1–2026Q1 保单数小幅收窄，受保人在 2025 峰后明显回落。") +
        table(["指标","2023Q1","2026Q1","累计增幅"], rows) +
        INS("团体有效<b>非整付保费</b>从 {} 增至 {}，但与个人业务规模差距悬殊；受保人数 2026Q1 较 2025 峰回落约 -14.7%，提示团体在保人口波动。".format(
            fmt_hkd(nsp["2023Q1"]), fmt_hkd(nsp["2026Q1"]))) +
        NOTE("团体有效保费数据目前仅有&quot;非退休&quot;口径与非整付一列；整付/退休口径并入退休计划篇，缺失维度如实声明。"),
        tag="p")

def p22_group_note():
    return pg("团体业务 · 注解与口径", H1("团体业务（三）口径注解：异常与范围") + LEAD(
        "团体业务数据标点多、口径窄，凡下结论前先标注三类限制。") +
        table(["项目","说明","处理"],
              [["2025Q1 受保人峰值","可能为新增团体范围/集体单","标 outlier，不做经营归因"],
               ["整付保费恒为 0","团体新造/有效整付均 0（both_zero）","无整付口径，仅年缴"],
               ["仅非退休口径","退休类由退休计划篇覆盖","分片读，不混淆"]]) +
        SPEC("团体数据在监管 L2/L3 原生按“保单/受保人/保费”三个颗粒给；本报告不把三颗粒强行合成件均率（需整付与期缴匹配），仅并列呈现。") +
        WARN("模板的“开放渠道 + 递延”（团体/健康）讲解需<b>外部产品与渠道证据</b>，本报告不越权归因渠道，仅停留在监管量值描述（A 级）。"),
        tag="p")

# ---------- 退休计划 ----------
def p23_ret_total():
    schemes = series("IF_RETIREMENT_SCHEMES")
    rows = [
        ["退休计划数量", fmt_int(schemes["2023Q1"]), fmt_int(schemes["2024Q1"]),
         fmt_int(schemes["2025Q1"]), fmt_int(schemes["2026Q1"]),
         fmt_rate((schemes["2026Q1"]/schemes["2025Q1"]-1) if schemes["2025Q1"] else None)],
    ]
    return pg("退休计划 · 总览", H1("退休计划（一）计划数量：存量小幅波动") + LEAD(
        "退休计划数量（含强积金/职业退休类，监管口径”退休计划“）2023Q1 为 42.6 万，后回落至 2025Q1 的 35.5 万，2026Q1 小幅回升至 36.1 万。") +
        table(["指标","2023Q1","2024Q1","2025Q1","2026Q1","25→26同比"], rows) +
        INS("计划数量四年累计约 -15%（42.6万→36.1万），呈结构性收缩，与基金余额/供款的回升（P24/P25）方向相反——即<b>更少的计划、更大的单计划规模</b>（集约化）。") +
        SPEC("“退休计划”为 IA 监管口径汇总（含退休计划/公积金），不代表单一市场产品品牌；计划数与员工参与变化需外部资料解读。"),
        tag="p")

def p24_ret_fund():
    fund = series("IF_RETIREMENT_ENDING_FUND_BALANCE")
    rows = [["2023Q1", fmt_hkd(fund["2023Q1"])], ["2024Q1", fmt_hkd(fund["2024Q1"])],
            ["2025Q1", fmt_hkd(fund["2025Q1"])], ["2026Q1", fmt_hkd(fund["2026Q1"])],
            ["累计增幅", fmt_rate((fund["2026Q1"]/fund["2023Q1"]-1) if fund["2023Q1"] else None)]]
    return pg("退休计划 · 基金余额", H1("退休计划（二）期末基金余额：2024 回落后的恢复") + LEAD(
        "退休计划期末基金余额 2023Q1 约 126.9 亿HK$，2024Q1 回落至 112.7 亿，2025Q1 回升至 124.5 亿，2026Q1 达 131.4 亿。") +
        table(["期间","期末基金余额"], rows) +
        INS("基金余额在 2024 触底后连续两个同季回升，2026Q1 回到并略超 2023 水平（累计 +3.6%），但计划数量收缩，指向<b>单计划资产集中化</b>。") +
        NOTE("基金余额为期末存量（stock），受缴款现金流、投资市值与申领共同影响；只作方向性解读，不拆投资损益。"),
        tag="p")

def p25_ret_contrib():
    rs = series("IF_RETIREMENT_SINGLE_CONTRIBUTIONS")
    rn = series("IF_RETIREMENT_NON_SINGLE_CONTRIBUTIONS")
    rows = [
        ["单项供款", fmt_hkd(rs["2023Q1"]), fmt_hkd(rs["2026Q1"]),
         fmt_rate((rs["2026Q1"]/rs["2023Q1"]-1) if rs["2023Q1"] else None),
         fmt_rate(yval("2025Q1","2026Q1","IF_RETIREMENT_SINGLE_CONTRIBUTIONS")["growth_rate"])],
        ["非单项供款", fmt_hkd(rn["2023Q1"]), fmt_hkd(rn["2026Q1"]),
         fmt_rate((rn["2026Q1"]/rn["2023Q1"]-1) if rn["2023Q1"] else None),
         fmt_rate(yval("2025Q1","2026Q1","IF_RETIREMENT_NON_SINGLE_CONTRIBUTIONS")["growth_rate"])],
        ["供款合计", fmt_hkd((rs["2023Q1"] or 0)+(rn["2023Q1"] or 0)),
         fmt_hkd((rs["2026Q1"] or 0)+(rn["2026Q1"] or 0)), "—", "—"],
    ]
    return pg("退休计划 · 供款", H1("退休计划（三）缴款现金流：单项供款回升") + LEAD(
        "退休计划缴款分<b>单项</b>与<b>非单项</b>供款（retirement contributions，非保单新造保费）。单项供款 2023Q1 6.24 亿→2026Q1 10.03 亿（+60.7%），非单项 2.0→2.07 亿基本持平。") +
        table(["缴款类型","2023Q1","2026Q1","累计增幅","25→26同比"], rows) +
        INS("供款增长集中在<b>单项供款</b>，非单项平稳——反映缴款流向特定（单项/大额）类目；与基金余额恢复方向一致。") +
        NOTE("退休供款是现金流（flow），与保单 NOP/APE 口径不同，不与个人业务直接相加或比较。"),
        tag="p")
