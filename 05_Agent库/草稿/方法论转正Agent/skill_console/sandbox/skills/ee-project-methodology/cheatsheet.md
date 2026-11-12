# 速查表：按手册的判断去做决定

## 决策规则
- 有人说「项目已启动」→ 先查五项证据；任一缺失 → 状态写「启动中」（Ch 1, Ch 10）。
- 一个事实不是 CONFIRMED → 不得写成已完成；TARGET STATE 尤其要和 CONFIRMED 分开（Ch 5）。
- 低优先级输入（会议、聊天、邮件）与基线冲突 → 登记冲突、Owner、影响和建议，不直接覆盖（Ch 5）。
- 任务出现「推进 / 跟进 / 尽快 / 待定 / 等待反馈」→ 退回重写字段（Ch 6）。
- 发出任务一个工作日内没有 Readback → 视为未接受，由 Principal 决定（Ch 6）。
- 交付物已发出、尚未验收 → DELIVERED，不是 DONE（Ch 7）。
- 证据只有合作方自述、BP、演示 → C 级，只能开验证任务（Ch 7）。
- 涉及上线、对外发布、真实个人数据、受规管活动、签约或收费 → 必须另设专业 Gate，日期不能代替（Ch 8）。
- 大量逾期 → 先冻结扩张、逐项 Disposition，不批量顺延 Due（Ch 9）。
- 专业判断（法律、财务、数据、牌照、安全）→ 只认专业 Owner 的书面结论（Ch 4）。

## Gate 速查（G0–G5）
| Gate | 目标 | 最低证据 | 允许结论 |
|---|---|---|---|
| G0 | 启动授权 | 目标、范围、Owner、唯一入口 | GO / HOLD / STOP |
| G1 | 事实基线 | 事实状态、来源、差距、Decision | GO / CONDITIONAL GO / HOLD |
| G2 | 执行准备 | 计划、自然人 Owner、资源、依赖、风险、专业前置 | GO / CONDITIONAL GO / HOLD |
| G3 | 交付形成 | 规定交付物、内部检查、版本记录 | ACCEPT / REWORK / HOLD |
| G4 | 真实验证 | 真实或指定数据、对象反馈、运行结果、异常记录 | PASS / PARTIAL / FAIL |
| G5 | 运行或关闭 | 验收、签收、主账回写、残余风险、运营 Owner | OPERATE / SCALE / CLOSE / STOP |

## 三套状态，别混用
| 维度 | 取值 | 注意 |
|---|---|---|
| 事实状态（七态） | CONFIRMED、PRINCIPLE AGREED、TASK TO VERIFY、PROPOSED、TARGET STATE、FUTURE SCOPE、PLACEHOLDER | 只有 CONFIRMED 算完成事实 |
| 执行状态 | NOT STARTED、IN PROGRESS、BLOCKED、DELIVERED、DONE、CLOSED、ON HOLD | 不表达健康度 |
| 健康度 RAG | GREEN / AMBER / RED | GREEN 不等于完成 |
| 优先级 | P0 / P1 / P2 | 不等于紧急程度 |

## 证据等级
A 正式合同、注册、签收、运行数据 → 正式验收｜B 已批准在用的内部标准与决策 → 内部执行｜C 自述、BP、演示 → 只能形成验证任务｜D 建议、假设、占位 → 不能证明能力或结果

## 默认节奏与阈值
- Readback：任务发出后 **1 个工作日**内。
- G1：**D 加五**；G2：**D 加七**；D 加十审查后才进入周度运行。
- 主账：每日回写；**周五锁定**并出快照；SteerCo **双周**一次。
- 恢复正常：须**连续两个**更新周期按时回写和验收。

## 危险信号
- Dashboard 与主账状态不一致 → 以主账为准，查数据源版本。
- 文件很多但没有 Evidence 和验收 → 「文件建设」，回到四步关闭。
- 入口仍指向旧版本 → 同步唯一入口和 FILE INDEX。
