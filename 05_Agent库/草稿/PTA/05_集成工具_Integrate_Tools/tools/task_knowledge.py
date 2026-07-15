#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：任务知识库加载（原 pta_common.py 原样迁移，逻辑不变）

"任务 ID → 任务名/执行步骤"外置成 JSON 文件，任何目标项目都可以放一份自己的
pta_tasks.json，PTA 就能处理该项目里的任意任务，不局限于本项目内置任务。
"""

import json
from pathlib import Path
from typing import Dict, Optional

DEFAULT_TASK_MAP_PATH = Path(__file__).resolve().parent.parent / "pta_tasks_default.json"


def load_task_map(explicit_path: Optional[str], project_root: Optional[Path]) -> Dict[str, dict]:
    """
    加载任务知识库，格式统一为 {TASK_ID: {"name": str, "steps": [ {...}, ... ]}}。

    加载优先级：
      1. explicit_path 显式指定的文件
      2. project_root 下的 pta_tasks.json（项目自带的任务知识库）
      3. PTA 自带的 pta_tasks_default.json（本项目内置任务，兜底/向后兼容）

    找不到任何文件时返回空字典——调用方需要对未知任务优雅降级（如生成"请手动执行"
    的占位步骤），而不是报错，因为"这个项目暂时没有已知任务知识库"是正常状态。
    """
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    if project_root:
        candidates.append(Path(project_root) / "pta_tasks.json")
    candidates.append(DEFAULT_TASK_MAP_PATH)

    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {k.upper(): v for k, v in data.items()}
            except json.JSONDecodeError as e:
                print(f"[警告] 任务知识库解析失败，跳过: {path} ({e})")
                continue
    return {}


def merge_suggested_tasks(project_root: Path, new_entries: Dict[str, dict],
                           owned_prefix: str = "RPT-") -> Dict[str, dict]:
    """把 skills/daily_sensing.py 每日巡检建议的任务，安全合并进目标项目自己的
    pta_tasks.json，供 agent.py 后续按正常执行路径识别（Jasper 打
    "执行 RPT-20260715-01" 时，intent_parsing/execution_planning 完全不用改，
    直接从这份文件里查到对应条目）。

    硬性不变量（不可放松）：只增改 key 以 owned_prefix 开头的条目，绝不 touch
    任何其他 key——不删除、不重排、不修改。这份文件可能混有人工手写的任务，
    daily_sensing 不是它的独占写者。

    写之前把原文件备份成 .bak（跟 memory/workspace.py 里 state.json 的备份
    习惯一致），避免一次写坏整份任务知识库。
    """
    task_map_path = Path(project_root) / "pta_tasks.json"

    bad_keys = [k for k in new_entries if not k.upper().startswith(owned_prefix.upper())]
    if bad_keys:
        raise ValueError(f"merge_suggested_tasks 只允许写 {owned_prefix} 前缀的 key，"
                          f"拒绝写入: {bad_keys}")

    existing: Dict[str, dict] = {}
    if task_map_path.exists():
        try:
            existing = json.loads(task_map_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[警告] 现有 pta_tasks.json 解析失败，本次合并中止，不覆盖: {task_map_path} ({e})")
            return existing

    merged = dict(existing)  # dict 保序：已有 key 的相对顺序不受影响
    merged.update(new_entries)

    if task_map_path.exists():
        task_map_path.replace(task_map_path.with_name(task_map_path.name + ".bak"))
    task_map_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
