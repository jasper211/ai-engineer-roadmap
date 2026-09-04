#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · tools/rbc_writer.py · rbc_statement 事务写入与 parse_result 记录

职责边界：把标准化 RBC 记录（由 skills/pru_rbc_parser 产出）事务性写入
rbc_statement，并原子写入/更新 parse_result。不解析、不抓取、不访问网络。

对齐任务书 T007 功能要求 5/6 与 data_contract.md：
- 同一 run_id 重复解析幂等：INSERT ... ON CONFLICT(insurer_code, report_year, run_id)
  DO UPDATE，不产生重复行。
- 单源事务写入：任何硬失败回滚，绝不留下部分 RBC 行或部分风险分解行。
- parse_result 准确记录 parse_status 与 records_produced。

说明（口径）：rbc_risk_component 规范化子表为可选；Prudential（General Insurance）
的风险分解（General Insurance Risk / Reserve and premium risk / Natural catastrophe
risk / Counterparty default and other risk 等）与 rbc_risk_component 的 risk_type 枚举
（MARKET/.../LIFE/GENERAL_INSURANCE/OPERATIONAL/OTHER）无法无损一一对应，故本实现
只写 rbc_statement 单行，原始风险分解完整保留在 rbc_statement.risk_breakdown_json，
不写 rbc_risk_component（避免有损合并口径）。
"""

import sqlite3
from typing import List, Optional

from tools import ratio_writer  # 复用 upsert_parse_result

# ON CONFLICT 列列表须与 data_contract.md / sqlite_store.py 的
# UNIQUE(insurer_code, report_year, run_id) 一致。
_INSERT_RBC_SQL = """
INSERT INTO rbc_statement (
    insurer_code, run_id, report_year, legal_entity_name_raw, solvency_ratio,
    solvency_ratio_raw, capital_base, capital_base_raw, prescribed_capital_amount,
    prescribed_capital_amount_raw, currency, amount_unit_raw, amount_scale,
    risk_breakdown_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(insurer_code, report_year, run_id)
DO UPDATE SET
    legal_entity_name_raw = excluded.legal_entity_name_raw,
    solvency_ratio = excluded.solvency_ratio,
    solvency_ratio_raw = excluded.solvency_ratio_raw,
    capital_base = excluded.capital_base,
    capital_base_raw = excluded.capital_base_raw,
    prescribed_capital_amount = excluded.prescribed_capital_amount,
    prescribed_capital_amount_raw = excluded.prescribed_capital_amount_raw,
    currency = excluded.currency,
    amount_unit_raw = excluded.amount_unit_raw,
    amount_scale = excluded.amount_scale,
    risk_breakdown_json = excluded.risk_breakdown_json
"""


def _insert_rbc(conn: sqlite3.Connection, run_id: int, insurer_code: str, rec: dict) -> None:
    """插入/更新单条 rbc_statement（幂等 UPSERT），不提交（事务由调用方控制）。"""
    conn.execute(_INSERT_RBC_SQL, (
        insurer_code,
        run_id,
        rec["report_year"],
        rec["legal_entity_name_raw"],
        rec.get("solvency_ratio"),
        rec.get("solvency_ratio_raw"),
        rec.get("capital_base"),
        rec.get("capital_base_raw"),
        rec.get("prescribed_capital_amount"),
        rec.get("prescribed_capital_amount_raw"),
        rec.get("currency", "HKD"),
        rec.get("amount_unit_raw"),
        rec.get("amount_scale"),
        rec.get("risk_breakdown_json"),
    ))


def write_rbc_outcome(
    conn: sqlite3.Connection,
    run_id: int,
    insurer_code: str,
    records: List[dict],
    parse_status: str,
    error_code: Optional[str] = None,
    message: Optional[str] = None,
) -> int:
    """原子写入一次 RBC 解析的完整结果：全部 rbc_statement 行 + parse_result。

    任何硬失败（约束冲突/类型错误/IO）回滚整个事务，不留部分 RBC 行。
    records 为空时（ZERO_RECORD / STRUCTURE_MISMATCH）只写 parse_result。
    返回写入的业务行数（records 长度）。
    """
    conn.execute("BEGIN")
    try:
        for rec in records:
            _insert_rbc(conn, run_id, insurer_code, rec)
        ratio_writer.upsert_parse_result(conn, run_id, parse_status, len(records), error_code, message)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return len(records)
