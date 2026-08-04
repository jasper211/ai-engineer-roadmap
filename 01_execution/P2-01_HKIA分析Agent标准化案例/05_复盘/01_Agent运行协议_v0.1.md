# HKIA 分析 Agent 运行协议 v0.1

> 本文件描述未来 Agent 应如何运行，不代表现在就应全部自动化。当前案例负责验证协议，重复案例负责证明可复用性。

## 1. Agent 的职责边界

### Agent 负责

- 将业务问题转换为待确认的分析合同；
- 路由主维度和所需事实表；
- 执行确定性公式、质量检查和回加总；
- 生成结构/趋势/比率证据包；
- 将结论按 A/B/C 分级，并提示缺失证据；
- 依据已签核的证据生成页面草稿；
- 保存来源、公式、分母和变更记录。

### 人负责

- 确认决策使用者和真正业务问题；
- 签核 Baseline、对象集、分母和 Peer Set；
- 判断机制是否具有业务解释力；
- 挑战替代解释和反事实；
- 批准 B 级机制进入标题；
- 对最终判断和发布负责。

## 2. 状态机

```text
INTAKE
→ CONTRACT_DRAFTED
→ CONTRACT_APPROVED
→ DATA_MAPPED
→ DATA_VALIDATED
→ EVIDENCE_BUILT
→ CLAIMS_REVIEWED
→ PAGE_DRAFTED
→ PAGE_APPROVED
→ RETROSPECTIVE_COMPLETED
```

任何状态失败都返回上一个产生缺陷的协议层，而不是只修改最终页面。

## 3. 阶段输入输出

| 状态 | 输入 | 输出 | 自动检查 | 人工 Gate |
|---|---|---|---|---|
| INTAKE | 初始业务提问 | 决策问题卡 | 是否包含对象、动作、用途 | 问题是否值得回答 |
| CONTRACT_DRAFTED | 问题卡、Spec | 分析合同 | 八字段完整性 | 分母/对象/主维度签核 |
| DATA_MAPPED | 合同、资产目录 | 字段映射 | 字段、覆盖、grain | 业务定义一致性 |
| DATA_VALIDATED | 事实表、公式 | 质量报告 | 回加总、单位、断点 | 异常处置选择 |
| EVIDENCE_BUILT | 已验证事实 | 三镜和边际证据 | 数字复算 | 证据是否回答问题 |
| CLAIMS_REVIEWED | 证据包 | A/B/C 命题表 | 语言权限 | 机制与替代解释 |
| PAGE_DRAFTED | 已批准命题 | 单页草稿 | 图文映射、来源 | 商业判断和可读性 |
| RETROSPECTIVE | 全链路日志 | 转正候选 | 重复问题统计 | 是否沉淀为规则/Skill |

## 4. 最小对象 Schema

### AnalysisContract

```yaml
question_id: HKIA-CHANNEL-001
decision_user: TBD
decision_action: TBD
object_scope: HK_new_individual_long_term_business
baseline:
  start: 2019-FY
  end: 2025-FY
  frequency: FY
  ytd_rule: same_period_only
measures: [NOP, APE]
primary_dimension: channel
denominator: same_scope_market_total
breakpoints: [2024_RBC_reporting_change]
forbidden_inference:
  - reconstruct_3d_from_parallel_2d
  - equate_APE_with_profit
status: draft
```

### Claim

```yaml
claim_id: C-001
statement: TBD
grade: A | B | C
evidence_ids: []
counter_explanation: TBD
falsification_condition: TBD
allowed_in_title: false
reviewer: TBD
```

## 5. 熔断规则

Agent 遇到以下情况必须停止生成确定性结论：

1. Baseline 字段缺失；
2. 份额分母不一致或未知；
3. NOP/APE 公式与事实表无法核对；
4. 互斥维度不能回加总；
5. 跨 2024 断点但没有双链说明；
6. 请求的数据颗粒度高于真实事实表；
7. B/C 命题没有证据等级却被要求写成标题；
8. 公司名称无法完成别名映射；
9. 页面数字不能反向定位到事实表。

熔断输出必须包含：失败规则、受影响命题、缺失输入、恢复条件。

## 6. 与现有 Agent 验证方法对齐

- **确定性检查优先**：公式、回加总、字段、单位、期间由脚本判断。
- **独立数据源交叉核验**：不能只看 Agent 自己生成的页面；必须回查事实表和来源。
- **异常特征清单优先**：持续积累分母漂移、口径断点、伪三维、语言越级等异常。
- **验证标准独立文档化**：阶段门和 DoD 不嵌死在某个提示词内。

## 7. 方法论转正规则

本案例只产生“候选规则”，不直接宣称通用：

- 第 1 次：记录动作、异常和人工修改；
- 第 2 次：验证在另一分析主题是否仍成立；
- 第 3 次：检查跨主题稳定性；
- 稳定后：转为模板、确定性检查脚本、Skill 或 Agent 能力；
- 不稳定：保留为人工判断指南，不强行自动化。

