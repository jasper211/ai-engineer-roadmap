# PTA Agent · AI 平台通用调用指南

> 适用平台：Kimi / Codex / Claude / OpenCode / 任何支持 Python 的 AI 环境
> 版本: v1.0.0
> 日期: 2026-07-09

---

## 快速开始（30 秒）

### 1. 获取代码

```bash
git clone https://github.com/jasper211/ai-engineer-roadmap.git
cd ai-engineer-roadmap/05_Agent库/草稿/PTA/
```

### 2. 验证环境

```bash
python3 --version  # 需要 Python 3.7+
```

### 3. 运行测试

```bash
bash test_pta_integration.sh
```

看到全是 ✅ 就是成功了。

---

## 各平台使用方式

### 平台 A：Kimi Code CLI

```bash
# 在 Kimi 终端中执行
kimi run python3 PTA-S01_意图解析器.py "按顺序完成 P2-02, P2-03"
```

### 平台 B：Codex CLI

```bash
# 在 Codex 环境中执行
codex run python3 PTA-S02_执行调度器.py --input task.json --dry-run
```

### 平台 C：Claude Code

```bash
# 在 Claude 终端中执行
claude python3 PTA-EXT_外部项目分析器.py --path /path/to/project --markdown report.md
```

### 平台 D：OpenCode（当前环境）

```bash
# 直接执行
python3 PTA-S01_意图解析器.py "分析 Rw 权益项目" --output task.json
```

---

## 核心命令速查

### 意图解析（S01）

```bash
python3 PTA-S01_意图解析器.py "你的自然语言指令" --output task.json
```

**示例**:
```bash
python3 PTA-S01_意图解析器.py "按顺序完成 P0-02, P0-03, P1-03" --output /tmp/task.json
```

### 执行调度（S02）

```bash
python3 PTA-S02_执行调度器.py --input task.json [--dry-run]
```

**示例**:
```bash
python3 PTA-S02_执行调度器.py --input /tmp/task.json --dry-run
python3 PTA-S02_执行调度器.py --input /tmp/task.json --output plan.json
```

### 进度追踪（S03）

```bash
python3 PTA-S03_进度追踪器.py --plan plan.json [--watch]
```

**示例**:
```bash
python3 PTA-S03_进度追踪器.py --plan /tmp/plan.json
python3 PTA-S03_进度追踪器.py --plan /tmp/plan.json --watch --interval 10
```

### 文档同步（S04）

```bash
python3 PTA-S04_文档同步器.py --task-id ID --task-name "名称" -m "提交信息" [--dry-run]
```

**示例**:
```bash
python3 PTA-S04_文档同步器.py --task-id P2-01 --task-name "PTA搭建" -m "feat: complete" --dry-run
```

### 归档复盘（S05）

```bash
python3 PTA-S05_归档复盘器.py --plan plan.json --task-id ID --task-name "名称"
```

**示例**:
```bash
python3 PTA-S05_归档复盘器.py --plan /tmp/plan.json --task-id P2-01 --task-name "PTA搭建"
```

### 外部项目分析（EXT）

```bash
python3 PTA-EXT_外部项目分析器.py --path /path/to/project [--depth N] [--markdown report.md]
```

**示例**:
```bash
python3 PTA-EXT_外部项目分析器.py --path /Users/xxx/Desktop/Rw权益项目 --depth 2 --markdown report.md
```

---

## 完整工作流示例

```bash
# Step 1: 解析意图
python3 PTA-S01_意图解析器.py "按顺序完成 P2-02, P2-03" --output /tmp/task.json

# Step 2: 调度执行（dry-run 先测试）
python3 PTA-S02_执行调度器.py --input /tmp/task.json --dry-run

# Step 3: 实际执行
python3 PTA-S02_执行调度器.py --input /tmp/task.json --output /tmp/plan.json

# Step 4: 监控进度
python3 PTA-S03_进度追踪器.py --plan /tmp/plan.json

# Step 5: 同步文档
python3 PTA-S04_文档同步器.py --task-id P2-01 --task-name "PTA搭建" -m "feat: complete"

# Step 6: 归档复盘
python3 PTA-S05_归档复盘器.py --plan /tmp/plan.json --task-id P2-01 --task-name "PTA搭建"
```

---

## 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.7+ | 必须 |
| Git | 任意 | S04 需要 |
| Bash | 任意 | 测试脚本需要 |

**纯 Python 标准库**，无外部依赖。

---

## 故障排查

| 问题 | 解决 |
|------|------|
| `python3: command not found` | 安装 Python 3 或改用 `python` |
| `Permission denied` | `chmod +x *.py` 或 `python3 xxx.py` |
| `Module not found` | 不需要安装，纯标准库 |
| Git 失败 | 检查 git config 和 SSH 密钥 |

---

## 文件清单

| 文件 | 大小 | 功能 |
|------|------|------|
| PTA-S01_意图解析器.py | 356 行 | 自然语言 → 任务包 |
| PTA-S02_执行调度器.py | 430 行 | 任务包 → 执行计划 |
| PTA-S03_进度追踪器.py | 289 行 | 监控进度 |
| PTA-S04_文档同步器.py | 341 行 | Git + 看板同步 |
| PTA-S05_归档复盘器.py | 353 行 | 执行记录 + 教训库 |
| PTA-EXT_外部项目分析器.py | 325 行 | 分析任意项目 |
| test_pta_integration.sh | 159 行 | 集成测试 |
| README.md | 306 行 | 详细文档 |
| AI_PLATFORM_GUIDE.md | 本文件 | 平台通用指南 |

**总计：2,769 行代码 + 文档**

---

## 验证清单

- [ ] Python 3.7+ 已安装
- [ ] Git 已配置
- [ ] 代码已下载
- [ ] `bash test_pta_integration.sh` 全部通过
- [ ] 能成功运行单个脚本
- [ ] 能完成完整工作流

---

> 维护时间：2026-07-09
> 维护人：Jasper
