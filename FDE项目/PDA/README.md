# PDA · 业绩数据多维分析 Agent（围绕牌照端 issuing_entity）

> 状态：测试中。SOP 第4步（开发）+第5步（集成测试）已完成——真实底表跑通，190项集成测试全过，修复2个真实bug（日期类型解析、future_dated计数），待 Jasper 确认归档（SOP第6步）。S1-S9九张专题视角表已全部反推完成。**PPT生成路线已于v0.15.0停止投入**（已实现第1/8/9/10/11页并用真实数据核验，代码保留但不再继续第2-7页）——起因是Jasper拿到业务真实在发的W37/W38周报后，发现①真实生产模板已演化到12页（我们复刻的是过时的11页模板）；②真实报表里"全流程转化漏斗"的"递交"阶段一周之内从563.2M骤降为0，证实当前生产脚本（非本Agent产出）本身有真实bug。据此判断"死磕复刻PPT"性价比低，改走**前端直接展示**替代PPT：新增`multiview_dashboard.py`，多视角tab切换单页应用。v0.16.0：S2业务端/S3执行管理端/S4产品端/同行业绩/银行业绩/代理人业务/KA业务共7个新增视角全部实现（加上此前的S1总览，8个视角全部完成）。**v0.17.0：对着业务真实在发的12页周报逐页比对后补齐3类缺口——①（P0）同行业绩/银行业绩/代理人业务/KA业务四个视角新增"本周快报"（当周值+环比上周，跟S3同一套`weekly_snapshot`模式，全站`cur_week`统一=W29）；②（P2）新增第9个视角"永明业绩"（对应PDF第3页Sun Life），KPI卡片用S1-A"永明业务目标"行(承保公司口径)、月度趋势用S2-C/D/E"永明经代"业务细分行(渠道口径，两者口径不同已在页面文案标注)、产品TOP10用S4-C全司TOP20榜单筛"保司=永明"（恰好前10名全部是永明产品）**。核实S9-H/I/J周度明细子表后确认：H=天领业务周度明细、I=成事家办周度明细、J=KA业务周度明细(ICLUB+合伙转介+IFA已合并口径)，代理人业务本周快报=H+I逐周相加、KA业务本周快报=J直接取用；已用真实数据核对"缺列=该周真实0贡献"（present-week-sum精确等于CSV自带"合计"列），缺列按0处理不算数据丢失。全部9个视角均用真实数据独立核验+built-in browser DOM核对确认渲染正确。

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
├── 05_集成工具_Integrate_Tools/
│   └── tools/fact_target_sync.py          只读同步服务器fact_target目标APE数据
├── 06_开发技能_Develop_Skills/
│   └── skills/data_loader.py              底表读取+完整性校验
│   └── skills/cleaner.py                  清洗标准化（含日期类型修正）
│   └── skills/aggregator.py               围绕issuing_entity的多维聚合
│   └── skills/dashboard_generator.py      HTML看板生成
│   └── skills/report_enricher.py          S8明细底表13个衍生字段
│   └── skills/s1_dashboard.py             S1总览仪表盘A-H八个板块
│   └── skills/s2_business_view.py         S2业务端视角全部20个子板块
│   └── skills/s3_execution_view.py        S3执行管理端全部20个子板块
│   └── skills/s4_product_view.py          S4产品端视角全部5个板块
│   └── skills/s5_finance_view.py          S5财务端视角全部8个板块
│   └── skills/s6_market_cross_view.py     S6市场与交叉视角全部12张子表
│   └── skills/s7_compliance_view.py       S7合规端视角全部6个板块
│   └── skills/s9_agent_ka_view.py         S9代理人与KA业务全部10个顶层板块
│   └── skills/db_config_local.py          数据库连接参数（本地文件，不进版本库）
│   └── skills/ppt_data_loader.py          PPT生成阶段：新版S1-S9 CSV加载（一板块一文件）
│   └── skills/ppt_chart_patch.py          PPT生成阶段：chart XML直接patch（绕开python-pptx限制）
│   └── skills/ppt_helpers.py              PPT生成阶段：结构化定位（按标题/表头/类别找元素）+ 段落级替换 + 列克隆
│   └── skills/ppt_monthly_bucket.py       PPT生成阶段：S3周度数据按%U周三规则聚合成月度
│   └── skills/ppt_config.py               PPT生成阶段：集中配置（8项业务细分顺序等口径常量）
│   └── skills/ppt_generator.py            PPT生成阶段（已停止投入）：build_slide1/8/9/10/11()已实现，slide2-7不再继续
│   └── skills/multiview_dashboard.py      前端阶段（PPT的替代方向）：多视角tab切换，S1总览/S2业务端/S3执行管理端/S4产品端/同行业绩/银行业绩/代理人业务/KA业务/永明业绩共9个视角全部实现（v0.17.0新增4个视角"本周快报"+永明业绩视角）
├── 07_接入记忆_Integrate_Memory/
│   └── raw_data/                          Jasper放置的原始底表Excel+业绩分析报表+PPT流水线参考代码
│   └── memory/workspace.py                本地缓存+PDA专属工作区隔离
│   └── data/                              清洗后数据缓存 + 看板HTML + S8/S1衍生数据CSV + fact_target快照
├── 08_设计提示词_Design_Prompts/           （本版本无LLM调用，留空）
├── 09_测试与调试_Test_and_Debug/
│   └── tests/test_integration.py          真实数据集成测试
├── 10_部署与运行_Deploy_and_Run/           （demo阶段不做调度上线，留空）
└── 11_监控与优化_Monitor_and_Optimize/     （demo阶段不做，留空）
```

## 快速开始

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --run
python3 04_定义Agent_Define_Agent/agents/agent.py --enrich
python3 04_定义Agent_Define_Agent/agents/agent.py --sync-targets
python3 04_定义Agent_Define_Agent/agents/agent.py --s1
python3 04_定义Agent_Define_Agent/agents/agent.py --s2
python3 04_定义Agent_Define_Agent/agents/agent.py --s3
python3 04_定义Agent_Define_Agent/agents/agent.py --s4
python3 04_定义Agent_Define_Agent/agents/agent.py --s5
python3 04_定义Agent_Define_Agent/agents/agent.py --s6
python3 04_定义Agent_Define_Agent/agents/agent.py --s7
python3 04_定义Agent_Define_Agent/agents/agent.py --s9
python3 04_定义Agent_Define_Agent/agents/agent.py --ppt
python3 04_定义Agent_Define_Agent/agents/agent.py --frontend
python3 04_定义Agent_Define_Agent/agents/agent.py --status
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

`--run` 读取 `raw_data/` 下的底表 Excel，清洗、聚合，在 `07_接入记忆_Integrate_Memory/data/` 生成 HTML 看板；`--enrich` 清洗后加上 S8 明细底表的13个衍生字段，存成CSV；`--sync-targets` 只读同步服务器 fact_target 目标APE数据（需要 `skills/db_config_local.py`，本地文件不进版本库）；`--s1` 复刻S1_总览仪表盘A-H八个板块，存成CSV；`--s2` 复刻S2_业务端视角全部20个子板块（含S/T的partner_code维度），存成CSV；`--s3` 复刻S3_执行管理端全部20个子板块（周度趋势+签批时效分析+未批核待签分布+同行/银行周度趋势），存成CSV；`--s4` 复刻S4_产品端视角全部5个板块，存成CSV；`--s5` 复刻S5_财务端视角全部8个板块（规模分档+大额保单TOP20），存成CSV；`--s6` 复刻S6_市场与交叉视角全部12张子表，存成CSV；`--s7` 复刻S7_合规端视角全部6个板块（牌照合规概览+牌照×业务细分+签批时效预警+TR人效），存成CSV；`--s9` 复刻S9_代理人与KA业务全部10个顶层板块（业务细分汇总+KA业绩分析+月度/周度明细），存成CSV；`--ppt` 从`raw_data/业绩报表PPT/template.pptx`+S1-S9 CSV生成周业绩PPT（已停止投入，实现到第1/8/9/10/11页为止，见 [PPT生成_旧流水线映射与新架构设计_v0.1.md](03_规划项目结构_Plan_Project_Structure/PPT生成_旧流水线映射与新架构设计_v0.1.md)）；`--frontend` 从S1-S9 CSV生成多视角前端HTML（代替PPT的新方向，S1总览/S2业务端/S3执行管理端/S4产品端/同行业绩/银行业绩/代理人业务/KA业务/永明业绩共9个视角全部实现，双击`业绩数据分析前端.html`即可打开）；`--status` 查看上次运行的记录数/future_dated数等摘要。

## 关联文档

- [需求定义.md](01_初始化项目_Initialize_Project/需求定义.md) — 含真实底表核实发现（日期类型bug、future_dated真实计数）
- [S8衍生字段_反推标准_v0.1.md](01_初始化项目_Initialize_Project/S8衍生字段_反推标准_v0.1.md) — 从《业绩分析报表》反推还原S8明细底表13个衍生字段规则，12个已100%核验
- [S1_总览仪表盘_反推标准_v0.1.md](01_初始化项目_Initialize_Project/S1_总览仪表盘_反推标准_v0.1.md) — 反推还原S1_总览仪表盘A-H全部8个板块，全部100%核验
- [S2_业务端视角_反推标准_v0.1.md](01_初始化项目_Initialize_Project/S2_业务端视角_反推标准_v0.1.md) — 反推还原S2_业务端视角全部20个子板块，含S/T的partner_code维度
- [S3_执行管理端_反推标准_v0.1.md](01_初始化项目_Initialize_Project/S3_执行管理端_反推标准_v0.1.md) — 反推还原S3_执行管理端全部20个子板块，含"周"定义的破解过程
- [S4_产品端视角_反推标准_v0.1.md](01_初始化项目_Initialize_Project/S4_产品端视角_反推标准_v0.1.md) — 反推还原S4_产品端视角全部5个板块，全部100%核验
- [S5_财务端视角_反推标准_v0.1.md](01_初始化项目_Initialize_Project/S5_财务端视角_反推标准_v0.1.md) — 反推还原S5_财务端视角全部8个板块
- [S6_市场与交叉视角_反推标准_v0.1.md](01_初始化项目_Initialize_Project/S6_市场与交叉视角_反推标准_v0.1.md) — 反推还原S6_市场与交叉视角全部12张子表
- [S7_合规端视角_反推标准_v0.1.md](01_初始化项目_Initialize_Project/S7_合规端视角_反推标准_v0.1.md) — 反推还原S7_合规端视角全部6个板块
- [S9_代理人与KA业务_反推标准_v0.1.md](01_初始化项目_Initialize_Project/S9_代理人与KA业务_反推标准_v0.1.md) — 反推还原S9_代理人与KA业务全部10个顶层板块，最后1张专题视角表
- [目标APE数据源_fact_target_核实.md](01_初始化项目_Initialize_Project/目标APE数据源_fact_target_核实.md) — 服务器fact_target表结构+编码映射核实记录
- [流程设计.md](03_规划项目结构_Plan_Project_Structure/流程设计.md) — L3-PDA-01~13 端到端流程 + 清洗/衍生字段规则明细表
- [执行记录.md](执行记录.md) — 端到端运行结果 + 踩坑记录
