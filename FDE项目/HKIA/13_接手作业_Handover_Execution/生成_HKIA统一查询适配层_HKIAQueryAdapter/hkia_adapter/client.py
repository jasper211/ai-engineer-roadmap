"""HKIAClient：统一入口。组装 config/connections/catalog/queries/policy/comparability/labels/units。
执行请求→硬阻断→响应契约。"""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from .config import load_config, Config
from .connections import ConnectionManager
from .catalog import MetricCatalog
from .identity import IdentityBridge, require_identity_mode
from .models import (QueryRequest, QueryResponse, MetricMeta, HkiaError,
                     HkiaBlockedError, ValidationError, NotComparableError, ReleaseBlockedError)
from . import units as units_mod
from . import labels as labels_mod
from .policy import PolicyEngine
from .comparability import Comparability
from .queries import QueryBuilder, ALLOWED_QUERY_TYPES

TEMPLATE_VERSION = "Q1_MARKET_TREND_V1"


class HKIAClient:
    def __init__(self, cfg: Config, conns: ConnectionManager, catalog: MetricCatalog,
                 identity: IdentityBridge, policy: PolicyEngine, comparability: Comparability,
                 builder: QueryBuilder):
        self.cfg = cfg
        self.conns = conns
        self.catalog = catalog
        self.identity = identity
        self.policy = policy
        self.comparability = comparability
        self.builder = builder

    @classmethod
    def open_readonly(cls, hkia_root=None, cfg_dir=None, mount_identity=True) -> "HKIAClient":
        cfg = load_config(hkia_root, cfg_dir)
        conns = ConnectionManager(cfg)
        catalog = MetricCatalog()
        identity = IdentityBridge() if mount_identity else None
        policy = PolicyEngine()
        comparability = Comparability()
        builder = QueryBuilder(catalog=catalog, connections=conns, identity=identity)
        return cls(cfg, conns, catalog, identity, policy, comparability, builder)

    def close(self):
        self.conns.close_all()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False

    def query(self, request: dict) -> dict:
        try:
            req = QueryRequest.from_dict(request)
            return self._execute(req)
        except HkiaBlockedError as e:
            return e.to_dict(req_type=request.get("query_type", ""))
        except HkiaError as e:
            return e.to_dict(req_type=request.get("query_type", ""))
        except Exception as e:
            err = HkiaError(f"内部错误: {e}")
            return err.to_dict(req_type=request.get("query_type", ""))

    def _execute(self, req: QueryRequest) -> dict:
        request_id = uuid.uuid4().hex[:12]
        qt = req.query_type
        if qt not in ALLOWED_QUERY_TYPES:
            raise ValidationError(f"不支持的 query_type: {qt}")
        if qt == "healthcheck":
            res = self.builder.build(req)
            return self._assemble(req, request_id, res, metric=None, metadata_extra={"healthcheck": True})
        if qt == "list_metrics":
            res = self.builder.build(req)
            return self._assemble(req, request_id, res, metric=None)
        if qt == "describe_metric":
            meta = self.catalog.get(req.metric_id)
            res = self.builder.build(req)
            return self._assemble(req, request_id, res, metric=meta)
        # 需要指标
        meta = self.catalog.get(req.metric_id)
        # 单位
        out_unit = units_mod.validate_output_unit(meta.unit, req.output_unit)
        # 可比性（仅比较类）
        comp = None
        if qt == "compare_periods":
            comp = self.comparability.check(meta)
        # 发布门禁（比较/发布）
        release = None
        release_claim = (req.filters or {}).get("publish_unvalidated_growth", False)
        if qt in ("compare_periods",):
            release = self.policy.evaluate(req, metric_id=req.metric_id,
                                           cross_scope_l16_vs_l1=(req.filters or {}).get("l16_vs_l1", False) or
                                           self._is_l16_vs_l1(req), release_scope_claim=release_claim,
                                           require_release_intent=True)
        else:
            release = self.policy.evaluate(req, metric_id=req.metric_id)
        # identity
        if qt in ("company_period_values", "compare_periods") and meta.entity_scope == "insurer":
            require_identity_mode(req.identity_mode)
        # 执行
        res = self.builder.build(req)
        # 若输出单位与源不同则转换
        res = self._convert_data_units(req, res, meta)
        return self._assemble(req, request_id, res, metric=meta, comparability=comp, release=release)

    def _is_l16_vs_l1(self, req):
        pa = (req.filters or {}).get("period_a"); pb = (req.filters or {}).get("period_b")
        if pa == "2024" and pb == "2025": return True
        if pa == "2025" and pb == "2024": return True
        return False

    def _convert_data_units(self, req, res, meta):
        src = meta.unit
        out = req.output_unit
        if out and units_mod.normalize_unit(src) != units_mod.normalize_unit(out):
            # 只对金额转换
            if units_mod.normalize_unit(src) in ("HKD_thousand", "HKD_million") and \
               units_mod.normalize_unit(out) in ("HKD_thousand", "HKD_million"):
                for d in res.get("data", []):
                    if "value" in d:
                        d["value"] = units_mod.convert(d["value"], src, out)
                        d["unit"] = out
        return res

    def _assemble(self, req, request_id, res, metric=None, comparability=None, release=None, metadata_extra=None):
        # build metadata
        meta = metric
        if meta is None and req.metric_id:
            try: meta = self.catalog.get(req.metric_id)
            except Exception: meta = None
        layer = meta.source_layer if meta else None
        period = req.period or (req.periods[0] if req.periods else None)
        md = {
            "metric_id": req.metric_id,
            "metric_label": (meta.label if meta else None),
            "period_basis": (meta.period_basis if meta else None),
            "entity_scope": (meta.entity_scope if meta else None),
            "source_unit": (meta.unit if meta else None),
            "output_unit": (req.output_unit if req.output_unit else (meta.unit if meta else None)),
            "certification": labels_mod.certification_for(layer or "", period),
            "schema": labels_mod.schema_for(layer or "", period),
            "source_layer": layer,
            "source_db": layer,
            "source_tables": [meta.source_table] if meta and meta.source_table else [],
            "data_version": "v1",
            "bridge_version": (self.identity.version if self.identity else None),
        }
        if metadata_extra: md.update(metadata_extra)
        if self.identity and meta and meta.source_layer in ("annual", "provisional2025"):
            md["bridge_note"] = "company 跨年须用 identity_mode=entity/lineage；裸公司名默认禁止"
        comp_dict = comparability.to_dict() if comparability else {"status": "comparable", "reasons": [], "required_bridge": None}
        rel_dict = release.to_dict() if release else {"status": "allowed", "level": None, "warnings": []}
        lineage = {"query_template_id": TEMPLATE_VERSION, "source_files": [], "checksums": []}
        data = res.get("data", [])
        return {"ok": True, "request_id": request_id, "query_type": req.query_type, "data": data,
                "metadata": md, "comparability": comp_dict, "release": rel_dict, "lineage": lineage}
