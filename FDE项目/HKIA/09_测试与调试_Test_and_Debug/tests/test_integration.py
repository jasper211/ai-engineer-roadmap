#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HKIA 集成测试——对着 raw_data/ 里的13份真实文件跑一遍全流程，做确定性检查
（不用LLM判断对不对，用脚本断言），对应 Agent搭建SOP 5.2节"确定性检查优先"。

跑之前必须已经把13份文件放进 07_接入记忆_Integrate_Memory/raw_data/。
"""
import sys
import unittest
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
for sub in ("06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(AGENT_ROOT / sub))

from skills.report_discovery import ReportDiscovery, EXPECTED_PERIODS
from skills.excel_parser import ExcelParser
from skills.normalizer import Normalizer
from memory.workspace import Workspace

RAW_DATA_DIR = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "raw_data"


class TestHKIAIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.discovery = ReportDiscovery(RAW_DATA_DIR)
        cls.reports, cls.problems = cls.discovery.discover()
        cls.parser = ExcelParser()
        cls.normalizer = Normalizer()

        cls.all_rows = []
        cls.parse_errors = []
        for r in cls.reports:
            try:
                parsed = cls.parser.parse(r.file_path)
                rows = cls.normalizer.normalize(
                    parsed, year=r.year, quarter=r.quarter,
                    period_type=r.period_type, source_report=r.file_path.name,
                )
                cls.all_rows.append((r, parsed, rows))
            except Exception as e:
                cls.parse_errors.append((r, e))

    def test_all_13_periods_present(self):
        """完整性：13期一期不缺，缺了要能看见，不能静默漏掉。"""
        self.assertEqual(
            len(self.reports), len(EXPECTED_PERIODS),
            f"应该有{len(EXPECTED_PERIODS)}期，实际找到{len(self.reports)}期。"
            f"问题：{self.problems}"
        )

    def test_no_parse_errors(self):
        """13份文件全部能解析成功，不能有沉默失败。"""
        self.assertEqual(
            len(self.parse_errors), 0,
            f"以下期数解析失败: {[(r.year, r.quarter, str(e)) for r, e in self.parse_errors]}"
        )

    def test_schema_version_matches_known_transition(self):
        """已知的新旧制度分界：2023~2024Q2应为pre_rbc，2024Q3起应为post_rbc。
        这是对着真实官网确认过的事实（RBC制度2024年7月实施），不是假设。"""
        for r, parsed, _ in self.all_rows:
            expected = "pre_rbc" if (r.year, r.quarter) <= (2024, 2) else "post_rbc"
            self.assertEqual(
                parsed["schema_version"], expected,
                f"{r.year}Q{r.quarter} 期望schema={expected}，实际={parsed['schema_version']}"
            )

    def test_spot_check_2023q1_new_business(self):
        """抽查1：2023Q1新造业务·基本計劃，对照官网原始Excel人工核实过的真实数值。"""
        rows = self._rows_for(2023, 1, "new_business", "基本計劃")
        values = {r.metric_name: r.value for r in rows}
        self.assertEqual(values.get("保單數目/整付保費"), 9903)
        self.assertEqual(values.get("保單數目/非整付保費"), 185127)
        self.assertEqual(values.get("承保款項或全年年金/整付保費"), 25128942)
        self.assertEqual(values.get("承保款項或全年年金/非整付保費"), 100972513)

    def test_spot_check_2023q1_in_force(self):
        """抽查2：2023Q1有效业务·基本計劃。"""
        rows = self._rows_for(2023, 1, "in_force", "基本計劃")
        values = {r.metric_name: r.value for r in rows}
        self.assertEqual(values.get("此期間末的有效業務/保單數目"), 12829191)
        self.assertEqual(values.get("此期間末的有效業務/承保保額或全年年金"), 7652363431)

    def test_spot_check_2025q1_new_business_participating(self):
        """抽查3：2025Q1新造业务·分紅業務下的終身壽險——这是修过重复bug的
        回归测试：同名"終身壽險"在分紅業務/其他業務下必须分开，不能撞成一条。"""
        rows = self._rows_for(2025, 1, "new_business", "終身壽險")
        other_biz_rows = self._rows_for(2025, 1, "new_business", "其他業務 / 終身壽險")
        self.assertGreater(len(rows), 0, "分紅業務下的終身壽險记录不应为空")
        self.assertGreater(len(other_biz_rows), 0, "其他業務下的終身壽險记录不应为空")
        values = {r.metric_name: r.value for r in rows}
        self.assertEqual(values.get("此期間的新造直接人壽業務/保單數目/整付保費"), 11001)

    def test_no_duplicate_category_metric_within_period(self):
        """确定性检查：同一期同一张表里，(category, metric_name)不应该重复
        ——重复意味着有两行数据被错误地合并成了一个key。"""
        for r, _, rows in self.all_rows:
            for table_type in ("new_business", "in_force"):
                seen = set()
                for row in rows:
                    if row.table_type != table_type:
                        continue
                    key = (row.category, row.metric_name)
                    self.assertNotIn(
                        key, seen,
                        f"{r.year}Q{r.quarter}/{table_type} 出现重复的 "
                        f"(category, metric_name): {key}"
                    )
                    seen.add(key)

    def test_end_to_end_writes_to_local_sqlite(self):
        """端到端：跑完整个agent流程，本地数据库真的有数据，不是空跑一遍。"""
        workspace = Workspace()
        workspace.reset()
        for _, _, rows in self.all_rows:
            workspace.insert_rows(rows)
        self.assertEqual(workspace.row_count(), sum(len(rows) for _, _, rows in self.all_rows))
        self.assertEqual(len(workspace.distinct_periods()), 13)

    def _rows_for(self, year, quarter, table_type, category):
        month_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
        target_date = f"{year}-{month_day}"
        for r, _, rows in self.all_rows:
            if r.year == year and r.quarter == quarter:
                return [row for row in rows if row.table_type == table_type and row.category == category]
        return []


if __name__ == "__main__":
    unittest.main(verbosity=2)
