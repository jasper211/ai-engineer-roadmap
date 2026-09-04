#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD 集成测试（T007）· Prudential RBC 披露声明 PDF 解析、标准化、事务入库

覆盖任务书 T007 验收标准：
- fixture 与真实证据分离（本文件只跑脱敏 fixture + 生成的最小 PDF；真实验证单独记录）。
- 覆盖：官方语句邻域、290%→2.90、报告年度、币种、可选金额、跨行断词、重复候选歧义、
  无文字层/错误格式、幂等、事务回滚、零记录。
- 不把 290% 写死为解析结果（解析器从 PDF 文本独立提取，另有 304%/110% 泛化断言）。
- 不联网（除本机临时 HTTP 服务器）；所有写操作在 tempfile 内，不污染默认数据库。

运行：python3 09_测试与调试_Test_and_Debug/tests/test_t007_parse.py
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
REPO_ROOT = ICD_DIR.parent.parent                           # 仓库根
FIXTURE_PATH = TESTS_DIR / "fixtures" / "pru_rbc_fixture.json"

for _pkg_dir in (
    "05_集成工具_Integrate_Tools",
    "07_接入记忆_Integrate_Memory",
    "06_开发技能_Develop_Skills",
):
    sys.path.insert(0, str(ICD_DIR / _pkg_dir))

from skills import fetch_disclosure, parse_disclosure, pdf_text, pru_rbc_parser
from tools import fetch_recorder, rbc_writer, snapshot, sqlite_store

AGENT_PY = ICD_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"

FAILURES = []


def check(cond, ok_msg, fail_msg=""):
    if cond:
        print(f"✅ {ok_msg}")
    else:
        print(f"❌ {fail_msg or ok_msg}")
        FAILURES.append(fail_msg or ok_msg)


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 最小 PDF 生成器（合法单页 PDF；无第三方库，字节偏移自算）
# ---------------------------------------------------------------------------
def _pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _make_pdf_with_text(lines) -> bytes:
    """生成最小合法单页 PDF，用 Helvetica 逐行显示文本（供 pdfplumber 提取）。"""
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


def _make_blank_pdf() -> bytes:
    """生成无文字层的最小合法 PDF（用于 PDF_NO_TEXT 测试）。"""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
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


# 端到端用最小 PDF 文本（只含语义邻域关键锚点）
def _e2e_pdf_lines():
    return [
        "Disclosure Statement at 31 December 2024",
        "1 Company profile",
        "Authorized insurer's name",
        "Prudential General Insurance Hong Kong Limited",
        "4 Capital adequacy",
        "Unit: in HKD thousands As at 31 December 2024",
        "Ratio of capital base to prescribed capital amount 290%",
        "Capital base 581,167",
        "Prescribed capital amount 200,745",
    ]


# ---------------------------------------------------------------------------
# 本机临时 HTTP 服务器
# ---------------------------------------------------------------------------
class _LocalServer:
    def __init__(self, body: bytes, content_type="application/pdf"):
        self.body = body
        self.content_type = content_type
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(outer.body)))
                self.send_header("Content-Type", outer.content_type)
                self.end_headers()
                self.wfile.write(outer.body)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def build_registry(base_url):
    """T007 本地测试注册表：PRUGI rbc（pdf）。source_id=1。"""
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-03",
        "description": "T007 本地测试注册表",
        "insurers": [{"insurer_code": "PRUGI", "name_en": "Prudential General Insurance Hong Kong Limited", "name_zh": "保诚一般保险（香港）有限公司"}],
        "sources": [
            {
                "insurer_code": "PRUGI", "disclosure_type": "rbc",
                "entry_url": f"{base_url}/rbc.pdf", "format": "pdf",
                "access_status": "OPEN", "parser_hint": "local test",
                "requires_browser": False, "evidence_basis": "T007 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-03", "url_version": 1,
            }
        ],
    }


def _run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, str(AGENT_PY)] + args,
        cwd=str(cwd), capture_output=True, text=True,
    )


def _pages(text: str, tables=None):
    return [{"text": text, "tables": tables or []}]


# ---------------------------------------------------------------------------
# T007-1 · 百分比解析（泛化，证明未写死 290%）
# ---------------------------------------------------------------------------
def test_parse_pct_unit():
    print("\n[T007-1] 百分比解析：290%→2.90 / 304%→3.04 / 110%→1.10 / N.A.→None")
    print("-" * 60)
    check(pru_rbc_parser._parse_pct_to_ratio("290%") == 2.90, "290% → 2.90", "290% 解析错误")
    check(pru_rbc_parser._parse_pct_to_ratio("304%") == 3.04, "304% → 3.04（泛化，非写死 290）", "304% 解析错误")
    check(pru_rbc_parser._parse_pct_to_ratio("110%") == 1.10, "110% → 1.10", "110% 解析错误")
    check(pru_rbc_parser._parse_pct_to_ratio("290.5%") == 2.905, "290.5% → 2.905", "290.5% 解析错误")
    check(pru_rbc_parser._parse_pct_to_ratio("N/A") is None, "'N/A' → None", "'N/A' 未判 None")
    check(pru_rbc_parser._parse_pct_to_ratio("-") is None, "'-' → None", "'-' 未判 None")


# ---------------------------------------------------------------------------
# T007-2 · 金额解析（千分位 / '-' / 括号负数）
# ---------------------------------------------------------------------------
def test_parse_amount_unit():
    print("\n[T007-2] 金额解析：581,167→581167 / '-'→None / (853)→-853")
    print("-" * 60)
    check(pru_rbc_parser._parse_amount("581,167") == 581167.0, "581,167 → 581167.0", "金额解析错误")
    check(pru_rbc_parser._parse_amount("200,745") == 200745.0, "200,745 → 200745.0", "金额解析错误")
    check(pru_rbc_parser._parse_amount("-") is None, "'-' → None（未披露，不推算）", "'-' 未判 None")
    check(pru_rbc_parser._parse_amount("N/A") is None, "'N/A' → None", "'N/A' 未判 None")
    check(pru_rbc_parser._parse_amount("(853)") == -853.0, "(853) → -853.0（风险分解负值）", "括号负数错误")
    check(pru_rbc_parser._parse_amount("1,234.5") == 1234.5, "1,234.5 → 1234.5", "小数金额错误")


# ---------------------------------------------------------------------------
# T007-3 · PDF 签名校验
# ---------------------------------------------------------------------------
def test_pdf_signature():
    print("\n[T007-3] PDF 签名：%PDF→True / HTML→False")
    print("-" * 60)
    check(pdf_text.has_pdf_signature(b"%PDF-1.7\n...") is True, "%PDF 签名 → True", "PDF 签名误判")
    check(pdf_text.has_pdf_signature(b"<html><body>error</body></html>") is False,
          "HTML 错误页 → False", "HTML 误判为 PDF")


# ---------------------------------------------------------------------------
# T007-4 · 官方语句邻域 fixture（290%→2.90 / 年度 / 币种 / 可选金额）
# ---------------------------------------------------------------------------
def test_fixture_official_neighborhood():
    print("\n[T007-4] 官方语句邻域：290%→2.90 / 2024 / HKD / 金额 / 风险分解 JSON")
    print("-" * 60)
    fx = load_fixture()
    r = pru_rbc_parser.extract_rbc(fx["pages"])
    check(r["status"] == "OK", f"status=OK（{r['status']}）", f"status: {r['status']}")
    check(r["report_year"] == 2024, f"report_year=2024（{r['report_year']}）", f"report_year: {r['report_year']}")
    rec = r["records"][0]
    check(rec["legal_entity_name_raw"] == "Prudential General Insurance Hong Kong Limited",
          "legal_entity_name_raw='Prudential General Insurance Hong Kong Limited'（法律主体原文）",
          f"legal_entity_name_raw: {rec['legal_entity_name_raw']}")
    check(rec["solvency_ratio"] == 2.90, "solvency_ratio=2.90", f"solvency_ratio: {rec['solvency_ratio']}")
    check(rec["solvency_ratio_raw"] == "290%", "solvency_ratio_raw='290%'（保留原文）", f"raw: {rec['solvency_ratio_raw']}")
    check(rec["currency"] == "HKD", "currency=HKD", f"currency: {rec['currency']}")
    check(rec["amount_unit_raw"] == "in HKD thousands", "amount_unit_raw='in HKD thousands'（单位原文）", f"amount_unit_raw: {rec['amount_unit_raw']}")
    check(rec["amount_scale"] == "thousands", "amount_scale='thousands'（规范化标度）", f"amount_scale: {rec['amount_scale']}")
    check(rec["capital_base"] == 581167000.0, "capital_base=581,167 thousand→581167000.0",
          f"capital_base: {rec['capital_base']}")
    check(rec["capital_base_raw"] == "581,167", "capital_base_raw='581,167'（披露原文，未折算）", f"capital_base_raw: {rec['capital_base_raw']}")
    check(rec["prescribed_capital_amount"] == 200745000.0,
          "prescribed_capital_amount=200,745 thousand→200745000.0",
          f"PCA: {rec['prescribed_capital_amount']}")
    check(rec["prescribed_capital_amount_raw"] == "200,745", "prescribed_capital_amount_raw='200,745'（披露原文）", f"PCA raw: {rec['prescribed_capital_amount_raw']}")

    rb = json.loads(rec["risk_breakdown_json"])
    check(rb["unit"] == "in HKD thousands", f"risk_breakdown.unit='in HKD thousands'（{rb['unit']}）", f"unit: {rb['unit']}")
    check(rb["prescribed_capital_amount_raw"] == "200,745", "PCA 原文 '200,745' 保留", "PCA 原文丢失")
    check(rb["capital_base_raw"] == "581,167", "capital base 原文 '581,167' 保留", "资本基础原文丢失")
    check(len(rb["prescribed_capital_components"]) == 7, f"PCA 子风险组件 7 条（{len(rb['prescribed_capital_components'])}）",
          f"PCA 组件数: {len(rb['prescribed_capital_components'])}")
    check(len(rb["capital_base_components"]) == 5, f"资本基础组件 5 条（{len(rb['capital_base_components'])}）",
          f"资本基础组件数: {len(rb['capital_base_components'])}")


# ---------------------------------------------------------------------------
# T007-5 · 跨行断词（ratio 标签跨行）
# ---------------------------------------------------------------------------
def test_cross_line_break():
    print("\n[T007-5] 跨行断词：ratio 标签跨行仍能提取 290%")
    print("-" * 60)
    text = (
        "Disclosure Statement at 31 December 2024\n"
        "1 Company profile\nAuthorized insurer's name\nPrudential General Insurance Hong Kong Limited\n"
        "4 Capital adequacy\n"
        "Unit: in HKD thousands\n"
        "Ratio of capital base to prescribed\ncapital amount 290%\n"
    )
    r = pru_rbc_parser.extract_rbc(_pages(text))
    check(r["status"] == "OK" and r["records"][0]["solvency_ratio"] == 2.90
          and r["records"][0]["solvency_ratio_raw"] == "290%",
          "跨行断词后仍提取 290%→2.90", "跨行断词解析失败")


# ---------------------------------------------------------------------------
# T007-6 · 重复候选比率歧义
# ---------------------------------------------------------------------------
def test_duplicate_candidate_ratio():
    print("\n[T007-6] 重复候选比率：两个不同百分比 → STRUCTURE_MISMATCH")
    print("-" * 60)
    text = (
        "Disclosure Statement at 31 December 2024\n"
        "1 Company profile\nAuthorized insurer's name\nPrudential General Insurance Hong Kong Limited\n"
        "4 Capital adequacy\n"
        "Ratio of capital base to prescribed capital amount 290% 295%\n"
    )
    try:
        pru_rbc_parser.extract_rbc(_pages(text))
        check(False, "", "重复候选比率未触发异常（漏检）")
    except pru_rbc_parser.PruRbcParseError as e:
        check("歧义" in str(e), f"触发 PruRbcParseError（歧义）：{e}", f"异常信息: {e}")


# ---------------------------------------------------------------------------
# T007-7 · 结构漂移（缺 Capital adequacy 段落）
# ---------------------------------------------------------------------------
def test_structure_drift():
    print("\n[T007-7] 结构漂移：缺 Capital adequacy 段落 → STRUCTURE_MISMATCH")
    print("-" * 60)
    text = "Disclosure Statement at 31 December 2024\nRatio of capital base to prescribed capital amount 290%\n"
    try:
        pru_rbc_parser.extract_rbc(_pages(text))
        check(False, "", "结构漂移未触发异常（漏检）")
    except pru_rbc_parser.PruRbcParseError as e:
        check("Capital adequacy" in str(e), f"触发 PruRbcParseError：{e}", f"异常信息: {e}")


# ---------------------------------------------------------------------------
# T007-8 · 错误年份（缺失 / 不一致）
# ---------------------------------------------------------------------------
def test_wrong_year():
    print("\n[T007-8] 错误年份：缺失 / 不一致 → STRUCTURE_MISMATCH")
    print("-" * 60)
    # 缺失
    text_missing = "4 Capital adequacy\nRatio of capital base to prescribed capital amount 290%\n"
    try:
        pru_rbc_parser.extract_rbc(_pages(text_missing))
        check(False, "", "年份缺失未触发异常（漏检）")
    except pru_rbc_parser.PruRbcParseError as e:
        check("年度" in str(e), f"年份缺失触发：{e}", f"异常信息: {e}")

    # 不一致
    text_inconsistent = (
        "4 Capital adequacy\n31 December 2024\n31 December 2023\n"
        "Ratio of capital base to prescribed capital amount 290%\n"
    )
    try:
        pru_rbc_parser.extract_rbc(_pages(text_inconsistent))
        check(False, "", "年份不一致未触发异常（漏检）")
    except pru_rbc_parser.PruRbcParseError as e:
        check("不一致" in str(e) or "歧义" in str(e), f"年份不一致触发：{e}", f"异常信息: {e}")


# ---------------------------------------------------------------------------
# T007-9 · 非 PDF（HTML 错误页）
# ---------------------------------------------------------------------------
def test_not_pdf():
    print("\n[T007-9] 非 PDF：HTML 字节 → PdfNotPdfError")
    print("-" * 60)
    try:
        pdf_text.extract_pages(b"<html><body>Access Denied</body></html>")
        check(False, "", "HTML 未触发 PdfNotPdfError（漏检）")
    except pdf_text.PdfNotPdfError as e:
        check("PDF" in str(e) or "%PDF" in str(e), f"触发 PdfNotPdfError：{e}", f"异常信息: {e}")


# ---------------------------------------------------------------------------
# T007-10 · 无文字层（最小空白 PDF）
# ---------------------------------------------------------------------------
def test_no_text_layer():
    print("\n[T007-10] 无文字层：最小空白 PDF → PdfNoTextError（不 OCR）")
    print("-" * 60)
    try:
        pdf_text.extract_pages(_make_blank_pdf())
        check(False, "", "无文字层未触发 PdfNoTextError（漏检）")
    except pdf_text.PdfNoTextError as e:
        check("文字层" in str(e) or "OCR" in str(e), f"触发 PdfNoTextError：{e}", f"异常信息: {e}")


# ---------------------------------------------------------------------------
# T007-11 · 最小文本 PDF 端到端（字节 → 提取）
# ---------------------------------------------------------------------------
def test_minimal_pdf_extract():
    print("\n[T007-11] 最小文本 PDF：字节 → pdf_text → extract_rbc")
    print("-" * 60)
    data = _make_pdf_with_text(_e2e_pdf_lines())
    r = pru_rbc_parser.parse_pru_rbc(data)
    check(r["status"] == "OK", f"status=OK（{r['status']}）", f"status: {r['status']}")
    rec = r["records"][0]
    check(rec["solvency_ratio"] == 2.90 and rec["solvency_ratio_raw"] == "290%", "最小 PDF 提取 290%→2.90", "提取失败")
    check(rec["report_year"] == 2024 and rec["currency"] == "HKD", "年度 2024 / 币种 HKD", "年度/币种错误")
    check(rec["capital_base"] == 581167000.0 and rec["prescribed_capital_amount"] == 200745000.0,
          "金额 581167000 / 200745000", "金额错误")


# ---------------------------------------------------------------------------
# T007-12 · 可选金额缺失 → NULL
# ---------------------------------------------------------------------------
def test_optional_amounts_null():
    print("\n[T007-12] 可选金额缺失：无 Capital base/PCA 行 → NULL")
    print("-" * 60)
    text = (
        "Disclosure Statement at 31 December 2024\n"
        "1 Company profile\nAuthorized insurer's name\nPrudential General Insurance Hong Kong Limited\n"
        "4 Capital adequacy\n"
        "Ratio of capital base to prescribed capital amount 290%\n"
    )
    r = pru_rbc_parser.extract_rbc(_pages(text))
    rec = r["records"][0]
    check(rec["capital_base"] is None, "capital_base=NULL（未披露，不推算）", f"capital_base: {rec['capital_base']}")
    check(rec["prescribed_capital_amount"] is None, "prescribed_capital_amount=NULL", f"PCA: {rec['prescribed_capital_amount']}")
    check(rec["solvency_ratio"] == 2.90, "核心比率仍 2.90", "核心比率错误")


# ---------------------------------------------------------------------------
# T007-13 · rbc_writer：幂等 / 回滚 / 零记录
# ---------------------------------------------------------------------------
def _rbc_record(**kw):
    base = {
        "report_year": 2024, "legal_entity_name_raw": "Prudential General Insurance Hong Kong Limited",
        "solvency_ratio": 2.90, "solvency_ratio_raw": "290%",
        "capital_base": 581167000.0, "capital_base_raw": "581,167",
        "prescribed_capital_amount": 200745000.0, "prescribed_capital_amount_raw": "200,745",
        "currency": "HKD", "amount_unit_raw": "in HKD thousands", "amount_scale": "thousands",
        "risk_breakdown_json": json.dumps({"unit": "in HKD thousands"}),
    }
    base.update(kw)
    return base


def test_rbc_writer_idempotent_rollback_zero():
    print("\n[T007-13] rbc_writer：幂等 / 回滚 / 零记录")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        reg = build_registry("http://127.0.0.1:1")
        sqlite_store.init_db(db, reg)
        conn = sqlite_store.connect(db)

        # 造一个 run_id（fetch_run 网络失败行，满足 FK）
        run_id = fetch_recorder.record_network_error(conn, 1, note="rbc-writer-test")
        conn.commit()

        # 幂等：同 run_id 同自然键写两次 → 仍 1 行
        rbc_writer.write_rbc_outcome(conn, run_id, "PRUGI", [_rbc_record()], "OK", None, "t")
        rbc_writer.write_rbc_outcome(conn, run_id, "PRUGI", [_rbc_record()], "OK", None, "t")
        n = conn.execute("SELECT COUNT(*) FROM rbc_statement WHERE run_id=?", (run_id,)).fetchone()[0]
        check(n == 1, f"幂等：重复写后 1 行（实际 {n}）", f"幂等失败，{n} 行")

        # 回滚：坏记录（report_year=None 违反 NOT NULL）→ 全部回滚
        run_id2 = fetch_recorder.record_network_error(conn, 1, note="rollback-test")
        conn.commit()
        good = _rbc_record()
        bad = _rbc_record(report_year=None)
        try:
            rbc_writer.write_rbc_outcome(conn, run_id2, "PRUGI", [good, bad], "OK")
            check(False, "", "坏记录未触发异常（漏检）")
        except sqlite3.IntegrityError:
            check(True, "坏记录触发 IntegrityError", "")
        n2 = conn.execute("SELECT COUNT(*) FROM rbc_statement WHERE run_id=?", (run_id2,)).fetchone()[0]
        check(n2 == 0, f"回滚后 0 行（实际 {n2}）", f"回滚失败，残留 {n2} 行")

        # 零记录：records=[] → 只写 parse_result，不写 rbc 行
        run_id3 = fetch_recorder.record_network_error(conn, 1, note="zero-test")
        conn.commit()
        rbc_writer.write_rbc_outcome(conn, run_id3, "PRUGI", [], "ZERO_RECORD", "ZERO_RECORD", "zero")
        n3 = conn.execute("SELECT COUNT(*) FROM rbc_statement WHERE run_id=?", (run_id3,)).fetchone()[0]
        pr = conn.execute(
            "SELECT parse_status, records_produced, error_code FROM parse_result WHERE run_id=?", (run_id3,)
        ).fetchone()
        check(n3 == 0 and pr == ("ZERO_RECORD", 0, "ZERO_RECORD"),
              f"零记录：0 rbc 行 + parse_result=(ZERO_RECORD,0,ZERO_RECORD)（{pr}）", f"零记录处理错误: {pr}")
        conn.close()


# ---------------------------------------------------------------------------
# T007-14 · 端到端：本地 HTTP 服务器 → fetch → parse → 证据链 + 幂等
# ---------------------------------------------------------------------------
def test_end_to_end_and_backref():
    print("\n[T007-14] 端到端：本地服务器 PDF → fetch → parse → 证据链 + 幂等")
    print("-" * 60)
    body = _make_pdf_with_text(_e2e_pdf_lines())
    srv = _LocalServer(body)
    try:
        reg = build_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)

            f = fetch_disclosure.fetch_one_source(conn, fetch_recorder.get_source(conn, 1), raw_root)
            conn.commit()
            check(f["result"] == "OK", f"fetch OK（{f['result']}）", f"fetch: {f}")

            p = parse_disclosure.parse_one_source(conn, fetch_recorder.get_source(conn, 1), raw_root)
            check(p["result"] == "OK", f"parse OK（{p['result']}）", f"parse: {p}")
            check(p["records_written"] == 1, f"records_written=1（{p['records_written']}）", f"records: {p}")
            check(p["parse_status"] == "OK", f"parse_status=OK（{p['parse_status']}）", f"parse_status: {p}")

            # 证据链反查
            fr = conn.execute(
                "SELECT final_url, http_status, content_hash, snapshot_path FROM fetch_run WHERE run_id=?",
                (p["run_id"],),
            ).fetchone()
            check(fr[0] == f"{srv.base}/rbc.pdf", f"final_url 反查（{fr[0]}）", f"final_url: {fr[0]}")
            check(fr[1] == 200, "http_status=200", f"http_status: {fr[1]}")
            check(fr[2] == snapshot.sha256_hex(body), "content_hash 与字节一致", "哈希不符")
            check(fr[3] == f"raw_data/PRUGI/1/{fr[2]}.pdf", f"snapshot_path 形如 raw_data/PRUGI/1/{{hash}}.pdf（{fr[3]}）",
                  f"snapshot_path: {fr[3]}")

            # 数据库行逐字核对（含法律主体原文与金额标度无损字段）
            row = conn.execute(
                "SELECT report_year, legal_entity_name_raw, solvency_ratio, solvency_ratio_raw, "
                "capital_base, capital_base_raw, prescribed_capital_amount, "
                "prescribed_capital_amount_raw, currency, amount_unit_raw, amount_scale "
                "FROM rbc_statement WHERE run_id=?",
                (p["run_id"],),
            ).fetchone()
            check(row == (2024, "Prudential General Insurance Hong Kong Limited", 2.90, "290%",
                          581167000.0, "581,167", 200745000.0, "200,745", "HKD",
                          "in HKD thousands", "thousands"),
                  f"rbc_statement 行={row}", f"rbc 行不符: {row}")

            # 幂等：重复解析不产生重复行
            p2 = parse_disclosure.parse_one_source(conn, fetch_recorder.get_source(conn, 1), raw_root)
            n = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
            check(p2["result"] == "OK" and n == 1, f"重复解析幂等（仍 {n} 行）", f"重复解析后 {n} 行")

            # SQLite integrity / FK
            check(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity_check=ok", "integrity 异常")
            check(conn.execute("PRAGMA foreign_key_check").fetchall() == [], "foreign_key_check 无违例", "FK 违例")
            conn.close()
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# T007-15 · CLI --parse 退出码
# ---------------------------------------------------------------------------
def test_cli_parse():
    print("\n[T007-15] CLI --parse：正常 0 / 未抓取非零 / 不存在源非零")
    print("-" * 60)
    body = _make_pdf_with_text(_e2e_pdf_lines())
    srv = _LocalServer(body)
    try:
        reg = build_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            reg_file = td / "reg.json"
            reg_file.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

            r = _run_cli(["--init-db", "--registry", str(reg_file), "--db-path", str(db)], REPO_ROOT)
            check(r.returncode == 0, f"init-db 退出 0（{r.returncode}）", f"init-db: {r.stderr}")

            r = _run_cli(["--parse", "1", "--registry", str(reg_file), "--db-path", str(db),
                          "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode != 0, f"未抓取 --parse 退出非零（{r.returncode}）", f"退出码 {r.returncode}")

            r = _run_cli(["--fetch", "1", "--registry", str(reg_file), "--db-path", str(db),
                          "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode == 0, f"--fetch 退出 0（{r.returncode}）", f"fetch: {r.stderr}")

            r = _run_cli(["--parse", "1", "--registry", str(reg_file), "--db-path", str(db),
                          "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode == 0, f"--parse 退出 0（{r.returncode}）", f"parse: {r.stdout}{r.stderr}")
            data = json.loads(r.stdout)
            check(data["records_written"] == 1, f"CLI 报告 records_written=1（{data['records_written']}）",
                  f"records: {data}")
            check(data["parse_status"] == "OK", f"CLI 报告 parse_status=OK（{data['parse_status']}）",
                  f"parse_status: {data}")
            check(data["report_year"] == 2024, f"CLI 报告 report_year=2024（{data['report_year']}）",
                  f"report_year: {data}")

            r = _run_cli(["--parse", "999", "--registry", str(reg_file), "--db-path", str(db),
                          "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode != 0, f"不存在源 --parse 退出非零（{r.returncode}）", f"退出码 {r.returncode}")
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# T007-16 · v0.4 → v0.5 主体隔离迁移（schema + 实体 + 幂等 + 回滚）
# ---------------------------------------------------------------------------
_OLD_RBC_DDL = """
CREATE TABLE rbc_statement (
  rbc_id                    INTEGER PRIMARY KEY,
  insurer_code              TEXT NOT NULL REFERENCES insurer(insurer_code),
  run_id                    INTEGER NOT NULL REFERENCES fetch_run(run_id),
  report_year               INTEGER NOT NULL,
  solvency_ratio            REAL,
  solvency_ratio_raw        TEXT,
  capital_base              REAL,
  prescribed_capital_amount REAL,
  currency                  TEXT NOT NULL DEFAULT 'HKD',
  risk_breakdown_json       TEXT,
  UNIQUE (insurer_code, report_year, run_id)
);
"""

_WRONG_URL = "https://www.prudential.com.hk/content/dam/prudential-phkl/pdf/en/regulatory-information/PGHK-RBC-public-disclosure-statement-2024.pdf"
_HASH = "b61630e9b275146bb4ea16a1f60ae189aa2e19daae11ea8a13751d66f97d0d51"


def _build_legacy_rbc_db(db_path, raw_root):
    """构造 v0.4 旧库：老 rbc_statement（无新列）+ PRU 错误归属 + 1 行错误 rbc + 快照。"""
    conn = sqlite_store.connect(db_path)
    sqlite_store.create_schema(conn)
    conn.execute("DROP TABLE rbc_statement")
    conn.execute(_OLD_RBC_DDL)
    conn.execute("INSERT INTO insurer (insurer_code, name_en, name_zh) VALUES ('PRU','Prudential Hong Kong Limited','保诚保险')")
    conn.execute("INSERT INTO insurer (insurer_code, name_en, name_zh) VALUES ('AIA','AIA International Limited','友邦保险')")
    conn.execute(
        "INSERT INTO data_source (insurer_code, disclosure_type, entry_url, format, access_status, evidence_basis) "
        "VALUES ('PRU','rbc',?,'pdf','OPEN','legacy-test')",
        (_WRONG_URL,),
    )
    sid = conn.execute("SELECT source_id FROM data_source WHERE entry_url=?", (_WRONG_URL,)).fetchone()[0]
    rel = f"raw_data/PRU/{sid}/{_HASH}.pdf"
    conn.execute(
        "INSERT INTO fetch_run (source_id, final_url, http_status, content_hash, content_length, snapshot_path, fetch_status) "
        "VALUES (?,?,200,?,242184,?,'OK')",
        (sid, _WRONG_URL, _HASH, rel),
    )
    run_id = conn.execute("SELECT run_id FROM fetch_run WHERE source_id=?", (sid,)).fetchone()[0]
    conn.execute(
        "INSERT INTO rbc_statement (insurer_code, run_id, report_year, solvency_ratio, solvency_ratio_raw, capital_base, prescribed_capital_amount, currency) "
        "VALUES ('PRU',?,2024,2.9,'290%',581167000.0,200745000.0,'HKD')",
        (run_id,),
    )
    conn.execute("INSERT INTO parse_result (run_id, parse_status, records_produced) VALUES (?, 'OK', 1)", (run_id,))
    old_fs = Path(raw_root) / "PRU" / str(sid) / f"{_HASH}.pdf"
    old_fs.parent.mkdir(parents=True, exist_ok=True)
    old_fs.write_bytes(b"%PDF-1.7\nlegacy-fake")
    conn.commit()
    conn.close()
    return sid, run_id


def _migration_registry():
    return {
        "schema_version": "1.1",
        "insurers": [
            {"insurer_code": "PRU", "name_en": "Prudential Hong Kong Limited", "name_zh": "保诚保险"},
            {"insurer_code": "PRUGI", "name_en": "Prudential General Insurance Hong Kong Limited", "name_zh": "保诚一般保险（香港）有限公司"},
            {"insurer_code": "AIA", "name_en": "AIA International Limited", "name_zh": "友邦保险"},
        ],
        "sources": [
            {"insurer_code": "PRU", "disclosure_type": "fulfillment_ratio",
             "entry_url": "https://example.com/irr.pdf", "format": "pdf", "access_status": "PARTIAL",
             "evidence_basis": "t", "allows_empty": False, "requires_browser": False},
            {"insurer_code": "PRUGI", "disclosure_type": "rbc",
             "entry_url": _WRONG_URL, "format": "pdf", "access_status": "OPEN",
             "evidence_basis": "t", "allows_empty": False, "requires_browser": False},
        ],
    }


def test_migration_rbc_v04():
    print("\n[T007-16] 迁移：schema 补列 + 主体归属 PRU→PRUGI + 快照移动 + 删除错误行 + 幂等")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        db = td / "icd.db"
        raw_root = td / "raw_data"
        sid, run_id = _build_legacy_rbc_db(db, raw_root)

        reg = _migration_registry()
        summary = sqlite_store.init_db(db, reg, raw_data_root=raw_root)

        # 备份存在（备份名随 SCHEMA_VERSION 递增，避免版本升级后硬编码失效）
        bak = db.with_name(f"icd.db.pre-v{sqlite_store.SCHEMA_VERSION}.bak")
        check(bak.exists(), f"迁移前全量备份 {bak.name} 存在", "迁移前未生成备份")

        # 迁移报告
        mig = summary.get("migration", {})
        acts = "\n".join(mig.get("actions", []))
        check(any(f"data_source[{sid}] insurer_code PRU→PRUGI" in a for a in mig.get("actions", [])),
              f"data_source[{sid}] 归属已修正（{acts}）", f"迁移 actions: {acts}")
        check(any("rbc_statement 新增列" in a for a in mig.get("actions", [])),
              "rbc_statement 新列已补齐", f"迁移 actions: {acts}")
        check(any("删除错误归属 rbc_statement 1 行" in a for a in mig.get("actions", [])),
              "错误归属 rbc_statement 1 行已删除", f"迁移 actions: {acts}")
        check(any(f"snapshot_path raw_data/PRU/{sid}/{_HASH}.pdf→raw_data/PRUGI/{sid}/{_HASH}.pdf" in a
                  for a in mig.get("actions", [])), "snapshot_path 已改写到 PRUGI", f"迁移 actions: {acts}")

        # 终态断言
        conn = sqlite_store.connect(db)
        code = conn.execute("SELECT insurer_code FROM data_source WHERE entry_url=?", (_WRONG_URL,)).fetchone()[0]
        check(code == "PRUGI", f"data_source insurer_code=PRUGI（{code}）", f"insurer_code: {code}")
        rbc_count = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
        check(rbc_count == 0, f"rbc_statement 错误行已删（0 行，实际 {rbc_count}）", f"rbc 残留 {rbc_count} 行")
        pr_count = conn.execute("SELECT COUNT(*) FROM parse_result").fetchone()[0]
        check(pr_count == 0, f"parse_result 错误行已删（0 行，实际 {pr_count}）", f"parse_result 残留 {pr_count} 行")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(rbc_statement)").fetchall()]
        for want in ("legal_entity_name_raw", "capital_base_raw", "prescribed_capital_amount_raw",
                     "amount_unit_raw", "amount_scale"):
            check(want in cols, f"rbc_statement 含新列 {want}", f"缺列 {want}: {cols}")
        uv = sqlite_store.get_user_version(conn)
        check(uv == sqlite_store.SCHEMA_VERSION, f"user_version={uv}（= {sqlite_store.SCHEMA_VERSION}）", f"user_version: {uv}")
        sp = conn.execute("SELECT snapshot_path FROM fetch_run WHERE source_id=?", (sid,)).fetchone()[0]
        check(sp == f"raw_data/PRUGI/{sid}/{_HASH}.pdf", f"fetch_run.snapshot_path 已改写（{sp}）", f"snapshot_path: {sp}")
        # 其他来源不受影响：AIA 险企仍在、PRU 险企仍在、fulfillment_ratio 空表未被触碰
        insurers = {r[0] for r in conn.execute("SELECT insurer_code FROM insurer").fetchall()}
        check({"PRU", "PRUGI", "AIA"} <= insurers, f"险企含 PRU/PRUGI/AIA（{sorted(insurers)}）", f"insurers: {insurers}")
        conn.close()

        # 快照物理移动
        check(not (Path(raw_root) / "PRU" / str(sid) / f"{_HASH}.pdf").exists(), "旧 PRU 快照已移走", "旧快照残留")
        check((Path(raw_root) / "PRUGI" / str(sid) / f"{_HASH}.pdf").exists(), "新 PRUGI 快照存在", "新快照缺失")

        # 幂等：再 init-db 不重复迁移、不重复备份
        summary2 = sqlite_store.init_db(db, reg, raw_data_root=raw_root)
        check("migration" not in summary2, "二次 init-db 无迁移报告（user_version 已升级，幂等）",
              f"二次迁移: {summary2.get('migration')}")
        conn2 = sqlite_store.connect(db)
        check(sqlite_store.get_user_version(conn2) == sqlite_store.SCHEMA_VERSION, "二次 init-db 后 user_version 不变", "")
        conn2.close()


def test_migration_rollback():
    print("\n[T007-17] 迁移回滚：归属 UPDATE 触发 FK 违例 → 数据库与快照不变")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        db = td / "icd.db"
        raw_root = td / "raw_data"
        sid, run_id = _build_legacy_rbc_db(db, raw_root)

        # 注册表把 wrong_url 映射到不存在的险企 → data_source UPDATE 触发 FK 违例
        reg = _migration_registry()
        bad = {"insurer_code": "NONEXISTENT", "disclosure_type": "rbc", "entry_url": _WRONG_URL,
               "format": "pdf", "access_status": "OPEN", "evidence_basis": "t"}
        reg["sources"] = [reg["sources"][0], bad]

        raised = False
        try:
            sqlite_store.init_db(db, reg, raw_data_root=raw_root)
        except sqlite3.IntegrityError:
            raised = True
        check(raised, "迁移 FK 违例被捕获（IntegrityError）", "迁移未抛 FK 违例")

        # 回滚后：归属仍 PRU、rbc 行仍在、快照仍在 PRU 路径、无新列
        conn = sqlite_store.connect(db)
        code = conn.execute("SELECT insurer_code FROM data_source WHERE entry_url=?", (_WRONG_URL,)).fetchone()[0]
        check(code == "PRU", f"回滚后 data_source 仍 PRU（{code}）", f"归属被部分修改: {code}")
        rbc_count = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
        check(rbc_count == 1, f"回滚后 rbc_statement 仍 1 行（实际 {rbc_count}）", f"rbc 行被删: {rbc_count}")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(rbc_statement)").fetchall()]
        check("legal_entity_name_raw" not in cols, "回滚后 rbc_statement 无新列（未部分提交）", f"新列残留: {cols}")
        conn.close()
        check((Path(raw_root) / "PRU" / str(sid) / f"{_HASH}.pdf").exists(), "回滚后 PRU 快照仍在", "快照被移动")


# ---------------------------------------------------------------------------
# T007-18 · 迁移故障注入：文件操作后 / DB 提交前 / 提交阶段失败 → 补偿恢复
# ---------------------------------------------------------------------------
class _CommitFailingConn:
    """包装真实连接，仅在 commit() 时抛错，其余方法全部委托（模拟提交阶段故障）。"""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def commit(self):
        raise RuntimeError("injected: commit failure")


def _assert_recovered(db, raw_root, sid, original_bytes, label):
    """断言故障后 DB 与物理快照一致（都在旧 PRU 路径）、原文件字节不丢失。"""
    conn = sqlite_store.connect(db)
    code = conn.execute("SELECT insurer_code FROM data_source WHERE entry_url=?", (_WRONG_URL,)).fetchone()[0]
    sp = conn.execute("SELECT snapshot_path FROM fetch_run WHERE source_id=?", (sid,)).fetchone()[0]
    uv = sqlite_store.get_user_version(conn)
    conn.close()
    old_pdf = Path(raw_root) / "PRU" / str(sid) / f"{_HASH}.pdf"
    new_pdf = Path(raw_root) / "PRUGI" / str(sid) / f"{_HASH}.pdf"
    check(code == "PRU", f"[{label}] 回滚后 data_source 仍 PRU（{code}）", f"[{label}] 归属被改: {code}")
    check(sp == f"raw_data/PRU/{sid}/{_HASH}.pdf",
          f"[{label}] 回滚后 snapshot_path 仍 PRU 路径（{sp}）", f"[{label}] snapshot_path: {sp}")
    check(uv < sqlite_store.SCHEMA_VERSION, f"[{label}] 回滚后 user_version 未升级（{uv}）", f"[{label}] user_version: {uv}")
    check(old_pdf.exists(), f"[{label}] 补偿后旧 PRU 快照仍在", f"[{label}] 旧快照丢失")
    check(not new_pdf.exists(), f"[{label}] 补偿后新 PRUGI 快照不存在", f"[{label}] 新快照残留")
    check(old_pdf.read_bytes() == original_bytes, f"[{label}] 原文件字节不丢失", f"[{label}] 文件内容被破坏")


def _assert_recovered_after_rerun(db, raw_root, sid, original_bytes, label):
    """断言再次 init-db 后迁移完成：DB 与物理快照一致（都在新 PRUGI 路径）。"""
    conn = sqlite_store.connect(db)
    code = conn.execute("SELECT insurer_code FROM data_source WHERE entry_url=?", (_WRONG_URL,)).fetchone()[0]
    sp = conn.execute("SELECT snapshot_path FROM fetch_run WHERE source_id=?", (sid,)).fetchone()[0]
    conn.close()
    old_pdf = Path(raw_root) / "PRU" / str(sid) / f"{_HASH}.pdf"
    new_pdf = Path(raw_root) / "PRUGI" / str(sid) / f"{_HASH}.pdf"
    check(code == "PRUGI", f"[{label}] 重跑后 data_source=PRUGI（{code}）", f"[{label}] insurer_code: {code}")
    check(sp == f"raw_data/PRUGI/{sid}/{_HASH}.pdf",
          f"[{label}] 重跑后 snapshot_path 已改写（{sp}）", f"[{label}] snapshot_path: {sp}")
    check(not old_pdf.exists(), f"[{label}] 重跑后旧 PRU 快照已移走", f"[{label}] 旧快照残留")
    check(new_pdf.exists(), f"[{label}] 重跑后新 PRUGI 快照存在", f"[{label}] 新快照缺失")
    check(new_pdf.read_bytes() == original_bytes, f"[{label}] 重跑后文件字节一致", f"[{label}] 重跑后文件内容被破坏")


def test_migration_move_before_commit_fault():
    print("\n[T007-18a] 迁移故障注入：文件移动后、DB 提交前失败（set_user_version）→ 补偿 + 幂等重跑")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        db = td / "icd.db"
        raw_root = td / "raw_data"
        sid, run_id = _build_legacy_rbc_db(db, raw_root)
        reg = _migration_registry()
        original_bytes = (Path(raw_root) / "PRU" / str(sid) / f"{_HASH}.pdf").read_bytes()

        _orig = sqlite_store.set_user_version
        def _boom(conn, version):
            raise RuntimeError("injected: set_user_version failure")
        sqlite_store.set_user_version = _boom
        try:
            raised = False
            try:
                sqlite_store.init_db(db, reg, raw_data_root=raw_root)
            except RuntimeError as e:
                raised = "set_user_version" in str(e)
            check(raised, "故障注入被捕获（set_user_version 抛 RuntimeError）", "未按预期抛出")
        finally:
            sqlite_store.set_user_version = _orig

        _assert_recovered(db, raw_root, sid, original_bytes, "18a")

        sqlite_store.init_db(db, reg, raw_data_root=raw_root)
        _assert_recovered_after_rerun(db, raw_root, sid, original_bytes, "18a")


def test_migration_move_commit_phase_fault():
    print("\n[T007-18b] 迁移故障注入：文件移动后、提交阶段失败（commit）→ 补偿 + 幂等重跑")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        db = td / "icd.db"
        raw_root = td / "raw_data"
        sid, run_id = _build_legacy_rbc_db(db, raw_root)
        reg = _migration_registry()
        original_bytes = (Path(raw_root) / "PRU" / str(sid) / f"{_HASH}.pdf").read_bytes()

        _orig = sqlite_store.connect
        def _boom(db_path):
            return _CommitFailingConn(_orig(db_path))
        sqlite_store.connect = _boom
        try:
            raised = False
            try:
                sqlite_store.init_db(db, reg, raw_data_root=raw_root)
            except RuntimeError as e:
                raised = "commit" in str(e)
            check(raised, "故障注入被捕获（commit 抛 RuntimeError）", "未按预期抛出")
        finally:
            sqlite_store.connect = _orig

        _assert_recovered(db, raw_root, sid, original_bytes, "18b")

        sqlite_store.init_db(db, reg, raw_data_root=raw_root)
        _assert_recovered_after_rerun(db, raw_root, sid, original_bytes, "18b")


def main():
    print("=" * 60)
    print("ICD 集成测试（T007 · Prudential RBC PDF 解析与入库）")
    print("=" * 60)
    test_parse_pct_unit()
    test_parse_amount_unit()
    test_pdf_signature()
    test_fixture_official_neighborhood()
    test_cross_line_break()
    test_duplicate_candidate_ratio()
    test_structure_drift()
    test_wrong_year()
    test_not_pdf()
    test_no_text_layer()
    test_minimal_pdf_extract()
    test_optional_amounts_null()
    test_rbc_writer_idempotent_rollback_zero()
    test_end_to_end_and_backref()
    test_cli_parse()
    test_migration_rbc_v04()
    test_migration_rollback()
    test_migration_move_before_commit_fault()
    test_migration_move_commit_phase_fault()

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"❌ 失败 {len(FAILURES)} 项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("✅ ALL CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
