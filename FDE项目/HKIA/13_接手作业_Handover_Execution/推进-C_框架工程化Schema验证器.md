# 推进-C · 框架工程化：机器对象 Schema 验证器

> 承接 Phase A 未完成的完成条件："为全部机器对象建立正式 Schema 验证器"。
> 属于纯工程任务，**不涉及业务裁定**，可在本地独立推进。
> 设计依据：`00_分析框架_Analysis_Framework/` 下的元模型、Spec、Registry、Run Log 规范。

---

## 一、目标

让 Phase A 规划的各机器对象在被 Agent 或人填写后，能通过确定性校验，拒绝不规范输入。

## 二、需覆盖对象清单

| 对象 | 依规范 | 期望校验重点 |
|------|--------|---------------|
| Source / Source Registry | `05_Source_Strategy与Registry规范` | ID 唯一、来源类型白名单、URL/路径、发布日期、版本、哈希 |
| Asset / Asset Card | `06_Source_Card与采集协议` | checksum、时段、业务类型、权限、只读 |
| Fact / Evidence / Claim | `07_Fact_Evidence_Claim元模型` | Fact 可复算、Evidence 原文绑定、Claim 分 A/B/C |
| Theme / Theme Card | `03_HKIA_Theme_Universe` / `04_Theme_Card与路由规范` | Theme 唯一、主解释轴单一、平行轴白名单 |
| Spec / Analysis Contract | `09_Spec_Registry与继承规范` / `10_Analysis_Contract与阶段门规范` | 颗粒度不越界、二维白名单、绑定真实事实表 |
| Run Log / Incident | `11_Agent运行模型` | 状态转换合法、角色、Gate、incident 分类 |
| 证据等级 / 语言权限 | `08_证据等级_语言权限与命题升级协议` | 语言权限不越级、命题等级与证据匹配 |
| 年度/季度 schema | `12_/03_data_coverage/*` | 版本路由、禁止连接规则 |

## 三、实现方案（建议）

- 用 **JSON Schema** 或 **YAML-based contract** 作声明式核心，每个对象一个 schema 文件。
- 校验器优先级：
  1. ID 唯一且符合命名规则；
  2. 必填字段完整；状态转换在允许集合内；
  3. 引用有效性（引用的 source/asset/fact ID 必须存在或显式 pending）；
  4. 确定性规则可执行（如规则晋升门、跨年禁止连接、单位/期间合法性）。
- 输出：校验报告（逐对象 pass/fail + 失败原因），不自动纠错，只报问题。

## 四、推进步骤

1. [ ] 盘点 12 层对象实际落盘样本（从 run 记录、registry、reviews 抽取真例）。
2. [ ] 为优先级 P0 对象写 schema 定义（Source / Asset / Fact / Claim / Spec / Run / Incident）。
3. [ ] 实现一个 YAML 泛化校验入口（可对单文件也可对目录批量跑）。
4. [ ] 用接手前已产生的真实 YAML/数据做反向验证（能识别到真实文件，不误报合法项）。
5. [ ] 输出 `Schema验证器_校验报告` 到 `跟进日志/验证与回归基线`。

## 五、约束

- 不新增对既有文件内容的改写；校验只读。
- 若某对象在真实数据中发现 schema 定义与现实不符，不开"免责特例"吞掉，而是登记 `问题与阻碍登记.md` 交由框架层裁决。
- 验证器本身作为 `13` 目录产物独立版本化，不并入接手前工程。
