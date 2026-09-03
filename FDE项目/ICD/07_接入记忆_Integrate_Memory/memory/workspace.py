#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · 记忆：专属数据目录与数据库路径推导

职责边界：只负责回答"默认数据库在哪、覆盖路径怎么解析、目录是否就绪"。
不负责建表/种子（那是 tools/sqlite_store 的职责），不负责读配置（那是
tools/config_loader 的职责）。

约束（对齐任务书 T002）：
- 默认数据库固定写入 ICD 专属 `07_接入记忆_Integrate_Memory/data/icd.db`，
  与原始快照目录 `raw_data/` 物理隔离，不写 ICD 以外路径。
- 所有路径从 `Path(__file__)` 推导，不依赖当前工作目录（cwd）。
- 测试必须用 `--db-path` 指向临时目录，不污染默认数据库。
"""

import re
from pathlib import Path
from typing import Optional

# 本文件位于 07_接入记忆_Integrate_Memory/memory/workspace.py
MEMORY_DIR = Path(__file__).resolve().parent        # memory/
NUMBERED_DIR = MEMORY_DIR.parent                     # 07_接入记忆_Integrate_Memory/
DATA_DIR = NUMBERED_DIR / "data"                     # 数据库专属目录（区别于 raw_data/）
DEFAULT_DB_PATH = DATA_DIR / "icd.db"


def default_db_path() -> Path:
    """返回默认数据库绝对路径（data/icd.db），不创建任何目录。"""
    return DEFAULT_DB_PATH


def resolve_db_path(db_path: Optional[str] = None) -> Path:
    """解析数据库路径：显式 --db-path 优先，否则回落到 ICD 专属默认路径。

    显式路径保持为调用方给定值（可以是相对路径，由调用方/测试自行决定语义），
    但这里统一转成绝对路径，避免"从不同 cwd 运行导致相对路径漂移"的坑。
    """
    if db_path:
        return Path(db_path).resolve()
    return DEFAULT_DB_PATH


def ensure_data_dir(db_path: Path) -> Path:
    """确保数据库所在目录存在（只建目录，不建库文件）。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


# ---------------------------------------------------------------------------
# raw_data 快照路径能力（对齐任务书 T003 允许范围）
# ---------------------------------------------------------------------------
RAW_DATA_DIR = NUMBERED_DIR / "raw_data"   # 07_接入记忆_Integrate_Memory/raw_data/
# insurer_code 只能由字母数字下划线连字符组成，杜绝路径穿越（如 "../" 或绝对路径）
_INSURER_DIR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# 快照扩展名白名单（对齐注册表 format 三值）
_SNAPSHOT_EXT_RE = re.compile(r"^[A-Za-z0-9]+$")


def raw_data_root() -> Path:
    """返回 raw_data 根目录（绝对路径），不创建任何目录。"""
    return RAW_DATA_DIR


def resolve_raw_data_root(raw_data_root_override: Optional[str] = None) -> Path:
    """解析 raw_data 根：显式覆盖优先（测试用临时目录），否则回落默认。"""
    if raw_data_root_override:
        return Path(raw_data_root_override).resolve()
    return RAW_DATA_DIR


def snapshot_relpath(
    insurer_code: str, source_id, content_hash: str, ext: str
) -> str:
    """入库用的相对路径：raw_data/{insurer}/{source}/{hash}.{ext}（对齐任务书 T003 功能要求 3）。"""
    return f"raw_data/{insurer_code}/{int(source_id)}/{content_hash}.{ext}"


def snapshot_fullpath(
    raw_data_root_override,
    insurer_code: str,
    source_id,
    content_hash: str,
    ext: str,
) -> Path:
    """快照落盘绝对路径：{root}/{insurer}/{source}/{hash}.{ext}，带防穿越守卫。

    - insurer_code / ext 先做白名单校验，非法即抛 ValueError；
    - 最终路径 resolve 后必须仍位于 raw_data 根之内，否则抛 ValueError。
    """
    root = (Path(raw_data_root_override) if raw_data_root_override else RAW_DATA_DIR).resolve()
    insurer = str(insurer_code)
    if not _INSURER_DIR_RE.fullmatch(insurer):
        raise ValueError(f"非法 insurer_code 用作路径段: {insurer!r}")
    if not _SNAPSHOT_EXT_RE.fullmatch(str(ext)):
        raise ValueError(f"非法快照扩展名: {ext!r}")
    p = (root / insurer / str(int(source_id)) / f"{content_hash}.{ext}").resolve()
    if p != root and root not in p.parents:
        raise ValueError(f"快照路径越界 raw_data 根: {p}")
    return p
