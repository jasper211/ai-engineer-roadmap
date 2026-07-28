# VNW · 价值节点驱动工作流 Agent

当前版本 v0.2.0 实现最小闭环：清单内容变更检测 → 信号提取 → 状态与产物落入专属工作区。已同时兼容旧标准化 v2.0 与当前权威 V3.44 表结构。

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --status
python3 04_定义Agent_Define_Agent/agents/agent.py --watch-dir /path/to/value-node-list --domain PAY
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

默认不会修改被监控目录。首次发现文件会处理；内容未变化会跳过；`--force` 可强制重跑；`--domain ALL` 处理全域。

Phase1 已验证的 `extract_signals.py` 已迁入 VNW，并补上新旧 Sheet 名、标题行和熔断字段兼容。每个源文件指纹使用独立输出目录，历史产物不会被新版覆盖。后续批次再迁移基线合并、规则空白生成与一致性校验。

## 统一前端与数据路径

- 正式前端：`10_部署与运行_Deploy_and_Run/frontend/`
- VNW 权威数据底座：`07_接入记忆_Integrate_Memory/data_foundation/`
- 数据同步技能：`06_开发技能_Develop_Skills/skills/sync_data_foundation.py`
- 规则识别方法论参考：`03_规划项目结构_Plan_Project_Structure/references/`

原独立目录“规则前端设计”已合并进 VNW，不再作为运行入口。

## 数据底座 → 前端展示

`06_开发技能_Develop_Skills/skills/sync_data_foundation.py` 是目前唯一真正处理业务数据的脚本：一键全量重建各数据表，写入两处物理数据底座副本，并额外导出 JSON 到前端 `10_部署与运行_Deploy_and_Run/frontend/public/data/`。

前端（React+Vite+TS）读取同步技能导出的 JSON。数据更新流程固定为：源头更新 → 重跑 `sync_data_foundation.py` → 前端本地 `npm run dev` 立即生效；线上发布仍需单独执行部署动作，不由数据同步脚本自动触发。

**权威数据源分级（2026-07-26 拍板，重要）**：公司数据仓库（PostgreSQL，`process_analytics` schema）是标准化的权威数据源，跟 01-05 层文件材料（本项目/OB 知识库背后的原始素材）冲突时以数据仓库为准；数据仓库没有的字段/表，才用文件材料补充。连接参数在本地未提交文件 `06_开发技能_Develop_Skills/skills/db_config_local.py` 里，不进版本库。T1/T12/T20/T25/T26 及新增 T29/T30 已切换为数据仓库权威源，详见 [执行记录.md](./执行记录.md) 2026-07-26 各条记录。
