#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD 集成测试（T006）· 中国人寿（海外）CLO 分红实现率 HTML 解析、标准化、事务入库

覆盖任务书 T006 验收标准：
- fixture 与真实证据分离（本文件只跑脱敏 fixture；真实验证单独记录，见任务书回执）。
- 记录数 = 明确业务单元格之和（按 JS 数组 dataSets1/2/3 与 policyYears 确定性提取，
  绝不用全页百分号正则）。
- 覆盖：≥2 产品、≥2 指标、跨年份、币种/披露分组（all-currencies vs RMB）、
  脚注/非数值 "NA"、结构漂移、零记录、重复执行、事务回滚。
  注：CLO 真实源是 JS 数组嵌入（非静态 <table>），无 rowspan/colspan 合并单元格；
  等价结构特征为「11 列观察期对齐 + 币种分组」，本测试覆盖二者，且额外断言静态
  Universal Life 结算利率 <table> 不被误解析。
- 数值断言：100%→1.0、84%→0.84、超过100%合法、开放区间 "(2014 or before)"→NULL。
- 不联网（除本机临时 HTTP 服务器）；所有写操作在 tempfile 内，不污染默认数据库。

运行：python3 09_测试与调试_Test_and_Debug/tests/test_t006_parse.py
"""

import http.server
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent                 # tests/
NUMBERED_DIR = TESTS_DIR.parent                             # 09_测试与调试_Test_and_Debug/
ICD_DIR = NUMBERED_DIR.parent                               # FDE项目/ICD/
REPO_ROOT = ICD_DIR.parent.parent                           # 仓库根
FIXTURE_PATH = TESTS_DIR / "fixtures" / "clo_fixture.html"

for _pkg_dir in (
    "05_集成工具_Integrate_Tools",
    "07_接入记忆_Integrate_Memory",
    "06_开发技能_Develop_Skills",
):
    sys.path.insert(0, str(ICD_DIR / _pkg_dir))

from skills import clo_html_parser, fetch_disclosure, parse_disclosure
from tools import fetch_recorder, ratio_writer, snapshot, sqlite_store

AGENT_PY = ICD_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"

FAILURES = []


def check(cond, ok_msg, fail_msg=""):
    if cond:
        print(f"✅ {ok_msg}")
    else:
        print(f"❌ {fail_msg or ok_msg}")
        FAILURES.append(fail_msg or ok_msg)


def load_fixture() -> bytes:
    return FIXTURE_PATH.read_bytes()


# ---------------------------------------------------------------------------
# 辅助：本机临时 HTTP 服务器，喂给定字节
# ---------------------------------------------------------------------------
class _LocalServer:
    def __init__(self, body: bytes):
        self.body = body
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(outer.body)))
                self.send_header("Content-Type", "text/html; charset=utf-8")
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
    """T006 本地测试注册表：CLO fulfillment_ratio（html）。source_id=1。"""
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-03",
        "description": "T006 本地测试注册表",
        "insurers": [{"insurer_code": "CLO", "name_en": "China Life (Overseas)", "name_zh": "中国人寿（海外）"}],
        "sources": [
            {
                "insurer_code": "CLO", "disclosure_type": "fulfillment_ratio",
                "entry_url": f"{base_url}/clo.html", "format": "html",
                "access_status": "OPEN", "parser_hint": "local test",
                "requires_browser": False, "evidence_basis": "T006 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-03", "url_version": 1,
            }
        ],
    }


def _run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, str(AGENT_PY)] + args,
        cwd=str(cwd), capture_output=True, text=True,
    )


def _minimal_html(ad_rows=None, td_rows=None, other_rows=None, policy_years=None,
                  report_year="2025", include_sections=True, include_vars=True):
    """构造最小 CLO 页面骨架，便于结构漂移测试。"""
    py = policy_years or ["Policy Year 1 (2024)", "Policy Year 2 (2023)"]
    ad = ad_rows if ad_rows is not None else []
    td = td_rows if td_rows is not None else []
    ot = other_rows if other_rows is not None else []

    sec = ""
    if include_sections:
        sec = (
            f"<h3>Reporting year: {report_year}</h3>"
            "<h3>1) Participating Plans - with Annual Dividend</h3>"
            "<h3>2) Participating Plans - with Terminal Dividend</h3>"
        )
    script = ""
    if include_vars:
        script = (
            "<script>"
            "var policyYears = " + json.dumps(py, ensure_ascii=False) + ";"
            "var dataSets1 = " + json.dumps(ad, ensure_ascii=False) + ";"
            "var dataSets2 = " + json.dumps(td, ensure_ascii=False) + ";"
            "var dataSets3 = " + json.dumps(ot, ensure_ascii=False) + ";"
            "</script>"
        )
    return f"<html lang='en'><body>{sec}{script}</body></html>"


# ---------------------------------------------------------------------------
# T006-1 · parse_ratio 数值断言
# ---------------------------------------------------------------------------
def test_parse_ratio_unit():
    print("\n[T006-1] 值解析：100%→1.0 / 84%→0.84 / 超过100%合法 / NA→None")
    print("-" * 60)
    check(clo_html_parser.parse_ratio("100%") == 1.0, "100% → 1.0", "100% 解析错误")
    check(clo_html_parser.parse_ratio("84%") == 0.84, "84% → 0.84", "84% 解析错误")
    check(clo_html_parser.parse_ratio("112%") == 1.12, "112% → 1.12（超过 100% 合法）", "112% 解析错误")
    check(clo_html_parser.parse_ratio("70%") == 0.70, "70% → 0.70", "70% 解析错误")
    check(clo_html_parser.parse_ratio("0%") == 0.0, "0% → 0.0", "0% 解析错误")
    check(clo_html_parser.parse_ratio("NA") is None, "'NA' → None", "'NA' 未判 None")
    check(clo_html_parser.parse_ratio("N/A") is None, "'N/A' → None", "'N/A' 未判 None")
    check(clo_html_parser.parse_ratio("") is None, "空串 → None", "空串未判 None")
    check(clo_html_parser.parse_ratio(None) is None, "None → None", "None 未判 None")


# ---------------------------------------------------------------------------
# T006-2 · parse_observation_year（数字年 / 开放区间）
# ---------------------------------------------------------------------------
def test_parse_observation_year():
    print("\n[T006-2] observation_year：Policy Year 1 (2024)→2024 / 10+ (2014 or before)→NULL")
    print("-" * 60)
    check(clo_html_parser.parse_observation_year("Policy Year 1 (2024)") == ("Policy Year 1 (2024)", 2024),
          "Policy Year 1 (2024) → (原文, 2024)", "Policy Year 1 (2024) 解析错误")
    check(clo_html_parser.parse_observation_year("Policy Year 10 (2015)") == ("Policy Year 10 (2015)", 2015),
          "Policy Year 10 (2015) → (原文, 2015)", "Policy Year 10 (2015) 解析错误")
    check(clo_html_parser.parse_observation_year("Policy Year 10+ (2014 or before)") == ("Policy Year 10+ (2014 or before)", None),
          "Policy Year 10+ (2014 or before) → (原文, None)（不虚构单年）", "开放区间映射错误")


# ---------------------------------------------------------------------------
# T006-3 · standardize_metric（官网原始名 → 标准枚举，不合并口径）
# ---------------------------------------------------------------------------
def test_standardize_metric():
    print("\n[T006-3] metric 标准化：Annual Dividend→AD / Terminal Dividend→TD / 其他→OTHER")
    print("-" * 60)
    cases = {
        "Annual Dividend": "AD",
        "Terminal Dividend": "TD",
        "Accumulated Interest": "OTHER",
        "Reversionary Bonus": "OTHER",
    }
    for raw, want in cases.items():
        got_type, got_raw = clo_html_parser.standardize_metric(raw)
        check(got_type == want and got_raw == raw, f"{raw!r} → ({want}, {raw!r})",
              f"{raw!r} → ({got_type}, {got_raw!r})")


# ---------------------------------------------------------------------------
# T006-4 · 完整 fixture 解析（不写库，纯解析）
# ---------------------------------------------------------------------------
def test_parse_fixture_full():
    print("\n[T006-4] 完整 fixture：3 产品 / 33 记录 / AD+TD / 币种分组 / NA / 排除 Universal Life 表")
    print("-" * 60)
    r = clo_html_parser.parse_clo_html(load_fixture())
    check(r["status"] == "OK", f"status=OK（{r['status']}）", f"status: {r['status']}")
    check(r["report_year"] == 2025, "report_year=2025", f"report_year: {r['report_year']}")
    check(r["product_count"] == 3, f"product_count=3（实际 {r['product_count']}）", f"product_count: {r['product_count']}")
    check(len(r["records"]) == 33, f"记录数 33（实际 {len(r['records'])}）", f"记录数: {len(r['records'])}")
    check(r["value_unparseable"] == 12, f"value_unparseable=12（实际 {r['value_unparseable']}）",
          f"value_unparseable: {r['value_unparseable']}")

    mt = Counter(x["metric_type"] for x in r["records"])
    check(dict(mt) == {"AD": 22, "TD": 11}, f"指标计数 {dict(mt)}", f"metric 计数: {dict(mt)}")
    sc = Counter(x["scope_currency_raw"] for x in r["records"])
    check(dict(sc) == {"Applied to all currencies plan": 22, "Applied to RMB plan": 11},
          f"币种分组计数 {dict(sc)}", f"scope 计数: {dict(sc)}")

    # 排除：Universal Life 结算利率表 / 导航 / 说明文字不得入库
    names = {x["product_name_raw"] for x in r["records"]}
    check("Prime Universal Life Insurance Plan" not in names, "Universal Life 结算利率表被排除", "万能寿险表被误记")
    check("Alpha Participating Endowment Plan" in names, "Alpha 产品名保留原文", "Alpha 产品名丢失")
    check("Beta RMB Savings Plan" in names, "Beta 产品名保留原文", "Beta 产品名丢失")
    check("Gamma Participating Whole Life Plan" in names, "Gamma 产品名保留原文", "Gamma 产品名丢失")
    check(all("Home" != n for n in names), "导航文本不入库", "导航文本被误记")

    by_key = {(x["product_name_raw"], x["metric_type"], x["observation_year_raw"]): x
              for x in r["records"]}
    alpha = "Alpha Participating Endowment Plan"
    beta = "Beta RMB Savings Plan"
    gamma = "Gamma Participating Whole Life Plan"

    # 数值抽查（跨年份）
    check(by_key[(alpha, "AD", "Policy Year 1 (2024)")]["normalized_value"] == 1.0
          and by_key[(alpha, "AD", "Policy Year 1 (2024)")]["observation_year"] == 2024,
          "Alpha AD Policy Year 1 (2024) 100%→1.0 且 observation_year=2024", "")
    check(by_key[(alpha, "AD", "Policy Year 10+ (2014 or before)")]["normalized_value"] == 0.76
          and by_key[(alpha, "AD", "Policy Year 10+ (2014 or before)")]["observation_year"] is None,
          "Alpha AD 开放区间 76%→0.76 且 observation_year=NULL", "开放区间落库错误")
    check(by_key[(beta, "AD", "Policy Year 8 (2017)")]["normalized_value"] == 0.84
          and by_key[(beta, "AD", "Policy Year 8 (2017)")]["scope_currency_raw"] == "Applied to RMB plan",
          "Beta AD Policy Year 8 (2017) 84%→0.84 且 scope=RMB plan", "Beta RMB 分组错误")
    check(by_key[(gamma, "TD", "Policy Year 3 (2022)")]["normalized_value"] == 0.78
          and by_key[(gamma, "TD", "Policy Year 3 (2022)")]["metric_type"] == "TD",
          "Gamma TD Policy Year 3 (2022) 78%→0.78", "Gamma TD 解析错误")

    # NA 非数值 → 保留原文、normalized=NULL
    check(by_key[(beta, "AD", "Policy Year 1 (2024)")]["normalized_value"] is None
          and by_key[(beta, "AD", "Policy Year 1 (2024)")]["raw_value"] == "NA",
          "Beta AD Policy Year 1 (2024) NA → 保留原文、normalized=NULL", "NA 处理错误")
    check(by_key[(gamma, "TD", "Policy Year 1 (2024)")]["normalized_value"] is None
          and by_key[(gamma, "TD", "Policy Year 1 (2024)")]["raw_value"] == "NA",
          "Gamma TD Policy Year 1 (2024) NA → 保留原文、normalized=NULL", "NA 处理错误")


# ---------------------------------------------------------------------------
# T006-5 · 结构漂移 → STRUCTURE_MISMATCH（CloParseError）
# ---------------------------------------------------------------------------
def test_structure_mismatch():
    print("\n[T006-5] 结构漂移：缺段落/缺变量/行宽不符/非字符串/报告年度缺失 → CloParseError")
    print("-" * 60)

    def _expect_error(html, label):
        try:
            clo_html_parser.parse_clo_html(html.encode("utf-8"))
            check(False, "", f"{label} 未触发异常（漏检）")
        except clo_html_parser.CloParseError:
            check(True, f"{label} → CloParseError", "")

    # 缺段落锚点（无 "Participating Plans - with ..."）
    _expect_error(
        "<html><body><script>var policyYears=['x'];var dataSets1=[];var dataSets2=[];var dataSets3=[];</script></body></html>",
        "缺段落锚点",
    )
    # 缺报告年度（段落存在但锚点前无 "Reporting year:"）
    _expect_error(
        _minimal_html(include_vars=False).replace("Reporting year: 2025", ""),
        "缺 Reporting year 标题",
    )
    # 缺 JS 变量 dataSets1
    html_missing_var = _minimal_html().replace("var dataSets1", "var dataSetsX")
    _expect_error(html_missing_var, "缺 dataSets1 变量")
    # 行宽不符（dataSets1 行只有 4 元素，期望 2+3=5）
    html_bad_width = _minimal_html(ad_rows=[[
        "P", "T", "S", "100%",
    ]])
    _expect_error(html_bad_width, "dataSets1 行宽不符")
    # 非字符串元素（dataSets1 值里出现数值 token，而非字符串字面量）
    html_nonstr = (
        "<html><body>"
        "<h3>Reporting year: 2025</h3>"
        "<h3>1) Participating Plans - with Annual Dividend</h3>"
        "<h3>2) Participating Plans - with Terminal Dividend</h3>"
        "<script>"
        "var policyYears = ['Policy Year 1 (2024)', 'Policy Year 2 (2023)'];"
        "var dataSets1 = [['P', 'T', 'S', 100, 100]];"
        "var dataSets2 = [];"
        "var dataSets3 = [];"
        "</script>"
        "</body></html>"
    )
    _expect_error(html_nonstr, "含非字符串元素")
    # 数组未闭合（policyYears 数组缺闭合 ']'）
    html_unclosed = (
        "<html><body>"
        "<h3>Reporting year: 2025</h3>"
        "<h3>1) Participating Plans - with Annual Dividend</h3>"
        "<h3>2) Participating Plans - with Terminal Dividend</h3>"
        "<script>"
        "var policyYears = ['Policy Year 1 (2024)', 'Policy Year 2 (2023)'"
        "var dataSets1 = []; var dataSets2 = []; var dataSets3 = [];"
        "</script>"
        "</body></html>"
    )
    _expect_error(html_unclosed, "数组未闭合")


# ---------------------------------------------------------------------------
# T006-6 · 零产品 / 零记录 → ZERO_RECORD
# ---------------------------------------------------------------------------
def test_zero_record():
    print("\n[T006-6] 零产品/零记录：dataSets 全空 → ZERO_RECORD")
    print("-" * 60)
    html = _minimal_html(ad_rows=[], td_rows=[], other_rows=[])
    r = clo_html_parser.parse_clo_html(html.encode("utf-8"))
    check(r["status"] == "ZERO_RECORD", f"status=ZERO_RECORD（{r['status']}）", f"status: {r['status']}")
    check(r["product_count"] == 0 and len(r["records"]) == 0, "零产品、零记录", "记录数非零")


# ---------------------------------------------------------------------------
# T006-7 · 端到端：抓取 → 解析 → 入库 → run_id 反查 → 幂等
# ---------------------------------------------------------------------------
def test_end_to_end_and_backref():
    print("\n[T006-7] 端到端：抓取→解析→入库→run_id 反查→幂等")
    print("-" * 60)
    srv = _LocalServer(load_fixture())
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
            check(p["records_written"] == 33, f"records_written=33（{p['records_written']}）", f"records: {p}")
            check(p["parse_status"] == "PARTIAL" and p["error_code"] == "VALUE_UNPARSEABLE",
                  f"parse_result=(PARTIAL, VALUE_UNPARSEABLE)（{p['parse_status']},{p['error_code']}）",
                  f"parse_result: {p['parse_status']},{p['error_code']}")

            n = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio WHERE run_id=?", (p["run_id"],)).fetchone()[0]
            check(n == 33, f"fulfillment_ratio 共 {n} 行", f"行数: {n}")

            # parse_result
            pr = conn.execute(
                "SELECT parse_status, records_produced, error_code FROM parse_result WHERE run_id=?", (p["run_id"],)
            ).fetchone()
            check(pr == ("PARTIAL", 33, "VALUE_UNPARSEABLE"), f"parse_result=(PARTIAL,33,VALUE_UNPARSEABLE)（{pr}）", f"parse_result: {pr}")

            # run_id 反查真实证据链
            fr = conn.execute(
                "SELECT final_url, http_status, content_hash, snapshot_path FROM fetch_run WHERE run_id=?",
                (p["run_id"],),
            ).fetchone()
            check(fr[0] == f"{srv.base}/clo.html", f"final_url 反查正确（{fr[0]}）", f"final_url: {fr[0]}")
            check(fr[1] == 200, "http_status=200", f"http_status: {fr[1]}")
            check(fr[2] == snapshot.sha256_hex(load_fixture()), "content_hash 与字节一致", "哈希不符")
            check(fr[3] == f"raw_data/CLO/1/{fr[2]}.html", "snapshot_path 形如 raw_data/CLO/1/{hash}.html", f"snapshot_path: {fr[3]}")

            # 幂等：重复解析不产生重复行
            p2 = parse_disclosure.parse_one_source(conn, fetch_recorder.get_source(conn, 1), raw_root)
            n2 = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            check(p2["result"] == "OK" and n2 == 33, f"重复解析幂等（仍 {n2} 行）", f"重复解析后 {n2} 行")
            conn.close()
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# T006-8 · 中途失败回滚
# ---------------------------------------------------------------------------
def test_rollback():
    print("\n[T006-8] 事务回滚：坏记录触发 IntegrityError，不留部分业务行")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        reg = build_registry("http://127.0.0.1:1")
        sqlite_store.init_db(db, reg)
        conn = sqlite_store.connect(db)
        run_id = fetch_recorder.record_network_error(conn, 1, note="rollback-test")
        conn.commit()

        good = {"product_name_raw": "Good", "metric_type": "AD", "metric_type_raw": "Annual Dividend",
                "report_year": 2025, "observation_year_raw": "Policy Year 1 (2024)", "observation_year": 2024,
                "scope_currency_raw": "Applied to all currencies plan", "raw_value": "100%",
                "normalized_value": 1.0, "product_id": None}
        bad = dict(good, product_name_raw="Bad", metric_type="INVALID", metric_type_raw="INVALID")

        try:
            ratio_writer.write_parse_outcome(conn, run_id, "CLO", [good, bad], "OK")
            check(False, "", "坏记录未触发异常（漏检）")
        except sqlite3.IntegrityError:
            check(True, "坏记录触发 IntegrityError", "")
        n = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio WHERE run_id=?", (run_id,)).fetchone()[0]
        check(n == 0, f"回滚后 0 行（实际 {n}）", f"回滚失败，残留 {n} 行")
        conn.close()


# ---------------------------------------------------------------------------
# T006-9 · CLI --parse 退出码
# ---------------------------------------------------------------------------
def test_cli_parse():
    print("\n[T006-9] CLI --parse：正常 0 / 未抓取非零 / 不存在源非零")
    print("-" * 60)
    srv = _LocalServer(load_fixture())
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
            check(data["records_written"] == 33, f"CLI 报告 records_written=33（{data['records_written']}）", f"records: {data}")
            check(data["parse_status"] == "PARTIAL", f"CLI 报告 parse_status=PARTIAL（{data['parse_status']}）", f"parse_status: {data}")
            check(data["error_code"] == "VALUE_UNPARSEABLE", f"CLI 报告 error_code=VALUE_UNPARSEABLE（{data['error_code']}）", f"error_code: {data}")

            r = _run_cli(["--parse", "999", "--registry", str(reg_file), "--db-path", str(db),
                          "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode != 0, f"不存在源 --parse 退出非零（{r.returncode}）", f"退出码 {r.returncode}")
    finally:
        srv.stop()


def main():
    print("=" * 60)
    print("ICD 集成测试（T006 · 中国人寿海外 CLO HTML 解析与入库）")
    print("=" * 60)
    test_parse_ratio_unit()
    test_parse_observation_year()
    test_standardize_metric()
    test_parse_fixture_full()
    test_structure_mismatch()
    test_zero_record()
    test_end_to_end_and_backref()
    test_rollback()
    test_cli_parse()

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
