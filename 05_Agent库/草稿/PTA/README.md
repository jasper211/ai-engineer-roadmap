# PTA · 项目任务协同 Agent

v2.18.0 —— 目录按《Agent 项目搭建全流程》11 步方法论重排为 01-12 编号+中英文
顶层文件夹。这是本项目第二次结构迁移：v2.0.0 先从 5 个独立脚本
（PTA-S01~S05）+ 一个主编排器（PTA-RUN）的扁平结构，迁移为
`agents/skills/tools/memory/prompts/tests` 六个职责模块；v2.1.0 在此基础上
给这六个模块套上编号外壳，**这套 01-11 结构是以后任何 Agent 搭建都要遵循的
标准模板，不只是 PTA 自己的一次性调整**；v2.3.0 新增 `--daily-scan` 每日
主动巡检能力，PTA 从纯粹的"被动执行引擎"升级为"主动感知 + 人工确认 + 执行"
的闭环；v2.17.0 将第12步任务看板升级为“今日指挥中心 + 候选任务决策抽屉”；
v2.18.0 接入执行计划生成、风险标注、dry-run 和批准记录，真实执行仍需二次授权。

历史版本 README（v1.x，扁平结构时期）保留在
[`_retired_flat_structure/README_v1.md`](_retired_flat_structure/README_v1.md)。

## 这是什么

**被动执行**：理解一句自然语言指令 → 拆解成可执行步骤 → 实际调度执行 →
追踪进度 → 归档复盘沉淀经验；跨会话记得"上次做到哪、下一步是什么"。适用于
任何项目，不局限于本项目自己的任务（把目标项目的 `pta_tasks.json` 传给
`--project-root` 即可）。

**主动感知**（v2.3.0 新增）：`--daily-scan` 每天检测目标项目的文件变化，
分析变化之间的逻辑关系，判断哪些跟你有关，生成一份简报——**但不会自动执行**，
只是把建议任务写进目标项目的 `pta_tasks.json`，你确认执行某条时，走的还是
上面"被动执行"完全不变的那条路径。见下方"每日巡检"一节。

## 目录结构（01-11 方法论）

编号只是给人看的顺序标识——Python 的 import 语句不能以数字开头，所以
agents/skills/tools/memory 这四个需要被当作包 import 的目录，各自嵌套在对应
编号文件夹里面，包名本身（agents/skills/tools/memory）没有变，只是外面多包了
一层编号目录；每个编号文件夹里都有一份 README.md 说明这一步的方法论定位。

```
PTA/
├── 01_初始化项目_Initialize_Project/       初始化：项目缘起，需求定义
│   └── 需求定义.md
├── 02_配置项目_Configure_Project/          全局配置：模型/密钥/元数据/规范
│   ├── settings.json      运行期配置（原 config.json）
│   ├── .env.example
│   └── .gitignore
├── 03_规划项目结构_Plan_Project_Structure/  结构规划：模块划分依据
│   └── 流程设计.md
├── 04_定义Agent_Define_Agent/              Agent 定义：角色/目标/执行逻辑
│   └── agents/
│       ├── agent.py      入口：Think-Act-Observe 主循环（原 PTA-RUN）
│       ├── agent.yaml     Agent 身份/能力/安全约束声明
│       └── __init__.py
├── 05_集成工具_Integrate_Tools/            工具集成：可复用的具体执行器
│   ├── tools/
│   │   ├── shell_exec.py     bash/python/browser-use 执行
│   │   ├── git_ops.py         git 操作（唯一有真实 push 能力的地方）
│   │   ├── task_knowledge.py   任务知识库加载（原 pta_common.py）+ 安全 merge 建议任务
│   │   ├── file_diff.py         文件快照/增量 diff（从 PTA-SCAN 抽取的通用原语）
│   │   └── llm_client.py         DeepSeek 调用封装（从 PTA-DISCOVER 抽取，两边共用）
│   └── pta_tasks_default.json  本项目内置任务知识库（兜底）
├── 06_开发技能_Develop_Skills/             技能开发：组合工具完成复杂操作
│   └── skills/           六个可复用技能（原 S01-S05 改为可直接 import 的类 + daily_sensing）
│       ├── intent_parsing.py       意图解析（原 S01）
│       ├── execution_planning.py   执行编排（原 S02）
│       ├── progress_tracking.py    进度追踪（原 S03）
│       ├── doc_sync.py              文档同步（原 S04，去掉了死代码）
│       ├── archive_review.py        归档复盘（原 S05，唯一的执行记录生成者）
│       └── daily_sensing.py          每日主动巡检（v2.3.0 新增，DailySensor）
├── 07_接入记忆_Integrate_Memory/           记忆接入：会话/历史持久化
│   └── memory/
│       └── workspace.py     专属工作区隔离 + state.json/daily_sensing_state.json 持久化
├── 08_设计提示词_Design_Prompts/           提示词设计：系统提示词+指令示例
│   └── prompts/
│       ├── system.md                  Agent 系统提示词
│       ├── task_examples.md            指令→解析结果对照表 + CLI 示例
│       └── daily_sensing_system.md      每日巡检的 LLM 系统提示词（含安全边界）
├── 09_测试与调试_Test_and_Debug/           测试与调试：集成测试
│   └── tests/
│       └── test_integration.py   集成测试（36 项，含每日巡检/规则扫描/文档发现/
│                                   项目智能分析/Rw专项校准等相关测试）
├── 10_部署与运行_Deploy_and_Run/           部署与运行：一键启动 + 定时任务
│   ├── quick_start.sh
│   ├── com.jasper.pta-daily-scan.plist    每日巡检定时任务模板（占位符，需手动安装）
│   └── INSTALL_DAILY_SCAN.md               手动安装说明
├── 11_监控与优化_Monitor_and_Optimize/     监控与优化：PTA 自我监控 + 分析/巡检类扩展脚本
│   ├── PTA-MONITOR_自我监控.py            监控 PTA 自己被调用得怎么样（成功率/澄清率等）
│   └── PTA-DASH/DISCOVER/EXT/INTEL/INTEL-RW/SCAN（"帮你分析别的项目"，未纳入 skills/tools 迁移，见下）
├── 12_任务看板_Task_Dashboard/             本地任务驾驶舱：人工决策、项目态势与运行监控
└── _retired_flat_structure/   旧版扁平脚本（S01-S05/RUN/config.json 等），保留供追溯，不再是入口
```

顶层还留了 `README.md`（本文件）、`AI_PLATFORM_GUIDE.md`、`CROSS_AI_TEST.md`——
这三份是跨阶段的元文档/使用指南，不属于某一个编号步骤，所以没有下沉到编号
文件夹里。

## 快速开始

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --status
python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04"              # dry-run
python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04" --execute     # 真实执行（不含 git push）

# 或者直接用封装好的一键脚本：
bash 10_部署与运行_Deploy_and_Run/quick_start.sh
```

更多示例见 [`08_设计提示词_Design_Prompts/prompts/task_examples.md`](08_设计提示词_Design_Prompts/prompts/task_examples.md)，
跨 AI 终端调用方式见 [`AI_PLATFORM_GUIDE.md`](AI_PLATFORM_GUIDE.md)。

## 每日巡检（v2.3.0 新增）

```bash
export DEEPSEEK_API_KEY=sk-xxx

# 检测目标项目自上次巡检以来的文件变化，分析关系，产出建议任务简报
python3 04_定义Agent_Define_Agent/agents/agent.py --daily-scan --project-root /path/to/project

# 简报里每条建议任务都带一个 RPT-YYYYMMDD-NN 格式的 ID，确认执行走的是
# 完全不变的正常执行路径：
python3 04_定义Agent_Define_Agent/agents/agent.py "执行 RPT-20260715-01" --project-root /path/to/project --execute
```

没有变化时零 API 调用；有变化但你没确认的建议任务，下次巡检会重新出现
（标记"仍待确认"，不会重复铸造新 ID）。要每天自动跑，见
[`10_部署与运行_Deploy_and_Run/INSTALL_DAILY_SCAN.md`](10_部署与运行_Deploy_and_Run/INSTALL_DAILY_SCAN.md)
手动安装 launchd 定时任务（不会自动安装）。

## Pipeline 健康检测（v2.9.0 新增）

依据《Pipeline差距矩阵_检测机制设计_v1.0.md》规格：跟 `--daily-scan` 平级、
不是它的子功能，全部是确定性检查（文件存在性/测试 exit code/字段读取/mtime），
不调用 LLM，不做主观判断——只把"矩阵声明"和"实际状态"的差异摆出来，人来决定
要不要改矩阵。

```bash
# 检测项定义读取优先级同 pta_tasks.json：--checks-path 显式路径 >
# project_root 下的 05_Agent库/草稿/_pipeline_health/checks.json > 内置空白兜底
python3 04_定义Agent_Define_Agent/agents/agent.py --pipeline-check --dry-run   # 首次必须先 dry-run 核对格式
python3 04_定义Agent_Define_Agent/agents/agent.py --pipeline-check --notify   # 正式运行，发现drift才推送企业微信
```

报告落在 `{project_root}/05_Agent库/草稿/_pipeline_health/检测记录_YYYY-MM-DD.md`，
基线存于同目录 `.baseline.json`。要每周自动跑，见
[`10_部署与运行_Deploy_and_Run/com.jasper.pta-pipeline-check.plist`](10_部署与运行_Deploy_and_Run/com.jasper.pta-pipeline-check.plist)
（跟 daily-scan 的每日 plist 完全独立，每周五触发，手动安装）。

## 安全约束（历次迁移都不变）

- `doc_sync`（真实 git push）必须显式 `--sync --execute -m "..."` 三者齐全才触发。
- `git_ops.sync_git` 绝不 `git add .`，只 add 明确来源的文件。
- PTA 自己的状态/运行产物写入目标项目的专属工作区，物理隔离于目标项目本身
  和 PTA 源码所在的共享仓库（见 `07_接入记忆_Integrate_Memory/memory/workspace.py`）。
- `--daily-scan` 的 LLM 输出只能是建议任务的名称/理由/优先级，绝不能是可执行的
  `steps`/`command`——避免被篡改的文档诱导模型生成危险命令又被 `--execute`
  无脑跑掉；所有建议任务的 `steps` 都是本地合成的人工核对占位步骤。
- `com.jasper.pta-daily-scan.plist` 模板里的 API Key 是占位符，真实密钥只填在
  `~/Library/LaunchAgents/` 里手动安装的副本里，绝不提交进这个 git 仓库。

## v2.0.0 迁移解决的结构性问题

旧版 PTA-RUN 用 5 次独立 subprocess 调用串联 S01→S02→S03→S05，每一跳之间靠临时
JSON 文件中转，`--project-root` 之类的参数要在每一跳手动重新拼进命令行——曾经因为
转发到 S05 那一跳漏拼了 `--project-root`，导致执行记录写进了错误的项目目录（见
`05_Agent库/草稿/Agent验证标准清单_v1.0.md` 的案例记录）。新结构里所有技能都是
同进程内的 Python 对象调用，`project_root` 只 resolve 一次、作为同一个变量传给
下面每个技能的构造函数，不存在"转发时漏传某一跳"这类风险。

## 扩展脚本迁移

`PTA-DASH`/`EXT`（批1）、`PTA-DISCOVER`/`SCAN`（批2）、`PTA-INTEL`/`INTEL-RW`
（批3）三批已全部迁移进 skills/tools，原脚本移入 `_retired_flat_structure/`，
详见 `11_监控与优化_Monitor_and_Optimize/README.md` 的迁移进度记录（含每批
迁移时顺带修复的真实 bug）。仅 `PTA-MONITOR_自我监控.py`（监控 PTA 自己，
不是分析别的项目）仍以独立脚本形式保留在 `11_监控与优化_Monitor_and_Optimize/`。
