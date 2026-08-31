# 年度公司事实层 Manifest v0.1

| 项 | 值 |
|---|---|
| asset_id | ANN-CMP-FACT-LAYER-2023-2024 |
| 版本 | v0.1 |
| 状态 | active_certified（2023 + 2024 两年度）|
| 源资产 | `ASTSET-IA-LTA-2024-FULL-XLSX` + `ASTSET-IA-LTA-2023-FULL-XLSX` |
| 源路径 | `01_sources/raw/SRC-REG-IA-LTA/{2023,2024}/full_annual_set/`（L8-L19 各 12 表）|
| 目标路径 | `生成_年度公司事实层_AnnualCompanyFactLayer/data/annual_company_fact_layer_2023_2024.db` |
| 表 | company_facts |
| 事实数 | 4,718（公司 4,638 + Market Total 80）|
| 单位 | count / HKD_thousand |
| 标签 | certified |

## 源文件（哈希见 facts.checksum_sha256）
| 年度 | 表 L8-L19 | 状态 |
|---|---|---|
| 2024 | 12 表全 | 全解析 |
| 2023 | 12 表全 | 全解析 |

## 覆盖语义（schema-aware）
| 表族 | 年度 | 关键语义 |
|---|---|---|
| L8-L13 inforce | 2024 | current_estimate；L11 → scheme_count |
| L8-L13 inforce | 2023 | net_liabilities；L11 → policy_count+lives |
| L14-L19 new business | 两者 | policy_count_single/annual + premium_single/annual |

## QA 结论
- 每表 公司sum=Market Total：80 检查全过。
- L14+L15=L16：exact 0。
- L13 成分（L11 路由）：exact 0。
- 详见 `qa/annual_company_fact_layer_qa_report.md`。
