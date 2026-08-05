"""业务数据分析·入口②系统性覆盖扫描：以104张业务表(public/comm_sandbox/fin_sandbox，
不含process_analytics)为锚点的五层分析结构。

五层定义（完整保留，不因数据缺口而降级替代）：
- L1描述层：这张表的事实是什么（有数据/没数据分别是什么事实），建立基线
- L2诊断层：现状分析——关联哪些L3/L4、谁负责、数据录入健康度，定位现状
- L3归因层：相关性/跟进/聚类分析——哪些表背后的任务高耗时/高错误/高成本，
  根因是流程设计/岗位能力/系统支撑不够/纯劳动密集型，哪类任务天然适合AI
- L4预测层：AI介入后的ROI/质量/产能释放/敏感性测算，把可行性从定性变定量
- L5决策层：该做什么——复用L3流程模型面板D的四象限语义(优先验证/治理后推进/
  补数据规则后推进/暂缓自动化)，基于该表关联L4已有的D1-D6+候选Agent封装档位+
  两轴冲突标记做DERIVED归类（不是面板D正式工作坊象限坐标，只是同一套语义在
  表维度的推导参考，两者不互相覆盖）

L3/L4今天全部标注BLOCKED——不是没做，是真实核查后发现底层输入不存在：
process_analytics.fact_card和fact_agent（唯一设计了耗时/错误率/agent协同字段的
两张表）当前均为0行，且全库没有任何薪酬/人力成本单价字段。这里如实描述缺什么，
不做代理指标或假设级替代，等这些输入真实产生后再激活，不是现在就编一个近似值。
"""
from __future__ import annotations

import json
from pathlib import Path

from skills.unified_analysis import D_FIELDS, axis_conflict
from skills.business_data_bridge import ANALYZED_L3_CODES

L3_REQUIRED_INPUTS = [
    "process_analytics.fact_card：任务级耗时(duration_hours)/SLA达成(sla_hours_actual/sla_breach_flag)/错误(error_flag)/人工干预(agent_assist_hours)——当前0行",
    "process_analytics.fact_agent：Agent执行统计(sla_breach_rate/error_count/rework_count_total)——当前0行",
]
L4_REQUIRED_INPUTS = [
    "人力成本单价：全库任何schema都没有薪酬/人力成本字段(dim_employee只有档案信息)，需HR/Finance提供",
    "process_analytics.fact_card真实运行数据：用于测算AI介入前后的耗时/错误率差异，当前0行",
]

QUADRANT_LABELS = {
    "q1": "优先验证",
    "q2": "治理后推进",
    "q3": "补数据/规则后推进",
    "q4": "暂缓自动化",
}


def derive_l4_quadrant(rel: dict) -> dict:
    """按面板D四象限语义，对单个L4做DERIVED归类——只用该L4已有的D1-D6/Tier/
    候选Agent封装档位/业务数据证据做确定性推导，不引入新数据源，不生成伪造坐标。
    """
    d1_d6 = rel.get("d1_d6") or {}
    complete = all(d1_d6.get(field) is not None for field in D_FIELDS)
    tier = rel.get("tier") or ""
    skill = rel.get("skill_feasibility") or {}
    grade = skill.get("grade") or ""
    grade_letter = grade[0] if grade else ""
    verified = skill.get("verification_status") == "VERIFIED"
    has_business_evidence = bool(rel.get("has_business_evidence"))
    conflict = axis_conflict(tier, grade or None)

    if conflict:
        quadrant = "q2"
        rationale = f"候选Agent封装档位={grade or '未评估'}，但当前Tier={tier or '未评估'}，两轴方向冲突，需业务方澄清后再定档"
    elif not complete or not has_business_evidence:
        missing = []
        if not complete:
            missing.append("D1-D6未全覆盖")
        if not has_business_evidence:
            missing.append("该L4暂无业务数据证据支撑")
        quadrant = "q3"
        rationale = f"缺口：{'；'.join(missing)}，需补齐后再评估"
    elif grade_letter in ("A", "B") and tier == "Auto":
        quadrant = "q1"
        rationale = f"D1-D6完整、候选Agent封装={grade}、Tier={tier}方向一致，且有业务数据证据支撑，可优先验证"
    elif grade_letter == "F" or tier == "Human":
        quadrant = "q4"
        rationale = f"候选Agent封装档位={grade or '未评估'}、Tier={tier or '未评估'}，判断当前暂不具备自动化条件"
    else:
        quadrant = "q3"
        rationale = f"候选Agent封装={grade or '未评估'}、Tier={tier or '未评估'}组合暂无法明确归入优先验证或暂缓，需人工判断"

    return {
        "l4_code": rel["l4_code"],
        "l4_name": rel["l4_name"],
        "quadrant": quadrant,
        "quadrant_label": QUADRANT_LABELS[quadrant],
        "axis_conflict": conflict,
        "confidence": "confirmed_basis" if verified else "draft_basis",
        "rationale": rationale,
        "classification_basis": "DERIVED",
    }


def business_label(description: str | None, table: str) -> str:
    """从已核实的description里截取短中文名(冒号前半句)，不核实的表用表名兜底，不编造。"""
    if not description:
        return table
    for sep in ("：", ":"):
        if sep in description:
            return description.split(sep, 1)[0]
    return description


def data_health_bucket(row_count: int) -> str:
    if row_count == 0:
        return "未开始录入"
    if row_count < 10:
        return "试点阶段(个位数记录)"
    if row_count < 1000:
        return "小规模在跑"
    return "规模化在跑"


def build_table_to_l4_index(l3_codes: list[str], load_l3_snapshot) -> dict[str, list[dict]]:
    """从各L3快照的l4.business_evidence里反向建立
    table -> [{l3_code,l4_code,l4_name,position_family,d1_d6,tier,skill_feasibility,has_business_evidence}] 索引。
    d1_d6/tier/skill_feasibility随身带上，供L5决策层的DERIVED象限归类直接复用，不重新拉取快照。
    """
    index: dict[str, list[dict]] = {}
    for l3_code in l3_codes:
        snapshot = load_l3_snapshot(l3_code)
        if snapshot is None:
            continue
        for l4 in snapshot.get("l4s", []):
            position = l4.get("position_family")
            has_business_evidence = bool(l4.get("business_evidence"))
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
                    "d1_d6": l4.get("d1_d6"),
                    "tier": l4.get("tier"),
                    "skill_feasibility": l4.get("skill_feasibility"),
                    "has_business_evidence": has_business_evidence,
                })
    return index


def build_table_analysis(db_catalog: dict, table_to_l4_index: dict[str, list[dict]], l3_codes: list[str]) -> dict:
    # "未定位关联"必须区分"查过、确认没有" vs "这个L3还没排到分析"——否则73个
    # 从未分析过的L3会被误读成"确认和这张表无关"。ANALYZED_L3_CODES是显式登记
    # 表，只有登记在案的L3才算"查过"。
    analyzed_count = sum(1 for code in l3_codes if code.removeprefix("L3-") in ANALYZED_L3_CODES)
    total_l3_count = len(l3_codes)

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

        positions = {r["position_family"]["category_name"] for r in related if r.get("position_family")}
        if related:
            status = "已定位关联"
        elif analyzed_count >= total_l3_count:
            status = "未定位关联(已核实无关联)"
        else:
            status = (
                f"未定位关联——目前只对{analyzed_count}/{total_l3_count}个L3做过业务数据匹配，"
                "其余L3尚未纳入本轮分析范围，不代表这张表真的无关"
            )
        layer2 = {
            "related_l3_l4": [
                {"l3_code": r["l3_code"], "l3_name": r["l3_name"], "l4_code": r["l4_code"], "l4_name": r["l4_name"]}
                for r in related
            ],
            "positions": sorted(positions),
            "data_health": data_health_bucket(table["row_count"]),
            "status": status,
            "analyzed_l3_coverage": {"analyzed": analyzed_count, "total": total_l3_count},
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
        l4_quadrants = [derive_l4_quadrant(r) for r in related]
        conflict_count = sum(1 for q in l4_quadrants if q["axis_conflict"])
        layer5 = {
            "status": "PRELIMINARY" if related else "NO_BASIS",
            "note": (
                f"{len(l4_quadrants)}个关联L4已按面板D四象限语义(优先验证/治理后推进/补数据规则后推进/暂缓自动化)"
                f"完成DERIVED归类{f'，其中{conflict_count}个存在D1-D6/Tier轴与候选Agent封装轴方向冲突，需业务方澄清' if conflict_count else ''}；"
                "该归类只是同一套语义在表维度的推导参考，不等同于面板D工作坊的正式象限坐标，完整决策仍需等L3/L4层激活后补充定量支撑。"
                if related else "无关联L4，暂无法给出决策建议。"
            ),
            "l4_quadrants": l4_quadrants,
        }

        entries.append({
            "schema": table["schema"],
            "table": table["table"],
            "row_count": table["row_count"],
            "role": table["role"],
            "table_type": table.get("table_type", "其他"),
            "description": table["description"],
            "business_label": business_label(table["description"], table["table"]),
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
