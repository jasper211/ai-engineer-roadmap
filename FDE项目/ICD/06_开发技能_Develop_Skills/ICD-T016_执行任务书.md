# ICD-T016 · 友邦与保诚寿险 RBC 主体补齐

> 执行与审计：Codex  
> 状态：ACCEPTED（Codex 自审）  
> 日期：2026-09-07

## 目标

优先补齐 `AIA International Limited`（AIA）和 `Prudential Hong Kong Limited`（PRU）寿险法律主体的 2024 RBC Disclosure Statement。现有 AIACO 和 PRUGI 数据属于不同持牌实体，不得替代。

## 验收标准

1. 从官方监管披露索引或官方静态资产确定最终 PDF，保留索引到文件的证据链。
2. PDF 中法律主体原文必须与目标 insurer_code 一致；不一致即停止入库并记录。
3. 提取报告年度、偿付能力比率、资本基础、规定资本额、币种、单位/标度与风险分解原文；所有标准值保留对应原文。
4. 快照、SHA-256、抓取记录、离线解析、幂等和结构漂移测试齐备。
5. 完成真实原文抽样、快照哈希、数值复算、数据库 integrity/FK 及全量回归后自审放行。

## 执行回执与自审

- AIA 寿险 PDF：run_id=21，HTTP 200，2,512,081 bytes，SHA-256 `2c8df3a0ffd2d0a18dc4d5c2898183cf8c78f30bf3291271ab3befd1a9c5ebb3`；主体 `AIA International Limited`，2024，212%，Capital Base/PCA 原文 `183,772,393`/`86,668,623`（in HKD thousands）。
- PRU 寿险 PDF：run_id=22，HTTP 200，228,727 bytes，SHA-256 `cabaf54ae47e1eae6fa47003647cf01e54d351efb338299983fbb79afb5a761a`；主体 `Prudential Hong Kong Limited`，2024，239%，Capital Base/PCA 原文 `113,845,439`/`47,664,502`（in HKD thousands）。
- 通用 RBC PDF 支持矩阵已扩展，并在写库前强制 `legal_entity_name_raw == insurer.name_en`；错误主体故障测试确认形成 `STRUCTURE_MISMATCH` 且业务表 0 写入。
- 全量离线编排 processed=14/succeeded=14/failed=0/unsupported=0，AIA/PRU RBC coverage 均为 FULL。
- T002-T016 共 13 套测试脚本全部通过；16 个成功快照重算 SHA-256 错配 0；`integrity_check=ok`、外键违例 0。
- 自审结论：满足验收标准，T016 放行。
