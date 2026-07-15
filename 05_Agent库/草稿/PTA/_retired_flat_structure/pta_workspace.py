#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA 专属工作区：所有子 Agent（S01-S05/PTA-RUN/PTA-DISCOVER/PTA-SCAN）读写自己的
状态、快照、运行产物、任务登记表时，都应该落在这里，而不是目标项目自己的文件夹里，
也不是 PTA 自己所在的这个共享 git 仓库里。

背景：PTA-DISCOVER/PTA-SCAN 曾经默认把状态文件写进目标项目自己的目录（违反"不改
任何项目文件"的原则）；PTA-S04 的 `git add .` 曾经把一份跟 PTA 无关、正在另一个
会话里编写的文件意外提交推送到共享仓库。两者的根因是同一件事：PTA 的"自己的东西"
和"项目的东西"没有物理隔离。这个模块就是那道隔离层。
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
# 任务分类管理（task_registry.json）
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
    不产生重复记录；新 key 视为首次发现，标记 reviewed=False 待人工审阅。
    workstream 分类规则：取 source_file 的第一级子目录名（没有子目录就用文件名本身）。
    返回合并后的完整登记表。"""
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
