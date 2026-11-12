# 第 7 章：执行主账、Dashboard、Evidence 与状态关闭
（对应手册：第十节、第十一节）

## Core Idea
执行主账是结构化事实源（SSOT），Dashboard 从主账生成；任务完成必须走完「交付 → 证据 → 验收 → 回写」，缺任何一项只能是已提交待验收或进行中。

## Frameworks Introduced
- **主账对象与字段**：
  | 对象 | 必须字段 | 维护责任 |
  |---|---|---|
  | Action | ID、工作流、优先级、动作、Owner、Due、状态、RAG、交付物、依赖、下一动作、证据、更新时间 | Case Manager 每日更新 |
  | RAID | 风险、问题、依赖、决策、Owner、影响、恢复选项、Due、决策人、结论 | Case Manager 登记，Principal 处理 |
  | Case | 真实对象、来源、授权、Owner、阶段、结果、Due、下一动作、证据 | Case Owner 更新，Case Manager 控制 |
  | Evidence | Evidence ID、对象、来源、日期、提供者、位置、验证状态、引用限制 | Case Manager 维护，专业 Owner 确认 |
  | Dashboard | 当前周期、KPI、工作流状态、红黄灯、关键决策、下一动作、数据源版本 | 从主账刷新并标明更新时间 |
  - Dashboard 的筛选和本地备注不能自动改变主账，除非已实现并验证双向同步。
- **版本控制六条**：保留永不覆盖的 issued 基线；每周一个主账版本、周内同一文件更新；新交付或 Readback 后限时回写并登记 Change Log；周五锁定主账、同步 Dashboard、导出 JSON 或 PDF 快照并生成文件清单或 hash；下周建新版本，旧版本进 Archive 并标明替代关系；入口文件和 FILE INDEX 始终指向同一个当前主账和 Dashboard。
- **执行状态（含义与禁用说法）**：
  | 状态 | 允许条件 | 不得使用的替代说法 |
  |---|---|---|
  | IN PROGRESS | 已认领并正在执行 | 已讨论、已安排 |
  | BLOCKED | 依赖或风险使下一动作无法继续，且已写明恢复方案 | 等回复 |
  | DELIVERED | 交付物已提交，但尚未验收 | 已完成 |
  | DONE | 交付物存在、Evidence 已登记、验收人已接受 | 文件已发出 |
  | CLOSED | DONE 后已回写主账、Case 和 Dashboard，残余风险有去向 | 群里说可以关闭 |
  | ON HOLD | 经 Decision 暂停，并有复审条件和日期 | 以后再说 |
- **Evidence 四级**：
  | 等级 | 典型证据 | 使用边界 |
  |---|---|---|
  | A | 正式合同、注册记录、客户签收、实际运行数据 | 可支持正式验收，仍受授权范围限制 |
  | B | 已批准并正在使用的内部标准、决策和正式交付 | 可支持内部执行 |
  | C | 合作方自述、BP、演示或未经独立验证的材料 | 只能形成验证任务 |
  | D | 建议、假设、占位或结构测试 | 不能证明真实能力或业务结果 |
- **完成和关闭的验收链六步**：执行人提交交付并说明完成与未完成范围 → Case Manager 登记 Evidence ID、来源、版本、位置 → 验收人按约定标准给出接受、返工或拒绝 → 专业事项由专业 Owner 复核 → 主账状态、下一动作、Updated At、RAID 同步 → Dashboard 和周报下次刷新时与主账一致。

## Key Concepts
- **SSOT**：主账是唯一事实源。
- **DELIVERED ≠ DONE ≠ CLOSED**：交付、验收、回写是三个不同状态。

## Mental Models
- 「文件发出了」最多是 DELIVERED。
- C 级证据只能开验证任务，不能关闭任务。

## Anti-patterns
- **把 DELIVERED 叫「已完成」**。
- **Dashboard 上改状态代替主账**。
- **用批量改状态制造「正常」**。

## Key Takeaways
1. 主账五类对象各有维护人。
2. 六个执行状态各有禁用说法。
3. 完成要走六步验收链；证据等级决定能证明什么。

## Connects To
- **第 5 章**：事实七态（事实状态）与本章执行状态是两套不同的状态机。
- **第 8 章**：Gate 的最低证据。
