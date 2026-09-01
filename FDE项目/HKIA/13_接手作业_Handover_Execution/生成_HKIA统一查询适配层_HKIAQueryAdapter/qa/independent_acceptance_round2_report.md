# HKIA统一查询适配层v1 · 第二轮独立验收

验收日期：2026-09-01  
结论：**PARTIAL。第一轮20项整改已全部通过，但第二层17项仅1项通过，暂不接受“技术适配层PASS / 其他模型接入READY”。**

## 一、确认完成的整改

- 上轮独立检查由3/20提升至20/20。
- 单位矩阵、limit上下限、单一period年度校验、scope覆盖、query_type×metric兼容已修正。
- `list_metrics`、`describe_metric`、2025 company_period_values已能返回数据。
- 主要数值行补充了scope/certification/schema；metadata改为source_db_id。
- CLI损坏JSON已返回JSON错误。
- 基础15项单测、执行方17项验收、旧基础Gate和公司桥Gate继续通过。
- 独立查询前后5个源DB哈希保持一致。

因此，上一轮报告列出的直接缺陷大部分已修复；本轮结果不是否定这些进展。

## 二、第二层黑盒结果

机器结果：`qa/independent_acceptance_round2_result.json`。17项中仅`filters`错误类型最终返回ValidationError这一项通过。

### P0：响应Schema与实际响应冲突

新增Schema要求所有响应必须包含：`ok/request_id/query_type/data/metadata/comparability/release/lineage`。

实际错误响应只有`ok/error_code/message/blocked_by/suggestion/query_type`，缺少request_id及其余五个块；CLI错误同样不符合。healthcheck的data为object，而Schema规定data必须为array。

因此当前“Schema存在”通过，但“成功和失败响应都通过Schema”未通过。必须用实际Schema校验器或等价递归验证跑所有成功/失败样例，而不是只检查文件存在或顶层键。

### P0：请求语义仍可被静默忽略

- filters中的未知字段被接受并忽略。
- periods数组中的`bad-period`未校验，接口静默返回合法期间的部分结果。
- offset=1与无offset返回完全相同的前三家公司。
- include_zero传字符串`"false"`仍被接受。
- financial fund_scope传不存在的值，返回成功空数据而不是拒绝。

任务书要求未知字段拒绝、期间匹配period_basis、排名显式处理零值。公开字段若尚未实现，应先拒绝，不能接受后忽略。

### P0：identity与lineage仍未区分

`identity_mode=entity`与`identity_mode=lineage`返回完全相同的数据；返回中没有business_lineage。当前桥只保存entity_key，未实现lineage查询语义。

此外：

- 2024零值公司`AXA China (HK)`被标为reported_value，而不是reported_zero。
- 2024缺记录的`China Re HK`返回成功空数组，没有保留`value=null + record_status=missing`。
- company_period_values没有返回bridge evidence或证据来源。

任务书明确要求区分entity/lineage、保留missing/reported_zero/reported_value，并让桥真正参与跨期响应。这一Gate仍未完成。

### P0：任务书指定口径门禁尚未交付

- 测试中没有L11 policy_count/lives/scheme_count硬阻断用例。
- 没有pre-RBC↔RBC且缺少审定桥时返回SCHEMA_BRIDGE_REQUIRED的可执行测试。
- 指标目录仍只有9项，其中6项缺comparable_with、source_definition或release_policy_id。
- Q4返回债务证券、股权、现金存款三项，但目录只有FIN_DEBT_SECURITIES；另外两项没有独立指标定义。

不能用代码中一段未被数据目录触发的字符串判断替代可执行门禁测试。

### P1：安装后无法作为包调用

`pip install --no-build-isolation --no-deps --target <temp>`安装成功，但从安装目录调用`HKIAClient.open_readonly()`失败：包内找不到`config/data_sources.json`。配置和桥资产位于Python包外，未纳入package data，也没有安装态资源定位策略。

如果其他模型只在当前源码目录内运行，可以临时绕过；但任务目标是标准接口且已提供pyproject，安装后不可用不应标READY。还需验证自定义cfg_dir会同步影响catalog/policy/identity，而不只是data_sources。

## 三、Gate判定

- [x] 5库、Q1—Q4、旧基础及桥回归通过。
- [x] 第一轮20项黑盒回归通过。
- [ ] 成功与失败响应均符合固定JSON Schema。
- [ ] 未知filters、periods元素、offset/include_zero、fund_scope严格执行或拒绝。
- [ ] entity与lineage语义分离，zero/missing和桥证据正确返回。
- [ ] L11及RBC切换门禁有真实指标与可执行反向测试。
- [ ] 指标目录所有条目字段完整，Q4返回项目全部登记。
- [ ] 安装后的包能够定位配置、桥和源数据。
- [ ] `qa/acceptance_result.json`反映全部独立Gate；当前仍只记录原17项并标PASS。

根据任务书“任一硬阻断测试失败，整体状态必须FAILED或PARTIAL”，最终状态仍为PARTIAL。`qa/final_acceptance.json`中的READY不成立。

## 四、下一轮最小整改

1. 统一成功/失败响应构造函数，让实际响应通过Schema；明确healthcheck data是array还是在Schema中作合法分支。
2. 为每个query_type定义filters子字段、类型和值域；逐项校验periods；实现或拒绝offset/include_zero。
3. 扩展桥模型，加载entity_key、business_lineage、record_status、evidence；entity与lineage走不同逻辑；missing返回显式记录。
4. 补齐L11/RBC指标和SCHEMA_BRIDGE_REQUIRED门禁测试。
5. 补齐指标目录必填字段及Q4三项独立定义。
6. 将config/schema/桥定位设计为安装态可用，增加临时安装后的healthcheck测试。
7. 将第二轮17项纳入正式回归，再更新最终验收结论。

本轮只新增第二层独立验收脚本、结果与报告，没有修改适配层业务实现、源DB、桥或执行方验收文件。
