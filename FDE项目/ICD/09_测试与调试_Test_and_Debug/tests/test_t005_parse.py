#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD 集成测试（T005）· CTF Life 分红实现率 HTML 表格解析、标准化、事务入库

覆盖任务书 T005 验收标准：
- fixture 与真实证据分离（本文件只跑脱敏 fixture；真实验证单独记录，见任务书回执）。
- 记录数 = 明确业务单元格之和（按表格层级/表头/rowspan/colspan 恢复，不用全页百分号正则）。
- 覆盖：≥2 产品、≥2 指标、跨年份、多层表头、rowspan/colspan、脚注/非数值值、
  不可解析值、空表、结构漂移、重复执行、事务回滚。
- 段落作用域：只解析 "Fulfillment Ratios of Dividends/Bonuses" 段落；
  导航、TCV 段落、无关表格、HTML 注释一律忽略。
- 数值断言：100%→1.0、94%→0.94、112%→1.12、超过 100% 合法、Before 2021→NULL。
- 不联网（除本机临时 HTTP 服务器）；所有写操作在 tempfile 内，不污染默认数据库。

运行：python3 09_测试与调试_Test_and_Debug/tests/test_t005_parse.py
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
FIXTURE_PATH = TESTS_DIR / "fixtures" / "ctf_fixture.html"

for _pkg_dir in (
    "05_集成工具_Integrate_Tools",
    "07_接入记忆_Integrate_Memory",
    "06_开发技能_Develop_Skills",
):
    sys.path.insert(0, str(ICD_DIR / _pkg_dir))

from skills import ctf_html_parser, fetch_disclosure, parse_disclosure
from tools import fetch_recorder, ratio_writer, snapshot, sqlite_store

AGENT_PY = ICD_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"

FAILURES = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"✅ {ok_msg}")
    else:
        print(f"❌ {fail_msg}")
        FAILURES.append(fail_msg)


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
    """T005 本地测试注册表：CTF fulfillment_ratio（html）。source_id=1。"""
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-03",
        "description": "T005 本地测试注册表",
        "insurers": [{"insurer_code": "CTF", "name_en": "CTF Life", "name_zh": "周大福人寿"}],
        "sources": [
            {
                "insurer_code": "CTF", "disclosure_type": "fulfillment_ratio",
                "entry_url": f"{base_url}/ctf.html", "format": "html",
                "access_status": "OPEN", "parser_hint": "local test",
                "requires_browser": False, "evidence_basis": "T005 本地服务器",
                "allows_empty": False, "last_verified_at": "2026-09-03", "url_version": 1,
            }
        ],
    }


def _run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, str(AGENT_PY)] + args,
        cwd=str(cwd), capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# T005-1 · parse_ratio 数值断言
# ---------------------------------------------------------------------------
def test_parse_ratio_unit():
    print("\n[T005-1] 值解析：100%→1.0 / 94%→0.94 / 超过100%合法 / 非数值→None")
    print("-" * 60)
    check(ctf_html_parser.parse_ratio("100%") == 1.0, "100% → 1.0", "100% 解析错误")
    check(ctf_html_parser.parse_ratio("94%") == 0.94, "94% → 0.94", "94% 解析错误")
    check(ctf_html_parser.parse_ratio("112%") == 1.12, "112% → 1.12（超过 100% 合法）", "112% 解析错误")
    check(ctf_html_parser.parse_ratio("105%") == 1.05, "105% → 1.05", "105% 解析错误")
    check(ctf_html_parser.parse_ratio("0%") == 0.0, "0% → 0.0", "0% 解析错误")
    for v in ("Closed to Sales", "Not yet launched", "Zero Bonus",
              "No Termination", "No Policy",
              "No policy has reached the first policy anniversary and thus no Fulfillment Ratios are shown."):
        check(ctf_html_parser.parse_ratio(v) is None, f"{v[:20]!r} → None", f"{v[:20]!r} 未判 None")
    check(ctf_html_parser.parse_ratio("") is None, "空串 → None", "空串未判 None")
    check(ctf_html_parser.parse_ratio(None) is None, "None → None", "None 未判 None")


# ---------------------------------------------------------------------------
# T005-2 · parse_observation_year（数字年 / 开放区间）
# ---------------------------------------------------------------------------
def test_parse_observation_year():
    print("\n[T005-2] observation_year：1(2024)→2024 / 11+(Before 2014)→NULL")
    print("-" * 60)
    check(ctf_html_parser.parse_observation_year("1(2024)") == ("1(2024)", 2024),
          "1(2024) → ('1(2024)', 2024)", "1(2024) 解析错误")
    check(ctf_html_parser.parse_observation_year("10(2015)") == ("10(2015)", 2015),
          "10(2015) → ('10(2015)', 2015)", "10(2015) 解析错误")
    check(ctf_html_parser.parse_observation_year("11+(Before 2014)") == ("11+(Before 2014)", None),
          "11+(Before 2014) → ('11+(Before 2014)', None)（不虚构单年）", "11+(Before 2014) 映射错误")


# ---------------------------------------------------------------------------
# T005-3 · standardize_metric（官网原始名 → 标准枚举，不合并口径）
# ---------------------------------------------------------------------------
def test_standardize_metric():
    print("\n[T005-3] metric 标准化：AD/TD/RB/TB 一一对应，Policy Value/Special Bonus→OTHER")
    print("-" * 60)
    cases = {
        "Annual Dividends": "AD",
        "Terminal Dividends": "TD",
        "Reversionary Bonus": "RB",
        "Terminal Bonus": "TB",
        "Policy Value": "OTHER",
        "Special Bonus": "OTHER",
    }
    for raw, want in cases.items():
        got_type, got_raw = ctf_html_parser.standardize_metric(raw)
        check(got_type == want and got_raw == raw, f"{raw!r} → ({want}, {raw!r})",
              f"{raw!r} → ({got_type}, {got_raw!r})")


# ---------------------------------------------------------------------------
# T005-4 · 完整 fixture 解析（不写库，纯解析）
# ---------------------------------------------------------------------------
def test_parse_fixture_full():
    print("\n[T005-4] 完整 fixture：3 产品 / 20 记录 / 四类指标 / rowspan|colspan / 空表不丢产品")
    print("-" * 60)
    r = ctf_html_parser.parse_ctf_html(load_fixture())
    check(r["status"] == "OK", f"status=OK（{r['status']}）", f"status: {r['status']}")
    check(r["report_year"] == 2025, "report_year=2025", f"report_year: {r['report_year']}")
    check(r["product_count"] == 3, "product_count=3（含空表产品）", f"product_count: {r['product_count']}")
    check(len(r["records"]) == 20, f"记录数 20（实际 {len(r['records'])}）", f"记录数: {len(r['records'])}")
    check(r["value_unparseable"] == 9, f"value_unparseable=9（实际 {r['value_unparseable']}）",
          f"value_unparseable: {r['value_unparseable']}")

    mt = Counter(x["metric_type"] for x in r["records"])
    check(dict(mt) == {"AD": 4, "TD": 4, "RB": 8, "OTHER": 4}, f"指标计数正确 {dict(mt)}", f"metric 计数: {dict(mt)}")
    sc = Counter(x["scope_currency_raw"] for x in r["records"])
    check(dict(sc) == {"USD": 16, "HKD": 4}, f"币种计数正确 {dict(sc)}", f"scope 计数: {dict(sc)}")

    # 段落作用域：TCV 产品 / 导航 / 无关表格不得出现
    names = {x["product_name_raw"] for x in r["records"]}
    check("Should Be Ignored - TCV Product" not in names, "TCV 段落产品被忽略", "TCV 产品被误记")
    check(all("TCV" not in n for n in names), "无 TCV/导航记录", "存在非履行率记录")

    # 产品名保留原文
    check("Alpha Test Plan - Life insurance (participating)" in names, "Alpha 产品名保留原文", "Alpha 产品名丢失")
    check("Beta Test Plan - Life insurance with cash coupons (participating)" in names, "Beta 产品名保留原文", "Beta 产品名丢失")

    # 数值抽查（验收标准 2）：以 (产品, 指标, 币种, 观察期原文) 为键
    by_key = {(x["product_name_raw"], x["metric_type"], x["scope_currency_raw"], x["observation_year_raw"]): x
              for x in r["records"]}
    alpha = "Alpha Test Plan - Life insurance (participating)"
    beta = "Beta Test Plan - Life insurance with cash coupons (participating)"
    check(by_key[(alpha, "AD", "USD", "1(2024)")]["normalized_value"] == 1.0, "Alpha AD 1(2024) 100%→1.0", "")
    check(by_key[(alpha, "AD", "USD", "2(2023)")]["normalized_value"] == 0.94, "Alpha AD 2(2023) 94%→0.94", "")
    check(by_key[(alpha, "AD", "USD", "3(2022)")]["normalized_value"] == 1.12, "Alpha AD 3(2022) 112%→1.12", "")
    check(by_key[(alpha, "AD", "USD", "4+(Before 2021)")]["normalized_value"] == 0.8
          and by_key[(alpha, "AD", "USD", "4+(Before 2021)")]["observation_year"] is None,
          "Alpha AD 4+(Before 2021) 80%→0.8 且 observation_year=NULL", "Before 2021 落库错误")
    check(by_key[(alpha, "TD", "USD", "1(2024)")]["normalized_value"] is None
          and by_key[(alpha, "TD", "USD", "1(2024)")]["raw_value"] == "Closed to Sales",
          "Alpha TD Closed to Sales → 保留原文、normalized=NULL", "非数值值处理错误")
    # rowspan：Beta RB 两个币种各 4 条
    check(by_key[(beta, "RB", "USD", "1(2024)")]["normalized_value"] == 1.0, "Beta RB USD 1(2024) 100%→1.0", "")
    check(by_key[(beta, "RB", "HKD", "2(2023)")]["normalized_value"] == 1.09, "Beta RB HKD 2(2023) 109%→1.09", "")
    check(by_key[(beta, "RB", "HKD", "4+(Before 2021)")]["normalized_value"] is None
          and by_key[(beta, "RB", "HKD", "4+(Before 2021)")]["raw_value"] == "No Termination",
          "Beta RB HKD No Termination → NULL", "No Termination 处理错误")
    # colspan：Beta Policy Value 跨 4 个观察期，各一条记录、normalized=NULL
    pv = [x for x in r["records"] if x["metric_type"] == "OTHER"]
    check(len(pv) == 4, f"Policy Value colspan=4 → 4 条记录（{len(pv)}）", f"PV 记录数: {len(pv)}")
    check(all(x["raw_value"] == "No policy has reached the first policy anniversary and thus no Fulfillment Ratios are shown."
              and x["normalized_value"] is None for x in pv),
          "Policy Value colspan 传播到 4 观察期且 normalized=NULL", "colspan 传播错误")


# ---------------------------------------------------------------------------
# T005-5 · 结构漂移 → STRUCTURE_MISMATCH（CtfParseError）
# ---------------------------------------------------------------------------
def test_structure_mismatch():
    print("\n[T005-5] 结构漂移：缺段落/缺表头/观察期表头异常 → CtfParseError")
    print("-" * 60)

    # 缺段落标题
    html_missing_section = "<html><body><h3>Total Cash Value Ratio</h3><table><tr><td>x</td></tr></table></body></html>"
    _expect_error(html_missing_section, "缺段落标题")

    # 段落存在但产品表格缺 Type/Policy Currency 表头
    html_bad_header = (
        "<h3>Fulfillment Ratios of Dividends/Bonuses</h3>"
        '<div class="tableStyleRatio__container">'
        '<p class="text-center fzBold">Bad Header Plan</p>'
        '<div class="tableStyleRatio__wrapper"><table class="tableStyleRatio">'
        "<thead><tr><th>Something</th><th>Else</th></tr></thead>"
        "<tbody><tr><td>100%</td><td>94%</td></tr></tbody>"
        "</table></div></div>"
    )
    _expect_error(html_bad_header, "缺 Type/Policy Currency 表头")

    # 观察期表头结构异常（标签不匹配模式）
    html_bad_obs = (
        "<h3>Fulfillment Ratios of Dividends/Bonuses</h3>"
        '<div class="tableStyleRatio__container">'
        '<p class="text-center fzBold">Bad Obs Plan</p>'
        '<div class="tableStyleRatio__wrapper"><table class="tableStyleRatio">'
        "<thead><tr><th rowspan=\"3\">Type</th><th rowspan=\"3\">Policy Currency</th>"
        "<td colspan=\"2\">Fulfillment Ratios for Reporting Year 2025</td></tr>"
        "<tr><td colspan=\"2\">Policy Year (Policy Effective in)</td></tr>"
        "<tr><td>FY24/25</td><td>FY25/26</td></tr></thead>"
        "<tbody><tr><td>Annual Dividends</td><td>USD</td><td>100%</td><td>94%</td></tr></tbody>"
        "</table></div></div>"
    )
    _expect_error(html_bad_obs, "观察期表头结构异常")


def _expect_error(html: str, label: str):
    try:
        ctf_html_parser.parse_ctf_html(html.encode("utf-8"))
        check(False, "", f"{label} 未抛错（漏检）")
    except ctf_html_parser.CtfParseError as e:
        check(True, f"{label} → CtfParseError: {str(e)[:60]}", "")


# ---------------------------------------------------------------------------
# T005-6 · 零记录 → ZERO_RECORD
# ---------------------------------------------------------------------------
def test_zero_record():
    print("\n[T005-6] 零产品 / 零业务记录 → ZERO_RECORD")
    print("-" * 60)
    # 段落存在但无产品容器 → ZERO_RECORD（零产品）
    html_no_products = "<h3>Fulfillment Ratios of Dividends/Bonuses</h3><p>no tables here</p>"
    r = ctf_html_parser.parse_ctf_html(html_no_products.encode("utf-8"))
    check(r["status"] == "ZERO_RECORD" and r["product_count"] == 0,
          f"零产品 → ZERO_RECORD（{r['status']}）", f"status: {r['status']}")

    # 有产品但全部为空表 → ZERO_RECORD（零业务记录）
    html_all_empty = (
        "<h3>Fulfillment Ratios of Dividends/Bonuses</h3>"
        '<div class="tableStyleRatio__container">'
        '<p class="text-center fzBold">All Empty Plan</p>'
        '<div class="tableStyleRatio__wrapper"><table class="tableStyleRatio">'
        "<thead><tr><th rowspan=\"3\">Type</th><th rowspan=\"3\">Policy Currency</th>"
        "<td colspan=\"2\">Fulfillment Ratios for Reporting Year 2025</td></tr>"
        "<tr><td colspan=\"2\">Policy Year (Policy Effective in)</td></tr>"
        "<tr><td>1(2024)</td><td>2(2023)</td></tr></thead>"
        "<tbody></tbody></table></div></div>"
    )
    r = ctf_html_parser.parse_ctf_html(html_all_empty.encode("utf-8"))
    check(r["status"] == "ZERO_RECORD" and r["product_count"] == 1 and r["report_year"] == 2025,
          f"全空表 → ZERO_RECORD（{r['status']}）", f"status: {r['status']} report_year={r['report_year']}")


# ---------------------------------------------------------------------------
# T005-7 · 端到端：fetch → parse → 入库 → run_id 反查 + 幂等
# ---------------------------------------------------------------------------
def _fetch_and_parse(body, reg):
    td = tempfile.TemporaryDirectory()
    tdp = Path(td.name)
    db, raw_root = tdp / "icd.db", tdp / "raw_data"
    sqlite_store.init_db(db, reg)
    conn = sqlite_store.connect(db)
    src = fetch_recorder.get_source(conn, 1)
    f = fetch_disclosure.fetch_one_source(conn, src, raw_root)
    p = parse_disclosure.parse_one_source(conn, src, raw_root)
    return td, db, conn, raw_root, f, p


def test_end_to_end_and_backref():
    print("\n[T005-7] 端到端：抓取→解析→入库 + run_id 反查 URL/哈希/快照 + 幂等")
    print("-" * 60)
    srv = _LocalServer(load_fixture())
    try:
        reg = build_registry(srv.base)
        td, db, conn, raw_root, f, p = _fetch_and_parse(load_fixture(), reg)
        try:
            check(f["result"] == "OK", f"fetch OK（{f['result']}）", f"fetch: {f}")
            check(p["result"] == "OK", f"parse OK（{p['result']}）", f"parse: {p}")
            check(p["parse_status"] == "PARTIAL", f"parse_status=PARTIAL（{p['parse_status']}）", f"parse_status: {p['parse_status']}")
            check(p["error_code"] == "VALUE_UNPARSEABLE", f"error_code=VALUE_UNPARSEABLE（{p['error_code']}）", f"error_code: {p['error_code']}")
            check(p["records_written"] == 20, f"入库 20 行（{p['records_written']}）", f"records: {p['records_written']}")

            n = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            check(n == 20, f"fulfillment_ratio 共 {n} 行", f"行数: {n}")

            # parse_result
            pr = conn.execute(
                "SELECT parse_status, records_produced, error_code FROM parse_result WHERE run_id=?", (p["run_id"],)
            ).fetchone()
            check(pr == ("PARTIAL", 20, "VALUE_UNPARSEABLE"), f"parse_result=(PARTIAL,20,VALUE_UNPARSEABLE)（{pr}）", f"parse_result: {pr}")

            # run_id 反查真实证据链
            fr = conn.execute(
                "SELECT final_url, http_status, content_hash, snapshot_path FROM fetch_run WHERE run_id=?",
                (p["run_id"],),
            ).fetchone()
            check(fr[0] == f"{srv.base}/ctf.html", f"final_url 反查正确（{fr[0]}）", f"final_url: {fr[0]}")
            check(fr[1] == 200, "http_status=200", f"http_status: {fr[1]}")
            check(fr[2] == snapshot.sha256_hex(load_fixture()), "content_hash 与字节一致", "哈希不符")
            check(fr[3] == f"raw_data/CTF/1/{fr[2]}.html", "snapshot_path 形如 raw_data/CTF/1/{hash}.html", f"snapshot_path: {fr[3]}")

            # 幂等：重复解析不产生重复行
            p2 = parse_disclosure.parse_one_source(conn, fetch_recorder.get_source(conn, 1), raw_root)
            n2 = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            check(p2["result"] == "OK" and n2 == 20, f"重复解析幂等（仍 {n2} 行）", f"重复解析后 {n2} 行")
        finally:
            conn.close()
            td.cleanup()
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# T005-8 · 中途失败回滚
# ---------------------------------------------------------------------------
def test_rollback():
    print("\n[T005-8] 事务回滚：坏记录触发 IntegrityError，不留部分业务行")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        reg = build_registry("http://127.0.0.1:1")
        sqlite_store.init_db(db, reg)
        conn = sqlite_store.connect(db)
        run_id = fetch_recorder.record_network_error(conn, 1, note="rollback-test")
        conn.commit()

        good = {"product_name_raw": "Good", "metric_type": "AD", "metric_type_raw": "Annual Dividends",
                "report_year": 2025, "observation_year_raw": "1(2024)", "observation_year": 2024,
                "scope_currency_raw": "USD", "raw_value": "100%", "normalized_value": 1.0, "product_id": None}
        bad = dict(good, product_name_raw="Bad", metric_type="INVALID", metric_type_raw="INVALID")

        try:
            ratio_writer.write_parse_outcome(conn, run_id, "CTF", [good, bad], "OK")
            check(False, "", "坏记录未触发异常（漏检）")
        except sqlite3.IntegrityError:
            check(True, "坏记录触发 IntegrityError", "")
        n = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio WHERE run_id=?", (run_id,)).fetchone()[0]
        check(n == 0, f"回滚后 0 行（实际 {n}）", f"回滚失败，残留 {n} 行")
        conn.close()


# ---------------------------------------------------------------------------
# T005-9 · CLI --parse 退出码
# ---------------------------------------------------------------------------
def test_cli_parse():
    print("\n[T005-9] CLI --parse：正常 0 / 未抓取非零 / 不存在源非零")
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
            check(data["records_written"] == 20, f"CLI 报告 records_written=20（{data['records_written']}）", f"records: {data}")
            check(data["parse_status"] == "PARTIAL", f"CLI 报告 parse_status=PARTIAL（{data['parse_status']}）", f"parse_status: {data}")
            check(data["error_code"] == "VALUE_UNPARSEABLE", f"CLI 报告 error_code=VALUE_UNPARSEABLE（{data['error_code']}）", f"error_code: {data}")

            r = _run_cli(["--parse", "999", "--registry", str(reg_file), "--db-path", str(db),
                          "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode != 0, f"不存在源 --parse 退出非零（{r.returncode}）", f"退出码 {r.returncode}")
    finally:
        srv.stop()


def main():
    print("=" * 60)
    print("ICD 集成测试（T005 · CTF Life HTML 解析与入库）")
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
