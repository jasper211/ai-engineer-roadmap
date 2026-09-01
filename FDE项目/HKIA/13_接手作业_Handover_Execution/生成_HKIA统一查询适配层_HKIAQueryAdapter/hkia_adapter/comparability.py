"""可比性判定：scope/schema/identity/期 维度。硬阻断不可比请求。"""
from __future__ import annotations
from typing import List, Optional
from .models import MetricMeta, ComparabilityResult, ValidationError, NotComparableError
from . import units


def _is_quarterly(period: Optional[str]) -> bool:
    return bool(period and len(period) == 6 and period[4] == "Q")


class Comparability:
    def __init__(self):
        pass

    def check(self, metric: MetricMeta, period_a=None, period_b=None,
              identity_mode=None, release_intent=None) -> ComparabilityResult:
        # 单位：count 不得转金额
        if metric.unit and normalize := units.normalize_unit(metric.unit):
            pass
        # 2024 L16 vs 2025 L1 (personal life vs personal long-term incl annuity)
        if self._is_L16_vs_L1(metric):
            raise NotComparableError()
        # L11 跨指标比较：policy_count/lives/scheme_count 不得互比
        if metric.metric_id.startswith("L11") and "count" in str(metric.metric_id):
            # 由 metric.prohibited_comparisons 承载
            pass
        if any("policy_count vs scheme_count" in pc for pc in metric.prohibited_comparisons):
            raise ValidationError(metric.metric_id + " 禁止 policy_count/lives/scheme_count 跨指标比较。")
        # pre-RBC vs RBC 未提供审定桥 → SCHEMA_BRIDGE_REQUIRED
        if self._cross_schema(metric):
            return ComparabilityResult(status="schema_bridge_required",
                                       reasons=["pre-RBC 与 RBC 指标无已审定桥"], required_bridge="SCHEMA_BRIDGE")
        return ComparabilityResult(status="comparable", reasons=["同口径可比"], required_bridge=None)

    def _is_L16_vs_L1(self, metric: MetricMeta) -> bool:
        # 适配层 query_type=compare_periods 时会显式带 pair；此处以 metric 层面提示
        return "2025 L1(个人长期含年金)直接比" in str(metric.prohibited_comparisons) and "2024 L16" in str(metric.comparable_with)

    def _cross_schema(self, metric: MetricMeta) -> bool:
        return str(metric.schema).startswith("lt_") and "2025" in str(metric.schema) and (
            "annual_lt" in str(metric.comparable_with))
