# ICD-T004 · AIA JSON分红实现率解析与入库

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：DISPATCHED（TD/TB口径方案已确认）  
> 派发日期：2026-09-03

## 目标

实现AIA静态JSON从原始快照到`fulfillment_ratio`的首个完整业务闭环，严格区分AD/TD、报告年度和观察年度，并保留原始产品名与证据链。

## 允许范围

- `06_开发技能_Develop_Skills/skills/`新增JSON解析和标准化模块
- `05_集成工具_Integrate_Tools/tools/`补充事务写入能力
- `04_定义Agent_Define_Agent/agents/agent.py`增加解析/单源闭环CLI
- `09_测试与调试_Test_and_Debug/tests/`测试及小型脱敏fixture
- `07_接入记忆_Integrate_Memory/`仅写受控真实验证快照/临时数据库，最终运行库是否保留须在回执说明
- `README.md`、`settings.json`、本任务书回执、任务日志执行方回执区

禁止修改T001契约与注册表、禁止ICD外写入、禁止Git提交或自行标ACCEPTED。

## 功能要求

1. 解析AIA结构`report_year + pData[]`，每产品读取`productNm/type/AD[]/TD[]`及逐年`ratio`。
2. 结构缺键、类型错误、零产品、零业务记录必须明确失败，不写业务表；不得静默跳过未知结构。
3. AD与TD逐条落库；`report_year`取披露年度，`observation_year`取数组对应年份，二者不得互换。
4. 百分比按T001契约存小数比率，保留`raw_value`；空值/不可解析值按门禁规则处理并记录错误。
5. 同一`run_id`重复解析幂等；同源业务写入使用事务，任何硬失败不得留下部分业务行。
6. `parse_result`准确记录OK、ZERO_RECORD、STRUCTURE_MISMATCH或PARTIAL及记录数。
7. 业务记录必须通过`run_id`反查真实URL、时间、哈希和快照路径。

## 验收标准

1. fixture覆盖多产品、AD/TD并存、跨年份、2015年前标签或非标准年份表达、空数组、坏比例、重复执行、结构漂移和中途失败回滚。
2. 数值断言至少覆盖`100%→1.0`、`94%→0.94`、超过100%的合法值。
3. 记录数等于所有合法AD/TD观测项之和，产品不静默丢失。
4. 解析不访问网络；真实验证通过T003先抓取AIA注册表URL，再解析快照。
5. 真实验证记录HTTP状态、哈希、产品数、AD/TD记录数、报告年度和至少3个官网原始数值抽查；若网络失败必须如实标记，不能用fixture替代真实PASS。
6. 全量旧测试无回归，测试不污染默认数据库。

## 执行回执

由vscode-deepseek追加，分开记录fixture结果和真实网络结果。

## 决策补充 · 2026-09-03

Jasper确认以下Schema修订，作为T004前置工作：

1. `fulfillment_ratio`新增`scope_currency_raw TEXT NOT NULL DEFAULT 'All'`。
2. 唯一键增加`scope_currency_raw`，允许同产品/红利类型/年份/run按币种分组保存多行。
3. 原样保存官网值`All`、`USD`、`HKD / MOP`，不拆分组合币种，不擅自映射为单币种。
4. 本任务额外授权修改`03_规划项目结构_Plan_Project_Structure/data_contract.md`、`05_集成工具_Integrate_Tools/tools/sqlite_store.py`及对应测试；不得改变其他已确认口径。
5. 若检测已有旧Schema数据库，必须明确失败并给迁移提示，或安全迁移；不得假装新列已存在。

## 第二项决策补充 · 2026-09-03

Jasper确认：

1. 标准指标枚举调整为`AD/TD/RB/TB/TCV/OTHER`。
2. 新增`metric_type_raw TEXT NOT NULL`，保存官网原始字段名；AIA分别写`AD/TD/RB/TB`。
3. RB与TB不得映射或合并到AD/TD；`REVERSIONARY`旧标准值移除，迁移实现必须明确处理旧Schema。
4. 唯一键至少包含`metric_type`与`scope_currency_raw`，保证官方不同指标及币种组均可无损保存。
5. 测试和真实验证必须覆盖RB/TB产品，记录数统计覆盖AIA全部四类字段，不得只解析AD/TD的53个产品。
