#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：复刻《业绩分析报表》S7_合规端视角 全部6个板块（A/B-D×APE/件数/E/F）。

对应 01_初始化项目_Initialize_Project/S7_合规端视角_反推标准_v0.1.md。三条S7专属规则：
1. A节的distinct计数列(保险公司数/产品数/KA数/TR数)统计范围是"批核∪未批核∪待签"三部分并集，
   不是全量也不是单一状态。
2. E节"牌照"简称是issuing_entity前8个字——跟S5-G/H的前4字不同，每张表的截断长度要单独验证。
3. F节"业务线数"用SEGMENT_GROUPS折算后的distinct(MGA业务算进同行经代)，不是原始segment_code
   的distinct；且F节状态过滤只排除"排期"，比其他表的"流失类"排除范围更宽松。
"""
import pandas as pd

from skills.s2_business_view import SEGMENT_GROUPS, UNAPPROVED_STATUSES
from skills.s4_product_view import CARRIER_SHORT_NAME

_SEGMENT_CODE_TO_LABEL = {code: label for label, codes in SEGMENT_GROUPS.items() for code in codes}


class S7ComplianceViewBuilder:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def _stage_pop(self, df: pd.DataFrame, stage: str) -> pd.DataFrame:
        if stage == "批核":
            return df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)]
        if stage == "未批核":
            return df[df["policy_status"].isin(UNAPPROVED_STATUSES)]
        if stage == "待签":
            return df[df["policy_status"] == "排期"]
        raise ValueError(stage)

    # ---- A. 牌照合规概览 ----
    def section_a(self) -> list:
        df = self.df
        rows = []
        totals = {"2026批核APE": 0.0, "批核件数": 0, "未批核APE": 0.0, "未批核件数": 0,
                  "待签APE": 0.0, "待签件数": 0}
        for entity in df["issuing_entity"].unique():
            g = df[df["issuing_entity"] == entity]
            b26 = self._stage_pop(g, "批核")
            unapp = self._stage_pop(g, "未批核")
            dq = self._stage_pop(g, "待签")
            combo = pd.concat([b26, unapp, dq])
            row = {
                "签单供应商": entity,
                "2026批核APE": float(b26["ape"].sum()), "批核件数": int(len(b26)),
                "未批核APE": float(unapp["ape"].sum()), "未批核件数": int(len(unapp)),
                "待签APE": float(dq["ape"].sum()), "待签件数": int(len(dq)),
                "保险公司数": int(combo["carrier_code"].nunique()),
                "产品数": int(combo["product_id"].nunique()),
                "KA数": int(combo["key_account"].nunique()),
                "TR数": int(combo["tr_name"].nunique()),
            }
            row["合计APE"] = row["2026批核APE"] + row["未批核APE"] + row["待签APE"]
            row["合计件数"] = row["批核件数"] + row["未批核件数"] + row["待签件数"]
            for k in totals:
                totals[k] += row[k]
            rows.append(row)
        rows.sort(key=lambda r: r["合计APE"], reverse=True)
        total_row = {"签单供应商": "合计", **totals,
                     "保险公司数": "-", "产品数": "-", "KA数": "-", "TR数": "-"}
        total_row["合计APE"] = totals["2026批核APE"] + totals["未批核APE"] + totals["待签APE"]
        total_row["合计件数"] = totals["批核件数"] + totals["未批核件数"] + totals["待签件数"]
        rows.append(total_row)
        return rows

    # ---- B/C/D. 牌照×业务细分 ----
    def _entity_segment_cross(self, stage: str, metric: str) -> list:
        pop = self._stage_pop(self.df, stage)
        rows = []
        for entity in self.df["issuing_entity"].unique():
            g_entity = pop[pop["issuing_entity"] == entity]
            row = {"签单供应商": entity}
            total = 0.0 if metric == "ape" else 0
            for label, codes in SEGMENT_GROUPS.items():
                g = g_entity[g_entity["segment_code"].isin(codes)]
                v = float(g["ape"].sum()) if metric == "ape" else int(len(g))
                row[label] = v
                total += v
            row["合计"] = total
            rows.append(row)
        total_row = {"签单供应商": "合计"}
        for label in list(SEGMENT_GROUPS) + ["合计"]:
            total_row[label] = sum(r[label] for r in rows)
        rows.append(total_row)
        return rows

    def section_b_ape(self):
        return self._entity_segment_cross("批核", "ape")

    def section_b_count(self):
        return self._entity_segment_cross("批核", "count")

    def section_c_ape(self):
        return self._entity_segment_cross("未批核", "ape")

    def section_c_count(self):
        return self._entity_segment_cross("未批核", "count")

    def section_d_ape(self):
        return self._entity_segment_cross("待签", "ape")

    def section_d_count(self):
        return self._entity_segment_cross("待签", "count")

    # ---- E. 签批时效异常预警（明细列表，status=生效+issue_year=2026+TAT>60天） ----
    def section_e(self) -> list:
        df = self._stage_pop(self.df, "批核").copy()
        df["_tat"] = (df["issue_date"] - df["sign_date"]).dt.days
        warn = df[df["_tat"] > 60].sort_values("_tat", ascending=False)
        rows = []
        for _, r in warn.iterrows():
            rows.append({
                "保单号": r["policy_no"], "签单日": r["sign_date"].strftime("%Y-%m-%d"),
                "批核日": r["issue_date"].strftime("%Y-%m-%d"), "时效(天)": int(r["_tat"]),
                "牌照": r["issuing_entity"][:8], "KA": r["key_account"],
                "保司": CARRIER_SHORT_NAME.get(r["carrier_code"], r["carrier_code"]),
                "产品": r["product_id"], "年期": r["premium_term"], "APE": float(r["ape"]),
                "状态": r["policy_status"],
            })
        return rows

    # ---- F. TR维度人效-2026签单（仅排除排期，比"流失类"更宽松） ----
    def section_f(self) -> list:
        df = self.df
        sub = df[(df["sign_date"].dt.year == 2026) & (df["policy_status"] != "排期")].copy()
        sub["_seg_label"] = sub["segment_code"].map(_SEGMENT_CODE_TO_LABEL)
        rows = []
        for tr, g in sub.groupby("tr_name", observed=True):
            count = len(g)
            ape = float(g["ape"].sum())
            rows.append({
                "TR": tr, "APE": ape, "件数": count, "件均APE": ape / count if count else 0.0,
                "服务KA数": int(g["key_account"].nunique()), "业务线数": int(g["_seg_label"].nunique()),
            })
        rows.sort(key=lambda r: r["APE"], reverse=True)
        return rows

    def build_all(self) -> dict:
        return {
            "A": self.section_a(),
            "B_ape": self.section_b_ape(), "B_count": self.section_b_count(),
            "C_ape": self.section_c_ape(), "C_count": self.section_c_count(),
            "D_ape": self.section_d_ape(), "D_count": self.section_d_count(),
            "E": self.section_e(), "F": self.section_f(),
        }
