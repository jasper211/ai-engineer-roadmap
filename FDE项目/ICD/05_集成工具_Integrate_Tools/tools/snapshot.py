#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · tools/snapshot.py · 原始字节快照（SHA-256 与原子落盘）

职责边界：只负责"算哈希 + 把字节原子写盘"，不访问网络、不写库、不解析内容。

对齐任务书 T003 功能要求：
- 原始字节读取后计算 SHA-256；
- 写同目录临时文件后 os.replace 到最终路径（原子重命名）；
- 任何失败清理临时文件，绝不留下半文件（`.tmp-*` 残留）。
"""

import hashlib
import os
import uuid
from pathlib import Path

# format → 快照扩展名白名单（未知/为空回落 .bin，但可抓取源 format 必在此三值内）
EXT_BY_FORMAT = {"json": "json", "html": "html", "pdf": "pdf"}


def sha256_hex(data: bytes) -> str:
    """原始字节的 SHA-256 十六进制（64 位小写）。"""
    return hashlib.sha256(data).hexdigest()


def ext_for_format(fmt) -> str:
    """按注册表 format 字段取快照扩展名，未知回落 .bin。"""
    return EXT_BY_FORMAT.get((fmt or "").lower(), "bin")


def write_atomic(final_path: Path, data: bytes) -> None:
    """把 data 写到 final_path：先写同目录临时文件，flush+fsync 后 os.replace 原子改名。

    - 临时文件与最终文件同目录，保证 os.replace 同一文件系统内原子替换；
    - 任一步失败 → 尽力删除临时文件并原样抛出，不留半文件。
    """
    final_path = Path(final_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = final_path.parent / f".tmp-{uuid.uuid4().hex}.bin"
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, final_path)
    except BaseException:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
