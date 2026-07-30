# HKIA · 香港保监局（IA）行业数据自动化分析 Agent

> 状态：测试中。SOP 第4步（开发）+第5步（集成测试）已完成——13期端到端跑通，8项集成测试全过，待 Mark/Jasper 确认归档（SOP第6步）。下面的命令现在可以直接跑。

## 这是什么

解析香港保险业监管局（IA）**长期业务**季度保费统计（2023Q1~2026Q1，共13期），标准化为长表格式，写入本地存储。数据来源是 Jasper **人工下载**的 13 份官网原始 Excel（放在 `07_接入记忆_Integrate_Memory/raw_data/`），demo 从解析本地文件开始，不做自动抓取——一般业务因官网 2024Q3 起已断更（无结构化数据可抓），本次不做；自动化抓取和一般业务处理都留到下一版本。

不做增量抓取、不做定时调度、不做分析层摘要、不做前端展示、不做云端部署——这些是 demo 验证通过之后的下一版本目标。详见 [需求定义.md](01_初始化项目_Initialize_Project/需求定义.md)。

## 目录结构（01-11 方法论）

按 [Agent 搭建 SOP v1.2](../../05_Agent库/草稿/Agent搭建SOP_v1.2.md) 的 01-11 编号骨架搭建，与 05_Agent库 下的 VNW/PTA/AIT 同构，但物理上独立存放在 `FDE项目/` 下（FDE 角色承接的客户/业务需求项目，不与个人能力整改项目的 Agent 资产库混放）。

```
HKIA/
├── 01_初始化项目_Initialize_Project/       需求定义.md
├── 02_配置项目_Configure_Project/          settings.json（运行期配置）
├── 03_规划项目结构_Plan_Project_Structure/  流程设计.md
├── 04_定义Agent_Define_Agent/
│   └── agents/agent.py + agent.yaml       主入口 + Agent身份声明
├── 05_集成工具_Integrate_Tools/            （本版本暂不需要，browser_fetcher留到下一版本自动化抓取时再开发）
├── 06_开发技能_Develop_Skills/
│   └── skills/report_discovery.py         本地文件发现+完整性校验
│   └── skills/excel_parser.py             .xls/.xlsx双引擎解析
│   └── skills/normalizer.py               标准化+YTD标注
├── 07_接入记忆_Integrate_Memory/
│   └── raw_data/                          人工放置的13份原始Excel（见该目录README）
│   └── memory/workspace.py                本地SQLite读写 + 专属工作区隔离
├── 08_设计提示词_Design_Prompts/           （本版本demo暂无LLM调用，留空）
├── 09_测试与调试_Test_and_Debug/
│   └── tests/test_integration.py
│   └── tests/probe_download_reliability.py （下一版本自动化抓取验证用，本demo不需要跑）
├── 10_部署与运行_Deploy_and_Run/           （demo阶段不做调度上线，留空）
└── 11_监控与优化_Monitor_and_Optimize/     （demo阶段不做，留空）
```

## 快速开始

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --run-demo
python3 04_定义Agent_Define_Agent/agents/agent.py --status
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

`--run-demo` 会清空重建本地SQLite（`07_接入记忆_Integrate_Memory/data/hkia.db`），一次性解析13份文件写入；`--status`查看当前库里有哪些期数、多少条记录。

## 关联文档

- [需求定义.md](01_初始化项目_Initialize_Project/需求定义.md) — 含官网真实实测发现（文件命名不统一、YTD累计口径、一般业务断更但长期业务未断更的纠正、Cloudflare防护）
- [流程设计.md](03_规划项目结构_Plan_Project_Structure/流程设计.md) — L3-HKIA-01~03 端到端流程，含4种表格结构变体的真实核实结果
- [执行记录.md](执行记录.md) — 端到端运行结果 + 6个真实踩坑记录 + 已知限制
- [raw_data/README.md](07_接入记忆_Integrate_Memory/raw_data/README.md) — 13份原始文件的期待清单
