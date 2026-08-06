# 生成_2025年度provisional事实层 · AnnualProvisional2025

> 承接 B1 本地可闭环任务：**2025 全年以 `provisional` 标签标准化接入**。
> 依据：`analysis_window_2023_2026Q1_v0.1.yaml`（annual_provisional: 2025, labeling_required: provisional）。

## 一句话

从 **2025Q4**（January to December 2025，latest complete calendar year view）抽取 **18 个核心市场指标**的市场总额，
固化为 **2025 全年 provisional 年度事实层**，写入标准事实层的 `annual_facts` 表。

## 定位与边界

- **这是年度的"最新完整日历年临时视图"**，不是任何季度的同期序列（后者由 B2 `market_facts` 承担）。
- **provisional = 临时统计**；在任何上下文不得当 **certified** 年度统计。
- 与 2024 certified 年度的正式 reconcile 待年度认证层建立后执行（见 QA 第五节）。

## 产物清单

| 文件 | 定位 |
|------|------|
| `scripts/build_annual_provisional_2025.py` | 幂等构建脚本（只读 2025Q4，产 CSV + 写 DB） |
| `data/annual_facts_2025_provisional.csv` | 18 指标年度事实（轻量可读） |
| `qa/annual_provisional_2025_qa_report.md` | QA 报告（覆盖/体量/基准/红线/回归） |
| → `生成_标准事实层_StandardFactLayer/data/standard_fact_layer_...db` | 写入目标（`annual_facts` 表） |

## 表结构（annual_facts）

`period, period_layer, period_label, certification, metric_id, value, unit, period_basis, comparability, source_asset, source_sheet, source_locator`

## 依据文档（只读）

- `12_分析框架验证_Validate_Framework/03_data_coverage/analysis_window_2023_2026Q1_v0.1.yaml`
- `.../quarterly_long_metric_comparability_v0.1.yaml`
- `.../quarterly_long_2023Q1_2026Q1_asset_manifest_v0.1.yaml`

## 纪律遵守

- 未改动任何接手前文档（00-12 只读）。
- 未把 provisional 当 certified。
- 来源缺失/口径迁移均如实登记，不补造。
