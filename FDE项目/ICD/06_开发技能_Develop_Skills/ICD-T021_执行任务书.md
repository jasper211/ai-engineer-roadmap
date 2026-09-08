# ICD-T021 · 下游数据交换契约与发布包

> 执行与审计：Codex  
> 状态：IN_PROGRESS  
> 日期：2026-09-08

## 目标与门禁

为 U020 等消费者生成不依赖 ICD 内部 SQLite Schema 的稳定 JSON/JSONL 交换包。只发布最新成功版本，完整保留官网原文、标准化值、run_id、URL、抓取时间、SHA-256 和 coverage；内容寻址、不可静默覆盖，CRITICAL 健康状态禁止发布，DEGRADED 状态必须标记 `PARTIAL_COVERAGE`。
