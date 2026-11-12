# 第 8 章：Gate 阶段验收
（对应手册：第十二节；Gate 记录最小结构见第十八节）

## Core Idea
Gate 控制的是「是否具备进入下一阶段的条件」，不是检查日期是否到达。Gate 名称可按风险调整，但必须保留进入条件、证据、验收人、结论和附带条件。

## Frameworks Introduced
- **G0–G5 阶段门**（手册原文写作 G零 至 G五）：
  | Gate | 通用目标 | 最低证据 | 允许结论 |
  |---|---|---|---|
  | G0（G零） | 启动授权 | 目标、范围、Owner、唯一入口 | GO、HOLD、STOP |
  | G1（G一） | 事实基线 | 事实状态、来源、差距和 Decision | GO、CONDITIONAL GO、HOLD |
  | G2（G二） | 执行准备 | 计划、自然人 Owner、资源、依赖、风险、专业前置 | GO、CONDITIONAL GO、HOLD |
  | G3（G三） | 交付形成 | 规定交付物、内部检查和版本记录 | ACCEPT、REWORK、HOLD |
  | G4（G四） | 真实验证 | 真实或指定数据、对象反馈、运行结果、异常记录 | PASS、PARTIAL、FAIL |
  | G5（G五） | 运行或关闭 | 验收、签收、主账回写、残余风险和运营 Owner | OPERATE、SCALE、CLOSE、STOP |
- **硬边界 Gate**：上线、对外发布、使用真实个人数据、开展受规管活动、签约或收费，必须增加相应的法律、数据、安全、牌照、财务或授权 Gate。**项目日期不能代替这些批准。**
- **Gate 记录最小结构**：Gate 和日期、进入条件、提交证据、未满足项、结论（GO / CONDITIONAL GO / HOLD / STOP）、附带条件和 Due、批准人、主账回写（版本、日期、经办人）。

## Key Concepts
- **CONDITIONAL GO**：带附带条件和 Due 的通过。
- **允许结论**：每个 Gate 只能用表中规定的结论用语。
- **Gate Review**：阶段点的固定动作，由 Principal 批准（见第 4 章）。

## Mental Models
- 问「条件齐了吗」，不问「日子到了吗」。
- 不同 Gate 结论词不同：G3 用 ACCEPT/REWORK，G4 用 PASS/PARTIAL/FAIL，不能混用。

## Anti-patterns
- **活动日期压过岗位或数据 Gate**（第 10 章 LinkedOut 经验）。
- **用「差不多可以」代替规定结论用语**。
- **硬边界事项没有专门 Gate**。

## Worked Example（示意，非手册原文）
> 手册本身没有示例。以下场景为说明规则用的虚构示意，规则依据见本章上文。

G2 执行准备 Gate 的一次评审：计划和自然人 Owner 已齐，但数据专业前置（数据使用授权）未取得 → 结论可为 CONDITIONAL GO，附带条件「数据授权书于 D 加十前取得，未取得则涉及真实数据的工作流 HOLD」，写入 Gate 记录并回写主账。若该事项属于「使用真实个人数据」，则必须另设数据 Gate，不能由日期或 G2 结论代替。

## Key Takeaways
1. 六个 Gate，各有目标、最低证据和允许结论。
2. 硬边界事项必须单设专业 Gate。
3. Gate 记录要回写主账。

## Connects To
- **第 3 章**：G1 在 D 加五、G2 在 D 加七。
- **第 9 章**：首月行动表中 G0 到 G5 的推进节奏。
