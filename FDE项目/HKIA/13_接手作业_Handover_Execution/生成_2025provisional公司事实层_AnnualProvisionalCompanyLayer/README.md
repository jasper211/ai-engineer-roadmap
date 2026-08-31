# 2025 provisional 公司级事实层

> **标：** 把 2025 全年 provisional 从"市场总额级"下探到**公司级**，使 certified(2022/2023/2024) ↔ provisional(2025) 可做公司级 reconcile。
> 来源：`01_sources/raw/SRC-REG-IA-LTQ/2025Q4/4q25long.xlsx`（January to December 2025）。
> 承接：`生成_2025年度provisional事实层_AnnualProvisional2025`（annual_facts 18 指标 = 市场总额级）。

## 覆盖
| 表 | 内容 | 提取指标 |
|---|---|---|
| Table L1（新造）| 公司级个人长期新造 | nb_total_single_premium（总额整付）；nb_total_annualized_premium（总额年度化）|
| Table L3（有效）| 公司级个人长期有效 | if_total_policies / if_total_sums_assured / if_total_single_premium / if_total_non_single_premium（总额列 c15-18）|

## 文件
```
生成_2025provisional公司事实层_AnnualProvisionalCompanyLayer/
├── data/annual_provisional_company_2025.db   SQLite（表 provisional_company_facts，414 事实）
├── scripts/build_provisional_company_2025.py
├── qa/reconcile_provisional_company_2025.py
└── README / manifest / qa_report
```

## QA（全过）
- **表内 reconcile**：公司 sum == Market Total（L1 新造、L3 有效，6 检查全过）。
- **vs annual_facts**：L1 新造公司加总 = 标准事实层 18 指标市场总额，diff ~3e-8（浮点）。
- **跨年 2024 certified vs 2025 provisional**：可做，但**有 schema 桥缺口**（2024 L16 个人寿险 vs 2025 L1 个人长期含年金），须标注。

## 口径纪律
- 单位：保单 count / 金额 hkd_thousand（千港元）。
- 标 provisional，不得当 certified。
- 2025 L1 總額（个人长期含年金/相连）与 2024 certified L16（个人寿险新造）口径不同，跨年对比须按 schema-bridge 处理。
## 用法
```bash
python3 scripts/build_provisional_company_2025.py   # 重建（幂等）
python3 qa/reconcile_provisional_company_2025.py    # QA
```
