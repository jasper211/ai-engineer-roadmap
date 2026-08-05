# L3统一分析模型 v1.0

> 标准ID：`VNW-L3-COM-GOLD-v1.0`  
> 输入：系统生成的单L3事实证据包  
> 输出：`vnw.l3-analysis.v1` JSON  
> 禁止：访问事实包以外的信息、补造任务、补造岗位、补造收益率。

## 1. 分析原则

1. 每条分析只能引用输入中存在的 `evidence_id`；
2. 数据库事实、正式补充材料、模型推导、工作坊共识必须分层；
3. 没有证据支持的字段输出空值，并写入 `missing_analysis`；
4. 模型分析只能标记为 `MODEL_DRAFT`，不能标记为已确认；
5. 任务只能从蓝图步骤、规则、交付物构成或有效知识条目拆出；
6. 资金、合规、对外发布和不可逆操作必须识别人工控制门；
7. 优先级建议必须解释数据依据、流程背景、风险限制和当前建议；
8. 负责人决策必须落到具体任务、最小试点、人工边界和待拍板事项。
9. `skill_feasibility`与自动化Tier是两条独立轴：前者回答是否适合封装，后者回答需要多少人工判断；
10. A/B/C/F只能影响Skill、Agent辅助或治理路径，不得直接推导优先级象限；
11. `PROVISIONAL_NOT_ELIGIBLE`、`CONSENSUS`和`UNVERIFIED`内容不得用于业务结论或证据引用。

## 2. 固定分析模块

对每个L4输出：

- 交付物角色；
- 所需具体能力；
- AI重塑方式；
- 质量锚点；
- AI负责；
- 人负责；
- 转人工条件；
- 不可绕过控制门；
- 数据依据；
- 流程背景；
- 风险/限制；
- 当前建议。

对每个可追溯任务输出建议Tier及理由；对每个L3输出优先级草稿和负责人决策草稿。

若L4含正式`skill_feasibility`，必须在以下字段中体现其影响：

- `specific_capabilities`：A/B档中的可封装能力与需拆分动作；
- `ai_reshape`：说明是确定性Skill执行、Agent辅助还是仅优化信息流；
- `risks_limits`：复合动作、资金关卡、物理执行和前置治理条件；
- `current_recommendation`：使用双轴设计路径，但不得仅凭封装档位摆放象限。

### 任务固定字段

`task_id, l4_code, task_name, source_type, sequence_no, sequence_status, source_step_id, source_line, previous_task_ids, next_task_ids, relation_type, evidence_refs, analysis_status, suggested_tier, tier_rationale`

- 每个L4至少输出一条具体工作任务；
- 蓝图对同一L4列出多个可独立执行、交接或验证的步骤时，每个步骤分别输出任务卡，不得压缩成一条泛化任务；
- Skill可行性证据将L4标记为“复合动作（建议先拆分）”时，至少输出两张分别可执行和讨论的任务卡；
- 只有名称不同但实质属于同一连续动作的蓝图文字才可合并，合并理由写入`tier_rationale`；
- `suggested_tier`只能是 `Human / Aug / Hybrid / Auto`；
- 任务名称必须是可执行动作，不得把L4名称或整段来源材料当作任务；
- `sequence_status`只能是`SOURCE_CONFIRMED / SOURCE_STEP_ONLY / UNCONFIRMED`；
- 只有蓝图、SOP或规则明确给出前后关系时才能使用`SOURCE_CONFIRMED`；
- 多个任务只能共同定位到同一蓝图步骤、但步骤内先后不明确时使用`SOURCE_STEP_ONLY`，
  它们在页面中并列展示，不得根据任务ID或模型返回顺序虚构先后；
- 无时序证据时使用`UNCONFIRMED`，由工作坊补充确认；
- `relation_type`只能表达来源中明确存在的顺序、并行、分支或返回关系；
- 面向系统展示的任务、分析和决策不得出现具体人员姓名；将来源姓名概括为岗位族、部门或授权决策角色，原始证据引用保持不变；
- 不得返回字段别名，也不得将结果包裹在 `output_contract` 中。

### 负责人决策固定字段

`priority, task_ids, title, pilot_scope, human_boundary, evidence_refs, analysis_status`

- 至少输出一条决策；
- `task_ids`只能引用本次输出并通过证据校验的任务；
- 决策必须说明先试哪个任务、试点边界以及必须由人承担的控制责任。

## 3. 证据要求

- `evidence_refs`不能为空；
- 引用必须来自当前L3事实包；
- 推导结论应说明其使用的输入字段；
- 证据冲突时并列展示，不替换原值；
- 输入不足时返回缺失态，不允许用行业常识填空。
- 只能引用`ACTIVE`且非`CONSENSUS`的证据ID；待佐证内容即使出现在事实包中也不得使用。

## 4. 版本与复核

输出必须记录模型名称、模型版本、提示词版本、生成时间和输入快照Hash。
模型输出进入页面时统一显示为“模型分析草稿”，经过负责人确认后才能另存为工作坊共识。
