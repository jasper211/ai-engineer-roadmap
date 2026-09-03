#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · tools/fetch_recorder.py · fetch_run 运行记录（三态写入 / 去重 / 取源）

职责边界：只负责 fetch_run 表的增读（不含 schema 迁移/种子，那归 sqlite_store），
不访问网络、不落盘快照。

对齐任务书 T003 功能要求与 data_contract.md 三态 CHECK 约束：
- 成功（OK）：content_hash 与 snapshot_path 双非空、http_status 非空；
- HTTP 失败（HTTP_ERROR）：content_hash/snapshot_path 为空、http_status 非空；
- 网络失败（NETWORK_ERROR）：三者皆空。
- 幂等：UNIQUE(source_id, content_hash) 对 NULL 不去重，故失败行各记一条；
  成功行按 (source_id, content_hash) 去重，由 find_ok_by_hash 在写前预判。
"""

import sqlite3
from typing import Dict, Optional


def _insert_fetch_run(
    conn: sqlite3.Connection,
    source_id: int,
    final_url,
    http_status,
    content_hash,
    content_length,
    snapshot_path,
    fetch_status: str,
    error_code,
    note,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO fetch_run (
            source_id, final_url, http_status, content_hash,
            content_length, snapshot_path, fetch_status, error_code, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id, final_url, http_status, content_hash,
            content_length, snapshot_path, fetch_status, error_code, note,
        ),
    )
    return cur.lastrowid


def record_ok(
    conn: sqlite3.Connection,
    source_id: int,
    final_url,
    http_status,
    content_hash: str,
    content_length: int,
    snapshot_path: str,
    note=None,
) -> int:
    """写成功抓取行（fetch_status='OK'）。"""
    return _insert_fetch_run(
        conn, source_id, final_url, http_status, content_hash,
        content_length, snapshot_path, "OK", None, note,
    )


def record_http_error(
    conn: sqlite3.Connection,
    source_id: int,
    final_url,
    http_status,
    error_code=None,
    note=None,
) -> int:
    """写 HTTP 失败行（fetch_status='HTTP_ERROR'，http_status 非空、无哈希/快照）。"""
    return _insert_fetch_run(
        conn, source_id, final_url, http_status, None, None, None,
        "HTTP_ERROR", error_code, note,
    )


def record_network_error(
    conn: sqlite3.Connection,
    source_id: int,
    error_code=None,
    note=None,
) -> int:
    """写网络失败行（fetch_status='NETWORK_ERROR'，http_status 为空、无哈希/快照）。"""
    return _insert_fetch_run(
        conn, source_id, None, None, None, None, None,
        "NETWORK_ERROR", error_code, note,
    )


def find_ok_by_hash(
    conn: sqlite3.Connection, source_id: int, content_hash: str,
):
    """查同源同内容是否已有成功行；命中返回 (run_id, content_hash, snapshot_path, content_length)，否则 None。"""
    return conn.execute(
        """
        SELECT run_id, content_hash, snapshot_path, content_length
        FROM fetch_run
        WHERE source_id = ? AND content_hash = ? AND fetch_status = 'OK'
        LIMIT 1
        """,
        (source_id, content_hash),
    ).fetchone()


_KEYS = (
    "source_id", "insurer_code", "disclosure_type",
    "entry_url", "format", "access_status", "requires_browser",
)


def get_source(conn: sqlite3.Connection, source_id: int) -> Optional[Dict]:
    """按 source_id 取数据源行（含抓取门禁所需字段）；不存在返回 None。"""
    row = conn.execute(
        """
        SELECT source_id, insurer_code, disclosure_type, entry_url,
               format, access_status, requires_browser
        FROM data_source
        WHERE source_id = ?
        """,
        (source_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(zip(_KEYS, row))
