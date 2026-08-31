# U20 跨年度同口径桥 · r3 修复验证记录

> 给 U20 侧复核用的交付文档。对应 `U20调用复验_20260831_r3.md` 的 A/B/C/D 修复。
> 日期：2026-08-06

---

## 一、修复总览（对应 r3 逐项）

| r3 问题 | 修复 | 验证状态 |
|---|---|---|
| A. 安盛源名称 | 2025 名改正为 AXA CRI (HK)/AXA CRI，经 ENTITY_AXA_CRI_HK 桥 | ✅ 已核对 |
| B. 缺失 vs 零值 | 排除清单加 record_status（reported_zero/missing/not_applicable/renamed）| ✅ 已核对 |
| C. 子方案残留冲突 | 方案2子集第三节"可用+65.4%"已统一撤回 | ✅ 已核对 |
| D. 连接示例 | 指引 4.2 补全可运行示例 | ✅ 已核对 |

---

## 二、机器可读产物（v2，请 U20 复核）

路径：`生成_跨年度同口径桥_CrossYearBridge/bridge/`
- `可比公司映射_2024L16_2025L1_v2.csv`（22 家可比，含双方真实源名 + entity_key + bridge_type + 双边 record_status + 金额）
- `排除清单_2024_2025_v2.csv`（46 行，含 record_status + exclusion_reason）
- `桥覆盖率与差异_v2.json`（覆盖率、闭合差、警示）

### CSV 列结构说明
| 文件 | 列 |
|---|---|
| 可比映射 | source_2024, source_2025, entity_key, bridge_type, premium_2024_hkd_thousand, premium_2025_hkd_thousand, record_status_2024, record_status_2025, evidence |
| 排除清单 | source_2024, source_2025, entity_key, record_status_2024, record_status_2025, premium_2024_hkd_thousand, premium_2025_hkd_thousand, exclusion_reason |

---

## 三、独立复算核对（U20 可直接复跑）

单位：千港元；容差仅用于浮点（0.00001），不用于掩盖业务差额。

| 年度 | 市场总额 | 映射22行合计 | 排除合计 | 闭合差 | 覆盖率 |
|---|---:|---:|---:|---:|---:|
| 2024 L16 | 90,226,978.42 | 89,858,894.05 | 368,084.37 | **0.0** | 99.59% |
| 2025 L1 | 162,006,264.86 | 153,082,664.76 | 8,923,600.09 | **3e-8** | 94.49% |

> 2024 排除金额仅 2 家：ZA Insure 355,976.37 + Transamerica 12,108 = 368,084.37。其余为 0 值/missing。

## 四、错误修正的核心证据

### 安盛（r3 关键缺陷）
| 2024 源名 | 2025 正确源名 | entity_key | bridge_type | 证据 |
|---|---|---|---|---|
| AXA China (Bermuda) | **AXA CRI (HK)** | ENTITY_AXA_CRI_HK | rename_or_alias | 标准层 company_facts entity_key |
| AXA China (HK) | **AXA CRI** | ENTITY_AXA_CRI | rename_or_alias | 标准层 company_facts entity_key |

> 已核对标准层 `standard_fact_layer...db` 的 `company_facts`：`ENTITY_AXA_CRI_HK` 同时有 source_abbrev='AXA China (Bermuda)' 和 'AXA CRI (HK)'，证实为同一实体；`ENTITY_AXA_CRI` 同理。

### record_status（缺失 vs 零值）
- 排除清单 46 行中：`reported_value` 2 家（ZA/Transamerica），`reported_zero` 33 家，`missing` 11 家。
- **11 家 missing** = 2024 L16 中无记录的再保险机构（China Re/GenRe/Munich Re 等），已标 `missing` 而非误记为 0；2024 的 `AXA China (HK)` 在排除清单为 name 问题，映射已含正确 AXA CRI 记录。

---

## 五、仍未验收项（明确，勿作放行）

- ❌ **范围等价证明**（2025 L1 非"其他"档不等于 2024 L16 的双向证据）——受 IA 2025 产品定义缺失 + 2024 Definition 损坏限制，当前环境未闭环。
- ❌ **分红+相连分项独立复算**（1492.0亿需回原始工作簿复算）。
- **→ 跨年度同口径增长（含 +65.4%）仍未验收、不得发布。** 本桥仅作机器可读的公司映射/覆盖/对账参考，非同口径增长结论。

## 六、U20 复核建议
1. 用 `bridge/*_v2.*` 三文件复跑第三方对账（CSV 汇总 vs 两库市场总额）。
2. 核对安盛两组映射是否可用（标准层 ENTITY_AXA_CRI_HK/ENTITY_AXA_CRI 为证据）。
3. 核对 record_status 是否区分 reported_zero/missing。
4. 确认范围等价未验收，不发布同口径增长。

---

## 更新记录
| 日期 | 作者 | 内容 |
|---|---|---|
| 2026-08-06 | Jasper/接手方 | 桥 r3 修复验证记录（A/B/C/D + 复算核对）|
