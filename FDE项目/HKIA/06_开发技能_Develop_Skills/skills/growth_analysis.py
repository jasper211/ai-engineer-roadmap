#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：对"總額"合计行计算环比(QoQ)/同比(YoY)增长率——demo进入分析层的第一步，
只做确定性算术，不接LLM。

关键点：新造业务是"年初至今累计值"（period_type=YTD_Q1/H1/9M/FY），有效业务是
"期末存量"（point-in-time）。两者的"环比"含义不一样，不能用同一套逻辑：

- 有效业务（存量）：QoQ直接比相邻两期的值，YoY直接比去年同季度的值——原始
  存储的值本身就是可比的。
- 新造业务（YTD累计）：
  - YoY可以直接比"去年同一累计区间 vs 今年同一累计区间"（如2024Q1对比2023Q1），
    因为两边都是"从当年1月累计到3月"，口径一致。
  - 但QoQ如果直接拿"2024Q1的YTD值"减"2023Q4的YTD值"，会算出一个巨大的负数——
    这不是真实业务下滑，只是每年1月YTD重新从零起算的记账artifact。必须先把
    每期的YTD累计值还原成"当季独立新增额"（discrete quarterly：Q1就是YTD_Q1
    本身，Q2/Q3/Q4分别是当期YTD减上一期YTD），再在这些独立季度值上算QoQ。
"""
from dataclasses import dataclass

QUARTER_ORDER = {"YTD_Q1": 1, "YTD_H1": 2, "YTD_9M": 3, "YTD_FY": 4}


@dataclass
class GrowthPoint:
    date: str
    value: float
    qoq: float | None  # None表示这一期没有可比的上一期（数据第一期，或跨年重置边界）
    yoy: float | None  # None表示去年同期没有数据


def _pct(curr: float, prev: float) -> float | None:
    if prev is None or prev == 0:
        return None
    return (curr - prev) / prev


class GrowthAnalyzer:
    def in_force_growth(self, series: list) -> list:
        """series: [(date, period_type, value), ...] 按时间升序。存量指标，
        QoQ/YoY都直接用原始值比。"""
        by_index = series
        results = []
        for i, (date, _, value) in enumerate(by_index):
            prev = by_index[i - 1][2] if i >= 1 else None
            prev_year = by_index[i - 4][2] if i >= 4 else None
            results.append(GrowthPoint(
                date=date, value=value,
                qoq=_pct(value, prev),
                yoy=_pct(value, prev_year),
            ))
        return results

    def new_business_growth(self, series: list) -> list:
        """series: [(date, period_type, value), ...] 按时间升序，value是YTD
        累计值。先还原出"当季独立新增额"，YoY仍然用原始YTD值同比（口径一致），
        QoQ改用还原后的独立季度值。"""
        discrete = []
        prev_ytd_this_year = None
        prev_year_marker = None
        for date, period_type, value in series:
            year = date[:4]
            if year != prev_year_marker:
                prev_ytd_this_year = None
                prev_year_marker = year
            if period_type == "YTD_Q1" or prev_ytd_this_year is None:
                q_value = value
            else:
                q_value = value - prev_ytd_this_year
            prev_ytd_this_year = value
            discrete.append(q_value)

        results = []
        for i, (date, _, ytd_value) in enumerate(series):
            prev_discrete = discrete[i - 1] if i >= 1 else None
            prev_year_ytd = series[i - 4][2] if i >= 4 else None
            results.append(GrowthPoint(
                date=date, value=ytd_value,
                qoq=_pct(discrete[i], prev_discrete),
                yoy=_pct(ytd_value, prev_year_ytd),
            ))
        return results
