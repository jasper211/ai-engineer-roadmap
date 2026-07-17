#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：三个项目的候选文件筛选规则（按价值优先级排序，只读扫描）。

2026-07-16 跟 Jasper 对齐：不对三个项目867个候选文档无差别提炼，要按价值
分层、分批处理。EA项目（流程架构项目_jasper）自己已有明确的治理分层（见
其 CLAUDE.md），直接复用这套分层定义优先级；Rw权益项目/AI工程能力整改
项目暂无同等细致的分层，用更简单的关键字黑名单排除，具体分层留待跑出
结果后再跟 Jasper 一起细化。

铁律：本模块只读扫描文件系统（os.walk + 路径过滤），不写入/修改/移动任何
目标项目文件。
"""

import os
from pathlib import Path
from typing import List

from tools.file_diff import CONCEPT_EXTRACTION_EXTENSIONS

# ── EA项目（流程架构项目_jasper）：按治理分层的处理优先级 ──
# 顺序即优先级：00治理 → 03发布成果 → 08任务与跟进 → 01原始材料 → 02过程成果
# （只探入"规则分析（Jasper）"这一个子目录，其余业务维度子目录本阶段跳过）。
# 04-07（Skill库/Agent库/Scripts库/Memory）是代码资产，非知识内容，不在其列。
EA_LAYER_PRIORITY = [
    "00_治理与元模型",
    "03_发布成果-交付物",
    "08_任务与跟进",
    "01_原始材料-外部导入",
    "02_过程成果-工作产出/规则分析（Jasper）",
]

# 通用归档/废弃关键字——即便在优先层内，命中这些关键字的子目录/文件也跳过
# （比如 00/03 层内部也可能有"_归档"这类子目录）。"历史遗留"是2026-07-16
# 跑02层规则分析dry-run时发现的真实漏网案例：`_历史遗留（5月）/`75个文件，
# 名字含义等同于已被取代的旧内容，但此前的黑名单没覆盖这个说法。
ARCHIVE_KEYWORDS = ("归档", "旧版", "废弃", "backup", "bak", "历史遗留")


def _is_archived(name: str) -> bool:
    lname = name.lower()
    return any(kw.lower() in lname for kw in ARCHIVE_KEYWORDS)


def _walk_candidates(base_dir: Path) -> List[Path]:
    """在 base_dir 下递归找候选文件（.md/.docx/.txt），跳过隐藏目录和
    命中归档关键字的目录/文件。返回绝对路径列表，按 os.walk 的自然顺序
    （同一层级内不额外排序，保持文件系统原有的相对次序）。"""
    results = []
    if not base_dir.exists():
        return results
    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not _is_archived(d)]
        for name in filenames:
            if name.startswith("."):
                continue
            if _is_archived(name):
                continue
            ext = Path(name).suffix.lower()
            if ext not in CONCEPT_EXTRACTION_EXTENSIONS:
                continue
            results.append(Path(dirpath) / name)
    return results


def get_ea_candidates(project_root: str) -> List[str]:
    """EA项目专用：按 EA_LAYER_PRIORITY 顺序遍历，返回相对 project_root 的
    路径列表（按优先级分层排序，同层内按文件系统自然顺序）。"""
    root = Path(project_root)
    ordered_relative: List[str] = []
    for layer in EA_LAYER_PRIORITY:
        layer_path = root / layer
        for abs_path in _walk_candidates(layer_path):
            ordered_relative.append(str(abs_path.relative_to(root)))
    return ordered_relative


def get_generic_candidates(project_root: str) -> List[str]:
    """Rw权益项目/AI工程能力整改项目专用：全目录扫描 + 归档关键字黑名单排除，
    暂无分层优先级（同一层级/顺序按文件系统自然顺序）。"""
    root = Path(project_root)
    return [str(p.relative_to(root)) for p in _walk_candidates(root)]


def get_candidates(project_name: str, project_root: str) -> List[str]:
    """按项目名分发到对应的筛选函数。project_name 是 agent.py 里
    PROJECT_ROOTS 映射用的同一套项目名。"""
    if project_name == "EA流程架构项目":
        return get_ea_candidates(project_root)
    return get_generic_candidates(project_root)
