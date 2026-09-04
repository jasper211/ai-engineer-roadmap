#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/fetch_disclosure.py · HTTP 抓取与原始证据固化编排（L3-ICD-02 实现）

职责边界：把"抓字节 → 算哈希 → 去重 → 原子落盘 → 写 fetch_run"串成一次源级操作。
不解析 JSON/HTML/PDF 业务内容（那是 L3-ICD-03 起）。

对齐任务书 T003 功能要求与验收标准：
- 快照成功后才写成功 fetch_run；HTTP/网络失败按三态写失败行；
- 同源同内容重复抓取 → 返回 UNCHANGED，不重复快照、不重复成功行；
- 快照写失败 → 返回 SNAPSHOT_ERROR（不写 fetch_run，不留半文件）；
- 数据库写失败 → 返回 DB_ERROR 并清理孤儿快照；
- BLOCKED / UNVERIFIED / requires_browser / 空 entry_url / 空 format → REJECTED，无副作用；
- dry_run → 只抓取+计算，不写快照、不写库，返回 DRY_RUN。
"""

from typing import Optional

from memory import workspace
from tools import fetch_recorder, http_fetcher, snapshot
from skills import yfl_api


def validate_fetchable(src: dict) -> Optional[str]:
    """抓取门禁：返回拒绝原因字符串；None 表示可抓取。"""
    status = src.get("access_status")
    if status in ("BLOCKED", "UNVERIFIED"):
        return f"access_status={status} 拒绝抓取"
    if src.get("requires_browser") in (1, True):
        return "requires_browser=true 拒绝抓取（需浏览器）"
    if not src.get("entry_url"):
        return "entry_url 为空，拒绝抓取"
    if not src.get("format"):
        return "format 为空，拒绝抓取"
    return None


def fetch_one_source(
    conn,
    src: dict,
    raw_data_root,
    *,
    dry_run: bool = False,
    max_bytes: Optional[int] = None,
    connect_timeout: Optional[float] = None,
    read_timeout: Optional[float] = None,
) -> dict:
    """对单个数据源执行一次抓取与证据固化，返回结构化结果 dict。

    结果 result 取值：OK / UNCHANGED / HTTP_ERROR / NETWORK_ERROR /
    REJECTED / SNAPSHOT_ERROR / DB_ERROR / DRY_RUN。
    """
    source_id = src["source_id"]
    insurer = src["insurer_code"]
    base = {
        "source_id": source_id,
        "insurer_code": insurer,
        "disclosure_type": src.get("disclosure_type"),
        "dry_run": bool(dry_run),
        "result": None,
        "http_status": None,
        "final_url": None,
        "content_hash": None,
        "content_length": None,
        "snapshot_path": None,
        "error_code": None,
        "note": None,
    }

    reject = validate_fetchable(src)
    if reject:
        base["result"] = "REJECTED"
        base["note"] = reject
        return base

    url = src["entry_url"]
    if insurer == "YFL" and src.get("disclosure_type") == "fulfillment_ratio":
        outcome = yfl_api.collect(url, lambda target: http_fetcher.fetch(
            target, max_bytes=max_bytes, connect_timeout=connect_timeout, read_timeout=read_timeout,
        ))
    else:
        outcome = http_fetcher.fetch(
            url, max_bytes=max_bytes, connect_timeout=connect_timeout, read_timeout=read_timeout,
        )

    # HTTP 失败：有状态码、无哈希/快照
    if outcome.fetch_status == "HTTP_ERROR":
        base["result"] = "HTTP_ERROR"
        base["http_status"] = outcome.http_status
        base["final_url"] = outcome.final_url
        base["error_code"] = outcome.error_code
        base["note"] = outcome.note
        if not dry_run:
            fetch_recorder.record_http_error(
                conn, source_id, outcome.final_url, outcome.http_status,
                outcome.error_code, outcome.note,
            )
            conn.commit()
        return base

    # 网络失败：无状态码、无哈希/快照
    if outcome.fetch_status == "NETWORK_ERROR":
        base["result"] = "NETWORK_ERROR"
        base["final_url"] = outcome.final_url
        base["error_code"] = outcome.error_code
        base["note"] = outcome.note
        if not dry_run:
            fetch_recorder.record_network_error(
                conn, source_id, outcome.error_code, outcome.note,
            )
            conn.commit()
        return base

    # 拿到原始字节：算哈希
    body = outcome.body
    content_hash = snapshot.sha256_hex(body)
    content_length = len(body)
    evidence_format = "json" if insurer == "YFL" and src.get("disclosure_type") == "fulfillment_ratio" else src.get("format")
    ext = snapshot.ext_for_format(evidence_format)
    relpath = workspace.snapshot_relpath(insurer, source_id, content_hash, ext)
    fullpath = workspace.snapshot_fullpath(
        raw_data_root, insurer, source_id, content_hash, ext
    )

    base["http_status"] = outcome.http_status
    base["final_url"] = outcome.final_url
    base["content_hash"] = content_hash
    base["content_length"] = content_length

    # dry-run：只演练，不碰数据库与快照
    if dry_run:
        base["result"] = "DRY_RUN"
        base["snapshot_path"] = relpath
        base["note"] = f"dry-run：未写快照/数据库（目标路径 {fullpath}）"
        return base

    # 去重：同源同内容已有成功行 → UNCHANGED，不重复落盘、不重复成功行
    existing = fetch_recorder.find_ok_by_hash(conn, source_id, content_hash)
    if existing is not None:
        base["result"] = "UNCHANGED"
        base["snapshot_path"] = existing[2]
        base["note"] = "同源同内容已存在，跳过快照与成功行"
        return base

    # 原子落盘快照（文件已存在则跳过，避免重复写）
    try:
        if not fullpath.exists():
            snapshot.write_atomic(fullpath, body)
    except Exception as e:  # noqa: BLE001 —— 快照失败须清晰报告，不留半文件
        base["result"] = "SNAPSHOT_ERROR"
        base["snapshot_path"] = None
        base["error_code"] = "SNAPSHOT_WRITE_FAILED"
        base["note"] = f"快照落盘失败: {type(e).__name__}: {e}"
        return base

    # 快照成功后才写成功 fetch_run
    try:
        fetch_recorder.record_ok(
            conn, source_id, outcome.final_url, outcome.http_status,
            content_hash, content_length, relpath,
        )
        conn.commit()
    except Exception as e:  # noqa: BLE001 —— DB 写失败须报告并清理孤儿快照
        try:
            if fullpath.exists():
                fullpath.unlink()
        except OSError:
            pass
        base["result"] = "DB_ERROR"
        base["snapshot_path"] = None
        base["error_code"] = "DB_WRITE_FAILED"
        base["note"] = f"fetch_run 写入失败: {type(e).__name__}: {e}（已清理孤儿快照）"
        return base

    base["result"] = "OK"
    base["snapshot_path"] = relpath
    return base
