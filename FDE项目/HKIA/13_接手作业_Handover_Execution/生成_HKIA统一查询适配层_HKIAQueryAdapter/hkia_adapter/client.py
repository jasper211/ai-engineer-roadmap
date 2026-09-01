"""HKIAClient：统一入口。请求校验→单位→可比性→发布→查询→响应组装。"""
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
from .request_validation import validate_request, validate_supported_year
from .policy import PolicyEngine
from .comparability import Comparability
from .queries import QueryBuilder, ALLOWED_QUERY_TYPES, TEMPLATE_ID


class HKIAClient:
    def __init__(self, cfg, conns, catalog, identity, policy, comparability, builder):
        self.cfg = cfg; self.conns = conns; self.catalog = catalog
        self.identity = identity; self.policy = policy
        self.comparability = comparability; self.builder = builder

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

    def close(self): self.conns.close_all()
    def __enter__(self): return self
    def __exit__(self, *a): self.close(); return False

    def query(self, request: dict) -> dict:
        try:
            req = QueryRequest.from_dict(request)
            return self._execute(req)
        except (HkiaBlockedError, HkiaError) as e:
            return self._error_response(e, request)
        except Exception as e:
            return self._error_response(HkiaError(f"内部错误: {e}"), request)

    def _error_response(self, e, request):
        """统一错误响应：含完整契约键（required: ok/request_id/query_type/data/metadata/comparability/release/lineage）。"""
        base = e.to_dict(req_type=request.get("query_type", ""))
        md = {"metric_id": None, "metric_label": None, "period_basis": None, "entity_scope": None,
              "source_unit": None, "output_unit": None, "certification": None, "schema": None,
              "source_layer": None, "source_db_id": None, "source_tables": [], "data_version": "v1",
              "bridge_version": (self.identity.version if self.identity else None)}
        base["request_id"] = uuid.uuid4().hex[:12]
        base["data"] = []
        base["metadata"] = md
        base["comparability"] = {"status": "not_comparable" if getattr(e, "error_code", "")=="NOT_COMPARABLE_SCOPE" else "unknown",
                                 "reasons": [], "required_bridge": None}
        base["release"] = {"status": "blocked" if getattr(e, "error_code", "")=="RELEASE_BLOCKED_UNVALIDATED_SCOPE" else "not_allowed",
                           "level": None, "warnings": []}
        base["lineage"] = {"query_template_id": TEMPLATE_ID.get(request.get("query_type", ""), "ERROR"), "source_files": [], "checksums": []}
        return base

    def _execute(self, req: QueryRequest) -> dict:
        request_id = uuid.uuid4().hex[:12]
        qt = req.query_type
        if qt not in ALLOWED_QUERY_TYPES:
            raise ValidationError(f"不支持的 query_type: {qt}")

        # 纯服务查询（无需指标）
        if qt == "healthcheck":
            res = self.builder.build(req)
            return self._assemble(req, request_id, res, metric=None)
        if qt == "list_metrics":
            res = self.builder.build(req)
            return self._assemble(req, request_id, res, metric=None)
        if qt == "describe_metric":
            meta = self.catalog.get(req.metric_id)
            res = self.builder.build(req)
            return self._assemble(req, request_id, res, metric=meta)

        # 需要指标
        meta = self.catalog.get(req.metric_id)
        # 结构/值域校验
        validate_request(req, meta)
        # 年度支持校验（certified 层只支持 2022-2024）
        if meta.source_layer == "annual":
            validate_supported_year(req.period, [2022, 2023, 2024])
        # 单位（硬失败）
        out_unit = units_mod.resolve_output_unit(meta.unit, req.output_unit)
        # scope 校验已由 request_validation 统一处理
        # 可比性（比较类）
        comp = None
        if qt == "compare_periods":
            comp = self.comparability.check(meta)
        # 发布门禁
        release_claim = (req.filters or {}).get("publish_unvalidated_growth", False)
        is_l16v1 = (req.filters or {}).get("period_a") in ("2024","2025") and (req.filters or {}).get("period_b") in ("2024","2025") \
                   and (req.filters or {}).get("period_a") != (req.filters or {}).get("period_b")
        if qt == "compare_periods":
            release = self.policy.evaluate(req, metric_id=req.metric_id,
                                           cross_scope_l16_vs_l1=is_l16v1 or self._is_l16_vs_l1(req),
                                           release_scope_claim=release_claim, require_release_intent=True)
        else:
            release = self.policy.evaluate(req, metric_id=req.metric_id)
        # identity：公司跨期必须显式 identity_mode
        if meta.entity_scope == "insurer" and req.query_type in ("company_period_values", "compare_periods"):
            require_identity_mode(req.identity_mode)
        # 执行
        res = self.builder.build(req)
        # 单位换算（仅金额且源/目标均为金额时）
        res = self._convert_data_units(req, res, meta)
        return self._assemble(req, request_id, res, metric=meta, comparability=comp, release=release)

    def _is_l16_vs_l1(self, req):
        pa = (req.filters or {}).get("period_a"); pb = (req.filters or {}).get("period_b")
        return (pa == "2024" and pb == "2025") or (pa == "2025" and pb == "2024")

    def _convert_data_units(self, req, res, meta):
        src = meta.unit; out = req.output_unit
        if out and units_mod.normalize_unit(src) and units_mod.normalize_unit(out) \
           and units_mod.normalize_unit(src) in ("HKD_thousand","HKD_million") \
           and units_mod.normalize_unit(out) in ("HKD_thousand","HKD_million") \
           and units_mod.normalize_unit(src) != units_mod.normalize_unit(out):
            for d in res.get("data", []):
                if "value" in d:
                    d["value"] = units_mod.convert(d["value"], src, out)
                    d["unit"] = out
        return res

    def _assemble(self, req, request_id, res, metric=None, comparability=None, release=None, metadata_extra=None):
        meta = metric
        if meta is None and req.metric_id:
            try: meta = self.catalog.get(req.metric_id)
            except Exception: meta = None
        layer = meta.source_layer if meta else None
        period = req.period or (req.periods[0] if getattr(req, "periods", None) else None)
        cert = labels_mod.certification_for(layer or "", period)
        output_unit = req.output_unit or (meta.unit if meta else None)
        md = {
            "metric_id": req.metric_id if meta else None,
            "metric_label": (meta.label if meta else None),
            "period_basis": (meta.period_basis if meta else None),
            "entity_scope": (meta.entity_scope if meta else None),
            "source_unit": (meta.unit if meta else None),
            "output_unit": output_unit,
            "certification": cert,
            "schema": labels_mod.schema_for(layer or "", period),
            "source_layer": layer,
            "source_db_id": (res.get("source_db") or layer),
            "source_tables": [res.get("source_table")] if res.get("source_table") else ([meta.source_table] if meta and meta.source_table else []),
            "data_version": "v1",
            "bridge_version": (self.identity.version if self.identity else None),
        }
        if metadata_extra: md.update(metadata_extra)
        comp_dict = comparability.to_dict() if comparability else {"status":"comparable","reasons":[],"required_bridge":None}
        rel_dict = release.to_dict() if release else {"status":"allowed","level":None,"warnings":[]}
        # lineage
        qt = req.query_type
        src_file = None
        if self.identity and qt in ("company_ranking","company_period_values"):
            src_file = self.identity.map_path.name
        source_files = []
        if meta and meta.source_layer:
            try:
                from pathlib import Path
                p = Path(self.cfg.abs_path(meta.source_layer))
                source_files = [p.name]
            except Exception: pass
        checksums = []
        if source_files:
            import hashlib
            try:
                with open(self.cfg.abs_path(meta.source_layer),"rb") as f:
                    checksums.append(hashlib.sha256(f.read()).hexdigest()[:16])
            except Exception: pass
        lineage = {"query_template_id": TEMPLATE_ID.get(qt, "UNKNOWN"),
                   "source_files": source_files, "checksums": checksums}
        return {"ok": True, "request_id": request_id, "query_type": qt, "data": res.get("data", []),
                "metadata": md, "comparability": comp_dict, "release": rel_dict, "lineage": lineage}
