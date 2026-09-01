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
