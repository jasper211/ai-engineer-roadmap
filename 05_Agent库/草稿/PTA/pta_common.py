#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA 公共工具：任务知识库（task map）加载逻辑，供 S01（任务命名）/S02（执行步骤）共用。

背景：v1.0.0 里"任务 ID → 任务名/执行步骤"是硬编码在 S01/S02 源码里的两份 Python
字典，只认识本项目自己的 9 个任务，且要求维护者同时手改两处、否则会分叉。
本模块把这份知识库外置成 JSON 文件，任何项目都可以放一份自己的 pta_tasks.json，
PTA 就能处理该项目里的任意任务，而不再局限于 AI 工程能力整改项目自身。
"""

import json
from pathlib import Path
from typing import Dict, Optional

DEFAULT_TASK_MAP_FILENAME = "pta_tasks_default.json"


def load_task_map(explicit_path: Optional[str], project_root: Optional[Path], script_dir: Path) -> Dict[str, dict]:
    """
    加载任务知识库，格式统一为 {TASK_ID: {"name": str, "steps": [ {...}, ... ]}}。

    加载优先级：
      1. --task-map 显式指定的文件
      2. project_root 下的 pta_tasks.json（项目自带的任务知识库）
      3. PTA 脚本目录自带的 pta_tasks_default.json（本项目内置任务，兜底/向后兼容）

    找不到任何文件时返回空字典——调用方需要对未知任务优雅降级（如生成"请手动执行"
    的占位步骤），而不是报错，因为"这个项目暂时没有已知任务知识库"是正常状态。
    """
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    if project_root:
        candidates.append(Path(project_root) / "pta_tasks.json")
    candidates.append(script_dir / DEFAULT_TASK_MAP_FILENAME)

    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {k.upper(): v for k, v in data.items()}
            except json.JSONDecodeError as e:
                print(f"[警告] 任务知识库解析失败，跳过: {path} ({e})")
                continue
    return {}
