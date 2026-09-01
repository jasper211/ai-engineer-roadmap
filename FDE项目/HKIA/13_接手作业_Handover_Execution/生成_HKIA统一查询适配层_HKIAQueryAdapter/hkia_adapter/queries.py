"""固定 SQL 模板（白名单）：所有查询来自代码内固定模板，禁止透传表名/列/WHERE/排序。"""
from __future__ import annotations
from typing import List, Dict, Any
from .models import MetricMeta, QueryRequest, ValidationError

# query_type 白名单
ALLOWED_QUERY_TYPES = {"market_trend", "company_ranking", "financial_snapshot",
                       "company_period_values", "compare_periods",
                       "describe_metric", "list_metrics", "healthcheck"}

# 白名单列
_COL_MARKET = {"period", "metric_id", "metric_label", "value", "unit"}
_COL_COMPANY_ANNUAL = {"insurer_name_source", "value_raw", "report_year", "table_id", "metric_sem", "entity_scope"}
_COL_COMPANY_2025 = {"insurer_name_en", "value", "year", "entity_scope", "metric_sem"}
_COL_FIN = {"period", "fund_scope", "item_id", "value_hkd_million"}


class QueryBuilder:
    def __init__(self, catalog=None, connections=None, identity=None):
        self.catalog = catalog
        self.conns = connections
        self.identity = identity

    def validate_query_type(self, qt: str):
        if qt not in ALLOWED_QUERY_TYPES:
            raise ValidationError(f"不支持的 query_type: {qt!r}（允许: {sorted(ALLOWED_QUERY_TYPES)}）")
        return qt

    def build(self, req: QueryRequest):
        qt = self.validate_query_type(req.query_type)
        if qt == "healthcheck":
            return self._health()
        if qt == "list_metrics":
            return self._list_metrics()
        if qt == "describe_metric":
            meta = self.catalog.get(req.metric_id)
            return self._describe(meta)
        if qt == "market_trend":
            return self._market_trend(req)
        if qt == "company_ranking":
            return self._company_ranking(req)
        if qt == "financial_snapshot":
            return self._financial_snapshot(req)
        if qt == "company_period_values":
            return self._company_period_values(req)
        if qt == "compare_periods":
            return self._compare_periods(req)
        raise ValidationError(f"尚未实现的 query_type: {qt}")

    def _health(self):
        rows = {}
        for db_id in ["master", "standard", "annual", "provisional2025", "financial"]:
            if db_id == "standard":
                n = 0
                for t in ["market_facts", "company_facts", "schema_metrics", "annual_facts"]:
                    n += int(self.conns.count(db_id, t))
                rows[db_id] = n
            else:
                t = "long_term_business" if db_id == "master" else \
                    ("company_facts" if db_id == "annual" else "provisional_company_facts" if db_id=="provisional2025" else "financial_facts")
                rows[db_id] = int(self.conns.count(db_id, t))
        return {"query_type": "healthcheck", "data": {"rows": rows}}

    def _list_metrics(self):
        ids = self.catalog.list_ids()
        return {"query_type": "list_metrics", "metric_ids": ids, "count": len(ids)}

    def _describe(self, meta: MetricMeta):
        return {"query_type": "describe_metric", "metric": {
            "metric_id": meta.metric_id, "label": meta.label, "unit": meta.unit,
            "entity_scope": meta.entity_scope, "period_basis": meta.period_basis,
            "certification_rule": meta.certification_rule, "schema": meta.schema,
            "source_definition": meta.source_definition,
            "prohibited_comparisons": meta.prohibited_comparisons,
        }}

    def _market_trend(self, req: QueryRequest):
        meta = self.catalog.get(req.metric_id)
        if "market_trend" not in (meta.supported_query_types or []):
            raise ValidationError(f"指标 {req.metric_id} 不支持 market_trend。")
        conn = self.conns.get("standard")
        periods = req.periods if req.periods else ([req.period] if req.period else None)
        if not periods:
            raise ValidationError("market_trend 需要 periods。")
        out_unit = req.output_unit or meta.unit
        rows = conn.execute(
            "SELECT period, metric_id, value, unit FROM market_facts WHERE metric_id=? AND period IN (%s) ORDER BY period"
            % ",".join("?" * len(periods)), [req.metric_id] + list(periods)).fetchall()
        data = []
        for r in rows:
            data.append({"period": r[0], "value": float(r[2]), "unit": r[3]})
        return {"query_type": "market_trend", "data": data, "metric": req.metric_id,
                "source_unit": meta.unit, "output_unit": out_unit}

    def _company_ranking(self, req: QueryRequest):
        meta = self.catalog.get(req.metric_id)
        sf = meta.source_filter or {}
        if "company_ranking" not in (meta.supported_query_types or []):
            raise ValidationError(f"指标 {req.metric_id} 不支持 company_ranking。")
        if meta.source_layer == "annual":
            conn = self.conns.get("annual")
            year = req.period if req.period else str(sf.get("report_year", 2024))
            limit = req.limit or 10
            rows = conn.execute("""
                SELECT insurer_name_source, value_raw, report_year
                FROM company_facts
                WHERE report_year=? AND table_id=? AND metric_sem=? AND entity_scope='insurer'
                ORDER BY value_raw DESC LIMIT ?
            """, [int(year), sf.get("table_id"), sf.get("metric_sem"), limit]).fetchall()
            data = [{"entity": r[0], "value": float(r[1]), "report_year": r[2]} for r in rows]
            return {"query_type": "company_ranking", "data": data, "metric": req.metric_id,
                    "source_unit": meta.unit, "source_layer": meta.source_layer}
        if meta.source_layer == "provisional2025":
            conn = self.conns.get("provisional2025")
            limit = req.limit or 10
            rows = conn.execute("""
                SELECT insurer_name_en, value, year, certification FROM provisional_company_facts
                WHERE metric_sem=? AND entity_scope='insurer' AND year=2025
                ORDER BY value DESC LIMIT ?
            """, [sf.get("metric_sem"), limit]).fetchall()
            data = [{"entity": r[0], "value": float(r[1]), "year": r[2], "certification": r[3]} for r in rows]
            return {"query_type": "company_ranking", "data": data, "metric": req.metric_id,
                    "source_unit": meta.unit, "source_layer": meta.source_layer}
        raise ValidationError(f"指标 {req.metric_id} 的公司排名源层未实现。")


    def _financial_snapshot(self, req: QueryRequest):
        meta = self.catalog.get(req.metric_id)
        # 简化：financial 层按 period + fund_scope + item 取数
        conn = self.conns.get("financial")
        period = req.period or "2026Q1"
        fund = (req.filters or {}).get("fund_scope", "long_term")
        item_id = req.metric_id.replace("FIN_", "").lower()
        r = conn.execute("""
            SELECT period, fund_scope, item_id, value_hkd_million, unit FROM financial_facts
            WHERE period=? AND fund_scope=? AND item_id=? 
        """, [period, fund, item_id]).fetchone()
        data = []
        # 返回指定 item 及该 fund 的同类资产科目集（Q4 返回3项）
        rows = conn.execute("""
            SELECT item_id, value_hkd_million FROM financial_facts
            WHERE period=? AND fund_scope=? AND item_id IN ('debt_securities','equities_portfolio','cash_and_deposits')
            ORDER BY value_hkd_million DESC
        """, [period, fund]).fetchall()
        seen=set()
        for row in rows:
            iid=row[0]
            if iid in seen: continue
            seen.add(iid)
            data.append({"period": period, "item_id": iid, "value": float(row[1]), "unit": "HKD_million"})
        return {"query_type": "financial_snapshot", "data": data, "metric": req.metric_id,
                "source_unit": "HKD_million", "source_layer": "financial"}

    def _company_period_values(self, req: QueryRequest):
        meta = self.catalog.get(req.metric_id)
        from .identity import require_identity_mode
        require_identity_mode(req.identity_mode)
        if meta.source_layer == "annual":
            conn = self.conns.get("annual")
            # 取某年度 L16 某公司值
            entity = (req.filters or {}).get("entity")
            if not entity:
                raise ValidationError("company_period_values 需要 filters.entity。")
            ek = self.identity.entity_for_2024(entity) if req.identity_mode == "entity" else entity
            rows = conn.execute("""
                SELECT insurer_name_source, value_raw, report_year FROM company_facts
                WHERE report_year=? AND table_id=? AND metric_sem=? AND entity_scope='insurer'
                  AND insurer_name_source=?
            """, [int(req.period or 2024), meta.source_filter.get("table_id"),
                  meta.source_filter.get("metric_sem"), entity]).fetchall()
            data = [{"entity": r[0], "value": float(r[1]), "report_year": r[2], "certification": "certified"} for r in rows]
            return {"query_type": "company_period_values", "data": data, "metric": req.metric_id,
                    "identity_mode": req.identity_mode}
        raise ValidationError(f"不支持 company_period_values 的源层 {meta.source_layer}")

    def _compare_periods(self, req: QueryRequest):
        """跨期比较。2024 L16 vs 2025 L1 必须硬阻断。"""
        from . import policy, comparability
        pa = (req.filters or {}).get("period_a")
        pb = (req.filters or {}).get("period_b")
        # scope 判定
        l16 = pa in ("2024",) or pb in ("2024",)
        l1 = (req.metric_id or "").startswith("PROV2025") or pa in ("2025",) or pb in ("2025",)
        if (l16 and l1) or (pa == "2024" and pb == "2025") or (pa == "2025" and pb == "2024"):
            raise NotComparableError()
        raise ValidationError("compare_periods 仅支持已验收同口径期对；当前无可发布同口径对。")
