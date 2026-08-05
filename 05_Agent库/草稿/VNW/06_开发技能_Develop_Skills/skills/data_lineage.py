"""104张业务数据表的数据血缘图：只用数据库里已经真实存在的证据连边，不做
同名字段/表名相似度之类的推测性连接。

三类证据，按权威性从高到低：

1. view_dependency（最高）：pg_get_viewdef()读出的真实视图SQL定义，FROM/JOIN
   引用的表就是这个视图的真实上游——这是SQL本身写明的事实，不是推断。18个视图
   全部来自这条路径，其中fact_channel_ka/fact_channel_partner/fact_customer/
   fact_product_id/fact_product_sku这5张表名带fact_前缀，实际是视图不是物理表，
   之前db_catalog.py的table_type分类按前缀判断误标成了"事实表"。

2. foreign_key（高）：information_schema里数据库设计者显式声明的外键约束，
   22条，全部真实存在，不是ORM或代码层面的隐式约定。

3. pipeline_sibling（中，语义不同于前两类）：sync_history/fin_sync_history里
   记录的真实ETL运行日志——只认可有命名、可重复的airflow流水线(commission_
   pipeline/performance_pipeline/insurance_plan_pipeline)，同一次流水线运行
   装载的表互为"同批产出"。这不是产出/消费关系，只是"来自同一个真实业务流程"
   的证据，前端必须用不同线型清楚区分，不能和前两类混着看当作同等强度的血缘。
   一次性的人工脚本(script:*/manual-*/wave*/bugfix:*等triggered_by)不算数——
   那是运维操作记录，不是可复现的数据流水线，不进图。

没有以上任何证据的表，如实标注"无可查血缘"——已确认这些表在整个仓库(VNW目录内外)
都没有对应的INSERT/COPY/ETL脚本，真实生产者是仓库之外的系统，这是数据侧真实边界，
不是分析没做到位。

血缘线索出来后，只用来生成"候选提示"(suggest_l4_candidates)：如果一张暂无L4关联
的表，血缘邻居已经有确认的L4关联，就提示"值得去核实"，明确标注via哪条边、什么证据，
不直接篡改104张表现有的已核实/未纳入分析范围状态——那两个状态继续只由business_data_
bridge.py的人工核实决定。
"""
from __future__ import annotations

import re
from collections.abc import Callable

SCHEMAS = ["public", "comm_sandbox", "fin_sandbox"]

_FROM_JOIN_RE = re.compile(
    r'(?:FROM|JOIN)\s+((?:"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)(?:\.(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_]*))?)',
    re.IGNORECASE,
)
_NAMED_PIPELINE_RE = re.compile(r'^airflow:([a-zA-Z0-9_]+):')


def extract_view_dependencies(db_query: Callable[[str, tuple], list[dict]], known_tables: set[tuple[str, str]]) -> list[dict]:
    """读每个视图的真实SQL定义，抽取FROM/JOIN引用的表。裸表名(未写schema前缀)
    按Postgres自己的dump习惯——同schema省略前缀——归到该视图所在schema下；
    跨schema引用pg_get_viewdef会自动补全schema前缀，直接按原文解析。
    """
    views = db_query(
        "SELECT table_schema, table_name FROM information_schema.views WHERE table_schema = ANY(%s)",
        (SCHEMAS,),
    )
    edges = []
    for v in views:
        schema, name = v["table_schema"], v["table_name"]
        rows = db_query("SELECT pg_get_viewdef(%s::regclass, true) AS def", (f"{schema}.{name}",))
        definition = rows[0]["def"] if rows else ""
        referenced: set[tuple[str, str]] = set()
        for match in _FROM_JOIN_RE.finditer(definition):
            token = match.group(1).replace('"', '')
            if "." in token:
                ref_schema, ref_table = token.split(".", 1)
            else:
                ref_schema, ref_table = schema, token
            candidate = (ref_schema, ref_table)
            if candidate in known_tables and candidate != (schema, name):
                referenced.add(candidate)
        for ref_schema, ref_table in sorted(referenced):
            edges.append({
                "from_schema": ref_schema,
                "from_table": ref_table,
                "to_schema": schema,
                "to_table": name,
                "edge_type": "view_dependency",
                "evidence": f"{schema}.{name}的真实视图定义中FROM/JOIN引用了{ref_schema}.{ref_table}",
            })
    return edges


def extract_foreign_keys(db_query: Callable[[str, tuple], list[dict]], known_tables: set[tuple[str, str]]) -> list[dict]:
    """读information_schema里数据库设计者显式声明的外键约束。自引用(如
    dim_person.merged_into_person_id指回dim_person自己)不构成图上的有向边，跳过。
    """
    rows = db_query(
        """SELECT tc.table_schema, tc.table_name, kcu.column_name,
                  ccu.table_schema AS foreign_schema, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
             FROM information_schema.table_constraints tc
             JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
             JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = ANY(%s)""",
        (SCHEMAS,),
    )
    edges = []
    for r in rows:
        child = (r["table_schema"], r["table_name"])
        parent = (r["foreign_schema"], r["foreign_table"])
        if child == parent or child not in known_tables or parent not in known_tables:
            continue
        edges.append({
            "from_schema": parent[0],
            "from_table": parent[1],
            "to_schema": child[0],
            "to_table": child[1],
            "edge_type": "foreign_key",
            "evidence": f"{child[0]}.{child[1]}.{r['column_name']} 外键引用 {parent[0]}.{parent[1]}.{r['foreign_column']}",
        })
    return edges


def extract_pipeline_groups(db_query: Callable[[str, tuple], list[dict]], known_tables: set[tuple[str, str]]) -> list[dict]:
    """只认可有命名、可重复的airflow流水线，人工一次性脚本不算数。同一流水线
    装载的表两两连边，边类型pipeline_sibling，语义是"同批真实产出"而非上下游。
    """
    # fin_sandbox.fin_sync_history字段是id/table_name/batch_id/rows_affected/synced_at/
    # synced_by，没有triggered_by/流水线名字段，本身就查不出命名流水线，不在这里查它。
    groups: dict[str, set[tuple[str, str]]] = {}
    rows = db_query("SELECT DISTINCT table_name, triggered_by FROM public.sync_history", ())
    for r in rows:
        match = _NAMED_PIPELINE_RE.match(r["triggered_by"] or "")
        if not match:
            continue
        candidate = ("public", r["table_name"])
        if candidate not in known_tables:
            continue
        groups.setdefault(match.group(1), set()).add(candidate)

    edges = []
    for pipeline, tables in groups.items():
        if len(tables) < 2:
            continue
        ordered = sorted(tables)
        for i, (s1, t1) in enumerate(ordered):
            for s2, t2 in ordered[i + 1:]:
                edges.append({
                    "from_schema": s1,
                    "from_table": t1,
                    "to_schema": s2,
                    "to_table": t2,
                    "edge_type": "pipeline_sibling",
                    "evidence": f"两表都由真实ETL流水线\"{pipeline}\"在同一批次装载(sync_history记录)，同源不代表互为上下游",
                })
    return edges


def build_lineage_graph(db_catalog: dict, business_label_fn, edges: list[dict]) -> dict:
    known_tables = {(t["schema"], t["table"]) for t in db_catalog["tables"] if t["schema"] != "process_analytics"}
    connected = {(e["from_schema"], e["from_table"]) for e in edges} | {(e["to_schema"], e["to_table"]) for e in edges}

    nodes = []
    for t in db_catalog["tables"]:
        if t["schema"] == "process_analytics":
            continue
        key = (t["schema"], t["table"])
        nodes.append({
            "schema": t["schema"],
            "table": t["table"],
            "table_type": t.get("table_type", "其他"),
            "business_label": business_label_fn(t["description"], t["table"]),
            "row_count": t["row_count"],
            "has_lineage": key in connected,
        })

    edge_type_counts = {"view_dependency": 0, "foreign_key": 0, "pipeline_sibling": 0}
    for e in edges:
        edge_type_counts[e["edge_type"]] = edge_type_counts.get(e["edge_type"], 0) + 1

    return {
        "schema_version": "vnw.data-lineage.v1",
        "source_policy": (
            "边只来自三类真实证据：视图SQL定义(pg_get_viewdef)/数据库外键约束/ETL流水线同批装载日志"
            "(sync_history，仅认可命名的可重复airflow流水线)，不做同名字段或表名相似度的推测性连接；"
            "无证据的表如实标注无可查血缘(已核实仓库内外都没有对应ETL脚本，生产者在仓库之外)"
        ),
        "edge_type_labels": {
            "view_dependency": "视图SQL依赖(最高置信度)",
            "foreign_key": "数据库外键约束(高置信度)",
            "pipeline_sibling": "同ETL流水线批次产出(中置信度，非上下游)",
        },
        "edge_type_counts": edge_type_counts,
        "nodes": nodes,
        "edges": edges,
    }


def suggest_l4_candidates(edges: list[dict], table_to_l4_index: dict[str, list[dict]], known_tables: set[tuple[str, str]]) -> dict[str, list[dict]]:
    """对暂无确认L4关联的表，如果血缘邻居已有确认的L4关联，给出DERIVED候选提示——
    不是新的确认关联，只是"值得去核实"，明确标注via哪张邻居表、什么边证据。
    """
    adjacency: dict[str, list[dict]] = {}
    for e in edges:
        a = f"{e['from_schema']}.{e['from_table']}"
        b = f"{e['to_schema']}.{e['to_table']}"
        adjacency.setdefault(a, []).append({"neighbor": b, "edge_type": e["edge_type"], "evidence": e["evidence"]})
        adjacency.setdefault(b, []).append({"neighbor": a, "edge_type": e["edge_type"], "evidence": e["evidence"]})

    suggestions: dict[str, list[dict]] = {}
    for schema, table in known_tables:
        key = f"{schema}.{table}"
        if table_to_l4_index.get(key):
            continue
        seen: dict[tuple[str, str], dict] = {}
        for link in adjacency.get(key, []):
            for rel in table_to_l4_index.get(link["neighbor"], []):
                dedup_key = (rel["l3_code"], rel["l4_code"])
                if dedup_key not in seen:
                    seen[dedup_key] = {
                        "l3_code": rel["l3_code"],
                        "l3_name": rel["l3_name"],
                        "l4_code": rel["l4_code"],
                        "l4_name": rel["l4_name"],
                        "via_table": link["neighbor"],
                        "edge_type": link["edge_type"],
                        "evidence": link["evidence"],
                    }
        if seen:
            suggestions[key] = list(seen.values())
    return suggestions


def flag_zombie_tables(nodes: list[dict], table_to_l4_index: dict[str, list[dict]], suggested_candidates: dict[str, list]) -> None:
    """就地给每个node加zombie_flag字段。三种真实信号(血缘边/已确认L4关联/血缘候选)
    一个都没有的表，才有资格被标——区分两种情况：0行是"从未启用"(可能只是还没到
    这个环节，不算真问题)，有行数据但仍然三条信号全无，才是更接近字面意义的
    "疑似僵尸表"(数据蓄在库里，血缘上无人产出/消费它，L4分析也没人认领)。
    这不是删除或下线建议，只是标出来提醒去核实——核实结果可能是"确实没用了"，
    也可能是"只是还没做匹配分析"，两种都要靠人判断，不能自动下结论。
    """
    for node in nodes:
        key = f"{node['schema']}.{node['table']}"
        has_signal = node["has_lineage"] or bool(table_to_l4_index.get(key)) or bool(suggested_candidates.get(key))
        if has_signal:
            node["zombie_flag"] = "none"
        elif node["row_count"] == 0:
            node["zombie_flag"] = "never_activated"
        else:
            node["zombie_flag"] = "suspected_zombie"
