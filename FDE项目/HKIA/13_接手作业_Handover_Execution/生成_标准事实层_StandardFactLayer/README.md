# 标准事实层 Standard Fact Layer · 2023Q1–2026Q1

> **B2 产物** · 把 2023Q1–2026Q1 的市场核心事实与公司事实固化为统一、可查询的 SQLite 标准事实表。
> Schema 遵循 intergalactic 风格：期间 / 指标ID / 原始值 / 单位 / 流量或存量 / 可比等级 / 来源locator。

## 快速导航
- 数据库：`data/standard_fact_layer_2023_2026Q1.db`
- 构建脚本：`scripts/build_standard_fact_layer.py`
- QA 报告：`qa/standard_fact_layer_qa_report.md`
- 清单：本文件 + `manifest_standard_fact_layer_v0.1.md`
- 验收：`验收与生成说明_v0.1.md`

## 三张表

### `market_facts`（72 行 = 18 指标 × 4 期间）
| 字段 | 说明 |
|---|---|
| `fact_id` | `M|{period}|{metric_id}` 唯一 |
| `period` | 2023Q1 / 2024Q1 / 2025Q1 / 2026Q1 |
| `metric_id` | 18 个核心指标之一 |
| `metric_label` | 中文业务名 |
| `value` | 原始值（HKD_thousand 或 count），**保持官方原值不折算** |
| `unit` | HKD_thousand / count |
| `period_basis` | flow_during_period / stock_at_period_end |
| `comparability` | 官方可比等级 |
| `source_sheet` / `source_range` / `source_file` | 来源定位 |

### `company_facts`（4914 行 = 公司 × 期间 × 指标）
| 字段 | 说明 |
|---|---|
| `fact_id` | `C|{period}|{entity_key}|{metric_id}` 唯一 |
| `entity_key` / `source_abbrev` | 规范实体键 + 源报表短名 |
| `business_lineage` / `bridge_class` | 线索桥归属 / 桥接类别（Chubb、canada_mypace 转移事件承接） |
| `value` / `value_status` | 原始值 + reported_numeric / reported_missing（**缺值保 NULL，不补零**） |
| 其余 | 同 market_facts，另含 `source_cell` 单元格定位 |

### `schema_metrics`（18 行）
- 官方指标字典：`metric_id → unit / period_basis / metric_label`（源自 `quarterly_long_metric_comparability_v0.1.yaml`）

## 数据纪律（沿用接手前口径）
1. **缺值 = NULL，绝不补零**：公司事实 `value_status='reported_missing'` 共 2471 行如实保留。
2. **原始值单位不擅自折算**：`value` 一律存 HKD_thousand / count，亿港元等衍生口径另算。
3. **可比等级如实标注**：个人 6 个核心指标 `comparable_with_schema_bridge`，跨 2025 断点需桥接；其余 `directly_comparable_by_label`。
4. **转移事件以 lineage 承接**：2026Q1 Chubb/canada_mypace 的转移在 `business_lineage` / `bridge_class` 标注，不虚增单个事实。
5. **Q1 序列不含 2025Q4**：仅四个同季期间。

## 可查询性（示例）
```sql
-- 个人新造整付保费，四期市场总额
SELECT period, value, unit FROM market_facts
WHERE metric_id='NB_IND_TOTAL_SINGLE_PREMIUM' ORDER BY period;

-- 2026Q1 个人新造整付保费 TOP5 公司（数值型）
SELECT entity_key, value FROM company_facts
WHERE period='2026Q1' AND metric_id='NB_IND_TOTAL_SINGLE_PREMIUM'
  AND value_status='reported_numeric'
ORDER BY value DESC LIMIT 5;
```

> 更多示例见 `scripts/query_examples.py`。
