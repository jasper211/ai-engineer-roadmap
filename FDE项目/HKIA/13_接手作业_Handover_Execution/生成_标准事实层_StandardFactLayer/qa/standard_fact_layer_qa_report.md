# 标准事实层 QA 报告

- 构建时间：2026-08-06
- 市场事实(72) / 公司事实(4914)

## 1. 覆盖检查
**市场事实按期间：** 2023Q1:18; 2024Q1:18; 2025Q1:18; 2026Q1:18
- 市场去重指标 18 / 公司去重指标 18（应均=18）
## 2. 缺失纪律
- reported_numeric 2443 / reported_missing 2471（缺值保 NULL，不补零）
## 3. 市场总额 vs 公司明细 reconcile（2026Q1）
- IF_GROUP_NON_RETIREMENT_LIVES: 市场 1,270,521 | 公司和 1,270,521 ✓
- IF_GROUP_NON_RETIREMENT_NON_SINGLE_PREMIUM_RECEIVABLE: 市场 2,212,759 | 公司和 2,212,759 ✓
- IF_GROUP_NON_RETIREMENT_POLICIES: 市场 15,394 | 公司和 15,394 ✓
- IF_GROUP_NON_RETIREMENT_SINGLE_PREMIUM_RECEIVABLE: 市场 0 | 公司和 0 ✓
- IF_IND_TOTAL_NON_SINGLE_PREMIUM_RECEIVABLE: 市场 150,911,425 | 公司和 150,911,425 ✓
- IF_IND_TOTAL_POLICIES: 市场 16,139,623 | 公司和 16,139,623 ✓
- IF_IND_TOTAL_SINGLE_PREMIUM_RECEIVABLE: 市场 91,170,510 | 公司和 91,170,510 ✓
- IF_IND_TOTAL_SUMS_ASSURED_OR_ANNUITIES: 市场 10,269,241,203 | 公司和 10,269,241,203 ✓
- IF_RETIREMENT_ENDING_FUND_BALANCE: 市场 131,447,875 | 公司和 131,447,875 ✓
- IF_RETIREMENT_NON_SINGLE_CONTRIBUTIONS: 市场 2,072,765 | 公司和 2,072,765 ✓
- IF_RETIREMENT_SCHEMES: 市场 361,394 | 公司和 361,394 ✓
- IF_RETIREMENT_SINGLE_CONTRIBUTIONS: 市场 10,033,196 | 公司和 10,033,196 ✓
- NB_GROUP_ANNUALIZED_PREMIUM: 市场 89,520 | 公司和 89,520 ✓
- NB_GROUP_LIVES: 市场 30,430 | 公司和 30,430 ✓
- NB_GROUP_POLICIES: 市场 471 | 公司和 471 ✓
- NB_GROUP_SINGLE_PREMIUM: 市场 0 | 公司和 0 ✓
- NB_IND_TOTAL_ANNUALIZED_PREMIUM: 市场 50,576,626 | 公司和 50,576,626 ✓
- NB_IND_TOTAL_SINGLE_PREMIUM: 市场 90,464,756 | 公司和 90,464,756 ✓
- reconcile 覆盖指标数：18
## 4. schema: unit / period_basis / comparability
- NB_IND_TOTAL_SINGLE_PREMIUM: flow_during_period | HKD_thousand | comparable_with_schema_bridge
- NB_IND_TOTAL_ANNUALIZED_PREMIUM: flow_during_period | HKD_thousand | comparable_with_schema_bridge
- NB_GROUP_POLICIES: flow_during_period | count | directly_comparable_by_label
- NB_GROUP_LIVES: flow_during_period | count | directly_comparable_by_label
- NB_GROUP_SINGLE_PREMIUM: flow_during_period | HKD_thousand | directly_comparable_by_label
- NB_GROUP_ANNUALIZED_PREMIUM: flow_during_period | HKD_thousand | directly_comparable_by_label
- IF_IND_TOTAL_POLICIES: stock_at_period_end | count | comparable_with_schema_bridge
- IF_IND_TOTAL_SUMS_ASSURED_OR_ANNUITIES: stock_at_period_end | HKD_thousand | comparable_with_schema_bridge
- IF_IND_TOTAL_SINGLE_PREMIUM_RECEIVABLE: flow_during_period | HKD_thousand | comparable_with_schema_bridge
- IF_IND_TOTAL_NON_SINGLE_PREMIUM_RECEIVABLE: flow_during_period | HKD_thousand | comparable_with_schema_bridge
- IF_GROUP_NON_RETIREMENT_POLICIES: stock_at_period_end | count | directly_comparable_by_label
- IF_GROUP_NON_RETIREMENT_LIVES: stock_at_period_end | count | directly_comparable_by_label
- IF_GROUP_NON_RETIREMENT_SINGLE_PREMIUM_RECEIVABLE: flow_during_period | HKD_thousand | directly_comparable_by_label
- IF_GROUP_NON_RETIREMENT_NON_SINGLE_PREMIUM_RECEIVABLE: flow_during_period | HKD_thousand | directly_comparable_by_label
- IF_RETIREMENT_SCHEMES: stock_at_period_end | count | directly_comparable_by_label
- IF_RETIREMENT_ENDING_FUND_BALANCE: stock_at_period_end | HKD_thousand | directly_comparable_by_label
- IF_RETIREMENT_SINGLE_CONTRIBUTIONS: flow_during_period | HKD_thousand | directly_comparable_by_label
- IF_RETIREMENT_NON_SINGLE_CONTRIBUTIONS: flow_during_period | HKD_thousand | directly_comparable_by_label