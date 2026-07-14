# PTA Agent · AI 平台通用调用指南

> 适用平台：Kimi / Codex / Claude / OpenCode / 任何能执行 shell 命令的 AI 环境
> 版本: v1.5.1
> 日期: 2026-07-13（v1.0.0 首版: 2026-07-09）

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
bash test_pta_integration.sh
```

看到全是 ✅ 就是成功了（8 项：S01-S05 各子 Agent + 主编排器 + 跨项目知识库）。

### 4.（可选）如果要用 PTA-DISCOVER 文档任务发现

```bash
export DEEPSEEK_API_KEY=sk-xxx   # 去 platform.deepseek.com 注册获取
```

---

## 统一入口：PTA-RUN（推荐从这里开始）

v1.1.0 起，不再需要人工依次调用 5 个子 Agent——PTA-RUN 自动串联 S01→S02→S03→S05，
并把状态记在 `.pta_state.json` 里，跨会话记得上次做到哪。**任何平台都应该优先用
这一个入口，而不是下面的单个子 Agent 命令**（那些留着是给调试用的）。

```bash
# 查看当前/历史任务状态（新会话开始时先跑这个，恢复上下文）
python3 PTA-RUN_主编排器.py --status

# 一句话指令 → 自动解析 + 出计划 + 出报告（默认 dry-run，不产生真实副作用）
python3 PTA-RUN_主编排器.py "按顺序完成 P1-03, P1-04"

# 真实执行（仍不含 git push）
python3 PTA-RUN_主编排器.py "按顺序完成 P1-03, P1-04" --execute

# 真实执行 + 真实同步文档（git add/commit/push，唯一含真实推送的阶段）
python3 PTA-RUN_主编排器.py "按顺序完成 P1-03, P1-04" --execute --sync -m "commit message"

# 对任意其他项目跑增量文档任务发现（v1.5.0 起，需要 DEEPSEEK_API_KEY）
python3 PTA-RUN_主编排器.py --discover --project-root /path/to/other/project
```

**⚠️ 给其他 AI 平台的重要提醒**：`--sync` 会真实执行 `git push` 到共享仓库。如果你
让另一个 AI 无人值守跑 PTA，务必确认它不会自作主张加上 `--sync`——这一步理应始终
需要人工明确要求。

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
python3 PTA-RUN_主编排器.py "执行 P3-01" --execute --project-root /path/to/other/project
```

未定义的任务 ID 会优雅降级成"请手动执行"的占位步骤，不会报错也不会瞎猜命令。

---

## 各平台触发方式示例

命令本身完全一样，只是"怎么让这个 AI 去跑 shell 命令"的语法不同：

### Kimi Code CLI

```bash
kimi run python3 PTA-RUN_主编排器.py --status
```

### Codex CLI

```bash
codex run python3 PTA-RUN_主编排器.py "按顺序完成 P2-02, P2-03" --execute
```

### Claude Code / 任何终端型 AI

直接把命令交给它的终端/bash 工具执行即可，跟人手动敲命令没有区别：

```bash
python3 PTA-RUN_主编排器.py --discover --project-root /path/to/project
```

### OpenCode / 任何支持 Python 的环境

```bash
python3 PTA-RUN_主编排器.py --status
```

---

## 子 Agent 单独调用（调试/单步排查时用）

正常使用请走上面的 PTA-RUN；只有在某一步出问题、需要单独排查时才手动调这些：

| 子 Agent | 命令 |
|----------|------|
| S01 意图解析 | `python3 PTA-S01_意图解析器.py "指令" --output task.json` |
| S02 执行调度 | `python3 PTA-S02_执行调度器.py --input task.json --dry-run` |
| S03 进度追踪 | `python3 PTA-S03_进度追踪器.py --plan plan.json` |
| S04 文档同步（**真实 git push**） | `python3 PTA-S04_文档同步器.py --task-id ID --task-name "名称" -m "msg" --dry-run` |
| S05 归档复盘 | `python3 PTA-S05_归档复盘器.py --plan plan.json --task-id ID --task-name "名称"` |
| DISCOVER 文档任务发现 | `python3 PTA-DISCOVER_文档任务发现器.py --project /path --scan --dry-run` |
| SCAN 规则扫描 | `python3 PTA-SCAN_智能项目扫描器_v2.py --project /path --snapshot snap.json` |
| EXT 外部项目分析 | `python3 PTA-EXT_外部项目分析器.py --path /path --markdown report.md` |

各自的完整参数说明见 [README.md](README.md)。

---

## 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.7+ | 必须，纯标准库无需 pip install |
| Git | 任意 | S04/PTA-RUN --sync 需要 |
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
| S04/--sync 的 git push 失败 | 检查目标仓库的 git 配置和推送权限 |
| PTA-DISCOVER 结果乱码 | 已修复的编码检测 bug，若仍出现请确认版本 ≥ v1.4.0 |

---

## 验证清单

- [ ] Python 3.7+ 已安装
- [ ] 代码已下载
- [ ] `bash test_pta_integration.sh` 全部通过（8 项）
- [ ] `python3 PTA-RUN_主编排器.py --status` 能正常运行
- [ ] （需要用 DISCOVER 的话）`DEEPSEEK_API_KEY` 已设置且能检测到

---

> 维护时间：2026-07-13
> 维护人：Jasper
