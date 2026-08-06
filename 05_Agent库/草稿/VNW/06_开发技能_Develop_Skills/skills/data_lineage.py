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

2026-08-05新增两块字段级证据(仍然只用真实数据，不猜)：

- extract_field_column_lineage：把18个视图里能安全解析的那部分，从"表级血缘"
  深挖到"字段级血缘"——用pg_get_viewdef()拿到的真实SQL，解析SELECT列表和FROM/
  JOIN别名，算出"视图的这个输出字段，直接透传/由哪些源字段计算而来"。含CTE(WITH)/
  UNION/窗口函数的视图SQL结构太复杂，解析容易出错，如实标"结构复杂未解析"而不是
  猜——8个视图这样处理，10个视图能解析到字段级。

- build_field_index：同名字段跨表索引——不是断言"这些字段有关系"，只是老实统计
  "这个字段名出现在哪些表里"。字段是某表主键的，那张表标"源头"；有真实外键指向
  源头的标"外键确认"；只是同名但没建外键的标"同名(业务方确认含义一致)"——2026-08-05
  向业务数据方核实过，字段名相同时业务含义确实一致，这条备注写死在index里，不是
  每次都要重新假设。

- build_field_anchor_links + UTILITY_SUPPORT_TABLES：僵尸判定的第4/第5类补充信号。
  第4类(field_anchored)是字段级真实主键锚定，纯数据驱动。第5类(utility_support)是
  人工登记表——按字段名匹配的方法论对"控制表/通用维度/清洗工具"这类表天然失效，
  每条都由业务方逐条核实过具体理由(2026-08-05)，不是自动推断出来的。
"""
from __future__ import annotations

import re
from collections.abc import Callable

SCHEMAS = ["public", "comm_sandbox", "fin_sandbox"]

# 审计/同步类字段几乎每张表都有，字段级索引里全部纳入只会刷屏、没有业务辨识度，排除。
_AUDIT_COLUMNS = {
    "batch_id", "created_at", "created_by", "updated_at", "updated_by",
    "view_built_at", "source_file",
}

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


def classify_shared_master_data(suggested_candidates: dict[str, list[dict]], min_l3_span: int = 3) -> dict[str, dict]:
    """跨L3共用主数据/维度表——不是人工登记，直接从suggest_l4_candidates的
    证据密度机械判定：一张表的血缘候选如果覆盖>=min_l3_span个不同L3，说明它
    被多个L3的真实流水线/视图/外键共用，不适合再往单一L4上强行归类，应归为
    "共用主数据/维度表"。原因文本直接拼自真实候选数据(哪个L3经由哪张表连接)，
    不是手写模板——数据变了这段文字自动跟着变，不会读起来对但内容过期。
    """
    result: dict[str, dict] = {}
    for key, candidates in suggested_candidates.items():
        by_l3: dict[str, list[dict]] = {}
        for c in candidates:
            by_l3.setdefault(c["l3_code"], []).append(c)
        if len(by_l3) < min_l3_span:
            continue
        parts = []
        for l3_code in sorted(by_l3):
            via_tables = sorted({c["via_table"] for c in by_l3[l3_code]})
            parts.append(f"{l3_code}(经由{'、'.join(via_tables)})")
        result[key] = {
            "l3_span_count": len(by_l3),
            "l3_codes": sorted(by_l3),
            "reason": f"血缘候选覆盖{len(by_l3)}个L3：{'；'.join(parts)}——跨L3共用的主数据/维度表，不建议归入单一L4",
        }
    return result


# 第5类信号——人工核实的"工具/服务支撑表"：既没有血缘边/L4关联，也没有字段级
# 主键锚定，但业务上已核实其存在是为了支撑其他表/流程运转(ETL控制、通用维度、
# 数据清洗工具)，不是真断点。这是人工登记表，不是自动推断——每条都要有可核查的
# 具体理由，不能拿"看起来像工具表"就往里塞。2026-08-05由Jasper逐条核实确认。
UTILITY_SUPPORT_TABLES: dict[tuple[str, str], str] = {
    ("public", "agg_sales_base_etl_scope"): (
        "agg_sales_base流水线的ETL范围控制表(哪些渠道/期间纳入本轮汇总计算)，"
        "服务于流水线运行本身，不是业务实体，字段命名匹配不到血缘也在预期内"
    ),
    ("public", "dim_date"): (
        "通用日期维度表，供任意表按日期值(而非声明的字段名/主键)关联，"
        "血缘/字段索引按字段名匹配的方法论对它天然失效，不代表未被使用"
    ),
    ("public", "map_name_entity_type"): (
        "名称实体类型判定表：判断原始名称字符串是机构还是自然人，用于数据清洗"
        "人工复核记录，服务于姓名/机构识别的清洗环节而非直接挂业务L4——"
        "2026-08-05业务方确认其真实用途"
    ),
}


def build_field_anchor_links(field_index: dict) -> dict[str, list[dict]]:
    """第4类连接信号——字段级真实主键锚定，供角色分类/僵尸判定做补充信号用，
    不算血缘边(不进edges/has_lineage，避免和view/FK/pipeline三类证据混淆强度)。

    只认"该字段是某张表真实声明的主键"(field_index里origin_tables非空)这一种情况，
    纯粹同名但两边都不是任何人主键的通用属性字段(active/remark/is_active/quarter
    这类)明确不算——2026-08-05实测过，同名不代表锚定，必须要求真实PK背书。
    """
    links: dict[str, list[dict]] = {}
    for field_name, entry in field_index["fields"].items():
        if not entry["origin_tables"]:
            continue
        usages = entry["usages"]
        all_keys = [f"{u['schema']}.{u['table']}" for u in usages]
        for u in usages:
            key = f"{u['schema']}.{u['table']}"
            others = [k for k in all_keys if k != key]
            if not others:
                continue
            links.setdefault(key, []).append({
                "field": field_name,
                "linked_tables": others,
                "origin_tables": [f"{o['schema']}.{o['table']}" for o in entry["origin_tables"]],
            })
    return links


def flag_zombie_tables(
    nodes: list[dict],
    table_to_l4_index: dict[str, list[dict]],
    suggested_candidates: dict[str, list],
    field_anchor_links: dict[str, list[dict]] | None = None,
    utility_support_tables: dict[tuple[str, str], str] | None = None,
) -> None:
    """就地给每个node加zombie_flag字段。五种真实信号(血缘边/已确认L4关联/血缘候选/
    字段级主键锚定/人工核实的工具支撑表)一个都没有的表，才有资格被标——区分四种情况：
    - 0行是"从未启用"(可能只是还没到这个环节，不算真问题)；
    - 有数据、但能用真实主键锚定字段连回其他有血缘/有L4的表，标"field_anchored"
      (2026-08-05新增：这类表此前被误标疑似僵尸，实测33张"独立/工具/配置"表里
      有25张其实能用这条证据连回主链，不是真孤立，只是没做正式判定)；
    - 有数据、无字段锚定，但业务方已核实是工具/服务支撑表(UTILITY_SUPPORT_TABLES
      登记表)，标"utility_support"——这类表的方法论局限(按字段名匹配)天然找不到
      它们，不代表真断点；
    - 有数据、五种信号全无，才是更接近字面意义的"疑似僵尸表"。
    这不是删除或下线建议，只是标出来提醒去核实——核实结果可能是"确实没用了"，
    也可能是"只是还没做匹配分析"，两种都要靠人判断，不能自动下结论。
    """
    field_anchor_links = field_anchor_links or {}
    utility_support_tables = utility_support_tables or {}
    for node in nodes:
        key = f"{node['schema']}.{node['table']}"
        has_signal = node["has_lineage"] or bool(table_to_l4_index.get(key)) or bool(suggested_candidates.get(key))
        if has_signal:
            node["zombie_flag"] = "none"
        elif node["row_count"] == 0:
            node["zombie_flag"] = "never_activated"
        elif field_anchor_links.get(key):
            node["zombie_flag"] = "field_anchored"
        elif (node["schema"], node["table"]) in utility_support_tables:
            node["zombie_flag"] = "utility_support"
            node["utility_support_reason"] = utility_support_tables[(node["schema"], node["table"])]
        else:
            node["zombie_flag"] = "suspected_zombie"


# ---------------------------------------------------------------------------
# 字段级血缘：视图SELECT列表解析
# ---------------------------------------------------------------------------

_STRUCTURE_KEYWORDS = {
    "ON", "WHERE", "GROUP", "ORDER", "WINDOW", "LEFT", "RIGHT", "INNER",
    "JOIN", "USING", "AS", "FULL", "CROSS", "NATURAL",
}
_COL_REF_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\.("[^"]+"|[A-Za-z_][A-Za-z0-9_]*)')
_AS_TAIL_RE = re.compile(r'\bAS\s+("[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s*$', re.IGNORECASE)
_BARE_DIRECT_RE = re.compile(r'^\s*(?:([A-Za-z_][A-Za-z0-9_]*)\.)?("[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s*$')
_DIRECT_WITH_AS_RE = re.compile(
    r'^\s*(?:([A-Za-z_][A-Za-z0-9_]*)\.)?("[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s+AS\s+("[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s*$',
    re.IGNORECASE,
)


def _split_top_level(text: str, sep: str = ',') -> list[str]:
    """按括号深度=0的分隔符切分，字符串字面量(单/双引号)内的逗号不切，
    避免把date_trunc('month'::text, col)这类函数调用里的逗号误判成列分隔符。"""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    in_string = False
    string_char = ''
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            current.append(ch)
            if ch == string_char:
                if i + 1 < len(text) and text[i + 1] == string_char:
                    current.append(text[i + 1])
                    i += 1
                else:
                    in_string = False
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = True
            string_char = ch
            current.append(ch)
            i += 1
            continue
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    parts.append(''.join(current))
    return parts


def _is_unparseable_structure(definition: str) -> str | None:
    """CTE(WITH)/UNION/窗口函数(OVER)的视图SQL结构太复杂，用简单解析容易解析错
    却不自知——如实标'结构复杂未解析'，不猜。"""
    stripped = definition.strip()
    if re.match(r'^WITH\b', stripped, re.IGNORECASE):
        return "含CTE(WITH子句)，需要完整SQL解析器，未解析"
    if re.search(r'\bUNION\b', stripped, re.IGNORECASE):
        return "含UNION，输出列在多个分支里可能来自不同源，未解析"
    if re.search(r'\bOVER\s*\(', stripped, re.IGNORECASE):
        return "含窗口函数(OVER)，未解析"
    return None


def _extract_select_and_from(definition: str) -> tuple[str, str] | None:
    select_m = re.search(r'\bSELECT\b', definition, re.IGNORECASE)
    from_m = re.search(r'\bFROM\b', definition, re.IGNORECASE)
    if not select_m or not from_m:
        return None
    select_list = definition[select_m.end():from_m.start()]
    rest = definition[from_m.start():]
    end_m = re.search(r'\b(WHERE|GROUP\s+BY|ORDER\s+BY|WINDOW)\b', rest, re.IGNORECASE)
    from_clause = rest[:end_m.start()] if end_m else rest
    return select_list, from_clause.rstrip().rstrip(';')


def _parse_from_aliases(from_clause: str, default_schema: str) -> dict[str, tuple[str, str]]:
    """只按JOIN关键字切分(FROM只在开头出现一次单独剥掉)，避免"IS DISTINCT FROM"
    这种合法SQL短语里的FROM被误认成新表的引用——这是实测踩过的坑，不是假设。
    裸表名(没写schema前缀)按Postgres自己的dump习惯——同schema省略前缀——归到
    视图所在schema下，不留None，否则后面按known_tables校验时会被误判成"表不存在"
    而整条sources被静默丢弃(已实测踩过这个坑)。"""
    from_clause = from_clause.strip()
    segments = re.split(r'\bJOIN\b', from_clause, flags=re.IGNORECASE)
    segments[0] = re.sub(r'^\s*FROM\s+', '', segments[0], flags=re.IGNORECASE)

    alias_map: dict[str, tuple[str, str]] = {}
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        head = re.split(r'\bON\b', seg, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        tokens = head.split()
        if not tokens:
            continue
        table_token = tokens[0].strip(',')
        alias = None
        if len(tokens) >= 2:
            candidate = tokens[1].strip(',')
            if candidate.upper() == 'AS' and len(tokens) >= 3:
                alias = tokens[2].strip(',')
            elif candidate.upper() not in _STRUCTURE_KEYWORDS:
                alias = candidate
        if '.' in table_token:
            schema, table = table_token.split('.', 1)
        else:
            schema, table = default_schema, table_token
        table = table.strip('"')
        if alias:
            alias_map[alias] = (schema, table)
        alias_map[table] = (schema, table)
    return alias_map


def _parse_select_item(item: str, alias_map: dict[str, tuple[str, str]]) -> dict | None:
    item = item.strip()
    m = _BARE_DIRECT_RE.match(item)
    if m:
        alias, col = m.groups()
        col = col.strip('"')
        source = alias_map.get(alias) if alias else None
        return {"output_column": col, "transform": "direct", "sources": [{"schema": source[0], "table": source[1], "column": col}] if source else []}
    m = _DIRECT_WITH_AS_RE.match(item)
    if m:
        alias, col, out = m.groups()
        col, out = col.strip('"'), out.strip('"')
        source = alias_map.get(alias) if alias else None
        return {"output_column": out, "transform": "direct", "sources": [{"schema": source[0], "table": source[1], "column": col}] if source else []}
    as_m = _AS_TAIL_RE.search(item)
    if not as_m:
        return None
    out = as_m.group(1).strip('"')
    expr = item[:as_m.start()]
    sources = []
    seen = set()
    for alias, col in _COL_REF_RE.findall(expr):
        col = col.strip('"')
        source = alias_map.get(alias)
        if not source:
            continue
        key = (source, col)
        if key in seen:
            continue
        seen.add(key)
        sources.append({"schema": source[0], "table": source[1], "column": col})
    return {"output_column": out, "transform": "derived" if sources else "computed_literal", "sources": sources}


def extract_field_column_lineage(db_query: Callable[[str, tuple], list[dict]], known_tables: set[tuple[str, str]]) -> dict:
    """把表级视图依赖挖深到字段级：这个视图的输出字段，是直接透传(direct)哪张表
    的哪个字段，还是由哪些字段计算(derived)出来的。只处理单层SELECT(无CTE/UNION/
    窗口函数)的视图，复杂的如实标注跳过原因，不猜错误答案。"""
    views = db_query(
        "SELECT table_schema, table_name FROM information_schema.views WHERE table_schema = ANY(%s)",
        (SCHEMAS,),
    )
    resolved: list[dict] = []
    unparsed: list[dict] = []
    for v in views:
        schema, name = v["table_schema"], v["table_name"]
        key = (schema, name)
        rows = db_query("SELECT pg_get_viewdef(%s::regclass, true) AS def", (f"{schema}.{name}",))
        definition = rows[0]["def"] if rows else ""

        reason = _is_unparseable_structure(definition)
        if reason:
            unparsed.append({"schema": schema, "table": name, "reason": reason})
            continue

        parts = _extract_select_and_from(definition)
        if not parts:
            unparsed.append({"schema": schema, "table": name, "reason": "未能定位SELECT/FROM结构"})
            continue
        select_list, from_clause = parts
        alias_map = _parse_from_aliases(from_clause, schema)

        columns = []
        for item in _split_top_level(select_list):
            if not item.strip():
                continue
            parsed = _parse_select_item(item, alias_map)
            if parsed is None:
                continue
            resolved_sources = [s for s in parsed["sources"] if (s["schema"], s["table"]) in known_tables]
            columns.append({
                "output_column": parsed["output_column"],
                "transform": parsed["transform"] if resolved_sources or parsed["transform"] == "computed_literal" else "computed_literal",
                "sources": resolved_sources,
            })
        resolved.append({"schema": schema, "table": name, "columns": columns})

    return {
        "resolved_views": resolved,
        "unparsed_views": unparsed,
    }


# ---------------------------------------------------------------------------
# 同名字段跨表索引
# ---------------------------------------------------------------------------

def build_field_index(db_catalog: dict, db_query: Callable[[str, tuple], list[dict]]) -> dict:
    """按字段名跨表分组的索引——纯统计，不断言关系。字段是某表主键的，那张表标
    "源头"(origin)；其他表如果有真实外键指向该源头，标"foreign_key_confirmed"；
    只是同名但没建外键的，标"same_name_business_confirmed"——2026-08-05已向业务
    数据方核实，字段名相同时业务含义确实一致，这个前提已确认，不是每次都要重新假设。
    """
    known_tables = {(t["schema"], t["table"]): t for t in db_catalog["tables"] if t["schema"] != "process_analytics"}

    pk_rows = db_query(
        """SELECT tc.table_schema, tc.table_name, kcu.column_name
             FROM information_schema.table_constraints tc
             JOIN information_schema.key_column_usage kcu
               ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = ANY(%s)""",
        (SCHEMAS,),
    )
    pk_set = {(r["table_schema"], r["table_name"], r["column_name"]) for r in pk_rows}

    fk_rows = db_query(
        """SELECT tc.table_schema, tc.table_name, kcu.column_name,
                  ccu.table_schema AS foreign_schema, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
             FROM information_schema.table_constraints tc
             JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
             JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = ANY(%s)""",
        (SCHEMAS,),
    )
    fk_by_child = {
        (r["table_schema"], r["table_name"], r["column_name"]): (r["foreign_schema"], r["foreign_table"], r["foreign_column"])
        for r in fk_rows
    }

    by_field: dict[str, list[dict]] = {}
    for (schema, table), t in known_tables.items():
        for col in t["columns"]:
            name = col["name"]
            if name in _AUDIT_COLUMNS:
                continue
            fk_target = fk_by_child.get((schema, table, name))
            by_field.setdefault(name, []).append({
                "schema": schema,
                "table": table,
                "is_primary_key": (schema, table, name) in pk_set,
                "fk_target": {"schema": fk_target[0], "table": fk_target[1], "column": fk_target[2]} if fk_target else None,
            })

    fields = {}
    for name, entries in by_field.items():
        if len(entries) < 2:
            continue
        origins = [{"schema": e["schema"], "table": e["table"]} for e in entries if e["is_primary_key"]]
        usages = []
        for e in entries:
            if e["is_primary_key"]:
                confidence = "origin"
            elif e["fk_target"]:
                confidence = "foreign_key_confirmed"
            else:
                confidence = "same_name_business_confirmed"
            usages.append({
                "schema": e["schema"],
                "table": e["table"],
                "confidence": confidence,
                "fk_target": e["fk_target"],
            })
        fields[name] = {"field_name": name, "origin_tables": origins, "usages": usages}

    return {
        "schema_version": "vnw.field-index.v1",
        "source_policy": (
            "按字段名跨表统计，非断言关系。origin=该表将此字段设为主键；"
            "foreign_key_confirmed=有真实外键指向源头；"
            "same_name_business_confirmed=仅同名无外键，但2026-08-05已向业务数据方核实"
            "同名字段业务含义一致，不是猜测。审计类字段(batch_id等)不纳入。"
        ),
        "fields": fields,
    }
