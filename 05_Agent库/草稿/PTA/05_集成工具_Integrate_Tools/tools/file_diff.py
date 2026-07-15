#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：文件快照与增量 diff（从 PTA-SCAN_智能项目扫描器_v2.py 抽取的通用原语）

只抽取"哈希全部文件→存快照→diff出新增/变更/删除"这一个机制，不 import 整个
PTA-SCAN（那个脚本是围绕 CLI/报告生成设计的，不是库）。用 os.walk 而不是
rglob——PTA-SCAN 的代码注释里记录过实测教训：rglob 没法在遍历时剪掉整个
目录，.git/node_modules 内部文件名大多不以 "." 开头，会被误当成"文档"扫进来；
这里沿用同一条经验教训，不是重踩一遍坑。

哈希算法用 sha256（不是 PTA-SCAN 用的 md5）——sha256 已经是本项目 tools/
task_knowledge.py 之外、_task_key 一类地方在用的约定，保持一致。
"""

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from difflib import unified_diff
from pathlib import Path
from typing import Dict, List, Optional, Set

from tools.office_text import OFFICE_EXTRACTORS, extract_office_text

DEFAULT_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".pta_runs", ".venv", "venv",
                        ".idea", ".vscode", ".pytest_cache"}

DEFAULT_TEXT_ENCODINGS = ("utf-8", "gbk", "gb18030", "big5")


def hash_file(path: Path) -> Optional[str]:
    """sha256 内容哈希；读取失败（权限/已删除等）返回 None，调用方需显式处理，
    不像 PTA-SCAN 原版那样吞掉异常悄悄返回空字符串。"""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def read_content_truncated(path: Path, max_chars: int, encodings: tuple = DEFAULT_TEXT_ENCODINGS) -> str:
    """读取文件内容用于 diff/LLM 分析，按后缀自动分流：.docx/.xlsx 走
    tools.office_text 抽取（原始格式是 zip+XML，不能直接 decode）；其余按
    常见编码依次尝试解码，而不是无脑假设 UTF-8——中国大陆项目里的 CSV/txt
    经常是 Windows/Excel 导出的 GBK 编码，errors='ignore' 硬读会把中文读成
    乱码（PTA-DISCOVER 早期版本真实踩过这个坑）。

    这是 skills/daily_sensing.py、skills/document_task_discovery.py、
    skills/rule_based_task_scan.py、skills/project_intelligence.py 共用的
    同一份实现——迁移前这几边（含退役前的 PTA-DISCOVER/PTA-SCAN/PTA-INTEL-RW
    脚本）各自维护了一份几乎相同的编码兜底逻辑，这里收敛成一份。

    plain "utf-8" 编码能成功解码带 BOM 的文件，但会在开头留一个字面上的
    U+FEFF 字符——如果这份内容后面要按列名做 CSV/表格解析（rule_based_task_scan、
    project_intelligence 的 Rw 台账解析都是这样），这个字符会混进第一个字段名
    里（`﻿track_id` 而不是 `track_id`），导致按列名查找全部落空。原
    PTA-SCAN/PTA-INTEL-RW 脚本都在编码候选列表里显式试过 "utf-8-sig" 来处理
    这个问题；这里改成解码后统一 strip 掉开头的 BOM 字符，不需要再单独试
    一次 "utf-8-sig" 编码。"""
    path = Path(path)
    if path.suffix.lower() in OFFICE_EXTRACTORS:
        text = extract_office_text(path)
    else:
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        for enc in encodings:
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = data.decode("utf-8", errors="ignore")
        text = text.lstrip("﻿")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[内容已截断]"
    return text


def snapshot_dir(root: Path, extensions: Optional[Set[str]] = None,
                  exclude_dirs: Set[str] = None, exclude_files: Optional[Set[str]] = None) -> Dict[str, dict]:
    """扫描 root 下所有文件（可用 extensions 限定后缀，不传则不限），返回
    {相对路径: {"hash", "size", "modified_time"}}。

    exclude_files 按文件名（不含路径）精确匹配排除——用于像 daily_sensing 那样
    "这个文件是我自己写的输出产物，不该被当成项目里的变更内容"这种场景（例如
    pta_tasks.json：daily_sensing 自己会往里写建议任务，如果不排除，下次扫描
    会把这些刚写进去的建议任务当成"新变化"重新分析一遍，分析出一堆"关于任务的
    任务"，是真实复现过的自我递归 bug）。默认不排除任何文件名，行为不变，
    不影响 dir_scan.py 等其他调用方。"""
    root = Path(root)
    exclude_dirs = exclude_dirs if exclude_dirs is not None else DEFAULT_EXCLUDE_DIRS
    exclude_files = exclude_files or set()
    snapshot: Dict[str, dict] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs and not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            if name in exclude_files:
                continue
            file_path = Path(dirpath) / name
            ext = file_path.suffix.lower()
            if extensions is not None and ext not in extensions:
                continue
            file_hash = hash_file(file_path)
            if file_hash is None:
                continue
            try:
                stat = file_path.stat()
            except OSError:
                continue
            rel = str(file_path.relative_to(root))
            snapshot[rel] = {
                "hash": file_hash,
                "size": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }

    return snapshot


@dataclass
class DiffResult:
    added: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.added and not self.changed and not self.removed


def diff_snapshots(old: Dict[str, dict], new: Dict[str, dict]) -> DiffResult:
    """按路径判断新增/删除，按 hash 判断是否变更（路径存在但 hash 不同）。"""
    added, changed, unchanged = [], [], []
    for path, info in new.items():
        if path not in old:
            added.append(path)
        elif old[path].get("hash") != info.get("hash"):
            changed.append(path)
        else:
            unchanged.append(path)
    removed = [path for path in old if path not in new]
    return DiffResult(added=sorted(added), changed=sorted(changed),
                       removed=sorted(removed), unchanged=sorted(unchanged))


def unified_diff_text(old_content: str, new_content: str, max_lines: int = 50) -> str:
    """生成人可读的 unified diff 片段，超过 max_lines 截断（控制喂给 LLM 的长度）。"""
    lines = list(unified_diff(
        old_content.splitlines(), new_content.splitlines(),
        fromfile="之前版本", tofile="当前版本", lineterm="",
    ))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... (截断，共 {len(lines)} 行差异)"]
    return "\n".join(lines)
