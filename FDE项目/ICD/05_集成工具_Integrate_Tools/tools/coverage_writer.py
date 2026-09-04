#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · tools/coverage_writer.py · coverage_status 确定性 upsert（L3-ICD-06 覆盖闭环）

职责边界：只负责把「险企 × 披露类型」的最新覆盖状态写入/更新 coverage_status 表，
不抓取、不解析、不判定业务结果（判定逻辑在 skills/run_all.py）。不访问网络。

对齐任务书 T009 功能要求 4 与 data_contract.md 3.10：
- 状态取值限定 FULL / PARTIAL / MISSING / BLOCKED / UNVERIFIED。
- 唯一键 UNIQUE(insurer_code, disclosure_type)，每次运行 UPSERT 同一自然键。
- last_attempt_at 每次尝试即更新；last_success_at / last_success_run_id 仅本次成功
  （FULL / PARTIAL）时更新，失败保留上一次成功时间（读旧行回填，不擦除历史成功）。
- last_error_code / last_error_message 失败时写入、成功时清空（NULL）。
- 不自行 commit：事务边界由调用方（run_all 聚合阶段）控制。
"""

import sqlite3
from typing import Optional

VALID_COVERAGE_STATUS = {"FULL", "PARTIAL", "MISSING", "BLOCKED", "UNVERIFIED"}

_COVERAGE_UPSERT_SQL = """
INSERT INTO coverage_status (
    insurer_code, disclosure_type, coverage_status,
    last_success_run_id, last_checked_at, last_attempt_at,
    last_success_at, last_error_code, last_error_message
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(insurer_code, disclosure_type) DO UPDATE SET
    coverage_status = excluded.coverage_status,
    last_success_run_id = excluded.last_success_run_id,
    last_checked_at = excluded.last_checked_at,
    last_attempt_at = excluded.last_attempt_at,
    last_success_at = excluded.last_success_at,
    last_error_code = excluded.last_error_code,
    last_error_message = excluded.last_error_message
"""


def _is_success_status(status: str) -> bool:
    """FULL / PARTIAL 表示「本次有至少一个源成功覆盖」；其余为无成功。"""
    return status in ("FULL", "PARTIAL")


def upsert_coverage(
    conn: sqlite3.Connection,
    insurer_code: str,
    disclosure_type: str,
    coverage_status: str,
    *,
    last_success_run_id: Optional[int] = None,
    last_attempt_at: Optional[str] = None,
    last_success_at: Optional[str] = None,
    last_error_code: Optional[str] = None,
    last_error_message: Optional[str] = None,
    last_checked_at: Optional[str] = None,
) -> None:
    """写入/更新一条 coverage_status（幂等 UPSERT），不提交。

    - coverage_status 必须是合法枚举，否则抛 ValueError（契约门禁）。
    - 本次非成功（MISSING/BLOCKED/UNVERIFIED）时，保留上一次成功的
      last_success_run_id / last_success_at（读旧行回填），不擦除历史成功证据。
    - last_checked_at 缺省回落到 last_attempt_at（向后兼容别名）。
    """
    if coverage_status not in VALID_COVERAGE_STATUS:
        raise ValueError(f"非法 coverage_status: {coverage_status!r}")

    if not _is_success_status(coverage_status):
        row = conn.execute(
            "SELECT last_success_run_id, last_success_at FROM coverage_status "
            "WHERE insurer_code = ? AND disclosure_type = ?",
            (insurer_code, disclosure_type),
        ).fetchone()
        if row is not None:
            if last_success_run_id is None:
                last_success_run_id = row[0]
            if last_success_at is None:
                last_success_at = row[1]

    if last_checked_at is None:
        last_checked_at = last_attempt_at

    conn.execute(_COVERAGE_UPSERT_SQL, (
        insurer_code, disclosure_type, coverage_status,
        last_success_run_id, last_checked_at, last_attempt_at,
        last_success_at, last_error_code, last_error_message,
    ))


def read_coverage(conn: sqlite3.Connection, insurer_code: str, disclosure_type: str) -> Optional[dict]:
    """读取单条 coverage_status（测试/审计用）；不存在返回 None。"""
    row = conn.execute(
        """
        SELECT insurer_code, disclosure_type, coverage_status,
               last_success_run_id, last_checked_at, last_attempt_at,
               last_success_at, last_error_code, last_error_message
        FROM coverage_status
        WHERE insurer_code = ? AND disclosure_type = ?
        """,
        (insurer_code, disclosure_type),
    ).fetchone()
    if row is None:
        return None
    keys = (
        "insurer_code", "disclosure_type", "coverage_status",
        "last_success_run_id", "last_checked_at", "last_attempt_at",
        "last_success_at", "last_error_code", "last_error_message",
    )
    return dict(zip(keys, row))
