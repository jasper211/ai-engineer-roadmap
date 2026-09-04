# ICD-T007 · Prudential RBC PDF 解析与入库

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：ACCEPTED  
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

---

## 执行回执（vscode-deepseek · 2026-09-03 · Round 1）

### 完成摘要

按任务书实现 Prudential（source_id=13）RBC 官方 PDF 的抓取、原始快照、文本层验证、Capital Adequacy 语义邻域解析、标准化与 SQLite 入库，形成首个 PDF/RBC 端到端闭环。核心比率（290%→2.90）由真实 PDF 独立提取，未写死；金额按 PDF 明示「in HKD thousands」标度折算绝对 HKD 入库，原文+标度无损保留在 `risk_breakdown_json`。

### 修改/新增文件清单

新增：
1. `requirements.txt` — 显式声明 `pdfplumber>=0.11.0,<0.12`（维护活跃，非静默依赖全局环境）
2. `06_开发技能_Develop_Skills/skills/pdf_text.py` — PDF 文本/表格提取（pdfplumber）；`%PDF` 签名校验、文字层校验（空→`PdfNoTextError`→`PDF_NO_TEXT`，不 OCR）；非 PDF→`PdfNotPdfError`
3. `06_开发技能_Develop_Skills/skills/pru_rbc_parser.py` — Capital Adequacy / Ratio 语义邻域解析（报告年度/偿付能力比率/币种/可选金额/风险分解 JSON），不全文百分号正则猜数、不写死 290%
4. `05_集成工具_Integrate_Tools/tools/rbc_writer.py` — `rbc_statement` 事务写入 + `parse_result`（幂等 UPSERT、原子回滚）
5. `09_测试与调试_Test_and_Debug/tests/fixtures/pru_rbc_fixture.json` — 脱敏文本+表格 fixture
6. `09_测试与调试_Test_and_Debug/tests/test_t007_parse.py` — 15 组确定性测试
7. `07_接入记忆_Integrate_Memory/T007_真实验证证据.md` — 真实 PDF/DB 验证产物
8. `07_接入记忆_Integrate_Memory/T007_真实PDF可再生素材_提取文本.txt` — 可再生文本证据（快照提取，非 OCR）

修改：
9. `06_开发技能_Develop_Skills/skills/parse_disclosure.py` — 接入 `pdf→PRU RBC` 分流 + PDF 错误语义（`PDF_NO_TEXT` / 非 PDF）
10. `README.md` — 快速开始补 `--parse 13`、当前状态补 T007
11. `02_配置项目_Configure_Project/settings.json` — status/stage/skills/tools/migration_note 更新

未触碰允许范围外任何文件：未改 `source_registry.json`、`data_contract.md`、`流程设计.md`、T001-T006 任务书、`agent.yaml`；未写 ICD 外路径；未 Git 提交；未自行标 ACCEPTED。（`agent.py` 无需功能改动：解析分流在 `skills/parse_disclosure.py`，`--parse` 已通用，其退出码映射已覆盖 RBC 的 OK/STRUCTURE_MISMATCH 等结果。）

### 依赖版本

- Python 3.14.4
- pdfplumber 0.11.10（基于 pdfminer.six 20260107，Pillow 12.2.0）

### 真实网络证据（与 fixture 分开）

- `SSL_CERT_FILE=/etc/ssl/cert.pem python3 ... --fetch 13` → EXIT=0；HTTP 200；Content-Type `application/pdf`；`%PDF-1.7` 签名；242184 字节；SHA-256 `b61630e9b275146bb4ea16a1f60ae189aa2e19daae11ea8a13751d66f97d0d51`；快照 `raw_data/PRU/13/{hash}.pdf`
- 文字层：4 页、8142 字符（非扫描件，无需 OCR）
- `--parse 13` → EXIT=0；`result=OK`；`run_id=6`；`report_year=2024`；`records_written=1`；`parse_status=OK`
- DB 落库：`solvency_ratio=2.9`、`solvency_ratio_raw='290%'`、`capital_base=581167000.0`、`prescribed_capital_amount=200745000.0`、`currency='HKD'`；`integrity_check=ok`、`foreign_key_check=[]`；重复 `--parse 13` 幂等仍 1 行
- 三处逐字抽查（PDF→DB）：① `Ratio of capital base to prescribed capital amount 290%` → `'290%'`/`2.9`；② `Capital base 581,167` → `581167000.0`；③ `Prescribed capital amount 200,745` → `200745000.0`（详见 `07_接入记忆_Integrate_Memory/T007_真实验证证据.md`）

### 确定性测试（fixture，不联网，tempfile，不污染默认库）

`python3 .../test_t007_parse.py` → EXIT=0，✅ ALL CHECKS PASSED，15 组：
百分比泛化（290%→2.90/304%→3.04/110%→1.10，证明未写死）、金额解析、PDF 签名、官方语句邻域（290%→2.90/2024/HKD/金额/风险分解 JSON）、跨行断词、重复候选比率歧义→STRUCTURE_MISMATCH、结构漂移→STRUCTURE_MISMATCH、错误年份（缺失/不一致）→STRUCTURE_MISMATCH、非 PDF→PdfNotPdfError、无文字层（最小空白 PDF）→PdfNoTextError、最小文本 PDF 端到端、可选金额缺失→NULL、rbc_writer 幂等/回滚/零记录、端到端（本地 HTTP 服务器→fetch→parse→证据链+幂等+integrity/FK）、CLI 退出码。

### 全量回归

`test_integration.py`（T002+T003）、`test_t004_parse.py`、`test_t005_parse.py`、`test_t006_parse.py`、`test_t007_parse.py` 均 EXIT=0；`py_compile` 全部 EXIT=0。

### 未决说明（供 Codex/Jasper 裁定，非阻断）

1. **主体身份差异**：PDF 主体为「Prudential General Insurance Hong Kong Limited」（一般保险），与注册表 `PRU`（「Prudential Hong Kong Limited」，寿险）是同一集团两个不同持牌实体。注册表禁止修改，故仅记录，未改。
2. **金额标度口径**：披露金额为「in HKD thousands」；本实现按 PDF 明示标度 ×1000 折算绝对 HKD 入库（币种金额语义），原文+标度保留在 `risk_breakdown_json`。若项目方偏好「保留披露原值 + 新增标度列」，属 Schema 决策。
3. **rbc_risk_component 未填充**：Prudential（一般保险）风险分解（General Insurance Risk / Reserve and premium risk / Natural catastrophe risk / Counterparty default and other risk 等）与 `rbc_risk_component` 的 risk_type 枚举无法无损一一对应，故只写 `rbc_statement` 单行 + `risk_breakdown_json` 原文，不写规范化子表（避免有损合并口径）。

### 建议任务状态

`SUBMITTED`（不自行标 ACCEPTED；审计结论由 Codex 填写）

---

## 执行回执（vscode-deepseek · 2026-09-03 · Round 2 · Jasper 重大决策返工）

### 决策依据

Jasper 已确认：真实 PDF 法律主体 `Prudential General Insurance Hong Kong Limited`（一般保险）必须作为独立主体，使用独立且语义明确的 `insurer_code`，并在 RBC 数据中保留法律主体原文；不得继续归到寿险 `Prudential Hong Kong Limited`（`PRU`）。授权最小修改 source_registry、数据契约、SQLite Schema/迁移、解析写入、测试、README/settings 与任务回执。

### 完成摘要

1. **独立主体编码**：新增 `insurer_code=PRUGI`（= Prudential **G**eneral **I**nsurance），name_en `Prudential General Insurance Hong Kong Limited`；寿险保持 `PRU`。`source_registry.json` 中 RBC 源（entry_url 含 `PGHK-RBC-public-disclosure-statement-2024.pdf`）由 `PRU` 改为 `PRUGI`，schema_version 1.0→1.1，险企 10→11。
2. **法律主体原文正式字段**：`rbc_statement` 新增 `legal_entity_name_raw TEXT NOT NULL`，保存「Authorized insurer's name」逐字原文；解析器无法提取即 `STRUCTURE_MISMATCH`，不再仅藏于 JSON。
3. **金额标度无损**：金额标准值仍为绝对 HKD（`capital_base`/`prescribed_capital_amount`），新增正式字段 `capital_base_raw`/`prescribed_capital_amount_raw`（披露原文）、`amount_unit_raw`（单位原文，如 `in HKD thousands`）、`amount_scale`（规范化标度 `thousands`/`millions`），可无损复现「原文 × 标度 = 绝对 HKD」。
4. **错误归属数据安全迁移**：`--init-db` 自动做 `pre-v4.bak` 全量备份后，在事务内①`data_source[13]` `PRU→PRUGI`；②删除错误归属 `rbc_statement`/`parse_result` 1 行（证据由备份+`fetch_run`+快照保留）；③移动快照 `raw_data/PRU/13/→raw_data/PRUGI/13/` 并回写 `fetch_run.snapshot_path`；④`ALTER TABLE` 补齐新列。迁移后 `--parse 13` 按新主体重建。`fulfillment_ratio`（4807 行）、其他险企与源不受影响。
5. **风险分解不强行映射**：`rbc_risk_component` 仍 0 行，完整子风险分解（22 PCA + 5 资本基础）保留在 `risk_breakdown_json`，不写不兼容枚举。
6. **schema 版本检测/迁移策略**：SQLite `PRAGMA user_version=4` 做版本检测；幂等（重复 init-db 无副作用）、原子（SQL 失败整体回滚，见 T007-17 测试）、主体隔离（PRU/PRUGI 分表分码）。

### 修改文件清单

修改：`source_registry.json`、`data_contract.md`（v0.5 + 3.8 迁移节）、`tools/sqlite_store.py`（新 rbc DDL + user_version + `migrate_rbc_v04` 迁移 + 备份）、`skills/pru_rbc_parser.py`（`_extract_legal_entity_name` + `_extract_currency_and_unit` + 新字段）、`tools/rbc_writer.py`（新列 UPSERT）、`skills/parse_disclosure.py`（rbc 分流 → `PRUGI`）、`agents/agent.py`（`--init-db` 传 `raw_data_root`）、`tests/test_t007_parse.py`（PRUGI 注册表 + 新字段断言 + T007-16 迁移/T007-17 回滚）、`tests/test_integration.py`（险企 10→11）、`tests/fixtures/pru_rbc_fixture.json`、`README.md`、`settings.json`（v0.5.0）。
新增：`07_接入记忆_Integrate_Memory/T007_Round2_迁移与重建证据.md`。

### 真实默认库证据（命令 + 退出码 + 真实 DB 行）

- `--init-db` EXIT=0：迁移报告 4 条 actions（见上）；备份 `icd.db.pre-v4.bak` SHA-256 `9265688e…`。
- `--parse 13` EXIT=0：`insurer_code=PRUGI`、`run_id=6`、`report_year=2024`、`records_written=1`、`parse_status=OK`。
- DB 直查 `rbc_statement` 单行：`('PRUGI', 6, 2024, 'Prudential General Insurance Hong Kong Limited', 2.9, '290%', 581167000.0, '581,167', 200745000.0, '200,745', 'HKD', 'in HKD thousands', 'thousands')`。
- `integrity_check=ok`、`foreign_key_check=[]`；`fulfillment_ratio`=4807、`fetch_run`=6、`rbc_risk_component`=0、`insurer`=11、`data_source`=21。
- 移动后快照 SHA-256 `b61630e9b275146bb4ea16a1f60ae189aa2e19daae11ea8a13751d66f97d0d51`（字节未变）。

### 确定性测试（不联网，tempfile）与全量回归

- `py_compile`（tools/memory/skills/agents/tests 全部 .py）EXIT=0；`--validate-config` EXIT=0。
- `test_t007_parse.py` EXIT=0（17 组，含新增 T007-16 迁移、T007-17 回滚，全部断言通过）。
- `test_integration.py`（T002+T003）、`test_t004_parse.py`、`test_t005_parse.py`、`test_t006_parse.py` 全部 EXIT=0、✅ ALL CHECKS PASSED，无回归。

### 范围

仅修改 ICD 允许范围内文件；未触碰 `流程设计.md`/T001-T006 任务书/`agent.yaml`/`需求定义.md`；未写 ICD 外路径；未 Git 提交；未自行标 ACCEPTED。注：仓库存在非 ICD 变更（`.claude/launch.json`、`05_Agent库/草稿/VNW/…`、`05_Agent库/草稿/_pipeline_health/…`），非本次执行产生，请 Codex 按文件路径区分。

### 建议任务状态

`SUBMITTED`（不自行标 ACCEPTED；审计结论由 Codex 填写）

---

## 执行回执（vscode-deepseek · 2026-09-03 · Round 3 · 快照/DB 一致性阻断项修复）

### 阻断项与修复设计

Codex Round 2 阻断项：`sqlite_store._move_snapshots()` 在 SQLite commit 前直接 `shutil.move`，若移动完成后 `seed_sources()`、`set_user_version()` 或 `commit()` 失败，DB 回滚到旧 `snapshot_path` 但文件系统不回滚，证据链指向不存在的旧路径；现有回滚测试只在移动前制造 FK 失败，未覆盖该窗口。

修复（不新增外部文件、不改变迁移结果语义）：

1. `tools/sqlite_store.py` 新增 `_SnapshotMoveJournal`：事务内每次物理快照移动都登记；`init_db` 在 DB 回滚时调用 `compensate()` 反向移回已移动文件，保证回滚后 DB 路径与物理快照一致、原文件不丢失。
2. 移动仅当「旧文件存在且新路径尚不存在」时执行，绝不覆盖既有文件（不丢文件）；补偿同样带存在性守卫（`new_fs.exists() and not old_fs.exists()`）。
3. 进程崩溃导致的未补偿移动，由幂等的 `_move_snapshots` 在下次 init-db 时对账收敛：即使旧路径已不存在也会回写 DB 到新路径，与新位置的文件对齐。
4. `init_db` 用 `committed` 标志区分「提交成功」与「回滚」：仅在回滚路径补偿，避免提交成功后把文件误移回旧路径。

### 修改文件清单

修改（仅 ICD 允许范围内）：`05_集成工具_Integrate_Tools/tools/sqlite_store.py`、`09_测试与调试_Test_and_Debug/tests/test_t007_parse.py`。未改其它任何文件。

### 确定性故障注入测试（不联网，tempfile，不污染默认库）

- 新增 T007-18a（文件移动后、DB 提交前失败）：monkeypatch `sqlite_store.set_user_version` 抛 `RuntimeError`。
- 新增 T007-18b（提交阶段失败）：monkeypatch `sqlite_store.connect` 返回 `commit()` 抛 `RuntimeError` 的代理连接（`sqlite3.Connection` 不可被 monkeypatch，故用包装类注入）。
- 每项验证：① 故障后 DB 回滚（`data_source` 仍 PRU、`snapshot_path` 仍 PRU 路径、`user_version` 未升级）+ 文件补偿（旧 PRU 快照仍在、新 PRUGI 快照不存在）+ 原文件字节不丢失；② 再次 `init_db` 幂等恢复（`data_source=PRUGI`、`snapshot_path` 改写、旧快照移走、新快照存在、字节一致）。

### 命令 + 退出码 + 证据

- `python3 -m py_compile`（tools/memory/skills/agents/tests 全部 .py）EXIT=0。
- `python3 04_定义Agent_Define_Agent/agents/agent.py --validate-config` EXIT=0（「配置校验通过：settings 与 source_registry 均合规」）。
- `python3 09_测试与调试_Test_and_Debug/tests/test_t007_parse.py` EXIT=0、`✅ ALL CHECKS PASSED`；共 19 组（原 17 + 新增 T007-18a/18b），18a/18b 各 12 项断言全通过（故障捕获 + 回滚一致性 + 补偿 + 原文件字节 + 幂等重跑收敛）。
- 全量回归：`test_integration.py`、`test_t004_parse.py`、`test_t005_parse.py`、`test_t006_parse.py` 全部 EXIT=0、`✅ ALL CHECKS PASSED`，无回归。

### 范围

仅修改 ICD 允许范围内文件（`sqlite_store.py`、`test_t007_parse.py`）；未触碰 `source_registry.json`/`data_contract.md`/`流程设计.md`/T001-T006 任务书/`agent.yaml`/`需求定义.md`/README/settings；未写 ICD 外路径；未 Git 提交；未自行标 ACCEPTED。仓库非 ICD 变更（`05_Agent库/草稿/PTA/…` 等）非本次执行产生，请 Codex 按文件路径区分。

### 建议任务状态

`SUBMITTED`（不自行标 ACCEPTED；审计结论由 Codex 填写）
