# ICD · 数据契约（SQLite Schema 设计）

> Agent ID: ICD
> 版本: v0.1.0
> 日期: 2026-09-03
> 阶段: SOP 第2步——流程设计（ICD-T001）
> 定位: 本文 DDL 可直接转为 SQLite schema；JSON/HTML/PDF 三类实现按同一契约开发与验收。
> 配套文件: `../02_配置项目_Configure_Project/source_registry.json`、`流程设计.md`

## 一、设计总纲

- **两条证据链主线**：`insurer`（险企）→ `data_source`（真实 URL）→ `fetch_run`（一次抓取）→ 业务记录。每条业务记录（`fulfillment_ratio` / `rbc_statement`）都带 `run_id` 外键，可反查到：真实 URL（`fetch_run.final_url` + `data_source.entry_url`）、HTTP 状态（`fetch_run.http_status`）、抓取时间（`fetch_run.fetched_at`）、内容哈希（`fetch_run.content_hash`）、原始快照相对路径（`fetch_run.snapshot_path`）。
- **快照先于入库**：原始快照成功落盘后，标准化结果才允许写库（对齐流程设计 L3-ICD-02）。
- **追加式历史**：`fetch_run` 与业务表只增不改；历史版本靠 `run_id` 维度保留，不覆盖旧值。
- **不提前建产品映射**：产品名变化时保留 `product_name_raw`，`product_id` 允许为空（`UNMAPPED`）。

## 二、需求项 → 数据表映射

| 需求项（任务书 B 项） | 数据表 |
|---|---|
| 险企规范实体及官网原始名称 | `insurer` + `insurer_official_name` |
| 数据源和 URL 版本 | `data_source`（`url_version`；历史 URL 见 `fetch_run.final_url`） |
| 抓取运行、HTTP 状态、抓取时间、内容哈希、原始快照相对路径 | `fetch_run` |
| 产品及官方原始产品名称 | `product` + `product_alias`（+ 业务表的 `product_name_raw`） |
| 分红实现率（报告年度/观察年度/红利类型/原始值/标准化数值/单位） | `fulfillment_ratio` |
| RBC（报告年度/偿付能力比率/资本基础/规定资本额/币种/可选风险分解） | `rbc_statement` + `rbc_risk_component` |
| 解析状态、覆盖状态、错误代码 | `parse_result` + `coverage_status` + `error_code` |
| 可追溯到一次抓取和一个原始证据 | 各业务表的 `run_id` 外键 + `fetch_run` 字段 |

## 三、核心约定

### 3.1 百分比统一存储方式

- 所有百分比/比率，统一存储为**小数比率**（原值 ÷ 100）：`94% → 0.94`，`100% → 1.0`，`304% → 3.04`。
- 原始字符串始终保留在 `*_raw` 列（`fulfillment_ratio.raw_value`、`rbc_statement.solvency_ratio_raw`），保证"不丢原文、不自行四舍五入"。
- 这一约定同时约束分红实现率（单位 `percent`）与 RBC 偿付能力比率（单位 `percent`）；RBC 的资本基础/规定资本额是**币种金额**，用 `currency` 列区分，不套用百分比约定。

### 3.2 空值语义（NULL ≠ 0 ≠ "无数据"）

| 列 | NULL 含义 |
|---|---|
| `data_source.entry_url` / `data_source.format` | 该源**未验证**（`UNVERIFIED`），本轮不得抓取 |
| `fetch_run.http_status` | 网络层失败（未收到 HTTP 响应） |
| `fetch_run.content_hash` | 抓取失败（未取得原始字节，无法计算真实哈希）；成功时非空（CHECK 约束保证） |
| `fetch_run.snapshot_path` | 快照未落盘（抓取失败）；成功时非空（CHECK 约束保证） |
| `fulfillment_ratio.normalized_value` | 原文存在但**无法解析为数字**（保留 `raw_value`，标记，不静默丢弃） |
| `fulfillment_ratio.product_id` / `rbc 相关 product` | 产品尚未映射到规范实体（`UNMAPPED`） |
| `rbc_statement.capital_base` / `prescribed_capital_amount` | 该份披露未公开此金额 |
| `rbc_statement.risk_breakdown_json` | 未捕获风险分解 |

### 3.3 重复抓取幂等策略

- **抓取层**：`fetch_run` 唯一约束 `(source_id, content_hash)`。SQLite 的 UNIQUE 对 NULL 视为互不相等，因此：
  - 成功抓取：同一源、同一内容哈希（非 NULL）→ 判定"无新版本"，不重复落盘快照、不重复解析（只记一次运行）。
  - 失败抓取：`content_hash = NULL`，各失败尝试之间**不去重**（每次失败单独成行，保留完整失败轨迹），也不与任何成功行冲突。
- **业务层**：`fulfillment_ratio` 唯一约束 `(insurer_code, product_name_raw, dividend_type, report_year, observation_year, run_id)`；`rbc_statement` 唯一约束 `(insurer_code, report_year, run_id)`。同一 `run_id` 重复处理 → UPSERT 到同一行，不产生重复记录。
- **跨运行**：新一次抓取产生新的 `run_id` → 新版本行，天然保留历史。

### 3.4 历史版本保留策略

- `fetch_run` 与业务表**只增不改**；旧版本行永不删除。
- "当前值"视图 = 对自然业务键取最大 `run_id`（或最大 `fetched_at`）的那一行。
- URL 变更：`data_source.url_version` 递增；每次抓取实际命中的最终 URL 记录在 `fetch_run.final_url`，故 URL 历史可完整重建，即使 `entry_url` 被原地更新。

### 3.5 产品名称变化但尚无 product_id 映射

- 业务记录始终保存 `product_name_raw`（官网原始产品名），`product_id` 允许为 `NULL`。
- `product_id IS NULL` 时，记录仍可经 `(insurer_code, product_name_raw, dividend_type, report_year, observation_year)` 查询。
- 后续建立映射（`product` + `product_alias`）后，回填 `product_id` 是**非破坏性 UPDATE**（`NULL → id`）；`product_name_raw` 永不删除，可追溯性不因映射而丧失。
- 名称漂移（同一产品跨年度改名）会自然产生多条 `product_name_raw`，由 `product_alias` 指向同一 `product_id` 收敛，不在抓取阶段强行合并。

## 四、SQLite DDL

```sql
PRAGMA foreign_keys = ON;

-- 1) 险企规范实体
CREATE TABLE insurer (
  insurer_code    TEXT PRIMARY KEY,                          -- 规范代码: 'AIA','AXA','YFL','SUN','CTF','FWD','BOC','CLO','PRU','MAN'
  name_en         TEXT NOT NULL,                             -- 英文规范名
  name_zh         TEXT,                                      -- 中文规范名（可空）
  legal_name_note TEXT,                                      -- 法律实体名备注 / 待与 IA 持牌险企名录核对
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 2) 官网原始名称（同一险企在官网可能以不同名称出现）
CREATE TABLE insurer_official_name (
  id            INTEGER PRIMARY KEY,
  insurer_code  TEXT NOT NULL REFERENCES insurer(insurer_code),
  official_name TEXT NOT NULL,                               -- 官网原文出现的名称
  language      TEXT NOT NULL CHECK (language IN ('en','zh','zh-hans','zh-hant')),
  source_hint   TEXT,                                        -- 首次观测到的来源（URL 片段或披露类型）
  first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (insurer_code, official_name, language)
);

-- 3) 数据源（每险企可多条；URL 未验证可为 NULL）
CREATE TABLE data_source (
  source_id        INTEGER PRIMARY KEY,
  insurer_code     TEXT NOT NULL REFERENCES insurer(insurer_code),
  disclosure_type  TEXT NOT NULL CHECK (disclosure_type IN ('fulfillment_ratio','total_cash_value_ratio','rbc')),
  entry_url        TEXT,                                     -- NULL = UNVERIFIED（未验证，不得抓取）
  format           TEXT,                                     -- 'json'/'html'/'pdf'; UNVERIFIED 可为 NULL
  access_status    TEXT NOT NULL CHECK (access_status IN ('OPEN','PARTIAL','BLOCKED','UNVERIFIED')),
  parser_hint      TEXT,                                     -- 解析提示/关键技术细节
  requires_browser INTEGER NOT NULL DEFAULT 0 CHECK (requires_browser IN (0,1)),
  evidence_basis   TEXT NOT NULL,                            -- 证据来源（需求定义§7.x + 实测日期）
  allows_empty     INTEGER NOT NULL DEFAULT 0 CHECK (allows_empty IN (0,1)),
  last_verified_at TEXT,                                     -- 最近一次实际验证时间（ISO8601）
  url_version      INTEGER NOT NULL DEFAULT 1,               -- URL 版本，URL 变更时递增
  is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  UNIQUE (insurer_code, disclosure_type, entry_url)
);

-- 4) 抓取运行（追加式，不可变）
CREATE TABLE fetch_run (
  run_id         INTEGER PRIMARY KEY,
  source_id      INTEGER NOT NULL REFERENCES data_source(source_id),
  fetched_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  final_url      TEXT,                                       -- 重定向后的最终 URL
  http_status    INTEGER,                                    -- 网络层失败为 NULL
  content_hash   TEXT,                                       -- SHA-256（原始字节）；仅成功抓取非空，失败为 NULL（见 CHECK）
  content_length INTEGER,                                    -- 字节数；失败为 NULL
  snapshot_path  TEXT,                                       -- 相对路径 raw/{insurer_code}/{source_id}/{hash}.bin；仅成功抓取非空，失败为 NULL
  fetch_status   TEXT NOT NULL CHECK (fetch_status IN ('OK','HTTP_ERROR','NETWORK_ERROR')),
  error_code     TEXT REFERENCES error_code(code),           -- 失败时非空
  note           TEXT,
  UNIQUE (source_id, content_hash),                          -- 幂等：同源同内容「成功」抓取去重；NULL 不参与去重（失败尝试各记一条）
  CHECK (
    (fetch_status = 'OK'            AND content_hash IS NOT NULL AND snapshot_path IS NOT NULL)
    OR
    (fetch_status = 'HTTP_ERROR'    AND content_hash IS NULL AND snapshot_path IS NULL AND http_status IS NOT NULL)
    OR
    (fetch_status = 'NETWORK_ERROR' AND content_hash IS NULL AND snapshot_path IS NULL AND http_status IS NULL)
  )
);

-- 5) 产品（规范实体，可惰性建立）
CREATE TABLE product (
  product_id        INTEGER PRIMARY KEY,
  insurer_code      TEXT NOT NULL REFERENCES insurer(insurer_code),
  canonical_name_en TEXT,
  canonical_name_zh TEXT,
  mapping_status    TEXT NOT NULL DEFAULT 'TENTATIVE' CHECK (mapping_status IN ('TENTATIVE','CONFIRMED')),
  first_seen_run_id INTEGER REFERENCES fetch_run(run_id),
  UNIQUE (insurer_code, canonical_name_en, canonical_name_zh)
);

-- 6) 产品原始名 → 产品映射（名称漂移收敛）
CREATE TABLE product_alias (
  id               INTEGER PRIMARY KEY,
  product_id       INTEGER NOT NULL REFERENCES product(product_id),
  raw_name         TEXT NOT NULL,                            -- 官网原始产品名
  language         TEXT CHECK (language IN ('en','zh','zh-hans','zh-hant')),
  first_seen_run_id INTEGER REFERENCES fetch_run(run_id),
  UNIQUE (raw_name)
);

-- 7) 分红实现率（业务记录）
CREATE TABLE fulfillment_ratio (
  ratio_id          INTEGER PRIMARY KEY,
  insurer_code      TEXT NOT NULL REFERENCES insurer(insurer_code),
  product_id        INTEGER REFERENCES product(product_id),  -- NULL = UNMAPPED
  product_name_raw  TEXT NOT NULL,                           -- 官网原始产品名
  dividend_type     TEXT NOT NULL CHECK (dividend_type IN ('AD','TD','TCV','REVERSIONARY','OTHER')),
  report_year       INTEGER NOT NULL,                        -- 披露报告年度
  observation_year  INTEGER NOT NULL,                        -- 比率对应的保单/观察年度
  raw_value         TEXT NOT NULL,                           -- 原始字符串（如 '94%'）
  normalized_value  REAL,                                    -- 小数比率 0.94；不可解析为 NULL
  unit              TEXT NOT NULL DEFAULT 'percent' CHECK (unit IN ('percent')),
  run_id            INTEGER NOT NULL REFERENCES fetch_run(run_id),
  UNIQUE (insurer_code, product_name_raw, dividend_type, report_year, observation_year, run_id)
);

-- 8) RBC 披露声明（业务记录）
CREATE TABLE rbc_statement (
  rbc_id                    INTEGER PRIMARY KEY,
  insurer_code              TEXT NOT NULL REFERENCES insurer(insurer_code),
  run_id                    INTEGER NOT NULL REFERENCES fetch_run(run_id),
  report_year               INTEGER NOT NULL,                -- 披露财年（如 2024）
  solvency_ratio            REAL,                            -- 偿付能力比率，小数（3.04 = 304%）
  solvency_ratio_raw        TEXT,                            -- 原始字符串（如 '304%'）
  capital_base              REAL,                            -- 资本基础（币种金额）
  prescribed_capital_amount REAL,                            -- 规定资本额（币种金额）
  currency                  TEXT NOT NULL DEFAULT 'HKD',
  risk_breakdown_json       TEXT,                            -- 可选：原始风险分解 JSON 字符串
  UNIQUE (insurer_code, report_year, run_id)
);

-- 9) RBC 风险分解（可选，规范化子表）
CREATE TABLE rbc_risk_component (
  id                        INTEGER PRIMARY KEY,
  rbc_id                    INTEGER NOT NULL REFERENCES rbc_statement(rbc_id),
  risk_type                 TEXT NOT NULL CHECK (risk_type IN (
                               'MARKET','INTEREST_RATE','CREDIT_SPREAD','EQUITY','PROPERTY',
                               'CURRENCY','LIFE','GENERAL_INSURANCE','OPERATIONAL','OTHER')),
  prescribed_capital_amount REAL,                            -- 该类风险的规定资本额
  currency                  TEXT NOT NULL DEFAULT 'HKD',
  UNIQUE (rbc_id, risk_type)
);

-- 10) 解析状态（每次抓取至多一条）
CREATE TABLE parse_result (
  id               INTEGER PRIMARY KEY,
  run_id           INTEGER NOT NULL REFERENCES fetch_run(run_id),
  parse_status     TEXT NOT NULL CHECK (parse_status IN ('OK','STRUCTURE_MISMATCH','ZERO_RECORD','PARTIAL','NOT_PARSED')),
  records_produced INTEGER NOT NULL DEFAULT 0,
  error_code       TEXT REFERENCES error_code(code),
  message          TEXT,
  UNIQUE (run_id)
);

-- 11) 覆盖状态（每险企 × 每披露类型一条）
CREATE TABLE coverage_status (
  id                  INTEGER PRIMARY KEY,
  insurer_code        TEXT NOT NULL REFERENCES insurer(insurer_code),
  disclosure_type     TEXT NOT NULL CHECK (disclosure_type IN ('fulfillment_ratio','total_cash_value_ratio','rbc')),
  coverage_status     TEXT NOT NULL CHECK (coverage_status IN ('FULL','PARTIAL','MISSING','BLOCKED','UNVERIFIED')),
  last_success_run_id INTEGER REFERENCES fetch_run(run_id),
  last_checked_at     TEXT,
  UNIQUE (insurer_code, disclosure_type)
);

-- 12) 错误代码注册表（初始化时播种）
CREATE TABLE error_code (
  code            TEXT PRIMARY KEY,
  category        TEXT NOT NULL CHECK (category IN ('NETWORK','HTTP','PARSE','DATA','IO')),
  is_hard_failure INTEGER NOT NULL DEFAULT 0 CHECK (is_hard_failure IN (0,1)),
  description     TEXT NOT NULL
);
```

## 五、错误代码种子（初始化时写入）

```sql
INSERT INTO error_code (code, category, is_hard_failure, description) VALUES
  ('HTTP_403',               'HTTP',   1, 'HTTP 403（多为机器人防护拦截）'),
  ('HTTP_404',               'HTTP',   1, 'HTTP 404（页面/文件不存在或路径过期）'),
  ('HTTP_5XX',               'HTTP',   1, 'HTTP 5xx（服务端错误）'),
  ('NETWORK_TIMEOUT',        'NETWORK',1, '网络超时'),
  ('NETWORK_CONNECTION',     'NETWORK',1, '连接失败/DNS 失败'),
  ('STRUCTURE_MISMATCH',     'PARSE',  1, 'HTTP 成功但页面/文件结构不符合预期（不得写"无数据"）'),
  ('ZERO_RECORD',            'PARSE',  1, '解析出 0 条记录（硬失败，除非 allows_empty=true）'),
  ('PDF_NO_TEXT',            'PARSE',  1, 'PDF 文字层损坏/扫描件，无法提取文字'),
  ('VALUE_UNPARSEABLE',      'DATA',   0, '值无法解析为数字（保留 raw_value，normalized=NULL）'),
  ('SNAPSHOT_WRITE_FAILED',  'IO',     1, '原始快照落盘失败'),
  ('DB_WRITE_FAILED',        'IO',     1, 'SQLite 写入失败');
```

## 六、关键索引（查询性能）

```sql
CREATE INDEX idx_fetch_run_source      ON fetch_run(source_id);
CREATE INDEX idx_ratio_natural         ON fulfillment_ratio(insurer_code, product_name_raw, dividend_type, report_year, observation_year);
CREATE INDEX idx_ratio_product         ON fulfillment_ratio(product_id);
CREATE INDEX idx_rbc_insurer_year      ON rbc_statement(insurer_code, report_year);
CREATE INDEX idx_alias_raw_name        ON product_alias(raw_name);
CREATE INDEX idx_official_name_insurer ON insurer_official_name(insurer_code);
```

## 七、示例查询（供 U020 薄封装 provider 参照）

```sql
-- 某险企某产品某年最新分红实现率（AD 口径，取最新抓取版本）
SELECT fr.product_name_raw, fr.dividend_type, fr.observation_year, fr.normalized_value, fr.raw_value,
       fr.run_id, fr2.final_url, fr2.fetched_at, fr2.content_hash, fr2.snapshot_path
FROM fulfillment_ratio fr
JOIN fetch_run fr2 ON fr2.run_id = fr.run_id
WHERE fr.insurer_code = 'AIA'
  AND fr.product_name_raw = :product
  AND fr.dividend_type = 'AD'
  AND fr.run_id = (
    SELECT MAX(x.run_id) FROM fulfillment_ratio x
    WHERE x.insurer_code = fr.insurer_code
      AND x.product_name_raw = fr.product_name_raw
      AND x.dividend_type = fr.dividend_type
      AND x.report_year = fr.report_year
      AND x.observation_year = fr.observation_year
  );

-- 某险企最新偿付能力比率
SELECT insurer_code, report_year, solvency_ratio, solvency_ratio_raw, currency, fr2.final_url, fr2.fetched_at
FROM rbc_statement r
JOIN fetch_run fr2 ON fr2.run_id = r.run_id
WHERE r.insurer_code = 'AIA'
  AND r.run_id = (SELECT MAX(x.run_id) FROM rbc_statement x WHERE x.insurer_code = r.insurer_code AND x.report_year = r.report_year);
```

## 八、预留扩展（本次不实现，仅记录）

- `batch_run` 表：如需按"一次全量刷新"分组审计，可新增批次表并把 `fetch_run.batch_id` 挂上去。当前用 `fetched_at` 即可满足年度刷新场景，暂不引入。
- `insurer_official_name` 的 `source_hint` 目前是自由文本；若后续要强约束，可改 FK 指向 `data_source.source_id`。