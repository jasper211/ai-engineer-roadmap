#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：把 excel_parser 输出的原始字段记录，标准化成长表格式：
date, category, metric_name, unit, value, table_type, period_type,
schema_version, source_report, fetched_at

- unit 从 metric_name 里拆出来（"千港元"/"(千港元)"），metric_name 保持干净
- schema_version 直接透传 excel_parser 判定的结果（"pre_rbc"/"post_rbc"），
  不在这里做新旧口径的映射/合并——按需求定义确认的原则，两套口径分开存
"""
import re
from dataclasses import dataclass
from datetime import date, datetime

UNIT_PATTERN = re.compile(r"^\(?(千港元|HK\$'000)\)?$")

QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


@dataclass
class NormalizedRow:
    date: str
    category: str
    metric_name: str
    unit: str
    value: float
    table_type: str
    period_type: str
    schema_version: str
    source_report: str
    fetched_at: str


def _split_unit(metric_name: str) -> "tuple[str, str]":
    parts = metric_name.split("/")
    if parts and UNIT_PATTERN.match(parts[-1]):
        return "/".join(parts[:-1]) or parts[-1], "千港元"
    return metric_name, ""


class Normalizer:
    def normalize(
        self,
        parsed: dict,
        year: int,
        quarter: int,
        period_type: str,
        source_report: str,
    ) -> "list[NormalizedRow]":
        month, day = QUARTER_END[quarter]
        period_end = date(year, month, day).isoformat()
        fetched_at = datetime.now().isoformat(timespec="seconds")
        schema_version = parsed["schema_version"]

        rows = []
        table_keys = (
            ("new_business", "new_business"),
            ("in_force", "in_force"),
            ("new_business_by_insurer", "new_business_by_insurer"),
        )
        for table_type, key in table_keys:
            for rec in parsed[key]:
                metric_name, unit = _split_unit(rec["metric_name"])
                rows.append(NormalizedRow(
                    date=period_end,
                    category=rec["category"],
                    metric_name=metric_name,
                    unit=unit,
                    value=rec["value"],
                    table_type=table_type,
                    period_type=period_type,
                    schema_version=schema_version,
                    source_report=source_report,
                    fetched_at=fetched_at,
                ))
        return rows
