#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆：专属工作区隔离 + 状态持久化（原 pta_workspace.py 全部逻辑 + 原
PTA-RUN_主编排器.py 里内嵌的 _load_state/_save_state 合并到这里，统一管理）。

背景：PTA 的"自己的东西"（状态、运行产物、任务登记表）必须和"目标项目的东西"
物理隔离，不能写进目标项目自己的文件夹里，也不能写进 PTA 源码所在的共享仓库里。
这是这次从扁平结构迁移到 agents/skills/tools/memory 结构时唯一必须原样保留、
不能简化的安全约束。
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

WORKSPACE_ROOT = Path(os.environ.get(
    "PTA_WORKSPACE_ROOT",
    # 兜底默认值改用 Path.home() 动态推导，不再写死某台机器的用户名——
    # 之前硬编码的 /Users/zhaoqitrenda.cn/... 是上一台机器的路径，换到新机器
    # （当前用户名不同）后这个目录本来就不存在/不可写，get_project_workspace()
    # 的 mkdir 会直接抛 PermissionError，真实复现过（--pipeline-check 和
    # --daily-scan 都踩到过）。PTA_WORKSPACE_ROOT 环境变量仍然是首选的显式
    # 覆盖方式，这里只是让"没设置环境变量时"的兜底值本身也是可用的，而不是
    # 一个必然失败的死路径。
    str(Path.home() / "Desktop" / "Jasper工作文档（不含EA项目）" / "项目工作区"),
))

EMPTY_STATE = {"version": 1, "current_task": None, "task_history": [], "context": {}, "discovery": None}


def get_project_workspace(project_root: Path) -> Path:
    """返回某个目标项目对应的专属工作区目录，自动创建。
    命名规则：<项目文件夹 basename>工作区（如 Rw权益项目 → Rw权益项目工作区）。"""
    name = Path(project_root).resolve().name
    ws = WORKSPACE_ROOT / f"{name}工作区"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "runs").mkdir(exist_ok=True)
    (ws / "reports").mkdir(exist_ok=True)
    return ws


# ============================================================
# Agent 运行状态（state.json）
# ============================================================

def load_state(workspace: Path) -> dict:
    state_path = workspace / "state.json"
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[警告] 状态文件损坏，已重置: {state_path}")
    return dict(EMPTY_STATE)


def save_state(workspace: Path, state: dict) -> None:
    state_path = workspace / "state.json"
    if state_path.exists():
        state_path.replace(state_path.with_name(state_path.name + ".bak"))
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# 任务分类管理（task_registry.json，供 discover 类功能使用）
# ============================================================

def _task_key(source_file: str, name: str) -> str:
    return hashlib.sha256(f"{source_file}::{name}".encode("utf-8")).hexdigest()[:16]


def load_task_registry(workspace: Path) -> Dict[str, dict]:
    path = workspace / "task_registry.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("tasks", {})
        except json.JSONDecodeError:
            print(f"[警告] 任务登记表损坏，当作空表处理: {path}")
    return {}


def save_task_registry(workspace: Path, registry: Dict[str, dict]) -> None:
    path = workspace / "task_registry.json"
    path.write_text(
        json.dumps({"updated_at": datetime.now().isoformat(), "tasks": registry},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def merge_task_registry(workspace: Path, discovered_tasks: List[dict]) -> Dict[str, dict]:
    """把一批新发现的任务合并进登记表：已存在的 key 只更新 last_seen 和最新字段，
    不产生重复记录；新 key 视为首次发现，标记 reviewed=False 待人工审阅。"""
    registry = load_task_registry(workspace)
    now = datetime.now().isoformat()

    for t in discovered_tasks:
        source_file = t.get("source_file", "")
        name = t.get("name", "")
        key = _task_key(source_file, name)
        parts = Path(source_file).parts
        workstream = parts[0] if len(parts) > 1 else source_file

        if key in registry:
            entry = registry[key]
            entry["last_seen"] = now
            entry["owner"] = t.get("owner", entry.get("owner"))
            entry["status"] = t.get("status", entry.get("status"))
            entry["due_date"] = t.get("due_date", entry.get("due_date"))
            entry["confidence"] = t.get("confidence", entry.get("confidence"))
        else:
            registry[key] = {
                "name": name,
                "owner": t.get("owner"),
                "status": t.get("status"),
                "due_date": t.get("due_date"),
                "evidence": t.get("evidence"),
                "confidence": t.get("confidence"),
                "source_file": source_file,
                "first_seen": now,
                "last_seen": now,
                "classification": {"workstream": workstream, "reviewed": False, "promoted": False},
            }

    save_task_registry(workspace, registry)
    return registry


# ============================================================
# 每日巡检状态（daily_sensing_state.json，供 skills/daily_sensing.py 使用）
# ============================================================

EMPTY_DAILY_SENSING_STATE = {"updated_at": None, "file_hashes": {}, "file_contents": {},
                              "suggested_task_fingerprints": {}}


def load_daily_sensing_state(workspace: Path) -> dict:
    """独立于 discover_state.json（PTA-DISCOVER 自己的增量记录，只覆盖
    .md/.txt/.csv）——每日巡检的扫描范围更广（含代码文件），共用一份文件会让
    两个功能的"已处理"判断互相污染：daily_sensing 扫过但 DISCOVER 自己从没
    看过的文件，会被 DISCOVER 误当成"已处理过"而跳过。"""
    path = workspace / "daily_sensing_state.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[警告] 每日巡检状态文件损坏，已重置: {path}")
    return dict(EMPTY_DAILY_SENSING_STATE)


def save_daily_sensing_state(workspace: Path, state: dict) -> None:
    path = workspace / "daily_sensing_state.json"
    state["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_suggested_task_status(workspace: Path, task_id: str, status: str) -> bool:
    """把某个 daily_sensing 建议任务的指纹状态改成 status（"done"/"dismissed"）。

    这是"执行→回写"闭环缺失的补丁：此前 status 只在建议任务第一次生成时被
    写成 "pending"，之后再没有任何代码路径改过它，导致哪怕任务真的被
    `--execute` 执行完了，daily_sensing 也永远认为它"仍待确认"，天天在简报里
    重复出现（真实问题，不是假设）。

    返回是否找到并修改成功——task_id 不是 daily_sensing 产出的（比如手写的
    P0-02 这类任务）时找不到，返回 False，调用方据此静默跳过，不报错。"""
    state = load_daily_sensing_state(workspace)
    fingerprints = state.get("suggested_task_fingerprints", {})
    for fp in fingerprints.values():
        if fp.get("task_id") == task_id:
            fp["status"] = status
            fp["status_updated_at"] = datetime.now().isoformat()
            save_daily_sensing_state(workspace, state)
            return True
    return False


def update_suggested_task_decision(workspace: Path, task_id: str, updates: dict) -> dict:
    """更新驾驶舱人工决策字段，同时保留 daily_sensing 原有状态机。

    ``status`` 仍只表示任务是否待处理/已完成/已关闭；``decision_status`` 表示
    人对候选任务做出的接收、转交或合并判断。两者分开后，前端扩展不会破坏
    daily_sensing 的自动回执和跨日重提逻辑。
    """
    allowed = {
        "decision_status", "owner", "due_date", "acceptance_criteria",
        "decision_note", "merged_into", "title", "priority",
    }
    safe_updates = {key: value for key, value in updates.items() if key in allowed}
    state = load_daily_sensing_state(workspace)
    fingerprints = state.get("suggested_task_fingerprints", {})
    for fp in fingerprints.values():
        if fp.get("task_id") != task_id:
            continue
        plan_inputs_changed = (
            ("title" in safe_updates and safe_updates["title"] != fp.get("name", "")) or
            ("priority" in safe_updates and safe_updates["priority"] != fp.get("priority", "P2")) or
            ("acceptance_criteria" in safe_updates and
             safe_updates["acceptance_criteria"] != fp.get("acceptance_criteria", ""))
        )
        if "title" in safe_updates:
            fp["name"] = safe_updates.pop("title")
        fp.update(safe_updates)
        fp["decision_updated_at"] = datetime.now().isoformat()
        decision = fp.get("decision_status", "pending_review")
        if decision in ("dismissed", "merged"):
            fp["status"] = "dismissed"
            fp["status_updated_at"] = fp["decision_updated_at"]
        elif decision in ("pending_review", "accepted", "transferred"):
            fp["status"] = "pending"
        if decision != "accepted" or plan_inputs_changed:
            fp.pop("execution", None)
        save_daily_sensing_state(workspace, state)
        return {"found": True, "task": dict(fp)}
    return {"found": False}


def update_suggested_task_execution(workspace: Path, task_id: str, execution: dict) -> dict:
    """保存驾驶舱执行准备状态；真实执行仍只能走 agent.py 的显式授权入口。"""
    state = load_daily_sensing_state(workspace)
    for fp in state.get("suggested_task_fingerprints", {}).values():
        if fp.get("task_id") != task_id:
            continue
        fp["execution"] = execution
        save_daily_sensing_state(workspace, state)
        return {"found": True, "execution": execution}
    return {"found": False}


# ============================================================
# 文档任务发现增量状态（discover_state.json，供 skills/document_task_discovery.py 使用）
# ============================================================

EMPTY_DISCOVER_STATE = {"updated_at": None, "file_hashes": {}}


def load_discover_state(workspace: Path) -> dict:
    """独立于 daily_sensing_state.json——两者的"已处理"判断语义不同（一个是
    "内容变没变过 LLM 语义分析"，一个是"今天扫描有没有变化"），共用一份文件
    会让其中一边的增量状态被另一边污染，PTA-DISCOVER 时代就是按这条原则
    单独开了一份状态文件，这里保留同样的边界。"""
    path = workspace / "discover_state.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[警告] 文档任务发现状态文件损坏，已重置: {path}")
    return dict(EMPTY_DISCOVER_STATE)


def save_discover_state(workspace: Path, state: dict) -> None:
    path = workspace / "discover_state.json"
    state["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# 规则扫描增量状态（rule_scan_state.json，供 skills/rule_based_task_scan.py 使用）
# ============================================================

EMPTY_RULE_SCAN_STATE = {"updated_at": None, "file_hashes": {}, "tasks": []}


def load_rule_scan_state(workspace: Path) -> dict:
    path = workspace / "rule_scan_state.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[警告] 规则扫描状态文件损坏，已重置: {path}")
    return dict(EMPTY_RULE_SCAN_STATE)


def save_rule_scan_state(workspace: Path, state: dict) -> None:
    path = workspace / "rule_scan_state.json"
    state["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# Skill 调用频率日志（skill_usage_log.json）——为未来"哪些skill该优化/该
# 合并/几乎没人用"这类判断提供依据。这是 PTA 自己的运行时数据，不是针对
# 某个目标项目的内容，所以不走 per-project workspace，直接落在 PTA 自己的
# 07_接入记忆_Integrate_Memory/ 下（不进 git，见 .gitignore）。
# ============================================================

SKILL_USAGE_LOG_PATH = Path(__file__).resolve().parent.parent / "skill_usage_log.json"


def log_skill_call(skill_name: str, project_root: Optional[str] = None) -> None:
    """记一条"这个 skill 被调用了一次"——纯追加，不做任何聚合/判断（那是
    仪表盘 API 的事）。读写失败（比如磁盘满）不该让调用方的主流程跟着失败，
    静默忽略，这不是关键路径。

    这个日志从这个函数第一次被调用那天开始累计——此前完全没有任何地方记录
    过"哪个skill被调用了几次"，历史调用量没有留下痕迹，没法补，仪表盘展示
    时需要如实说明这一点，不能暗示是PTA诞生以来的完整历史。"""
    try:
        if SKILL_USAGE_LOG_PATH.exists():
            data = json.loads(SKILL_USAGE_LOG_PATH.read_text(encoding="utf-8"))
        else:
            data = {"calls": []}
        data["calls"].append({
            "skill": skill_name,
            "timestamp": datetime.now().isoformat(),
            "project_root": project_root,
        })
        SKILL_USAGE_LOG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_skill_usage_summary() -> List[dict]:
    """给仪表盘用的聚合视图——按 skill 分组统计调用次数 + 最后调用时间，
    按次数从多到少排序，方便一眼看出"哪个技能用得最多/几乎没人用"。"""
    if not SKILL_USAGE_LOG_PATH.exists():
        return []
    try:
        data = json.loads(SKILL_USAGE_LOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    counts: Dict[str, dict] = {}
    for call in data.get("calls", []):
        skill = call.get("skill", "unknown")
        entry = counts.setdefault(skill, {"skill": skill, "count": 0, "last_called": ""})
        entry["count"] += 1
        if call.get("timestamp", "") > entry["last_called"]:
            entry["last_called"] = call["timestamp"]
    return sorted(counts.values(), key=lambda x: x["count"], reverse=True)
