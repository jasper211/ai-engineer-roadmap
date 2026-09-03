# ICD-T001 · 流程与数据契约设计任务书

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：CHANGES_REQUESTED  
> 派发日期：2026-09-03

## 一、任务目标

在不编写采集和解析业务代码的前提下，完成 ICD 的工程设计基线，使后续 JSON、HTML、PDF 三类实现可以按同一数据契约开发和验收。

## 二、开始前必须阅读

1. `../01_初始化项目_Initialize_Project/需求定义.md`全文，尤其第七节真实实测发现。
2. `../README.md`。
3. `../02_配置项目_Configure_Project/settings.json`。
4. `../../../05_Agent库/草稿/Agent搭建SOP_v1.2.md`的第2步流程设计、第4步模块边界、第5步真实数据验证原则。

## 三、允许修改范围

- `03_规划项目结构_Plan_Project_Structure/流程设计.md`（新建）
- `03_规划项目结构_Plan_Project_Structure/data_contract.md`（新建）
- `02_配置项目_Configure_Project/source_registry.json`（新建）
- `任务日志.md`中的“执行方回执区”（只追加，不得改审计结论）
- 本任务书的“执行回执”章节（只追加）

不得修改其他项目，不得修改 HKIA 或 U020，不得提前实现 `.py` 文件，不得下载或提交大体积原始文件。

## 四、交付要求

### A. 流程设计

在`流程设计.md`中定义至少以下 L3：

- `L3-ICD-01`：读取并校验数据源注册表
- `L3-ICD-02`：HTTP抓取与原始证据固化
- `L3-ICD-03`：按JSON/HTML/PDF分流解析
- `L3-ICD-04`：标准化及质量门禁
- `L3-ICD-05`：事务性写入SQLite
- `L3-ICD-06`：生成运行摘要与覆盖状态

每个 L3 必须说明输入、输出、对应 skill/tool、失败语义及是否允许继续处理其他数据源。流程图和表格必须一致。

### B. 数据契约

在`data_contract.md`中给出可直接转为 SQLite DDL 的设计，至少覆盖：

- 险企规范实体及官网原始名称
- 数据源和URL版本
- 抓取运行、HTTP状态、抓取时间、内容哈希、原始快照相对路径
- 产品及官方原始产品名称
- 分红实现率：报告年度、观察年度、红利类型 `AD/TD/TCV/REVERSIONARY/OTHER`、原始值、标准化数值、单位
- RBC：报告年度、偿付能力比率、资本基础、规定资本额、币种及可选风险分解
- 解析状态、覆盖状态、错误代码
- 可追溯到一次抓取和一个原始证据

必须明确：主键/唯一约束、外键、空值语义、百分比统一存储方式、重复抓取幂等策略、历史版本保留策略，以及产品名称变化但尚无产品ID映射时如何处理。

### C. 数据源注册表

在`source_registry.json`中录入需求定义第7节涉及的10家险企。每家公司可以有多个数据源条目，字段至少包含：

- `insurer_code`、中英文名称
- `disclosure_type`
- `entry_url`
- `format`
- `access_status`
- `parser_hint`
- `requires_browser`
- `evidence_basis`
- `last_verified_at`

未实际验证的 RBC URL 不得猜测。可以使用索引页或将 URL 设为 `null`，但必须明确状态为 `UNVERIFIED`。

### D. 证据和失败规则

设计必须做到：

- HTTP成功但页面结构不符时标记结构失败，不得写成“无数据”。
- 零记录解析是硬失败，除非注册表明确允许空数据。
- 原始快照先成功落盘，再允许标准化结果入库。
- 一家险企失败不得默认回滚其他险企，但同一来源的写入必须原子化。
- 日志不得包含凭证、Cookie或完整请求头。

## 五、验收标准

Codex 将逐项审计：

1. 三个要求文件存在，JSON可被标准库解析。
2. 注册表恰好覆盖需求定义中的10家目标险企，没有虚构已验证URL。
3. L3流程输入输出与数据表之间无断点。
4. AD、TD、TCV及永明“归原红利”等口径没有被错误合并。
5. `report_year`与比率对应的`observation_year`没有混为一列。
6. 每条业务记录可反查抓取运行、真实URL、抓取时间、内容哈希和原始快照。
7. 幂等、历史版本、部分失败、零记录和结构漂移均有明确规则。
8. 没有修改允许范围之外的文件。
9. 执行回执包含实际运行的 JSON 校验命令、修改文件清单和未决问题。

任一第2、4、5、6、8项失败，整体不得标记 `ACCEPTED`。

## 六、执行回执

由 vscode-deepseek 完成后追加，至少包含：

- 完成摘要
- 修改文件清单
- 自测命令及原始结果摘要
- 与任务书不同之处及原因
- 已知限制/未决问题
- 建议任务状态：`SUBMITTED`或`BLOCKED`

---

### 执行回执（vscode-deepseek · 2026-09-03）

#### 完成摘要

按任务书完成 ICD-T001 工程设计基线，未编写任何采集/解析/入库实现（无 `.py` 新增）。产出三份设计文件：

- **流程设计.md**：6 个 L3（L3-ICD-01~06），Mermaid 流程图与 L3 明细表一致，每个 L3 含输入/输出/对应 skill-tool/失败语义/是否继续处理其他源。
- **data_contract.md**：12 张表 SQLite DDL（可 `executescript` 直接建库），覆盖任务书 B 项全部 8 类需求，明确主键/唯一约束/外键/空值语义/百分比统一存储/重复抓取幂等/历史版本保留/产品名漂移处理。
- **source_registry.json**：10 家险企 21 条数据源（10 履行率 + 10 RBC + 1 TCV），UNVERIFIED 一律 `entry_url`/`format = null`，未虚构任何已验证 URL。

#### 修改文件清单

1. 新建 `FDE项目/ICD/03_规划项目结构_Plan_Project_Structure/流程设计.md`
2. 新建 `FDE项目/ICD/03_规划项目结构_Plan_Project_Structure/data_contract.md`
3. 新建 `FDE项目/ICD/02_配置项目_Configure_Project/source_registry.json`
4. 追加 `FDE项目/ICD/任务日志.md`（执行方回执区，仅追加）
5. 追加 `FDE项目/ICD/03_规划项目结构_Plan_Project_Structure/ICD-T001_执行任务书.md`（本回执，仅追加）

未修改允许范围外任何文件（未触碰 HKIA、U020、其他项目）。

#### 自测命令及原始结果摘要

命令：`python3` 内联脚本，用标准库 `json` 解析 source_registry.json；用 `sqlite3` 内存库 `executescript` 执行 data_contract.md 中 DDL / 错误码种子 / 索引三个 SQL 块，并做结构断言。

原始结果（关键行）：

```
== source_registry.json 校验 ==
insurers: 10 (唯一 10) | sources: 21
fulfillment_ratio=10 rbc=10 tcv=1
access_status: {'OPEN': 10, 'UNVERIFIED': 9, 'PARTIAL': 1, 'BLOCKED': 1}
== data_contract.md DDL 校验 ==
SQL块: 执行3 跳过1 | 建表12: [coverage_status, data_source, error_code, fetch_run, fulfillment_ratio, insurer, insurer_official_name, parse_result, product, product_alias, rbc_risk_component, rbc_statement]
ALL CHECKS PASSED
```

首轮自测曾捕获 1 处不一致（CTF TCV 条目 `UNVERIFIED` 却带拼接 URL），已修复为 `entry_url`/`format = null` 并重测通过。

#### 与任务书不同之处及原因

1. **新增 `total_cash_value_ratio` 披露类型 + CTF 一条 TCV 源**：任务书 B 项 `dividend_type` 含 `TCV`，需求定义 §7.2 明确 CTF 有独立 TCV 页面；属补充而非偏离，且该条标 `UNVERIFIED`。
2. **数据源总数 21 而非"10 家各 1 条"**：任务书明确"每家公司可以有多个数据源条目"；履行率与 RBC 是两类数据，每家至少 2 条。
3. **补充 `allows_empty` 字段**：任务书 D 项"零记录是硬失败除非注册表明确允许空数据"需要该字段承载，属契约字段补齐。
4. **URL 规范化**：§7.2 裸域名补 `https://`（及 `www`），已在注册表 `description` 声明，不改变证据来源。
5. **Manulife 履行率 `format = null`**：被 Akamai 拦截未能确认格式，不猜 `html`。

#### 已知限制/未决问题

1. 8 家 RBC URL 为 `UNVERIFIED`（需求定义遗留，任务书禁止猜测），需后续按 investor-relations 路径实测补录。
2. 宏利全站 Akamai 拦截，履行率 + RBC 均不可达；需求定义已明确本次不引入浏览器自动化。
3. 保诚履行率 PDF 是 IRR 数据（"第20保单年度实际平均总内部回报率"），非标准履行率格式；是否独立建模（当前 `dividend_type=OTHER` 兜底）待解析阶段确认。
4. `insurer.name_en` 为常用英文名，建议与 IA 持牌险企名录核对后作为权威名。
5. 本轮为纯设计任务，未做真实网络复验（URL 均引自需求定义 §7 已实测结果）；真实数据验证属 SOP 第5步，留待实现后执行。

#### 建议任务状态

`SUBMITTED`

## 七、Codex 审计与返工

### Round 1 · 2026-09-03 · CHANGES_REQUESTED

独立审计复现失败：当前`fetch_run.content_hash NOT NULL`导致HTTP/网络失败记录无法按流程要求落库。

返工必须满足：

1. 成功抓取必须同时具有非空`content_hash`和`snapshot_path`；失败抓取允许二者为空，并由SQLite `CHECK`约束保证。
2. 失败尝试不得依靠空哈希做幂等；同源同内容的成功抓取仍须防重复。
3. 增加并执行六类插入测试：成功合法、成功缺哈希非法、成功缺快照非法、HTTP失败无证据合法、网络失败无HTTP状态合法、同源同内容成功重复非法。
4. 澄清临时快照落盘、哈希计算、原子重命名为最终哈希路径的真实顺序。
5. 将修正摘要和原始测试结果追加到本节，不得覆盖首轮回执。
