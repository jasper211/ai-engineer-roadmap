"""入口①场景分析：给人工authoring的业务场景记录(business_scenarios/*.json)
派生出后四环——流程现状/数据治理/任务清单/流程优化——不改动人工原始记录，
也不引入新的AI调用，全部是对已有真实数据(model_snapshots)的机械规则/直接
复用，和data_lineage.json/table_analysis.json同样的SSOT+DERIVED分层原则。

流程现状(build_process_status)：l3_trace里人工判断的gate_a原样保留展示，
不用重新查询到的live_gates静默覆盖——两层证据并列。
数据治理(build_data_governance)：判定语言复用table_analysis.py的
_governance_track/_process_lever_track同一套说法，不发明新表述。
任务清单(build_task_list)：人工next_steps和机械算出的治理条目统一转成
结构化任务，各自标注来源；没有依据的字段(优先级/负责人)不臆造。
流程优化(build_process_optimization)：只对场景本身发现的建模缺口
(GATE_A_BLOCKED)生成条目——这类缺口是"价值节点映射/熔断判定未完成"，
和该L3已有的decision_drafts(AI任务试点建议，前提是任务/Tier已经就绪)
是两件不同层次的事，机械规则判不出语义上是否覆盖，因此不假装"匹配"，
如实并列展示两边证据，把"是否已被现有流程模型覆盖"的判断交给人工——
如果现有AI任务建议里确实没有能解决这个缺口的，就是本场景新发现的优化点，
需要把这个发现补充进该L3的分析输入材料后重跑统一分析。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "vnw.business-scenario-analysis.v1"


def build_process_status(scenario: dict, model_index: dict[str, dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for component in scenario.get("components", []):
        for trace in component.get("l3_trace", []):
            code = trace["l3_code"]
            if code in seen:
                continue
            entry = model_index.get(code)
            seen[code] = {
                "l3_code": code,
                "l3_name": entry["l3_name"] if entry else None,
                "manual_note": trace.get("note"),
                "manual_gate_a": trace.get("gate_a"),
                "in_current_db": trace["in_current_db"],
                "live_gates": entry["gates"] if entry else None,
                "model_readiness": entry["classification"] if entry else None,
                "has_demo": bool(entry.get("has_demo")) if entry else False,
            }
    return list(seen.values())


def build_data_governance(scenario: dict, process_status: list[dict]) -> list[dict]:
    items: list[dict] = []
    for component in scenario.get("components", []):
        if component.get("state") in ("B", "C"):
            reason = (
                "状态C：完全无系统化数据来源，需要先确认核算方式或补齐数据源"
                if component["state"] == "C"
                else "状态B：有表但未标准化/无数据，需要先确认为何未populate"
            )
            items.append({"flag": "DATA_GAP", "component_name": component["component_name"], "reason": reason})
    for ps in process_status:
        if not ps["in_current_db"]:
            items.append({
                "flag": "PROCESS_MISSING", "l3_code": ps["l3_code"],
                "reason": "当前数据库process_analytics.dim_process未覆盖此L3，需先确认是否已改名/合并/从未建模",
            })
        elif ps["live_gates"] and ps["live_gates"].get("A") == "BLOCKED":
            items.append({
                "flag": "GATE_A_BLOCKED", "l3_code": ps["l3_code"],
                "reason": "Gate A未通过，价值节点映射/熔断判定尚未完整，需先推进该L3的建模",
            })
    return items


def build_task_list(scenario: dict, data_governance: list[dict]) -> list[dict]:
    tasks: list[dict] = []
    scenario_id = scenario["scenario_id"]
    for i, step in enumerate(scenario.get("next_steps", []), 1):
        tasks.append({
            "task_id": f"{scenario_id}-T{i}", "type": "业务确认",
            "description": step, "source": "人工next_steps",
        })
    type_by_flag = {"DATA_GAP": "数据治理", "PROCESS_MISSING": "流程建模", "GATE_A_BLOCKED": "流程建模"}
    for i, item in enumerate(data_governance, 1):
        tasks.append({
            "task_id": f"{scenario_id}-G{i}", "type": type_by_flag.get(item["flag"], "数据治理"),
            "description": item["reason"], "source": "机械规则(data_governance)",
        })
    return tasks


def build_process_optimization(process_status: list[dict], data_governance: list[dict], load_snapshot) -> list[dict]:
    gate_blocked = {item["l3_code"]: item for item in data_governance if item["flag"] == "GATE_A_BLOCKED"}
    items: list[dict] = []
    for ps in process_status:
        if ps["l3_code"] not in gate_blocked:
            continue
        snapshot = load_snapshot(ps["l3_code"]) if ps["model_readiness"] else None
        drafts = (snapshot.get("analysis", {}).get("decision_drafts") or []) if snapshot else []
        existing = [
            {"priority": d.get("priority"), "title": d.get("title"), "pilot_scope": d.get("pilot_scope")}
            for d in drafts[:3]
        ]
        conclusion = (
            "该L3尚未产出统一分析结果，无法比对，需先推进建模后再判断"
            if not existing
            else "上面是该L3已有的AI任务试点建议(基于当前证据产出，前提是任务/Tier已就绪)；"
                 "如果里面有能直接解决本场景这个缺口的，说明流程模型已覆盖，可直接参考推进；"
                 "如果没有相关的，说明这是本场景新发现、现有流程模型未覆盖的优化点，"
                 "需要把这个发现补充进该L3的分析输入材料(相关SOP/规则/证据)后重跑统一分析"
        )
        items.append({
            "l3_code": ps["l3_code"], "l3_name": ps["l3_name"],
            "scenario_finding": gate_blocked[ps["l3_code"]]["reason"],
            "existing_decision_drafts": existing,
            "conclusion": conclusion,
        })
    return items


def build_scenario_analysis(scenario: dict, model_index: dict[str, dict], load_snapshot) -> dict:
    process_status = build_process_status(scenario, model_index)
    data_governance = build_data_governance(scenario, process_status)
    task_list = build_task_list(scenario, data_governance)
    process_optimization = build_process_optimization(process_status, data_governance, load_snapshot)
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": scenario["scenario_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "process_status": process_status,
        "data_governance": data_governance,
        "task_list": task_list,
        "process_optimization": process_optimization,
    }
