"""固定 SQL 模板（白名单）+ 查询结果组装。禁止透传表名/列/WHERE/排序。"""
from __future__ import annotations
from typing import List, Dict, Optional
from .models import MetricMeta, QueryRequest, ValidationError, NotComparableError

ALLOWED_QUERY_TYPES = {"market_trend", "company_ranking", "financial_snapshot",
                       "company_period_values", "compare_periods",
                       "describe_metric", "list_metrics", "healthcheck"}

# 模板 ID 映射（供 lineage 使用）
TEMPLATE_ID = {
    "market_trend": "Q1_MARKET_TREND_V1",
    "company_ranking": "Q2_COMPANY_RANKING_V1",
    "financial_snapshot": "Q4_FINANCIAL_SNAPSHOT_V1",
    "company_period_values": "Q5_COMPANY_PERIOD_VALUES_V1",
    "compare_periods": "Q6_COMPARE_PERIODS_V1",
    "describe_metric": "M2_DESCRIBE_METRIC_V1",
    "list_metrics": "M1_LIST_METRICS_V1",
    "healthcheck": "H1_HEALTHCHECK_V1",
}


class QueryBuilder:
    def __init__(self, catalog=None, connections=None, identity=None):
        self.catalog = catalog
        self.conns = connections
        self.identity = identity

    def validate_query_type(self, qt):
        if qt not in ALLOWED_QUERY_TYPES:
            raise ValidationError(f"不支持的 query_type: {qt!r}")
        return qt

    def template_id(self, qt):
        return TEMPLATE_ID.get(qt, "UNKNOWN_TEMPLATE")

    def build(self, req):
        self.validate_query_type(req.query_type)
        qt = req.query_type
        if qt == "healthcheck": return self._health()
        if qt == "list_metrics": return self._list_metrics()
        if qt == "describe_metric": return self._describe(self.catalog.get(req.metric_id))
        if qt == "market_trend": return self._market_trend(req)
        if qt == "company_ranking": return self._company_ranking(req)
        if qt == "financial_snapshot": return self._financial_snapshot(req)
        if qt == "company_period_values": return self._company_period_values(req)
        if qt == "compare_periods": return self._compare_periods(req)
        raise ValidationError(f"未实现 query_type: {qt}")

    def _health(self):
        rows = {}
        for db_id in ["master", "standard", "annual", "provisional2025", "financial"]:
            if db_id == "standard":
                n = 0
                for t in ["market_facts", "company_facts", "schema_metrics", "annual_facts"]:
                    n += int(self.conns.count(db_id, t))
                rows[db_id] = n
            else:
                t = ("long_term_business" if db_id == "master" else
                     "company_facts" if db_id == "annual" else
                     "provisional_company_facts" if db_id == "provisional2025" else "financial_facts")
                rows[db_id] = int(self.conns.count(db_id, t))
        rows = [{"db_id": k, "row_count": v} for k, v in rows.items()]
        return {"query_type": "healthcheck", "data": rows}

    def _list_metrics(self):
        ids = self.catalog.list_ids()
        metas = [self.catalog.get(i) for i in ids]
        data = [{"metric_id": m.metric_id, "label": m.label, "unit": m.unit,
                 "entity_scope": m.entity_scope, "period_basis": m.period_basis,
                 "supported_query_types": m.supported_query_types} for m in metas]
        return {"query_type": "list_metrics", "data": data, "metric_ids": ids, "count": len(ids)}

    def _describe(self, meta):
        data = [{
            "metric_id": meta.metric_id, "label": meta.label, "unit": meta.unit,
            "entity_scope": meta.entity_scope, "period_basis": meta.period_basis,
            "certification_rule": meta.certification_rule, "schema": meta.schema,
            "source_layer": meta.source_layer, "source_table": meta.source_table,
            "comparable_with": meta.comparable_with,
            "prohibited_comparisons": meta.prohibited_comparisons,
            "aggregation": meta.aggregation,
            "source_definition": meta.source_definition,
        }]
        return {"query_type": "describe_metric", "data": data}

    def _market_trend(self, req):
        meta = self.catalog.get(req.metric_id)
        periods = req.periods if req.periods else ([req.period] if req.period else None)
        if not periods:
            raise ValidationError("market_trend 需要 periods。")
        conn = self.conns.get("standard")
        rows = conn.execute(
            "SELECT period, metric_id, value, unit FROM market_facts WHERE metric_id=? AND period IN (%s) ORDER BY period"
            % ",".join("?" * len(periods)), [req.metric_id] + list(periods)).fetchall()
        data = [{"period": r[0], "value": float(r[2]), "unit": r[3],
                 "entity_scope": "market_total", "certification": "provisional",
                 "schema": meta.schema} for r in rows]
        return {"query_type": "market_trend", "data": data, "metric": req.metric_id,
                "source_unit": meta.unit, "source_layer": meta.source_layer, "source_db": meta.source_layer,
                "source_table": meta.source_table, "certification": "provisional"}

    def _company_ranking(self, req):
        meta = self.catalog.get(req.metric_id)
        sf = meta.source_filter or {}
        if "company_ranking" not in (meta.supported_query_types or []):
            raise ValidationError(f"指标 {req.metric_id} 不支持 company_ranking。")
        limit = req.limit if req.limit is not None else 10
        if meta.source_layer == "annual":
            conn = self.conns.get("annual")
            year = req.period or "2024"
            offset = req.offset or 0
            rows = conn.execute("""
                SELECT insurer_name_source, value_raw, report_year FROM company_facts
                WHERE report_year=? AND table_id=? AND metric_sem=? AND entity_scope='insurer'
                ORDER BY value_raw DESC LIMIT ? OFFSET ?
            """, [int(year), sf.get("table_id"), sf.get("metric_sem"), limit, offset]).fetchall()
            data = [{"entity": r[0], "value": float(r[1]), "report_year": r[2],
                     "entity_key": (self.identity.entity_for_2024(r[0]) if self.identity else None),
                     "entity_scope": "insurer", "certification": "certified", "schema": meta.schema}
                    for r in rows]
            return {"query_type": "company_ranking", "data": data, "metric": req.metric_id,
                    "source_unit": meta.unit, "source_layer": "annual",
                    "source_db": "annual", "source_table": "company_facts", "certification": "certified"}
        if meta.source_layer == "provisional2025":
            conn = self.conns.get("provisional2025")
            offset = req.offset or 0
            rows = conn.execute("""
                SELECT insurer_name_en, value, year, certification FROM provisional_company_facts
                WHERE metric_sem=? AND entity_scope='insurer' AND year=2025
                ORDER BY value DESC LIMIT ? OFFSET ?
            """, [sf.get("metric_sem"), limit, offset]).fetchall()
            data = [{"entity": r[0], "value": float(r[1]), "year": r[2],
                     "entity_key": (self.identity.entity_for_2025(r[0]) if self.identity else None),
                     "entity_scope": "insurer", "certification": "provisional", "schema": meta.schema}
                    for r in rows]
            return {"query_type": "company_ranking", "data": data, "metric": req.metric_id,
                    "source_unit": meta.unit, "source_layer": "provisional2025",
                    "source_db": "provisional2025", "source_table": "provisional_company_facts",
                    "certification": "provisional"}
        raise ValidationError(f"指标 {req.metric_id} 的公司排名源层未实现。")

    def _financial_snapshot(self, req):
        conn = self.conns.get("financial")
        period = req.period or "2026Q1"
        fund = (req.filters or {}).get("fund_scope", "long_term")
        rows = conn.execute("""
            SELECT item_id, value_hkd_million FROM financial_facts
            WHERE period=? AND fund_scope=? AND item_id IN ('debt_securities','equities_portfolio','cash_and_deposits')
            ORDER BY value_hkd_million DESC
        """, [period, fund]).fetchall()
        data = [{"period": period, "item_id": r[0], "value": float(r[1]), "unit": "HKD_million",
                 "entity_scope": "fund", "certification": "provisional", "schema": "financial"}
                for r in rows]
        return {"query_type": "financial_snapshot", "data": data, "metric": req.metric_id,
                "source_unit": "HKD_million", "source_layer": "financial",
                "source_db": "financial", "source_table": "financial_facts", "certification": "provisional"}

    def _company_period_values(self, req):
        meta = self.catalog.get(req.metric_id)
        from .identity import require_identity_mode
        require_identity_mode(req.identity_mode)
        entity = (req.filters or {}).get("entity")
        if not entity:
            raise ValidationError("company_period_values 需要 filters.entity。")
        ident = self.identity.resolve(entity, req.identity_mode) if self.identity else {}
        bridge_evidence = "standard_layer_entity_key" if self.identity else None
        if meta.source_layer == "annual":
            conn = self.conns.get("annual")
            rows = conn.execute(
                "SELECT insurer_name_source, value_raw, report_year FROM company_facts "
                "WHERE report_year=? AND table_id=? AND metric_sem=? AND entity_scope='insurer' "
                "AND insurer_name_source=?",
                [int(req.period or 2024), meta.source_filter.get("table_id"),
                 meta.source_filter.get("metric_sem"), entity]).fetchall()
            if rows:
                val = float(rows[0][1])
                data = [dict(entity=entity, value=None if val == 0 and rows[0][1] is None else val,
                             report_year=rows[0][2], entity_key=ident.get("entity_key"),
                             business_lineage=ident.get("business_lineage"), entity_scope="insurer",
                             certification="certified", schema=meta.schema,
                             record_status="reported_zero" if val == 0 else "reported_value",
                             bridge_evidence=bridge_evidence, bridge_type="rename_or_alias" if ident.get("note") else "same_name")]
            else:
                data = [dict(entity=entity, value=None, report_year=int(req.period or 2024),
                             entity_key=ident.get("entity_key"), business_lineage=ident.get("business_lineage"),
                             entity_scope="insurer", certification="certified", schema=meta.schema,
                             record_status="missing", bridge_evidence=bridge_evidence)]
            return {"query_type": "company_period_values", "data": data, "metric": req.metric_id,
                    "identity_mode": req.identity_mode, "source_layer": "annual", "identity_note": ident.get("note")}
        if meta.source_layer == "provisional2025":
            conn = self.conns.get("provisional2025")
            rows = conn.execute("""
                SELECT insurer_name_en, value, year, certification FROM provisional_company_facts
                WHERE metric_sem=? AND entity_scope='insurer' AND year=2025 AND insurer_name_en=?
            """, [meta.source_filter.get("metric_sem"), entity]).fetchall()
            if rows:
                val = float(rows[0][1])
                data = [dict(entity=entity, value=val, year=rows[0][2],
                             entity_key=ident.get("entity_key"), business_lineage=ident.get("business_lineage"),
                             entity_scope="insurer", certification="provisional", schema=meta.schema,
                             record_status="reported_zero" if val == 0 else "reported_value",
                             bridge_evidence=bridge_evidence)]
            else:
                data = [dict(entity=entity, value=None, year=2025,
                             entity_key=ident.get("entity_key"), business_lineage=ident.get("business_lineage"),
                             entity_scope="insurer", certification="provisional", schema=meta.schema,
                             record_status="missing", bridge_evidence=bridge_evidence)]
            return {"query_type": "company_period_values", "data": data, "metric": req.metric_id,
                    "identity_mode": req.identity_mode, "source_layer": "provisional2025", "identity_note": ident.get("note")}
        raise ValidationError(f"不支持 company_period_values 的源层 {meta.source_layer}")

    def _compare_periods(self, req):
        from .models import (NotComparableError, ValidationError, SchemaBridgeRequiredError, L11CountMixError)
        pa = (req.filters or {}).get("period_a"); pb = (req.filters or {}).get("period_b")
        metric_b = (req.filters or {}).get("metric_b")
        # L11 数量类跨指标比较禁止（policy_count vs scheme_count）
        if (req.metric_id and "L11" in req.metric_id) or (metric_b and "L11" in str(metric_b)):
            raise L11CountMixError()
        # pre-RBC ↔ RBC 无审定桥 → SCHEMA_BRIDGE_REQUIRED
        if (pa and pb and _cross_rbc(pa, pb)):
            raise SchemaBridgeRequiredError()
        l16 = req.metric_id and ("ANNUAL_L16" in req.metric_id or "L16" in req.metric_id)
        l1 = req.metric_id and "PROV2025" in req.metric_id or (pa == "2025" and pb == "2024") or (pa == "2024" and pb == "2025")
        if (l16 and l1):
            raise NotComparableError()
        raise ValidationError("compare_periods 仅支持已验收同口径期对；当前无可发布同口径对。")


def _cross_rbc(pa, pb):
    yr = []
    for p in (pa, pb):
        if p:
            dig = "".join(ch for ch in str(p) if ch.isdigit())
            if len(dig) >= 4:
                try: yr.append(int(dig[:4]))
                except ValueError: pass
    if len(yr) == 2 and yr[0] != yr[1]:
        pre = {2022, 2023}; rbc = {2024}
        return (yr[0] in pre and yr[1] in rbc) or (yr[0] in rbc and yr[1] in pre)
    return False
