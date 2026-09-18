# FDE 项目

以 FDE（Forward Deployed Engineer）角色承接的具体需求项目，每个项目独立建 Agent，严格按 [Agent 搭建 SOP v1.2](../05_Agent库/草稿/Agent搭建SOP_v1.2.md) 的 01-11 编号骨架搭建，不与 `05_Agent库/草稿` 下的 VNW/PTA/AIT/OB 混放。

## 项目列表

| Agent ID | 名称 | 状态 | 启动文档 |
|---|---|---|---|
| HKIA | 香港保监局（IA）行业数据自动化分析 Agent | 测试中——13期端到端跑通，8项集成测试全过，待 Mark/Jasper 确认归档 | [README](HKIA/README.md) · [需求定义](HKIA/01_初始化项目_Initialize_Project/需求定义.md) · [流程设计](HKIA/03_规划项目结构_Plan_Project_Structure/流程设计.md) · [执行记录](HKIA/执行记录.md) |
| PDA | 业绩数据多维分析 Agent（围绕牌照端 issuing_entity） | 测试中——看板+S8衍生字段+S1(全8板块)+S2(核心12/20)+S3(核心6/20)+S4(全5板块)+S5(全8板块)均已反推验证；目标APE数据源(服务器fact_target表)已打通只读同步；下一批转向S6-S7/S9共4张专题表+S2的S/T板块+S3的E/F/J-O板块 | [README](PDA/README.md) · [需求定义](PDA/01_初始化项目_Initialize_Project/需求定义.md) · [S8衍生字段标准](PDA/01_初始化项目_Initialize_Project/S8衍生字段_反推标准_v0.1.md) · [S1标准](PDA/01_初始化项目_Initialize_Project/S1_总览仪表盘_反推标准_v0.1.md) · [S2标准](PDA/01_初始化项目_Initialize_Project/S2_业务端视角_反推标准_v0.1.md) · [S3标准](PDA/01_初始化项目_Initialize_Project/S3_执行管理端_反推标准_v0.1.md) · [S4标准](PDA/01_初始化项目_Initialize_Project/S4_产品端视角_反推标准_v0.1.md) · [S5标准](PDA/01_初始化项目_Initialize_Project/S5_财务端视角_反推标准_v0.1.md) · [流程设计](PDA/03_规划项目结构_Plan_Project_Structure/流程设计.md) · [执行记录](PDA/执行记录.md) |
| ICD | 保司自主披露数据采集 Agent（分红实现率+RBC披露声明，独立于HKIA现有架构的第五类数据源） | 需求定义已确认（10家险企真实实测），待 Codex 接手执行 SOP 第2步起 | [README](ICD/README.md) · [需求定义](ICD/01_初始化项目_Initialize_Project/需求定义.md) |
