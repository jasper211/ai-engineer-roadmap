"""适配层验收脚本：正常路径 + 防误用 + 契约 + 回归。生成 acceptance_result.json。"""
import sys, os, json, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hkia_adapter import HKIAClient

ADAPTER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT = os.path.join(ADAPTER_DIR, "qa", "acceptance_result.json")


def run():
    client = HKIAClient.open_readonly()
    results = {}
    # 1. 5库健康
    h = client.query({"query_type": "healthcheck"})
    rows = h["data"]["rows"]
    results["5db_connect_and_rows"] = bool(h["ok"] and rows["master"]==59516 and
        rows["standard"]==5022 and rows["annual"]==7097 and
        rows["provisional2025"]==414 and rows["financial"]==408)
    # 2. Q1
    q1 = client.query({"query_type":"market_trend","metric_id":"NB_IND_TOTAL_ANNUALIZED_PREMIUM",
                       "periods":["2023Q1","2024Q1","2025Q1","2026Q1"],"output_unit":"HKD_million"})
    results["q1_4rows"] = q1["ok"] and len(q1["data"])==4
    results["q1_2026Q1_value"] = q1["ok"] and abs(q1["data"][-1]["value"]-50576.6259556103)<0.01
    # 3. Q2
    q2 = client.query({"query_type":"company_ranking","metric_id":"ANNUAL_L16_PREMIUM_SINGLE",
                       "period":"2024","entity_scope":"insurer","limit":10,"output_unit":"HKD_million"})
    results["q2_top"] = q2["ok"] and q2["data"][0]["entity"]=="Hang Seng Insurance" and abs(q2["data"][0]["value"]-22147.387)<0.01
    # 4. Q3
    q3 = client.query({"query_type":"company_ranking","metric_id":"PROV2025_NB_TOTAL_SINGLE",
                       "period":"2025","entity_scope":"insurer","limit":10,"output_unit":"HKD_million"})
    results["q3_top"] = q3["ok"] and q3["data"][0]["entity"]=="Hang Seng Insurance" and abs(q3["data"][0]["value"]-28731.149)<0.01
    # 5. Q4
    q4 = client.query({"query_type":"financial_snapshot","metric_id":"FIN_DEBT_SECURITIES",
                       "period":"2026Q1","filters":{"fund_scope":"long_term"}})
    results["q4_rows"] = q4["ok"] and len(q4["data"])==3
    # 防误用
    results["block_unknown_querytype"] = (lambda r: not r["ok"])(client.query({"query_type":"execute_sql"}))
    results["block_count_to_money"] = (lambda r: not r["ok"])(client.query({"query_type":"market_trend","metric_id":"NB_GROUP_POLICIES","periods":["2023Q1"],"output_unit":"HKD_million"}))
    results["block_l16_vs_l1"] = (lambda r: not r["ok"] and r.get("error_code")=="NOT_COMPARABLE_SCOPE")(
        client.query({"query_type":"compare_periods","metric_id":"ANNUAL_L16_PREMIUM_SINGLE",
                      "filters":{"period_a":"2024","period_b":"2025"},"identity_mode":"entity","release_intent":"internal_analysis"}))
    results["block_bare_name"] = (lambda r: not r["ok"])(
        client.query({"query_type":"company_period_values","metric_id":"ANNUAL_L16_PREMIUM_SINGLE",
                      "period":"2024","filters":{"entity":"AIA International"}}))
    results["block_65pct_release"] = (lambda r: not r["ok"] and r.get("error_code")=="RELEASE_BLOCKED_UNVALIDATED_SCOPE")(
        client.query({"query_type":"compare_periods","metric_id":"ANNUAL_L16_PREMIUM_SINGLE",
                      "filters":{"period_a":"2024","period_b":"2025","publish_unvalidated_growth":True},
                      "identity_mode":"entity","release_intent":"reporting"}))
    results["block_sql_field"] = (lambda r: not r["ok"])(
        client.query({"query_type":"company_ranking","metric_id":"ANNUAL_L16_PREMIUM_SINGLE","period":"2024","limit":10,"sort.":"DROP TABLE"}))
    results["block_unknown_unit"] = (lambda r: not r["ok"])(
        client.query({"query_type":"market_trend","metric_id":"NB_IND_TOTAL_SINGLE_PREMIUM","periods":["2023Q1"],"output_unit":"euro"}))
    results["block_unknown_field"] = (lambda r: not r["ok"])(
        client.query({"query_type":"market_trend","metric_id":"NB_IND_TOTAL_SINGLE_PREMIUM","periods":["2023Q1"],"evil":"x"}))
    # 契约
    sample = q1
    results["contract_has_all_keys"] = all(k in sample for k in ("ok","request_id","query_type","data","metadata","comparability","release","lineage"))
    results["metadata_has_labels"] = "source_unit" in sample["metadata"] and "certification" in sample["metadata"]
    results["quarter_not_certified"] = sample["metadata"]["certification"]=="provisional"
    client.close()
    all_pass = all(results.values())
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out = {"overall": "PASS" if all_pass else "PARTIAL",
           "tested_at": ts, "results": results,
           "technical_adapter": "PASS" if all_pass else "FAILED",
           "analysis_conclusion_release": "NOT_PASS (范围等价未验收, +65.4%禁止放行)"}
    os.makedirs(os.path.dirname(RESULT), exist_ok=True)
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(run())
