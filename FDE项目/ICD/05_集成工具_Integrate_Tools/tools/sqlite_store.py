#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · tools/sqlite_store.py · SQLite 迁移与幂等初始化

职责边界：把已验收的 `../03_规划项目结构_Plan_Project_Structure/data_contract.md`
里的 12 张表 DDL + 6 个索引 + 11 条错误代码种子，转成可重复执行的迁移资源。
本模块不访问网络、不解析披露文件、不删除任何已存在的行。

幂等保证（对齐任务书 T002 功能要求第 5 条与验收标准第 4/5 条）：
- 建表用 `CREATE TABLE IF NOT EXISTS`，建索引用 `CREATE INDEX IF NOT EXISTS`，
  重复执行不触碰已存在的行。
- 险企/错误代码用 `INSERT OR IGNORE`（主键冲突即跳过）。
- 数据源用 `NOT EXISTS` 子查询按自然键去重（含 entry_url 为 NULL 的
  UNVERIFIED 条目——SQLite 的 UNIQUE 对 NULL 不去重，所以这里显式判空）。
- 全程只 INSERT，绝无 DELETE/UPDATE，`fetch_run` 与业务表已有行不受影响。
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

# 12 张表的规范名称（顺序即 data_contract.md 定义顺序，验收标准第 3 条用）
TABLES: List[str] = [
    "insurer",
    "insurer_official_name",
    "data_source",
    "fetch_run",
    "product",
    "product_alias",
    "fulfillment_ratio",
    "rbc_statement",
    "rbc_risk_component",
    "parse_result",
    "coverage_status",
    "error_code",
]

# DDL 完全对齐 data_contract.md 第四节（含 fetch_run 的三态 CHECK 约束）
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS insurer (
  insurer_code    TEXT PRIMARY KEY,
  name_en         TEXT NOT NULL,
  name_zh         TEXT,
  legal_name_note TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS insurer_official_name (
  id            INTEGER PRIMARY KEY,
  insurer_code  TEXT NOT NULL REFERENCES insurer(insurer_code),
  official_name TEXT NOT NULL,
  language      TEXT NOT NULL CHECK (language IN ('en','zh','zh-hans','zh-hant')),
  source_hint   TEXT,
  first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (insurer_code, official_name, language)
);

CREATE TABLE IF NOT EXISTS data_source (
  source_id        INTEGER PRIMARY KEY,
  insurer_code     TEXT NOT NULL REFERENCES insurer(insurer_code),
  disclosure_type  TEXT NOT NULL CHECK (disclosure_type IN ('fulfillment_ratio','total_cash_value_ratio','rbc')),
  entry_url        TEXT,
  format           TEXT,
  access_status    TEXT NOT NULL CHECK (access_status IN ('OPEN','PARTIAL','BLOCKED','UNVERIFIED')),
  parser_hint      TEXT,
  requires_browser INTEGER NOT NULL DEFAULT 0 CHECK (requires_browser IN (0,1)),
  evidence_basis   TEXT NOT NULL,
  allows_empty     INTEGER NOT NULL DEFAULT 0 CHECK (allows_empty IN (0,1)),
  last_verified_at TEXT,
  url_version      INTEGER NOT NULL DEFAULT 1,
  is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  UNIQUE (insurer_code, disclosure_type, entry_url)
);

CREATE TABLE IF NOT EXISTS fetch_run (
  run_id         INTEGER PRIMARY KEY,
  source_id      INTEGER NOT NULL REFERENCES data_source(source_id),
  fetched_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  final_url      TEXT,
  http_status    INTEGER,
  content_hash   TEXT,
  content_length INTEGER,
  snapshot_path  TEXT,
  fetch_status   TEXT NOT NULL CHECK (fetch_status IN ('OK','HTTP_ERROR','NETWORK_ERROR')),
  error_code     TEXT REFERENCES error_code(code),
  note           TEXT,
  UNIQUE (source_id, content_hash),
  CHECK (
    (fetch_status = 'OK'            AND content_hash IS NOT NULL AND snapshot_path IS NOT NULL)
    OR
    (fetch_status = 'HTTP_ERROR'    AND content_hash IS NULL AND snapshot_path IS NULL AND http_status IS NOT NULL)
    OR
    (fetch_status = 'NETWORK_ERROR' AND content_hash IS NULL AND snapshot_path IS NULL AND http_status IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS product (
  product_id        INTEGER PRIMARY KEY,
  insurer_code      TEXT NOT NULL REFERENCES insurer(insurer_code),
  canonical_name_en TEXT,
  canonical_name_zh TEXT,
  mapping_status    TEXT NOT NULL DEFAULT 'TENTATIVE' CHECK (mapping_status IN ('TENTATIVE','CONFIRMED')),
  first_seen_run_id INTEGER REFERENCES fetch_run(run_id),
  UNIQUE (insurer_code, canonical_name_en, canonical_name_zh)
);

CREATE TABLE IF NOT EXISTS product_alias (
  id               INTEGER PRIMARY KEY,
  product_id       INTEGER NOT NULL REFERENCES product(product_id),
  raw_name         TEXT NOT NULL,
  language         TEXT CHECK (language IN ('en','zh','zh-hans','zh-hant')),
  first_seen_run_id INTEGER REFERENCES fetch_run(run_id),
  UNIQUE (raw_name)
);

CREATE TABLE IF NOT EXISTS fulfillment_ratio (
  ratio_id          INTEGER PRIMARY KEY,
  insurer_code      TEXT NOT NULL REFERENCES insurer(insurer_code),
  product_id        INTEGER REFERENCES product(product_id),
  product_name_raw  TEXT NOT NULL,
  dividend_type     TEXT NOT NULL CHECK (dividend_type IN ('AD','TD','TCV','REVERSIONARY','OTHER')),
  report_year       INTEGER NOT NULL,
  observation_year  INTEGER NOT NULL,
  raw_value         TEXT NOT NULL,
  normalized_value  REAL,
  unit              TEXT NOT NULL DEFAULT 'percent' CHECK (unit IN ('percent')),
  run_id            INTEGER NOT NULL REFERENCES fetch_run(run_id),
  UNIQUE (insurer_code, product_name_raw, dividend_type, report_year, observation_year, run_id)
);

CREATE TABLE IF NOT EXISTS rbc_statement (
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

CREATE TABLE IF NOT EXISTS rbc_risk_component (
  id                        INTEGER PRIMARY KEY,
  rbc_id                    INTEGER NOT NULL REFERENCES rbc_statement(rbc_id),
  risk_type                 TEXT NOT NULL CHECK (risk_type IN (
                               'MARKET','INTEREST_RATE','CREDIT_SPREAD','EQUITY','PROPERTY',
                               'CURRENCY','LIFE','GENERAL_INSURANCE','OPERATIONAL','OTHER')),
  prescribed_capital_amount REAL,
  currency                  TEXT NOT NULL DEFAULT 'HKD',
  UNIQUE (rbc_id, risk_type)
);

CREATE TABLE IF NOT EXISTS parse_result (
  id               INTEGER PRIMARY KEY,
  run_id           INTEGER NOT NULL REFERENCES fetch_run(run_id),
  parse_status     TEXT NOT NULL CHECK (parse_status IN ('OK','STRUCTURE_MISMATCH','ZERO_RECORD','PARTIAL','NOT_PARSED')),
  records_produced INTEGER NOT NULL DEFAULT 0,
  error_code       TEXT REFERENCES error_code(code),
  message          TEXT,
  UNIQUE (run_id)
);

CREATE TABLE IF NOT EXISTS coverage_status (
  id                  INTEGER PRIMARY KEY,
  insurer_code        TEXT NOT NULL REFERENCES insurer(insurer_code),
  disclosure_type     TEXT NOT NULL CHECK (disclosure_type IN ('fulfillment_ratio','total_cash_value_ratio','rbc')),
  coverage_status     TEXT NOT NULL CHECK (coverage_status IN ('FULL','PARTIAL','MISSING','BLOCKED','UNVERIFIED')),
  last_success_run_id INTEGER REFERENCES fetch_run(run_id),
  last_checked_at     TEXT,
  UNIQUE (insurer_code, disclosure_type)
);

CREATE TABLE IF NOT EXISTS error_code (
  code            TEXT PRIMARY KEY,
  category        TEXT NOT NULL CHECK (category IN ('NETWORK','HTTP','PARSE','DATA','IO')),
  is_hard_failure INTEGER NOT NULL DEFAULT 0 CHECK (is_hard_failure IN (0,1)),
  description     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fetch_run_source      ON fetch_run(source_id);
CREATE INDEX IF NOT EXISTS idx_ratio_natural         ON fulfillment_ratio(insurer_code, product_name_raw, dividend_type, report_year, observation_year);
CREATE INDEX IF NOT EXISTS idx_ratio_product         ON fulfillment_ratio(product_id);
CREATE INDEX IF NOT EXISTS idx_rbc_insurer_year      ON rbc_statement(insurer_code, report_year);
CREATE INDEX IF NOT EXISTS idx_alias_raw_name        ON product_alias(raw_name);
CREATE INDEX IF NOT EXISTS idx_official_name_insurer ON insurer_official_name(insurer_code);
"""

# 11 条错误代码种子（对齐 data_contract.md 第五节）
ERROR_CODE_SEEDS: List[Tuple[str, str, int, str]] = [
    ("HTTP_403",               "HTTP",    1, "HTTP 403（多为机器人防护拦截）"),
    ("HTTP_404",               "HTTP",    1, "HTTP 404（页面/文件不存在或路径过期）"),
    ("HTTP_5XX",               "HTTP",    1, "HTTP 5xx（服务端错误）"),
    ("NETWORK_TIMEOUT",        "NETWORK", 1, "网络超时"),
    ("NETWORK_CONNECTION",     "NETWORK", 1, "连接失败/DNS 失败"),
    ("STRUCTURE_MISMATCH",     "PARSE",   1, "HTTP 成功但页面/文件结构不符合预期（不得写\"无数据\"）"),
    ("ZERO_RECORD",            "PARSE",   1, "解析出 0 条记录（硬失败，除非 allows_empty=true）"),
    ("PDF_NO_TEXT",            "PARSE",   1, "PDF 文字层损坏/扫描件，无法提取文字"),
    ("VALUE_UNPARSEABLE",      "DATA",    0, "值无法解析为数字（保留 raw_value，normalized=NULL）"),
    ("SNAPSHOT_WRITE_FAILED",  "IO",      1, "原始快照落盘失败"),
    ("DB_WRITE_FAILED",        "IO",      1, "SQLite 写入失败"),
]


def connect(db_path: Path) -> sqlite3.Connection:
    """打开（必要时创建）数据库连接，父目录自动创建，foreign_keys 开启。"""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """幂等建表 + 建索引（全部 IF NOT EXISTS，不触碰已有行）。"""
    conn.executescript(SCHEMA_SQL)


def seed_error_codes(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO error_code (code, category, is_hard_failure, description) VALUES (?, ?, ?, ?)",
        ERROR_CODE_SEEDS,
    )


def seed_insurers(conn: sqlite3.Connection, insurers: List[dict]) -> None:
    rows = [(i.get("insurer_code"), i.get("name_en"), i.get("name_zh")) for i in insurers]
    conn.executemany(
        "INSERT OR IGNORE INTO insurer (insurer_code, name_en, name_zh) VALUES (?, ?, ?)",
        rows,
    )


def seed_sources(conn: sqlite3.Connection, sources: List[dict]) -> None:
    """按自然键幂等插入数据源；entry_url 为 NULL 的 UNVERIFIED 条目用显式判空去重。"""
    sql = """
        INSERT INTO data_source (
            insurer_code, disclosure_type, entry_url, format, access_status,
            parser_hint, requires_browser, evidence_basis, allows_empty,
            last_verified_at, url_version, is_active
        )
        SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1
        WHERE NOT EXISTS (
            SELECT 1 FROM data_source
            WHERE insurer_code = ?
              AND disclosure_type = ?
              AND access_status = ?
              AND ((entry_url IS NULL AND ? IS NULL) OR (entry_url = ?))
        )
    """
    for s in sources:
        code = s.get("insurer_code")
        d_type = s.get("disclosure_type")
        entry_url = s.get("entry_url")
        fmt = s.get("format")
        status = s.get("access_status")
        params = (
            code, d_type, entry_url, fmt, status,
            s.get("parser_hint"),
            1 if s.get("requires_browser") else 0,
            s.get("evidence_basis"),
            1 if s.get("allows_empty") else 0,
            s.get("last_verified_at"),
            s.get("url_version", 1),
            code, d_type, status, entry_url, entry_url,
        )
        conn.execute(sql, params)


def table_names(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def collect_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def init_db(db_path: Path, registry: dict) -> dict:
    """初始化数据库：建 schema + 播种险企/数据源/错误代码，全程幂等、只增不改。

    返回摘要 dict：12 张表是否齐备 + 各表行数（供 --init-db 输出与测试断言）。
    """
    conn = connect(db_path)
    try:
        create_schema(conn)
        seed_error_codes(conn)
        seed_insurers(conn, registry.get("insurers", []))
        seed_sources(conn, registry.get("sources", []))
        conn.commit()
        counts = collect_counts(conn)
        names = table_names(conn)
        missing = [t for t in TABLES if t not in names]
        return {
            "schema_version": "1.0",
            "table_count": len([t for t in TABLES if t in names]),
            "tables_present": [t for t in TABLES if t in names],
            "missing_tables": missing,
            "counts": counts,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
