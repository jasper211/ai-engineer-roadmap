"""HKIA 适配层 全部测试（unittest 标准库）：
正常路径 + 防误用硬阻断 + 契约。"""
import sys, os, unittest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hkia_adapter import HKIAClient


class _ClientBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = HKIAClient.open_readonly()
    @classmethod
    def tearDownClass(cls):
        cls.client.close()


class TestConnections(_ClientBase):
    def test_5_db_rowcounts(self):
        r = self.client.query({"query_type": "healthcheck"})
        self.assertTrue(r["ok"])
        rows = r["data"]["rows"]
        self.assertEqual(rows["master"], 59516)
        self.assertEqual(rows["standard"], 72+4914+18+18)
        self.assertEqual(rows["annual"], 7097)
        self.assertEqual(rows["provisional2025"], 414)
        self.assertEqual(rows["financial"], 408)


class TestCoreQueries(_ClientBase):
    def test_q1_market_trend(self):
        r = self.client.query({"query_type": "market_trend",
                               "metric_id": "NB_IND_TOTAL_ANNUALIZED_PREMIUM",
                               "periods": ["2023Q1","2024Q1","2025Q1","2026Q1"],
                               "output_unit": "HKD_million"})
        self.assertTrue(r["ok"], str(r))
        self.assertEqual(len(r["data"]), 4)
        self.assertAlmostEqual(r["data"][-1]["value"], 50576.6259556103, places=2)

    def test_q2_company_ranking_2024(self):
        r = self.client.query({"query_type": "company_ranking",
                               "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                               "period": "2024", "entity_scope": "insurer", "limit": 10,
                               "output_unit": "HKD_million"})
        self.assertTrue(r["ok"], str(r))
        self.assertEqual(len(r["data"]), 10)
        self.assertEqual(r["data"][0]["entity"], "Hang Seng Insurance")
        self.assertAlmostEqual(r["data"][0]["value"], 22147.387, places=2)

    def test_q3_company_ranking_2025(self):
        r = self.client.query({"query_type": "company_ranking",
                               "metric_id": "PROV2025_NB_TOTAL_SINGLE",
                               "period": "2025", "entity_scope": "insurer", "limit": 10,
                               "output_unit": "HKD_million"})
        self.assertTrue(r["ok"], str(r))
        self.assertEqual(len(r["data"]), 10)
        self.assertEqual(r["data"][0]["entity"], "Hang Seng Insurance")
        self.assertAlmostEqual(r["data"][0]["value"], 28731.149, places=2)

    def test_q4_financial_snapshot(self):
        r = self.client.query({"query_type": "financial_snapshot",
                               "metric_id": "FIN_DEBT_SECURITIES",
                               "period": "2026Q1", "filters": {"fund_scope": "long_term"}})
        self.assertTrue(r["ok"], str(r))
        self.assertGreaterEqual(len(r["data"]), 3)


class TestMisuseBlock(_ClientBase):
    def test_unknown_query_type(self):
        r = self.client.query({"query_type": "execute_sql"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "VALIDATION_ERROR")

    def test_sqlinjection_field(self):
        r = self.client.query({"query_type": "company_ranking",
                               "metric_id": "ANNUAL_L16_PREMIUM_SINGLE", "period": "2024",
                               "limit": 10, "sort.": "DROP TABLE"})
        self.assertFalse(r["ok"])

    def test_count_to_money(self):
        r = self.client.query({"query_type": "market_trend", "metric_id": "NB_GROUP_POLICIES",
                               "periods": ["2023Q1"], "output_unit": "HKD_million"})
        self.assertFalse(r["ok"])

    def test_l16_vs_l1_blocked(self):
        r = self.client.query({"query_type": "compare_periods",
                               "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                               "filters": {"period_a": "2024", "period_b": "2025"},
                               "identity_mode": "entity", "release_intent": "internal_analysis"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "NOT_COMPARABLE_SCOPE")
        self.assertNotIn("growth", str(r).lower())

    def test_bare_name_cross_year_blocked(self):
        r = self.client.query({"query_type": "company_period_values",
                               "metric_id": "ANNUAL_L16_PREMIUM_SINGLE", "period": "2024",
                               "filters": {"entity": "AIA International"}})
        self.assertFalse(r["ok"])
        self.assertIn("identity_mode", str(r.get("message", "")))

    def test_publish_65_blocked(self):
        r = self.client.query({"query_type": "compare_periods",
                               "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
                               "filters": {"period_a": "2024", "period_b": "2025",
                                           "publish_unvalidated_growth": True},
                               "identity_mode": "entity", "release_intent": "reporting"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "RELEASE_BLOCKED_UNVALIDATED_SCOPE")

    def test_unknown_unit_blocked(self):
        r = self.client.query({"query_type": "market_trend", "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM",
                               "periods": ["2023Q1"], "output_unit": "euro"})
        self.assertFalse(r["ok"])


class TestContract(_ClientBase):
    def test_response_schema_keys(self):
        r = self.client.query({"query_type": "market_trend",
                               "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM",
                               "periods": ["2023Q1"]})
        self.assertTrue(r["ok"])
        for k in ("ok", "request_id", "query_type", "data", "metadata", "comparability", "release", "lineage"):
            self.assertIn(k, r)

    def test_metadata_has_labels(self):
        r = self.client.query({"query_type": "market_trend",
                               "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM",
                               "periods": ["2023Q1"]})
        md = r["metadata"]
        self.assertEqual(md["certification"], "provisional")
        self.assertIn("source_unit", md)

    def test_quarter_not_certified(self):
        # 2023Q1 是季度 provisional，绝不能被标 certified
        r = self.client.query({"query_type": "market_trend",
                               "metric_id": "NB_IND_TOTAL_SINGLE_PREMIUM",
                               "periods": ["2023Q1"]})
        self.assertEqual(r["metadata"]["certification"], "provisional")


if __name__ == "__main__":
    unittest.main(verbosity=2)
