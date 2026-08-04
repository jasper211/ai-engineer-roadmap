# Analysis Contract 与阶段门规范 v0.1

## 1. Contract 的作用

Contract 是一次分析的执行许可证。它必须在打开分析结果前回答：

- 谁要据此做什么；
- 对象、期间和分母是什么；
- 主Theme和主维度是什么；
- 使用哪些口径和事实表；
- 哪些断点、扩展和禁止推断适用；
- 谁签核了哪些字段。

## 2. Contract状态

```text
draft
→ business_scope_approved
→ data_mapping_verified
→ executable
→ analysis_completed
→ review_passed
→ published
→ superseded / invalidated
```

只有`executable`状态允许生成正式证据包；草稿可以做探索，但不得形成对外标题。

## 3. 必填区块

### 决策区

- decision_user、decision_action、intended_surface；
- primary_question；
- primary_theme和parallel_validation_themes。

### Baseline八字段

- start、end、frequency、same_period_rule；
- object_set、denominator、measures、breakpoints。

### 数据区

- fact_table、grain、source_chain；
- required_fields、mapping_version、quality_gate。

### 分析区

- primary_dimension；
- selected_specs；
- allowed_crosses；
- company/Peer规则；
- required_lenses和required_models。

### 证据与表达区

- minimum_claim_grade；
- prohibited_inferences；
- required_counterevidence；
- page_contract和DoD。

### 签核区

- business_owner、data_steward、analysis_owner、reviewer；
- 每个Gate的时间、决定和保留意见。

## 4. 阶段门

| Gate | 检查 | 失败返回 |
|---|---|---|
| G0 Intake | 决策用户、动作和问题清楚 | 问题定义 |
| G1 Contract | Baseline、主Theme、主维度、Spec齐全 | Contract |
| G2 Data Ready | 事实表、字段、公式、断点可追溯 | L0/L1/Data Steward |
| G3 Evidence | 三镜、边际、证据链接和反证齐全 | L2-L5/Analyst |
| G4 Page | 图文对应、语言权限、来源、DoD | Claim/Page |
| G5 Publish | 责任人批准、版本和受众权限 | Review/治理 |
| G6 Retrospective | 人工修改、异常和转正候选已记录 | Agent Run Log |

## 5. 熔断规则

Agent必须停止正式分析并输出恢复条件，如果：

1. Baseline字段不完整；
2. 主Theme或主维度多于一个；
3. 份额分母未知或跨期变化；
4. NOP/APE公式无法绑定事实字段；
5. 跨断点但未声明处理方式；
6. 请求交叉不在L4白名单；
7. 请求粒度高于L0事实表；
8. A/B/C等级与页面权限冲突；
9. 页面数字无法回溯Fact；
10. 关键冲突处于未解决状态。

熔断输出：规则ID、受影响问题/Claim、缺失输入、恢复条件、责任人。

## 6. 探索与正式分析分离

- `exploration`：允许快速查询和发现模式，但所有输出带水印/状态，不进入正式Claim。
- `contracted_analysis`：严格继承Spec，通过阶段门后才能发布。

这样既不压制探索，也不让探索性结果伪装成正式分析。

