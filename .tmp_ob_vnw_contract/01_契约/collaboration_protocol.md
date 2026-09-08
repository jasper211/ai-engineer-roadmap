# OB–VNW 协同协议 v1

## 1. 边界

- OB Agent 管理知识内容与 `02_OB发布/`，声明文件是什么、关联哪个 L3/L4、处于什么状态。
- VNW Agent 只读 OB 发布物和源文件，管理 `03_VNW回执/` 与 `05_运行审计/`。
- VNW 不回写 OB，不把未注册或未确认内容写入正式事实，不因扫描而自动应用快照、调用模型或部署前端。

## 2. 交接单位

一次交接由唯一 `release_id`、一份 `input_manifest.json` 和源文件内容共同构成。`source_id + sha256` 是跨 Agent 对账键。`relative_path` 必须相对 `ob_root_path`，不得越界。

OB 发布时必须提供文件级 Hash 与可复核定位。Markdown 优先提供章节或行范围；CSV 提供实际数据行范围；Excel 提供工作表与单元格范围。仅写 `WHOLE_FILE` 的大文件不得作为字段级结论的唯一定位依据。

## 3. 状态机

`DRAFT → UNDER_REVIEW → CONFIRMED → DEPRECATED` 是 OB 内容生命周期。VNW 处理状态为：

`RECEIVED → VALIDATION_FAILED | READY_FOR_REVIEW → APPLIED → REANALYSIS_REQUIRED | FACTS_REFRESHED → ANALYZED → DEPLOYED`

首版只读消费入口最多到 `READY_FOR_REVIEW`。`APPLIED` 之后的状态必须由现有 VNW 显式命令与部署流程产生，不能由交换区校验器代填。

## 4. 纳入规则

1. `CONFIRMED + PRIMARY_SSOT/CORROBORATING`：可进入正式事实候选。
2. `CONFIRMED + CONTEXT_ONLY`：只进入面板 F 的补充来源与分析逻辑说明，不参与 Gate 和自动结论。
3. `DRAFT/UNDER_REVIEW`：进入待补或待复核，不进入正式模型。
4. `DEPRECATED`：触发移除影响检查，禁止继续作为现行证据。
5. 没有 L3/L4 的业务资料不得猜测归属；方法论和数据口径文件可不绑定 L3，但必须明确知识类型。

## 5. 影响与重分析

默认面板映射以 `knowledge_type_dictionary.json` 为准。VNW 在实际构建后仍以逐字段快照比较为最终判断。

以下任一变化要求重分析：已纳入来源的 Hash、定位片段、L3/L4 归属、知识类型、证据等级、版本或状态发生变化，并改变分析输入 Hash；或新增/删除已确认来源。只改变未进入分析输入的元数据时，可只刷新事实或证据说明。

Gate 的硬条件继续服从 VNW 当前标准：缺流程蓝图、L4 或完整 D1-D6 时不生成模型；规则/SOP 缺失可生成“待完善模型”并显式展示缺口。

## 6. 运行顺序

1. OB Agent 发布并校验清单。
2. VNW 只读校验文件存在性、Hash、mtime、定位和编码。
3. VNW 生成回执与受影响 L3/面板候选，不更新前端。
4. 人工确认后，另行运行 VNW `--apply-source-updates`。
5. 分析输入 Hash 变化的 L3 另行重跑统一模型。
6. 校验通过后单独构建和部署前端。

## 7. 禁止事项

- 禁止仅凭文件名相似度自动确认 L3/L4。
- 禁止把大模型推断标成 OB 事实。
- 禁止把源文件 mtime 变化等同于内容变化；内容变化以 SHA-256 为准。
- 禁止扫描任务自动应用、自动调用模型或自动发布公网。
