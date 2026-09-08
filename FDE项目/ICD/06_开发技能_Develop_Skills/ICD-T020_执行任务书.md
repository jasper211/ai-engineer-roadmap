# ICD-T020 · 生产健康检查与数据过期告警

> 执行与审计：Codex  
> 状态：ACCEPTED  
> 日期：2026-09-08

## 目标与门禁

提供无网络、只读、可供调度器判断的健康检查：验证 SQLite 完整性与外键、业务孤儿与重复键、成功快照存在性和 SHA-256、年度数据时效、coverage 缺口。退出码固定为 0=HEALTHY、1=DEGRADED、2=CRITICAL；已知覆盖缺口不得伪装成系统故障，快照损坏等完整性问题不得降级成普通警告。

## 执行与审计回执

- 新增 `tools/icd_health.py` 与 CLI `--health`，全程无网络并以 SQLite `mode=ro` 检查。
- 检查项：integrity、foreign keys、业务孤儿、分红重复自然键、成功快照存在性/SHA-256、最大年龄和 coverage 缺口。
- 真实基线：`DEGRADED` / exit 1；21 个成功快照缺失 0、哈希错配 0，数据库 integrity=ok、外键/业务孤儿/重复键均为 0；仅有 6 个已知非 FULL 覆盖项。
- 故障注入测试把一个成功快照路径改为不存在，确定性返回 `CRITICAL` / exit 2；真实数据库检查前后 SHA-256 不变。
- 新增生产运行手册，固定更新顺序、状态处置和禁止破坏现场要求。T002–T020 共 17 套测试脚本全量通过。
- 效率指标：Codex 单闭环完成；返工 0；人工 Gate 0；DeepSeek 调用 0。
