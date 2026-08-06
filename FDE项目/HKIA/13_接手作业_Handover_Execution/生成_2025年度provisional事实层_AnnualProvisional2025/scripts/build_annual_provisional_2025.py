#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_annual_provisional_2025.py
===============================
B1 · 2025 全年 provisional 事实层构建
从 2025Q4（January to December 2025）资产抽取 18 个核心市场指标的市场总额，
写入 "annual_facts" 层并标注 period_layer=annual_provisional。

依据：
  - analysis_window_2023_2026Q1_v0.1.yaml (annual_provisional: 2025, labeling_required: provisional)
  - quarterly_long_2023Q1_2026Q1_asset_manifest_v0.1.yaml (2025Q4 角色=latest_complete_calendar_year_view)
  - quarterly_long_metric_comparability_v0.1.yaml (18 core metrics / unit / period_basis / comparability)

纪律：
  - 只读 2025Q4 原始资产（不修改）。
  - 事实标记 provisional，禁止当 certified 年度统计。
  - 保留期间/指标ID/原始值/单位/流量存量/可比等级/来源locator。

产物：
  - data/annual_facts_2025_provisional.csv
  - data/annual_provisional_2025.csv          (轻量展示，含 period_layer)
  附 QC：18 指标完整性 + 体量合理性核对。
"""
import os
import sqlite3
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(os.path.dirname(os.path.dirname(BASE)),
                   "12_分析框架验证_Validate_Framework",
                   "01_sources", "raw", "SRC-REG-IA-LTQ", "2025Q4", "4q25long.xlsx")
DB  = os.path.join(os.path.dirname(BASE),
                   "生成_标准事实层_StandardFactLayer", "data",
                   "standard_fact_layer_2023_2026Q1.db")

PERIOD = "2025"
SOURCE_ASSET = "SRC-REG-IA-LTQ-2025Q4/4q25long.xlsx"
CERTIFICATION = "provisional"
LAYER = "annual_provisional"


def col_letter(idx):
    # 0-based index -> excel column letter
    s = ""
    n = idx + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def main():
    xls = pd.ExcelFile(SRC)

    roi = pd.read_excel(xls, sheet_name="Table L1", header=None)
    rgg = pd.read_excel(xls, sheet_name="Table L2", header=None)
    rif = pd.read_excel(xls, sheet_name="Table L3", header=None)
    rgf = pd.read_excel(xls, sheet_name="Table L4", header=None)

    # 定位 "Market Total" 行（按列0文本匹配，不依赖硬编码行号）
    def total_row(df):
        for i in range(len(df)):
            v = df.iloc[i, 0]
            if isinstance(v, str) and v.strip().lower() == "market total":
                return i
        raise RuntimeError("Market Total row not found")

    rl1 = roi.iloc[total_row(roi)]
    rl2 = rgg.iloc[total_row(rgg)]
    rl3 = rif.iloc[total_row(rif)]
    rl4 = rgf.iloc[total_row(rgf)]

    # 18 个核心指标：sheet + 列 + period_basis
    # 依据 quarterly_long_metric_comparability_v0.1.yaml (unit/comparability)
    S = {
        # ---- 新造 个人 (Table L1) ----
        "NB_IND_TOTAL_SINGLE_PREMIUM": dict(row=rl1, col=8,  unit="HKD_thousand",
            basis="flow_during_period", comp="comparable_with_schema_bridge", sheet="Table L1"),
        "NB_IND_TOTAL_ANNUALIZED_PREMIUM": dict(row=rl1, col=9, unit="HKD_thousand",
            basis="flow_during_period", comp="comparable_with_schema_bridge", sheet="Table L1"),
        # ---- 新造 团体 (Table L2) ----
        "NB_GROUP_POLICIES": dict(row=rl2, col=2, unit="count",
            basis="flow_during_period", comp="directly_comparable_by_label", sheet="Table L2"),
        "NB_GROUP_LIVES": dict(row=rl2, col=3, unit="count",
            basis="flow_during_period", comp="directly_comparable_by_label_with_outlier_review", sheet="Table L2"),
        "NB_GROUP_SINGLE_PREMIUM": dict(row=rl2, col=4, unit="HKD_thousand",
            basis="flow_during_period", comp="directly_comparable_by_label", sheet="Table L2"),
        "NB_GROUP_ANNUALIZED_PREMIUM": dict(row=rl2, col=5, unit="HKD_thousand",
            basis="flow_during_period", comp="directly_comparable_by_label", sheet="Table L2"),
        # ---- 有效 个人 (Table L3) ----
        "IF_IND_TOTAL_POLICIES": dict(row=rl3, col=14, unit="count",
            basis="stock_at_period_end", comp="comparable_with_schema_bridge", sheet="Table L3"),
        "IF_IND_TOTAL_SUMS_ASSURED_OR_ANNUITIES": dict(row=rl3, col=15, unit="HKD_thousand",
            basis="stock_at_period_end", comp="comparable_with_schema_bridge", sheet="Table L3"),
        "IF_IND_TOTAL_SINGLE_PREMIUM_RECEIVABLE": dict(row=rl3, col=16, unit="HKD_thousand",
            basis="flow_during_period", comp="comparable_with_schema_bridge", sheet="Table L3"),
        "IF_IND_TOTAL_NON_SINGLE_PREMIUM_RECEIVABLE": dict(row=rl3, col=17, unit="HKD_thousand",
            basis="flow_during_period", comp="comparable_with_schema_bridge", sheet="Table L3"),
        # ---- 有效 团体非退休 (Table L4) ----
        "IF_GROUP_NON_RETIREMENT_POLICIES": dict(row=rl4, col=2, unit="count",
            basis="stock_at_period_end", comp="directly_comparable_by_label", sheet="Table L4"),
        "IF_GROUP_NON_RETIREMENT_LIVES": dict(row=rl4, col=3, unit="count",
            basis="stock_at_period_end", comp="directly_comparable_by_label", sheet="Table L4"),
        "IF_GROUP_NON_RETIREMENT_SINGLE_PREMIUM_RECEIVABLE": dict(row=rl4, col=4, unit="HKD_thousand",
            basis="flow_during_period", comp="directly_comparable_by_label", sheet="Table L4"),
        "IF_GROUP_NON_RETIREMENT_NON_SINGLE_PREMIUM_RECEIVABLE": dict(row=rl4, col=5, unit="HKD_thousand",
            basis="flow_during_period", comp="directly_comparable_by_label", sheet="Table L4"),
        # ---- 退休计划 (Table L4) ----
        "IF_RETIREMENT_SCHEMES": dict(row=rl4, col=6, unit="count",
            basis="stock_at_period_end", comp="directly_comparable_by_label", sheet="Table L4"),
        "IF_RETIREMENT_ENDING_FUND_BALANCE": dict(row=rl4, col=7, unit="HKD_thousand",
            basis="stock_at_period_end", comp="directly_comparable_by_label", sheet="Table L4"),
        "IF_RETIREMENT_SINGLE_CONTRIBUTIONS": dict(row=rl4, col=8, unit="HKD_thousand",
            basis="flow_during_period", comp="directly_comparable_by_label", sheet="Table L4"),
        "IF_RETIREMENT_NON_SINGLE_CONTRIBUTIONS": dict(row=rl4, col=9, unit="HKD_thousand",
            basis="flow_during_period", comp="directly_comparable_by_label", sheet="Table L4"),
    }

    rows = []
    missing = []
    for metric_id, m in S.items():
        val = m["row"][m["col"]]
        if pd.isna(val):
            missing.append(metric_id)
            val = None
        sheet = m["sheet"]
        rows.append(dict(
            period=PERIOD, period_layer=LAYER, period_label=f"January to December {PERIOD}",
            certification=CERTIFICATION, metric_id=metric_id,
            value=val, unit=m["unit"], period_basis=m["basis"], comparability=m["comp"],
            source_asset=SOURCE_ASSET, source_sheet=sheet,
            source_locator=f"{sheet}!{col_letter(m['col'])}{m['row'].name + 1}",
        ))

    df = pd.DataFrame(rows)

    # ---- 展示 CSV ----
    out_csv = os.path.join(BASE, "data", "annual_facts_2025_provisional.csv")
    df.to_csv(out_csv, index=False)

    # ---- 写入标准事实层 DB（新增 annual_facts 表，保留既有表）----
    if os.path.exists(DB):
        conn = sqlite3.connect(DB)
        df.to_sql("annual_facts", conn, if_exists="replace", index=False)
        conn.commit()
    else:
        conn = sqlite3.connect(os.path.join(BASE, "data", "annual_provisional_2025.db"))
        df.to_sql("annual_facts", conn, if_exists="replace", index=False)
        conn.commit()
    conn.close()

    # ---- QC ----
    print(f"== B1 2025 全年 provisional 事实层 ==")
    print(f" 指标数: {len(df)} / 18 （缺失: {missing or '无'}）")
    print(f" 输出CSV: {out_csv}")
    print(f" 目标DB: {DB if os.path.exists(DB) else 'annual_provisional_2025.db'}")
    # 体量合理性核对（亿港元）
    print("\n 亿元级关键指标（HKD_thousand -> 亿港元 /1e5, 保留2位）:")
    for mid in ["NB_IND_TOTAL_SINGLE_PREMIUM", "NB_IND_TOTAL_ANNUALIZED_PREMIUM",
                "IF_IND_TOTAL_SINGLE_PREMIUM_RECEIVABLE", "IF_IND_TOTAL_NON_SINGLE_PREMIUM_RECEIVABLE"]:
        r = df[df.metric_id == mid]
        if len(r):
            print(f"  {mid:<42} {r.iloc[0]['value']:.3f} (千港元) ≈ {r.iloc[0]['value']/1e5:.2f} 亿港元")
    return df


if __name__ == "__main__":
    main()
