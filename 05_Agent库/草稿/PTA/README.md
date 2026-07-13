# PTA Agent · 项目任务协同 Agent

> Agent ID: PTA
> 版本: v1.5.0
> 状态: 已上线（5/5 子 Agent + 主编排器 + 5 个扩展工具）
> 日期: 2026-07-03（v1.1.0 编排器更新: 2026-07-13 · v1.3.0 文档任务发现器: 2026-07-13 · v1.4.0 增量扫描: 2026-07-13 · v1.5.0 编排器接入发现: 2026-07-13）

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

**接入文档任务发现（v1.5.0 起）**：此前 PTA-DISCOVER（§3.6）是完全独立的工具，
跑完之后只有自己知道结果，PTA-RUN 的 `--status` 看不到"文档里发现了新任务"这件事——
不符合 Agent 该有的"感知外部变化"能力。现在可以让 PTA-RUN 直接调度 PTA-DISCOVER：

```bash
# 对某个项目跑一次增量文档任务发现，结果计入 .pta_state.json
python3 PTA-RUN_主编排器.py --discover --project-root /path/to/other/project

# 之后随时 --status 都能看到这个项目最近发现了什么
python3 PTA-RUN_主编排器.py --status
```

同样刻意保留安全边界：这一步仍然只把发现摘要记进状态文件，**不会**自动写入任何
项目的 `pta_tasks.json`。需要 `export DEEPSEEK_API_KEY=sk-xxx`。

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

### 3.6 PTA-DISCOVER 文档任务发现器（扩展工具，v1.4.0）

**功能**：调用 DeepSeek API 阅读外部项目的自由行文文档（合同/会议纪要/审计报告等），
提取隐含的任务，产出人工可审阅的"发现报告"。

**为什么需要它**：S01 的意图解析是纯正则规则，只能处理一句已经说清楚的指令；
PTA-SCAN 也是纯规则扫描，只能读懂已结构化的 markdown checklist 和带列名的 CSV。
两者都读不懂合同、会议纪要里"藏在一段话里的任务"——这一步是阅读理解，只有模型能做。

**⚠️ 安全边界（刻意设计）**：输出只是发现报告，**不会**自动写入 `pta_tasks.json`
的 `steps`/`command` 字段——那些字段驱动 S02 的真实 shell/python 执行。任意文档
的内容直接进执行步骤等于一个命令注入面。把发现的任务变成可执行步骤，永远需要
人工手写 `pta_tasks.json`。

**环境要求**：`export DEEPSEEK_API_KEY=sk-xxx`（不要把 key 写进代码或文件）

**增量扫描（v1.4.0 起）**：`--scan` 现在按内容 sha256 跟"上一次 PTA-DISCOVER 自己
的处理记录"比对，只处理新增/变更过的文件，而不是每次全量重扫。记录存在
`<project>/.pta_discover_state.json`——这是一份独立文件，不是 PTA-SCAN 的
`.pta_snapshot.json`：PTA-SCAN 每次运行会整体覆盖写自己的快照，共用一份文件会让
两边互相冲掉对方的记录，所以两边各自维护状态，但用的是同一套"内容哈希比对"思路。

**常用命令**：

```bash
# 显式指定候选文件（总是处理，不受增量状态影响）
python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project \
    --files 合同.md 会议纪要.md --output discovered_tasks.json

# 增量扫描：只处理自上次 PTA-DISCOVER 运行以来新增/变更的 .md/.txt/.csv
python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project --scan --output discovered_tasks.json

# 忽略增量记录，强制全部重新处理
python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project --scan --force

# 只看这次会发给模型的候选文件和字符数，不实际调用 API（免费预览，也不更新增量状态）
python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project --scan --dry-run
```

**输出**：每个发现的任务包含 `name`/`owner`/`status`/`due_date`/`evidence`（原文
证据片段）/`confidence`/`source_file`，供人工判断是否可信、是否需要转化为
`pta_tasks.json` 里的真实执行步骤。

---

## 四、故障排查

### 4.1 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| S01 解析失败 | 指令过于模糊 | 提供具体任务 ID（如 P1-01） |
| S02 步骤失败 | 脚本不存在 | 检查任务知识库配置（见 §5.1，`pta_tasks.json` 或内置 `pta_tasks_default.json`） |
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

### 5.1 添加新任务到执行映射（跨项目通用，v1.2.0 起）

v1.0.0 里任务执行知识库是硬编码在 `PTA-S02_执行调度器.py` 源码里的 Python 字典，
只认识本项目自己的 9 个任务；v1.2.0 起改为外部 JSON 文件（`pta_common.py` 统一加载，
S01/S02 共用），加载优先级：

1. `--task-map <path>` 显式指定的文件
2. `--project-root <dir>` 下的 `pta_tasks.json`（**目标项目自己的**任务知识库）
3. PTA 目录自带的 [pta_tasks_default.json](pta_tasks_default.json)（本项目内置 9 个任务，兜底）

**给任意项目（不只是本项目）添加新任务**：在目标项目根目录放一份 `pta_tasks.json`：

```json
{
  "P3-01": {
    "name": "新任务名称",
    "steps": [
      {"action": "step1", "tool": "bash", "command": "echo 'hello'", "description": "第一步"},
      {"action": "step2", "tool": "python", "script": "script.py", "description": "第二步"}
    ]
  }
}
```

然后：

```bash
python3 PTA-RUN_主编排器.py "执行 P3-01" --execute --project-root /path/to/other/project
```

未在任务知识库里定义的任务 ID，S02 会优雅降级为一个"请手动执行"的占位步骤，
不会报错，也不会瞎猜命令。

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
| [PTA-DISCOVER_文档任务发现器.py](PTA-DISCOVER_文档任务发现器.py) | 调用 DeepSeek 从自由行文文档中发现任务（仅报告，不驱动执行） | 约 220 行 |
| [pta_common.py](pta_common.py) | 任务知识库加载逻辑（S01/S02 共用） | 约 40 行 |
| [pta_tasks_default.json](pta_tasks_default.json) | 本项目内置的 9 个任务知识库（兜底） | 约 60 行 |
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
| v1.2.0 | 2026-07-13 | 任务知识库外置为 JSON（`pta_common.py` + `pta_tasks_default.json`），S01/S02 支持 `--project-root`/`--task-map` 加载任意项目自己的 `pta_tasks.json`，不再局限于本项目硬编码的 9 个任务；S01 任务 ID 识别正则从只认 `P#-##` 泛化为任意大写字母前缀编号（如 `TRK-001`、`RW-01`）；已用一个真实的假外部项目验证：自定义任务被正确识别并执行，而非落到通用占位步骤 |
| v1.3.0 | 2026-07-13 | 新增 PTA-DISCOVER 文档任务发现器：调用 DeepSeek API（纯 `urllib` 实现，无需额外 pip 依赖）从合同/会议纪要等自由行文文档中提取任务；刻意只产出人工可审阅的发现报告，不自动写入 `pta_tasks.json` 的可执行步骤，避免文档内容变成命令注入面；修复 SSL 证书验证 bug（Homebrew Python 默认证书路径缺失）、内容去重（同一文档在项目里存在多份拷贝时跳过重复调用）、GBK 编码检测 bug（无脑假设 UTF-8 曾把一份 GBK CSV 读成乱码喂给模型）；已在真实的 Rw 权益项目上跑通全量扫描：563 个文件、4568 条任务、0 失败 |
| v1.4.0 | 2026-07-13 | PTA-DISCOVER `--scan` 从"按最近 N 天"改为按内容 sha256 跟自己的历史处理记录比对的真正增量扫描（记录存 `.pta_discover_state.json`，跟 PTA-SCAN 的快照文件分开维护，避免互相覆盖写）；新增 `--force` 强制全量重扫；已用三个场景验证：新文件→处理、内容不变→0 次调用直接跳过、内容变了→正确识别新增任务 |
| v1.5.0 | 2026-07-13 | PTA-RUN 新增 `--discover --project-root <path>`，直接调度 PTA-DISCOVER 做增量文档任务发现，结果（含前 5 条预览）计入 `.pta_state.json`，`--status` 能直接看到"文档里发现了几条新任务"，不用再单独去读发现报告；同样保留安全边界，只记摘要，不自动写入任何项目的 `pta_tasks.json`；已端到端验证：首次发现、增量跳过（0 次调用）两种场景 |

---

> 维护时间：2026-07-03
> 维护人：Jasper
