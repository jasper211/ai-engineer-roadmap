# L5自愿终止率事实层QA报告

日期：2026-09-08  
结论：PASS（9/9）

## 覆盖

- 报告年度：2022、2023、2024，全部标记为`certified`。
- 事实数：171条，每个报告年度57条。
- 总体终止率：每份年度表内五年历史序列。
- 报告年度分项：投保第一年、第二年、第三年及以后。
- 非相连业务保留分红／其他业务维度；相连业务标记该维度不适用。
- 单位：`percentage_point`。

## 确定性检查

1. 总行数171：PASS。
2. 三个certified报告年度：PASS。
3. 单位全部为percentage_point：PASS。
4. 认证标签全部为certified：PASS。
5. 2024非相连全部保单总体终止率3.7%：PASS。
6. 2024相连全部保单总体终止率7.0%：PASS。
7. 2024细分险种22个N.A.完整保留：PASS。
8. 无未解析值：PASS。
9. fact_id唯一：PASS。

## 关键边界

2024年Whole Life和Endowment的最新年度总体率及保单年度分项为N.A.，但All Policies仍披露3.7%和7.0%。因此不得把细分N.A.填为零，也不得用All Policies反推险种明细。

## 产物

- 数据库：`data/annual_market_fact_layer_2022_2024.db`
- 表：`termination_rate_facts`
- SHA256：`fd8b5c29cc88652e349f0a27b26bc6d270f759047d073a1453a21b33346b16d2`
