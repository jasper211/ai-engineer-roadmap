# 推进-B · 本地可闭环任务

> 不依赖外部采集/人工输入、接手方可在当前环境直接推进的任务。全部基于**已落库资产**。
> 执行前确认数据集只读原则：接手前原始来源一律不覆盖，产出写入 `13` 目录或按原 12 层资产规范扩展。

## 环境说明

- 工作根：`HKIA/`（FDE项目下）
- DB：`07_接入记忆_Integrate_Memory/data/hkia.db`
- 主程序：`python3 04_定义Agent_Define_Agent/agents/agent.py <--run-demo|--status>`
- 集成测试：`python3 09_测试与调试_Test_and_Debug/tests/test_integration.py`
- 年度/季度资产清单：`12_分析框架验证_Validate_Framework/02_assets/`、`03_data_coverage/`

---

## B1 · 2025 全年临时包标准化

- 依据：`analysis_window_2023_2026Q1_v0.1.yaml`（annual_provisional: 2025，`labeling_required: provisional`）。
- 现状：2025Q4 资产已落库（1q25/4q25 在 raw_data）。
- 待做：
  1. 对 2025 各季度做 metric 级 schema 映射（2025 起 LT QR 新 Schema）。
  2. 将 2025 全年以 `provisional` 标签接入，明确不得当 certified 年度统计。
- 预期产出：更新后的季度/年度事实层 + 指标覆盖矩阵。

## B2 · 2023Q1–2026Q1 同期序列正式接入

- 依据：`quarterly_long_metric_comparability_v0.1.yaml`（18 指标 / 72 事实）。
- 现状：五期资产（1q23/1q24/1q25/4q25/1q26）已落库、已期审计；仅剩 metric 级事实化。
- 待做：把 72 条市场核心事实 & 4914 条公司事实固化为可查询标准事实表，供后续分析路由。
- 预期产出：`intergalactic`-style 标准事实层（保留期间/指标ID/原始值/单位/流量存量/可比等级/来源locator）。

## B3 · PwC TCF 监管回溯链

> ⏸ **暂缓（2026-08-06）**：属外部非业务信息输入，依赖 IA 官网监管文件（GL21/GL16/Conduct in Focus Issue 8）下载，非当前业务主线，后续处理。

- 依据：`HKIA-PWC-TCF-PILOT-01`（已下载 3 页 PDF，抽取机制 Finding，识别 8 条引用）。
- 待做：为 8 条引用建立到 IA 监管原文（GL21/GL16）的回溯任务，逐条核证或登记未回溯。
- 预期产出：引用–监管条款回溯登记表。

## B4 · 财务季度回溯 2024Q4–2025Q4

> ✅ **已完成 v0.1（2026-08-06）**：`生成_行业财务事实层_FinancialFactLayer/` 交付行业财务事实层（financial_fact_layer.db）。
> 覆盖 2024Q4/2025Q1/2025Q3/2025Q4/2026Q1 共 5 期 × 4 基金口径 × 17 科目 = 340 事实；恒等式 reconcile QA 全过。
> ⚠️ **2025Q2 缺口待补**：源为 OLE2 旧格式，本环境缺转换工具，登记 `pending_conversion_tool`（见 QA 报告）。

- 依据：`ASTSET-IA-FINANCIAL-2024Q4-2026Q1-XLSX`（六期季度财务已下载，2025Q2 因格式未解析）。
- 待做：`2025Q2` 在具备 OLE2→xlsx 转换工具后补排队重跑 `scripts/build_financial_fact_layer.py` + `qa/`。
- 约束：IS 口径与长期业务口径分离，不混用。

## B5 · 投诉 / 中介动态资产入库

- 依据：`IA_complaints` / `IA_intermediary_statistics`（已盘点 8 期投诉、中介动态数据）。
- 待做：对已落库/可解析文件跑解析入库；登记中介牌照统计覆盖情况。
- 约束：中介数据与保险业务数据分区记录。

---

## 执行纪律

- 每完成一项：更新 `数据资产变更登记.md` + `跟进日志` + `里程碑与验收对照.md`。
- 每项改动跑 `09/测试` 与 `验证与回归基线.md` 中列出的回归项，确保不破坏接手前基线。
- 若某项在本地运行时发现数据缺口（如缺源文件），登记 `问题与阻碍登记.md`，不伪造。
