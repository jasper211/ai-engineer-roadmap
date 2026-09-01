"""发布策略门禁：release gates 与策略配置。硬阻断不可发布/不可比请求。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional
from .models import ReleaseResult, QueryRequest, ReleaseBlockedError, NotComparableError, ValidationError


class PolicyEngine:
    def __init__(self, path: Optional[Path] = None):
        if path:
            self.path = Path(path)
        else:
            base = Path(__file__).resolve().parents[1] / "config"
            pkg = Path(__file__).resolve().parent / "_assets" / "config" / "release_policies.json"
            cand = base / "release_policies.json"
            self.path = cand if cand.exists() else pkg
        self.policies = json.loads(self.path.read_text(encoding="utf-8")).get("policies", {})

    def evaluate(self, req: QueryRequest, metric_id=None, output_unit=None,
                 cross_scope_l16_vs_l1=False, release_scope_claim=None,
                 require_release_intent=False) -> ReleaseResult:
        # 硬阻断 1: 请求发布 +65.4% 同口径增长（未验收）
        if release_scope_claim is not None and release_scope_claim is True:
            raise ReleaseBlockedError()
        # 硬阻断 2: 2024 L16 vs 2025 L1 比较
        if cross_scope_l16_vs_l1:
            raise NotComparableError()
        # release_intent：仅比较/发布类请求必须携带
        if require_release_intent and req.release_intent is None:
            raise ValidationError("比较/发布请求必须携带 release_intent。")
        # release_intent 白名单（若提供了才校验；比较类已在前面要求必需）
        allowed_intent = {"internal_analysis", "research", "draft", "reporting", "client_review"}
        if req.release_intent is not None and req.release_intent not in allowed_intent:
            raise ValidationError(f"release_intent 不合法: {req.release_intent!r}")
        level = "internal_analysis"
        warnings = []
        if metric_id and metric_id.startswith("ANNUAL_L16"):
            warnings.append("年度 L16 certified 可分开展示两年，跨 schema 同口径增长未验收，不得发布增长率。")
            # 同口径增长：若 intent 高到 reporting 且含增长率，阻断
            if req.release_intent in ("reporting", "client_review"):
                raise ReleaseBlockedError(message="年度 L16 跨年同口径增长未验收，报告/客户意图不发布增长率。",
                                          blocked_by="release_policy")
        return ReleaseResult(status="allowed", level=level, warnings=warnings)

    def blocked_level(self) -> str:
        return "blocked"
