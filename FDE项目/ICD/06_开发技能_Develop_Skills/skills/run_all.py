#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/run_all.py · 全量运行编排（L3-ICD-01 循环 + L3-ICD-06 聚合）

职责边界：把「读取 active 源 → 逐源 fetch/discover/parse → 覆盖状态聚合 →
运行摘要落盘」串成一次全量批次运行。不重实现单源抓取/解析——复用
fetch_disclosure.fetch_one_source / parse_disclosure.parse_one_source /
rbc_index_discovery.discover_disclosure_pdf。

对齐任务书 T009 功能要求 1/2/3/4/6/7：
- 按固定 source_id 顺序处理 is_active=1 的源；BLOCKED / UNVERIFIED /
  requires_browser 跳过（不发网络请求）并进入摘要与覆盖状态。
- 单源 fetch / 发现 / 解析失败不得中止其余源（隔离）；仅全局数据库损坏（
  sqlite3.DatabaseError）才向上抛（硬失败，由 CLI 转非零退出）。
- rbc 索引源（disclosure_type=rbc 且 format=html）执行「发现」而非解析；尚未接入
  的 OPEN/PARTIAL 源显式标为 unsupported，不假装成功。
- coverage_status 按险企 × 披露类型确定性推导（FULL/PARTIAL/MISSING/BLOCKED/
  UNVERIFIED），区分「值不可数值化（仍覆盖成功）」与「来源覆盖缺失」。
- --no-network：跳过抓取，基于既有快照完成解析/汇总。
"""

import re
import sqlite3
from collections import OrderedDict
from typing import Dict, List, Optional

from skills import fetch_disclosure, parse_disclosure, rbc_index_discovery, summary_writer
from tools import coverage_writer, fetch_recorder
from memory import workspace


# ---------------------------------------------------------------------------
# 分类：把数据源映射为「动作」
# ---------------------------------------------------------------------------
def classify_source(src: dict) -> str:
    """返回数据源应执行的动作。

    取值：skip_blocked / skip_unverified / skip_browser / discover /
    fetch_parse / unsupported。判定顺序固定：先门禁（BLOCKED/UNVERIFIED/
    requires_browser），再 rbc 索引发现，再已接入解析，最后未接入。
    """
    status = src.get("access_status")
    if status == "BLOCKED":
        return "skip_blocked"
    if status == "UNVERIFIED":
        return "skip_unverified"
    if src.get("requires_browser") in (1, True):
        return "skip_browser"
    if src.get("disclosure_type") == "rbc" and src.get("format") == "html":
        return "discover"
    if parse_disclosure.supports_parse(src):
        return "fetch_parse"
    return "unsupported"


# ---------------------------------------------------------------------------
# 索引发现（复用 rbc_index_discovery 的核心，封装「定位快照 → 读字节 → 发现」）
# ---------------------------------------------------------------------------
def discover_for_source(conn: sqlite3.Connection, src: dict, raw_data_root) -> dict:
    """从某 rbc 索引源最新成功抓取的快照确定性地发现目标 PDF；返回结构化结果 dict。

    结果 result 取值：OK / AMBIGUOUS_OR_NO_MATCH / NO_FETCH_RUN / SNAPSHOT_MISSING。
    """
    source_id = src["source_id"]
    base = {
        "source_id": source_id,
        "result": None,
        "run_id": None,
        "filename_hint": None,
        "discovered_pdf_url": None,
        "candidate_count": 0,
        "message": None,
    }

    run = parse_disclosure._latest_ok_run(conn, source_id)
    if run is None:
        base["result"] = "NO_FETCH_RUN"
        base["message"] = "未找到可发现索引的成功抓取"
        return base
    base["run_id"] = run["run_id"]

    try:
        fpath = parse_disclosure._snapshot_file(raw_data_root, run["snapshot_path"])
    except ValueError as e:
        base["result"] = "SNAPSHOT_MISSING"
        base["message"] = str(e)
        return base
    if not fpath.exists():
        base["result"] = "SNAPSHOT_MISSING"
        base["message"] = f"快照不存在: {fpath}"
        return base
    try:
        html = fpath.read_bytes()
    except OSError as e:
        base["result"] = "SNAPSHOT_MISSING"
        base["message"] = f"快照读取失败: {type(e).__name__}: {e}"
        return base

    hint = None
    hint_text = src.get("parser_hint") or ""
    m = re.search(r"([A-Za-z0-9][\w\s%.-]*\.pdf)", hint_text, re.IGNORECASE)
    if m:
        hint = m.group(1).strip()
    base["filename_hint"] = hint

    candidates = rbc_index_discovery.extract_disclosure_pdf_candidates(html)
    base["candidate_count"] = len(candidates)
    try:
        url = rbc_index_discovery.discover_disclosure_pdf(html, filename_hint=hint)
    except rbc_index_discovery.RbcIndexDiscoveryError as e:
        base["result"] = "AMBIGUOUS_OR_NO_MATCH"
        base["message"] = str(e)
        return base

    base["result"] = "OK"
    base["discovered_pdf_url"] = url
    return base


# ---------------------------------------------------------------------------
# 单源处理（隔离）
# ---------------------------------------------------------------------------
def _process_source(conn: sqlite3.Connection, src: dict, raw_data_root, no_network: bool) -> dict:
    """对单个数据源执行 fetch/discover/parse 之一，返回逐源摘要条目（永不抛业务异常）。"""
    action = classify_source(src)
    entry = {
        "source_id": src["source_id"],
        "insurer_code": src["insurer_code"],
        "disclosure_type": src["disclosure_type"],
        "action": action,
        "fetch_status": None,
        "parse_status": None,
        "parse_detail": None,
        "run_id": None,
        "records_written": None,
        "error_code": None,
        "message": None,
    }

    if action == "skip_blocked":
        entry["fetch_status"] = "SKIPPED"
        entry["message"] = "access_status=BLOCKED 跳过，不发网络请求"
        return entry
    if action == "skip_unverified":
        entry["fetch_status"] = "SKIPPED"
        entry["message"] = "access_status=UNVERIFIED 跳过，不发网络请求"
        return entry
    if action == "skip_browser":
        entry["fetch_status"] = "SKIPPED"
        entry["message"] = "requires_browser=true 跳过，不引入浏览器自动化"
        return entry
    if action == "unsupported":
        entry["fetch_status"] = "UNSUPPORTED"
        entry["message"] = "format 未接入解析（缺覆盖），不假装成功"
        return entry

    # 可处理源：抓取（--no-network 则跳过，复用既有快照）
    if no_network:
        entry["fetch_status"] = "NO_NETWORK"
    else:
        fr = fetch_disclosure.fetch_one_source(conn, src, raw_data_root)
        entry["fetch_status"] = fr.get("result")
        entry["error_code"] = fr.get("error_code")
        entry["message"] = fr.get("note")
        if fr["result"] in ("HTTP_ERROR", "NETWORK_ERROR", "REJECTED", "SNAPSHOT_ERROR", "DB_ERROR"):
            return entry

    if action == "discover":
        d = discover_for_source(conn, src, raw_data_root)
        entry["parse_status"] = d["result"]
        entry["run_id"] = d.get("run_id")
        entry["discovered_pdf_url"] = d.get("discovered_pdf_url")
        if d["result"] == "OK":
            entry["error_code"] = None
        elif d["result"] == "AMBIGUOUS_OR_NO_MATCH":
            entry["error_code"] = "STRUCTURE_MISMATCH"
        else:
            entry["error_code"] = None
        entry["message"] = d.get("message")
        return entry

    # fetch_parse
    p = parse_disclosure.parse_one_source(conn, src, raw_data_root)
    entry["parse_status"] = p["result"]
    # parse_detail：值不可数值化等软失败时 parse_result 表状态（如 PARTIAL），
    # 与「结果 OK」区分，便于审计阅读，但不改变覆盖成功判定（以 records_written>0 为准）。
    entry["parse_detail"] = p.get("parse_status") if p.get("parse_status") != p.get("result") else None
    entry["run_id"] = p.get("run_id")
    entry["records_written"] = p.get("records_written")
    entry["error_code"] = p.get("error_code")
    entry["message"] = p.get("message")
    return entry


# ---------------------------------------------------------------------------
# 覆盖状态推导
# ---------------------------------------------------------------------------
def _source_succeeded(entry: dict) -> bool:
    """源级成功判定：发现源以确定性定位成功为准；业务源以 records_written > 0 为准。

    关键语义（任务书要求 4）：parse_result=PARTIAL（值不可数值化，但 records_written>0）
    仍算「覆盖成功」，不误判为覆盖缺失。
    """
    if entry["action"] == "discover":
        return entry.get("parse_status") == "OK"
    return (entry.get("records_written") or 0) > 0


def coverage_for_pair(entries: List[dict]) -> dict:
    """按险企 × 披露类型推导确定性覆盖状态（见 data_contract.md 3.10）。"""
    processable = [e for e in entries if e["action"] in ("fetch_parse", "discover", "unsupported")]
    blocked = [e for e in entries if e["action"] in ("skip_blocked", "skip_browser")]
    unverified = [e for e in entries if e["action"] == "skip_unverified"]

    if not processable:
        if blocked and not unverified:
            status = "BLOCKED"
        elif unverified and not blocked:
            status = "UNVERIFIED"
        elif blocked:
            status = "BLOCKED"
        else:
            status = "UNVERIFIED"
        return {"coverage_status": status, "last_success_run_id": None,
                "last_error_code": None, "last_error_message": None}

    succeeded = [e for e in processable if _source_succeeded(e)]
    if not succeeded:
        err = None
        msg = None
        for e in reversed(processable):
            if e.get("error_code"):
                err = e["error_code"]
                msg = e.get("message")
                break
        if err is None and processable:
            err = processable[-1].get("error_code")
            msg = processable[-1].get("message")
        return {"coverage_status": "MISSING", "last_success_run_id": None,
                "last_error_code": err, "last_error_message": msg}

    success_run_id = succeeded[-1].get("run_id")
    if len(succeeded) == len(processable):
        return {"coverage_status": "FULL", "last_success_run_id": success_run_id,
                "last_error_code": None, "last_error_message": None}
    return {"coverage_status": "PARTIAL", "last_success_run_id": success_run_id,
            "last_error_code": None, "last_error_message": None}


def _compute_counts(entries: List[dict]) -> Dict[str, int]:
    attempted = [e for e in entries if e["action"] in ("fetch_parse", "discover")]
    return {
        "processed": len(attempted),
        "succeeded": sum(1 for e in attempted if _source_succeeded(e)),
        "failed": sum(1 for e in attempted if not _source_succeeded(e)),
        "skipped": sum(1 for e in entries if e["action"] in ("skip_blocked", "skip_unverified", "skip_browser")),
        "unsupported": sum(1 for e in entries if e["action"] == "unsupported"),
    }


def _build_and_write_coverage(conn: sqlite3.Connection, entries: List[dict], now_iso: str) -> List[dict]:
    """按 source_id 首现顺序聚合 (insurer, disclosure_type)，事务写入 coverage_status。"""
    pairs: "OrderedDict" = OrderedDict()
    for e in entries:
        key = (e["insurer_code"], e["disclosure_type"])
        pairs.setdefault(key, []).append(e)

    coverage: List[dict] = []
    for (insurer, dtype), es in pairs.items():
        cov = coverage_for_pair(es)
        success = cov["coverage_status"] in ("FULL", "PARTIAL")
        coverage_writer.upsert_coverage(
            conn, insurer, dtype, cov["coverage_status"],
            last_success_run_id=cov.get("last_success_run_id"),
            last_attempt_at=now_iso,
            last_success_at=now_iso if success else None,
            last_error_code=cov.get("last_error_code"),
            last_error_message=cov.get("last_error_message"),
            last_checked_at=now_iso,
        )
        coverage.append({
            "insurer_code": insurer,
            "disclosure_type": dtype,
            "coverage_status": cov["coverage_status"],
            "last_success_run_id": cov.get("last_success_run_id"),
            "last_attempt_at": now_iso,
            "last_success_at": now_iso if success else None,
            "last_error_code": cov.get("last_error_code"),
            "last_error_message": cov.get("last_error_message"),
        })
    conn.commit()
    return coverage


# ---------------------------------------------------------------------------
# 全量运行入口
# ---------------------------------------------------------------------------
def run_all(
    conn: sqlite3.Connection,
    raw_data_root,
    *,
    no_network: bool = False,
    summary_dir=None,
) -> dict:
    """执行一次全量批次运行并返回运行摘要 dict。

    - conn 必须是已初始化（CLI 层已校验配置与库状态）。
    - 单源失败隔离；sqlite3.DatabaseError 视为数据库损坏 → 向上抛（硬失败）。
    - summary_dir 为摘要受控目录；None 时回落 workspace 默认目录。
    """
    started_at = summary_writer.utc_now_iso()
    run_id = summary_writer.new_run_id()
    mode = "no_network" if no_network else "network"

    if summary_dir is None:
        summary_dir = workspace.summaries_root()

    source_ids = [
        r[0] for r in conn.execute(
            "SELECT source_id FROM data_source WHERE is_active = 1 ORDER BY source_id"
        ).fetchall()
    ]

    entries: List[dict] = []
    for sid in source_ids:
        src = fetch_recorder.get_source(conn, sid)
        if src is None:
            continue
        try:
            entry = _process_source(conn, src, raw_data_root, no_network)
        except sqlite3.DatabaseError:
            raise
        except Exception as e:  # noqa: BLE001 —— 单源未预期异常隔离，不中止其余源
            entry = {
                "source_id": sid,
                "insurer_code": src["insurer_code"],
                "disclosure_type": src["disclosure_type"],
                "action": classify_source(src),
                "fetch_status": None,
                "parse_status": None,
                "run_id": None,
                "records_written": None,
                "error_code": "DB_WRITE_FAILED",
                "message": f"未预期异常（单源隔离）: {type(e).__name__}: {e}",
            }
        entries.append(entry)

    coverage = _build_and_write_coverage(conn, entries, started_at)
    finished_at = summary_writer.utc_now_iso()

    summary = {
        "run_id": run_id,
        "mode": mode,
        "started_at": started_at,
        "finished_at": finished_at,
        "counts": _compute_counts(entries),
        "sources": entries,
        "coverage": coverage,
    }

    files = summary_writer.write_summary(summary_dir, summary)
    summary["summary_files"] = files
    summary["run_id"] = files["run_id"]
    return summary
