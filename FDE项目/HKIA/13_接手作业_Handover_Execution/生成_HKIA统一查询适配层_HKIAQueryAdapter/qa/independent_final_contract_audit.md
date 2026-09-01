# HKIA 统一查询适配层——独立终审（真实契约穿透）

审计日期：2026-09-01  
审计结论：**PARTIAL / 暂不建议宣布“完全验收通过”**

## 1. 已通过

- `qa/independent_acceptance.py`：20/20 PASS。
- `qa/independent_acceptance_round2.py`：19/19 PASS。
- `tests/test_all.py`：19/19 PASS。
- `qa/verify_adapter.py`：17/17 PASS。
- 源数据库哈希、基线门禁、公司桥门禁均通过。
- 通过 `pip install --target <临时目录>` 安装后，以 `/tmp` 为工作目录、脱离源码目录调用核心 Q1，成功返回 4 个期间（2023Q1、2024Q1、2025Q1、2026Q1）及真实数据。说明 wheel 已携带必要配置、桥和 Schema 资源，且可定位外部 5 库。

## 2. 未通过：失败响应违反公开 JSON Schema

使用 `schema/response_schema.json` 对实际响应逐字段、逐类型校验：

| 用例 | 业务结果 | Schema 结果 |
|---|---:|---:|
| Q1 成功响应 | PASS | PASS |
| healthcheck 成功响应 | PASS | PASS |
| 非法 query_type | 正确阻断 | **FAIL** |
| L11 policy_count / scheme_count 门禁 | 正确阻断 | **FAIL** |
| pre-RBC / RBC 门禁 | 正确阻断 | **FAIL** |

共同失败原因：

- `client.py::_error_response()` 返回 `metadata.certification = null`、`metadata.schema = null`；
- 但 `schema/response_schema.json` 规定上述两个字段必须为 `string`；
- 因而“所有 query 响应（成功与失败）必须符合 Schema”的公开契约尚未成立。

## 3. 为什么现有验收没有发现

`qa/independent_acceptance_round2.py` 的 `error_response_meets_required_contract` 只检查顶层 required key 是否存在，没有验证嵌套 required 字段的类型。其 `installed_package_can_open` 也只探测 healthcheck；本轮已补做真实 Q1 安装态穿透并确认通过。

## 4. 必须整改与复验标准

二选一，但必须保持根目录 Schema 与包内 `_assets/schema/response_schema.json` 一致：

1. 推荐：失败响应提供明确字符串标签，例如 `certification="not_applicable"`、`schema="not_applicable"`；或
2. 若接口设计确认失败响应允许无标签，则将这两个字段的 Schema 类型改为 `["string", "null"]`。

复验必须使用真正的 JSON Schema 校验（或等价递归类型校验），至少覆盖：成功查询、healthcheck、请求校验失败、L11 门禁、RBC 门禁、发布门禁；六类响应全部符合契约后，技术适配层方可判定 **PASS / 可供其他模型标准接入**。

## 5. 分层结论

- 数据库、查询、单位、标签、身份桥、可比性和安装态核心查询：**PASS**。
- 统一响应契约：**NOT PASS（1 个集中缺口）**。
- 技术适配层整体：**PARTIAL**。
- `+65.4%` 及 2024 L16 vs 2025 L1 同口径增长结论：仍为 **NOT PASS / 禁止发布**；该分析结论边界与本次技术契约缺口相互独立。
