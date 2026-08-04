# HKIA Fact / Evidence / Claim 元模型 v0.1

> 定位：规定系统如何把多源资料转换为可复核事实、证据关系和可进入报告的分析命题。

## 1. 核心对象

```text
Fact：观察到什么
Evidence Link：某项证据与某个命题是什么关系
Claim：基于当前证据允许说什么
```

同一个 Fact 可以支持多个 Claim；同一个 Claim 也可以同时拥有支持、反对和限定证据。

## 2. Fact

Fact 是来源、期间、对象和口径明确，能够复核的最小事实单元。

| 类型 | 定义 | 示例 |
|---|---|---|
| observed_metric | 来源直接披露的数值 | 某期渠道年度化保费 |
| derived_metric | 由已登记公式计算 | NOP、APE、份额、增量贡献 |
| event_fact | 明确发生的事件 | RBC制度生效 |
| document_fact | 文件明确声明的定义 | 报表为YTD口径 |
| entity_fact | 实体身份和关系 | 公司更名、集团归属 |

最低字段：`fact_id`、类型、纯事实statement、subject、metric/event、value、unit、period、object_scope、source_id、asset_id、locator、method、schema_version、quality_status、version。

规则：

1. 必须回到具体 Asset 和引用位置；
2. 派生 Fact 必须引用公式及输入 Fact；
3. statement 不使用“因为、导致、偏好、能力”等机制语言；
4. 更正产生新版本，不覆盖旧 Fact；
5. 多次转载共享同一原始证据链。

## 3. Evidence Item 与 Evidence Link

Evidence Item 可以是 Fact、外部 Opinion、内部 Experience、Research Finding、Counterexample 或 Missing Evidence。

Evidence Link 描述它与 Claim 的关系：

| relation | 含义 |
|---|---|
| supports | 支持命题 |
| contradicts | 反对或推翻 |
| qualifies | 限定范围或语言强度 |
| contextualizes | 提供背景但不直接证明 |
| motivates | 值得调查但不构成证明 |
| duplicates | 与另一证据共享原始链 |

证据距离分为 `direct / near / indirect / contextual`。数量不能抵消距离：十条背景观点不能替代一条直接事实。

## 4. Claim

报告标题、Insight和建议必须绑定 Claim ID。

| 类型 | 回答什么 | 最低要求 |
|---|---|---|
| descriptive | 发生了什么 | 直接Fact |
| comparative | 相对谁强/弱 | 同合同可比Fact |
| decomposition | 增量如何分配 | 互斥维度且可回加总 |
| association | 哪些变量方向一致 | 多条Fact，不写因果 |
| mechanism | 通过什么变量发生 | 近端证据、替代解释、反证 |
| causal | X是否导致Y | 时间顺序、机制、反事实/识别设计 |
| motivation | 客户/公司为何选择 | 调研、访谈或行为证据 |
| value | 是否创造利润/EV/资本回报 | 价值和资本数据 |
| recommendation | 应采取什么行动 | 已验证命题、目标、约束和责任人 |

最低字段：`claim_id`、theme_id、claim_type、statement、scope、baseline_contract_id、grade、status、evidence_links、alternative_explanations、falsification_conditions、unresolved_conflicts、allowed_surfaces、owner、reviewer、version。

## 5. Experience Card

老板经验不直接塞进Prompt，而要记录：经验规则、适用情境、历史案例、反例、观察指标、决策用途、保密级别、维护人和复核时间。

Experience 可以影响问题优先级和机制排序；要进入确定性对外结论，仍须与 Fact 建立证据关系。

## 6. Claim Graph

```text
C1 结果：代理份额下降
├─ C2 比较：代理增长慢于市场
├─ C3 分解：经纪承接最多增量
└─ C4 机制：开放渠道承接配置型需求
   ├─ 平行结构证据
   ├─ 专家/公司解释
   ├─ 替代解释
   └─ 待补客户/销售证据
```

C1-C3可以是A级；C4不能自动继承父命题等级。

## 7. 全链路溯源

```text
Page Object → Claim → Evidence Link
→ Fact / Opinion / Experience → Asset → Source
```

派生数值还需：`Derived Fact → Formula → Input Facts`。

## 8. 对现有SQLite的影响

`long_term_business` 已是事实数据载体，但尚缺 fact_id、asset_id、sheet/cell locator、formula lineage、quality status和版本关系。Phase B在其上增加事实登记映射层，不重写现有解析能力。

