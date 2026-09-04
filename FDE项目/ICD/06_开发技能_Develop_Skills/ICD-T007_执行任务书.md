# ICD-T007 · Prudential RBC PDF 解析与入库

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：DISPATCHED  
> 派发日期：2026-09-03

## 目标

实现注册表 source_id=13（Prudential Hong Kong Limited 2024 RBC Public Disclosure Statement）的真实 PDF 抓取、原始快照、文本层验证、核心偿付能力数据解析、标准化和 SQLite 入库，形成首个 PDF/RBC 端到端闭环。

## 允许范围

- `06_开发技能_Develop_Skills/skills/`新增 PDF 文本提取和 Prudential RBC 解析/分流
- `05_集成工具_Integrate_Tools/tools/`新增 RBC 事务写入及必要通用工具
- `04_定义Agent_Define_Agent/agents/agent.py`接入 PDF/RBC 解析
- `09_测试与调试_Test_and_Debug/tests/`新增脱敏文本或最小 PDF fixture 与 T007 测试
- 项目根新增明确、最小化的 Python 依赖声明（如 `requirements.txt`）；不得静默依赖全局环境
- `07_接入记忆_Integrate_Memory/`写受控真实 PDF、数据库验证产物和可再生文本证据
- `README.md`、`settings.json`、本任务书和任务日志回执区

禁止修改 `source_registry.json`、已确认数据契约/流程设计、T001-T006 任务书；真实 PDF 若无法由现有 RBC Schema 无损表达核心口径，停止并提出重大决策 Gate。禁止 ICD 外写入、Git 提交或自行标记 ACCEPTED。

## 功能要求

1. 先通过 T003 抓取 source_id=13，验证 HTTP 200、`%PDF` 文件签名、Content-Type、哈希和快照；HTML 错误页不得当 PDF。
2. 选择维护活跃的 PDF 文本库并写入依赖文件；解析器不得联网，不执行 PDF 内嵌代码。首先验证文字层可用，空文字层明确 `PDF_NO_TEXT`，不得 OCR 猜数。
3. 仅从明确的 Capital Adequacy/Ratio of capital base to prescribed capital amount 语义邻域提取：报告年度、偿付能力比率、币种，以及披露中明确存在时的 capital base、prescribed capital amount；不得用全文任意百分号命中。
4. 百分比存小数比率且保留原文；金额及币种按契约保存。无法确认的可选字段写 NULL，不推算、不编造。核心比率缺失或歧义必须 `STRUCTURE_MISMATCH`。
5. 复用 run_id 证据链；`rbc_statement` 同 run_id 重复解析幂等，单源事务写入，硬失败不得留下部分 RBC 或风险分解行；`parse_result` 状态准确。
6. 结构漂移、错误年份、重复候选比率、非 PDF、无文字层、零记录分别具备确定性失败测试。

## 验收标准

1. fixture 覆盖官方语句邻域、290%→2.90、年度、币种、可选金额、跨行断词、重复候选歧义、无文字层/错误格式、幂等和回滚。
2. 真实验证从 source_id=13 快照解析，记录 PDF 页数、文本字符数、报告年度、偿付能力比率原文与标准值、币种及可选金额；至少三处 PDF 文本原文→数据库字段逐字核对。
3. 预期人工锚点为 Prudential 2024 披露中的 290%，但必须由当前真实 PDF 独立提取验证，不可把 290% 写死为解析结果。
4. 每条 RBC 记录经 run_id 反查真实 URL、HTTP 200、时间、哈希、快照；SQLite integrity、外键、自然键、幂等均通过。
5. 全量 T002-T006 测试无回归；fixture 测试不污染默认数据库。

## 执行回执

由 vscode-deepseek 追加依赖版本、命令、退出码、fixture/回归/真实网络证据和文件清单，不得自行标记 ACCEPTED。
