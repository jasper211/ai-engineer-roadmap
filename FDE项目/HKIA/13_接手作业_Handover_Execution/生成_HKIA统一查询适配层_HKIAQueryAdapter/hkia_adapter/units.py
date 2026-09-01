"""单位标准化：只允许 HKD_thousand<->HKD_million 转换；count 不得转金额；空/未知单位硬失败。"""
from __future__ import annotations
from typing import Optional
from .models import ValidationError

MONEY = ("HKD_thousand", "HKD_million")
ALIASES = {"千港元": "HKD_thousand", "hkd_thousand": "HKD_thousand",
           "HKD_million": "HKD_million", "百万港元": "HKD_million",
           "count": "count", "Count": "count"}


def normalize_unit(u: Optional[str]) -> Optional[str]:
    """归一化已知单位别名；未知/空返回 None（由调用方决定是否硬失败）。"""
    if u is None:
        return None
    u = str(u).strip()
    if u in ALIASES:
        return ALIASES[u]
    if u == "count":
        return "count"
    if u in MONEY:
        return u
    return None  # 未知


def is_money(u: Optional[str]) -> bool:
    return normalize_unit(u) in MONEY


def is_count(u: Optional[str]) -> bool:
    return normalize_unit(u) == "count"


def convert(value, from_unit: str, to_unit: str) -> float:
    """金额单位换算；count 与金额、未知单位一律硬失败。"""
    f, t = normalize_unit(from_unit), normalize_unit(to_unit)
    if f is None or t is None:
        raise ValidationError(f"未知或空单位: from={from_unit!r} to={to_unit!r}")
    if f == "count" or t == "count":
        raise ValidationError("count 不得转换为金额单位，也不得参与金额聚合。")
    if f == t:
        return float(value)
    if f == "HKD_thousand" and t == "HKD_million":
        return float(value) / 1000.0
    if f == "HKD_million" and t == "HKD_thousand":
        return float(value) * 1000.0
    raise ValidationError(f"不支持的金额单位转换: {f} -> {t}")


def resolve_output_unit(metric_unit: Optional[str], requested: Optional[str]) -> str:
    """解析最终输出单位，并对不合法组合硬失败。
    规则：
      - 指标单位必须已知（count 或金额）。
      - count 指标：requested 只能为 None 或 count；其他一律失败。
      - 金额指标：requested 为 None/金额；requested=count/未知 一律失败。"""
    src = normalize_unit(metric_unit)
    if src is None:
        raise ValidationError(f"指标无有效单位: {metric_unit!r}")
    if src == "count":
        if requested is None:
            return "count"
        if normalize_unit(requested) == "count":
            return "count"
        raise ValidationError("count 指标不接受金额或未知输出单位。")
    # 金额指标
    if requested is None:
        return src
    req = normalize_unit(requested)
    if req is None:
        raise ValidationError(f"未知输出单位: {requested!r}")
    if req == "count":
        raise ValidationError("金额指标不接受 count 输出单位。")
    return req
