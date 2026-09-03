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

# 初始化 SQLite（幂等：建12张表 + 导入10家险企/21条数据源/11条错误代码）
python3 04_定义Agent_Define_Agent/agents/agent.py --init-db

# 抓取单个数据源（写快照 raw_data/{insurer}/{source}/{hash}.{ext} + fetch_run 运行记录；需先 --init-db）
python3 04_定义Agent_Define_Agent/agents/agent.py --fetch 1

# 抓取演练（只抓取并计算 SHA-256，不写快照、不写数据库）
python3 04_定义Agent_Define_Agent/agents/agent.py --fetch 1 --dry-run

# 解析最新成功抓取的快照（AIA JSON source_id=1 / CTF Life HTML source_id=5 → fulfillment_ratio + parse_result；需先 --fetch）
python3 04_定义Agent_Define_Agent/agents/agent.py --parse 1
python3 04_定义Agent_Define_Agent/agents/agent.py --parse 5
```

- 数据库默认写入 `07_接入记忆_Integrate_Memory/data/icd.db`（ICD 专属，与 `raw_data/` 快照隔离）。
- 原始快照默认写入 `07_接入记忆_Integrate_Memory/raw_data/{insurer}/{source}/{hash}.{ext}`。
- 测试请用 `--db-path`、`--raw-data-root` 指向临时目录，不污染默认数据库与快照目录。
- 当前状态：T004 已交付 AIA JSON 分红实现率解析与入库（--parse 1）；T005 已交付 CTF Life HTML 表格解析与入库（--parse 5）。`fulfillment_ratio` 采用 `AD/TD/RB/TB/TCV/OTHER` 指标枚举 + `metric_type_raw` + `scope_currency_raw`，四类指标与币种分组无损保存；`observation_year_raw` 原样保存官网观察期标签（AIA `Before 2015`、CTF `11+(Before 2014)` 均写 `observation_year=NULL`，不虚构单年），存在不可数值化观测项时 `parse_result` 写 `PARTIAL` + `VALUE_UNPARSEABLE` 并保留原文。CTF HTML 解析基于表格层级/表头/rowspan/colspan 语义恢复记录（`skills/ctf_html_parser.py`），官网 `Policy Value`/`Special Bonus` 映射到 `OTHER` 且原文保留在 `metric_type_raw`。其余 HTML 源（AXA/YFL/SUN/FWD/BOC/CLO）、PDF/RBC（T006）解析尚未接入。

## 架构

按 [Agent搭建SOP v1.2](../../05_Agent库/草稿/Agent搭建SOP_v1.2.md) 的01-11编号骨架组织。

## 快速上手（Codex）

1. 先读 [`01_初始化项目_Initialize_Project/需求定义.md`](01_初始化项目_Initialize_Project/需求定义.md) 全文——第七节"真实实测发现"是本次交接最有价值的部分（10家险企逐一实测的真实URL/格式/关键数字），直接复用，不需要重新摸索
2. 需求定义已确认，直接从SOP第2步"流程设计"开始
