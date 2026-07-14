# OB知识库同步巡检Agent · README

> **文档定位**：OB-SYNC-AG01 的使用说明  
> **核心作用**：① 巡检 OB 同步健康状态 ② 确保多终端 AI 可访问 OB 知识库 ③ 生成可视化健康报告  
> **使用场景**：① 每天开机后手动运行 ② 配置变更后验证 ③ 挂载 launchd 定时执行  
> **维护责任**：Jasper  
> **迭代规则**：每发现一个未覆盖的巡检项，追加检查和输出  
> **关联文件**：config.json / ob_sync_agent.py  
> **版本**：v1.0 | 2026-07-10

---

## 一、Agent 概述

### 解决的问题
- ObsidianVault 的符号链接是否完整？
- Qoder / Claude Desktop / Kimi Code 的 MCP 配置是否一致？
- MCP Server 能否正常构建索引？
- F1/F2/F3 文件是否存在？

### 运行方式

```bash
# 手动执行
python3 ob_sync_agent.py

# 指定输出路径
python3 ob_sync_agent.py --output /path/to/report.md

# 挂载定时任务（每早9点）
# 添加到 crontab 或 launchd plist
```

### 巡检项目

| 检查项 | 内容 | 异常时的含义 |
|--------|------|-------------|
| **符号链接** | Desktop → OB 的 symlink 是否有断链 | 如果移动了文件夹，更新 symlink |
| **MCP 配置** | Qoder/Claude/Kimi 的 mcp.json 是否指向正确 Server 路径 | AI 工具无法读 OB，更新 JSON |
| **MCP Server** | 能否调起 `vault.mjs` 构建索引 | Node 环境或 Server 文件有问题 |
| **F1/F2/F3** | V2.0 上下文文件是否存在可读 | Jasper 需要重建/补文件 |
| **Vault 统计** | Markdown 文件数 + 目录数 | 趋势监控 |

## 二、产出文件

| 文件 | 用途 | 位置 |
|------|------|------|
| `OB同步健康报告.md` | 健康报告 | `项目-流程架构/08_任务与跟进/AI上下文/` |

报告中每项标注 ✅/❌，有问题时附操作建议。

## 三、目录结构

```
OB知识库同步巡检Agent/
├── config.json          ← Agent 配置
├── README.md            ← 本文档
├── ob_sync_agent.py     ← 主脚本
└── 执行记录.md           ← 每次运行的日志（自动生成）
```

## 四、扩展计划

- v1.1：增加 Git 同步状态检查（是否 auto-push 正常）
- v1.2：增加 Ob 笔记质量检查（是否有破损 wikilink）
- v2.0：接入 Qoder MCP 自动修复（检测到配置错误自动建议修复命令）
