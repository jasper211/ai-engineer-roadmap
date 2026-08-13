# PTA · Project Task Agent

PTA 是一套面向个人和小团队的本地项目任务协同 Agent，核心目标是把“自然语言任务、文件变化、执行跟踪、任务驾驶舱”整合到同一套工作流里。

它适合这样的使用场景：

- 你希望把一句自然语言指令拆成可执行步骤
- 你希望跨会话保留任务状态和执行记录
- 你希望定期扫描项目文件变化并生成候选任务
- 你希望给团队一个本地可部署的任务驾驶舱

## 核心能力

- `Think-Act-Observe` 主循环：意图解析、执行编排、进度追踪、归档复盘
- `--daily-scan`：扫描项目文件变化，生成候选任务
- `--pipeline-check`：对关键文件、测试和产物做确定性检查
- 本地任务驾驶舱：任务查看、执行准备、Agent 状态监控、巡检项目管理
- 工作区隔离：PTA 自己的状态、报告、执行记录写入独立工作区，而不是写回业务项目目录

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 04_定义Agent_Define_Agent/agents/agent.py --status
```

也可以直接：

```bash
bash 10_部署与运行_Deploy_and_Run/quick_start.sh
```

## 任务驾驶舱

后端：

```bash
python3 12_任务看板_Task_Dashboard/api/server.py --port 8787
```

前端开发模式：

```bash
cd 12_任务看板_Task_Dashboard/web
npm install
npm run dev
```

## 团队部署前需要改的配置

- `02_配置项目_Configure_Project/.env.example`
- `02_配置项目_Configure_Project/daily_scan_projects.json`
- `02_配置项目_Configure_Project/agent_registry.json`
- `02_配置项目_Configure_Project/wecom_config.example.json`

每位同事都应该维护自己的项目路径、工作区路径和通知配置。

## 开源交接

如果要导出一份适合同事直接使用的干净版本，使用：

```bash
python3 10_部署与运行_Deploy_and_Run/export_open_source_package.py
```

它会自动移除本机缓存、日志、私有路径映射和敏感配置，并生成可分发目录与 zip 包。
