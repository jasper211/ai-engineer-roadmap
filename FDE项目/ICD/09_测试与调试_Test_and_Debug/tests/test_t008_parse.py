#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD 集成测试（T008）· AIA Company Limited 2024 RBC 官方索引发现、PDF 解析与入库

覆盖任务书 T008 验收标准（确定性部分，不联网除本机临时 HTTP 服务器）：
- 泛化证明：不写死 304%（另有 212%/457%/290% 泛化断言）；跨行断词、重复候选歧义、结构漂移、
  错误年度、无文字层、非 PDF 分别确定性失败。
- 法律主体：英式 'Authorised insurer's name' 与美式 'Authorized insurer's name' 均正确提取，
  并清洗 '(the "Company")' 指代标注 → 法律主体原文 'AIA Company Limited'（独立 insurer_code=AIACO）。
- 金额标度：'in HKD thousands' 折算绝对 HKD（70,993,766 → 70,993,766,000）。
- 索引发现：官方域名/2024/英文/Disclosure Statement 约束 + 目标文件名消歧 + 零匹配/歧义确定性失败。
- 两段证据链：索引 fetch_run + PDF fetch_run，rbc_statement 可回查最终 PDF。
- 迁移 v0.5→v0.6：AIA rbc 索引源 format pdf→html、AIACO 主体与 AIACO rbc PDF 源种子。
- rbc_writer 幂等/回滚/integrity/FK。
全部写操作在 tempfile 内，不污染默认数据库。

运行：python3 09_测试与调试_Test_and_Debug/tests/test_t008_parse.py
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

from skills import fetch_disclosure, parse_disclosure, rbc_index_discovery, rbc_parser
from tools import fetch_recorder, rbc_writer, snapshot, sqlite_store

AGENT_PY = ICD_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"
FIXTURE_PATH = TESTS_DIR / "fixtures" / "aia_rbc_fixture.json"
INDEX_FIXTURE = TESTS_DIR / "fixtures" / "aia_index_fixture.html"

FAILURES = []


def check(cond, ok_msg, fail_msg=""):
    if cond:
        print(f"✅ {ok_msg}")
    else:
        print(f"❌ {fail_msg or ok_msg}")
        FAILURES.append(fail_msg or ok_msg)


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _pages(text: str, tables=None):
    return [{"text": text, "tables": tables or []}]


# ---------------------------------------------------------------------------
# 最小 PDF 生成器（合法单页 PDF；无第三方库）
# ---------------------------------------------------------------------------
def _pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _make_pdf_with_text(lines) -> bytes:
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


def _e2e_aia_pdf_lines():
    return [
        "AIA Company Limited",
        "Disclosure Statement",
        "At 31 December 2024",
        "1 Company profile",
        "(a) Authorised insurer's name",
        "AIA Company Limited (the \"Company\")",
        "4 Capital adequacy",
        "Unit: in HKD thousands As at 31 December 2024",
        "Ratio of capital base to prescribed capital amount 304%",
        "Capital base 70,993,766",
        "Prescribed capital amount 23,371,785",
    ]


# ---------------------------------------------------------------------------
# 本机临时 HTTP 服务器
# ---------------------------------------------------------------------------
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
                body, ctype = outer.routes[self.path]
                self.send_response(200)
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
    """T008 本地测试注册表：source_id=1 = AIA rbc 索引（html），source_id=2 = AIACO rbc PDF。"""
    return {
        "schema_version": "1.2",
        "generated_at": "2026-09-03",
        "description": "T008 本地测试注册表",
        "insurers": [
            {"insurer_code": "AIA", "name_en": "AIA International Limited", "name_zh": "友邦保险"},
            {"insurer_code": "AIACO", "name_en": "AIA Company Limited", "name_zh": None},
        ],
        "sources": [
            {
                "insurer_code": "AIA", "disclosure_type": "rbc",
                "entry_url": f"{base_url}/index.html", "format": "html",
                "access_status": "OPEN",
                "parser_hint": "rbc 索引源。目标文件名 'AIA Co Disclosure Statement 2024_Eng.pdf'（discover 消歧选择器）。",
                "requires_browser": False, "evidence_basis": "T008 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-03", "url_version": 1,
            },
            {
                "insurer_code": "AIACO", "disclosure_type": "rbc",
                "entry_url": f"{base_url}/aia_co.pdf", "format": "pdf",
                "access_status": "OPEN",
                "parser_hint": "AIA Co 2024 英文 Disclosure Statement PDF（由 source_id=1 索引发现）。",
                "requires_browser": False, "evidence_basis": "T008 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-03", "url_version": 1,
            },
        ],
    }


def _run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, str(AGENT_PY)] + args,
        cwd=str(cwd), capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# T008-1 · 法律主体：英式/美式拼写 + "(the Company)" 清洗
# ---------------------------------------------------------------------------
def test_legal_entity_spellings():
    print("\n[T008-1] 法律主体：Authorised/Authorized 拼写 + '(the Company)' 清洗")
    print("-" * 60)
    text = (
        "1 Company profile\n"
        "(a) Authorised insurer's name\n"
        "AIA Company Limited (the \"Company\")\n"
        "4 Capital adequacy\n"
        "31 December 2024\n"
        "Ratio of capital base to prescribed capital amount 304%\n"
    )
    r = rbc_parser.extract_rbc(_pages(text))
    rec = r["records"][0]
    check(rec["legal_entity_name_raw"] == "AIA Company Limited",
          "英式 Authorised → 'AIA Company Limited'（清洗 '(the Company)'）",
          f"legal_entity_name_raw: {rec['legal_entity_name_raw']!r}")

    # 美式拼写（T007 Prudential 版式回归）
    text2 = (
        "1 Company profile\n"
        "Authorized insurer's name\n"
        "Prudential General Insurance Hong Kong Limited\n"
        "4 Capital adequacy\n"
        "31 December 2024\n"
        "Ratio of capital base to prescribed capital amount 290%\n"
    )
    r2 = rbc_parser.extract_rbc(_pages(text2))
    check(r2["records"][0]["legal_entity_name_raw"] == "Prudential General Insurance Hong Kong Limited",
          "美式 Authorized → Prudential GI 名称正确（回归）",
          f"legal_entity_name_raw: {r2['records'][0]['legal_entity_name_raw']!r}")

    # 同行版式：标签与名称同行
    text3 = (
        "1 Company profile\n"
        "Authorised insurer's name: AIA Company Limited\n"
        "4 Capital adequacy\n"
        "31 December 2024\n"
        "Ratio of capital base to prescribed capital amount 304%\n"
    )
    r3 = rbc_parser.extract_rbc(_pages(text3))
    check(r3["records"][0]["legal_entity_name_raw"] == "AIA Company Limited",
          "同行 'name: X' → 'AIA Company Limited'",
          f"legal_entity_name_raw: {r3['records'][0]['legal_entity_name_raw']!r}")


# ---------------------------------------------------------------------------
# T008-2 · 百分比泛化（证明不写死 304%）
# ---------------------------------------------------------------------------
def test_ratio_generalization():
    print("\n[T008-2] 百分比泛化：304%→3.04 / 212%→2.12 / 457%→4.57 / 290%→2.90")
    print("-" * 60)
    check(rbc_parser._parse_pct_to_ratio("304%") == 3.04, "304% → 3.04", "304% 解析错误")
    check(rbc_parser._parse_pct_to_ratio("212%") == 2.12, "212% → 2.12（AIAI 版式）", "212% 解析错误")
    check(rbc_parser._parse_pct_to_ratio("457%") == 4.57, "457% → 4.57（AIAE 版式）", "457% 解析错误")
    check(rbc_parser._parse_pct_to_ratio("290%") == 2.90, "290% → 2.90（Prudential 版式）", "290% 解析错误")


# ---------------------------------------------------------------------------
# T008-3 · 官方语句邻域 fixture（304%→3.04 / 金额标度 / 币种 / 法律主体）
# ---------------------------------------------------------------------------
def test_fixture_official_neighborhood():
    print("\n[T008-3] 官方语句邻域：304%→3.04 / 2024 / HKD / 金额千标度 / 法律主体")
    print("-" * 60)
    fx = load_fixture()
    r = rbc_parser.extract_rbc(fx["pages"])
    check(r["status"] == "OK", f"status=OK（{r['status']}）", f"status: {r['status']}")
    check(r["report_year"] == 2024, f"report_year=2024（{r['report_year']}）", f"report_year: {r['report_year']}")
    rec = r["records"][0]
    check(rec["legal_entity_name_raw"] == "AIA Company Limited",
          "legal_entity_name_raw='AIA Company Limited'（法律主体原文）",
          f"legal_entity_name_raw: {rec['legal_entity_name_raw']!r}")
    check(rec["solvency_ratio"] == 3.04, "solvency_ratio=3.04", f"solvency_ratio: {rec['solvency_ratio']}")
    check(rec["solvency_ratio_raw"] == "304%", "solvency_ratio_raw='304%'（保留原文）", f"raw: {rec['solvency_ratio_raw']}")
    check(rec["currency"] == "HKD", "currency=HKD", f"currency: {rec['currency']}")
    check(rec["amount_unit_raw"] == "in HKD thousands", "amount_unit_raw='in HKD thousands'", f"amount_unit_raw: {rec['amount_unit_raw']}")
    check(rec["amount_scale"] == "thousands", "amount_scale='thousands'", f"amount_scale: {rec['amount_scale']}")
    check(rec["capital_base_raw"] == "70,993,766", "capital_base_raw='70,993,766'", f"capital_base_raw: {rec['capital_base_raw']}")
    check(rec["capital_base"] == 70993766000.0, "capital_base=70,993,766,000（千→绝对 HKD）", f"capital_base: {rec['capital_base']}")
    check(rec["prescribed_capital_amount_raw"] == "23,371,785", "prescribed_capital_amount_raw='23,371,785'", f"pca_raw: {rec['prescribed_capital_amount_raw']}")
    check(rec["prescribed_capital_amount"] == 23371785000.0, "prescribed_capital_amount=23,371,785,000", f"pca: {rec['prescribed_capital_amount']}")
    check(rec["risk_breakdown_json"] is not None, "risk_breakdown_json 非空（无损风险分解）", "risk_breakdown_json 为空")


# ---------------------------------------------------------------------------
# T008-4 · 跨行断词（ratio 标签跨行）
# ---------------------------------------------------------------------------
def test_ratio_cross_line():
    print("\n[T008-4] 跨行断词：ratio 标签跨行仍提取 304%")
    print("-" * 60)
    text = (
        "1 Company profile\nAuthorised insurer's name\nAIA Company Limited\n"
        "4 Capital adequacy\n31 December 2024\n"
        "Ratio of capital base to prescribed\ncapital amount 304%\n"
    )
    r = rbc_parser.extract_rbc(_pages(text))
    rec = r["records"][0]
    check(rec["solvency_ratio"] == 3.04 and rec["solvency_ratio_raw"] == "304%",
          "跨行断词后 ratio=3.04（空白折叠归一匹配）",
          f"ratio: {rec['solvency_ratio']} raw: {rec['solvency_ratio_raw']}")


# ---------------------------------------------------------------------------
# T008-5 · 重复候选比率歧义 → STRUCTURE_MISMATCH
# ---------------------------------------------------------------------------
def test_ratio_ambiguous():
    print("\n[T008-5] 重复候选比率歧义 → RbcParseError（STRUCTURE_MISMATCH）")
    print("-" * 60)
    text = (
        "1 Company profile\nAuthorised insurer's name\nAIA Company Limited\n"
        "4 Capital adequacy\n31 December 2024\n"
        "Ratio of capital base to prescribed capital amount 304%\n"
        "Ratio of capital base to prescribed capital amount 304%\n"
        "Ratio of capital base to prescribed capital amount 212%\n"
    )
    try:
        rbc_parser.extract_rbc(_pages(text))
        check(False, "", "重复候选未触发歧义（漏检）")
    except rbc_parser.RbcParseError as e:
        check("歧义" in str(e), f"触发歧义：{e}", f"异常信息: {e}")


# ---------------------------------------------------------------------------
# T008-6 · 结构漂移 / 错误年度 → STRUCTURE_MISMATCH
# ---------------------------------------------------------------------------
def test_structure_drift_and_year():
    print("\n[T008-6] 结构漂移 / 错误年度 → RbcParseError")
    print("-" * 60)
    try:
        rbc_parser.extract_rbc(_pages(
            "1 Company profile\nAuthorised insurer's name\nAIA Company Limited\n"
            "31 December 2024\nRatio of capital base to prescribed capital amount 304%\n"
        ))
        check(False, "", "缺 Capital adequacy 段落未触发（漏检）")
    except rbc_parser.RbcParseError as e:
        check("Capital adequacy" in str(e), f"结构漂移触发：{e}", f"异常: {e}")

    try:
        rbc_parser.extract_rbc(_pages(
            "1 Company profile\nAuthorised insurer's name\nAIA Company Limited\n"
            "4 Capital adequacy\n31 December 2024\n31 December 2023\n"
            "Ratio of capital base to prescribed capital amount 304%\n"
        ))
        check(False, "", "年份不一致未触发（漏检）")
    except rbc_parser.RbcParseError as e:
        check("不一致" in str(e) or "歧义" in str(e), f"年份不一致触发：{e}", f"异常: {e}")


# ---------------------------------------------------------------------------
# T008-7 · 非 PDF / 无文字层（复用 pdf_text 语义）
# ---------------------------------------------------------------------------
def test_pdf_errors():
    print("\n[T008-7] 非 PDF / 无文字层")
    print("-" * 60)
    from skills import pdf_text
    try:
        rbc_parser.parse_rbc(b"<html><body>Access Denied</body></html>")
        check(False, "", "HTML 未触发 PdfNotPdfError（漏检）")
    except pdf_text.PdfNotPdfError:
        check(True, "HTML → PdfNotPdfError", "")
    try:
        rbc_parser.parse_rbc(_make_blank_pdf())
        check(False, "", "无文字层未触发 PdfNoTextError（漏检）")
    except pdf_text.PdfNoTextError:
        check(True, "空白 PDF → PdfNoTextError（不 OCR）", "")


# ---------------------------------------------------------------------------
# T008-8 · 索引发现（官方域名/年度/英文/语义约束 + 消歧 + 确定性失败）
# ---------------------------------------------------------------------------
def test_index_discovery():
    print("\n[T008-8] 索引发现：约束筛选 + 消歧 + 零匹配/歧义确定性失败")
    print("-" * 60)
    html = INDEX_FIXTURE.read_bytes()

    cands = rbc_index_discovery.extract_disclosure_pdf_candidates(html)
    check(len(cands) == 3, f"候选 = 3（AIA Co/AIAI/AIAE 2024 Eng；排除 2025/财务/非官方域名）（实际 {len(cands)}）",
          f"candidates: {cands}")
    check(all("aia.com" in c for c in cands), "候选均在官方域名 aia.com", f"candidates: {cands}")

    url = rbc_index_discovery.discover_disclosure_pdf(html, filename_hint="AIA Co Disclosure Statement 2024_Eng.pdf")
    check(url.endswith("AIA%20Co%20Disclosure%20Statement%202024_Eng.pdf"),
          f"消歧定位 AIA Co（{url}）", f"url: {url}")

    # 无提示 → 歧义
    try:
        rbc_index_discovery.discover_disclosure_pdf(html)
        check(False, "", "无消歧未触发（漏检）")
    except rbc_index_discovery.RbcIndexDiscoveryError as e:
        check("3" in str(e), f"无消歧触发歧义：{e}", f"异常: {e}")

    # 零匹配
    try:
        rbc_index_discovery.discover_disclosure_pdf(b"<html><body>no pdf here</body></html>", filename_hint="x.pdf")
        check(False, "", "零匹配未触发（漏检）")
    except rbc_index_discovery.RbcIndexDiscoveryError as e:
        check("未找到" in str(e), f"零匹配触发：{e}", f"异常: {e}")


# ---------------------------------------------------------------------------
# T008-9 · 两段证据链端到端（索引 fetch → 发现 → PDF fetch → 解析 → 回查）
# ---------------------------------------------------------------------------
def test_two_link_chain():
    print("\n[T008-9] 两段证据链：索引 fetch_run + PDF fetch_run，rbc_statement 回查 PDF")
    print("-" * 60)
    pdf_bytes = _make_pdf_with_text(_e2e_aia_pdf_lines())
    pdf_path = "/AIA%20Co%20Disclosure%20Statement%202024_Eng.pdf"
    index_html = (
        "<html><body>"
        f"<a href=\"{pdf_path}\">Disclosure statement (including Independent practitioner's reasonable assurance report)</a>"
        "</body></html>"
    ).encode("utf-8")
    srv = _LocalServer({
        "/index.html": (index_html, "text/html"),
        pdf_path: (pdf_bytes, "application/pdf"),
    })
    try:
        reg = _local_registry(srv.base)
        reg["sources"][1]["entry_url"] = f"{srv.base}{pdf_path}"  # AIACO pdf 源指向本地 PDF
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "icd.db"
            raw_root = Path(td) / "raw"
            sqlite_store.init_db(db, reg, raw_data_root=raw_root)
            conn = sqlite_store.connect(db)

            # 1) 抓取索引（证据链 1）
            idx_src = fetch_recorder.get_source(conn, 1)
            r1 = fetch_disclosure.fetch_one_source(conn, idx_src, raw_root)
            check(r1["result"] == "OK" and r1["snapshot_path"].endswith(".html"),
                  f"索引抓取 OK，快照 .html（{r1['snapshot_path']}）", f"r1: {r1}")

            # 2) 发现：从索引快照定位 PDF（本地 base_url + 本地域名白名单）
            idx_snap = parse_disclosure._snapshot_file(raw_root, r1["snapshot_path"])
            disc = rbc_index_discovery.discover_disclosure_pdf(
                idx_snap.read_bytes(), base_url=srv.base,
                allowed_domains=("127.0.0.1",),
                filename_hint="AIA Co Disclosure Statement 2024_Eng.pdf",
            )
            check(disc == f"{srv.base}{pdf_path}", f"发现目标 PDF（{disc}）", f"disc: {disc}")

            # 3) 抓取 PDF（证据链 2）
            pdf_src = fetch_recorder.get_source(conn, 2)
            r2 = fetch_disclosure.fetch_one_source(conn, pdf_src, raw_root)
            check(r2["result"] == "OK" and r2["snapshot_path"].endswith(".pdf"),
                  f"PDF 抓取 OK，快照 .pdf（{r2['snapshot_path']}）", f"r2: {r2}")

            # 4) 解析 → rbc_statement
            p = parse_disclosure.parse_one_source(conn, pdf_src, raw_root)
            check(p["result"] == "OK", f"解析 OK（{p['result']}）", f"p: {p}")

            # 5) rbc_statement.run_id → PDF fetch_run（回查最终 PDF）
            row = conn.execute(
                "SELECT r.insurer_code, r.legal_entity_name_raw, r.solvency_ratio, r.solvency_ratio_raw, "
                "r.capital_base, f.run_id, f.final_url, f.http_status, f.snapshot_path "
                "FROM rbc_statement r JOIN fetch_run f ON f.run_id = r.run_id"
            ).fetchone()
            check(row[0] == "AIACO", f"insurer_code=AIACO（{row[0]}）", f"code: {row[0]}")
            check(row[1] == "AIA Company Limited", f"legal_entity_name_raw='AIA Company Limited'（{row[1]}）", f"le: {row[1]}")
            check(row[2] == 3.04 and row[3] == "304%", f"ratio 3.04 / '304%'（{row[2]}/{row[3]}）", f"ratio: {row[2]}/{row[3]}")
            check(row[4] == 70993766000.0, f"capital_base=70,993,766,000（{row[4]}）", f"cb: {row[4]}")
            check(row[6] == f"{srv.base}{pdf_path}", f"run_id 回查 final_url = PDF（{row[6]}）", f"url: {row[6]}")
            check(row[7] == 200, f"PDF http_status=200（{row[7]}）", f"http: {row[7]}")
            check(row[8].endswith(".pdf"), f"PDF snapshot_path .pdf（{row[8]}）", f"sp: {row[8]}")

            # 6) 索引 fetch_run 独立证据保留
            idx_row = conn.execute("SELECT final_url, snapshot_path FROM fetch_run WHERE source_id=1").fetchone()
            check(idx_row[0] == f"{srv.base}/index.html" and idx_row[1].endswith(".html"),
                  f"索引 fetch_run 保留（final_url={idx_row[0]}）", f"idx: {idx_row}")

            # 7) 幂等：重复解析仍 1 行
            p2 = parse_disclosure.parse_one_source(conn, pdf_src, raw_root)
            n = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
            check(n == 1 and p2["result"] == "OK", f"重复解析幂等仍 1 行（{n}）", f"n: {n}")

            # 8) integrity / FK
            check(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity_check=ok", "integrity 失败")
            check(conn.execute("PRAGMA foreign_key_check").fetchall() == [], "foreign_key_check=[]", "FK 违例")
            conn.close()
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# T008-10 · 迁移 v0.5→v0.6：索引源 format 修正 + AIACO 主体/源种子
# ---------------------------------------------------------------------------
def test_migration_v05():
    print("\n[T008-10] 迁移 v0.5→v0.6：索引源 format pdf→html + AIACO 主体/源种子")
    print("-" * 60)
    real_reg = json.loads((ICD_DIR / "02_配置项目_Configure_Project" / "source_registry.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        raw_root = Path(td) / "raw"
        conn = sqlite_store.connect(db)
        # 构造 v0.5 旧库：建 schema + 播种，但索引源 format 为 pdf、无 AIACO 主体/源，user_version=4
        sqlite_store.create_schema(conn)
        sqlite_store.seed_error_codes(conn)
        old_insurers = [i for i in real_reg["insurers"] if i["insurer_code"] != "AIACO"]
        old_sources = []
        for s in real_reg["sources"]:
            if s["insurer_code"] == "AIACO":
                continue
            s = dict(s)
            if s["disclosure_type"] == "rbc" and s.get("entry_url") and "regulatory-disclosures" in s["entry_url"]:
                s["format"] = "pdf"  # 模拟旧元数据
            old_sources.append(s)
        sqlite_store.seed_insurers(conn, old_insurers)
        sqlite_store.seed_sources(conn, old_sources)
        sqlite_store.set_user_version(conn, 4)
        conn.commit()
        conn.close()

        summary = sqlite_store.init_db(db, real_reg, raw_data_root=raw_root)
        conn = sqlite_store.connect(db)
        fmt = conn.execute("SELECT format FROM data_source WHERE entry_url LIKE '%regulatory-disclosures%'").fetchone()[0]
        check(fmt == "html", f"迁移后索引源 format=html（{fmt}）", f"fmt: {fmt}")
        check(conn.execute("SELECT COUNT(*) FROM insurer").fetchone()[0] == 12,
              "迁移+种子后险企 12", "险企数错误")
        check(conn.execute("SELECT COUNT(*) FROM data_source").fetchone()[0] == 22,
              "迁移+种子后源 22", "源数错误")
        check(conn.execute("SELECT COUNT(*) FROM insurer WHERE insurer_code='AIACO'").fetchone()[0] == 1,
              "AIACO 主体存在", "AIACO 缺失")
        check(conn.execute("SELECT COUNT(*) FROM data_source WHERE insurer_code='AIACO' AND format='pdf'").fetchone()[0] == 1,
              "AIACO rbc PDF 源存在", "AIACO 源缺失")
        check(sqlite_store.get_user_version(conn) == sqlite_store.SCHEMA_VERSION,
              f"user_version={sqlite_store.SCHEMA_VERSION}", f"uv: {sqlite_store.get_user_version(conn)}")
        conn.close()

        summary2 = sqlite_store.init_db(db, real_reg, raw_data_root=raw_root)
        check("migration" not in summary2, "二次 init-db 无迁移报告（幂等）", f"二次迁移: {summary2.get('migration')}")


# ---------------------------------------------------------------------------
# T008-11 · rbc_writer 幂等 / 回滚 / 零记录
# ---------------------------------------------------------------------------
def test_rbc_writer():
    print("\n[T008-11] rbc_writer：幂等 UPSERT / 回滚 / 零记录")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        reg = _local_registry("http://127.0.0.1:1")
        sqlite_store.init_db(db, reg, raw_data_root=Path(td) / "raw")
        conn = sqlite_store.connect(db)

        rec = {
            "report_year": 2024, "legal_entity_name_raw": "AIA Company Limited",
            "solvency_ratio": 3.04, "solvency_ratio_raw": "304%",
            "capital_base": 70993766000.0, "capital_base_raw": "70,993,766",
            "prescribed_capital_amount": 23371785000.0, "prescribed_capital_amount_raw": "23,371,785",
            "currency": "HKD", "amount_unit_raw": "in HKD thousands", "amount_scale": "thousands",
            "risk_breakdown_json": "{}",
        }
        # run_id 需要先有 fetch_run 行（FK）；构造 run_id 1/2/3
        for rid, h in ((1, "abc"), (2, "def"), (3, "ghi")):
            conn.execute(
                "INSERT INTO fetch_run (run_id, source_id, final_url, http_status, content_hash, content_length, snapshot_path, fetch_status) "
                "VALUES (?, 2, ?, 200, ?, 100, ?, 'OK')",
                (rid, f"http://x/{h}.pdf", h, f"raw_data/AIACO/2/{h}.pdf"),
            )
        conn.commit()

        n1 = rbc_writer.write_rbc_outcome(conn, 1, "AIACO", [rec], "OK", None, "ok")
        n2 = rbc_writer.write_rbc_outcome(conn, 1, "AIACO", [rec], "OK", None, "ok")
        cnt = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
        check(n1 == 1 and n2 == 1 and cnt == 1, f"幂等 UPSERT 仍 1 行（{cnt}）", f"cnt: {cnt}")

        # 回滚：坏记录（legal_entity_name_raw=None 违反 NOT NULL）→ 整体回滚，不留部分行
        bad = dict(rec)
        bad["legal_entity_name_raw"] = None
        try:
            rbc_writer.write_rbc_outcome(conn, 2, "AIACO", [bad], "OK", None, "ok")
            check(False, "", "坏记录未抛错（漏检）")
        except sqlite3.IntegrityError:
            check(True, "坏记录触发 IntegrityError（回滚）", "")
        cnt2 = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
        check(cnt2 == 1, f"回滚后仍 1 行（{cnt2}）", f"cnt2: {cnt2}")

        # 零记录：只写 parse_result
        n0 = rbc_writer.write_rbc_outcome(conn, 3, "AIACO", [], "ZERO_RECORD", "ZERO_RECORD", "none")
        cnt3 = conn.execute("SELECT COUNT(*) FROM rbc_statement").fetchone()[0]
        check(n0 == 0 and cnt3 == 1, f"零记录只写 parse_result（rbc_statement 仍 {cnt3}）", f"cnt3: {cnt3}")
        conn.close()


# ---------------------------------------------------------------------------
# T008-12 · CLI：--validate-config（真实注册表）与 --discover 无抓取语义
# ---------------------------------------------------------------------------
def test_cli():
    print("\n[T008-12] CLI：--validate-config 通过（真实注册表 12 险企 / 22 源）")
    print("-" * 60)
    r = _run_cli(["--validate-config"], ICD_DIR)
    check(r.returncode == 0, f"--validate-config EXIT=0（{r.returncode}）", f"stderr: {r.stderr}")


# ---------------------------------------------------------------------------
# T008-13 · CLI --discover：parser_hint 消歧选择器（get_source 返回 parser_hint）
# ---------------------------------------------------------------------------
def test_cli_discover():
    print("\n[T008-13] CLI --discover：从索引快照消歧定位 AIA Co PDF（parser_hint 消歧选择器）")
    print("-" * 60)
    srv = _LocalServer({"/index.html": (INDEX_FIXTURE.read_bytes(), "text/html")})
    try:
        reg = _local_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            reg_file = td / "reg.json"
            reg_file.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

            r = _run_cli(["--init-db", "--registry", str(reg_file), "--db-path", str(db)], ICD_DIR)
            check(r.returncode == 0, f"init-db 退出 0（{r.returncode}）", f"init-db: {r.stderr}")

            r = _run_cli(["--fetch", "1", "--registry", str(reg_file), "--db-path", str(db),
                          "--raw-data-root", str(raw_root)], ICD_DIR)
            check(r.returncode == 0, f"--fetch 1 退出 0（{r.returncode}）", f"fetch: {r.stderr}")

            r = _run_cli(["--discover", "1", "--registry", str(reg_file), "--db-path", str(db),
                          "--raw-data-root", str(raw_root)], ICD_DIR)
            check(r.returncode == 0, f"--discover 1 退出 0（{r.returncode}）", f"discover: {r.stdout}{r.stderr}")
            data = json.loads(r.stdout)
            check(data["result"] == "OK", f"--discover 结果 OK（{data['result']}）", f"result: {data}")
            check(data["filename_hint"] == "AIA Co Disclosure Statement 2024_Eng.pdf",
                  f"filename_hint 从 parser_hint 提取（{data['filename_hint']}）", f"hint: {data}")
            check(data["discovered_pdf_url"].endswith("AIA%20Co%20Disclosure%20Statement%202024_Eng.pdf"),
                  f"消歧定位 AIA Co PDF（{data['discovered_pdf_url']}）", f"url: {data}")
    finally:
        srv.stop()


def main():
    test_legal_entity_spellings()
    test_ratio_generalization()
    test_fixture_official_neighborhood()
    test_ratio_cross_line()
    test_ratio_ambiguous()
    test_structure_drift_and_year()
    test_pdf_errors()
    test_index_discovery()
    test_two_link_chain()
    test_migration_v05()
    test_rbc_writer()
    test_cli()
    test_cli_discover()

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
