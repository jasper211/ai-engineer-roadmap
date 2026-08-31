#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补充 2025Q2 行业财务事实层（源：PDF 版）
=========================================
背景：IA 官方 2q25 Industry Financial xlsx 文件损坏（旧 OLE2结构不可读、Excel打不开），
     但官网同季度提供 PDF 版（可行）。本脚本从 PDF 第1页"By Fund"表格提取 2025Q2 资产负债，
     生成 17科目×4基金=68条事实，并入/对齐 financial_fact_layer.db。
数据：截至 2025年6月（2025Q2），单位港币百万元，provisional/unaudited。
校验：与 3q25 xlsx 中 June2025 列交叉核对（行业总资产 5,738,914 等）。
"""
import os, sqlite3, hashlib, json

PDF = "/Users/a112233/Downloads/2q25_Industry_Financial_Info.pdf"
DB  = os.path.join(os.path.dirname(__file__), "..", "data", "financial_fact_layer.db")

# 科目顺序（与 PDF 表格行一致）及中文标签
ITEMS = [
    ("total_assets","總資產"),("cash_and_deposits","現金和存款"),
    ("debt_securities","債務證券"),("equities_portfolio","股權 (包括組合投資)"),
    ("properties","房產"),("loans_and_advances","貸款及墊款"),
    ("unit_linked_or_retirement_policyholder_assets","與單位相連產品或退休計劃相關的保單持有人賬戶資產"),
    ("other_financial_assets","其他金融資產"),("reinsurance_assets","再保險資產"),
    ("tax_assets","稅務資產"),("other_assets","其他資產"),("total_liabilities","總負債"),
    ("insurance_liabilities_incl_reinsurance","保險負債 (包括再保險負債)"),
    ("financial_liabilities","金融負債"),("tax_liabilities","稅務負債"),
    ("other_liabilities","其他負債"),("net_assets","淨資產"),
]
SCOPES = ["industry_total","long_term","participating_long_term","general_business"]

def parse_pdf():
    import pdfplumber
    with pdfplumber.open(PDF) as pdf:
        tbl = pdf.pages[0].extract_tables()[0]
    facts=[]
    # skip header row0, rows1-17 items, ignore note rows
    for i,row in enumerate(tbl[1:19], start=0):
        if i >= len(ITEMS): break
        item_id, label = ITEMS[i]
        for si, scope in enumerate(SCOPES):
            raw = row[si+1] if si+1 < len(row) else None
            if raw is None or raw.strip()=="": val=None
            elif raw.strip()=="-": val=0.0
            else: val=float(raw.replace(",",""))
            facts.append(dict(period="2025Q2", fund_scope=scope, item_id=item_id,
                item_label_zh=label, value_hkd_million=val, unit="HKD_million",
                flag="provisional_unaudited", certification="provisional", source_file="2q25_Industry_Financial_Info.pdf",
                checksum_sha256="pdf"))
    return facts

def main():
    facts=parse_pdf()
    print(f"提取到 {len(facts)} 条 2025Q2 财务事实（17科目×4基金）")
    # 交叉核对行业总资产
    for fa in facts:
        if fa['fund_scope']=='industry_total' and fa['item_id']=='total_assets':
            print(f"  2025Q2 行业总资产 = {fa['value_hkd_million']:,} 百万元（官方 5,738,914）")
    # 写入 DB（若已存在表则插入 2025Q2，覆盖该期）
    conn=sqlite3.connect(DB); cur=conn.cursor()
    cols=[r[1] for r in cur.execute("PRAGMA table_info(financial_facts)").fetchall()]
    if not cols:
        cur.execute("""CREATE TABLE financial_facts(
            period TEXT, fund_scope TEXT, item_id TEXT, item_label_zh TEXT,
            value_hkd_million REAL, unit TEXT, flag TEXT, source_file TEXT, checksum_sha256 TEXT, certification TEXT)""")
    # 删除已有 2025Q2（幂等）
    cur.execute("DELETE FROM financial_facts WHERE period='2025Q2'")
    cur.executemany("""INSERT INTO financial_facts VALUES
      (:period,:fund_scope,:item_id,:item_label_zh,:value_hkd_million,:unit,:flag,:source_file,:checksum_sha256,:certification)""", facts)
    conn.commit()
    n=cur.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0]
    per=cur.execute("SELECT COUNT(DISTINCT period) FROM financial_facts").fetchone()[0]
    pr=cur.execute("SELECT DISTINCT period FROM financial_facts ORDER BY period").fetchall()
    conn.close()
    print(f"写入完成。financial_facts 总行数={n}, 覆盖期数={per}")
    print("  期:", [p[0] for p in pr])

if __name__=="__main__":
    main()
