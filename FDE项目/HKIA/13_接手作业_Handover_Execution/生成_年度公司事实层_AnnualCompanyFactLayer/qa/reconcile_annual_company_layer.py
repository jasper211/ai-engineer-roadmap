#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
年度公司事实层 QA (2022/2023/2024)
校验：
  1. 每表 internal：公司行 sum == 该表 Market Total（同 metric）
  2. 新造成分：L14+L15 = L16
  3. inforce 成分 vs L13（schema-aware L11 路由）：
     - pre-RBC (2022/2023)：L11 贡献 policy_count + contribution；L13=Σ(L8,9,10,12).metric + L11.*
     - RBC (2024)：L11 贡献 scheme_count + contribution；L13=Σ(L8,9,10,12).metric + L11.*
     - current_estimate/net_liabilities：Σ(L8..12) 直接
容差：保单数/人数/scheme 精确(≤0.05)；金额 1e-3 (HKD_thousand)。
"""
import os, sqlite3
DB=os.path.join(os.path.dirname(__file__),"..","data","annual_company_fact_layer_2022_2024.db")
conn=sqlite3.connect(DB); cur=conn.cursor()

def mt(year,table,metric):
    r=cur.execute("SELECT value_raw FROM company_facts WHERE report_year=? AND table_id=? AND metric_sem=? AND entity_scope='market_total'",(year,table,metric)).fetchone()
    return r[0] if r else None
def sum_ins(year,table,metric):
    r=cur.execute("SELECT SUM(value_raw) FROM company_facts WHERE report_year=? AND table_id=? AND metric_sem=? AND entity_scope='insurer' AND value_raw IS NOT NULL",(year,table,metric)).fetchone()
    return r[0] if r else None

YEARS=[2022,2023,2024]
print("=== 1. 每表 internal: 公司sum vs Market Total ===")
worst=0; fail=0; checked=0
for year in YEARS:
    for tbl in ["L8","L9","L10","L11","L12","L13","L14","L15","L16","L17","L18","L19"]:
        for metric in ["policy_count","sums_assured","premium_single","premium_annual","current_estimate","net_liabilities","premium","lives","scheme_count","contribution_single","contribution_annual"]:
            mv=mt(year,tbl,metric); sv=sum_ins(year,tbl,metric)
            if mv is None or sv is None: continue
            checked+=1; d=abs(mv-sv)
            tol=1e-3 if metric not in ("policy_count","lives","scheme_count") else 0.05
            if d>worst: worst=d
            if d>tol:
                fail+=1
                if fail<=25: print(f"{year:5}{tbl:6}{metric:24}{mv:16.3f}{sv:16.3f}{d:10.4f}")
print(f"checked={checked} fails={fail} worst_diff={worst:.3g}")
print("RESULT:", "PASS" if fail==0 else "HAS-MISMATCH")

print("\n=== 2. 新造成分 L14+L15 vs L16 ===")
for year in YEARS:
    for metric in ["policy_count","premium_single","premium_annual"]:
        s14=sum_ins(year,"L14",metric); s15=sum_ins(year,"L15",metric); s16=sum_ins(year,"L16",metric)
        if s14 is None or s15 is None or s16 is None: continue
        d=abs((s14+s15)-s16); note="OK" if d<1e-3 else "<-- MISMATCH"
        print(f"  {year} {metric:16}: L14+L15={s14+s15:.3f} L16={s16:.3f} diff={d:.4f} {note}")

print("\n=== 3. inforce 成分 vs L13（schema-aware L11 路由） ===")
print("   pre-RBC(2022/2023) L11→policy_count+contribution；RBC(2024) L11→scheme_count+contribution")
for year in YEARS:
    print(f"  -- {year} --")
    route="scheme_count" if year==2024 else "policy_count"
    for metric, l11m in [("policy_count",route),("premium_single","contribution_single"),("premium_annual","contribution_annual")]:
        sbase=sum((sum_ins(year,t,metric) or 0) for t in ["L8","L9","L10","L12"])
        extra=sum_ins(year,"L11",l11m) or 0
        comp=sbase+extra; s13=sum_ins(year,"L13",metric)
        if s13 is None: continue
        d=abs(comp-s13); note="OK" if d<1e-3 else "<-- MISMATCH"
        print(f"     Σ(L8,9,10,12).{metric}+L11.{l11m}={comp:,.3f}  L13={s13:,.3f} diff={d:.4f} {note}")
    # liability type: 2024 current_estimate, 2022/2023 net_liabilities
    liab="current_estimate" if year==2024 else "net_liabilities"
    sbase=sum((sum_ins(year,t,liab) or 0) for t in ["L8","L9","L10","L11","L12"])
    s13=sum_ins(year,"L13",liab)
    if s13 is not None:
        d=abs(sbase-s13); note="OK" if d<1e-3 else "<-- MISMATCH"
        print(f"     Σ(L8..12).{liab}={sbase:,.3f}  L13={s13:,.3f} diff={d:.4f} {note}")
conn.close()
print("\nQA DONE")
