#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：只读同步 mga_platform.public.fact_target（目标APE数据源）到本地CSV快照。

对应 01_初始化项目_Initialize_Project/目标APE数据源_fact_target_核实.md。
连接参数在 skills/db_config_local.py（本地文件，已gitignore，不进版本库）。
fact_target是规划性质的参考数据（年度/月度目标，不是交易流水），不需要每次跑Agent
都连库，走本地快照+手动/定期同步即可，参照 VNW postgres_reader.py 的只读约束
（仅SELECT，禁止INSERT/UPDATE/DELETE/DROP等）。
"""
import csv
import re
from pathlib import Path

READ_ONLY_SQL = re.compile(r"^\s*(SELECT|WITH)\b", re.I)
FORBIDDEN_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE)\b", re.I)

FACT_TARGET_COLUMNS = [
    "target_id", "period_key", "business_category", "segment_code", "ka_id", "team_id",
    "target_category", "carrier_code", "business_line", "product_category", "target_ape",
]

FACT_TARGET_SQL = f"""
    SELECT {', '.join(FACT_TARGET_COLUMNS)}
    FROM public.fact_target
    ORDER BY target_id;
"""


def assert_read_only(sql: str) -> None:
    if not READ_ONLY_SQL.search(sql) or FORBIDDEN_SQL.search(sql):
        raise ValueError("PDA仅允许对fact_target执行SELECT只读查询")


def sync(out_path: Path) -> int:
    """连接mga_platform，拉取fact_target全量，写本地CSV快照，返回行数。
    需要 skills/db_config_local.py 存在（本地专属，不在版本库里）。"""
    import psycopg2
    from skills.db_config_local import DB_CONFIG

    assert_read_only(FACT_TARGET_SQL)
    conn = psycopg2.connect(**DB_CONFIG, connect_timeout=10)
    try:
        cur = conn.cursor()
        cur.execute(FACT_TARGET_SQL)
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(FACT_TARGET_COLUMNS)
        w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    import sys
    default_out = Path(__file__).resolve().parents[2] / "07_接入记忆_Integrate_Memory" / "data" / "fact_target_snapshot.csv"
    n = sync(default_out)
    print(f"已同步 {n} 行到 {default_out}")
