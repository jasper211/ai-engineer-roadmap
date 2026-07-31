# PDA · 业绩数据多维分析 Agent（围绕牌照端 issuing_entity）

> 状态：测试中。SOP 第4步（开发）+第5步（集成测试）已完成——真实底表跑通，24项集成测试全过，修复2个真实bug（日期类型解析、future_dated计数），待 Jasper 确认归档（SOP第6步）。

## 这是什么

读取 Jasper 人工放置的业绩数据底表 Excel，清洗标准化后围绕牌照端（issuing_entity）做 7 类多维聚合，生成可交互 HTML 看板。是《业绩数据分析项目启动方案》阶段一的 Agent 化 + 调整优化版本——真实核实原始底表后发现阶段一原型有 2 个未被发现的真实 bug（日期字段类型不统一、future_dated 计数错误），本版本在清洗流程里直接修复。详见 [需求定义.md](01_初始化项目_Initialize_Project/需求定义.md) 第十一节。

不做 CRM/保司系统实时同步、不做多用户权限、不做知识库问答——这些是启动方案的阶段二/三，前提条件（API 是否开放等）尚未确认，见需求定义 4.2 节。

## 目录结构（01-11 方法论）

按 [Agent 搭建 SOP v1.2](../../05_Agent库/草稿/Agent搭建SOP_v1.2.md) 的 01-11 编号骨架搭建，与 05_Agent库 下的 VNW/PTA/AIT 同构，物理独立存放在 `FDE项目/` 下。

```
PDA/
├── 01_初始化项目_Initialize_Project/       需求定义.md（含真实底表核实发现）
├── 02_配置项目_Configure_Project/          settings.json
├── 03_规划项目结构_Plan_Project_Structure/  流程设计.md
├── 04_定义Agent_Define_Agent/
│   └── agents/agent.py + agent.yaml       主入口 + Agent身份声明
├── 05_集成工具_Integrate_Tools/            （本版本暂不需要）
├── 06_开发技能_Develop_Skills/
│   └── skills/data_loader.py              底表读取+完整性校验
│   └── skills/cleaner.py                  清洗标准化（含日期类型修正）
│   └── skills/aggregator.py               围绕issuing_entity的多维聚合
│   └── skills/dashboard_generator.py      HTML看板生成
├── 07_接入记忆_Integrate_Memory/
│   └── raw_data/                          Jasper放置的原始底表Excel
│   └── memory/workspace.py                本地缓存+PDA专属工作区隔离
│   └── data/                              清洗后数据缓存 + 生成的看板HTML
├── 08_设计提示词_Design_Prompts/           （本版本无LLM调用，留空）
├── 09_测试与调试_Test_and_Debug/
│   └── tests/test_integration.py          真实数据集成测试
├── 10_部署与运行_Deploy_and_Run/           （demo阶段不做调度上线，留空）
└── 11_监控与优化_Monitor_and_Optimize/     （demo阶段不做，留空）
```

## 快速开始

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --run
python3 04_定义Agent_Define_Agent/agents/agent.py --status
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

`--run` 读取 `raw_data/` 下的底表 Excel，清洗、聚合，在 `07_接入记忆_Integrate_Memory/data/` 生成 HTML 看板；`--status` 查看上次运行的记录数/future_dated数等摘要。

## 关联文档

- [需求定义.md](01_初始化项目_Initialize_Project/需求定义.md) — 含真实底表核实发现（日期类型bug、future_dated真实计数）
- [流程设计.md](03_规划项目结构_Plan_Project_Structure/流程设计.md) — L3-PDA-01~04 端到端流程 + 清洗规则明细表
- [执行记录.md](执行记录.md) — 端到端运行结果 + 踩坑记录
