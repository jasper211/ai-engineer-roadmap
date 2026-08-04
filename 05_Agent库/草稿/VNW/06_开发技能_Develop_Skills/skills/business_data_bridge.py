"""L4 → 业务数据仓库(public/comm_sandbox/fin_sandbox) 桥接：L3-COM参照模型。

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
"""
from __future__ import annotations

from collections.abc import Callable

EVIDENCE_TYPE_LABELS = {
    "output": "产出证据",
    "rule": "规则证据",
    "workflow": "流程状态证据",
    "audit": "追溯证据",
}

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
}
# L4-COM-06(佣金税务处理)/L4-COM-07(佣金争议处理)/L4-COM-17(IA合规拦截引擎)
# 在完整122张表目录里逐一核实后仍未找到对应业务表——业务数据仓库本身没有
# 税务专属表、争议工单表、合规规则拦截日志表，这是真实的数据侧空白，不是
# 匹配方法的遗漏。

BUSINESS_TABLE_SOURCE = "public/comm_sandbox/fin_sandbox业务数据仓库（人工按业务含义匹配，非外键关联，2026-08-04 L3-COM参照模型，基于122张表完整目录核实）"


def load_business_table_row_counts(db_query: Callable[[str, tuple], list[dict]]) -> dict[str, int]:
    """对L4_BUSINESS_TABLE_MAP引用到的全部表各查一次实时行数（业务数据仓库是活数据，不缓存计数）。"""
    refs = {(item["schema"], item["table"]) for rows in L4_BUSINESS_TABLE_MAP.values() for item in rows}
    counts = {}
    for schema, table in sorted(refs):
        rows = db_query(f"SELECT count(*) AS n FROM {schema}.{table}", ())
        counts[f"{schema}.{table}"] = rows[0]["n"] if rows else 0
    return counts
