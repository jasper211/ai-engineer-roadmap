# 目标APE数据源核实：public.fact_target

> 日期：2026-08-02
> 连接：`mga_platform`数据库（host 43.98.163.46:5432），沿用 VNW Agent 已有的只读连接配置
> 权限：仅执行 SELECT，未做任何写操作，遵守 Jasper"只读，不可改/删/增"的约束

## 一、表结构

`public.fact_target`，62 行，字段：`target_id, period_key, business_category, segment_code, ka_id, team_id, target_category, carrier_code, business_line, product_category, target_ape, target_revenue, target_headcount, target_active_rate, batch_id, created_at, created_by, updated_at, updated_by`

`target_category` 取值：全业务规划(10行) / 永明业务规划(10行) / 高客业务规划(10行) / 人寿业务规划(10行) / 中台年业务目标(10行) / 中台月业务目标(12行，按`period_key`=202601~202612月度)

## 二、business_category / segment_code 编码 → 原始底表值 对照表

| fact_target 编码 | 原始底表值 | 核实方式 | 置信度 |
|---|---|---|---|
| business_category=AGT | 代理人业务 | 与`fact_target`4类(AGT/BRK/KA/MGA)对齐原始底表`business_category`4类 | 高 |
| business_category=BRK | 经代业务 | 同上 | 高 |
| business_category=KA | KA业务 | 同上 | 高 |
| business_category=MGA | MGA业务 | 同上 | 高 |
| segment_code=SLC | 天领业务 | S2sheet目标APE=193,000,000，与T00001精确匹配；行数597，等于AGT类目下的天领业务行数 | 高（金额+行数双重核验） |
| segment_code=GTD | 成事家办 | S2sheet目标APE=70,000,000，与T00002精确匹配；行数296，等于AGT类目下的成事家办行数 | 高 |
| segment_code=BK | BK业务 | S2sheet目标APE=200,000,000与T00004精确匹配 | 高 |
| segment_code=REF | 合伙转介业务 | S9sheet目标APE=73,000,000与T00007精确匹配 | 高 |
| segment_code=IFA | IFA业务 | S9sheet目标APE=25,000,000与T00008精确匹配 | 高 |
| segment_code=ICLUB | ICLUB业务 | S9sheet目标APE=52,000,000与T00009精确匹配 | 高 |
| segment_code=TA | MGA业务 | 行数对齐（MGA类目下只有MGA业务209行，target_ape=600,000,000） | 中——只靠行数逻辑排除得出，未找到独立数字交叉验证 |
| segment_code=SLBRK | 永明经代 | S2-A节目标APE=340,000,000，S2-B节(永明子集)目标APE**同样是**340,000,000（跟SLBRK在全业务规划/永明业务规划两条target_category下的target_ape一致，因为永明经代100%是永明carrier）——与T00006/T00016精确匹配 | 高（金额双重核验，2026-09-17更新为高） |
| segment_code=BRK | 同行经代 | S2-A节目标APE=160,000,000(全业务)，S2-B节=140,000,000(永明子集)，分别与T00005/T00015精确匹配——两个不同数字的双重验证排除了巧合 | 高（金额双重核验，2026-09-17更新为高） |
| segment_code=NGP | **原始底表里没有对应数据**（0行） | AGT类目下 597(天领)+296(成事家办)=893=AGT总行数，NGP没有剩余行可分配 | 高——但意味着NGP是"有预算目标、无实际业务"的规划中线路，非当前bug |

## 三、已用真实数字核实的S1 KPI

| S1 KPI | 数值 | 反推公式 | 校验 |
|---|---|---|---|
| 2026全业务目标 | 1,113,000,000 | `target_category='全业务规划'`下**排除 segment_code IN ('NGP','TA')** 后 target_ape 求和 | ✅ 精确匹配（193+70+200+160+340+73+25+52=1113百万） |
| 2026永明业务目标 | 976,100,000 | `target_category='永明业务规划' AND carrier_code='SLHK'`下**同样排除 NGP/TA** 后求和 | ✅ 精确匹配 |

**排除 NGP/TA 的原因待Jasper确认**——目前的假设是：NGP 是尚无实际业务量的规划线路（结论合理但未证实），TA(MGA业务/天誉)可能是单独核算、不计入这两个"全业务"口径的汇总（S1的H节"永明业绩汇报数据"另有独立口径，可能TA走另一套统计）。

## 四、S2核实补充（2026-09-17）

S2_业务端视角的A/B节（业务细分年度汇总）直接列出了8个业务细分（不含MGA业务/TA）各自的目标APE，
用这8个数字逐一反查`fact_target`，SLBRK/BRK的映射方向已用两组不同金额（全业务160M/140M区分
BRK，永明经代在两个target_category下金额相同=340M区分SLBRK）交叉验证，置信度从"低"升到"高"。
**同时发现**：S2按segment_code分组时，"同行经代"= segment_code IN('同行经代','MGA业务')——即
MGA业务(TA)在**实际数据聚合**时会折进"同行经代"，但**查目标值**时"同行经代"只对应BRK一个编码
的target_ape（不含TA的600M）。这跟"排除NGP/TA"是两回事：NGP/TA被排除出的是S1"全业务/永明业务"
**两个汇总KPI**，跟S2"同行经代"分组本身是否含MGA的实际数据无关。

## 五、下一步

- [ ] Jasper 确认"全业务目标"/"永明业务目标"口径里排除 NGP、TA 两个 segment 的原因
- [ ] 高客业务规划/人寿业务规划/中台年业务目标/中台月业务目标 这4类`target_category`分别对应S1-S9哪些KPI，尚未逐一核对
