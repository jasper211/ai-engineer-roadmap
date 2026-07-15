# 04 · 定义 Agent Define Agent

> 对应方法论：`agents/__init__.py` / `agent.yaml` / `agent.py` —— 定义 Agent 的角色、目标、工具和执行逻辑。

## 本文件夹内容（`agents/` 包）

- `agent.py` —— 入口：Think-Act-Observe 主循环（原 PTA-RUN_主编排器.py 迁移）
- `agent.yaml` —— Agent 身份/能力/安全约束声明（供任何加载本项目的 AI 终端先读一遍）
- `__init__.py`

`agent.py` 是唯一的运行入口：`python3 04_定义Agent_Define_Agent/agents/agent.py --status`。
