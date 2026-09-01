"""指标目录：加载 metric_catalog.json，提供指标元数据查找。缺项即失败。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional
from .models import MetricMeta, ValidationError


class MetricCatalog:
    def __init__(self, path: Optional[Path] = None):
        base = Path(__file__).resolve().parents[1] / "config"
        self.path = path or (base / "metric_catalog.json")
        self._raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._metrics: Dict[str, MetricMeta] = {}
        for mid, m in self._raw.get("metrics", {}).items():
            self._metrics[mid] = MetricMeta(
                metric_id=mid, label=m.get("label",""), source_layer=m.get("source_layer"),
                source_table=m.get("source_table"), unit=m.get("unit"),
                entity_scope=m.get("entity_scope"), period_basis=m.get("period_basis"),
                certification_rule=m.get("certification_rule"), schema=m.get("schema"),
                supported_query_types=list(m.get("supported_query_types", [])),
                comparable_with=list(m.get("comparable_with", [])),
                prohibited_comparisons=list(m.get("prohibited_comparisons", [])),
                aggregation=m.get("aggregation"), source_definition=m.get("source_definition"),
                release_policy_id=m.get("release_policy_id"),
                source_filter=m.get("source_filter") or {},
            )

    def get(self, metric_id: str) -> MetricMeta:
        if metric_id not in self._metrics:
            raise ValidationError(f"指标目录无此指标: {metric_id!r}（不允许临时猜测）")
        return self._metrics[metric_id]

    def has(self, metric_id: str) -> bool:
        return metric_id in self._metrics

    def list_ids(self) -> List[str]:
        return sorted(self._metrics.keys())

    def describe(self, metric_id: str) -> MetricMeta:
        return self.get(metric_id)
