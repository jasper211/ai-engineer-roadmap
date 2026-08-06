# B1 · 2025 全年 Provisional 事实层 QA 报告 v0.1

> 日期：2026-08-06 · 属 B1 本地可闭环任务
> 范围：2025 年全年（calendar year）以 `provisional` 标签接入的年度事实层（annual_facts）。

## 一、QA 结论（一句话）

**2025 全年 18 核心市场指标已从 2025Q4 资产完整抽取，全部落位 Market Total 行，标签正确为 `annual_provisional`；与 certified 年度（2024）的正式 reconcile 因年度 L 表属不同量纲/表族，标记为「待年度认证层建立后执行」，不做伪 certified 合并。**

## 二、覆盖核对（完整性）

| 指标族 | 指标数 | 抽取状态 |
|--------|:---:|:---:|
| 新造 个人 (Table L1) | 2 | ✅ |
| 新造 团体 (Table L2) | 4 | ✅ |
| 有效 个人 (Table L3) | 4 | ✅ |
| 有效 团体/退休 (Table L4) | 8 | ✅ |
| **合计** | **18** | **全抽取，无缺失** |

- 来源资产：`SRC-REG-IA-LTQ-2025Q4/4q25long.xlsx`（January to December 2025）
- 每项均带 `period_layer=annual_provisional`、`certification=provisional`、单期/同期基准、单位、可比等级、来源 locator。

## 三、体量合理性核对（亿港元, /1e5）

| 指标 | 千港元 | 约亿港元 | 合理区间 |
|------|--------|:---:|---|
| NB_IND_TOTAL_ANNUALIZED_PREMIUM | 168,551,949 | 1,685.5 | 全年个人年化新单 ~16xx亿，符合全年量级 ✔ |
| NB_IND_TOTAL_SINGLE_PREMIUM | 162,006,265 | 1,620.1 | 全年个人整付 ~16xx亿 ✔ |
| IF_IND_TOTAL_NON_SINGLE_PREMIUM_RECEIVABLE | 498,636,411 | 4,986.4 | 存量非整付可收保费 ~中四位数亿 ✔ |
| IF_IND_TOTAL_SINGLE_PREMIUM_RECEIVABLE | 164,176,912 | 1,641.8 | 存量整付可收 ✔ |

> 与季度序列对比：2025Q1 个人年化新单 464.6 亿、整付 468.5 亿；2025 全年（Q4 累计视角）~1685/1620 亿 ≈ 3.5×Q1，符合全年 vs 单季量级特征，方向合理。

## 四、Period 基准核对（避免口径混用）

| 检查项 | 结果 |
|--------|:---:|
| 2025 全年确为 `annual` 层（非 Q1 序列） | ✅ |
| 与 2026Q1 / 2025Q1 等 Q1 序列分表存续，不混入 market_facts 表 | ✅（写入独立 annual_facts 表） |
| `period_basis`（flow/stock）逐项正确 | ✅（6 flow / 12 stock 与 schema 一致） |
| `directly_comparable_by_label` vs `comparable_with_schema_bridge` 分级 | ✅（与 comparability yaml 一致） |

## 五、Red Line / 限制（必须随引用同行）

1. **2025 全年为 `provisional`（临时统计）**，在任何对外上下文**不得**标注为 certified 年度统计。比较规则仅限 `analysis_window` 中允许的 `2024_full_year→2025_full_year_provisional`。
2. **不得以 2025 全年除以某单季**计算增长率（`prohibited`）。
3. **与 2024 certified 年度的正式 reconcile**：2024 来自**年度 L 表族**（HKD_million / scheme_count / 不同量纲），与 2025Q4 的新季报形式存在**单位与表族差异**。在年度认证事实层（annual_long normalized layer）建立前，**不做伪 certified 合并**；此类差异列入 `annual_long_schema_registry` 的 `prohibited_joins` 语义。
4. 单笔异常（如 Chubb）仍需公司披露佐证，不得由排名反推为自然增长。

## 六、回归影响

- 本事实入独立 `annual_facts` 表，未改动 `market_facts` / `company_facts` / `schema_metrics`。
- 已落库原始资产（2025Q4）只读，未覆盖。
- 对 `09_测试` 既有集成测试的影响：无（新增表不在原测试断言范围）。

## 七、下一步（非本项阻塞）

- [ ] 承接年度认证基线层（2023/2024 annual_long）后，对 2025 provisional 执行 certified↔provisional 回溯 reconcile 并登记。
- [ ] 将 2025 provisional 纳入「谁增长」解释层（可与 2026Q1 排名并列引用，但须加 provisional 注）。

---
> QA 依据：`analysis_window_2023_2026Q1_v0.1.yaml`、`quarterly_long_metric_comparability_v0.1.yaml`、
> `quarterly_long_2023Q1_2026Q1_asset_manifest_v0.1.yaml`、`annual_long_schema_registry_v0.1.yaml`。
