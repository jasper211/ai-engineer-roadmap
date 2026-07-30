"""统一L3分析执行器：prepare -> run/import -> validate -> publish。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from skills.l3_analysis_contract import (
    ANALYSIS_SCHEMA_VERSION,
    ANALYSIS_STANDARD_ID,
    REQUIRED_L4_FIELDS,
    analysis_input_hash,
    eligible_analysis_evidence_ids,
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
    blueprint_steps = fact_pack.get("blueprint", {}).get("steps", [])
    step_by_evidence = {
        step.get("evidence_ref"): step
        for step in blueprint_steps
        if step.get("evidence_ref")
    }
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
        evidence_refs = task.get("evidence_refs") or analysis.get("evidence_refs", [])
        matched_steps = [
            step_by_evidence[ref] for ref in evidence_refs
            if ref in step_by_evidence
            and code in step_by_evidence[ref].get("l4_codes", [])
        ]
        matched_steps.sort(key=lambda step: step.get("sequence", 10**9))
        source_step = matched_steps[0] if matched_steps else {}
        supplied_status = task.get("sequence_status", "")
        sequence_status = supplied_status if supplied_status in {
            "SOURCE_CONFIRMED", "SOURCE_STEP_ONLY", "UNCONFIRMED",
        } else ("SOURCE_STEP_ONLY" if source_step else "UNCONFIRMED")
        normalized_tasks.append({
            "task_id": task.get("task_id") or f"{code}-M{sequence[code]:02d}",
            "l4_code": code,
            "task_name": task["task_name"],
            "source_type": task.get("source_type") or "MODEL_DECOMPOSITION_FROM_L4",
            "sequence_no": (
                task.get("sequence_no")
                if supplied_status == "SOURCE_CONFIRMED"
                else source_step.get("sequence")
            ),
            "sequence_status": sequence_status,
            "source_step_id": task.get("source_step_id") or source_step.get("step_id", ""),
            "source_line": task.get("source_line") or source_step.get("source_line"),
            "previous_task_ids": task.get("previous_task_ids", []),
            "next_task_ids": task.get("next_task_ids", []),
            "relation_type": task.get("relation_type", "UNCONFIRMED"),
            "evidence_refs": evidence_refs,
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
    raw_control_chain = package.get("control_chain", [])
    package["control_chain"] = [
        item for item in raw_control_chain
        if isinstance(item, dict) and item.get("l4_code") and item.get("label")
    ]
    rejected_controls = len(raw_control_chain) - len(package["control_chain"]) if isinstance(raw_control_chain, list) else 0
    if rejected_controls:
        missing.append(f"控制链缺少L4定位，已拒绝{rejected_controls}条")
    package["missing_analysis"] = list(dict.fromkeys(filter(None, missing)))
    package.setdefault("source_scope", {
        "database": "process_analytics",
        "knowledge": "ACTIVE supplemental evidence only",
        "evidence_count": len(fact_pack["evidence_registry"]),
    })
    package.setdefault("rejected_task_sources", [])
    return package


TASK_FIELDS = {
    "task_id", "l4_code", "task_name", "source_type", "evidence_refs",
    "analysis_status", "suggested_tier", "tier_rationale",
}
DECISION_FIELDS = {
    "priority", "task_ids", "title", "pilot_scope", "human_boundary",
    "evidence_refs", "analysis_status",
}
VALID_TIERS = {"Human", "Aug", "Hybrid", "Auto"}


class L3AnalysisRunner:
    def __init__(self, agent_root: Path):
        self.agent_root = Path(agent_root)
        self.prompt_path = self.agent_root / "08_设计提示词_Design_Prompts/L3统一分析模型_v1.0.md"
        self.run_root = self.agent_root / "07_接入记忆_Integrate_Memory/analysis_runs"
        self.package_root = self.agent_root / "07_接入记忆_Integrate_Memory/analysis_packages"

    def _fact_pack(self, snapshot: dict) -> dict:
        l4s = json.loads(json.dumps(snapshot.get("l4s", []), ensure_ascii=False))
        for item in l4s:
            skill = item.get("skill_feasibility")
            if skill and skill.get("verification_status") == "PROVISIONAL":
                item["skill_feasibility"] = {
                    "verification_status": "PROVISIONAL_NOT_ELIGIBLE",
                    "note": "待书面佐证，不向分析模型提供判断内容",
                }
        return {
            "l3_code": snapshot["l3_code"],
            "l3_name": snapshot["l3_name"],
            "snapshot_hash": analysis_input_hash(snapshot),
            "source_policy": snapshot.get("source_policy", {}),
            "gates": snapshot.get("gates", {}),
            "l2_capabilities": snapshot.get("l2_capabilities", []),
            "l4s": l4s,
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
        readiness = snapshot.get("model_readiness", {})
        if readiness and not readiness.get("model_generation_allowed", False):
            raise ValueError(f"{snapshot['l3_code']}未通过模型准入，不生成分析运行包")
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

    def prepare_repair(self, snapshot_path: Path, package_path: Path) -> Path:
        """准备只补任务与决策的运行包；已发布L4分析与优先级保持冻结。"""
        snapshot_path = Path(snapshot_path)
        package_path = Path(package_path)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        readiness = snapshot.get("model_readiness", {})
        if readiness and not readiness.get("model_generation_allowed", False):
            raise ValueError(f"{snapshot['l3_code']}未通过模型准入，不执行分析修复")
        current_package = json.loads(package_path.read_text(encoding="utf-8"))
        fact_pack = self._fact_pack(snapshot)
        blueprint_task_counts: Counter[str] = Counter()
        for step in fact_pack.get("blueprint", {}).get("steps", []):
            for code in set(step.get("l4_codes", [])):
                blueprint_task_counts[code] += 1
        minimum_task_counts = {
            item["l4_code"]: max(
                1,
                blueprint_task_counts[item["l4_code"]],
                2
                if "复合动作" in str(
                    (item.get("skill_feasibility") or {}).get(
                        "action_singularity", ""
                    )
                )
                else 1,
            )
            for item in fact_pack["l4s"]
        }
        package_hash = canonical_hash(current_package)
        run_id = (
            f"{snapshot['l3_code']}_REPAIR_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
            f"{fact_pack['snapshot_hash'][:10]}"
        )
        run_dir = self.run_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        request = {
            "run_id": run_id,
            "run_type": "MODULE_REPAIR",
            "repair_modules": ["tasks", "decision_drafts"],
            "status": "PREPARED",
            "l3_code": snapshot["l3_code"],
            "input_snapshot_path": str(snapshot_path.resolve()),
            "input_snapshot_hash": fact_pack["snapshot_hash"],
            "current_package_path": str(package_path.resolve()),
            "current_package_hash": package_hash,
            "minimum_task_counts": minimum_task_counts,
            "analysis_standard_id": ANALYSIS_STANDARD_ID,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }
        output_contract = {
            "tasks": [{
                "task_id": "L4-XXX-01-M01",
                "l4_code": "L4-XXX-01",
                "task_name": "具体、可执行的日常工作步骤",
                "source_type": "MODEL_DECOMPOSITION_FROM_L4",
                "sequence_no": 1,
                "sequence_status": "SOURCE_CONFIRMED|SOURCE_STEP_ONLY|UNCONFIRMED",
                "source_step_id": "仅在蓝图存在对应步骤时填写",
                "source_line": 0,
                "previous_task_ids": [],
                "next_task_ids": [],
                "relation_type": "SEQUENTIAL|PARALLEL|BRANCH|RETURN|UNCONFIRMED",
                "evidence_refs": ["当前fact_pack中真实存在的evidence_id"],
                "analysis_status": "MODEL_DRAFT",
                "suggested_tier": "Human|Aug|Hybrid|Auto",
                "tier_rationale": "基于证据说明AI与人的任务边界",
            }],
            "decision_drafts": [{
                "priority": 1,
                "task_ids": ["必须引用上方真实task_id"],
                "title": "负责人需要拍板的具体试点",
                "pilot_scope": "最小试点范围与可观察产出",
                "human_boundary": "不可交给AI的判断、审批或控制门",
                "evidence_refs": ["当前fact_pack中真实存在的evidence_id"],
                "analysis_status": "MODEL_DRAFT",
            }],
        }
        user_payload = {
            "instruction": (
                "这是模块修复，不得重写已冻结的l4_analysis或priority_drafts。"
                "只返回顶层tasks与decision_drafts，不要用output_contract包裹。"
                "每个L4至少拆出1个来自事实包的具体工作任务；任务须覆盖全部L4。"
                "并且每个L4的任务数量不得低于minimum_task_counts；不同蓝图步骤、"
                "失败返回、重新联调，以及知识库标记的复合动作应拆成独立任务。"
                "只有蓝图、SOP或规则明确给出顺序时，sequence_status才可写"
                "SOURCE_CONFIRMED；只能定位到同一蓝图阶段、但阶段内先后不明确时写"
                "SOURCE_STEP_ONLY；没有时序证据时写UNCONFIRMED，不得按task_id猜顺序。"
                "展示文本不得出现具体人员姓名；来源中的姓名必须概括为岗位族、"
                "部门或授权决策角色，但证据引用保持原样以便溯源。"
                "所有evidence_refs必须是fact_pack中真实evidence_id且不能为空。"
                "decision_drafts至少1条，只能引用本次tasks中的task_id。"
                "证据不支持的细节不得补造。"
            ),
            "repair_output_contract": output_contract,
            "minimum_task_counts": minimum_task_counts,
            "frozen_analysis": {
                "l4_analysis": current_package.get("l4_analysis", []),
                "priority_drafts": current_package.get("priority_drafts", []),
            },
            "fact_pack": fact_pack,
        }
        (run_dir / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (run_dir / "system_prompt.md").write_text(self.prompt_path.read_text(encoding="utf-8"), encoding="utf-8")
        (run_dir / "user_payload.json").write_text(json.dumps(user_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return run_dir

    def prepare_l4_refresh(
        self, snapshot_path: Path, package_path: Path, target_l4_codes: list[str]
    ) -> Path:
        """按一小批L4刷新分析，避免大型L3整包输出被模型截断。"""
        snapshot_path = Path(snapshot_path)
        package_path = Path(package_path)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        current_package = json.loads(package_path.read_text(encoding="utf-8"))
        fact_pack = self._fact_pack(snapshot)
        available = {item["l4_code"] for item in fact_pack["l4s"]}
        targets = list(dict.fromkeys(target_l4_codes))
        if not targets or set(targets) - available:
            raise ValueError(f"L4刷新目标为空或不属于当前L3：{targets}")
        if len(targets) > 6:
            raise ValueError("单批最多刷新6个L4，避免模型输出截断")

        target_fact_pack = dict(fact_pack)
        target_fact_pack["l4s"] = [
            item for item in fact_pack["l4s"] if item["l4_code"] in targets
        ]
        skill_evidence_by_l4: dict[str, str] = {}
        for evidence in fact_pack["evidence_registry"]:
            source = evidence.get("source", {})
            source_key = str(source.get("source_key", ""))
            if (
                evidence.get("field_name") == "skill_feasibility"
                and evidence.get("status") == "ACTIVE"
            ):
                code = source_key.split("@", 1)[0]
                if code in targets:
                    skill_evidence_by_l4[code] = evidence["evidence_id"]
        for item in target_fact_pack["l4s"]:
            item["skill_feasibility_evidence_id"] = skill_evidence_by_l4.get(
                item["l4_code"], ""
            )
        blueprint = json.loads(json.dumps(fact_pack.get("blueprint", {}), ensure_ascii=False))
        if isinstance(blueprint.get("steps"), list):
            blueprint["steps"] = [
                step for step in blueprint["steps"]
                if set(step.get("l4_codes", [])) & set(targets)
            ]
        target_fact_pack["blueprint"] = blueprint

        package_hash = canonical_hash(current_package)
        run_id = (
            f"{snapshot['l3_code']}_L4REFRESH_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
            f"{targets[0].replace('L4-', '')}_{len(targets)}"
        )
        run_dir = self.run_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        request = {
            "run_id": run_id,
            "run_type": "L4_BATCH_REFRESH",
            "refresh_modules": ["l4_analysis", "priority_drafts"],
            "target_l4_codes": targets,
            "status": "PREPARED",
            "l3_code": snapshot["l3_code"],
            "input_snapshot_path": str(snapshot_path.resolve()),
            "input_snapshot_hash": fact_pack["snapshot_hash"],
            "current_package_path": str(package_path.resolve()),
            "current_package_hash": package_hash,
            "publish_package_path": str(
                (self.package_root / f"{snapshot['l3_code']}.model.json").resolve()
            ),
            "analysis_standard_id": ANALYSIS_STANDARD_ID,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }
        contract = self._output_contract(target_fact_pack)["l4_analysis"]
        user_payload = {
            "instruction": (
                "这是L4分批刷新，只返回顶层l4_analysis数组，不得返回或改写tasks、"
                "decision_drafts、control_chain。必须且只能覆盖target_l4_codes。"
                "逐项融合数据库D1-D6、AI协作Tier、已核验Skill封装可行性和蓝图背景；"
                "Skill等级与AI协作Tier是两个独立判断，不得互相替代。"
                "若L4提供skill_feasibility_evidence_id，evidence_refs必须包含该编号。"
                "所有结论必须引用eligible事实证据；证据不足则留空或明确限制，不得补造。"
            ),
            "target_l4_codes": targets,
            "refresh_output_contract": {"l4_analysis": contract},
            "current_l4_analysis": [
                item for item in current_package.get("l4_analysis", [])
                if item.get("l4_code") in targets
            ],
            "fact_pack": target_fact_pack,
        }
        (run_dir / "request.json").write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (run_dir / "system_prompt.md").write_text(
            self.prompt_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (run_dir / "user_payload.json").write_text(
            json.dumps(user_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
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
        current_hash = analysis_input_hash(json.loads(Path(request["input_snapshot_path"]).read_text(encoding="utf-8")))
        if current_hash != request["input_snapshot_hash"]:
            raise ValueError("事实快照已变化，禁止发布基于旧输入的分析")
        response_file = Path(response_path) if response_path else run_dir / "response.raw.json"
        if request.get("run_type") == "MODULE_REPAIR":
            return self._validate_and_merge_repair(run_dir, request, fact_pack, response_file)
        if request.get("run_type") == "L4_BATCH_REFRESH":
            return self._validate_and_merge_l4_refresh(
                run_dir, request, fact_pack, response_file
            )
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
        evidence_ids = eligible_analysis_evidence_ids(fact_pack["evidence_registry"])
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
        replaced_package = None
        if output.exists():
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            replaced_package = output.with_name(f"{output.name}.before-refresh.{timestamp}.bak")
            shutil.copy2(output, replaced_package)
        output.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        request.update({
            "status": "PUBLISHED",
            "published_path": str(output),
            "replaced_package_backup": str(replaced_package) if replaced_package else "",
            "published_at": datetime.now(timezone.utc).isoformat(),
        })
        (run_dir / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output

    def _validate_and_merge_l4_refresh(
        self, run_dir: Path, request: dict, fact_pack: dict, response_file: Path
    ) -> Path:
        package_path = Path(request["current_package_path"])
        output_path = Path(request.get("publish_package_path", package_path))
        current_package = json.loads(package_path.read_text(encoding="utf-8"))
        if canonical_hash(current_package) != request["current_package_hash"]:
            raise ValueError("现有分析包已变化，禁止合并基于旧版本的L4刷新")
        refreshed = _json_from_text(response_file.read_text(encoding="utf-8"))
        items = refreshed.get("l4_analysis")
        if not isinstance(items, list):
            raise ValueError("L4分批刷新必须返回l4_analysis数组")
        targets = set(request["target_l4_codes"])
        returned = {
            item.get("l4_code") for item in items if isinstance(item, dict)
        }
        if returned != targets or len(items) != len(targets):
            raise ValueError(
                f"L4分批刷新范围不一致：期望{sorted(targets)}，实际{sorted(returned)}"
            )
        evidence_ids = eligible_analysis_evidence_ids(fact_pack["evidence_registry"])
        skill_evidence_by_l4 = {
            item["l4_code"]: item.get("skill_feasibility_evidence_id", "")
            for item in fact_pack["l4s"]
        }
        rejected_refs = []
        for item in items:
            missing_fields = set(REQUIRED_L4_FIELDS) - set(item)
            if missing_fields:
                raise ValueError(
                    f"{item.get('l4_code')}刷新字段不完整：{sorted(missing_fields)}"
                )
            refs = item.get("evidence_refs") or []
            valid_refs = [ref for ref in refs if ref in evidence_ids]
            invalid_refs = [ref for ref in refs if ref not in evidence_ids]
            if not valid_refs:
                raise ValueError(f"{item.get('l4_code')}刷新缺少有效证据")
            required_skill_ref = skill_evidence_by_l4.get(item.get("l4_code"), "")
            if required_skill_ref and required_skill_ref not in valid_refs:
                raise ValueError(
                    f"{item.get('l4_code')}刷新未引用对应Skill可行性证据"
                )
            if invalid_refs:
                rejected_refs.extend({
                    "l4_code": item.get("l4_code"),
                    "evidence_ref": ref,
                    "reason": "模型返回的引用不在当前可用证据注册表，合并时拒绝",
                    "run_id": request["run_id"],
                } for ref in invalid_refs)
            item["evidence_refs"] = valid_refs
            item["analysis_status"] = "MODEL_DRAFT"

        replacement = {item["l4_code"]: item for item in items}
        merged = dict(current_package)
        merged["l4_analysis"] = [
            replacement.get(item.get("l4_code"), item)
            for item in current_package.get("l4_analysis", [])
        ]
        old_priority = {
            item.get("l4_code"): item
            for item in current_package.get("priority_drafts", [])
        }
        for item in items:
            old_priority[item["l4_code"]] = {
                "l4_code": item["l4_code"],
                "quadrant": (
                    item.get("quadrant")
                    if item.get("quadrant") in {"q1", "q2", "q3", "q4"}
                    else "unclassified"
                ),
                "data_basis": item.get("data_basis", []),
                "process_context": item.get("process_context", ""),
                "risks_limits": item.get("risks_limits", []),
                "current_recommendation": item.get("current_recommendation", ""),
                "evidence_refs": item.get("evidence_refs", []),
                "analysis_status": "MODEL_DRAFT",
            }
        merged["priority_drafts"] = [
            old_priority[item["l4_code"]]
            for item in merged["l4_analysis"]
            if item["l4_code"] in old_priority
        ]
        merged.setdefault("refresh_history", []).append({
            "run_id": request["run_id"],
            "modules": request["refresh_modules"],
            "target_l4_codes": sorted(targets),
            "model": request.get("model", "external-import"),
            "refreshed_at": request.get("returned_at")
            or datetime.now(timezone.utc).isoformat(),
            "input_snapshot_hash": request["input_snapshot_hash"],
            "previous_package_hash": request["current_package_hash"],
        })
        if rejected_refs:
            merged.setdefault("rejected_evidence_refs", []).extend(rejected_refs)
        current_snapshot = json.loads(
            Path(request["input_snapshot_path"]).read_text(encoding="utf-8")
        )
        all_l4_codes = {
            item["l4_code"] for item in current_snapshot.get("l4s", [])
        }
        validate_analysis_package(merged, evidence_ids, all_l4_codes)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = None
        if output_path.exists():
            backup = output_path.with_name(
                f"{output_path.name}.before-l4-refresh.{timestamp}.bak"
            )
            shutil.copy2(output_path, backup)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        validation = {
            "status": "VALIDATED_AND_MERGED",
            "run_type": "L4_BATCH_REFRESH",
            "l3_code": request["l3_code"],
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "target_l4_codes": sorted(targets),
            "preserved_modules": ["tasks", "decision_drafts", "control_chain"],
            "refreshed_modules": request["refresh_modules"],
            "backup_path": str(backup) if backup else "",
            "rejected_evidence_refs": rejected_refs,
        }
        (run_dir / "validation.json").write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        request.update({
            "status": "PUBLISHED",
            "published_path": str(output_path),
            "backup_path": str(backup) if backup else "",
            "published_at": datetime.now(timezone.utc).isoformat(),
        })
        (run_dir / "request.json").write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return output_path

    def _validate_and_merge_repair(
        self, run_dir: Path, request: dict, fact_pack: dict, response_file: Path
    ) -> Path:
        package_path = Path(request["current_package_path"])
        current_package = json.loads(package_path.read_text(encoding="utf-8"))
        if canonical_hash(current_package) != request["current_package_hash"]:
            raise ValueError("现有分析包已变化，禁止合并基于旧版本的修复")

        repaired = _json_from_text(response_file.read_text(encoding="utf-8"))
        tasks = repaired.get("tasks")
        decisions = repaired.get("decision_drafts")
        if not isinstance(tasks, list) or not isinstance(decisions, list):
            raise ValueError("修复输出必须包含tasks与decision_drafts数组")

        evidence_ids = eligible_analysis_evidence_ids(fact_pack["evidence_registry"])
        l4_codes = {item["l4_code"] for item in fact_pack["l4s"]}
        task_ids: set[str] = set()
        covered_l4s: set[str] = set()
        for task in tasks:
            if not isinstance(task, dict) or not TASK_FIELDS <= set(task):
                raise ValueError("修复任务字段不完整")
            if task["l4_code"] not in l4_codes:
                raise ValueError(f"修复任务跨出当前L3：{task.get('task_id')}")
            if not task["task_id"] or task["task_id"] in task_ids:
                raise ValueError(f"修复任务ID为空或重复：{task.get('task_id')}")
            refs = task.get("evidence_refs") or []
            if not refs or set(refs) - evidence_ids:
                raise ValueError(f"修复任务缺少有效证据：{task['task_id']}")
            if task.get("suggested_tier") not in VALID_TIERS:
                raise ValueError(f"修复任务Tier不合法：{task['task_id']}")
            if not task.get("task_name") or not task.get("tier_rationale"):
                raise ValueError(f"修复任务内容不完整：{task['task_id']}")
            task["analysis_status"] = "MODEL_DRAFT"
            task_ids.add(task["task_id"])
            covered_l4s.add(task["l4_code"])
        if covered_l4s != l4_codes:
            missing = sorted(l4_codes - covered_l4s)
            raise ValueError(f"修复任务未覆盖全部L4：{missing}")
        actual_task_counts = Counter(task["l4_code"] for task in tasks)
        below_minimum = {
            code: {"expected": minimum, "actual": actual_task_counts[code]}
            for code, minimum in request.get("minimum_task_counts", {}).items()
            if actual_task_counts[code] < minimum
        }
        if below_minimum:
            raise ValueError(f"修复任务未达到蓝图步骤颗粒度：{below_minimum}")

        if not decisions:
            raise ValueError("修复输出至少需要1条负责人决策")
        for decision in decisions:
            if not isinstance(decision, dict) or not DECISION_FIELDS <= set(decision):
                raise ValueError("负责人决策字段不完整")
            if not decision.get("task_ids") or not set(decision["task_ids"]) <= task_ids:
                raise ValueError(f"负责人决策引用未知任务：{decision.get('title')}")
            refs = decision.get("evidence_refs") or []
            if not refs or set(refs) - evidence_ids:
                raise ValueError(f"负责人决策缺少有效证据：{decision.get('title')}")
            if not all(decision.get(field) for field in ("title", "pilot_scope", "human_boundary")):
                raise ValueError("负责人决策内容不完整")
            decision["analysis_status"] = "MODEL_DRAFT"

        merged = dict(current_package)
        merged["tasks"] = tasks
        merged["decision_drafts"] = decisions
        # 只清理由本次修复已解决的缺失项，其他数据不足提示原样保留。
        merged["missing_analysis"] = [
            item for item in current_package.get("missing_analysis", [])
            if not any(marker in str(item) for marker in (
                "负责人决策草稿结构不合格",
                "模型未返回可校验的逐任务拆分",
                "逐任务分析缺失",
                "任务级负责人决策建议",
            ))
        ]
        merged.setdefault("repair_history", []).append({
            "run_id": request["run_id"],
            "modules": request["repair_modules"],
            "model": request.get("model", "external-import"),
            "repaired_at": request.get("returned_at") or datetime.now(timezone.utc).isoformat(),
            "input_snapshot_hash": request["input_snapshot_hash"],
            "previous_package_hash": request["current_package_hash"],
            "task_count": len(tasks),
            "decision_count": len(decisions),
        })
        validate_analysis_package(merged, evidence_ids, l4_codes)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = package_path.with_name(f"{package_path.name}.before-repair.{timestamp}.bak")
        shutil.copy2(package_path, backup)
        package_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = {
            "status": "VALIDATED_AND_MERGED",
            "run_type": "MODULE_REPAIR",
            "l3_code": request["l3_code"],
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "preserved_modules": ["l4_analysis", "priority_drafts"],
            "repaired_modules": request["repair_modules"],
            "l4_coverage": sorted(covered_l4s),
            "task_count": len(tasks),
            "decision_count": len(decisions),
            "backup_path": str(backup),
        }
        (run_dir / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        request.update({
            "status": "PUBLISHED",
            "published_path": str(package_path),
            "backup_path": str(backup),
            "published_at": datetime.now(timezone.utc).isoformat(),
        })
        (run_dir / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return package_path
