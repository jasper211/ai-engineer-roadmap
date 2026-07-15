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
    "/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/项目工作区",
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
