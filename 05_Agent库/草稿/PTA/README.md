# PTA Agent · 项目任务协同 Agent

> Agent ID: PTA
> 版本: v1.1.0
> 状态: 已上线（5/5 子 Agent + 主编排器 + 4 个扩展工具）
> 日期: 2026-07-03（v1.1.0 编排器更新: 2026-07-13）

---

## 📋 文档定位说明

| 字段 | 内容 |
|------|------|
| **文档定位** | PTA Agent 的使用手册和快速入门指南 |
| **核心作用** | ① 帮助用户快速理解 PTA 的功能 ② 提供常用命令示例 ③ 作为故障排查参考 |
| **使用场景** | ① 新任务开始时查阅 ② 子 Agent 调用时参考 ③ 集成测试时对照 |
| **维护责任** | Jasper 主责，每次子 Agent 更新后同步更新 |
| **迭代规则** | ① 新增子 Agent 时追加 ② 命令变更时更新 ③ 用户反馈驱动改进 |
| **关联文件** | [config.json](config.json) · [需求定义](需求定义.md) · [流程设计](流程设计.md) · [Agent 搭建 SOP](../Agent搭建SOP_v1.0.md) |

---

## 一、PTA 是什么？

**PTA** = **P**roject **T**ask **A**ssistant（项目任务协同 Agent）

PTA 是你的「AI 项目经理」，它能：
- **理解**你的自然语言指令（S01）
- **分解**任务为可执行步骤（S02）
- **监控**执行进度并预警（S03）
- **同步**文档到 Git + 看板（S04）
- **复盘**任务，沉淀经验教训（S05）

---

## 二、快速开始

### 2.0 统一入口：PTA-RUN 主编排器（推荐）

v1.0.0 的 5 个子 Agent 需要人工依次调用、手动接力传文件，本质是"脚本"而非
[Agent 搭建 SOP](../Agent搭建SOP_v1.0.md) §1.2 定义的"Agent"（缺自动串联 + 状态记忆）。
v1.1.0 起用 `PTA-RUN_主编排器.py` 统一串联 S01→S02→S03→S05，并把 `.pta_state.json`
落到磁盘，实现跨会话的进度记忆。

```bash
# 查看当前/历史任务状态（"回顾下进度，继续推进"）
python3 PTA-RUN_主编排器.py --status

# 一句话指令 → 自动解析 + 出执行计划 + 出进度报告（默认 dry-run，不产生真实副作用）
python3 PTA-RUN_主编排器.py "按顺序完成 P1-03, P1-04"

# 真实执行任务步骤（仍不含 git push）
python3 PTA-RUN_主编排器.py "按顺序完成 P1-03, P1-04" --execute

# 真实执行 + 追加真实文档同步（git add/commit/push，唯一含真实推送的阶段）
python3 PTA-RUN_主编排器.py "按顺序完成 P1-03, P1-04" --execute --sync -m "commit message"
```

**⚠️ 安全设计**：S02 原本会给任何 execute/sequential 任务自动追加一个真实 `git push`
步骤且无法关闭。PTA-RUN 通过 `--no-sync` 把这一步从自动执行计划里摘出来，改成独立、
显式确认的阶段——`--sync` 必须同时搭配 `--execute` 和 `--message` 才会真正触发，
避免无人值守场景下未经确认就推送到共享仓库。

### 2.1 手动逐步调用（调试 / 单步排查时使用）

```bash
# Step 1: 解析意图（S01）
python3 PTA-S01_意图解析器.py "按顺序完成 P0-02, P0-03, P1-03, P1-04" --output task.json

# Step 2: 调度执行（S02）
python3 PTA-S02_执行调度器.py --input task.json --dry-run

# Step 3: 监控进度（S03）
python3 PTA-S03_进度追踪器.py --plan execution_plan.json

# Step 4: 同步文档（S04）
python3 PTA-S04_文档同步器.py --task-id P2-01 --task-name "PTA搭建" -m "feat: PTA v1.0"

# Step 5: 归档复盘（S05）
python3 PTA-S05_归档复盘器.py --plan execution_plan.json --task-id P2-01 --task-name "PTA搭建"
```

### 2.2 一键集成测试

```bash
bash test_pta_integration.sh
```

---

## 三、子 Agent 详解

### 3.1 PTA-S01 意图解析器

**功能**：将自然语言指令转换为结构化任务包

**输入**：自然语言（如"按顺序完成 P0-02, P0-03"）
**输出**：JSON 任务包（任务类型、优先级、任务项、约束条件）

**常用命令**：

```bash
# 基本解析
python3 PTA-S01_意图解析器.py "按顺序完成 P0-02, P0-03, P1-03, P1-04"

# 保存到文件
python3 PTA-S01_意图解析器.py "按顺序完成 P0-02, P0-03" --output task.json

# 模糊指令（会提示需要澄清）
python3 PTA-S01_意图解析器.py "帮我看看进度"
```

**输出示例**：

```json
{
  "task_id": "T-20260709-001",
  "type": "sequential",
  "priority": "P1",
  "items": [
    {"id": "P0-02", "name": "前端 Vercel 部署", "status": "pending"},
    {"id": "P0-03", "name": "MCP Server 公开", "status": "pending"}
  ],
  "constraints": ["order"],
  "confidence": 0.8,
  "needs_clarification": false
}
```

---

### 3.2 PTA-S02 执行调度器

**功能**：将任务包分解为可执行步骤，调度工具执行

**输入**：S01 生成的任务包 JSON
**输出**：执行计划 JSON（步骤列表 + 执行结果）

**常用命令**：

```bash
# Dry-run 模式（安全测试）
python3 PTA-S02_执行调度器.py --input task.json --dry-run

# 实际执行
python3 PTA-S02_执行调度器.py --input task.json --output plan.json

# 指定项目根目录
python3 PTA-S02_执行调度器.py --input task.json --project-root /path/to/project
```

**支持的工具**：
- `bash`：执行 shell 命令
- `python`：运行 Python 脚本
- `browser-use`：浏览器自动化（需 MCP）

---

### 3.3 PTA-S03 进度追踪器

**功能**：监控执行状态，生成进度报告，检测异常

**输入**：S02 生成的执行计划 JSON
**输出**：进度报告（完成率、状态、异常预警）

**常用命令**：

```bash
# 单次报告
python3 PTA-S03_进度追踪器.py --plan execution_plan.json

# 持续监控（每 10 秒刷新）
python3 PTA-S03_进度追踪器.py --plan execution_plan.json --watch --interval 10

# 保存报告
python3 PTA-S03_进度追踪器.py --plan execution_plan.json --output report.json
```

**监控指标**：
- 完成率（%）
- 步骤状态（✅ 完成 / ❌ 失败 / 🔄 运行中 / ⏳ 待开始）
- 异常预警（超时、失败原因）
- 预计完成时间

---

### 3.4 PTA-S04 文档同步器

**功能**：任务完成后自动同步文档（Git + 看板 + 执行记录）

**输入**：任务完成信号
**输出**：Git 提交 + 看板更新 + 执行记录

**常用命令**：

```bash
# Dry-run 模式（推荐先测试）
python3 PTA-S04_文档同步器.py --task-id P2-01 --task-name "PTA搭建" -m "feat: PTA v1.0" --dry-run

# 实际执行
python3 PTA-S04_文档同步器.py --task-id P2-01 --task-name "PTA搭建" -m "feat: PTA v1.0"

# 更新看板状态
python3 PTA-S04_文档同步器.py --task-id P2-01 --task-name "PTA搭建" -m "update: progress" --status "进行中"

# 指定文件提交
python3 PTA-S04_文档同步器.py --task-id P2-01 --task-name "PTA搭建" -m "feat: add S01" --files file1.py file2.py
```

**同步清单**：
- [ ] Git add + commit + push
- [ ] 更新 `能力整改看板.md`
- [ ] 创建 `任务执行记录.md`

---

### 3.5 PTA-S05 归档复盘器

**功能**：生成执行记录，沉淀经验教训，更新 F3 教训库

**输入**：执行计划 JSON
**输出**：执行记录 Markdown + 教训库更新

**常用命令**：

```bash
# 基本复盘（不更新教训库）
python3 PTA-S05_归档复盘器.py --plan execution_plan.json --task-id P2-01 --task-name "PTA搭建" --no-lessons

# 完整复盘（更新教训库）
python3 PTA-S05_归档复盘器.py --plan execution_plan.json --task-id P2-01 --task-name "PTA搭建"
```

**复盘内容**：
- 执行摘要（步骤数、成功率、耗时）
- 步骤执行日志
- 经验教训（自动提取）
- 改进建议（自动生成）

---

## 四、故障排查

### 4.1 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| S01 解析失败 | 指令过于模糊 | 提供具体任务 ID（如 P1-01） |
| S02 步骤失败 | 脚本不存在 | 检查 TASK_EXECUTION_MAP 配置 |
| S04 Git 失败 | 无变更或冲突 | 检查 git status，手动解决冲突 |
| S05 记录未生成 | 计划文件不存在 | 确认 plan.json 路径正确 |

### 4.2 调试模式

所有子 Agent 都支持 `--dry-run` 模式：

```bash
# 安全测试，不实际执行
python3 PTA-S02_执行调度器.py --input task.json --dry-run
python3 PTA-S04_文档同步器.py --task-id P2-01 --task-name "测试" -m "test" --dry-run
```

---

## 五、扩展开发

### 5.1 添加新任务到执行映射

编辑 `PTA-S02_执行调度器.py` 中的 `TASK_EXECUTION_MAP`：

```python
"P3-01": {
    "name": "新任务名称",
    "steps": [
        {"action": "step1", "tool": "bash", "command": "echo 'hello'", "description": "第一步"},
        {"action": "step2", "tool": "python", "script": "script.py", "description": "第二步"},
    ]
}
```

### 5.2 添加新工具类型

编辑 `PTA-S02_执行调度器.py` 中的 `TOOL_EXECUTORS`：

```python
TOOL_EXECUTORS = {
    "bash": "_exec_bash",
    "python": "_exec_python",
    "browser-use": "_exec_browser_use",
    "my-tool": "_exec_my_tool",  # 新增
}
```

然后添加执行方法：

```python
def _exec_my_tool(self, step: ExecutionStep) -> Tuple[bool, str]:
    # 实现工具逻辑
    return True, "成功"
```

---

## 六、文件清单

| 文件 | 说明 | 大小 |
|------|------|------|
| [PTA-RUN_主编排器.py](PTA-RUN_主编排器.py) | 统一入口：串联 S01→S02→S03→S05 + 状态记忆 | 约 220 行 |
| [PTA-S01_意图解析器.py](PTA-S01_意图解析器.py) | 自然语言 → 任务包 | 356 行 |
| [PTA-S02_执行调度器.py](PTA-S02_执行调度器.py) | 任务包 → 执行计划 | 430 行 |
| [PTA-S03_进度追踪器.py](PTA-S03_进度追踪器.py) | 监控进度 | 289 行 |
| [PTA-S04_文档同步器.py](PTA-S04_文档同步器.py) | Git + 看板同步 | 341 行 |
| [PTA-S05_归档复盘器.py](PTA-S05_归档复盘器.py) | 执行记录 + 教训库 | 353 行 |
| [test_pta_integration.sh](test_pta_integration.sh) | 集成测试脚本 | 159 行 |
| [config.json](config.json) | Agent 配置 | 63 行 |
| [需求定义.md](需求定义.md) | 需求文档 | 141 行 |
| [流程设计.md](流程设计.md) | 流程设计 | 307 行 |

**总计：1,769 行代码 + 文档**

---

## 七、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0.0 | 2026-07-03 | 初始版本，5 个子 Agent 全部完成 |
| v1.1.0 | 2026-07-13 | 新增 PTA-RUN 主编排器（自动串联 + `.pta_state.json` 状态记忆）；修复 S02 脚本路径递归查找 bug（集成测试 82%→100%）；修复 S01 task_id 同日碰撞 bug；S02 新增 `--no-sync` 把 git push 从自动计划中摘出，改为显式确认阶段；.gitignore 修正（此前把三个 Agent 的 config.json 全部误伞盖忽略，从未进过版本库） |

---

> 维护时间：2026-07-03
> 维护人：Jasper
