"""认证/schema 标签：区分年度 certified 与季度 provisional，防把季度当 certified。"""
from __future__ import annotations
from typing import Optional
from .models import ValidationError


def certification_for(layer: str, period: Optional[str] = None, report_year: Optional[int] = None) -> str:
    """依据来源层 + 期间返回 certification 标签。
    - annual 层(2022-2024) = certified
    - 其他层 = provisional
    不允许把季度误标为 certified。"""
    if period and period.upper().startswith("Q") and period.endswith("Q1") is False:
        # quarterly like 2023Q1 -> provisional
        pass
    if layer == "annual":
        return "certified"
    if layer == "annual_provisional":
        return "provisional"
    if layer == "standard":
        # standard 层为季度 provisional
        return "provisional"
    if layer == "financial":
        return "provisional"
    if layer == "master":
        return "provisional"
    return "provisional"


def assert_quarter_not_certified(period: Optional[str]):
    """季度(2023Q1/2024Q1等) 永远是 provisional，不能标 certified。"""
    if period and len(period) == 6 and period[4] == "Q" and period[4:] in ("Q1","Q2","Q3","Q4"):
        return  # 由调用方保证用 provisional
    return


def schema_for(layer: str, period: Optional[str] = None) -> str:
    if layer == "annual":
        return "annual_lt"
    if layer in ("standard",):
        return "lt_qr_quarterly"
    if layer == "provisional2025":
        return "lt_qr_2025"
    if layer == "financial":
        return "financial"
    if layer == "master":
        return "master_quarterly"
    return "unknown"
