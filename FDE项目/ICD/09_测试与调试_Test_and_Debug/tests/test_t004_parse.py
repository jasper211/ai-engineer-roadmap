#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD 集成测试（T004）· AIA JSON 分红实现率解析、标准化、事务入库

覆盖任务书 T004 验收标准与三项决策补充：
- fixture 与真实证据分离（本文件只跑脱敏 fixture；真实验证单独记录，见任务书回执）。
- 数值断言覆盖 100%→1.0、94%→0.94、超过 100% 的合法值（112%→1.12、105%→1.05）。
- 记录数 = 所有合法 AD/TD/RB/TB 观测项之和，产品不静默丢失。
- 多产品、AD/TD/RB/TB 并存、跨年份、Before 2015（observation_year=NULL）、真实数字年 2014、
  空数组、坏比例、脚注、重复执行、结构漂移、中途失败回滚。
- 旧版 fulfillment_ratio 明确失败（SchemaMigrationRequired），不假装新列已存在。
- 存在不可数值化观测项时 parse_result 写 PARTIAL + VALUE_UNPARSEABLE，仍保留全部原文记录。
- 不联网（除本机临时 HTTP 服务器）；所有写操作在 tempfile 内，不污染默认数据库。

运行：python3 09_测试与调试_Test_and_Debug/tests/test_t004_parse.py
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
FIXTURE_PATH = TESTS_DIR / "fixtures" / "aia_fixture.json"

for _pkg_dir in (
    "05_集成工具_Integrate_Tools",
    "07_接入记忆_Integrate_Memory",
    "06_开发技能_Develop_Skills",
):
    sys.path.insert(0, str(ICD_DIR / _pkg_dir))

from skills import aia_json_parser, fetch_disclosure, parse_disclosure
from tools import fetch_recorder, ratio_writer, snapshot, sqlite_store

AGENT_PY = ICD_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"

FAILURES = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"✅ {ok_msg}")
    else:
        print(f"❌ {fail_msg}")
        FAILURES.append(fail_msg)


def load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


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
                self.send_header("Content-Type", "application/json")
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
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-03",
        "description": "T004 本地测试注册表",
        "insurers": [{"insurer_code": "AIA", "name_en": "AIA", "name_zh": "友邦"}],
        "sources": [
            {
                "insurer_code": "AIA", "disclosure_type": "fulfillment_ratio",
                "entry_url": f"{base_url}/fr.json", "format": "json",
                "access_status": "OPEN", "parser_hint": "local test",
                "requires_browser": False, "evidence_basis": "T004 本地服务器",
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
# T004-1 · Schema 新列与枚举
# ---------------------------------------------------------------------------
def test_schema_new_columns():
    print("\n[T004-1] fulfillment_ratio 新列 metric_type/metric_type_raw/scope_currency_raw/observation_year_raw + 枚举")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        reg = build_registry("http://127.0.0.1:1")
        sqlite_store.init_db(db, reg)  # 建表 + 播种 AIA 险企
        conn = sqlite_store.connect(db)
        cols = sqlite_store.fulfillment_ratio_columns(conn)
        check("metric_type" in cols, "metric_type 列存在", f"缺 metric_type：{cols}")
        check("metric_type_raw" in cols, "metric_type_raw 列存在", f"缺 metric_type_raw：{cols}")
        check("scope_currency_raw" in cols, "scope_currency_raw 列存在", f"缺 scope_currency_raw：{cols}")
        check("observation_year_raw" in cols, "observation_year_raw 列存在", f"缺 observation_year_raw：{cols}")
        check("dividend_type" not in cols, "旧列 dividend_type 已移除", "旧列 dividend_type 仍在")

        # observation_year 必须可空（v0.3：Before 2015 → NULL）
        notnull = sqlite_store._ratio_column_notnull(conn)
        check(notnull.get("observation_year", 1) == 0, "observation_year 可空（v0.3）", "observation_year 仍为 NOT NULL")

        # 造一个合法 run_id（满足 run_id 外键），再单独测 metric_type 枚举
        run_id = fetch_recorder.record_network_error(conn, 1, note="enum-test")
        conn.commit()

        # 枚举：AD/TD/RB/TB/TCV/OTHER 合法，REVERSIONARY/未知 拒绝
        def _try_insert(mt):
            try:
                conn.execute(
                    "INSERT INTO fulfillment_ratio (insurer_code, product_name_raw, metric_type,"
                    " metric_type_raw, report_year, observation_year_raw, observation_year, scope_currency_raw,"
                    " raw_value, run_id) VALUES ('AIA','P',?,'RAW',2025,'2024',2024,'All','100%',?)",
                    (mt, run_id),
                )
                return True
            except sqlite3.IntegrityError:
                return False

        for mt in ("AD", "TD", "RB", "TB", "TCV", "OTHER"):
            check(_try_insert(mt), f"枚举 {mt} 可插入", f"枚举 {mt} 被拒绝")
        check(not _try_insert("REVERSIONARY"), "REVERSIONARY 已被拒绝（旧值移除）", "REVERSIONARY 被误放行")
        check(not _try_insert("INVALID"), "未知枚举被拒绝", "未知枚举被误放行")
        conn.close()


# ---------------------------------------------------------------------------
# T004-2 · 旧 Schema 迁移检测
# ---------------------------------------------------------------------------
def test_migration_detection():
    print("\n[T004-2] 旧版 fulfillment_ratio 明确失败（SchemaMigrationRequired）")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "legacy.db"
        conn = sqlite_store.connect(db)
        conn.execute(
            "CREATE TABLE fulfillment_ratio ("
            "ratio_id INTEGER PRIMARY KEY, insurer_code TEXT NOT NULL,"
            "product_name_raw TEXT NOT NULL,"
            "dividend_type TEXT NOT NULL CHECK (dividend_type IN ('AD','TD','TCV','REVERSIONARY','OTHER')),"
            "report_year INTEGER NOT NULL, observation_year INTEGER NOT NULL,"
            "raw_value TEXT NOT NULL, normalized_value REAL,"
            "unit TEXT NOT NULL DEFAULT 'percent', run_id INTEGER NOT NULL,"
            "UNIQUE (insurer_code, product_name_raw, dividend_type, report_year, observation_year, run_id))"
        )
        conn.commit()
        conn.close()

        reg = build_registry("http://127.0.0.1:1")
        try:
            sqlite_store.init_db(db, reg)
            check(False, "", "旧表 init_db 未失败（漏检）")
        except sqlite_store.SchemaMigrationRequired as e:
            check("dividend_type" in str(e), f"旧表被检出并拒绝：{e}", f"错误信息不含 dividend_type: {e}")

        # CLI 黑盒：--init-db 旧库非零退出
        reg_file = Path(td) / "reg.json"
        reg_file.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        r = _run_cli(["--init-db", "--registry", str(reg_file), "--db-path", str(db)], REPO_ROOT)
        check(r.returncode != 0, f"CLI --init-db 旧库退出非零（{r.returncode}）", f"CLI 退出码 {r.returncode}")
        check("迁移" in r.stderr or "Schema" in r.stderr, "CLI stderr 含迁移提示", f"stderr 无迁移提示: {r.stderr}")

    # 第三项决策：v0.2 表（有 metric_type/scope_currency_raw，但缺 observation_year_raw、
    # observation_year 仍 NOT NULL）也必须被检出为旧版
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "v02.db"
        conn = sqlite_store.connect(db)
        conn.execute(
            "CREATE TABLE fulfillment_ratio ("
            "ratio_id INTEGER PRIMARY KEY, insurer_code TEXT NOT NULL,"
            "product_name_raw TEXT NOT NULL, metric_type TEXT NOT NULL,"
            "metric_type_raw TEXT NOT NULL, report_year INTEGER NOT NULL,"
            "observation_year INTEGER NOT NULL,"
            "scope_currency_raw TEXT NOT NULL DEFAULT 'All',"
            "raw_value TEXT NOT NULL, normalized_value REAL,"
            "unit TEXT NOT NULL DEFAULT 'percent', run_id INTEGER NOT NULL,"
            "UNIQUE (insurer_code, product_name_raw, metric_type, scope_currency_raw, report_year, observation_year, run_id))"
        )
        conn.commit()
        conn.close()
        reg = build_registry("http://127.0.0.1:1")
        try:
            sqlite_store.init_db(db, reg)
            check(False, "", "v0.2 表 init_db 未失败（漏检 observation_year_raw/NOT NULL）")
        except sqlite_store.SchemaMigrationRequired as e:
            check("observation_year_raw" in str(e) or "observation_year" in str(e),
                  f"v0.2 表被检出并拒绝：{e}", f"错误信息不含 observation_year: {e}")


# ---------------------------------------------------------------------------
# T004-3 · parse_ratio 数值断言
# ---------------------------------------------------------------------------
def test_parse_ratio_unit():
    print("\n[T004-3] ratio 解析：100%→1.0 / 94%→0.94 / 超过100%合法 / 脚注 / 不可解析")
    print("-" * 60)
    check(aia_json_parser.parse_ratio("100%") == 1.0, "100% → 1.0", "100% 解析错误")
    check(aia_json_parser.parse_ratio("94%") == 0.94, "94% → 0.94", "94% 解析错误")
    check(aia_json_parser.parse_ratio("112%") == 1.12, "112% → 1.12（超过 100% 合法）", "112% 解析错误")
    check(aia_json_parser.parse_ratio("105%") == 1.05, "105% → 1.05", "105% 解析错误")
    check(aia_json_parser.parse_ratio("0%") == 0.0, "0% → 0.0", "0% 解析错误")
    check(aia_json_parser.parse_ratio("100%<sup>(6)</sup>") == 1.0, "脚注 100%<sup>(6)</sup> → 1.0", "脚注解析错误")
    check(aia_json_parser.parse_ratio("Closed to sales") is None, "Closed to sales → None", "Closed to sales 未判 None")
    check(aia_json_parser.parse_ratio("Not yet launched") is None, "Not yet launched → None", "Not yet launched 未判 None")
    check(aia_json_parser.parse_ratio("N.A.<sup>(5)</sup>") is None, "N.A.<sup>(5)</sup> → None", "N.A. 未判 None")
    check(aia_json_parser.parse_ratio("") is None, "空串 → None", "空串未判 None")
    check(aia_json_parser.parse_ratio(None) is None, "None → None", "None 未判 None")


# ---------------------------------------------------------------------------
# T004-4 · parse_observation_year（Before 2015）
# ---------------------------------------------------------------------------
def test_parse_observation_year():
    print("\n[T004-4] observation_year：数字年(原文+整数) / Before 2015 → NULL / 非法标签抛错")
    print("-" * 60)
    check(aia_json_parser.parse_observation_year("2024") == ("2024", 2024), "2024 → ('2024', 2024)", "2024 解析错误")
    check(aia_json_parser.parse_observation_year("2015") == ("2015", 2015), "2015 → ('2015', 2015)", "2015 解析错误")
    check(aia_json_parser.parse_observation_year("Before 2015") == ("Before 2015", None),
          "Before 2015 → ('Before 2015', None)（不虚构 2014）", "Before 2015 映射错误")
    try:
        aia_json_parser.parse_observation_year("FY2024/25")
        check(False, "", "非法年份标签未抛错")
    except ValueError:
        check(True, "非法年份标签抛 ValueError", "")


# ---------------------------------------------------------------------------
# T004-5 · 完整 fixture 解析（不写库，纯解析）
# ---------------------------------------------------------------------------
def test_parse_fixture_full():
    print("\n[T004-5] 完整 fixture：6 产品 / 14 记录 / 四类指标 / 币种分组 / 空数组不丢产品")
    print("-" * 60)
    body = FIXTURE_PATH.read_bytes()
    r = aia_json_parser.parse_aia_json(body)
    check(r["status"] == "OK", f"status=OK（{r['status']}）", f"status 错误: {r['status']}")
    check(r["report_year"] == 2025, "report_year=2025", f"report_year: {r['report_year']}")
    check(r["product_count"] == 6, "product_count=6", f"product_count: {r['product_count']}")
    check(len(r["records"]) == 14, f"记录数 14（实际 {len(r['records'])}）", f"记录数: {len(r['records'])}")
    check(r["value_unparseable"] == 3, f"value_unparseable=3（实际 {r['value_unparseable']}）", f"value_unparseable: {r['value_unparseable']}")

    from collections import Counter
    mt = Counter(x["metric_type"] for x in r["records"])
    check(dict(mt) == {"AD": 7, "TD": 2, "RB": 2, "TB": 3}, f"四类指标计数正确 {dict(mt)}", f"metric_type 计数: {dict(mt)}")
    sc = Counter(x["scope_currency_raw"] for x in r["records"])
    check(dict(sc) == {"All": 12, "USD": 1, "HKD / MOP": 1}, f"币种分组计数正确 {dict(sc)}", f"scope 计数: {dict(sc)}")

    # 产品不静默丢失：6 个产品名都应被处理（含空数组产品在 pData 中但 0 记录）
    names_in_pdata = {p["productNm"]["en"] for p in json.loads(body.decode("utf-8"))["pData"]}
    names_in_records = {x["product_name_raw"] for x in r["records"]}
    check(names_in_records <= names_in_pdata, "记录中的产品名都在 pData 内", "记录中出现未知产品名")

    # 数值抽查（验收标准 2）：以 observation_year_raw 为键（唯一键口径）
    by_raw = {(x["product_name_raw"], x["metric_type"], x["observation_year_raw"]): x for x in r["records"]}
    check(by_raw[("Product Alpha", "AD", "2024")]["normalized_value"] == 1.0, "Alpha AD 2024 → 1.0", "")
    check(by_raw[("Product Alpha", "AD", "2023")]["normalized_value"] == 0.94, "Alpha AD 2023 → 0.94", "")
    check(by_raw[("Product Alpha", "AD", "2022")]["normalized_value"] == 1.12, "Alpha AD 2022 → 1.12", "")
    check(by_raw[("Product Alpha", "AD", "Before 2015")]["observation_year"] is None
          and by_raw[("Product Alpha", "AD", "Before 2015")]["normalized_value"] == 0.8
          and by_raw[("Product Alpha", "AD", "Before 2015")]["raw_value"] == "80%",
          "Alpha AD Before 2015 → observation_year=NULL / 0.8（不虚构 2014）", "Before 2015 落库错误")
    check(by_raw[("Product Alpha", "AD", "2014")]["observation_year"] == 2014
          and by_raw[("Product Alpha", "AD", "2014")]["normalized_value"] == 0.9,
          "Alpha AD 真实数字年 2014 → observation_year=2014 / 0.9（与 Before 2015 不冲突）", "2014 落库错误")
    check(by_raw[("Product Alpha", "TD", "2024")]["normalized_value"] is None
          and by_raw[("Product Alpha", "TD", "2024")]["raw_value"] == "Closed to sales",
          "不可解析值保留 raw_value、normalized=NULL", "不可解析值处理错误")


# ---------------------------------------------------------------------------
# T004-6 · 结构漂移 → STRUCTURE_MISMATCH
# ---------------------------------------------------------------------------
def test_parse_structure_mismatch():
    print("\n[T004-6] 结构漂移：缺键/类型错误 → STRUCTURE_MISMATCH（AiaParseError）")
    print("-" * 60)
    base = load_fixture()

    cases = {
        "report_year 缺失": lambda d: d.pop("report_year"),
        "report_year 非整数": lambda d: d.update(report_year="2025"),
        "pData 缺失": lambda d: d.pop("pData"),
        "pData 非数组": lambda d: d.update(pData={"x": 1}),
        "产品非对象": lambda d: d["pData"].__setitem__(0, "not-a-dict"),
        "productNm 缺失": lambda d: d["pData"][0].pop("productNm"),
        "指标非数组": lambda d: d["pData"][0].update(AD="oops"),
        "data 非数组": lambda d: d["pData"][0]["AD"][0].update(data="oops"),
        "缺 ratio 键": lambda d: d["pData"][0]["AD"][0]["data"][0].pop("ratio"),
        "非法年份": lambda d: d["pData"][0]["AD"][0]["data"][0].update(year="FY2024/25"),
    }
    for label, mutate in cases.items():
        doc = json.loads(json.dumps(base, ensure_ascii=False))
        mutate(doc)
        try:
            aia_json_parser.parse_aia_json(json.dumps(doc).encode("utf-8"))
            check(False, "", f"{label} 未抛 AiaParseError（漏检）")
        except aia_json_parser.AiaParseError as e:
            check(True, f"{label} → STRUCTURE_MISMATCH（{str(e)[:40]}）", "")


# ---------------------------------------------------------------------------
# T004-7 · 零记录 → ZERO_RECORD
# ---------------------------------------------------------------------------
def test_parse_zero_record():
    print("\n[T004-7] 零产品/零业务记录 → ZERO_RECORD")
    print("-" * 60)
    # 零产品：pData 空数组
    doc = load_fixture()
    doc["pData"] = []
    r = aia_json_parser.parse_aia_json(json.dumps(doc, ensure_ascii=False).encode("utf-8"))
    check(r["status"] == "ZERO_RECORD", f"pData=[] → ZERO_RECORD（{r['status']}）", f"status: {r['status']}")

    # 零业务记录：产品存在但全部空 data
    doc = load_fixture()
    doc["pData"] = [{
        "productNm": {"en": "Only Empty"},
        "type": {"en": "Term"},
        "AD": [{"currency": {"en": "All"}, "remark": {"en": ""}, "data": []}],
    }]
    r = aia_json_parser.parse_aia_json(json.dumps(doc, ensure_ascii=False).encode("utf-8"))
    check(r["status"] == "ZERO_RECORD", f"全空 data → ZERO_RECORD（{r['status']}）", f"status: {r['status']}")


# ---------------------------------------------------------------------------
# T004-8 · 端到端：fetch → parse → 入库 → run_id 反查
# ---------------------------------------------------------------------------
def _fetch_and_parse(body, reg):
    """在 temp 目录内跑 fetch + parse，返回 (db, raw_root, fetch_result, parse_result)。"""
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
    print("\n[T004-8] 端到端：抓取→解析→入库 + run_id 反查 URL/哈希/快照")
    print("-" * 60)
    srv = _LocalServer(FIXTURE_PATH.read_bytes())
    try:
        reg = build_registry(srv.base)
        td, db, conn, raw_root, f, p = _fetch_and_parse(FIXTURE_PATH.read_bytes(), reg)
        try:
            check(f["result"] == "OK", f"fetch OK（{f['result']}）", f"fetch: {f}")
            check(p["result"] == "OK", f"parse OK（{p['result']}）", f"parse: {p}")
            check(p["parse_status"] == "PARTIAL", f"parse_status=PARTIAL（{p['parse_status']}）", f"parse_status: {p['parse_status']}")
            check(p["error_code"] == "VALUE_UNPARSEABLE", f"error_code=VALUE_UNPARSEABLE（{p['error_code']}）", f"error_code: {p['error_code']}")
            check(p["records_written"] == 14, f"入库 14 行（{p['records_written']}）", f"records: {p['records_written']}")

            # 业务行 count
            n = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            check(n == 14, f"fulfillment_ratio 共 {n} 行", f"行数: {n}")

            # Before 2015 → observation_year NULL；真实 2014 → 整数，二者 observation_year_raw 不同、不冲突
            b2015 = conn.execute(
                "SELECT observation_year_raw, observation_year, raw_value, normalized_value "
                "FROM fulfillment_ratio WHERE product_name_raw='Product Alpha' AND metric_type='AD' "
                "AND observation_year_raw='Before 2015'"
            ).fetchone()
            check(b2015 is not None and b2015[1] is None and b2015[2] == "80%" and b2015[3] == 0.8,
                  f"Before 2015 落库 observation_year=NULL（{b2015}）", f"Before 2015 落库错误: {b2015}")
            y2014 = conn.execute(
                "SELECT observation_year_raw, observation_year FROM fulfillment_ratio "
                "WHERE product_name_raw='Product Alpha' AND metric_type='AD' AND observation_year_raw='2014'"
            ).fetchone()
            check(y2014 is not None and y2014[1] == 2014,
                  f"真实 2014 落库 observation_year=2014（{y2014}）", f"2014 落库错误: {y2014}")

            # parse_result（软失败：保留全部记录，写 PARTIAL + VALUE_UNPARSEABLE）
            pr = conn.execute(
                "SELECT parse_status, records_produced, error_code FROM parse_result WHERE run_id=?", (p["run_id"],)
            ).fetchone()
            check(pr == ("PARTIAL", 14, "VALUE_UNPARSEABLE"), f"parse_result=(PARTIAL,14,VALUE_UNPARSEABLE)（{pr}）", f"parse_result: {pr}")

            # run_id 反查真实证据链
            fr = conn.execute(
                "SELECT final_url, http_status, content_hash, snapshot_path FROM fetch_run WHERE run_id=?",
                (p["run_id"],),
            ).fetchone()
            check(fr[0] == f"{srv.base}/fr.json", f"final_url 反查正确（{fr[0]}）", f"final_url: {fr[0]}")
            check(fr[1] == 200, "http_status=200", f"http_status: {fr[1]}")
            check(fr[2] == snapshot.sha256_hex(FIXTURE_PATH.read_bytes()), "content_hash 与字节一致", "哈希不符")
            check(fr[3] == f"raw_data/AIA/1/{fr[2]}.json", "snapshot_path 形如 raw_data/AIA/1/{hash}.json", f"snapshot_path: {fr[3]}")

            # 幂等：重复解析不产生重复行
            p2 = parse_disclosure.parse_one_source(conn, fetch_recorder.get_source(conn, 1), raw_root)
            n2 = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio").fetchone()[0]
            check(p2["result"] == "OK" and n2 == 14, f"重复解析幂等（仍 {n2} 行）", f"重复解析后 {n2} 行")
        finally:
            conn.close()
            td.cleanup()
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# T004-9 · 中途失败回滚
# ---------------------------------------------------------------------------
def test_rollback():
    print("\n[T004-9] 事务回滚：坏记录触发 IntegrityError，不留部分业务行")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        reg = build_registry("http://127.0.0.1:1")
        sqlite_store.init_db(db, reg)
        conn = sqlite_store.connect(db)
        # 造一个合法 run_id（NETWORK_ERROR 最简，无哈希/快照）
        run_id = fetch_recorder.record_network_error(conn, 1, note="rollback-test")
        conn.commit()

        good = {"product_name_raw": "Good", "metric_type": "AD", "metric_type_raw": "AD",
                "report_year": 2025, "observation_year_raw": "2024", "observation_year": 2024,
                "scope_currency_raw": "All",
                "raw_value": "100%", "normalized_value": 1.0, "product_id": None}
        bad = dict(good, product_name_raw="Bad", metric_type="INVALID", metric_type_raw="INVALID")

        try:
            ratio_writer.write_parse_outcome(conn, run_id, "AIA", [good, bad], "OK")
            check(False, "", "坏记录未触发异常（漏检）")
        except sqlite3.IntegrityError:
            check(True, "坏记录触发 IntegrityError", "")
        n = conn.execute("SELECT COUNT(*) FROM fulfillment_ratio WHERE run_id=?", (run_id,)).fetchone()[0]
        check(n == 0, f"回滚后 0 行（实际 {n}）", f"回滚失败，残留 {n} 行")
        conn.close()


# ---------------------------------------------------------------------------
# T004-10 · CLI --parse 退出码
# ---------------------------------------------------------------------------
def test_cli_parse():
    print("\n[T004-10] CLI --parse：正常 0 / 未抓取非零 / 不存在源非零 / 幂等")
    print("-" * 60)
    srv = _LocalServer(FIXTURE_PATH.read_bytes())
    try:
        reg = build_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            reg_file = td / "reg.json"
            reg_file.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

            r = _run_cli(["--init-db", "--registry", str(reg_file), "--db-path", str(db)], REPO_ROOT)
            check(r.returncode == 0, f"init-db 退出 0（{r.returncode}）", f"init-db: {r.stderr}")

            # 未抓取就解析 → 非零
            r = _run_cli(["--parse", "1", "--registry", str(reg_file), "--db-path", str(db), "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode != 0, f"未抓取 --parse 退出非零（{r.returncode}）", f"退出码 {r.returncode}")

            r = _run_cli(["--fetch", "1", "--registry", str(reg_file), "--db-path", str(db), "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode == 0, f"--fetch 退出 0（{r.returncode}）", f"fetch: {r.stderr}")

            r = _run_cli(["--parse", "1", "--registry", str(reg_file), "--db-path", str(db), "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode == 0, f"--parse 退出 0（{r.returncode}）", f"parse: {r.stdout}{r.stderr}")
            data = json.loads(r.stdout)
            check(data["records_written"] == 14, f"CLI 报告 records_written=14（{data['records_written']}）", f"records: {data}")
            check(data["parse_status"] == "PARTIAL", f"CLI 报告 parse_status=PARTIAL（{data['parse_status']}）", f"parse_status: {data}")
            check(data["error_code"] == "VALUE_UNPARSEABLE", f"CLI 报告 error_code=VALUE_UNPARSEABLE（{data['error_code']}）", f"error_code: {data}")

            r = _run_cli(["--parse", "999", "--registry", str(reg_file), "--db-path", str(db), "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode != 0, f"不存在源 --parse 退出非零（{r.returncode}）", f"退出码 {r.returncode}")
    finally:
        srv.stop()


def main():
    print("=" * 60)
    print("ICD 集成测试（T004 · AIA JSON 解析与入库）")
    print("=" * 60)
    test_schema_new_columns()
    test_migration_detection()
    test_parse_ratio_unit()
    test_parse_observation_year()
    test_parse_fixture_full()
    test_parse_structure_mismatch()
    test_parse_zero_record()
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
