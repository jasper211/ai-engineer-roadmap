# 年度公司事实层 QA 报告

> 对应 `生成_年度公司事实层_AnnualCompanyFactLayer/data/annual_company_fact_layer_2023_2024.db`
> 日期：2026-08-06

## 一、覆盖

| 维度 | 值 | 结果 |
|---|---|---|
| 年度 | 2024（RBC）、2023/2022（pre-RBC）| ✅ |
| 表 | L8-L19（各 12 表）| ✅ |
| 事实 | 7,097（公司 6,978 + Market Total 119）| ✅ |
| 指标语义 | policy_count/sums_assured/premium_single/premium_annual/current_estimate/net_liabilities/lives/scheme_count/contribution_single/contribution_annual | ✅ 由行标签驱动识别 |

## 二、reconcile 结果

### 1. 每表 internal（公司 sum = Market Total）
- **119 检查全过**，最大差 1.9e-6（HKD_thousand 浮点）。
- 每张公司表的 Market Total 与本表全部公司行相加精确吻合，证明解析完整无漏行。

### 2. 新造成分 L14+L15 = L16
- 2024：policy_count、premium_single 均 exact 0。
- 2023：policy_count、premium_annual 均 exact 0。
- 2022：policy_count、premium_annual 均 exact 0。
- 说明：L15（linked）+ L14（non-linked）加总恒等于 L16（个人新造总额）。

### 3. inforce 成分 vs L13（schema-aware L11 路由）
- **2024（RBC）**：L13 = Σ(L8,9,10,12).metric + L11.scheme_count/contribution → 全部 exact 0。
- **2023/2022（pre-RBC）**：L13 = Σ(L8,9,10,12).metric + L11.policy_count/contribution → 全部 exact 0。
- current_estimate（2024）sum 亦 exact 0。
- 关键：L11 退休计划在 RBC 用 scheme_count、在 pre-RBC 用 policy_count；L13 总数并入方式已按 schema 路由正确。

## 三、schema 校验 key point
- 2023 年付列在前、2024 整付列在前：由**标签驱动**映射解决，非固定列号。QA 证实两年度均正确。
- 2023 负债为 net_liabilities、2024 为 current_estimate：语义正确区分，未混用。

## 四、数据纪律
- `-` 占位符 → 0；`N.A.` 保持 NULL。
- Market Total 单独 entity_scope，不参与普通公司行累加。
- 金额统一 HKD_thousand，保单/受保人/计划数为 count，不混加。

## 五、回归方式
```bash
python3 scripts/build_annual_company_fact_layer.py   # 重建（幂等）
python3 qa/reconcile_annual_company_layer.py         # QA
```
