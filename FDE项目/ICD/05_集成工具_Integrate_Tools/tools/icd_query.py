"""ICD 稳定只读查询层：白名单查询、最新版本语义和来源证据。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote


class ICDQueryError(ValueError):
    """查询参数或只读数据库不符合契约。"""


METRICS = {"AD", "TD", "RB", "TB", "TCV", "OTHER"}
DISCLOSURE_TYPES = {"fulfillment_ratio", "total_cash_value_ratio", "rbc"}


def open_readonly(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    if not path.is_file():
        raise ICDQueryError(f"ICD 数据库不存在: {path}")
    uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        required = {"fulfillment_ratio", "rbc_statement", "fetch_run", "data_source", "coverage_status"}
        actual = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(required - actual)
        if missing:
            conn.close()
            raise ICDQueryError(f"ICD schema 不兼容，缺表: {', '.join(missing)}")
        return conn
    except sqlite3.Error as exc:
        raise ICDQueryError(f"ICD 数据库只读打开失败: {exc}") from exc


def _limit(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5000:
        raise ICDQueryError("limit 必须是 1..5000 的整数")
    return value


def _rows(conn: sqlite3.Connection, sql: str, params: list[Any]) -> List[Dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def fulfillment(
    conn: sqlite3.Connection, *, insurer_code: Optional[str] = None,
    product_name: Optional[str] = None, metric_type: Optional[str] = None,
    report_year: Optional[int] = None, include_history: bool = False, limit: int = 1000,
) -> Dict[str, Any]:
    limit = _limit(limit)
    if metric_type is not None and metric_type not in METRICS:
        raise ICDQueryError(f"未知 metric_type: {metric_type}")
    if report_year is not None and (not isinstance(report_year, int) or isinstance(report_year, bool)):
        raise ICDQueryError("report_year 必须是整数")
    where, params = ["frun.fetch_status='OK'"], []
    if insurer_code:
        where.append("f.insurer_code=?"); params.append(insurer_code)
    if product_name:
        where.append("f.product_name_raw LIKE ? ESCAPE '\\'"); params.append(f"%{product_name}%")
    if metric_type:
        where.append("f.metric_type=?"); params.append(metric_type)
    if report_year is not None:
        where.append("f.report_year=?"); params.append(report_year)
    latest = "" if include_history else """
      AND f.run_id=(SELECT MAX(f2.run_id) FROM fulfillment_ratio f2
                    JOIN fetch_run fr2 ON fr2.run_id=f2.run_id AND fr2.fetch_status='OK'
                    WHERE f2.insurer_code=f.insurer_code
                      AND f2.product_name_raw=f.product_name_raw
                      AND f2.metric_type=f.metric_type
                      AND f2.scope_currency_raw=f.scope_currency_raw
                      AND f2.report_year=f.report_year
                      AND f2.observation_year_raw=f.observation_year_raw)
    """
    sql = f"""
      SELECT f.insurer_code,f.product_name_raw,f.metric_type,f.metric_type_raw,
             f.report_year,f.observation_year_raw,f.observation_year,f.scope_currency_raw,
             f.raw_value,f.normalized_value,f.unit,f.run_id,
             ds.entry_url AS source_url,frun.final_url,frun.fetched_at,
             frun.content_hash AS sha256,frun.snapshot_path
      FROM fulfillment_ratio f
      JOIN fetch_run frun ON frun.run_id=f.run_id
      JOIN data_source ds ON ds.source_id=frun.source_id
      WHERE {' AND '.join(where)} {latest}
      ORDER BY f.insurer_code,f.product_name_raw,f.metric_type,f.report_year DESC,
               COALESCE(f.observation_year,-1) DESC,f.observation_year_raw DESC,f.run_id DESC
      LIMIT ?
    """
    params.append(limit)
    data = _rows(conn, sql, params)
    return {"query_type": "fulfillment", "count": len(data), "data": data,
            "quality_notes": ["normalized_value 为小数比率；1.0=100%", "normalized_value=null 表示官网原文不可数值化，不等于0", "product_name_raw 为官网原始名称"]}


def rbc(conn: sqlite3.Connection, *, insurer_code: Optional[str] = None,
        report_year: Optional[int] = None, include_history: bool = False,
        limit: int = 1000) -> Dict[str, Any]:
    limit = _limit(limit)
    where, params = ["frun.fetch_status='OK'"], []
    if insurer_code:
        where.append("r.insurer_code=?"); params.append(insurer_code)
    if report_year is not None:
        if not isinstance(report_year, int) or isinstance(report_year, bool):
            raise ICDQueryError("report_year 必须是整数")
        where.append("r.report_year=?"); params.append(report_year)
    latest = "" if include_history else """
      AND r.run_id=(SELECT MAX(r2.run_id) FROM rbc_statement r2
                    JOIN fetch_run fr2 ON fr2.run_id=r2.run_id AND fr2.fetch_status='OK'
                    WHERE r2.insurer_code=r.insurer_code AND r2.report_year=r.report_year)
    """
    sql = f"""
      SELECT r.insurer_code,r.legal_entity_name_raw,r.report_year,
             r.solvency_ratio,r.solvency_ratio_raw,r.capital_base,r.capital_base_raw,
             r.prescribed_capital_amount,r.prescribed_capital_amount_raw,r.currency,
             r.amount_unit_raw,r.amount_scale,r.risk_breakdown_json,r.run_id,
             ds.entry_url AS source_url,frun.final_url,frun.fetched_at,
             frun.content_hash AS sha256,frun.snapshot_path
      FROM rbc_statement r JOIN fetch_run frun ON frun.run_id=r.run_id
      JOIN data_source ds ON ds.source_id=frun.source_id
      WHERE {' AND '.join(where)} {latest}
      ORDER BY r.insurer_code,r.report_year DESC,r.run_id DESC LIMIT ?
    """
    params.append(limit)
    data = _rows(conn, sql, params)
    return {"query_type": "rbc", "count": len(data), "data": data,
            "quality_notes": ["solvency_ratio 为小数比率；3.04=304%", "legal_entity_name_raw 是披露文件中的法律主体原文", "金额标准值按明示标度折算，原文与标度同时返回"]}


def coverage(conn: sqlite3.Connection, *, insurer_code: Optional[str] = None,
             disclosure_type: Optional[str] = None) -> Dict[str, Any]:
    if disclosure_type is not None and disclosure_type not in DISCLOSURE_TYPES:
        raise ICDQueryError(f"未知 disclosure_type: {disclosure_type}")
    where, params = ["1=1"], []
    if insurer_code:
        where.append("insurer_code=?"); params.append(insurer_code)
    if disclosure_type:
        where.append("disclosure_type=?"); params.append(disclosure_type)
    data = _rows(conn, f"SELECT insurer_code,disclosure_type,coverage_status,last_success_run_id,last_attempt_at,last_success_at,last_error_code,last_error_message FROM coverage_status WHERE {' AND '.join(where)} ORDER BY disclosure_type,insurer_code", params)
    return {"query_type": "coverage", "count": len(data), "data": data}


def evidence(conn: sqlite3.Connection, *, run_id: int) -> Dict[str, Any]:
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ICDQueryError("run_id 必须是正整数")
    data = _rows(conn, """
      SELECT fr.run_id,fr.source_id,ds.insurer_code,ds.disclosure_type,
             ds.entry_url AS source_url,fr.final_url,fr.fetched_at,fr.http_status,
             fr.fetch_status,fr.content_hash AS sha256,fr.content_length,
             fr.snapshot_path,fr.error_code,fr.note
      FROM fetch_run fr JOIN data_source ds ON ds.source_id=fr.source_id
      WHERE fr.run_id=?
    """, [run_id])
    return {"query_type": "evidence", "count": len(data), "data": data}


class ICDClient:
    """小型上下文管理客户端，始终以 SQLite mode=ro 连接。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @classmethod
    def open_readonly(cls, db_path: Path | str) -> "ICDClient":
        return cls(open_readonly(db_path))

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ICDClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def fulfillment(self, **kwargs: Any) -> Dict[str, Any]:
        return fulfillment(self.conn, **kwargs)

    def rbc(self, **kwargs: Any) -> Dict[str, Any]:
        return rbc(self.conn, **kwargs)

    def coverage(self, **kwargs: Any) -> Dict[str, Any]:
        return coverage(self.conn, **kwargs)

    def evidence(self, **kwargs: Any) -> Dict[str, Any]:
        return evidence(self.conn, **kwargs)
