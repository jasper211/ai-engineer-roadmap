#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HKIA 专属工作区：本地SQLite读写，物理隔离在本Agent目录下
（07_接入记忆_Integrate_Memory/data/hkia.db），不写入目标项目或其他Agent目录。

demo阶段是一次性全量写入，不做增量/去重——每次运行 --reset 会清空重建，
不是"追加不重复"的持久化逻辑。
"""
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "hkia.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS long_term_business (
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    unit TEXT,
    value REAL NOT NULL,
    table_type TEXT NOT NULL,
    period_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_report TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
"""


class Workspace:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def reset(self):
        """demo一次性全量写入前先清空——不是增量去重逻辑，见需求定义第四节。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DROP TABLE IF EXISTS long_term_business")
            conn.executescript(SCHEMA)

    def ensure_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)

    def insert_rows(self, rows: list):
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """INSERT INTO long_term_business
                   (date, category, metric_name, unit, value, table_type,
                    period_type, schema_version, source_report, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (r.date, r.category, r.metric_name, r.unit, r.value,
                     r.table_type, r.period_type, r.schema_version,
                     r.source_report, r.fetched_at)
                    for r in rows
                ],
            )

    def row_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM long_term_business").fetchone()[0]

    def distinct_periods(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            return [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT date FROM long_term_business ORDER BY date"
                ).fetchall()
            ]
