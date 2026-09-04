# ICD-T009 · 全量运行编排、摘要与覆盖状态闭环

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：DISPATCHED  
> 派发日期：2026-09-04

## 目标

落实流程设计 L3-ICD-06：提供一次命令即可按注册表处理所有 active 数据源的批次入口，确保单源失败隔离，生成机器可读和人可读运行摘要，并事务性更新 `coverage_status`。不得重复实现现有单源 fetch/parse；批次层只负责编排与聚合。

## 允许范围

- ICD 内 agent CLI、编排/摘要 skill、coverage_status 写入工具
- 数据契约与必要的最小 Schema 迁移
- fixture、确定性测试、README/settings、agent.yaml、流程设计状态更新、证据与回执

禁止修改 ICD 外项目、Git 提交、读取/记录密钥或引入浏览器自动化。不得在真实验证中强抓 BLOCKED/UNVERIFIED/requires_browser 源。

## 功能要求

1. 新增明确批次命令（如 `--run-all`）：先校验配置与初始化状态，再按固定 source_id 顺序处理 `is_active=1` 的源；`BLOCKED`、`UNVERIFIED`、`requires_browser=true` 必须跳过并进入摘要，不发网络请求。
2. 复用现有 `--fetch`/`--parse` 能力；HTML RBC 索引源执行发现步骤但不得误当业务 HTML 解析，最终 PDF 独立源正常抓取解析。普通 HTML/JSON/PDF 源按当前支持矩阵处理；尚未接入的 OPEN/PARTIAL 源须显式标为 UNSUPPORTED/缺覆盖，不能假装成功。
3. 单源抓取、发现或解析失败不得中止其余源；全局配置/数据库损坏才硬失败。每源摘要至少包含 source_id、insurer_code、disclosure_type、action、fetch/parse 状态、run_id、records_written、error_code/message。
4. `coverage_status` 必须按险企×披露类型反映最新真实结果，状态限定 FULL/PARTIAL/MISSING/BLOCKED/UNVERIFIED；定义确定、可重复的优先级与 upsert 规则，保留 last_attempt_at、last_success_at、last_error_code 等契约字段。不得把不可解析值导致的 `parse_result=PARTIAL` 自动误判为数据源覆盖缺失，需区分“记录值部分不可数值化”和“来源覆盖不完整”。
5. 摘要必须写入受控目录，采用唯一运行标识/时间，禁止覆盖历史；JSON 为机器接口，Markdown 为审计阅读，内容不得含密钥、Cookie 或完整请求头。
6. 支持 `--no-network` 或等价确定性模式，以已有快照完成解析/汇总；正常真实运行允许网络但对 UNCHANGED 应复用最新成功快照并确保摘要语义明确。
7. 幂等：同一批次重复汇总不重复业务行；coverage_status 仅更新同一自然键；摘要运行 ID 唯一。部分失败不得回滚其他源已成功数据。

## 验收标准

1. fixture 覆盖：一源成功、一源 HTTP 失败、一源结构失败、一源未支持、BLOCKED、UNVERIFIED、requires_browser、索引发现歧义，以及后一源仍继续执行。
2. `coverage_status` 状态和时间/错误字段逐项断言；重复运行行数不变；数据库 integrity/FK 通过。
3. `--no-network` 基于现有真实快照至少汇总 AIA/CTF/CLO 分红与 PRUGI/AIACO RBC，业务记录计数保持 4807 与 2，不污染或重复。
4. 真实批次验证记录每类状态数量、成功业务记录数、失败/跳过清单和摘要文件路径；全量 T002-T008 无回归。
5. README、settings、agent.yaml 与流程设计同步为当前实现状态；执行回执完整列命令、退出码、证据和范围。

## 执行回执

> 由 vscode-deepseek 于 2026-09-04 追加；状态建议 `SUBMITTED`，**不得自行标记 ACCEPTED**。

### 一、实现清单（允许范围内新增/修改）

- 新增 `skills/run_all.py`：`classify_source`（动作矩阵）、`discover_for_source`（索引发现，CLI 与批次复用）、`_process_source`（单源隔离）、`coverage_for_pair`（覆盖优先级推导）、`run_all`（全量编排入口）。
- 新增 `tools/coverage_writer.py`：`upsert_coverage`（`UNIQUE(insurer_code, disclosure_type)` 幂等 UPSERT + 失败保留历史成功时间/run_id）、`read_coverage`。
- 新增 `skills/summary_writer.py`：`utc_now_iso` / `new_run_id`（唯一运行标识）、`write_summary`（JSON+Markdown 写入受控目录，不覆盖历史）、`render_markdown`。
- 修改 `tools/sqlite_store.py`：`coverage_status` 新增 `last_attempt_at`/`last_success_at`/`last_error_code`/`last_error_message` 四列；`SCHEMA_VERSION` 5→6；新增 `migrate_coverage_v06` 并在 `init_db` 调用。
- 修改 `skills/parse_disclosure.py`：新增 `supports_parse`（支持矩阵，与 `parse_one_source` 分流一致，供编排层复用避免漂移）。
- 修改 `memory/workspace.py`：新增 `summaries_root` / `resolve_summaries_root`。
- 修改 `agents/agent.py`：新增 `--run-all` / `--no-network` / `--summaries-root` 与 `cmd_run_all`；`cmd_discover` 重构为复用 `run_all.discover_for_source`。
- 修改 `data_contract.md`：v0.7.0，coverage_status DDL 补四列 + 新增 3.10 迁移与覆盖语义说明。
- 修改 `README.md` / `settings.json`（v0.7.0，skills/tools 清单与 migration_note）/ `agents/agent.yaml`（同步当前实现状态）。
- 新增测试 `tests/test_t009_run_all.py`；修改 `tests/test_t007_parse.py`（备份名随 `SCHEMA_VERSION` 递增，避免版本升级后硬编码失效）。

### 二、确定性测试（不联网，tempfile）

```text
python3 -m py_compile $(find 04_定义Agent_Define_Agent/agents 05_集成工具_Integrate_Tools/tools 06_开发技能_Develop_Skills/skills 07_接入记忆_Integrate_Memory/memory 09_测试与调试_Test_and_Debug/tests -name '*.py')
# EXIT=0（全部 .py 编译通过）

python3 09_测试与调试_Test_and_Debug/tests/test_t009_run_all.py
# EXIT=0  ✅ ALL CHECKS PASSED
# T009-1 动作矩阵 9 例；T009-2 覆盖优先级+upsert（含 PARTIAL=值不可数值化仍计覆盖成功）；
# T009-3 全量批次 8 类场景 + coverage 逐项断言 + 后一源继续 + integrity/FK；
# T009-4 幂等（业务行/coverage 行不变、run_id 唯一、摘要不覆盖）；T009-5 --no-network；
# T009-6 CLI --run-all 端到端 + 未初始化硬失败 + --validate-config

for t in test_integration test_t004_parse test_t005_parse test_t006_parse test_t007_parse test_t008_parse test_t009_run_all; do
  python3 "09_测试与调试_Test_and_Debug/tests/$t.py"; done
# 七套全部 EXIT=0 ✅ ALL CHECKS PASSED（T002+T003 / T004 / T005 / T006 / T007 / T008 无回归 + T009 新增）
```

### 三、真实验证（默认库 `07_接入记忆_Integrate_Memory/data/icd.db`）

**schema 迁移（v5→v6）**：`--init-db` EXIT=0；`user_version=6`、12 表齐备；迁移报告 `coverage_status 新增列: last_attempt_at, last_success_at, last_error_code, last_error_message`；备份 `icd.db.pre-v6.bak`；业务数据保留（fulfillment_ratio 4807 / rbc_statement 2 / fetch_run 8 / parse_result 5）。

**`--run-all --no-network`（确定性，复用既有真实快照）**：EXIT=0；`counts={processed:6, succeeded:6, failed:0, skipped:10, unsupported:6}`；逐源 records：AIA 1573 / CTF 1969 / CLO 1265 / PRUGI 1 / AIACO 1 / AIA 索引 discover OK；**fulfillment_ratio=4807、rbc_statement=2 保持（不污染、不重复）**；coverage_status 22 行（FULL 6 = AIA/CTF/CLO 分红 + AIA 索引 + PRUGI + AIACO RBC；MISSING 6 = AXA/YFL/SUN/FWD/BOC/PRU 未接入；BLOCKED 1 = MAN；UNVERIFIED 9 = CTF TCV + 8 家 RBC）；integrity_check=ok、foreign_key_check=[]、fetch_run 仍 8；摘要 JSON+MD 写入 `07_接入记忆_Integrate_Memory/summaries/`。

**`--run-all`（联网，`SSL_CERT_FILE=/etc/ssl/cert.pem`）**：EXIT=0；同 counts；AIA/CLO/PRUGI/AIACO/AIA 索引 `UNCHANGED` 复用快照；CTF 因 CSRF token 刷新致哈希变化→新版本（见未决问题）。

### 四、范围与合规

- 仅改 ICD 允许范围内文件；未改 `source_registry.json` / T001-T008 任务书 / `需求定义.md` / HKIA / U020；未写 ICD 外路径。
- 未 Git 提交；未读取/记录密钥、Cookie 或完整请求头；未引入浏览器自动化；未自行标 ACCEPTED。
- 仓库非 ICD 变更（`05_Agent库/草稿/VNW/.../pending.json`、`11_监控与优化_Monitor_and_Optimize/` 等）非本次执行产生。

### 五、未决问题 / 已知限制（供 Codex/Jasper 裁定，非本任务阻断）

1. **CTF 页 CSRF token 轮换导致哈希非确定**：CTF 页内嵌 `<meta name="csrf-token" content="…">` 每次请求轮换，实测 1015616 字节中 70 字节差异全在 csrf-token，使内容哈希每次不同、`UNCHANGED` 去重对 CTF 失效，联网重跑会追加「同业务数据、不同 run_id」的新版本。属抓取层内容规范化问题（T003/T005），不在 T009 编排范围；本次验证产生的伪新版本（run_id=9 / 1969 行 / 快照）已精确回滚，默认库恢复 4807+2。建议后续在抓取层对已知动态 token 做哈希前规范化（不影响快照保真度——快照仍存原始字节，仅去重哈希可选用规范化内容哈希）。
2. **索引源（AIA rbc）覆盖语义**：`coverage_status(AIA, rbc)=FULL` 表示「官方索引可确定性定位目标 PDF」，业务数据实际归属 AIACO（独立主体）；已在摘要/契约注明，如需区分「发现覆盖」与「业务覆盖」可另行约定。
3. **退出码约定**：`--run-all` 批次完整跑完（含单源失败）即 EXIT=0，单源失败已隔离并写入摘要；仅全局配置/数据库硬失败 EXIT=1。若审计期望「存在源失败即非零」，可再议。

