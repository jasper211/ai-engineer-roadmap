#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：复刻《业绩分析报表》S4_产品端视角 全部5个板块（A-E，S4是覆盖率100%的一张表）。

对应 01_初始化项目_Initialize_Project/S4_产品端视角_反推标准_v0.1.md。

两条S4专属规则：
1. A节排除4种状态（含拒保），B/C/D/E节只排除3种"流失类"（不含拒保）——两个口径不能混用。
2. B/C节的"联合主键"分组前，SQ_rate要标准化成统一的百分比字符串（0.025和"2.5%"是同一个值，
   不标准化会被错误拆成两行）。这条标准化只用在这里，不影响report_enricher的"首年折扣(标准化)"
   字段本身（那个字段按Jasper指示是原样透传，需求不同）。
"""
import pandas as pd

LAPSE_STATUSES = ["取消投保", "退保", "搁置受保"]  # B/C/D/E节"流失类"，不含拒保
LAPSE_STATUSES_WITH_REJECT = LAPSE_STATUSES + ["拒保"]  # A节排除范围

# carrier_code -> 报表短名（精确核验，见标准文档1.1）
CARRIER_SHORT_NAME = {
    "香港永明金融有限公司": "永明",
    "香港安盛保险有限公司": "安盛",
    "中国人寿保险（海外）股份有限公司（澳门）": "澳门中国人寿",
    "万通保险国际有限公司": "万通",
    "立桥人寿保险有限公司": "立桥",
    "中国太平洋保险（香港）有限公司": "太平洋",
    "宏利人寿保险（国际）有限公司": "宏利",
    "中国人寿保险（海外）股份有限公司（香港）": "中国人寿",
    "中银人寿保险有限公司": "中银人寿",
    "友邦保险（国际）有限公司": "友邦",
    "保诚保险有限公司": "保诚",
    "永明金融有限公司": "永明金融有限公司",
    "微蓝保险有限公司": "微蓝保险有限公司",
    "安达人寿保险有限公司": "安达人寿保险有限公司",
    "保柏（亚洲）有限公司": "保柏（亚洲）有限公司",
}
# A节固定列出的零业务保司（写死的参考名单，不是算出来的，见标准文档1.1）
ZERO_CARRIERS = {
    "周大福人寿保险有限公司": "周大福",
    "中国太平保险（澳门）有限公司": "澳门太平",
    "保柏环球有限公司": "保柏",
    "富卫人寿保险（百慕大）有限公司": "富卫",
    "忠意保险有限公司": "忠意",
    "信诺环球保险公司": "信诺",
}

TERM_BUCKET_EDGES = [1, 5, 20]
TERM_BUCKET_LABELS = ["短期(≤1年)", "中期(2-5年)", "长期(6-20年)", "终身(>20年)"]


def normalize_sq_rate(v) -> "str | None":
    """把SQ_rate标准化成统一的百分比字符串，用于B/C节联合主键分组——
    不用于report_enricher的'首年折扣(标准化)'字段（那个是原样透传，需求不同）。"""
    if pd.isna(v):
        return None
    if isinstance(v, str):
        return v  # 已经是"2.5%"这种格式，或"申请保司折扣优惠"这类文字，原样作为分组key
    pct = v * 100
    return f"{int(pct)}%" if pct == int(pct) else f"{pct:g}%"


def _term_bucket(value) -> "str | None":
    if not isinstance(value, (int, float)) or isinstance(value, bool) or pd.isna(value):
        return None
    for edge, label in zip(TERM_BUCKET_EDGES, TERM_BUCKET_LABELS):
        if value <= edge:
            return label
    return TERM_BUCKET_LABELS[-1]


class S4ProductViewBuilder:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    # ---- A. 保险公司维度 ----
    def section_a(self) -> list:
        df = self.df
        sub = df[(df["sign_date"].dt.year == 2026) & (~df["policy_status"].isin(LAPSE_STATUSES_WITH_REJECT))]
        rows = []
        for raw_name, short_name in CARRIER_SHORT_NAME.items():
            g = sub[sub["carrier_code"] == raw_name]
            count, ape, premium = len(g), float(g["ape"].sum()), float(g["premium"].sum())
            rows.append({
                "保险公司": short_name, "件数": count, "APE": ape, "年总保费(HKD)": premium,
                "APE件均": ape / count if count else 0.0, "年总保费件均": premium / count if count else 0.0,
            })
        for short_name in ZERO_CARRIERS.values():
            rows.append({"保险公司": short_name, "件数": 0, "APE": 0.0, "年总保费(HKD)": 0.0,
                         "APE件均": 0.0, "年总保费件均": 0.0})
        rows.sort(key=lambda r: r["APE"], reverse=True)

        total_count = sum(r["件数"] for r in rows)
        total_ape = sum(r["APE"] for r in rows)
        total_premium = sum(r["年总保费(HKD)"] for r in rows)
        for r in rows:
            r["件数占比"] = r["件数"] / total_count if total_count else 0.0
            r["APE占比"] = r["APE"] / total_ape if total_ape else 0.0
        rows.append({
            "保险公司": "合计", "件数": total_count, "APE": total_ape, "年总保费(HKD)": total_premium,
            "APE件均": total_ape / total_count if total_count else 0.0,
            "年总保费件均": total_premium / total_count if total_count else 0.0,
            "件数占比": 1.0, "APE占比": 1.0,
        })
        return rows

    # ---- B/C. 产品TOP20（按年总保费/APE降序） ----
    def _product_top(self, rank_by: str, top_n: int = 20) -> list:
        df = self.df
        sub = df[(df["sign_date"].dt.year == 2026) & (~df["policy_status"].isin(LAPSE_STATUSES))].copy()
        sub["_carrier_short"] = sub["carrier_code"].map(CARRIER_SHORT_NAME).fillna(sub["carrier_code"])
        sub["_sq"] = sub["SQ_rate"].apply(normalize_sq_rate)
        # 联合主键要求SQ_rate有值——SQ_rate缺失(约80%的记录)的行在这个排名里整体不出现，
        # 不是被归成一个"缺失"分组（真实数据验证：一个产品+年期组合下281条SQ_rate缺失的记录，
        # 报表TOP20完全不显示这一组，即便金额比很多上榜产品都大）
        sub = sub[sub["_sq"].notna()]

        rows = []
        group_cols = ["_carrier_short", "product_id", "premium_term", "_sq"]
        for (carrier, product, term, sq), g in sub.groupby(group_cols, dropna=False, observed=True):
            count = len(g)
            premium, ape = float(g["premium"].sum()), float(g["ape"].sum())
            rows.append({
                "保司": carrier, "产品名称": product, "年期": term, "首年折扣": sq, "件数": count,
                "年总保费(HKD)": premium, "年总保费件均": premium / count if count else 0.0,
                "APE": ape, "APE件均": ape / count if count else 0.0,
            })
        rows.sort(key=lambda r: r[rank_by], reverse=True)
        top = rows[:top_n]
        for i, r in enumerate(top, 1):
            r["排名"] = i
        return top

    def section_b(self):
        rows = self._product_top("年总保费(HKD)")
        return [{"排名": r["排名"], "保司": r["保司"], "产品名称": r["产品名称"], "年期": r["年期"],
                  "首年折扣": r["首年折扣"], "件数": r["件数"], "年总保费(HKD)": r["年总保费(HKD)"],
                  "年总保费件均": r["年总保费件均"]} for r in rows]

    def section_c(self):
        rows = self._product_top("APE")
        return [{"排名": r["排名"], "保司": r["保司"], "产品名称": r["产品名称"], "年期": r["年期"],
                  "首年折扣": r["首年折扣"], "件数": r["件数"], "APE": r["APE"],
                  "APE件均": r["APE件均"]} for r in rows]

    # ---- D/E. 年期分布 / 供款方式分布 ----
    def _distribution(self, group_col_values: pd.Series, group_name: str) -> list:
        df = self.df
        sub = df[(df["sign_date"].dt.year == 2026) & (~df["policy_status"].isin(LAPSE_STATUSES)) & (df["ape"] > 0)].copy()
        sub["_group"] = group_col_values.loc[sub.index]

        # "合计"是基础过滤条件下的全量（sign_year=2026+非流失+APE>0），不是各分档相加——
        # D节premium_term为文本/缺失的7条记录不落入任何分档，但仍计入合计（跟S1-F"失效"档
        # 同一种模式：分档覆盖不了100%时，合计要用独立的基础口径，不能假设分档能兜底全部）
        total_count, total_ape, total_premium = len(sub), float(sub["ape"].sum()), float(sub["premium"].sum())

        rows = []
        for val, g in sub.groupby("_group", observed=True):
            count, ape, premium = len(g), float(g["ape"].sum()), float(g["premium"].sum())
            rows.append({group_name: val, "件数": count, "APE": ape, "年总保费(HKD)": premium,
                         "APE件均": ape / count if count else 0.0, "年总保费件均": premium / count if count else 0.0,
                         "件数占比": count / total_count if total_count else 0.0})
        rows.append({group_name: "合计", "件数": total_count, "APE": total_ape, "年总保费(HKD)": total_premium,
                     "APE件均": total_ape / total_count if total_count else 0.0,
                     "年总保费件均": total_premium / total_count if total_count else 0.0, "件数占比": 1.0})
        return rows

    def section_d(self) -> list:
        term_bucket = self.df["premium_term"].apply(_term_bucket)
        return self._distribution(term_bucket, "年期分类")

    def section_e(self) -> list:
        return self._distribution(self.df["payment_mode"], "供款方式")

    def build_all(self) -> dict:
        return {"A": self.section_a(), "B": self.section_b(), "C": self.section_c(),
                "D": self.section_d(), "E": self.section_e()}
