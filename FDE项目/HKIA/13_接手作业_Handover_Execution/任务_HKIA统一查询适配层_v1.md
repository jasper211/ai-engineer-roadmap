# 任务：封装 HKIA 统一查询适配层 v1

> 任务性质：数据产品工程化 / Agent输入接口标准化  
> 执行对象：接手Agent或其他编码模型  
> 优先级：P0  
> 前置状态：5库基础调用通过；公司桥v2.1技术终验通过；跨年度同口径增长尚未验收  
> 核心原则：让模型只能调用经过口径约束的语义接口，不能直接拼SQL、猜单位、猜认证状态或越过发布门禁。

---

## 一、任务目标

在现有5个SQLite数据库、公司桥v2.1及口径规则之上，建立一个本地、只读、可测试的 **HKIA统一查询适配层**。

适配层必须把以下分散能力收口成一个标准接口：

1. 数据源定位与只读连接；
2. 市场趋势、公司排名、行业财务和公司跨期取数；
3. 单位标准化及原单位保留；
4. certified/provisional标签；
5. 公司真实源名、entity_key及桥证据；
6. 指标、范围、期间和schema可比性判断；
7. 禁止发布或禁止计算场景的机器可读阻断；
8. 来源、SQL模板版本、数据版本及口径说明的可追溯返回。

最终使用者不应知道5个DB的具体表结构，也不应获得执行任意SQL的入口。

---

## 二、必须先读的输入

执行前完整阅读并以当前文件为准：

- `U20调用指引_v1.md`
- `数据资产整合视图_U20输入源_v1.md`
- `U20桥修复终验_v2.1.md`
- `U20桥修复独立验证_v2.1_result.json`
- `生成_跨年度同口径桥_CrossYearBridge/bridge/可比公司映射_2024L16_2025L1_v2.csv`
- `生成_跨年度同口径桥_CrossYearBridge/bridge/排除清单_2024_2025_v2.csv`
- `生成_跨年度同口径桥_CrossYearBridge/bridge/桥覆盖率与差异_v2.json`
- `verify_u20_call.py`
- `verify_u20_r3fix.py`

5个DB路径只能由统一配置模块解析，不得散落硬编码在业务函数中。

---

## 三、交付目录

在当前接手目录下新建：

```text
生成_HKIA统一查询适配层_HKIAQueryAdapter/
├── README.md
├── pyproject.toml
├── hkia_adapter/
│   ├── __init__.py
│   ├── config.py
│   ├── connections.py
│   ├── catalog.py
│   ├── models.py
│   ├── queries.py
│   ├── units.py
│   ├── labels.py
│   ├── identity.py
│   ├── comparability.py
│   ├── policy.py
│   └── cli.py
├── config/
│   ├── data_sources.json
│   ├── metric_catalog.json
│   └── release_policies.json
├── examples/
│   ├── query_examples.py
│   └── expected_responses.json
├── tests/
│   ├── test_connections.py
│   ├── test_core_queries.py
│   ├── test_units_labels.py
│   ├── test_identity.py
│   ├── test_comparability.py
│   ├── test_policy_gates.py
│   └── test_contract.py
└── qa/
    ├── acceptance_report.md
    └── acceptance_result.json
```

首版采用Python标准库优先。不得为了HTTP界面引入不必要依赖；本地Python API + JSON CLI是v1必需交付，HTTP API是后续可选项。

---

## 四、唯一允许暴露的调用面

### 4.1 Python入口

```python
from hkia_adapter import HKIAClient

client = HKIAClient.open_readonly()

result = client.query({
    "query_type": "market_trend",
    "metric_id": "NB_IND_TOTAL_ANNUALIZED_PREMIUM",
    "periods": ["2023Q1", "2024Q1", "2025Q1", "2026Q1"],
    "output_unit": "HKD_million"
})
```

### 4.2 CLI入口

```bash
python -m hkia_adapter.cli query --request request.json
```

CLI标准输出只能是JSON；日志写到标准错误。成功退出码0，参数/口径/策略阻断使用非零退出码。

### 4.3 允许的query_type

v1仅允许：

- `market_trend`
- `company_ranking`
- `financial_snapshot`
- `company_period_values`
- `compare_periods`
- `describe_metric`
- `list_metrics`
- `healthcheck`

不得提供 `execute_sql()`、`raw_query()`、透传表名、透传WHERE或任意SQL字段。

---

## 五、统一请求契约

请求字段必须使用白名单并进行严格校验：

```json
{
  "query_type": "company_ranking",
  "metric_id": "ANNUAL_L16_PREMIUM_SINGLE",
  "period": "2024",
  "entity_scope": "insurer",
  "limit": 10,
  "output_unit": "HKD_million",
  "include_zero": false,
  "release_intent": "internal_analysis"
}
```

要求：

- 未声明或不支持的字段直接拒绝，不静默忽略；
- `limit`必须有上下限；
- 期间必须符合指标支持的period_basis；
- count指标不接受金额单位；
- 空单位或未知单位不允许自动推断；
- 所有公司跨期请求必须显式选择 `identity_mode=entity` 或 `identity_mode=lineage`；默认不按裸公司名关联；
- 所有比较请求必须携带 `release_intent`。

---

## 六、统一响应契约

每次响应必须同时返回数据、口径和判定：

```json
{
  "ok": true,
  "request_id": "...",
  "query_type": "market_trend",
  "data": [],
  "metadata": {
    "metric_id": "...",
    "metric_label": "...",
    "period_basis": "quarterly_ytd",
    "entity_scope": "market_total",
    "source_unit": "HKD_thousand",
    "output_unit": "HKD_million",
    "certification": "provisional",
    "schema": "...",
    "source_layer": "standard_fact_layer",
    "source_db_id": "standard",
    "source_tables": ["market_facts"],
    "data_version": "...",
    "bridge_version": null
  },
  "comparability": {
    "status": "comparable",
    "reasons": [],
    "required_bridge": null
  },
  "release": {
    "status": "allowed",
    "level": "internal_analysis",
    "warnings": []
  },
  "lineage": {
    "query_template_id": "Q1_MARKET_TREND_V1",
    "source_files": [],
    "checksums": []
  }
}
```

禁止只返回数字列表。若来源表没有认证字段，必须说明标签依据；不得伪造数据库原生字段。

错误响应至少包含：`ok=false`、稳定的`error_code`、用户可读`message`、`blocked_by`、修正建议及适用口径。

---

## 七、强制防误用规则

以下规则必须在代码中执行，不能只写在README：

1. 所有SQLite连接使用 `mode=ro`，并启用 `PRAGMA query_only=ON`。
2. SQL只能来自代码内固定模板；所有值使用参数绑定；表名、列名、排序字段来自代码白名单。
3. 金额仅允许已声明转换：`HKD_thousand ↔ HKD_million`；count与金额不能互换或聚合。
4. `None`保留为缺失；不得转换为0。`missing`、`reported_zero`、`reported_value`必须保留。
5. 2022—2024 certified只适用于年度公司层；季度2023Q1/2024Q1等必须是provisional。
6. 2024 L16与2025 L1比较必须返回 `NOT_COMPARABLE_SCOPE`，不得计算或返回增长率。
7. `+65.4%`不得作为已验收同口径增长返回；若请求该结论，返回 `RELEASE_BLOCKED_UNVALIDATED_SCOPE`。
8. L11的policy_count/lives/scheme_count不得跨指标比较。
9. pre-RBC与RBC指标无已审定桥时返回 `SCHEMA_BRIDGE_REQUIRED`。
10. 公司跨年必须使用v2.1的source_name/entity_key/record_status；不得直接用字符串相等代替identity桥。
11. `identity_mode=entity`与`identity_mode=lineage`必须区分；Canada→MyPace等业务承接不得标成同一法人自然增长。
12. 排名默认排除missing；是否包含reported_zero由请求显式决定。
13. 不允许模型通过请求覆盖认证、单位、scope、schema、identity或release判定。
14. 不支持的比较必须硬阻断，不能用warning后继续给增长率。

---

## 八、指标目录设计

`metric_catalog.json`不得只复制18个metric_id名称。每个指标至少定义：

- metric_id / label；
- source_layer / source_table；
- source_metric或固定过滤条件；
- unit；
- entity_scope；
- period_basis；
- certification_rule；
- schema；
- supported_query_types；
- comparable_with；
- prohibited_comparisons；
- aggregation；
- source_definition；
- release_policy_id。

Q1—Q4用到的指标必须全部登记；目录缺项时查询失败，不允许临时猜测。

---

## 九、必须交付的测试

### 9.1 正常路径

- 5库连接及行数：59,516 / 72+4,914+18+18 / 7,097 / 414 / 408；
- Q1趋势返回4行且2026Q1换算为50,576.6259556103百万港元；
- Q2返回2024前10，首位Hang Seng Insurance，22,147.387百万港元；
- Q3返回2025前10，首位Hang Seng Insurance，28,731.149百万港元；
- Q4返回3项且保持HKD_million；
- 公司桥22行及排除46行可加载，68行entity_key与标准层一致；
- 2024/2025金额闭合与v2.1验收一致。

### 9.2 反向/防误用测试

必须证明以下请求失败且不返回增长率：

- 2024 L16 vs 2025 L1；
- count转HKD_million；
- 空单位参与金额聚合；
- 2023Q1标certified；
- policy_count vs scheme_count；
- pre-RBC vs RBC但未提供审定桥；
- 裸公司名跨年度拼接；
- 任意SQL、任意表名、任意排序字段注入；
- 客户端覆盖release_status；
- 请求发布+65.4%同口径增长。

### 9.3 契约测试

- 成功与失败响应都通过固定JSON Schema；
- 相同请求产生相同字段结构；
- 所有数值均带单位、期间、scope和认证标签；
- 排名/趋势结果每行保留entity或market scope；
- response内包含数据版本与桥版本；
- 不泄露本地绝对路径给下游模型，路径只留在内部日志。

---

## 十、验收Gate

只有全部满足才能标记完成：

- [ ] 现有 `verify_u20_call.py` 基础检查继续全部通过；
- [ ] `verify_u20_r3fix.py` 17/17继续通过；
- [ ] 适配层自身测试全部通过；
- [ ] 正常查询结果与现有DB直接查询一致；
- [ ] 所有防误用测试为硬失败，无增长率泄漏；
- [ ] 源DB哈希/行数在测试前后不变；
- [ ] 示例仅调用适配层，不直接import sqlite3或读取CSV；
- [ ] README包含“能力边界、禁止事项、接入示例、版本升级方式”；
- [ ] `acceptance_result.json`逐项给出布尔结果、证据和测试时间；
- [ ] `acceptance_report.md`明确区分“技术接入PASS”和“分析结论发布PASS”。

不得因为多数测试通过而将状态写为PASS。任一硬阻断测试失败，整体状态必须是FAILED或PARTIAL。

---

## 十一、非目标

本任务不包含：

- 自动下载IA新数据；
- 修改或重建现有5个源DB；
- 开放通用SQL；
- 证明2024 L16与2025 L1范围等价；
- 放行+65.4%增长结论；
- 使用公司增长幅度自动判断自然增长、转让或重分类；
- 对外部署公网HTTP服务。

---

## 十二、给执行Agent的完整任务指令

> 请在HKIA接手目录中实现“HKIA统一查询适配层v1”。先阅读本任务书列出的全部输入材料，保持5个SQLite源库只读，不修改现有事实层和公司桥。实现本地Python API和JSON CLI，只允许白名单语义查询，禁止任意SQL。把单位、认证、schema、scope、identity/lineage、record_status、comparability和release gate固化为代码规则，并对不可比请求硬阻断。完整实现任务书第九节测试，复跑现有基础与桥验证，生成机器可读验收JSON和人工验收报告。技术适配层PASS不得被描述为同口径增长结论PASS；2024 L16 vs 2025 L1及+65.4%发布请求必须被拒绝。不要只产出设计文档；必须交付可运行代码、示例、测试和验收证据。

---

## 十三、完成后的下一步

适配层通过验收后，再安排不同模型进行黑盒接入测试：只给README、请求Schema和示例，不向模型暴露数据库结构，观察其能否完成Q1—Q4及是否会被策略门禁正确阻断。该黑盒评测应作为另一项独立任务，不并入本次实现验收。
