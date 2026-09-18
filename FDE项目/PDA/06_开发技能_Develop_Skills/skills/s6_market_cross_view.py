#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：复刻《业绩分析报表》S6_市场与交叉视角 全部6个板块×2指标（A-F各含APE/件数，共12张子表）。

对应 01_初始化项目_Initialize_Project/S6_市场与交叉视角_反推标准_v0.1.md。S6是纯交叉透视表，
没有新规则——完全复用S2(SEGMENT_GROUPS+MGA拆分KA标签)和S4(CARRIER_SHORT_NAME)的既有组件。
"""
import pandas as pd

from skills.s2_business_view import SEGMENT_GROUPS, UNAPPROVED_STATUSES
from skills.s4_product_view import CARRIER_SHORT_NAME


def _mga_split_ka(df: pd.DataFrame) -> pd.Series:
    is_mga = df["segment_code"] == "MGA业务"
    return df["key_account"].where(~is_mga, df["key_account"] + "(MGA)")


class S6MarketCrossViewBuilder:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def _population(self, status_mode: str) -> pd.DataFrame:
        df = self.df
        if status_mode == "批核":
            return df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)]
        if status_mode == "未批核":
            return df[df["policy_status"].isin(UNAPPROVED_STATUSES)]
        if status_mode == "待签":
            return df[df["policy_status"] == "排期"]
        raise ValueError(status_mode)

    def _cross_table(self, status_mode: str, row_dim: str) -> list:
        """row_dim: 'ka'(按KA,含MGA拆分) 或 'carrier'(按保司简称)。列固定是SEGMENT_GROUPS的8个业务细分+合计。"""
        pop = self._population(status_mode).copy()
        if row_dim == "ka":
            pop["_row"] = _mga_split_ka(pop)
            row_label = "KA"
        elif row_dim == "carrier":
            pop["_row"] = pop["carrier_code"].map(CARRIER_SHORT_NAME).fillna(pop["carrier_code"])
            row_label = "保司"
        else:
            raise ValueError(row_dim)

        rows = []
        for row_val, g_row in pop.groupby("_row", observed=True):
            row = {row_label: row_val}
            total = 0.0
            for seg_label, codes in SEGMENT_GROUPS.items():
                v = float(g_row.loc[g_row["segment_code"].isin(codes), "ape"].sum())
                row[seg_label] = v
                total += v
            row["合计"] = total
            if total > 0:  # 全0行(该KA/保司在此status下完全没有匹配记录)不出现在报表里
                rows.append(row)
        rows.sort(key=lambda r: r["合计"], reverse=True)

        total_row = {row_label: "合计"}
        for seg_label in list(SEGMENT_GROUPS) + ["合计"]:
            total_row[seg_label] = sum(r[seg_label] for r in rows)
        rows.append(total_row)
        return rows

    def _cross_table_count(self, status_mode: str, row_dim: str) -> list:
        pop = self._population(status_mode).copy()
        if row_dim == "ka":
            pop["_row"] = _mga_split_ka(pop)
            row_label = "KA"
        else:
            pop["_row"] = pop["carrier_code"].map(CARRIER_SHORT_NAME).fillna(pop["carrier_code"])
            row_label = "保司"

        rows = []
        for row_val, g_row in pop.groupby("_row", observed=True):
            row = {row_label: row_val}
            total = 0
            for seg_label, codes in SEGMENT_GROUPS.items():
                v = int(g_row["segment_code"].isin(codes).sum())
                row[seg_label] = v
                total += v
            row["合计"] = total
            if total > 0:
                rows.append(row)
        rows.sort(key=lambda r: r["合计"], reverse=True)

        total_row = {row_label: "合计"}
        for seg_label in list(SEGMENT_GROUPS) + ["合计"]:
            total_row[seg_label] = sum(r[seg_label] for r in rows)
        rows.append(total_row)
        return rows

    def build_all(self) -> dict:
        result = {}
        for code, status_mode in [("A", "批核"), ("B", "未批核"), ("C", "待签")]:
            result[f"{code}-APE"] = self._cross_table(status_mode, "ka")
            result[f"{code}-件数"] = self._cross_table_count(status_mode, "ka")
        for code, status_mode in [("D", "批核"), ("E", "未批核"), ("F", "待签")]:
            result[f"{code}-APE"] = self._cross_table(status_mode, "carrier")
            result[f"{code}-件数"] = self._cross_table_count(status_mode, "carrier")
        return result
