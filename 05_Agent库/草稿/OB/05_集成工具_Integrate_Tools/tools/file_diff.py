#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：文件快照与增量 diff（移植自 PTA 的 tools/file_diff.py，逻辑不变）。

批量概念笔记提炼需要"哪些文件是新的/变了"这个增量判断，PTA 的 daily_sensing
早就验证过这套机制（sha256 内容哈希 + 按路径 diff），这里原样复用，不重新
发明。跟 PTA 版本的唯一实质差异：这里默认的候选后缀收窄为
`{".md", ".docx", ".txt"}`——概念提炼只关心文本类文档，不像 PTA 需要扫描
更广泛的项目文件类型。

用 os.walk 而不是 rglob——PTA-SCAN 的教训：rglob 没法在遍历时剪掉整个目录，
.git/node_modules 内部文件名大多不以"."开头，会被误当成"文档"扫进来。
"""

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from tools.office_text import OFFICE_EXTRACTORS, extract_office_text

DEFAULT_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
                        ".idea", ".vscode", ".pytest_cache", "_retired_flat_structure"}

DEFAULT_TEXT_ENCODINGS = ("utf-8", "gbk", "gb18030", "big5")

#: 概念笔记提炼只关心文本类文档，跟 PTA 默认扫描更广泛类型不同
CONCEPT_EXTRACTION_EXTENSIONS = {".md", ".docx", ".txt"}


def hash_file(path: Path) -> Optional[str]:
    """sha256 内容哈希；读取失败（权限/已删除等）返回 None，调用方需显式处理。"""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def read_content_truncated(path: Path, max_chars: int, encodings: tuple = DEFAULT_TEXT_ENCODINGS) -> str:
    """读取文件内容用于提炼，按后缀自动分流：.docx 走 tools.office_text 抽取
    （zip+XML 格式不能直接 decode）；其余按常见编码依次尝试解码，不无脑假设
    UTF-8——中国大陆项目里的文本文件常见 GBK 编码。解码后统一 strip 掉开头
    的 BOM 字符（U+FEFF），避免混进后续按内容解析时的第一个字段。"""
    path = Path(path)
    if path.suffix.lower() in OFFICE_EXTRACTORS:
        text = extract_office_text(path)
    else:
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        # 真实复现过：UTF-16（如Windows记事本导出）带BOM的.txt文件，naive
        # UTF-8解码不会报错（NUL字节本身是合法UTF-8单字节码点），却会产出
        # 每个字符间夹着字面NUL控制字符的乱码文本——这类乱码混进LLM输出后，
        # 未转义的控制字符会让json.loads()报'Invalid control character'。
        # BOM检测必须放在8-bit编码列表之前，否则永远走不到这条分支。
        if data[:2] == b"\xff\xfe":
            text = data.decode("utf-16-le")
        elif data[:2] == b"\xfe\xff":
            text = data.decode("utf-16-be")
        else:
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
    {相对路径: {"hash", "size", "modified_time"}}。只读扫描，不修改任何文件。"""
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


def snapshot_files(root: Path, relative_paths: List[str]) -> Dict[str, dict]:
    """只对给定的一批相对路径做快照（哈希+大小+修改时间），不遍历整棵目录树。

    project_filters.py 按分层优先级规则先选出候选文件列表（可能只占项目
    全量文件的一小部分），批量提炼编排不需要再对整个项目目录做一次全量
    walk——直接对已经筛选好的候选文件逐个哈希即可，避免在不相关的文件上
    浪费遍历/哈希开销。"""
    root = Path(root)
    snapshot: Dict[str, dict] = {}
    for rel in relative_paths:
        file_path = root / rel
        file_hash = hash_file(file_path)
        if file_hash is None:
            continue
        try:
            stat = file_path.stat()
        except OSError:
            continue
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
