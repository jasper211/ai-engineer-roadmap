# 年度市场事实层

当前已完成L1–L7年度市场事实，覆盖2022–2024三个certified报告年度。

## 当前覆盖

- L1：有效业务与新造业务；保单数、保费、保额、净负债／Current Estimate；共675条事实。
- L1保留非相连、相连、产品、市场总额及额外储备控制行，并区分pre-RBC与RBC Schema。
- L2–L3：非相连分红/其他业务与相连险种明细，共780条事实。
- L4：新造业务非相连分红属性、相连缴费方式及险种明细，共540条事实；2024相连业务当年产品明细N.A.与已发布缴费方式总计分别保存。
- L6：团体与退休计划有效业务及2024新增团体新造业务，共452条事实。
- L7：年金及其他有效业务、个人年金新造业务，共324条事实。
- 表：L5a非相连、L5b相连。
- 指标：五年总体终止率；报告年度按第一年、第二年、第三年及以后拆分的终止率。
- 维度：报告年度、观察年度、相连属性、险种、保单年度、分红属性。
- 状态：`reported`、`reported_zero`、`not_applicable`、`blank`分开保存。
- 单位：`percentage_point`。

## 重建与验证

使用包含`openpyxl`的Python环境：

```bash
python3 scripts/build_l5_termination_fact_layer.py
python3 scripts/build_l1_market_facts.py
python3 scripts/build_l2_l3_market_facts.py
python3 scripts/build_l4_market_facts.py
python3 scripts/build_l6_l7_market_facts.py
python3 qa/verify_l5_termination_fact_layer.py
python3 qa/verify_l1_market_facts.py
python3 qa/verify_l2_l3_market_facts.py
python3 qa/verify_l4_market_facts.py
python3 qa/verify_l6_l7_market_facts.py
```

下一步修复年度公司事实层L14–L16缴费方式列的完整暴露，并将L1–L7及L13/L16/L19接入统一查询适配层。
