#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/parse_disclosure.py · 单源披露文件解析编排（L3-ICD-03 实现）

职责边界：把"定位快照 → 读原始字节 → 按格式解析 → 标准化 → 事务入库 + parse_result"
串成一次源级解析操作。不访问网络（原始字节已由 L3-ICD-02 抓取并固化为快照）。

对齐任务书 T004 功能要求与验收标准：
- 解析必须通过 run_id 反查真实快照（URL/时间/哈希/路径），不凭空构造。
- 结构缺键/类型错误/零业务记录 → 明确失败，不写业务表（只记 parse_result）。
- 同 run_id 重复解析幂等；业务写入走事务，任何硬失败不留部分业务行。
- 记录数覆盖 AIA 全部四类指标（AD/TD/RB/TB），不静默丢产品/丢组。
- 存在无法数值化但保留原文的观测项时，parse_result 写 PARTIAL + VALUE_UNPARSEABLE（软失败）。

结果 dict 顶层 result 取值：
  OK / ZERO_RECORD / STRUCTURE_MISMATCH / NO_FETCH_RUN /
  SNAPSHOT_MISSING / UNSUPPORTED_FORMAT / DB_ERROR
"""

from pathlib import Path
from typing import Optional

from skills import aia_json_parser, ctf_html_parser
from tools import ratio_writer

# 快照入库用的逻辑前缀（对齐 memory/workspace.snapshot_relpath）
_SNAPSHOT_PREFIX = "raw_data"


def _latest_ok_run(conn, source_id: int) -> Optional[dict]:
    """取某数据源最新一次成功抓取（fetch_status='OK'）；无则 None。"""
    row = conn.execute(
        """
        SELECT run_id, snapshot_path, content_hash, http_status, fetched_at, final_url
        FROM fetch_run
        WHERE source_id = ? AND fetch_status = 'OK'
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (source_id,),
    ).fetchone()
    if row is None:
        return None
    keys = ("run_id", "snapshot_path", "content_hash", "http_status", "fetched_at", "final_url")
    return dict(zip(keys, row))


def _snapshot_file(raw_data_root, snapshot_path: str) -> Path:
    """把 fetch_run.snapshot_path（如 'raw_data/AIA/1/{hash}.json'）解析为
    raw_data 根下的绝对文件路径，带防穿越守卫。"""
    p = Path(snapshot_path)
    parts = p.parts
    if parts and parts[0] == _SNAPSHOT_PREFIX:
        parts = parts[1:]
    root = Path(raw_data_root).resolve()
    f = root.joinpath(*parts).resolve()
    if f != root and root not in f.parents:
        raise ValueError(f"快照路径越界 raw_data 根: {f}")
    return f


def parse_one_source(conn, src: dict, raw_data_root) -> dict:
    """对单个数据源执行一次解析与入库，返回结构化结果 dict。"""
    source_id = src["source_id"]
    insurer = src["insurer_code"]
    fmt = src.get("format")

    base = {
        "source_id": source_id,
        "insurer_code": insurer,
        "disclosure_type": src.get("disclosure_type"),
        "result": None,
        "run_id": None,
        "report_year": None,
        "product_count": None,
        "records_written": None,
        "value_unparseable": None,
        "parse_status": None,
        "error_code": None,
        "message": None,
    }

    # 1) 通过 run_id 反查真实快照
    run = _latest_ok_run(conn, source_id)
    if run is None:
        base["result"] = "NO_FETCH_RUN"
        base["message"] = "未找到可解析的成功抓取（请先 --fetch 该数据源）"
        return base
    run_id = run["run_id"]
    base["run_id"] = run_id

    # 2) 定位并读取快照
    try:
        fpath = _snapshot_file(raw_data_root, run["snapshot_path"])
    except ValueError as e:
        base["result"] = "SNAPSHOT_MISSING"
        base["message"] = str(e)
        return base
    if not fpath.exists():
        base["result"] = "SNAPSHOT_MISSING"
        base["message"] = f"快照文件不存在: {fpath}"
        return base
    try:
        body = fpath.read_bytes()
    except OSError as e:
        base["result"] = "SNAPSHOT_MISSING"
        base["message"] = f"快照读取失败: {type(e).__name__}: {e}"
        return base

    # 3) 按格式 + 险企分流解析（T004 接入 AIA JSON；T005 接入 CTF Life HTML）
    try:
        if fmt == "json":
            parsed = aia_json_parser.parse_aia_json(body)
        elif fmt == "html" and insurer == "CTF":
            parsed = ctf_html_parser.parse_ctf_html(body)
        else:
            base["result"] = "UNSUPPORTED_FORMAT"
            base["message"] = (
                f"暂未接入 format={fmt!r} insurer={insurer!r} 的解析"
                f"（已接入：AIA JSON、CTF HTML；其余 HTML/PDF 待后续任务）"
            )
            return base
    except (aia_json_parser.AiaParseError, ctf_html_parser.CtfParseError) as e:
        base["result"] = "STRUCTURE_MISMATCH"
        base["parse_status"] = "STRUCTURE_MISMATCH"
        base["error_code"] = "STRUCTURE_MISMATCH"
        base["message"] = str(e)
        try:
            ratio_writer.write_parse_outcome(
                conn, run_id, insurer, [], "STRUCTURE_MISMATCH", "STRUCTURE_MISMATCH", str(e),
            )
        except Exception as we:  # noqa: BLE001 —— 记录失败也须报告，不掩盖解析结论
            base["result"] = "DB_ERROR"
            base["error_code"] = "DB_WRITE_FAILED"
            base["message"] = f"parse_result 写入失败: {type(we).__name__}: {we}"
        return base

    status = parsed["status"]
    records = parsed["records"]
    value_unparseable = parsed["value_unparseable"]
    base["report_year"] = parsed["report_year"]
    base["product_count"] = parsed["product_count"]
    base["value_unparseable"] = value_unparseable

    # 第三项决策补充：只要存在无法数值化但保留原文的观测项，parse_result 写 PARTIAL
    # + VALUE_UNPARSEABLE（软失败），记录数仍包含这些原始观测项，不静默丢弃。
    if status == "OK" and value_unparseable > 0:
        parse_status = "PARTIAL"
        error_code = "VALUE_UNPARSEABLE"
    elif status == "ZERO_RECORD":
        parse_status = "ZERO_RECORD"
        error_code = "ZERO_RECORD"
    else:
        parse_status = status
        error_code = None

    base["parse_status"] = parse_status
    base["error_code"] = error_code

    message = (
        f"products={parsed['product_count']}, records={len(records)}, "
        f"value_unparseable={value_unparseable}"
    )

    # 4) 事务入库（OK/PARTIAL 写全部业务行；ZERO_RECORD 只写 parse_result，不写业务表）
    try:
        n = ratio_writer.write_parse_outcome(
            conn, run_id, insurer, records, parse_status, error_code, message,
        )
    except Exception as e:  # noqa: BLE001 —— DB 写失败须清晰报告，业务行已回滚
        base["result"] = "DB_ERROR"
        base["error_code"] = "DB_WRITE_FAILED"
        base["message"] = f"入库失败（已回滚）: {type(e).__name__}: {e}"
        return base

    base["result"] = status
    base["records_written"] = n
    base["message"] = message
    return base
