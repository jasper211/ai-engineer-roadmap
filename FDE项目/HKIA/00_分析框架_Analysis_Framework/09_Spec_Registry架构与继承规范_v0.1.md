# HKIA Spec Registry 架构与继承规范 v0.1

> 定位：把分析中的隐含假设变成可登记、可继承、可冲突处理、可被Agent验证的协议对象。

## 1. Spec 与 Contract

- **Spec**：长期稳定的规则，例如“季度只能同季同比”“APE=年度化+10%×整付”。
- **Analysis Contract**：某次任务对多个Spec的具体实例化，例如“2019FY到2025FY、主维度为渠道、NOP/APE并列”。

Agent 不直接从培训文档自由发挥，而是：

```text
Theme路由 → 选择Spec → 生成Contract草稿
→ 人工签核关键字段 → 数据映射 → 执行与验收
```

## 2. L0-L5层级

| 层级 | 职责 | 回答的问题 |
|---|---|---|
| L0 数据底座 | SSOT、颗粒度、来源、对账边界 | 当前能看多细、哪个表是事实主链 |
| L1 横向合同 | 时间、Baseline、NOP/APE、份额、边际 | 如何比较、如何计算 |
| L2 业务维度 | 产品、渠道、缴费、货币、客群、状态 | 沿什么轴解释结构 |
| L3 公司实体 | 公司别名、集团、分类、Peer、固定/动态样本 | 谁获得或失去结果 |
| L4 合法交叉 | 市场二维白名单、禁止伪立方 | 哪些联合关系可直接观测 |
| L5 命题与页面 | A/B/C、图形、Insight、来源、DoD | 如何表达且不越过证据 |

## 3. 优先级与冲突

原则：**低层数据边界优先于高层表达需要。**

```text
L0 > L1 > L2 > L3 > L4 > L5
```

典型冲突：

| 请求 | 冲突 | 处理 |
|---|---|---|
| 页面希望展示公司×渠道×货币 | L0/L4无联合事实 | 拆成平行证据或申请新数据 |
| 把2026Q1接在2025FY后 | L1时间合同 | 改为2026Q1同比2025Q1验证线 |
| 用APE直接写利润增长 | L1口径合同 | 降级为持续化价值代理，补利润数据 |
| 媒体机制写入标题 | L5证据协议 | 按Claim等级与页面权限处理 |

## 4. Spec对象最低字段

| 字段 | 含义 |
|---|---|
| spec_id | 稳定编号 |
| level | L0-L5 |
| name / purpose | 名称和职责 |
| applies_to | 适用Theme、数据或输出 |
| required_inputs | 执行前必需字段 |
| rules | 可执行规则 |
| prohibited | 禁止项 |
| validation_checks | 确定性检查 |
| human_gates | 人工判断点 |
| dependencies | 继承的低层Spec |
| conflict_priority | 冲突优先级 |
| owner/status/version | 治理信息 |

## 5. 核心Spec集合

### L0

- `SPEC-L0-SSOT`：事实主链、source/asset/fact溯源。
- `SPEC-L0-GRAIN`：每张事实表粒度和可观测联合维度。
- `SPEC-L0-BREAKPOINT`：2024 RBC等断点与双链。

### L1

- `SPEC-L1-TIME`：Baseline八字段、FY/YTD、同季比较。
- `SPEC-L1-MEASURE`：NOP、APE、件数、件均和价值边界。
- `SPEC-L1-RATIO-MARGIN`：份额、净增量、贡献率和回加总。

### L2

- 产品、渠道、缴费年期、币种、客群/地域、业务状态六类维度Spec。

### L3

- `SPEC-L3-INSURER`：实体别名、集团、公司分类和具名规则。
- `SPEC-L3-PEER`：Peer选择、固定/动态样本并列。

### L4

- `SPEC-L4-MARKET-2D`：市场层合法二维白名单。
- `SPEC-L4-NO-FAKE-CUBE`：边际分布不能恢复联合高维事实。

### L5

- `SPEC-L5-CLAIM`：Claim等级、证据链、反证与语言权限。
- `SPEC-L5-PAGE`：图形选择、逐图Insight、综合判断、来源与DoD。

## 6. 继承包

为了减少每次手工选择，Theme绑定Spec Package：

```text
mandatory_base = L0全部 + L1全部 + L5全部
theme_primary = 该Theme的主维度Spec
optional_extension = 公司/Peer、合法二维、平行验证维度
```

例如T12：

```text
mandatory_base
+ SPEC-L2-CHANNEL
+ SPEC-L3-INSURER（公司落点时）
+ SPEC-L3-PEER（公司比较时）
+ SPEC-L4-MARKET-2D（验证产品×渠道时）
```

## 7. Spec版本与影响分析

修改Spec时必须记录：

- 变更原因；
- 受影响Theme；
- 受影响Fact/Claim/报告；
- 是否需要重算或重新签核；
- 生效日期和兼容策略。

Formula或分母变化默认触发相关派生Fact失效；语言规则变化默认触发已发布Claim复审。

