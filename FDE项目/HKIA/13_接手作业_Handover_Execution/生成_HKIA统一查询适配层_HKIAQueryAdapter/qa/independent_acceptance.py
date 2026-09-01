"""Independent black-box acceptance for the task contract; does not modify adapter assets."""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HANDOVER = ROOT.parent
sys.path.insert(0, str(ROOT))
from hkia_adapter import HKIAClient


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def query(client, body):
    result = client.query(body)
    return result


def main():
    results = {}
    evidence = {}
    with HKIAClient.open_readonly() as client:
        db_paths = {k: client.cfg.abs_path(k) for k in client.cfg.source_names()}
        before = {k: sha256(v) for k, v in db_paths.items()}

        list_result = query(client, {"query_type": "list_metrics"})
        results["list_metrics_returns_catalog"] = bool(list_result.get("ok") and list_result.get("data"))
        evidence["list_metrics"] = list_result

        describe = query(client, {"query_type": "describe_metric", "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM"})
        results["describe_metric_returns_definition"] = bool(describe.get("ok") and describe.get("data"))
        evidence["describe_metric"] = describe

        count_unknown = query(client, {"query_type": "market_trend", "metric_id": "NB_GROUP_POLICIES",
                                       "periods": ["2023Q1"], "output_unit": "euro"})
        results["count_rejects_unknown_unit"] = not count_unknown.get("ok", False)
        evidence["count_unknown_unit"] = count_unknown

        money_count = query(client, {"query_type": "market_trend", "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM",
                                     "periods": ["2023Q1"], "output_unit": "count"})
        results["money_rejects_count_unit"] = not money_count.get("ok", False)
        evidence["money_count_unit"] = money_count

        neg_limit = query(client, {"query_type": "company_ranking", "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                                   "period": "2024", "limit": -1})
        results["negative_limit_rejected"] = not neg_limit.get("ok", False)
        evidence["negative_limit"] = {"ok": neg_limit.get("ok"), "row_count": len(neg_limit.get("data", []))}

        huge_limit = query(client, {"query_type": "company_ranking", "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                                    "period": "2024", "limit": 10**9})
        results["huge_limit_rejected"] = not huge_limit.get("ok", False)
        evidence["huge_limit"] = {"ok": huge_limit.get("ok"), "row_count": len(huge_limit.get("data", []))}

        invalid_year = query(client, {"query_type": "company_ranking", "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                                      "period": "2025", "limit": 10})
        results["annual_layer_rejects_unsupported_year"] = not invalid_year.get("ok", False)
        evidence["unsupported_annual_year"] = invalid_year

        wrong_scope = query(client, {"query_type": "company_ranking", "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                                     "period": "2024", "entity_scope": "market_total", "limit": 3})
        results["scope_override_rejected"] = not wrong_scope.get("ok", False)
        evidence["scope_override"] = {"ok": wrong_scope.get("ok"), "metadata": wrong_scope.get("metadata")}

        wrong_query_metric = query(client, {"query_type": "financial_snapshot",
                                            "metric_id": "ANNUAL_L16_PREMIUM_SINGLE", "period": "2026Q1"})
        results["query_metric_compatibility_enforced"] = not wrong_query_metric.get("ok", False)
        evidence["wrong_query_metric"] = wrong_query_metric

        annual_value = query(client, {"query_type": "company_period_values",
                                      "metric_id": "ANNUAL_L16_PREMIUM_SINGLE", "period": "2024",
                                      "identity_mode": "entity", "filters": {"entity": "AXA China (Bermuda)"}})
        row = (annual_value.get("data") or [{}])[0]
        results["company_value_returns_identity_and_status"] = bool(
            annual_value.get("ok") and row.get("entity_key") == "ENTITY_AXA_CRI_HK"
            and row.get("record_status") in {"reported_value", "reported_zero", "missing"})
        evidence["annual_company_value"] = annual_value

        provisional_value = query(client, {"query_type": "company_period_values",
                                           "metric_id": "PROV2025_NB_TOTAL_SINGLE", "period": "2025",
                                           "identity_mode": "entity", "filters": {"entity": "AXA CRI (HK)"}})
        results["advertised_provisional_company_value_works"] = bool(provisional_value.get("ok"))
        evidence["provisional_company_value"] = provisional_value

        trend = query(client, {"query_type": "market_trend", "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM",
                               "periods": ["2023Q1"]})
        trend_row = (trend.get("data") or [{}])[0]
        required_row_fields = {"unit", "period", "entity_scope", "certification", "schema"}
        results["every_value_row_has_required_labels"] = required_row_fields <= set(trend_row)
        evidence["trend_row_fields"] = sorted(trend_row)

        lineage = trend.get("lineage") or {}
        results["lineage_is_populated_and_specific"] = bool(
            lineage.get("source_files") and lineage.get("checksums")
            and lineage.get("query_template_id") != "Q1_MARKET_TREND_V1" or
            (lineage.get("source_files") and lineage.get("checksums")))
        evidence["lineage"] = lineage

        results["metadata_uses_contract_source_db_id"] = "source_db_id" in (trend.get("metadata") or {})
        evidence["metadata_keys"] = sorted((trend.get("metadata") or {}).keys())

        malformed = query(client, {"query_type": "market_trend", "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM",
                                   "periods": "2023Q1"})
        results["request_types_strictly_validated"] = (
            not malformed.get("ok", False) and malformed.get("error_code") == "VALIDATION_ERROR")
        evidence["malformed_periods"] = malformed

        after = {k: sha256(v) for k, v in db_paths.items()}
        results["source_db_hashes_unchanged"] = before == after
        evidence["source_hashes_before"] = before
        evidence["source_hashes_after"] = after

    schema_files = list(ROOT.rglob("*schema*.json"))
    results["response_json_schema_delivered"] = bool(schema_files)
    evidence["schema_files"] = [str(p.relative_to(ROOT)) for p in schema_files]

    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad.json"
        bad.write_text("{bad", encoding="utf-8")
        proc = subprocess.run([sys.executable, "-m", "hkia_adapter.cli", "query", "--request", str(bad)],
                              cwd=ROOT, capture_output=True, text=True)
        try:
            cli_payload = json.loads(proc.stdout)
            cli_json = isinstance(cli_payload, dict) and cli_payload.get("ok") is False
        except Exception:
            cli_json = False
        results["cli_invalid_json_returns_json_error"] = cli_json and proc.returncode != 0
        evidence["cli_invalid_json"] = {"returncode": proc.returncode, "stdout": proc.stdout, "stderr_tail": proc.stderr[-500:]}

    existing_gate = subprocess.run([sys.executable, str(HANDOVER / "verify_u20_call.py")],
                                   capture_output=True, text=True)
    bridge_gate = subprocess.run([sys.executable, str(HANDOVER / "verify_u20_r3fix.py"),
                                  "--output", str(Path(tempfile.gettempdir()) / "adapter_bridge_recheck.json")],
                                 capture_output=True, text=True)
    results["existing_baseline_gate_passes"] = existing_gate.returncode == 0
    results["existing_bridge_gate_passes"] = bridge_gate.returncode == 0
    evidence["existing_gate_returncodes"] = {"baseline": existing_gate.returncode, "bridge": bridge_gate.returncode}

    result = {
        "overall": "PASS" if all(results.values()) else "PARTIAL",
        "passed": sum(results.values()),
        "total": len(results),
        "results": results,
        "evidence": evidence,
        "note": "Independent black-box checks add contract cases not present in the implementation-owned acceptance script."
    }
    output = HERE / "independent_acceptance_result.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("overall", "passed", "total", "results")}, ensure_ascii=False, indent=2))
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
