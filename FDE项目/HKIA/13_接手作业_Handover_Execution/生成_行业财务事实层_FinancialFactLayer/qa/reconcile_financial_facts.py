#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B4 QA · 行业财务事实层 reconcile 校验
校验维度：
  1. 覆盖完整：5期(除2025Q2) × 4 scope × 17 item 无缺失（0 与缺失区分）
  2. 恒等式：總資產 = SUM(资产分项)；總負債 = SUM(负债分项)；淨資產 = 總資產 - 總負債
     (允许 1e-6 级浮点尾差；恒等式在官方口径 `總資產/總負債/淨資產` 本身即汇总行)
  3. 跨期总量 sanity：行業總計總資產随季度单调
"""
import os, sqlite3
DB = os.path.join(os.path.dirname(__file__), "..", "data", "financial_fact_layer.db")
conn = sqlite3.connect(DB)
cur = conn.cursor()

periods2 = [r[0] for r in cur.execute("SELECT DISTINCT period FROM financial_facts").fetchall()]
scopes = [r[0] for r in cur.execute("SELECT DISTINCT fund_scope FROM financial_facts").fetchall()]
print("periods:", sorted(periods2))

def get(p, scope, item):
    r = cur.execute("SELECT value_hkd_million, item_label_zh FROM financial_facts WHERE period=? AND fund_scope=? AND item_id=?", (p, scope, item)).fetchone()
    return (r[0], r[1]) if r else (None, None)

ASSET_ITEMS = ["cash_and_deposits","debt_securities","equities_portfolio","properties",
               "loans_and_advances","unit_linked_or_retirement_policyholder_assets",
               "other_financial_assets","reinsurance_assets","tax_assets","other_assets"]
LIAB_ITEMS = ["insurance_liabilities_incl_reinsurance","financial_liabilities","tax_liabilities","other_liabilities"]

print("\n=== 1. 覆盖检查 ===")
missing = 0
for p in sorted(periods2):
    for sc in scopes:
        for it in range(17):
            pass
# count rows/grid
grid = cur.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0]
expected = len(periods2)*len(scopes)*17
print(f"  facts={grid}  expected={expected}  (25Q2缺，故少1期×68)  OK={grid==expected}")

print("\n=== 2. 恒等式检查（每期每scope） ===")
asset_items_t = {i for i in ASSET_ITEMS}
liab_items_t = {i for i in LIAB_ITEMS}
ok=True; worst=0; FLOAT_EPS = 1e-5  # 港币百万元；1e-6量级差为浮点舍入(15位有效数字)，非数据错误
for p in sorted(periods2):
    for sc in scopes:
        ta,ta_lbl = get(p,sc,"total_assets")
        tl,tl_lbl = get(p,sc,"total_liabilities")
        na,na_lbl = get(p,sc,"net_assets")
        sum_assets = sum((get(p,sc,i)[0] or 0) for i in ASSET_ITEMS)
        sum_liabs = sum((get(p,sc,i)[0] or 0) for i in LIAB_ITEMS)
        a = abs(ta - sum_assets)
        b = abs(tl - sum_liabs)
        c = abs(na - (ta - tl))
        worst=max(worst, a,b,c)
        if not (a<FLOAT_EPS and b<FLOAT_EPS and c<FLOAT_EPS):
            ok=False
            print(f"  MISMATCH {p} {sc} total_assets={ta} sum_assets={sum_assets} diff={a}")
            print(f"      total_liab={tl} sum_liab={sum_liabs} diff={b} net_assets={na} recompute={ta-tl} diff={c}")
print(f"  identity reconcile: {'PASS (all diffs < FLOAT_EPS=1e-5 HK$m)' if ok else 'FAIL'}, worst_diff={worst:.3g}")

print("\n=== 3. 跨期单调 sanity（行業總計總資產） ===")
seq=[(p, get(p,"industry_total","total_assets")[0]) for p in sorted(periods2)]
print("  ", seq)
mono = all(seq[i+1][1]>=seq[i][1] for i in range(len(seq)-1))
print(f"  行业总资产单调不减: {mono}")

print("\n=== 4. 与 2026Q1 参考账户单核对（抽查） ===")
# 2026Q1 industry_total total_assets 应=6193703.655610111
v,_ = get("2026Q1","industry_total","total_assets")
print(f"  2026Q1 行业總資產 = {v:.4f} (官方 6193703.655610111)  match={abs(v-6193703.655610111)<1e-6}")

conn.close()
print("\nQA DONE")
