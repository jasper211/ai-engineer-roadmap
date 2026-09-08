# 年度市场事实层

当前已完成L1个人寿险市场总览与L5个人寿险保单自愿终止率，覆盖2022–2024三个certified报告年度。

## 当前覆盖

- L1：有效业务与新造业务；保单数、保费、保额、净负债／Current Estimate；共675条事实。
- L1保留非相连、相连、产品、市场总额及额外储备控制行，并区分pre-RBC与RBC Schema。
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
python3 qa/verify_l5_termination_fact_layer.py
python3 qa/verify_l1_market_facts.py
```

下一切片将加入L2–L4市场金额与数量事实，并与L8–L19年度公司事实层建立控制关系。
