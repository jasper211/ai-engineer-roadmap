#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2025 provisional 公司事实层 QA
校验：
  1. 表内 reconcile：公司 sum == Market Total（Table L1 新造 / Table L3 有效）
  2. 与标准事实层 annual_facts(18指标) 的市场总额一致性（新造个人整付/年化）
  3. 跨年 certified(2024) vs provisional(2025) 公司级可选对比（schema-bridge 标注）
"""
import os, sqlite3
DB=os.path.join(os.path.dirname(__file__),"..","data","annual_provisional_company_2025.db")
conn=sqlite3.connect(DB); cur=conn.cursor()

def scope_sum(tbl, metric):
    r=cur.execute("SELECT SUM(value) FROM provisional_company_facts WHERE table_id=? AND metric_sem=? AND entity_scope='insurer'",(tbl,metric)).fetchone()
    return r[0] if r else 0
def scope_mt(tbl, metric):
    r=cur.execute("SELECT value FROM provisional_company_facts WHERE table_id=? AND metric_sem=? AND entity_scope='market_total'",(tbl,metric)).fetchone()
    return r[0] if r else None

print("=== 1. 表内 reconcile: 公司sum vs Market Total ===")
checks=[
 ("L1","nb_total_single_premium","hkd_thousand"),
 ("L1","nb_total_annualized_premium","hkd_thousand"),
 ("L3","if_total_policies","count"),
 ("L3","if_total_sums_assured","hkd_thousand"),
 ("L3","if_total_single_premium","hkd_thousand"),
 ("L3","if_total_non_single_premium","hkd_thousand"),
]
worst=0; fail=0
for tbl,metric,unit in checks:
    ss=scope_sum(tbl,metric); mv=scope_mt(tbl,metric)
    if mv is None: continue
    d=abs(ss-mv); worst=max(worst,d)
    tol=0.05 if unit=="count" else 1e-3
    ok = d<tol
    if not ok: fail+=1
    print(f"  {tbl}.{metric:34} sum={ss:,.3f} market={mv:,.3f} diff={d:.4g} {'OK' if ok else '<-- MISMATCH'}")
print(f"RESULT: {'PASS' if fail==0 else 'FAIL'} worst_diff={worst:.3g}")

print("\n=== 2. vs 标准事实层 annual_facts (市场总额) ===")
std=os.path.join(os.path.dirname(__file__),"..","..","生成_标准事实层_StandardFactLayer","data","standard_fact_layer_2023_2026Q1.db")
s2=sqlite3.connect(std); c2=s2.cursor()
def annual_metric(mid):
    r=c2.execute("SELECT value FROM annual_facts WHERE metric_id=?",(mid,)).fetchone()
    return r[0] if r else None
pairs=[
 ("nb_total_single_premium","NB_IND_TOTAL_SINGLE_PREMIUM"),
 ("nb_total_annualized_premium","NB_IND_TOTAL_ANNUALIZED_PREMIUM"),
]
for met,mid in pairs:
    ss=scope_sum("L1",met); mv=annual_metric(mid)
    d=abs(ss-mv) if mv is not None else None
    print(f"  L1.{met} (sum company) = {ss:,.3f}")
    print(f"    vs annual_facts.{mid} = {mv:,.3f}  diff={d}")
print("\n=== 3. 跨年 2024 certified vs 2025 provisional（NB 个人整付，schema 桥接）===")
ann=os.path.join(os.path.dirname(__file__),"..","..","生成_年度公司事实层_AnnualCompanyFactLayer","data","annual_company_fact_layer_2022_2024.db")
a=sqlite3.connect(ann); a2=a.cursor()
# 2024 certified: L16 individual life NB total single premium (公司)
r=a2.execute("SELECT SUM(value_raw) FROM company_facts WHERE report_year=2024 AND table_id='L16' AND metric_sem='premium_single' AND entity_scope='insurer'").fetchone()
cert24=r[0] if r else None
prov25=scope_sum("L1","nb_total_single_premium")
print(f"  2024 certified L16 individual NB single pref (sum company) = {cert24:,.3f}")
print(f"  2025 provisional L1 individual long-term NB single pref     = {prov25:,.3f}")
print(f"  YOY change = {(prov25-cert24)/cert24*100:.1f}%  (注意口令差异：2024 L16=個人壽險新造；2025 L1 總額=個人長期含相連年金，需 bridge)")
s2.close(); a.close(); conn.close()
print("\nQA DONE")
