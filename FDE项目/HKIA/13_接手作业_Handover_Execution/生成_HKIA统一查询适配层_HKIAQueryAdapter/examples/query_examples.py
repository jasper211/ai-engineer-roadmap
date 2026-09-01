"""适配层调用示例：Q1-Q4 语义查询，仅调用适配层，不直接 import sqlite3。"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hkia_adapter import HKIAClient


def main():
    with HKIAClient.open_readonly() as client:
        # Q1 市场趋势（标准事实层）
        r = client.query({
            "query_type": "market_trend",
            "metric_id": "NB_IND_TOTAL_ANNUALIZED_PREMIUM",
            "periods": ["2023Q1", "2024Q1", "2025Q1", "2026Q1"],
            "output_unit": "HKD_million",
        })
        print("=== Q1 个人新造年度化保费(百万港元) ===")
        for d in r["data"]:
            print(f"  {d['period']}: {round(d['value'],2)}")

        # Q2 2024 年度公司排名（certified L16）
        r2 = client.query({
            "query_type": "company_ranking",
            "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
            "period": "2024", "entity_scope": "insurer", "limit": 5,
            "output_unit": "HKD_million",
        })
        print("\n=== Q2 2024 个人寿险新造整付 Top5(百万港元) ===")
        for d in r2["data"]:
            print(f"  {d['entity']}: {round(d['value'],2)}")

        # Q3 2025 公司排名（provisional）
        r3 = client.query({
            "query_type": "company_ranking",
            "metric_id": "PROV2025_NB_TOTAL_SINGLE",
            "period": "2025", "entity_scope": "insurer", "limit": 5,
            "output_unit": "HKD_million",
        })
        print("\n=== Q3 2025 个人长期新造整付 Top5(百万港元,含年金混入口径) ===")
        for d in r3["data"]:
            print(f"  {d['entity']}: {round(d['value'],2)}")

        # Q4 财务快照
        r4 = client.query({
            "query_type": "financial_snapshot",
            "metric_id": "FIN_DEBT_SECURITIES",
            "period": "2026Q1", "filters": {"fund_scope": "long_term"},
        })
        print("\n=== Q4 2026Q1 长期业务资产(百万港元) ===")
        for d in r4["data"]:
            print(f"  {d.get('item_id')}: {round(d['value'],2)}")


if __name__ == "__main__":
    main()
