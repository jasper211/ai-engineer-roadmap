# ICD Agent · 保司自主披露数据采集

采集香港持牌保险公司在**自己官网**公开披露的两类合规数据：**分红实现率**（Fulfillment Ratio，GN16/GL16依据）+ **RBC风险为本资本披露声明**（Disclosure Statement，含偿付能力充足率，2025-08-08 IA通函依据），标准化后供下游项目查询。

首要消费方是U020"月度行情热点解读"项目模块3（联动影响分析），产出设计为通用只读接口，为未来其他项目留出接入空间。

## 这是什么、不是什么

- 不是U020项目的一部分，是独立的FDE项目子项目，物理隔离
- 不是HKIA项目（`FDE项目/HKIA`）的扩展——HKIA现有架构是"查询已ETL好的IA官方统计"，ICD是"多站点抓取+多格式解析各险企自己的披露页面"，工程形态不同，详见需求定义"零"节
- 数据来源是10+家险企各自的官网（不是IA官方聚合页——那两个聚合页都被Cloudflare拦截，已验证）

## 快速开始

```bash
# 结构化项目状态（agent_id/version/stage/险企数/源数/access_status分布/数据库路径）
python3 04_定义Agent_Define_Agent/agents/agent.py --status

# 严格校验配置（非法JSON/重复险企/未知险企引用/UNVERIFIED带URL 等一律非零退出）
python3 04_定义Agent_Define_Agent/agents/agent.py --validate-config

# 初始化 SQLite（幂等：建12张表 + 导入12家险企/22条数据源/11条错误代码；旧库自动做 pre-v5.bak 备份并幂等迁移）
python3 04_定义Agent_Define_Agent/agents/agent.py --init-db

# 抓取单个数据源（写快照 raw_data/{insurer}/{source}/{hash}.{ext} + fetch_run 运行记录；需先 --init-db）
python3 04_定义Agent_Define_Agent/agents/agent.py --fetch 1

# 抓取演练（只抓取并计算 SHA-256，不写快照、不写数据库）
python3 04_定义Agent_Define_Agent/agents/agent.py --fetch 1 --dry-run

# 解析最新成功抓取的快照（AIA JSON source_id=1 / CTF Life HTML source_id=5 / CLO HTML source_id=9 → fulfillment_ratio；Prudential General Insurance RBC PDF source_id=13（PRUGI）/ AIA Company Limited RBC PDF source_id=22（AIACO）→ rbc_statement；需先 --fetch）
python3 04_定义Agent_Define_Agent/agents/agent.py --parse 1
python3 04_定义Agent_Define_Agent/agents/agent.py --parse 5
python3 04_定义Agent_Define_Agent/agents/agent.py --parse 9
python3 04_定义Agent_Define_Agent/agents/agent.py --parse 13
python3 04_定义Agent_Define_Agent/agents/agent.py --parse 22

# 从官方索引快照确定性发现目标 RBC PDF 链接（只读，不写数据；source_id=12 为 AIA 监管披露索引）
python3 04_定义Agent_Define_Agent/agents/agent.py --discover 12

# 全量运行（L3-ICD-06）：按 source_id 顺序处理所有 is_active=1 的源，
# 单源失败隔离，生成运行摘要（JSON+Markdown）并更新 coverage_status
python3 04_定义Agent_Define_Agent/agents/agent.py --run-all

# 全量运行 · 确定性模式：跳过抓取，基于既有快照完成解析/汇总（不联网）
python3 04_定义Agent_Define_Agent/agents/agent.py --run-all --no-network
```

- 运行摘要默认写入 `07_接入记忆_Integrate_Memory/summaries/{run_id}.json` 与 `.md`（受控目录，run_id 唯一、不覆盖历史）；测试请用 `--summaries-root` 指向临时目录。
- `coverage_status` 按险企 × 披露类型反映最新真实结果（`FULL/PARTIAL/MISSING/BLOCKED/UNVERIFIED`），`parse_result=PARTIAL`（值不可数值化）仍计为覆盖成功，不误判为覆盖缺失。

- 数据库默认写入 `07_接入记忆_Integrate_Memory/data/icd.db`（ICD 专属，与 `raw_data/` 快照隔离）。
- 原始快照默认写入 `07_接入记忆_Integrate_Memory/raw_data/{insurer}/{source}/{hash}.{ext}`。
- 测试请用 `--db-path`、`--raw-data-root` 指向临时目录，不污染默认数据库与快照目录。
- 当前状态：T004 已交付 AIA JSON 分红实现率解析与入库（--parse 1）；T005 已交付 CTF Life HTML 表格解析与入库（--parse 5）；T006 已交付中国人寿（海外）CLO HTML 分红实现率解析与入库（--parse 9）。`fulfillment_ratio` 采用 `AD/TD/RB/TB/TCV/OTHER` 指标枚举 + `metric_type_raw` + `scope_currency_raw`，四类指标与币种分组无损保存；`observation_year_raw` 原样保存官网观察期标签（AIA `Before 2015`、CTF `11+(Before 2014)`、CLO `Policy Year 10+ (2014 or before)` 均写 `observation_year=NULL`，不虚构单年），存在不可数值化观测项时 `parse_result` 写 `PARTIAL` + `VALUE_UNPARSEABLE` 并保留原文。CTF HTML 解析基于表格层级/表头/rowspan/colspan 语义恢复记录（`skills/ctf_html_parser.py`），官网 `Policy Value`/`Special Bonus` 映射到 `OTHER` 且原文保留在 `metric_type_raw`。CLO HTML 解析基于 `<script>` 内嵌 JS 数组（`policyYears`/`dataSets1`/`dataSets2`/`dataSets3`）确定性提取（`skills/clo_html_parser.py`），`Annual Dividend`→`AD`、`Terminal Dividend`→`TD`、`Accumulated Interest`→`OTHER`，并排除「Historical Crediting Interest Rate for Universal Life Plans」万能寿险结算利率静态表。T007 已交付 Prudential General Insurance 香港（PRUGI，一般保险，与寿险 PRU 为不同持牌实体）RBC 披露声明 PDF 解析与入库（--parse 13）：`skills/pdf_text.py`（pdfplumber 文本/表格提取 + PDF 签名/文字层校验，空文字层→PDF_NO_TEXT，不 OCR）、`skills/pru_rbc_parser.py`（Capital adequacy / Ratio of capital base to prescribed capital amount 语义邻域解析，290%→2.90、年度、币种、法律主体原文（`legal_entity_name_raw`）、可选金额，不全文百分号正则猜数）、`tools/rbc_writer.py`（rbc_statement 事务写入 + parse_result，幂等/回滚）。金额按披露明示「in HKD thousands」标度折算绝对 HKD 入库（`capital_base`/`prescribed_capital_amount`），披露原文保留在 `capital_base_raw`/`prescribed_capital_amount_raw`、单位与标度保留在 `amount_unit_raw`/`amount_scale`，完整子风险分解保留在 `risk_breakdown_json`（不写不兼容枚举）。SQLite 用 `PRAGMA user_version` 做 schema 版本检测（v0.5=4，v0.6=5），旧库 `--init-db` 自动做 `.pre-v4.bak`/`.pre-v5.bak` 备份并幂等迁移（修正主体归属、移动快照、删除错误业务行、索引源 format pdf→html）。其余 HTML 源（AXA/YFL/SUN/FWD/BOC）与其余 RBC 源解析尚未接入。T008 已交付 AIA Company Limited（AIACO，与寿险 AIA International Limited 为不同持牌实体）2024 英文 RBC 披露声明：`skills/rbc_parser.py`（可复用 Capital Adequacy 语义邻域解析，304%→3.04、法律主体原文、金额标度、无损风险分解）、`skills/rbc_index_discovery.py`（官方索引→2024 英文 Disclosure Statement PDF 确定性发现 + 目标文件名消歧），`pru_rbc_parser.py` 降级为向后兼容垫片；source_id=12 现为 AIA 官方监管披露索引（发现源，format=html），发现的最终 PDF 以独立 AIACO rbc 源（source_id=22）登记，形成索引→PDF 两段证据链；`--discover 12` 可从索引快照确定性复现发现结果。T009 已交付 L3-ICD-06 全量运行闭环：`--run-all`（`--no-network`）按 source_id 顺序处理所有 active 源，单源失败隔离，`BLOCKED/UNVERIFIED/requires_browser` 跳过、未接入源标 `unsupported`、rbc 索引源执行发现而非解析；聚合阶段 `skills/run_all.py` + `tools/coverage_writer.py` 按自然键 UPSERT `coverage_status`（新增 `last_attempt_at`/`last_success_at`/`last_error_code`/`last_error_message` 列，schema user_version 5→6），`skills/summary_writer.py` 写入唯一 run_id 的 JSON+Markdown 摘要到 `summaries/`。

## 架构

按 [Agent搭建SOP v1.2](../../05_Agent库/草稿/Agent搭建SOP_v1.2.md) 的01-11编号骨架组织。

## 快速上手（Codex）

1. 先读 [`01_初始化项目_Initialize_Project/需求定义.md`](01_初始化项目_Initialize_Project/需求定义.md) 全文——第七节"真实实测发现"是本次交接最有价值的部分（10家险企逐一实测的真实URL/格式/关键数字），直接复用，不需要重新摸索
2. 需求定义已确认，直接从SOP第2步"流程设计"开始
