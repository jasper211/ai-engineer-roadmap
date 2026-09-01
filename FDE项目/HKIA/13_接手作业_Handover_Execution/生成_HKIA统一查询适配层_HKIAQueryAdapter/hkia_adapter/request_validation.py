"""请求结构与值域校验：类型、枚举、limit/offset、periods、filters、scope、query_type×metric、fund_scope。"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .models import QueryRequest, MetricMeta, ValidationError

# 已知 filter 白名单（子字段）
KNOWN_FILTER_KEYS = {"entity", "fund_scope", "period_a", "period_b", "metric_b", "publish_unvalidated_growth"}
KNOWN_FUND_SCOPES = {"industry_total", "long_term", "participating_long_term", "general_business"}


def validate_request(req: QueryRequest, meta: Optional[MetricMeta]):
    # filters 必须为 dict
    if req.filters is not None:
        if not isinstance(req.filters, dict):
            raise ValidationError("filters 必须为对象(dict)。")
        unknown = set(req.filters) - KNOWN_FILTER_KEYS
        if unknown:
            raise ValidationError(f"filters 含未知字段: {sorted(unknown)}")
        # fund_scope 白名单
        if "fund_scope" in req.filters and req.filters["fund_scope"] not in KNOWN_FUND_SCOPES:
            raise ValidationError(f"fund_scope 不合法: {req.filters['fund_scope']!r}")
    # limit / offset 值域
    if req.limit is not None:
        if not isinstance(req.limit, int) or isinstance(req.limit, bool):
            raise ValidationError("limit 必须为整数。")
        if req.limit <= 0 or req.limit > 1000:
            raise ValidationError("limit 必须在 1..1000 之间。")
    if req.offset is not None:
        if not isinstance(req.offset, int) or isinstance(req.offset, bool) or req.offset < 0 or req.offset > 1000000:
            raise ValidationError("offset 必须在 0..1000000 之间。")
    # include_zero 必须为 bool
    if not isinstance(req.include_zero, bool):
        raise ValidationError("include_zero 必须为布尔值。")
    # periods 必须为数组 + 每项期间匹配
    if req.periods is not None:
        if not isinstance(req.periods, list) or not all(isinstance(x, str) for x in req.periods):
            raise ValidationError("periods 必须为字符串数组。")
        if meta and meta.period_basis:
            for per in req.periods:
                if not _period_matches(per, meta.period_basis):
                    raise ValidationError(f"期间 {per!r} 不符合指标 period_basis={meta.period_basis}。")
    # 单个 period 匹配
    if meta and req.period and meta.period_basis and not _period_matches(req.period, meta.period_basis):
        raise ValidationError(f"期间 {req.period!r} 不符合指标 period_basis={meta.period_basis}。")
    # query_type × metric 兼容
    if meta and req.query_type not in (meta.supported_query_types or []):
        raise ValidationError(f"指标 {req.metric_id} 不支持 query_type={req.query_type}（支持: {sorted(meta.supported_query_types or [])}）。")
    # scope 白名单 + 覆盖防护（仅显式指定时）
    if req.entity_scope is not None:
        if req.entity_scope not in ("market_total", "insurer", "fund", ""):
            raise ValidationError(f"entity_scope 不合法: {req.entity_scope!r}")
        if meta and req.entity_scope != meta.entity_scope:
            raise ValidationError(
                f"entity_scope={req.entity_scope!r} 与指标 {meta.metric_id} 的实体范围 {meta.entity_scope!r} 不一致，禁止覆盖。")
    # identity_mode 校验
    if req.query_type in ("company_period_values", "compare_periods") and req.identity_mode is not None \
       and req.identity_mode not in ("entity", "lineage"):
        raise ValidationError(f"identity_mode 必须为 entity 或 lineage，收到 {req.identity_mode!r}。")


def _period_matches(period: str, basis: str) -> bool:
    if basis in ("annual_certified", "annual_provisional"):
        return len(period) == 4 and period.isdigit()
    if basis in ("quarterly_ytd", "quarterly_snapshot"):
        return len(period) == 6 and period[4] == "Q" and period[5] in "1234"
    return True


def validate_supported_year(period: Optional[str], supported_years: List[int]):
    if period and "Q" not in str(period):
        if str(period).isdigit():
            y = int(period)
            if y not in supported_years:
                raise ValidationError(f"当前源层不支持年度 {y}（支持: {supported_years}）。")
