# 03 · 规划项目结构 Plan Project Structure

> 对应方法论：按职责划分模块（`agents/skills/tools/memory/prompts/tests`），保持高内聚低耦合，便于扩展、测试与团队协作。

## 目录方法论（PTA 及以后所有 Agent 都应遵循）

```
my-agent/
├── 01_初始化项目_Initialize_Project/
├── 02_配置项目_Configure_Project/
├── 03_规划项目结构_Plan_Project_Structure/   ← 本文件夹
├── 04_定义Agent_Define_Agent/          agents/    Agent 角色/目标/执行逻辑
├── 05_集成工具_Integrate_Tools/         tools/     可复用的具体执行器
├── 06_开发技能_Develop_Skills/          skills/    组合工具完成的任务能力
├── 07_接入记忆_Integrate_Memory/        memory/    会话/历史持久化
├── 08_设计提示词_Design_Prompts/        prompts/   系统提示词与任务模板
├── 09_测试与调试_Test_and_Debug/        tests/     单元/集成测试
├── 10_部署与运行_Deploy_and_Run/                    打包/启动脚本
└── 11_监控与优化_Monitor_and_Optimize/               运行监控/评估/分析工具
```

**技术约束（务必记住）**：Python 的 `import` 语句不能以数字开头，所以
`agents/skills/tools/memory` 这四个需要被当包 import 的目录，各自嵌套
在对应编号文件夹**里面**（例如 `04_定义Agent_Define_Agent/agents/`），
包名本身不带编号前缀；编号只是给人看的顺序标识，不进入 import 路径。
`prompts/`、`tests/` 同样嵌套，是为了保持结构一致，虽然它们不是被 import
的 Python 包。

调用方（如 `agents/agent.py`）需要把每个编号文件夹加进 `sys.path`（而不是
项目根目录本身），才能让 `from skills.xxx import` 这类语句解析成功——
具体写法见 `04_定义Agent_Define_Agent/agents/agent.py` 开头的 `sys.path.insert` 代码。

## 本文件夹内容

- `流程设计.md` —— PTA 最初的流程/子 Agent 交互设计文档
