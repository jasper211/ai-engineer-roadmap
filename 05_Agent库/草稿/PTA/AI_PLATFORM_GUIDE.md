# PTA Agent · AI 平台通用调用指南

> 适用平台：Kimi / Codex / Claude / OpenCode / 任何能执行 shell 命令的 AI 环境
> 版本: v2.1.0
> 日期: 2026-07-14（v1.0.0 首版: 2026-07-09）
>
> v2.0.0 变更：项目从扁平的 PTA-S01~S05 + PTA-RUN 脚本结构，迁移为
> `agents/skills/tools/memory/prompts/tests` 标准结构。**统一入口从
> `PTA-RUN_主编排器.py` 换成 `agents/agent.py`**；S01-S05 不再是可独立调用的
> 脚本，改成了 `skills/` 下的 Python 类，调试单个环节请直接看对应 `skills/*.py`
> 源码或写测试脚本 import 调用，不再有对应的 CLI 入口。旧版脚本原样保留在
> `_retired_flat_structure/` 供追溯。
>
> v2.1.0 变更：按《Agent 项目搭建全流程》11 步方法论，把 agents/skills/tools/
> memory/prompts/tests 六个包目录各自套进一个编号+中英文命名的顶层文件夹
> （01-11，见 [README.md](README.md) 的目录结构一节），下文命令里的路径已按
> 新结构更新。这套 01-11 结构是以后任何 Agent 搭建都要遵循的标准模板。

---

## 核心事实：PTA 没有任何"平台专属"的东西

PTA 就是一组纯 Python 脚本，靠命令行参数交互。**任何 AI 平台只要能执行 shell 命令，
调用方式都跟本文档一样**——不需要 Claude、不需要特定 SDK，让那个 AI 在它自己的
终端/代码执行工具里跑 `python3 xxx.py` 就行，跟人手动敲命令没有区别。

唯一的平台差异是"这个 AI 怎么触发 shell 命令"（有的叫 `kimi run`，有的直接给终端），
命令本身永远一样。

---

## 快速开始（1 分钟）

### 1. 获取代码

```bash
git clone https://github.com/jasper211/ai-engineer-roadmap.git
cd ai-engineer-roadmap/05_Agent库/草稿/PTA/
```

### 2. 验证环境

```bash
python3 --version  # 需要 Python 3.7+，纯标准库无需 pip install
```

### 3. 运行测试

```bash
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

看到全是 ✅ 就是成功了（9 项：5 个技能 + agent.py 全链路 + 跨项目知识库 +
git 同步安全行为验证）。

### 4.（可选）如果要用 PTA-DISCOVER 文档任务发现

```bash
export DEEPSEEK_API_KEY=sk-xxx   # 去 platform.deepseek.com 注册获取
```

---

## 统一入口：04_定义Agent_Define_Agent/agents/agent.py（推荐从这里开始）

`04_定义Agent_Define_Agent/agents/agent.py` 是 Think-Act-Observe 主循环，自动串联意图解析→执行编排→
进度追踪→归档复盘，并把状态记在专属工作区的 `state.json` 里，跨会话记得
上次做到哪。**任何平台都应该优先用这一个入口**。

```bash
# 查看当前/历史任务状态（新会话开始时先跑这个，恢复上下文）
python3 04_定义Agent_Define_Agent/agents/agent.py --status

# 一句话指令 → 自动解析 + 出计划 + 出报告（默认 dry-run，不产生真实副作用）
python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04"

# 真实执行（仍不含 git push）
python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04" --execute

# 真实执行 + 真实同步文档（git add/commit/push，唯一含真实推送的阶段）
python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04" --execute --sync -m "commit message"
```

**⚠️ 给其他 AI 平台的重要提醒**：`--sync` 会真实执行 `git push` 到共享仓库。如果你
让另一个 AI 无人值守跑 PTA，务必确认它不会自作主张加上 `--sync`——这一步理应始终
需要人工明确要求。

**文档任务发现（--discover）尚未迁移**：这个功能这次没有并入 `agent.py`，仍需
直接调用独立脚本 `PTA-DISCOVER_文档任务发现器.py`（见下面"扩展脚本"一节），
需要 `DEEPSEEK_API_KEY`。

---

## 跨项目使用：不再局限于本项目的 9 个任务

v1.2.0 起，PTA 不再硬编码"只认识这个能力整改项目自己的任务"。要在**别的项目**上
用 PTA，在目标项目根目录放一份 `pta_tasks.json`：

```json
{
  "P3-01": {
    "name": "新任务名称",
    "steps": [
      {"action": "step1", "tool": "bash", "command": "echo hello", "description": "第一步"}
    ]
  }
}
```

然后：

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py "执行 P3-01" --execute --project-root /path/to/other/project
```

未定义的任务 ID 会优雅降级成"请手动执行"的占位步骤，不会报错也不会瞎猜命令。

---

## 各平台触发方式示例

命令本身完全一样，只是"怎么让这个 AI 去跑 shell 命令"的语法不同：

### Kimi Code CLI

```bash
kimi run python3 04_定义Agent_Define_Agent/agents/agent.py --status
```

### Codex CLI

```bash
codex run python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P2-02, P2-03" --execute
```

### Claude Code / 任何终端型 AI

直接把命令交给它的终端/bash 工具执行即可，跟人手动敲命令没有区别：

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --status --project-root /path/to/project
```

### OpenCode / 任何支持 Python 的环境

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --status
```

---

## 五个技能（S01-S05）：不再有 CLI，调试请直接看源码/写脚本 import

v2.0.0 起 S01-S05 不再是独立可调用的脚本，而是 `skills/` 下的 Python 类，
只能被 `04_定义Agent_Define_Agent/agents/agent.py`（或任何 import 它们的代码）在同进程内调用，没有
单独的命令行参数可传。正常使用只走 `04_定义Agent_Define_Agent/agents/agent.py` 一个入口即可；如果
需要单独排查某个环节，最快的方式是照着 `09_测试与调试_Test_and_Debug/tests/test_integration.py` 里
对应 Test 的写法，写几行 Python 直接 import 调用：

| 技能 | 源码 | 对应旧版 |
|------|------|---------|
| 意图解析 | `06_开发技能_Develop_Skills/skills/intent_parsing.py` | S01 |
| 执行编排 | `06_开发技能_Develop_Skills/skills/execution_planning.py` | S02 |
| 进度追踪 | `06_开发技能_Develop_Skills/skills/progress_tracking.py` | S03 |
| 文档同步（**真实 git push**） | `06_开发技能_Develop_Skills/skills/doc_sync.py` | S04 |
| 归档复盘 | `06_开发技能_Develop_Skills/skills/archive_review.py` | S05 |
| 项目仪表盘（**批1新迁移**） | `06_开发技能_Develop_Skills/skills/project_dashboard.py` | PTA-DASH |

## 工具（v2.4.0 批1 新增）

| 工具 | 源码 | 对应旧版 |
|------|------|---------|
| 目录结构分析 | `05_集成工具_Integrate_Tools/tools/dir_scan.py` | PTA-EXT |

命令行调用：

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --dashboard --project-root /path/to/Rw项目 --person Roy
python3 04_定义Agent_Define_Agent/agents/agent.py --dir-scan --project-root /path --depth 2 --report-output report.md
```

## 扩展脚本（批2/批3待做，仍是独立 CLI 脚本）

| 脚本 | 命令 |
|------|------|
| **MONITOR 自我监控**（PTA 自己用得怎么样，非分析别的项目） | `python3 11_监控与优化_Monitor_and_Optimize/PTA-MONITOR_自我监控.py`（不传 `--project-root` 则汇总所有用过 PTA 的项目） |
| DISCOVER 文档任务发现 | `python3 11_监控与优化_Monitor_and_Optimize/PTA-DISCOVER_文档任务发现器.py --project /path --scan --dry-run` |
| SCAN 规则扫描 | `python3 11_监控与优化_Monitor_and_Optimize/PTA-SCAN_智能项目扫描器_v2.py --project /path --snapshot snap.json` |
| INTEL / INTEL-RW 智能项目分析器 | 见各自源码文件头注释 |

DISCOVER/SCAN（批2）、INTEL+INTEL-RW 合并（批3）已确认要做，尚未执行，
详见 `11_监控与优化_Monitor_and_Optimize/README.md` 的迁移进度说明。

---

## 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.7+ | 必须，纯标准库无需 pip install |
| Git | 任意 | doc_sync / agent.py --sync 需要 |
| DeepSeek API Key | — | 只有用 PTA-DISCOVER 时需要，`export DEEPSEEK_API_KEY=sk-xxx` |

---

## 故障排查

| 问题 | 原因 / 解决 |
|------|------|
| `python3: command not found` | 安装 Python 3 或改用 `python` |
| `Permission denied` | `chmod +x *.py` 或改用 `python3 xxx.py` |
| `Module not found` | 核心功能不需要安装任何包；PTA-DISCOVER 遇到 SSL 证书报错见下一条 |
| PTA-DISCOVER 报 SSL 证书错误 | 已知的 Homebrew Python 证书路径问题，脚本内置了 certifi/系统证书兜底，正常应该不会再出现 |
| DEEPSEEK_API_KEY 检测不到 | 确认写在 `~/.zshenv`（非交互式 shell 会读的文件），不是只写在 `~/.zshrc` |
| doc_sync/--sync 的 git push 失败 | 检查目标仓库的 git 配置和推送权限 |
| PTA-DISCOVER 结果乱码 | 已修复的编码检测 bug，若仍出现请确认版本 ≥ v1.4.0 |

---

## 验证清单

- [ ] Python 3.7+ 已安装
- [ ] 代码已下载
- [ ] `python3 09_测试与调试_Test_and_Debug/tests/test_integration.py` 全部通过（9 项）
- [ ] `python3 04_定义Agent_Define_Agent/agents/agent.py --status` 能正常运行
- [ ] （需要用 DISCOVER 的话）`DEEPSEEK_API_KEY` 已设置且能检测到

---

> 维护时间：2026-07-14
> 维护人：Jasper
