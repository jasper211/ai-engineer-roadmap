# HKIA 统一查询适配层 v1 · 验收报告

> 任务：`任务_HKIA统一查询适配层_v1.md`
> 日期：2026-09-01
> 结论：**技术适配层 PASS；分析结论发布 NOT-PASS（范围等价未验收）**

---

## 一、验收结论摘要

| 维度 | 状态 |
|---|---|
| **技术接入** | ✅ **PASS** |
| 正常查询（Q1-Q4）| ✅ PASS |
| 防误用硬阻断 | ✅ PASS（全部硬失败，无增长率泄漏）|
| 契约与标签 | ✅ PASS |
| **分析结论发布** | ❌ **NOT-PASS**（+65.4% 禁止放行；2024 L16 vs 2025 L1 禁止发布增长率）|

**重要**：技术适配层 PASS 不等于同口径增长结论 PASS。适配层正确地**阻止**了未验收的同口径增长发布。

## 二、验收项明细（对应任务书第九、十节）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 5 库连接与行数（59,516 / 72+4914+18+18 / 7,097 / 414 / 408）| ✅ | healthcheck 返回一致 |
| Q1 趋势 4 行，2026Q1=50,576.626百万港元 | ✅ | verify_adapter |
| Q2 2024 Top10，首位 Hang Seng 22,147.387百万港元 | ✅ | verify_adapter |
| Q3 2025 Top10，首位 Hang Seng 28,731.149百万港元 | ✅ | verify_adapter |
| Q4 财务快照 3 项，单位 HKD_million | ✅ | verify_adapter |
| 公司桥 22行+46行可加载，entity_key 与标准层一致 | ✅ | identity.py 加载 v2.1 |
| 未知 query_type 拒绝 | ✅ | execute_sql → 拒绝 |
| count 转金额拒绝 | ✅ | NB_GROUP_POLICIES + HKD_million → 拒绝 |
| 2024 L16 vs 2025 L1 阻断 | ✅ | NOT_COMPARABLE_SCOPE |
| 裸公司名跨年阻断 | ✅ | 需 identity_mode |
| 发布 +65.4% 阻断 | ✅ | RELEASE_BLOCKED_UNVALIDATED_SCOPE |
| 任意 SQL/表名/排序/字段注入阻断 | ✅ | 白名单 + 固定模板 |
| 空/未知单位拒绝 | ✅ | euro → 拒绝 |
| 契约 8 键齐全 | ✅ | ok/request_id/.../lineage |
| 季度不标 certified | ✅ | 2023Q1 → provisional |
| 源 DB 未修改 | ✅ | 全程 mode=ro + query_only |

## 三、技术实现摘要

- `hkia_adapter/` 含 config/connections/models/units/labels/catalog/identity/comparability/policy/queries/client/cli。
- 全部 SQLite `mode=ro` + `PRAGMA query_only`；SQL 只来自代码固定模板 + 白名单列 + 参数绑定。
- 单位只允许 HKD_thousand↔HKD_million；count 不得转金额。
- 认证区分年度 certified 与季度 provisional。
- 公司跨年必须 identity_mode=entity/lineage，用 v2.1 桥 entity_key。
- 发布门禁硬阻断未验收同口径增长。

## 四、运行方式

```bash
python3 tests/test_all.py          # 15 项单元测试
python3 qa/verify_adapter.py       # 17 项验收检查 → acceptance_result.json
python3 examples/query_examples.py # 语义查询示例
```

## 五、已知边界（非缺陷）

- 适配层不验证"2024 L16 与 2025 L1 范围等价"（缺 IA 定义）；此判定留待独立分析验收。
- 财务层 certification 为 provisional；无 certified 财务年度。
- HTTP API 未实现（v1 交付为 Python API + JSON CLI，HTTP 为后续可选项）。

## 六、结论

适配层**技术接入 PASS**，可交付 U20 作为受口径约束的查询输入层。
**跨年度同口径增长结论仍 NOT-PASS**，+65.4% 不得通过本适配层发布为已验收结论。

---
## 七·补充：独立审计整改后最终状态（2026-09-01）

原独立审计（`independent_acceptance_report.md`）判定 PARTIAL（20项仅3过），指出 P0 缺陷。已按审计整改：

**整改内容**：
1. units.py 重写为单位硬失败（count+euro→拒、金额+count→拒）。
2. 新增 request_validation.py：limit/offset/periods 类型值域、scope 覆盖防护、query_type×metric 兼容、年度支持校验。
3. company_period_values 支持 annual + provisional2025，返回 entity_key / record_status；identity 进结果。
4. list_metrics / describe_metric 返回真实 data；数值行补 entity_scope/certification/schema。
5. lineage 真实填充（source_files/checksums/query_template_id 分模板）。
6. metadata 用 source_db_id；新增 schema/response_schema.json。
7. cli.py 坏 JSON 返回 JSON 错误 + 非零退出码。

**整改后独立审计：20/20 PASS（overall=PASS）**
- scope 覆盖拒绝 ✓、单位门禁 ✓、list/describe ✓、identity进结果 ✓、provisional company_value ✓、行标签 ✓、lineage ✓、source_db_id ✓、JSON Schema ✓、CLI错误 ✓、基础gate ✓、桥gate ✓、源DB哈希不变 ✓。

**最终验收判定**：
- 技术适配层：**PASS**（独立审计20/20 + 单元15/15 + 适配层17/17）。
- 分析结论发布：**NOT PASS**（+65.4% 禁止放行；2024 L16 vs 2025 L1 禁止发布增长率）。
- 供其他模型标准化接入：**READY**（README + 请求Schema + 只读语义接口）。

---
## 八·深度优化（审计报告第3/5节补充项）

依独立审计 `U20桥修复独立复核_r3fix` 及 `independent_acceptance_report.md` 点名的"未覆盖深层项"，已补充：

| 项 | 实现 | 测试 |
|---|---|---|
| **L11 gate** | comparability 拦截 policy_count/lives/scheme_count 跨指标比较 | test_l11_count_mix_blocked |
| **pre-RBC ↔ RBC** | 跨 RBC 断点比较无审定桥 → SCHEMA_BRIDGE_REQUIRED | test_pre_rbc_rbc_bridge_required |
| **identity_mode=lineage** | 与 entity 区分；从标准层加载 business_lineage（Canada→MyPace/Chubb），返回 identity_note | test_lineage_mode_distinct_from_entity |
| **指标目录完整性** | 从 9→10 项，全部补 comparable_with/source_definition/release_policy_id | catalog 检查 |
| **自定义配置目录** | open_readonly(cfg_dir=...) 支持外部配置 | test_custom_config_dir_loads |

**最终测试**：单元 19/19 + 独立审计 20/20 + 适配层验收 17/17 + 基础/桥 gate + 源DB哈希不变，全部 PASS。

---
## 九·第三轮审计整改（round2 19项，从公共接口验收）

独立审计第三轮（`independent_acceptance_round2_report.md`）判定 PARTIAL（5/19），要求不得只测内部类、从 `HKIAClient.query` 公共接口验收。已全部修复：

| 审计项 | 修复 |
|---|---|
| 错误响应契约 | 错误响应补全 request_id/data/metadata/comparability/release/lineage 全部契约键 |
| healthcheck data | 改为 list（符合 Schema array）|
| 未知嵌套 filters | 拒绝未知 filters 子字段 |
| periods 逐项校验 | 非法期间按 period_basis 拒绝 |
| offset | SQL 支持 OFFSET（生效）|
| include_zero 类型 | 必须 bool |
| filters 类型 | 必须 dict |
| zero 值状态 | record_status=reported_zero |
| missing 状态 | value=null + record_status=missing |
| bridge evidence | company 行返回 bridge_evidence + bridge_type |
| 非法 fund_scope | 白名单拒绝 |
| Q4 三指标 | 补 FIN_EQUITIES_PORTFOLIO / FIN_CASH_AND_DEPOSITS 登记 |
| L11 公共门禁 | compare_periods 对 policy_count vs scheme_count 返回 L11COUNT_BLOCKED |
| RBC 公共门禁 | compare_periods 2023 vs 2024 返回 SCHEMA_BRIDGE_REQUIRED |
| 安装包 | config/schema/bridge 打包进 _assets；安装后从非源码目录 healthcheck+Q1 通过 |

**最终：单元 19/19 + 轮1独立审计 20/20 + 轮3独立审计 19/19 + 适配层验收 17/17 + 基础/桥gate + 安装探测，全部 PASS。**

---
## 十·第四轮独立终审整改（真实 Schema 契约穿透）

独立终审（`independent_final_contract_audit.md`）判定 PARTIAL，指出唯一集中缺口：
- **失败响应违反公开 JSON Schema**：`metadata.certification` 与 `metadata.schema` 为 `null`，而 Schema 规定必须 `string`。

**整改**（采用审计推荐方案1）：
- `_error_response()` 将失败响应的 `certification`、`schema` 设为**字符串 `"not_applicable"`**，满足 Schema string 约束。
- 保持根目录 `schema/response_schema.json` 与包内 `_assets/schema/response_schema.json` 一致。
- 新增 `qa/schema_validator.py`（等价递归类型校验）与 `qa/final_contract_recheck.py`，**用真实 Schema 递归校验六类响应**（成功/healthcheck/请求校验失败/单位门禁/L11/RBC/发布门禁）。

**复验**：六类响应全部通过 Schema 递归校验；根目录与包内 schema 一致。

最终：单元 19/19 + 轮1 20/20 + 轮3 19/19 + 适配层 17/17 + 六类响应 Schema 复验 PASS + 安装态探测 PASS。
**技术适配层可判定 PASS，可供其他模型标准接入。+65.4% 与 2024 L16 vs 2025 L1 仍禁止发布。**
