# 06 开发技能

本层实现 VNW 可复用的确定性技能和分析编排。

## 主要技能

- `l3_model_builder.py`：构建 L3 快照、Gate 和输入谱系；
- `blueprint_parser.py`：解析显式流程步骤、判断和回退；
- `l3_analysis_runner.py`：准备、运行、校验、修复和发布分析包；
- `l3_analysis_contract.py`：统一输出契约；
- `sync_data_foundation.py`：重建数据底座和前端 JSON；
- `sync_flow_blueprints.py`：同步流程蓝图输入；
- `change_detection.py`：源文件变化识别；
- `audit_l4_deliverables.mjs`：L4 交付物质量审计。

统一分析命令和边界见
[统一L3分析执行器_运行说明_v1.0.md](./统一L3分析执行器_运行说明_v1.0.md)。

本层脚本可以生成或校验派生结果，但不得替代业务负责人确认事实。
