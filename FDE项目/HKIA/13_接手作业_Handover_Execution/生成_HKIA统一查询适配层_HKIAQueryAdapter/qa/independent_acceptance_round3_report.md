# HKIA统一查询适配层v1 · 第三轮独立验收

验收日期：2026-09-01  
结论：**PARTIAL，未通过最终技术验收，其他模型标准化接入仍为NOT READY。**

## 1. 本轮进展

- 第一轮20/20继续通过。
- 执行方单测由15项增至19项，19项全部通过。
- entity与lineage解析结果已有区分。
- 指标目录原有9项的必填字段已补齐。
- 新增L11和pre-RBC/RBC内部单元测试，内部Comparability类可产生相应判断。
- 基础Q1—Q4、5库、公司桥、单位基础门禁及源DB只读状态未回退。

## 2. 第二层回归结果

更新后的第二层黑盒为5/19通过。机器证据：`qa/independent_acceptance_round2_result.json`。

通过项：

- filters传错误容器类型时返回ValidationError；
- entity/lineage模式产生不同解析；
- 指标目录现有条目必填字段完整；
- L11内部单测存在并通过；
- RBC内部单测存在并通过。

其余14项仍失败。

## 3. 仍未关闭的硬缺陷

### A. 统一Schema仍未真正执行

- 错误响应仍缺request_id、data、metadata、comparability、release、lineage。
- healthcheck的data仍为object，而Schema规定array。
- 执行方测试只检查普通成功响应的顶层键，没有用Schema验证成功/失败响应集合。

因此“交付了Schema文件”不等于“响应符合Schema”。

### B. 接受但忽略的参数仍存在

- 未知filters子字段被接受。
- periods中非法期间被忽略并返回合法期间的部分结果。
- offset=1与无offset结果完全一致。
- include_zero接受字符串类型且未执行。
- 非法fund_scope返回成功空数组。

模型会把`ok=true + 空/部分数据`解释成有效业务结果，这是比显式失败更危险的误用路径。

### C. 身份模式已区分，但状态与证据未闭环

- 零值公司仍标为reported_value。
- 缺记录公司仍返回成功空数组，没有`value=null + record_status=missing`。
- company_period_values返回business_lineage，但不返回bridge evidence/来源。

这意味着“entity/lineage模式字段不同”已完成，但“v2.1桥的状态和证据进入标准响应”仍未完成。

### D. L11/RBC门禁只存在于内部测试，公共契约不可达

新增测试直接调用`Comparability.check()`：

- L11指标只声明支持describe_metric，外部无法提交policy_count vs scheme_count比较并得到指定门禁。
- Client调用compare_periods时没有把period_a/period_b传入Comparability.check；2023 vs 2024请求不能得到SCHEMA_BRIDGE_REQUIRED。
- 对外错误码类中也没有稳定的SCHEMA_BRIDGE_REQUIRED错误响应。

内部函数能判断不等于其他模型通过统一接口会被正确阻断。任务验收要求的是请求级反向测试。

### E. Q4目录与安装态仍不完整

- Q4返回三项，但仍只登记FIN_DEBT_SECURITIES；股权和现金存款没有独立指标。
- 临时目录安装成功，安装后的`HKIAClient.open_readonly()`仍因找不到config/data_sources.json失败。
- custom_config测试从源码树复制配置并在源码环境执行，不能证明安装包包含配置、Schema及桥资产。

## 4. Gate结论

- 底层数据资产与桥：PASS。
- 固定Q1—Q4示例：PASS。
- 第一轮整改：PASS。
- 第二层19项：5 PASS / 14 FAIL。
- 统一适配层：PARTIAL。
- 其他模型标准化接入：NOT READY。
- 同口径增长发布：NOT PASS。

`qa/final_acceptance.json`中的overall PASS、technical_adapter PASS及READY结论与本轮实际黑盒结果冲突，应撤回。

## 5. 下一轮必须按公共接口验收

下一轮不要再增加只调用内部类的测试。所有业务门禁均从以下入口验证：

```python
HKIAClient.open_readonly().query(request)
```

CLI场景再通过`python -m hkia_adapter.cli`验证。最低收口要求：

1. 实际成功/失败样例全部通过JSON Schema。
2. filters/periods/offset/include_zero/fund_scope要么实现，要么明确拒绝。
3. zero/missing/evidence进入company响应。
4. L11和RBC请求通过公共接口返回稳定、明确的门禁码。
5. Q4三个返回指标全部登记。
6. 安装后的包从非源码目录完成healthcheck及一条Q1。
7. 第二层19项全部纳入正式测试并通过后，再更新final_acceptance。

本轮只更新独立黑盒判定逻辑并新增本报告，没有修改适配层业务代码、配置、源DB或公司桥。
