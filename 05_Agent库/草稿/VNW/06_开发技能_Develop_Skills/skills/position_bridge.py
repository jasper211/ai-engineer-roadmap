"""L3 → 岗位族/岗位类别 桥接：当前是哪个岗位在负责这个L3(及其下全部L4)。

来源：`2026-07-20_68L3岗位族归属设计_v6.1_SUBMITTED.md` 第三/四节"各族详细映射"，
HR权威文档逐L3显式列出所属岗位类别，覆盖68个L3（本文档口径），非L4级颗粒度——
同一L3下的全部L4共享同一岗位类别，文档本身未做L4级细分。
只标注岗位（岗位类别+岗位族），不体现具体人名。
"""
from __future__ import annotations

L3_POSITION_CATEGORY_SOURCE = "2026-07-20_68L3岗位族归属设计_v6.1_SUBMITTED.md 三/四节各族详细映射"

L3_POSITION_CATEGORY: dict[str, dict] = {}


def _register(family_code: str, family_name: str, category_name: str, category_type: str, l3_codes: list[str]) -> None:
    for code in l3_codes:
        L3_POSITION_CATEGORY[code] = {
            "family_code": family_code,
            "family_name": family_name,
            "category_name": category_name,
            "category_type": category_type,
        }


_register("JF-01", "保司战略族", "市场进入策略岗", "目标态核心",
           ["L3-CAS", "L3-MED", "L3-MEI", "L3-MIO", "L3-SFC", "L3-SRE", "L3-VPV"])
_register("JF-01", "保司战略族", "战略体系及流程管理岗", "目标态核心",
           ["L3-KPI", "L3-CPM", "L3-EFB", "L3-USV"])
_register("JF-01", "保司战略族", "保司战略官", "目标态核心",
           ["L3-IAC-AUTH", "L3-IAC-NEG"])
_register("JF-02", "保司关系族", "保司关系经理岗", "目标态核心",
           ["L3-IAO", "L3-IRI", "L3-IBE", "L3-IMF", "L3-IRR", "L3-IPI-ONB", "L3-IPI-OPS"])
_register("JF-03", "机构业务族", "业务发展BD岗", "目标态核心",
           ["L3-IBEC", "L3-IBRD", "L3-KAEC", "L3-KAET"])
_register("JF-03", "机构业务族", "经代机构合作岗", "目标态核心",
           ["L3-NG", "L3-ASD", "L3-BSRV", "L3-CRR", "L3-URD", "L3-UCA"])
_register("JF-03", "机构业务族", "联合运营管理岗", "目标态核心",
           ["L3-JOPD", "L3-URF"])
_register("JF-03", "机构业务族", "保单服务岗", "目标态核心",
           ["L3-RSJD"])
_register("JF-03", "机构业务族", "KA管理岗", "目标态核心",
           ["L3-KAOP", "L3-KASC", "L3-KAEM", "L3-KAOE", "L3-KAGA"])
_register("JF-03", "机构业务族", "服务寻源与供应商管理岗", "目标态核心",
           ["L3-SOB"])
_register("JF-04", "事业部运营族", "事业部运营管理岗", "目标态核心",
           ["L3-FBA", "L3-FLM", "L3-FOB", "L3-FPG"])
_register("JF-05", "理财师发展族", "理财师辅导与发展岗", "目标态核心",
           ["L3-FOR", "L3-FTR", "L3-EO"])
_register("JF-06", "权益服务族", "权益战略与方案设计岗", "目标态核心",
           ["L3-OBC", "L3-RPD", "L3-RSD", "L3-SLM", "L3-SPD"])
_register("JF-06", "权益服务族", "服务执行与跟踪岗", "目标态核心",
           ["L3-CDA-SRA", "L3-COB", "L3-SPO", "L3-SVC"])
_register("JF-06", "权益服务族", "服务结算与生命周期岗", "目标态核心",
           ["L3-CDS", "L3-SSD", "L3-SDS", "L3-SSVA"])
_register("JF-07", "佣金合规族", "佣金管理与合规岗", "目标态核心",
           ["L3-COM", "L3-SRM"])
_register("职能层", "职能支撑层", "人力资源管理岗", "目标态核心",
           ["L3-HRA", "L3-HRM", "L3-SPE"])
_register("职能层", "职能支撑层", "财务管理岗", "目标态核心",
           ["L3-BAM", "L3-CFM"])
_register("职能层", "职能支撑层", "合规管理岗", "目标态核心",
           ["L3-RCM", "L3-UCR"])

assert len(L3_POSITION_CATEGORY) == 68, len(L3_POSITION_CATEGORY)
