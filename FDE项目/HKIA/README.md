# HKIA · 香港保监局（IA）行业数据自动化分析 Agent

> 状态：草稿，SOP 第3步（配置编写）。`agents/agent.py` 尚未开发，下面的命令是第4步开发完成后的目标形态，现在还跑不了。

## 这是什么

抓取香港保险业监管局（IA）官网的一般/长期业务季度保费统计，标准化为长表格式，写入本地存储。demo 阶段只做 **2023Q1~2024Q2**——这是官网实测确认的唯一还有结构化 Excel 数据的窗口，2024Q3 起官网因风险为本资本制度（RBC）实施改为年度新闻稿+PDF附件，留作下一批单独处理。

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
├── 05_集成工具_Integrate_Tools/
│   └── tools/browser_fetcher.py           Playwright 封装（纯技术层）
├── 06_开发技能_Develop_Skills/
│   └── skills/report_discovery.py         报表发现+抓取
│   └── skills/excel_parser.py             一般/长期业务双引擎解析
│   └── skills/normalizer.py               标准化+YTD标注+中文翻译
├── 07_接入记忆_Integrate_Memory/
│   └── memory/workspace.py                本地SQLite读写 + 专属工作区隔离
├── 08_设计提示词_Design_Prompts/           （本版本demo暂无LLM调用，留空）
├── 09_测试与调试_Test_and_Debug/
│   └── tests/test_integration.py
├── 10_部署与运行_Deploy_and_Run/           （demo阶段不做调度上线，留空）
└── 11_监控与优化_Monitor_and_Optimize/     （demo阶段不做，留空）
```

## 快速开始（第4步开发完成后）

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --run-demo
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

## 关联文档

- [需求定义.md](01_初始化项目_Initialize_Project/需求定义.md) — 含官网真实实测发现（文件命名不统一、YTD累计口径、2024Q3断更、Cloudflare防护）
- [流程设计.md](03_规划项目结构_Plan_Project_Structure/流程设计.md) — L3-HKIA-01~04 端到端流程
