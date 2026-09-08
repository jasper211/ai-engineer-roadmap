# ICD-T018 · CTF、FWD、BOC、CLO RBC 接入

> 执行与审计：Codex  
> 状态：ACCEPTED  
> 日期：2026-09-07

## 目标与门禁

发现并接入 CTF Life、FWD Life、BOC Life、China Life Overseas 的官方 2024 RBC Disclosure Statement。沿用官方来源、原始快照与哈希、法律主体精确匹配、唯一完整金额标度、原文复算和 fail-closed 门禁；单家无法安全提取时明确记录缺口，不用第三方数据凑数。

## 执行与审计回执

- FWD：官方 PDF `run_id=26`，SHA-256 `05a0ce4c3c9d9a7c2b30d0b25256994a42d2d24e3fb022e136ae05f65362bdb5`；2024、199%，Capital Base/PCA 原文 `21,295,041` / `10,703,322`，单位 `in HKD thousands`。
- BOC：官方 PDF `run_id=27`，SHA-256 `e5e7ae4c6efe1dce869d74adce7fe64df0d08d3bfe1f87b9a47c4bd2350f7bf4`；2024、204%，Capital Base/PCA 原文 `16,924,044` / `8,311,199`，单位 `in HKD thousands`。
- 修复 FWD 正文含 2023 比较期时的年度误判：优先使用唯一披露标题年度；标题缺失才回退全文唯一年度，多个标题年度仍硬失败。
- 修复 FWD 法律主体后的跨行注册地说明；只裁剪完整固定说明，不裁剪名称内 `(Bermuda)`，入库前仍与注册表法律名称精确相等。
- CTF 官网现页仅展示 2025 披露，旧年度推导 URL 返回 404；CLO 未发现可核验的官方 RBC 文件。两者维持 `UNVERIFIED`，未使用第三方来源或猜测数值。
- 离线全流程 processed=19 / succeeded=18 / failed=1（已知 YFL 无文字层安全失败）；RBC 共 8 个法律主体。T002–T018 共 15 套测试脚本全部通过；`integrity_check=ok`、外键违例 0。
- 效率指标：Codex 实现/审计 1 个闭环；返工 1 次（真实 FWD 比较年度暴露解析假设，写库前修复）；人工 Gate 0；DeepSeek 调用 0。
