# ICD-T003 · HTTP抓取与原始证据固化

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：ACCEPTED  
> 派发日期：2026-09-03

## 目标

实现L3-ICD-02：从已验证、无需浏览器的数据源抓取原始字节，安全固化快照、计算SHA-256并记录`fetch_run`。本任务不解析JSON/HTML/PDF业务内容。

## 允许范围

- `05_集成工具_Integrate_Tools/tools/`新增或修改HTTP、快照、SQLite运行记录模块
- `06_开发技能_Develop_Skills/skills/`新增抓取编排模块
- `04_定义Agent_Define_Agent/agents/agent.py`增加抓取CLI
- `07_接入记忆_Integrate_Memory/memory/`补充快照路径能力
- `09_测试与调试_Test_and_Debug/tests/test_integration.py`
- `README.md`、`settings.json`、本任务书回执和任务日志执行方回执区

禁止修改T001契约/注册表、禁止Git提交、禁止ICD外写入。真实网络测试只能对注册表中`OPEN/PARTIAL`且`requires_browser=false`的源执行；自测主体必须使用本机临时HTTP服务器。

## 功能要求

1. 标准库实现HTTP GET，固定可识别UA、连接/读取超时、有限重定向和最大响应体限制。
2. 不记录Cookie、Authorization或完整请求头；日志只保留安全元数据。
3. 原始字节读取后计算SHA-256，写同目录临时文件并`os.replace`到`raw_data/{insurer}/{source}/{hash}.{ext}`。
4. 快照成功后才写成功`fetch_run`；HTTP/网络失败按T001三态约束写失败行。
5. 同源同内容重复抓取不重复快照、不重复成功行，返回明确`UNCHANGED`结果。
6. 数据库或快照写失败必须清晰报告；不得留下半文件。数据库需先通过T002初始化。
7. CLI支持按源ID抓取及`--dry-run`；BLOCKED、UNVERIFIED、requires_browser源必须拒绝。

## 验收标准

1. 本地HTTP服务器覆盖：200字节保真、重定向、403、404、5xx、超时、超限响应、同内容重复、不同内容新版本。
2. 成功快照哈希与文件字节一致，路径无穿越且位于指定raw_data根。
3. HTTP失败有状态码且无哈希/快照；网络失败无HTTP状态且无哈希/快照。
4. 同内容二次抓取不新增文件和成功行；不同内容新增版本。
5. dry-run不写快照和数据库；被禁源非零退出且无副作用。
6. 任何测试失败后无`.tmp`残留；所有测试使用临时目录。
7. 执行方提交命令、退出码、覆盖场景和未决问题；不得自行标ACCEPTED。

## 执行回执

由vscode-deepseek追加。

## Codex审计与返工

### Round 1 · 2026-09-03 · CHANGES_REQUESTED

响应体读取超时当前会从`_read_capped()`直接抛出，绕过`FetchOutcome`和失败运行记录。返工要求：

1. 捕获响应头成功后的body读取超时和连接异常，统一返回`NETWORK_ERROR`；`NETWORK_TIMEOUT`与`NETWORK_CONNECTION`正确区分。
2. 按T001三态约束写入失败行：`http_status/content_hash/snapshot_path`均为NULL。
3. 新增慢body和body中途断连两类本机HTTP测试，覆盖工具返回值与编排层数据库记录。
4. 断言失败后无快照及`.tmp`残留；现有142项断言不得回归。
5. 追加返工回执，不修改审计文字，不自行标ACCEPTED。

### 执行回执（vscode-deepseek · 2026-09-03）

#### 完成摘要

按任务书实现 L3-ICD-02「HTTP 抓取与原始证据固化」，不解析 JSON/HTML/PDF 业务内容。新增 3 个工具模块（HTTP / 快照 / 运行记录）+ 1 个抓取编排 skill，扩展 memory 路径能力与 agent CLI，并新增 12 组本地 HTTP 服务器集成测试。主体测试全部使用本机临时 `http.server`，未访问真实网络。

#### 修改文件清单

新增：
1. `05_集成工具_Integrate_Tools/tools/http_fetcher.py` — 标准库 HTTP GET（固定可识别 UA、连接/读取超时分离、有限重定向、最大响应体限制）
2. `05_集成工具_Integrate_Tools/tools/snapshot.py` — SHA-256 + 同目录临时文件 + `os.replace` 原子落盘
3. `05_集成工具_Integrate_Tools/tools/fetch_recorder.py` — fetch_run 三态写入 / 同源同内容去重 / 取源
4. `06_开发技能_Develop_Skills/skills/__init__.py` + `fetch_disclosure.py` — L3-ICD-02 抓取编排

修改：
5. `07_接入记忆_Integrate_Memory/memory/workspace.py` — 补 raw_data 根 / 相对路径 / 绝对路径（带防穿越守卫）
6. `04_定义Agent_Define_Agent/agents/agent.py` — 增 `--fetch SOURCE_ID` / `--dry-run` / `--raw-data-root` CLI
7. `09_测试与调试_Test_and_Debug/tests/test_integration.py` — T003 本地 HTTP 服务器 12 组测试
8. `02_配置项目_Configure_Project/settings.json` — status/stage/tools/skills/migration_note 更新
9. `README.md` — 快速开始补 --fetch/--dry-run、当前状态更新
10. 本任务书回执 + `任务日志.md` 执行方回执区（追加）

未触碰允许范围外任何文件：未改 `data_contract.md`、`流程设计.md`、`source_registry.json`、`ICD-T001/T002 任务书`、`agent.yaml`（不在允许范围）、未动 HKIA/U020、未 Git 提交。

#### 自测命令、退出码与覆盖场景

命令：

```
# 语法编译（8 个 .py）
python3 -m py_compile 05_集成工具_Integrate_Tools/tools/*.py \
  07_接入记忆_Integrate_Memory/memory/*.py 06_开发技能_Develop_Skills/skills/*.py \
  04_定义Agent_Define_Agent/agents/*.py 09_测试与调试_Test_and_Debug/tests/*.py   → EXIT=0

# 配置校验（settings.json 更新后）
python3 04_定义Agent_Define_Agent/agents/agent.py --validate-config   → EXIT=0

# 全量集成测试（T002 15 组 + T003 12 组）
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py   → EXIT=0，✅ 142 项，❌ 0 项
```

覆盖场景（对应验收标准 1）：

| 场景 | 结果 | 断言要点 |
|---|---|---|
| 200 字节保真 | OK | 哈希=SHA-256(字节)、快照字节一致、UA 可识别、无 Cookie/Authorization |
| 重定向 302→200 | OK | final_url=/final、内容哈希正确 |
| 403 / 404 / 5xx | HTTP_ERROR | http_status 非空、无哈希/快照、error_code 对应 |
| 超时 | NETWORK_ERROR | http_status=NULL、error_code=NETWORK_TIMEOUT、无哈希/快照 |
| 超限响应 | HTTP_ERROR | http_status=200、note 说明上限、不落快照 |
| 同内容重复 | UNCHANGED | 不新增快照文件、不新增成功行 |
| 不同内容新版本 | OK | 新增版本（2 快照 + 2 成功行） |
| BLOCKED/UNVERIFIED/requires_browser | REJECTED | 无 fetch_run 行、无快照、CLI 退出码 2 |
| dry-run | DRY_RUN | 不写快照、不写数据库 |
| 路径防穿越 | ValueError | 非法 insurer_code/扩展名抛异常、正常路径在 raw_data 根内 |
| 无 .tmp 残留 | — | 各测试组内 `_assert_no_tmp` 均过 |

CLI 退出码约定：`OK/UNCHANGED/DRY_RUN=0`；`REJECTED=2`；`HTTP_ERROR=3`；`NETWORK_ERROR=4`；`SNAPSHOT_ERROR/DB_ERROR=5`；配置非法/DB 未初始化/源不存在=1。

#### 与任务书不同之处及原因

1. **快照目录锚点**：任务书写 `raw_data/{insurer}/{source}/{hash}.{ext}`；本实现把 `raw_data` 锚定在 `07_接入记忆_Integrate_Memory/raw_data/`（settings.json 明示 raw_data 与 data/ 隔离）。入库 `snapshot_path` 值为 `raw_data/{insurer}/{source}/{hash}.{ext}`，绝对路径由 `memory/workspace` 解析并带防穿越守卫。
2. **超限响应归类 HTTP_ERROR**：三态 CHECK 只允许 OK/HTTP_ERROR/NETWORK_ERROR；超限（收到 200 但体量超限）以 `http_status=200 + HTTP_ERROR` 记录，note 说明上限。未新增 "BODY_TOO_LARGE" 错误码——那会破坏 T002 的 11 条种子断言且属 T001 契约。
3. **快照/DB 写失败不写 fetch_run 行**：三态 CHECK 无法表达"哈希已有但快照未落盘"的第四态，故快照写失败/DB 写失败以 CLI 明确报 `SNAPSHOT_ERROR`/`DB_ERROR` + 非零退出 + 清理孤儿快照，不写成功型 fetch_run（对齐功能要求 6「不得留下半文件」）。
4. **新增 `--raw-data-root`**：任务书只要求 --fetch/--dry-run；为满足验收标准 6「测试用临时目录」补一个 raw_data 根覆盖参数，不改变默认行为。
5. **未改 agent.yaml**：允许范围仅列 `agent.py`，故 tools/skills 清单更新落在 `settings.json`（属允许范围），agent.yaml 待后续任务同步。

#### 已知限制/未决问题

1. 本轮未做真实网络探针（任务书要求主体测试用本机临时服务器；真实网络仅限注册表 OPEN/PARTIAL 且 requires_browser=false 源，留待受控探针/后续任务）。
2. `agent.yaml` 的 tools/skills/memory 清单未同步（不在 T003 允许范围），建议 Codex 下轮一并更新或另行派发。
3. connect/read 超时经模块级 `_Timeouts` 注入，单线程设计（CLI 逐源串行）；未来并发抓取需改为线程局部。
4. 重定向循环/超限（>5 次）会被 HTTPRedirectHandler 折叠为 HTTP_ERROR(302)，error_code 为空（无对应种子）。

#### 建议任务状态

`SUBMITTED`（不自行标 ACCEPTED；审计结论由 Codex 填写）

### Codex Round 2 · 2026-09-03 · ACCEPTED

Codex独立复跑156项断言全部通过；响应体超时与中途断连均正确落为NETWORK_ERROR。T003验收完成。

### 返工回执（vscode-deepseek · 2026-09-03 · Round 2）

#### 返工摘要

按 Codex Round 1 返工要求修复"响应头成功后响应体读取超时/中途断连绕过失败记录"问题。

根因：`http_fetcher.fetch()` 只对 `opener.open()` 阶段做了异常折叠，`_read_capped(resp, cap)` 在响应体读取阶段抛出的 `socket.timeout`/断连异常未被捕获，直接向上抛，导致编排层不写 `NETWORK_ERROR fetch_run`。此外 Python `http.client` 的有界 `read(amt)` 在 EOF 时只返回 `b""`、不抛 `IncompleteRead`，body 中途断连（Content-Length 未满足即关闭）会被误判为"正常读完"。

修复（`tools/http_fetcher.py`）：

1. 把响应体读取整体包进 `try`：`socket.timeout`/`TimeoutError` → `NETWORK_ERROR/NETWORK_TIMEOUT`；`http.client.IncompleteRead` → `NETWORK_ERROR/NETWORK_CONNECTION`；其余 `ConnectionError`/`OSError`/`HTTPException` → `NETWORK_ERROR/NETWORK_CONNECTION`。三类均返回 `http_status=None`、无哈希/无快照。
2. `_read_capped()` 在读到 EOF 时主动检查 `resp.length`（Content-Length 剩余字节）：若 >0 说明 body 中途断连，抛出 `http.client.IncompleteRead`，由 `fetch()` 统一折叠。超限（`total > cap`）路径在读满前主动返回、不触碰 EOF，仍正确归 `HTTP_ERROR`。
3. 以 `try/finally` + 受保护 `resp.close()` 替换 `with resp:`，关闭连接失败不掩盖业务结果，也不改变原语义。

#### 修改文件清单

1. `05_集成工具_Integrate_Tools/tools/http_fetcher.py` — 响应体读取异常折叠 + `_read_capped` 断连检测。
2. `09_测试与调试_Test_and_Debug/tests/test_integration.py` — 测试服务器新增 `/slow-body`、`/truncated` 两条路由；测试注册表源扩至 13 条（新增 12/13）；新增 T003-13、T003-14 两组本机 HTTP 测试并登记进 `main()`。

#### 自测命令、退出码与覆盖场景

```
# 语法编译
python3 -m py_compile 05_集成工具_Integrate_Tools/tools/*.py \
  07_接入记忆_Integrate_Memory/memory/*.py 06_开发技能_Develop_Skills/skills/*.py \
  04_定义Agent_Define_Agent/agents/*.py 09_测试与调试_Test_and_Debug/tests/*.py   → EXIT=0

# 全量集成测试（T002 15 组 + T003 14 组）
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py   → EXIT=0，✅ 156 项，❌ 0 项
```

新增覆盖场景（对应返工要求 3/4）：

| 场景 | 结果 | 断言要点 |
|---|---|---|
| 慢响应体（200 头已回、body 延迟） | NETWORK_ERROR/NETWORK_TIMEOUT | http_status=None、无哈希/快照、error_code=NETWORK_TIMEOUT |
| body 中途断连（Content-Length=1000 只发 13 字节即断开） | NETWORK_ERROR/NETWORK_CONNECTION | http_status=None、无哈希/快照、error_code=NETWORK_CONNECTION |

两组均断言：工具返回值三态正确 + 编排层 `fetch_run` 失败行 `fetch_status=NETWORK_ERROR` 且 `http_status/content_hash/snapshot_path` 全 NULL + 无快照文件 + 无 `.tmp` 残留。

回归：原 142 项断言无回归；全量 156 项 `ALL CHECKS PASSED`，`py_compile` 通过。

#### 范围声明

仅改 `http_fetcher.py`、`test_integration.py` 并追加本返工回执与任务日志执行方回执区；未改 Codex 审计文字（Round 1 CHANGES_REQUESTED 原样保留）、未改 `data_contract.md`/`流程设计.md`/`source_registry.json`/T001/T002 任务书、未写 ICD 外路径、未联网真实站点、未 Git 提交。

#### 建议任务状态

`SUBMITTED`（不自行标 ACCEPTED；审计结论由 Codex 填写）
