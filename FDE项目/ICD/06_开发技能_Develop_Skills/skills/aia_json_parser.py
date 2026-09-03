#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/aia_json_parser.py · AIA 分红实现率 JSON 解析与标准化（L3-ICD-03 解析层）

职责边界：纯函数，把 AIA 静态 JSON 的原始字节解析为标准化的观测记录列表。
不访问网络、不读库、不写库（入库由 tools/ratio_writer + skills/parse_disclosure 负责）。

AIA JSON 结构（2026 版真实文件，report_year=2025，81 个产品）：
  {
    "report_year": 2025,
    "pData": [
      {
        "productNm": {"en": "...", "zh-hk": "...", "zh-cn": "..."},
        "type": {"en": "...", "zh-hk": "...", "zh-cn": "..."},
        "AD": [ {"currency": {"en":"All"|"USD"|"HKD / MOP", ...}, "remark": {...},
                 "data": [ {"year":"2024","ratio":"112%"}, ... ] } ],
        "TD": [ ... ], "RB": [ ... ], "TB": [ ... ]      # 四个指标字段可选出现
      }, ...
    ]
  }

标准化约定（对齐 data_contract.md 与 T004 两项决策补充）：
- metric_type / metric_type_raw：AIA 四类指标字段 AD/TD/RB/TB 一一对应（官网字段名即键名）。
  RB(Reversionary Bonuses) 与 TB(Terminal Bonuses) 与 AD/TD 分开保存，不合并。
- scope_currency_raw：取 currency.en 原样保存（All / USD / HKD / MOP），不拆分组合币种。
- report_year：披露报告年度（取 report_year）。
- observation_year_raw / observation_year：数字年份同时写原文标签与整数年；"Before 2015"
  等开放区间标签原样保存到 observation_year_raw，observation_year 写 NULL，不虚构单年。
- ratio 解析：先剥离 <sup>...</sup> 脚注标记，再匹配整数/小数百分比转小数比率；
  无法解析（如 "Closed to sales" / "Not yet launched" / "N.A.<sup>(5)</sup>"）时
  normalized_value=None、保留 raw_value，计为 VALUE_UNPARSEABLE 软失败，不静默丢弃。
"""

import json
import re
from typing import List, Optional

# AIA 四个指标字段（官网顶层标题明确区分的四类口径）
METRIC_KEYS = ("AD", "TD", "RB", "TB")

# "Before 2015" 开放区间标签：observation_year 写 NULL，原文保留在 observation_year_raw
BEFORE_YEAR_LABEL = "Before 2015"

# 百分比匹配：整数或小数 + '%'
_PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
_YEAR_RE = re.compile(r"^\d{4}$")
# 脚注标记（如 <sup>(5)</sup>）：连同内容一并剥离，避免污染数值解析
_FOOTNOTE_RE = re.compile(r"<sup>.*?</sup>", re.DOTALL)
_ANY_TAG_RE = re.compile(r"<[^>]+>")


class AiaParseError(Exception):
    """AIA JSON 结构不符合预期（结构缺键/类型错误），对应 STRUCTURE_MISMATCH 硬失败。"""


def parse_ratio(ratio_str) -> Optional[float]:
    """把官网 ratio 字符串解析为小数比率；无法解析返回 None。

    - "94%" -> 0.94， "100%" -> 1.0， "112%" -> 1.12（超过 100% 合法）
    - "100%<sup>(6)</sup>" -> 1.0（剥离脚注后解析，raw_value 仍保留原文）
    - "Closed to sales" / "Not yet launched" / "N.A.<sup>(5)</sup>" -> None
    """
    if ratio_str is None:
        return None
    s = str(ratio_str)
    s = _FOOTNOTE_RE.sub("", s)
    s = _ANY_TAG_RE.sub("", s).strip()
    m = _PCT_RE.match(s)
    if m:
        return float(m.group(1)) / 100.0
    return None


def parse_observation_year(year_str):
    """把 year 标签解析为 (observation_year_raw, observation_year)；无法解析抛 ValueError。

    - 数字年份 "2024" → ("2024", 2024)（原文标签与整数年同时保存）
    - "Before 2015" → ("Before 2015", None)（开放区间标签，整数年写 NULL，不虚构 2014）
    """
    if year_str is None:
        raise ValueError("observation year 缺失")
    s = str(year_str).strip()
    if _YEAR_RE.match(s):
        return (s, int(s))
    if s == BEFORE_YEAR_LABEL:
        return (s, None)
    raise ValueError(f"无法解析的年份标签: {year_str!r}")


def _product_name(pnm: dict) -> str:
    """取产品原始英文名，回退繁中/简中。"""
    if not isinstance(pnm, dict):
        return ""
    for k in ("en", "zh-hk", "zh-cn"):
        v = pnm.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _currency_label(currency_obj) -> str:
    """取币种/披露分组原始值（en 优先，回退繁中/简中）；缺失回退 'All'。"""
    if not isinstance(currency_obj, dict):
        return "All"
    for k in ("en", "zh-hk", "zh-cn"):
        v = currency_obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "All"


def parse_aia_json(body: bytes) -> dict:
    """解析 AIA JSON 字节 → 标准化结果。

    返回：
      {"status": "OK" | "ZERO_RECORD", "report_year": int, "product_count": int,
       "records": [record...], "value_unparseable": int}

    record 结构（可直接交给 ratio_writer 入库）：
      product_name_raw / metric_type / metric_type_raw / report_year /
      observation_year_raw / observation_year / scope_currency_raw / raw_value /
      normalized_value / product_id

    结构缺键、类型错误、零产品、零业务记录 → 抛 AiaParseError（STRUCTURE_MISMATCH）。
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        raise AiaParseError(f"JSON 非 UTF-8: {type(e).__name__}")

    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise AiaParseError(f"JSON 解析失败: {e}")

    if not isinstance(doc, dict):
        raise AiaParseError("顶层不是 JSON 对象")

    report_year = doc.get("report_year")
    if not isinstance(report_year, int) or isinstance(report_year, bool):
        raise AiaParseError("report_year 缺失或非整数")

    pdata = doc.get("pData")
    if not isinstance(pdata, list):
        raise AiaParseError("pData 缺失或非数组")

    records: List[dict] = []
    value_unparseable = 0

    for pi, prod in enumerate(pdata):
        if not isinstance(prod, dict):
            raise AiaParseError(f"pData[{pi}] 不是对象")
        pnm = prod.get("productNm")
        if not isinstance(pnm, dict):
            raise AiaParseError(f"pData[{pi}] 缺少 productNm 对象")
        name = _product_name(pnm)
        if not name:
            raise AiaParseError(f"pData[{pi}] productNm 无可用名称")

        for key in METRIC_KEYS:
            groups = prod.get(key)
            if groups is None:
                continue
            if not isinstance(groups, list):
                raise AiaParseError(f"pData[{pi}].{key} 非数组")
            for gi, grp in enumerate(groups):
                if not isinstance(grp, dict):
                    raise AiaParseError(f"pData[{pi}].{key}[{gi}] 不是对象")
                currency = _currency_label(grp.get("currency"))
                data = grp.get("data")
                if not isinstance(data, list):
                    raise AiaParseError(f"pData[{pi}].{key}[{gi}].data 非数组")
                for di, item in enumerate(data):
                    if not isinstance(item, dict):
                        raise AiaParseError(f"pData[{pi}].{key}[{gi}].data[{di}] 不是对象")
                    if "year" not in item or "ratio" not in item:
                        raise AiaParseError(f"pData[{pi}].{key}[{gi}].data[{di}] 缺 year/ratio")
                    try:
                        obs_raw, obs_year = parse_observation_year(item["year"])
                    except ValueError as e:
                        raise AiaParseError(f"pData[{pi}].{key}[{gi}].data[{di}] {e}")

                    raw = item["ratio"]
                    raw = "" if raw is None else str(raw)
                    norm = parse_ratio(raw)
                    if norm is None:
                        value_unparseable += 1
                    records.append({
                        "product_name_raw": name,
                        "metric_type": key,
                        "metric_type_raw": key,
                        "report_year": report_year,
                        "observation_year_raw": obs_raw,
                        "observation_year": obs_year,
                        "scope_currency_raw": currency,
                        "raw_value": raw,
                        "normalized_value": norm,
                        "product_id": None,
                    })

    status = "OK" if records else "ZERO_RECORD"
    return {
        "status": status,
        "report_year": report_year,
        "product_count": len(pdata),
        "records": records,
        "value_unparseable": value_unparseable,
    }
