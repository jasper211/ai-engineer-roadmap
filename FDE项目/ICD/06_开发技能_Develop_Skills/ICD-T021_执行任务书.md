# ICD-T021 · 下游数据交换契约与发布包

> 执行与审计：Codex  
> 状态：ACCEPTED  
> 日期：2026-09-08

## 目标与门禁

为 U020 等消费者生成不依赖 ICD 内部 SQLite Schema 的稳定 JSON/JSONL 交换包。只发布最新成功版本，完整保留官网原文、标准化值、run_id、URL、抓取时间、SHA-256 和 coverage；内容寻址、不可静默覆盖，CRITICAL 健康状态禁止发布，DEGRADED 状态必须标记 `PARTIAL_COVERAGE`。

## 执行与审计回执

- 新增 `tools/icd_export.py` 与 CLI `--export`，输出 manifest、分红 JSONL、RBC JSON、coverage JSON 和发布时 health JSON。
- 正式包 `icd-exchange-v1-147a281d97570988`：13,039 条分红、8 条 RBC、23 条覆盖状态；契约 `1.0.0`，状态 `PARTIAL_COVERAGE`。
- manifest 对每个数据文件记录字节数和 SHA-256；业务记录保留 run_id、官方 URL、抓取时间、快照哈希和原始值。
- 包 ID 由契约版本与文件内容生成；审计修复了实时 `checked_at` 导致相同数据包 ID 漂移的问题。相同数据重复导出已验证 `reused=true`，不覆盖文件。
- CRITICAL 故障注入确定性阻止发布；DEGRADED 可发布但必须携带 coverage 缺口。审计前旧包移入 `_superseded` 留档，未删除。
- T002–T021 共 18 套测试脚本全量通过。效率指标：Codex 单闭环；审计返工 1 次；人工 Gate 0；DeepSeek 调用 0。
