# ICD-T022 · 下游消费者交换包验收器

> 执行与审计：Codex  
> 状态：ACCEPTED  
> 日期：2026-09-08

## 目标与门禁

从不信任生产方的消费者视角独立验收 v1 交换包：目录身份、契约版本、文件集合、字节数/SHA-256、JSON/JSONL、记录数、必需字段、关键类型、自然键唯一性及 release_status/health/coverage 一致性。任何失败返回退出码 2，禁止下游读入。

## 执行与审计回执

- 新增 `tools/icd_export_validator.py` 与 CLI `--validate-export BUNDLE_PATH`；正式包验收结果 `ACCEPTED`、errors=0、exit=0。
- 独立重算内容寻址 bundle_id，核对目录名、契约版本、精确文件集合、文件字节数和 SHA-256；不能仅信任 manifest 自报身份。
- 逐行验证 13,039 条分红 JSONL 和 8 条 RBC：必需字段、关键类型、证据哈希、自然键唯一性，以及可直接复算的百分比原文与标准值。
- 验证 23 条 coverage 状态，并强制 `READY/HEALTHY/无缺口` 或 `PARTIAL_COVERAGE/DEGRADED/有缺口` 一致。
- 负向测试覆盖文件字节篡改，以及攻击者同步更新 manifest 文件哈希后的语义篡改；两者均被拒绝。
- T002–T022 共 19 套测试脚本全量通过。效率指标：Codex 单闭环；审计补强 1 次；人工 Gate 0；DeepSeek 调用 0。
