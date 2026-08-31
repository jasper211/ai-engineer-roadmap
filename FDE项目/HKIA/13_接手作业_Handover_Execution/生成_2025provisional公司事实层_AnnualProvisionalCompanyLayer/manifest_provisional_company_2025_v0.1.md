# 2025 provisional 公司级事实层 Manifest v0.1

| 项 | 值 |
|---|---|
| asset_id | ANN-PROV-CMP-2025 |
| 版本 | v0.1 |
| 状态 | active_provisional |
| 源资产 | `4q25long.xlsx`（2025Q4, January to December 2025）|
| 源路径 | `01_sources/raw/SRC-REG-IA-LTQ/2025Q4/` |
| 目标路径 | `生成_2025provisional公司事实层_AnnualProvisionalCompanyLayer/data/annual_provisional_company_2025.db` |
| 表 | provisional_company_facts |
| 事实数 | 414（公司 408 + Market Total 6）|
| 单位 | count / hkd_thousand |
| 标签 | provisional |

## 提取
| 表 | 列 | 指标 |
|---|---|---|
| Table L1 | c9/c10 总额整付/年度化 | nb_total_single_premium / nb_total_annualized_premium |
| Table L3 | c15-18 总额保单/保额/整付/非整付 | if_total_policies / sums_assured / single / non_single |

## QA
- 表内 reconcile（公司加总=Market Total）：6 检查全过。
- 与 annual_facts 一致性：diff ~3e-8 浮点。
- 跨年 certified↔provisional：可做，schema-bridge 口径差异须标注。
