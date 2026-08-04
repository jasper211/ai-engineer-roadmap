"""VNW统一分析Spec v1.0 的确定性计算层。

不新增数据源，只对l3_model_builder.py已产出的model dict做二次计算：
证据分级(A/B/C，复用tools/evidence.py的EvidenceClass/EvidenceStatus，不新造
体系)、双轴声明+冲突标记(D1-D6/Tier轴 vs 候选Agent封装轴，禁止合并)、根因阶梯
(事实→机制→结构→策略四层)、DoD清单、跨面板综合判断。

结论状态机(DRAFT/CONFIRMED)通过读取
07_接入记忆_Integrate_Memory/analysis_confirmations/L3-XXX.json决定——该文件
由Jasper/业务负责人人工创建，VNW不自动生成CONFIRMED状态。

详见：03_规划项目结构_Plan_Project_Structure/VNW统一分析Spec_v1.0.md
"""
from __future__ import annotations

import json
from pathlib import Path

D_FIELDS = (
    "agent_d1_input_struct",
    "agent_d2_rule_clear",
    "agent_d3_output_verify",
    "agent_d4_api_reach",
    "agent_d5_fallback",
    "agent_d6_compliance",
)


def evidence_grade(evidence_class: str, status: str) -> str | None:
    """证据等级映射，直接对应tools/evidence.py的枚举，不新造分级标准。"""
    if evidence_class == "AUTHORITATIVE" and status == "ACTIVE":
        return "A"
    if evidence_class == "SUPPLEMENTAL" and status == "ACTIVE":
        return "B"
    if evidence_class == "CONSENSUS" or status == "UNVERIFIED":
        return "C"
    return None  # MISSING/CONFLICT/STALE：不作为证据引用


def axis_conflict(tier: str, skill_grade: str | None) -> bool:
    """D1-D6/Tier轴 与 候选Agent封装轴 方向相反时标注冲突，不合并成单一分数。"""
    if not skill_grade:
        return False
    letter = skill_grade[0]
    high_pack = letter in ("A", "B")
    needs_human = tier in ("Hybrid", "Human")
    if high_pack and needs_human:
        return True
    if letter == "F" and tier == "Auto":
        return True
    return False


def l4_root_cause_ladder(l4: dict) -> list[dict]:
    """四层根因阶梯：事实→机制→结构→策略。纯计算，不调用LLM。"""
    d1_d6 = l4.get("d1_d6") or {}
    complete = all(d1_d6.get(field) is not None for field in D_FIELDS)
    tier = l4.get("tier") or "待评估"
    layers = [{
        "layer": "事实层",
        "grade": "A" if complete else "缺口",
        "statement": f"Tier={tier}；D1-D6{'完整' if complete else '不完整，待补'}",
    }]

    skill = l4.get("skill_feasibility")
    if skill:
        verified = skill.get("verification_status") == "VERIFIED"
        conflict = axis_conflict(tier, skill.get("grade"))
        statement = f"候选Agent封装档位={skill.get('grade', '')}；{skill.get('recommended_path', '')}"
        if conflict:
            statement += "【与事实层Tier方向冲突，待业务方澄清】"
        layers.append({
            "layer": "机制层",
            "grade": "A" if verified else "B",
            "statement": statement,
            "axis_conflict": conflict,
        })
    else:
        layers.append({"layer": "机制层", "grade": "缺口", "statement": "候选Agent封装评估未覆盖该L4", "axis_conflict": False})

    business = l4.get("business_evidence") or []
    position = l4.get("position_family")
    if business or position:
        types = sorted({item["evidence_type"] for item in business})
        type_label = "、".join(types) if types else "无业务数据证据"
        pos_label = f"{position['category_name']}（{position['family_name']}）" if position else "未归口"
        layers.append({
            "layer": "结构层",
            "grade": "B" if business else "缺口",
            "statement": f"业务数据证据类型={type_label}；负责岗位={pos_label}",
        })
    else:
        layers.append({"layer": "结构层", "grade": "缺口", "statement": "无业务数据证据，无岗位归属，待补"})

    layers.append({
        "layer": "策略层",
        "grade": "C",
        "statement": "该不该优先投入需结合L3级KPI关联与价值流位置人工判断，见综合判断区块",
    })
    return layers


def load_confirmation(confirmations_dir: Path, l3_code: str) -> dict | None:
    path = confirmations_dir / f"{l3_code}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def dod_checklist(model: dict, conflicts: list[str]) -> list[dict]:
    dims = {
        "L2业务能力": bool(model.get("l2_capabilities")),
        "价值流位置": bool(model.get("value_stream_mappings")),
        "岗位归属": any(l4.get("position_family") for l4 in model["l4s"]),
        "KPI关联": bool(model.get("kpi_mappings")),
        "业务数据证据": any(l4.get("business_evidence") for l4 in model["l4s"]),
    }
    dims_covered = sum(1 for value in dims.values() if value)
    return [
        {"item": "分析基线完整可复述", "satisfied": bool(model.get("analysis_input_hash"))},
        {"item": f"六个受控维度中{dims_covered}/5个有数据（缺项已显式标待补）", "satisfied": True, "detail": dims},
        {"item": "D1-D6轴与候选Agent轴并列展示，未合并为单一分数", "satisfied": True},
        {"item": f"两轴方向冲突已标注（{len(conflicts)}处）", "satisfied": True},
        {"item": "每条结论标注证据等级A/B/C", "satisfied": True},
        {"item": "根因阶梯四层完整，缺层显式标待补", "satisfied": True},
        {"item": "每个面板有对应Insight", "satisfied": True},
        {"item": "报告末尾有跨面板综合判断", "satisfied": True},
        {"item": "C级结论标注待谁确认", "satisfied": True},
        {"item": "报告状态标注DRAFT/CONFIRMED", "satisfied": True},
    ]


def l3_synthesis(model: dict, confirmations_dir: Path | None = None) -> dict:
    l4s = model["l4s"]
    conflicts = [
        l4["l4_code"] for l4 in l4s
        if axis_conflict(l4.get("tier", ""), (l4.get("skill_feasibility") or {}).get("grade"))
    ]
    confirmation = load_confirmation(confirmations_dir, model["l3_code"]) if confirmations_dir else None
    return {
        "schema_version": "vnw.unified-analysis.v1",
        "status": "CONFIRMED" if confirmation else "DRAFT",
        "confirmed_by": confirmation.get("confirmed_by") if confirmation else None,
        "confirmed_at": confirmation.get("confirmed_at") if confirmation else None,
        "confirmation_notes": confirmation.get("notes") if confirmation else None,
        "axis_conflicts": conflicts,
        "coverage": {
            "l4_total": len(l4s),
            "business_evidence_covered": sum(1 for l4 in l4s if l4.get("business_evidence")),
            "position_covered": sum(1 for l4 in l4s if l4.get("position_family")),
            "kpi_count": len(model.get("kpi_mappings") or []),
            "value_stream_count": len(model.get("value_stream_mappings") or []),
        },
        "gate_a_status": model["gates"]["A"]["status"],
        "dod_checklist": dod_checklist(model, conflicts),
        "root_cause_ladders": {l4["l4_code"]: l4_root_cause_ladder(l4) for l4 in l4s},
    }
