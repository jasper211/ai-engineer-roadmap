"""
HKIA 统一查询适配层 v1
========================
本地、只读、可测试的语义查询适配层。
允许调用白名单语义查询，禁止任意 SQL、单位/认证/scope 覆盖。
"""
from .config import Config, load_config
from .connections import ConnectionManager
from .models import (
    QueryRequest, QueryResponse, MetricMeta, ComparabilityResult,
    ReleaseResult, LineageResult, HkiaError, HkiaBlockedError,
)
from .client import HKIAClient

__all__ = [
    "Config", "load_config", "ConnectionManager",
    "QueryRequest", "QueryResponse", "MetricMeta", "ComparabilityResult",
    "ReleaseResult", "LineageResult", "HkiaError", "HkiaBlockedError",
    "HKIAClient",
]
__version__ = "1.0.0"
