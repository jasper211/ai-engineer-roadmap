"""基于权威库和合格补充证据构建L3基础模型快照。"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from tools.evidence import EvidenceClass, EvidenceRecord, EvidenceStatus, SourceRef, authoritative
from tools.postgres_reader import PostgresL3Reader
from tools.snapshot_writer import write_snapshot
from skills.blueprint_parser import parse_blueprint

VALID_TIERS = {"Human", "Aug", "Hybrid", "Auto"}
D_FIELDS = (
    "agent_d1_input_struct",
    "agent_d2_rule_clear",
    "agent_d3_output_verify",
    "agent_d4_api_reach",
    "agent_d5_fallback",
    "agent_d6_compliance",
)


@dataclass(frozen=True)
class BlueprintIndex:
    l3_code: str
    l3_name: str
    version: str
    filename: str


def load_blueprint_index(path: Path) -> dict[str, BlueprintIndex]:
    result = {}
    with Path(path).open(encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            code = row.get("l3_code", "").strip()
            if not code:
                continue
            full_code = (code if code.startswith("L3-") else f"L3-{code}").upper()
            raw_version = row.get("version", "").strip()
            version_match = re.search(r"(\d+)\D+(\d+)", raw_version)
            normalized_version = f"V{version_match.group(1)}.{version_match.group(2)}" if version_match else raw_version
            result[full_code] = BlueprintIndex(
                l3_code=full_code,
                l3_name=row.get("l3_name", "").strip(),
                version=normalized_version,
                filename=row.get("filename", "").strip(),
            )
    return result


def gate_result(status: str, checks: list[dict]) -> dict:
    return {"status": status, "checks": checks}


class L3ModelBuilder:
    schema_version = "vnw.l3-model.v1"

    def __init__(
        self,
        reader: PostgresL3Reader,
        blueprint_index: dict[str, BlueprintIndex],
        blueprint_dir: Path | None = None,
    ):
        self.reader = reader
        self.blueprint_index = blueprint_index
        self.blueprint_dir = blueprint_dir

    def build(self, l3_code: str, supplemental: list[EvidenceRecord] | None = None) -> dict:
        processes = self.reader.processes(l3_code)
        nodes = self.reader.value_nodes(l3_code)
        mappings = self.reader.vn_l4_mappings(l3_code)
        l2s = self.reader.l2_mappings(l3_code)
        kpis = self.reader.kpi_mappings(l3_code)
        value_stages = self.reader.value_stream_mappings(l3_code)
        blueprint = self.blueprint_index.get(l3_code)
        parsed_blueprint = None
        if blueprint and self.blueprint_dir:
            source_path = self.blueprint_dir / blueprint.filename
            if source_path.exists():
                parsed_blueprint = parse_blueprint(
                    source_path,
                    {row.get("l4_code", "") for row in processes if row.get("l4_code")},
                )
        evidence: dict[str, dict] = {}

        def add(record: EvidenceRecord) -> str:
            evidence[record.evidence_id] = record.to_dict()
            return record.evidence_id

        if parsed_blueprint and parsed_blueprint["structure_status"] == "PARSED":
            for step in parsed_blueprint["steps"]:
                step["evidence_ref"] = add(EvidenceRecord(
                    field_name=f"blueprint.steps.{step['step_id']}",
                    value={"step_name": step["step_name"], "l4_codes": step["l4_codes"]},
                    evidence_class=EvidenceClass.SUPPLEMENTAL,
                    status=EvidenceStatus.ACTIVE,
                    source=SourceRef(
                        source_system="L3流程库",
                        source_object=blueprint.filename,
                        source_key=f"line:{step['source_line']}",
                        source_field="step",
                        source_version=blueprint.version,
                    ),
                ))
            for decision in parsed_blueprint["decisions"]:
                decision["evidence_ref"] = add(EvidenceRecord(
                    field_name=f"blueprint.decisions.{decision['decision_id']}",
                    value={"question": decision["question"], "branches": decision["branches"]},
                    evidence_class=EvidenceClass.SUPPLEMENTAL,
                    status=EvidenceStatus.ACTIVE,
                    source=SourceRef(
                        source_system="L3流程库",
                        source_object=blueprint.filename,
                        source_key=f"line:{decision['source_line']}",
                        source_field="decision",
                        source_version=blueprint.version,
                    ),
                ))
            for node in parsed_blueprint["blueprint_value_nodes"]:
                node["evidence_ref"] = add(EvidenceRecord(
                    field_name=f"blueprint.value_nodes.{node['vn_id']}",
                    value={"vn_name": node["vn_name"], "l4_codes": node["l4_codes"], "status": node["status_text"]},
                    evidence_class=EvidenceClass.SUPPLEMENTAL,
                    status=EvidenceStatus.ACTIVE,
                    source=SourceRef(
                        source_system="L3流程库",
                        source_object=blueprint.filename,
                        source_key=f"line:{node['source_line']}",
                        source_field="value_node_mapping",
                        source_version=blueprint.version,
                    ),
                ))
            for row in parsed_blueprint["raci"]:
                row["evidence_ref"] = add(EvidenceRecord(
                    field_name=f"blueprint.raci.{row['l4_code']}",
                    value={key: row[key] for key in ("accountable", "responsible", "consulted", "informed")},
                    evidence_class=EvidenceClass.SUPPLEMENTAL,
                    status=EvidenceStatus.ACTIVE,
                    source=SourceRef(
                        source_system="L3流程库",
                        source_object=blueprint.filename,
                        source_key=f"line:{row['source_line']}",
                        source_field="raci",
                        source_version=blueprint.version,
                    ),
                ))

        l4s = []
        for row in processes:
            code = row.get("l4_code", "")
            refs = {
                field: add(authoritative(field, row.get(field), "dim_process", code, field))
                for field in (
                    "l4_name", "l4_deliverable", "l4_deliverable_type",
                    "agentifiability", "agent_human_touchpoint", *D_FIELDS,
                )
            }
            l4s.append({
                "l4_code": code,
                "l4_name": row.get("l4_name", ""),
                "deliverable": row.get("l4_deliverable", ""),
                "deliverable_type": row.get("l4_deliverable_type", ""),
                "tier": row.get("agentifiability", ""),
                "human_touchpoint": row.get("agent_human_touchpoint", ""),
                "d1_d6": {field: row.get(field) for field in D_FIELDS},
                "evidence_refs": refs,
            })

        vn_items = []
        for row in nodes:
            key = row.get("vn_id", "")
            refs = {
                field: add(authoritative(field, row.get(field), "dim_vn", key, field))
                for field in (
                    "vn_name", "overall_judgment", "is_fused", "priority",
                    "gate1_data_linked", "gate2_grounded", "gate3_traceable",
                )
            }
            vn_items.append({
                "vn_id": key,
                "vn_name": row.get("vn_name", ""),
                "is_fused": row.get("is_fused"),
                "priority": row.get("priority", ""),
                "overall_judgment": row.get("overall_judgment", ""),
                "evidence_refs": refs,
            })

        if supplemental:
            for record in supplemental:
                if record.evidence_class is not EvidenceClass.SUPPLEMENTAL:
                    raise ValueError("supplemental参数只接受SUPPLEMENTAL证据")
                add(record)

        has_l4 = bool(l4s)
        names_complete = has_l4 and all(item["l4_name"] for item in l4s)
        has_blueprint = blueprint is not None
        gate_m_checks = [
            {"rule_id": "M-001", "passed": has_l4, "detail": f"L4数量={len(l4s)}"},
            {"rule_id": "M-002", "passed": has_blueprint, "detail": blueprint.filename if blueprint else "缺少蓝图索引"},
            {"rule_id": "M-003", "passed": names_complete, "detail": "L4名称完整" if names_complete else "L4名称缺失"},
        ]
        gate_m = "PASS" if all(c["passed"] for c in gate_m_checks) else ("PARTIAL" if has_l4 else "FAIL")

        deliverables_complete = has_l4 and all(item["deliverable"] for item in l4s)
        tiers_valid = has_l4 and all(item["tier"] in VALID_TIERS for item in l4s)
        gate_e_checks = [
            {"rule_id": "E-001", "passed": gate_m == "PASS", "detail": f"Gate M={gate_m}"},
            {"rule_id": "E-002", "passed": deliverables_complete, "detail": f"交付物完整={sum(bool(x['deliverable']) for x in l4s)}/{len(l4s)}"},
            {"rule_id": "E-003", "passed": tiers_valid, "detail": "Tier合法" if tiers_valid else "Tier缺失或非法"},
        ]
        gate_e = "PASS" if all(c["passed"] for c in gate_e_checks) else ("PARTIAL" if has_l4 else "FAIL")

        d_complete_count = sum(all(item["d1_d6"][field] is not None for field in D_FIELDS) for item in l4s)
        d_complete = has_l4 and d_complete_count == len(l4s)
        mapping_complete = bool(mappings)
        not_fused = bool(nodes) and all(row.get("is_fused") is False for row in nodes)
        gate_a_checks = [
            {"rule_id": "A-001", "passed": gate_e == "PASS", "detail": f"Gate E={gate_e}"},
            {"rule_id": "A-002", "passed": d_complete, "detail": f"D1-D6完整={d_complete_count}/{len(l4s)}"},
            {"rule_id": "A-003", "passed": mapping_complete, "detail": f"价值节点-L4映射={len(mappings)}"},
            {"rule_id": "A-004", "passed": not_fused, "detail": "无熔断节点" if not_fused else "存在熔断或无价值节点"},
        ]
        gate_a = "PASS" if all(c["passed"] for c in gate_a_checks) else "BLOCKED"

        l3_name = processes[0].get("l3_name", "") if processes else (blueprint.l3_name if blueprint else "")
        model = {
            "schema_version": self.schema_version,
            "l3_code": l3_code,
            "l3_name": l3_name,
            "source_policy": {
                "database_authority": "process_analytics",
                "supplemental_requires_active": True,
                "consensus_separate": True,
                "reverse_writeback": False,
            },
            "blueprint": {
                "coverage": "INDEXED" if blueprint else "MISSING",
                "version": blueprint.version if blueprint else "",
                "filename": blueprint.filename if blueprint else "",
                "structure_status": parsed_blueprint["structure_status"] if parsed_blueprint else ("INDEX_ONLY" if blueprint else "UNAVAILABLE"),
                "steps": parsed_blueprint["steps"] if parsed_blueprint else [],
                "decisions": parsed_blueprint["decisions"] if parsed_blueprint else [],
                "edges": parsed_blueprint["edges"] if parsed_blueprint else [],
                "blueprint_value_nodes": parsed_blueprint["blueprint_value_nodes"] if parsed_blueprint else [],
                "raci": parsed_blueprint["raci"] if parsed_blueprint else [],
                "source_path": parsed_blueprint["source_path"] if parsed_blueprint else "",
                "source_hash": parsed_blueprint["source_hash"] if parsed_blueprint else "",
                "diagnostics": parsed_blueprint["diagnostics"] if parsed_blueprint else {},
                "note": (
                    "已从蓝图正文解析；步骤顺序边由显式步骤编号派生，判断分支保留原文行号"
                    if parsed_blueprint and parsed_blueprint["structure_status"] == "PARSED"
                    else "正文缺少可确认结构或与当前数据库冲突，禁止生成箭头、决策点和回退关系"
                ),
            },
            "l2_capabilities": l2s,
            "l4s": l4s,
            "value_nodes": vn_items,
            "vn_l4_mappings": mappings,
            "kpi_mappings": kpis,
            "value_stream_mappings": value_stages,
            "gates": {
                "M": gate_result(gate_m, gate_m_checks),
                "E": gate_result(gate_e, gate_e_checks),
                "A": gate_result(gate_a, gate_a_checks),
            },
            "evidence_registry": sorted(evidence.values(), key=lambda item: item["evidence_id"]),
            "supplemental_evidence_refs": [record.evidence_id for record in (supplemental or [])],
        }
        return model

    def build_and_write(
        self, l3_codes: list[str], output_dir: Path, supplemental_by_l3: dict[str, list[EvidenceRecord]] | None = None
    ) -> list[dict]:
        results = []
        models = []
        for code in l3_codes:
            model = self.build(code, (supplemental_by_l3 or {}).get(code, []))
            models.append(model)
            results.append(write_snapshot(model, output_dir))
        indexed_models = {}
        for snapshot_path in output_dir.glob("L3-*.json"):
            if snapshot_path.name.endswith(".manifest.json"):
                continue
            stored_model = json.loads(snapshot_path.read_text(encoding="utf-8"))
            if stored_model.get("schema_version") == self.schema_version:
                indexed_models[stored_model["l3_code"]] = stored_model
        for model in models:
            indexed_models[model["l3_code"]] = model
        index = {
            "schema_version": "vnw.l3-model-index.v1",
            "source_policy": "PostgreSQL权威；仅生效OB材料可补充；工作坊判断仅存浏览器本地",
            "models": [
                {
                    "l3_code": model["l3_code"],
                    "l3_name": model["l3_name"],
                    "l4_count": len(model["l4s"]),
                    "value_node_count": len(model["value_nodes"]),
                    "blueprint_coverage": model["blueprint"]["coverage"],
                    "blueprint_version": model["blueprint"]["version"],
                    "gates": {key: value["status"] for key, value in model["gates"].items()},
                    "classification": "MODEL_READY" if model["gates"]["A"]["status"] == "PASS" else "NEEDS_DATA",
                    "highest_gate": (
                        "A" if model["gates"]["A"]["status"] == "PASS"
                        else "E" if model["gates"]["E"]["status"] == "PASS"
                        else "M" if model["gates"]["M"]["status"] == "PASS"
                        else "NONE"
                    ),
                    "gap_reasons": [
                        check["detail"]
                        for gate in ("M", "E", "A")
                        for check in model["gates"][gate]["checks"]
                        if not check["passed"]
                    ],
                    "blueprint_structure_status": model["blueprint"]["structure_status"],
                    "snapshot_file": f"{model['l3_code']}.json",
                }
                for model in sorted(indexed_models.values(), key=lambda item: item["l3_code"])
            ],
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return results
