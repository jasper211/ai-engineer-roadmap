# PDA · 业绩数据多维分析 Agent（围绕牌照端 issuing_entity）

> 状态：测试中。SOP 第4步（开发）+第5步（集成测试）已完成——真实底表跑通，241项集成测试全过，修复多个真实bug（日期类型解析、future_dated计数、S2-S/T排序规则与月份范围、S4-A保司清单、S1-B融资占比算法），待 Jasper 确认归档（SOP第6步）。**v0.22.0（最新）：Mark标准报表Phase2，补齐第10-18页，`mark_standard_report.py`至此覆盖Mark原文18页标准报表全部页面（v0.20.0第1-9页+v0.22.0第10-18页）。第10页银行业绩/第11页代理人业务/第12页KA业务三个新视角复用`multiview_dashboard.py`的`build_bank_view()`/`build_agent_view()`/`build_ka_view()`，KA明细表直接渲染S9各子表原始CSV（已自带正确排序+"合计"行，不需要重新计算）；第13页永明产品保费TOP10+完整年期分布（population跟第3页同一组1171条签单记录，按保费而非APE排序，年期分布新增"年期缺失"/"文本年期"两档区分report_enricher.py`_term_bucket()`本身未细分的两种None情况）；**第14页"执行明细、来源说明与管理行动"是全新页面（无现成实现可复用）**——8线×4事件表的"递交"按Jasper指示留空"—"+页面显式标注数据源缺口说明（S3目前只有递交总量没有按业务线拆分的周度板块），不新增反推逻辑凑数据；数据与解释边界7项指标（已交付文件行数/缺批核日期/APE保费缺失/未来签单日/拒保/负时效/实体别名归一化）全部独立pandas重算，不是照抄Mark那次10-09批次跑出来的数字；管理行动建议套用Jasper给定的4条通用模板+角色占位符（业务管理负责人/数据负责人/渠道及运营负责人/业务与数据负责人），真实姓名留给业务侧指定。第15页同行完整渠道推荐人明确区分partner_code/referral_code/key_account三个字段各自独立分组。第16-18页Q/R/S周度热力矩阵完整表格复用S3-B/C/D同一数据源，独立重写成APE+件数同格的Mark单元格样式，窗口取"最近15周"（已核对确认Mark原始页面本身就只展示最近15周，不是本项目主动收窄）。新增22项集成测试断言（243+22=265项全部通过），built-in browser逐页截图+`get_page_text()`逐格比对数字100%一致，`--frontend`9视角前端+`--status`回归测试正常，详见执行记录.md v0.22.0。Mark标准报表18页全部完成。**v0.20.0：新增`mark_standard_report.py`——把业务方同事Mark基于同批数据做的18页独立标准报表（`raw_data/Mark标准报表_W40_20261009.pdf`）程序化复刻，本轮完成第1-9页，浅色打印页面视觉系统（`<section class="page">`配合`page-break-after:always`，浏览器"打印为PDF"即可导出真实多页PDF），跟`multiview_dashboard.py`深色tab系统是两套独立CSS、不共用`:root`变量。逐页核对p01.txt-p09.txt原文后发现并修正了4处Mark真实口径不同于现有build_*_view()实现的地方（不是简单复用能对上数字的）：第7页签批时效表+新增的"签批时效分档分布"模块排除了1条TAT<0异常值（分母1646而非1647，已用PDF渲染截图肉眼核对确认）；第6/8页KA排名改用S6全量三阶段口径（不是S2-I/K的TOP20截断）；第3页永明产品排名把SQ_rate缺失记录计入"未提供"档参与排名（不是像S4-B/C那样整体排除）；第9页同行月度分析改用自然日历月统计（不是周→月分桶算法，两者在部分月份有记录级别差异）。新增`agent.py --mark-report`命令，新增22项集成测试断言，全部独立pandas重算核对，详见执行记录.md v0.20.0。S1-S9九张专题视角表已全部反推完成。**v0.19.0（最新）：拿到业务方权威的raw→9-sheet报表生成脚本`generate_report.py`后逐项核对此前的反推规则（确认多数正确，发现并修正4处真实bug，详见下方"关联文档"及`执行记录.md` v0.19.0）；系统性核实并修复了`issuing_entity`字段的简繁体别名重复问题（怡泰/九富/众和恒富/富强天一/置富理财共5对同一家公司因写法不同被拆散统计，已在`cleaner.py`归一化，归一化前后总记录数/总APE/总保费三项大盘指标独立验证精确不变）；底表+ground truth同步换成2026-10-09批次数据（3993条有效记录），详见执行记录.md v0.19.0。** **PPT生成路线已于v0.15.0停止投入**（已实现第1/8/9/10/11页并用真实数据核验，代码保留但不再继续第2-7页）——起因是Jasper拿到业务真实在发的W37/W38周报后，发现①真实生产模板已演化到12页（我们复刻的是过时的11页模板）；②真实报表里"全流程转化漏斗"的"递交"阶段一周之内从563.2M骤降为0，证实当前生产脚本（非本Agent产出）本身有真实bug。据此判断"死磕复刻PPT"性价比低，改走**前端直接展示**替代PPT：新增`multiview_dashboard.py`，多视角tab切换单页应用。v0.16.0：S2业务端/S3执行管理端/S4产品端/同行业绩/银行业绩/代理人业务/KA业务共7个新增视角全部实现（加上此前的S1总览，8个视角全部完成）。v0.17.0：对着业务真实在发的12页周报逐页比对后补齐3类缺口——①（P0）同行业绩/银行业绩/代理人业务/KA业务四个视角新增"本周快报"（当周值+环比上周，跟S3同一套`weekly_snapshot`模式，全站`cur_week`统一=W29）；②（P2）新增第9个视角"永明业绩"（对应PDF第3页Sun Life），KPI卡片用S1-A"永明业务目标"行(承保公司口径)、月度趋势用S2-C/D/E"永明经代"业务细分行(渠道口径，两者口径不同已在页面文案标注)、产品TOP10用S4-C全司TOP20榜单筛"保司=永明"（恰好前10名全部是永明产品）。核实S9-H/I/J周度明细子表后确认：H=天领业务周度明细、I=成事家办周度明细、J=KA业务周度明细(ICLUB+合伙转介+IFA已合并口径)，代理人业务本周快报=H+I逐周相加、KA业务本周快报=J直接取用；已用真实数据核对"缺列=该周真实0贡献"（present-week-sum精确等于CSV自带"合计"列），缺列按0处理不算数据丢失。**v0.18.0（里程碑）：对着W37/W38 12页真实周报逐页再核对一遍后，补齐P4-P9共6项颗粒度缺口——银行月度走势×3+达成甜甜圈（P4）、同行/银行/代理人/KA四视角"本周快报"从整体3个数字升级为按KEY ACCOUNT逐行拆分+合计行（P5）、S3业务线×全部周完整表格对应真实周报Q/R/S热力矩阵（P6）、永明牌照×月批核明细表（P7）、S1月度明细表格（P8）、S1达标节奏线+批核APE月度走势预测（P9）。前端至此已跟真实12页周报数据+结构颗粒度基本对齐，可直接用于业务部门展示。⚠️P9的"最低月底线(69.5M)"和"10-12月预测(100/100/96M)"两个数字系从2026-09-25期W38周报PDF人工读取后写入代码常量`SUNLIFE_FORECAST_SOURCE`，不是程序反推得出，页面已用醒目文案标注来源和局限，详见执行记录.md v0.18.0。** 全部9个视角均用真实数据独立核验+built-in browser DOM核对确认渲染正确。

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
│   └── skills/cleaner.py                  清洗标准化（含日期类型修正+issuing_entity简繁别名归一化，v0.19.0新增）
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
│   └── skills/multiview_dashboard.py      前端阶段（PPT的替代方向）：多视角tab切换，S1总览/S2业务端/S3执行管理端/S4产品端/同行业绩/银行业绩/代理人业务/KA业务/永明业绩共9个视角全部实现，v0.18.0补齐P4-P9六项颗粒度缺口后已跟真实12页周报数据+结构基本对齐
│   └── skills/mark_standard_report.py     Mark标准报表：18页打印页面程序化复刻，v0.20.0第1-9页+v0.22.0第10-18页，Mark原文18页标准报表已全部完成，浅色独立视觉系统+page-break打印CSS
├── 07_接入记忆_Integrate_Memory/
│   └── raw_data/                          Jasper放置的原始底表Excel+业绩分析报表+PPT流水线参考代码+Carrie提供的generate_report.py权威生成脚本（v0.19.0新增）
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
python3 04_定义Agent_Define_Agent/agents/agent.py --refresh-frontend
python3 04_定义Agent_Define_Agent/agents/agent.py --mark-report
python3 04_定义Agent_Define_Agent/agents/agent.py --status
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

`--run` 读取 `raw_data/` 下的底表 Excel，清洗、聚合，在 `07_接入记忆_Integrate_Memory/data/` 生成 HTML 看板；`--enrich` 清洗后加上 S8 明细底表的13个衍生字段，存成CSV；`--sync-targets` 只读同步服务器 fact_target 目标APE数据（需要 `skills/db_config_local.py`，本地文件不进版本库）；`--s1` 复刻S1_总览仪表盘A-H八个板块，存成CSV；`--s2` 复刻S2_业务端视角全部20个子板块（含S/T的partner_code维度），存成CSV；`--s3` 复刻S3_执行管理端全部20个子板块（周度趋势+签批时效分析+未批核待签分布+同行/银行周度趋势），存成CSV；`--s4` 复刻S4_产品端视角全部5个板块，存成CSV；`--s5` 复刻S5_财务端视角全部8个板块（规模分档+大额保单TOP20），存成CSV；`--s6` 复刻S6_市场与交叉视角全部12张子表，存成CSV；`--s7` 复刻S7_合规端视角全部6个板块（牌照合规概览+牌照×业务细分+签批时效预警+TR人效），存成CSV；`--s9` 复刻S9_代理人与KA业务全部10个顶层板块（业务细分汇总+KA业绩分析+月度/周度明细），存成CSV；`--ppt` 从`raw_data/业绩报表PPT/template.pptx`+S1-S9 CSV生成周业绩PPT（已停止投入，实现到第1/8/9/10/11页为止，见 [PPT生成_旧流水线映射与新架构设计_v0.1.md](03_规划项目结构_Plan_Project_Structure/PPT生成_旧流水线映射与新架构设计_v0.1.md)）；`--frontend` 从S1-S9 CSV生成多视角前端HTML（代替PPT的新方向，S1总览/S2业务端/S3执行管理端/S4产品端/同行业绩/银行业绩/代理人业务/KA业务/永明业绩共9个视角全部实现，v0.18.0已跟真实12页周报数据+结构颗粒度基本对齐，双击`业绩数据分析前端.html`即可打开）；`--refresh-frontend` 换新底表后一条命令跑完前端需要的全部步骤（sync-targets→s1/s2/s3/s4/s9→frontend，不含S5/S6/S7因为前端9个视角用不到），sync-targets失败不中断，继续用上一次的fact_target快照——**注意不会更新`skills/multiview_dashboard.py::SUNLIFE_FORECAST_SOURCE`里"最低月底线"/"10-12月预测"这两个人工抄录自周报PDF的数字，业务侧预测目标变了需要单独更新**；`--mark-report` 生成Mark标准报表（18页打印页面，v0.20.0第1-9页+v0.22.0第10-18页，全18页已完成，需要先跑`--s1`/`--s2`/`--s3`/`--s4`/`--s6`/`--s9`，`--refresh-frontend`不含S6不会自动刷新，换新底表后要单独跑一遍`--s6`），输出`业绩数据分析_Mark标准报表.html`，浏览器打开后点右上角「打印/导出PDF」即可导出真实多页PDF；`--status` 查看上次运行的记录数/future_dated数等摘要。

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
- Mark标准报表18页逐页映射参照`raw_data/Mark标准报表_文本提取/p01.txt`-`p18.txt`原文（权威架构设计文档`Mark标准报表_页面映射与架构设计_v0.1.md`未在03目录下实际落地，这是Phase1遗留的文档缺口，详见mark_standard_report.py模块docstring）
- [执行记录.md](执行记录.md) — 端到端运行结果 + 踩坑记录
