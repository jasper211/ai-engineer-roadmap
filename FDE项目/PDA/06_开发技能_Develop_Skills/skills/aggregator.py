#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：围绕 issuing_entity 做多维聚合。

对应 流程设计.md L3-PDA-03。输出结构对齐阶段一原型看板 HTML 里内嵌的 DATA 对象
（entities/months/top_carriers/by_entity_*/cycle_avg/fin_by_entity），
这样 dashboard_generator 复用原型的 Chart.js 渲染逻辑不需要改一行 JS。
"""
import pandas as pd

TOP_CARRIER_N = 6


def _agg(group: pd.DataFrame) -> dict:
    return {
        "premium": float(group["premium"].sum()),
        "ape": float(group["ape"].sum()),
        "count": int(len(group)),
    }


def _by_entity_and(df: pd.DataFrame, sub_col: str) -> dict:
    """按 'entity|sub' 拼key的聚合，跟阶段一原型的key格式一致（JS里用split('|')解析）。"""
    out = {}
    for (entity, sub), group in df.groupby(["issuing_entity", sub_col], observed=True):
        out[f"{entity}|{sub}"] = _agg(group)
    return out


class Aggregator:
    """接收 cleaner 产出的清洗后 DataFrame，返回聚合结果 dict，不读写任何持久化状态。"""

    def aggregate(self, df: pd.DataFrame) -> dict:
        entities = sorted(df["issuing_entity"].unique().tolist())

        month = df["sign_date"].dt.strftime("%Y-%m")
        months = sorted(month.dropna().unique().tolist())
        df = df.assign(_month=month)

        carrier_totals = df.groupby("carrier_code")["premium"].sum().sort_values(ascending=False)
        top_carriers = carrier_totals.head(TOP_CARRIER_N).index.tolist()
        df = df.assign(
            _carrier_bucket=df["carrier_code"].where(df["carrier_code"].isin(top_carriers), "其他")
        )

        by_entity_all = {e: _agg(g) for e, g in df.groupby("issuing_entity", observed=True)}
        eff = df[df["policy_status_tier"] == "生效"]
        by_entity_effective = {e: _agg(g) for e, g in eff.groupby("issuing_entity", observed=True)}

        cycle_avg = {}
        for entity, g in df.groupby("issuing_entity", observed=True):
            both = g.dropna(subset=["sign_date", "issue_date"])
            if len(both):
                days = (both["issue_date"] - both["sign_date"]).dt.days
                cycle_avg[entity] = round(float(days.mean()), 1)

        fin_by_entity = {}
        for entity, g in df.groupby("issuing_entity", observed=True):
            fin_by_entity[entity] = [int((g["Is_Premium_Financing"] == 1).sum()), int(len(g))]

        return {
            "entities": entities,
            "months": months,
            "top_carriers": top_carriers,
            "by_entity_all": by_entity_all,
            "by_entity_effective": by_entity_effective,
            "by_entity_bcat": _by_entity_and(df, "business_category"),
            "by_entity_mkt": _by_entity_and(df, "market_segment"),
            "by_entity_prod": _by_entity_and(df, "product_category"),
            "by_entity_carrier": _by_entity_and(df, "_carrier_bucket"),
            "by_entity_cust": _by_entity_and(df, "customer_type"),
            "by_entity_status": _by_entity_and(df, "policy_status_tier"),
            "by_entity_month": _by_entity_and(df, "_month"),
            "by_entity_ccy": _by_entity_and(df, "currency_code"),
            "cycle_avg": cycle_avg,
            "fin_by_entity": fin_by_entity,
        }
