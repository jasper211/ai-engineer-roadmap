#!/usr/bin/env python3
"""Independent deterministic checks for the L5 annual termination-rate slice."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data/annual_market_fact_layer_2022_2024.db"


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    checks = {}
    checks["row_count_171"] = con.execute("SELECT COUNT(*) FROM termination_rate_facts").fetchone()[0] == 171
    checks["three_certified_years"] = con.execute(
        "SELECT GROUP_CONCAT(DISTINCT report_year) FROM termination_rate_facts").fetchone()[0] == "2022,2023,2024"
    checks["units_are_percentage_points"] = con.execute(
        "SELECT COUNT(*) FROM termination_rate_facts WHERE unit!='percentage_point'").fetchone()[0] == 0
    checks["all_rows_certified"] = con.execute(
        "SELECT COUNT(*) FROM termination_rate_facts WHERE certification!='certified'").fetchone()[0] == 0
    checks["2024_nonlinked_all_policies_3_7"] = con.execute(
        "SELECT value FROM termination_rate_facts WHERE report_year=2024 AND observation_year=2024 "
        "AND linked_status='non_linked' AND insurance_type='all_policies' "
        "AND metric_id='overall_termination_rate'").fetchone() == (3.7,)
    checks["2024_linked_all_policies_7_0"] = con.execute(
        "SELECT value FROM termination_rate_facts WHERE report_year=2024 AND observation_year=2024 "
        "AND linked_status='linked' AND insurance_type='all_policies' "
        "AND metric_id='overall_termination_rate'").fetchone() == (7.0,)
    checks["2024_detail_na_preserved"] = con.execute(
        "SELECT COUNT(*) FROM termination_rate_facts WHERE report_year=2024 "
        "AND insurance_type IN ('whole_life','endowment') AND record_status='not_applicable'").fetchone()[0] == 22
    checks["no_unparsed_values"] = con.execute(
        "SELECT COUNT(*) FROM termination_rate_facts WHERE record_status='unparsed'").fetchone()[0] == 0
    checks["unique_fact_ids"] = con.execute(
        "SELECT COUNT(*)=COUNT(DISTINCT fact_id) FROM termination_rate_facts").fetchone()[0] == 1
    con.close()
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT: {sum(checks.values())}/{len(checks)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
