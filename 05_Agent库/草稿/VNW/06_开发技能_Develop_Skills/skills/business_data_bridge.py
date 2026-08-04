"""L4 → 业务数据仓库(public/comm_sandbox/fin_sandbox) 试点桥接。

与position_bridge/l3_position_category不同，这条链路没有任何权威文档可依据——
public(75表)/comm_sandbox(24表)/fin_sandbox(5表)三个schema此前VNW代码从未
查询过，也没有字段级外键指向process_analytics。这里的匹配是人工按业务含义
判断（看列名、看数据实际内容），不是机械关联，因此每条都标注confidence，
strong=表名/字段直接对应该L4交付物，weak=业务领域相关但字段不完全对口。

2026-08-04试点范围：只做L3-COM（18个L4），验证方法可行后再扩展到其他L3。
"""
from __future__ import annotations

from collections.abc import Callable

L4_BUSINESS_TABLE_MAP: dict[str, list[dict]] = {
    "L4-COM-01": [
        {"schema": "public", "table": "fact_commission_rate", "matched_columns": ["carrier_code", "product_id", "basic_rate", "fyc_rate", "effective_start_date"], "rationale": "佣金费率主表，字段直接对应\"标准化政策库\"", "confidence": "strong"},
        {"schema": "public", "table": "config_product_commission_formula", "matched_columns": ["first_year_formula", "renewal_year_formula"], "rationale": "费率计算公式配置", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "dim_comm_scheme", "matched_columns": ["scheme_name", "scheme_type", "valid_from", "valid_to"], "rationale": "佣金方案定义", "confidence": "strong"},
    ],
    "L4-COM-02": [
        {"schema": "comm_sandbox", "table": "fact_commission_tier_rate", "matched_columns": ["tier_level", "customer_type", "product_sku", "rate_y1"], "rationale": "分档/细分市场费率表，对应\"各细分市场配置\"", "confidence": "strong"},
        {"schema": "comm_sandbox", "table": "commission_tier_adjustment", "matched_columns": ["adj_y1", "adjust_reason"], "rationale": "档位调整记录；当前表内0行，口径已建但未产生数据", "confidence": "weak"},
    ],
    "L4-COM-05": [
        {"schema": "comm_sandbox", "table": "commission_tier_adjustment", "matched_columns": ["adjust_reason", "adjusted_by"], "rationale": "调整记录表理论对口\"追溯调整\"；当前0行，未populate", "confidence": "weak"},
    ],
    "L4-COM-08": [
        {"schema": "public", "table": "fact_commission_rate", "matched_columns": ["carrier_code"], "rationale": "carrier_code支持跨保司维度筛选，但无专门的\"跨保司整合\"落地表", "confidence": "weak"},
    ],
    "L4-COM-09": [
        {"schema": "fin_sandbox", "table": "match_receipt_receivable", "matched_columns": ["diff_hkd", "diff_pct", "diff_category", "rate_missing"], "rationale": "应收实收差异表自带异常分类字段，直接可做异常检测输入", "confidence": "strong"},
    ],
    "L4-COM-10": [
        {"schema": "fin_sandbox", "table": "fact_receivable", "matched_columns": ["policy_no", "commission_amount", "premium_hkd", "commission_rate"], "rationale": "应收明细主表，字段直接对应\"应收明细清单\"", "confidence": "strong"},
        {"schema": "public", "table": "fact_policy", "matched_columns": ["policy_no", "premium", "ape", "issue_date"], "rationale": "保单信息整合来源", "confidence": "strong"},
    ],
    "L4-COM-11": [
        {"schema": "fin_sandbox", "table": "fact_receipt", "matched_columns": ["receipt_amount_hkd", "process_date", "policy_no"], "rationale": "实收清单主表", "confidence": "strong"},
        {"schema": "fin_sandbox", "table": "match_receipt_receivable", "matched_columns": ["receipt_amount_hkd", "receivable_amount_hkd", "diff_hkd", "diff_pct"], "rationale": "应收实收匹配+差异对照表，字段与交付物名称《差异对照表》完全对应", "confidence": "strong"},
    ],
    "L4-COM-12": [
        {"schema": "public", "table": "fact_channel_partner", "matched_columns": ["partner_code", "total_premium_hkd", "policy_count"], "rationale": "渠道汇总表，但无\"应派金额拆分\"专属表，弱对应", "confidence": "weak"},
    ],
    "L4-COM-13": [
        {"schema": "public", "table": "dim_payee", "matched_columns": ["bank_account_number", "payment_cycle", "min_payout_threshold"], "rationale": "收款人银行信息表理论对口\"实派执行\"；当前表内0行，未populate，是财务制单环节的真实数据缺口", "confidence": "weak"},
    ],
    "L4-COM-14": [
        {"schema": "public", "table": "dim_payee", "matched_columns": ["bank_name", "bank_account_number", "default_currency"], "rationale": "银行转账所需信息字段齐全，但表内0行，未populate", "confidence": "weak"},
    ],
    "L4-COM-16": [
        {"schema": "fin_sandbox", "table": "fact_receipt", "matched_columns": ["source_file", "batch_id", "created_at"], "rationale": "source_file/batch_id留有导入批次痕迹，可作为该L4的下游落地证据", "confidence": "weak"},
    ],
    "L4-COM-18": [
        {"schema": "fin_sandbox", "table": "config_carrier_settlement_schedule_rules", "matched_columns": ["settlement_basis_type", "settlement_offset_months", "effective_start_date"], "rationale": "结算规则版本配置，与\"收款映射版本管理\"业务含义接近", "confidence": "weak"},
    ],
}
# L4-COM-03/04/06/07/15/17 未找到对应业务表，如实不收录（不是遗漏，是business
# schema里确实没有佣金外发/预算/税务/争议/台账/合规拦截对应的表）。

BUSINESS_TABLE_SOURCE = "public/comm_sandbox/fin_sandbox业务数据仓库（人工按业务含义匹配，非外键关联，2026-08-04 L3-COM试点）"


def load_business_table_row_counts(db_query: Callable[[str, tuple], list[dict]]) -> dict[str, int]:
    """对L4_BUSINESS_TABLE_MAP引用到的全部表各查一次实时行数（业务数据仓库是活数据，不缓存计数）。"""
    refs = {(item["schema"], item["table"]) for rows in L4_BUSINESS_TABLE_MAP.values() for item in rows}
    counts = {}
    for schema, table in sorted(refs):
        rows = db_query(f"SELECT count(*) AS n FROM {schema}.{table}", ())
        counts[f"{schema}.{table}"] = rows[0]["n"] if rows else 0
    return counts
