#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2025 全年 provisional 公司级事实层
==================================
范围：从 2025Q4 原始文件 (4q25long.xlsx) 的 Table L1(新造) / Table L3(有效) 提取公司级数据。
  - Table L1 '總額' 列（整付 col9 / 年度化 col10）：个人新造保费
  - Table L3 '總額' 列（保單數目 col15 / 承保保額 col16 / 整付 col17 / 非整付 col18）：个人有效业务
来源：2025Q4 = January to December 2025（年度 provisional）
依据：quarterly_long_metric_comparability_v0.1.yaml 年度 provisional 接入；build_annual_provisional_2025 已取市场级。
本层为公司级补充，使 certified(2022/2023/2024) ↔ provisional(2025) 可做公司级 reconcile。
"""
import os, sqlite3, hashlib, glob

SRC = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/FDE项目/HKIA/12_分析框架验证_Validate_Framework/01_sources/raw/SRC-REG-IA-LTQ/2025Q4/4q25long.xlsx"
YEAR=2025
CERT="provisional"

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as fh:
        for b in iter(lambda: fh.read(65536), b""): h.update(b)
    return h.hexdigest()

def load_sheet(name):
    import openpyxl
    wb=openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws=wb[name]
    grid=[]
    for row in ws.iter_rows():
        grid.append([c.value for c in row])
    wb.close()
    return grid

def parse_l1(grid):
    """Table L1 新造：col1=英文名 col2=中文名 col9=总额整付 col10=总额年度化，
       上市总额行(Market Total)。"""
    facts=[]
    for r in range(1, len(grid)+1):
        row=grid[r-1]
        if len(row)<10: continue
        name_en=row[0]; name_zh=row[1]
        if not name_en or not str(name_en).strip(): continue
        s=str(name_en).strip()
        try:
            sv=float(row[8]); av=float(row[9])  # col9, col10
        except (TypeError,ValueError):
            continue
        if '總' in s or 'market total' in s.lower():
            scope="market_total"
        else:
            scope="insurer"
        facts.append(dict(period_layer="annual_provisional", year=YEAR, certification=CERT,
            table_id="L1", subject="individual_long_term_new_business", entity_scope=scope,
            insurer_name_en=name_en, insurer_name_zh=(name_zh or ""),
            metric_sem="nb_total_single_premium", value=sv, unit="hkd_thousand",
            source_sheet="Table L1", source_cell=f"L1!I{r}"))
        facts.append(dict(period_layer="annual_provisional", year=YEAR, certification=CERT,
            table_id="L1", subject="individual_long_term_new_business", entity_scope=scope,
            insurer_name_en=name_en, insurer_name_zh=(name_zh or ""),
            metric_sem="nb_total_annualized_premium", value=av, unit="hkd_thousand",
            source_sheet="Table L1", source_cell=f"L1!J{r}"))
    return facts

def parse_l3(grid):
    """Table L3 有效：col1=英文名 col2=中文名；總額列 col15=保單 col16=保額 col17=整付 col18=非整付。"""
    facts=[]
    for r in range(1, len(grid)+1):
        row=grid[r-1]
        if len(row)<18: continue
        name_en=row[0]; name_zh=row[1]
        if not name_en or not str(name_en).strip(): continue
        s=str(name_en).strip()
        try:
            pol=float(row[14]); sums=float(row[15]); single=float(row[16]); nonsingle=float(row[17])
        except (TypeError,ValueError):
            continue
        scope="market_total" if ('總' in s or 'market total' in s.lower()) else "insurer"
        for sem,val in [("if_total_policies",pol),("if_total_sums_assured",sums),
                        ("if_total_single_premium",single),("if_total_non_single_premium",nonsingle)]:
            unit="count" if sem=="if_total_policies" else "hkd_thousand"
            facts.append(dict(period_layer="annual_provisional", year=YEAR, certification=CERT,
                table_id="L3", subject="individual_long_term_inforce", entity_scope=scope,
                insurer_name_en=name_en, insurer_name_zh=(name_zh or ""),
                metric_sem=sem, value=val, unit=unit,
                source_sheet="Table L3", source_cell=f"L3!{r}:{r+8}"))
    return facts

def main():
    out_dir=os.path.join(os.path.dirname(__file__),"..","data"); out_dir=os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    db_path=os.path.join(out_dir,"annual_provisional_company_2025.db")
    l1=parse_l1(load_sheet("Table L1"))
    l3=parse_l3(load_sheet("Table L3"))
    facts=l1+l3
    for fa in facts:
        fa["source_file"]="4q25long.xlsx"; fa["checksum_sha256"]=sha256(SRC)
    if os.path.exists(db_path): os.remove(db_path)
    conn=sqlite3.connect(db_path); cur=conn.cursor()
    cur.execute("""CREATE TABLE provisional_company_facts(
      period_layer TEXT, year INTEGER, certification TEXT, table_id TEXT, subject TEXT,
      entity_scope TEXT, insurer_name_en TEXT, insurer_name_zh TEXT, metric_sem TEXT,
      value REAL, unit TEXT, source_sheet TEXT, source_cell TEXT, source_file TEXT, checksum_sha256 TEXT)""")
    cur.executemany("""INSERT INTO provisional_company_facts VALUES
      (:period_layer,:year,:certification,:table_id,:subject,:entity_scope,:insurer_name_en,
       :insurer_name_zh,:metric_sem,:value,:unit,:source_sheet,:source_cell,:source_file,:checksum_sha256)""", facts)
    conn.commit()
    n=cur.execute("SELECT COUNT(*) FROM provisional_company_facts").fetchone()[0]
    nins=cur.execute("SELECT COUNT(*) FROM provisional_company_facts WHERE entity_scope='insurer'").fetchone()[0]
    nmt=cur.execute("SELECT COUNT(*) FROM provisional_company_facts WHERE entity_scope='market_total'").fetchone()[0]
    conn.close()
    print(f"DB: {db_path}")
    print(f"  facts={n} insurer={nins} market_total={nmt}")
    print(f"  l1 facts={len(l1)} l3 facts={len(l3)}")

if __name__=="__main__":
    main()
