# ICD-T005 · CTF Life HTML 分红实现率解析与入库

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：ACCEPTED  
> 派发日期：2026-09-03

## 目标

实现注册表中 CTF Life `fulfillment_ratio` HTML 源（当前按注册表顺序为 source_id=5）的完整闭环：通过 T003 抓取真实 HTML 快照，解析产品/指标/观察期/原始比率，复用统一标准化与事务写入能力，并以真实官网证据验收。

## 允许范围

- `06_开发技能_Develop_Skills/skills/`新增或扩展 HTML 解析与解析分流模块
- `05_集成工具_Integrate_Tools/tools/`仅补充解析所需的通用、可测试能力
- `04_定义Agent_Define_Agent/agents/agent.py`补充 HTML 单源解析接入
- `09_测试与调试_Test_and_Debug/tests/`新增脱敏 HTML fixture 和 T005 测试
- `07_接入记忆_Integrate_Memory/`写受控真实快照及数据库验证产物
- `README.md`、`settings.json`、本任务书回执、任务日志执行方回执区

禁止修改 `source_registry.json`、已确认的数据契约/流程口径和 T001-T004 任务书；若真实结构证明现契约无法无损表达，必须停止并提出重大决策 Gate。禁止 ICD 外写入、Git 提交或自行标记 ACCEPTED。

## 功能要求

1. 先抓取并分析真实 CTF HTML DOM，记录 HTTP 状态、最终 URL、哈希、字节数、页面语言及稳定结构锚点；不得只根据需求文档中的旧计数实现。
2. 解析器必须使用 Python 标准库或已明确登记的依赖，不得用脆弱的全页百分号正则充当业务解析；须基于表格层级、标题、表头和单元格关系恢复记录。
3. 原样保留产品名、`metric_type_raw`、`observation_year_raw`、`scope_currency_raw` 和 `raw_value`；标准指标只可映射到 `AD/TD/RB/TB/TCV/OTHER`，不得合并不同官网口径。
4. 数字观察年写整数；非数字观察期写 NULL 并保留原文。百分比换算沿用 T004；不可数值化值保留原文并使源级结果为 `PARTIAL + VALUE_UNPARSEABLE`。
5. 结构漂移、零产品或零业务记录必须明确失败并写 `parse_result`；解析不得联网；入库按单个 run_id 事务化，失败不留部分行，重复解析幂等。
6. 不得将导航、脚注、示例文字、营销内容或同页非分红表格误记为业务记录；重复表头、rowspan/colspan、空单元格必须有确定性处理和测试。

## 验收标准

1. 小型脱敏 fixture 覆盖至少两个产品、两个指标、跨年份、rowspan/colspan 或多层表头、脚注值、不可解析值、空表、结构漂移、重复执行和事务回滚。
2. fixture 记录数由明确业务单元格计算，逐条断言关键原文及标准值；不得只断言“数量大于零”。
3. 真实验证必须通过 T003 抓取 source_id=5 后解析快照，记录产品数、表格数、各指标计数、业务记录总数、不可解析数及至少三组“官网 HTML 原文→数据库行”抽查。
4. 每条业务记录可经 run_id 反查 CTF 真实 URL、HTTP 200、抓取时间、哈希和快照路径。
5. T002-T004 全量测试无回归，测试不污染默认数据库；真实站点若结构变化或不可达，如实记录并停止，不得用 fixture 冒充真实 PASS。

## 执行回执

由 vscode-deepseek 追加完整命令、退出码、文件清单、fixture 与真实网络证据；不得自行标记 ACCEPTED。

#### 2026-09-03 · vscode-deepseek · T005 回执

**一、完成内容（均在允许范围内）**

- `06_开发技能_Develop_Skills/skills/ctf_html_parser.py`（新）：CTF Life `fulfillment_ratio` HTML 表格解析与标准化。基于 `html.parser.HTMLParser`（标准库）+ 表格网格重建（rowspan/colspan 传播），按段落标题/产品容器/三层表头/单元格关系恢复记录；不访问网络、不读库写库、不用全页百分号正则猜数据。
- `06_开发技能_Develop_Skills/skills/parse_disclosure.py`：L3-ICD-03 解析分流从「仅 JSON」扩展为「`json`→aia_json_parser；`html` 且 `insurer=CTF`→ctf_html_parser；其余→UNSUPPORTED_FORMAT」；结构异常统一捕获 `AiaParseError`/`CtfParseError` 并写 `STRUCTURE_MISMATCH`。
- `09_测试与调试_Test_and_Debug/tests/fixtures/ctf_fixture.html`（新）：脱敏 fixture（无真实产品名）。
- `09_测试与调试_Test_and_Debug/tests/test_t005_parse.py`（新）：9 组确定性测试。
- `README.md`、`02_配置项目_Configure_Project/settings.json`：反映 T005 能力（skills 增 `ctf_html_parser`，status/stage 更新）。
- `07_接入记忆_Integrate_Memory/raw_data/CTF/5/{hash}.html`（受控真实快照）与 `data/icd.db`（受控真实验证库）。

**二、真实 DOM 分析（先抓取，后实现；非旧计数）**

- `--fetch 5`（首次因本机 Python 默认 CA 缺中间证书报 `SSLCertVerificationError`，加 `SSL_CERT_FILE=/etc/ssl/cert.pem` 后成功，同 T004 已知环境问题）。
- HTTP `200`，`final_url=https://www.ctflife.com.hk/en/support/important-information/fulfillment-ratios-dividends`，`content_hash=c23e4c85c58014b1427b8e64953e5976fffc407317a0a7d2468d85d0caccb98a`，`content_length=1015616` 字节，页面 `<html lang="en">`、UTF-8。
- 目标段落 `Fulfillment Ratios of Dividends/Bonuses`（`<h3>`）内有 **70 张产品表格**；稳定锚点：产品容器 `div.tableStyleRatio__container` → `<p class="...fzBold">`（产品名）→ `table.tableStyleRatio`；表头 3 层（`Type`/`Policy Currency` 各 `rowspan=3`，报告年度与 `Policy Year (Policy Effective in)` 各 `colspan=11`，第三层 11 个观察期标签 `1(2024)`…`10(2015)`、`11+(Before 2014)`）。
- 数据行关键特征：指标单元格带 `rowspan`（Annual/Terminal Dividends、Policy Value rowspan=2；Reversionary/Terminal Bonus rowspan=3，按 USD/HKD/CNY 多币种分组）；个别值单元格 `colspan=11`（“No policy has reached…”）；个别 `rowspan=3` 指标实际只有 2 个币种行（HTML 作者超填 rowspan，按实际行数处理）。页面另有 `Total Cash Value Ratio` 段落（source_id=6 的 TCV 口径）与导航/快速跳转 `<select>`，均不属于 `fulfillment_ratio`，已按段落作用域排除。

**三、标准化口径（均落入既有 Schema，无新增 Gate）**

- 指标：`Annual Dividends→AD`、`Terminal Dividends→TD`、`Reversionary Bonus→RB`、`Terminal Bonus→TB`；官网第五/第六口径 `Policy Value`、`Special Bonus` → `OTHER`，`metric_type_raw` 原样保存原文（`Policy Value`/`Special Bonus`），不与 AD/TD/RB/TB 合并。
- 币种：`scope_currency_raw` 保存 `USD`/`HKD`/`CNY` 原文，不拆分。
- 观察期：`1(2024)` → `observation_year_raw='1(2024)'`、`observation_year=2024`；`11+(Before 2014)` → `observation_year_raw='11+(Before 2014)'`、`observation_year=NULL`（开放区间，不虚构单年）。观察期标签含“保单年度 N + 生效年 YYYY”两部分，完整标签保留在 `observation_year_raw`，括号内日历年写入整数 `observation_year`——与 AIA 的 `Before 2015→NULL` 语义一致，Schema 可无损表达，无需 Gate。
- 值：数字百分比沿用 T004 换算小数比率；非数值占位（`Closed to Sales`/`Not yet launched`/`Zero Bonus`/`No Termination`/`No Policy`/`No policy has reached…`）保留原文、`normalized_value=NULL`，源级结果 `PARTIAL + VALUE_UNPARSEABLE`。`colspan=11` 值单元格按 colspan 传播到全部 11 个观察期列（各一条保留原文、NULL 记录）。

**四、fixture 自测（脱敏，不联网）**

- `python3 -m py_compile`（10 个 .py）→ 退出码 0。
- `python3 09_测试与调试_Test_and_Debug/tests/test_t005_parse.py` → 退出码 0，`✅ ALL CHECKS PASSED`（9 组）。
  - fixture 3 产品 20 记录（= 明确业务单元格之和：Alpha AD 4 + TD 4 + Beta RB 8（rowspan=2 两币种）+ Policy Value colspan=4 → 4 + 空表 0），非“数量大于零”式断言。
  - 覆盖：≥2 产品、AD/TD/RB/OTHER 四类指标、跨年份、多层表头、rowspan/colspan、脚注/非数值值、不可解析值、空表、结构漂移（缺段落/缺表头/观察期表头异常 → `CtfParseError`）、零产品/零业务记录 → `ZERO_RECORD`、重复执行幂等、事务回滚（坏记录 → 0 残留行）。
  - 逐条断言原文与标准值：`100%→1.0`、`94%→0.94`、`112%→1.12`、`109%→1.09`、`4+(Before 2021) 80%→0.8 且 observation_year=NULL`、`Closed to Sales→NULL 保留原文`、Policy Value colspan 传播 4 观察期。
  - 段落作用域：TCV 段落产品、导航 `<select>`、无关 `<table>`、HTML 注释一律不产生记录。
- 全量旧测试无回归：`test_t004_parse.py` 退出 0；`test_integration.py`（T002+T003）退出 0。测试全程 `--db-path`/`--raw-data-root` 指向 tempfile，不污染默认库。

**五、真实网络验证（与 fixture 分开）**

- `--fetch 5`（`SSL_CERT_FILE=/etc/ssl/cert.pem`）→ 退出 0；`--parse 5` → 退出 0。
- `--parse 5` 结果：`report_year=2025`、`product_count=70`、`records_written=1969`、`value_unparseable=1602`、`parse_status=PARTIAL`、`error_code=VALUE_UNPARSEABLE`、`run_id=3`。
- 数据库计数（`WHERE run_id=3`）：1969 条；指标 `AD 572 / TD 748 / RB 264 / TB 253 / OTHER 132`（`metric_type_raw`：`Annual Dividends 572 / Terminal Dividends 748 / Reversionary Bonus 264 / Terminal Bonus 253 / Policy Value 121 / Special Bonus 11`）；币种 `USD 1342 / HKD 506 / CNY 121`；数值化 367、不可解析 1602；`observation_year=NULL` 179（= 179 数据行 × 1 个 `11+(Before 2014)` 列）。
- 官网原文 → 数据库行抽查（逐字比对 /tmp 同哈希 HTML）：
  1. `Leisure Life Insurance Plan` · Annual Dividends · USD · `11+(Before 2014)` → 官网 `99%` → DB `raw_value='99%'`、`normalized_value=0.99`、`observation_year=NULL`。
  2. `Glorious Life` · Policy Value · USD · `1(2024)` → 官网 `Closed to Sales` → DB `metric_type=OTHER`、`metric_type_raw='Policy Value'`、`raw_value='Closed to Sales'`、`normalized_value=NULL`。
  3. `ComboPro Insurance Plan` · Special Bonus · USD · `3(2022)` → 官网 `Zero Bonus` → DB `metric_type=OTHER`、`metric_type_raw='Special Bonus'`、`normalized_value=NULL`。
  4. `Glorious Life` · Annual Dividends · HKD · `11+(Before 2014)` → 官网 `97%` → DB `normalized_value=0.97`。
- 每条记录可经 `run_id=3` 反查：`final_url`、`http_status=200`、`fetched_at=2026-09-03T09:44:23.433Z`、`content_hash=c23e4c85…`、`snapshot_path=raw_data/CTF/5/{hash}.html`。重复 `--parse 5` 幂等：仍 1969 行，`fulfillment_ratio` 总计 3542（AIA 1573 + CTF 1969）。

**六、范围与合规**

- 未改 `source_registry.json`、`data_contract.md`、`流程设计.md`、T001-T004 任务书、`agent.yaml`；未写 ICD 外路径；未 Git 提交；未自行标 ACCEPTED。
- 无 Schema 变更：CTF 真实结构（双维度观察期标签 `N(YYYY)`、`Policy Value`/`Special Bonus` 口径、多币种 rowspan）均可由既有 `metric_type(OTHER)` + `metric_type_raw` + `scope_currency_raw` + `observation_year_raw/observation_year` 无损表达，故未触发重大决策 Gate。
- 环境说明：真实抓取需 `SSL_CERT_FILE=/etc/ssl/cert.pem`（本机 Homebrew openssl@3 CA 为空，与 T004 相同；非代码缺陷）。

**七、状态**

建议 `SUBMITTED`，待 Codex 审计。

## Codex 独立审计 · ACCEPTED · 2026-09-03

- Codex 独立复跑 T005、T004、T002+T003 三套测试，全部退出码 0。
- 独立直查真实库：CTF run 共 1969 行，无空产品名/指标/币种/观察期、无自然业务键重复；`parse_result=('PARTIAL',1969,'VALUE_UNPARSEABLE')`；SQLite integrity 与外键检查通过。
- 真实证据链、70 产品、AD/TD/RB/TB/OTHER 分离、USD/HKD/CNY、开放观察期、rowspan/colspan、事务回滚和重复解析均符合任务书，T005 正式放行。
