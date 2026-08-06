"""入口①场景分析：给人工authoring的业务场景记录(business_scenarios/*.json)
用AI辅助推理产出后四环——目标/流程现状/数据治理/任务清单/流程优化。

和上一版的区别：上一版是纯机械规则(读l3_trace.gate_a、组成项state B/C)，
只能回答"场景里已经提到的东西现在什么状态"，回答不了"做成这件事到底需要
什么"——这需要结合业务场景本身和行业通常做法做推理，是简单数据映射匹配
解决不了的，因此改为调用大模型，架构上和table_root_cause_analysis.py同源：
把全部真实存在的L3(l3_catalog)和表(table_catalog)摘要喂给模型，模型只能
在这个真实目录里挑相关项，不能凭空编造L3编码或表名；建议新增的表要明确
标注(new_table_proposal)，不能包装成已存在的表；全部标注MODEL_DRAFT。

场景需求(definition/components)和数据现状(business_evidence/state)两块
保持人工authoring不变，不在这个模块的范围内。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.llm_client import DEFAULT_MODEL, call_json_model

SCHEMA_VERSION = "vnw.business-scenario-analysis.v2"


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


def build_l3_catalog(model_index: dict) -> list[dict]:
    """74个L3的精简摘要——只给相关性判断需要的信息，不带完整L4明细。"""
    catalog = []
    for m in model_index.get("models", []):
        catalog.append({
            "l3_code": m["l3_code"],
            "l3_name": m["l3_name"],
            "l4_count": m.get("l4_count", 0),
            "classification": m.get("classification"),
            "kpis": [k.get("kpi_name") for k in m.get("kpis", [])],
        })
    return catalog


def build_table_catalog(db_catalog: dict) -> list[dict]:
    """122张业务数据表的精简摘要——不带columns明细，本层只需要判断
    "有没有能支撑某个数据需求的表"，不需要判断具体字段。"""
    catalog = []
    for t in db_catalog.get("tables", []):
        if t["schema"] == "process_analytics":
            continue
        catalog.append({
            "schema": t["schema"],
            "table": t["table"],
            "description": t.get("description", ""),
            "table_type": t.get("table_type", "其他"),
            "row_count": t.get("row_count", 0),
        })
    return catalog


def build_prompt_payload(scenario: dict, l3_catalog: list[dict], table_catalog: list[dict]) -> str:
    return json.dumps(
        {"scenario": scenario, "l3_catalog": l3_catalog, "table_catalog": table_catalog},
        ensure_ascii=False, separators=(",", ":"),
    )


def validate_scenario_analysis(package: dict, l3_catalog: list[dict], table_catalog: list[dict]) -> None:
    known_l3 = {c["l3_code"] for c in l3_catalog}
    known_tables = {f"{c['schema']}.{c['table']}" for c in table_catalog}

    if package.get("status") != "MODEL_DRAFT":
        raise ValueError("输出必须标注status=MODEL_DRAFT")

    goal = package.get("goal")
    if not isinstance(goal, dict) or not all(goal.get(k) for k in ("definition", "industry_logic", "our_approach")):
        raise ValueError("goal缺少definition/industry_logic/our_approach")

    process_status = package.get("process_status")
    if not isinstance(process_status, list) or not process_status:
        raise ValueError("process_status缺失或为空")
    for item in process_status:
        for l3 in item.get("relevant_l3s", []):
            if l3.get("l3_code") not in known_l3:
                raise ValueError(f"process_status引用了l3_catalog以外的L3：{l3.get('l3_code')}")
            if l3.get("relationship") not in ("核心支撑", "部分支撑", "存在缺口"):
                raise ValueError(f"relationship不在固定枚举内：{l3.get('relationship')}")

    data_governance = package.get("data_governance")
    if not isinstance(data_governance, list):
        raise ValueError("data_governance缺失")
    for item in data_governance:
        for t in item.get("existing_tables", []):
            key = f"{t.get('schema')}.{t.get('table')}"
            if key not in known_tables:
                raise ValueError(f"data_governance引用了table_catalog以外的表：{key}")

    task_list = package.get("task_list")
    if not isinstance(task_list, list) or not task_list:
        raise ValueError("task_list缺失或为空")
    known_task_ids = {t.get("task_id") for t in task_list}
    for t in task_list:
        for dep in t.get("depends_on", []):
            if dep not in known_task_ids:
                raise ValueError(f"task_list的depends_on引用了不存在的task_id：{dep}")
        if t.get("priority") not in ("P0", "P1", "P2"):
            raise ValueError(f"priority不在固定枚举内：{t.get('priority')}")

    process_optimization = package.get("process_optimization")
    if not isinstance(process_optimization, list):
        raise ValueError("process_optimization缺失")


def run_scenario_analysis(agent_root: Path, scenario: dict, model_index: dict, db_catalog: dict, max_attempts: int = 2) -> dict:
    agent_root = Path(agent_root)
    prompt_path = agent_root / "08_设计提示词_Design_Prompts/场景分析模型_v1.0.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    l3_catalog = build_l3_catalog(model_index)
    table_catalog = build_table_catalog(db_catalog)
    api_key, model = load_api_config(agent_root)
    if not api_key:
        raise RuntimeError("VNW未配置模型凭证(DEEPSEEK_API_KEY或deepseek_config.json)")

    payload = build_prompt_payload(scenario, l3_catalog, table_catalog)
    last_error: Exception | None = None
    package = None
    # 大模型偶发输出不符合grounding约束(如引用了目录以外的编码)，不是
    # 网络问题，call_json_model自己的重试机制不覆盖这种情况；这里单独
    # 重试几次，仍失败才真正报错。
    for _ in range(max_attempts):
        raw = call_json_model(system_prompt, payload, api_key=api_key, model=model)
        try:
            package = _json_from_text(raw)
            validate_scenario_analysis(package, l3_catalog, table_catalog)
            last_error = None
            break
        except (ValueError, json.JSONDecodeError) as error:
            last_error = error
            package = None
    if last_error is not None or package is None:
        raise RuntimeError(f"场景分析模型输出连续{max_attempts}次未通过校验：{last_error}")

    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": scenario["scenario_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_run": {"model_name": model, "generated_at": datetime.now(timezone.utc).isoformat()},
        "status": package["status"],
        "goal": package["goal"],
        "process_status": package["process_status"],
        "data_governance": package["data_governance"],
        "task_list": package["task_list"],
        "process_optimization": package["process_optimization"],
    }


def write_scenario_analysis(result: dict, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
