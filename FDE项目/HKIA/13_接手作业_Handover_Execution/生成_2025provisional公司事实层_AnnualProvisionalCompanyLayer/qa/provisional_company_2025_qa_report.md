# 2025 provisional 公司级事实层 QA 报告

> `annual_provisional_company_2025.db` · 2026-08-06

## 一、覆盖
- Table L1（新造）：公司级个人长期 整付/年度化 保费
- Table L3（有效）：公司级个人长期 保单数/保额/整付/非整付
- 414 事实（公司 408 + Market Total 6）

## 二、reconcile 结果
### 1. 表内 reconcile（公司 sum = Market Total）
| 表.指标 | 公司加总 | Market Total | diff | 结果 |
|---|---|---|---|---|
| L1.新造整付 | 162,006,264.857 | 相同 | 3e-8 | OK |
| L1.新造年化 | 168,551,949.464 | 相同 | 3e-8 | OK |
| L3.有效保单 | 16,058,327 | 相同 | 0 | OK |
| L3.有效保额 | 10,040,227,097.871 | 相同 | 1.9e-6 | OK |
| L3.有效整付 | 164,176,912.250 | 相同 | 0 | OK |
| L3.有效非整付 | 498,636,410.523 | 相同 | 0 | OK |

### 2. vs 标准事实层 annual_facts（18 指标市场总额）
- L1.新造整付 / 年化 公司加总 = annual_facts.NB_IND_TOTAL_SINGLE/ANNUALIZED_PREMIUM，diff ~3e-8 浮点 ✓
- 证明 2025 provisional 公司层与既有市场总额层完全自洽。

### 3. 跨年 certified(2024) vs provisional(2025)
| 指标 | 2024 certified | 2025 provisional | YOY |
|---|---|---|---|
| 个人整付保费 | 90,226,978（L16 个人寿险新造）| 162,006,265（L1 个人长期新造）| +79.6% |
- ⚠️ **口径差异**：2024 L16=个人寿险新造；2025 L1 總額=个人长期（含分红/其他/相连/年金）。跨年对比须按 schema-bridge 处理，非纯自然增长。整付井喷部分来自渠道/产品结构（此前 2025Q1 整付+93.1% 已记录）。

## 三、纪律
- provisional 标签，不当 certified。
- 跨年公司对比必须标注 2024 L16 vs 2025 L1 的 scope 差异。
