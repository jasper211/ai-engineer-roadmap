#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B2 · 标准事实层 Standard Fact Layer Build
====================================================
把 2023Q1–2026Q1 的
  - 72 条市场核心事实（market_total_core_facts_2023Q1_2026Q1_v0.1.csv）
  - 4914 条公司事实（HKIA_company_fact_layer_2023Q1_2026Q1_v0.1.xlsx / Company Facts）
固化为统一、可查询的 SQLite 标准事实表。

Schema 遵循 intergalactic 风格：期间 / 指标ID / 原始值 / 单位 / 流量或存量 / 可比等级 / 来源locator。

纪律（沿用接手前口径）：
  - 缺值保持 NULL，绝不补零（company_numeric/missing 如实登记 status）；
  - 原始值单位 HKD_thousand / count 保留，不擅自折算；
  - 每个 fact 带 source 定位（sheet + cell + file 或 source_range）；
  - 2026Q1 Chubb/canada_mypace 转移事件以 lineage 桥承接，单值不"发明"。

输出：
  data/standard_fact_layer_2023_2026Q1.db
  qa/standard_fact_layer_qa_report.md
"""
import sqlite3, json, re, os
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[1]                 # 生成_标准事实层
VFRAME = BASE.parent.parent / "12_分析框架验证_Validate_Framework"
QRONG = VFRAME / "04_normalized" / "quarterly_long"
OUTDB = BASE / "data" / "standard_fact_layer_2023_2026Q1.db"
QADIR = BASE / "qa"
QADIR.mkdir(parents=True, exist_ok=True)
(BASE / "data").mkdir(parents=True, exist_ok=True)

MARKET_CSV = QRONG / "market_total_core_facts_2023Q1_2026Q1_v0.1.csv"
COMPANY_XLSX = VFRAME / "outputs" / "HKIA_company_fact_layer_2023Q1_2026Q1_v0.1.xlsx"
YOY_CSV = QRONG / "core_metric_yoy_2023Q1_2026Q1_v0.1.csv"
BRIDGE_CSV = QRONG / "insurer_identity_alias_bridge_v0.1.csv"

SCHEMA_METRICS = [  # 18 指标 官方定义（来自 quarterly_long_metric_comparability_v0.1.yaml）
    ("NB_IND_TOTAL_SINGLE_PREMIUM","HKD_thousand","flow_during_period","个人新造整付保费"),
    ("NB_IND_TOTAL_ANNUALIZED_PREMIUM","HKD_thousand","flow_during_period","个人新造年度化保费"),
    ("NB_GROUP_POLICIES","count","flow_during_period","团体新造保单数"),
    ("NB_GROUP_LIVES","count","flow_during_period","团体新造受保人数"),
    ("NB_GROUP_SINGLE_PREMIUM","HKD_thousand","flow_during_period","团体新造整付保费"),
    ("NB_GROUP_ANNUALIZED_PREMIUM","HKD_thousand","flow_during_period","团体新造年度化保费"),
    ("IF_IND_TOTAL_POLICIES","count","stock_at_period_end","个人有效保单数"),
    ("IF_IND_TOTAL_SUMS_ASSURED_OR_ANNUITIES","HKD_thousand","stock_at_period_end","个人有效保额/年金"),
    ("IF_IND_TOTAL_SINGLE_PREMIUM_RECEIVABLE","HKD_thousand","flow_during_period","个人有效整付保费"),
    ("IF_IND_TOTAL_NON_SINGLE_PREMIUM_RECEIVABLE","HKD_thousand","flow_during_period","个人有效非整付保费"),
    ("IF_GROUP_NON_RETIREMENT_POLICIES","count","stock_at_period_end","团体(非退休)有效保单数"),
    ("IF_GROUP_NON_RETIREMENT_LIVES","count","stock_at_period_end","团体(非退休)有效受保人数"),
    ("IF_GROUP_NON_RETIREMENT_SINGLE_PREMIUM_RECEIVABLE","HKD_thousand","flow_during_period","团体(非退休)有效整付保费"),
    ("IF_GROUP_NON_RETIREMENT_NON_SINGLE_PREMIUM_RECEIVABLE","HKD_thousand","flow_during_period","团体(非退休)有效非整付保费"),
    ("IF_RETIREMENT_SCHEMES","count","stock_at_period_end","退休计划数量"),
    ("IF_RETIREMENT_ENDING_FUND_BALANCE","HKD_thousand","stock_at_period_end","退休计划期末基金余额"),
    ("IF_RETIREMENT_SINGLE_CONTRIBUTIONS","HKD_thousand","flow_during_period","退休计划单项供款"),
    ("IF_RETIREMENT_NON_SINGLE_CONTRIBUTIONS","HKD_thousand","flow_during_period","退休计划非单项供款"),
]
COMPARABILITY = {  # 官方可比等级（来自 yaml）
    "NB_IND_TOTAL_SINGLE_PREMIUM":"comparable_with_schema_bridge",
    "NB_IND_TOTAL_ANNUALIZED_PREMIUM":"comparable_with_schema_bridge",
    "IF_IND_TOTAL_POLICIES":"comparable_with_schema_bridge",
    "IF_IND_TOTAL_SUMS_ASSURED_OR_ANNUITIES":"comparable_with_schema_bridge",
    "IF_IND_TOTAL_SINGLE_PREMIUM_RECEIVABLE":"comparable_with_schema_bridge",
    "IF_IND_TOTAL_NON_SINGLE_PREMIUM_RECEIVABLE":"comparable_with_schema_bridge",
}
PERIODS = ["2023Q1","2024Q1","2025Q1","2026Q1"]

def load_market():
    df = pd.read_csv(MARKET_CSV)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df

def load_company():
    df = pd.read_excel(COMPANY_XLSX, sheet_name="Company Facts")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df

def period_basis_of(metric):
    for m,u,b,zh in SCHEMA_METRICS:
        if m==metric: return b
    return "unknown"

def comparability_of(metric):
    return COMPARABILITY.get(metric, "directly_comparable_by_label")

def expected_unit(metric):
    for m,u,b,zh in SCHEMA_METRICS:
        if m==metric: return u
    return "unknown"

def build(conn):
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS market_facts(
        fact_id TEXT PRIMARY KEY,
        period TEXT, metric_id TEXT, metric_label TEXT,
        value REAL, unit TEXT, period_basis TEXT, comparability TEXT,
        source_sheet TEXT, source_range TEXT, source_file TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS company_facts(
        fact_id TEXT PRIMARY KEY,
        period TEXT, metric_id TEXT, metric_label TEXT,
        entity_key TEXT, source_abbrev TEXT, business_lineage TEXT, bridge_class TEXT,
        value REAL, value_status TEXT, unit TEXT, period_basis TEXT, comparability TEXT,
        source_sheet TEXT, source_cell TEXT, source_file TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS schema_metrics(
        metric_id TEXT PRIMARY KEY, unit TEXT, period_basis TEXT, metric_label TEXT)""")
    for m,u,b,zh in SCHEMA_METRICS:
        cur.execute("INSERT OR REPLACE INTO schema_metrics VALUES(?,?,?,?)",(m,u,b,zh))
    conn.commit()

def fmt(v):
    return None if pd.isna(v) else float(v)

def main():
    mkt = load_market()
    comp = load_company()
    if os.path.exists(OUTDB): os.remove(OUTDB)
    conn = sqlite3.connect(OUTDB)
    build(conn); cur = conn.cursor()

    n_mkt=0
    for _,r in mkt.iterrows():
        p=r["period"]; m=r["metric_id"]
        v=fmt(r["value"])
        u=r.get("unit","HKD_thousand"); b=r.get("period_basis",period_basis_of(m))
        c=r.get("comparability",comparability_of(m))
        ss=r.get("source_sheet",""); sr=r.get("source_range","")
        fid=f"M|{p}|{m}"
        cur.execute("""INSERT OR REPLACE INTO market_facts VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (fid,p,m,"",v,u,b,c,ss,sr,"market_total_core_facts_2023Q1_2026Q1_v0.1.csv"))
        n_mkt+=1
    # metric_label 用 schema_metrics 回填
    for m,uu,bb,zh in SCHEMA_METRICS:
        cur.execute("UPDATE market_facts SET metric_label=?, unit=?, period_basis=?, comparability=? WHERE metric_id=?",(zh,uu,bb, comparability_of(m),m))

    n_comp=0
    for _,r in comp.iterrows():
        p=r["period"]; m=r["metric_id"]
        v=fmt(r["value"]); st=r.get("value_status","reported_missing")
        u=r.get("unit","HKD_thousand"); b=period_basis_of(m)
        fid=f"C|{p}|{r['canonical_entity_key']}|{m}"
        cur.execute("""INSERT OR REPLACE INTO company_facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fid,p,m,"",r["canonical_entity_key"],r.get("source_abbreviated_name",""),
             r.get("business_lineage_key",""),r.get("bridge_class",""),
             v,st,u,b,comparability_of(m),r.get("source_sheet",""),r.get("source_cell",""),r.get("source_file","")))
        n_comp+=1
    for m,uu,bb,zh in SCHEMA_METRICS:
        cur.execute("UPDATE company_facts SET metric_label=? WHERE metric_id=?",(zh,m))

    conn.commit()
    print(f"market_facts: {n_mkt}, company_facts: {n_comp}")
    conn.close()

    # ---------- QA ----------
    run_qa()

def run_qa():
    conn=sqlite3.connect(OUTDB)
    cur=conn.cursor()
    lines=[]
    lines.append("# 标准事实层 QA 报告")
    lines.append("")
    lines.append("- 构建时间：2026-08-06")
    lines.append(f"- 市场事实({cur.execute('select count(*) from market_facts').fetchone()[0]}) / 公司事实({cur.execute('select count(*) from company_facts').fetchone()[0]})")
    lines.append("")
    # 1) 期数与指标覆盖
    lines.append("## 1. 覆盖检查")
    per=cur.execute("select period,count(*) from market_facts group by period").fetchall()
    lines.append("**市场事实按期间：** "+"; ".join(f"{p}:{n}" for p,n in per))
    met_n=cur.execute("select count(distinct metric_id) from market_facts").fetchone()[0]
    met_c=cur.execute("select count(distinct metric_id) from company_facts").fetchone()[0]
    lines.append(f"- 市场去重指标 {met_n} / 公司去重指标 {met_c}（应均=18）")
    # 2) 缺失保持 NULL
    mis=cur.execute("select count(*) from company_facts where value_status='reported_missing'").fetchone()[0]
    num=cur.execute("select count(*) from company_facts where value_status='reported_numeric'").fetchone()[0]
    lines.append(f"## 2. 缺失纪律\n- reported_numeric {num} / reported_missing {mis}（缺值保 NULL，不补零）")
    # 3) 市场总额 vs 公司明细 reconciliation（2026Q1，取市场有值指标）
    lines.append("## 3. 市场总额 vs 公司明细 reconcile（2026Q1）")
    mlbs = dict(cur.execute("select metric_id, group_concat(distinct metric_label) from market_facts group by metric_id").fetchall())
    ordered = sorted(mlbs.keys())
    occ = 0
    c2 = sqlite3.connect(OUTDB); cur2 = c2.cursor()
    for m in ordered:
        mv = cur2.execute("select value from market_facts where period='2026Q1' and metric_id=?", (m,)).fetchone()
        if mv is None or mv[0] is None:
            continue
        cv = cur2.execute("""select coalesce(sum(value),0) from company_facts
                             where period='2026Q1' and metric_id=? and value_status='reported_numeric'""", (m,)).fetchone()[0]
        flag = "✓" if abs(float(mv[0])-float(cv)) < 1 else "⚠差异"
        lines.append(f"- {m}: 市场 {mv[0]:,.0f} | 公司和 {cv:,.0f} {flag}")
        occ += 1
    lines.append(f"- reconcile 覆盖指标数：{occ}")
    c2.close()
    # 4) 单位与 basis 登记
    lines.append("## 4. schema: unit / period_basis / comparability")
    for m,u,b,zh in SCHEMA_METRICS:
        lines.append(f"- {m}: {b} | {u} | {comparability_of(m)}")
    conn.close()
    (QADIR/"standard_fact_layer_qa_report.md").write_text("\n".join(lines),encoding="utf-8")
    print("QA 报告:", QADIR/"standard_fact_layer_qa_report.md")

if __name__=="__main__":
    main()
