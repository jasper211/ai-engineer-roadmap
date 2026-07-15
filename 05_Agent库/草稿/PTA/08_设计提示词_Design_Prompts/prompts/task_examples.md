# PTA 指令示例

给不熟悉 PTA 的人（或另一个 AI 终端）看的"这句话会被怎么理解"对照表。

| 用户说 | intent_parsing 识别出的 type | items | 备注 |
|---|---|---|---|
| "按顺序完成 P1-03, P1-04" | sequential | P1-03, P1-04 | 从任务知识库查这两个 ID 对应的执行步骤 |
| "回顾下进度" | review | （空） | 等价于 `--status`，只读，不产生新计划 |
| "帮我处理一下环境自检" | execute | GENERAL（模糊） | 没有可识别的任务 ID，会触发 needs_clarification |
| "如果 P1-01 完成了就做 P1-02" | conditional | P1-01, P1-02 | 条件类型目前只影响分类，不改变实际执行顺序 |
| "修正一下 P1-01 的执行记录" | correct | P1-01 | 归档复盘阶段可以人工二次编辑生成的执行记录 |

## 命令行调用示例

以下命令从 PTA 项目根目录执行（入口路径按 01-11 编号方法论结构，见 [README.md](../../README.md)）：

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --status
python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04"                       # dry-run，只出计划+报告
python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04" --execute              # 真实执行步骤，不 git push
python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04" --execute --sync -m "完成P1-03/04"  # 额外真实同步

# 对别的项目跑（状态落在该项目专属工作区，不影响 PTA 自己）
python3 04_定义Agent_Define_Agent/agents/agent.py "执行 T-01" --project-root /path/to/other/project
```
