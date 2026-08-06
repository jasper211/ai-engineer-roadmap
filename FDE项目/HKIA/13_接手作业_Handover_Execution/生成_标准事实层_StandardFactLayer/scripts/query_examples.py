#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标准事实层 · 查询示例（证明可查询性）
运行：python3 scripts/query_examples.py
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "standard_fact_layer_2023_2026Q1.db"


def q(conn, title, sql, params=()):
    print(f"\n▶ {title}")
    rows = conn.execute(sql, params).fetchall()
    cols = [d[0] for d in conn.execute(sql, params).description]
    print("  | ".join(cols))
    for r in rows:
        print("  | ".join(str(x) for x in r))
    print(f"  ({len(rows)} 行)")
    return rows


def main():
    conn = sqlite3.connect(DB)
    # 1. 个人新造整付保费四期市场总额
    s1 = """SELECT period, value, unit FROM market_facts
            WHERE metric_id='NB_IND_TOTAL_SINGLE_PREMIUM' ORDER BY period"""
    q(conn, "个人新造整付保费 · 市场总额四期", s1)

    # 2. 2026Q1 个人新造整付保费公司 TOP5（数值型）
    s2 = """SELECT entity_key, source_abbrev, value, unit FROM company_facts
            WHERE period='2026Q1' AND metric_id='NB_IND_TOTAL_SINGLE_PREMIUM'
              AND value_status='reported_numeric'
            ORDER BY value DESC LIMIT 5"""
    q(conn, "2026Q1 个人新造整付保费 · 公司 TOP5", s2)

    # 3. 跨 2025 schema 断点的个人核心指标可比等级
    s3 = """SELECT DISTINCT metric_id, comparability, period_basis FROM company_facts
            WHERE metric_id='IF_IND_TOTAL_POLICIES'"""
    q(conn, "指标可比等级（示例 IF_IND_TOTAL_POLICIES）", s3)

    # 4. 缺失保持 NULL 抽查
    s4 = """SELECT count(*) AS missing FROM company_facts WHERE value_status='reported_missing'"""
    q(conn, "缺值（NULL）总行数（应=2471）", s4)

    # 5. 通过线索桥识别 Chubb 转移
    s5 = """SELECT period, business_lineage, metric_id, count(*) AS n
            FROM company_facts WHERE business_lineage LIKE 'LINEAGE_CHUBB%'
            GROUP BY period, business_lineage, metric_id LIMIT 6"""
    q(conn, "Chubb 线索桥事实分布（示例）", s5)

    conn.close()


if __name__ == "__main__":
    main()
