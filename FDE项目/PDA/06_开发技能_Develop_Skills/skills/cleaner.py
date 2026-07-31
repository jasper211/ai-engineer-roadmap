#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：清洗标准化底表 DataFrame。

对应 流程设计.md L3-PDA-02。修复需求定义.md 第十一节核实出的 2 个真实 bug：
- 【真问题1】res_date/sign_date/submit_date/issue_date 混有 Excel 序列号整数，
  朴素 pd.to_datetime 会静默解析成 1970 年附近的错误时间戳。
- 【真问题2】future_dated 用文件名解析出的导出日期动态判断，不再硬编码某个日期。
"""
import datetime as dt

import pandas as pd

DATE_COLUMNS = ["res_date", "sign_date", "submit_date", "issue_date"]

EXCEL_EPOCH = dt.datetime(1899, 12, 30)

# 沿用阶段一原型 footer 已经写死的三档口径（需求定义.md 七、十一节），不是本次新发明
STATUS_TIER_MAP = {
    "生效": "生效",
    "待批核": "在途",
    "pending": "在途",
    "排期": "在途",
    "已签单": "在途",
    "尚欠保费": "在途",
    "取消投保": "终止",
    "退保": "终止",
    "搁置受保": "终止",
    "拒保": "终止",
}

# 全角/半角空格等"看起来空但不是NaN"的值，清洗时统一转空
BLANK_LIKE = {"　", " ", ""}


class UnmappedStatusError(Exception):
    """出现 STATUS_TIER_MAP 里没有的 policy_status 取值时抛出，不静默归类。"""


def _excel_serial_to_date(x):
    """把单元格值统一转成 Timestamp：int/float 按 Excel 序列号换算，
    datetime/date 直接用，其余（含空）返回 NaT。"""
    if pd.isna(x):
        return pd.NaT
    if isinstance(x, (dt.datetime, dt.date)):
        return pd.Timestamp(x)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return pd.Timestamp(EXCEL_EPOCH + dt.timedelta(days=float(x)))
    return pd.NaT


class Cleaner:
    """接收 DataLoader 产出的原始 DataFrame，返回清洗后 DataFrame，不读写任何持久化状态。"""

    def clean(self, df: pd.DataFrame, export_date: "pd.Timestamp | None") -> pd.DataFrame:
        df = df.copy()

        for col in DATE_COLUMNS:
            df[col] = df[col].apply(_excel_serial_to_date)

        unknown_status = set(df["policy_status"].unique()) - set(STATUS_TIER_MAP)
        if unknown_status:
            raise UnmappedStatusError(f"policy_status 出现未知取值，需要补充映射规则: {unknown_status}")
        df["policy_status_tier"] = df["policy_status"].map(STATUS_TIER_MAP)

        if export_date is not None:
            df["future_dated"] = df["sign_date"] > export_date
        else:
            df["future_dated"] = False

        df["premium"] = pd.to_numeric(df["premium"], errors="coerce").fillna(0)
        df["ape"] = pd.to_numeric(df["ape"], errors="coerce").fillna(0)

        df["currency_code"] = df["currency_code"].where(df["currency_code"].notna(), "未填")

        df["sum_assured"] = df["sum_assured"].apply(
            lambda x: pd.NA if isinstance(x, str) and x.strip() in BLANK_LIKE else x
        )

        df["Is_Premium_Financing"] = pd.to_numeric(df["Is_Premium_Financing"], errors="coerce").fillna(0).astype(int)

        return df
