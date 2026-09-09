# ICD 接入 U20 模块3：完整规划、分析框架与承接说明

> 文档版本：v1.0  
> 形成日期：2026-09-09  
> 提供方：ICD（保司自主披露数据采集 Agent）  
> 承接方：U020「月度行情热点解读」模块3  
> 文档状态：HANDOFF_READY  
> 本次边界：完成规划、数据核验、接口设计、分析规则、测试与验收定义；本文件不直接修改 U20 源码。

## 1. 结论先行

ICD 已具备接入 U20 模块3并参与完整五维影响分析的工程条件。建议立即使用“模块1热点 + 模块2行情指标 + HKIA行业数据 + ICD履行率/RBC + 产品库可用部分”完成第一轮端到端测试，测试后再决定补充缺失保司或新数据源的优先级。

本次接入不是增加一张静态数据卡，而是把 ICD 变成模块3的受控证据源：任何引用 ICD 数字的结论都必须携带 Evidence ID、主体、统计期、来源 URL、快照哈希和覆盖限制，并通过 U20 现有证据契约校验。

当前数据足以支持内部测试和分析链路验收，但不能被表述为：

- 全市场无缺口覆盖；
- 当前 2026 年经营状态或未来预测；
- 基于披露中位数的跨公司优劣排名；
- 集团层面的偿付能力比较；
- 个别客户的产品建议或收益承诺。

## 2. 接入目标与不做事项

### 2.1 目标

1. 在模块3的行业、市场、保险公司、产品、客户五个维度中形成同一条可审计分析链。
2. 把月度驱动、季度行业佐证、年度保司/产品披露严格区分，避免时间尺度混用。
3. 将履行率用于解释历史非保证利益表现，将 RBC 用于解释特定法律主体在披露时点的资本缓冲背景。
4. 所有事实数字均可回到正式交换包、官方 URL 和原始快照。
5. 数据缺失、主体不匹配、产品无法映射时降级输出，不猜测、不模糊拼接。

### 2.2 本轮不做

1. 不把 ICD 直接连接到 U20 的生产数据库；U20 只消费经验证的只读交换包。
2. 不使用模糊字符串自动合并产品或法律主体。
3. 不以历史履行率直接推导未来分红。
4. 不以 RBC 比率直接推导公司信用评级、违约概率或集团实力。
5. 不因为产品库当前连接不可用而阻塞 ICD + HKIA 的首轮测试。
6. 不在测试前为追求数量继续扩张外部来源。

## 3. 已核验的现状基线

### 3.1 ICD 正式交换包

- 包 ID：`icd-exchange-v1-147a281d97570988`
- 契约版本：`1.0.0`
- 发布状态：`PARTIAL_COVERAGE`
- 履行率记录：13,039 条
- RBC 记录：8 条
- coverage 记录：23 条
- 消费者验收：`ACCEPTED`
- 验收错误：0
- 正式目录：`FDE项目/ICD/07_接入记忆_Integrate_Memory/exports/icd-exchange-v1-147a281d97570988`

U20 必须先运行 ICD 消费者验收器，成功后才可读业务文件：

```bash
python3 FDE项目/ICD/04_定义Agent_Define_Agent/agents/agent.py \
  --validate-export \
  FDE项目/ICD/07_接入记忆_Integrate_Memory/exports/icd-exchange-v1-147a281d97570988
```

正式包文件：

| 文件 | 用途 |
|---|---|
| `manifest.json` | 包 ID、契约版本、记录数、文件哈希、发布状态和消费者规则 |
| `fulfillment_ratio.jsonl` | 产品级历史履行率/分红实现率及原始证据 |
| `rbc_statement.json` | 法律主体级 RBC、资本基础、规定资本及风险拆分 |
| `coverage_status.json` | 各保司、各披露类型的覆盖与失败语义 |
| `health.json` | 生成时的数据健康状态 |

### 3.2 ICD 数据覆盖

履行率已覆盖 9 家：AIA、AXA、BOC、CLO、CTF、FWD、PRU、SUN、YFL。MAN 因官网防护阻断，明确标记 `BLOCKED`，不得伪装成无产品或 0。

RBC 已覆盖 8 个独立法律主体：

| ICD代码 | 法律主体 | 报告年 | 披露比率 |
|---|---|---:|---:|
| AIA | AIA International Limited | 2024 | 212% |
| AIACO | AIA Company Limited | 2024 | 304% |
| AXA | AXA China Region Insurance Company Limited | 2024 | 204% |
| BOC | BOC Group Life Assurance Company Limited | 2024 | 204% |
| FWD | FWD Life Insurance Company (Bermuda) Limited | 2024 | 199% |
| PRU | Prudential Hong Kong Limited | 2024 | 239% |
| PRUGI | Prudential General Insurance Hong Kong Limited | 2024 | 290% |
| SUN | Sun Life Hong Kong Limited | 2024 | 229% |

重要限制：AIA 与 AIACO、PRU 与 PRUGI 分别是不同法律主体。U20 不得按品牌名把它们合并，也不得把一般保险主体的 RBC 用于寿险产品结论。

### 3.3 HKIA 数据

U20 现有 HKIA 数据源可用，已核验健康状态：

- 主数据 59,516 条；
- 标准数据 5,022 条；
- 年度数据 7,097 条；
- 2025 provisional 数据 414 条；
- 财务数据 408 条；
- 合计 72,457 条；
- 快照指纹：`e927e89b96cecef7`；
- 可用指标 12 个。

模块3现已读取三条季度市场序列：

| 指标 | 2023Q1 | 2024Q1 | 2025Q1 | 2023Q1→2025Q1 | 2024Q1→2025Q1 |
|---|---:|---:|---:|---:|---:|
| 新造个人人寿业务年度化保费，百万港元 | 23,775.374 | 38,179.074 | 46,460.183 | +95.41% | +21.69% |
| 新造个人人寿业务整付保费，百万港元 | 23,132.416 | 26,959.725 | 46,854.224 | +102.55% | +73.79% |
| 有效个人人寿保单数，份 | 15,232,380 | 15,438,598 | 15,748,256 | +3.39% | +2.01% |

这些数据用于季度/跨年行业背景，不代表 2026 当前月度状态。2025 数据带 provisional 属性时，页面和文字必须明确标示“临时数据”。

### 3.4 产品服务器数据

历史核验结果为：739 个产品、1,014 个产品特征值、25 个产品类型；其中 67 个产品具有特征内容，特征覆盖约 9%。U20 当前主要读取“红利权益”知识，默认最多 20 条。

当前 Codex 运行环境未配置 `PRODUCT_DB_HOST/PORT/NAME/USER/PASSWORD`，因此本次未重新验证实时连接。结论是“历史可用、当前连通待 U20 环境复验”，不是“数据库不可用”。

产品库在本轮是增强源，不是硬依赖：连接失败时必须留下审计事件并降级；不得生成模拟产品数据。

### 3.5 U20 模块3当前结构

模块3已经具备以下基础：

- 五维输出：行业、市场、保险公司、产品、客户；
- 模块1已确认热点作为事件驱动；
- 模块2核心指标作为市场与产品传导数据；
- HKIA 三条季度序列作为保司季度佐证；
- Evidence ID 白名单、未知 ID 拒绝、claim-evidence 汇总和发布前检查；
- 产品库在 LIVE 连接失败时安全降级。

当前明确缺口：

1. `quarterly_insurer_evidence.dividend_and_savings` 仍是 planned/空结构；
2. 模块3提示词仍声明履行率/RBC 未接入，并禁止引用精确值；
3. 保险公司维度当前主要只有 IA 注册信息，没有 ICD 的经营披露佐证；
4. 产品名和保司法律主体尚无正式映射表；
5. U20 尚无 ICD 交换包 provider、健康检查和降级事件。

## 4. 目标分析模型

### 4.1 总体因果链

模块3必须按以下顺序组织信息：

```text
模块1：当月已确认热点/事件
        ↓ 解释外部驱动
模块2：当月核心行情指标及方向
        ↓ 解释市场传导
HKIA：季度/年度行业规模与结构佐证
        ↓ 约束行业与保司背景
ICD：年度法律主体 RBC + 产品历史履行率
        ↓ 约束保司承压能力与历史兑现观察
产品库：产品类型、条款/特征映射
        ↓ 约束影响落到哪些产品
模块3：行业 / 市场 / 保险公司 / 产品 / 客户联动影响
```

月度热点与行情是“驱动”，HKIA 是“行业佐证”，ICD 是“年度经营/产品历史佐证”。任何输出都不得把后两者写成当月变化的直接证据。

### 4.2 时间角色

每条证据新增或派生 `time_role`：

| time_role | 含义 | 可支持结论 |
|---|---|---|
| `CURRENT_DRIVER` | 当前分析月的热点或行情 | 本月发生了什么、方向如何 |
| `QUARTERLY_CONTEXT` | HKIA季度数据 | 行业趋势是否与月度机制相容 |
| `ANNUAL_ENTITY_CONTEXT` | 法律主体年度 RBC | 披露时点资本缓冲背景 |
| `HISTORICAL_PRODUCT_OBSERVATION` | 历史履行率 | 特定产品过去非保证利益的公开观察 |
| `STATIC_PRODUCT_ATTRIBUTE` | 产品库条款/类型 | 哪类产品可能暴露于该传导链 |

一个事实可以支持机制或背景，但不能跨越其时间角色。例：2024 RBC 只能写成“2024 年末披露的资本背景”，不能写成“本月偿付能力为 239%”。

### 4.3 五维分析职责

| 维度 | 主要输入 | ICD作用 | 输出要求 |
|---|---|---|---|
| 行业 | 模块1热点、HKIA市场总量 | 以 coverage 说明样本边界 | 说明行业环境、监管/资金/需求变化，不下公司排名 |
| 市场 | 模块2核心指标、热点 | 通常不直接驱动 | 描述利率、权益、汇率等传导方向及不确定性 |
| 保险公司 | 保司相关热点、HKIA公司数据、ICD RBC | 提供法律主体资本背景 | 主体精确、年份明确；只论背景和潜在敏感度 |
| 产品 | 模块2传导、产品库、ICD履行率 | 提供产品历史公开观察 | 仅在产品精确映射后引用；N/A不归零，不外推未来 |
| 客户 | 前四维经门禁后的影响 | 限制结论边界 | 说明可能关注项与风险，不提供个性化投保或收益承诺 |

## 5. 数据接线与字段契约

### 5.1 消费模式

U20 新增只读 provider，例如：

```text
05_集成工具_Integrate_Tools/tools/live_sources/icd.py
```

配置项建议：

```text
ICD_EXCHANGE_BUNDLE=/absolute/path/to/icd-exchange-v1-147a281d97570988
```

不得将包 ID 写死在业务代码中。provider 启动流程：

1. 解析绝对目录；
2. 调用或复用 `--validate-export` 等价校验；
3. 校验失败返回 `REJECTED`，不加载任何业务记录；
4. 校验通过后按需读取 JSON/JSONL；
5. 输出有界记录与 provider health；
6. 不修改 ICD 文件，不直连 ICD SQLite。

### 5.2 U20 状态建议结构

```json
{
  "module3_evidence": {
    "icd": {
      "status": "OK|DEGRADED|REJECTED|UNAVAILABLE",
      "bundle_id": "icd-exchange-v1-...",
      "contract_version": "1.0.0",
      "release_status": "PARTIAL_COVERAGE",
      "data_as_of": {},
      "fulfillment_ratio": [],
      "rbc_statement": [],
      "coverage_status": [],
      "limitations": []
    }
  }
}
```

必须把 `release_status=PARTIAL_COVERAGE` 传递到最终内容元数据和限制说明，不能只记录在后台日志。

### 5.3 履行率最小字段

下游使用字段：

- `insurer_code`
- `product_name_raw`
- `metric_type` / `metric_type_raw`
- `report_year`
- `observation_year` / `observation_year_raw`
- `scope_currency_raw`
- `raw_value`
- `normalized_value`
- `unit`
- `run_id`
- `source_url` / `final_url`
- `fetched_at`
- `sha256`
- `snapshot_path`

规则：`normalized_value=null` 表示不可数值化，不得转换为 0；展示原文时使用 `raw_value`。不同币种组、指标类型和观察年度不得折叠。

### 5.4 RBC 最小字段

下游使用字段：

- `insurer_code`
- `legal_entity_name_raw`
- `report_year`
- `solvency_ratio` / `solvency_ratio_raw`
- `capital_base` / `capital_base_raw`
- `prescribed_capital_amount` / `prescribed_capital_amount_raw`
- `currency`
- `amount_unit_raw` / `amount_scale`
- `risk_breakdown_json`
- `run_id`
- `source_url` / `final_url`
- `fetched_at`
- `sha256`
- `snapshot_path`

模块3默认只展示比率、主体、年份及必要限制。资本金额和风险拆分仅在确实支撑相关热点时进入模型上下文，避免无关字段扩大 token 消耗。

### 5.5 Evidence ID 规则

建议由 U20 对 ICD 自然业务键生成稳定 ID：

```text
icd:fulfillment:{sha256前12位}:{自然键哈希前12位}
icd:rbc:{sha256前12位}:{insurer_code}:{report_year}
icd:coverage:{bundle_id}:{insurer_code}:{disclosure_type}
```

Evidence 对象至少包含：

```json
{
  "evidence_id": "icd:rbc:...",
  "fact": "Prudential Hong Kong Limited 披露2024年RBC为239%",
  "source_type": "ICD_OFFICIAL_DISCLOSURE",
  "time_role": "ANNUAL_ENTITY_CONTEXT",
  "insurer_code": "PRU",
  "legal_entity_name": "Prudential Hong Kong Limited",
  "report_year": 2024,
  "source_url": "https://...",
  "sha256": "...",
  "snapshot_path": "raw_data/...",
  "bundle_id": "icd-exchange-v1-147a281d97570988",
  "limitations": ["历史披露，不代表当前值", "法律主体口径，不代表集团"]
}
```

## 6. 映射门禁

### 6.1 保司与法律主体

U20 建立显式映射表，字段至少为：

```text
u20_insurer_id, u20_brand_name, icd_insurer_code,
legal_entity_name, business_line, match_status, reviewed_at
```

`match_status` 只允许：

- `EXACT`：法律主体逐字或权威别名精确匹配；
- `ALIASED`：人工维护的明确别名；
- `AMBIGUOUS`：一个品牌对应多个法律主体；
- `UNMATCHED`：无匹配。

只有 `EXACT` 或经审计的 `ALIASED` 可进入公司级数字结论。`AMBIGUOUS` 只能输出“品牌下存在多个披露主体，当前无法归并”。

### 6.2 产品映射

产品映射必须独立维护：

```text
u20_product_id, icd_insurer_code, icd_product_name_raw,
product_db_name, match_status, match_method, reviewed_at
```

允许的 `match_method`：

- `EXACT_NAME`
- `CURATED_ALIAS`
- `OFFICIAL_PRODUCT_CODE`

禁止自动生产使用仅基于相似度的 `FUZZY_NAME`。产品无法匹配时，履行率可保留在“官方披露补充资料”中，但不能注入具体产品影响结论。

## 7. 分析规则与内容质量门槛

### 7.1 事实、机制、判断分层

每条分析拆成：

1. `FACT`：来源数据直接表达的事实；
2. `MECHANISM`：热点/指标到行业、保司或产品的通用传导机制；
3. `JUDGMENT`：在证据约束下形成的本期判断。

建议每条输出包含：

```json
{
  "claim_type": "FACT|MECHANISM|JUDGMENT",
  "time_role": "CURRENT_DRIVER|QUARTERLY_CONTEXT|ANNUAL_ENTITY_CONTEXT|HISTORICAL_PRODUCT_OBSERVATION",
  "confidence": "HIGH|MEDIUM|LOW",
  "text": "...",
  "evidence_ids": ["..."],
  "limitations": ["..."]
}
```

`FACT` 必须有直接证据；`JUDGMENT` 至少要有驱动事实和相关背景证据；纯机制说明可引用内部规则，但不得伪装为当期事实。

### 7.2 履行率使用规则

1. 只能描述具体保司、具体产品、具体指标、具体观察年度和币种组。
2. 不把所有历史记录求中位数后用于保司排名。当前各保司数值观察率差异较大，大量记录为官网 N/A、未推出或其他占位原文。
3. `N/A`、`Not yet launched` 等保留原文，不参与数值统计。
4. 历史履行率不是保证回报，也不是未来分红预测。
5. 产品映射不明确时，只能输出覆盖限制，不能引用具体值。

### 7.3 RBC 使用规则

1. 必须同时展示法律主体和报告年。
2. 不以品牌/集团名替代法律主体。
3. 不把 199%—304% 的当前样本直接转化为信用评级或安全排名。
4. 不把一般保险主体的数字用于寿险产品分析。
5. 不同公司的资本结构、风险结构和业务类型不同，单一比率不等价于综合经营质量。
6. 只有热点涉及利率、权益、信用、汇率、退保或资本监管时，才按需选取 `risk_breakdown_json` 的相关成分。

### 7.4 HKIA 使用规则

1. provisional 数据必须标示临时性质。
2. 季度总量用于行业趋势，不替代保司自主披露。
3. 公司级 HKIA 数据只有在主体映射明确时才能与 ICD 并列展示。
4. 相同指标的修订版本发生冲突时保留最新权威版本和快照指纹，不平均处理。

### 7.5 数据源优先级

同一事实冲突时按以下顺序处理：

1. 同一法律主体、同一统计期的官方监管/公司披露原文；
2. HKIA 标准化官方数据；
3. ICD 对官方原文的结构化结果；
4. U20 产品库中的产品属性；
5. 新闻与热点材料。

冲突不得静默覆盖。最终内容应说明冲突值、统计口径和采用理由。

## 8. 模块3完整输出规格

### 8.1 总结区

总结区应回答：

- 当月最重要的 1—3 个驱动是什么；
- 模块2哪些指标确认或削弱这些驱动；
- HKIA提供了什么行业背景；
- ICD对哪些保司/产品结论提供了历史佐证；
- 哪些结论因 coverage、主体或产品映射不足而降级。

总结不得堆放全部 ICD 数字，只选择与当月驱动相关的最小证据集合。

### 8.2 行业维度

目标内容：热点对香港寿险需求、保费结构、资金配置或监管环境的影响。当前可用的 HKIA 基线显示，2023Q1 至 2025Q1 年度化保费和整付保费显著增长，而有效保单数增幅相对温和；这可支持“保费金额扩张速度高于保单数量扩张”的历史行业背景观察，但必须标注跨年 Q1 比较和 2025 provisional 属性。

ICD 在此维度主要贡献 coverage：提醒读者履行率覆盖 9 家、RBC 覆盖 8 个法律主体，不能把样本自动等同全市场。

### 8.3 市场维度

由模块2的当月利率、权益、汇率、信用等核心指标主导。ICD 不应替代月度行情，只在需要解释保险资产负债敏感度时提供背景。

输出至少包含：指标方向、作用机制、受影响对象、反向情形和证据 ID。若当月指标快照未冻结，禁止生成“当前市场上涨/下跌”的伪完整报告。

### 8.4 保险公司维度

分析顺序：

1. 找出模块1中明确涉及的保险公司或监管事件；
2. 完成品牌到法律主体映射；
3. 读取同一主体 HKIA 公司数据（若有）；
4. 读取 ICD RBC 年度背景；
5. 结合模块2指标讨论潜在敏感度；
6. 明示该结论不是当前偿付能力预测。

若热点只提品牌而无法确认法律主体，输出应停在品牌层机制，不注入 RBC 精确值。

### 8.5 产品维度

产品维度继续使用模块2的传导矩阵作为主干。ICD 的作用是为已精确匹配的分红/储蓄产品增加历史履行率观察，产品库用于确认产品类型和特征。

推荐结构：

```text
当前驱动 → 指标信号 → 产品类型影响机制
→ 精确匹配产品的历史履行率观察
→ 不能外推未来的限制说明
```

履行率只应回答“过去公开披露了什么”，不能回答“未来会派多少”。

### 8.6 客户维度

客户维度只能表达需要关注的风险变量，例如非保证利益波动、融资成本、汇率暴露、退保与流动性安排。不得根据 RBC 或履行率给出个体化购买/退保指令，不得承诺收益或安全性。

## 9. 提示词改造要求

当前提示词中“履行率/RBC未接入，因此不得引用精确值”的规则应被替换为：

```text
只有输入 evidence_records 中明确提供的 ICD 精确值才可使用。
引用时必须同时返回对应 evidence_id，并在文字中保留法律主体/产品、报告年或观察年。
禁止根据缺失、N/A、品牌近似或未映射产品生成数字。
RBC 是特定法律主体在年度披露时点的资本背景，不代表集团或当前值。
历史履行率不代表未来分红，不得作为跨公司排名依据。
```

同时要求模型返回 `claim_type`、`time_role`、`confidence`、`evidence_ids` 和 `limitations`。U20 现有 Evidence ID 白名单逻辑继续作为硬门禁，不能只依赖提示词自律。

## 10. U20 文件级承接清单

建议改动范围：

| 文件/位置 | 工作项 |
|---|---|
| `05_集成工具_Integrate_Tools/tools/live_sources/icd.py` | 新建交换包只读 provider、校验、过滤、健康状态 |
| `06_开发技能_Develop_Skills/skills/insurance_impact.py` | 填充 `dividend_and_savings`，注入五维事实，更新提示词和输出结构 |
| Evidence contract 相关实现 | 注册 ICD Evidence ID、时间角色、限制和拒绝规则 |
| runtime readiness/health | 增加 ICD bundle 状态、契约版本和降级原因 |
| 配置模板 | 增加 `ICD_EXCHANGE_BUNDLE`，不写凭据、不硬编码用户目录 |
| 测试目录 | 新增 provider、映射、证据、模块3和端到端测试 |

接入时先复制契约逻辑或调用稳定 CLI，不复制 9.9MB 的业务文件进源码目录。生产部署可使用版本化共享目录或发布工件。

## 11. 测试计划

### 11.1 Provider 测试

1. 正式包验收成功，记录数为 13,039 / 8 / 23。
2. 文件字节篡改后拒绝加载。
3. 同步修改 manifest 哈希的语义篡改仍被拒绝。
4. 缺文件、未知契约版本、记录数不一致时 fail closed。
5. `PARTIAL_COVERAGE` 可加载但必须返回 `DEGRADED`，不得伪装为全覆盖。
6. provider 全程只读，运行前后交换包文件哈希不变。

### 11.2 映射测试

1. AIA 与 AIACO 不合并。
2. PRU 与 PRUGI 不合并。
3. 一般保险主体不进入寿险产品结论。
4. `AMBIGUOUS/UNMATCHED` 主体不得产生精确 RBC 判断。
5. 产品只有 `EXACT_NAME/CURATED_ALIAS/OFFICIAL_PRODUCT_CODE` 才能进入履行率结论。
6. 币种组和指标类型不会被折叠。

### 11.3 证据与提示词负向测试

1. 模型返回未知 Evidence ID 时该 claim 被拒绝。
2. 精确数字没有 Evidence ID 时该 claim 被拒绝。
3. 把 2024 RBC 写成“当前”时预检失败。
4. 把 `normalized_value=null` 写为 0 时预检失败。
5. 用履行率生成跨公司优劣排名时预检失败。
6. 未标注 provisional 的 2025 HKIA 数据不得发布。
7. 把品牌当法律主体时预检失败。

### 11.4 端到端场景矩阵

| 场景 | 预期 |
|---|---|
| ICD、HKIA、模块1、模块2全部可用 | 五维完整输出，全部事实可追溯 |
| 产品库不可连接 | 产品特征降级，ICD/HKIA链路继续；展示限制 |
| ICD包不可用 | 不引用履行率/RBC；模块3继续并记录 `ICD_UNAVAILABLE` |
| ICD为部分覆盖 | 可引用已覆盖主体；总结和元数据明确部分覆盖 |
| 热点涉及品牌但主体不清 | 只输出品牌层机制，不注入主体 RBC |
| 产品未映射 | 不注入产品级履行率 |
| 模块2当月指标缺失 | 禁止生成当前市场方向，输出数据缺口 |

### 11.5 首轮测试输入冻结

为了得到可复核结果，首次端到端测试必须冻结同一 run bundle：

- 分析月份；
- 模块1 confirmed events 及 Evidence ID；
- 模块2核心指标快照及 Evidence ID；
- HKIA快照指纹；
- ICD bundle ID；
- 产品库连接状态及 `last_updated` 范围；
- 模型与提示词版本。

没有这组冻结输入，不能声称产出的是“当前完整分析”，只能称为接口或模板测试。

## 12. 验收标准

### 12.1 工程硬门槛

- ICD 正式包校验结果必须为 `ACCEPTED`；
- 所有进入正文的精确数字 100% 绑定已知 Evidence ID；
- 未知或缺失 Evidence ID 的数字 claim 为 0；
- 法律主体错误合并为 0；
- N/A 转 0 为 0；
- 年度数据被写成当前值为 0；
- 产品模糊自动映射进入生产结论为 0；
- `PARTIAL_COVERAGE` 和 provisional 标识不丢失；
- ICD/provider 读取前后源文件哈希不变；
- 产品库不可用时主流程仍能安全降级完成。

### 12.2 内容质量门槛

每个维度至少回答“发生什么、为何影响、影响谁、证据是什么、限制是什么”。最终稿应做到：

- 月度驱动与季度/年度背景清楚分层；
- 结论具体到相关维度，不重复同一句套话；
- 数据只在相关时出现，不做数字堆砌；
- 每个判断标明置信度；
- 正向和反向情形至少各有一条；
- 不进行不受证据支持的预测、排名或个性化建议。

## 13. 降级和发布策略

| 状态 | 内部测试 | 正式发布 | 行为 |
|---|---|---|---|
| ICD `OK` + 全部关键输入齐全 | 允许 | 允许，仍需内容审计 | 正常五维输出 |
| ICD `DEGRADED/PARTIAL_COVERAGE` | 允许 | 有条件允许 | 只用已覆盖对象并展示限制 |
| ICD `REJECTED` | 允许测试降级 | 不得引用 ICD | 删除 ICD claims，保留失败事件 |
| 产品库不可用 | 允许 | 有条件允许 | 不展示未验证产品属性 |
| 模块2当前指标缺失 | 接口测试可继续 | 不允许称“当月完整分析” | 输出缺口，不生成市场方向 |
| Evidence 门禁失败 | 不通过 | 禁止 | 修正后重跑 |

## 14. 分阶段承接任务

### 阶段 A：ICD Provider 与健康检查

- 新增 provider；
- 接入正式包校验；
- 实现按保司/产品/指标/年度有界过滤；
- 输出 status、bundle_id、coverage、limitations；
- 完成篡改和只读测试。

### 阶段 B：主体/产品映射与 Evidence

- 建立法律主体显式映射；
- 建立产品显式映射；
- 生成稳定 ICD Evidence ID；
- 把时间角色和覆盖限制加入证据契约。

### 阶段 C：模块3五维接入

- 填充 `quarterly_insurer_evidence.dividend_and_savings`；
- 为保险公司与产品维度增加 ICD facts；
- 更新提示词中“未接入”规则；
- 扩充结构化输出和发布前门禁；
- 保持市场维度仍由模块2主导。

### 阶段 D：冻结输入的端到端测试

- 选择一个明确分析月份；
- 冻结模块1、模块2、HKIA、ICD、产品库状态；
- 生成完整五维报告；
- 做数字、主体、时间、Evidence 和文字质量审计；
- 记录 token、耗时、降级次数和返工原因。

### 阶段 E：测试后补数决策

只依据测试暴露的实际影响排序数据缺口。优先级原则：

1. 阻断高频热点或高频产品分析的缺口；
2. 能显著提高主体/产品映射率的缺口；
3. 能减少低置信度结论的缺口；
4. 最后才是单纯扩大保司数量。

## 15. 当前可形成的分析与不能形成的分析

### 15.1 已可形成

- 基于模块1热点和模块2指标的五维传导主线；
- 基于 HKIA 的季度/跨年行业规模和结构背景；
- 对已映射法律主体引用 2024 RBC 背景；
- 对已精确映射产品引用历史履行率观察；
- 对所有缺失、阻断和部分覆盖做显式披露；
- 全链路 Evidence ID 和原始官方证据回溯。

### 15.2 当前不能可靠形成

- 未冻结当月模块1、模块2输入时的“当前月完整结论”；
- MAN 的履行率数值；
- CLO、CTF、MAN 的已核验 RBC，以及 YFL 无文字层 PDF 对应的 RBC；
- 所有 739 个产品的完整特征分析；
- 未映射品牌或产品的精确公司/产品判断；
- 履行率、RBC 对未来收益或安全性的预测。

## 16. 预期成品质量

接入后的模块3不应只是“热点摘要 + 数据附录”，而应形成以下联动能力：

1. 能说明一个热点先影响哪些市场变量；
2. 能说明这些变量如何影响保险行业的资产端、负债端或需求端；
3. 能区分行业影响与特定法律主体背景；
4. 能把影响落到已映射的产品类型，并以历史履行率提供有限佐证；
5. 能把客户层表达约束为风险关注点，而非销售或投资建议；
6. 能让每个关键数字和判断回到证据；
7. 在数据不足时主动缩小结论，而不是补写流畅但不可审计的内容。

质量预期可以概括为：**数据不是越多越好，而是每一个被使用的数据都必须改变、约束或提高某条分析结论的可信度。**

## 17. 承接完成检查单

- [ ] U20 已配置 `ICD_EXCHANGE_BUNDLE`
- [ ] 正式包在 U20 环境验收为 `ACCEPTED`
- [ ] ICD provider 全程只读
- [ ] 法律主体映射表已审计
- [ ] 产品映射表不使用生产级模糊匹配
- [ ] `dividend_and_savings` 已由 planned 改为真实证据结构
- [ ] 模块3提示词已允许“仅引用输入中的 ICD 精确值”
- [ ] `claim_type/time_role/confidence/limitations` 已进入输出契约
- [ ] 未知 Evidence ID、时间错配、N/A归零均有负向测试
- [ ] product DB 不可用场景可降级
- [ ] 首轮测试输入已冻结
- [ ] 五维报告已完成人工内容审计
- [ ] 测试结果、token、耗时、返工和缺口已记录
- [ ] 测试后补数优先级已重新评估

## 18. 给 U20 的执行指令摘要

先实现并测试 ICD provider，再做主体/产品映射，然后把 ICD evidence 注入模块3现有 Evidence ID 门禁；不要绕过证据契约直接把数据拼进提示词。首轮使用当前可用数据完成冻结输入的端到端分析，产品服务器不可用时按降级路径继续。只有测试证明某项缺失数据实质阻断内容质量时，才回到 ICD 扩充来源。

本交接不需要 Jasper 对普通实现细节逐项决策。需要升级为重大决策的情况仅包括：改变模块3业务结论口径、允许模糊主体/产品映射、允许无证据数字发布、对外正式发布，或引入新的付费/受限外部数据源。
