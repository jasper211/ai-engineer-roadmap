# Agent 搭建 SOP（标准操作流程）

> 版本: v1.0 | 2026-07-03
> 定位: 从 0 到 1 搭建一个 Agent 的完整步骤指南
> 适用范围: PTA / VNW / AIT 三大主 Agent 及所有子 Agent

---

## 📋 文档定位说明

| 字段 | 内容 |
|------|------|
| **文档定位** | Agent 开发的标准化操作手册 |
| **核心作用** | ① 确保每个 Agent 按统一流程搭建 ② 降低 Agent 开发的理解门槛 ③ 作为复盘和交接的参考 |
| **使用场景** | ① 新 Agent 开发前阅读 ② 开发过程中对照检查 ③ 开发完成后审计 |
| **维护责任** | Jasper 主责，每完成一个 Agent 后更新经验教训 |
| **迭代规则** | ① 每完成 3 个 Agent 后复盘优化 ② 发现流程瓶颈时更新 |
| **关联文件** | [三大主 Agent 体系架构](三大主Agent体系架构_v1.0.md) · [Agent 资产库规范](../../../流程架构项目_jasper/05_Agent库/AGENT_INDEX.md) |

---

## 一、Agent 是什么？

### 1.1 通俗理解

Agent = **自动化机器人**，它有：
- **大脑**（JSON 配置）：知道自己是干什么的、能调用什么工具
- **感官**（监控/输入）：感知外部变化（文件变更、用户指令）
- **手脚**（子 Agent/脚本）：执行具体任务（解析 Excel、生成报告）
- **记忆**（状态文件）：记住上次做了什么，避免重复

### 1.2 与脚本的区别

| 维度 | 脚本（Script） | Agent |
|------|-------------|-------|
| **触发方式** | 手动执行 | 自动监控 + 触发 |
| **上下文** | 每次从头开始 | 有状态记忆 |
| **协作能力** | 独立运行 | 可调用其他 Agent |
| **配置化** | 硬编码 | JSON 配置驱动 |
| **可复用** | 复制粘贴 | 标准化接口调用 |

### 1.3 Agent 的组成部分

```
Agent/
├── config.json          ← 大脑：定义职责、输入输出、依赖关系
├── README.md            ← 说明书：人类可读的文档
├── 子Agent/              ← 手脚：具体执行单元
│   ├── S01_xxx.py
│   ├── S02_xxx.py
│   └── ...
├── 执行记录.md            ← 日志：每次运行的记录
└── .state.json          ← 记忆：状态持久化
```

---

## 二、Agent 搭建六步法

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ 第1步   │ → │ 第2步   │ → │ 第3步   │ → │ 第4步   │ → │ 第5步   │ → │ 第6步   │
│ 需求定义 │    │ 流程设计 │    │ 配置编写 │    │ 子Agent │    │ 集成测试 │    │ 文档归档 │
│         │    │         │    │         │    │ 开发    │    │         │    │         │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
   1天           1天           0.5天          2-3天          1天           0.5天
```

---

## 第1步：需求定义（1天）

### 1.1 回答三个问题

| 问题 | 示例（VNW） |
|------|------------|
| **这个 Agent 解决什么问题？** | 价值节点清单更新后，自动完成信号提取到规则空白地图的全流程 |
| **谁用这个 Agent？** | Jasper（触发）、AI 协同终端（执行）、Mark（审核产出） |
| **成功标准是什么？** | 清单更新后 5 分钟内自动生成新的规则空白地图 |

### 1.2 输出物

- [ ] `需求定义.md`（3-5 句话描述）
- [ ] 确认 L3 流程边界（从哪开始、到哪结束）

---

## 第2步：流程设计（1天）

### 2.1 画出 L3 端到端流程

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ L3-XXX-01│ → │ L3-XXX-02│ → │ L3-XXX-03│ → │ L3-XXX-04│ → │ L3-XXX-05│
│ 输入处理 │    │ 核心处理 │    │ 中间处理 │    │ 输出生成 │    │ 同步归档 │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
     ↑                                                              ↓
     └──────────────────────────────────────────────────────────────┘
                           反馈闭环
```

### 2.2 定义每个 L3 的输入输出

| L3 编码 | 名称 | 输入 | 输出 | 子 Agent |
|---------|------|------|------|---------|
| L3-VNW-01 | 节点解析 | 清单 Excel | 节点 JSON | VNW-S01, VNW-S02 |
| L3-VNW-02 | 信号提取 | 节点 JSON + 蓝图 | 信号基线 MD | VNW-S03 |

### 2.3 输出物

- [ ] 流程图（Mermaid 或文字描述）
- [ ] 子 Agent 清单（名称 + 职责 + 输入输出）

---

## 第3步：配置编写（0.5天）

### 3.1 编写 config.json

```json
{
  "agent_id": "VNW",
  "name": "价值节点驱动工作流 Agent",
  "version": "1.0.0",
  "status": "草稿",
  "description": "自动完成价值节点清单→信号提取→规则空白地图的全流程",
  
  "l3_flow": [
    {
      "code": "L3-VNW-01",
      "name": "节点解析",
      "sub_agents": ["VNW-S01", "VNW-S02"],
      "input": "价值节点清单 Excel",
      "output": "结构化节点 JSON"
    }
  ],
  
  "skills_used": ["pandas", "markdown", "re", "jinja2"],
  
  "dependencies": {
    "upstream": [],
    "downstream": ["PTA-S04"]
  },
  
  "archive_gate": {
    "mark_confirmed": false,
    "deliverables": ["config.json", "README.md"]
  }
}
```

### 3.2 编写 README.md

```markdown
# VNW Agent · 价值节点驱动工作流

## 快速开始

```bash
# 检查清单变更
python3 VNW-S01_清单监控器.py --check

# 全量信号提取
python3 VNW-S03_信号提取器.py --all

# 生成规则空白地图
python3 VNW-S05_规则空白生成器.py --baseline auto_v1.1.md
```

## 架构

```
[清单 Excel] → [S01 监控] → [S02 解析] → [S03 信号提取] → [S04 基线合并] → [S05 规则空白] → [HTML 报告]
```
```

### 3.3 输出物

- [ ] `config.json`（机器可读）
- [ ] `README.md`（人类可读）

---

## 第4步：子 Agent 开发（2-3天）

### 4.1 每个子 Agent 的标准结构

```python
#!/usr/bin/env python3
"""
{AgentID}-S{序号} · {名称}
功能：{一句话描述}
运行：python3 {文件名}.py [--参数]
"""

import argparse
from pathlib import Path

# 配置区
DEFAULT_CONFIG = {
    "input_dir": "/path/to/input",
    "output_dir": "/path/to/output",
}

class {SubAgentName}:
    """{描述}"""
    
    def __init__(self, config: dict):
        self.config = config
    
    def run(self) -> dict:
        """主执行逻辑"""
        pass
    
    def validate(self) -> bool:
        """输入验证"""
        pass

def main():
    parser = argparse.ArgumentParser(description="{名称}")
    parser.add_argument("--input", help="输入路径")
    parser.add_argument("--output", help="输出路径")
    args = parser.parse_args()
    
    agent = {SubAgentName}(vars(args))
    result = agent.run()
    print(result)

if __name__ == "__main__":
    main()
```

### 4.2 开发 checklist

每个子 Agent 必须满足：

- [ ] 有清晰的 docstring（功能、运行方式）
- [ ] 有 argparse 参数支持
- [ ] 有输入验证（validate 方法）
- [ ] 有错误处理（try-except + 友好错误信息）
- [ ] 有返回值（结构化 dict，便于上游调用）
- [ ] 有状态持久化（如需记忆上次状态）
- [ ] 生产环境只读（如需写入，只在实验环境）

### 4.3 输出物

- [ ] 所有子 Agent 的 `.py` 文件
- [ ] 每个子 Agent 的单元测试（至少 1 个测试用例）

---

## 第5步：集成测试（1天）

### 5.1 测试层级

| 层级 | 测试内容 | 工具 |
|------|---------|------|
| 单元测试 | 每个子 Agent 独立运行 | pytest |
| 集成测试 | 子 Agent 串联运行 | shell 脚本 |
| 端到端测试 | 完整 L3 流程 | 手动验证 |

### 5.2 集成测试脚本示例

```bash
#!/bin/bash
# test_vnw_integration.sh

echo "=== VNW Agent 集成测试 ==="

# Step 1: 监控检查
python3 VNW-S01_清单监控器.py --check
if [ $? -ne 0 ]; then
    echo "✅ 检测到变更，继续执行"
else
    echo "ℹ️ 无变更，跳过"
    exit 0
fi

# Step 2: 节点解析
python3 VNW-S02_节点解析器.py --input "$INPUT_EXCEL" --output nodes.json

# Step 3: 信号提取
python3 VNW-S03_信号提取器.py --input nodes.json --output baseline.md

# Step 4: 规则空白生成
python3 VNW-S05_规则空白生成器.py --baseline baseline.md --output rule_gap.html

echo "=== 测试完成 ==="
```

### 5.3 输出物

- [ ] 集成测试脚本
- [ ] 测试报告（通过/失败 + 截图证据）

---

## 第6步：文档归档（0.5天）

### 6.1 归档 checklist

- [ ] 更新 Agent 状态（草稿 → 测试中 → 已确认）
- [ ] 创建执行记录（任务执行记录.md）
- [ ] 更新看板（能力整改看板.md）
- [ ] Git 提交（feat(agent): XXX Agent v1.0）
- [ ] 更新 AGENT_INDEX.md（Agent 资产库索引）

### 6.2 执行记录模板

```markdown
# {AgentID} · {名称} · 执行记录

## 任务信息

| 字段 | 内容 |
|------|------|
| Agent ID | {AgentID} |
| 版本 | v1.0.0 |
| 开始时间 | 2026-XX-XX |
| 完成时间 | 2026-XX-XX |

## 产出清单

| 产出 | 路径 | 说明 |
|------|------|------|
| 配置文件 | config.json | Agent 元数据 |
| 子 Agent | S01_xxx.py | ... |

## 踩坑记录

| 问题 | 解决方案 |
|------|---------|
| ... | ... |
```

### 6.3 输出物

- [ ] 执行记录.md
- [ ] Git 提交 + Push
- [ ] 看板更新

---

## 三、三大 Agent 同步推进策略

### 3.1 时间线

```
Week 1: VNW 需求定义 + 流程设计 + 配置编写
Week 2: VNW 子 Agent 开发 + 集成测试 + 文档归档
Week 3: PTA 需求定义 + 流程设计 + 配置编写
Week 4: PTA 子 Agent 开发 + 集成测试 + 文档归档
Week 5: AIT 需求定义 + 流程设计 + 配置编写
Week 6: AIT 子 Agent 开发 + 集成测试 + 文档归档
```

### 3.2 并行策略

| 周次 | VNW | PTA | AIT |
|------|-----|-----|-----|
| W1 | 需求+流程+配置 | - | - |
| W2 | 开发+测试+归档 | 需求+流程+配置 | - |
| W3 | 维护迭代 | 开发+测试+归档 | 需求+流程+配置 |
| W4 | 维护迭代 | 维护迭代 | 开发+测试+归档 |

### 3.3 依赖关系

```
VNW 先完成（基础能力）
    ↓
PTA 复用 VNW 的部分子 Agent（如文档同步）
    ↓
AIT 复用 VNW 的信号提取 + PTA 的任务调度
```

---

## 四、快速参考

### 4.1 常用命令

```bash
# 创建新 Agent 目录
mkdir -p 05_Agent库/草稿/{AgentID}

# 初始化 Agent 配置
cp templates/agent_config.json 05_Agent库/草稿/{AgentID}/config.json

# 运行子 Agent
python3 {AgentID}-S{序号}_{名称}.py --help

# 集成测试
bash test_{agent_id}_integration.sh

# Git 提交
git add . && git commit -m "feat(agent): {AgentID} v{版本} - {描述}" && git push
```

### 4.2 检查清单

每次开发前：
- [ ] 阅读本 SOP
- [ ] 确认需求定义.md
- [ ] 确认 L3 流程边界

每次开发后：
- [ ] 运行单元测试
- [ ] 运行集成测试
- [ ] 更新执行记录
- [ ] 更新看板
- [ ] Git 提交

---

> 归档时间：2026-07-03
> 下次更新：完成第一个 Agent 后复盘
