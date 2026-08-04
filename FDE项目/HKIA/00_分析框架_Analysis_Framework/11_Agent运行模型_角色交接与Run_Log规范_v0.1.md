# HKIA Agent运行模型、角色交接与Run Log规范 v0.1

> 定位：记录一次分析如何被多个角色执行、验证、返工和签核，使过程与结果具有同等可审计性。

## 1. Run 是基本执行单元

一个 Run 对应一个有明确入口和终点的工作实例，例如：

- 摄入一批季度数据；
- 评估一个新公众号来源；
- 完成一个Theme的分析合同；
- 构建并审阅一页材料；
- 对已发布Claim进行重算。

Run 不等于对话轮次。一次Run可以跨多轮对话，也可以包含多个Agent Step。

## 2. 角色与权限

| 角色 | 主要职责 | 可批准 | 不可自行决定 |
|---|---|---|---|
| Source Scout | 发现、获取、登记Asset | 已批准Source的采集结果 | 新来源长期纳入、权限争议 |
| Ingestion Agent | 解析、标准化、实体映射 | 解析状态 | 修改原始资料、业务口径 |
| Data Steward | SSOT、公式、质量、断点 | G2数据就绪 | 决策用途、机制解释 |
| Analysis Planner | 问题卡、Theme和Spec路由 | Contract草稿 | 替业务Owner签核G0/G1 |
| Evidence Analyst | 三镜、边际、Fact和Claim草稿 | A级候选事实包 | 自行提升机制等级 |
| Industry Challenger | 替代解释、反证、证据升级 | B级复核意见 | 编造行业经验 |
| Report Composer | 页面结构、图形、来源 | 页面草稿 | 改写Claim等级或数据边界 |
| Reviewer/Evaluator | DoD、权限、回归、发布建议 | G4质量结论 | 最终业务责任 |
| Methodology Curator | 提取稳定规则和异常模式 | 转正候选 | 单次案例直接转正 |
| Human Business Owner | 决策目的、业务判断、发布责任 | G0/G1/G5 | — |

早期可以由同一AI终端扮演多个角色，但每个Step必须声明当前角色，不能把Planner的假设伪装成Reviewer批准。

## 3. 五类运行对象

### Run

记录目标、模式、Contract、当前Gate、参与者、状态、开始/结束时间、输入/输出摘要和最终结果。

### Step

记录一次具体动作：角色、目的、输入对象、工具、操作、输出对象、验证、假设、耗时和状态。

### Gate Decision

记录阶段门结果：`pass / conditional_pass / fail / waived`，以及检查项、证据、批准人、保留意见和恢复条件。

### Handoff

记录角色之间的移交：交付对象、完成定义、已知限制、待解决问题、接收方检查和是否接受。

### Incident

记录错误、越权、返工或异常：发现方式、影响对象、根因、修复、预防规则和方法论候选。

## 4. Run状态机

```text
created
→ active
→ waiting_human / waiting_data / blocked_by_gate
→ active
→ completed / cancelled / superseded
```

`waiting_*`不是失败；它表示系统正确识别了外部依赖。只有目标真正完成且所有必需Gate通过，Run才能`completed`。

## 5. Step最低字段

| 字段 | 说明 |
|---|---|
| step_id / run_id | 稳定关联 |
| role | 当前执行角色 |
| objective | 本步消除什么不确定性 |
| input_refs | Source/Asset/Fact/Claim/Spec/Contract等 |
| action | 实际动作，不只写“分析” |
| tools | 工具和关键参数/版本 |
| assumptions | 显式假设 |
| output_refs | 新增或修改对象 |
| validation | 自动检查和结果 |
| human_decisions | 人工选择或批准 |
| incidents | 本步触发的异常 |
| started_at/ended_at | 时间 |
| status | completed/failed/reworked/waiting |

## 6. Handoff契约

标准移交包必须包含：

1. 当前对象和版本；
2. 已完成的验收项；
3. 未完成项和明确限制；
4. 关键假设与冲突；
5. 接收角色必须重新检查什么；
6. 接受、退回或条件接受决定。

典型移交：

```text
Planner → Data Steward：Contract + 数据需求
Data Steward → Analyst：Verified Fact Set + 质量限制
Analyst → Challenger：Claim Graph + Evidence Links
Challenger → Composer：允许表达的Claim + 替代解释
Composer → Reviewer：页面 + Page-to-Claim映射
Reviewer → Business Owner：DoD结果 + 发布风险
```

## 7. 人工Gate不可被“已输出文件”替代

- 文件存在不代表Gate通过；
- Reviewer未签核不代表内容错误，但状态必须保持草稿；
- 人工反馈必须记录其改变了问题、规则、证据还是页面；
- `waived`必须记录批准人、原因、风险和到期时间。

## 8. Incident分类

| 类别 | 示例 |
|---|---|
| scope | 未建框架就过早产出报告 |
| data | 字段匹配、单位、分母、断点错误 |
| reasoning | 把相关写成因果、证据越级 |
| presentation | 百分比格式、图文不一致 |
| tooling | 路径、依赖、渲染失败 |
| governance | 绕过Gate、未记录人工决定 |
| access | 抓取权限、登录或保存范围问题 |

每个Incident必须回答：为何现有检查没提前发现，以及应在哪个更早的Gate增加什么规则。

## 9. 方法论转正接口

Run结束后产生三类候选：

- `deterministic_check_candidate`：可脚本判断；
- `workflow_rule_candidate`：可成为阶段门或交接规则；
- `human_judgment_guide`：不适合自动化，但应形成审阅提示。

转正需至少三个独立案例验证，记录命中率、误报、漏报和适用边界。

## 10. 运行指标

| 指标 | 用途 |
|---|---|
| gate_first_pass_rate | 哪层最常返工 |
| rework_by_cause | 返工来自数据、推理还是表达 |
| human_override_rate | 哪些步骤仍依赖人工 |
| traceability_complete | 输出能否完整回溯 |
| incident_escape_rate | 错误是否直到页面/发布才发现 |
| time_by_role | 时间消耗分布 |
| automation_coverage | 确定性动作自动化程度 |
| methodology_candidates | 可沉淀规则数量及转正率 |

这些指标评估系统运行，不直接评价业务结论是否“深刻”。

