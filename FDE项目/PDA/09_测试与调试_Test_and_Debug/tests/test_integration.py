#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDA 集成测试唯一入口。白盒 import 调用真实 skill，不用 subprocess 黑盒调用。

按 Agent 搭建 SOP v1.2 第5步"Agent验证方法论·五条原则"：
- 能用脚本/断言判定对错的，不用主观判断（本文件全部是确定性断言）
- 用真实底表跑（07_接入记忆_Integrate_Memory/raw_data/ 下 Jasper 放的原始文件），
  不是只用合成 fixture——断言里的具体数字（3593/53/12等）就是需求定义.md
  第十一节核实出的真实数字，不是随手编的期望值。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
for sub in ("06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(AGENT_ROOT / sub))

from skills.data_loader import DataLoader, MissingColumnsError
from skills.cleaner import Cleaner, UnmappedStatusError
from skills.aggregator import Aggregator
from skills.dashboard_generator import DashboardGenerator
from skills.report_enricher import ReportEnricher, UnmappedPolicyStageError
from skills.s1_dashboard import S1DashboardBuilder
from skills.s2_business_view import S2BusinessViewBuilder
from skills.s3_execution_view import S3ExecutionViewBuilder
from skills.s4_product_view import S4ProductViewBuilder
from skills.s5_finance_view import S5FinanceViewBuilder
from skills.s6_market_cross_view import S6MarketCrossViewBuilder
from skills.s7_compliance_view import S7ComplianceViewBuilder
from skills.s9_agent_ka_view import S9AgentKaViewBuilder

RAW_DATA_DIR = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "raw_data"
REPORT_FILE = RAW_DATA_DIR / "业绩分析报表_0724.xlsx"
FACT_TARGET_SNAPSHOT = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "fact_target_snapshot.csv"

failures = []


def check(name, condition, detail=""):
    status = "✅" if condition else "❌"
    print(f"{status} {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def main():
    if not any(RAW_DATA_DIR.glob("*.xlsx")):
        print(f"⚠️ {RAW_DATA_DIR} 下没有真实底表文件，无法做真实数据验证，测试终止")
        sys.exit(1)

    # ---- L3-PDA-01 ----
    load_result = DataLoader(RAW_DATA_DIR).load()
    check("底表读取成功", load_result.df is not None)
    check("有效记录数为 3593（真实核实数字，见需求定义.md七节）",
          len(load_result.df) == 3593, f"实际 {len(load_result.df)}")
    check("剔除表头残留行 1 行", load_result.header_echo_rows_dropped == 1,
          f"实际 {load_result.header_echo_rows_dropped}")
    check("表头残留行已从数据中剔除（policy_id 不再含'订单编号'）",
          "订单编号" not in load_result.df["policy_id"].values)
    check("导出日期解析成功", load_result.export_date is not None)

    # ---- L3-PDA-02 ----
    df = Cleaner().clean(load_result.df, load_result.export_date)
    check("清洗后行数不变（清洗不丢行）", len(df) == len(load_result.df))
    check("sign_date 无 NaT（Excel序列号日期已全部修正）", df["sign_date"].notna().all())
    check("sign_date 范围正确，不含1970年附近脏值（真问题1已修复）",
          df["sign_date"].min().year >= 2024, f"实际最小值 {df['sign_date'].min()}")
    check("future_dated 真实为 53 条，不是原型硬编码的11条（真问题2已修复）",
          int(df["future_dated"].sum()) == 53, f"实际 {int(df['future_dated'].sum())}")
    check("policy_status_tier 全部归入 生效/在途/终止 三档，无遗漏",
          set(df["policy_status_tier"].unique()) == {"生效", "在途", "终止"})
    check("在途+终止+生效计数等于总行数（三档映射无重复无遗漏）",
          df["policy_status_tier"].value_counts().sum() == len(df))
    check("premium 无缺失（缺失已按0处理）", df["premium"].notna().all())
    check("currency_code 无缺失（空值已归为'未填'）", df["currency_code"].notna().all())

    try:
        Cleaner().clean(load_result.df.assign(policy_status=["未知状态"] * len(load_result.df)), load_result.export_date)
        check("policy_status 出现未知取值时应抛出 UnmappedStatusError", False)
    except UnmappedStatusError:
        check("policy_status 出现未知取值时正确抛出 UnmappedStatusError", True)

    # ---- L3-PDA-03 ----
    agg = Aggregator().aggregate(df)
    check("覆盖牌照端 12 家", len(agg["entities"]) == 12, f"实际 {len(agg['entities'])}")
    check("总保费与原始底表逐行加总一致（独立重算校验，不是自我复述）",
          abs(sum(v["premium"] for v in agg["by_entity_all"].values()) - df["premium"].sum()) < 0.01)
    check("总保单数与清洗后行数一致",
          sum(v["count"] for v in agg["by_entity_all"].values()) == len(df))
    check("top_carriers 命中香港永明金融（已知最大保司）",
          "香港永明金融有限公司" in agg["top_carriers"])
    check("cycle_avg 已计算出结果（非空）", len(agg["cycle_avg"]) > 0)
    check("months 覆盖到 future_dated 批次所在的 2026-08（真实反映修复后的完整数据）",
          "2026-08" in agg["months"])

    # ---- L3-PDA-04 ----
    html = DashboardGenerator().render(
        agg,
        source_file_name=load_result.source_file.name,
        export_date="2026-07-24",
        raw_rows=load_result.raw_row_count,
        header_rows_dropped=load_result.header_echo_rows_dropped,
        record_count=len(df),
        future_dated_count=int(df["future_dated"].sum()),
        generated_at="test-run",
    )
    check("看板 HTML 生成成功且非空", len(html) > 10000)
    check("看板 footer 里真实数字(53)已注入，不再是原型硬编码的11",
          "53 条签单日期晚于导出日" in html)
    check("看板未残留未替换的占位符", "__DATA_JSON__" not in html and "__SOURCE__" not in html)

    # ---- 缺列时应报错，不静默跳过 ----
    from skills.data_loader import EXPECTED_COLUMNS
    broken = load_result.df.drop(columns=["premium"])
    missing = [c for c in EXPECTED_COLUMNS if c not in broken.columns]
    check("列完整性校验能识别出缺失列", missing == ["premium"])

    # ---- L3-PDA-05：report_enricher，对照真实"业绩分析报表"S8独立核验 ----
    # 按SOP 5.2节"独立数据源交叉核验"原则：ground truth来自另一份独立文件（Jasper提供的
    # 业绩分析报表_0724.xlsx），不是拿enricher自己的输出自我复述。
    enriched = ReportEnricher().enrich(df)
    if REPORT_FILE.exists():
        import pandas as pd
        s8 = pd.read_excel(REPORT_FILE, sheet_name="S8_明细数据底表", header=1)
        m = enriched.merge(s8, left_on="policy_id", right_on="订单编号", how="inner")
        check("report_enricher 与真实S8全部匹配上（未丢单）", len(m) == len(enriched))

        simple_fields = [
            ("保单阶段", "保单阶段_x", "保单阶段_y"),
            ("业务大类", "业务大类_x", "业务大类_y"),
            ("融资标签", "融资标签_x", "融资标签_y"),
            ("保费分档", "保费分档_x", "保费分档_y"),
            ("APE分档", "APE分档_x", "APE分档_y"),
            ("签单年", "签单年_x", "签单年_y"),
            ("签单年月", "签单年月_x", "签单年月_y"),
            ("预约年月", "预约年月_x", "预约年月_y"),
        ]
        for name, ca, cb in simple_fields:
            match = (m[ca].astype(object).where(m[ca].notna(), None)
                     == m[cb].astype(object).where(m[cb].notna(), None)).sum()
            check(f"report_enricher『{name}』与真实S8 100%匹配", match == len(m), f"{match}/{len(m)}")

        # 年期分类：真实数据里24行(premium_term为文本/缺失)两边都是None，直接==会判false，需分开算
        term_match = ((m["年期分类_x"] == m["年期分类_y"]) | (m["年期分类_x"].isna() & m["年期分类_y"].isna())).sum()
        check("report_enricher『年期分类』与真实S8 100%匹配", term_match == len(m), f"{term_match}/{len(m)}")

        # 签批时效/批核年/批核年月：issue_date缺失的704条两边都是NaN，同样要分开算
        for name, ca, cb in [("签批时效(天)", "签批时效(天)_x", "签批时效(天)_y"),
                              ("批核年", "批核年_x", "批核年_y"),
                              ("批核年月", "批核年月_x", "批核年月_y")]:
            match = ((m[ca] == m[cb]) | (m[ca].isna() & m[cb].isna())).sum()
            check(f"report_enricher『{name}』与真实S8 100%匹配", match == len(m), f"{match}/{len(m)}")
    else:
        check(f"⚠️ {REPORT_FILE.name} 不存在，跳过report_enricher独立核验（不算失败，但下次有文件要重跑）", True)

    try:
        ReportEnricher().enrich(df.assign(policy_status=["未知状态"] * len(df)))
        check("policy_status 出现未知取值时 enrich 应抛出 UnmappedPolicyStageError", False)
    except UnmappedPolicyStageError:
        check("policy_status 出现未知取值时 enrich 正确抛出 UnmappedPolicyStageError", True)

    # ---- L3-PDA-06：s1_dashboard，对照真实"业绩分析报表"S1_总览仪表盘独立核验 ----
    # ground truth数字直接抄自S1 sheet原文（2026-07-31人工核对时记录），不是从builder自己反算的。
    if REPORT_FILE.exists() and FACT_TARGET_SNAPSHOT.exists():
        import pandas as pd
        fact_target = pd.read_csv(FACT_TARGET_SNAPSHOT)
        s1 = S1DashboardBuilder(enriched, fact_target, report_month="2026-07").build_all()

        a = {r["指标"]: r for r in s1["A"]}
        check("S1-A 全业务目标APE", a["2026全业务目标"]["目标APE"] == 1113000000)
        check("S1-A 全业务已达成APE", abs(a["2026全业务目标"]["已达成APE"] - 618939268.33) < 0.01)
        check("S1-A 永明目标APE", a["2026永明业务目标"]["目标APE"] == 976100000)
        check("S1-A 永明已达成APE", abs(a["2026永明业务目标"]["已达成APE"] - 522699342.4) < 0.01)

        b = {r["指标行"]: r for r in s1["B"]}
        b_truth = {
            "批核(2025)": (1645, 616841098.5942),
            "批核(2026)": (1205, 618939268.33),
            "未批核(跨年)": (260, 123714140.47),
            "待签(跨年)": (55, 20033148.4),
            "流失(2026)": (97, 34167370.61),
        }
        for label, (count, ape) in b_truth.items():
            check(f"S1-B『{label}』件数+APE", b[label]["件数"] == count and abs(b[label]["APE"] - ape) < 0.01)

        c_first = s1["C"][0]
        check("S1-C 首月(2025-01)件数+APE", c_first["年月"] == "2025-01" and c_first["件数"] == 69
              and abs(c_first["APE"] - 22560612.856) < 0.01 and c_first["环比增长%"] is None)

        d_first = s1["D"][0]
        check("S1-D 首月(2025-01)件数+APE", d_first["年月"] == "2025-01" and d_first["件数"] == 70
              and abs(d_first["APE"] - 25095612.856) < 0.01)

        e_by_month = {r["年月"]: r for r in s1["E"]}
        check("S1-E 2026-01 同比增长%", abs(e_by_month["2026-01"]["同比增长%"] - 1.8206296247174274) < 1e-6)

        f = {r["保单状态"]: r for r in s1["F"]}
        check("S1-F A.批核(2026)", f["A.批核(2026)"]["件数"] == 1205
              and abs(f["A.批核(2026)"]["APE"] - 618939268.33) < 0.01)
        check("S1-F G.失效恒为0", f["G.失效"]["件数"] == 0 and f["G.失效"]["APE"] == 0)
        check("S1-F 合计1617件（拒保2条不计入本表，是报表自身的已知缺口）", f["合计"]["件数"] == 1617)

        g = {r["业务类型"]: r for r in s1["G"]}
        check("S1-G 经代业务（必须用业务大类含MGA重分类，否则会差91件）",
              g["经代业务"]["批核件数"] == 932 and abs(g["经代业务"]["2026批核APE"] - 518519894.28) < 0.01)
        check("S1-G 合计批核件数=1205", g["合计"]["批核件数"] == 1205)

        h = {r["牌照"]: r for r in s1["H"]}
        check("S1-H JF 2026-01", abs(h["JF"]["2026-01"] - 45864039.84) < 0.01)
        check("S1-H UNIWIN 2026-01", abs(h["UNIWIN"]["2026-01"] - 21654896.28) < 0.01)
        check("S1-H DW Bank 2026-01", abs(h["DW Bank"]["2026-01"] - 18259800) < 0.01)
        check("S1-H DW-Non-Bank 2026-01", abs(h["DW-Non-Bank"]["2026-01"] - 401809.2) < 0.01)
        check("S1-H Sub Total 2026-01 = JF+UNIWIN+DW-Non-Bank+EG（不含DW Bank）",
              abs(h["Sub Total"]["2026-01"] - 67920745.32) < 0.01)
        check("S1-H JF 未批核", abs(h["JF"]["未批核"] - 23077485.2) < 0.01)
        check("S1-H JF 本月已递交", abs(h["JF"]["本月已递交"] - 14526341.81) < 0.01)
    else:
        check("⚠️ 报表文件或fact_target快照不存在，跳过S1独立核验", True)

    # ---- L3-PDA-07：s2_business_view，对照真实"业绩分析报表"S2_业务端视角独立核验 ----
    if REPORT_FILE.exists() and FACT_TARGET_SNAPSHOT.exists():
        s2b = S2BusinessViewBuilder(df, fact_target)

        a = {r["业务细分"]: r for r in s2b.segment_summary(carrier=None)}
        check("S2-A 同行经代（含MGA折算,批核319件）", a["同行经代"]["批核件数"] == 319
              and abs(a["同行经代"]["2026批核APE"] - 133982611.88) < 0.01)
        check("S2-A 合计目标APE=1,113,000,000", abs(a["合计"]["目标APE"] - 1113000000) < 0.01)

        bb = {r["业务细分"]: r for r in s2b.segment_summary(carrier="香港永明金融有限公司")}
        check("S2-B 同行经代（永明子集,批核221件,目标140M）", bb["同行经代"]["批核件数"] == 221
              and abs(bb["同行经代"]["目标APE"] - 140000000) < 0.01)

        c = {r["业务细分"]: r for r in s2b.section_c()}
        check("S2-C 天领业务2026-01（流失类排除口径）",
              abs(c["天领业务"]["2026-01"]["ape"] - 6673951) < 1)

        i = {r["KEY ACCOUNT"]: r for r in s2b.section_i()}
        check("S2-I 天誉国际/天誉国际(MGA) 拆分正确", "天誉国际(MGA)" in i
              and i["天誉国际(MGA)"]["批核件数"] == 91 and i["天誉国际"]["批核件数"] == 96)

        j = {r["推荐人"]: r for r in s2b.section_j()}
        check("S2-J 姜通（referral_code不限carrier）", j["姜通"]["批核件数"] == 349
              and abs(j["姜通"]["2026批核APE"] - 124571660.7) < 0.01)

        k = s2b.section_k()
        k_total = [r for r in k if r["KEY ACCOUNT"] == "合计"][0]
        check("S2-K 合计批核件数=731（=A节同行经代319+永明经代412）", k_total["批核件数"] == 731)
        check("S2-K 行数27（26个KA+合计,天誉国际(MGA)独立成行）", len(k) == 27)

        o = s2b.section_o()
        check("S2-O 只有民生银行/平安银行/合计3行（不含0值幽灵行）",
              [r["KEY ACCOUNT"] for r in o] == ["民生银行", "平安银行", "合计"])
    else:
        check("⚠️ 报表文件或fact_target快照不存在，跳过S2独立核验", True)

    # ---- L3-PDA-08：s3_execution_view，对照真实"业绩分析报表"S3_执行管理端独立核验 ----
    if REPORT_FILE.exists():
        s3b = S3ExecutionViewBuilder(df)

        funnel = s3b.funnel()
        check("S3-A 预约W01/W02/W03（周定义=%YW%U，周日起始）",
              funnel["预约"]["2026W01"]["count"] == 16 and funnel["预约"]["2026W02"]["count"] == 36
              and funnel["预约"]["2026W03"]["count"] == 35)
        check("S3-A 批核W01（仅status=生效）",
              abs(funnel["批核"]["2026W01"]["ape"] - 18039303.12) < 0.01 and funnel["批核"]["2026W01"]["count"] == 63)
        check("S3-A 周列表从W01开始（不含%U产生的W00零头）",
              "2026W00" not in funnel["预约"])

        b_seg = {r["业务细分"]: r for r in s3b.section_b()}
        check("S3-B 天领业务W01", abs(b_seg["天领业务"]["2026W01"]["ape"] - 156000) < 0.01)

        g = {r["业务细分"]: r for r in s3b.section_g()}
        check("S3-G 天领业务时效7项指标", g["天领业务"]["件数"] == 200
              and abs(g["天领业务"]["平均时效(天)"] - 20.2) < 0.05
              and g["天领业务"]["SLA达标率≤60"] is not None and abs(g["天领业务"]["SLA达标率≤60"] - 0.985) < 0.001)

        h = {r["时效分档"]: r for r in s3b.section_h()}
        check("S3-H ≤7天分档排除TAT<0异常值(126件不是127件)", h["≤7天"]["件数"] == 126
              and abs(h["≤7天"]["APE"] - 35843324.08) < 1)
        check("S3-H 合计=全量1205件（不是6档相加的1204件）", h["合计"]["件数"] == 1205)
    else:
        check("⚠️ 报表文件不存在，跳过S3独立核验", True)

    # ---- L3-PDA-09：s4_product_view，对照真实"业绩分析报表"S4_产品端视角独立核验 ----
    if REPORT_FILE.exists():
        s4b = S4ProductViewBuilder(df)

        a = {r["保险公司"]: r for r in s4b.section_a()}
        check("S4-A 永明（A节排除4种状态含拒保，跟B-E的3种不同）", a["永明"]["件数"] == 934
              and abs(a["永明"]["APE"] - 361550464.53) < 0.01)
        check("S4-A 合计1205件", a["合计"]["件数"] == 1205)
        check("S4-A 零业务保司也列出(如'周大福')", a.get("周大福", {}).get("件数") == 0)

        c = s4b.section_c()
        check("S4-C 第1名（万年青·卓金保险计划II/21%）", c[0]["产品名称"] == "万年青·卓金保险计划II"
              and c[0]["首年折扣"] == "21%" and c[0]["件数"] == 43 and abs(c[0]["APE"] - 26395200) < 0.01)

        b4 = s4b.section_b()
        check("S4-B 第1/2名（永誉传承储蓄计划按SQ_rate拆成2.5%/3.5%两行，不是合并成1行）",
              b4[0]["首年折扣"] == "2.5%" and b4[0]["件数"] == 13
              and b4[1]["首年折扣"] == "3.5%" and b4[1]["件数"] == 8)
        check("S4-B SQ_rate缺失的记录不出现在TOP20（即便金额很大）",
              all(r["首年折扣"] is not None for r in b4))

        d = {r["年期分类"]: r for r in s4b.section_d()}
        check("S4-D 中期(2-5年)1021件", d["中期(2-5年)"]["件数"] == 1021)
        check("S4-D 合计1206件（不等于4档相加的1199，7条premium_term非数字的记录不落入任何档但计入合计）",
              d["合计"]["件数"] == 1206)

        e = {r["供款方式"]: r for r in s4b.section_e()}
        check("S4-E 预缴/年缴/整付/合计", e["预缴"]["件数"] == 430 and e["年缴"]["件数"] == 685
              and e["整付"]["件数"] == 91 and e["合计"]["件数"] == 1206)
    else:
        check("⚠️ 报表文件不存在，跳过S4独立核验", True)

    # ---- L3-PDA-10：s5_finance_view，对照真实"业绩分析报表"S5_财务端视角独立核验 ----
    if REPORT_FILE.exists():
        s5b = S5FinanceViewBuilder(df)

        a = {r["牌照(签单供应商)"]: r for r in s5b.section_a()}
        check("S5-A 怡泰财富管理有限公司", a["怡泰财富管理有限公司"]["件数"] == 240
              and abs(a["怡泰财富管理有限公司"]["批核APE"] - 238231097.58) < 0.01
              and abs(a["怡泰财富管理有限公司"]["批核年总保费(HKD)"] - 1900461727.38) < 0.01)
        check("S5-A 合计1205件（含零业务entity）", a["合计"]["件数"] == 1205 and len(s5b.section_a()) == 13)

        d = {r["保费规模档"]: r for r in s5b.section_d()}
        check("S5-D 保费分档（复用report_enricher的边界常量）",
              d["<5万"]["件数"] == 113 and d["100万+"]["件数"] == 182 and d["合计"]["件数"] == 1205)

        f = {r["类型"]: r for r in s5b.section_f()}
        check("S5-F 常规/融资", f["常规"]["件数"] == 1079 and abs(f["常规"]["APE"] - 397770708.33) < 0.01
              and f["融资"]["件数"] == 126 and abs(f["融资"]["年总保费(HKD)"] - 1854385600) < 0.01)

        g = s5b.section_g()
        check("S5-G TOP20金额并列时按sign_date升序排（不是随机/policy_no顺序）",
              g[0]["保单号"] == 611222899 and g[1]["保单号"] == 611222895 and g[2]["保单号"] == 611222827)

        h = s5b.section_h()
        check("S5-H 第1名（薪火传承环球终身寿险计划，13,571,999.45）",
              h[0]["产品"] == "薪火传承环球终身寿险计划" and abs(h[0]["APE"] - 13571999.45) < 0.01
              and h[0]["牌照"] == "富强天一" and h[0]["保司"] == "中银人寿")

        bp = {r["牌照"]: r for r in s5b.section_b_premium()}
        check("S5-B_premium 怡泰2026-01", abs(bp["怡泰财富管理有限公司"]["2026-01"] - 74396333.7) < 0.01)
    else:
        check("⚠️ 报表文件不存在，跳过S5独立核验", True)

    # ---- L3-PDA-11：s6_market_cross_view，对照真实"业绩分析报表"S6_市场与交叉视角独立核验 ----
    if REPORT_FILE.exists():
        s6b = S6MarketCrossViewBuilder(df)

        a = {r["KA"]: r for r in s6b._cross_table("批核", "ka")}
        check("S6-A 天誉国际/天誉国际(MGA) 同行经代列", abs(a["天誉国际"]["同行经代"] - 44347079.86) < 0.01
              and abs(a["天誉国际(MGA)"]["同行经代"] - 22040525.74) < 0.01)
        check("S6-A 行数57（56个KA+合计，全0行已过滤）", len(s6b._cross_table("批核", "ka")) == 57)

        d = {r["保司"]: r for r in s6b._cross_table("批核", "carrier")}
        check("S6-D 永明整行8个业务细分", abs(d["永明"]["天领业务"] - 50585272.04) < 0.01
              and abs(d["永明"]["BK业务"] - 231135120.06) < 0.01 and abs(d["永明"]["合计"] - 522699342.4) < 0.01)

        b6 = {r["KA"]: r for r in s6b._cross_table("未批核", "ka")}
        check("S6-B 天誉国际(MGA)未批核", abs(b6["天誉国际(MGA)"]["同行经代"] - 39142184.84) < 0.01)

        c6 = {r["KA"]: r for r in s6b._cross_table("待签", "ka")}
        check("S6-C 天誉国际(MGA)/唯思 待签", abs(c6["天誉国际(MGA)"]["同行经代"] - 6236700) < 0.01
              and abs(c6["唯思"]["同行经代"] - 3352000) < 0.01)
    else:
        check("⚠️ 报表文件不存在，跳过S6独立核验", True)

    # ---- L3-PDA-12：s7_compliance_view，对照真实"业绩分析报表"S7_合规端视角独立核验 ----
    if REPORT_FILE.exists():
        s7b = S7ComplianceViewBuilder(df)

        a7 = {r["签单供应商"]: r for r in s7b.section_a()}
        yt = a7["怡泰财富管理有限公司"]
        check("S7-A 怡泰批核/未批核/待签/distinct数量列", abs(yt["2026批核APE"] - 238231097.58) < 0.01
              and yt["批核件数"] == 240 and abs(yt["未批核APE"] - 29823924) < 0.01 and yt["未批核件数"] == 46
              and abs(yt["待签APE"] - 2535000) < 0.01 and yt["待签件数"] == 5
              and yt["保险公司数"] == 12 and yt["产品数"] == 20 and yt["KA数"] == 15 and yt["TR数"] == 7)

        ba7 = {r["签单供应商"]: r for r in s7b.section_b_ape()}
        check("S7-B_ape 怡泰整行8个业务细分", abs(ba7["怡泰财富管理有限公司"]["BK业务"] - 231135120.06) < 0.01
              and abs(ba7["怡泰财富管理有限公司"]["合计"] - 238231097.58) < 0.01)

        e7 = s7b.section_e()
        check("S7-E 前2条时效异常（244天/220天）", e7[0]["保单号"] == 611221282 and e7[0]["时效(天)"] == 244
              and e7[0]["牌照"] == "众和恒富理财集团" and e7[1]["保单号"] == 611208853 and e7[1]["时效(天)"] == 220)

        f7 = {r["TR"]: r for r in s7b.section_f()}
        check("S7-F 李咏媱/余文茜（业务线数用SEGMENT_GROUPS折算）", abs(f7["李咏媱"]["APE"] - 51095259.2) < 0.01
              and f7["李咏媱"]["件数"] == 158 and f7["李咏媱"]["业务线数"] == 5
              and abs(f7["余文茜"]["APE"] - 44473555.74) < 0.01 and f7["余文茜"]["业务线数"] == 2)
    else:
        check("⚠️ 报表文件不存在，跳过S7独立核验", True)

    # ---- L3-PDA-13：s9_agent_ka_view，对照真实"业绩分析报表"S9_代理人与KA业务独立核验 ----
    if REPORT_FILE.exists() and FACT_TARGET_SNAPSHOT.exists():
        s9b = S9AgentKaViewBuilder(df, fact_target)

        a9 = {r["业务细分"]: r for r in s9b.section_a()}
        check("S9-A 合计（5条代理人业务线过滤自S2-A）", a9["合计"]["目标APE"] == 413000000
              and abs(a9["合计"]["2026批核APE"] - 100419374.05) < 0.01 and a9["合计"]["批核件数"] == 273)

        b9 = {r["KEY ACCOUNT"]: r for r in s9b.section_b()}
        check("S9-B 苏州贴牌/厦门贴牌并列（2026批核APE相同，用总APE降序二级排序）",
              b9["苏州贴牌"]["2026批核APE"] == b9["厦门贴牌"]["2026批核APE"] == 273000.0
              and b9["苏州贴牌"]["总APE"] > b9["厦门贴牌"]["总APE"])
        check("S9-B 合计200件", b9["合计"]["批核件数"] == 200)

        d9 = {r["指标"]: r for r in s9b.section_d()}
        check("S9-D 预约APE 2026-01（标题写含流失单，实测=S2的res/sign/issue三态口径）",
              abs(d9["预约 APE"]["2026-01"] - 6673951.26) < 0.01)

        f9 = s9b.section_f()
        f9_iclub = {r["KEY ACCOUNT"]: r for r in f9["ICLUB业务"]}
        check("S9-F-ICLUB 个人转介", abs(f9_iclub["个人转介"]["2026批核APE"] - 18526812.08) < 0.01)

        g9 = {r["指标"]: r for r in s9b.section_g()}
        check("S9-G 批核APE 2026-03（segment IN ICLUB/合伙转介/IFA）", abs(g9["批核 APE"]["2026-03"] - 834747.01) < 0.01)

        h9 = s9b.section_h()
        h9_res = {r["KEY ACCOUNT"]: r for r in h9["预约_APE"]}
        check("S9-H 天领重庆预约APE W01 + 长沙贴牌不在预约表(0贡献已过滤)",
              h9_res["天领重庆"]["2026W01"] == 156000.0 and "长沙贴牌" not in h9_res)
        h9_issue = {r["KEY ACCOUNT"] for r in h9["批核_APE"]}
        check("S9-H 长沙贴牌出现在批核表(该子表独立过滤0贡献KA)", "长沙贴牌" in h9_issue)
    else:
        check("⚠️ 报表文件或fact_target快照不存在，跳过S9独立核验", True)

    print()
    if failures:
        print(f"❌ {len(failures)} 项失败: {failures}")
        sys.exit(1)
    else:
        print("✅ 全部检查通过")
        print("真实数据验证对象：raw_data/" + load_result.source_file.name)


if __name__ == "__main__":
    main()
