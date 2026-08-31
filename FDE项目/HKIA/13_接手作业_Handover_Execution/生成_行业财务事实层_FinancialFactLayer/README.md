# 行业财务事实层 · Financial Fact Layer

> B4 · 香港保险业 IA 季度临时财务资料（Assets & Liabilities）
> 承接：`12_分析框架验证/02_assets/asset_registry_phase_b` 的 `ASTSET-IA-FINANCIAL-2024Q4-2026Q1-XLSX`。

## 这是什么

把 IA 季度临时财务 XLSX 的 **"By Fund"** sheet（行业总计/长期/分红长期/一般业务 四类基金 × 17 个资产/负债科目）
解析为标准话事实层，供 U20 等下游作为**资产负债表 / 资产配置**输入源。

## 覆盖范围

| 项目 | 内容 |
|---|---|
| 期数 | **2024Q4, 2025Q1, 2025Q3, 2025Q4, 2026Q1**（5 期）|
| ⚠️ 缺口 | **2025Q2**（源为 DRM/ECMA-376 加密文件，需 IA 密码/重发，登记 `encrypted_pending_ia`）|
| 基金范围 | industry_total / long_term / participating_long_term / general_business |
| 科目 | 總資產、現金和存款、債務證券、股權、房產、貸款及墊款、保單持有人賬戶資產、其他金融資產、再保險資產、稅務資產、其他資產、總負債、保險負債、金融負債、稅務負債、其他負債、淨資產（17 项）|
| 单位 | 港币百万元（HK$'million，官方原始值）|
| 标签 | `provisional_unaudited` |

## 文件结构
```
生成_行业财务事实层_FinancialFactLayer/
├── data/financial_fact_layer.db        SQLite（表 financial_facts）
├── scripts/build_financial_fact_layer.py  构建（幂等可重建）
├── qa/reconcile_financial_facts.py      identify 恒等式 QA
└── qa/financial_fact_layer_qa_report.md     QA 报告
```

## 用法
```bash
python3 scripts/build_financial_fact_layer.py  # 重建 DB
python3 qa/reconcile_financial_facts.py        # QA
```
查询示例见 `scripts/query_examples.py`（有则用）。

## 口径纪律
- `value_hkd_million` 为官方原始值，不做单位换算。
- 占位符 `-` → 0.0（无该科目），与真实 0 在源中无字段区分，均已记录。
- 2025Q2 补齐需 IA 提供密码或重新下发未加密版本，补齐后重跑本脚本+QA 即可。
- 引用时须带 `provisional_unaudited` 标签，不得当最终审计数。
