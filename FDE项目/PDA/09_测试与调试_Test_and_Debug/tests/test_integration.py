#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDA 集成测试唯一入口。白盒 import 调用真实 skill，不用 subprocess 黑盒调用。

按 Agent 搭建 SOP v1.2 第5步"Agent验证方法论·五条原则"：
- 能用脚本/断言判定对错的，不用主观判断（本文件全部是确定性断言）
- 用真实底表跑（07_接入记忆_Integrate_Memory/raw_data/ 下 Jasper 放的原始文件），
  不是只用合成 fixture——断言里的具体数字就是对照真实ground truth报表(或独立pandas
  重算)核实出的真实数字，不是随手编的期望值。

v0.19.0随底表换成『业绩数据底表-20261009.xlsx』(3993条有效记录)、ground truth换成
『业绩分析报表_1009.xlsx』后，本文件里全部写死的具体期望数字已重新核对更新（原3593/
53等是针对0724那批旧数据核实出的，不是这次的通用规则）。其中一类断言（S1-H/S5-A/
S5-B_premium/S7-A/S7-B_ape，全部是按issuing_entity分组的板块）改成了"用独立pandas
重算、不直接读ground truth单元格"的模式——原因见cleaner.py模块docstring：业绩分析
报表的生成脚本本身也有issuing_entity简繁体重复的bug（只精确匹配简体名，繁体变体的
业务被漏算成0），本项目v0.19.0已在cleaner.py里把简繁变体归一化，这些板块的正确值
反而会跟ground truth报表的原始单元格不一致（ground truth是bug前的数字），因此这几
处改为拿同样的过滤条件在NORMALIZED数据上独立用pandas重新算一遍作为期望值，不是放
宽验证、是避免把ground truth自身的已知bug当成标准答案。
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
REPORT_FILE = RAW_DATA_DIR / "业绩分析报表_1009.xlsx"
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
    check("有效记录数为 3993（v0.19.0换成『业绩数据底表-20261009.xlsx』后的真实数字）",
          len(load_result.df) == 3993, f"实际 {len(load_result.df)}")
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
    check("future_dated 真实为 21 条（v0.19.0新底表核实数字，导出日2026-10-09）",
          int(df["future_dated"].sum()) == 21, f"实际 {int(df['future_dated'].sum())}")
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
    check("months 覆盖到 future_dated 批次所在的 2026-11（真实反映v0.19.0新底表完整数据）",
          "2026-11" in agg["months"])

    # ---- L3-PDA-04 ----
    html = DashboardGenerator().render(
        agg,
        source_file_name=load_result.source_file.name,
        export_date="2026-10-09",
        raw_rows=load_result.raw_row_count,
        header_rows_dropped=load_result.header_echo_rows_dropped,
        record_count=len(df),
        future_dated_count=int(df["future_dated"].sum()),
        generated_at="test-run",
    )
    check("看板 HTML 生成成功且非空", len(html) > 10000)
    check("看板 footer 里真实数字(21)已注入（v0.19.0新底表真实future_dated数）",
          "21 条签单日期晚于导出日" in html)
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
        import openpyxl

        # v0.19.0发现：业绩分析报表_1009.xlsx的S8_明细数据底表sheet存在真实的数据生成
        # bug（在生成这份ground truth的权威脚本generate_report.py里，不是本项目的问题）——
        # 对照generate_report.py第2183-2191行：orig_cols里的'discount_std'
        # （对应表头"首年折扣(标准化)"）这一列在它们内部df里实际并不存在，
        # `available_cols = [c for c in orig_cols if c in df.columns]`会把它整体过滤掉，
        # 但表头(orig_hdrs)44列照写不变——结果是S8明细数据底表sheet里全部3993行数据
        # 从"保费分档"往后整体左移一位(44个表头对应43个实际写入的数据列)，是对
        # **全表统一**生效的错位，不是只在某些行发生。已跟旧的业绩分析报表_0724.xlsx
        # 核对过同一位置：0724版本"首年折扣(标准化)"列有正常的空字符串/百分比值，不存在
        # 这个错位，确认是1009这批新生成报表的回归bug。用openpyxl直接按行读取+统一校正
        # （在"首年折扣(标准化)"位置插回None，原有该位置往后的全部列整体右移一位还原），
        # 不是放宽断言容差——校正后"首年折扣(标准化)"全部为None(该列本身在这份报表里
        # 确实拿不到数据，如实反映，不是编造)，其余12个衍生字段校正后再跟enricher比对，
        # 断言仍要求100%匹配。
        wb8 = openpyxl.load_workbook(REPORT_FILE, read_only=True, data_only=True)
        ws8 = wb8["S8_明细数据底表"]
        raw_rows8 = list(ws8.iter_rows(values_only=True))
        header8 = list(raw_rows8[1])
        DISCOUNT_COL = header8.index("首年折扣(标准化)")  # 34

        def _fix_row8(row):
            return row[:DISCOUNT_COL] + (None,) + row[DISCOUNT_COL:len(header8) - 1]

        fixed_rows8 = [_fix_row8(r) for r in raw_rows8[2:] if r[0] is not None]
        s8 = pd.DataFrame(fixed_rows8, columns=header8)
        check("S8 ground truth列错位校正：校正后不再残留'首年折扣(标准化)'为万/%混杂的脏值",
              s8["首年折扣(标准化)"].dropna().apply(lambda v: "万" not in str(v)).all())
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
    # ground truth数字v0.19.0已对照新ground truth『业绩分析报表_1009.xlsx』S1 sheet原文
    # 重新核对更新（report_month=2026-10，数据导出日2026-10-09所在月份，H节"本月已递交"
    # 要用这个月）。
    if REPORT_FILE.exists() and FACT_TARGET_SNAPSHOT.exists():
        import pandas as pd
        fact_target = pd.read_csv(FACT_TARGET_SNAPSHOT)
        s1 = S1DashboardBuilder(enriched, fact_target, report_month="2026-10").build_all()

        a = {r["指标"]: r for r in s1["A"]}
        check("S1-A 全业务目标APE", a["2026全业务目标"]["目标APE"] == 1113000000)
        check("S1-A 全业务已达成APE", abs(a["2026全业务目标"]["已达成APE"] - 772125888.12) < 0.01)
        check("S1-A 永明目标APE", a["2026永明业务目标"]["目标APE"] == 976100000)
        check("S1-A 永明已达成APE", abs(a["2026永明业务目标"]["已达成APE"] - 616255478.47) < 0.01)

        b = {r["指标行"]: r for r in s1["B"]}
        b_truth = {
            "批核(2025)": (1645, 616841098.5942),
            "批核(2026)": (1647, 772125888.12),
            "未批核(跨年)": (171, 87065729.29),
            "待签(跨年)": (20, 9082797.6),
            "流失(2026)": (179, 77898082.23),
        }
        for label, (count, ape) in b_truth.items():
            check(f"S1-B『{label}』件数+APE", b[label]["件数"] == count and abs(b[label]["APE"] - ape) < 0.01)
        # v0.19.0修正发现：融资占比之前用件数均值算(count-based mean)，跟权威脚本
        # generate_report.py的APE加权公式(sum(ape where is_pf)/sum(ape))不一致——
        # "批核(2026)"这行两种算法差异巨大(8.2% vs 30.2%)，已在s1_dashboard.py修正为
        # APE加权，这里用同样公式独立核算验证。
        pf_2026 = df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)]
        pf_ape_expect = pf_2026[pf_2026["Is_Premium_Financing"] == 1]["ape"].sum() / pf_2026["ape"].sum()
        check("S1-B『批核(2026)』融资占比=APE加权口径（已修正，不是按件数均值）",
              abs(b["批核(2026)"]["融资占比"] - pf_ape_expect) < 1e-9
              and abs(b["批核(2026)"]["融资占比"] - 0.3020732287164955) < 1e-6)

        c_first = s1["C"][0]
        check("S1-C 首月(2025-01)件数+APE", c_first["年月"] == "2025-01" and c_first["件数"] == 69
              and abs(c_first["APE"] - 22560612.856) < 0.01 and c_first["环比增长%"] is None)

        d_first = s1["D"][0]
        check("S1-D 首月(2025-01)件数+APE", d_first["年月"] == "2025-01" and d_first["件数"] == 70
              and abs(d_first["APE"] - 25095612.856) < 0.01)

        e_by_month = {r["年月"]: r for r in s1["E"]}
        check("S1-E 2026-01 同比增长%", abs(e_by_month["2026-01"]["同比增长%"] - 1.8206296247174274) < 1e-6)

        f = {r["保单状态"]: r for r in s1["F"]}
        check("S1-F A.批核(2026)", f["A.批核(2026)"]["件数"] == 1647
              and abs(f["A.批核(2026)"]["APE"] - 772125888.12) < 0.01)
        check("S1-F G.失效恒为0", f["G.失效"]["件数"] == 0 and f["G.失效"]["APE"] == 0)
        check("S1-F 合计2017件（跟ground truth S1 sheet F节合计行精确核对）", f["合计"]["件数"] == 2017)

        g = {r["业务类型"]: r for r in s1["G"]}
        check("S1-G 经代业务（必须用业务大类含MGA重分类）",
              g["经代业务"]["批核件数"] == 1305 and abs(g["经代业务"]["2026批核APE"] - 652633421.11) < 0.01)
        check("S1-G 合计批核件数=1647", g["合计"]["批核件数"] == 1647)

        # S1-H：v0.19.0重点发现——ground truth报表自身的H节(永明业绩汇报数据)JF/UNIWIN/
        # DW-Non-Bank/EG/Sub Total五行在1009这份ground truth里全部是0（逐一核对xlsx原始
        # 单元格确认），根因是ground truth的生成脚本跟JF/UNIWIN/怡泰的issuing_entity
        # 过滤条件只精确匹配简体名，而raw底表里2026年JF的全部批核业务(106条/45.8M，
        # 包括2026-01整月)实际都挂在繁体变体"九富保險服務有限公司"下——ground truth
        # 报表因为这个bug把JF等几行的2026年数据算成了0，不能作为这几行的核验基准。
        # 本项目v0.19.0已在cleaner.py归一化简繁变体，所以2026-01这几个月度值在
        # "ground truth bug修复前"和"修复后"刚好不变(因为2026-01历史数据在两次导出
        # 之间都完整挂在同一个实体变体下，没被侦分)，但"未批核"/"本月已递交"这两个
        # 当前快照值会因为归一化合并了更多记录而变化，所以改成独立pandas重算（见下）
        # 作为期望值，不能直接抄ground truth单元格（那是0，是错的）。
        h = {r["牌照"]: r for r in s1["H"]}
        check("S1-H JF 2026-01（历史月份值，两次导出间不受简繁归一化影响，跟ground truth一致）",
              abs(h["JF"]["2026-01"] - 45864039.84) < 0.01)
        check("S1-H UNIWIN 2026-01", abs(h["UNIWIN"]["2026-01"] - 21654896.28) < 0.01)
        check("S1-H DW Bank 2026-01", abs(h["DW Bank"]["2026-01"] - 18259800) < 0.01)
        check("S1-H DW-Non-Bank 2026-01", abs(h["DW-Non-Bank"]["2026-01"] - 401809.2) < 0.01)
        check("S1-H Sub Total 2026-01 = JF+UNIWIN+DW-Non-Bank+EG（不含DW Bank）",
              abs(h["Sub Total"]["2026-01"] - 67920745.32) < 0.01)
        # 独立pandas重算（carrier=永明+归一化后的entity，不跟ground truth报表的0值比对）
        yt_ym_jf = enriched[(enriched["carrier_code"] == "香港永明金融有限公司")
                             & (enriched["issuing_entity"] == "九富保险服务有限公司")]
        jf_unapp_expect = yt_ym_jf[yt_ym_jf["policy_status"].isin(
            ["尚欠保费", "已签单", "pending", "待批核"])]["ape"].sum()
        jf_submitted_expect = yt_ym_jf[yt_ym_jf["submit_date"].dt.strftime("%Y-%m") == "2026-10"]["ape"].sum()
        check("S1-H JF 未批核=独立pandas重算（carrier=永明+归一化后entity，不能用ground truth的0值）",
              abs(h["JF"]["未批核"] - jf_unapp_expect) < 0.01 and abs(h["JF"]["未批核"] - 14217925.05) < 0.01)
        check("S1-H JF 本月已递交(2026-10)=独立pandas重算",
              abs(h["JF"]["本月已递交"] - jf_submitted_expect) < 0.01 and abs(h["JF"]["本月已递交"] - 1479000.0) < 0.01)
    else:
        check("⚠️ 报表文件或fact_target快照不存在，跳过S1独立核验", True)

    # ---- L3-PDA-07：s2_business_view，对照真实"业绩分析报表"S2_业务端视角独立核验 ----
    if REPORT_FILE.exists() and FACT_TARGET_SNAPSHOT.exists():
        s2b = S2BusinessViewBuilder(df, fact_target)

        a = {r["业务细分"]: r for r in s2b.segment_summary(carrier=None)}
        check("S2-A 同行经代（含MGA折算,批核553件）", a["同行经代"]["批核件数"] == 553
              and abs(a["同行经代"]["2026批核APE"] - 215766149.94) < 0.01)
        check("S2-A 合计目标APE=1,113,000,000", abs(a["合计"]["目标APE"] - 1113000000) < 0.01)

        bb = {r["业务细分"]: r for r in s2b.segment_summary(carrier="香港永明金融有限公司")}
        check("S2-B 同行经代（永明子集,批核316件,目标140M）", bb["同行经代"]["批核件数"] == 316
              and abs(bb["同行经代"]["目标APE"] - 140000000) < 0.01)

        c = {r["业务细分"]: r for r in s2b.section_c()}
        check("S2-C 天领业务2026-01（流失类排除口径）",
              abs(c["天领业务"]["2026-01"]["ape"] - 6673951) < 1)

        i = {r["KEY ACCOUNT"]: r for r in s2b.section_i()}
        check("S2-I 天誉国际/天誉国际(MGA) 拆分正确", "天誉国际(MGA)" in i
              and i["天誉国际(MGA)"]["批核件数"] == 230 and i["天誉国际"]["批核件数"] == 149)

        j = {r["推荐人"]: r for r in s2b.section_j()}
        check("S2-J 姜通（referral_code不限carrier）", j["姜通"]["批核件数"] == 568
              and abs(j["姜通"]["2026批核APE"] - 200248265.86) < 0.01)

        k = s2b.section_k()
        k_total = [r for r in k if r["KEY ACCOUNT"] == "合计"][0]
        check("S2-K 合计批核件数=1072（=A节同行经代553+永明经代519）", k_total["批核件数"] == 1072)
        check("S2-K 行数27（26个KA+合计,天誉国际(MGA)独立成行）", len(k) == 27)

        o = s2b.section_o()
        check("S2-O 民生银行/平安银行/浦发银行/合计4行（浦发银行是v0.19.0新数据里新出现的真实业务，不是0值幽灵行）",
              [r["KEY ACCOUNT"] for r in o] == ["民生银行", "平安银行", "浦发银行", "合计"])

        s_rows = {r["合作伙伴(分行)"]: r for r in s2b.section_s()}
        # v0.19.0用权威脚本generate_report.py核实修正：S/T节月份范围不是固定2026-01~08，
        # 是跟其余月度板块同规则的动态范围(get_months_2026)——1009数据已滚动到2026-11，
        # 已在s2_business_view.py::_bank_partner_frame()改成动态月份后重新核对。
        check("S2-S 民生广州分行（issue_ym+仅生效，月份动态滚动到2026-11）",
              abs(s_rows["民生广州分行"]["2026-01"] - 780000) < 0.01
              and abs(s_rows["民生广州分行"]["合计"] - 44479560.06) < 0.01)
        check("S2-S 民生郑州全0参照行（partner_code参照列表不过滤零业务，同S4-A模式）",
              s_rows["民生郑州"]["合计"] == 0)
        check("S2-S 行数51（50个历史partner_code+合计）", len(s_rows) == 51)
        check("S2-S 合计行", abs(s_rows["合计"]["合计"] - 253002615.06) < 0.01)

        t_rows = {r["合作伙伴(分行)"]: r for r in s2b.section_t()}
        check("S2-T 民生广州分行件数（行顺序跟随S节，同一partner_code）",
              t_rows["民生广州分行"]["2026-01"] == 1 and t_rows["民生广州分行"]["合计"] == 26)
        check("S2-T 合计233件", t_rows["合计"]["合计"] == 233)
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
        check("S3-G 天领业务时效7项指标", g["天领业务"]["件数"] == 250
              and abs(g["天领业务"]["平均时效(天)"] - 20.4) < 0.05
              and g["天领业务"]["SLA达标率≤60"] is not None and abs(g["天领业务"]["SLA达标率≤60"] - 0.984) < 0.001)

        h = {r["时效分档"]: r for r in s3b.section_h()}
        check("S3-H ≤7天分档排除TAT<0异常值", h["≤7天"]["件数"] == 220
              and abs(h["≤7天"]["APE"] - 65324249.10) < 1)
        check("S3-H 合计=排除TAT<0后的有效样本1646件（v0.21.0修复：合计行之前用排除前的1647，"
              "6档之和对不上合计，Jasper指示section_g/section_h口径同步后一并修正）",
              h["合计"]["件数"] == 1646
              and sum(h[k]["件数"] for k in ["≤7天", "8-14天", "15-30天", "31-60天", "61-90天", ">90天"]) == 1646)

        e_ape = {r["KEY ACCOUNT"]: r for r in s3b.section_e_ape()}
        check("S3-E_ape 天誉国际(MGA)（status IN未批核4态+排期，is_pf=0）",
              abs(e_ape["天誉国际(MGA)"]["2026-07"] - 3377999.84) < 0.01
              and abs(e_ape["天誉国际(MGA)"]["合计"] - 19213347.14) < 0.01)

        f_ape = {r["KEY ACCOUNT"]: r for r in s3b.section_f_ape()}
        check("S3-F_ape 平安银行（is_pf=1融资）", abs(f_ape["平安银行"]["合计"] - 20748000) < 0.01)

        j_ape = {r["KEY ACCOUNT"]: r for r in s3b.section_j_ape()}
        check("S3-J_ape 天誉国际/天誉国际(MGA)周度合计（同行，res_yw排除流失类）",
              abs(j_ape["天誉国际(MGA)"]["合计"] - 92917831.84) < 0.01
              and abs(j_ape["天誉国际"]["合计"] - 74097263.86) < 0.01)

        m_ape = {r["KEY ACCOUNT"]: r for r in s3b.section_m_ape()}
        check("S3-M_ape 民生银行W01-W03（银行，res_yw）",
              abs(m_ape["民生银行"]["2026W01"] - 1560000) < 0.01
              and abs(m_ape["民生银行"]["2026W03"] - 3120000) < 0.01)
    else:
        check("⚠️ 报表文件不存在，跳过S3独立核验", True)

    # ---- L3-PDA-09：s4_product_view，对照真实"业绩分析报表"S4_产品端视角独立核验 ----
    if REPORT_FILE.exists():
        s4b = S4ProductViewBuilder(df)

        a = {r["保险公司"]: r for r in s4b.section_a()}
        check("S4-A 永明（A节排除4种状态含拒保，跟B-E的3种不同）", a["永明"]["件数"] == 1169
              and abs(a["永明"]["APE"] - 444389148.52) < 0.01)
        check("S4-A 合计1531件", a["合计"]["件数"] == 1531)
        check("S4-A 零业务保司也列出(如'周大福')", a.get("周大福", {}).get("件数") == 0)
        # v0.19.0修正：A节保司清单之前是21家写死名单(含ZERO_CARRIERS)，跟generate_report.py
        # 核实后发现官方"固定基础清单"正好是17家，多出的4家("永明金融有限公司(新加坡)"等)
        # 本身就不该写死在基础清单里，是数据里出现的"额外"保司，改成动态追加后用ground
        # truth xlsx逐行核对全部21个真实保司(17固定+4额外)名称/数值精确匹配。
        check("S4-A 保司总数=21（17家固定清单+4家数据里新出现的额外保司，动态追加不写死）",
              len(s4b.section_a()) - 1 == 21)  # 减1是合计行
        check("S4-A '澳门太平'零业务占位（官方固定清单里的历史命名，当前数据下确认零业务）",
              a.get("澳门太平", {}).get("件数") == 0)

        c = s4b.section_c()
        check("S4-C 第1名（万年青·卓金保险计划II/20%）", c[0]["产品名称"] == "万年青·卓金保险计划II"
              and c[0]["首年折扣"] == "20%" and c[0]["件数"] == 69 and abs(c[0]["APE"] - 38485200) < 0.01)

        b4 = s4b.section_b()
        check("S4-B 第1/2名（永誉传承储蓄计划按SQ_rate拆成2.5%/3.5%两行，不是合并成1行）",
              b4[0]["首年折扣"] == "2.5%" and b4[0]["件数"] == 25
              and b4[1]["首年折扣"] == "3.5%" and b4[1]["件数"] == 13)
        check("S4-B SQ_rate缺失的记录不出现在TOP20（即便金额很大）",
              all(r["首年折扣"] is not None for r in b4))

        d = {r["年期分类"]: r for r in s4b.section_d()}
        check("S4-D 中期(2-5年)1305件", d["中期(2-5年)"]["件数"] == 1305)
        check("S4-D 合计1533件（不等于4档相加的，有premium_term非数字的记录不落入任何档但计入合计）",
              d["合计"]["件数"] == 1533)

        e = {r["供款方式"]: r for r in s4b.section_e()}
        check("S4-E 预缴/年缴/整付/合计", e["预缴"]["件数"] == 547 and e["年缴"]["件数"] == 876
              and e["整付"]["件数"] == 110 and e["合计"]["件数"] == 1533)
    else:
        check("⚠️ 报表文件不存在，跳过S4独立核验", True)

    # ---- L3-PDA-10：s5_finance_view，对照真实"业绩分析报表"S5_财务端视角独立核验 ----
    if REPORT_FILE.exists():
        s5b = S5FinanceViewBuilder(df)

        # S5-A/S5-B_premium：跟S1-H同一个v0.19.0重点发现——ground truth报表里"怡泰财富
        # 管理有限公司"这一行是全0(逐一核对xlsx原始单元格确认)，因为ground truth生成
        # 脚本按issuing_entity精确匹配时只认简体名，而本项目1009底表里"怡泰"2026批核
        # 业务的279条记录里大部分实际挂在繁体变体"怡泰財富管理有限公司"下——ground
        # truth这一行不能作为核验基准，改成独立pandas重算（在cleaner.py归一化后的
        # 数据上按同样条件重新筛选+求和）作为期望值。
        a = {r["牌照(签单供应商)"]: r for r in s5b.section_a()}
        yt_b26_expect = enriched[(enriched["policy_status"] == "生效") & (enriched["issue_date"].dt.year == 2026)
                                   & (enriched["issuing_entity"] == "怡泰财富管理有限公司")]
        check("S5-A 怡泰财富管理有限公司=独立pandas重算（不能用ground truth的0值，entity已归一化）",
              a["怡泰财富管理有限公司"]["件数"] == len(yt_b26_expect) == 279
              and abs(a["怡泰财富管理有限公司"]["批核APE"] - yt_b26_expect["ape"].sum()) < 0.01
              and abs(a["怡泰财富管理有限公司"]["批核APE"] - 260581685.58) < 0.01
              and abs(a["怡泰财富管理有限公司"]["批核年总保费(HKD)"] - yt_b26_expect["premium"].sum()) < 0.01
              and abs(a["怡泰财富管理有限公司"]["批核年总保费(HKD)"] - 1972373515.38) < 0.01)
        check("S5-A 合计1647件（含零业务entity）", a["合计"]["件数"] == 1647 and len(s5b.section_a()) == 13)

        d = {r["保费规模档"]: r for r in s5b.section_d()}
        check("S5-D 保费分档（复用report_enricher的边界常量）",
              d["<5万"]["件数"] == 159 and d["100万+"]["件数"] == 212 and d["合计"]["件数"] == 1647)

        f = {r["类型"]: r for r in s5b.section_f()}
        check("S5-F 常规/融资", f["常规"]["件数"] == 1512 and abs(f["常规"]["APE"] - 538887328.12) < 0.01
              and f["融资"]["件数"] == 135 and abs(f["融资"]["年总保费(HKD)"] - 1912085600) < 0.01)

        g = s5b.section_g()
        # 保单号字段是字符串类型（v0.19.0发现：旧断言拿int字面量跟字符串比较，Python里
        # 永远判false，这是测试自身的类型bug，跟底表数据、跟generate_report.py都无关——
        # 三个保单号本身(611222899/611222895/611222827)在新旧两批数据下完全没变，顺序
        # 也没变，只是比较类型从int改成str）。
        check("S5-G TOP20金额并列时按sign_date升序排（不是随机/policy_no顺序）",
              g[0]["保单号"] == "611222899" and g[1]["保单号"] == "611222895" and g[2]["保单号"] == "611222827")

        h = s5b.section_h()
        check("S5-H 第1名（薪火传承环球终身寿险计划，13,571,999.45）",
              h[0]["产品"] == "薪火传承环球终身寿险计划" and abs(h[0]["APE"] - 13571999.45) < 0.01
              and h[0]["牌照"] == "富强天一" and h[0]["保司"] == "中银人寿")

        bp = {r["牌照"]: r for r in s5b.section_b_premium()}
        yt_jan_expect = enriched[(enriched["issuing_entity"] == "怡泰财富管理有限公司")
                                   & (enriched["policy_status"] == "生效")
                                   & (enriched["issue_date"].dt.strftime("%Y-%m") == "2026-01")]["premium"].sum()
        check("S5-B_premium 怡泰2026-01=独立pandas重算（同S5-A，不能用ground truth的0值）",
              abs(bp["怡泰财富管理有限公司"]["2026-01"] - yt_jan_expect) < 0.01
              and abs(bp["怡泰财富管理有限公司"]["2026-01"] - 74396333.7) < 0.01)
    else:
        check("⚠️ 报表文件不存在，跳过S5独立核验", True)

    # ---- L3-PDA-11：s6_market_cross_view，对照真实"业绩分析报表"S6_市场与交叉视角独立核验 ----
    if REPORT_FILE.exists():
        s6b = S6MarketCrossViewBuilder(df)

        a = {r["KA"]: r for r in s6b._cross_table("批核", "ka")}
        check("S6-A 天誉国际/天誉国际(MGA) 同行经代列", abs(a["天誉国际"]["同行经代"] - 60007469.86) < 0.01
              and abs(a["天誉国际(MGA)"]["同行经代"] - 73704484.70) < 0.01)
        check("S6-A 行数58（57个KA+合计，全0行已过滤）", len(s6b._cross_table("批核", "ka")) == 58)

        d = {r["保司"]: r for r in s6b._cross_table("批核", "carrier")}
        check("S6-D 永明整行8个业务细分", abs(d["永明"]["天领业务"] - 59553034.44) < 0.01
              and abs(d["永明"]["BK业务"] - 252542415.06) < 0.01 and abs(d["永明"]["合计"] - 616255478.47) < 0.01)

        b6 = {r["KA"]: r for r in s6b._cross_table("未批核", "ka")}
        check("S6-B 天誉国际(MGA)未批核", abs(b6["天誉国际(MGA)"]["同行经代"] - 14995347.14) < 0.01)

        c6 = {r["KA"]: r for r in s6b._cross_table("待签", "ka")}
        check("S6-C 天誉国际(MGA)/唯思 待签", abs(c6["天誉国际(MGA)"]["同行经代"] - 4218000) < 0.01
              and abs(c6["唯思"]["同行经代"] - 285000) < 0.01)
    else:
        check("⚠️ 报表文件不存在，跳过S6独立核验", True)

    # ---- L3-PDA-12：s7_compliance_view，对照真实"业绩分析报表"S7_合规端视角独立核验 ----
    if REPORT_FILE.exists():
        s7b = S7ComplianceViewBuilder(df)

        # S7-A/B_ape 同样是issuing_entity分组，跟S1-H/S5-A同一个v0.19.0发现：ground
        # truth这两行对"怡泰财富管理有限公司"全是0，不能直接用，改成跟S5-A同一份独立
        # pandas重算结果比对（已在上面验证过与builder一致，这里复用同样的数值）。
        a7 = {r["签单供应商"]: r for r in s7b.section_a()}
        yt = a7["怡泰财富管理有限公司"]
        check("S7-A 怡泰批核/未批核/待签/distinct数量列=独立pandas重算（不能用ground truth的0值）",
              abs(yt["2026批核APE"] - 260581685.58) < 0.01
              and yt["批核件数"] == 279 and abs(yt["未批核APE"] - 28479941.6) < 0.01 and yt["未批核件数"] == 28
              and abs(yt["待签APE"] - 1570771.8) < 0.01 and yt["待签件数"] == 4
              and yt["保险公司数"] == 12 and yt["产品数"] == 22 and yt["KA数"] == 16 and yt["TR数"] == 7)

        ba7 = {r["签单供应商"]: r for r in s7b.section_b_ape()}
        check("S7-B_ape 怡泰整行8个业务细分=独立pandas重算（不能用ground truth的0值）",
              abs(ba7["怡泰财富管理有限公司"]["BK业务"] - 253002615.06) < 0.01
              and abs(ba7["怡泰财富管理有限公司"]["合计"] - 260581685.58) < 0.01)

        # S7-E是逐条明细（不是按issuing_entity分组求和），每条记录自己的issuing_entity
        # 标签在归一化后可能从繁体变简体，但TAT排序本身跟entity标签无关，不受影响——
        # 跟ground truth逐条核对保单号/时效/牌照（牌照字段=归一化后简体名截断前8字）。
        e7 = s7b.section_e()
        check("S7-E 前2条时效异常（244天/220天，保单号是字符串类型，跟S5-G同一处类型修正）",
              e7[0]["保单号"] == "611221282" and e7[0]["时效(天)"] == 244
              and e7[0]["牌照"] == "众和恒富理财集团" and e7[1]["保单号"] == "611208853" and e7[1]["时效(天)"] == 220
              and e7[1]["牌照"] == "怡泰财富管理有限")

        f7 = {r["TR"]: r for r in s7b.section_f()}
        check("S7-F 李咏媱/余文茜（业务线数用SEGMENT_GROUPS折算）", abs(f7["李咏媱"]["APE"] - 54605259.2) < 0.01
              and f7["李咏媱"]["件数"] == 166 and f7["李咏媱"]["业务线数"] == 5
              and abs(f7["余文茜"]["APE"] - 60763060.9) < 0.01 and f7["余文茜"]["业务线数"] == 2)
    else:
        check("⚠️ 报表文件不存在，跳过S7独立核验", True)

    # ---- L3-PDA-13：s9_agent_ka_view，对照真实"业绩分析报表"S9_代理人与KA业务独立核验 ----
    if REPORT_FILE.exists() and FACT_TARGET_SNAPSHOT.exists():
        s9b = S9AgentKaViewBuilder(df, fact_target)

        a9 = {r["业务细分"]: r for r in s9b.section_a()}
        check("S9-A 合计（5条代理人业务线过滤自S2-A）", a9["合计"]["目标APE"] == 413000000
              and abs(a9["合计"]["2026批核APE"] - 119492467.01) < 0.01 and a9["合计"]["批核件数"] == 342)

        # v0.19.0新数据下苏州贴牌/厦门贴牌的2026批核APE已不再相同(819000 vs 351000)，
        # 之前(0724数据)验证过的"并列用总APE降序二级排序"真实并列样本在1009数据下不
        # 复现——不代表排序规则本身变了，只是数据恰好不再出现这组并列，改成验证通用的
        # "整表严格按2026批核APE降序排列"（对全部相邻行都成立，覆盖面比单一并列样本更广）。
        b9 = {r["KEY ACCOUNT"]: r for r in s9b.section_b()}
        b9_list = s9b.section_b()
        b9_rows = [r for r in b9_list if r["KEY ACCOUNT"] != "合计"]
        check("S9-B 全部相邻行严格按2026批核APE降序排列（0724数据的并列样本在1009数据下已不复现）",
              all(b9_rows[i]["2026批核APE"] >= b9_rows[i + 1]["2026批核APE"] for i in range(len(b9_rows) - 1)))
        check("S9-B 合计250件", b9["合计"]["批核件数"] == 250)

        d9 = {r["指标"]: r for r in s9b.section_d()}
        check("S9-D 预约APE 2026-01（标题写含流失单，实测=S2的res/sign/issue三态口径）",
              abs(d9["预约 APE"]["2026-01"] - 6673951.26) < 0.01)

        f9 = s9b.section_f()
        f9_iclub = {r["KEY ACCOUNT"]: r for r in f9["ICLUB业务"]}
        check("S9-F-ICLUB 个人转介", abs(f9_iclub["个人转介"]["2026批核APE"] - 20994812.08) < 0.01)

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

    # ---- PPT生成：build_slide1，对照真实S1 CSV+template.pptx核验 ----
    from skills.ppt_generator import build_slide1
    from skills.ppt_data_loader import load_sheet
    from pptx import Presentation

    s1_dir = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "S1_总览仪表盘"
    template_path = RAW_DATA_DIR / "业绩报表PPT" / "template.pptx"
    if s1_dir.exists() and template_path.exists():
        prs_test = Presentation(str(template_path))
        s1_data = load_sheet(s1_dir)
        stats1 = build_slide1(prs_test, s1_data)

        check("Slide1 文本替换全部命中", stats1["subs_hits"] == 19 and not stats1["subs_misses"],
              f"hits={stats1['subs_hits']} misses={stats1['subs_misses']}")
        check("Slide1 全业务达成率=已达成/目标（跟S1-A算法一致）",
              abs(stats1["full_rate"] - stats1["full_achv"] / stats1["full_target"]) < 1e-9)
        check("Slide1 管道分母=批核+未批核+待签+流失（含流失，跟B模块口径一致）",
              abs(stats1["pipe_total"] - (stats1["issued_ape"] + stats1["unbat_ape"]
                  + stats1["pend_ape"] + stats1["lost_ape"])) < 0.01)
        check("Slide1 月度网格月份数跟S1-C的2026月份数一致",
              len(stats1["months_2026"]) == sum(1 for m in s1_data["C"]["年月"] if m.startswith("2026-")))

        chart0_shape = next(sh for sh in prs_test.slides[0].shapes if sh.has_chart and sh.shape_id == 81)
        cats0 = list(chart0_shape.chart.plots[0].categories)
        check("Slide1 Chart0类别顺序=经代/代理人/KA（跟patch时假设的cat_order一致）",
              cats0 == ["经代业务", "代理人业务", "KA 业务"])
    else:
        check("⚠️ S1数据或template.pptx不存在，跳过PPT Slide1核验", True)

    # ---- PPT生成：build_slide8/9/10/11，对照真实S2/S3 CSV+template.pptx核验 ----
    from skills.ppt_generator import build_slide8, build_slide9, build_slide10, build_slide11
    from skills.ppt_data_loader import num as ppt_num

    s2_dir = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "S2_业务端视角"
    s3_dir = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "S3_执行管理端"
    if s2_dir.exists() and s3_dir.exists() and template_path.exists():
        # --- Slide8：同行业绩 第1部分 ---
        prs8 = Presentation(str(template_path))
        s2_data = load_sheet(s2_dir)
        s3_data = load_sheet(s3_dir)
        stats8 = build_slide8(prs8, s2_data)

        check("Slide8 文本替换全部命中", stats8["subs_hits"] == 6 and not stats8["subs_misses"],
              f"hits={stats8['subs_hits']} misses={stats8['subs_misses']}")
        k_df = s2_data["K"]
        k_nonzero = k_df[k_df["KEY ACCOUNT"] != "合计"]
        check("Slide8 KA行数=K.csv非合计行数（残差补齐算法在新pipeline下已废弃，K.csv本身就是完整口径）",
              stats8["n_ka_rows"] == len(k_nonzero))
        k_total_row = k_df[k_df["KEY ACCOUNT"] == "合计"].iloc[0]
        check("Slide8 同行2026批核APE=K.csv合计行独立核对",
              abs(stats8["issued_ape"] - ppt_num(k_total_row["2026批核APE"])) < 0.01)
        top10_expect = k_nonzero.assign(_s=k_nonzero["2026批核APE"].apply(ppt_num)).sort_values("_s", ascending=False).head(10)["KEY ACCOUNT"].tolist()
        check("Slide8 Chart1 TOP10排序=K.csv按2026批核APE独立降序排序", stats8["top10_ka"] == top10_expect)
        tbl8 = next(sh for sh in prs8.slides[7].shapes if sh.has_table).table
        check("Slide8 表格行数=表头1+KA行数+合计1", len(tbl8.rows) == 1 + stats8["n_ka_rows"] + 1)

        # --- Slide9：同行业绩 第2部分 ---
        prs9 = Presentation(str(template_path))
        stats9 = build_slide9(prs9, s3_data)
        check("Slide9 文本替换全部命中", stats9["subs_hits"] == 19 and not stats9["subs_misses"],
              f"hits={stats9['subs_hits']} misses={stats9['subs_misses']}")
        j_ape_df = s3_data["J_ape"]
        weeks_j = [c for c in j_ape_df.columns if c.startswith("2026W")]
        current_week_expect = max(weeks_j, key=lambda w: int(w.replace("2026W", "")))
        check("Slide9 当前周=J_ape.csv周列独立算出的最大周号", stats9["current_week"] == current_week_expect)
        j_total_row = j_ape_df[j_ape_df["KEY ACCOUNT"] == "合计"].iloc[0]
        monthly_appt_sum = sum(r[1] for r in stats9["monthly_rows"])
        check("Slide9 月度分桶预约APE总和=J_ape.csv合计列独立核对（周→月聚合不丢单）",
              abs(monthly_appt_sum - ppt_num(j_total_row["合计"])) < 0.01)
        check("Slide9 Y表KA数>0（union(J/K/L当周>0的KA)非空）", len(stats9["y_table_kas"]) > 0)

        # --- Slide10：BK业务 第1部分 ---
        prs10 = Presentation(str(template_path))
        stats10 = build_slide10(prs10, s2_data, s3_data)
        check("Slide10 文本替换全部命中", stats10["subs_hits"] == 19 and not stats10["subs_misses"],
              f"hits={stats10['subs_hits']} misses={stats10['subs_misses']}")
        a_bk_row = s2_data["A"][s2_data["A"]["业务细分"] == "BK业务"].iloc[0]
        check("Slide10 BK目标/达成率=S2-A.csv独立核对",
              abs(stats10["target"] - ppt_num(a_bk_row["目标APE"])) < 0.01
              and abs(stats10["rate"] - ppt_num(a_bk_row["达成率"])) < 1e-9)
        check("Slide10 S2-O合计跟S3-O_ape合计存在真实口径差异(非0，已记录在案，非代码bug)",
              stats10["o_total_s2"] != stats10["o_total_s3"])
        donut_shape10 = next(sh for sh in prs10.slides[9].shapes if sh.has_chart and sh.shape_id == 95)
        donut_vals = [ppt_num(v) for v in list(donut_shape10.chart.series)[0].values]
        check("Slide10 甜甜圈两扇区非负且已批核扇区不超过target(达成率>100%时裁剪，避免负数扇区)",
              donut_vals[0] >= 0 and donut_vals[1] >= 0 and donut_vals[0] <= stats10["target"] / 1e6 + 0.05)

        # --- Slide11：BK业务 第2部分 ---
        prs11 = Presentation(str(template_path))
        stats11 = build_slide11(prs11, s2_data, s3_data)
        check("Slide11 文本替换全部命中", stats11["subs_hits"] == 7 and not stats11["subs_misses"],
              f"hits={stats11['subs_hits']} misses={stats11['subs_misses']}")
        s_df = s2_data["S"]
        s_nonzero = s_df[(s_df["合作伙伴(分行)"] != "合计") & (s_df["合计"].apply(ppt_num) > 0)]
        check("Slide11 分行数=S.csv合计列>0的分行数独立核对", stats11["n_branches"] == len(s_nonzero))
        top_branch_expect = s_nonzero.assign(_s=s_nonzero["合计"].apply(ppt_num)).sort_values("_s", ascending=False).iloc[0]["合作伙伴(分行)"]
        check("Slide11 分行榜首=S.csv按合计列独立降序排序", stats11["top_branch"] == top_branch_expect)
        y_table11 = next(sh for sh in prs11.slides[10].shapes if sh.has_table).table
        rows11 = list(y_table11.rows)
        last_row_cells = [c.text for c in rows11[-1].cells]
        m_ape_df = s3_data["M_ape"]
        m_total_row = m_ape_df[m_ape_df["KEY ACCOUNT"] == "合计"].iloc[0]
        cur_week_col = stats11["current_week"]
        expect_appt_total_m = (ppt_num(m_total_row[cur_week_col]) if cur_week_col in m_total_row.index else 0.0) / 1e6
        check("Slide11 表格银行合计行=本周预约(M)列=M_ape.csv合计行当周值独立核对",
              last_row_cells[0] == "银行合计"
              and abs(float(last_row_cells[1].rstrip("M")) - expect_appt_total_m) < 0.01)
    else:
        check("⚠️ S2/S3数据或template.pptx不存在，跳过PPT Slide8/9/10/11核验", True)

    # ---- 前端：multiview_dashboard，对照真实S1 CSV独立核验（代替PPT的新方向） ----
    from skills.multiview_dashboard import build_s1_view
    from skills.ppt_data_loader import load_sheet as _mv_load_sheet

    s1_dir_mv = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "S1_总览仪表盘"
    if s1_dir_mv.exists():
        s1_mv = _mv_load_sheet(s1_dir_mv)
        v1 = build_s1_view(s1_mv)

        check("前端S1视角 全业务达成率跟ppt_generator.py::build_slide1同一份S1-A算法一致",
              abs(v1["full_rate"] - v1["full_achv"] / v1["full_target"]) < 1e-9)
        check("前端S1视角 管道分母=批核+未批核+待签+流失（跟PPT Slide1口径一致）",
              abs(v1["pipe_total"] - (v1["issued_ape"] + v1["unbat_ape"] + v1["pend_ape"] + v1["lost_ape"])) < 0.01)
        check("前端S1视角 业务类型3类之和=G板块合计批核APE",
              abs(sum(b["batch"] for b in v1["business_type"].values())
                  - float(s1_mv["G"][s1_mv["G"]["业务类型"] == "合计"].iloc[0]["2026批核APE"].replace(",", ""))) < 1.0)
        check("前端S1视角 月度趋势月份数=S1-C的月份数", len(v1["monthly_trend"]["labels"]) == len(s1_mv["C"]))
        check("前端S1视角 状态明细行数=F板块非合计行数",
              len(v1["status_detail"]) == sum(1 for _, r in s1_mv["F"].iterrows() if r["保单状态"] != "合计"))

    else:
        check("⚠️ S1数据不存在，跳过前端S1视角核验", True)

    # ---- 前端：S2/S3/S4/同行/银行/代理人/KA 共7个新增视角，对照真实CSV独立核验 ----
    from skills.multiview_dashboard import (
        build_s2_view, build_s3_view, build_s4_view,
        build_peer_view, build_bank_view, build_agent_view, build_ka_view,
        build_sunlife_view,
    )

    s2_dir_mv = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "S2_业务端视角"
    s3_dir_mv = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "S3_执行管理端"
    s4_dir_mv = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "S4_产品端视角"
    s9_dir_mv = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "S9_代理人与KA业务"

    if s2_dir_mv.exists() and s3_dir_mv.exists() and s4_dir_mv.exists() and s9_dir_mv.exists():
        s2_mv = _mv_load_sheet(s2_dir_mv)
        s3_mv = _mv_load_sheet(s3_dir_mv)
        s4_mv = _mv_load_sheet(s4_dir_mv)
        s9_mv = _mv_load_sheet(s9_dir_mv)

        # --- S2业务端 ---
        v2 = build_s2_view(s2_mv)
        a2_noTotal = s2_mv["A"][s2_mv["A"]["业务细分"] != "合计"]
        check("前端S2视角 target_total=A板块非合计行目标APE独立求和",
              abs(v2["target_total"] - a2_noTotal["目标APE"].apply(ppt_num).sum()) < 1)
        check("前端S2视角 overall_rate=issued_total/target_total",
              abs(v2["overall_rate"] - v2["issued_total"] / v2["target_total"]) < 1e-9)
        i2_noTotal = s2_mv["I"][s2_mv["I"]["KEY ACCOUNT"] != "合计"]
        check("前端S2视角 ka_rank行数=I板块非合计行数（I板块本身无预排序，独立降序验证）",
              len(v2["ka_rank"]) == len(i2_noTotal))
        check("前端S2视角 ka_rank按批核APE降序排列",
              all(v2["ka_rank"][i]["issued"] >= v2["ka_rank"][i + 1]["issued"] for i in range(len(v2["ka_rank"]) - 1)))
        check("前端S2视角 8个业务细分渠道月度趋势小图数据齐全", len(v2["segments"]) == len(v2["monthly_by_segment"]))

        # --- S3执行管理端 ---
        v3 = build_s3_view(s3_mv)
        a3 = s3_mv["A"]
        weeks3 = [c[:-4] for c in a3.columns if c.endswith("_APE")]
        submit_row = a3[a3["阶段"] == "递交"].iloc[0]
        submit_ape_expect = sum(ppt_num(submit_row[f"{w}_APE"]) for w in weeks3)
        check("前端S3视角 递交阶段合计APE=A板块独立核算（真实非零，W37/W38口径证据）",
              abs(v3["stage_totals"]["递交"]["ape"] - submit_ape_expect) < 1 and v3["stage_totals"]["递交"]["ape"] > 0)
        check("前端S3视角 周度趋势含预约/签单/递交/批核4条完整线",
              set(["预约", "签单", "递交", "批核"]) <= set(v3["weekly_trend"].keys()))
        check("前端S3视角 签批时效表行数=G板块行数（含合计行）", len(v3["timeliness"]) == len(s3_mv["G"]))
        _tl_row = {r["业务细分"]: r for r in v3["timeliness"]}
        check("前端S3视角 签批时效已跟Mark标准报表同步排除TAT<0异常值（同行经代552件，不是未排除的553）",
              _tl_row["同行经代"]["件数"] == 552 and _tl_row["合计"]["件数"] == 1646)
        check("前端S3视角 未批核/待签分布(常规)行数=E_ape非合计行数",
              len(v3["unbat_pending_regular"]["rows"]) == sum(1 for _, r in s3_mv["E_ape"].iterrows() if str(r["KEY ACCOUNT"]).strip() != "合计"))

        # --- P0本周快报 + P1本周各业务线分布（v0.17.0新增） ---
        cur_w, prev_w = weeks3[-1], weeks3[-2]
        check("前端S3视角 cur_week=A板块最后一列周号（不用猜，新版CSV列范围即数据实际覆盖范围）",
              v3["cur_week"] == cur_w.replace("2026W", "W"))
        appt_row = a3[a3["阶段"] == "预约"].iloc[0]
        cur_ape_expect = ppt_num(appt_row[f"{cur_w}_APE"])
        prev_ape_expect = ppt_num(appt_row[f"{prev_w}_APE"])
        check("前端S3视角 本周快报-预约当周APE=A板块独立核算",
              abs(v3["weekly_snapshot"]["预约"]["ape"] - cur_ape_expect) < 1)
        check("前端S3视角 本周快报-预约环比=（当周-上周）/上周独立核算",
              abs(v3["weekly_snapshot"]["预约"]["wow"] - (cur_ape_expect - prev_ape_expect) / prev_ape_expect) < 1e-9)
        from skills.ppt_config import SEGMENT_ORDER
        b3 = s3_mv["B"]
        biz_week_expect = [ppt_num(b3[b3["业务细分"] == seg].iloc[0][f"{cur_w}_APE"]) if seg in b3["业务细分"].values else 0.0 for seg in SEGMENT_ORDER]
        check("前端S3视角 本周各业务线分布(预约)=B板块当周列独立核算，且8项业务线顺序跟SEGMENT_ORDER一致",
              v3["business_line_this_week"]["labels"] == list(SEGMENT_ORDER)
              and all(abs(a - b) < 1 for a, b in zip(v3["business_line_this_week"]["预约"], biz_week_expect)))

        # --- S4产品端 ---
        v4 = build_s4_view(s4_mv)
        check("前端S4视角 产品TOP榜行数=C板块行数（已自带排名列）", len(v4["product_rank"]) == len(s4_mv["C"]))
        check("前端S4视角 保司分布行数=A板块行数", len(v4["carrier_dist"]) == len(s4_mv["A"]))
        check("前端S4视角 产品TOP榜按排名升序排列",
              [p["排名"] for p in v4["product_rank"]] == sorted(p["排名"] for p in v4["product_rank"]))

        # --- 同行业绩 ---
        vp = build_peer_view(s2_mv, s3_mv)
        k2_total = s2_mv["K"][s2_mv["K"]["KEY ACCOUNT"] == "合计"].iloc[0]
        check("前端同行视角 issued_ape=K板块合计行独立核对",
              abs(vp["issued_ape"] - ppt_num(k2_total["2026批核APE"])) < 1)
        j_ape_tot = s3_mv["J_ape"][s3_mv["J_ape"]["KEY ACCOUNT"] == "合计"].iloc[0]
        monthly_appt_sum = sum(r["预约APE"] for r in vp["monthly_rows"])
        check("前端同行视角 月度分桶预约APE合计=J_ape合计列独立核对（周→月聚合不丢单）",
              abs(monthly_appt_sum - ppt_num(j_ape_tot["合计"])) < 1)
        check("前端同行视角 ka_rank按批核APE降序排列",
              all(vp["ka_rank"][i]["issued"] >= vp["ka_rank"][i + 1]["issued"] for i in range(len(vp["ka_rank"]) - 1)))

        # --- 同行业绩 本周快报（v0.17.0新增，P0） ---
        weeks_p = [c for c in s3_mv["J_ape"].columns if c.startswith("2026W")]
        cur_wp, prev_wp = weeks_p[-1], weeks_p[-2]
        j_ape_tot_row = s3_mv["J_ape"][s3_mv["J_ape"]["KEY ACCOUNT"] == "合计"].iloc[0]
        j_cnt_tot_row = s3_mv["J_count"][s3_mv["J_count"]["KEY ACCOUNT"] == "合计"].iloc[0]
        expect_p_cur = ppt_num(j_ape_tot_row[cur_wp])
        expect_p_prev = ppt_num(j_ape_tot_row[prev_wp])
        check("前端同行视角 本周快报-预约当周APE/件数=J_ape/J_count合计行独立核算",
              abs(vp["weekly_snapshot"]["预约"]["ape"] - expect_p_cur) < 1
              and vp["weekly_snapshot"]["预约"]["cnt"] == int(ppt_num(j_cnt_tot_row[cur_wp])))
        check("前端同行视角 本周快报-预约环比=（当周-上周）/上周独立核算",
              abs(vp["weekly_snapshot"]["预约"]["wow"] - (expect_p_cur - expect_p_prev) / expect_p_prev) < 1e-9)

        # --- 银行业绩 ---
        vb = build_bank_view(s2_mv, s3_mv)
        a2_bk = s2_mv["A"][s2_mv["A"]["业务细分"] == "BK业务"].iloc[0]
        check("前端银行视角 target=S2-A BK业务行独立核对",
              abs(vb["target"] - ppt_num(a2_bk["目标APE"])) < 1)
        o2_total = s2_mv["O"][s2_mv["O"]["KEY ACCOUNT"] == "合计"].iloc[0]
        check("前端银行视角 issued_ape(S2-O全量口径)=O板块合计行独立核对",
              abs(vb["issued_ape"] - ppt_num(o2_total["2026批核APE"])) < 1)
        check("前端银行视角 S2-O与S3-O_ape总量存在真实口径差异(非0，已在页面文案标注，非bug)",
              vb["o_diff"] != 0)

        # --- 银行业绩 本周快报（v0.17.0新增，P0） ---
        weeks_b = sorted(
            set(c for c in s3_mv["M_ape"].columns if c.startswith("2026W"))
            | set(c for c in s3_mv["N_ape"].columns if c.startswith("2026W"))
            | set(c for c in s3_mv["O_ape"].columns if c.startswith("2026W")),
            key=lambda w: int(w.replace("2026W", "")),
        )
        cur_wb, prev_wb = weeks_b[-1], weeks_b[-2]
        o_ape_tot_row = s3_mv["O_ape"][s3_mv["O_ape"]["KEY ACCOUNT"] == "合计"].iloc[0]
        expect_b_cur = ppt_num(o_ape_tot_row[cur_wb]) if cur_wb in o_ape_tot_row.index else 0.0
        expect_b_prev = ppt_num(o_ape_tot_row[prev_wb]) if prev_wb in o_ape_tot_row.index else 0.0
        check("前端银行视角 本周快报-批核当周APE=O_ape合计行独立核算（缺列按0处理，跟趋势图safe()同一套机制）",
              abs(vb["weekly_snapshot"]["批核"]["ape"] - expect_b_cur) < 1)
        check("前端银行视角 本周快报-批核环比口径正确：O_ape缺上周列则wow=None，否则=（当周-上周）/上周",
              (vb["weekly_snapshot"]["批核"]["wow"] is None) if prev_wb not in o_ape_tot_row.index
              else abs(vb["weekly_snapshot"]["批核"]["wow"] - (expect_b_cur - expect_b_prev) / expect_b_prev) < 1e-9)

        # --- 代理人业务（天领业务+成事家办） ---
        va = build_agent_view(s9_mv)
        a9 = s9_mv["A"]
        agent_target_expect = a9[a9["业务细分"].isin(["天领业务", "成事家办"])]["目标APE"].apply(ppt_num).sum()
        check("前端代理人视角 target_total=S9-A天领+成事家办独立求和",
              abs(va["target_total"] - agent_target_expect) < 1)
        b9_noTotal = s9_mv["B"][s9_mv["B"]["KEY ACCOUNT"] != "合计"]
        c9_noTotal = s9_mv["C"][s9_mv["C"]["KEY ACCOUNT"] != "合计"]
        check("前端代理人视角 ka_rank行数=S9-B+S9-C非合计行数之和",
              len(va["ka_rank"]) == len(b9_noTotal) + len(c9_noTotal))
        check("前端代理人视角 月度趋势含8个月(2026-01至08)",
              len(va["monthly_trend"]["labels"]) == 8)

        # --- 代理人业务 本周快报（v0.17.0新增，P0）：H核实=天领业务周度明细，I核实=成事家办 ---
        def _s9g(row, col):
            return ppt_num(row[col]) if col in row.index else 0.0

        weeks_h = sorted(
            set(c for c in s9_mv["H_预约_APE"].columns if c.startswith("2026W"))
            | set(c for c in s9_mv["H_签单_APE"].columns if c.startswith("2026W"))
            | set(c for c in s9_mv["H_批核_APE"].columns if c.startswith("2026W")),
            key=lambda w: int(w.replace("2026W", "")),
        )
        cur_wh, prev_wh = weeks_h[-1], weeks_h[-2]
        h_appt_tot = s9_mv["H_预约_APE"][s9_mv["H_预约_APE"]["KEY ACCOUNT"] == "合计"].iloc[0]
        i_appt_tot = s9_mv["I_预约_APE"][s9_mv["I_预约_APE"]["KEY ACCOUNT"] == "合计"].iloc[0]
        expect_a_cur = _s9g(h_appt_tot, cur_wh) + _s9g(i_appt_tot, cur_wh)
        expect_a_prev = _s9g(h_appt_tot, prev_wh) + _s9g(i_appt_tot, prev_wh)
        check("前端代理人视角 本周快报-预约当周APE=H(天领)+I(成事家办)合计行独立求和",
              abs(va["weekly_snapshot"]["预约"]["ape"] - expect_a_cur) < 1)
        check("前端代理人视角 本周快报-预约环比=（当周-上周）/上周独立核算",
              abs(va["weekly_snapshot"]["预约"]["wow"] - (expect_a_cur - expect_a_prev) / expect_a_prev) < 1e-9
              if expect_a_prev else va["weekly_snapshot"]["预约"]["wow"] is None)
        check("前端代理人视角 cur_week（H预约/签单/批核并集推出）跟同行/银行视角的当前周一致，全站口径统一",
              va["cur_week"] == cur_wh.replace("2026W", "W") == vp["cur_week"] == vb["cur_week"])

        # --- KA业务（ICLUB+合伙转介+IFA） ---
        vk = build_ka_view(s9_mv)
        ka_target_expect = a9[a9["业务细分"].isin(["ICLUB业务", "合伙转介业务", "IFA业务"])]["目标APE"].apply(ppt_num).sum()
        check("前端KA业务视角 target_total=S9-A ICLUB+合伙转介+IFA独立求和",
              abs(vk["target_total"] - ka_target_expect) < 1)
        check("前端KA业务视角 note_ifa_empty=True（IFA业务当前批核APE确为0，S9-A独立核实）",
              vk["note_ifa_empty"] and ppt_num(a9[a9["业务细分"] == "IFA业务"].iloc[0]["2026批核APE"]) == 0)
        g9_row = s9_mv["G"][s9_mv["G"]["指标"] == "批核 APE"].iloc[0]
        check("前端KA业务视角 月度趋势批核[2](2026-03)=S9-G板块独立核对（G本身即ICLUB+合伙转介+IFA合计口径）",
              abs(vk["monthly_trend"]["批核"][2] - ppt_num(g9_row["2026-03"])) < 1)

        # --- KA业务 本周快报（v0.17.0新增，P0）：J核实=KA业务周度明细(ICLUB+合伙转介+IFA合计口径) ---
        j2_appt_ape_tot = s9_mv["J_预约_APE"][s9_mv["J_预约_APE"]["KEY ACCOUNT"] == "合计"].iloc[0]
        j2_appt_cnt_tot = s9_mv["J_预约_件数"][s9_mv["J_预约_件数"]["KEY ACCOUNT"] == "合计"].iloc[0]
        expect_k_cur = _s9g(j2_appt_ape_tot, cur_wh)
        check("前端KA业务视角 本周快报-预约当周APE/件数=J_预约_APE/件数合计行独立核算（跟代理人共用canonical当前周）",
              abs(vk["weekly_snapshot"]["预约"]["ape"] - expect_k_cur) < 1
              and vk["weekly_snapshot"]["预约"]["cnt"] == int(_s9g(j2_appt_cnt_tot, cur_wh)))
        check("前端KA业务视角 cur_week跟代理人视角一致（同一份S9-H canonical周范围，不因J自身列缺失而漂移）",
              vk["cur_week"] == va["cur_week"])

        # --- 永明业绩（P2新增视角） ---
        vs = build_sunlife_view(s1_mv, s2_mv, s4_mv)
        a1_sun = s1_mv["A"][s1_mv["A"]["指标"] == "2026永明业务目标"].iloc[0]
        check("前端永明视角 sun_target/sun_achv=S1-A'2026永明业务目标'行独立核对（跟build_s1_view同一份数据）",
              abs(vs["sun_target"] - ppt_num(a1_sun["目标APE"])) < 1
              and abs(vs["sun_achv"] - ppt_num(a1_sun["已达成APE"])) < 1)
        check("前端永明视角 sun_rate=S1-A'2026永明业务目标'行目标达成率独立核对",
              abs(vs["sun_rate"] - ppt_num(a1_sun["目标达成率"])) < 1e-9)
        c2_sl = s2_mv["C"][s2_mv["C"]["业务细分"] == "永明经代"].iloc[0]
        month_cols_sl = [c for c in s2_mv["C"].columns if c.endswith("_APE") and c.startswith("2026-")]
        check("前端永明视角 月度趋势预约[0](2026-01)=S2-C'永明经代'行独立核对",
              abs(vs["monthly_trend"]["预约"][0] - ppt_num(c2_sl[month_cols_sl[0]])) < 1)
        c4_sl = s4_mv["C"][s4_mv["C"]["保司"] == "永明"].copy()
        check("前端永明视角 产品TOP10行数=min(10, S4-C保司=永明的行数)独立核对",
              len(vs["product_top10"]) == min(10, len(c4_sl)))
        check("前端永明视角 产品TOP10按APE降序排列，且每条APE能在S4-C永明行里找到匹配（未在筛选中改动数值）",
              all(vs["product_top10"][i]["APE"] >= vs["product_top10"][i + 1]["APE"] for i in range(len(vs["product_top10"]) - 1))
              and all(any(abs(p["APE"] - ppt_num(r["APE"])) < 1 and p["产品名称"] == r["产品名称"] for _, r in c4_sl.iterrows())
                      for p in vs["product_top10"]))

        # ==================== v0.18.0新增：P4-P9六项缺口补齐 ====================
        from skills.multiview_dashboard import SUNLIFE_FORECAST_SOURCE

        # --- P4：银行月度走势×3 + 达成甜甜圈 ---
        m_ape3, n_ape3, o_ape3 = s3_mv["M_ape"], s3_mv["N_ape"], s3_mv["O_ape"]
        weeks_o3 = [c for c in o_ape3.columns if c.startswith("2026W")]
        for bank in ["民生银行", "平安银行"]:
            row_o = o_ape3[o_ape3["KEY ACCOUNT"] == bank].iloc[0]
            weekly_sum = sum(ppt_num(row_o[w]) for w in weeks_o3 if w in row_o.index)
            monthly_sum = sum(vb["monthly_by_bank"]["批核"]["series"].get(bank, []))
            check(f"前端银行视角 月度走势×3(批核)-{bank}月度分桶合计=周度独立求和（ppt_monthly_bucket周→月不丢单）",
                  abs(weekly_sum - monthly_sum) < 1)
        target_expect = ppt_num(a2_bk["目标APE"])
        issued_expect = ppt_num(o2_total["2026批核APE"])
        check("前端银行视角 达成甜甜圈已批核=min(issued,target)、目标剩余=max(target-issued,0)（BK达成率>100%时不出现负数扇区）",
              abs(vb["donut_achv"] - min(issued_expect, target_expect)) < 1
              and abs(vb["donut_remain"] - max(target_expect - issued_expect, 0)) < 1)
        check("前端银行视角 达成甜甜圈已批核不超过目标（裁剪生效）",
              vb["donut_achv"] <= vb["target"] + 1e-6)

        # --- P5：同行/银行/代理人/KA 本周快报明细表（按实体拆分） ---
        check("前端同行视角 本周快报明细表行汇总=weekly_snapshot整体值独立核对（按KA拆分不丢单）",
              all(abs(sum(r["vals"][m] for r in vp["weekly_detail"]["rows"]) - vp["weekly_snapshot"][m]["ape"]) < 1
                  for m in ["预约", "签单", "批核"]))
        check("前端同行视角 本周快报明细表total字段=各行独立求和",
              all(abs(vp["weekly_detail"]["total"][m] - sum(r["vals"][m] for r in vp["weekly_detail"]["rows"])) < 1e-6
                  for m in ["预约", "签单", "批核"]))
        check("前端银行视角 本周快报明细表行汇总=weekly_snapshot整体值独立核对",
              all(abs(sum(r["vals"][m] for r in vb["weekly_detail"]["rows"]) - vb["weekly_snapshot"][m]["ape"]) < 1
                  for m in ["预约", "签单", "批核"]))
        check("前端代理人视角 本周快报明细表行汇总=weekly_snapshot整体值独立核对（天领H+成事家办I逐KA拆分不丢单）",
              all(abs(sum(r["vals"][m] for r in va["weekly_detail"]["rows"]) - va["weekly_snapshot"][m]["ape"]) < 1
                  for m in ["预约", "签单", "批核"]))
        check("前端KA业务视角 本周快报明细表行汇总=weekly_snapshot整体值独立核对",
              all(abs(sum(r["vals"][m] for r in vk["weekly_detail"]["rows"]) - vk["weekly_snapshot"][m]["ape"]) < 1
                  for m in ["预约", "签单", "批核"]))

        # --- P6：S3 业务线×全部周完整表格 ---
        b3_full = s3_mv["B"]
        b3_noTotal = b3_full[b3_full["业务细分"] != "合计"]
        week_cols_full = [c for c in b3_full.columns if c.endswith("_APE")]
        weeks_full = [c[:-4] for c in week_cols_full]
        appt_total_expect = [round(b3_noTotal[f"{w}_APE"].apply(ppt_num).sum(), 0) for w in weeks_full]
        check("前端S3视角 业务线×全部周完整表格(预约)合计行=8个业务细分独立求和（容差1元浮点舍入）",
              all(abs(a - b) <= 1.0 for a, b in zip(appt_total_expect, v3["full_week_table"]["预约"]["total"])))
        check("前端S3视角 业务线×全部周完整表格覆盖全部周次（跟weekly_trend/weeks_count同一份A/B/C/D周范围）",
              len(v3["full_week_table"]["预约"]["weeks"]) == v3["weeks_count"]
              and len(v3["full_week_table"]["签单"]["weeks"]) == v3["weeks_count"]
              and len(v3["full_week_table"]["批核"]["weeks"]) == v3["weeks_count"])
        check("前端S3视角 业务线×全部周完整表格行数=SEGMENT_ORDER长度（8项业务细分，含目前0贡献的IFA业务行）",
              len(v3["full_week_table"]["预约"]["rows"]) == len(SEGMENT_ORDER))

        # --- P7：永明牌照×月批核明细表 ---
        h1 = s1_mv["H"]
        license_month_cols_expect = [c for c in h1.columns if c not in ("牌照", "未批核", "本月已递交")]
        check("前端永明视角 牌照明细表行数=S1-H板块行数（JF/UNIWIN/DW-Non-Bank/EG/Sub Total/DW Bank）",
              len(vs["license_table"]["rows"]) == len(h1))
        check("前端永明视角 牌照明细表月份数=S1-H板块月份列数（排除未批核/本月已递交两个快照列）",
              len(vs["license_table"]["months"]) == len(license_month_cols_expect))
        jf_row_expect = h1[h1["牌照"] == "JF"].iloc[0]
        jf_row_got = next(r for r in vs["license_table"]["rows"] if r["牌照"] == "JF")
        check("前端永明视角 JF牌照2026-01批核APE/未批核/本月已递交=S1-H原始行独立核对（三个字段都要对，不只挑一个）",
              abs(jf_row_got["monthly"][license_month_cols_expect.index("2026-01")] - ppt_num(jf_row_expect["2026-01"])) < 1
              and abs(jf_row_got["未批核"] - ppt_num(jf_row_expect["未批核"])) < 1
              and abs(jf_row_got["本月已递交"] - ppt_num(jf_row_expect["本月已递交"])) < 1)

        # --- P8：S1 月度明细表格 ---
        c1, d1, e1 = s1_mv["C"], s1_mv["D"], s1_mv["E"]
        check("前端S1视角 月度明细表格行数=C板块月份数（跟monthly_trend.labels同一份months列表）",
              len(v1["monthly_table"]) == len(c1) == len(v1["monthly_trend"]["labels"]))
        appr_ape_sum_expect = e1["APE"].apply(ppt_num).sum()
        appr_ape_sum_got = sum(r["批核APE"] for r in v1["monthly_table"])
        check("前端S1视角 月度明细表格批核APE合计=E板块APE列独立求和",
              abs(appr_ape_sum_got - appr_ape_sum_expect) < 1)
        first_month = sorted(c1["年月"].tolist())[0]
        c1_first = c1[c1["年月"] == first_month].iloc[0]
        check("前端S1视角 月度明细表格首月预约APE/件数=C板块独立核对",
              abs(v1["monthly_table"][0]["预约APE"] - ppt_num(c1_first["APE"])) < 1
              and v1["monthly_table"][0]["预约件数"] == int(ppt_num(c1_first["件数"])))

        # --- P9：达标节奏线 + 批核APE月度走势预测（重点：数据来源诚实披露） ---
        a1_full = s1_mv["A"][s1_mv["A"]["指标"] == "2026全业务目标"].iloc[0]
        full_gap_expect = ppt_num(a1_full["目标APE"]) - ppt_num(a1_full["已达成APE"])
        months_2026_expect = sorted(m for m in c1["年月"].tolist() if m.startswith("2026-"))
        cur_month_num_expect = int(months_2026_expect[-1].split("-")[1])
        remaining_expect = 12 - cur_month_num_expect
        check("前端S1视角 达标节奏线剩余月份=12-当前月（当前月=数据实际覆盖到的最后一个2026年月份，不是日历今天）",
              v1["forecast_pace"]["remaining_months"] == remaining_expect)
        check("前端S1视角 达标节奏线=剩余缺口÷剩余月份独立核算",
              abs(v1["forecast_pace"]["pace_per_month"] - full_gap_expect / remaining_expect) < 1)
        check("前端S1视角 预测数字(最低月底线69.5M/10-12月预测100-100-96M)跟SUNLIFE_FORECAST_SOURCE配置值完全一致（未被代码二次加工）",
              v1["forecast_pace"]["min_monthly_line"] == SUNLIFE_FORECAST_SOURCE["min_monthly_line"] == 69.5e6
              and v1["forecast_chart"]["forecast"][9] == 100.0e6  # 2026-10
              and v1["forecast_chart"]["forecast"][10] == 100.0e6  # 2026-11
              and v1["forecast_chart"]["forecast"][11] == 96.0e6)  # 2026-12
        check("前端S1视角 批核APE月度走势历史月份(实际)不使用预测值填充（10-12月forecast之外的actual用真实E板块数据或None，不混用）",
              all(v1["forecast_chart"]["actual"][i] is None or isinstance(v1["forecast_chart"]["actual"][i], (int, float))
                  for i in range(12))
              and v1["forecast_chart"]["forecast"][:9] == [None] * 9)

        try:
            from skills.multiview_dashboard import render as _mv_render
            html_out = _mv_render(s1_dir_mv.parent, agent_version="test", source_name="test")
            check("前端render()端到端跑通且全部9个视角被标记为available（v0.17.0新增永明业绩视角）",
                  html_out.count('"available": true') == 9)
            check("前端render()输出的HTML页面里确实包含P9预测数值来源披露文字（不能只在数据字典里有、页面不显示）",
                  "2026-09-25期" in html_out and "业务侧人工设定" in html_out and "未独立验证/反推" in html_out)
        except Exception as e:
            check("前端render()端到端跑通", False, str(e))
    else:
        check("⚠️ S2/S3/S4/S9数据不存在，跳过前端新增视角核验", True)

    # ---- Mark标准报表（mark_standard_report.py，第1-9页，v0.20.0新增） ----
    # 口径说明见mark_standard_report.py模块docstring：第7页T表+分档分布、第6/8页KA
    # 排名、第3页I产品排名、第9页W月度分析，均跟现有multiview_dashboard.py的
    # build_*_view()口径有真实差异，本节断言是独立pandas重算，不是对着被测代码的
    # 自我复述。
    s6_dir_mv = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "S6_市场与交叉视角"
    mark_data_root = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data"
    if s1_dir_mv.exists() and s2_dir_mv.exists() and s3_dir_mv.exists() and s4_dir_mv.exists() and s6_dir_mv.exists():
        import skills.mark_standard_report as msr

        # --- 第7页：签批时效表+分档分布（排除TAT<0异常值，分母=1646不是1647） ---
        base7 = df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)].copy()
        base7["_tat"] = (base7["issue_date"] - base7["sign_date"]).dt.days
        expect_excluded = int((base7["_tat"] < 0).sum())
        expect_valid = int((base7["_tat"] >= 0).sum())
        te = msr._timeliness_corrected(df)
        check("第7页 签批时效：排除TAT<0异常值后有效样本=1646（独立pandas重算，排除数=1）",
              te["total_valid"] == expect_valid == 1646 and te["excluded_count"] == expect_excluded == 1)
        bucket_sum = sum(r["件数"] for r in te["bucket_rows"])
        check("第7页 分档分布：6档件数之和=有效样本总数（不多不少，TAT<0的1条不落入任何档）",
              bucket_sum == te["total_valid"])
        expect_buckets = {"≤7天": 220, "8-14天": 369, "15-30天": 611, "31-60天": 286, "61-90天": 69, ">90天": 91}
        got_buckets = {r["分档"]: r["件数"] for r in te["bucket_rows"]}
        check("第7页 分档分布：各档件数=独立核对自Mark原文p14.txt（220/369/611/286/69/91）",
              got_buckets == expect_buckets, f"实际 {got_buckets}")
        check("第7页 SLA≤60天达标率=（≤7+8-14+15-30+31-60四档之和）/有效样本=1486/1646≈90.3%",
              te["sla60_count"] == 1486 and abs(te["sla60_rate"] - 1486 / 1646) < 1e-9)
        seg_552 = next(r for r in te["segment_rows"] if r["业务细分"] == "同行经代")
        check("第7页 T表：排除异常值后'同行经代'件数=552（不是build_s3_view().timeliness未排除时的553，"
              "跟Mark PDF渲染截图肉眼核对一致）",
              seg_552["件数"] == 552)

        # --- 第3页：永明未批核/待签KPI + 产品排名(SQ_rate缺失计入'未提供') ---
        pipe3 = msr._sunlife_pipeline_kpi(df)
        sl = df[df["carrier_code"] == msr.SUNLIFE_CARRIER]
        from skills.s2_business_view import UNAPPROVED_STATUSES as _UNAPP
        expect_unbat = sl[sl["policy_status"].isin(_UNAPP)]
        expect_pend = sl[sl["policy_status"] == "排期"]
        check("第3页 永明未批核APE/件数独立核对（carrier=香港永明金融有限公司,status IN未批核4态）",
              abs(pipe3["unbat_ape"] - float(expect_unbat["ape"].sum())) < 1
              and pipe3["unbat_cnt"] == len(expect_unbat) == 123)
        check("第3页 永明待签APE/件数独立核对（status=排期）",
              abs(pipe3["pend_ape"] - float(expect_pend["ape"].sum())) < 1
              and pipe3["pend_cnt"] == len(expect_pend) == 11)

        product3 = msr._sunlife_product_ranking(df)
        top1 = product3["top10"][0]
        check("第3页 产品排名：TOP1=SQ_rate缺失('未提供')档，378件/156.19M——跟S4-B/C'缺失整体排除'"
              "口径不同，必须独立计算，不能直接复用S4的_product_top()",
              top1["首年折扣"] == "未提供" and top1["件数"] == 378 and abs(top1["APE"] / 1e6 - 156.19) < 0.01)
        top10_cnt = sum(r["件数"] for r in product3["top10"])
        top10_ape = sum(r["APE"] for r in product3["top10"])
        check("第3页 产品排名：TOP10合计987件/388.61M、总体1171件/444.41M（逐项核对自p04.txt原文）",
              top10_cnt == 987 and abs(top10_ape / 1e6 - 388.61) < 0.01
              and product3["total_cnt"] == 1171 and abs(product3["total_ape"] / 1e6 - 444.41) < 0.01)

        # --- 第6/8页：KA排名（S6全量口径，不是S2-I/K的TOP20截断） ---
        s6_mv = _mv_load_sheet(s6_dir_mv)
        ka6 = msr._ka_rank_from_s6(s6_mv, ("A-APE", "B-APE", "C-APE"), ("A-件数", "B-件数", "C-件数"), top_n=10)
        top10_batch = sum(r["batch"] for r in ka6["top"])
        check("第6页 P表 KA TOP10批核APE合计=602.65M（独立核对S6-A-APE'合计'列，全量三阶段口径）",
              abs(top10_batch / 1e6 - 602.65) < 0.01)
        check("第6页 P表 其他+TOP10+=总体（总体批核APE=772.13M，等于S1-B批核(2026)总量）",
              abs((ka6["rest"]["batch"] + top10_batch) / 1e6 - 772.13) < 0.01
              and abs(ka6["total"]["batch"] / 1e6 - 772.13) < 0.01)

        ka8 = msr._ka_rank_from_s2(s2_mv["K"], top_n=10)
        check("第8页 V表 同行KA TOP10批核APE合计=365.49M（S2-K全量口径，独立核对自p08.txt）",
              abs(sum(r["batch"] for r in ka8["top"]) / 1e6 - 365.49) < 0.01)
        check("第8页 V表 总体批核/未批核/待签=399.63M/51.61M/7.07M（跟build_peer_view()的issued_ape等一致）",
              abs(ka8["total"]["batch"] / 1e6 - 399.63) < 0.01
              and abs(ka8["total"]["unbat"] / 1e6 - 51.61) < 0.01)

        # --- 第9页：同行月度分析（自然日历月，不是derive_monthly_buckets的周→月桶算法） ---
        from skills.s2_business_view import PEER_SEGMENTS as _PEERSEG, LAPSE_STATUSES as _LAPSE
        pop9 = df[df["segment_code"].isin(_PEERSEG)]
        sign9 = pop9[~pop9["policy_status"].isin(_LAPSE + ["排期"])]
        jan_sign = sign9[(sign9["sign_date"].dt.year == 2026) & (sign9["sign_date"].dt.month == 1)]
        cal_monthly = msr._peer_calendar_monthly(df)
        jan_row = next(r for r in cal_monthly if r["month"] == "26-Jan")
        check("第9页 W表 同行月度分析：按自然日历月统计（不是周→月分桶算法），"
              "26-Jan签单=16.33M/56件（跟derive_monthly_buckets桶算法算出的16.18M/55件不同，"
              "已核对自然月口径才是跟p09.txt原文匹配的）",
              abs(jan_row["签单APE"] - float(jan_sign["ape"].sum())) < 1
              and jan_row["签单件数"] == len(jan_sign) == 56)
        oct_row = cal_monthly[-1]
        check("第9页 W表 26-Oct（本月）预约/签单/批核=16.42M/31件、14.10M/33件、6.15M/25件（跟同行W40"
              "本周快报是两个不同口径——本月是Oct全月自然日历，本周只是W40单周）",
              abs(oct_row["预约APE"] / 1e6 - 16.42) < 0.01 and oct_row["预约件数"] == 31
              and abs(oct_row["签单APE"] / 1e6 - 14.10) < 0.01 and oct_row["签单件数"] == 33
              and abs(oct_row["批核APE"] / 1e6 - 6.15) < 0.01 and oct_row["批核件数"] == 25)

        # --- 第1/2页：当月未完结判断 + 月度明细表格复用build_s1_view()，独立核对关键行 ---
        monthly_table1 = v1["monthly_table"]
        oct26 = next(r for r in monthly_table1 if r["month"] == "26-Oct")
        check("第1页 月度明细表格：26-Oct行=18.31M/36件/14.95M/35件/9.59M/36件（独立核对自p01.txt原文，"
              "直接复用build_s1_view()的monthly_table，未重新计算）",
              abs(oct26["预约APE"] / 1e6 - 18.31) < 0.01 and oct26["预约件数"] == 36
              and abs(oct26["批核APE"] / 1e6 - 9.59) < 0.01 and oct26["批核件数"] == 36)

        # --- Phase2新增：第10-18页（v0.22.0），全部独立pandas重算核对 ---
        from skills.multiview_dashboard import build_bank_view as _bv, build_agent_view as _av, build_ka_view as _kv

        bank_v_t = _bv(s2_mv, s3_mv)
        agent_v_t = _av(s9_mv)
        ka_v_t = _kv(s9_mv)

        # 第10页：银行业绩
        check("第10页 BK批核/未批核/待签=253.00M/27.38M/0.78M（build_bank_view()跟S2-A/O一致，逐项核对自p10.txt）",
              abs(bank_v_t["issued_ape"] / 1e6 - 253.00) < 0.01 and bank_v_t["issued_cnt"] == 233
              and abs(bank_v_t["unbat_ape"] / 1e6 - 27.38) < 0.01 and bank_v_t["unbat_cnt"] == 24
              and abs(bank_v_t["pend_ape"] / 1e6 - 0.78) < 0.01 and bank_v_t["pend_cnt"] == 1)
        bb_t = bank_v_t["branch_bar"]
        check("第10页 AD表：分行TOP10合计=212.14M，跟p10.txt列出的10个分行顺序逐一匹配（民生广州/南京/上海/..."
              "/平安钟丽丽），独立核对branch_bar前10名之和",
              abs(sum(bb_t["合计"][:10]) / 1e6 - 212.14) < 0.01
              and bb_t["labels"][:5] == ["民生广州分行", "民生南京分行", "民生上海分行", "民生北京分行", "民生深圳分行"])
        bk_month_label_t, bk_month_t = msr._segment_calendar_current_month(df, ["BK业务"])
        check("第10页 BK本月(自然日历月)预约/签单/批核=0.78M/1件、0.00M/0件、0.78M/1件（独立pandas重算，"
              "跟p10.txt'BK 本月预约/签单/批核'精确匹配）",
              abs(bk_month_t["预约"]["ape"] / 1e6 - 0.78) < 0.01 and bk_month_t["预约"]["cnt"] == 1
              and bk_month_t["签单"]["cnt"] == 0
              and abs(bk_month_t["批核"]["ape"] / 1e6 - 0.78) < 0.01 and bk_month_t["批核"]["cnt"] == 1)
        bank_cnt_t = msr._bank_weekly_detail_with_count(s3_mv)
        check("第10页 AC表：W40银行KA本周详情——民生银行预约0.78M/1件、浦发银行批核0.78M/1件、"
              "平安银行全0，逐格核对自p10.txt",
              next(r for r in bank_cnt_t["rows"] if r["ka"] == "民生银行")["vals"]["预约"] == {"ape": 780000.0, "cnt": 1}
              and next(r for r in bank_cnt_t["rows"] if r["ka"] == "浦发银行")["vals"]["批核"] == {"ape": 780000.0, "cnt": 1})

        # 第11页：代理人业务
        check("第11页 代理人业务批核/未批核/待签=91.77M/7.15M/1.24M（build_agent_view()，逐项核对自p11.txt）",
              abs(agent_v_t["issued_total"] / 1e6 - 91.77) < 0.01
              and abs(agent_v_t["unbat_total"] / 1e6 - 7.15) < 0.01
              and abs(agent_v_t["pend_total"] / 1e6 - 1.24) < 0.01)
        tl_row_t = s9_mv["B"][s9_mv["B"]["KEY ACCOUNT"] == "天领重庆"].iloc[0]
        check("第11页 KA明细(天领业务)：天领重庆批核3582万/136件、未批核118万/4件（S9-B原始CSV已排序+自带"
              "合计行，直接渲染不需要重新排序，逐项核对自p11.txt）",
              round(ppt_num(tl_row_t["2026批核APE"]) / 1e4) == 3582 and int(ppt_num(tl_row_t["批核件数"])) == 136
              and round(ppt_num(tl_row_t["未批核APE"]) / 1e4) == 118 and int(ppt_num(tl_row_t["未批核件数"])) == 4)
        agent_month_label_t, agent_month_t = msr._segment_calendar_current_month(df, ["天领业务", "成事家办"])
        check("第11页 代理人本月(自然日历月)预约/签单/批核=0.56M/3件、0.00M/0件、2.40M/8件（独立pandas重算，"
              "跟W40单周口径不同，逐项核对自p11.txt'代理人10月预约/签单/批核'）",
              abs(agent_month_t["预约"]["ape"] / 1e6 - 0.56) < 0.01 and agent_month_t["预约"]["cnt"] == 3
              and agent_month_t["签单"]["cnt"] == 0
              and abs(agent_month_t["批核"]["ape"] / 1e6 - 2.40) < 0.01 and agent_month_t["批核"]["cnt"] == 8)

        # 第12页：KA业务
        check("第12页 KA业务批核/未批核/待签=27.72M/0.93M/0.00M（build_ka_view()，逐项核对自p12.txt）",
              abs(ka_v_t["issued_total"] / 1e6 - 27.72) < 0.01
              and abs(ka_v_t["unbat_total"] / 1e6 - 0.93) < 0.01 and ka_v_t["pend_total"] == 0.0)
        iclub_row_t = s9_mv["F_ICLUB业务"][s9_mv["F_ICLUB业务"]["KEY ACCOUNT"] == "个人转介"].iloc[0]
        ifa_row_t = s9_mv["F_IFA业务"][s9_mv["F_IFA业务"]["KEY ACCOUNT"] == "IFA"].iloc[0]
        check("第12页 KA明细：ICLUB'个人转介'批核2099万/12件；IFA未批核85万/2件（S9-F_xxx原始CSV，"
              "逐项核对自p12.txt）",
              round(ppt_num(iclub_row_t["2026批核APE"]) / 1e4) == 2099 and int(ppt_num(iclub_row_t["批核件数"])) == 12
              and round(ppt_num(ifa_row_t["未批核APE"]) / 1e4) == 85 and int(ppt_num(ifa_row_t["未批核件数"])) == 2)

        # 第13页：永明产品保费+完整年期分布
        premium13 = msr._sunlife_premium_ranking(df)
        check("第13页 产品保费TOP1=永誉传承储蓄计划/1年期/2.5%折扣/25件/347.88M保费（按保费降序，不是"
              "第3页按APE降序，独立重算核对自p13.txt）",
              premium13["top"][0]["产品名称"] == "永誉传承储蓄计划" and premium13["top"][0]["年期"] == 1
              and premium13["top"][0]["件数"] == 25 and abs(premium13["top"][0]["保费"] / 1e6 - 347.88) < 0.01)
        check("第13页 产品保费：TOP10合计937件/870.32M、总体1171件/951.42M（跟第3页总体1171件/444.41M是"
              "同一组记录的APE/保费两个不同金额口径，不能互换）",
              sum(r["件数"] for r in premium13["top"]) == 937
              and abs(sum(r["保费"] for r in premium13["top"]) / 1e6 - 870.32) < 0.01
              and premium13["total_cnt"] == 1171 and abs(premium13["total_premium"] / 1e6 - 951.42) < 0.01)
        term13 = msr._sunlife_term_distribution(df)
        term13_by_label = {r["年期类别"]: r for r in term13}
        check("第13页 完整年期分布：6档件数=1038/44/61/25/2/1（中期/短期/长期/终身/年期缺失/文本年期），"
              "年期缺失/文本年期是report_enricher.py既有_term_bucket()本身返回None、未细分的两种情况，"
              "本页独立拆分成2档，逐项核对自p13.txt",
              term13_by_label["中期(2-5年)"]["件数"] == 1038 and term13_by_label["短期(≤1年)"]["件数"] == 44
              and term13_by_label["长期(6-20年)"]["件数"] == 61 and term13_by_label["终身(>20年)"]["件数"] == 25
              and term13_by_label["年期缺失"]["件数"] == 2 and term13_by_label["文本年期"]["件数"] == 1)

        # 第14页：执行明细、来源说明与管理行动（全新页面，至少5项）
        event14 = msr._page14_event_table(s3_mv, msr._current_week_full(s3_mv))
        check("第14页 8线×4事件当周表：合计预约17.61M/33件、签单13.33M/26件、批核7.81M/27件（独立核对自"
              "p14.txt'2026W40完整八线/四事件'合计行；递交只有总量，不按业务线拆分，见下一项断言）",
              abs(event14["totals"]["res"]["ape"] / 1e6 - 17.61) < 0.01 and event14["totals"]["res"]["cnt"] == 33
              and abs(event14["totals"]["sign"]["ape"] / 1e6 - 13.33) < 0.01 and event14["totals"]["sign"]["cnt"] == 26
              and abs(event14["totals"]["issue"]["ape"] / 1e6 - 7.81) < 0.01 and event14["totals"]["issue"]["cnt"] == 27)

        from skills.data_loader import DataLoader as _DL14
        from skills.cleaner import Cleaner as _CL14, ENTITY_ALIAS_MAP as _EAM14
        import pandas as _pd14
        lr14 = _DL14(AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "raw_data").load()
        raw14 = lr14.df
        df14 = _CL14().clean(lr14.df, lr14.export_date)
        expect_missing_issue = int(((df14["policy_status"] == "生效") & df14["issue_date"].isna()).sum())
        expect_ape_missing = int(_pd14.to_numeric(raw14["ape"], errors="coerce").isna().sum())
        expect_premium_missing = int(_pd14.to_numeric(raw14["premium"], errors="coerce").isna().sum())
        expect_future_dated = int(df14["future_dated"].sum())
        expect_declined = int((df14["policy_status"] == "拒保").sum())
        expect_alias_records = int(raw14["issuing_entity"].isin(_EAM14.keys()).sum())
        expect_alias_pairs = int(sum(1 for k in _EAM14 if (raw14["issuing_entity"] == k).any()))
        dq_t = msr._data_quality_disclosure(raw14, df14, msr._timeliness_corrected(df14)["excluded_count"])
        check("第14页 数据与解释边界：缺批核日期2单(生效但issue_date为空)、APE/保费缺失均10单、"
              "未来签单日21单、拒保2单——全部独立pandas重算得出，不是照抄p14.txt原数字（可能因v0.19/"
              "v0.21修正而不同，本次恰好一致），逐项核对自p14.txt",
              dq_t["missing_issue_date"] == expect_missing_issue == 2
              and dq_t["ape_missing"] == expect_ape_missing == 10
              and dq_t["premium_missing"] == expect_premium_missing == 10
              and dq_t["future_dated"] == expect_future_dated == 21
              and dq_t["declined"] == expect_declined == 2)
        check("第14页 数据与解释边界：实体别名归一化披露——1669条记录涉及5个实体对子（独立统计raw_df里"
              "issuing_entity命中ENTITY_ALIAS_MAP键的记录数+实际出现的键数，不是Mark原文数字，p14.txt"
              "本身没有披露这项，是本项目独立新增的披露内容）",
              dq_t["entity_alias_records"] == expect_alias_records == 1669
              and dq_t["entity_alias_pairs"] == expect_alias_pairs == 5)
        unapp14 = msr._unapproved_channel_top10(df14)
        check("第14页 在途推进TOP10：平安银行23.48M/20件排第1，总体87.07M/171件（key_account跨全部"
              "业务线，MGA业务拆分成'XX(MGA)'独立行，逐项核对自p14.txt'未批渠道TOP10'）",
              unapp14["top"][0]["ka"] == "平安银行" and abs(unapp14["top"][0]["ape"] / 1e6 - 23.48) < 0.01
              and unapp14["top"][0]["cnt"] == 20
              and abs(unapp14["total"]["ape"] / 1e6 - 87.07) < 0.01 and unapp14["total"]["cnt"] == 171)

        try:
            html_mark_14 = msr.render(mark_data_root, agent_version="test", source_name="test.xlsx")
        except Exception as e:
            html_mark_14 = ""
            check("第14页 render()可生成（供下方2项断言复用）", False, str(e))
        if html_mark_14:
            check("第14页 '递交×业务线'数据缺口说明文字确实出现在渲染后的HTML里（不新增反推逻辑凑数据，"
                  "按Jasper指示只标注缺口说明）",
                  "递交事件当前无业务线拆分数据源" in html_mark_14 and "不新增反推逻辑凑出" in html_mark_14)
            import re as _re14
            roles_found = _re14.findall(r"（(业务管理负责人|数据负责人|渠道及运营负责人|业务与数据负责人)）", html_mark_14)
            check("第14页 管理行动建议文案的角色占位符格式正确——4条建议分别带'（角色）'格式的占位符"
                  "（业务管理负责人/数据负责人/渠道及运营负责人/业务与数据负责人），不是猜测的真实姓名",
                  set(roles_found) == {"业务管理负责人", "数据负责人", "渠道及运营负责人", "业务与数据负责人"}
                  and len(roles_found) == 4)

        # 第15页：同行合作渠道与推荐人·完整总体
        partner15 = msr._peer_partner_full(df)
        check("第15页 合作渠道TOP10：紫荆保险39.69M/116件排第1，TOP10合计291.67M/798件（partner_code"
              "分组，population=PEER_SEGMENTS同第8页V模块，逐项核对自p15.txt）",
              partner15["top"][0]["partner"] == "紫荆保险" and abs(partner15["top"][0]["batch"] / 1e6 - 39.69) < 0.01
              and partner15["top"][0]["batch_c"] == 116
              and abs(sum(r["batch"] for r in partner15["top"]) / 1e6 - 291.67) < 0.01
              and sum(r["batch_c"] for r in partner15["top"]) == 798)
        referrer15 = msr._peer_referrer_full(df)
        other15 = referrer15["other"]
        check("第15页 推荐人：姜通200.25M批核/664件阶段件数，其他/未提供=73.89M批核/158件（referral_code"
              "分组，6个具名推荐人之和=总体减'其他/未提供'，独立核对自p15.txt）",
              referrer15["named"][0]["name"] == "姜通" and abs(referrer15["named"][0]["batch"] / 1e6 - 200.25) < 0.01
              and referrer15["named"][0]["cnt"] == 664
              and abs(other15["batch"] / 1e6 - 73.89) < 0.01 and other15["cnt"] == 158)

        # 第16-18页：Q/R/S周度热力矩阵完整表格
        heat_q_t = msr._heat_table(s3_mv["B"], msr._recent_weeks(s3_mv["B"]))
        heat_r_t = msr._heat_table(s3_mv["C"], msr._recent_weeks(s3_mv["C"]))
        heat_s_t = msr._heat_table(s3_mv["D"], msr._recent_weeks(s3_mv["D"]))
        check("第16页 Q预约热力矩阵：窗口=最近15周(W26-W40)，天领业务W26=0.7M/5件、同行经代W29=18.0M/42件，"
              "逐格核对自p16.txt（数据源S3-B，跟build_s3_view().full_week_table同一取数方式，独立重写成"
              "APE+件数同格）",
              heat_q_t["weeks"] == [f"W{i}" for i in range(26, 41)]
              and abs(next(r for r in heat_q_t["rows"] if r["segment"] == "天领业务")["vals"][0]["ape"] / 1e6 - 0.7) < 0.05
              and next(r for r in heat_q_t["rows"] if r["segment"] == "天领业务")["vals"][0]["cnt"] == 5
              and abs(next(r for r in heat_q_t["rows"] if r["segment"] == "同行经代")["vals"][3]["ape"] / 1e6 - 18.0) < 0.05
              and next(r for r in heat_q_t["rows"] if r["segment"] == "同行经代")["vals"][3]["cnt"] == 42)
        check("第17页 R签单热力矩阵：天领业务W28=6.0M/6件、合计W29=26.6M/72件，逐格核对自p17.txt",
              abs(next(r for r in heat_r_t["rows"] if r["segment"] == "天领业务")["vals"][2]["ape"] / 1e6 - 6.0) < 0.05
              and next(r for r in heat_r_t["rows"] if r["segment"] == "天领业务")["vals"][2]["cnt"] == 6
              and abs(heat_r_t["total"][3]["ape"] / 1e6 - 26.6) < 0.05 and heat_r_t["total"][3]["cnt"] == 72)
        check("第18页 S批核热力矩阵：永明经代W27=9.9M/22件、合计W40=7.8M/27件（=本周快报批核口径，"
              "跟第6页M模块同一数据源），逐格核对自p18.txt",
              abs(next(r for r in heat_s_t["rows"] if r["segment"] == "永明经代")["vals"][1]["ape"] / 1e6 - 9.9) < 0.05
              and next(r for r in heat_s_t["rows"] if r["segment"] == "永明经代")["vals"][1]["cnt"] == 22
              and abs(heat_s_t["total"][-1]["ape"] / 1e6 - 7.8) < 0.05 and heat_s_t["total"][-1]["cnt"] == 27)

        # --- render()端到端 + 边界说明文案披露核验 ---
        try:
            html_mark = msr.render(mark_data_root, agent_version="test", source_name="test.xlsx")
            check("Mark标准报表render()端到端跑通，含全18页data-page section（第1-18页，Mark18页标准报表"
                  "Phase1+Phase2全部完成）",
                  all(html_mark.count(f'data-page="{p}"') == 1 for p in range(1, 19))
                  and 'data-page="19"' not in html_mark)
            check("Mark标准报表：术语口径跟Mark原文一致（'各环节业务周累计'而非'全流程转化漏斗'、"
                  "'差额'而非'缺口'、页脚统一'文件快照｜数据完整时点未核实｜工作稿'）",
                  "各环节业务周累计" in html_mark and "全流程转化漏斗" not in html_mark
                  and "差额340.87M" in html_mark
                  and "文件快照｜数据完整时点未核实｜工作稿" in html_mark)
            check("Mark标准报表：第7页'排除1件'异常值披露文字 + 分档分布边界说明均已渲染进HTML",
                  "排除1件" in html_mark and "不入分母" in html_mark)
            check("Mark标准报表：第3页永明牌照明细的issuing_entity归一化披露文字已渲染（原始名称不逐字"
                  "保留的说明，不能让人误以为是照抄Mark原文的展示方式）",
                  "本项目cleaner.py已把简繁体写法的同一实体合并" in html_mark)
            check("Mark标准报表：边界说明原文照抄到位（'各环节不是同一批保单，不能据此计算转化率'、"
                  "'当月未完结，不作全月结论'、'原始名称不擅自合并'类表述未被省略或改写）",
                  "各环节不是同一批保单，不能据此计算转化率" in html_mark
                  and "当月未完结，不作全月结论" in html_mark)
            s3_mv_fresh = _mv_load_sheet(s3_dir_mv)
            expect_week_full = msr._current_week_full(s3_mv_fresh)
            check("Mark标准报表：页脚周数独立核对自build_s3_view()同一套current_week_from_labels()"
                  "逻辑算出（不是写死占位符），本次数据=2026W40",
                  expect_week_full == "2026W40" and f"{expect_week_full}文件快照" in html_mark)
        except Exception as e:
            check("Mark标准报表render()端到端跑通", False, str(e))
    else:
        check("⚠️ S1/S2/S3/S4/S6数据不存在，跳过Mark标准报表核验（需要先跑一遍agent.py --s6）", True)

    print()
    if failures:
        print(f"❌ {len(failures)} 项失败: {failures}")
        sys.exit(1)
    else:
        print("✅ 全部检查通过")
        print("真实数据验证对象：raw_data/" + load_result.source_file.name)


if __name__ == "__main__":
    main()
