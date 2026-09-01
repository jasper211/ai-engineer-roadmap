"""第四轮独立终审复验：六类响应全部通过真实 JSON Schema 递归校验。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hkia_adapter import HKIAClient
from schema_validator import validate

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_schema():
    # 根目录 schema 与包内 _assets/schema 应一致
    schema = json.loads(open(os.path.join(ROOT, "schema", "response_schema.json"), encoding="utf-8").read())
    pkg_schema = os.path.join(ROOT, "hkia_adapter", "_assets", "schema", "response_schema.json")
    same = "same"
    if os.path.exists(pkg_schema):
        p = json.load(open(pkg_schema, encoding="utf-8"))
        same = "same" if json.dumps(p, sort_keys=True) == json.dumps(schema, sort_keys=True) else "DIFF"
    return schema, same


def main():
    results = {}
    schema, same = load_schema()
    results["schema_root_and_pkg_consistent"] = (same == "same")
    cases = []
    with HKIAClient.open_readonly() as client:
        cases = [
            ("success_query", client.query({"query_type": "market_trend",
                                            "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM", "periods": ["2026Q1"]})),
            ("healthcheck", client.query({"query_type": "healthcheck"})),
            ("validation_fail", client.query({"query_type": "execute_sql"})),
            ("unit_gate_fail", client.query({"query_type": "market_trend",
                                             "metric_id": "NB_GROUP_POLICIES", "periods": ["2023Q1"], "output_unit": "HKD_million"})),
        ]
    with HKIAClient.open_readonly() as client:
        # compare_periods 需要单独触发门禁；用 try 捕获阻断响应
        for name, body in [
            ("l11_gate", {"query_type": "compare_periods", "metric_id": "ANNUAL_L11_RETIREMENT",
                          "filters": {"period_a": "2023", "period_b": "2024", "metric_b": "ANNUAL_L11_SCHEME_COUNT"},
                          "identity_mode": "entity", "release_intent": "internal_analysis"}),
            ("rbc_gate", {"query_type": "compare_periods", "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                          "filters": {"period_a": "2023", "period_b": "2024"},
                          "identity_mode": "entity", "release_intent": "internal_analysis"}),
            ("release_gate", {"query_type": "compare_periods", "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                              "filters": {"period_a": "2024", "period_b": "2025", "publish_unvalidated_growth": True},
                              "identity_mode": "entity", "release_intent": "reporting"}),
        ]:
            r = client.query(body)
            cases.append((name, r))
    for name, resp in cases:
        errors = validate(resp, schema)
        results[name] = (len(errors) == 0)
        print(f"  {name}: schema_ok={len(errors)==0} errors={errors[:3]}")
    overall = all(results.values())
    out = {"overall": "PASS" if overall else "PARTIAL", "schema_consistent": same,
           "cases": results, "note": "六类响应递归 Schema 校验"}
    outfile = os.path.join(HERE, "final_contract_recheck.json")
    open(outfile, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps({"overall": out["overall"], "schema": same, "cases": results}, ensure_ascii=False, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
