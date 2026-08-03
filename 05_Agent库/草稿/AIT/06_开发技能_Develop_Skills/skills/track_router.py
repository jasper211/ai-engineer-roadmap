"""AIT L3-AIT-02 轨道判定器。

按`流程设计.md`三节的优先级逻辑，把VNW决策确认记录里的任务分到机器规则轨道
或人的规则轨道，Aug/Hybrid额外标注强制介入点的关卡形态。只读VNW的
model_snapshots和决策确认记录，不修改两者，只产出判定结果。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GATE_TYPE_BY_TIER = {
    "Aug": "固定关卡",
    "Hybrid": "条件关卡",
}


def load_decisions(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_snapshot(path: Path) -> dict:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    manifest_path = path.parent / (path.stem + ".manifest.json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshot["snapshot_hash"] = manifest.get("snapshot_hash", "")
    return snapshot


def route_task(task: dict, l4_lookup: dict[str, dict]) -> dict:
    """单条任务的轨道判定。task须含task_id/l4_code/suggested_tier。"""
    l4 = l4_lookup.get(task["l4_code"], {})
    skill = l4.get("skill_feasibility") or {}
    funds_gate = bool(skill.get("funds_safety_hard_gate"))
    physical = bool(skill.get("physical_execution"))
    tier = task.get("suggested_tier", "")

    if funds_gate or physical:
        return {
            "track": "人的规则轨道",
            "gate_type": None,
            "gate_reason": "资金安全强制关卡" if funds_gate else "物理执行类",
            "build_agent": False,
        }
    if tier == "Auto":
        return {"track": "机器规则轨道", "gate_type": None, "gate_reason": None, "build_agent": True}
    if tier in GATE_TYPE_BY_TIER:
        return {
            "track": "机器规则轨道",
            "gate_type": GATE_TYPE_BY_TIER[tier],
            "gate_reason": f"建议Tier={tier}，AI化设计需强制附带介入点设计",
            "build_agent": True,
        }
    if tier == "Human":
        return {"track": "人的规则轨道", "gate_type": None, "gate_reason": "建议Tier=Human", "build_agent": False}
    return {"track": "待定", "gate_type": None, "gate_reason": f"未知Tier值：{tier!r}", "build_agent": False}


def build_track_assignments(decisions: dict, snapshot: dict) -> dict:
    l3_code = decisions["l3_code"]
    task_lookup = {t["task_id"]: t for t in snapshot["analysis"]["tasks"]}
    l4_lookup = {l4["l4_code"]: l4 for l4 in snapshot["l4s"]}

    decision_results = []
    for decision in decisions["decisions"]:
        task_routes = []
        for task_id in decision["task_ids"]:
            task = task_lookup.get(task_id)
            if task is None:
                task_routes.append({
                    "task_id": task_id,
                    "error": "在model_snapshots的analysis.tasks里找不到这个task_id，可能是快照已重新生成、编号变了",
                })
                continue
            routing = route_task(task, l4_lookup)
            task_routes.append({
                "task_id": task_id,
                "l4_code": task["l4_code"],
                "task_name": task.get("task_name", ""),
                "suggested_tier": task.get("suggested_tier", ""),
                **routing,
            })
        decision_results.append({
            "decision_id": decision["decision_id"],
            "task_name": decision["task_name"],
            "pilot_scope": decision["pilot_scope"],
            "human_boundary": decision["human_boundary"],
            "selected_by": decision["selected_by"],
            "selected_at": decision["selected_at"],
            "tasks": task_routes,
        })

    return {
        "schema_version": "ait.track-assignment.v1",
        "l3_code": l3_code,
        "source_decisions": decisions["source"],
        "source_snapshot_hash": snapshot.get("snapshot_hash", ""),
        "decisions": decision_results,
    }


def build_and_write(decisions_path: Path, snapshot_path: Path, output_dir: Path) -> Path:
    decisions = load_decisions(decisions_path)
    snapshot = load_snapshot(snapshot_path)
    result = build_track_assignments(decisions, snapshot)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{result['l3_code']}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path
