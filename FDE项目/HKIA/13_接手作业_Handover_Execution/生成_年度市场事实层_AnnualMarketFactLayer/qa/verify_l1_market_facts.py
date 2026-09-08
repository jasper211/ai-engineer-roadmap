#!/usr/bin/env python3
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data/annual_market_fact_layer_2022_2024.db"


def scalar(con, sql, args=()):
    row = con.execute(sql, args).fetchone()
    return None if row is None else row[0]


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    checks = {}
    checks["row_count_675"] = scalar(con, "SELECT COUNT(*) FROM market_amount_facts") == 675
    checks["three_years_equal_rows"] = con.execute(
        "SELECT report_year,COUNT(*) FROM market_amount_facts GROUP BY report_year").fetchall() == [(2022,225),(2023,225),(2024,225)]
    checks["no_unparsed"] = scalar(con, "SELECT COUNT(*) FROM market_amount_facts WHERE record_status='unparsed'") == 0
    checks["certified_only"] = scalar(con, "SELECT COUNT(*) FROM market_amount_facts WHERE certification!='certified'") == 0
    checks["units_whitelisted"] = scalar(con, "SELECT COUNT(*) FROM market_amount_facts WHERE unit NOT IN ('count','HKD_million')") == 0
    checks["2024_total_inforce_policy_count"] = scalar(con,
        "SELECT value FROM market_amount_facts WHERE report_year=2024 AND observation_year=2024 AND section='inforce' "
        "AND metric_id='policy_count' AND linked_status='total' AND component_type='market_total'") == 14464355.0
    checks["2024_total_new_business_premium"] = abs(scalar(con,
        "SELECT value FROM market_amount_facts WHERE report_year=2024 AND observation_year=2024 AND section='new_business' "
        "AND metric_id='office_premium' AND linked_status='total' AND component_type='market_total'") - 206887.727) <= 0.0005
    checks["linked_sums_assured_na_preserved"] = scalar(con,
        "SELECT COUNT(*) FROM market_amount_facts WHERE report_year IN (2022,2023) AND metric_id='sums_assured' "
        "AND linked_status='linked' AND component_type='subtotal' AND record_status='not_applicable'") == 10
    checks["adjustment_rows_retained"] = scalar(con,
        "SELECT COUNT(*) FROM market_amount_facts WHERE component_type='additional_reserve'") == 30
    component_rows = con.execute("""
      SELECT t.report_year,t.observation_year,t.section,t.metric_id,
             ABS(t.value-n.value-l.value) AS diff
      FROM market_amount_facts t
      JOIN market_amount_facts n ON n.report_year=t.report_year AND n.observation_year=t.observation_year
        AND n.section=t.section AND n.metric_id=t.metric_id AND n.linked_status='non_linked'
        AND n.insurance_type='all_products' AND n.component_type='subtotal'
      JOIN market_amount_facts l ON l.report_year=t.report_year AND l.observation_year=t.observation_year
        AND l.section=t.section AND l.metric_id=t.metric_id AND l.linked_status='linked'
        AND l.insurance_type='all_products' AND l.component_type='subtotal'
      WHERE t.linked_status='total' AND t.component_type='market_total'
    """).fetchall()
    comparable_diffs = [r[-1] for r in component_rows if r[-1] is not None]
    checks["component_totals_reconcile"] = (len(component_rows) == 90
        and len(comparable_diffs) == 76 and max(comparable_diffs) <= 1e-6)
    overlap_diffs = con.execute("""
      SELECT ABS(a.value-b.value)
      FROM market_amount_facts a JOIN market_amount_facts b
        ON b.report_year=a.report_year+1 AND b.observation_year=a.observation_year
       AND b.section=a.section AND b.metric_id=a.metric_id AND b.linked_status=a.linked_status
       AND b.insurance_type=a.insurance_type AND b.component_type=a.component_type
      WHERE a.value IS NOT NULL AND b.value IS NOT NULL
    """).fetchall()
    checks["overlapping_vintages_consistent"] = bool(overlap_diffs) and max(r[0] for r in overlap_diffs) <= 1e-6
    checks["unique_ids"] = scalar(con, "SELECT COUNT(*)=COUNT(DISTINCT fact_id) FROM market_amount_facts") == 1
    con.close()
    for name, ok in checks.items(): print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT: {sum(checks.values())}/{len(checks)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
