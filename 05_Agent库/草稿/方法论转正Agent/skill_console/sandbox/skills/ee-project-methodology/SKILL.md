---
name: ee-project-methodology
description: "Knowledge base from 《EE 项目启动与运行方法论 · 负责人执行手册 v1.0》（2026-09-09，源自 RW LinkedOut 项目经验）. Use when launching or running an EE project, applying the fact seven-state model, Evidence A–D grading, Readback, task minimum fields, G0–G5 Gates, recovery steps or startup acceptance, or when referencing the handbook's chapters."
---

<!-- argument-hint: [topic, framework name, or chapter number] -->

# EE 项目启动与运行方法论 · 负责人执行手册 v1.0
**来源**：EE（Mark 发布），基于 RW LinkedOut 项目截至 2026-09-09 的材料 | **章节**：本技能 10 章（对应手册 20 节） | **生成**：2026-11-12

## 如何使用本技能
- **不带参数**：加载下面的核心框架。
- **带主题**：如 `Gate`、`Readback`、`七态`、`恢复`，我会先读对应章节再回答。
- **带章节号**：如 `ch08`，直接加载该章。
- 遇到核心框架没覆盖的问题，我会先读相关章节文件再回答，并标出章节出处。

---

## 核心框架与判断
- **启动是一个结论，不是一个动作**：建群、开会、发任务、建文件夹都不等于已启动。范围、共同事实、责任人、执行主账、验收证据、阶段门同时建立，才算进入受控执行（ch01）。
- **项目开始的五项证据**：唯一工作区和入口、经确认的章程和范围、实名责任和 Readback、执行主账和阶段门、证据索引和关闭规则（ch01）。
- **六层控制**：方向、事实、责任、执行、验收、汇报恢复；Dashboard 不能替代主账，主账一行状态不能替代交付物（ch02）。
- **Project 层与 Case 层并行**：只有 Project 没有真实 Case 就变成文件建设；Case 的失败和终止也是有效结论，只要有确认和证据（ch02）。
- **事实七态**：只有 CONFIRMED 可作为已完成事实；PRINCIPLE AGREED、TASK TO VERIFY、PROPOSED、TARGET STATE 都不可以；FUTURE SCOPE 不进当前必达；PLACEHOLDER 不计成果（ch05）。
- **事实优先级**：基线 ＞ 正式 Decision 和签署文件 ＞ 执行主账 ＞ Dashboard 和周报 ＞ 纪要、IM、邮件、口头。低优先级不能直接覆盖高优先级（ch05）。
- **任务 11 个最低字段**：ID、动作和对象、Owner、Due、交付物、验收人、验收标准、依赖、证据路径、状态和 RAG、下一动作。出现「推进、跟进、尽快、待定、等待反馈」即不合格（ch06）。
- **Readback**：一个工作日内回答六问；沉默不视为接受；已读只证明信息到达（ch06）。
- **执行状态**：DELIVERED（未验收）≠ DONE（证据加验收）≠ CLOSED（已回写）（ch07）。
- **Evidence 四级**：A 可支持正式验收；B 支持内部执行；C 只能形成验证任务；D 不能证明能力或结果（ch07）。
- **Gate 看条件不看日期**：G0 启动授权、G1 事实基线、G2 执行准备、G3 交付形成、G4 真实验证、G5 运行或关闭，各有最低证据和允许结论；硬边界（上线、对外发布、真实个人数据、受规管活动、签约或收费）必须另设专业 Gate（ch08）。
- **恢复不是顺延**：冻结扩张 → 恢复基线 → 逐项 Disposition → 实名 Readback → 恢复关键路径 → 证据关闭 → 账板对账（ch09）。
- **启动验收 10 项**：任一关键项未通过，只能标「启动中、条件启动或阻塞」，不得对外表述为正常运行（ch10）。
- **角色边界**：Principal 批准 Gate；专业结论只能由专业 Owner 书面给出；Case Manager 维护事实，不编造结论（ch04）。

---

## 章节索引
| # | 标题 | 关键框架 |
|---|---|---|
| [ch01](chapters/ch01-scope-and-start-evidence.md) | 使用范围、负责人职责与项目开始的五项证据 | 五项证据、负责人必须先确认的五件事 |
| [ch02](chapters/ch02-control-model.md) | 六层项目控制模型，Project 层与 Case 层 | 六层控制、Project 对 Case |
| [ch03](chapters/ch03-launch.md) | 启动前准备与启动十个工作日 | 准备五步、D 减三至 D 加十、启动完成判断 |
| [ch04](chapters/ch04-roles.md) | 角色和责任 | 七角色三栏表 |
| [ch05](chapters/ch05-common-facts.md) | 共同事实控制 | 七态、五级优先级、变更六步 |
| [ch06](chapters/ch06-tasks-and-readback.md) | 任务拆解标准与 Readback | 六级拆解、11 字段、九段主线、Readback 六问 |
| [ch07](chapters/ch07-ledger-evidence-closure.md) | 执行主账、Dashboard、Evidence 与状态关闭 | 主账对象、版本控制、执行状态、A–D、验收链 |
| [ch08](chapters/ch08-gates.md) | Gate 阶段验收 | G0–G5、硬边界、Gate 记录 |
| [ch09](chapters/ch09-cadence-and-recovery.md) | 周度节奏、逾期和项目恢复 | 周节奏、会议规则、RAG、恢复七步、首月行动表 |
| [ch10](chapters/ch10-acceptance-templates-and-lessons.md) | 启动验收、文件结构、交办模板与 LinkedOut 经验 | 启动验收 10 项、最小目录、模板、九条教训 |

## 主题索引
- **Archive** → ch05, ch07, ch10
- **CONDITIONAL GO** → ch08, ch09
- **Case / Case Owner** → ch02, ch04, ch07
- **Dashboard** → ch02, ch07, ch09
- **Evidence 等级（A–D）** → ch07
- **G0 至 G5（G零 至 G五）** → ch08, ch03, ch09
- **RAG / 优先级** → ch06, ch09
- **Readback** → ch06, ch03, ch09
- **SteerCo** → ch04, ch09
- **执行状态（DELIVERED / DONE / CLOSED 等）** → ch07
- **事实七态 / 事实优先级** → ch05
- **任务最低字段 / 任务书** → ch06, ch10
- **启动十个工作日** → ch03
- **启动验收** → ch10, ch01
- **硬边界 Gate** → ch08
- **恢复七步法 / Disposition** → ch09
- **周报 / 会议规则** → ch09, ch10
- **最小文件结构** → ch10
- **LinkedOut 经验** → ch10

## 配套文件
- [glossary.md](glossary.md)：全部关键术语及定义
- [patterns.md](patterns.md)：全部方法与流程
- [cheatsheet.md](cheatsheet.md)：决策规则、Gate 速查、三套状态对照

---

## 范围与限制
本技能只覆盖手册内容。手册是通用方法，来源项目（LinkedOut）的商业、法律、技术或合作方事实不能直接套用到新项目。具体项目的结论仍需该项目自己的证据和有权人签署。
