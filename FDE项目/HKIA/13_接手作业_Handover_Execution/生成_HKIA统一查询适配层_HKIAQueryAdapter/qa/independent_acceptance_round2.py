"""Second-stage adversarial checks for contract completeness and semantic controls."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from hkia_adapter import HKIAClient


def main():
    checks = {}
    evidence = {}
    schema = json.loads((ROOT / "schema/response_schema.json").read_text())
    required = set(schema["required"])

    with HKIAClient.open_readonly() as client:
        error = client.query({"query_type": "execute_sql"})
        checks["error_response_meets_required_contract"] = required <= set(error)
        evidence["error_response_keys"] = sorted(error)

        health = client.query({"query_type": "healthcheck"})
        checks["health_data_matches_schema_array"] = isinstance(health.get("data"), list)
        evidence["health_data_type"] = type(health.get("data")).__name__

        nested_unknown = client.query({"query_type": "company_ranking",
                                       "metric_id": "ANNUAL_L16_PREMIUM_SINGLE", "period": "2024",
                                       "filters": {"evil_sqlish_field": "anything"}})
        checks["unknown_nested_filter_rejected"] = not nested_unknown.get("ok", False)
        evidence["unknown_nested_filter"] = nested_unknown

        invalid_periods = client.query({"query_type": "market_trend",
                                        "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM",
                                        "periods": ["2023Q1", "bad-period"]})
        checks["every_period_item_validated"] = not invalid_periods.get("ok", False)
        evidence["invalid_periods"] = invalid_periods

        base_req = {"query_type": "company_ranking", "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                    "period": "2024", "limit": 3}
        first = client.query(base_req)
        shifted = client.query(dict(base_req, offset=1))
        first_names = [x.get("entity") for x in first.get("data", [])]
        shifted_names = [x.get("entity") for x in shifted.get("data", [])]
        checks["offset_is_honored_or_rejected"] = (not shifted.get("ok", False)) or shifted_names != first_names
        evidence["offset_entities"] = {"base": first_names, "offset_1": shifted_names}

        bad_include = client.query(dict(base_req, include_zero="false"))
        checks["include_zero_type_validated"] = not bad_include.get("ok", False)
        evidence["bad_include_zero"] = {"ok": bad_include.get("ok"), "error_code": bad_include.get("error_code")}

        filters_list = client.query({"query_type": "company_period_values",
                                     "metric_id": "ANNUAL_L16_PREMIUM_SINGLE", "period": "2024",
                                     "identity_mode": "entity", "filters": []})
        checks["filters_type_returns_validation_error"] = (
            not filters_list.get("ok", False) and filters_list.get("error_code") == "VALIDATION_ERROR")
        evidence["filters_list"] = filters_list

        entity_req = {"query_type": "company_period_values", "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                      "period": "2024", "filters": {"entity": "AIA International"}}
        entity_result = client.query(dict(entity_req, identity_mode="entity"))
        lineage_result = client.query(dict(entity_req, identity_mode="lineage"))
        entity_row = (entity_result.get("data") or [{}])[0]
        lineage_row = (lineage_result.get("data") or [{}])[0]
        checks["entity_and_lineage_modes_are_distinct"] = bool(
            entity_result.get("ok") and lineage_result.get("ok")
            and (entity_row.get("business_lineage") or lineage_row.get("business_lineage"))
            and entity_row != lineage_row)
        evidence["identity_modes"] = {"entity": entity_row, "lineage": lineage_row}

        zero = client.query({"query_type": "company_period_values",
                             "metric_id": "ANNUAL_L16_PREMIUM_SINGLE", "period": "2024",
                             "identity_mode": "entity", "filters": {"entity": "AXA China (HK)"}})
        zero_row = (zero.get("data") or [{}])[0]
        checks["zero_value_status_is_reported_zero"] = zero_row.get("value") == 0 and zero_row.get("record_status") == "reported_zero"
        evidence["zero_value_row"] = zero_row

        missing = client.query({"query_type": "company_period_values",
                                "metric_id": "ANNUAL_L16_PREMIUM_SINGLE", "period": "2024",
                                "identity_mode": "entity", "filters": {"entity": "China Re HK"}})
        missing_row = (missing.get("data") or [{}])[0]
        checks["missing_status_is_preserved"] = bool(
            missing.get("ok") and missing_row.get("record_status") == "missing"
            and missing_row.get("value") is None)
        evidence["missing_company"] = missing

        checks["bridge_evidence_returned_for_company_value"] = bool(
            entity_row.get("bridge_evidence") or entity_row.get("evidence"))
        evidence["company_value_keys"] = sorted(entity_row)

        financial = client.query({"query_type": "financial_snapshot", "metric_id": "FIN_DEBT_SECURITIES",
                                  "period": "2026Q1", "filters": {"fund_scope": "not_a_scope"}})
        checks["financial_filter_value_whitelisted"] = not financial.get("ok", False)
        evidence["invalid_fund_scope"] = financial

    metrics = json.loads((ROOT / "config/metric_catalog.json").read_text())["metrics"]
    required_metric_fields = {"label", "source_layer", "source_table", "unit", "entity_scope",
                              "period_basis", "certification_rule", "schema", "supported_query_types",
                              "comparable_with", "prohibited_comparisons", "aggregation",
                              "source_definition", "release_policy_id"}
    missing_fields = {k: sorted(required_metric_fields - set(v)) for k, v in metrics.items()
                      if required_metric_fields - set(v)}
    checks["metric_catalog_all_required_fields"] = not missing_fields
    evidence["metric_catalog_missing_fields"] = missing_fields

    checks["q4_all_returned_items_catalogued"] = all(
        x in metrics for x in ("FIN_DEBT_SECURITIES", "FIN_EQUITIES_PORTFOLIO", "FIN_CASH_AND_DEPOSITS"))
    evidence["financial_metric_ids"] = sorted(k for k in metrics if k.startswith("FIN_"))

    test_text = "\n".join(p.read_text(errors="ignore") for p in [ROOT / "tests/test_all.py", ROOT / "qa/verify_adapter.py"])
    lowered_tests = test_text.lower()
    checks["l11_gate_has_executable_test"] = "test_l11_count_mix" in lowered_tests and "comp.check(meta)" in lowered_tests
    checks["rbc_schema_gate_has_executable_test"] = "test_pre_rbc" in lowered_tests and "schema_bridge_required" in lowered_tests

    with HKIAClient.open_readonly() as client:
        l11_public = client.query({"query_type": "compare_periods", "metric_id": "ANNUAL_L11_RETIREMENT",
                                   "filters": {"period_a": "2023", "period_b": "2024",
                                               "metric_b": "ANNUAL_L11_SCHEME_COUNT"},
                                   "identity_mode": "entity", "release_intent": "internal_analysis"})
        checks["l11_gate_reachable_through_public_contract"] = (
            not l11_public.get("ok", False) and "policy_count" in l11_public.get("message", "")
            and "scheme_count" in l11_public.get("message", ""))
        evidence["l11_public"] = l11_public
        rbc_public = client.query({"query_type": "compare_periods", "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                                  "filters": {"period_a": "2023", "period_b": "2024"},
                                  "identity_mode": "entity", "release_intent": "internal_analysis"})
        checks["rbc_gate_reachable_through_public_contract"] = (
            not rbc_public.get("ok", False)
            and (rbc_public.get("error_code") == "SCHEMA_BRIDGE_REQUIRED"
                 or rbc_public.get("blocked_by") == "schema_bridge"))
        evidence["rbc_public"] = rbc_public

    with tempfile.TemporaryDirectory() as td:
        install = subprocess.run([sys.executable, "-m", "pip", "install", "--no-build-isolation", "--no-deps",
                                  "--target", td, str(ROOT)], capture_output=True, text=True)
        probe = subprocess.run([sys.executable, "-c",
                                "from hkia_adapter import HKIAClient; c=HKIAClient.open_readonly(); print(c.query({'query_type':'healthcheck'})['ok']); c.close()"],
                               cwd="/tmp", env={"PYTHONPATH": td}, capture_output=True, text=True) if install.returncode == 0 else None
        checks["installed_package_can_open"] = bool(probe and probe.returncode == 0 and probe.stdout.strip() == "True")
        evidence["install_probe"] = {"install_returncode": install.returncode,
                                     "probe_returncode": None if probe is None else probe.returncode,
                                     "probe_stdout": None if probe is None else probe.stdout,
                                     "probe_stderr_tail": None if probe is None else probe.stderr[-600:]}

    out = {"overall": "PASS" if all(checks.values()) else "PARTIAL",
           "passed": sum(checks.values()), "total": len(checks), "results": checks, "evidence": evidence}
    (HERE / "independent_acceptance_round2_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("overall", "passed", "total", "results")}, ensure_ascii=False, indent=2))
    return 0 if out["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
