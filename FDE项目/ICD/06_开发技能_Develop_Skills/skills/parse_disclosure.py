#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/parse_disclosure.py · 单源披露文件解析编排（L3-ICD-03 实现）

职责边界：把"定位快照 → 读原始字节 → 按格式解析 → 标准化 → 事务入库 + parse_result"
串成一次源级解析操作。不访问网络（原始字节已由 L3-ICD-02 抓取并固化为快照）。

对齐任务书 T004/T005/T006/T007 功能要求与验收标准：
- 解析必须通过 run_id 反查真实快照（URL/时间/哈希/路径），不凭空构造。
- 结构缺键/类型错误/零业务记录 → 明确失败，不写业务表（只记 parse_result）。
- 同 run_id 重复解析幂等；业务写入走事务，任何硬失败不留部分业务行。
- 记录数覆盖 AIA 四类指标（AD/TD/RB/TB）与 CTF/CLO 表格与 Prudential RBC PDF。
- 存在无法数值化但保留原文的观测项时，parse_result 写 PARTIAL + VALUE_UNPARSEABLE（软失败）。

结果 dict 顶层 result 取值：
  OK / ZERO_RECORD / STRUCTURE_MISMATCH / NO_FETCH_RUN /
  SNAPSHOT_MISSING / UNSUPPORTED_FORMAT / DB_ERROR
"""

from pathlib import Path
from typing import Optional

from skills import aia_json_parser, clo_html_parser, ctf_html_parser, multi_html_parser, nextjs_ratio, pdf_text, rbc_parser, yfl_api
from tools import ratio_writer, rbc_writer

# 快照入库用的逻辑前缀（对齐 memory/workspace.snapshot_relpath）
_SNAPSHOT_PREFIX = "raw_data"

# 当前已接入解析的支持矩阵（与 parse_one_source 的分流一致；供 run_all 分类复用，
# 避免编排层与解析层对「哪些源已接入」的判断发生漂移）。
_SUPPORTED_RATIO_HTML_INSURERS = ("CTF", "CLO", "SUN", "BOC", "YFL", "AXA", "FWD")
_SUPPORTED_RBC_PDF_INSURERS = ("PRUGI", "AIACO")


def supports_parse(src: dict) -> bool:
    """判断某数据源是否已接入解析（True = parse_one_source 会走真实解析分支）。

    已接入：json（任意险企，当前仅 AIA）；html 且 insurer ∈ {CTF, CLO, SUN, BOC}；
    pdf 且 insurer ∈ {PRUGI, AIACO}（RBC）。其余（AXA/YFL/FWD 的
    html、PRU 履行率 pdf 等）→ False（parse_one_source 返回 UNSUPPORTED_FORMAT）。
    注意：rbc 索引源（html）不在此支持矩阵内——它走「发现」而非「解析」。
    """
    fmt = src.get("format")
    insurer = src.get("insurer_code")
    if fmt == "json":
        return True
    if fmt == "html":
        return insurer in _SUPPORTED_RATIO_HTML_INSURERS
    if fmt == "pdf":
        return insurer in _SUPPORTED_RBC_PDF_INSURERS
    return False


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


def _record_parse_failure(conn, run_id: int, base: dict, parse_status: str, error_code: str, message: str) -> dict:
    """失败路径：只写 parse_result（不写业务行）；parse_result 写入失败也须报告。"""
    try:
        ratio_writer.upsert_parse_result(conn, run_id, parse_status, 0, error_code, message)
        conn.commit()
    except Exception as we:  # noqa: BLE001 —— 记录失败也须报告，不掩盖解析结论
        base["result"] = "DB_ERROR"
        base["error_code"] = "DB_WRITE_FAILED"
        base["message"] = f"parse_result 写入失败: {type(we).__name__}: {we}"
    return base


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

    # 3) 按格式 + 险企分流解析（T004 AIA JSON / T005 CTF HTML / T006 CLO HTML /
    #    T007 PRUGI RBC PDF / T008 AIACO RBC PDF，后两者共用通用 rbc_parser）
    is_rbc = fmt == "pdf" and insurer in ("PRUGI", "AIACO")
    try:
        if fmt == "json":
            parsed = aia_json_parser.parse_aia_json(body)
        elif fmt == "html" and insurer == "CTF":
            parsed = ctf_html_parser.parse_ctf_html(body)
        elif fmt == "html" and insurer == "CLO":
            parsed = clo_html_parser.parse_clo_html(body)
        elif fmt == "html" and insurer == "SUN":
            parsed = multi_html_parser.parse_sun_html(body)
        elif fmt == "html" and insurer == "BOC":
            parsed = multi_html_parser.parse_boc_html(body)
        elif fmt == "html" and insurer == "YFL":
            parsed = yfl_api.parse_bundle(body)
        elif fmt == "html" and insurer in ("AXA", "FWD"):
            parsed = nextjs_ratio.parse_bundle(body)
        elif is_rbc:
            parsed = rbc_parser.parse_rbc(body)
        else:
            base["result"] = "UNSUPPORTED_FORMAT"
            base["message"] = (
                f"暂未接入 format={fmt!r} insurer={insurer!r} 的解析"
                f"（已接入：AIA JSON、CTF/CLO/SUN/BOC HTML、PRUGI/AIACO RBC PDF；其余 HTML/PDF 待后续任务）"
            )
            return base
    except rbc_parser.RbcParseError as e:
        base["result"] = "STRUCTURE_MISMATCH"
        base["parse_status"] = "STRUCTURE_MISMATCH"
        base["error_code"] = "STRUCTURE_MISMATCH"
        base["message"] = str(e)
        return _record_parse_failure(conn, run_id, base, "STRUCTURE_MISMATCH", "STRUCTURE_MISMATCH", str(e))
    except pdf_text.PdfNoTextError as e:
        base["result"] = "STRUCTURE_MISMATCH"
        base["parse_status"] = "STRUCTURE_MISMATCH"
        base["error_code"] = "PDF_NO_TEXT"
        base["message"] = str(e)
        return _record_parse_failure(conn, run_id, base, "STRUCTURE_MISMATCH", "PDF_NO_TEXT", str(e))
    except (pdf_text.PdfNotPdfError, pdf_text.PdfExtractionError) as e:
        base["result"] = "STRUCTURE_MISMATCH"
        base["parse_status"] = "STRUCTURE_MISMATCH"
        base["error_code"] = "STRUCTURE_MISMATCH"
        base["message"] = str(e)
        return _record_parse_failure(conn, run_id, base, "STRUCTURE_MISMATCH", "STRUCTURE_MISMATCH", str(e))
    except (
        aia_json_parser.AiaParseError,
        ctf_html_parser.CtfParseError,
        clo_html_parser.CloParseError,
        multi_html_parser.MultiHtmlParseError,
        yfl_api.YflApiError,
        nextjs_ratio.NextRatioError,
    ) as e:
        base["result"] = "STRUCTURE_MISMATCH"
        base["parse_status"] = "STRUCTURE_MISMATCH"
        base["error_code"] = "STRUCTURE_MISMATCH"
        base["message"] = str(e)
        return _record_parse_failure(conn, run_id, base, "STRUCTURE_MISMATCH", "STRUCTURE_MISMATCH", str(e))

    status = parsed["status"]
    records = parsed["records"]
    value_unparseable = parsed["value_unparseable"]
    base["report_year"] = parsed["report_year"]
    base["product_count"] = parsed["product_count"]
    base["value_unparseable"] = value_unparseable

    # 第三项决策补充：只要存在无法数值化但保留原文的观测项，parse_result 写 PARTIAL
    # + VALUE_UNPARSEABLE（软失败），记录数仍包含这些原始观测项，不静默丢弃。
    # RBC 单条声明无该软失败语义（金额可选、缺失即 NULL，属 OK）。
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

    if is_rbc:
        message = (
            f"report_year={parsed['report_year']}, records={len(records)}, "
            f"solvency_ratio_raw={records[0]['solvency_ratio_raw'] if records else None}"
        )
    else:
        message = (
            f"products={parsed['product_count']}, records={len(records)}, "
            f"value_unparseable={value_unparseable}"
        )

    # 4) 事务入库（OK/PARTIAL 写全部业务行；ZERO_RECORD 只写 parse_result，不写业务表）
    try:
        if is_rbc:
            n = rbc_writer.write_rbc_outcome(
                conn, run_id, insurer, records, parse_status, error_code, message,
            )
        else:
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
