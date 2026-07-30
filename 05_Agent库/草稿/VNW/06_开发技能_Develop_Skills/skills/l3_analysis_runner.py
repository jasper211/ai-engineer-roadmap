"""统一L3分析执行器：prepare -> run/import -> validate -> publish。"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from skills.l3_analysis_contract import (
    ANALYSIS_SCHEMA_VERSION,
    ANALYSIS_STANDARD_ID,
    REQUIRED_L4_FIELDS,
    validate_analysis_package,
)
from tools.llm_client import DEFAULT_MODEL, call_json_model


def canonical_hash(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_from_text(text: str) -> dict:
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.S)
    if fenced:
        cleaned = fenced.group(1)
    value = json.loads(cleaned)
    if isinstance(value.get("analysis"), dict):
        value = value["analysis"]
    if isinstance(value.get("output_contract"), dict):
        value = value["output_contract"]
    if not isinstance(value, dict):
        raise ValueError("模型输出不是JSON对象")
    return value


def load_api_config(agent_root: Path) -> tuple[str, str]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    model = os.environ.get("VNW_ANALYSIS_MODEL", "").strip() or DEFAULT_MODEL
    config_path = agent_root / "02_配置项目_Configure_Project/deepseek_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        api_key = api_key or str(config.get("DEEPSEEK_API_KEY", "")).strip()
        model = str(config.get("model", "")).strip() or model
    return api_key, model


def normalize_model_package(package: dict, fact_pack: dict) -> dict:
    """只做可证明的结构归一化，不生成新的业务结论。"""
    l4_by_code = {item.get("l4_code", ""): item for item in package.get("l4_analysis", []) if isinstance(item, dict)}
    normalized_tasks = []
    sequence: dict[str, int] = {}
    for task in package.get("tasks", []):
        if not isinstance(task, dict):
            continue
        code = str(task.get("l4_code", ""))
        analysis = l4_by_code.get(code)
        if not analysis or not task.get("task_name"):
            continue
        sequence[code] = sequence.get(code, 0) + 1
        normalized_tasks.append({
            "task_id": task.get("task_id") or f"{code}-M{sequence[code]:02d}",
            "l4_code": code,
            "task_name": task["task_name"],
            "source_type": task.get("source_type") or "MODEL_DECOMPOSITION_FROM_L4",
            "evidence_refs": task.get("evidence_refs") or analysis.get("evidence_refs", []),
            "analysis_status": "MODEL_DRAFT",
            "suggested_tier": task.get("suggested_tier") or task.get("recommended_tier", ""),
            "tier_rationale": task.get("tier_rationale") or task.get("rationale", ""),
        })
    package["tasks"] = normalized_tasks

    # 位置不能从Auto/Hybrid等生产方式推断，因此不接受模型自造象限名。
    package["priority_drafts"] = [
        {
            "l4_code": item["l4_code"],
            "quadrant": item.get("quadrant") if item.get("quadrant") in {"q1", "q2", "q3", "q4"} else "unclassified",
            "data_basis": item.get("data_basis", []),
            "process_context": item.get("process_context", ""),
            "risks_limits": item.get("risks_limits", []),
            "current_recommendation": item.get("current_recommendation", ""),
            "evidence_refs": item.get("evidence_refs", []),
            "analysis_status": "MODEL_DRAFT",
        }
        for item in package.get("l4_analysis", [])
        if isinstance(item, dict)
    ]

    required_decision_fields = {"priority", "task_ids", "title", "pilot_scope", "human_boundary", "evidence_refs"}
    valid_task_ids = {item["task_id"] for item in normalized_tasks}
    decisions = []
    rejected_decisions = 0
    for item in package.get("decision_drafts", []):
        if (
            isinstance(item, dict)
            and required_decision_fields.issubset(item)
            and set(item.get("task_ids", [])) <= valid_task_ids
        ):
            decisions.append({**item, "analysis_status": "MODEL_DRAFT"})
        else:
            rejected_decisions += 1
    package["decision_drafts"] = decisions

    missing = []
    for item in package.get("missing_analysis", []):
        if isinstance(item, str):
            missing.append(item)
        elif isinstance(item, dict):
            missing.append(" · ".join(str(item.get(key, "")) for key in ("l4_code", "field", "reason") if item.get(key)))
    if rejected_decisions:
        missing.append(f"负责人决策草稿结构不合格，已拒绝{rejected_decisions}条")
    if not normalized_tasks:
        missing.append("模型未返回可校验的逐任务拆分")
    package["missing_analysis"] = list(dict.fromkeys(filter(None, missing)))
    package.setdefault("source_scope", {
        "database": "process_analytics",
        "knowledge": "ACTIVE supplemental evidence only",
        "evidence_count": len(fact_pack["evidence_registry"]),
    })
    package.setdefault("control_chain", [])
    package.setdefault("rejected_task_sources", [])
    return package


class L3AnalysisRunner:
    def __init__(self, agent_root: Path):
        self.agent_root = Path(agent_root)
        self.prompt_path = self.agent_root / "08_设计提示词_Design_Prompts/L3统一分析模型_v1.0.md"
        self.run_root = self.agent_root / "07_接入记忆_Integrate_Memory/analysis_runs"
        self.package_root = self.agent_root / "07_接入记忆_Integrate_Memory/analysis_packages"

    def _fact_pack(self, snapshot: dict) -> dict:
        return {
            "l3_code": snapshot["l3_code"],
            "l3_name": snapshot["l3_name"],
            "snapshot_hash": canonical_hash(snapshot),
            "source_policy": snapshot.get("source_policy", {}),
            "gates": snapshot.get("gates", {}),
            "l2_capabilities": snapshot.get("l2_capabilities", []),
            "l4s": snapshot.get("l4s", []),
            "value_nodes": snapshot.get("value_nodes", []),
            "vn_l4_mappings": snapshot.get("vn_l4_mappings", []),
            "kpi_mappings": snapshot.get("kpi_mappings", []),
            "value_stream_mappings": snapshot.get("value_stream_mappings", []),
            "blueprint": snapshot.get("blueprint", {}),
            "evidence_registry": snapshot.get("evidence_registry", []),
        }

    def _output_contract(self, fact_pack: dict) -> dict:
        return {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "analysis_standard_id": ANALYSIS_STANDARD_ID,
            "generation_mode": "UNIFIED_MODEL",
            "analysis_status": "MODEL_DRAFT",
            "model_run": None,
            "source_scope": {
                "database": "process_analytics",
                "knowledge": "ACTIVE supplemental evidence only",
                "evidence_count": len(fact_pack["evidence_registry"]),
            },
            "l4_analysis": [
                {
                    "l4_code": item["l4_code"],
                    "analysis_status": "MODEL_DRAFT",
                    "evidence_refs": [],
                    "confidence": "MODEL_DRAFT",
                    **{
                        field: [] if field in {
                            "specific_capabilities", "handoff_triggers", "control_gates",
                            "data_basis", "risks_limits",
                        } else ""
                        for field in REQUIRED_L4_FIELDS
                    },
                    "database_tier": item.get("tier", ""),
                    "recommended_tier": "",
                    "quadrant": "unclassified",
                }
                for item in fact_pack["l4s"]
            ],
            "tasks": [],
            "priority_drafts": [],
            "decision_drafts": [],
            "control_chain": [],
            "rejected_task_sources": [],
            "missing_analysis": [],
        }

    def prepare(self, snapshot_path: Path) -> Path:
        snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        fact_pack = self._fact_pack(snapshot)
        run_id = f"{snapshot['l3_code']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{fact_pack['snapshot_hash'][:10]}"
        run_dir = self.run_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        system_prompt = self.prompt_path.read_text(encoding="utf-8")
        request = {
            "run_id": run_id,
            "status": "PREPARED",
            "l3_code": snapshot["l3_code"],
            "input_snapshot_path": str(Path(snapshot_path).resolve()),
            "input_snapshot_hash": fact_pack["snapshot_hash"],
            "analysis_standard_id": ANALYSIS_STANDARD_ID,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }
        user_payload = {
            "instruction": "只使用fact_pack。严格返回output_contract同结构JSON；所有MODEL_DRAFT结论必须引用fact_pack中的evidence_id。没有证据则留空并写入missing_analysis。",
            "output_contract": self._output_contract(fact_pack),
            "fact_pack": fact_pack,
        }
        (run_dir / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (run_dir / "system_prompt.md").write_text(system_prompt, encoding="utf-8")
        (run_dir / "user_payload.json").write_text(json.dumps(user_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return run_dir

    def run(self, run_dir: Path, model: str | None = None) -> Path:
        run_dir = Path(run_dir)
        request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
        api_key, configured_model = load_api_config(self.agent_root)
        if not api_key:
            raise RuntimeError("VNW未配置模型凭证；运行包已保留，可配置后重试或导入外部结果")
        selected_model = model or configured_model
        raw = call_json_model(
            (run_dir / "system_prompt.md").read_text(encoding="utf-8"),
            (run_dir / "user_payload.json").read_text(encoding="utf-8"),
            api_key=api_key,
            model=selected_model,
        )
        response_path = run_dir / "response.raw.json"
        response_path.write_text(raw.strip() + "\n", encoding="utf-8")
        request.update({"status": "MODEL_RETURNED", "model": selected_model, "returned_at": datetime.now(timezone.utc).isoformat()})
        (run_dir / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return response_path

    def validate_and_publish(self, run_dir: Path, response_path: Path | None = None) -> Path:
        run_dir = Path(run_dir)
        request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
        payload = json.loads((run_dir / "user_payload.json").read_text(encoding="utf-8"))
        fact_pack = payload["fact_pack"]
        current_hash = canonical_hash(json.loads(Path(request["input_snapshot_path"]).read_text(encoding="utf-8")))
        if current_hash != request["input_snapshot_hash"]:
            raise ValueError("事实快照已变化，禁止发布基于旧输入的分析")
        response_file = Path(response_path) if response_path else run_dir / "response.raw.json"
        package = _json_from_text(response_file.read_text(encoding="utf-8"))
        package = normalize_model_package(package, fact_pack)
        package["schema_version"] = ANALYSIS_SCHEMA_VERSION
        package["analysis_standard_id"] = ANALYSIS_STANDARD_ID
        package["analysis_status"] = "MODEL_DRAFT"
        package["generation_mode"] = "UNIFIED_MODEL"
        package["model_run"] = {
            "model_name": request.get("model", "external-import"),
            "model_version": request.get("model", "external-import"),
            "prompt_version": ANALYSIS_STANDARD_ID,
            "generated_at": request.get("returned_at") or datetime.now(timezone.utc).isoformat(),
            "input_snapshot_hash": request["input_snapshot_hash"],
        }
        for item in package.get("l4_analysis", []):
            item["analysis_status"] = "MODEL_DRAFT"
        for collection in ("tasks", "priority_drafts", "decision_drafts"):
            for item in package.get(collection, []):
                item["analysis_status"] = "MODEL_DRAFT"
        evidence_ids = {item["evidence_id"] for item in fact_pack["evidence_registry"]}
        l4_codes = {item["l4_code"] for item in fact_pack["l4s"]}
        validate_analysis_package(package, evidence_ids, l4_codes)
        validation = {
            "status": "VALIDATED",
            "l3_code": request["l3_code"],
            "input_snapshot_hash": request["input_snapshot_hash"],
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "l4_count": len(package.get("l4_analysis", [])),
            "task_count": len(package.get("tasks", [])),
            "evidence_ref_count": len({
                ref for item in package.get("l4_analysis", []) for ref in item.get("evidence_refs", [])
            }),
        }
        (run_dir / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.package_root.mkdir(parents=True, exist_ok=True)
        output = self.package_root / f"{request['l3_code']}.model.json"
        if any(self.package_root.glob(f"{request['l3_code']}.*.json")):
            raise FileExistsError(f"{request['l3_code']}已有分析包，禁止静默覆盖")
        output.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        request.update({"status": "PUBLISHED", "published_path": str(output), "published_at": datetime.now(timezone.utc).isoformat()})
        (run_dir / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output
