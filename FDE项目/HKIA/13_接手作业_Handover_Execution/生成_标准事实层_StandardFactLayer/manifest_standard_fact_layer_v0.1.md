# Manifest · 标准事实层 Standard Fact Layer v0.1

| 项 | 值 |
|---|---|
| asset_id | HKIA-LTQ-STANDARD-FACT-LAYER-001 |
| version | v0.1 |
| status | built_and_verified |
| 生成日期 | 2026-08-06 |
| 数据库 | `data/standard_fact_layer_2023_2026Q1.db` |
| sha256(db) | `c90c62939eb6c51af35cea890d01f534d61cf44dda7af307f52c9f508b48ba05` |
| sha256(build script) | `5c71cd0d0257d511a48d8e1ffc912e9af6507376695d0e3f2613f9631026392e` |

## 源输入
| 输入 | 路径 | 角色 |
|---|---|---|
| 市场核心事实 CSV | `12_分析框架验证_Validate_Framework/04_normalized/quarterly_long/market_total_core_facts_2023Q1_2026Q1_v0.1.csv` | 72 市场事实 |
| 公司事实 XLSX | `12_分析框架验证_Validate_Framework/outputs/HKIA_company_fact_layer_2023Q1_2026Q1_v0.1.xlsx`（Company Facts sheet） | 4914 公司事实 |
| 指标 schema | `03_data_coverage/quarterly_long_metric_comparability_v0.1.yaml` | 18 指标单位/流量存量/可比等级 |

## 事实行数
| 表 | 行数 | 说明 |
|---|---|---|
| market_facts | 72 | 18 指标 × 4 期间 |
| company_facts | 4914 | 公司 × 期间 × 指标 |
| schema_metrics | 18 | 官方指标字典 |

## 质量（QA）要点
- 覆盖：mark 去重指标 18 / 公司去重指标 18。
- 缺失：reported_numeric 2443 / reported_missing 2471（缺值保 NULL）。
- reconcile：2026Q1 全部 18 指标市场总额 = 公司数值和（差=0）✓。

## 产出目录结构
```
生成_标准事实层_StandardFactLayer/
├── README.md
├── manifest_standard_fact_layer_v0.1.md      (本文件)
├── 验收与生成说明_v0.1.md
├── data/standard_fact_layer_2023_2026Q1.db
├── qa/standard_fact_layer_qa_report.md
└── scripts/
    ├── build_standard_fact_layer.py
    └── query_examples.py
```

## 后续（next_gate）
- [ ] 公司排名仅用于通过 identity 与 outlier gate 的指标（承接 company_fact_layer next_gate）。
- [ ] 2026Q1 Chubb/canada_mypace 转移事件附加外部上下文（A9，当前暂缓）。
- [ ] 由本层派生镜像回流 `07_项目立项启动/`（验证后）。
