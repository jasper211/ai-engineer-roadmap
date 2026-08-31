# 行业财务事实层 QA 报告

> B4 · 对应 `生成_行业财务事实层_FinancialFactLayer/data/financial_fact_layer.db`
> 日期：2026-08-06

## 一、覆盖

| 维度 | 数值 | 预期 | 结果 |
|---|---|---|---|
| 期数 | 4 期×17 科目 + 2025Q1 等 | 5 期（除 2025Q2）| ✅ 340 事实，覆盖完整 |
| fund_scope | 4（industry/long_term/participating/general）| 4 | ✅ |
| item_id | 17（總資產..淨資產）| 17 | ✅ |
| 中文科目标签 | 17 个（与 2026Q1 参考文件逐字一致）| 17 | ✅ |

## 二、恒等式 reconcile

对每期每 scope：
- `總資產 = Σ(10 个资产分项)`
- `總負債 = Σ(4 个负债分项)`
- `淨資產 = 總資產 - 總負債`

**结果：PASS**，最大差异 1e-6 HK$'million（即 15 位有效数字浮点舍入，约 1 港元，非数据错误）。
动态容差 `FLOAT_EPS = 1e-5 HK$'million`，全部通过。

## 三、跨期 sanity

- 行業總計總資產随季度单调不减：`5330886→5491368→5946721→6068242→6193704 (HK$m)` ✅
- 2026Q1 行业总资产 = 6193703.655610111，与官方源精确一致 ✅
- 2024Q4 行业总资产 = 5330885.59106，与 1q26 文件"By Fund (Qtr Cmp)" 的 Dec2024 列一致 ✅

## 四、数据纪律

- 单位：港币百万元（官方源原始值，不做换算）。
- 标签：`provisional_unaudited`（官方 note(4)）。
- 占位符 `-`（无该科目）→ 转 0.0，与"真实为 0"（如 participating 的 unit-linked 资产）区分记录。
- 缺失：**2025Q2 整期缺失**（见下）。

## 五、已知缺口

| 缺口 | 原因 | 状态 |
|---|---|---|
| **2025Q2** | 源文件为 **DRM/ECMA-376 加密 Office 容器**（含 EncryptedPackage/EncryptedDSIHash/EncryptedSIHash/DRMEncryptedDataSpace）；非普通旧格式，msoffcrypto 亦无法识别 | `encrypted_pending_ia` 需 IA 提供密码/重新下载未加密版本后补齐 |

## 六、回归方式

```bash
python3 scripts/build_financial_fact_layer.py   # 重建 DB（幂等）
python3 qa/reconcile_financial_facts.py         # QA
```
