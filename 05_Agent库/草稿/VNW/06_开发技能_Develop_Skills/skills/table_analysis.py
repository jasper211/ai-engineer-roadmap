"""业务数据分析·入口②系统性覆盖扫描：以104张业务表(public/comm_sandbox/fin_sandbox，
不含process_analytics)为锚点的五层分析结构。

五层定义（2026-08-06重构L3/L4/L5，完整保留，不因数据缺口而降级替代）：
- L1描述层：这张表的事实是什么（有数据/没数据分别是什么事实），建立基线
- L2诊断层：现状分析——关联哪些L3/L4、谁负责、数据录入健康度，定位现状
- L3根因分析层：基于data_lineage.json真实血缘边+表结构，用AI辅助推理(标注
  MODEL_DRAFT)给出①表级血缘说明(真实上下游表名+中文名)②任务特征聚类(6个
  固定枚举，见table_root_cause_analysis.py)——用血缘图+业务对象做归因，
  识别数据加工环节，是"业务能力L2层"在数据侧的自下而上投影。没有root_cause
  分析覆盖的表(尚未跑批或本轮未覆盖)保持BLOCKED，如实说明原因。
- L4反向补全层：基于L3识别出的血缘位置+任务聚类+该表已关联的L4，用AI辅助
  推理反向推断可能存在但未被记录的隐藏产出(交付物或过程产物)——用数据证据
  倒推流程蓝图没写全的地方。同样标注MODEL_DRAFT，没有关联L4的表留空。
- L5决策层：该做什么——保留原有面板D四象限DERIVED归类，新增两条机械判定
  的轨道(不需要AI，基于L1-L4已有信号规则计算)：
  - 轨道A数据治理优先：哪些表要先立数据标准/理清血缘/定owner
  - 轨道B流程补全杠杆：哪些表的数据证据可以直接撬动补全缺失的L3/L4流程定义

L3/L4改造前的旧设计(相关性/耗时/ROI测算)依赖process_analytics.fact_card和
fact_agent(唯一设计了耗时/错误率/agent协同字段的两张表)，当前均为0行，且
全库没有任何薪酬/人力成本单价字段——这条路径真实数据缺口没有变化，但2026-08-06
判断不必再死等这类数据，改用已经建扎实的血缘证据做归因，是同一套"如实反映
真实证据"纪律下的另一条可行路径，不是放弃原判断。
"""
from __future__ import annotations

import json
from pathlib import Path

from skills.unified_analysis import D_FIELDS, axis_conflict
from skills.business_data_bridge import ANALYZED_L3_CODES

L3_BLOCKED_REASON = "该表尚未纳入本轮血缘根因分析范围(需运行table_root_cause_analysis)，暂无法给出上下游血缘归因与任务聚类"
L4_BLOCKED_REASON = "L3根因分析未覆盖，暂无法反向推断隐藏产出"

# 系统运维表——不是业务数据，是本系统自身的登录/审计/会话表，天然不该往任何
# L3/L4业务分析上靠。人工登记，理由直接来自db_catalog.py里已核实的description
# ("与保险业务流程无关")，不是新猜测；不落进"未纳入分析范围"，因为那意味着
# "还没查"，而这三张表是"查过、确认和业务无关"。
NON_BUSINESS_TABLES: dict[tuple[str, str], str] = {
    ("public", "auth_audit_log"): "本数据系统(非保险业务)的用户登录/操作审计日志，与保险业务流程无关",
    ("public", "auth_sessions"): "本数据系统的登录会话表，与保险业务流程无关",
    ("public", "auth_users"): "本数据系统的用户账号表，当前仅1个admin账号，与保险业务流程无关",
}

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
                    "deliverable": l4.get("deliverable"),
                    "deliverable_type": l4.get("deliverable_type"),
                })
    return index


def _governance_track(table_type: str, positions: list[str], root_cause_layer3: dict | None) -> dict | None:
    """轨道A·数据治理优先——机械规则，不需要AI。命中条件：AI根因分析把这张表
    聚类为"枢纽整合型"(血缘位置上被广泛引用，出错会向外扩散)，但L2层暂无明确
    负责岗位——有影响力但没人管，应该优先理清owner和数据标准。"""
    cluster = ((root_cause_layer3 or {}).get("task_cluster") or {}).get("label")
    if cluster == "枢纽整合型" and not positions:
        return {
            "flagged": True,
            "reason": "任务聚类为枢纽整合型(血缘位置上被广泛引用)，但暂无明确负责岗位——建议优先理清owner和数据标准，避免问题向外扩散",
        }
    return None


def _process_lever_track(root_cause_layer4: dict | None) -> dict | None:
    """轨道B·流程补全杠杆——机械规则，不需要AI。命中条件：AI根因分析发现了
    隐藏产出候选，说明数据证据暗示对应L4的流程蓝图记录可能不完整，值得拿这份
    数据证据去推动业务方补全蓝图/L4定义。"""
    hidden = (root_cause_layer4 or {}).get("hidden_deliverables") or []
    if hidden:
        names = "、".join(item.get("candidate_name", "") for item in hidden[:2])
        return {
            "flagged": True,
            "reason": f"AI根因分析发现{len(hidden)}个隐藏产出候选({names}等)，数据证据显示对应L4的交付物记录可能不完整，建议核实并补全流程蓝图",
        }
    return None


def build_table_analysis(
    db_catalog: dict,
    table_to_l4_index: dict[str, list[dict]],
    l3_codes: list[str],
    shared_master_data: dict[str, dict] | None = None,
    utility_support_info: dict[str, str] | None = None,
    field_anchor_info: dict[str, list[dict]] | None = None,
    root_cause_analysis: dict[str, dict] | None = None,
) -> dict:
    # "未定位关联"必须区分"查过、确认没有" vs "这个L3还没排到分析"——否则73个
    # 从未分析过的L3会被误读成"确认和这张表无关"。ANALYZED_L3_CODES是显式登记
    # 表，只有登记在案的L3才算"查过"。
    analyzed_count = sum(1 for code in l3_codes if code.removeprefix("L3-") in ANALYZED_L3_CODES)
    total_l3_count = len(l3_codes)
    shared_master_data = shared_master_data or {}
    utility_support_info = utility_support_info or {}
    field_anchor_info = field_anchor_info or {}
    root_cause_analysis = root_cause_analysis or {}

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
        non_business_reason = NON_BUSINESS_TABLES.get((table["schema"], table["table"]))
        if related:
            status = "已定位关联"
        elif non_business_reason:
            status = "已核实与业务无关(系统表)"
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
            "non_business": {"reason": non_business_reason} if not related and non_business_reason else None,
            "shared_master_data": shared_master_data.get(key) if not related and not non_business_reason else None,
            "utility_support": (
                {"reason": utility_support_info[key]}
                if not related and not non_business_reason and key in utility_support_info else None
            ),
            "field_anchored": (
                {"anchors": field_anchor_info[key]}
                if not related and not non_business_reason and key in field_anchor_info else None
            ),
        }

        root_cause_entry = root_cause_analysis.get(key)
        rc_layer3 = (root_cause_entry or {}).get("layer3")
        rc_layer4 = (root_cause_entry or {}).get("layer4")

        layer3 = rc_layer3 if rc_layer3 else {
            "status": "BLOCKED",
            "upstream": [],
            "downstream": [],
            "task_cluster": None,
            "reason": L3_BLOCKED_REASON,
        }
        layer4 = rc_layer4 if rc_layer4 else {
            "status": "BLOCKED",
            "hidden_deliverables": [],
            "reason": L4_BLOCKED_REASON,
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
            "governance_track": _governance_track(table.get("table_type", "其他"), sorted(positions), rc_layer3),
            "process_lever_track": _process_lever_track(rc_layer4),
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
        "source_policy": "五层分析结构：L1/L2层基于真实数据现算；L3/L4层基于data_lineage.json真实血缘用AI辅助推理(标注MODEL_DRAFT，未覆盖的表如实标注BLOCKED)；L5层四象限归类+两条机械判定轨道均为DERIVED，不做代理指标或假设替代",
        "tables": entries,
    }
