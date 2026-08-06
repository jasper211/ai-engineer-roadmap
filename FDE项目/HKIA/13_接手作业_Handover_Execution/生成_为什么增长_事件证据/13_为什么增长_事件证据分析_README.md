# 13 · 为什么增长 · 事件证据分析

> 承接上一个大模型 STEP-047（公司排名与增量贡献）之后的下一阶段：
> **从"谁增长、贡献多少"推进到"为什么增长"。**
>
> 原则同 `13_接手作业_README.md`：不更改接手前任何文档；全部产出写入本目录；
> 外部证据严格区分为「官方事实 / 行业事件线索 / 机制假说」，不把二手信息当事实。

## 上游结论（接手前，只读引用）

- 成果：`12_分析框架验证_Validate_Framework/outputs/HKIA_company_fact_layer_2023Q1_2026Q1_v0.1.xlsx`
- manifest：`12_.../02_assets/company_fact_layer_2023Q1_2026Q1_manifest_v0.1.yaml`
- 测试：`12_.../06_tests/company_ranking_gate_2026Q1_v0.1.yaml`
- 运行记录 STEP-047：`12_.../05_runs/run_phase_b_slice_01_v0.1.yaml`

## 需要"为什么增长"解释的核心对象（来自 manifest）

| 指标 | 前三/最大贡献者 | 需解释点 |
|------|----------------|---------|
| 新造整付保费 | HSBC, FWD Bermuda, Manulife（55.5%） | HSBC 贡献市场净增量 34.1% |
| 新造年度化保费 | HSBC, BOC Life, AIA Intl（55.8%） | HSBC 贡献净增量 61.5% |
| 有效保单数 | AIA, Prudential, Manulife（55.8%） | Prudential 贡献净增量 26.8% |
| 有效非整付保费 | HSBC, AIA, BOC Life（46.4%） | HSBC 贡献净增量 30.2% |
| **Chubb** | single_premium_receivable_growth **+44.97倍**（2025Q1→2026Q1） | ⚠️ 单笔保费异常，需外部/事件证据（疑与业务转移/收购相关） |
| Canada→MyPace | 业务转移，多项下降 | 转让调整致降，已公式校验 |

## 目标公司（重大变化候选）

**HSBC Life / BOC Life / Manulife / Sun Life / Chubb**（manifest 排名焦点 + 上一个大模型点名）。

## 本目录预期产物

- `事件证据登记_YYYYMMDD.csv`：Web 搜索产出的受控事件证据（来源/日期/证据等级）。
- `为什么增长_候选解释_分析.md`：基于登记的候选解释（区分事实/线索/假说）。
- `待人工复核清单.md`：需 Jasper 确认或进一步核实的点。

## 证据等级约定（遵循项目 08_证据等级规范）

- `F-官方`：公司官方披露 / 监管新闻稿 / 官方财报（可直接引用）。
- `E-事件线索`：行业媒体可靠报道、来源确实但未经官方证实。
- `H-机制假说`：基于数据的解释假设，未获直接证据，不得写成事实。
- `Q-成问题`：来源不确定、口径不清，仅登记待核。
