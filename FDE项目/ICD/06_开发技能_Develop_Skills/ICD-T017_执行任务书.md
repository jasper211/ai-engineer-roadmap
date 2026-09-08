# ICD-T017 · AXA、YFL、Sun Life RBC 接入

> 执行与审计：Codex  
> 状态：ACCEPTED（AXA/SUN 入库；YFL 安全失败）  
> 日期：2026-09-07

## 目标与门禁

发现并接入 AXA China Region Insurance Company Limited、YF Life Insurance International Limited、Sun Life Hong Kong Limited 的官方 2024 RBC Disclosure Statement。仅使用官方索引/文件；逐份核对法律主体、年度、偿付能力比率、资本金额原文与单位；结构或主体不一致即失败，不写业务数据。完成快照哈希、离线解析、幂等、故障测试、全量回归和数据库完整性审计后放行。

## 执行回执与自审

- AXA：官方 `/en/cri` 页面定位的 Prismic PDF，run_id=23，SHA-256 `d3bada8339bf1e169df0661fecda89f47539a9c5c97f4738472d220a89363095`；法律主体正确，2024、204%，Capital Base/PCA 原文 `10,636,247`/`5,189,682` 千港元。
- Sun Life：官方 PDF run_id=25，SHA-256 `317089452d81b18ccc32137a1b6be7246acf5eea12224085451cd339f13f4a0a`；法律主体正确，2024、229%，Capital Base/PCA 原文 `20,981,085`/`9,165,514` 千港元。
- YF Life：官方 PDF run_id=24，SHA-256 `529938a06940ca9d3429f9f89ac95b586faec99fb5f4d695e2526a3b7b7b9e1d`；文件无可提取文字层，解析 `PDF_NO_TEXT`，业务表不写入，coverage=`MISSING`。不使用搜索摘要或未经批准的 OCR 猜数。
- 修复通用 RBC 单位选择：同一 PDF 同时出现不完整 `in HKD` 与完整 `in HKD thousands` 时，穷尽候选并优先唯一带标度单位；多标度/多币种歧义直接失败。AXA/SUN 金额正确乘 1,000 后才入库。
- 全量离线编排 processed=17/succeeded=16/failed=1；唯一失败为已知 YFL `PDF_NO_TEXT`。T002-T017 共 14 套测试脚本通过；integrity=ok、外键违例 0。
- 自审结论：AXA/SUN 放行；YFL 以可复核安全失败收口，继续保留专项缺口，不阻塞下一批来源。
