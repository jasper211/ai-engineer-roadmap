# 07 · 接入记忆 Integrate Memory

> 对应方法论：管理短期会话与长期记忆，支持向量存储与检索。

## 本文件夹内容（`memory/` 包）

- `workspace.py` —— 专属工作区隔离 + 跨会话状态持久化（原 `pta_workspace.py`）

PTA 目前的记忆形态是"按目标项目区分的专属工作区 + `state.json`"（结构化状态，
非向量库）——`get_project_workspace(project_root)` 保证 PTA 自己的状态/运行
产物永远物理隔离于目标项目本身和 PTA 源码所在的共享仓库，这是所有迁移里
唯一不允许简化的安全约束。

后续若某个 Agent 需要真正的向量检索/长期记忆，在这里新增
`vector_store.py`/`history.db` 一类模块，接口上仍归 `memory/` 包管。
