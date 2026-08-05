"""数据库现状目录：process_analytics(流程数据) + public/comm_sandbox/fin_sandbox(业务数据)
的活体catalog，独立于T1-T30治理表（那是过程产出物/文件同步的数据，这里是直连
PostgreSQL的表结构+行数快照）。

业务含义(description)只对已实际核实过的表填写，未核实的表如实留空标"待分析"，
不按表名/字段猜测编造。行数是运行时查询，不写死。
"""
from __future__ import annotations

from collections.abc import Callable

SCHEMAS = ["process_analytics", "public", "comm_sandbox", "fin_sandbox"]

# 已核实的表说明。key = "schema.table"。process_analytics的备份表(*_backup_*)
# 不在此列出，目录构建时整体过滤掉。
KNOWN_TABLES: dict[str, dict] = {
    "process_analytics.dim_process": {"role": "流程数据", "description": "L4流程主表：l3_code/l4_code、交付物、Tier(agentifiability)、D1-D6六维评估，VNW建模的核心权威源"},
    "process_analytics.dim_vn": {"role": "流程数据", "description": "价值节点主表：优先级、融合状态(is_fused)、三道Gate判断字段"},
    "process_analytics.bridge_vn_l4": {"role": "流程数据", "description": "价值节点-L4映射桥接表"},
    "process_analytics.bridge_l3_l2": {"role": "流程数据", "description": "L3-L2业务能力桥接表"},
    "process_analytics.bridge_kpi_l3": {"role": "流程数据", "description": "KPI-L3战略权重表：Mark优先级排序用的贡献权重，weight_confirmed字段全部为pending/blocked草稿状态，未确认"},
    "process_analytics.dim_kpi": {"role": "流程数据", "description": "KPI主表：43条记录=32条业务指标定义(KPI_NN，含公式/单位/周期，通过l3_codes字段直接映射多个L3) + 11条Mark战略KPI(KPI-Txx，is_mark_kpi=true，对应岗位族而非L3)"},
    "process_analytics.bridge_l3_vs_stage": {"role": "流程数据", "description": "L3-价值流阶段桥接表"},
    "process_analytics.dim_vs": {"role": "流程数据", "description": "价值流/客户旅程主表：vs_code、stage_code、stage_sequence(旅程第几阶段)"},
    "process_analytics.dim_org": {"role": "流程数据", "description": "岗位组织表：headcount_target_min/max是目标态编制设计，不是当前实际在岗人数；缺少\"职能支撑层\"分类"},
    "process_analytics.dim_agent": {"role": "流程数据", "description": "候选Agent主表(361条原子粒度)：owner_position_family字段100%为空，无法直接桥接岗位族，需经L4编码走候选Agent目录旧口径中转"},
    "process_analytics.dim_l1": {"role": "流程数据", "description": "L1战略分类维度表，仅5条，覆盖窄"},
    "process_analytics.dim_l2": {"role": "流程数据", "description": "L2业务能力维度表，19条，L1-L2层级关系"},
    "process_analytics.dim_m_strategy": {"role": "流程数据", "description": "M系列战略分类维度表，9条，覆盖窄"},
    "process_analytics.dim_deliverable": {"role": "流程数据", "description": "交付物维度表：368条，l4_code/l3_code/vs_code关联，与dim_process的deliverable字段是同源不同粒度的两份"},
    "process_analytics.dim_time": {"role": "流程数据", "description": "时间维度表，当前0行，未populate"},
    "process_analytics.fact_agent": {"role": "流程数据", "description": "Agent执行事实表(按月汇总SLA/返工/人工干预)，当前0行，AIT尚未产生真实运行数据"},
    "process_analytics.fact_card": {"role": "流程数据", "description": "任务执行事实卡表(逐任务执行记录，含efficiency_score/agent_assist等字段)，当前0行——这是\"协同新规则\"轨道需要的真实运行反馈基础，目前无法启动"},
    "process_analytics.rework_alert_log": {"role": "流程数据", "description": "返工预警日志，当前0行，未populate"},
    "fin_sandbox.match_receipt_receivable": {"role": "业务数据", "description": "应收实收匹配与差异对照表：diff_hkd/diff_pct/diff_category/rate_missing字段直接支持差异检测与异常识别"},
    "fin_sandbox.fact_receipt": {"role": "业务数据", "description": "实收流水主表：按保单/结算期记录实际到账金额，source_file/batch_id留有ETL导入批次痕迹"},
    "fin_sandbox.fact_receivable": {"role": "业务数据", "description": "应收明细主表：按保单记录应收佣金金额、费率、保单年度，是佣金核算的核心事实表"},
    "fin_sandbox.config_carrier_settlement_schedule_rules": {"role": "业务数据", "description": "保司结算周期规则配置：结算基准类型、偏移月数、容差天数"},
    "comm_sandbox.fact_commission_tier_rate": {"role": "业务数据", "description": "佣金分档费率表：按tier_level/customer_type/product_sku等维度的分档费率(Y1-Y10)"},
    "comm_sandbox.commission_tier_adjustment": {"role": "业务数据", "description": "佣金档位调整记录表：口径已建但当前0行，未产生调整数据"},
    "comm_sandbox.dim_comm_scheme": {"role": "业务数据", "description": "佣金方案定义表：方案名称、类型、生效期间"},
    "comm_sandbox.market_publish_event": {"role": "业务数据", "description": "市场费率发布事件表：当前0行"},
    "public.fact_commission_rate": {"role": "业务数据", "description": "佣金费率主表：按保司/产品/客户类型/年度的基础费率、超额费率、FYC/RYC费率，是佣金政策的核心事实表"},
    "public.fact_policy": {"role": "业务数据", "description": "保单主表：保单号、产品、保费、状态、签单/生效日期、理财师归属等56个字段的完整保单信息"},
    "public.config_product_commission_formula": {"role": "业务数据", "description": "产品佣金计算公式配置：首年/续期公式定义"},
    "public.dim_payee": {"role": "业务数据", "description": "收款人银行账户信息表：银行名称、账号、付款周期；当前0行——但实际付款银行信息真实存在于dim_license(见下)，dim_payee本身是空表，不代表付款信息整体缺失，是表设计上的重复/未启用"},
    "public.fact_channel_partner": {"role": "业务数据", "description": "渠道伙伴月度汇总表：保单数、客户数、总保费、平均审批周期"},

    # 2026-08-04第二轮：对剩余91张未核实表逐一取列名+样本数据分析后补齐。
    "comm_sandbox.commission_tier_adjustment_history_long": {"role": "业务数据", "description": "佣金档位调整历史归档表：commission_tier_adjustment的归档版，当前0行"},
    "comm_sandbox.competitor_rate": {"role": "业务数据", "description": "竞品费率对比表：按产品记录Y1-Y10逐年竞品费率及来源，当前0行未populate"},
    "comm_sandbox.config_partner_routing": {"role": "业务数据", "description": "渠道路由规则表：按保司/业务线/产品/伙伴分类条件，决定佣金归属到哪个牌照(license_code)"},
    "comm_sandbox.config_product_pricing_group": {"role": "业务数据", "description": "产品定价分组映射表：product_sku到定价组(pricing_group_id)的归类"},
    "comm_sandbox.config_quarter": {"role": "业务数据", "description": "季度日历表：quarter_code与起止日期对照"},
    "comm_sandbox.config_table_type_coefficient": {"role": "业务数据", "description": "费率折算系数配置：按table_type/premium_term/费率区间的系数换算规则，当前0行未populate"},
    "comm_sandbox.config_table_type_def": {"role": "业务数据", "description": "佣金制表类型定义表：20种制表类型(如\"同行经代B2B\")的业务分类、牌照口径、最长续期年限规则"},
    "comm_sandbox.config_table_type_product_scope": {"role": "业务数据", "description": "制表类型产品范围配置：按carrier/product等维度定义某制表类型INCLUDE/EXCLUDE哪些产品"},
    "comm_sandbox.config_table_type_tier_pricing_rules": {"role": "业务数据", "description": "分档定价规则表：按渠道/保司/产品条件匹配fyc/ryc档位及调整系数，是佣金费率计算的规则源之一"},
    "comm_sandbox.fact_commission_tier_rate_history_long": {"role": "业务数据", "description": "佣金分档费率历史归档表：fact_commission_tier_rate的历史版本，含pricing_trace计算过程字符串，33万+行"},
    "comm_sandbox.map_commission_plan_scheme": {"role": "业务数据", "description": "佣金方案代码映射表：commission_plan_code对应到scheme_id/table_type/carrier_code"},
    "comm_sandbox.market_publish_change": {"role": "业务数据", "description": "费率发布变更明细表：记录一次发布事件里每行费率变化前后的值，当前0行"},
    "comm_sandbox.market_row_state": {"role": "业务数据", "description": "费率行状态跟踪表：逐条费率记录的审核工作流状态(待确认/新增等)+变化原因+发布后的费率快照"},
    "comm_sandbox.market_table_header_state": {"role": "业务数据", "description": "费率表头审批工作流表：按table_type×quarter的提交/审批/发布/撤回状态跟踪"},
    "comm_sandbox.source_diff_confirm": {"role": "业务数据", "description": "费率来源差异确认表：当前0行未populate"},
    "comm_sandbox.v_commission_tier_effective": {"role": "业务数据", "description": "生效佣金费率视图：在fact_commission_tier_rate基础上应用调整后得到的当前有效费率(含eff_y1-y10/is_adjusted等字段)"},
    "comm_sandbox.v_commission_tier_published": {"role": "业务数据", "description": "已正式发布费率视图：当前0行，说明目前还没有走完正式发布流程的费率"},
    "comm_sandbox.v_payout_ratio_check": {"role": "业务数据", "description": "佣金支出比率校验视图：对比市场费率(mkt)与来源费率(src)算出payout ratio，用于费率健康度检查"},
    "comm_sandbox.v_qoq_rate_compare": {"role": "业务数据", "description": "费率环比对比视图：同一产品/条件下当季度(cur)与上季度(prev)费率差异对比"},
    "comm_sandbox.v_tier_rate_readable": {"role": "业务数据", "description": "费率中文可读视图：v_commission_tier_effective的中文字段版(保司/牌照/产品品类等)，供业务人员直接查阅"},
    "fin_sandbox.fin_sync_history": {"role": "业务数据", "description": "财务数据同步历史日志：记录哪张财务表何时从哪个批次同步、影响行数，当前仅1行"},
    "public.agg_market_commission_tier_rate": {"role": "业务数据", "description": "市场佣金费率汇总宽表：合作伙伴层级+保司+产品维度的费率明细，含Y1-Y10逐年总佣金/基础/超额/SMPA拆分"},
    "public.agg_sales_base": {"role": "业务数据", "description": "销售业务基础汇总表：订单粒度，含保单号/产品/保费/APE/预约-签单-递交-批核各环节日期与签批时效天数，是agg_source_commission_wide等下游表的基础"},
    "public.agg_sales_base_etl_scope": {"role": "业务数据", "description": "agg_sales_base的ETL抽取范围参数记录表(记录抽取用的起止日期字段)"},
    "public.agg_source_commission_wide": {"role": "业务数据", "description": "来源佣金费率宽表：按carrier/license/产品维度的费率明细，含basic/extra/smpa/fyc/ryc多档位Y1-Y10费率"},
    "public.auth_audit_log": {"role": "系统数据", "description": "本数据系统(非保险业务)的用户登录/操作审计日志，与保险业务流程无关"},
    "public.auth_sessions": {"role": "系统数据", "description": "本数据系统的登录会话表，与保险业务流程无关"},
    "public.auth_users": {"role": "系统数据", "description": "本数据系统的用户账号表，当前仅1个admin账号，与保险业务流程无关"},
    "public.bridge_partner_ka": {"role": "业务数据", "description": "渠道伙伴-KA归属桥接表：伙伴的团队、推荐人、上下级关系"},
    "public.bridge_person_identity": {"role": "业务数据", "description": "人员身份归一化桥接表：把各业务表里的partner_code/employee_name等原始标识统一映射到person_id，是跨表识别\"这是同一个人\"的核心基础设施表"},
    "public.bridge_person_relationship": {"role": "业务数据", "description": "人员关系桥接表：refers(推荐)/supervises(管理)等人际关系记录"},
    "public.bridge_person_role": {"role": "业务数据", "description": "人员角色桥接表：person_id对应担任的角色(如PARTNER_ADVISOR)及所属组织"},
    "public.bridge_strategy_routing": {"role": "业务数据", "description": "策略路由配置表：当前0行未populate"},
    "public.config_commission_table_type": {"role": "业务数据", "description": "佣金制表业务类型配置：伙伴与制表类型/主签牌照/生效期间的对应关系"},
    "public.config_identity_source_map": {"role": "业务数据", "description": "人员身份来源映射配置：定义从哪些源表哪些字段能识别出哪种角色，是bridge_person_identity生成逻辑的配置表"},
    "public.config_license_carrier_mapping": {"role": "业务数据", "description": "牌照-保司佣金方案映射配置：license_code与carrier_code对应到具体commission_plan_code及生效期间"},
    "public.config_license_cost_deduction": {"role": "业务数据", "description": "牌照平台服务费扣除配置：当前0行未populate"},
    "public.config_partner_routing": {"role": "业务数据", "description": "渠道路由规则表：按伙伴/保司/业务线/产品条件分配牌照(assigned_license_code)，与comm_sandbox.config_partner_routing同类但字段命名不同(bussiness_line_comdition等拼写差异)，疑似两处独立维护的重复配置"},
    "public.config_product_exclusion_range": {"role": "业务数据", "description": "产品排除范围配置：定义某制表类型下需要排除哪些保司/产品线/产品"},
    "public.config_product_feature_type": {"role": "业务数据", "description": "产品特征类型字典：定义产品可有哪些标准化特征字段(如投保年龄、红利结构)，是dim_product_feature_value的取值口径"},
    "public.config_quarter": {"role": "业务数据", "description": "季度日历表：与comm_sandbox.config_quarter同结构(两schema各维护一份)"},
    "public.config_strategy_header": {"role": "业务数据", "description": "策略头配置表：当前0行未populate"},
    "public.config_strategy_tiers": {"role": "业务数据", "description": "策略分档奖励配置表：当前0行未populate"},
    "public.dim_binder_agreement": {"role": "业务数据", "description": "转介协议主表：渠道伙伴的转介协议编号、签约主体、付款主体、有效期"},
    "public.dim_carrier": {"role": "业务数据", "description": "保司主数据表：保司代码、中英文名、评级、服务热线，与fin_sandbox/comm_sandbox里的carrier_code是同一套编码"},
    "public.dim_comm_scheme": {"role": "业务数据", "description": "佣金方案主表：与comm_sandbox.dim_comm_scheme同名同结构，当前0行"},
    "public.dim_customer": {"role": "业务数据", "description": "客户主数据表：客户身份信息(姓名/国籍/联系方式/职业)"},
    "public.dim_customer_type": {"role": "业务数据", "description": "客户类型字典表：当前0行未populate"},
    "public.dim_date": {"role": "业务数据", "description": "日期维度表：年/季/月/周/是否工作日/节假日标记"},
    "public.dim_employee": {"role": "业务数据", "description": "HR员工档案表：姓名、入职/转正日期、合同地区、雇佣类型、学历；与process_analytics.dim_org(目标态编制设计)不是一回事，这是实际HR档案"},
    "public.dim_ka": {"role": "业务数据", "description": "KA(经代机构)主数据表：市场细分、合作等级、对接人、结算方式"},
    "public.dim_license": {"role": "业务数据", "description": "持牌机构主数据表：12个持牌实体的牌照信息+**结算/后台两套银行账户**(已脱敏哈希)；这是实际付款账户信息的真实来源，dim_payee是空表不代表付款信息缺失"},
    "public.dim_lookup_code": {"role": "业务数据", "description": "通用代码字典表：各类字段枚举值的中英文对照(如产品品类CI=重疾)"},
    "public.dim_partner": {"role": "业务数据", "description": "渠道伙伴主数据表：合作伙伴档案(签约主体、牌照、结算周期、最低起付额、合作状态)"},
    "public.dim_partner_equity": {"role": "业务数据", "description": "伙伴权益配置表：当前0行未populate"},
    "public.dim_person": {"role": "业务数据", "description": "统一人员主数据表：bridge_person_identity归一化后的人员档案，区分INTERNAL/EMPLOYEE等范围与分组"},
    "public.dim_predicate_library": {"role": "业务数据", "description": "保单生命周期事件类型定义库：75种事件(如预约/签单/核保)的业务定义，是fact_sales_activity的事件字典"},
    "public.dim_product_benefit_profile": {"role": "业务数据", "description": "产品权益特征一致性检查表：现金价值/身故赔付等权益标记在跨计划书间是否一致"},
    "public.dim_product_feature_value": {"role": "业务数据", "description": "产品特征取值表：产品在config_product_feature_type定义的各标准化特征上的具体取值"},
    "public.dim_product_id": {"role": "业务数据", "description": "产品ID主数据表：产品代码、中英文名、费率选项、缴费期、保障期"},
    "public.dim_product_sku": {"role": "业务数据", "description": "产品SKU主数据表：产品线分类、是否离岸/保费融资、回溯期、冷静期天数"},
    "public.dim_role_type": {"role": "业务数据", "description": "人员角色类型字典表：35种角色定义，区分内部员工与外部角色"},
    "public.dim_segmentation": {"role": "业务数据", "description": "业务细分市场字典表：如天领业务、成事家办等细分市场代码"},
    "public.dim_strategy": {"role": "业务数据", "description": "策略主数据表：当前0行未populate"},
    "public.fact_channel_ka": {"role": "业务数据", "description": "KA渠道月度业绩汇总表：按月统计保单数/客户数/总保费/APE"},
    "public.fact_customer": {"role": "业务数据", "description": "客户月度业绩汇总表：按月统计客户的保单数、保费、生效/退保/取消件数"},
    "public.fact_insurance_plan_header": {"role": "业务数据", "description": "保险计划书主表：计划书参数(保额/保费/年龄/性别/吸烟状态)，来自计划书文件解析(source_file为xlsx)"},
    "public.fact_insurance_plan_header_history": {"role": "业务数据", "description": "保险计划书历史归档表：fact_insurance_plan_header的历史版本"},
    "public.fact_insurance_plan_lines": {"role": "业务数据", "description": "保险计划书逐年现金价值明细表：每份计划书按保单年度展开的现价/身故赔付等精算数值(guaranteed/reversionary/terminal bonus拆分)"},
    "public.fact_insurance_plan_lines_history": {"role": "业务数据", "description": "保险计划书逐年现金价值历史归档表：fact_insurance_plan_lines的历史版本，4万+行"},
    "public.fact_policy_etl_scope": {"role": "业务数据", "description": "fact_policy的ETL抽取范围参数记录表"},
    "public.fact_product_id": {"role": "业务数据", "description": "产品月度业绩汇总表：按product_id+月份统计保单数/保费/IRR均值"},
    "public.fact_product_sku": {"role": "业务数据", "description": "产品SKU月度业绩汇总表：按product_sku+月份统计保单数/保费"},
    "public.fact_sales_activity": {"role": "业务数据", "description": "保单生命周期事件流水表：每张保单从预约、签单到核保等各阶段的事件时间戳，是v_policy_current_state等下游视图的事件源，4.8万行"},
    "public.fact_target": {"role": "业务数据", "description": "业务目标表：按业务类型/细分市场/KA的年度APE等目标值"},
    "public.map_name_entity_type": {"role": "业务数据", "description": "名称实体类型判定表：判断某个原始名称字符串是机构还是自然人，用于数据清洗人工复核记录"},
    "public.map_partner_payee": {"role": "业务数据", "description": "伙伴-收款人映射及分成比例表：当前0行未populate"},
    "public.mapping_product": {"role": "业务数据", "description": "产品映射表：当前0行未populate"},
    "public.partner_tier_rules": {"role": "业务数据", "description": "伙伴档位规则表：按伙伴/保司/产品条件确定fyc/ryc档位及调整系数，与comm_sandbox的分档定价规则同类，适用范围不同"},
    "public.person_match_suspect": {"role": "业务数据", "description": "人员身份匹配疑似项表：bridge_person_identity归一化过程中无法自动确认、需人工复核的姓名/工号(如\"LFX\"这种缩写)，是数据清洗待办清单"},
    "public.product_risk_override": {"role": "业务数据", "description": "产品业务线人工修正表：产品分类的人工覆盖调整记录及修正理由"},
    "public.sales_renewal_due_snapshot": {"role": "业务数据", "description": "保单续期到期日快照表：按快照日期记录每张保单的下次续期到期日和已缴至日期，近3万行"},
    "public.sync_history": {"role": "业务数据", "description": "数据同步历史日志：记录哪张表何时从哪个源文件同步、影响行数、是否成功"},
    "public.v_dim_person": {"role": "业务数据", "description": "dim_person的精简视图(去掉批次/审计字段)"},
    "public.v_fact_policy_person": {"role": "业务数据", "description": "保单-人员关联视图：把fact_policy的伙伴/理财师/客户原始字段关联到person_id，供跨表按人查询"},
    "public.v_fact_sales_activity": {"role": "业务数据", "description": "销售活动关联视图：fact_sales_activity关联客户/伙伴/产品信息后的宽表，含审批周期天数(approval_cycle_days)——与COM-11\"银行到账确认\"上游的保单审批环节相关"},
    "public.v_person_activity": {"role": "业务数据", "description": "人员活动流水视图：person_id在各业务角色下的活动记录及金额，近4万行"},
    "public.v_person_coverage": {"role": "业务数据", "description": "人员身份识别覆盖率统计视图：渠道理财师/个人客户等群体的身份匹配成功率统计，用于评估bridge_person_identity的数据质量"},
    "public.v_plan_metrics": {"role": "业务数据", "description": "计划书精算指标视图：IRR、回本年份等从fact_insurance_plan_lines衍生出的精算指标"},
    "public.v_plan_year_snapshot": {"role": "业务数据", "description": "fact_insurance_plan_lines的精简视图(去掉wth系列提取字段)"},
    "public.v_policy_current_state": {"role": "业务数据", "description": "保单当前状态视图：综合fact_sales_activity事件流水计算出的保单最新状态，是事件驱动状态机的下游汇总结果"},
}

# 表类型是命名规律的机械归类(前缀/后缀)，不是业务含义判断——业务含义仍然只
# 来自KNOWN_TABLES里逐表核实的description，这里只是给"按结构分层"提供一个
# 独立于业务含义的筛选维度。规则命中不到的表如实归"其他"，不强凑分类。
_TABLE_TYPE_RULES = [
    ("dim_", "维度表"),
    ("fact_", "事实表"),
    ("agg_", "汇总表"),
    ("config_", "配置表"),
    ("bridge_", "桥接表"),
    ("mapping_", "映射表"),
    ("map_", "映射表"),
    ("auth_", "系统表"),
    ("v_", "视图"),
]
_TABLE_TYPE_SUFFIX_RULES = [
    ("_snapshot", "快照表"),
    ("_history", "历史记录表"),
    ("_history_long", "历史记录表"),
    ("_rules", "规则表"),
    ("_override", "规则表"),
    ("_adjustment", "调整记录表"),
    ("_suspect", "疑似记录表"),
    ("_event", "事件记录表"),
    ("_change", "事件记录表"),
    ("_state", "状态记录表"),
]


def infer_table_type(table_name: str) -> str:
    for prefix, label in _TABLE_TYPE_RULES:
        if table_name.startswith(prefix):
            return label
    for suffix, label in _TABLE_TYPE_SUFFIX_RULES:
        if table_name.endswith(suffix):
            return label
    if table_name.startswith("match_"):
        return "核对匹配表"
    return "其他"


def build_catalog(db_query: Callable[[str, tuple], list[dict]]) -> dict:
    tables = db_query(
        """SELECT table_schema, table_name
             FROM information_schema.tables
            WHERE table_schema = ANY(%s)
              AND table_name NOT LIKE '%%_backup_%%'
            ORDER BY table_schema, table_name""",
        (SCHEMAS,),
    )
    # 有些视图按命名前缀会被误判成"事实表"(如fact_channel_ka实际是SQL视图，不是
    # 物理表)——这里用information_schema.views查真实类型覆盖前缀猜测，不再靠命名判断。
    real_views = {
        (row["table_schema"], row["table_name"])
        for row in db_query(
            "SELECT table_schema, table_name FROM information_schema.views WHERE table_schema = ANY(%s)",
            (SCHEMAS,),
        )
    }
    all_columns = db_query(
        """SELECT table_schema, table_name, column_name, data_type
             FROM information_schema.columns
            WHERE table_schema = ANY(%s)
            ORDER BY table_schema, table_name, ordinal_position""",
        (SCHEMAS,),
    )
    columns_by_table: dict[str, list[dict]] = {}
    for col in all_columns:
        key = f"{col['table_schema']}.{col['table_name']}"
        columns_by_table.setdefault(key, []).append({"name": col["column_name"], "type": col["data_type"]})

    count_sql = " UNION ALL ".join(
        f"SELECT '{row['table_schema']}.{row['table_name']}' AS key, count(*) AS n FROM {row['table_schema']}.{row['table_name']}"
        for row in tables
    )
    count_rows = db_query(count_sql, ()) if count_sql else []
    counts = {row["key"]: row["n"] for row in count_rows}

    entries = []
    for row in tables:
        schema, table = row["table_schema"], row["table_name"]
        key = f"{schema}.{table}"
        known = KNOWN_TABLES.get(key)
        entries.append({
            "schema": schema,
            "table": table,
            "row_count": counts.get(key, 0),
            "columns": columns_by_table.get(key, []),
            "role": known["role"] if known else ("流程数据" if schema == "process_analytics" else "业务数据"),
            "description": known["description"] if known else None,
            "table_type": "视图" if (schema, table) in real_views else infer_table_type(table),
        })
    return {
        "schema_version": "vnw.db-catalog.v1",
        "source_policy": "PostgreSQL information_schema实时查询；业务含义仅对已核实的表填写，其余标注待分析，不猜测编造",
        "schemas": SCHEMAS,
        "tables": entries,
    }
