"""单位标准化：只允许 HKD_thousand<->HKD_million 转换；count 不得转金额；空/未知单位拒绝。"""
from __future__ import annotations
from typing import Optional
from .models import ValidationError

MONEY_UNITS = {"HKD_thousand", "hkd_thousand", "HKD_million", "千港元", "HKD_million(百万港元)"}
COUNT_UNITS = {"count", "Count"}
KNOWN_ALIASES = {"千港元": "HKD_thousand", "hkd_thousand": "HKD_thousand",
                 "HKD_million": "HKD_million", "百万港元": "HKD_million"}


def normalize_unit(u: Optional[str]) -> Optional[str]:
    """把已知别名归一为 HKD_thousand / HKD_million / count。空/未知返回 None(拒绝)。"""
    if u is None:
        return None
    u = str(u).strip()
    if u in KNOWN_ALIASES:
        return KNOWN_ALIASES[u]
    if u.lower() in ("hkd_thousand", "hkd_million"):
        return "HKD_thousand" if u.lower()=="hkd_thousand" else "HKD_million"
    if u.lower() == "count":
        return "count"
    return None  # 未知单位


def is_money(u: Optional[str]) -> bool:
    n = normalize_unit(u)
    return n in ("HKD_thousand", "HKD_million")


def is_count(u: Optional[str]) -> bool:
    return normalize_unit(u) == "count"


def convert(value, from_unit: str, to_unit: str) -> float:
    """金额单位转换。count 到金额报错；只允许 HKD_thousand<->HKD_million。"""
    f = normalize_unit(from_unit)
    t = normalize_unit(to_unit)
    if f is None or t is None:
        raise ValidationError(f"未知或空单位: from={from_unit!r} to={to_unit!r}")
    if f == "count" or t == "count":
        raise ValidationError("count 不得转换为金额单位，也不得参与金额聚合。")
    # both money
    if f == t:
        return float(value)
    # HKD_thousand -> HKD_million (divide by 1000)
    if f == "HKD_thousand" and t == "HKD_million":
        return float(value) / 1000.0
    if f == "HKD_million" and t == "HKD_thousand":
        return float(value) * 1000.0
    raise ValidationError(f"不支持的金额单位转换: {f} -> {t}")


def validate_output_unit(metric_unit: Optional[str], requested: Optional[str]):
    """校验请求 is 输出单位是否合法。指标 count 不接受金额单位。"""
    metric_n = normalize_unit(metric_unit)
    if metric_n is None:
        raise ValidationError(f"指标无有效单位: {metric_unit!r}")
    if metric_n == "count":
        if requested is not None and normalize_unit(requested) not in (None, "count"):
            raise ValidationError("count 指标不接受金额输出单位。")
        return "count"
    if requested is None:
        return metric_n
    req_n = normalize_unit(requested)
    if req_n is None:
        raise ValidationError(f"未知输出单位: {requested!r}")
    return req_n
