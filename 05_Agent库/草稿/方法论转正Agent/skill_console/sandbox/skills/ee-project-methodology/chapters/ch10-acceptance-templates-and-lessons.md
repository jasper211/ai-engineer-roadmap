# 第 10 章：启动验收标准、最小文件结构、交办模板与 LinkedOut 经验
（对应手册：第十六至二十节）

## Core Idea
新项目用 10 个验收项判断能否从「启动中」转为「正常运行」；任一关键项未通过，只能标记为启动中、条件启动或阻塞，不得对外或向管理层表述为已正常运行。

## Frameworks Introduced
- **新项目启动验收 10 项**（手册表格为 11 行 × 3 列，含 1 行表头）：
  | 验收项 | 通过标准 | 验收人 |
  |---|---|---|
  | 唯一入口 | 入口文件能直接找到当前基线、主账、Dashboard 和负责人 | Principal |
  | 章程和范围 | 目标、周期、成功标准、不做事项和变更方法已确认 | Owner |
  | 共同事实 | 每项关键事实有状态、Owner、来源和下一动作 | Principal |
  | 角色 | 关键角色有任务书和 Readback，没有匿名 Owner | Owner 和 Principal |
  | 主账 | Action、RAID、Case、Evidence 字段完整且可更新 | Case Manager |
  | 第一批对象 | 至少一个真实对象具备来源、决策人、授权和成功标准 | 业务 Owner |
  | 专业边界 | 法律、财务、数据、安全、牌照等前置已指定专业 Owner | 相应专业 Owner |
  | Gate | 启动和执行准备 Gate 有书面结论 | Principal |
  | 更新节奏 | 每日、周会、周五锁定和升级规则明确 | Case Manager |
  | 账板一致 | Dashboard 标明主账版本且状态一致 | Principal 抽查 |
- **最小文件结构**：00 项目入口 / 01 章程范围与角色 / 02 共同事实与 Decision / 03 执行主账与 Dashboard / 04 Readback 与任务认领 / 05 周报与会议 / 06 证据与交付 / 07 Case / 90 Archive。名称可调，职责不能混。
- **交办模板**：项目负责人任务书（项目名称、目标和周期、本期必达、明确不做、第一批真实对象、Principal、Case Manager 或 PM、工作流和 Owner、D 加一 Readback、第一阶段 Gate、重大风险和专业前置、验收人和关闭标准）；周报最小结构（可验收结果和 Evidence ID、事实和 Decision 变化、Project 与 Case 状态、P0/红灯/逾期与恢复、待决定事项、下周交付/Owner/Due、主账与 Dashboard 版本和更新时间）。
- **LinkedOut 经验转化表（观察到的问题 → 通用控制）**：
  - 岗位类型和平台内容被误作真实需求 → 候选库、真实 Demand 与 Case 分层，Gate 批准；
  - 任务发出但 Owner 未明确接受 → D 加一 Readback 和自然人责任；
  - 旧 Due 积累成大量逾期 → 逐项 Disposition 和恢复任务书；
  - 有文件但没有验收和 Evidence → 交付、证据、验收、回写四步关闭；
  - Dashboard 与主账状态漂移 → 主账作为 SSOT，Dashboard 从主账生成；
  - 目标主体或目标能力被写成已完成 → TARGET STATE 与 CONFIRMED 分离；
  - 专业判断由项目管理角色代替 → 专业 Owner 和专门 Gate；
  - 活动日期压过岗位或数据 Gate → 日期不能替代进入条件；
  - 资料迁移后入口仍指向旧版本 → 唯一入口和 FILE INDEX 同步维护。
- **依据与交接**：手册基于 RW LinkedOut 项目截至 2026-09-09 的治理和执行材料归纳；这些材料提供方法来源，不代表其中商业、法律、技术或合作方事实可直接复制到新项目。交接时连同章程、负责人任务书、主账模板一并交给负责人，要求一个工作日内 Readback；第一次 Gate Review 重点检查唯一事实源和第一批真实对象，而不是文件数量。

## Key Concepts
- **条件启动**：部分关键项未通过时的合规表述之一。
- **FILE INDEX**：入口文件中的当前文件清单。

## Mental Models
- 对外说「正常运行」之前，先过一遍验收表。

## Anti-patterns
- **未过验收就对外宣称正常运行**。
- **把来源项目的事实直接复制到新项目**。

## Key Takeaways
1. 用验收表判断启动是否完成，每项都有指定验收人。
2. 九个目录职责分离。
3. LinkedOut 的九条教训已转化为通用控制。

## Connects To
- **第 1 章**：五项证据是验收表的浓缩版。
- **第 8 章**：Gate 记录最小结构。
