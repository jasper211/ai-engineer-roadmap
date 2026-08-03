#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：给清洗后的底表 DataFrame 加上"业绩分析报表"（S8_明细数据底表）用到的13个衍生字段。

对应 01_初始化项目_Initialize_Project/S8衍生字段_反推标准_v0.1.md——每条规则都是
拿真实底表跟 raw_data/业绩分析报表_0724.xlsx 的 S8 sheet 逐行核对出来的，不是猜的。
Jasper 手动修复了该文件里"APE分档往后7列表头错位"的bug后，12/13条规则已100%匹配；
唯一未完成的是"首年折扣(标准化)"——来源字段已确认是 SQ_rate，但目前只是原样透传，
真正的标准化分档规则还没有，所以这里也只原样透传，不擅自编一套边界。
"""
import datetime as dt

import pandas as pd

# 业务大类：等于 business_category，唯一例外 MGA业务→经代业务（真实数据验证，209条天誉国际MGA业务）
BUSINESS_MAJOR_CATEGORY_OVERRIDE = {"MGA业务": "经代业务"}

# 保单阶段：policy_status → A/B/C/D 四档字母（对应报表口径：批核/未批核/待签/流失）
POLICY_STAGE_MAP = {
    "生效": "A",
    "尚欠保费": "B", "已签单": "B", "pending": "B", "待批核": "B",
    "排期": "C",
    "取消投保": "D", "退保": "D", "搁置受保": "D", "拒保": "D",
}

PREMIUM_BUCKET_EDGES = [5, 20, 50, 100]
PREMIUM_BUCKET_LABELS = ["<5万", "5-20万", "20-50万", "50-100万", "100万+"]
APE_BUCKET_EDGES = [3, 15, 40, 80]
APE_BUCKET_LABELS = ["<3万", "3-15万", "15-40万", "40-80万", "80万+"]

TERM_BUCKET_EDGES = [1, 5, 20]
TERM_BUCKET_LABELS = ["短期(≤1年)", "中期(2-5年)", "长期(6-20年)", "终身(>20年)"]


class UnmappedPolicyStageError(Exception):
    """policy_status 出现 POLICY_STAGE_MAP 里没有的取值时抛出，不静默归类。"""


def _money_bucket(value, edges, labels) -> "str | None":
    if pd.isna(value):
        return None
    wan = value / 10000
    for edge, label in zip(edges, labels):
        if wan < edge:
            return label
    return labels[-1]


def _term_bucket(value) -> "str | None":
    """premium_term 只有数字才分档；文本值（"终身"/"至100岁"）返回None——
    反直觉，但真实数据100%如此（见标准文档一节"年期分类"）。"""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or pd.isna(value):
        return None
    for edge, label in zip(TERM_BUCKET_EDGES, TERM_BUCKET_LABELS):
        if value <= edge:
            return label
    return TERM_BUCKET_LABELS[-1]


class ReportEnricher:
    """接收 cleaner 产出的清洗后 DataFrame，返回附加13个衍生字段的 DataFrame。"""

    def enrich(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        unknown = set(df["policy_status"].unique()) - set(POLICY_STAGE_MAP)
        if unknown:
            raise UnmappedPolicyStageError(f"policy_status 出现未知取值，需要补充映射规则: {unknown}")
        df["保单阶段"] = df["policy_status"].map(POLICY_STAGE_MAP)

        df["业务大类"] = df["business_category"].replace(BUSINESS_MAJOR_CATEGORY_OVERRIDE)

        df["融资标签"] = df["Is_Premium_Financing"].map({0: "常规", 1: "融资"})

        df["年期分类"] = df["premium_term"].apply(_term_bucket)

        df["保费分档"] = df["premium"].apply(lambda v: _money_bucket(v, PREMIUM_BUCKET_EDGES, PREMIUM_BUCKET_LABELS))
        df["APE分档"] = df["ape"].apply(lambda v: _money_bucket(v, APE_BUCKET_EDGES, APE_BUCKET_LABELS))

        df["签批时效(天)"] = (df["issue_date"] - df["sign_date"]).dt.days
        df["签单年"] = df["sign_date"].dt.year
        df["签单年月"] = df["sign_date"].dt.strftime("%Y-%m")
        df["批核年"] = df["issue_date"].dt.year
        df["批核年月"] = df["issue_date"].dt.strftime("%Y-%m")
        df["预约年月"] = df["res_date"].dt.strftime("%Y-%m")

        # 首年折扣(标准化)：来源字段=SQ_rate已确认，标准化分档规则待Jasper提供，本版本原样透传
        df["首年折扣(标准化)_原始未标准化"] = df["SQ_rate"]

        return df
