"""L3统一模型分析契约。

该模块只创建和校验分析包，不调用LLM。所有L3必须先使用同一个事实包生成器，
再由同一分析模型填充PENDING_MODEL字段；没有证据引用的结论禁止进入展示层。
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json


ANALYSIS_SCHEMA_VERSION = "vnw.l3-analysis.v1"
ANALYSIS_STANDARD_ID = "VNW-L3-COM-GOLD-v1.0"
REQUIRED_L4_FIELDS = (
    "deliverable_role",
    "specific_capabilities",
    "ai_reshape",
    "quality_anchor",
    "ai_responsibility",
    "human_responsibility",
    "handoff_triggers",
    "control_gates",
    "data_basis",
    "process_context",
    "risks_limits",
    "current_recommendation",
)


ANALYSIS_INPUT_FIELDS = (
    "l3_code", "l3_name", "source_policy", "blueprint", "l2_capabilities",
    "l4s", "value_nodes", "vn_l4_mappings", "kpi_mappings",
    "value_stream_mappings", "gates", "model_readiness", "evidence_registry",
)


def eligible_analysis_evidence_ids(evidence_registry) -> set[str]:
    """分析模型不得引用工作坊共识或未验证证据；缺失事实仍可作为缺口证据。"""
    items = evidence_registry.values() if isinstance(evidence_registry, dict) else evidence_registry
    return {
        item["evidence_id"] for item in items
        if item.get("evidence_class") != "CONSENSUS"
        and item.get("status") != "UNVERIFIED"
    }


def analysis_input_hash(snapshot: dict) -> str:
    """只对模型允许读取的事实与准入信息做Hash，不包含分析结果和生成时间。"""
    payload = {field: snapshot.get(field) for field in ANALYSIS_INPUT_FIELDS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_analysis_envelope(
    l3_code: str,
    l4s: list[dict],
    blueprint: dict,
    evidence_ids: set[str],
) -> dict:
    """为任意L3创建相同结构的待分析包，并提取有直接证据的蓝图任务。"""
    tasks = []
    valid_l4_codes = {item["l4_code"] for item in l4s}
    rejected_task_sources = []
    sequence_by_l4: dict[str, int] = defaultdict(int)
    for step in blueprint.get("steps", []):
        step_ref = step.get("evidence_ref", "")
        if not step_ref or step_ref not in evidence_ids:
            continue
        activities = step.get("activities") or [step.get("step_name", "")]
        for l4_code in step.get("l4_codes", []):
            if l4_code not in valid_l4_codes:
                rejected_task_sources.append({
                    "step_id": step.get("step_id", ""),
                    "l4_code": l4_code,
                    "evidence_ref": step_ref,
                    "reason": "蓝图L4编码不在当前数据库L3集合",
                })
                continue
            for activity in activities:
                if not activity:
                    continue
                sequence_by_l4[l4_code] += 1
                tasks.append({
                    "task_id": f"{l4_code}-T{sequence_by_l4[l4_code]:02d}",
                    "l4_code": l4_code,
                    "task_name": activity,
                    "source_type": "BLUEPRINT",
                    "sequence_no": step.get("sequence"),
                    "sequence_status": "SOURCE_CONFIRMED",
                    "source_step_id": step.get("step_id", ""),
                    "source_line": step.get("source_line"),
                    "previous_task_ids": [],
                    "next_task_ids": [],
                    "relation_type": "SEQUENTIAL",
                    "evidence_refs": [step_ref],
                    "analysis_status": "FACT_EXTRACTED",
                    "suggested_tier": "",
                    "tier_rationale": "",
                })

    l4_analysis = []
    for l4 in l4s:
        refs = sorted({
            ref for ref in l4.get("evidence_refs", {}).values()
            if ref and ref in evidence_ids
        })
        item = {
            "l4_code": l4["l4_code"],
            "analysis_status": "PENDING_MODEL",
            "evidence_refs": refs,
            "confidence": "UNASSESSED",
        }
        for field in REQUIRED_L4_FIELDS:
            item[field] = [] if field in {
                "specific_capabilities", "handoff_triggers", "control_gates",
                "data_basis", "risks_limits",
            } else ""
        l4_analysis.append(item)

    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_standard_id": ANALYSIS_STANDARD_ID,
        "generation_mode": "EVIDENCE_ONLY_BOOTSTRAP",
        "analysis_status": "PENDING_MODEL",
        "model_run": None,
        "source_scope": {
            "database": "process_analytics",
            "knowledge": "ACTIVE supplemental evidence only",
            "evidence_count": len(evidence_ids),
        },
        "l4_analysis": l4_analysis,
        "tasks": tasks,
        "priority_drafts": [],
        "decision_drafts": [],
        "rejected_task_sources": rejected_task_sources,
        "missing_analysis": [
            "逐L4交付物与具体能力分析",
            "逐任务AI分工分析",
            "逐L4人机协作与控制分析",
            "逐L4优先级四维分析",
            "任务级负责人决策建议",
        ],
    }


def validate_analysis_package(package: dict, evidence_ids: set[str], l4_codes: set[str]) -> None:
    """拒绝无证据、跨L3或结构不一致的模型输出。"""
    if package.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        raise ValueError("分析包schema_version不匹配")
    if package.get("analysis_standard_id") != ANALYSIS_STANDARD_ID:
        raise ValueError("分析标准不一致")

    seen = set()
    for item in package.get("l4_analysis", []):
        code = item.get("l4_code", "")
        if code not in l4_codes:
            raise ValueError(f"分析包含当前L3以外的L4：{code}")
        if code in seen:
            raise ValueError(f"L4分析重复：{code}")
        seen.add(code)
        missing = [field for field in REQUIRED_L4_FIELDS if field not in item]
        if missing:
            raise ValueError(f"{code}缺少分析字段：{','.join(missing)}")
        if item.get("analysis_status") == "MODEL_DRAFT":
            refs = item.get("evidence_refs") or []
            if not refs:
                raise ValueError(f"{code}模型分析没有证据引用")
            unknown = set(refs) - evidence_ids
            if unknown:
                raise ValueError(f"{code}引用未知证据：{sorted(unknown)}")

    if seen != l4_codes:
        raise ValueError(f"L4分析覆盖不完整：{len(seen)}/{len(l4_codes)}")

    for task in package.get("tasks", []):
        if task.get("l4_code") not in l4_codes:
            raise ValueError(f"任务跨出当前L3：{task.get('task_id')}")
        refs = task.get("evidence_refs") or []
        if not refs or set(refs) - evidence_ids:
            raise ValueError(f"任务缺少有效证据：{task.get('task_id')}")
        sequence_status = task.get("sequence_status", "UNCONFIRMED")
        if sequence_status not in {
            "SOURCE_CONFIRMED", "SOURCE_STEP_ONLY", "UNCONFIRMED",
        }:
            raise ValueError(f"任务时序状态不合法：{task.get('task_id')}")
        if sequence_status == "SOURCE_CONFIRMED" and not task.get("sequence_no"):
            raise ValueError(f"任务声明时序已确认但缺少序号：{task.get('task_id')}")
