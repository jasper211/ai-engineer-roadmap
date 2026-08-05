"""业务数据分析·入口②系统性覆盖扫描：以104张业务表(public/comm_sandbox/fin_sandbox，
不含process_analytics)为锚点的五层分析结构。

五层定义（完整保留，不因数据缺口而降级替代）：
- L1描述层：这张表的事实是什么（有数据/没数据分别是什么事实），建立基线
- L2诊断层：现状分析——关联哪些L3/L4、谁负责、数据录入健康度，定位现状
- L3归因层：相关性/跟进/聚类分析——哪些表背后的任务高耗时/高错误/高成本，
  根因是流程设计/岗位能力/系统支撑不够/纯劳动密集型，哪类任务天然适合AI
- L4预测层：AI介入后的ROI/质量/产能释放/敏感性测算，把可行性从定性变定量
- L5决策层：该做什么，衔接流程模型面板D的优先级矩阵

L3/L4今天全部标注BLOCKED——不是没做，是真实核查后发现底层输入不存在：
process_analytics.fact_card和fact_agent（唯一设计了耗时/错误率/agent协同字段的
两张表）当前均为0行，且全库没有任何薪酬/人力成本单价字段。这里如实描述缺什么，
不做代理指标或假设级替代，等这些输入真实产生后再激活，不是现在就编一个近似值。
"""
from __future__ import annotations

import json
from pathlib import Path

L3_REQUIRED_INPUTS = [
    "process_analytics.fact_card：任务级耗时(duration_hours)/SLA达成(sla_hours_actual/sla_breach_flag)/错误(error_flag)/人工干预(agent_assist_hours)——当前0行",
    "process_analytics.fact_agent：Agent执行统计(sla_breach_rate/error_count/rework_count_total)——当前0行",
]
L4_REQUIRED_INPUTS = [
    "人力成本单价：全库任何schema都没有薪酬/人力成本字段(dim_employee只有档案信息)，需HR/Finance提供",
    "process_analytics.fact_card真实运行数据：用于测算AI介入前后的耗时/错误率差异，当前0行",
]


def data_health_bucket(row_count: int) -> str:
    if row_count == 0:
        return "未开始录入"
    if row_count < 10:
        return "试点阶段(个位数记录)"
    if row_count < 1000:
        return "小规模在跑"
    return "规模化在跑"


def build_table_to_l4_index(l3_codes: list[str], load_l3_snapshot) -> dict[str, list[dict]]:
    """从各L3快照的l4.business_evidence里反向建立 table -> [{l3_code,l4_code,l4_name,position_family}] 索引。"""
    index: dict[str, list[dict]] = {}
    for l3_code in l3_codes:
        snapshot = load_l3_snapshot(l3_code)
        if snapshot is None:
            continue
        for l4 in snapshot.get("l4s", []):
            position = l4.get("position_family")
            for evidence in l4.get("business_evidence", []):
                key = f"{evidence['schema']}.{evidence['table']}"
                index.setdefault(key, []).append({
                    "l3_code": l3_code,
                    "l3_name": snapshot.get("l3_name", ""),
                    "l4_code": l4["l4_code"],
                    "l4_name": l4["l4_name"],
                    "evidence_type": evidence["evidence_type"],
                    "confidence": evidence["confidence"],
                    "position_family": position,
                })
    return index


def build_table_analysis(db_catalog: dict, table_to_l4_index: dict[str, list[dict]]) -> dict:
    entries = []
    for table in db_catalog["tables"]:
        if table["schema"] == "process_analytics":
            continue
        key = f"{table['schema']}.{table['table']}"
        related = table_to_l4_index.get(key, [])
        has_data = table["row_count"] > 0

        layer1 = {
            "fact_statement": (
                f"{key}现有{table['row_count']}行数据。{table['description'] or '业务含义待核实。'}"
                if has_data else
                f"{key}当前0行，尚无数据录入。{table['description'] or '业务含义待核实。'}"
            ),
            "has_data": has_data,
        }

        related_l4_tiers = [
            {"l4_code": r["l4_code"], "tier": None} for r in related
        ]
        positions = {r["position_family"]["category_name"] for r in related if r.get("position_family")}
        layer2 = {
            "related_l3_l4": [
                {"l3_code": r["l3_code"], "l3_name": r["l3_name"], "l4_code": r["l4_code"], "l4_name": r["l4_name"]}
                for r in related
            ],
            "positions": sorted(positions),
            "data_health": data_health_bucket(table["row_count"]),
            "status": "已定位关联" if related else "未定位关联(未进入试点范围或确实无关联L4)",
        }

        layer3 = {
            "status": "BLOCKED",
            "goal": "相关性分析(哪些任务场景高耗时/高错误/高成本)、跟进分析(根因是流程设计/岗位能力/系统支撑不够/纯劳动密集型)、聚类分析(哪类任务天然适合AI)",
            "required_inputs": L3_REQUIRED_INPUTS,
            "reason": "全库唯一设计了耗时/错误率字段的两张表(fact_card/fact_agent)当前均为0行，没有可分析的真实任务级数据。",
        }
        layer4 = {
            "status": "BLOCKED",
            "goal": "ROI测算(节省工时×人力成本)、质量预测(AI介入后错误率)、产能释放、敏感性分析",
            "required_inputs": L4_REQUIRED_INPUTS,
            "reason": "缺人力成本单价和真实任务执行数据，测算公式需要的输入今天不存在，不做近似替代。",
        }
        layer5 = {
            "status": "PRELIMINARY" if related else "NO_BASIS",
            "note": (
                "已知关联L4的Tier/封装档位等流程模型结论可作初步参考，但完整决策需等L3/L4层激活后补充定量支撑，当前仅为初步判断。"
                if related else "无关联L4，暂无法给出决策建议。"
            ),
        }

        entries.append({
            "schema": table["schema"],
            "table": table["table"],
            "row_count": table["row_count"],
            "role": table["role"],
            "layer1": layer1,
            "layer2": layer2,
            "layer3": layer3,
            "layer4": layer4,
            "layer5": layer5,
        })
    return {
        "schema_version": "vnw.table-analysis.v1",
        "source_policy": "五层分析结构：描述/诊断层基于真实数据现算；归因/预测层如实标注BLOCKED+缺失输入，不做代理指标或假设替代",
        "tables": entries,
    }
