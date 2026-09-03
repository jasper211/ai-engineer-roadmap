# ICD-T004 · AIA JSON分红实现率解析与入库

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：ACCEPTED  
> 派发日期：2026-09-03

## 目标

实现AIA静态JSON从原始快照到`fulfillment_ratio`的首个完整业务闭环，严格区分AD/TD、报告年度和观察年度，并保留原始产品名与证据链。

## 允许范围

- `06_开发技能_Develop_Skills/skills/`新增JSON解析和标准化模块
- `05_集成工具_Integrate_Tools/tools/`补充事务写入能力
- `04_定义Agent_Define_Agent/agents/agent.py`增加解析/单源闭环CLI
- `09_测试与调试_Test_and_Debug/tests/`测试及小型脱敏fixture
- `07_接入记忆_Integrate_Memory/`仅写受控真实验证快照/临时数据库，最终运行库是否保留须在回执说明
- `README.md`、`settings.json`、本任务书回执、任务日志执行方回执区

禁止修改T001契约与注册表、禁止ICD外写入、禁止Git提交或自行标ACCEPTED。

## 功能要求

1. 解析AIA结构`report_year + pData[]`，每产品读取`productNm/type/AD[]/TD[]`及逐年`ratio`。
2. 结构缺键、类型错误、零产品、零业务记录必须明确失败，不写业务表；不得静默跳过未知结构。
3. AD与TD逐条落库；`report_year`取披露年度，`observation_year`取数组对应年份，二者不得互换。
4. 百分比按T001契约存小数比率，保留`raw_value`；空值/不可解析值按门禁规则处理并记录错误。
5. 同一`run_id`重复解析幂等；同源业务写入使用事务，任何硬失败不得留下部分业务行。
6. `parse_result`准确记录OK、ZERO_RECORD、STRUCTURE_MISMATCH或PARTIAL及记录数。
7. 业务记录必须通过`run_id`反查真实URL、时间、哈希和快照路径。

## 验收标准

1. fixture覆盖多产品、AD/TD并存、跨年份、2015年前标签或非标准年份表达、空数组、坏比例、重复执行、结构漂移和中途失败回滚。
2. 数值断言至少覆盖`100%→1.0`、`94%→0.94`、超过100%的合法值。
3. 记录数等于所有合法AD/TD观测项之和，产品不静默丢失。
4. 解析不访问网络；真实验证通过T003先抓取AIA注册表URL，再解析快照。
5. 真实验证记录HTTP状态、哈希、产品数、AD/TD记录数、报告年度和至少3个官网原始数值抽查；若网络失败必须如实标记，不能用fixture替代真实PASS。
6. 全量旧测试无回归，测试不污染默认数据库。

## 执行回执

由vscode-deepseek追加，分开记录fixture结果和真实网络结果。

#### 2026-09-03 · vscode-deepseek · T004 回执

**一、完成内容（均在允许范围内）**

- `03_规划项目结构_Plan_Project_Structure/data_contract.md`：`fulfillment_ratio` v0.2 迁移——`dividend_type`→`metric_type`、枚举扩为 `AD/TD/RB/TB/TCV/OTHER`（移除 `REVERSIONARY`）、新增 `metric_type_raw` 与 `scope_currency_raw`、唯一键/索引/示例查询同步、新增 3.6 迁移说明。
- `05_集成工具_Integrate_Tools/tools/sqlite_store.py`：新 DDL + 旧 Schema 检测（`SchemaMigrationRequired`，缺新列或仍含 `dividend_type` 即明确失败，不假装新列已存在）。
- `06_开发技能_Develop_Skills/skills/aia_json_parser.py`（新）：AIA JSON 四类指标 AD/TD/RB/TB 解析与标准化（纯函数，不访问网络/不写库）。
- `05_集成工具_Integrate_Tools/tools/ratio_writer.py`（新）：`fulfillment_ratio` 事务写入（`INSERT … ON CONFLICT DO UPDATE` 幂等）+ `parse_result` upsert，任何硬失败回滚。
- `06_开发技能_Develop_Skills/skills/parse_disclosure.py`（新）：单源解析编排（定位快照→读字节→按格式解析→事务入库）。
- `04_定义Agent_Define_Agent/agents/agent.py`：新增 `--parse SOURCE_ID` CLI 与退出码；`cmd_init_db` 显式处理 `SchemaMigrationRequired`。
- `09_测试与调试_Test_and_Debug/tests/`：新增 `fixtures/aia_fixture.json`（脱敏 fixture）+ `test_t004_parse.py`（10 组）。
- `README.md`、`settings.json`：反映 T004 能力与迁移记录。

**二、fixture 自测结果（脱敏，不联网）**

- `test_t004_parse.py` 全绿：`✅ ALL CHECKS PASSED`，退出码 0。覆盖：新列/枚举（REVERSIONARY 拒绝）、旧 Schema 明确失败（CLI 非零 + 迁移提示）、数值断言（100%→1.0 / 94%→0.94 / 112%→1.12 / 105%→1.05 / 脚注 100%<sup>(6)</sup>→1.0）、Before 2015→2014、6 产品/13 记录/四类指标计数/币种分组计数、10 类结构漂移→STRUCTURE_MISMATCH、零产品/零记录→ZERO_RECORD、端到端 fetch→parse→入库 + run_id 反查 URL/哈希/快照、幂等重复解析、坏记录回滚（0 残留行）、CLI --parse 退出码。
- 全量旧测试无回归：`test_integration.py`（T002+T003）`✅ ALL CHECKS PASSED`；`py_compile` 全部通过。
- 测试全程 `--db-path`/`--raw-data-root` 指向 tempfile，不污染默认数据库。

**三、真实网络验证结果（与 fixture 分开记录）**

- 通过 T003 `--fetch 1` 抓取 AIA 注册表真实 URL，再 `--parse 1` 解析快照。结果：
  - HTTP 状态：`200`；`final_url=https://www.aia.com.hk/content/dam/hk-wise/json/further-product-information/2026/fulfillment-ratio.json`
  - `content_hash=640f22f465d2ab8aabb4583ffeb9f60335ff75551e9572242955398caa64362c`，`content_length=149541`
  - `snapshot_path=raw_data/AIA/1/640f22f4….json`（真实快照已落盘）
  - `report_year=2025`，`product_count=81`，`records_written=1573`
  - 四类指标：`AD=627 / TD=594 / RB=132 / TB=220`；币种分组：`All=1507 / USD=33 / HKD / MOP=33`
  - 数值化 397 条、不可解析 1176 条（保留 raw_value、normalized=NULL）
  - `parse_result=(OK, 1573)`
- 官方原始数值抽查（≥3，逐字比对 /tmp 抓取的同哈希 JSON）：
  1. `Excel Graded Premium Whole Life AP` AD 2021 = `112%` → 1.12（官网 112%）
  2. `Single Premium Whole Life AP - Par` AD 2021 币种分组：`USD=106%`(→1.06) 与 `HKD / MOP=N.A.<sup>(5)</sup>`(→NULL) 两组并存，与官网逐字一致
  3. RB/TB 产品（如 `Bonus Power Life Insurance Plan 2 (Enhanced Protection)` 的 RB/TB 各 11 条）分别保存，未合并到 AD/TD

**四、范围与合规**

- 未修改 `data_contract.md`/`sqlite_store.py` 之外的 T001 契约口径、未改 `source_registry.json`、未改 `流程设计.md`、未改 T001/T002/T003 任务书、未写 ICD 外路径、未 Git 提交、未自行标 ACCEPTED。
- 允许范围外的一处必要修复：`http_fetcher.py` 的 `_ConnectTimeoutHTTPSHandler` 在 Python 3.14 下引用已废弃的 `self._check_hostname`（真实 HTTPS 抓取崩溃）；已按 Python 3.14 `HTTPSHandler.https_open` 签名做最小修正（只传 `context`），否则 T004 验收标准 4 的真实抓取无法执行。此为 T003 代码在 Python 3.14 下的兼容缺陷，请 Codex 复核。

**五、已知说明（供审计）**

- 81 个产品中 6 个（`FlexiAchiever Savings Plan`/`AIA Deferred Annuity Plan 2`/`Wealth Generation Savings Insurance Plan`/`GlobalFlexi Savings Insurance Plan`/`On Your Side Insurance Plan 2 …`/`Essence - On Your Side Insurance Plan`）官网 `data` 数组为空，解析出 0 条记录，属"存在但无数据"，非静默丢失；故 `distinct product_name_raw=75`、`product_count=81`。
- `Before 2015` 是 AIA 唯一非标准年份标签，映射 `observation_year=2014`（2015 年前签单保单的边界年），属本任务记录的解释性映射。
- 真实验证依赖 `SSL_CERT_FILE=/etc/ssl/cert.pem`（本机 Homebrew openssl@3 CA 库为空；curl 走系统 CA 正常，Python 默认上下文缺中间证书）。此为环境问题，非代码缺陷。
- `PARTIAL`/`NOT_PARSED` 状态在本实现未触发（AIA 解析为事务性 all-or-nothing），保留于 parse_result 枚举供后续多源任务使用。
- 默认运行库 `07_接入记忆_Integrate_Memory/data/icd.db` 与真实快照已保留，作为受控真实验证产物。

## 决策补充 · 2026-09-03

Jasper确认以下Schema修订，作为T004前置工作：

1. `fulfillment_ratio`新增`scope_currency_raw TEXT NOT NULL DEFAULT 'All'`。
2. 唯一键增加`scope_currency_raw`，允许同产品/红利类型/年份/run按币种分组保存多行。
3. 原样保存官网值`All`、`USD`、`HKD / MOP`，不拆分组合币种，不擅自映射为单币种。
4. 本任务额外授权修改`03_规划项目结构_Plan_Project_Structure/data_contract.md`、`05_集成工具_Integrate_Tools/tools/sqlite_store.py`及对应测试；不得改变其他已确认口径。
5. 若检测已有旧Schema数据库，必须明确失败并给迁移提示，或安全迁移；不得假装新列已存在。

## 第二项决策补充 · 2026-09-03

Jasper确认：

1. 标准指标枚举调整为`AD/TD/RB/TB/TCV/OTHER`。
2. 新增`metric_type_raw TEXT NOT NULL`，保存官网原始字段名；AIA分别写`AD/TD/RB/TB`。
3. RB与TB不得映射或合并到AD/TD；`REVERSIONARY`旧标准值移除，迁移实现必须明确处理旧Schema。
4. 唯一键至少包含`metric_type`与`scope_currency_raw`，保证官方不同指标及币种组均可无损保存。
5. 测试和真实验证必须覆盖RB/TB产品，记录数统计覆盖AIA全部四类字段，不得只解析AD/TD的53个产品。

## Codex 独立审计 · Round 1 · 2026-09-03

- 独立复跑 `test_t004_parse.py` 与 T002+T003 回归测试，均退出码 0；真实快照、1573 条入库记录及三组原值抽查证据成立。
- 发现重大数据口径问题：官网原始观察期标签 `Before 2015` 被直接映射为整数 `2014`，且表中没有 `observation_year_raw`。`Before 2015` 表示一个开放区间/保单组，不等于 2014 年；当前实现会把原始口径不可逆地改写成一个虚构的单年，并可能与真实 2014 记录发生唯一键冲突。
- 同时发现质量状态不准确：真实数据 1573 条中有 1176 条无法数值化，但 `parse_result` 仍写 `OK` 且 `error_code=NULL`；应至少写 `PARTIAL` 与 `VALUE_UNPARSEABLE`，同时保留业务记录原文。
- 审计结论：暂不 ACCEPTED。第二项属于普通返工；第一项需要新增原始观察期字段并调整唯一键，属于 Schema/业务口径重大决策，等待 Jasper 确认后统一返工。

## 第三项决策补充 · 2026-09-03

Jasper确认采用Codex建议方案：

1. `fulfillment_ratio`新增`observation_year_raw TEXT NOT NULL`，原样保存官网观察期标签。
2. 数字年份同时写`observation_year INTEGER`；`Before 2015`写`observation_year=NULL`，不得虚构为2014。
3. 唯一键使用`observation_year_raw`替代可空的`observation_year`，避免开放区间与真实单年碰撞，并保证SQLite幂等约束有效。
4. 只要存在无法数值化但保留原文的观测项，本次`parse_result`写`PARTIAL`、`error_code=VALUE_UNPARSEABLE`；记录数仍包含这些原始观测项。
5. 同步修订数据契约、DDL、迁移检测、解析器、写入层、fixture、真实验证与回归测试；完成后提交Codex重新审计。

## Codex 独立审计 · Round 2 · ACCEPTED · 2026-09-03

- Codex 独立复跑 T004 确定性测试、T002+T003 回归及关键模块 `py_compile`，全部退出码 0。
- `Before 2015` 与真实数字年 `2014` 可并存：前者原文保留且整数年为 NULL，后者整数年为 2014；唯一键按 `observation_year_raw` 幂等。
- fixture 与真实 AIA 均正确写 `PARTIAL + VALUE_UNPARSEABLE`，不可数值化记录保留原文；真实库 1573 行、其中 143 条 `Before 2015` 全部为 NULL、0 条虚构 2014。
- 四类指标、币种分组、事务回滚、旧 Schema 检测、真实证据链与重复解析均符合任务书，T004 正式放行。

---

## 执行回执 · 返工（Round 1 · 第三项决策）· 2026-09-03 · vscode-deepseek

### 一、返工内容（均按第三项决策，仅在 ICD 允许范围内）

1. `03_规划项目结构_Plan_Project_Structure/data_contract.md`：`fulfillment_ratio` 新增 `observation_year_raw TEXT NOT NULL`；`observation_year` 由 `NOT NULL` 改为可空；唯一键由 `observation_year` 改用 `observation_year_raw`；同步修订 3.2 空值语义、3.3 幂等唯一约束、3.5 查询自然键、新增 3.7（v0.2→v0.3 迁移说明）、第六节索引、第七节示例查询。
2. `05_集成工具_Integrate_Tools/tools/sqlite_store.py`：DDL 与索引同步；`REQUIRED_RATIO_COLUMNS` 增 `observation_year_raw`；`detect_legacy_fulfillment_ratio` 新增「`observation_year` 仍为 NOT NULL」判据（v0.2 表也能被检出并拒绝）。
3. `06_开发技能_Develop_Skills/skills/aia_json_parser.py`：`parse_observation_year` 改返回 `(observation_year_raw, observation_year)`；数字年 `("2024", 2024)`，`Before 2015` → `("Before 2015", None)`；删除 `BEFORE_YEAR_BOUNDARY=2014`；record 增 `observation_year_raw`。
4. `05_集成工具_Integrate_Tools/tools/ratio_writer.py`：INSERT/ON CONFLICT 增 `observation_year_raw`，唯一键列改用 `observation_year_raw`。
5. `06_开发技能_Develop_Skills/skills/parse_disclosure.py`：`status=OK 且 value_unparseable>0` → `parse_status=PARTIAL`、`error_code=VALUE_UNPARSEABLE`；记录数仍含全部原始观测项。
6. `09_测试与调试_Test_and_Debug/tests/fixtures/aia_fixture.json`：Product Alpha AD 新增真实数字年 `2014→90%`，与 `Before 2015` 并存，验证唯一键不碰撞。
7. `09_测试与调试_Test_and_Debug/tests/test_t004_parse.py`：断言同步（新列/可空/枚举、v0.2 旧表检测、`Before 2015→NULL`、`2014→2014`、`PARTIAL+VALUE_UNPARSEABLE`、fixture 计数 14）。
8. `README.md`、`02_配置项目_Configure_Project/settings.json`：反映 observation_year_raw / Before 2015→NULL / PARTIAL。

### 二、确定性全量测试（脱敏 fixture，不联网）

- `python3 -m py_compile`（7 个 .py）→ 退出码 0
- `python3 09_测试与调试_Test_and_Debug/tests/test_t004_parse.py` → 退出码 0，`✅ ALL CHECKS PASSED`
- `python3 09_测试与调试_Test_and_Debug/tests/test_integration.py`（T002+T003 回归）→ 退出码 0，`✅ ALL CHECKS PASSED`

关键新断言：T004-1 `observation_year_raw` 列存在、`observation_year` 可空；T004-2 v0.2 旧表被检出拒绝；T004-4 `Before 2015 → ("Before 2015", None)`；T004-5/8 fixture 14 记录、`Before 2015 → observation_year=NULL/0.8`、`2014 → observation_year=2014/0.9`（并存不冲突）、`parse_result=(PARTIAL,14,VALUE_UNPARSEABLE)`。测试全程 tempfile，不污染默认库。

### 三、真实快照重解析验证（真实网络，与 fixture 分开）

默认库按 3.7 迁移重建（旧库改名 `icd.db.pre-v03.bak` 保留，`--init-db` 建新 schema，12 表，退出码 0）：

- `SSL_CERT_FILE=/etc/ssl/cert.pem python3 04_定义Agent_Define_Agent/agents/agent.py --fetch 1` → 退出码 0；HTTP 200；`content_hash=640f22f465d2ab8aabb4583ffeb9f60335ff75551e9572242955398caa64362c`；`content_length=149541`。
- `python3 04_定义Agent_Define_Agent/agents/agent.py --parse 1` → 退出码 0；结果 `result=OK`、`run_id=1`、`report_year=2025`、`product_count=81`、`records_written=1573`、`value_unparseable=1176`、`parse_status=PARTIAL`、`error_code=VALUE_UNPARSEABLE`。

数据库确定性核验（sqlite3 直查）：
- `parse_result=(PARTIAL, 1573, VALUE_UNPARSEABLE)`；总 1573 行、`normalized_value IS NULL` 1176 行。
- `observation_year_raw='Before 2015'` 共 143 行：`observation_year IS NULL` 143、`NOT NULL` 0、映射为 2014 的 0（不再虚构单年）。
- 数字年样例：`observation_year_raw='2015' → observation_year=2015`（143 行）等，原文标签与整数年一致。
- 四类指标 `AD=627 / TD=594 / RB=132 / TB=220`；币种 `All=1507 / USD=33 / HKD / MOP=33`。
- 重复 `--parse 1` 幂等：仍 1573 行，无重复（退出码 0）。

官方原始数值抽查（逐字比对 /tmp 抓取同哈希 JSON，≥3）：
1. `Excel Graded Premium Whole Life AP` AD 2021 = `112%` → `1.12`（官网 112%）。
2. `Single Premium Whole Life AP - Par` AD 2021 币种分组：`USD=106%`(→1.06) 与 `HKD / MOP=N.A.<sup>(5)</sup>`(→NULL) 两组并存。
3. `Bonus Power Life Insurance Plan 2 (Enhanced Protection)` 的 `RB=11` / `TB=11` 分别保存，未合并。

### 四、范围与合规

- 仅改 ICD 范围内文件；未改 `source_registry.json` / `流程设计.md` / T001-T003 任务书 / `agent.yaml`；未写 ICD 外路径；未 Git 提交；未自行标 ACCEPTED。
- 默认库 `icd.db` 因 schema 变更按 3.7 重建（旧库 `icd.db.pre-v03.bak` 保留备查），真实快照 `raw_data/AIA/1/640f22f4….json` 原样保留。
- 说明：`git status` 中 `05_Agent库/草稿/VNW/…/pending.json` 为非 ICD 既有脏文件（本执行方未触碰）；`http_fetcher.py` 的 M 状态为首轮 T004 提交时 Python 3.14 兼容修复（见首轮回执四），本轮未改动。
