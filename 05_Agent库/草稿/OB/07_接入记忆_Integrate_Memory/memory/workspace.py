#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆：OB 自己的状态持久化——批量概念笔记提炼的增量扫描快照。

隔离原则同 PTA 的 memory/workspace.py：OB 自己的运行产物（每个项目的文件
扫描快照）必须物理隔离于三个目标项目自身的文件夹（呼应"OB 对项目文件只读
不修改不移动"的铁律）和 vault 本身（vault 只放最终的知识原子，不放扫描
状态这类运行时数据）。这是 OB 第一次真正用到 memory/ 这个包——巡检/检索
两条能力线目前都是无状态的，不需要跨会话持久化。
"""

import json
import os
from pathlib import Path

WORKSPACE_ROOT = Path(os.environ.get(
    "OB_WORKSPACE_ROOT",
    "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/项目工作区/OB",
))


def _snapshot_path(project_name: str) -> Path:
    return WORKSPACE_ROOT / project_name / "extraction_snapshot.json"


def load_extraction_snapshot(project_name: str) -> dict:
    """加载某个项目上一次批量提炼的文件快照（相对路径 -> {hash, size, modified_time}）。
    不存在/损坏时返回空字典，等价于"第一次跑，所有候选文件都算新增"。"""
    path = _snapshot_path(project_name)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_extraction_snapshot(project_name: str, snapshot: dict):
    """保存某个项目最新的文件快照，供下次增量比对使用。"""
    path = _snapshot_path(project_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)


def atom_embeddings_dir(project_name: str) -> str:
    """原子语义去重缓存（tools/atom_embeddings.py）的存放目录——同样落在
    OB 自己的工作区，跟提炼快照物理相邻但文件分开（各自独立读写，互不影响）。"""
    d = WORKSPACE_ROOT / project_name
    d.mkdir(parents=True, exist_ok=True)
    return str(d)
