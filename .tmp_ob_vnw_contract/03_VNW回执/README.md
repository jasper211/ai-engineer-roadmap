# VNW回执说明

`latest_receipt.json` 由只读校验器覆盖，`history/` 由后续编排器按 release_id 留存。首版回执中的 `affected_l3` 是根据已注册知识类型计算的候选影响；实际应用后的面板变化和是否重分析，仍以 VNW 快照字段差异及 `analysis_input_hash` 为准。

`READY_FOR_REVIEW` 不等于已应用；只有人工执行VNW应用流程后才能记录 `APPLIED`。
