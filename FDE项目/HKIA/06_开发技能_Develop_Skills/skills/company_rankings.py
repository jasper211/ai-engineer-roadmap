#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：按保险公司计算6类排名表，全部是对已入库长表数据的确定性聚合/算术，
不做新采集、不接LLM。对应"香港保险圈"同类信息图的6张表，逐一验证过真实
数字一致（见执行记录.md v0.2.4）。

两个可复用的"口径"：
- 总保费 = 整付保費(原始金额) + 年度化保費
- 标准保费 = 整付保費 × 10% + 年度化保費（剔除大额整付保单对排名的干扰）

两个可复用的"范围"：
- 全渠道：来自 new_business_by_insurer（Table L1 總額行）
- 单一渠道（如經紀）/剔除某渠道（如非银）：来自
  new_business_by_insurer_channel（Table L1(channel) 按渠道拆分）

新增排名口径/新增渠道口径时，只需要在 PREMIUM_FORMULAS / CHANNELS 里加一条，
不需要改计算逻辑本身——这是应 Jasper 后续持续补充维度的需求特意这样设计的。
"""
import re
from dataclasses import dataclass, field

GRAND_TOTAL_CATEGORY = "市場總額"

# "非银"排名剔除的是"银行系"保险公司本身（母行/关联行是滙豐/中銀/恒生——
# 恒生银行是滙豐集团旗下子行，恒生保险也归为银行系——几乎全部业务走自家
# 银行渠道），不是"每家公司剔除自己的银行渠道销售额"——用剔除后的公司名单
# 重排，但分母（市场份额的总量）仍然是全市场总量，不重新计算。这条名单是
# 对着"香港保险圈"同期排名反推验证出来的（第一次只排除滙豐+中銀两家时，
# 前15位加总跟对方报的300对不上，实际到300要连恒生也排除掉）——不是从任何
# 单一sheet字段能直接读出来的，是需要人工维护的名单，以后银行系保险公司
# 有变动要跟着改。
BANK_AFFILIATED_INSURERS = {"滙豐人壽", "中銀人壽", "恒生保險"}

CHANNELS = {
    "agent": "(a) 代理",
    "bank": "(b) 銀行保險",
    "broker": "(c)  經紀",
    "direct": "(d) 直接銷售",
    "other": "(e)  其他",
}

PREMIUM_FORMULAS = {
    "total": lambda single, annualized: single + annualized,
    "standard": lambda single, annualized: single * 0.1 + annualized,
}


@dataclass
class CompanyRow:
    company: str
    current: float
    share_pct: float
    prior: "float | None"
    yoy_pct: "float | None"


@dataclass
class PolicyCountRow:
    company: str
    single_count: float
    non_single_count: float
    single_avg: "float | None"   # 万港元/件
    non_single_avg: "float | None"


def _index_rows(rows: list) -> dict:
    """rows: [(table_type, category, metric_name, value), ...]
    返回 {(table_type, category): {metric_name: value}}，后面按需要用
    metric_name的子串去精确匹配某个字段，不整表扫描。"""
    idx = {}
    for table_type, category, metric_name, value in rows:
        idx.setdefault((table_type, category), {})[metric_name] = value
    return idx


def _find_value(fields: dict, must_contain: list, must_not_contain: list = ()) -> "float | None":
    for metric_name, value in fields.items():
        if all(s in metric_name for s in must_contain) and not any(s in metric_name for s in must_not_contain):
            return value
    return None


class CompanyRankings:
    def _premium_by_company(
        self, rows: list, table_type: str, channel_include: "list[str] | None",
        formula: str,
    ) -> dict:
        """返回 {company: 保费值}，company不含市場總額。
        channel_include=None 表示用 new_business_by_insurer 的"總額"行（全渠道）；
        channel_include=[渠道列表] 表示用 new_business_by_insurer_channel，把列表里
        的渠道各自的整付/年度化加总（用于"经纪渠道"单渠道，或"非银"=除银行外
        全部渠道相加）。"""
        idx = _index_rows(rows)
        result = {}
        for (t, category), fields in idx.items():
            if t != table_type or category == GRAND_TOTAL_CATEGORY:
                continue
            if channel_include is None:
                single = _find_value(fields, ["總額", "整付保費"], ["保單數目"])
                annualized = _find_value(fields, ["總額", "年度化保費"], ["保單數目"])
            else:
                single = sum(
                    _find_value(fields, [CHANNELS[ch], "整付保費"], ["保單數目", "總額"]) or 0
                    for ch in channel_include
                )
                annualized = sum(
                    _find_value(fields, [CHANNELS[ch], "年度化保費"], ["保單數目", "總額"]) or 0
                    for ch in channel_include
                )
            if single is None and annualized is None:
                continue
            result[category] = PREMIUM_FORMULAS[formula](single or 0, annualized or 0)
        return result

    def rank(
        self, rows_current: list, rows_prior: "list | None", table_type: str,
        formula: str, channel_include: "list[str] | None" = None, top_n: int = 15,
        exclude_companies: "set | None" = None,
    ) -> "list[CompanyRow]":
        """通用排名：全渠道总保费/标准保费、单渠道（经纪）都走 channel_include；
        "非银"这类排名用 exclude_companies——分母（市场份额总量）用全部公司
        算，只是排名列表里不出现被排除的公司，不是从每家公司身上扣掉一块。"""
        current_map = self._premium_by_company(rows_current, table_type, channel_include, formula)
        prior_map = self._premium_by_company(rows_prior, table_type, channel_include, formula) if rows_prior else {}

        total = sum(current_map.values())
        ranked = sorted(current_map.items(), key=lambda kv: kv[1], reverse=True)
        if exclude_companies:
            ranked = [(c, v) for c, v in ranked if c not in exclude_companies]

        result = []
        for company, value in ranked[:top_n]:
            prior = prior_map.get(company)
            yoy = (value - prior) / prior if prior else None
            result.append(CompanyRow(
                company=company,
                current=value,
                share_pct=value / total * 100 if total else 0,
                prior=prior,
                yoy_pct=yoy,
            ))
        return result

    def policy_count_and_avg(self, rows_current: list, table_type: str, top_n: int = 15) -> "list[PolicyCountRow]":
        """保单数+件均保费——排序用总保费(整付+年度化)降序，跟参考图一致。"""
        idx = _index_rows(rows_current)
        result = []
        for (t, category), fields in idx.items():
            if t != table_type or category == GRAND_TOTAL_CATEGORY:
                continue
            single_count = _find_value(fields, ["總額", "保單數目", "整付保費"])
            non_single_count = _find_value(fields, ["總額", "保單數目", "非整付保費"])
            single_amount = _find_value(fields, ["總額", "保費數額", "整付保費"], ["保單數目"])
            annualized = _find_value(fields, ["總額", "保費數額", "年度化保費"], ["保單數目"])
            if single_count is None and non_single_count is None:
                continue
            single_avg = (single_amount / single_count / 10) if single_count else None  # 千港元/件 -> 万港元/件
            non_single_avg = (annualized / non_single_count / 10) if non_single_count else None
            sort_key = (single_amount or 0) + (annualized or 0)
            result.append((sort_key, PolicyCountRow(
                company=category,
                single_count=single_count or 0,
                non_single_count=non_single_count or 0,
                single_avg=single_avg,
                non_single_avg=non_single_avg,
            )))
        result.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in result[:top_n]]
