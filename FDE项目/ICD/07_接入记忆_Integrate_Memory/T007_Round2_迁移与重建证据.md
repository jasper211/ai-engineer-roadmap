# ICD-T007 · Round 2 主体隔离迁移与重建证据

> 执行方：vscode-deepseek · 生成日期：2026-09-03 · 状态：SUBMITTED 回执配套证据（Round 2）
> 背景：Jasper 重大决策确认——真实 RBC PDF 法律主体为「Prudential General Insurance Hong Kong Limited」（一般保险），
> 必须作为独立主体（insurer_code=PRUGI），不得继续归到寿险 PRU（Prudential Hong Kong Limited）。
> 本文件记录默认库 icd.db 的幂等迁移 + 按新主体重建的真实数据证据；Round 1 证据见 `T007_真实验证证据.md`。

## 一、迁移命令与退出码（真实默认库）

```bash
# 1) 幂等迁移（--init-db 自动检测 user_version<4 并迁移）
python3 04_定义Agent_Define_Agent/agents/agent.py --init-db
# EXIT=0

# 2) 按新主体重新解析（读取已迁移快照，不联网）
python3 04_定义Agent_Define_Agent/agents/agent.py --parse 13
# EXIT=0 · result=OK · insurer_code=PRUGI · run_id=6 · report_year=2024 · records_written=1
```

## 二、迁移报告（--init-db 输出，逐字）

```json
"migration": {
  "schema_version": 4,
  "actions": [
    "data_source[13] insurer_code PRU→PRUGI (https://www.prudential.com.hk/content/dam/prudential-phkl/pdf/en/regulatory-information/PGHK-RBC-public-disclosure-statement-2024.pdf)",
    "删除错误归属 rbc_statement 1 行（insurer_code=PRU）",
    "rbc_statement 新增列: legal_entity_name_raw, capital_base_raw, prescribed_capital_amount_raw, amount_unit_raw, amount_scale",
    "fetch_run[6] snapshot_path raw_data/PRU/13/b61630e9….pdf→raw_data/PRUGI/13/b61630e9….pdf (move=yes)"
  ],
  "backup_path": "…/07_接入记忆_Integrate_Memory/data/icd.db.pre-v4.bak"
}
```

## 三、迁移前备份（回滚依据）

- 备份文件：`07_接入记忆_Integrate_Memory/data/icd.db.pre-v4.bak`（SQLite backup API 全量复制）
- 备份文件 SHA-256：`9265688eb8850437fd54810c847886a8021e9ff70a61e3e8227138b24cd9c201`
- 用途：迁移失败或审计需复核错误归属原始状态时的唯一恢复点。

## 四、主体隔离（insurer 表）

| insurer_code | name_en | 主体性质 |
|---|---|---|
| PRU | Prudential Hong Kong Limited | 寿险（保留，不动） |
| PRUGI | Prudential General Insurance Hong Kong Limited | 一般保险（新增独立主体） |

- `source_registry.json`：RBC 源（entry_url 含 `PGHK-RBC-public-disclosure-statement-2024.pdf`）由 `PRU` 改为 `PRUGI`，schema_version 1.0→1.1。
- 险企总数 10→11；数据源仍 21 条。

## 五、data_source / fetch_run 归属修正

- `data_source[13]`：`insurer_code` `PRU`→`PRUGI`（同一 source_id、同一 entry_url、同一 url_version，未影响其他 20 条源）。
- `fetch_run[6]`：`snapshot_path` `raw_data/PRU/13/{hash}.pdf`→`raw_data/PRUGI/13/{hash}.pdf`；`content_hash`/`final_url`/`http_status=200`/`fetch_status='OK'` 不变。
- 快照物理移动：`raw_data/PRU/13/b61630e9….pdf` → `raw_data/PRUGI/13/b61630e9….pdf`；移动后文件 SHA-256 仍 `b61630e9b275146bb4ea16a1f60ae189aa2e19daae11ea8a13751d66f97d0d51`（字节未变，242184 字节）。

## 六、rbc_statement 重建（按新主体重新 --parse，真实字段逐字）

```
rbc_id                        = 1
insurer_code                  = PRUGI
run_id                        = 6
report_year                   = 2024
legal_entity_name_raw         = Prudential General Insurance Hong Kong Limited
solvency_ratio                = 2.9
solvency_ratio_raw            = 290%
capital_base                  = 581167000.0      （绝对 HKD，581,167 × 1000）
capital_base_raw              = 581,167
prescribed_capital_amount     = 200745000.0      （绝对 HKD，200,745 × 1000）
prescribed_capital_amount_raw = 200,745
currency                      = HKD
amount_unit_raw               = in HKD thousands
amount_scale                  = thousands
risk_breakdown_json           = （22 条 PCA 子风险 + 5 条资本基础组成原文，1825 字符）
```

### 逐字核对（PDF 文本 → DB 字段，含法律主体原文）

1. PDF 第 1 页 `Authorized insurer's name` 下一行 `Prudential General Insurance Hong Kong Limited`
   → DB `legal_entity_name_raw='Prudential General Insurance Hong Kong Limited'` ✅
2. PDF 第 3 页 `Capital base 581,167`（表头 `Unit: in HKD thousands`）
   → DB `capital_base=581167000.0` + `capital_base_raw='581,167'` + `amount_unit_raw='in HKD thousands'` + `amount_scale='thousands'` ✅
3. PDF 第 3 页 `Prescribed capital amount 200,745`
   → DB `prescribed_capital_amount=200745000.0` + `prescribed_capital_amount_raw='200,745'` ✅
4. PDF 第 4 页 `Ratio of capital base to prescribed capital amount 290%`
   → DB `solvency_ratio_raw='290%'` + `solvency_ratio=2.9` ✅

## 七、风险分解不强行映射（保留 JSON）

- `rbc_risk_component` 行数 = 0（未写不兼容枚举）。
- `risk_breakdown_json` 保留 22 条 PCA 子风险 + 5 条资本基础组成原文（含 `General Insurance Risk (diversified RCA)`、`Reserve and premium risk RCA`、`Natural catastrophe risk RCA` 等一般保险口径，非寿险 MARKET/…/LIFE 枚举）。

## 八、其他来源不受影响

- `fulfillment_ratio` = 4807 行（AIA 1573 + CTF 1969 + CLO 1265，未变）。
- `fetch_run` = 6 行（未变）；`parse_result` 由 4 行减为 3 行（仅删除错误归属 run_id=6 的 1 行，迁移后重建为 1 行 → 又回到 4 行：3 条 PARTIAL + 1 条 PRUGI OK）。
- `integrity_check=ok`、`foreign_key_check=[]`。

## 九、幂等与回滚

- 幂等：再次 `--init-db` 时 `user_version=4`，无迁移报告、无重复备份、无重复动作。
- 回滚：迁移在事务内执行；任一 SQL 失败整体回滚（见 test_t007_parse.py T007-17：归属 UPDATE 触发 FK 违例后，data_source 仍 PRU、rbc_statement 仍 1 行、无新列、快照未移动）。

## 十、确定性测试与全量回归

- `py_compile`（tools/memory/skills/agents/tests 全部 .py）：EXIT=0。
- `--validate-config`：EXIT=0（settings 与 source_registry 均合规）。
- 全量回归（不联网，tempfile）：`test_integration.py`（T002+T003）、`test_t004_parse.py`、`test_t005_parse.py`、`test_t006_parse.py`、`test_t007_parse.py` 全部 EXIT=0、✅ ALL CHECKS PASSED（T007 含 17 组，含新增 T007-16 迁移 / T007-17 回滚）。
