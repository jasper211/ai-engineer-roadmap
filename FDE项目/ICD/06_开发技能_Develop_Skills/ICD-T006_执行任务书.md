# ICD-T006 · 中国人寿（海外）HTML 分红实现率解析与入库

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：ACCEPTED  
> 派发日期：2026-09-03

## 目标

实现注册表中中国人寿（海外）CLO `fulfillment_ratio` HTML 源（当前按注册表顺序为 source_id=9）的完整闭环，使成功标准指定的 AIA、CTF Life、CLO 三家分红实现率全部具备真实官网证据、标准化记录和可重复查询结果。

## 允许范围

- `06_开发技能_Develop_Skills/skills/`新增或扩展 CLO HTML 解析与解析分流
- `05_集成工具_Integrate_Tools/tools/`仅补充必要的通用解析能力
- `04_定义Agent_Define_Agent/agents/agent.py`补充接入（若需要）
- `09_测试与调试_Test_and_Debug/tests/`新增脱敏 fixture 与 T006 测试
- `07_接入记忆_Integrate_Memory/`写受控真实快照及数据库验证产物
- `README.md`、`settings.json`、本任务书和任务日志回执区

禁止修改 `source_registry.json`、数据契约、流程设计、T001-T005 任务书；真实结构若无法由现契约无损表达，停止并提出重大决策 Gate。禁止 ICD 外写入、Git 提交或自行标记 ACCEPTED。

## 功能要求

1. 先通过 T003 抓取 source_id=9，记录 HTTP 状态、最终 URL、哈希、字节数、页面语言、目标表格数量和稳定 DOM 锚点；以当前真实页面为准。
2. 解析必须基于页面段落、产品标题、表头、行列与合并单元格关系；不得用全页百分号匹配冒充业务解析，也不得读取官方 PDF 替代注册表 HTML。
3. 原样保存产品名、指标原文、币种/披露分组、报告年度、观察期原文和数值原文；AD/TD/RB/TB/TCV/OTHER 不得合并。未知指标不得猜测；可无损落 `OTHER + metric_type_raw` 时须有测试，否则升级 Gate。
4. 数字观察年写整数，非数字期间写 NULL 并保留原文；百分比统一为小数比率。不可数值化项保留原文并写 `PARTIAL + VALUE_UNPARSEABLE`。
5. 结构漂移、零产品和零业务记录明确失败；解析不联网；同一 run_id 事务写入、硬失败回滚、重复解析幂等。
6. 页面导航、说明文字、脚注、隐藏模板和非目标表格不得入库；中英文混排、HTML 实体及空白折叠需确定性处理。

## 验收标准

1. 脱敏 fixture 至少覆盖两个产品、两个指标、跨年份、合并单元格、脚注/非数值、结构漂移、零记录、幂等和回滚。
2. 真实验证通过 source_id=9 的 T003 快照完成，记录产品数、记录数、指标/观察年分布、可数值与不可数值计数，并至少逐字核对 3 组官网 HTML→数据库原值。
3. 每条记录均可经 run_id 反查最终 URL、HTTP 状态、时间、哈希和快照；关键维度不得为空，自然业务键不得重复。
4. 全量 T002-T005 测试无回归，测试仅使用临时目录。

## 执行回执

由 vscode-deepseek 追加；必须分开记录 fixture、回归测试和真实网络证据，不得自行标记 ACCEPTED。

### 一、真实网络证据（source_id=9 · CLO fulfillment_ratio）

- **抓取命令**：`SSL_CERT_FILE=/etc/ssl/cert.pem python3 04_定义Agent_Define_Agent/agents/agent.py --fetch 9` → `EXIT=0`
- **HTTP 状态**：200
- **最终 URL**：`https://www.chinalife.com.hk/products/dividend-philosophy-and-investment-strategy`（无重定向）
- **内容哈希（SHA-256）**：`0ef53f6216f6f8760cdd5e02f06865ac0a048ce939b373146b7b59f513b7924a`
- **字节数**：`125326`
- **页面语言**：`<html lang="en">`（charset=utf-8；title=`Dividend Philosophy and Investment Strategy | China Life (Overseas)`）
- **fetch_run**：`run_id=5`（`OK`）；另 `run_id=4` 为未设 `SSL_CERT_FILE` 时的 `NETWORK_ERROR`（环境 CA 包缺 GoDaddy 链，非代码缺陷，见"已知限制"）
- **抓取快照**：`raw_data/CLO/9/0ef53f62…7924a.html`（125326 字节，与 SHA-256 一致）

#### 关键结构发现（先抓取后实现，以当前真实页面为准）

该页分红实现率数据**不在静态 `<table>` 里**，而是内嵌在页面一个 `<script>` 块中、由 JS 客户端渲染到空容器 `<div id="part1/2/3">` 的三个数组：

- `var policyYears = [...]`：11 个观察期标签 `Policy Year 1 (2024)`…`Policy Year 10 (2015)`、`Policy Year 10+ (2014 or before)`。
- `var dataSets1 = [...]`：68 产品（Annual Dividend → AD）。
- `var dataSets2 = [...]`：47 产品（Terminal Dividend → TD）。
- `var dataSets3 = []`：0 产品（Accumulated Interest，本年空且 HTML 注释掉）。
- 每行固定 `len(policyYears)+3` 个字符串：`[产品名, 产品类型, 币种/披露分组, 11 个值]`；值为百分比（`100%`/`70%`）或 `NA`。

页面里 6 个静态 `<table>` 是「Historical Crediting Interest Rate for Universal Life Plans」（Reporting year: 2021），属**万能寿险结算利率**，是另一种披露口径，**不属于 fulfillment_ratio，已排除**。

稳定 DOM 锚点：`<h3>Reporting year: 2025</h3>`、`<h3>1) Participating Plans - with Annual Dividend</h3>`、`<h3>2) Participating Plans - with Terminal Dividend</h3>`、`<!-- 3) Plans with Accumulated Interest -->`（注释）、`<div id="part1">`/`<div id="part2">`（空容器）。

#### 真实验证计数（`--parse 9` → `EXIT=0`，`run_id=5`）

- **report_year**：2025
- **product_count**：115（AD 68 + TD 47）
- **records_written**：1265（115 × 11）
- **value_unparseable**：926（`NA`）
- **metric 分布**：AD=748、TD=517（`metric_type_raw` 分别 `Annual Dividend`/`Terminal Dividend`）
- **币种/披露分组**：`Applied to all currencies plan`=1221、`Applied to RMB plan`=44
- **观察年分布**：整数年 1150（2024~2015）、`observation_year=NULL` 115（开放区间 `Policy Year 10+ (2014 or before)`）
- **可数值/不可数值**：`normalized_value` 非空 339、空 926（`NA`）
- **parse_result**：`PARTIAL` + `VALUE_UNPARSEABLE`，`records_produced=1265`
- **run_id 反查**：`final_url`=上述 URL、`http_status=200`、`content_hash`=上述哈希、`content_length=125326`、`snapshot_path`=上述快照
- **幂等**：重复 `--parse 9` 后总量仍 4807（3542 既有 + 1265 CLO），`run_id=5` 仍 1265 行、`parse_result` 仍 1 行
- **完整性**：`PRAGMA integrity_check`=ok、`foreign_key_check`=0 违例、自然业务键重复 0、关键维度（产品名/指标原文/观察期原文/原始值）空值 0

#### 逐字抽查（官网 HTML → 数据库原值，共 5 组，均 PASS）

1. `Properous Future Education Saving Plan` AD `Policy Year 1 (2024)`：scope=`Applied to all currencies plan`、raw=`100%` → `1.0`、observation_year=2024
2. `Properous Future Education Saving Plan` AD `Policy Year 10+ (2014 or before)`：raw=`76%` → `0.76`、observation_year=NULL
3. `Easy Life Retirement 60` AD `Policy Year 10+ (2014 or before)`：raw=`79%` → `0.79`、observation_year=NULL
4. `10-Year RMB Savings Insurance Plan` AD `Policy Year 8 (2017)`：scope=`Applied to RMB plan`、raw=`84%` → `0.84`
5. `Reach Insurance Plan` TD `Policy Year 1 (2024)`：raw=`NA` → NULL、metric_type_raw=`Terminal Dividend`

### 二、脱敏 fixture 测试（不联网）

- **新增**：`09_测试与调试_Test_and_Debug/tests/fixtures/clo_fixture.html`（脱敏，3 产品，无真实业务数据；含 Universal Life 静态表以验证排除）
- **新增**：`09_测试与调试_Test_and_Debug/tests/test_t006_parse.py`（9 组）
- **命令**：`python3 09_测试与调试_Test_and_Debug/tests/test_t006_parse.py` → `EXIT=0`，`✅ ALL CHECKS PASSED`
- **覆盖**：≥2 产品、≥2 指标（AD+TD）、跨年份、币种分组（all-currencies vs RMB）、脚注/非数值 `NA`、结构漂移（缺段落/缺变量/行宽不符/非字符串/数组未闭合/缺报告年度 6 类）、零记录、幂等、回滚、CLI 退出码。
- **说明**：CLO 为 JS 数组嵌入源（非静态 `<table>`），无 rowspan/colspan 合并单元格；等价结构特征为「11 列观察期对齐 + 币种分组」，二者均已覆盖，并额外断言静态 Universal Life 结算利率 `<table>` 不被误解析、导航文本不入库。

### 三、全量回归测试

| 命令 | 退出码 | 结果 |
|---|---|---|
| `python3 -m py_compile skills/clo_html_parser.py skills/parse_disclosure.py tests/test_t006_parse.py` | 0 | 编译通过 |
| `python3 09_测试与调试_Test_and_Debug/tests/test_integration.py`（T002+T003） | 0 | ✅ ALL CHECKS PASSED |
| `python3 09_测试与调试_Test_and_Debug/tests/test_t004_parse.py`（T004） | 0 | ✅ ALL CHECKS PASSED |
| `python3 09_测试与调试_Test_and_Debug/tests/test_t005_parse.py`（T005） | 0 | ✅ ALL CHECKS PASSED |
| `python3 09_测试与调试_Test_and_Debug/tests/test_t006_parse.py`（T006） | 0 | ✅ ALL CHECKS PASSED |

全部测试使用 `tempfile` 临时目录 + 本机临时 HTTP 服务器，不污染默认数据库与快照目录。

### 四、修改文件与范围

- 新增：`skills/clo_html_parser.py`、`tests/fixtures/clo_fixture.html`、`tests/test_t006_parse.py`
- 修改：`skills/parse_disclosure.py`（接入 CLO HTML 分流 + 异常捕获）、`README.md`、`settings.json`、本任务书回执、任务日志回执
- **未修改**：`source_registry.json`、`data_contract.md`、`流程设计.md`、T001-T005 任务书、`agent.yaml`
- **无 Schema 变更**：CLO 真实结构（产品名/指标/币种分组/报告年度/观察期原文/数值原文）可由现契约无损表达，未触发 Gate
- 未写 ICD 外路径；未 Git 提交；未自行标记 ACCEPTED

### 五、已知限制与说明（供 Codex 审计）

1. **注册表 hint 失准**：`source_registry.json` 对 source_id=9 的 `parser_hint` 写"纯 HTML `<table>`…9 个真实表格"。实测分红实现率数据在 JS 数组里、不在静态表；6 个静态表是万能寿险结算利率。因禁止修改 `source_registry.json`，hint 保持原样，仅在此记录（如需修正由 Codex/Jasper 裁定）。
2. **产品类型不落库**：`dataSets[i][1]`（如 `Product type - Participating endowment`）为非契约字段，与 AIA/CTF 既有做法一致（契约无此列），不落库。
3. **Accumulated Interest 本年空**：`dataSets3=[]` 且 HTML 注释掉；解析器仍将其映射为 `OTHER + metric_type_raw="Accumulated Interest"`（有测试），本年产出 0 条。
4. **SSL 环境**：本机 Python urllib 默认 CA 包（`/usr/local/etc/openssl@3/cert.pem`）缺该站 GoDaddy 链，抓取需 `SSL_CERT_FILE=/etc/ssl/cert.pem`（同 T005）。属环境 CA 问题，非 `http_fetcher.py` 代码缺陷。

> 状态建议：`SUBMITTED`，待 Codex 审计。

## Codex 独立审计 · ACCEPTED · 2026-09-03

- Codex 独立复跑 T006、T005、T004、T002+T003 全量测试，全部退出码 0。
- 真实库独立直查：CLO run 1265 行，关键维度空值 0、自然键重复 0、开放观察期 115 行全部整数年 NULL；`parse_result=('PARTIAL',1265,'VALUE_UNPARSEABLE')`，SQLite integrity 与外键检查通过。
- 内嵌 JS 数组按受限 tokenizer 解析，无 `eval`/脚本执行；静态万能寿险利率表正确排除。真实证据链和五组原值抽查成立，T006 正式放行。
