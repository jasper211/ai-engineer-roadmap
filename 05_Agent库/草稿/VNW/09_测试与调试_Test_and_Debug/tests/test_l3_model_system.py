from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path

VNW_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VNW_ROOT / "05_集成工具_Integrate_Tools"))
sys.path.insert(0, str(VNW_ROOT / "06_开发技能_Develop_Skills"))

from skills.l3_model_builder import BlueprintIndex, L3ModelBuilder  # noqa: E402
from skills.l3_analysis_contract import ANALYSIS_STANDARD_ID, validate_analysis_package  # noqa: E402
from skills.l3_analysis_runner import L3AnalysisRunner, _json_from_text, normalize_model_package  # noqa: E402
from skills.blueprint_parser import parse_blueprint  # noqa: E402
from tools.evidence import EvidenceClass, EvidenceRecord, EvidenceStatus, SourceRef, authoritative  # noqa: E402
from tools.obsidian_reader import note_is_eligible  # noqa: E402
from tools.postgres_reader import BulkPostgresL3Reader, assert_read_only_sql  # noqa: E402
from tools.snapshot_writer import write_snapshot  # noqa: E402


class FakeReader:
    def __init__(self, complete_d: bool, with_mapping: bool):
        d_value = "Y" if complete_d else None
        self.row = {
            "l3_code": "L3-T", "l3_name": "测试流程", "l4_code": "L4-T-01",
            "l4_name": "形成测试交付物", "l4_deliverable": "测试交付物",
            "l4_deliverable_type": "文档", "agentifiability": "Hybrid",
            "agent_human_touchpoint": "人工复核",
            **{field: d_value for field in (
                "agent_d1_input_struct", "agent_d2_rule_clear", "agent_d3_output_verify",
                "agent_d4_api_reach", "agent_d5_fallback", "agent_d6_compliance",
            )},
        }
        self.with_mapping = with_mapping

    def processes(self, _): return [self.row]
    def value_nodes(self, _): return [{"vn_id": "VN-T-01", "vn_name": "测试节点", "is_fused": False}]
    def vn_l4_mappings(self, _): return [{"vn_id": "VN-T-01", "l4_code": "L4-T-01", "mapping_status": "direct"}] if self.with_mapping else []
    def l2_mappings(self, _): return [{"l2_code": "L2-T", "l2_name": "测试能力"}]
    def kpi_mappings(self, _): return []
    def value_stream_mappings(self, _): return []


class L3ModelSystemTests(unittest.TestCase):
    def builder(self, complete_d=True, with_mapping=True):
        index = {"L3-T": BlueprintIndex("L3-T", "测试流程", "V1.0", "蓝图.md")}
        return L3ModelBuilder(FakeReader(complete_d, with_mapping), index)

    def test_evidence_is_deterministic(self):
        a = authoritative("deliverable", "文档", "dim_process", "L4-T-01", "l4_deliverable")
        b = authoritative("deliverable", "文档", "dim_process", "L4-T-01", "l4_deliverable")
        self.assertEqual(a.evidence_id, b.evidence_id)

    def test_derived_requires_rule(self):
        with self.assertRaises(ValueError):
            EvidenceRecord("gate", "PASS", EvidenceClass.DERIVED, SourceRef("VNW", "gate", "A", "status"))

    def test_nonactive_supplemental_is_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceRecord("note", "x", EvidenceClass.SUPPLEMENTAL, SourceRef("OB", "n", "n", "content"), EvidenceStatus.UNVERIFIED)

    def test_sql_mutation_is_rejected(self):
        assert_read_only_sql("SELECT * FROM process_analytics.dim_process")
        with self.assertRaises(ValueError):
            assert_read_only_sql("WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x")

    def test_pending_ob_note_is_rejected(self):
        self.assertFalse(note_is_eligible({"status": "生效", "content": "⚠️ 待复核：源文档已被删除"}))
        self.assertTrue(note_is_eligible({"status": "生效", "content": "这是源文档治理规则说明"}))

    def test_gate_a_requires_d_and_mapping(self):
        self.assertEqual(self.builder(False, False).build("L3-T")["gates"]["A"]["status"], "BLOCKED")
        self.assertEqual(self.builder(True, True).build("L3-T")["gates"]["A"]["status"], "PASS")

    def test_index_does_not_invent_blueprint_structure(self):
        model = self.builder().build("L3-T")
        self.assertEqual(model["blueprint"]["structure_status"], "INDEX_ONLY")
        self.assertEqual(model["blueprint"]["steps"], [])
        self.assertEqual(model["blueprint"]["edges"], [])

    def test_snapshot_hash_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = self.builder().build("L3-T")
            first = write_snapshot(model, Path(tmp))
            second = write_snapshot(model, Path(tmp))
            self.assertEqual(first["snapshot_hash"], second["snapshot_hash"])

    def test_all_l3_receive_same_analysis_contract(self):
        model = self.builder().build("L3-T")
        self.assertEqual(model["analysis"]["analysis_standard_id"], ANALYSIS_STANDARD_ID)
        self.assertEqual(len(model["analysis"]["l4_analysis"]), 1)
        self.assertEqual(model["analysis"]["l4_analysis"][0]["analysis_status"], "PENDING_MODEL")

    def test_model_draft_without_evidence_is_rejected(self):
        model = self.builder().build("L3-T")
        package = model["analysis"]
        package["l4_analysis"][0]["analysis_status"] = "MODEL_DRAFT"
        package["l4_analysis"][0]["evidence_refs"] = []
        with self.assertRaises(ValueError):
            validate_analysis_package(package, set(), {"L4-T-01"})

    def test_blueprint_parser_keeps_explicit_steps_and_returns(self):
        content = """## 三、关键步骤
步骤1：准备
  └─ 执行L4-T-01：形成输入
步骤2：验证
  └─ 执行L4-T-02：形成输出
  【判断节点1】是否通过？
    ├─ 通过 → 步骤3
    └─ 未通过 → 返回L4-T-01修订
步骤3：完成
  └─ 执行L4-T-03：交付
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blueprint.md"
            path.write_text(content, encoding="utf-8")
            result = parse_blueprint(path, {"L4-T-01", "L4-T-02", "L4-T-03"})
        self.assertEqual(result["structure_status"], "PARSED")
        self.assertEqual(len(result["steps"]), 3)
        self.assertEqual(len(result["decisions"]), 1)
        self.assertTrue(any(edge["edge_type"] == "RETURN" for edge in result["edges"]))

    def test_blueprint_without_l4_is_conflict_not_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blueprint.md"
            path.write_text("## 流程概览\n当前L4结构待确认。", encoding="utf-8")
            result = parse_blueprint(path, {"L4-T-01"})
        self.assertEqual(result["structure_status"], "CONFLICT")
        self.assertEqual(result["steps"], [])

    def test_bulk_reader_groups_rows_without_changing_values(self):
        reader = BulkPostgresL3Reader({
            "processes": [{"l3_code": "L3-B", "l4_code": "2"}, {"l3_code": "L3-A", "l4_code": "1"}],
            "value_nodes": [], "mappings": [], "l2s": [], "kpis": [], "value_streams": [],
        })
        self.assertEqual(reader.l3_codes, ["L3-A", "L3-B"])
        self.assertEqual(reader.processes("L3-A")[0]["l4_code"], "1")

    def test_blueprint_parser_supports_com_main_chain(self):
        content = """## 二、关联价值节点
| VN编码 | VN名称 | 优先级 | 核心交付物 | 关联L4 | 状态 |
| VN-PAY-01 | 佣金包 | P0 | 《佣金表》 | COM-01 / COM-02 | 熔断 |
## 三、端到端L4链路
### 3.1 主链路
[COM-01] 政策接收 ──→ 《政策库》
[COM-02] 差异拆解 ──→ 《配置表》
### 3.2 支链路
## 五、RACI矩阵
| L4 | L4名称 | 主责(A) | 执行(R) | 咨询(C) | 知会(I) |
| COM-01 | 政策接收 | 刘敏然 | Cici | Carrie | Mark |
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "com.md"
            path.write_text(content, encoding="utf-8")
            result = parse_blueprint(path, {"L4-COM-01", "L4-COM-02"})
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(result["blueprint_value_nodes"][0]["vn_id"], "VN-PAY-01")
        self.assertEqual(result["raci"][0]["accountable"], "刘敏然")

    def test_analysis_runner_prepares_auditable_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "08_设计提示词_Design_Prompts/L3统一分析模型_v1.0.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text("只使用事实包。", encoding="utf-8")
            snapshot = root / "L3-T.json"
            snapshot.write_text(json.dumps(self.builder().build("L3-T"), ensure_ascii=False), encoding="utf-8")
            run_dir = L3AnalysisRunner(root).prepare(snapshot)
            request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
            payload = json.loads((run_dir / "user_payload.json").read_text(encoding="utf-8"))
            self.assertEqual(request["status"], "PREPARED")
            self.assertEqual(payload["fact_pack"]["l3_code"], "L3-T")
            self.assertEqual(len(payload["output_contract"]["l4_analysis"]), 1)

    def test_analysis_runner_rejects_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "08_设计提示词_Design_Prompts/L3统一分析模型_v1.0.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text("只使用事实包。", encoding="utf-8")
            snapshot = root / "L3-T.json"
            model = self.builder().build("L3-T")
            snapshot.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
            runner = L3AnalysisRunner(root)
            run_dir = runner.prepare(snapshot)
            (run_dir / "response.raw.json").write_text("{}", encoding="utf-8")
            model["l3_name"] = "已变化"
            snapshot.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "事实快照已变化"):
                runner.validate_and_publish(run_dir)

    def test_analysis_runner_accepts_output_contract_wrapper(self):
        value = _json_from_text('{"output_contract":{"schema_version":"vnw.l3-analysis.v1"}}')
        self.assertEqual(value["schema_version"], "vnw.l3-analysis.v1")

    def test_analysis_runner_normalizes_tasks_without_inventing_quadrant(self):
        package = {
            "l4_analysis": [{
                "l4_code": "L4-T-01", "evidence_refs": ["EVD-1"], "quadrant": "Auto",
                "data_basis": ["x"], "process_context": "y", "risks_limits": ["z"],
                "current_recommendation": "r",
            }],
            "tasks": [{"l4_code": "L4-T-01", "task_name": "测试", "recommended_tier": "Auto", "rationale": "规则"}],
            "decision_drafts": [{"decision_id": "Q1"}],
            "missing_analysis": [],
        }
        result = normalize_model_package(package, {"evidence_registry": []})
        self.assertEqual(result["tasks"][0]["evidence_refs"], ["EVD-1"])
        self.assertEqual(result["priority_drafts"][0]["quadrant"], "unclassified")
        self.assertEqual(result["decision_drafts"], [])


if __name__ == "__main__":
    unittest.main()
