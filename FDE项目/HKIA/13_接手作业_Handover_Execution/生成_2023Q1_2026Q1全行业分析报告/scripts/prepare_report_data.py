#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HKIA · 2023Q1→2026Q1 全行业分析报告 · 数据预处理
====================================================
从既有标准化资产抽取报告所需全部数据，汇总为单一 JSON，
供 HTML 生成器注入。遵循接手前口径纪律：
- provisional 标签如实携带；
- 缺值保持 null，绝不补零；
- 2026Q1 转移事件以 lineage 桥承接；
- 禁止跨期错比（Q1 不做年化增长）。

输入资产：
  HKIA_company_fact_layer_2023Q1_2026Q1_v0.1.xlsx（公司级，含计算值）
  04_normalized/quarterly_long/market_total_core_facts_2023Q1_2026Q1_v0.1.csv
  04_normalized/quarterly_long/core_metric_yoy_2023Q1_2026Q1_v0.1.csv

产出：
  report_data_2023_2026Q1.json
"""
import json
import re
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]          # 13_接手作业_Handover_Execution
VFRAME = BASE.parent / "12_分析框架验证_Validate_Framework"   # 数据所在
DATA = Path(__file__).resolve().parent / "data"
DATA.mkdir(exist_ok=True)

XLSX = VFRAME / "outputs" / "HKIA_company_fact_layer_2023Q1_2026Q1_v0.1.xlsx"
QRONG = VFRAME / "04_normalized" / "quarterly_long"
MARKET = QRONG / "market_total_core_facts_2023Q1_2026Q1_v0.1.csv"
YOY = QRONG / "core_metric_yoy_2023Q1_2026Q1_v0.1.csv"

OUT = DATA / "report_data_2023_2026Q1.json"

# 指标中文名与业务大类映射
BUSINESS_CLASS = {
    "个人业务": ["NB_IND_", "IF_IND_"],
    "团体业务": ["NB_GROUP_", "IF_GROUP_"],
    "退休计划": ["IF_RETIREMENT_", "RETIREMENT_"],
}

METRIC_LABEL = {
    "NB_IND_TOTAL_SINGLE_PREMIUM": "个人新造整付保费 (NOP)", 
    "NB_IND_TOTAL_ANNUALIZED_PREMIUM": "个人新造年度化保费 (APE)",
    "NB_GROUP_POLICIES": "团体新造保单数",
    "NB_GROUP_LIVES": "团体新造受保人数",
    "NB_GROUP_ANNUALIZED_PREMIUM": "团体新造年度化保费",
    "IF_IND_TOTAL_POLICIES": "个人有效保单数",
    "IF_IND_TOTAL_SUMS_ASSURED_OR_ANNUITIES": "个人有效保额/年金",
    "IF_IND_TOTAL_SINGLE_PREMIUM_RECEIVABLE": "个人有效整付保费",
    "IF_IND_TOTAL_NON_SINGLE_PREMIUM_RECEIVABLE": "个人有效非整付保费",
    "IF_GROUP_NON_RETIREMENT_POLICIES": "团体(非退休)有效保单数",
    "IF_GROUP_NON_RETIREMENT_LIVES": "团体(非退休)有效受保人数",
    "IF_GROUP_NON_RETIREMENT_NON_SINGLE_PREMIUM_RECEIVABLE": "团体(非退休)有效非整付保费",
    "IF_RETIREMENT_SCHEMES": "退休计划数量",
    "IF_RETIREMENT_ENDING_FUND_BALANCE": "退休计划期末基金余额",
    "IF_RETIREMENT_SINGLE_CONTRIBUTIONS": "退休计划单项供款",
    "IF_RETIREMENT_NON_SINGLE_CONTRIBUTIONS": "退休计划非单项供款",
}

PERIODS = ["2023Q1", "2024Q1", "2025Q1", "2026Q1"]


def hkd(v):
    """千港元 → 亿港元，便于阅读。"""
    return round(v / 1e6, 4) if v is not None else None


def pct(rate):
    return round(rate * 100, 2) if rate is not None else None


def load_company_facts():
    """公司事实层（含计算值）。"""
    df = pd.read_excel(XLSX, sheet_name="Company Facts")
    return df


def load_market():
    df = pd.read_csv(MARKET)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def load_yoy():
    df = pd.read_csv(YOY)
    return df


def build_market_section(market):
    """市场总量：三大类核心指标按期间。"""
    rows = {}
    for _, r in market.iterrows():
        key = r["metric_id"]
        if key not in rows:
            rows[key] = {}
        rows[key][r["period"]] = {
            "value": r["value"],
            "value_yi": hkd(r["value"]) if r["value"] is not None else None,
            "unit": r["unit"],
            "basis": r["period_basis"],
            "comparability": r["comparability"],
        }
    return rows


def build_yoy_section(yoy):
    """每对期间、每指标同比。"""
    out = {}
    for _, r in yoy.iterrows():
        key = f"{r['from_period']}→{r['to_period']}|{r['metric_id']}"
        out[key] = {
            "from_period": r["from_period"],
            "to_period": r["to_period"],
            "metric_id": r["metric_id"],
            "prior_value": r["prior_value"] if pd.notna(r["prior_value"]) else None,
            "current_value": r["current_value"] if pd.notna(r["current_value"]) else None,
            "absolute_change": r["absolute_change"] if pd.notna(r["absolute_change"]) else None,
            "growth_rate": r["growth_rate"] if pd.notna(r["growth_rate"]) else None,
            "growth_rate_pct": pct(r["growth_rate"]) if pd.notna(r["growth_rate"]) else None,
            "rate_status": r["rate_status"],
            "interpretation_status": r["interpretation_status"],
        }
    return out


def build_company_rankings(xlsx):
    """解析公司排名 sheet（data_only 取计算值）。"""
    wb = pd.ExcelFile(XLSX)
    sheets = [s for s in wb.sheet_names if "Ranking" in s]
    rankings = []
    for s in sheets:
        df = pd.read_excel(XLSX, sheet_name=s, header=None)
        # 找 metric 标题行（含 metric_id 的行）
        metric = None
        for idx, row in df.iterrows():
            c0 = str(row[0]) if pd.notna(row[0]) else ""
            if c0.startswith("rank") or c0.strip() == "rank":
                header_idx = idx
                metric = metric_from_above(df, idx)
                cols = {j: str(row[j]).strip() for j in range(len(row))}

                # 收集数据行
                j = idx + 1
                while j < len(df):
                    val0 = df.iloc[j][0]
                    if pd.isna(val0) or str(val0).strip() == "":
                        break
                    rec = {
                        "metric": metric,
                        "rank": df.iloc[j][0],
                        "entity_key": df.iloc[j][1],
                        "entity_name": df.iloc[j][2],
                        "current_value": df.iloc[j][3] if pd.notna(df.iloc[j][3]) else None,
                        "market_share": df.iloc[j][4] if pd.notna(df.iloc[j][4]) else None,
                        "prior_value": df.iloc[j][5] if pd.notna(df.iloc[j][5]) else None,
                        "growth": df.iloc[j][6] if pd.notna(df.iloc[j][6]) else None,
                        "gate": df.iloc[j][7] if j + 0 < len(df.columns) and pd.notna(df.iloc[j][7]) else None,
                    }
                    rankings.append(rec)
                    j += 1
    return rankings


def metric_from_above(df, header_idx):
    """向上找最近的 metric 标题单元格。"""
    for idx in range(header_idx - 1, max(header_idx - 3, -1), -1):
        for c in range(len(df.columns)):
            v = df.iloc[idx][c]
            if pd.notna(v) and re.search(r"NB_|IF_|metric", str(v)):
                m = re.search(r"(NB_[A-Z_]+|IF_[A-Z_]+|RETIREMENT_[A-Z_]+)", str(v))
                if m:
                    return m.group(1)
    return "unknown"


def build_increment(xlsx):
    wb = pd.ExcelFile(XLSX)
    sheets = [s for s in wb.sheet_names if "Contribution" in s]
    increments = []
    for s in sheets:
        df = pd.read_excel(XLSX, sheet_name=s, header=None)
        for idx, row in df.iterrows():
            c0 = str(row[0]) if pd.notna(row[0]) else ""
            if c0.strip() == "rank":
                metric = metric_from_above(df, idx)
                j = idx + 1
                while j < len(df):
                    v0 = df.iloc[j][0]
                    if pd.isna(v0) or str(v0).strip() == "":
                        break
                    increments.append({
                        "metric": metric,
                        "rank": df.iloc[j][0],
                        "entity_key": df.iloc[j][1],
                        "entity_name": df.iloc[j][2],
                        "prior_value": df.iloc[j][3] if pd.notna(df.iloc[j][3]) else None,
                        "current_value": df.iloc[j][4] if pd.notna(df.iloc[j][4]) else None,
                        "absolute_change": df.iloc[j][5] if pd.notna(df.iloc[j][5]) else None,
                        "market_change": df.iloc[j][6] if pd.notna(df.iloc[j][6]) else None,
                        "contribution": df.iloc[j][7] if pd.notna(df.iloc[j][7]) else None,
                        "gate": df.iloc[j][8] if j + 0 < len(df.columns) and pd.notna(df.iloc[j][8]) else None,
                    })
                    j += 1
    return increments


def build_identity(xlsx):
    wb = pd.ExcelFile(XLSX)
    if "Identity Bridge" not in wb.sheet_names:
        return []
    df = pd.read_excel(XLSX, sheet_name="Identity Bridge", header=0)
    return df.head(20).to_dict("records")


def main():
    print("加载市场核心事实...")
    market = load_market()
    yoy = load_yoy()

    print("构建市场总量...")
    market_section = build_market_section(market)

    print("构建同比...")
    yoy_section = build_yoy_section(yoy)

    print("解析公司排名与增量贡献（计算值）...")
    rankings = build_company_rankings(XLSX)
    increments = build_increment(XLSX)
    identity = build_identity(XLSX)

    # 汇总统计
    summary = {
        "periods": PERIODS,
        "market_metrics_count": len(market_section),
        "ranking_rows": len(rankings),
        "increment_rows": len(increments),
        "identity_rows": len(identity),
    }

    payload = {
        "generated_at": "2026-08-05",
        "window": {"start": "2023Q1", "end": "2026Q1", "title": "香港长期保险 2023Q1→2026Q1"},
        "summary": summary,
        "business_class_map": {
            k: v for k, v in {
                "个人业务": ["个人新造整付/年度化保费", "个人有效保费/保单/保额"],
                "团体业务": ["团体新造保单/受保人数/年度化保费", "团体(非退休)有效保单/受保人数/非整付保费"],
                "退休计划": ["退休计划数量", "期末基金余额", "单项/非单项供款"],
            }.items()
        },
        "metric_label": METRIC_LABEL,
        "market": market_section,
        "yoy": yoy_section,
        "rankings": rankings,
        "increments": increments,
        "identity": identity,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"已写入 {OUT}")
    print("汇总:", summary)


if __name__ == "__main__":
    main()
