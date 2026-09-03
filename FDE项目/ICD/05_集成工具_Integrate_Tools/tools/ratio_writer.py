#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · tools/ratio_writer.py · fulfillment_ratio 事务写入与 parse_result 记录

职责边界：把标准化观测记录（由 skills/aia_json_parser 产出）事务性写入
fulfillment_ratio，并原子写入/更新 parse_result。不解析、不抓取、不访问网络。

对齐任务书 T004 功能要求 5/6 与 data_contract.md：
- 同一 run_id 重复解析幂等：INSERT ... ON CONFLICT(...) DO UPDATE，不产生重复行。
- 同源业务写入使用事务：任何硬失败回滚，绝不留下部分业务行。
- parse_result 准确记录 parse_status（OK / STRUCTURE_MISMATCH / ZERO_RECORD /
  PARTIAL / NOT_PARSED）与 records_produced。
- 唯一键含 metric_type 与 scope_currency_raw，同产品/指标/币种组/年份无损保存多行。
"""

import sqlite3
from typing import List, Optional

# 注意：ON CONFLICT 的列列表顺序须与 data_contract.md / sqlite_store.py 的
# UNIQUE(insurer_code, product_name_raw, metric_type, scope_currency_raw,
#        report_year, observation_year_raw, run_id) 一致。
_INSERT_RATIO_SQL = """
INSERT INTO fulfillment_ratio (
    insurer_code, product_id, product_name_raw, metric_type, metric_type_raw,
    report_year, observation_year_raw, observation_year, scope_currency_raw, raw_value,
    normalized_value, unit, run_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'percent', ?)
ON CONFLICT(insurer_code, product_name_raw, metric_type, scope_currency_raw,
            report_year, observation_year_raw, run_id)
DO UPDATE SET
    normalized_value = excluded.normalized_value,
    raw_value = excluded.raw_value,
    product_id = excluded.product_id,
    observation_year = excluded.observation_year
"""

_UPSERT_PARSE_RESULT_SQL = """
INSERT INTO parse_result (run_id, parse_status, records_produced, error_code, message)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(run_id) DO UPDATE SET
    parse_status = excluded.parse_status,
    records_produced = excluded.records_produced,
    error_code = excluded.error_code,
    message = excluded.message
"""


def _insert_ratio(conn: sqlite3.Connection, run_id: int, insurer_code: str, rec: dict) -> None:
    """插入/更新单条 fulfillment_ratio（幂等 UPSERT），不提交（事务由调用方控制）。"""
    conn.execute(_INSERT_RATIO_SQL, (
        insurer_code,
        rec.get("product_id"),
        rec["product_name_raw"],
        rec["metric_type"],
        rec["metric_type_raw"],
        rec["report_year"],
        rec["observation_year_raw"],
        rec["observation_year"],
        rec["scope_currency_raw"],
        rec["raw_value"],
        rec["normalized_value"],
        run_id,
    ))


def upsert_parse_result(
    conn: sqlite3.Connection,
    run_id: int,
    parse_status: str,
    records_produced: int,
    error_code: Optional[str] = None,
    message: Optional[str] = None,
) -> None:
    """写入/更新 parse_result（UNIQUE(run_id) 幂等），不提交（事务由调用方控制）。"""
    conn.execute(_UPSERT_PARSE_RESULT_SQL, (
        run_id, parse_status, records_produced, error_code, message,
    ))


def write_parse_outcome(
    conn: sqlite3.Connection,
    run_id: int,
    insurer_code: str,
    records: List[dict],
    parse_status: str,
    error_code: Optional[str] = None,
    message: Optional[str] = None,
) -> int:
    """原子写入一次解析的完整结果：全部业务行 + parse_result。

    任何硬失败（约束冲突/类型错误/IO）回滚整个事务，不留部分业务行。
    records 为空时（ZERO_RECORD / STRUCTURE_MISMATCH）只写 parse_result。
    返回写入的业务行数（records 长度）。
    """
    conn.execute("BEGIN")
    try:
        for rec in records:
            _insert_ratio(conn, run_id, insurer_code, rec)
        upsert_parse_result(conn, run_id, parse_status, len(records), error_code, message)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return len(records)
