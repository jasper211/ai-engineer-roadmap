# 年度公司事实层 · Annual Company Fact Layer

> 承接：`12_分析框架验证/03_data_coverage/annual_long_schema_registry_v0.1.yaml` 的 L8-L19 公司级表解析。
> 目标：从 IA 年度长期业务 L8-L19 公司级 Excel 构建**可查询的公司级事实库**，供 U20 作为公司维度输入源。
> 覆盖：2024（RBC）+ 2023、2022（pre-RBC）三个 certified 年度。

## 这是什么

把 IA 年度长期业务 **L8-L13（有效业务 inforce）** 与 **L14-L19（新造业务 new business）** 公司级表
解析为统一长表事实层，保留：
- 报告年 + 表号 + 业务主题
- 保险公司名（英文/中文，源称谓）
- 指标语义（policy_count/sums_assured/premium_single/premium_annual/current_estimate/net_liabilities/lives/scheme_count/contribution_*）
- 单位（count 或 HKD_thousand）
- Market Total 控制记录（entity_scope=market_total）

## 覆盖

| 项 | 内容 |
|---|---|
| 年度 | 2024（RBC schema）、2023/2022（pre-RBC schema）|
| 表 | L8-L13（inforce）、L14-L19（new business）|
| 事实数 | 7,097（公司 6,978 + Market Total 119）|
| 单位 | count（保单数/生活/计划数）；HKD_thousand（金额）|
| 标签 | 年度 = certified（官方年度审计统计）|

## 文件结构
```
生成_年度公司事实层_AnnualCompanyFactLayer/
├── data/annual_company_fact_layer_2022_2024.db   SQLite（表 company_facts）
├── scripts/build_annual_company_fact_layer.py      构建（幂等）
├── qa/reconcile_annual_company_layer.py            QA
└── (README / manifest / qa_report)
```

## QA 结果（全过）
- **每表 internal reconcile：** 公司行 sum == Market Total，80 检查全过（最大差 1.9e-6）。
- **L14+L15=L16：** exact 0（两年度）。
- **L13 inforce（schema-aware L11 路由）：** 2024 用 schema_count、2023 用 policy_count + contribution，全部 exact 0。
- 2023 用 net_liabilities、2024 用 current_estimate，均正确区分。

## 用法
```bash
python3 scripts/build_annual_company_fact_layer.py   # 重建 DB（幂等）
python3 qa/reconcile_annual_company_layer.py         # QA
```

## 口径纪律（与 schema registry 一致）
- 标签驱动列映射，不依赖固定列号（2023 年付列在前、2024 整付列在前）。
- `-` 占位符 → 0；`N.A.` 保持缺失（NULL），不强制转 0。
- L11 退休计划：2023=policy_count+lives，2024=scheme_count；L13 总数并入方式已按 schema 路由。
- Market Total 作为控制记录保留，不当作普通公司明细。
