# 05 · 集成工具 Integrate Tools

> 对应方法论：封装可复用工具，支持外部 API、计算、检索等能力。

## 本文件夹内容（`tools/` 包）

- `shell_exec.py` —— bash / python 脚本 / browser-use 占位执行器
- `git_ops.py` —— git add/commit/push 封装（唯一有真实 push 能力的地方，绝不 `git add .`）
- `task_knowledge.py` —— 任务知识库加载（原 `pta_common.py`）
- `pta_tasks_default.json` —— 本项目内置的任务知识库（兜底数据，不是代码）

`tools/` 只负责"每一种步骤具体怎么跑"，不负责"分解成哪些步骤"——那是
`06_开发技能_Develop_Skills/` 的职责。
