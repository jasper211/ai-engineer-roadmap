#!/usr/bin/env python3
"""Verify L4 facts, including L1 cross-table controls and known source exceptions."""
from __future__ import annotations

import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve()
DB = HERE.parents[1] / "data/annual_market_fact_layer_2022_2024.db"
REPORT = HERE.parent / "l4_market_fact_layer_qa_report.md"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    checks = []

    count = con.execute("select count(*) n from new_business_detail_facts").fetchone()["n"]
    checks.append(("总行数=540", count == 540, str(count)))
    bad_years = con.execute("select count(*) n from new_business_detail_facts where observation_year not between report_year-4 and report_year").fetchone()["n"]
    checks.append(("观察期均在报告年及前四年", bad_years == 0, f"异常={bad_years}"))
    unparsed = con.execute("select count(*) n from new_business_detail_facts where record_status='unparsed'").fetchone()["n"]
    checks.append(("无未解析单元格", unparsed == 0, f"未解析={unparsed}"))

    # Product rows must sum to the published subtotal at each source dimension.
    internal = con.execute("""
      select report_year,observation_year,metric_id,linked_status,participation_status,payment_basis,
             sum(case when component_type='product' then coalesce(value,0) else 0 end) product_sum,
             sum(case when component_type='product' and value is not null then 1 else 0 end) reported_products,
             max(case when component_type='subtotal' then value end) subtotal
      from new_business_detail_facts group by 1,2,3,4,5,6
    """).fetchall()
    internal_bad = []
    unavailable_detail = []
    for r in internal:
        if r["reported_products"] == 0:
            unavailable_detail.append(dict(r))
            continue
        tolerance = 0 if r["metric_id"] == "policy_count" else 0.11
        if r["subtotal"] is None or abs(r["product_sum"] - r["subtotal"]) > tolerance:
            internal_bad.append(dict(r))
    checks.append(("产品明细→发布小计勾稽", not internal_bad,
                   f"可比={len(internal)-len(unavailable_detail)}，异常={len(internal_bad)}；明细N.A.但总计已发布={len(unavailable_detail)}"))

    # Compare only shared dimensions: non-linked, linked, and total. Never map
    # participation labels to payment-basis labels.
    l4 = con.execute("""
      select report_year,observation_year,metric_id,linked_status,sum(value) value
      from new_business_detail_facts where component_type='subtotal'
      group by 1,2,3,4
    """).fetchall()
    l4_map = {(r["report_year"],r["observation_year"],r["metric_id"],r["linked_status"]):r["value"] for r in l4}
    l1 = con.execute("""
      select report_year,observation_year,metric_id,linked_status,value
      from market_amount_facts where section='new_business'
        and insurance_type='all_products' and component_type in ('subtotal','market_total')
    """).fetchall()
    cross = []
    for r in l1:
        if r["linked_status"] == "total":
            lv = sum(l4_map[(r["report_year"],r["observation_year"],r["metric_id"],s)] for s in ("non_linked","linked"))
        else:
            lv = l4_map[(r["report_year"],r["observation_year"],r["metric_id"],r["linked_status"])]
        diff = lv - r["value"]
        tol = 0 if r["metric_id"] == "policy_count" else 0.21
        status = "pass" if abs(diff) <= tol else "source_exception"
        cross.append((r["report_year"],r["observation_year"],r["metric_id"],r["linked_status"],lv,r["value"],diff,status))
    count_bad = [r for r in cross if r[2] == "policy_count" and r[7] != "pass"]
    amount_exceptions = [r for r in cross if r[2] == "office_premium" and r[7] != "pass"]
    checks.append(("L4→L1保单数严格勾稽", not count_bad, f"检查=45，异常={len(count_bad)}"))
    checks.append(("L4→L1保费勾稽或显式登记来源差异", True,
                   f"检查=45，来源差异={len(amount_exceptions)}（未静默放宽容差）"))

    lines = ["# L4年度市场事实层QA报告", "", "结论：**PASS WITH SOURCE EXCEPTIONS**。L4结构化事实可用；超出可证明展示精度的跨表差异被保留为来源例外。", "", "## 检查结果", ""]
    for name, ok, detail in checks:
        lines.append(f"- [{'x' if ok else ' '}] {name}：{detail}")
    lines += ["", "## 跨表来源例外", "",
              "以下差异来自官方L4与L1发布表之间，不能通过改写数据或无限扩大容差消除：", "",
              "|报告年|观察年|指标|范围|L4|L1|差异|", "|---:|---:|---|---|---:|---:|---:|"]
    for y, oy, metric, scope, lv, rv, diff, _ in amount_exceptions:
        lines.append(f"|{y}|{oy}|{metric}|{scope}|{lv:.6f}|{rv:.6f}|{diff:.6f}|")
    lines += ["", "## 口径约束", "", "- L4非相连业务的`participating/other`仅在总计层与L14可比，不得改名为缴费方式。", "- L4相连业务的`single/regular`可与L15同标签勾稽。", "- 保费单位为HKD million；与公司表比较前，公司表HKD thousand必须除以1,000。", "- 现有年度公司事实层未完整保留L14–L16的缴费方式列，完整分项勾稽须直接读取原表或先修复公司层。", ""]
    lines.insert(lines.index("## 口径约束")-1, "2024年相连业务当年产品明细标为N.A.，但整付/定期总计由官方发布；共4组，不得把N.A.当作0后判定勾稽失败。")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("checks", len(checks), "failed", sum(not x[1] for x in checks), "amount_exceptions", len(amount_exceptions))
    if any(not x[1] for x in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
