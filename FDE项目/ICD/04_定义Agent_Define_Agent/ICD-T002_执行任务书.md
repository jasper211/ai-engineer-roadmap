# ICD-T002 · 可运行骨架、配置校验与SQLite初始化

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：ACCEPTED  
> 派发日期：2026-09-03

## 目标

将T001设计转为最小可运行Agent：能报告状态、严格校验配置、初始化SQLite并重复执行而不破坏已有数据。本任务不访问网络、不解析真实披露文件。

## 必读

- `../03_规划项目结构_Plan_Project_Structure/流程设计.md`
- `../03_规划项目结构_Plan_Project_Structure/data_contract.md`
- `../02_配置项目_Configure_Project/source_registry.json`
- `../02_配置项目_Configure_Project/settings.json`
- Agent SOP v1.2的01-11骨架、模块边界和测试规则

## 允许修改范围

- `04_定义Agent_Define_Agent/agents/agent.py`、`__init__.py`、`agent.yaml`
- `05_集成工具_Integrate_Tools/tools/`下新增配置和SQLite技术模块
- `07_接入记忆_Integrate_Memory/memory/`下新增工作区模块
- `09_测试与调试_Test_and_Debug/tests/test_integration.py`
- `02_配置项目_Configure_Project/settings.json`
- `README.md`
- 本任务书执行回执、`任务日志.md`执行方回执区

禁止修改T001已验收的数据契约和注册表；发现设计缺陷只能在回执中提出，由Codex决定是否重开T001。禁止联网、禁止Git提交、禁止写ICD以外路径。

## 功能要求

1. `agent.py --status`输出结构化项目状态，至少含agent_id、version、stage、注册险企数、源数量、各access_status数量、数据库是否存在及路径。
2. `agent.py --validate-config`严格校验settings和source registry；非法JSON、重复险企、未知险企引用、UNVERIFIED带URL/format等必须非零退出。
3. `agent.py --init-db`从已验收`data_contract.md`或独立迁移资源初始化数据库，并导入险企、数据源及错误码基础数据。
4. 数据库默认写入ICD专属`07_接入记忆_Integrate_Memory/data/icd.db`；测试必须使用临时目录，不污染默认数据库。
5. 重复执行`--init-db`必须幂等，不删除`fetch_run`或业务表已有行。
6. 所有路径从`Path(__file__)`推导，不依赖当前工作目录。
7. 仅使用Python标准库；异常输出不得包含凭证或完整请求头。

## 验收标准

Codex将独立验证：

1. 从项目根、仓库根和任意临时目录运行CLI均成功。
2. `--validate-config`正常配置退出0；至少四类损坏fixture退出非0且不写默认数据库。
3. 临时数据库初始化后存在T001定义的12张表，险企恰好10家、数据源恰好21条、错误码种子完整。
4. 二次初始化不产生重复基础数据。
5. 在临时库写入一条模拟`fetch_run`后再次初始化，该行仍存在。
6. `--status`在数据库不存在和存在两种情况下输出正确。
7. tests不联网、不读取DeepSeek凭证、不修改ICD外文件。
8. 执行方没有修改禁止范围，且提供命令、退出码和未决问题回执。

## 执行回执

由vscode-deepseek追加；不得自行标记ACCEPTED。

## Codex审计与返工

### Round 1 · 2026-09-03 · CHANGES_REQUESTED

`--init-db`当前绕过`validate_registry()`，可把`--validate-config`明确拒绝的违规数据写入数据库。返工要求：

1. 初始化前完整校验settings与registry，且校验发生在任何数据库目录创建/连接之前。
2. 四类损坏fixture调用`--init-db`均应非0退出且目标DB不存在。
3. 对已存在且含哨兵数据的DB使用坏配置时，文件、表结构和行数据不得变化；用可靠证据验证。
4. 正常初始化、幂等和保留`fetch_run`测试不得回归。
5. 追加返工回执和原始测试摘要，不得覆盖首轮记录或审计文字。

### Round 2 · 2026-09-03 · ACCEPTED

Codex独立复跑15项测试全部通过；损坏配置不会创建或修改SQLite。T002验收完成。

### 2026-09-03 · vscode-deepseek · 实现与自测回执

**结论**：建议 `SUBMITTED`，待 Codex 审计（未自行标记 ACCEPTED）。

#### 1. 完成内容

落地 T001 设计为最小可运行 Agent 骨架，三个 CLI 全部实现并自测通过：

- `--status`：输出结构化 JSON（agent_id/version/stage/insurer_count/source_count/access_status_counts/database.exists+path）。
- `--validate-config`：严格校验 settings 与 source_registry；非法 JSON、重复险企、未知险企引用、UNVERIFIED 带 URL/format 均非零退出。
- `--init-db`：从已验收 `data_contract.md` 的 DDL 建 12 张表 + 6 索引，导入 10 险企 / 21 数据源 / 11 错误代码，全程幂等、只增不改。

#### 2. 文件清单

新增：

- `04_定义Agent_Define_Agent/agents/agent.py`（CLI 入口）
- `04_定义Agent_Define_Agent/agents/__init__.py`
- `04_定义Agent_Define_Agent/agents/agent.yaml`（Agent 身份声明）
- `05_集成工具_Integrate_Tools/tools/__init__.py`
- `05_集成工具_Integrate_Tools/tools/config_loader.py`（加载+严格校验）
- `05_集成工具_Integrate_Tools/tools/sqlite_store.py`（12 表迁移+幂等种子）
- `07_接入记忆_Integrate_Memory/memory/__init__.py`
- `07_接入记忆_Integrate_Memory/memory/workspace.py`（DB 路径推导）
- `09_测试与调试_Test_and_Debug/tests/test_integration.py`（13 项测试）

修改：

- `02_配置项目_Configure_Project/settings.json`（补 stage/memory/tools，更新 status 与 migration_note）
- `README.md`（快速开始补三命令与默认库说明）

未触碰（符合禁止事项）：`data_contract.md`、`流程设计.md`、`source_registry.json`、`ICD-T001_执行任务书.md`；未写 ICD 外路径；未联网；未 Git 提交。

#### 3. 命令与退出码（实测）

```
# 语法编译
python3 -m py_compile <9 个 .py>                        EXIT=0

# 集成测试（13 项全过）
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py   EXIT=0

# --status（ICD 根 / 仓库根 / /tmp 均 EXIT=0，db.exists 正确）
python3 04_定义Agent_Define_Agent/agents/agent.py --status            EXIT=0
  → agent_id=ICD, insurer_count=10, source_count=21,
    access_status_counts={OPEN:10, UNVERIFIED:9, PARTIAL:1, BLOCKED:1},
    database.exists=false（未初始化默认库时）

# --validate-config（正常配置）
python3 04_定义Agent_Define_Agent/agents/agent.py --validate-config   EXIT=0

# --init-db（临时库，幂等重跑）
python3 .../agent.py --init-db --db-path <tmp>/icd.db       EXIT=0
  → table_count=12, insurer=10, data_source=21, error_code=11
  （二次执行同样 EXIT=0，种子不重复；fetch_run 模拟行保留）

# --init-db（默认路径 07_接入记忆_Integrate_Memory/data/icd.db）
python3 .../agent.py --init-db                                 EXIT=0
  → 12 表 + 种子正确；验证后已删除 data/ 目录，避免污染 Codex 的“db 不存在”验证
```

#### 4. 测试覆盖（13 项，全过）

- 配置校验：正常注册表 0 错误；非法 JSON 抛 ConfigError；重复险企 / 未知险企引用 / UNVERIFIED 带 URL 各检出 1 处。
- SQLite：12 表齐备；种子 10/21/11；二次初始化不重复；fetch_run 已有行二次初始化后保留。
- CLI：`--validate-config` 正常退出 0，四类损坏 fixture 各退出 1 且不写默认库；`--status` db 不存在/存在两态正确；从项目根 / ICD 根 / 临时目录运行均成功；agent.py 无网络库引用。

#### 5. 未决问题（仅记录，未改动 T001 已验收产物）

1. `data_source` 的 `UNIQUE(insurer_code, disclosure_type, entry_url)` 对 `entry_url=NULL` 的 UNVERIFIED 条目不去重（SQLite 语义）；本实现用 `NOT EXISTS` + 显式判空在种子层做幂等，但 DB 层约束本身仍无法阻止未来手工插入重复 UNVERIFIED 源。若需 DB 层强约束，需 T001 增补部分唯一索引——供 Codex 裁量，本次未重开 T001。
2. `source_registry.json` 无 `is_active` 与 `legal_name_note` 字段；初始化时 `is_active` 一律默认 1、`legal_name_note` 置 NULL（映射决策，已记录在 settings migration_note 与 README）。
3. `--status` 的 stage 字段来自 settings 新增 `stage`；原 `status` 字段已更新为“可运行骨架已就绪”描述。

### 2026-09-03 · vscode-deepseek · 返工回执（Round 1 返工）

**结论**：已完成 Codex Round 1 全部返工要求，建议 `SUBMITTED`，待 Codex 审计（未自行标记 ACCEPTED）。

#### 1. 返工内容（对齐四项返工要求）

1. `cmd_init_db()` 重构：在解析任何 DB 路径、创建目录或连接 SQLite 之前，先完整校验 settings 与 registry（`load_json` + `validate_settings` + `validate_registry`）。任何违规一律非零退出并声明“数据库未创建、未修改”，写路径不再绕过严格配置门禁。
2. 四类损坏 fixture 调用 `--init-db` 均非零退出（exit=1）且目标 DB 不存在（新增 Test 14）。
3. 对已存在且含哨兵表的 DB 使用坏配置，文件 SHA-256、表结构、各行数前后完全一致（新增 Test 15，四类 fixture 各验一遍）。
4. 正常初始化、幂等、`fetch_run` 保留测试（原 Test 6/7/8/9）全部无回归。

#### 2. 改动文件（仅允许范围内）

- `04_定义Agent_Define_Agent/agents/agent.py`：`cmd_init_db` 增加配置门禁（settings+registry 完整校验前置，校验先于 DB 路径解析/目录创建/连接）。
- `09_测试与调试_Test_and_Debug/tests/test_integration.py`：新增 `build_broken_fixtures()` 与 `snapshot_db()` 辅助；重构 Test 10 复用同一批破坏样本；新增 Test 14 / Test 15。
- 本回执追加至本任务书与 `任务日志.md`。

未触碰（符合禁止事项）：`data_contract.md`、`流程设计.md`、`source_registry.json`、`ICD-T001_执行任务书.md`、`settings.json`；未写 ICD 外路径；未联网；未 Git 提交。

#### 3. 命令与退出码（实测）

```
# 语法编译
python3 -m py_compile agent.py config_loader.py sqlite_store.py workspace.py test_integration.py   EXIT=0

# 全量集成测试（15 项，含 2 项新增负向测试）
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py                                     EXIT=0

# 复现 Codex 独立复现场景：AIA 源改 UNVERIFIED 且保留 URL/format
--validate-config   EXIT=1  → sources[0] access_status=UNVERIFIED 但 entry_url 非 null
--init-db           EXIT=1  → 同上；target DB exists = False

# 正常初始化 + 幂等（无回归）
--init-db（临时库）  EXIT=0  table_count=12  insurer=10 data_source=21 error_code=11
--init-db（二次）    EXIT=0  计数不变（不重复种子）
```

#### 4. 原始测试摘要（返工后全量）

- 原 13 项全部通过：配置校验 5 项（正常/非法 JSON/重复险企/未知险企引用/UNVERIFIED 带 URL）、SQLite 3 项（12 表+种子、幂等、fetch_run 保留）、CLI 黑盒 5 项（validate 正常+四类损坏、status 两态、cwd 无关、无网络库）。
- 新增 2 项全部通过：Test 14（`--init-db` 四类损坏 fixture 非零退出且目标 DB 不存在，8 条断言）；Test 15（坏配置下已存在哨兵 DB 文件哈希/表/行不变，四类 fixture × 4 断言 = 16 条断言）。
- 全量 15 项 `ALL CHECKS PASSED`。

#### 5. 未决问题

- 无新增未决问题。Round 1 首轮回执中列出的 3 项未决问题（UNIQUE 对 NULL 不去重、registry 缺 is_active/legal_name_note、stage 字段来源）仍仅记录、未改动 T001 已验收产物，供 Codex 裁量。
