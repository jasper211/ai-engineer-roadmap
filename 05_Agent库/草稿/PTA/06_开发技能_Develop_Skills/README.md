# 06 · 开发技能 Develop Skills

> 对应方法论：实现具体任务能力，组合工具完成复杂操作。

## 本文件夹内容（`skills/` 包，原 PTA-S01~S05）

- `intent_parsing.py` —— 意图解析（Think：自然语言 → 结构化任务包，原 S01）
- `execution_planning.py` —— 执行编排（Act：任务包 → 步骤 → 调用 `tools/` 实际执行，原 S02）
- `progress_tracking.py` —— 进度追踪（Observe：执行结果 → 进度报告 + 异常预警，原 S03）
- `doc_sync.py` —— 文档同步（看板更新 + 真实 git push，原 S04，已去掉死代码）
- `archive_review.py` —— 归档复盘（生成执行记录、提炼经验教训，原 S05，唯一的执行记录生成者）

这五个类只能被同进程内的代码 `import` 调用（如 `04_定义Agent_Define_Agent/agents/agent.py`），
不再有独立的命令行入口——调试单个技能，照着
`09_测试与调试_Test_and_Debug/tests/test_integration.py` 里对应 Test 的写法直接 import 调用。
