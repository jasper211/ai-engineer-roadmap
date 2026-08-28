# 行业财务事实层 Manifest v0.1

| 项 | 值 |
|---|---|
| asset_id | FIN-FACT-LAYER-2024Q4-2026Q1 |
| 版本 | v0.1 |
| 状态 | active_test（2025Q2 缺口待补）|
| 源资产 | `ASTSET-IA-FINANCIAL-2024Q4-2026Q1-XLSX`（asset_registry_phase_b）|
| 源路径 | `01_sources/raw/SRC-REG-IA-FINANCIAL/{2024,2025,2026}/` |
| 目标路径 | `生成_行业财务事实层_FinancialFactLayer/data/financial_fact_layer.db` |
| 表 | financial_facts |
| 事实数 | 340（5 期 × 4 scope × 17 科目）|
| 单位 | HKD_million |
| 标签 | provisional_unaudited |

## 源文件哈希（构建时登记）
| 期 | 文件 | SHA256 |
|---|---|---|
| 2024Q4 | 4q24_Industry_Financial_Info.xlsx | （由构建脚本登记于 facts 表 checksum_sha256 字段）|
| 2025Q1 | 1q25_Industry_Financial_Info.xlsx | 同上 |
| 2025Q3 | 3q25_Industry_Financial_Info.xlsx | 同上 |
| 2025Q4 | 4q25_IndustryFinancial_Info.xlsx | 同上 |
| 2026Q1 | 1q26_Industry_Financial_Info.xlsx | 同上 |
| ⚠️ 2025Q2 | 2q25_Industry_Financial_Info.xlsx | 未解析（OLE2），见 QA 报告 |

## 纪律
- 只读原始来源，不覆盖。产出写 13 目录。
- 新期（2026Q2 等）直接加进 PERIOD_FILES 重跑脚本 + QA 即可。
- 2025Q2 补齐需 OLE2 转换工具。
