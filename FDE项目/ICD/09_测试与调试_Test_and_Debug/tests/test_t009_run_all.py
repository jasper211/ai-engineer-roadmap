#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD 集成测试（T009）· 全量运行编排、摘要与 coverage_status 闭环（L3-ICD-06）

覆盖任务书 T009 验收标准（确定性部分，不联网除本机临时 HTTP 服务器）：
- classify_source 动作矩阵：成功/HTTP 失败/结构失败/未接入/BLOCKED/UNVERIFIED/
  requires_browser/索引发现歧义/后一源仍继续。
- coverage_status 逐项断言（状态/时间/错误字段），重复运行行数不变，integrity/FK 通过。
- --no-network 基于既有快照完成解析/汇总（不重复、不污染业务行）。
- 摘要 JSON+Markdown 写入受控目录，run_id 唯一、不覆盖历史、不含凭证。
- CLI --run-all / --no-network 端到端；--validate-config 无回归。
全部写操作在 tempfile 内，不污染默认数据库与 summaries 目录。

运行：python3 09_测试与调试_Test_and_Debug/tests/test_t009_run_all.py
"""

import http.server
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent                 # tests/
NUMBERED_DIR = TESTS_DIR.parent                             # 09_测试与调试_Test_and_Debug/
ICD_DIR = NUMBERED_DIR.parent                               # FDE项目/ICD/

for _pkg_dir in (
    "05_集成工具_Integrate_Tools",
    "07_接入记忆_Integrate_Memory",
    "06_开发技能_Develop_Skills",
):
    sys.path.insert(0, str(ICD_DIR / _pkg_dir))

from skills import run_all, summary_writer
from tools import coverage_writer, fetch_recorder, sqlite_store

AGENT_PY = ICD_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"
AIA_FIXTURE = TESTS_DIR / "fixtures" / "aia_fixture.json"

FAILURES = []


def check(cond, ok_msg, fail_msg=""):
    if cond:
        print(f"✅ {ok_msg}")
    else:
        print(f"❌ {fail_msg or ok_msg}")
        FAILURES.append(fail_msg or ok_msg)


def _pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _make_pdf_with_text(lines) -> bytes:
    """最小合法单页 PDF（复用 T008 同款生成器，无第三方库）。"""
    content = []
    y = 720
    for ln in lines:
        content.append(f"BT /F1 12 Tf 72 {y} Td ({_pdf_escape(ln)}) Tj ET")
        y -= 16
    stream = "\n".join(content).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objs) + 1)
    out += b"startxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


def _pru_pdf_bytes():
    return _make_pdf_with_text([
        "Prudential General Insurance Hong Kong Limited",
        "Disclosure Statement",
        "At 31 December 2024",
        "1 Company profile",
        "Authorized insurer's name",
        "Prudential General Insurance Hong Kong Limited",
        "4 Capital adequacy",
        "Unit: in HKD thousands As at 31 December 2024",
        "Ratio of capital base to prescribed capital amount 290%",
        "Capital base 581,167",
        "Prescribed capital amount 200,745",
    ])


class _LocalServer:
    def __init__(self, routes):
        # routes: {path: (bytes, content_type)}
        self.routes = routes
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path not in outer.routes:
                    self.send_response(404)
                    self.end_headers()
                    return
                body, ctype, status = outer.routes[self.path]
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Type", ctype)
                self.end_headers()
                self.wfile.write(body)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _local_registry(base_url):
    """T009 本地测试注册表：9 源覆盖成功/HTTP失败/结构失败/未接入/BLOCKED/UNVERIFIED/浏览器/索引歧义/后一源继续。"""
    return {
        "schema_version": "1.3",
        "generated_at": "2026-09-04",
        "description": "T009 本地测试注册表",
        "insurers": [
            {"insurer_code": "AIA", "name_en": "AIA International Limited", "name_zh": "友邦保险"},
            {"insurer_code": "CTF", "name_en": "Chow Tai Fook Life Insurance Company Limited", "name_zh": "周大福人寿"},
            {"insurer_code": "CLO", "name_en": "China Life Insurance (Overseas) Company Limited", "name_zh": "中国人寿保险（海外）"},
            {"insurer_code": "AXA", "name_en": "AXA China Region Insurance Company Limited", "name_zh": "安盛保险"},
            {"insurer_code": "MAN", "name_en": "Manulife (International) Limited", "name_zh": "宏利保险"},
            {"insurer_code": "FWD", "name_en": "FWD Life Insurance Company (Bermuda) Limited", "name_zh": "富卫人寿"},
            {"insurer_code": "PRUGI", "name_en": "Prudential General Insurance Hong Kong Limited", "name_zh": "保诚一般保险（香港）"},
        ],
        "sources": [
            {   # 1) 成功（AIA json）
                "insurer_code": "AIA", "disclosure_type": "fulfillment_ratio",
                "entry_url": f"{base_url}/aia.json", "format": "json",
                "access_status": "OPEN", "parser_hint": "AIA 静态 JSON",
                "requires_browser": False, "evidence_basis": "T009 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-04", "url_version": 1,
            },
            {   # 2) HTTP 失败（CTF html，服务器返回 500）
                "insurer_code": "CTF", "disclosure_type": "fulfillment_ratio",
                "entry_url": f"{base_url}/ctf_500.html", "format": "html",
                "access_status": "OPEN", "parser_hint": "CTF 纯 HTML 表格",
                "requires_browser": False, "evidence_basis": "T009 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-04", "url_version": 1,
            },
            {   # 3) 结构失败（CLO html，缺内嵌 JS 数组）
                "insurer_code": "CLO", "disclosure_type": "fulfillment_ratio",
                "entry_url": f"{base_url}/clo_bad.html", "format": "html",
                "access_status": "OPEN", "parser_hint": "CLO 内嵌 JS 数组",
                "requires_browser": False, "evidence_basis": "T009 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-04", "url_version": 1,
            },
            {   # 4) 未接入（AXA html）
                "insurer_code": "AXA", "disclosure_type": "fulfillment_ratio",
                "entry_url": f"{base_url}/axa.html", "format": "html",
                "access_status": "OPEN", "parser_hint": "Next.js SSR，未接入",
                "requires_browser": False, "evidence_basis": "T009 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-04", "url_version": 1,
            },
            {   # 5) BLOCKED
                "insurer_code": "MAN", "disclosure_type": "fulfillment_ratio",
                "entry_url": f"{base_url}/man.html", "format": None,
                "access_status": "BLOCKED", "parser_hint": "全站 Akamai 拦截",
                "requires_browser": True, "evidence_basis": "T009 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-04", "url_version": 1,
            },
            {   # 6) UNVERIFIED
                "insurer_code": "CTF", "disclosure_type": "rbc",
                "entry_url": None, "format": None,
                "access_status": "UNVERIFIED", "parser_hint": "未实测 RBC URL",
                "requires_browser": False, "evidence_basis": "T009 本地服务器",
                "allows_empty": False, "last_verified_at": None, "url_version": 1,
            },
            {   # 7) requires_browser（OPEN + requires_browser=true）
                "insurer_code": "FWD", "disclosure_type": "fulfillment_ratio",
                "entry_url": f"{base_url}/fwd.html", "format": "html",
                "access_status": "OPEN", "parser_hint": "需浏览器 JS 挑战",
                "requires_browser": True, "evidence_basis": "T009 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-04", "url_version": 1,
            },
            {   # 8) 索引发现歧义（AIA rbc html，无文件名消歧提示）
                "insurer_code": "AIA", "disclosure_type": "rbc",
                "entry_url": f"{base_url}/index.html", "format": "html",
                "access_status": "OPEN", "parser_hint": "监管披露索引（无目标文件名提示）",
                "requires_browser": False, "evidence_basis": "T009 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-04", "url_version": 1,
            },
            {   # 9) 后一源仍继续（PRUGI rbc pdf）
                "insurer_code": "PRUGI", "disclosure_type": "rbc",
                "entry_url": f"{base_url}/pru.pdf", "format": "pdf",
                "access_status": "OPEN", "parser_hint": "Prudential GI 2024 RBC PDF",
                "requires_browser": False, "evidence_basis": "T009 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-04", "url_version": 1,
            },
        ],
    }


def _ambig_index_html():
    """含两个满足「官方域名/2024/英文/Disclosure Statement」约束的候选 PDF。"""
    return (
        "<html><body>"
        '<a href="https://www.aia.com/content/dam/x/AIA%20Co%20Disclosure%20Statement%202024_Eng.pdf">Disclosure statement</a>'
        '<a href="https://www.aia.com/content/dam/x/AIAI%20Disclosure%20Statement%202024_Eng.pdf">Disclosure statement</a>'
        "</body></html>"
    ).encode("utf-8")


def _routes():
    return {
        "/aia.json": (AIA_FIXTURE.read_bytes(), "application/json", 200),
        "/ctf_500.html": (b"<html>error</html>", "text/html", 500),
        "/clo_bad.html": (b"<html><body>no script data</body></html>", "text/html", 200),
        "/axa.html": (b"<html><body>axa next data</body></html>", "text/html", 200),
        "/fwd.html": (b"<html><body>js challenge</body></html>", "text/html", 200),
        "/index.html": (_ambig_index_html(), "text/html", 200),
        "/pru.pdf": (_pru_pdf_bytes(), "application/pdf", 200),
    }


def _init(db, raw_root, reg):
    sqlite_store.init_db(db, reg, raw_data_root=raw_root)
    return sqlite_store.connect(db)


def _read_coverage(conn, insurer, dtype):
    return coverage_writer.read_coverage(conn, insurer, dtype)


# ---------------------------------------------------------------------------
# T009-1 · classify_source 动作矩阵（纯函数）
# ---------------------------------------------------------------------------
def test_classify():
    print("\n[T009-1] classify_source 动作矩阵")
    print("-" * 60)
    cases = [
        ({"access_status": "BLOCKED", "requires_browser": 0}, "skip_blocked"),
        ({"access_status": "UNVERIFIED", "requires_browser": 0}, "skip_unverified"),
        ({"access_status": "OPEN", "requires_browser": 1}, "skip_browser"),
        ({"access_status": "OPEN", "disclosure_type": "rbc", "format": "html", "requires_browser": 0}, "discover"),
        ({"access_status": "OPEN", "disclosure_type": "fulfillment_ratio", "format": "json", "insurer_code": "AIA", "requires_browser": 0}, "fetch_parse"),
        ({"access_status": "OPEN", "disclosure_type": "fulfillment_ratio", "format": "html", "insurer_code": "CTF", "requires_browser": 0}, "fetch_parse"),
        ({"access_status": "OPEN", "disclosure_type": "rbc", "format": "pdf", "insurer_code": "PRUGI", "requires_browser": 0}, "fetch_parse"),
        ({"access_status": "OPEN", "disclosure_type": "fulfillment_ratio", "format": "html", "insurer_code": "AXA", "requires_browser": 0}, "fetch_parse"),
        ({"access_status": "PARTIAL", "disclosure_type": "fulfillment_ratio", "format": "pdf", "insurer_code": "PRU", "requires_browser": 0}, "unsupported"),
    ]
    for src, expected in cases:
        got = run_all.classify_source(src)
        check(got == expected, f"{src.get('insurer_code','?')}/{src.get('disclosure_type','?')} → {expected}", f"got {got}, expected {expected}")


# ---------------------------------------------------------------------------
# T009-2 · coverage_for_pair 优先级 + coverage_writer upsert
# ---------------------------------------------------------------------------
def test_coverage_priority():
    print("\n[T009-2] coverage_for_pair 优先级 + upsert（含 PARTIAL=值不可数值化仍成功）")
    print("-" * 60)
    def e(**kw):
        base = {"action": "fetch_parse", "records_written": 0, "run_id": None, "error_code": None}
        base.update(kw)
        return base
    check(run_all.coverage_for_pair([e(action="skip_blocked")])["coverage_status"] == "BLOCKED", "全部 BLOCKED → BLOCKED")
    check(run_all.coverage_for_pair([e(action="skip_unverified")])["coverage_status"] == "UNVERIFIED", "全部 UNVERIFIED → UNVERIFIED")
    check(run_all.coverage_for_pair([e(action="unsupported")])["coverage_status"] == "MISSING", "未接入 → MISSING")
    check(run_all.coverage_for_pair([e(action="fetch_parse", records_written=5, run_id=1)])["coverage_status"] == "FULL", "单源成功 → FULL")
    # 关键语义：PARTIAL（值不可数值化）仍 records_written>0 → 覆盖成功
    check(run_all.coverage_for_pair([e(action="fetch_parse", records_written=14, run_id=1, parse_status="PARTIAL")])["coverage_status"] == "FULL",
          "parse_result=PARTIAL 但 records>0 → 仍 FULL（不误判覆盖缺失）")
    check(run_all.coverage_for_pair([
        e(action="fetch_parse", records_written=5, run_id=1),
        e(action="unsupported"),
    ])["coverage_status"] == "PARTIAL", "一成功一未接入 → PARTIAL")
    check(run_all.coverage_for_pair([e(action="fetch_parse", records_written=0, error_code="HTTP_5XX")])["coverage_status"] == "MISSING",
          "全部失败 → MISSING（保留 error_code）")
    m = run_all.coverage_for_pair([e(action="fetch_parse", records_written=0, error_code="HTTP_5XX")])
    check(m["last_error_code"] == "HTTP_5XX", "MISSING 记录 last_error_code=HTTP_5XX", f"err: {m['last_error_code']}")

    # upsert 幂等 + 保留历史成功
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        reg = _local_registry("http://127.0.0.1:1")
        sqlite_store.init_db(db, reg, raw_data_root=Path(td) / "raw")
        conn = sqlite_store.connect(db)
        # 造一个合法 fetch_run（NETWORK_ERROR 行）供 last_success_run_id FK 引用
        conn.execute("INSERT INTO fetch_run (source_id, fetch_status) VALUES (1, 'NETWORK_ERROR')")
        conn.commit()
        coverage_writer.upsert_coverage(conn, "AIA", "fulfillment_ratio", "FULL",
                                        last_success_run_id=1, last_attempt_at="t1", last_success_at="t1")
        conn.commit()
        coverage_writer.upsert_coverage(conn, "AIA", "fulfillment_ratio", "MISSING",
                                        last_attempt_at="t2", last_error_code="HTTP_5XX", last_error_message="boom")
        conn.commit()
        r = _read_coverage(conn, "AIA", "fulfillment_ratio")
        check(r["coverage_status"] == "MISSING", "二次 upsert 覆盖状态为 MISSING")
        check(r["last_success_at"] == "t1", "失败保留上次成功时间（不擦除）", f"lsa: {r['last_success_at']}")
        check(r["last_success_run_id"] == 1, "失败保留 last_success_run_id", f"lsrid: {r['last_success_run_id']}")
        check(r["last_error_code"] == "HTTP_5XX", "失败写入 last_error_code")
        conn.close()


# ---------------------------------------------------------------------------
# T009-3 · 全量批次端到端（8 类场景 + coverage 逐项断言 + 后一源继续）
# ---------------------------------------------------------------------------
def test_full_batch():
    print("\n[T009-3] 全量批次：单源隔离 + coverage_status 逐项断言 + 后一源继续")
    print("-" * 60)
    srv = _LocalServer(_routes())
    try:
        reg = _local_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root, summary_dir = td / "icd.db", td / "raw", td / "summaries"
            conn = _init(db, raw_root, reg)
            summary = run_all.run_all(conn, raw_root, summary_dir=summary_dir)
            conn.close()

            # 计数
            c = summary["counts"]
            check(c["processed"] == 6 and c["succeeded"] == 2 and c["failed"] == 4 and c["skipped"] == 3 and c["unsupported"] == 0,
                  f"counts processed=6/succeeded=2/failed=4/skipped=3/unsupported=0（实际 {c}）", f"counts: {c}")

            # 逐源：后一源（source_id=9 PRUGI）仍继续成功
            by_id = {e["source_id"]: e for e in summary["sources"]}
            check(by_id[1]["parse_status"] == "OK" and by_id[1]["parse_detail"] == "PARTIAL" and (by_id[1]["records_written"] or 0) > 0,
                  f"source_id=1 成功且值部分不可数值化 OK(PARTIAL)，records={by_id[1]['records_written']}", f"s1: {by_id[1]}")
            check(by_id[2]["fetch_status"] == "HTTP_ERROR", f"source_id=2 HTTP 失败（{by_id[2]['fetch_status']}）", f"s2: {by_id[2]}")
            check(by_id[3]["parse_status"] == "STRUCTURE_MISMATCH", f"source_id=3 结构失败（{by_id[3]['parse_status']}）", f"s3: {by_id[3]}")
            check(by_id[4]["action"] == "fetch_parse" and by_id[4]["fetch_status"] == "NETWORK_ERROR",
                  f"source_id=4 已接入且坏 Next.js 结构显式失败（{by_id[4]['fetch_status']}）", f"s4: {by_id[4]}")
            check(by_id[5]["action"] == "skip_blocked", f"source_id=5 BLOCKED 跳过", f"s5: {by_id[5]}")
            check(by_id[6]["action"] == "skip_unverified", f"source_id=6 UNVERIFIED 跳过", f"s6: {by_id[6]}")
            check(by_id[7]["action"] == "skip_browser", f"source_id=7 requires_browser 跳过", f"s7: {by_id[7]}")
            check(by_id[8]["parse_status"] == "AMBIGUOUS_OR_NO_MATCH", f"source_id=8 索引歧义（{by_id[8]['parse_status']}）", f"s8: {by_id[8]}")
            check(by_id[9]["parse_status"] == "OK" and (by_id[9]["records_written"] or 0) == 1,
                  f"source_id=9 后一源仍继续成功（records={by_id[9]['records_written']}）", f"s9: {by_id[9]}")

            # coverage 逐项
            conn = sqlite_store.connect(db)
            exp = {
                ("AIA", "fulfillment_ratio"): "FULL",
                ("CTF", "fulfillment_ratio"): "MISSING",
                ("CLO", "fulfillment_ratio"): "MISSING",
                ("AXA", "fulfillment_ratio"): "MISSING",
                ("MAN", "fulfillment_ratio"): "BLOCKED",
                ("CTF", "rbc"): "UNVERIFIED",
                ("FWD", "fulfillment_ratio"): "BLOCKED",
                ("AIA", "rbc"): "MISSING",
                ("PRUGI", "rbc"): "FULL",
            }
            for (ins, dtype), want in exp.items():
                r = _read_coverage(conn, ins, dtype)
                check(r is not None and r["coverage_status"] == want,
                      f"coverage {ins}/{dtype} = {want}", f"{ins}/{dtype}: {r}")
                check(r["last_attempt_at"] is not None and r["last_checked_at"] == r["last_attempt_at"],
                      f"coverage {ins}/{dtype} last_attempt_at/last_checked_at 已写", f"{ins}/{dtype}: {r}")
            # 成功对 last_success_at 已写、无错误码
            r_ok = _read_coverage(conn, "AIA", "fulfillment_ratio")
            check(r_ok["last_success_at"] is not None and r_ok["last_success_run_id"] is not None and r_ok["last_error_code"] is None,
                  "成功对 last_success_at/run_id 已写、last_error_code=NULL", f"r_ok: {r_ok}")
            # 失败对记录 error_code
            r_ctf = _read_coverage(conn, "CTF", "fulfillment_ratio")
            check(r_ctf["last_error_code"] == "HTTP_5XX", f"CTF/fulfillment last_error_code=HTTP_5XX（{r_ctf['last_error_code']}）", f"r_ctf: {r_ctf}")
            r_aia_rbc = _read_coverage(conn, "AIA", "rbc")
            check(r_aia_rbc["last_error_code"] == "STRUCTURE_MISMATCH", f"AIA/rbc 歧义 last_error_code=STRUCTURE_MISMATCH（{r_aia_rbc['last_error_code']}）", f"r_aia_rbc: {r_aia_rbc}")

            # coverage 行数 = 9 个自然键
            n = conn.execute("SELECT COUNT(*) FROM coverage_status").fetchone()[0]
            check(n == 9, f"coverage_status 行数 = 9（{n}）", f"n: {n}")

            # integrity / FK
            check(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity_check=ok", "integrity 失败")
            check(conn.execute("PRAGMA foreign_key_check").fetchall() == [], "foreign_key_check=[]", "FK 违例")

            # 业务行：AIA fulfillment > 0，PRUGI rbc = 1
            nfr = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            nrbc = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
            check(nfr > 0 and nrbc == 1, f"业务行 fulfillment={nfr} / rbc={nrbc}", f"nfr={nfr}, nrbc={nrbc}")
            conn.close()

            # 摘要文件
            files = summary["summary_files"]
            check(Path(files["json_path"]).exists() and Path(files["markdown_path"]).exists(),
                  f"摘要 JSON+MD 已写入（{files['json_path']}）", f"files: {files}")
            check("cookie" not in json.dumps(summary).lower() and "authorization" not in json.dumps(summary).lower(),
                  "摘要不含 Cookie/凭证/完整请求头", "")
            return db, raw_root, summary_dir, summary
    finally:
        srv.stop()
    return None


# ---------------------------------------------------------------------------
# T009-4 · 幂等：重复批次不重复业务行/coverage 行，摘要 run_id 唯一不覆盖
# ---------------------------------------------------------------------------
def test_idempotency_and_unique_run_id():
    print("\n[T009-4] 幂等：重复批次行数不变 + 摘要 run_id 唯一不覆盖")
    print("-" * 60)
    srv = _LocalServer(_routes())
    try:
        reg = _local_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root, summary_dir = td / "icd.db", td / "raw", td / "summaries"
            conn = _init(db, raw_root, reg)
            s1 = run_all.run_all(conn, raw_root, summary_dir=summary_dir)
            conn.close()
            conn = sqlite_store.connect(db)
            fr1 = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            rbc1 = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
            cov1 = conn.execute("SELECT COUNT(*) FROM coverage_status").fetchone()[0]
            s2 = run_all.run_all(conn, raw_root, summary_dir=summary_dir)
            conn.close()
            conn = sqlite_store.connect(db)
            fr2 = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            rbc2 = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
            cov2 = conn.execute("SELECT COUNT(*) FROM coverage_status").fetchone()[0]
            conn.close()
            check(fr1 == fr2 and rbc1 == rbc2, f"业务行不变 fulfillment={fr1}→{fr2} rbc={rbc1}→{rbc2}", f"{fr1}/{fr2} {rbc1}/{rbc2}")
            check(cov1 == cov2 == 9, f"coverage 行数不变（{cov1}→{cov2}）", f"{cov1}/{cov2}")
            check(s1["run_id"] != s2["run_id"], f"两次 run_id 唯一（{s1['run_id']} ≠ {s2['run_id']}）", "run_id 重复")
            jsons = sorted(summary_dir.glob("*.json"))
            mds = sorted(summary_dir.glob("*.md"))
            check(len(jsons) == 2 and len(mds) == 2, f"摘要文件不覆盖（2 JSON + 2 MD，实际 {len(jsons)}/{len(mds)}）", f"{len(jsons)}/{len(mds)}")
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# T009-5 · --no-network：基于既有快照完成解析/汇总，业务行不重复
# ---------------------------------------------------------------------------
def test_no_network():
    print("\n[T009-5] --no-network：既有快照完成解析/汇总，业务行不重复")
    print("-" * 60)
    srv = _LocalServer(_routes())
    try:
        reg = _local_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root, summary_dir = td / "icd.db", td / "raw", td / "summaries"
            conn = _init(db, raw_root, reg)
            run_all.run_all(conn, raw_root, summary_dir=summary_dir)  # 网络跑一遍（产出快照+业务行）
            conn.close()
            conn = sqlite_store.connect(db)
            fr_before = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            rbc_before = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
            s = run_all.run_all(conn, raw_root, no_network=True, summary_dir=summary_dir)
            conn.close()
            check(s["mode"] == "no_network", f"mode=no_network（{s['mode']}）", f"mode: {s['mode']}")
            # 成功源 fetch_status = NO_NETWORK
            by_id = {e["source_id"]: e for e in s["sources"]}
            check(by_id[1]["fetch_status"] == "NO_NETWORK" and (by_id[1]["records_written"] or 0) > 0,
                  f"no-network 下 source_id=1 复用快照解析（records={by_id[1]['records_written']}）", f"s1: {by_id[1]}")
            check(by_id[9]["fetch_status"] == "NO_NETWORK" and (by_id[9]["records_written"] or 0) == 1,
                  f"no-network 下 source_id=9 复用快照解析（records={by_id[9]['records_written']}）", f"s9: {by_id[9]}")
            conn = sqlite_store.connect(db)
            fr_after = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            rbc_after = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
            conn.close()
            check(fr_before == fr_after and rbc_before == rbc_after,
                  f"业务行不重复 fulfillment={fr_before}→{fr_after} rbc={rbc_before}→{rbc_after}", f"{fr_before}/{fr_after} {rbc_before}/{rbc_after}")
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# T009-6 · CLI --run-all 端到端 + 未初始化硬失败 + --validate-config
# ---------------------------------------------------------------------------
def test_cli_run_all():
    print("\n[T009-6] CLI --run-all / --no-network / 未初始化硬失败 / --validate-config")
    print("-" * 60)
    def _run_cli(args, cwd=ICD_DIR):
        return subprocess.run(
            [sys.executable, str(AGENT_PY)] + args,
            cwd=str(cwd), capture_output=True, text=True,
        )

    r = _run_cli(["--validate-config"])
    check(r.returncode == 0, f"--validate-config EXIT=0（{r.returncode}）", f"stderr: {r.stderr}")

    # 未初始化 DB → --run-all 硬失败 exit 1
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        empty_db = td / "empty.db"
        r = _run_cli(["--run-all", "--db-path", str(empty_db), "--summaries-root", str(td / "s")])
        check(r.returncode == 1, f"未初始化 --run-all EXIT=1（{r.returncode}）", f"rc: {r.returncode}")

    # 端到端 --run-all（本地服务器 + 临时 DB + 临时 registry）
    srv = _LocalServer(_routes())
    try:
        reg = _local_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root, summary_dir = td / "icd.db", td / "raw", td / "summaries"
            reg_file = td / "reg.json"
            reg_file.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

            r = _run_cli(["--init-db", "--registry", str(reg_file), "--db-path", str(db)])
            check(r.returncode == 0, f"--init-db EXIT=0（{r.returncode}）", f"init-db: {r.stderr}")

            r = _run_cli(["--run-all", "--registry", str(reg_file), "--db-path", str(db),
                          "--raw-data-root", str(raw_root), "--summaries-root", str(summary_dir)])
            check(r.returncode == 0, f"--run-all EXIT=0（{r.returncode}）", f"run-all: {r.stderr}")
            data = json.loads(r.stdout)
            check(data["mode"] == "network", f"CLI 摘要 mode=network（{data['mode']}）", f"mode: {data['mode']}")
            check(data["counts"]["succeeded"] == 2, f"CLI 摘要 succeeded=2（{data['counts']['succeeded']}）", f"counts: {data['counts']}")
            check(Path(data["summary_files"]["json_path"]).exists(), "CLI 摘要 JSON 存在", f"files: {data['summary_files']}")
    finally:
        srv.stop()


def main():
    test_classify()
    test_coverage_priority()
    test_full_batch()
    test_idempotency_and_unique_run_id()
    test_no_network()
    test_cli_run_all()

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"❌ 失败 {len(FAILURES)} 项：")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("✅ ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
