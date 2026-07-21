# OB · Obsidian 知识库 Agent

v0.4.0 —— 按 01-11 骨架（同 PTA 已验证的标准模板）搭建，三条能力线（巡检/
检索服务/概念笔记提炼）全部实现+真实数据验证通过，vault 已完成物理迁移+
内容重置，概念笔记提炼补齐了批量+增量编排（不再只能单文件手动调用）。

**2026-07-21 补充（写入侧自动化增强，详见
[写入侧自动化增强设计_v1.md](03_规划项目结构_Plan_Project_Structure/写入侧自动化增强设计_v1.md)）**：
- `write_atom()` 现在补齐 authority_layer（确定性派生）/confidence+
  confidence_reason（LLM随提炼一并给出）/decision_status/entity_type/
  entity_ref 完整schema，不再只写5个基础字段——此前 Jasper AI协同经验引擎
  418个原子schema"贫瘠"就是因为这一步一直缺失，不是EA/Jasper两个项目本该
  用不同schema
- 新增 `agent.py --cluster-project <项目名>`（`skills/cluster_atoms.py`）：
  把"待聚类"原子匹配进既有枢纽或组建新枢纽，硬性限制单枢纽不超过15个原子，
  直接针对已发现的"财务流程与凭证"204原子巨型垃圾桶枢纽问题设计防线
- 修复 `com.jasper.ob-sync-agent.plist` 指向已废弃脚本路径的问题
- **`com.jasper.ob-daily-extract.plist` 仍未激活**（模板已就绪，需 Jasper
  确认真实API成本后手动 `launchctl load`）；聚类脚本已用合成数据验证但
  未跑过真实vault数据，建议先 `--dry-run` 验证

原游离目录 `05_Agent库/OB知识库同步巡检Agent/` 已清空移除，历史代码保留在
[`_retired_flat_structure/`](_retired_flat_structure/)。

## vault 现状（2026-07-17）

真实 vault（唯一真源，.git 和 GitHub 远程 `jasper211/obsidian-knowledge-base`
都在这个位置）位于 `~/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault/`。

iCloud 容器内的 `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/第二大脑Obsidian`
现在是**单向同步生成的镜像副本**（`tools/sync_to_icloud.py`，不含 `.git`），
供手机端 Obsidian 读取——手机端 Obsidian 的"iCloud 仓库"检测只认这个专属
容器，不认普通 Desktop 路径。**不要直接在 iCloud 镜像路径下编辑**，下次
同步会被 Desktop 真源覆盖（迁移前是反过来：vault 直接建在 iCloud 容器里，
2026-07-17 起改为 Desktop 唯一真源 + iCloud 单向镜像，原因是未来要把知识库
分享给其他人协同，iCloud 容器路径不方便共享，且 iCloud 同步延迟影响 OB
自己读写的实时性）。

已完成 vault 重置：只承载 `概念/`（30+ 篇结构化概念笔记）+ `MOC/`（导航）+
三个项目的知识原子，不再镜像三个项目的原始文件——原始文件留在 Desktop
原地，由概念笔记提炼能力本地读取、只读不改。

## 这是什么

不是单一循环，是三条独立触发、共享底层工具的能力线：

1. **巡检**（✅ 7项检查）——symlink 完整性、多终端 MCP 配置一致性、MCP
   Server 连通性、F 文件可读性、vault 统计、同步完整性抽查、**GitHub 同步
   状态**（工作区干净时 `git pull --ff-only`，确保本地内容跟 GitHub 一致，
   不干净则跳过并报警，不自动 stash/合并）。
2. **检索服务**（✅）——对 PTA 等业务 Agent 暴露薄客户端检索接口，底层是
   `obsidian-mcp-server` 的关键词+图谱+向量混合检索（本轮校准了 6 个真实
   bug，含 `tools.mjs` 里"7个工具收到组合对象却按 vaultIndex 直接访问"的
   连接层 bug，已通过真实 MCP 连接验证 8 个工具全部正常）。
3. **概念笔记提炼**（✅ 单文件 + 批量增量）——把三个项目的原始文档提炼成
   结构化知识原子，写回 vault：
   - `agent.py --extract <文件路径> --project <项目名>`：单文件手动提炼
   - `agent.py --extract-project <项目名> [--dry-run] [--max-files N]`：
     批量+增量，按 `tools/project_filters.py` 的价值分层筛选候选文件
     （EA 项目：00→03→08→01→02/规则分析（Jasper）优先级，跳过 04-07 代码
     资产层和归档内容；Rw/AI 项目：关键字黑名单排除），`tools/file_diff.py`
     做增量比对（只处理新增/变更），语义去重见 `tools/atom_embeddings.py`
     （复用 `obsidian-mcp-server` 的 embedding 能力，本机无 OPENAI_API_KEY
     时优雅退回精确匹配去重，不崩溃）
   - **对项目文件只读，不修改、不移动、不删除**——真实验证过（哈希比对+
     状态文件隔离核查）

详见 [需求定义.md](01_初始化项目_Initialize_Project/需求定义.md) 和
[流程设计.md](03_规划项目结构_Plan_Project_Structure/流程设计.md)。

## 快速开始

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --sync-check
python3 04_定义Agent_Define_Agent/agents/agent.py --retrieve "价值节点" --mode hybrid
python3 04_定义Agent_Define_Agent/agents/agent.py --extract-project "EA流程架构项目" --dry-run   # 免费，先看会处理哪些文件
python3 04_定义Agent_Define_Agent/agents/agent.py --extract-project "EA流程架构项目" --max-files 5  # 需DEEPSEEK_API_KEY，产生真实费用
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

## 目录结构（01-11 方法论，同 PTA）

```
OB/
├── 01_初始化项目_Initialize_Project/
│   └── 需求定义.md
├── 02_配置项目_Configure_Project/
│   └── settings.json
├── 03_规划项目结构_Plan_Project_Structure/
│   └── 流程设计.md
├── 04_定义Agent_Define_Agent/
│   └── agents/
│       ├── agent.py      入口：--sync-check / --retrieve / --extract / --extract-project
│       └── agent.yaml
├── 05_集成工具_Integrate_Tools/
│   └── tools/
│       ├── mcp_bridge.py        封装对 vault.mjs 的 node subprocess 调用（巡检用）
│       ├── retrieval_bridge.py   封装对 hybrid_search 的 node subprocess 调用（检索用）
│       ├── atom_embeddings.py    原子语义去重（复用 vector.mjs 的 getEmbeddings）
│       ├── agent_status.py      跨Agent状态注册表 + 统一健康报告生成
│       ├── llm_client.py         DeepSeek 调用封装（移植自PTA）
│       ├── file_diff.py          文件快照+增量diff（移植自PTA）
│       └── office_text.py        .docx/.xlsx 文本抽取（移植自PTA）
│       └── project_filters.py    三项目候选文件筛选规则（按价值分层优先级）
├── 06_开发技能_Develop_Skills/
│   └── skills/
│       ├── vault_sync_health.py         巡检能力线（含GitHub同步检查）
│       ├── knowledge_retrieval.py       检索服务能力线
│       ├── concept_note_extraction.py   单文件概念笔记提炼
│       └── batch_concept_extraction.py  批量+增量提炼编排
├── 07_接入记忆_Integrate_Memory/
│   └── memory/
│       └── workspace.py   per-project扫描快照持久化（OB_WORKSPACE_ROOT物理隔离）
├── 08_设计提示词_Design_Prompts/
│   └── prompts/
│       └── concept_note_extraction_system.md   定义"知识原子"的LLM系统提示词
├── 09_测试与调试_Test_and_Debug/
│   └── tests/
│       └── test_integration.py   14个测试场景/44项断言（对真实vault/真实项目跑，全过）
├── 10_部署与运行_Deploy_and_Run/
│   ├── com.jasper.ob-sync-agent.plist      迁移的模板，内容尚未更新指向新入口
│   └── com.jasper.ob-daily-extract.plist   批量提炼定时任务模板（不自动安装，需填真实API key）
├── 11_监控与优化_Monitor_and_Optimize/  暂空——对应"OB监控自己"，非"OB管理其他Agent状态"
└── _retired_flat_structure/          原游离目录迁移前的完整代码，标注"不再是入口"
```

## 当前状态（v0.4.0）

三条能力线全部实现+真实数据验证通过；vault 已完成物理迁移+内容重置；
概念笔记提炼补齐批量+增量编排。下一步：PTA↔OB 真正接线（PTA 的分析类
skill 调用 OB 的 `--retrieve` 取背景上下文，目前代码里还没有这条调用）。

## 关联文档

- [三大主Agent体系架构 v1.2](../三大主Agent体系架构_v1.2.md) 七节/九-2节
- [Agent搭建SOP v1.2](../Agent搭建SOP_v1.2.md)
