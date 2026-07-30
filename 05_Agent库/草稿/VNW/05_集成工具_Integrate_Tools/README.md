# 05 集成工具

本层提供 VNW 的基础设施适配，不承载业务判断。

| 模块 | 作用 | 边界 |
|---|---|---|
| `postgres_reader.py` | 读取 `process_analytics` 权威事实 | 拒绝写操作 |
| `obsidian_reader.py` | 读取合格补充知识 | 待复核、失效材料不进入分析证据 |
| `evidence.py` | 建立证据类别和稳定证据 ID | 不改变原值 |
| `file_fingerprint.py` | 文件 SHA-256 和变化识别 | 不代表业务版本已确认 |
| `snapshot_writer.py` | 确定性写入快照和 manifest | 输入变化产生新 Hash |
| `llm_client.py` | 调用配置中的模型 | 只能读取运行包 |
| `legacy_runner.py` | 兼容早期最小闭环 | 不作为新模型主链 |

## 证据层级

1. `AUTHORITATIVE`：数据库权威事实；
2. `SUPPLEMENTAL`：正式复核或合格材料补充；
3. `DERIVED`：有明确规则的系统推导；
4. `MODEL_DRAFT`：大模型分析草稿；
5. `CONSENSUS`：工作坊或负责人共识。

低优先级证据不得静默覆盖高优先级事实。`UNVERIFIED`、
`PROVISIONAL_NOT_ELIGIBLE` 和待复核材料不能支持正式模型结论。
