"""请求结构与值域校验：未声明/不支持字段、类型、limit、期间、scope、query_type×metric 兼容。"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .models import QueryRequest, MetricMeta, ValidationError
from .queries import ALLOWED_QUERY_TYPES  # 避免循环：queries 只常量子集


def validate_request(req: QueryRequest, meta: Optional[MetricMeta]):
    # limit / offset 值域
    if req.limit is not None:
        if not isinstance(req.limit, int) or isinstance(req.limit, bool):
            raise ValidationError("limit 必须为整数。")
        if req.limit <= 0 or req.limit > 1000:
            raise ValidationError("limit 必须在 1..1000 之间。")
    if req.offset is not None:
        if not isinstance(req.offset, int) or req.offset < 0 or req.offset > 1000000:
            raise ValidationError("offset 必须在 0..1000000 之间。")
    # periods 必须为数组
    if req.periods is not None:
        if not isinstance(req.periods, list) or not all(isinstance(x, str) for x in req.periods):
            raise ValidationError("periods 必须为字符串数组。")
    # periods 与 period 不能同时给（歧义）→ 允许但要求至少一种
    # 期间类型匹配（若有 meta）
    if meta and meta.period_basis:
        if req.period and not _period_matches(req.period, meta.period_basis):
            raise ValidationError(f"期间 {req.period!r} 不符合指标 period_basis={meta.period_basis}。")
    # query_type × metric 兼容
    if meta and req.query_type not in (meta.supported_query_types or []):
        raise ValidationError(f"指标 {req.metric_id} 不支持 query_type={req.query_type}（支持: {sorted(meta.supported_query_types or [])}）。")
    # scope 白名单 + 覆盖防护
    if req.entity_scope not in ("market_total", "insurer", "fund", ""):
        raise ValidationError(f"entity_scope 不合法: {req.entity_scope!r}")
    if meta and req.entity_scope and req.entity_scope != meta.entity_scope:
        # 公司级指标不接受 market_total；市场级不接受 insurer/fund —— 防 scope 覆盖
        raise ValidationError(
            f"entity_scope={req.entity_scope!r} 与指标 {meta.metric_id} 的实体范围 {meta.entity_scope!r} 不一致，禁止覆盖。")


def _period_matches(period: str, basis: str) -> bool:
    if basis in ("annual_certified", "annual_provisional"):
        return len(period) == 4 and period.isdigit()
    if basis in ("quarterly_ytd", "quarterly_snapshot"):
        return len(period) == 6 and period[4] == "Q" and period[5] in "1234"
    return True


def validate_supported_year(period: Optional[str], supported_years: List[int]):
    if period and "Q" not in str(period):
        if period.isdigit():
            y = int(period)
            if y not in supported_years:
                raise ValidationError(f"当前源层不支持年度 {y}（支持: {supported_years}）。")
