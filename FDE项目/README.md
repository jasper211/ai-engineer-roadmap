# FDE 项目

以 FDE（Forward Deployed Engineer）角色承接的具体需求项目，每个项目独立建 Agent，严格按 [Agent 搭建 SOP v1.2](../05_Agent库/草稿/Agent搭建SOP_v1.2.md) 的 01-11 编号骨架搭建，不与 `05_Agent库/草稿` 下的 VNW/PTA/AIT/OB 混放。

## 项目列表

| Agent ID | 名称 | 状态 | 启动文档 |
|---|---|---|---|
| HKIA | 香港保监局（IA）行业数据自动化分析 Agent | 测试中——13期端到端跑通，8项集成测试全过，待 Mark/Jasper 确认归档 | [README](HKIA/README.md) · [需求定义](HKIA/01_初始化项目_Initialize_Project/需求定义.md) · [流程设计](HKIA/03_规划项目结构_Plan_Project_Structure/流程设计.md) · [执行记录](HKIA/执行记录.md) |
| PDA | 业绩数据多维分析 Agent（围绕牌照端 issuing_entity） | 测试中——看板端到端跑通(34项集成测试全过)，新增反推还原《业绩分析报表》S8明细底表13个衍生字段(12个已100%核验)，待 Jasper 提供"首年折扣标准化"规则+确认是否继续反推S1-S9其余7张专题表 | [README](PDA/README.md) · [需求定义](PDA/01_初始化项目_Initialize_Project/需求定义.md) · [S8衍生字段标准](PDA/01_初始化项目_Initialize_Project/S8衍生字段_反推标准_v0.1.md) · [流程设计](PDA/03_规划项目结构_Plan_Project_Structure/流程设计.md) · [执行记录](PDA/执行记录.md) |
| ICD | 保司自主披露数据采集 Agent（分红实现率+RBC披露声明，独立于HKIA现有架构的第五类数据源） | 需求定义已确认（10家险企真实实测），待 Codex 接手执行 SOP 第2步起 | [README](ICD/README.md) · [需求定义](ICD/01_初始化项目_Initialize_Project/需求定义.md) |
