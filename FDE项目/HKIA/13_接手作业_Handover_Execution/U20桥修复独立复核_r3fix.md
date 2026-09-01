# U20桥修复独立复核 · r3fix

复核日期：2026-08-31。对象：`U20桥修复验证记录_r3fix_v1.md`及其引用的v2清单。

**结论：r3的A/B/C/D四项具体修复通过；v2桥仍有12行entity_key与标准层不一致，暂不通过按标准实体键直接联接的整体验收。** 同口径增长继续禁止放行，此项与本轮技术修复验收分开。

本次按电子表格技能的只读核验要求，逐行对账CSV与SQLite源记录，未修改5个源库、v2清单或接手文档。新增独立验证工具与结果记录；旧轮结果未覆盖。

## 1. 修复Checklist

- [x] 基础5库检查25/25通过，Q1—Q4返回4 / 10 / 10 / 3行。
- [x] A：安盛两组真实源名已修正，标准层证实分别对应 `ENTITY_AXA_CRI_HK`、`ENTITY_AXA_CRI`。
- [x] B：22行映射、46行排除清单的金额与record_status逐年度核验通过；2024缺失11行的名称/金额为空，不再伪装成报告零值。
- [x] C：子方案第三节旧放行语句已撤回，明确所有列示增幅不得作为同口径增长发布。
- [x] D：指引两种连接方式的4条SELECT实际返回57 / 68 / 57 / 68行，内容与两年度源公司集合一致；只读URI接入有效。
- [x] v2清单两年度非空源名全部覆盖源库公司集合，无重复、无遗漏；金额闭合及覆盖率通过。
- [ ] 全部v2实体键均可连接标准层：12行不一致，见下表。
- [ ] 产品范围等价与1492.0亿分项复算：本轮不验收，也未获得新增证明；同口径增长仍不得发布。

新增17项程序检查15项通过、2项失败（分别为映射清单/排除清单的实体键一致性）；退出码1反映这一明确缺陷，不是基础查询失败。

## 2. 已复算的金额与状态

| 年度 | 映射金额（千港元） | 排除金额（千港元） | 市场总额（千港元） | 金额覆盖率 |
|---|---:|---:|---:|---:|
| 2024 L16 | 89,858,894.053197 | 368,084.37 | 90,226,978.423197 | 99.592046% |
| 2025 L1 | 153,082,664.76323748 | 8,923,600.094 | 162,006,264.85723746 | 94.491818% |

差额分别约4.77e-9、-1.86e-8千港元，均在0.00001千港元容差内。修复记录中的覆盖率与闭合判断正确；覆盖率依然只是清单金额占市场总额，不是已证实的同口径业务覆盖率。

排除清单状态：2024为33行reported_zero、2行reported_value、11行missing；2025为43行reported_zero、3行reported_value。修复记录第四节的“2/33/11”应理解为**2024列**，不是双年度共同状态。

## 3. 剩余12处实体键差异（完整名单）

行号均包含CSV表头，标准键来自当前标准层 `company_facts` 的实际 `source_abbrev → entity_key`，未自行生成替代键。

| v2清单 | 行 | 公司 | 当前CSV entity_key | 标准层实际entity_key |
|---|---:|---|---|---|
| 映射 | 16 | Manulife (Int'l) | ENTITY_MANULIFE_INTL | ENTITY_MANULIFE_INT_L |
| 映射 | 18 | SJPI(HK)L | ENTITY_SJPIHKL | ENTITY_SJPI_HK_L |
| 排除 | 2 | AIA (HK) | ENTITY_AIA_(HK) | ENTITY_AIA_HK |
| 排除 | 11 | CPIC Life (HK) | ENTITY_CPIC_LIFE_(HK) | ENTITY_CPIC_LIFE_HK |
| 排除 | 13 | Friends Provident Int'l | ENTITY_FRIENDS_PROVIDENT_INTL | ENTITY_FRIENDS_PROVIDENT_INT_L |
| 排除 | 15 | FWD Life (HK) | ENTITY_FWD_LIFE_(HK) | ENTITY_FWD_LIFE_HK |
| 排除 | 17 | Generali Life (HK) | ENTITY_GENERALI_LIFE_(HK) | ENTITY_GENERALI_LIFE_HK |
| 排除 | 20 | Liberty Int'l | ENTITY_LIBERTY_INTL | ENTITY_LIBERTY_INT_L |
| 排除 | 26 | Prudential (America) | ENTITY_PRUDENTIAL_(AMERICA) | ENTITY_PRUDENTIAL_AMERICA |
| 排除 | 27 | RL360° | ENTITY_RL360° | ENTITY_RL360 |
| 排除 | 32 | Transamerica Life (Bermuda) | ENTITY_TRANSAMERICA_LIFE_(BERMUDA) | ENTITY_TRANSAMERICA_LIFE_BERMUDA |
| 排除 | 46 | Swiss Re (Asia) | ENTITY_SWISS_RE_(ASIA) | ENTITY_SWISS_RE_ASIA |

映射表两处还明确填写 `evidence=standard_layer_entity_key`，但键值与该证据源不符。其余10处若有意使用自建键，应明确独立命名空间并提供到标准层键的映射；现有提交没有这种声明。最小修正是按标准层实际键回填这12行，不要用另一套去标点规则重新生成键。**本轮没有替用户改动它们。**

## 4. 调用示例与验证边界

指引ROOT仍是 `/Users/.../HKIA/...`，使用者需要配置真实路径，这是配置项，不再认定为SQL语法缺陷。本轮提取原代码块中的4条SELECT，在真实只读连接上执行；没有执行文档里的任意Python，也没有声称原样占位路径能直接运行。

安盛两组身份映射已通过不等于业务沿革及范围等价全场景通过。本轮验证的是源名称、数值、状态、标准实体键引用和只读查询，不证明自然增长，也不复核修复记录关于Definition损坏/缺失的外部原因。

## 5. 收口建议

本轮技术缺陷集中为上表12个键，修正后可复跑 `verify_u20_r3fix.py`；无需重新构建已对账的基础事实库。输出 `U20桥修复独立验证_r3fix_result.json` 含逐行差异、原SQL及结果、金额/状态分布、基础查询结果和输入SHA256。

“基础调用/名值状态对账”已可使用；“直接按标准entity_key联接”待这12行修正；“同口径增长发布”是独立的后续分析验收，不因技术键修正而自动放行。
