"""统一请求/响应契约、指标元数据、可比性/发布/沿革结果、错误类型。"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


class HkiaError(Exception):
    error_code = "HKIA_ERROR"
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
    def to_dict(self, req_type: str = ""):
        return {"ok": False, "error_code": self.error_code, "message": self.message,
                "blocked_by": None, "suggestion": None, "query_type": req_type}


class HkiaBlockedError(HkiaError):
    error_code = "BLOCKED"
    def __init__(self, message: str, blocked_by: str = "", suggestion: str = "", applicability: str = ""):
        super().__init__(message)
        self.blocked_by = blocked_by
        self.suggestion = suggestion
        self.applicability = applicability
    def to_dict(self, req_type: str = ""):
        return {"ok": False, "error_code": self.error_code, "message": self.message,
                "blocked_by": self.blocked_by, "suggestion": self.suggestion,
                "query_type": req_type}


class ValidationError(HkiaError):
    error_code = "VALIDATION_ERROR"


class NotComparableError(HkiaBlockedError):
    error_code = "NOT_COMPARABLE_SCOPE"

    def __init__(self, message="2024 L16 与 2025 L1 口径不同，不可计算同比增长。", applicability="2024 L16 vs 2025 L1"):
        super().__init__(message, blocked_by="scope", suggestion="改用已验收的市场级口径或等待范围等价验收。", applicability=applicability)


class ReleaseBlockedError(HkiaBlockedError):
    error_code = "RELEASE_BLOCKED_UNVALIDATED_SCOPE"
    def __init__(self, message="+65.4% 尚未通过范围等价验收，不得发布为已验收的同口径增长。", applicability="比较/发布同口径增长"):
        super().__init__(message, blocked_by="release_policy", suggestion="仅可返回待验证异口径试算并明确标注。", applicability=applicability)


@dataclass
class QueryRequest:
    query_type: str
    metric_id: Optional[str] = None
    period: Optional[str] = None
    periods: Optional[List[str]] = None
    entity_scope: str = "market_total"
    limit: Optional[int] = None
    offset: Optional[int] = None
    output_unit: Optional[str] = None
    include_zero: bool = False
    identity_mode: Optional[str] = None
    release_intent: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict):
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        known = {k: v for k, v in d.items() if k in allowed}
        unknown = {k for k in d if k not in allowed}
        if unknown:
            raise ValidationError(f"未知请求字段: {sorted(unknown)}")
        return cls(**known)


@dataclass
class MetricMeta:
    metric_id: str
    label: str
    source_layer: Optional[str] = None
    source_table: Optional[str] = None
    unit: Optional[str] = None
    entity_scope: Optional[str] = None
    period_basis: Optional[str] = None
    certification_rule: Optional[str] = None
    schema: Optional[str] = None
    supported_query_types: List[str] = field(default_factory=list)
    comparable_with: List[str] = field(default_factory=list)
    prohibited_comparisons: List[str] = field(default_factory=list)
    aggregation: Optional[str] = None
    source_definition: Optional[str] = None
    release_policy_id: Optional[str] = None
    source_filter: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComparabilityResult:
    status: str
    reasons: List[str] = field(default_factory=list)
    required_bridge: Optional[str] = None


@dataclass
class ReleaseResult:
    status: str
    level: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class LineageResult:
    query_template_id: str
    source_files: List[str] = field(default_factory=list)
    checksums: List[str] = field(default_factory=list)


@dataclass
class MetricValue:
    value: Any
    unit: str
    period: Optional[str] = None
    entity: Optional[str] = None
    entity_key: Optional[str] = None
    entity_scope: Optional[str] = None
    certification: Optional[str] = None
    schema: Optional[str] = None
    record_status: Optional[str] = None


@dataclass
class QueryResponse:
    ok: bool = True
    request_id: str = ""
    query_type: str = ""
    data: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    comparability: Dict[str, Any] = field(default_factory=dict)
    release: Dict[str, Any] = field(default_factory=dict)
    lineage: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
