#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD 集成测试（T002）

覆盖任务书验收标准：
- 配置校验：正常配置 0 错误；四类损坏 fixture（非法 JSON / 重复险企 /
  未知险企引用 / UNVERIFIED 带 URL）各非零退出。
- SQLite 初始化：12 张表、11 家险企、21 条数据源、11 条错误代码种子；
  二次初始化不产生重复；fetch_run 已有行在二次初始化后仍存在。
- CLI：--status 在数据库不存在/存在两种情况下输出正确；
  从项目根 / ICD 根 / 任意临时目录运行均成功（路径从 __file__ 推导）。
- 不联网、不读 DeepSeek 凭证、不写 ICD 外文件（所有写操作都在 tempfile 内）。

运行：python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
"""

import hashlib
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent                 # tests/
NUMBERED_DIR = TESTS_DIR.parent                             # 09_测试与调试_Test_and_Debug/
ICD_DIR = NUMBERED_DIR.parent                               # FDE项目/ICD/
REPO_ROOT = ICD_DIR.parent.parent                           # AI工程能力整改项目（仓库根）

for _pkg_dir in (
    "05_集成工具_Integrate_Tools",
    "07_接入记忆_Integrate_Memory",
    "06_开发技能_Develop_Skills",
):
    sys.path.insert(0, str(ICD_DIR / _pkg_dir))
sys.path.insert(0, str(ICD_DIR / "04_定义Agent_Define_Agent" / "agents"))

from memory import workspace
from skills import fetch_disclosure
from tools import config_loader, fetch_recorder, http_fetcher, snapshot, sqlite_store
import agent as agent_module

AGENT_PY = ICD_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"
REGISTRY_PATH = ICD_DIR / "02_配置项目_Configure_Project" / "source_registry.json"
SETTINGS_PATH = ICD_DIR / "02_配置项目_Configure_Project" / "settings.json"

FAILURES = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"✅ {ok_msg}")
    else:
        print(f"❌ {fail_msg}")
        FAILURES.append(fail_msg)


def load_real_registry():
    return config_loader.load_json(REGISTRY_PATH)


def build_broken_fixtures():
    """构造四类损坏 registry fixture 内容：非法 JSON / 重复险企 / 未知险企引用 /
    UNVERIFIED 带 URL。返回 {名称: 文件内容}，供 --validate-config 与 --init-db
    黑盒负向测试共用，保证两处门禁用同一批破坏样本。"""
    real = load_real_registry()
    fixtures = {"invalid_json": "{ not valid json"}

    dup = json.loads(json.dumps(real, ensure_ascii=False))
    dup["insurers"].append(dict(dup["insurers"][0]))
    fixtures["duplicate_insurer"] = json.dumps(dup, ensure_ascii=False)

    unk = json.loads(json.dumps(real, ensure_ascii=False))
    unk["sources"][0]["insurer_code"] = "XXX"
    fixtures["unknown_insurer"] = json.dumps(unk, ensure_ascii=False)

    uvr = json.loads(json.dumps(real, ensure_ascii=False))
    next(s for s in uvr["sources"] if s["access_status"] == "UNVERIFIED")["entry_url"] = "https://x/guess.pdf"
    fixtures["unverified_url"] = json.dumps(uvr, ensure_ascii=False)

    return fixtures


def snapshot_db(db):
    """只读快照一个 SQLite 文件的字节哈希、表名与各表行数，用于前后一致性比对。"""
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    conn = sqlite_store.connect(db)
    try:
        tables = sqlite_store.table_names(conn)
        rows = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    finally:
        conn.close()
    return digest, tables, rows


# ---------------------------------------------------------------------------
# 配置校验（白盒）
# ---------------------------------------------------------------------------
def test_config_valid_registry():
    print("\n[Test 1] 配置校验：正常注册表 0 错误")
    print("-" * 60)
    reg = load_real_registry()
    errs = config_loader.validate_registry(reg)
    check(len(errs) == 0, f"正常注册表校验通过（{len(errs)} 处错误）", f"正常注册表被误判：{errs}")
    settings = config_loader.load_json(SETTINGS_PATH)
    errs = config_loader.validate_settings(settings)
    check(len(errs) == 0, f"正常 settings 校验通过（{len(errs)} 处错误）", f"settings 被误判：{errs}")


def test_config_invalid_json():
    print("\n[Test 2] 配置校验：非法 JSON 抛 ConfigError")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad.json"
        bad.write_text("{ this is not json", encoding="utf-8")
        try:
            config_loader.load_json(bad)
            check(False, "", "非法 JSON 未抛 ConfigError")
        except config_loader.ConfigError:
            check(True, "非法 JSON 正确抛出 ConfigError", "")


def test_config_duplicate_insurer():
    print("\n[Test 3] 配置校验：重复险企 insurer_code 报错")
    print("-" * 60)
    reg = load_real_registry()
    reg = json.loads(json.dumps(reg, ensure_ascii=False))  # 深拷贝
    dup = dict(reg["insurers"][0])
    reg["insurers"].append(dup)
    errs = config_loader.validate_registry(reg)
    check(any("重复险企" in e for e in errs), f"重复险企被检出（{len(errs)} 处）", f"重复险企漏检：{errs}")


def test_config_unknown_insurer_ref():
    print("\n[Test 4] 配置校验：未知险企引用报错")
    print("-" * 60)
    reg = load_real_registry()
    reg = json.loads(json.dumps(reg, ensure_ascii=False))
    reg["sources"][0]["insurer_code"] = "XXX_NOT_EXIST"
    errs = config_loader.validate_registry(reg)
    check(any("未知险企" in e for e in errs), f"未知险企引用被检出（{len(errs)} 处）", f"未知险企引用漏检：{errs}")


def test_config_unverified_with_url():
    print("\n[Test 5] 配置校验：UNVERIFIED 带 URL/format 报错")
    print("-" * 60)
    reg = load_real_registry()
    reg = json.loads(json.dumps(reg, ensure_ascii=False))
    # 找到一条 UNVERIFIED 源，给它塞一个 URL
    unverified = next(s for s in reg["sources"] if s["access_status"] == "UNVERIFIED")
    unverified["entry_url"] = "https://example.com/guess.pdf"
    errs = config_loader.validate_registry(reg)
    check(any("UNVERIFIED" in e and "entry_url" in e for e in errs), f"UNVERIFIED 带 URL 被检出（{len(errs)} 处）", f"UNVERIFIED 带 URL 漏检：{errs}")


# ---------------------------------------------------------------------------
# SQLite 初始化（白盒）
# ---------------------------------------------------------------------------
def test_init_db_schema_and_seeds():
    print("\n[Test 6] SQLite 初始化：12 表 + 种子数量正确")
    print("-" * 60)
    reg = load_real_registry()
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        summary = sqlite_store.init_db(db, reg)
        check(summary["table_count"] == 12, f"12 张表齐备（missing={summary['missing_tables']}）",
              f"表缺失：{summary['missing_tables']}")
        c = summary["counts"]
        check(c["insurer"] == 11, f"险企 11 家（实际 {c['insurer']}）", f"险企数错误：{c['insurer']}")
        check(c["data_source"] == 21, f"数据源 21 条（实际 {c['data_source']}）", f"数据源数错误：{c['data_source']}")
        check(c["error_code"] == 11, f"错误代码 11 条（实际 {c['error_code']}）", f"错误代码数错误：{c['error_code']}")


def test_init_db_idempotent():
    print("\n[Test 7] SQLite 二次初始化幂等（不产生重复种子）")
    print("-" * 60)
    reg = load_real_registry()
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        sqlite_store.init_db(db, reg)
        summary2 = sqlite_store.init_db(db, reg)
        c = summary2["counts"]
        check(c["insurer"] == 11, f"二次初始化险企仍 11（实际 {c['insurer']}）", f"险企重复：{c['insurer']}")
        check(c["data_source"] == 21, f"二次初始化数据源仍 21（实际 {c['data_source']}）", f"数据源重复：{c['data_source']}")
        check(c["error_code"] == 11, f"二次初始化错误代码仍 11（实际 {c['error_code']}）", f"错误代码重复：{c['error_code']}")


def test_init_db_preserves_fetch_run():
    print("\n[Test 8] 二次初始化不删除 fetch_run 已有行")
    print("-" * 60)
    reg = load_real_registry()
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        sqlite_store.init_db(db, reg)
        conn = sqlite_store.connect(db)
        # 取一个真实 source_id，插入一条合法的"网络失败"fetch_run（满足三态 CHECK）
        src_id = conn.execute("SELECT source_id FROM data_source ORDER BY source_id LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO fetch_run (source_id, fetch_status, note) VALUES (?, 'NETWORK_ERROR', 'simulated')",
            (src_id,),
        )
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM fetch_run").fetchone()[0]
        conn.close()
        check(before == 1, f"模拟 fetch_run 已写入（{before} 行）", f"模拟 fetch_run 写入失败：{before}")

        sqlite_store.init_db(db, reg)  # 二次初始化
        conn = sqlite_store.connect(db)
        after = conn.execute("SELECT COUNT(*) FROM fetch_run").fetchone()[0]
        note = conn.execute("SELECT note FROM fetch_run WHERE note='simulated'").fetchone()
        conn.close()
        check(after == 1 and note is not None, f"二次初始化后 fetch_run 仍 {after} 行且模拟行保留", f"fetch_run 被破坏：after={after}")


# ---------------------------------------------------------------------------
# CLI 黑盒
# ---------------------------------------------------------------------------
def run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, str(AGENT_PY)] + args,
        cwd=str(cwd), capture_output=True, text=True,
    )


def test_cli_validate_config_ok():
    print("\n[Test 9] CLI --validate-config 正常配置退出 0")
    print("-" * 60)
    r = run_cli(["--validate-config"], REPO_ROOT)
    check(r.returncode == 0, f"退出码 {r.returncode}", f"退出码非 0：{r.returncode}\nstderr={r.stderr}")


def test_cli_validate_config_broken():
    print("\n[Test 10] CLI --validate-config 四类损坏 fixture 均非零退出且不写默认库")
    print("-" * 60)
    fixtures = build_broken_fixtures()

    default_db = workspace.default_db_path()
    existed_before = default_db.exists()

    with tempfile.TemporaryDirectory() as td:
        for name, content in fixtures.items():
            reg_file = Path(td) / f"{name}.json"
            reg_file.write_text(content, encoding="utf-8")
            r = run_cli(["--validate-config", "--registry", str(reg_file)], REPO_ROOT)
            check(r.returncode != 0, f"{name} → 退出码 {r.returncode}（非零，符合预期）", f"{name} 退出码为 0，漏检")

    # 校验不应写默认数据库
    default_db_after = default_db.exists()
    check(not default_db_after or (existed_before and default_db_after),
          "校验过程未创建默认数据库", f"校验意外写入了默认数据库：{default_db}")


def test_cli_init_db_broken():
    print("\n[Test 14] CLI --init-db 四类损坏 fixture 均非零退出且目标 DB 不存在")
    print("-" * 60)
    fixtures = build_broken_fixtures()
    with tempfile.TemporaryDirectory() as td:
        for name, content in fixtures.items():
            reg_file = Path(td) / f"{name}.json"
            reg_file.write_text(content, encoding="utf-8")
            db = Path(td) / f"{name}.db"
            r = run_cli(["--init-db", "--registry", str(reg_file), "--db-path", str(db)], REPO_ROOT)
            check(r.returncode != 0, f"{name} → 退出码 {r.returncode}（非零，符合预期）", f"{name} 退出码为 0，写路径绕过配置门禁")
            check(not db.exists(), f"{name} → 目标 DB 未创建", f"{name} → 目标 DB 被违规创建：{db}")


def test_cli_init_db_preserves_existing_db_on_bad_config():
    print("\n[Test 15] CLI --init-db 坏配置下，已存在哨兵 DB 的文件/表/行完全不变")
    print("-" * 60)
    fixtures = build_broken_fixtures()
    with tempfile.TemporaryDirectory() as td:
        for name, content in fixtures.items():
            reg_file = Path(td) / f"{name}.json"
            reg_file.write_text(content, encoding="utf-8")
            db = Path(td) / f"{name}_existing.db"

            # 预存哨兵表 + 哨兵行（不属于 ICD schema），证明坏配置下 init-db 绝不触碰已有库
            conn = sqlite_store.connect(db)
            conn.execute("CREATE TABLE sentinel (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            conn.execute("INSERT INTO sentinel (payload) VALUES ('do-not-touch')")
            conn.commit()
            conn.close()

            before_hash, before_tables, before_rows = snapshot_db(db)

            r = run_cli(["--init-db", "--registry", str(reg_file), "--db-path", str(db)], REPO_ROOT)
            check(r.returncode != 0, f"{name} → 退出码 {r.returncode}（非零）", f"{name} 退出码为 0，坏配置被放行")

            after_hash, after_tables, after_rows = snapshot_db(db)
            check(before_hash == after_hash, f"{name} → 文件哈希不变", f"{name} → 文件被修改：{before_hash[:12]} → {after_hash[:12]}")
            check(before_tables == after_tables, f"{name} → 表结构不变", f"{name} → 表结构变化：{before_tables} → {after_tables}")
            check(before_rows == after_rows, f"{name} → 行数据不变", f"{name} → 行数据变化：{before_rows} → {after_rows}")


def test_cli_status_db_absent_and_present():
    print("\n[Test 11] CLI --status 数据库不存在/存在两种情况")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "icd.db"
        # 情况一：数据库不存在
        r = run_cli(["--status", "--db-path", str(db)], REPO_ROOT)
        ok = r.returncode == 0
        data = None
        if ok:
            try:
                data = json.loads(r.stdout)
            except json.JSONDecodeError:
                ok = False
        check(ok and data["database"]["exists"] is False, "DB 不存在 → exists=false", f"退出码/JSON 异常：{r.returncode} {r.stdout}")
        check(data is not None and data["agent_id"] == "ICD", "agent_id=ICD", f"agent_id 错误：{data}")
        check(data is not None and data["insurer_count"] == 11, "insurer_count=11", f"insurer_count 错误：{data}")
        check(data is not None and data["source_count"] == 21, "source_count=21", f"source_count 错误：{data}")

        # 情况二：先初始化，数据库存在
        reg = load_real_registry()
        sqlite_store.init_db(db, reg)
        r = run_cli(["--status", "--db-path", str(db)], REPO_ROOT)
        data2 = json.loads(r.stdout) if r.returncode == 0 else None
        check(r.returncode == 0 and data2["database"]["exists"] is True, "DB 存在 → exists=true", f"exists 错误：{r.returncode} {r.stdout}")


def test_cli_cwd_independence():
    print("\n[Test 12] CLI 从项目根 / ICD 根 / 临时目录运行均成功")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        for label, cwd in (("项目根", REPO_ROOT), ("ICD 根", ICD_DIR), ("临时目录", Path(td))):
            r = run_cli(["--status"], cwd)
            ok = r.returncode == 0
            data = json.loads(r.stdout) if ok else None
            check(ok and data is not None and data["agent_id"] == "ICD",
                  f"{label} → 成功，agent_id=ICD", f"{label} → 失败：{r.returncode} {r.stderr}")


def test_no_network_imports():
    print("\n[Test 13] 骨架不引入网络库（不联网保证）")
    print("-" * 60)
    for p in (agent_module.__file__,):
        src = Path(p).read_text(encoding="utf-8")
        bad = [tok for tok in ("requests", "urllib", "http.client", "socket") if tok in src]
        check(len(bad) == 0, "agent.py 无网络库引用", f"发现网络库引用：{bad}")


# ---------------------------------------------------------------------------
# T003 · HTTP 抓取与原始证据固化（本机临时 HTTP 服务器，不访问真实网络）
# ---------------------------------------------------------------------------
class _LocalServer:
    """本机临时 HTTP 服务器，覆盖：200 字节保真 / 重定向 / 403 / 404 / 5xx /
    连接超时 / 慢响应体超时 / 响应体中途断连 / 超限 / 动态内容（版本变化）。
    所有请求头被记录用于 UA/凭证断言。"""

    def __init__(self):
        self.content = b"hello-icd-bytes-200"
        self.paths = []
        self.headers = []
        self._lock = threading.Lock()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # 静默
                pass

            def do_GET(self):
                outer._route(self)

        self._handler = Handler
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def _route(self, h):
        with self._lock:
            self.paths.append(h.path)
            self.headers.append({k.lower(): v for k, v in h.headers.items()})
        p = h.path
        if p == "/redirect":
            h.send_response(302)
            h.send_header("Location", "/final")
            h.end_headers()
        elif p == "/final":
            self._respond(h, 200, self.content)
        elif p == "/forbidden":
            self._respond(h, 403, b"forbidden")
        elif p == "/missing":
            self._respond(h, 404, b"not found")
        elif p == "/server-error":
            self._respond(h, 500, b"boom")
        elif p == "/slow":
            time.sleep(2.0)
            self._respond(h, 200, b"slow")
        elif p == "/slow-body":
            self._respond_slow_body(h)
        elif p == "/truncated":
            self._respond_truncated(h)
        elif p == "/big":
            self._respond(h, 200, b"x" * (256 * 1024))
        elif p == "/dynamic":
            self._respond(h, 200, self.content)
        else:
            self._respond(h, 200, self.content)

    def _respond(self, h, status, body):
        h.send_response(status)
        h.send_header("Content-Length", str(len(body)))
        h.send_header("Content-Type", "application/octet-stream")
        h.end_headers()
        h.wfile.write(body)

    def _respond_slow_body(self, h):
        """先发 200 响应头（Content-Length=100），再只写 10 字节并 flush，
        随后 sleep 超过客户端 read_timeout——客户端读完响应头进入 body 读取，
        第二次 read 阻塞到超时，触发"响应体读取超时"。"""
        h.send_response(200)
        h.send_header("Content-Length", "100")
        h.send_header("Content-Type", "application/octet-stream")
        h.end_headers()
        h.wfile.write(b"x" * 10)
        h.wfile.flush()
        time.sleep(2.0)  # 超过测试 read_timeout(0.3s)，剩余字节不发，连接保持

    def _respond_truncated(self, h):
        """承诺 Content-Length=1000，但只写 13 字节后立即返回关闭连接，
        触发客户端 IncompleteRead（响应体中途断连）。"""
        h.send_response(200)
        h.send_header("Content-Length", "1000")
        h.send_header("Content-Type", "application/octet-stream")
        h.end_headers()
        h.wfile.write(b"partial-bytes")
        h.wfile.flush()
        # 处理函数返回 → HTTP/1.0 连接关闭，但 Content-Length 未满足

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def build_fetch_registry(base_url):
    """构造 T003 本地测试注册表：1 家测试险企，13 条源覆盖各场景。"""
    def src(dtype, url, fmt, status, browser=False):
        return {
            "insurer_code": "TST", "disclosure_type": dtype,
            "entry_url": url, "format": fmt, "access_status": status,
            "parser_hint": "local test", "requires_browser": browser,
            "evidence_basis": "T003 本地 HTTP 服务器", "allows_empty": False,
            "last_verified_at": "2026-09-03", "url_version": 1,
        }
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-03",
        "description": "T003 本地 HTTP 测试注册表",
        "insurers": [
            {"insurer_code": "TST", "name_en": "Test Insurer", "name_zh": "测试险企"},
        ],
        "sources": [
            src("fulfillment_ratio", f"{base_url}/final", "json", "OPEN"),          # 1
            src("rbc", f"{base_url}/forbidden", "pdf", "OPEN"),                     # 2
            src("rbc", f"{base_url}/final", "json", "BLOCKED", True),               # 3
            {"insurer_code": "TST", "disclosure_type": "rbc", "entry_url": None,   # 4
             "format": None, "access_status": "UNVERIFIED", "parser_hint": "local test",
             "requires_browser": False, "evidence_basis": "T003 本地 HTTP 服务器",
             "allows_empty": False, "last_verified_at": None, "url_version": 1},
            src("fulfillment_ratio", f"{base_url}/missing", "html", "OPEN"),       # 5
            src("fulfillment_ratio", f"{base_url}/server-error", "html", "OPEN"),  # 6
            src("fulfillment_ratio", f"{base_url}/slow", "html", "OPEN"),          # 7
            src("fulfillment_ratio", f"{base_url}/big", "html", "OPEN"),           # 8
            src("fulfillment_ratio", f"{base_url}/dynamic", "html", "OPEN"),       # 9
            src("rbc", f"{base_url}/browser-only", "json", "OPEN", True),          # 10
            src("rbc", f"{base_url}/redirect", "json", "OPEN"),                    # 11
             src("fulfillment_ratio", f"{base_url}/slow-body", "html", "OPEN"),     # 12
             src("fulfillment_ratio", f"{base_url}/truncated", "html", "OPEN"),     # 13
        ],
    }


def _count_ok_rows(conn, source_id):
    return conn.execute(
        "SELECT COUNT(*) FROM fetch_run WHERE source_id=? AND fetch_status='OK'",
        (source_id,),
    ).fetchone()[0]


def _count_fetch_rows(conn, source_id):
    return conn.execute(
        "SELECT COUNT(*) FROM fetch_run WHERE source_id=?", (source_id,),
    ).fetchone()[0]


def _snapshot_files(raw_root, insurer, source_id):
    d = Path(raw_root) / insurer / str(source_id)
    if not d.exists():
        return []
    return [p for p in d.iterdir() if p.is_file() and not p.name.startswith(".tmp-")]


def _assert_no_tmp(raw_root):
    hits = [str(p) for p in Path(raw_root).rglob(".tmp-*")]
    check(len(hits) == 0, "无 .tmp 残留", f"发现 .tmp 残留: {hits}")


def _run_fetch_cli(args, cwd):
    return subprocess.run(
        [sys.executable, str(AGENT_PY)] + args,
        cwd=str(cwd), capture_output=True, text=True,
    )


def test_t003_fetch_ok_and_fidelity():
    print("\n[T003-1] 抓取成功：字节保真 + 哈希一致 + UA 可识别 + 无凭证头")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            src = fetch_recorder.get_source(conn, 1)
            res = fetch_disclosure.fetch_one_source(conn, src, raw_root)
            check(res["result"] == "OK", f"result=OK（{res['result']}）", f"结果非 OK: {res}")
            check(res["http_status"] == 200, "http_status=200", f"http_status: {res['http_status']}")
            want_hash = snapshot.sha256_hex(srv.content)
            check(res["content_hash"] == want_hash, "content_hash 与字节 SHA-256 一致", f"哈希不符: {res['content_hash']}")
            check(res["content_length"] == len(srv.content), f"content_length={len(srv.content)}", f"长度错误: {res['content_length']}")
            full = workspace.snapshot_fullpath(raw_root, "TST", 1, want_hash, "json")
            check(full.exists(), "快照文件已落盘", f"快照缺失: {full}")
            check(full.read_bytes() == srv.content, "快照字节与响应体一致", "快照字节不一致")
            row = conn.execute(
                "SELECT content_hash, snapshot_path, content_length, http_status, fetch_status FROM fetch_run WHERE source_id=1"
            ).fetchone()
            check(row is not None and row[0] == want_hash and row[1] == res["snapshot_path"]
                  and row[2] == len(srv.content) and row[3] == 200 and row[4] == "OK",
                  "fetch_run OK 行字段正确", f"fetch_run 行: {row}")
            check(res["snapshot_path"] == f"raw_data/TST/1/{want_hash}.json",
                  "snapshot_path 形如 raw_data/TST/1/{hash}.json", f"snapshot_path: {res['snapshot_path']}")
            check(srv.headers and srv.headers[0].get("user-agent") == http_fetcher.USER_AGENT,
                  "请求 UA 为固定可识别值", f"UA 错误: {srv.headers}")
            check("cookie" not in srv.headers[0] and "authorization" not in srv.headers[0],
                  "请求未带 Cookie/Authorization", f"带凭证头: {srv.headers[0]}")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_fetch_redirect():
    print("\n[T003-2] 重定向：302→200 最终 URL 与内容正确")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            src = fetch_recorder.get_source(conn, 11)
            res = fetch_disclosure.fetch_one_source(conn, src, raw_root)
            check(res["result"] == "OK", f"重定向后 OK（{res['result']}）", f"结果: {res}")
            check(res["final_url"] == f"{srv.base}/final", f"final_url={srv.base}/final", f"final_url: {res['final_url']}")
            check(res["content_hash"] == snapshot.sha256_hex(srv.content), "重定向后内容哈希正确", "内容哈希错误")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_fetch_http_errors():
    print("\n[T003-3] HTTP 失败：403/404/5xx 有状态码、无哈希/快照")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            cases = [(2, 403, "HTTP_403"), (5, 404, "HTTP_404"), (6, 500, "HTTP_5XX")]
            for sid, want_status, want_code in cases:
                src = fetch_recorder.get_source(conn, sid)
                res = fetch_disclosure.fetch_one_source(conn, src, raw_root)
                check(res["result"] == "HTTP_ERROR", f"source {sid} → HTTP_ERROR", f"source {sid} 结果: {res['result']}")
                check(res["http_status"] == want_status, f"source {sid} http_status={want_status}", f"source {sid} http_status={res['http_status']}")
                check(res["content_hash"] is None and res["snapshot_path"] is None,
                      f"source {sid} 无哈希/快照", f"source {sid} 泄漏哈希/快照: {res}")
                check(res["error_code"] == want_code, f"source {sid} error_code={want_code}", f"source {sid} error_code={res['error_code']}")
                files = _snapshot_files(raw_root, "TST", sid)
                check(len(files) == 0, f"source {sid} 无快照文件", f"source {sid} 快照残留: {files}")
                row = conn.execute(
                    "SELECT fetch_status, http_status, content_hash FROM fetch_run WHERE source_id=?", (sid,)
                ).fetchone()
                check(row is not None and row[0] == "HTTP_ERROR" and row[1] == want_status and row[2] is None,
                      f"source {sid} 失败行三态正确", f"source {sid} 失败行: {row}")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_fetch_timeout():
    print("\n[T003-4] 网络失败：超时无 HTTP 状态、无哈希/快照")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            src = fetch_recorder.get_source(conn, 7)
            res = fetch_disclosure.fetch_one_source(conn, src, raw_root, read_timeout=0.3)
            check(res["result"] == "NETWORK_ERROR", f"result=NETWORK_ERROR（{res['result']}）", f"结果: {res}")
            check(res["http_status"] is None, "http_status=None", f"http_status: {res['http_status']}")
            check(res["content_hash"] is None and res["snapshot_path"] is None, "无哈希/快照", f"泄漏: {res}")
            check(res["error_code"] == "NETWORK_TIMEOUT", f"error_code=NETWORK_TIMEOUT（{res['error_code']}）", f"error_code: {res['error_code']}")
            row = conn.execute(
                "SELECT fetch_status, http_status, content_hash FROM fetch_run WHERE source_id=7"
            ).fetchone()
            check(row is not None and row[0] == "NETWORK_ERROR" and row[1] is None and row[2] is None,
                  "网络失败行三态正确（http_status NULL）", f"失败行: {row}")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_fetch_slow_body_timeout():
    print("\n[T003-13] 慢响应体：响应头成功后 body 读取超时 → NETWORK_ERROR")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            src = fetch_recorder.get_source(conn, 12)
            res = fetch_disclosure.fetch_one_source(conn, src, raw_root, read_timeout=0.3)
            check(res["result"] == "NETWORK_ERROR", f"result=NETWORK_ERROR（{res['result']}）", f"结果: {res}")
            check(res["http_status"] is None, "http_status=None（未误记为 HTTP 成功/错误）", f"http_status: {res['http_status']}")
            check(res["content_hash"] is None and res["snapshot_path"] is None, "无哈希/快照", f"泄漏: {res}")
            check(res["error_code"] == "NETWORK_TIMEOUT", f"error_code=NETWORK_TIMEOUT（{res['error_code']}）", f"error_code: {res['error_code']}")
            row = conn.execute(
                "SELECT fetch_status, http_status, content_hash, snapshot_path FROM fetch_run WHERE source_id=12"
            ).fetchone()
            check(row is not None and row[0] == "NETWORK_ERROR" and row[1] is None
                  and row[2] is None and row[3] is None,
                  "慢body失败行三态正确（http_status/content_hash/snapshot_path 全 NULL）", f"失败行: {row}")
            check(len(_snapshot_files(raw_root, "TST", 12)) == 0, "无快照文件", "快照残留")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_fetch_midstream_disconnect():
    print("\n[T003-14] 响应体中途断连：NETWORK_ERROR/NETWORK_CONNECTION，无快照/哈希")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            src = fetch_recorder.get_source(conn, 13)
            res = fetch_disclosure.fetch_one_source(conn, src, raw_root, read_timeout=2.0)
            check(res["result"] == "NETWORK_ERROR", f"result=NETWORK_ERROR（{res['result']}）", f"结果: {res}")
            check(res["http_status"] is None, "http_status=None（未误记为 HTTP 成功/错误）", f"http_status: {res['http_status']}")
            check(res["content_hash"] is None and res["snapshot_path"] is None, "无哈希/快照", f"泄漏: {res}")
            check(res["error_code"] == "NETWORK_CONNECTION", f"error_code=NETWORK_CONNECTION（{res['error_code']}）", f"error_code: {res['error_code']}")
            row = conn.execute(
                "SELECT fetch_status, http_status, content_hash, snapshot_path FROM fetch_run WHERE source_id=13"
            ).fetchone()
            check(row is not None and row[0] == "NETWORK_ERROR" and row[1] is None
                  and row[2] is None and row[3] is None,
                  "断连失败行三态正确（全 NULL）", f"失败行: {row}")
            check(len(_snapshot_files(raw_root, "TST", 13)) == 0, "无快照文件", "快照残留")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_fetch_oversized():
    print("\n[T003-5] 超限响应：HTTP_ERROR 且不落快照")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            src = fetch_recorder.get_source(conn, 8)
            res = fetch_disclosure.fetch_one_source(conn, src, raw_root, max_bytes=1024)
            check(res["result"] == "HTTP_ERROR", f"result=HTTP_ERROR（{res['result']}）", f"结果: {res}")
            check(res["http_status"] == 200, "http_status=200（有响应但超限）", f"http_status: {res['http_status']}")
            check(res["content_hash"] is None and res["snapshot_path"] is None, "无哈希/快照", f"泄漏: {res}")
            check(res["note"] is not None and "上限" in res["note"], "note 说明超限", f"note: {res['note']}")
            files = _snapshot_files(raw_root, "TST", 8)
            check(len(files) == 0, "超限源无快照文件", f"快照残留: {files}")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_fetch_dedup_and_version():
    print("\n[T003-6] 同内容 UNCHANGED；不同内容新版本")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            src = fetch_recorder.get_source(conn, 9)
            srv.content = b"version-A"
            r1 = fetch_disclosure.fetch_one_source(conn, src, raw_root)
            check(r1["result"] == "OK", f"首抓 OK（{r1['result']}）", f"首抓: {r1}")
            files1, ok1 = _snapshot_files(raw_root, "TST", 9), _count_ok_rows(conn, 9)
            check(len(files1) == 1 and ok1 == 1, "首抓 1 快照 + 1 成功行", f"files={len(files1)} ok={ok1}")
            r2 = fetch_disclosure.fetch_one_source(conn, src, raw_root)
            check(r2["result"] == "UNCHANGED", f"同内容 UNCHANGED（{r2['result']}）", f"结果: {r2}")
            files2, ok2 = _snapshot_files(raw_root, "TST", 9), _count_ok_rows(conn, 9)
            check(len(files2) == 1 and ok2 == 1, "UNCHANGED 不新增快照/成功行", f"files={len(files2)} ok={ok2}")
            srv.content = b"version-B"
            r3 = fetch_disclosure.fetch_one_source(conn, src, raw_root)
            check(r3["result"] == "OK", f"不同内容 OK（{r3['result']}）", f"结果: {r3}")
            files3, ok3 = _snapshot_files(raw_root, "TST", 9), _count_ok_rows(conn, 9)
            check(len(files3) == 2 and ok3 == 2, "不同内容新增版本（2 快照 + 2 成功行）", f"files={len(files3)} ok={ok3}")
            check(r3["content_hash"] != r1["content_hash"], "新版本哈希不同", "哈希相同异常")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_fetch_reject():
    print("\n[T003-7] 被禁源拒绝：BLOCKED / UNVERIFIED / requires_browser 无副作用")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            for sid, label in ((3, "BLOCKED"), (4, "UNVERIFIED"), (10, "requires_browser")):
                src = fetch_recorder.get_source(conn, sid)
                res = fetch_disclosure.fetch_one_source(conn, src, raw_root)
                check(res["result"] == "REJECTED", f"source {sid} ({label}) → REJECTED", f"source {sid} 结果: {res['result']}")
                check(_count_fetch_rows(conn, sid) == 0, f"source {sid} 无 fetch_run 副作用", f"source {sid} 有 fetch_run 行")
                check(len(_snapshot_files(raw_root, "TST", sid)) == 0, f"source {sid} 无快照副作用", f"source {sid} 快照残留")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_fetch_dry_run():
    print("\n[T003-8] dry-run：不写快照、不写数据库")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            sqlite_store.init_db(db, reg)
            conn = sqlite_store.connect(db)
            src = fetch_recorder.get_source(conn, 1)
            res = fetch_disclosure.fetch_one_source(conn, src, raw_root, dry_run=True)
            check(res["result"] == "DRY_RUN", f"result=DRY_RUN（{res['result']}）", f"结果: {res}")
            check(res["content_hash"] == snapshot.sha256_hex(srv.content), "dry-run 仍计算哈希", "哈希错误")
            check(_count_fetch_rows(conn, 1) == 0, "dry-run 无 fetch_run 行", "dry-run 写库了")
            check(len(_snapshot_files(raw_root, "TST", 1)) == 0, "dry-run 无快照文件", "dry-run 写快照了")
            _assert_no_tmp(raw_root)
            conn.close()
    finally:
        srv.stop()


def test_t003_path_traversal_guard():
    print("\n[T003-9] 快照路径防穿越")
    print("-" * 60)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "raw_data"
        try:
            workspace.snapshot_fullpath(root, "../etc", 1, "abc", "json")
            check(False, "", "非法 insurer_code 未抛异常")
        except ValueError:
            check(True, "非法 insurer_code（../etc）抛 ValueError", "")
        try:
            workspace.snapshot_fullpath(root, "TST", 1, "abc", "x/../y")
            check(False, "", "非法扩展名未抛异常")
        except ValueError:
            check(True, "非法扩展名抛 ValueError", "")
        p = workspace.snapshot_fullpath(root, "TST", 1, "abc", "json")
        check(p == root.resolve() / "TST" / "1" / "abc.json", "正常路径位于 raw_data 根内", f"路径: {p}")
        check(root.resolve() in p.parents, "路径无穿越", "路径越界")


def test_t003_cli_fetch_rejected_nonzero():
    print("\n[T003-10] CLI：被禁源非零退出且无副作用")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            reg_file = td / "registry.json"
            reg_file.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
            r = _run_fetch_cli(["--init-db", "--registry", str(reg_file), "--db-path", str(db)], REPO_ROOT)
            check(r.returncode == 0, f"init-db 退出 0（{r.returncode}）", f"init-db 失败: {r.stderr}")
            for sid in (3, 4, 10):
                r = _run_fetch_cli(["--fetch", str(sid), "--registry", str(reg_file), "--db-path", str(db), "--raw-data-root", str(raw_root)], REPO_ROOT)
                check(r.returncode == 2, f"source {sid} 退出码 2（{r.returncode}）", f"source {sid} 退出码 {r.returncode}: {r.stdout}{r.stderr}")
            conn = sqlite_store.connect(db)
            total = conn.execute("SELECT COUNT(*) FROM fetch_run").fetchone()[0]
            conn.close()
            check(total == 0, "被禁源无 fetch_run 副作用", f"fetch_run 行数 {total}")
            files = [f for f in Path(raw_root).rglob("*") if f.is_file()] if Path(raw_root).exists() else []
            check(len(files) == 0, "被禁源无快照副作用", f"快照残留: {files}")
    finally:
        srv.stop()


def test_t003_cli_fetch_ok_and_dryrun():
    print("\n[T003-11] CLI：正常抓取退出 0 落盘；--dry-run 不写")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            reg_file = td / "registry.json"
            reg_file.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
            _run_fetch_cli(["--init-db", "--registry", str(reg_file), "--db-path", str(db)], REPO_ROOT)
            r = _run_fetch_cli(["--fetch", "1", "--registry", str(reg_file), "--db-path", str(db), "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode == 0, f"--fetch 1 退出 0（{r.returncode}）", f"退出 {r.returncode}: {r.stdout}{r.stderr}")
            conn = sqlite_store.connect(db)
            ok = _count_ok_rows(conn, 1)
            conn.close()
            check(ok == 1, "正常抓取写 1 成功行", f"成功行 {ok}")
            check(len(_snapshot_files(raw_root, "TST", 1)) == 1, "正常抓取落 1 快照", "快照数错误")
            r = _run_fetch_cli(["--fetch", "1", "--dry-run", "--registry", str(reg_file), "--db-path", str(db), "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode == 0, f"--fetch 1 --dry-run 退出 0（{r.returncode}）", f"退出 {r.returncode}: {r.stdout}{r.stderr}")
            conn = sqlite_store.connect(db)
            ok2 = _count_ok_rows(conn, 1)
            conn.close()
            check(ok2 == 1, "dry-run 不新增成功行", f"成功行 {ok2}")
            check(len(_snapshot_files(raw_root, "TST", 1)) == 1, "dry-run 不新增快照", "dry-run 新增快照")
            _assert_no_tmp(raw_root)
    finally:
        srv.stop()


def test_t003_cli_fetch_db_not_init():
    print("\n[T003-12] CLI：数据库未初始化 → 非零退出")
    print("-" * 60)
    srv = _LocalServer()
    try:
        reg = build_fetch_registry(srv.base)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            db, raw_root = td / "icd.db", td / "raw_data"
            reg_file = td / "registry.json"
            reg_file.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
            r = _run_fetch_cli(["--fetch", "1", "--registry", str(reg_file), "--db-path", str(db), "--raw-data-root", str(raw_root)], REPO_ROOT)
            check(r.returncode != 0, f"未初始化退出非零（{r.returncode}）", f"退出 {r.returncode}")
    finally:
        srv.stop()


def main():
    print("=" * 60)
    print("ICD 集成测试（T002 + T003）")
    print("=" * 60)
    test_config_valid_registry()
    test_config_invalid_json()
    test_config_duplicate_insurer()
    test_config_unknown_insurer_ref()
    test_config_unverified_with_url()
    test_init_db_schema_and_seeds()
    test_init_db_idempotent()
    test_init_db_preserves_fetch_run()
    test_cli_validate_config_ok()
    test_cli_validate_config_broken()
    test_cli_init_db_broken()
    test_cli_init_db_preserves_existing_db_on_bad_config()
    test_cli_status_db_absent_and_present()
    test_cli_cwd_independence()
    test_no_network_imports()

    print("\n" + "=" * 60)
    print("T003 · HTTP 抓取与原始证据固化")
    print("=" * 60)
    test_t003_fetch_ok_and_fidelity()
    test_t003_fetch_redirect()
    test_t003_fetch_http_errors()
    test_t003_fetch_timeout()
    test_t003_fetch_slow_body_timeout()
    test_t003_fetch_midstream_disconnect()
    test_t003_fetch_oversized()
    test_t003_fetch_dedup_and_version()
    test_t003_fetch_reject()
    test_t003_fetch_dry_run()
    test_t003_path_traversal_guard()
    test_t003_cli_fetch_rejected_nonzero()
    test_t003_cli_fetch_ok_and_dryrun()
    test_t003_cli_fetch_db_not_init()

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
