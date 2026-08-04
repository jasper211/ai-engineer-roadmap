# Phase A：HR域全链路命题链示范 v0.1

> 状态：草稿
> 定位：`00_VNW流程分析框架总蓝图_v0.2.md` 第4节 Phase A 的实际产出——用 HR 域（L3-HRA/HRM/SPE）做一次完整的 Fact→Evidence→Claim 示范，检验命题链方法本身跑不跑得通
> 数据来源：`model_snapshots/L3-HRA.json` / `L3-HRM.json` / `L3-SPE.json`，2026-08-04 读取

---

## 1. Fact（事实——照系统读，不加解读）

| fact_id | L3 | 陈述 | 字段 | 来源 |
|---|---|---|---|---|
| F-HR-001 | L3-HRA | Gate M = PASS | gates.M.status | L3-HRA.json#gates |
| F-HR-002 | L3-HRA | Gate E = PASS | gates.E.status | L3-HRA.json#gates |
| F-HR-003 | L3-HRA | Gate A = BLOCKED | gates.A.status | L3-HRA.json#gates |
| F-HR-004 | L3-HRA | 价值节点 VN-HR-04（人效分析报告，P1）标记为熔断 | value_nodes[VN-HR-04].is_fused=true | L3-HRA.json#value_nodes |
| F-HR-005 | L3-HRA | 价值节点 VN-HR-05（人力资源诊断与改善建议报告，P0）标记为熔断 | value_nodes[VN-HR-05].is_fused=true | L3-HRA.json#value_nodes |
| F-HR-006 | L3-HRA | 该L3共2个价值节点，2个（100%）处于熔断状态 | 对value_nodes聚合计数 | 派生自F-HR-004/005 |
| F-HR-007 | L3-HRM | Gate M = PASS | gates.M.status | L3-HRM.json#gates |
| F-HR-008 | L3-HRM | Gate E = PASS | gates.E.status | L3-HRM.json#gates |
| F-HR-009 | L3-HRM | Gate A = BLOCKED | gates.A.status | L3-HRM.json#gates |
| F-HR-010 | L3-HRM | 价值节点 VN-HR-08（员工成长路径方案，P1）标记为熔断 | value_nodes[VN-HR-08].is_fused=true | L3-HRM.json#value_nodes |
| F-HR-011 | L3-HRM | 价值节点 VN-HR-10（员工档案，P0）标记为熔断 | value_nodes[VN-HR-10].is_fused=true | L3-HRM.json#value_nodes |
| F-HR-012 | L3-HRM | 该L3共7个价值节点，2个（29%）处于熔断状态，其余5个（VN-HR-06/07/09/13/14）正常 | 对value_nodes聚合计数 | 派生自value_nodes |
| F-HR-013 | L3-SPE | Gate M = PASS | gates.M.status | L3-SPE.json#gates |
| F-HR-014 | L3-SPE | Gate E = PASS | gates.E.status | L3-SPE.json#gates |
| F-HR-015 | L3-SPE | Gate A = PASS | gates.A.status | L3-SPE.json#gates |
| F-HR-016 | L3-SPE | 该L3共3个价值节点（VN-HR-03/11/12），0个熔断 | 对value_nodes聚合计数 | L3-SPE.json#value_nodes |

---

## 2. Evidence（这些事实分别支持哪句结论）

| evidence_id | fact_id | claim_id | 关系 | 说明 |
|---|---|---|---|---|
| E-HR-001 | F-HR-004, F-HR-005, F-HR-006 | C-HR-001 | supports | HRA全部价值节点熔断，直接对应Gate A检查项A-004"存在熔断或无价值节点" |
| E-HR-002 | F-HR-010, F-HR-011, F-HR-012 | C-HR-002 | supports | HRM部分（2/7）价值节点熔断，同样触发A-004 |
| E-HR-003 | F-HR-016 | C-HR-003 | supports | SPE零熔断，A-004通过 |
| E-HR-004 | F-HR-006, F-HR-012, F-HR-016 | C-HR-004 | supports | 三个L3的熔断比例与Gate A结果对照 |

---

## 3. Claim（结论，带分级）

### C-HR-001（A级）
**L3-HRA 当前无法进入AIT阶段，直接原因是其2个价值节点（VN-HR-04人效分析报告、VN-HR-05人力资源诊断与改善建议报告）100%处于熔断状态。**
- 分级理由：单一权威字段直接读取，2/2节点均为`is_fused=true`，不需要推导。
- 推翻条件：VN-HR-04或VN-HR-05任一项熔断状态解除后，需重新判定Gate A。
- status：MODEL_DRAFT

### C-HR-002（A级）
**L3-HRM 当前无法进入AIT阶段，直接原因是其7个价值节点中有2个（VN-HR-08员工成长路径方案、VN-HR-10员工档案）处于熔断状态，其余5个正常。**
- 分级理由：同上，直接读取字段。
- 推翻条件：VN-HR-08、VN-HR-10均解除熔断后，需重新判定Gate A。
- status：MODEL_DRAFT

### C-HR-003（A级）
**L3-SPE 已通过Gate A，其3个价值节点均未熔断。**
- 分级理由：直接读取字段。
- 推翻条件：未来任一价值节点被标记熔断，Gate A可能重新判定为BLOCKED。
- status：MODEL_DRAFT

### C-HR-004（B级）——比较性结论，不是简单复述规则
**如果按"解除阻断需要处理的熔断节点数量"衡量，HRM（需处理2个）看起来比HRA（需处理2个，但占其全部价值节点的100%）更接近解除阻断；但两者各有1个P0优先级节点卡着（HRA的VN-HR-05、HRM的VN-HR-10），不能简单说HRM明显更容易解除。**
- 分级理由：三个L3的熔断节点数与Gate A结果方向一致（支持"存在熔断即阻断"这条已知规则，这部分本身是A级，因为是系统检查项A-004自己声明的逻辑），但"用节点数量代表解除阻断所需工作量"是我加的一层解读，没有验证——解除一个P0节点的熔断，实际工作量可能远大于解除一个P1节点，"数量"不等于"难度"，这个替代解释没有排除，所以整条比较性结论只能标B，不能标A。
- 替代解释（未排除）：熔断节点数量可能跟解除难度无关，真正决定难度的是节点本身的业务复杂度，不是数量。
- 推翻条件：如果HRM的2个熔断节点解除耗时远长于HRA的2个，则推翻"HRM更接近解除"这个判断。
- status：MODEL_DRAFT

---

## 4. Phase A 验收自查

对照 `00_VNW流程分析框架总蓝图_v0.2.md` 第4节的验收标准——"任意一条结论都能回答来自哪里、用什么口径、支持哪个命题、谁签核、什么会推翻"：

| 检查项 | 结果 |
|---|---|
| 来自哪里 | 每条Claim都能追到具体evidence_id→fact_id→JSON字段路径，链路完整 |
| 用什么口径 | Fact表的"字段"列明确写了具体读取路径，不是笼统的"数据显示" |
| 支持哪个命题 | Evidence表逐条列出fact→claim的关系 |
| 谁签核 | **缺失**——status目前只有MODEL_DRAFT一种状态，没有owner/reviewer字段。这是故意的：VNW"不得静默转正"的原则下，还没有人真正要签核这几条结论，先不造一个没人用的字段；等真的有人（Jasper）要确认某条Claim时，再补上signed_by/signed_at |
| 什么会推翻 | 每条Claim都有明确的推翻条件 |

**结论**：命题链方法本身跑得通，能满足4/5验收项；"签核"这项缺失是有意暂缓，不是漏做。

---

## 5. 这次示范暴露的新缺口

- Gate A 检查项 A-004 的判定逻辑（"存在即阻断"还是有别的阈值）本轮是从检查项文本反推的，没有去读 `l3_model_builder.py` 里 A-004 具体怎么实现，如果检查文本和代码实现不一致，C-HR-004 的A级子结论会站不住——这条建议下次核实一下代码。
- "熔断节点数量代表解除难度"这个替代解释怎么排除，需要真实的"解除熔断所需工作量"数据，VNW目前没有这类数据，C-HR-004 大概率会长期停在B级，除非有人补充这块信息。
