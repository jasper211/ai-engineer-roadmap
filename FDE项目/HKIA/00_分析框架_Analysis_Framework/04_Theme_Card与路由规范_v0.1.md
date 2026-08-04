# Theme Card 与路由规范 v0.1

## 1. Theme Card 的作用

Theme Card 是分析框架的最小治理单元。它让 Agent 在收到问题或资料时知道：

- 这个对象属于哪个主题；
- 需要继承什么 Spec；
- 应检索哪些来源；
- 当前有哪些事实和缺口；
- 哪些语言不能使用。

## 2. 标准字段

| 字段 | 含义 | 是否必填 |
|---|---|---|
| theme_id | 稳定编号 | 是 |
| name | 主题名称 | 是 |
| definition | 主题定义 | 是 |
| decision_questions | 稳定决策问题 | 是 |
| in_scope/out_of_scope | 主题边界 | 是 |
| primary_dimension | 唯一主解释轴 | 是 |
| validation_dimensions | 平行验证轴 | 否 |
| inherited_specs | 必须继承的Spec | 是 |
| required_facts | 最低事实需求 | 是 |
| preferred_sources | 推荐来源类型 | 是 |
| current_coverage | 当前证据覆盖 | 是 |
| forbidden_inferences | 禁止推断 | 是 |
| evidence_upgrade | 从A/B到更高解释所需证据 | 是 |
| deliverables | 合适的输出形式 | 否 |
| agent_route | 建议Agent角色链 | 是 |
| owner/status/version | 治理字段 | 是 |

## 3. 问题路由规则

1. 先识别问题要解释的“结果变量”。
2. 选择一个主主题；其他主题只能作为平行验证或上下游背景。
3. 若同时出现两个同等重要的结果变量，拆成两个分析任务，通过综合页连接。
4. 若问题直接询问客户动机、利润或经营动作，但只有监管数据，进入主题后立即触发证据缺口，不允许降格成数据切片替代回答。
5. 路由必须记录置信度和备选主题，低置信度交给人工确认。

## 4. 资料路由规则

资料可以路由到多个主题，但每个被抽取的 Fact/Claim 必须有一个主要主题：

- 数值表按指标与维度路由；
- 监管文件按影响对象和生效事件路由；
- 行业文章逐命题路由，不能整篇只贴一个标签；
- 专家观点记录作者、时间、原文、观点对象和证据引用；
- 老板经验同时记录适用情境和反例。

## 5. 示例：T12 渠道竞争与分销迁移

| 字段 | 内容 |
|---|---|
| theme_id | T12 |
| definition | 研究代理、银行、经纪、直接等渠道的规模、份额、增量承接及公司落点 |
| decision_questions | 哪个渠道做大、跑赢市场、承接增量；变化对公司意味着什么 |
| primary_dimension | channel |
| validation_dimensions | payment_term、product、currency、company |
| inherited_specs | 时间/Baseline、NOP/APE、渠道、市场二维、公司实体、页面合同 |
| required_facts | 渠道金额、市场份额、年度路径、渠道净增量、公司单维落点 |
| preferred_sources | IA事实表、公司披露、行业媒体、专家观点、内部经验 |
| current_coverage | A级事实强；机制和经营动作弱 |
| forbidden_inferences | 渠道份额变化直接等同客户偏好或代理生产率变化 |
| evidence_upgrade | 客户调研、中介数据、销售流程、公司披露、老板案例 |
| agent_route | Planner → Data Steward → Analyst → Challenger → Composer → Reviewer |

## 6. Theme Card 验收

- 另一位分析师能否判断一个问题是否属于该主题；
- 能否据此列出最低数据需求，而不是先打开数据库；
- 能否知道当前不可回答什么；
- Agent 能否据此选择事实表、来源和 Spec；
- 新资料进入时能否落到具体 Fact/Claim，而不是只存文章摘要。

