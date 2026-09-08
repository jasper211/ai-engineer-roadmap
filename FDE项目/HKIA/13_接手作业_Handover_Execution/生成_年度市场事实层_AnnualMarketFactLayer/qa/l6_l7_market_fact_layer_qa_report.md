# L6–L7年度市场事实层QA报告

结论：**PASS**。共同指标可跨期使用；2024新增或停止披露的维度必须通过`schema_version`与`record_status`识别。

## Checklist

- [x] group_retirement_facts行数：452/452
- [x] group_retirement_facts无未解析值：异常=0
- [x] group_retirement_facts观察期有效：异常=0
- [x] annuity_other_facts行数：324/324
- [x] annuity_other_facts无未解析值：异常=0
- [x] annuity_other_facts观察期有效：异常=0
- [x] L6团体有效业务类别合计：可比=43，异常=0
- [x] L6退休计划类别合计：可比=37，异常=0
- [x] L6团体新造分部合计：可比=7，异常=0
- [x] L7年金新造缴费方式合计：可比=36，异常=0
- [x] L7个人/团体年金→年金小计：检查=27，异常=0
- [x] 2024 RBC新增指标被隔离保存：团体新造=63，计划数=12，旧口径误植=0

## 分析使用边界

- L6的2024团体有效业务只发布`group_life_total`，不可伪造A/C/I类别拆分。
- L6的团体新造业务与退休计划`scheme_count`仅属于2024 RBC口径，不可向前补零。
- L7在2024将部分相连、团体年金及其他险种标为N.A.；N.A.代表不可用，不等于零。
- `net_liabilities`与`current estimate`通过统一指标承接，但必须保留`schema_version`供报告披露口径。
