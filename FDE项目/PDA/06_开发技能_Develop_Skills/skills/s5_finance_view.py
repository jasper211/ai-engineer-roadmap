#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：复刻《业绩分析报表》S5_财务端视角 全部8个板块（A/B-保费/B-件数/C-APE/C-件数/D/E/F/G/H）。

对应 01_初始化项目_Initialize_Project/S5_财务端视角_反推标准_v0.1.md。基础口径统一是
`status=生效 AND issue_year=2026`，比S1-S4简单——没有"未批核/待签"维度。

复用两处已有成果：D/E节分档边界=report_enricher的PREMIUM_BUCKET/APE_BUCKET常量；
G/H节"保司"简称=s4_product_view的CARRIER_SHORT_NAME映射。"牌照"简称是S5独有规则：
issuing_entity前4个字的截断，不是查表映射。
"""
import pandas as pd

from skills.report_enricher import PREMIUM_BUCKET_EDGES, PREMIUM_BUCKET_LABELS, APE_BUCKET_EDGES, APE_BUCKET_LABELS
from skills.s4_product_view import CARRIER_SHORT_NAME


def _money_bucket(value, edges, labels):
    if pd.isna(value):
        return None
    wan = value / 10000
    for edge, label in zip(edges, labels):
        if wan < edge:
            return label
    return labels[-1]


class S5FinanceViewBuilder:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self._b26 = df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)]

    # ---- A. 牌照维度-2026批核 ----
    def section_a(self) -> list:
        g = self._b26.groupby("issuing_entity", observed=True).agg(
            件数=("ape", "size"), 批核APE=("ape", "sum"), 批核年总保费=("premium", "sum")
        ).reset_index()
        for entity in self.df["issuing_entity"].unique():
            if entity not in g["issuing_entity"].values:
                g.loc[len(g)] = [entity, 0, 0.0, 0.0]
        g = g.sort_values("批核年总保费", ascending=False)
        total_count, total_ape, total_premium = g["件数"].sum(), g["批核APE"].sum(), g["批核年总保费"].sum()
        rows = [{
            "牌照(签单供应商)": r["issuing_entity"], "件数": int(r["件数"]), "批核APE": float(r["批核APE"]),
            "批核年总保费(HKD)": float(r["批核年总保费"]),
            "件数占比": r["件数"] / total_count if total_count else 0.0,
            "APE占比": r["批核APE"] / total_ape if total_ape else 0.0,
            "批核年总保费占比": r["批核年总保费"] / total_premium if total_premium else 0.0,
        } for _, r in g.iterrows()]
        rows.append({
            "牌照(签单供应商)": "合计", "件数": int(total_count), "批核APE": float(total_ape),
            "批核年总保费(HKD)": float(total_premium), "件数占比": 1.0, "APE占比": 1.0, "批核年总保费占比": 1.0,
        })
        return rows

    # ---- B/C. 牌照×批核月度（保费/APE，各含件数） ----
    def _monthly_by_entity(self, metric: str, year: int = 2026) -> list:
        df = self._b26.copy()
        month = df["issue_date"].dt.strftime("%Y-%m")
        months = sorted(m for m in month.unique() if m.startswith(str(year)))
        df = df.assign(_month=month)

        rows = []
        for entity in self.df["issuing_entity"].unique():
            g_entity = df[df["issuing_entity"] == entity]
            row = {"牌照": entity}
            total = 0.0
            for m in months:
                v = float(g_entity.loc[g_entity["_month"] == m, metric].sum())
                row[m] = v
                total += v
            row["合计"] = total
            rows.append(row)
        total_row = {"牌照": "合计"}
        for m in months + ["合计"]:
            total_row[m] = sum(r[m] for r in rows)
        rows.append(total_row)
        return rows

    def section_b_premium(self):
        return self._monthly_by_entity("premium")

    def section_b_count(self) -> list:
        df = self._b26.copy()
        month = df["issue_date"].dt.strftime("%Y-%m")
        months = sorted(m for m in month.unique() if m.startswith("2026"))
        df = df.assign(_month=month)
        rows = []
        for entity in self.df["issuing_entity"].unique():
            g_entity = df[df["issuing_entity"] == entity]
            row = {"牌照": entity}
            total = 0
            for m in months:
                v = int((g_entity["_month"] == m).sum())
                row[m] = v
                total += v
            row["合计"] = total
            rows.append(row)
        total_row = {"牌照": "合计"}
        for m in months + ["合计"]:
            total_row[m] = sum(r[m] for r in rows)
        rows.append(total_row)
        return rows

    def section_c_ape(self):
        return self._monthly_by_entity("ape")

    def section_c_count(self):
        return self.section_b_count()

    # ---- D/E. 保费/APE规模分布 ----
    def section_d(self) -> list:
        df = self._b26.copy()
        df["_bucket"] = df["premium"].apply(lambda v: _money_bucket(v, PREMIUM_BUCKET_EDGES, PREMIUM_BUCKET_LABELS))
        total_premium = float(df["premium"].sum())
        pf = df[df["Is_Premium_Financing"] == 1]
        rows = []
        for label in PREMIUM_BUCKET_LABELS:
            g = df[df["_bucket"] == label]
            g_pf = pf[pf["_bucket"] == label]
            premium = float(g["premium"].sum())
            rows.append({
                "保费规模档": label, "件数": int(len(g)), "年总保费(HKD)": premium,
                "年总保费件均": premium / len(g) if len(g) else 0.0,
                "年总保费占比": premium / total_premium if total_premium else 0.0,
                "融资年总保费占比": float(g_pf["premium"].sum()) / premium if premium else 0.0,
            })
        total_count = len(df)
        total_pf_premium = float(pf["premium"].sum())
        rows.append({
            "保费规模档": "合计", "件数": total_count, "年总保费(HKD)": total_premium,
            "年总保费件均": total_premium / total_count if total_count else 0.0,
            "年总保费占比": 1.0, "融资年总保费占比": total_pf_premium / total_premium if total_premium else 0.0,
        })
        return rows

    def section_e(self) -> list:
        df = self._b26.copy()
        df["_bucket"] = df["ape"].apply(lambda v: _money_bucket(v, APE_BUCKET_EDGES, APE_BUCKET_LABELS))
        total_ape = float(df["ape"].sum())
        pf = df[df["Is_Premium_Financing"] == 1]
        rows = []
        for label in APE_BUCKET_LABELS:
            g = df[df["_bucket"] == label]
            g_pf = pf[pf["_bucket"] == label]
            ape = float(g["ape"].sum())
            rows.append({
                "APE规模档": label, "件数": int(len(g)), "APE": ape,
                "APE占比": ape / total_ape if total_ape else 0.0,
                "APE件均": ape / len(g) if len(g) else 0.0,
                "融资APE占比": float(g_pf["ape"].sum()) / ape if ape else 0.0,
            })
        total_count = len(df)
        total_pf_ape = float(pf["ape"].sum())
        rows.append({
            "APE规模档": "合计", "件数": total_count, "APE": total_ape, "APE占比": 1.0,
            "APE件均": total_ape / total_count if total_count else 0.0,
            "融资APE占比": total_pf_ape / total_ape if total_ape else 0.0,
        })
        return rows

    # ---- F. 常规 vs 融资对比 ----
    def section_f(self) -> list:
        df = self._b26
        total_count, total_ape, total_premium = len(df), float(df["ape"].sum()), float(df["premium"].sum())
        rows = []
        for label, is_pf in [("常规", 0), ("融资", 1)]:
            g = df[df["Is_Premium_Financing"] == is_pf]
            count, ape, premium = len(g), float(g["ape"].sum()), float(g["premium"].sum())
            rows.append({
                "类型": label, "件数": count, "APE": ape, "年总保费(HKD)": premium,
                "件数占比": count / total_count if total_count else 0.0,
                "APE占比": ape / total_ape if total_ape else 0.0,
                "年总保费占比": premium / total_premium if total_premium else 0.0,
            })
        rows.append({"类型": "合计", "件数": total_count, "APE": total_ape, "年总保费(HKD)": total_premium,
                     "件数占比": 1.0, "APE占比": 1.0, "年总保费占比": 1.0})
        return rows

    # ---- G/H. 大额保单TOP20（并列金额时sign_date升序） ----
    def _top20_policies(self, rank_by: str, top_n: int = 20) -> list:
        df = self._b26.copy()
        df["_short"] = df["issuing_entity"].str[:4]
        df["_carrier_short"] = df["carrier_code"].map(CARRIER_SHORT_NAME).fillna(df["carrier_code"])
        df = df.sort_values([rank_by, "sign_date"], ascending=[False, True])
        rows = []
        for i, (_, r) in enumerate(df.head(top_n).iterrows(), 1):
            rows.append({
                "排名": i, "保单号": r["policy_no"], "签单日": r["sign_date"].strftime("%Y-%m-%d"),
                "牌照": r["_short"], "KA": r["key_account"], "保司": r["_carrier_short"],
                "产品": r["product_id"], "年期": r["premium_term"], "APE": float(r["ape"]),
            })
        return rows

    def section_g(self):
        return self._top20_policies("premium")

    def section_h(self):
        return self._top20_policies("ape")

    def build_all(self) -> dict:
        return {
            "A": self.section_a(),
            "B_premium": self.section_b_premium(), "B_count": self.section_b_count(),
            "C_ape": self.section_c_ape(), "C_count": self.section_c_count(),
            "D": self.section_d(), "E": self.section_e(), "F": self.section_f(),
            "G": self.section_g(), "H": self.section_h(),
        }
