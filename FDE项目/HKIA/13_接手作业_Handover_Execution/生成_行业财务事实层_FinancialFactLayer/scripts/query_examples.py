#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行业财务事实层查询示例
用法: python3 scripts/query_examples.py
"""
import os, sqlite3
DB = os.path.join(os.path.dirname(__file__), "..", "data", "financial_fact_layer.db")
conn=sqlite3.connect(DB)
cur=conn.cursor()

def show(title, rows, header=None):
    print(f"\n=== {title} ===")
    if header: print(" | ".join(header))
    for r in rows: print(" | ".join("" if v is None else str(v) for v in r))

# 1. 某期某科目全 scope
show("2026Q1 总资产(Total assets) 按基金口径",
     cur.execute("SELECT fund_scope, round(value_hkd_million,1) FROM financial_facts WHERE period='2026Q1' AND item_id='total_assets' ORDER BY fund_scope").fetchall(),
     ["fund_scope","total_assets(HK$m)"])

# 2. 行业总计某科目跨期趋势
show("行业总计 Total assets 跨期",
     cur.execute("SELECT period, round(value_hkd_million,1) FROM financial_facts WHERE fund_scope='industry_total' AND item_id='total_assets' ORDER BY period").fetchall(),
     ["period","industry_total_assets(HK$m)"])

# 3. 长期业务资产配置结构(2026Q1)
show("长期业务资产分项占比(2026Q1, % of long-term total assets)",
     cur.execute("""SELECT item_label_zh, round(value_hkd_million,1),
        round(100.0*value_hkd_million/(SELECT value_hkd_million FROM financial_facts WHERE period='2026Q1' AND fund_scope='long_term' AND item_id='total_assets'),2)||'%'
        FROM financial_facts WHERE period='2026Q1' AND fund_scope='long_term' AND item_id IN
        ('cash_and_deposits','debt_securities','equities_portfolio','properties','loans_and_advances','other_financial_assets','reinsurance_assets') ORDER BY value_hkd_million DESC""").fetchall(),
     ["item","HK$m","share"])

# 4. 净资产跨期
show("行业总计净资産(Net assets) 跨期",
     cur.execute("SELECT period, round(value_hkd_million,1) FROM financial_facts WHERE fund_scope='industry_total' AND item_id='net_assets' ORDER BY period").fetchall(),
     ["period","net_assets(HK$m)"])
conn.close()
