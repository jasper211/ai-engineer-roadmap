"""process_analytics只读查询边界。"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable


MUTATION = re.compile(
    r"\b(insert|update|delete|merge|alter|drop|truncate|create|grant|revoke|copy|call|execute)\b",
    re.I,
)


def assert_read_only_sql(sql: str) -> None:
    normalized = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.S).strip()
    if not normalized or MUTATION.search(normalized):
        raise ValueError("VNW V1只允许只读SELECT查询")
    if not re.match(r"^(select|with)\b", normalized, re.I):
        raise ValueError("VNW V1只允许只读SELECT查询")


class PostgresL3Reader:
    def __init__(self, query: Callable[[str, tuple], list[dict]]):
        self.query = query

    def _read(self, sql: str, l3_code: str) -> list[dict]:
        assert_read_only_sql(sql)
        return self.query(sql, (l3_code,))

    def processes(self, l3_code: str) -> list[dict]:
        return self._read(
            """SELECT l3_code, l3_name, l4_code, l4_name, l4_deliverable,
                      l4_deliverable_type, agentifiability, agent_human_touchpoint,
                      agent_d1_input_struct, agent_d2_rule_clear, agent_d3_output_verify,
                      agent_d4_api_reach, agent_d5_fallback, agent_d6_compliance
                 FROM process_analytics.dim_process
                WHERE l3_code = %s AND COALESCE(is_current, TRUE)
                ORDER BY l4_code""",
            l3_code,
        )

    def value_nodes(self, l3_code: str) -> list[dict]:
        return self._read(
            """SELECT DISTINCT vn.vn_id, vn.vn_name, vn.overall_judgment, vn.is_fused,
                              vn.priority, vn.gate1_data_linked, vn.gate2_grounded,
                              vn.gate3_traceable
                 FROM process_analytics.dim_vn vn
                 JOIN process_analytics.bridge_vn_l4 b ON b.vn_id = vn.vn_id
                WHERE b.l3_code = %s
                ORDER BY vn.vn_id""",
            l3_code,
        )

    def vn_l4_mappings(self, l3_code: str) -> list[dict]:
        return self._read(
            """SELECT b.vn_id, b.l4_code, b.mapping_status
                 FROM process_analytics.bridge_vn_l4 b
                WHERE b.l3_code = %s
                ORDER BY b.vn_id, b.l4_code""",
            l3_code,
        )

    def l2_mappings(self, l3_code: str) -> list[dict]:
        return self._read(
            """SELECT l3_code, l2_code, l2_name
                 FROM process_analytics.bridge_l3_l2
                WHERE l3_code = %s
                ORDER BY l2_code""",
            l3_code,
        )

    def kpi_mappings(self, l3_code: str) -> list[dict]:
        return self._read(
            """SELECT kpi_id AS kpi_code, kpi_name, contribution_weight,
                      weight_confirmed, row_status
                 FROM process_analytics.bridge_kpi_l3
                WHERE l3_id = %s
                ORDER BY kpi_id""",
            l3_code,
        )

    def value_stream_mappings(self, l3_code: str) -> list[dict]:
        return self._read(
            """SELECT b.l3_code, b.vs_code, b.stage_code, v.vs_name
                 FROM process_analytics.bridge_l3_vs_stage b
                 LEFT JOIN process_analytics.dim_vs v
                   ON v.vs_code = b.vs_code AND v.stage_code = b.stage_code
                WHERE b.l3_code = %s
                ORDER BY b.vs_code, b.stage_code""",
            l3_code,
        )


class BulkPostgresL3Reader:
    """每张权威表只读一次，在内存中按L3分组，供全量扫描复用。"""

    def __init__(self, datasets: dict[str, list[dict]]):
        self.datasets = datasets
        self.grouped: dict[str, dict[str, list[dict]]] = {}
        for name, rows in datasets.items():
            by_l3: dict[str, list[dict]] = defaultdict(list)
            for row in rows:
                code = str(row.get("l3_code") or "")
                if code:
                    by_l3[code].append(row)
            self.grouped[name] = dict(by_l3)

    @classmethod
    def from_query(cls, query: Callable[[str, tuple], list[dict]]) -> "BulkPostgresL3Reader":
        sql_by_dataset = {
            "processes": """SELECT l3_code, l3_name, l4_code, l4_name, l4_deliverable,
                      l4_deliverable_type, agentifiability, agent_human_touchpoint,
                      agent_d1_input_struct, agent_d2_rule_clear, agent_d3_output_verify,
                      agent_d4_api_reach, agent_d5_fallback, agent_d6_compliance
                 FROM process_analytics.dim_process
                WHERE COALESCE(is_current, TRUE)
                ORDER BY l3_code, l4_code""",
            "value_nodes": """SELECT DISTINCT b.l3_code, vn.vn_id, vn.vn_name,
                      vn.overall_judgment, vn.is_fused, vn.priority,
                      vn.gate1_data_linked, vn.gate2_grounded, vn.gate3_traceable
                 FROM process_analytics.dim_vn vn
                 JOIN process_analytics.bridge_vn_l4 b ON b.vn_id = vn.vn_id
                ORDER BY b.l3_code, vn.vn_id""",
            "mappings": """SELECT b.l3_code, b.vn_id, b.l4_code, b.mapping_status
                 FROM process_analytics.bridge_vn_l4 b
                ORDER BY b.l3_code, b.vn_id, b.l4_code""",
            "l2s": """SELECT l3_code, l2_code, l2_name
                 FROM process_analytics.bridge_l3_l2
                ORDER BY l3_code, l2_code""",
            "kpis": """SELECT l3_id AS l3_code, kpi_id AS kpi_code, kpi_name,
                      contribution_weight, weight_confirmed, row_status
                 FROM process_analytics.bridge_kpi_l3
                ORDER BY l3_id, kpi_id""",
            "value_streams": """SELECT b.l3_code, b.vs_code, b.stage_code, v.vs_name
                 FROM process_analytics.bridge_l3_vs_stage b
                 LEFT JOIN process_analytics.dim_vs v
                   ON v.vs_code = b.vs_code AND v.stage_code = b.stage_code
                ORDER BY b.l3_code, b.vs_code, b.stage_code""",
        }
        datasets = {}
        for name, sql in sql_by_dataset.items():
            assert_read_only_sql(sql)
            datasets[name] = query(sql, ())
        return cls(datasets)

    @property
    def l3_codes(self) -> list[str]:
        return sorted(self.grouped["processes"])

    def _get(self, dataset: str, l3_code: str) -> list[dict]:
        return self.grouped[dataset].get(l3_code, [])

    def processes(self, code: str): return self._get("processes", code)
    def value_nodes(self, code: str): return self._get("value_nodes", code)
    def vn_l4_mappings(self, code: str): return self._get("mappings", code)
    def l2_mappings(self, code: str): return self._get("l2s", code)
    def kpi_mappings(self, code: str): return self._get("kpis", code)
    def value_stream_mappings(self, code: str): return self._get("value_streams", code)
