# HKIA Source Strategy 与 Registry 规范 v0.1

> 目标：让每一项输入在进入解析和分析前，先获得稳定身份、来源属性、获取权限、证据权限和可追溯记录。

## 1. 五类对象不能混用

| 对象 | 定义 | 示例 |
|---|---|---|
| Source | 持续发布内容的来源主体或栏目 | IA长期业务季度统计栏目、某公司投资者关系网站 |
| Asset | 某次发布的具体资料 | `4q25long.xlsx`、一篇公众号文章、一次演讲视频 |
| Fact | 可复核的数值或明确发生的事件 | 2025年代理渠道APE金额 |
| Opinion | 某人或机构对事实的解释/判断 | “开放渠道更适合大额配置” |
| Experience | 内部人员在特定情境下形成的经验规则 | 老板判断某类渠道变化通常先看哪些指标 |

关系：一个 Source 发布多个 Asset；一个 Asset 可抽取多个 Fact 和 Opinion；Experience 必须单独记录适用情境，不能伪装成外部 Fact。

## 2. 来源分类

### S1 监管与政府原始来源

- 监管结构化数据：IA Excel/CSV/API。
- 监管文件：通告、咨询、规则、新闻稿。
- 政府/公共统计：HKMA、统计处、data.gov.hk等。

主要权限：可支持 A 级结果事实与制度事件；通常不能单独支持客户动机和公司内部经营动作。

### S2 公司原始披露

- 年报、财务报告、业绩会、公告、官方产品与渠道资料。

主要权限：可以 A 级证明“公司披露了什么”及经审计数字；公司自述的因果解释仍需考虑选择性披露。

### S3 研究与专业数据库

- 行业研究、学术论文、评级报告、商业数据库。

主要权限：取决于方法透明度和原始来源；可支持事实交叉验证或机制，但不能只凭品牌声誉自动升级。

### S4 行业媒体与公众号

- 专业媒体、行业公众号、信息图、访谈整理。

主要权限：适合发现事件、案例和机制假说。引用监管或公司数字时必须追溯原始来源；无法追溯时只能作为二手证据。

### S5 专家与社交动态

- LinkedIn等平台的专家动态、演讲、个人文章和评论。

主要权限：适合发现趋势信号、解释框架和待验证命题。作者身份和经验相关性影响参考价值，但观点本身不成为 A 级市场事实。

### S6 内部知识与经验

- 老板知识库、内部会议、复盘、业务判断、访谈。

主要权限：提供问题优先级、阈值、历史语境和行动映射。必须转换为 Experience Card，并记录情境、案例、反例和维护人。

### S7 用户临时提供资料

- 临时上传的文件、截图、转发内容、未纳入稳定监测的链接。

主要权限：先进入待登记区；确认来源主体和原始出处后再决定证据等级。

## 3. 来源评价不压缩成一个总分

来源质量使用多维画像，避免“一个80分来源所有内容都可信”：

| 维度 | 核心问题 | 取值示例 |
|---|---|---|
| authority | 来源是否拥有发布该事实的职责或一手位置 | primary / official / professional / informal |
| proximity | 距离原始事件或数据有几层 | primary / secondary / tertiary |
| method_transparency | 口径、样本、公式是否透明 | high / medium / low |
| reproducibility | 能否复算或回到原文 | high / medium / low |
| timeliness | 信息是否在适当时间窗口内 | current / historical / stale |
| bias_profile | 有何制度性立场或利益 | regulatory / corporate_self_report / commercial / personal |
| access_stability | URL/API/文件是否稳定可重取 | stable / fragile / manual_only |
| rights | 是否允许保存、解析和内部使用 | allowed / restricted / unknown |

评价作用于具体 Asset，而不仅是 Source。即使同一公众号，不同文章的原始引用和方法透明度也可能不同。

## 4. 证据准入规则

| 内容类型 | 可进入 | 不可直接进入 |
|---|---|---|
| 官方结构化数据 | Fact；A级命题 | 客户动机、经营策略 |
| 监管规则原文 | Policy Fact、Event | 未经验证的业务影响 |
| 公司审计数字 | Company Fact | 全市场外推 |
| 公司管理层解释 | Company Claim | 独立市场事实 |
| 媒体引用且可追溯原始来源 | Fact引用 + Media Claim | 省略原始出处 |
| 媒体无来源数字 | Unverified Claim | A级事实表 |
| 专家观点 | Expert Opinion、机制候选 | 确定性因果结论 |
| 老板经验 | Experience、问题路由、阈值候选 | 外部事实 |

### 事实提升条件

二手材料里的数字只有满足以下条件才能进入正式 Fact：

1. 能定位原始来源；
2. 原始口径、期间、对象和单位清楚；
3. 抽取值与原始资料一致；
4. 保存原始 Asset ID 和引用位置。

否则保留为 `unverified_numeric_claim`。

## 5. Source Registry 最低字段

| 字段 | 说明 |
|---|---|
| source_id | 稳定编号，不随URL变化 |
| name | 来源名称 |
| publisher | 发布主体 |
| source_class | S1-S7分类 |
| channels | website/API/RSS/WeChat/LinkedIn/email/manual等 |
| base_urls | 官方入口，不等于某篇Asset URL |
| themes | 主要覆盖Theme ID |
| acquisition_mode | manual/automated/connector/hybrid |
| update_pattern | 固定频率或事件触发 |
| access_policy | 权限、登录、robots/条款和保存范围 |
| quality_profile | 多维来源画像默认值 |
| evidence_permissions | 可产生哪些对象 |
| owner | 维护人/Agent |
| status/version | active/watchlist/paused/retired |

## 6. 来源状态

```text
candidate → assessed → approved → active
                         ↓
                  paused / restricted / retired
```

- `candidate`：只知道可能有价值。
- `assessed`：已完成主题相关性、权限与质量画像。
- `approved`：允许进入采集计划。
- `active`：实际产生Asset并被监测。
- `restricted`：可以人工阅读但不允许自动抓取/持久化全文。

## 7. 主题驱动的来源规划

来源必须服务 Theme，不做无边界信息收集：

| Theme | 第一来源 | 第二来源 | 解释性来源 | 内部来源 |
|---|---|---|---|---|
| T12 渠道迁移 | IA渠道事实 | 公司披露 | 行业媒体、专家 | 老板渠道经验 |
| T01 增长质量 | IA整付/年度化 | 公司价值披露 | 研究报告 | 价值判断经验 |
| T20 公司格局 | IA公司事实 | 年报/业绩会 | 媒体访谈 | Peer与能力判断 |
| T30 监管资本 | 监管原文 | 公司实施披露 | 法律/专业解读 | 历史执行经验 |

## 8. 治理红线

1. 不因来源数量多就提高结论等级；重复转载只算一条原始证据链。
2. 不将同一机构的多篇文章当作独立交叉验证。
3. 不自动抓取权限不明、需要绕过访问控制或禁止持久化的内容。
4. 不保存账号凭证到Source Registry。
5. 不删除或覆盖已进入证据链的原始Asset；更正通过新版本关联。
6. 不让摘要替代原文快照和引用位置。

