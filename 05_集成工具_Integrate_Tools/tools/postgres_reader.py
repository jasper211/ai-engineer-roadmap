"""process_analytics只读适配器。

query函数由调用方注入，便于测试；本模块不持有连接参数，不执行写SQL。
"""
from __future__ import annotations

import re
from collections.abc import Callable


READ_ONLY_SQL = re.compile(r"^\s*(SELECT|WITH)\b", re.I)
FORBIDDEN_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE)\b", re.I)


def assert_read_only(sql: str) -> None:
    if not READ_ONLY_SQL.search(sql) or FORBIDDEN_SQL.search(sql):
        raise ValueError("V1仅允许SELECT/WITH只读查询")


class PostgresL3Reader:
    def __init__(self, query: Callable[[str, tuple], list[dict]]):
        self._query = query

    def _run(self, sql: str, params: tuple = ()) -> list[dict]:
        assert_read_only(sql)
        return self._query(sql, params)

    def processes(self, l3_code: str) -> list[dict]:
        return self._run(
            """SELECT * FROM process_analytics.dim_process
               WHERE l3_code = %s AND COALESCE(is_current, TRUE)
               ORDER BY l4_code""",
            (l3_code,),
        )

    def value_nodes(self, l3_code: str) -> list[dict]:
        return self._run(
            """SELECT * FROM process_analytics.dim_vn
               WHERE l3_code = %s ORDER BY vn_id""",
            (l3_code,),
        )

    def vn_l4_mappings(self, l3_code: str) -> list[dict]:
        return self._run(
            """SELECT * FROM process_analytics.bridge_vn_l4
               WHERE l3_code = %s ORDER BY vn_id, l4_code""",
            (l3_code,),
        )

    def l2_mappings(self, l3_code: str) -> list[dict]:
        return self._run(
            """SELECT * FROM process_analytics.bridge_l3_l2
               WHERE l3_code = %s ORDER BY l2_code""",
            (l3_code,),
        )

    def kpi_mappings(self, l3_code: str) -> list[dict]:
        return self._run(
            """SELECT * FROM process_analytics.bridge_kpi_l3
               WHERE l3_id = %s ORDER BY kpi_id""",
            (l3_code,),
        )

    def value_stream_mappings(self, l3_code: str) -> list[dict]:
        return self._run(
            """SELECT * FROM process_analytics.bridge_l3_vs_stage
               WHERE l3_code = %s ORDER BY vs_code, stage_code""",
            (l3_code,),
        )

