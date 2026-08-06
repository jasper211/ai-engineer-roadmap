"""L4 → 业务数据仓库(public/comm_sandbox/fin_sandbox) 桥接：L3-COM参照模型，
2026-08-05起扩展到HRA/HRM/RSJD/FBA/KAGA共5个L3。

与position_bridge/l3_position_category不同，这条链路没有任何权威文档可依据——
public(75表)/comm_sandbox(24表)/fin_sandbox(5表)三个schema此前VNW代码从未
查询过，也没有字段级外键指向process_analytics。这里的匹配是人工按业务含义
判断（看列名、看数据实际内容），不是机械关联。

2026-08-04第一轮：仅覆盖13张此前已核实的表，试点L3-COM。
2026-08-04第二轮：数据库现状目录122张表全部核实完业务含义后，基于完整目录
重新梳理L3-COM的匹配，并引入evidence_type维度——不再只回答"有没有表"，而是
回答"这张表在流程里扮演什么角色"，直接服务"AI是否更有意义"的判断：

- output（产出证据）：表内容就是该L4交付物本身的实际数据
- rule（规则证据）：config_*/dim_*等参数化配置表，说明该环节的判断逻辑已经
  显式化——这是Skill/Auto方向的强信号，逻辑不需要AI去"学"，只需要执行
- workflow（流程状态证据）：表里有审批/确认/发布/待处理等状态字段，直接
  暴露当前人工关卡卡在哪个节点，是设计人机协作边界的第一手材料
- audit（追溯证据）：history/sync_history类表，反映变更是否可追溯、版本
  管理是否成熟

L3-COM是参照模型：其他L3的业务数据接入，应复用这四类evidence_type的判断
方式，而不是重新发明匹配逻辑。confidence仍保留：strong=表名/字段直接对应
该L4交付物，weak=业务领域相关但字段不完全对口或当前0行未populate。

2026-08-05：发现"未定位关联"被误读为"确认无关联"——实际上74个L3里只有
L3-COM做过这项分析，其余73个从未检查，被匹配成COM的0个关联表并不代表真的
无关。为了不再制造这种误导，引入ANALYZED_L3_CODES这个显式登记表：只有登记
在案的L3，其"某L4关联表数=0"才代表"查过、确认没有"，没登记的L3一律如实
标注"未纳入本轮分析范围"，前端table_analysis.py据此区分两种状态。

本轮新增HRA(人力分析)/HRM(人员全生命周期)/RSJD(经代机构销售执行)/
FBA(理财师业务分析)/KAGA(KA业绩跟踪)共5个L3，同样基于122张表完整目录的
真实字段核实，不是猜测。HRM/HRA里大量L4标注为空——这是真实数据缺口：
全库没有薪酬/培训/绩效考核/招聘/岗位编制方案专属表，dim_employee只是
基础档案表，不能代替这些环节的专属交付物表。
"""
from __future__ import annotations

from collections.abc import Callable

EVIDENCE_TYPE_LABELS = {
    "output": "产出证据",
    "rule": "规则证据",
    "workflow": "流程状态证据",
    "audit": "追溯证据",
}

# 已完整核实过业务数据匹配的L3（哪怕结果是某些L4确认无关联表，也算"查过"）。
# 不在这个集合里的L3，其L4在L4_BUSINESS_TABLE_MAP里没有任何entry——不是因为
# 查过没有，是因为还没排到。table_analysis.py靠这个集合区分两种状态。
ANALYZED_L3_CODES = {"COM", "HRA", "HRM", "RSJD", "FBA", "KAGA"}

L4_BUSINESS_TABLE_MAP: dict[str, list[dict]] = {
    "L4-COM-01": [
        {"schema": "public", "table": "fact_commission_rate", "evidence_type": "output", "matched_columns": ["carrier_code", "product_id", "basic_rate", "fyc_rate", "effective_start_date"], "rationale": "佣金费率主表，字段直接对应\"标准化政策库\"", "confidence": "strong"},
        {"schema": "public", "table": "config_product_commission_formula", "evidence_type": "rule", "matched_columns": ["first_year_formula", "renewal_year_formula"], "rationale": "费率计算公式已参数化配置", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "dim_comm_scheme", "evidence_type": "rule", "matched_columns": ["scheme_name", "scheme_type", "valid_from", "valid_to"], "rationale": "佣金方案定义", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "config_table_type_def", "evidence_type": "rule", "matched_columns": ["table_type_name", "business_category", "partner_category", "ryc_max_year"], "rationale": "20种制表类型的分类规则，正是\"标准化政策库\"的分类体系本身", "confidence": "strong"},
        {"schema": "public", "table": "config_license_carrier_mapping", "evidence_type": "rule", "matched_columns": ["license_code", "carrier_code", "commission_plan_code"], "rationale": "牌照-保司-方案映射规则，是政策接收后的落地配置", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "market_table_header_state", "evidence_type": "workflow", "matched_columns": ["header_status", "submitted_by", "approved_by", "published_by"], "rationale": "费率表提交/审批/发布工作流状态，直接暴露\"政策接收与校准\"当前的人工关卡在哪一步", "confidence": "strong"},
    ],
    "L4-COM-02": [
        {"schema": "comm_sandbox", "table": "fact_commission_tier_rate", "evidence_type": "output", "matched_columns": ["tier_level", "customer_type", "product_sku", "rate_y1"], "rationale": "分档/细分市场费率表，对应\"各细分市场配置\"", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "config_table_type_product_scope", "evidence_type": "rule", "matched_columns": ["scope_mode", "match_dim", "match_value"], "rationale": "产品范围INCLUDE/EXCLUDE规则，是\"差异化拆解\"的规则依据", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "config_table_type_tier_pricing_rules", "evidence_type": "rule", "matched_columns": ["fyc_tier", "ryc_tier", "fyc_adjustment", "ryc_adjustment"], "rationale": "分档定价规则，验证环节的判断依据已参数化", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "market_row_state", "evidence_type": "workflow", "matched_columns": ["row_status", "change_type", "confirmed_by"], "rationale": "逐条费率行的确认状态(待确认/新增等)，是\"验证\"过程的真实工作流留痕", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "commission_tier_adjustment", "evidence_type": "output", "matched_columns": ["adj_y1", "adjust_reason"], "rationale": "档位调整记录；口径已建但当前0行，未产生数据", "confidence": "weak"},
    ],
    "L4-COM-03": [
        {"schema": "comm_sandbox", "table": "market_publish_event", "evidence_type": "workflow", "matched_columns": ["action", "affected_rows", "published_by"], "rationale": "费率发布事件表，字段含义正对应\"外发\"动作；当前0行，说明外发流程尚未在系统内走过", "confidence": "weak"},
        {"schema": "comm_sandbox", "table": "v_commission_tier_published", "evidence_type": "output", "matched_columns": ["publish_no", "row_bizkey"], "rationale": "已发布费率视图，结构对应\"佣金外发凭证\"；当前0行", "confidence": "weak"},
        {"schema": "comm_sandbox", "table": "market_publish_change", "evidence_type": "output", "matched_columns": ["publish_event_id"], "rationale": "费率发布变更明细表，外键指向market_publish_event，是同一条\"外发\"事件的变更明细；当前0行", "confidence": "weak"},
    ],
    "L4-COM-04": [
        {"schema": "public", "table": "fact_target", "evidence_type": "output", "matched_columns": ["period_key", "target_ape", "target_revenue", "business_category"], "rationale": "按业务类型/细分市场/KA的年度目标表，直接对应\"年度预算与规划\"", "confidence": "strong"},
    ],
    "L4-COM-05": [
        {"schema": "comm_sandbox", "table": "commission_tier_adjustment", "evidence_type": "output", "matched_columns": ["adjust_reason", "adjusted_by"], "rationale": "调整记录表理论对口\"追溯调整\"；当前0行，未populate", "confidence": "weak"},
        {"schema": "comm_sandbox", "table": "commission_tier_adjustment_history_long", "evidence_type": "audit", "matched_columns": ["adjustment_id", "effective_start_date", "effective_end_date"], "rationale": "调整历史归档表，理论上承接追溯轨迹；当前0行", "confidence": "weak"},
    ],
    "L4-COM-06": [],
    "L4-COM-07": [],
    "L4-COM-08": [
        {"schema": "public", "table": "agg_source_commission_wide", "evidence_type": "output", "matched_columns": ["carrier_code", "license_code", "basic_y1", "fyc_y1"], "rationale": "carrier维度费率宽表，是真正的\"跨保司佣金整合\"落地数据，5734行", "confidence": "strong"},
        {"schema": "public", "table": "agg_market_commission_tier_rate", "evidence_type": "output", "matched_columns": ["保司代码", "合作伙伴层级", "总佣金_y1"], "rationale": "市场佣金费率汇总宽表，合作伙伴+保司+产品维度整合，7518行", "confidence": "strong"},
    ],
    "L4-COM-09": [
        {"schema": "fin_sandbox", "table": "match_receipt_receivable", "evidence_type": "output", "matched_columns": ["diff_hkd", "diff_pct", "diff_category", "rate_missing"], "rationale": "应收实收差异表自带异常分类字段，直接可做异常检测输入", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "v_payout_ratio_check", "evidence_type": "output", "matched_columns": ["mkt_y1", "src_y1", "payout_y1"], "rationale": "佣金支出比率校验视图，专门用于费率异常检测", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "v_qoq_rate_compare", "evidence_type": "output", "matched_columns": ["total_diff", "y1_diff", "changed"], "rationale": "费率环比对比视图，changed字段直接标记异常变化", "confidence": "strong"},
    ],
    "L4-COM-10": [
        {"schema": "fin_sandbox", "table": "fact_receivable", "evidence_type": "output", "matched_columns": ["policy_no", "commission_amount", "premium_hkd", "commission_rate"], "rationale": "应收明细主表，字段直接对应\"应收明细清单\"", "confidence": "strong"},
        {"schema": "public", "table": "fact_policy", "evidence_type": "output", "matched_columns": ["policy_no", "premium", "ape", "issue_date"], "rationale": "保单信息整合来源", "confidence": "strong"},
        {"schema": "public", "table": "v_policy_current_state", "evidence_type": "output", "matched_columns": ["status_master", "ape", "premium_hkd"], "rationale": "保单当前状态视图，为应收核算提供保单状态口径", "confidence": "weak"},
    ],
    "L4-COM-11": [
        {"schema": "fin_sandbox", "table": "fact_receipt", "evidence_type": "output", "matched_columns": ["receipt_amount_hkd", "process_date", "policy_no"], "rationale": "实收清单主表", "confidence": "strong"},
        {"schema": "fin_sandbox", "table": "match_receipt_receivable", "evidence_type": "output", "matched_columns": ["receipt_amount_hkd", "receivable_amount_hkd", "diff_hkd", "diff_pct"], "rationale": "应收实收匹配+差异对照表，字段与交付物名称《差异对照表》完全对应", "confidence": "strong"},
    ],
    "L4-COM-12": [
        {"schema": "public", "table": "partner_tier_rules", "evidence_type": "rule", "matched_columns": ["fyc_tier", "ryc_tier", "fyc_adjustment", "ryc_adjustment"], "rationale": "伙伴档位规则，是\"应派金额拆分\"的计算依据，规则已参数化", "confidence": "strong"},
        {"schema": "public", "table": "dim_partner", "evidence_type": "output", "matched_columns": ["payment_cycle", "min_payout_threshold", "partner_status"], "rationale": "渠道伙伴主档，含结算周期与起付额，是\"渠道对账\"的伙伴侧依据", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "config_partner_routing", "evidence_type": "rule", "matched_columns": ["assigned_license_code", "priority"], "rationale": "渠道路由规则，决定应派归属到哪个牌照", "confidence": "strong"},
        {"schema": "public", "table": "config_partner_routing", "evidence_type": "rule", "matched_columns": ["assigned_license_code", "priority", "partner_code_condition"], "rationale": "同为渠道路由规则表(所有合作伙伴的合作匹配规则)，与comm_sandbox同名表功能等价但字段命名独立维护(含拼写差异bussiness_line_comdition)，2026-08-05业务方确认其为真实有效的路由规则表，非断点", "confidence": "strong"},
        {"schema": "public", "table": "fact_channel_partner", "evidence_type": "output", "matched_columns": ["partner_code", "total_premium_hkd", "policy_count"], "rationale": "渠道月度汇总表，弱对应\"应派清单\"（无逐笔应派落地表）", "confidence": "weak"},
    ],
    "L4-COM-13": [
        {"schema": "public", "table": "dim_license", "evidence_type": "output", "matched_columns": ["bank_name_for_settlement", "bank_account_hash_for_settlement", "payment_cycle"], "rationale": "持牌机构结算银行账户信息（已脱敏），是\"实派执行\"真实的付款账户依据；此前误判dim_payee(空表)为数据缺口，实际付款信息在dim_license", "confidence": "strong"},
    ],
    "L4-COM-14": [
        {"schema": "public", "table": "dim_license", "evidence_type": "output", "matched_columns": ["bank_name_for_settlement", "bank_account_hash_for_settlement"], "rationale": "银行转账所需账户信息，字段齐全", "confidence": "strong"},
    ],
    "L4-COM-15": [
        {"schema": "public", "table": "sync_history", "evidence_type": "audit", "matched_columns": ["sync_time", "rows_affected", "status"], "rationale": "数据同步归档日志，与\"台账更新\"业务含义邻近但非专属表，弱对应", "confidence": "weak"},
    ],
    "L4-COM-16": [
        {"schema": "public", "table": "sync_history", "evidence_type": "audit", "matched_columns": ["source_file", "rows_affected", "sync_mode"], "rationale": "数据同步日志直接记录\"导入\"动作的源文件与影响行数，比fact_receipt的批次痕迹更贴合该L4本身", "confidence": "strong"},
        {"schema": "fin_sandbox", "table": "fact_receipt", "evidence_type": "output", "matched_columns": ["source_file", "batch_id", "created_at"], "rationale": "source_file/batch_id留有导入批次痕迹，是导入结果的下游落地", "confidence": "weak"},
    ],
    "L4-COM-17": [],
    "L4-COM-18": [
        {"schema": "comm_sandbox", "table": "market_table_header_state", "evidence_type": "audit", "matched_columns": ["row_version", "current_publish_no"], "rationale": "row_version字段直接对应\"版本管理\"，比结算周期规则更贴合该L4本身", "confidence": "strong"},
        {"schema": "fin_sandbox", "table": "config_carrier_settlement_schedule_rules", "evidence_type": "rule", "matched_columns": ["settlement_basis_type", "settlement_offset_months", "effective_start_date"], "rationale": "结算规则版本配置，与\"收款映射版本管理\"业务含义接近", "confidence": "weak"},
    ],
    # L3-HRA 人力分析与决策支持流程：dim_employee是唯一的HR业务表，只有档案
    # 字段(入职/转正/离职/学历/合同地区)，没有薪酬/绩效字段——02靠fact_target
    # 的编制目标弱对应，03/04(成本/薪酬对标)全库确实没有薪酬字段，07是报告
    # 交付物本身，不是数据表。
    "L4-HRA-01": [
        {"schema": "public", "table": "dim_employee", "evidence_type": "output", "matched_columns": ["employee_id", "first_hire_date", "regularization_date", "work_status", "contract_region", "employment_type"], "rationale": "HR员工档案表，是人效数据采集与清洗的原始输入", "confidence": "strong"},
    ],
    "L4-HRA-02": [
        {"schema": "public", "table": "fact_target", "evidence_type": "output", "matched_columns": ["target_headcount", "period_key", "business_category"], "rationale": "业务目标表含target_headcount字段，可作对标的目标值一侧，但没有实际人效计算结果表", "confidence": "weak"},
    ],
    "L4-HRA-03": [],
    "L4-HRA-04": [],
    "L4-HRA-05": [
        {"schema": "public", "table": "dim_employee", "evidence_type": "output", "matched_columns": ["highest_education", "employment_type", "contract_region", "nationality"], "rationale": "学历/雇佣类型/合同地区字段直接支持人员素质结构盘点", "confidence": "strong"},
    ],
    "L4-HRA-06": [
        {"schema": "public", "table": "dim_employee", "evidence_type": "output", "matched_columns": ["recorded_term_date", "work_status", "first_hire_date"], "rationale": "离职登记日期与在职状态字段直接支持流失率计算", "confidence": "strong"},
    ],
    "L4-HRA-07": [],

    # L3-HRM 人员全生命周期管理流程：dim_employee反复作为不同L4的证据(入职/
    # 转正/退出)，字段互不重叠，这正是"同一张表服务多个L4"的真实例子；招聘/
    # 培训/绩效/薪酬/晋升全库没有专属表，是真实数据缺口，不是没找。
    "L4-HRM-01": [
        {"schema": "public", "table": "fact_target", "evidence_type": "output", "matched_columns": ["target_headcount", "team_id", "period_key"], "rationale": "编制目标数字化依据，但没有岗位JD文本表", "confidence": "weak"},
    ],
    "L4-HRM-02": [],
    "L4-HRM-03": [
        {"schema": "public", "table": "dim_employee", "evidence_type": "output", "matched_columns": ["first_hire_date", "employment_type", "contract_region", "id_card_masked"], "rationale": "入职日期/雇佣类型/合同地区字段直接对应入职配置", "confidence": "strong"},
    ],
    "L4-HRM-04": [
        {"schema": "public", "table": "dim_employee", "evidence_type": "output", "matched_columns": ["regularization_date", "work_status"], "rationale": "转正日期字段直接对应试用期考核结果", "confidence": "strong"},
    ],
    "L4-HRM-05": [],
    "L4-HRM-06": [],
    "L4-HRM-07": [],
    "L4-HRM-08": [],
    "L4-HRM-09": [
        {"schema": "public", "table": "dim_employee", "evidence_type": "output", "matched_columns": ["recorded_term_date", "work_status"], "rationale": "离职登记日期与在职状态字段直接对应人员退出归档", "confidence": "strong"},
    ],

    # L3-RSJD 经代机构销售业务执行流程：数据基础比HRA/HRM扎实很多，销售链路
    # 有完整的事件流水/汇总/状态视图/计划书表支撑。
    "L4-RSJD-01": [
        {"schema": "public", "table": "fact_sales_activity", "evidence_type": "output", "matched_columns": ["policy_id", "event_type", "status_after", "event_date", "operator"], "rationale": "保单生命周期事件流水表，逐条记录销售执行动作", "confidence": "strong"},
        {"schema": "public", "table": "dim_customer", "evidence_type": "output", "matched_columns": ["customer_id", "customer_type", "occupation", "income"], "rationale": "客户主数据表，是客户管理的直接依据", "confidence": "strong"},
    ],
    "L4-RSJD-02": [
        {"schema": "public", "table": "agg_sales_base", "evidence_type": "output", "matched_columns": ["保费(hkd)", "ape", "是否融资", "签批时效(天)"], "rationale": "订单粒度的保费/APE/签批时效汇总表，是财务模型测算的直接输入", "confidence": "strong"},
    ],
    "L4-RSJD-03": [
        {"schema": "public", "table": "v_policy_current_state", "evidence_type": "workflow", "matched_columns": ["status_master", "last_status_event_type", "status_match"], "rationale": "保单当前状态视图，status_match字段直接暴露状态是否校准一致，对应内部审核与校准", "confidence": "strong"},
    ],
    "L4-RSJD-04": [
        {"schema": "public", "table": "fact_insurance_plan_header", "evidence_type": "output", "matched_columns": ["plan_header_id", "sum_assured", "premium", "product_name"], "rationale": "保险计划书主表，本身就是\"方案\"这一交付物的数据化版本", "confidence": "strong"},
        {"schema": "public", "table": "fact_insurance_plan_lines", "evidence_type": "output", "matched_columns": ["plan_line_id", "policy_year", "gcv", "tcv_irr"], "rationale": "计划书逐年现金价值明细，是方案交付内容的精算细节", "confidence": "strong"},
    ],

    # L3-FBA 理财师业务分析：与RSJD共用agg_sales_base(同一张原始销售汇总表
    # 服务不同L3的不同L4，是"一表多L4/跨L3"的真实例子)；"分公司"维度全库
    # 没有对应表(只有process_analytics.dim_org有编制层级，不在业务数据仓库
    # 范围内)，03/04是真实数据缺口。
    "L4-FBA-01": [
        {"schema": "public", "table": "agg_sales_base", "evidence_type": "output", "matched_columns": ["签单日期", "保费(hkd)", "ape", "签单年月"], "rationale": "订单粒度销售汇总表，是月度/季度业绩数据汇总的原始输入", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "config_quarter", "evidence_type": "rule", "matched_columns": ["quarter_code", "q_start", "q_end"], "rationale": "季度日历配置表，是\"按季度分析\"切分区间的规则依据", "confidence": "strong"},
        {"schema": "public", "table": "config_quarter", "evidence_type": "rule", "matched_columns": ["quarter_code", "q_start", "q_end"], "rationale": "与comm_sandbox.config_quarter同结构、同行数(两schema各维护一份)，同为季度日历规则依据", "confidence": "strong"},
    ],
    "L4-FBA-02": [
        {"schema": "public", "table": "v_person_activity", "evidence_type": "output", "matched_columns": ["person_id", "role_code", "measure", "biz_date"], "rationale": "人员活动流水视图，measure字段可作活动率计算的原始输入，但未专门按理财师角色聚合", "confidence": "weak"},
    ],
    "L4-FBA-03": [],
    "L4-FBA-04": [],

    # L3-KAGA KA业绩跟踪与运维：fact_channel_ka是专属月度汇总表，字段与
    # L4-KAGA-01几乎逐字对应，是本轮里置信度最高的匹配之一。
    "L4-KAGA-01": [
        {"schema": "public", "table": "fact_channel_ka", "evidence_type": "output", "matched_columns": ["ka_id", "month", "policy_count", "total_premium_hkd", "total_ape"], "rationale": "KA渠道月度业绩汇总表，字段与\"定期业绩数据收集\"逐项对应", "confidence": "strong"},
    ],
    "L4-KAGA-02": [
        {"schema": "public", "table": "dim_ka", "evidence_type": "output", "matched_columns": ["ka_tier", "ka_status", "regulatory_status"], "rationale": "KA主数据表的分级/状态字段可作复盘诊断的维度依据，但没有专门的复盘结论表", "confidence": "weak"},
    ],
    "L4-KAGA-03": [],
    "L4-KAGA-04": [
        {"schema": "public", "table": "dim_ka", "evidence_type": "output", "matched_columns": ["contact_person", "support_team_org_id", "business_support_emp_id"], "rationale": "对接人与支持团队字段直接对应KA关系维护与长效运营", "confidence": "strong"},
    ],
}
# L4-COM-06(佣金税务处理)/L4-COM-07(佣金争议处理)/L4-COM-17(IA合规拦截引擎)
# 在完整122张表目录里逐一核实后仍未找到对应业务表——业务数据仓库本身没有
# 税务专属表、争议工单表、合规规则拦截日志表，这是真实的数据侧空白，不是
# 匹配方法的遗漏。
#
# L4-HRA-03/04(人员成本/薪酬市场对标)、L4-HRM-02/05/06/07/08(招聘/培训/
# 绩效/薪酬/晋升)、L4-FBA-03/04(分公司维度/报告定稿)、L4-KAGA-03(策略调整)
# 同理：全库没有薪酬字段、没有招聘/培训/绩效专属表、没有分公司组织维度表，
# 这些是数据侧真实空白，不是分析没做到位。

BUSINESS_TABLE_SOURCE = "public/comm_sandbox/fin_sandbox业务数据仓库（人工按业务含义匹配，非外键关联，2026-08-04 L3-COM参照模型 + 2026-08-05扩展HRA/HRM/RSJD/FBA/KAGA，基于122张表完整目录核实）"


def load_business_table_row_counts(db_query: Callable[[str, tuple], list[dict]]) -> dict[str, int]:
    """对L4_BUSINESS_TABLE_MAP引用到的全部表各查一次实时行数（业务数据仓库是活数据，不缓存计数）。"""
    refs = {(item["schema"], item["table"]) for rows in L4_BUSINESS_TABLE_MAP.values() for item in rows}
    counts = {}
    for schema, table in sorted(refs):
        rows = db_query(f"SELECT count(*) AS n FROM {schema}.{table}", ())
        counts[f"{schema}.{table}"] = rows[0]["n"] if rows else 0
    return counts
