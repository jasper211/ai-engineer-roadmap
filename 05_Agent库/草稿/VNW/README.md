# VNW · 价值节点驱动工作流 Agent

当前版本 v0.2.0 实现最小闭环：清单内容变更检测 → 信号提取 → 状态与产物落入专属工作区。已同时兼容旧标准化 v2.0 与当前权威 V3.44 表结构。

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --status
python3 04_定义Agent_Define_Agent/agents/agent.py --watch-dir /path/to/value-node-list --domain PAY
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

默认不会修改被监控目录。首次发现文件会处理；内容未变化会跳过；`--force` 可强制重跑；`--domain ALL` 处理全域。

Phase1 已验证的 `extract_signals.py` 已迁入 VNW，并补上新旧 Sheet 名、标题行和熔断字段兼容。每个源文件指纹使用独立输出目录，历史产物不会被新版覆盖。后续批次再迁移基线合并、规则空白生成与一致性校验。

## 数据底座 → 前端展示

`06_开发技能_Develop_Skills/skills/sync_data_foundation.py` 是目前唯一真正处理业务数据的脚本：一键全量重建 01-04 层产出的 23 张数据表（A 类自动同步 + C 类人工维护 + T22 人工试点），写入两处物理数据底座副本，并额外导出 JSON 到前端 `app_v2/public/data/`。

前端（`规则前端设计/Agent_价值节点-规则分析前端/app_v2`，React+Vite+TS）以 A 类表为现状做展示，读的就是这份 JSON 导出。数据更新流程固定为：源文件变更 → 重跑 `sync_data_foundation.py` → 前端本地 `npm run dev` 立即生效，线上部署需另行手动 `vercel --prod`（不自动发布）。详见 [执行记录.md](./执行记录.md) 2026-07-25 各条记录。
