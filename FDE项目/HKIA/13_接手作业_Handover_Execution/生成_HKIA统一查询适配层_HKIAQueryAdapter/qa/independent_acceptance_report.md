# HKIA统一查询适配层v1 · 独立验收报告

验收日期：2026-09-01  
依据：`任务_HKIA统一查询适配层_v1.md`  
结论：**PARTIAL，不接受执行方报告中的“技术适配层PASS”；当前不宜直接交给其他模型作为防误用标准接口。**

## 1. 已通过

- 执行方自带15项单元测试及17项验收检查全部通过。
- 旧基础Gate 25/25、公司桥Gate 17/17继续通过。
- Q1—Q4核心取数与期望值一致。
- 5库使用只读连接；本轮查询前后5个DB的SHA256完全一致。
- 2024 L16 vs 2025 L1、+65.4%发布请求、未知query_type及已覆盖的SQL字段注入会被阻断。
- v2.1公司桥仍保持68行实体键一致及两年度金额闭合。

这些结果证明底层数据和部分白名单查询可用，但不足以证明接口无法被模型误用。

## 2. 独立黑盒结果

新增20项契约/反向检查仅3项通过、17项失败。机器证据见 `qa/independent_acceptance_result.json`。

### P0：单位门禁可绕过

- count指标请求未知单位`euro`返回成功；数据行为仍是count，但metadata把output_unit标成euro。
- 金额指标请求`output_unit=count`同样返回成功；数据仍是千港元，但metadata标成count。

根因在 `units.py`：count分支把归一化失败的单位None当作允许值；金额分支又允许count作为输出。`client.py`仅在两端都是金额单位时转换，其他不一致组合静默跳过。结果是“数值单位”和“声明单位”分裂，属于模型接入的硬阻断缺陷。

### P0：请求白名单没有语义约束

以下请求均被错误接受：

- `limit=-1`返回全部57家公司；`limit=1,000,000,000`也被接受，没有上下限。
- 年度certified指标请求2025，返回成功空集并标certified，而不是拒绝不支持年度。
- 公司排名请求`entity_scope=market_total`，实际仍查insurer并返回成功，属于scope覆盖被静默忽略。
- `financial_snapshot`搭配年度L16指标仍返回3项财务数据，metadata却描述L16及千港元，说明query_type与metric兼容性未统一检查。
- `periods`传字符串而非数组，返回通用`HKIA_ERROR`内部错误，不是稳定的`VALIDATION_ERROR`。

任务要求“未声明/不支持字段拒绝、limit有边界、期间匹配period_basis、客户端不能覆盖scope”。当前只检查了字段名，没有检查字段类型、值域及查询组合。

### P0：身份桥只被校验，没有进入查询结果

`company_period_values`计算了entity_key变量，但SQL仍按原始`entity`字符串查询，结果也不返回entity_key或record_status。`identity_mode=lineage`没有独立语义实现。

目录声明2025 provisional指标支持`company_period_values`，实现却只支持annual层，2025请求直接失败。因而“公司跨年使用v2.1桥”目前是文档/前置校验，尚不是完整查询能力。

### P0：统一响应契约未落实

- `list_metrics`和`describe_metric`在QueryBuilder里生成了`metric_ids`/`metric`，但响应组装只读取`res.data`，最终两个接口都成功返回空data。
- 数值行没有统一携带entity_scope、certification、schema；市场趋势行仅有period/value/unit。
- lineage的source_files/checksums恒为空，query_template_id对所有查询恒为Q1模板。
- metadata字段为`source_db`而非约定的`source_db_id`，data_version固定为字符串v1，没有资产版本依据。
- 未交付成功/失败响应JSON Schema文件，现有测试只检查顶层8个键存在。
- CLI在`json.load()`处于try之外；输入损坏JSON时产生traceback、stdout没有JSON错误响应。

这些缺陷会使其他模型无法可靠判断数字来源、单位、状态和可发布边界。

## 3. 未完成的任务书Gate

- [x] `verify_u20_call.py`继续通过。
- [x] `verify_u20_r3fix.py`继续通过。
- [ ] 适配层自身测试覆盖全部任务要求：现有测试缺limit/类型/scope/期间、L11、pre-RBC↔RBC、身份桥真实使用、客户端覆盖策略、CLI错误和逐行契约。
- [x] 已覆盖的Q1—Q4结果与DB一致。
- [ ] 所有防误用测试硬失败：单位、scope、期间及query/metric组合存在绕过。
- [x] 独立验收已验证源DB查询前后哈希不变；执行方原报告仅凭只读代码声明，没有记录哈希证据。
- [x] 示例未直接import sqlite3或CSV。
- [x] README包含边界、禁止事项、示例与升级方式。
- [ ] acceptance_result逐项反映真实状态：执行方文件仍写overall PASS，未包含本报告发现的失败项。
- [x] 报告区分技术接入与分析发布，但技术PASS结论不成立。

另外，指标目录只有9项，其中6项缺少任务书要求的comparable_with、source_definition或release_policy_id；没有可执行的L11与pre-RBC/RBC指标门禁测试。Q4以一个债务证券metric返回三个资产项目，另外两个项目没有各自目录定义。

## 4. 验收判定

当前状态应为：

- 底层5库及公司桥：PASS；
- Q1—Q4固定示例：PASS；
- HKIA统一查询适配层v1：**PARTIAL**；
- 供其他模型进行受控标准化接入：**NOT READY**；
- 同口径增长发布：NOT PASS。

根据任务书，“任一硬阻断测试失败，整体不得标PASS”。执行方`qa/acceptance_result.json`及`qa/acceptance_report.md`的技术PASS结论需要撤回或更新。

## 5. 最小整改顺序

1. 建立单一请求Schema校验层：类型、枚举、limit/offset、期间、scope、query_type×metric兼容矩阵全部先验校验。
2. 修复单位矩阵，任何未知、count↔金额或声明/实际不一致都硬失败。
3. 让identity/lineage真正参与跨期查询，并在每行返回source_name、entity_key、business_lineage、record_status和bridge evidence。
4. 重构响应组装，修复list/describe；所有数值行补单位、期间、scope、认证、schema；为每个模板返回真实source file/checksum/version。
5. 补成功/错误JSON Schema与CLI错误封装。
6. 把本轮20项独立检查并入正式回归，再补L11、pre-RBC/RBC、配置安装及自定义配置目录测试。
7. 全部通过后重新生成acceptance_result，旧PASS不得继续作为有效验收凭证。

本轮仅新增独立验收脚本、结果和报告，没有修改适配层业务实现、源DB、配置或公司桥。
