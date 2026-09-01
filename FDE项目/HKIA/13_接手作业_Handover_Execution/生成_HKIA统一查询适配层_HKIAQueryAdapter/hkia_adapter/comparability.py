"""可比性判定：scope/schema/identity 维度。硬阻断不可比请求。"""
from __future__ import annotations
from typing import Optional
from .models import MetricMeta, ComparabilityResult, ValidationError, NotComparableError


class Comparability:
    def __init__(self):
        pass

    def check(self, metric: MetricMeta, period_a=None, period_b=None) -> ComparabilityResult:
        # L11 跨指标比较（policy_count/lives/scheme_count）禁止
        for pc in metric.prohibited_comparisons or []:
            if "policy_count" in pc and ("scheme_count" in pc or "lives" in pc):
                raise ValidationError(metric.metric_id + " 禁止 policy_count/lives/scheme_count 跨指标比较。")
        # 2024 L16 vs 2025 L1 scope 不可比
        if self._is_l16_vs_l1(metric, period_a, period_b):
            raise NotComparableError()
        return ComparabilityResult(status="comparable", reasons=["同口径可比"], required_bridge=None)

    def _is_l16_vs_l1(self, metric, pa, pb):
        l16 = "L16" in str(metric.metric_id) or "ANNUAL_L16" in str(metric.metric_id)
        l1 = "PROV2025" in str(metric.metric_id) or (pa == "2025" and pb == "2024") or (pa == "2024" and pb == "2025")
        return (l16 and l1)
