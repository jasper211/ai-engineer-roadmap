# ICD-T008 · AIA RBC 官方索引发现、PDF 解析与入库

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：DISPATCHED  
> 派发日期：2026-09-03

## 目标

完成需求成功标准中的第二家 RBC：从注册表 source_id=12 的 AIA 官方监管披露索引，确定 2024 英文 Disclosure Statement PDF 的真实 URL 与法律主体，形成索引发现→PDF 抓取→文本解析→标准化→SQLite 入库的可审计闭环。需求材料中的 304% 仅为人工锚点，结果必须由当前真实 PDF 独立提取，不得写死。

## 允许范围

- ICD 内 source registry、数据契约与必要的主体种子修正
- PDF 索引发现、下载解析、RBC 通用解析/写入工具
- agent CLI 接入、fixture、测试、README/settings、证据材料、任务书与任务日志

禁止修改 ICD 外项目；禁止 Git 提交；禁止读取或记录密钥；不得引入浏览器自动化。若出现无法从官方页面确认 PDF、核心口径不可无损表达或必须改变已确认业务边界的情况，停止并提出 Gate。

## 功能要求

1. 先抓取 source_id=12 官方索引页并保留证据，解析链接时必须限定官方域名、2024 报告期、英文 Disclosure Statement 语义，不得凭搜索结果或文件名猜测。
2. 索引页与最终 PDF 是两段证据链：记录索引 final_url/HTTP/哈希/快照，以及 PDF final_url/HTTP/哈希/快照；数据库记录必须可回查最终 PDF。若现有 fetch_run/source 模型不足以表达两段链路，提出最小可审计方案。
3. 读取 PDF 的 `Authorized insurer's name`。当前 AIA 代码代表 AIA International Limited；若 PDF 为 AIA Company Limited 或其他法律主体，按 T007 已确认政策建立独立、语义明确的 insurer_code，修正 source 归属并迁移快照，不得混淆。
4. 泛化现有 Prudential 专用解析器为可复用 RBC Capital Adequacy 解析能力，保留针对不同版式的受限适配；不得复制一套仅改名字的硬编码解析器，不得全文任意百分号命中。
5. 提取 report_year、legal_entity_name_raw、solvency_ratio/raw、currency、capital_base/raw、prescribed_capital_amount/raw、amount_unit_raw/scale，以及可无损表达的风险分解；不能无损映射的分解保留 JSON，不强塞枚举。
6. 结构漂移、PDF 链接歧义、错误年度、法律主体不一致、重复比率、非 PDF、无文字层、零记录均需确定性失败或明确状态测试；事务、幂等、迁移补偿与既有 T002-T007 回归必须通过。

## 验收标准

1. 真实官方索引可重复定位唯一的 2024 英文 PDF；索引和 PDF 的 URL、HTTP 状态、哈希、字节、快照和抓取时间齐备。
2. 真实 PDF 文字层可用，记录页数与字符数；至少逐字核对法律主体、304% 原文/3.04 标准值及一项金额或单位至数据库。
3. 最终记录法律主体编码与 PDF 原文一致，不复用不同持牌实体代码；默认库旧数据安全迁移，integrity/FK/自然键/快照路径均正确。
4. 解析器证明不是写死 304%，fixture 至少覆盖另一合法比率、跨行断词、歧义和结构漂移。
5. 全量 T002-T007 无回归；测试不污染默认数据库；执行回执列明命令、退出码、计数、证据与变更范围。

## 执行回执

由 vscode-deepseek 完成后追加；不得自行标记 ACCEPTED。

### 2026-09-03 / 2026-09-04（UTC）· vscode-deepseek · ICD-T008 回执

**建议状态：`SUBMITTED`**（待 Codex 审计；不自行标 ACCEPTED）。

#### 一、目标达成

完成需求成功标准中的第二家 RBC：从注册表 source_id=12 的 AIA 官方监管披露索引确定 2024 英文 Disclosure Statement PDF 的真实 URL 与法律主体，形成「索引发现 → PDF 抓取 → 文本解析 → 标准化 → SQLite 入库」可审计闭环。304% 仅为人工锚点，结果由当前真实 PDF 独立提取，未写死。

#### 二、两段真实证据链

**段 1 · 官方索引（source_id=12）· fetch_run.run_id=7**
- `--fetch 12` EXIT=0、HTTP 200、243320 字节
- final_url = `https://www.aia.com/en/investor-relations/overview/regulatory-disclosures`
- SHA-256 = `0a581e8a5f26a17e774592fb2c8c650ac4a83ec8d78aa1d5cb74649063e90972`
- 快照 = `raw_data/AIA/12/0a581e8a….html`

**段 2 · 发现 → 最终 PDF（source_id=22）· fetch_run.run_id=8**
- `--discover 12` EXIT=0、candidate_count=3、filename_hint=`AIA Co Disclosure Statement 2024_Eng.pdf`
- 消歧定位 PDF URL = `https://www.aia.com/content/dam/group-wise/en/docs/investor-relations/2025/AIA%20Co%20Disclosure%20Statement%202024_Eng.pdf`
- `--fetch 22` EXIT=0、HTTP 200、`%PDF-1.6`、2678448 字节
- SHA-256 = `8061102051f14ae91729d12eac138e0f6e573a42ee183c8f3a406958075b696b`
- 快照 = `raw_data/AIACO/22/80611020….pdf`；文字层 12 页、14186 字符（非扫描件，pdfplumber 直接提取，无 OCR）

#### 三、法律主体确认（功能要求 3）

- PDF 第 3 页「(a) Authorised insurer's name」= `AIA Company Limited (the "Company")`
- 剥离定义性括号后 `legal_entity_name_raw = "AIA Company Limited"`
- ≠ 注册表 `AIA`（AIA International Limited，寿险）；按 T007 已确认主体隔离政策建立独立 **`insurer_code=AIACO`**（AIA Company），`name_en=AIA Company Limited`
- 附带核实（非任务目标）：AIAI 212%、AIAE 457%，三者确为不同持牌实体

#### 四、解析入库结果（rbc_statement）

- `--parse 22` EXIT=0、run_id=8、report_year=2024、records_written=1、parse_status=OK
- DB 直查单行：`('AIACO', 8, 2024, 'AIA Company Limited', 3.04, '304%', 70993766000.0, '70,993,766', 23371785000.0, '23,371,785', 'HKD', 'in HKD thousands', 'thousands')`
- 三处 PDF 原文 → DB 逐字核对：
  1. `Ratio of capital base to prescribed capital amount 304%` → `'304%'` / `3.04`
  2. `Capital base 70,993,766`（Unit: in HKD thousands）→ `70,993,766,000.0`（原文 `'70,993,766'`）
  3. `Prescribed capital amount 23,371,785` → `23,371,785,000.0`（原文 `'23,371,785'`）
- `risk_breakdown_json`：prescribed_capital_components=30 行、capital_base_components=5 行，无损保留原文与标度（`unit: in HKD thousands`）

#### 五、一致性 / 幂等 / 证据回查

- `PRAGMA integrity_check` = ok；`PRAGMA foreign_key_check` = []
- 自然键 `(insurer_code, report_year, run_id)` 重复 = 0；AIACO rbc 行 = 1（重复 `--parse 22` 幂等仍 1 行）
- 迁移：`--init-db` user_version 4→5，`icd.db.pre-v5.bak` 备份生成；`data_source[12]` format `pdf`→`html`；新增 AIACO 主体与 AIACO rbc PDF 源（12 险企 / 22 源）
- rbc_statement(AIACO).run_id=8 → fetch_run.final_url / http_status=200 / content_hash / snapshot_path 均可回查最终 PDF；索引段 run_id=7 独立保留为发现证据

#### 六、确定性测试（不联网，tempfile，不污染默认库）

| 命令 | 退出码 | ✅ 断言 |
|---|---|---|
| `python3 -m py_compile`（全部 .py） | 0 | — |
| `test_integration.py`（T002+T003） | 0 | 156 |
| `test_t004_parse.py` | 0 | 84 |
| `test_t005_parse.py` | 0 | 71 |
| `test_t006_parse.py` | 0 | 64 |
| `test_t007_parse.py` | 0 | 119 |
| `test_t008_parse.py` | 0 | 65 |

全量 T002-T008 六套测试 **EXIT=0**、✅ 合计 559 断言、❌ 0。T008 覆盖：不写死 304%（另有 212%/457%/290% 泛化断言）、跨行断词、重复候选歧义、结构漂移、错误年度、无文字层、非 PDF、英/美式 `Authorised/Authorized insurer's name` 与 `(the "Company")` 清洗、金额标度、官方域名/2024/英文/Disclosure Statement 索引约束、零匹配/歧义确定性失败、两段证据链回查、迁移 v0.5→v0.6、幂等/回滚、CLI `--discover`。

#### 七、命令与退出码（真实网络）

| 命令 | 退出码 | 关键结果 |
|---|---|---|
| `--init-db` | 0 | user_version=5，12 险企 / 22 源，迁移 actions |
| `--fetch 12` | 0 | HTTP 200 / 243320 B / hash `0a581e8a…` / run_id=7 |
| `--discover 12` | 0 | 3 候选 → 消歧定位 AIA Co PDF |
| `--fetch 22` | 0 | HTTP 200 / 2678448 B / `%PDF-1.6` / hash `80611020…` / run_id=8 |
| `--parse 22` | 0 | records=1 / 304%→3.04 / AIACO |

#### 八、变更范围

- 允许范围内：source registry（source_id=12 索引 format pdf→html；新增 AIACO 主体 + AIACO rbc PDF 源 source_id=22）、数据契约（rbc_statement 字段 T007 已建立）、`rbc_parser.py` 泛化、`rbc_index_discovery.py`、agent CLI `--discover`、`fetch_recorder.get_source` 返回 `parser_hint`、fixture、测试、README/settings、证据材料、任务书与任务日志。
- 未改 ICD 外项目；未 Git 提交；未读取/记录密钥；未引入浏览器自动化。

#### 九、未决说明（供 Codex 复核，非阻断）

1. 并行执行观察：本工作区已存在早于本执行的 T008 实现（`rbc_parser.py`/`rbc_index_discovery.py`/fixtures/迁移/`--discover` 等），判断为并行/先前执行产物，采纳为唯一主线并补齐 `parser_hint` 返回、T008-13 `--discover` 测试、真实网络验证、README/settings 与回执。
2. http_fetcher UA 变更：www.aia.com（Akamai 边缘）对非浏览器 UA 挂起连接，改为浏览器 UA（无登录、无 Cookie、无凭证），仅影响 HTTP 抓取层，T002-T008 全量回归通过。
3. AIAI 212% / AIAE 457%：注册表 parser_hint 作索引歧义上下文标注，curl 独立核实成立，非本任务采集目标，未入库。

#### 十、状态

**建议 `SUBMITTED`**，待 Codex 审计；不自行标 ACCEPTED。真实验证证据见 `07_接入记忆_Integrate_Memory/T008_真实验证证据.md`。
