"""表级根因分析：基于真实数据血缘(data_lineage.json)+已确认L4关联，用AI辅助
推理补全业务数据分析五层结构里的L3根因层(表级上下游血缘+任务特征聚类)和L4
反向补全层(隐藏产出候选)。

和l3_analysis_runner.py的区别：
- 这是表级、跨104张表一次性分析——"任务特征聚类"本质是横向比较任务，必须让
  模型同时看到多张表的血缘位置才能聚出有意义的类，不能像L3分析那样按L3拆开跑；
- 没有l3_analysis_contract.py那套task/priority_draft/decision_draft复杂契约，
  这里的契约结构简单得多(每张表只有task_cluster+hidden_deliverables两块)；
- 没有人工预审门槛——校验通过就直接发布进table_root_cause_analysis.json，
  复核在浏览器页面上对着MODEL_DRAFT标签做，不在发布前做。

复用的纪律：模型只能引用fact_pack里出现的表/L4，禁止编造未出现的血缘关系或
凭空发明新L4；全部标注MODEL_DRAFT，不允许输出CONFIRMED。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from tools.llm_client import DEFAULT_MODEL, call_json_model

SCHEMA_VERSION = "vnw.table-root-cause.v1"

# 任务特征聚类固定枚举——不是自由聚类，是为了让输出可校验、可跨表比较。
# 每个类型的判定依据都来自真实in/out-degree分布实测(如agg_sales_base
# in=0/out=11是源头，dim_product_id in=10/out=10是双向枢纽)，不是臆造分类。
TASK_CLUSTER_LABELS = {
    "源头采集型": "血缘位置上没有真实上游(in-degree=0)但有下游，是数据进入本系统的起点——原始录入/批量导入类任务",
    "枢纽整合型": "血缘位置上同时有较多上游和下游(各≥3条边)，是被广泛引用的核心整合点——主数据维护/多方核对类任务，出错会向外扩散",
    "终端消费型": "只有上游、没有下游(out-degree=0)，是数据链路的末端产出——报表/看板生成类任务",
    "规则配置型": "table_type为配置表/规则表，通常连接度不高——规则/参数维护类任务，人工低频操作但影响面大",
    "直通转换型": "上下游各只有少量边(通常各1-2条)，处于链路中段——格式转换/清洗类任务",
    "孤立支撑型": "没有真实血缘边(has_lineage=false)，独立于可追踪的主链路之外——人工维护/外部系统落地/纯参照类任务",
}


def _json_from_text(text: str) -> dict:
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.S)
    if fenced:
        cleaned = fenced.group(1)
    return json.loads(cleaned)


def load_api_config(agent_root: Path) -> tuple[str, str]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    model = os.environ.get("VNW_ANALYSIS_MODEL", "").strip() or DEFAULT_MODEL
    config_path = agent_root / "02_配置项目_Configure_Project/deepseek_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        api_key = api_key or str(config.get("DEEPSEEK_API_KEY", "")).strip()
        model = str(config.get("model", "")).strip() or model
    return api_key, model


def build_table_fact_pack(
    db_catalog: dict, data_lineage: dict, table_to_l4_index: dict[str, list[dict]]
) -> list[dict]:
    """给104张表(不含process_analytics)各生成一条精简证据，供模型做跨表聚类
    推理。上下游只用data_lineage.json里的真实edges反查，不猜测；related_l4s
    带上deliverable文本，供L4层反向补全时对比已记录的交付物。"""
    node_by_key = {f"{n['schema']}.{n['table']}": n for n in data_lineage["nodes"]}
    upstream_by_key: dict[str, list[dict]] = {}
    downstream_by_key: dict[str, list[dict]] = {}
    for e in data_lineage["edges"]:
        from_key = f"{e['from_schema']}.{e['from_table']}"
        to_key = f"{e['to_schema']}.{e['to_table']}"
        from_label = node_by_key.get(from_key, {}).get("business_label", from_key)
        to_label = node_by_key.get(to_key, {}).get("business_label", to_key)
        downstream_by_key.setdefault(from_key, []).append(
            {"key": to_key, "business_label": to_label, "edge_type": e["edge_type"]}
        )
        upstream_by_key.setdefault(to_key, []).append(
            {"key": from_key, "business_label": from_label, "edge_type": e["edge_type"]}
        )

    packs = []
    for table in db_catalog["tables"]:
        if table["schema"] == "process_analytics":
            continue
        key = f"{table['schema']}.{table['table']}"
        node = node_by_key.get(key, {})
        related = table_to_l4_index.get(key, [])
        packs.append({
            "key": key,
            "business_label": node.get("business_label", table["table"]),
            "table_type": table.get("table_type", "其他"),
            "row_count": table["row_count"],
            "has_lineage": node.get("has_lineage", False),
            "upstream": upstream_by_key.get(key, []),
            "downstream": downstream_by_key.get(key, []),
            "related_l4s": [
                {
                    "l3_code": r["l3_code"], "l4_code": r["l4_code"], "l4_name": r["l4_name"],
                    "deliverable": r.get("deliverable"), "deliverable_type": r.get("deliverable_type"),
                }
                for r in related
            ],
        })
    return packs


def build_prompt_payload(fact_packs: list[dict]) -> str:
    return json.dumps({"tables": fact_packs}, ensure_ascii=False, separators=(",", ":"))


def chunk_fact_packs(fact_packs: list[dict], batch_size: int = 15) -> list[list[dict]]:
    """104张表一次性喂给模型会导致输出被截断/连接中断(实测出现过
    JSONDecodeError和IncompleteRead两种失败)。按批拆分是安全的——
    task_cluster的判定依据(自身in/out-degree、has_lineage、table_type)
    都是表自己的属性，不需要跨表比较，拆批不影响聚类质量。"""
    return [fact_packs[i:i + batch_size] for i in range(0, len(fact_packs), batch_size)]


def _known_keys(fact_packs: list[dict]) -> dict[str, dict]:
    return {p["key"]: p for p in fact_packs}


def validate_table_root_cause(package: dict, fact_packs: list[dict]) -> None:
    """只允许引用fact_pack里真实出现的表/L4/血缘边，禁止模型编造未出现的关系。"""
    known = _known_keys(fact_packs)
    tables = package.get("tables")
    if not isinstance(tables, list):
        raise ValueError("输出缺少tables数组")
    seen_keys = set()
    for item in tables:
        key = item.get("key")
        if key not in known:
            raise ValueError(f"引用了fact_pack以外的表：{key}")
        seen_keys.add(key)
        pack = known[key]
        layer3 = item.get("layer3") or {}
        layer4 = item.get("layer4") or {}

        known_upstream = {u["key"] for u in pack["upstream"]}
        known_downstream = {d["key"] for d in pack["downstream"]}
        for u in layer3.get("upstream", []):
            if u.get("key") not in known_upstream:
                raise ValueError(f"{key}的layer3.upstream引用了未在真实血缘边里出现的表：{u.get('key')}")
        for d in layer3.get("downstream", []):
            if d.get("key") not in known_downstream:
                raise ValueError(f"{key}的layer3.downstream引用了未在真实血缘边里出现的表：{d.get('key')}")

        cluster = (layer3.get("task_cluster") or {}).get("label")
        if cluster not in TASK_CLUSTER_LABELS:
            raise ValueError(f"{key}的task_cluster.label不在固定枚举内：{cluster}")

        known_l4_codes = {r["l4_code"] for r in pack["related_l4s"]}
        for hd in layer4.get("hidden_deliverables", []):
            if hd.get("l4_code") not in known_l4_codes:
                raise ValueError(f"{key}的hidden_deliverables引用了该表related_l4s以外的L4：{hd.get('l4_code')}")

        if layer3.get("status") != "MODEL_DRAFT" or layer4.get("status") != "MODEL_DRAFT":
            raise ValueError(f"{key}的layer3/layer4必须标注MODEL_DRAFT")

    missing = set(known) - seen_keys
    if missing:
        raise ValueError(f"输出缺少{len(missing)}张表的分析结果，例如：{sorted(missing)[:5]}")


def run_table_root_cause_analysis(
    agent_root: Path, db_catalog: dict, data_lineage: dict, table_to_l4_index: dict, batch_size: int = 15,
) -> dict:
    """prepare + call + validate 一体化——没有人工预审门槛，校验通过即为发布态。
    按批调用模型(见chunk_fact_packs)，每批各自校验，全部通过后再合并发布；
    任何一批校验失败都会中止整体发布，不会写入部分结果。"""
    agent_root = Path(agent_root)
    prompt_path = agent_root / "08_设计提示词_Design_Prompts/表级根因分析模型_v1.0.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    fact_packs = build_table_fact_pack(db_catalog, data_lineage, table_to_l4_index)
    api_key, model = load_api_config(agent_root)
    if not api_key:
        raise RuntimeError("VNW未配置模型凭证(DEEPSEEK_API_KEY或deepseek_config.json)")

    batches = chunk_fact_packs(fact_packs, batch_size)
    all_tables: list[dict] = []
    for batch in batches:
        raw = call_json_model(system_prompt, build_prompt_payload(batch), api_key=api_key, model=model)
        package = _json_from_text(raw)
        validate_table_root_cause(package, batch)
        all_tables.extend(package["tables"])

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_run": {
            "model_name": model, "generated_at": datetime.now(timezone.utc).isoformat(),
            "batch_count": len(batches), "batch_size": batch_size,
        },
        "tables": all_tables,
    }


def write_table_root_cause_analysis(result: dict, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
