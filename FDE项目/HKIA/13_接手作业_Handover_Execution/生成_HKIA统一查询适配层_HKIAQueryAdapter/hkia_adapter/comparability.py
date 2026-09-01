"""可比性判定：scope/schema/L11/identity 维度。硬阻断不可比请求。"""
from __future__ import annotations
from typing import Optional, List
from .models import MetricMeta, ComparabilityResult, ValidationError, NotComparableError

# RBC 制度切换：年度层 2024=RBC；2022/2023=pre-RBC。季度 2024Q3 起=RBC。
RBC_YEARS = {2024}
PRE_RBC_YEARS = {2022, 2023}
RBC_QUARTER_CUTOFF = "2024Q3"

# L11 相关数量类 indicator 关键词（不可跨指标互比）
L11_COUNT_KW = ("policy_count", "lives", "scheme_count", "受保人", "计划数")


class Comparability:
    def __init__(self):
        pass

    def check(self, metric: MetricMeta, period_a=None, period_b=None,
              identity_mode=None) -> ComparabilityResult:
        # L11 数量类跨指标比较禁止
        if self._is_l11_count_mix(metric):
            raise ValidationError(f"{metric.metric_id} 禁止 policy_count/lives/scheme_count(保单数/受保人数/计划数) 跨指标比较。")
        # pre-RBC ↔ RBC 无审定桥 → SCHEMA_BRIDGE_REQUIRED
        if self._cross_schema_same_metric(metric, period_a, period_b):
            return ComparabilityResult(status="schema_bridge_required",
                                       reasons=["pre-RBC 与 RBC 指标无已审定桥"], required_bridge="SCHEMA_BRIDGE")
        # 2024 L16 vs 2025 L1 scope 不可比
        if self._is_l16_vs_l1(metric, period_a, period_b):
            raise NotComparableError()
        return ComparabilityResult(status="comparable", reasons=["同口径可比"], required_bridge=None)

    def _is_l11_count_mix(self, metric) -> bool:
        if metric is None:
            return False
        for pc in metric.prohibited_comparisons or []:
            lc = pc.lower()
            if any(k in lc for k in ("policy_count", "scheme_count", "lives")):
                return True
        # 指标名含 L11 且 unit=count 且属多种数量
        return "L11" in str(metric.metric_id)

    def _cross_schema_same_metric(self, metric, pa, pb) -> bool:
        # 若涉及跨年比较(compare_periods)且两期跨 RBC 断点，且无审定桥 → 需 bridge
        y_a = _year_of(pa); y_b = _year_of(pb)
        if y_a is not None and y_b is not None and y_a != y_b:
            in_pre = (y_a in PRE_RBC_YEARS) or (y_b in PRE_RBC_YEARS)
            in_rbc = (y_a in RBC_YEARS) or (y_b in RBC_YEARS)
            if in_pre and in_rbc:
                return True
        return False

    def _is_l16_vs_l1(self, metric, pa, pb):
        l16 = (metric is not None) and ("L16" in str(metric.metric_id) or "ANNUAL_L16" in str(metric.metric_id))
        l1 = "PROV2025" in str(metric.metric_id) or (pa == "2025" and pb == "2024") or (pa == "2024" and pb == "2025")
        return (l16 and l1)


def _year_of(period) -> Optional[int]:
    if not period:
        return None
    p = str(period)
    digits = "".join(ch for ch in p if ch.isdigit())
    if len(digits) >= 4:
        try:
            return int(digits[:4])
        except ValueError:
            return None
    return None
