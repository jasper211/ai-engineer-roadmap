# Agent搭建Pipeline差距矩阵 · 优化设计 + 每周检测机制规格 v1.0

> 定位：给`_RPT__AI协同建造者_Agent架构目标差距与实现路径_Jasper_v5_0.html`里"04·Agent搭建Pipeline差距矩阵"配一套可自动化的检测机制。本文档是设计规格，交付对象是执行实现的Agent/工具（文中称"work"），不是矩阵本身的内容重写。
> 前提待确认：本设计假设VNW/AIT按v5.0口径并行推进（该文档已明确"不再等待VNW全量完成再启动AIT"）。若Jasper未确认覆盖此前"VNW/AIT不开新战线"的默认原则，第4阶段（AIT三轨道建造）的检测项按此假设设计，需相应调整。
> 关联文件：`_RPT__AI协同建造者_Agent架构目标差距与实现路径_Jasper_v5_0.html`（矩阵原件）· `三大主Agent体系架构_v1.3.md` · `Agent搭建SOP_v1.2.md` · `D-20260709-001_Agent验证方法论与方法论转正Agent.md` · `Agent验证标准清单_v1.0.md`

---

## 一、为什么要做这个机制

矩阵目前是**人工手写的快照**（截至2026-07-20），本质上跟之前架构文档"PTA-S04需要--execute确认"那次错误是同一类风险：写下的状态会跟实际代码/配置状态逐渐脱节，而且没人会主动发现，直到下次要汇报或者真的出了问题。

目标不是让机器"评判进展好不好"（那是主观判断，D-20260709-001明确不让LLM做这个），而是让机器**把矩阵里能查证的部分，跟当前代码/配置的真实状态做一次比对，把"声明"和"事实"的差异摆出来**。人（Jasper/Mark）来决定这个差异要不要改矩阵、改多少分。

---

## 二、矩阵结构优化：从"人工快照"到"可检测快照"

现有矩阵每个格子是一句判断+一句补充说明（如"🟡 业务Agent零调用 / 上下文效果未验证"），人读起来清楚，但机器没法自动核实。优化方向：**给每个格子增加一个"证据锚点"字段**，指向一个可查证的具体事实来源，检测脚本只做"这个锚点现在的值是什么"这一件事，不做判断。

### 2.1 字段设计（每个矩阵格子，即每个"阶段×维度"组合，新增以下元数据）

| 字段 | 说明 | 示例 |
|---|---|---|
| `stage_id` | 沿用矩阵原有7阶段编号 | `2`（VNW发现→SOP） |
| `dimension` | BUILD / GOVERN / VERIFY / OWN | `VERIFY` |
| `claim` | 矩阵里当前写的判断（人工，不变） | "多L4/多域未全测" |
| `evidence_type` | `auto`（脚本可查）/ `manual`（只能人工判断，脚本只读不判断） | `auto` |
| `evidence_source` | 具体查证方法（文件路径/命令/字段名） | `python3 05_Agent库/草稿/VNW/09_测试与调试_Test_and_Debug/tests/test_integration.py --list-cases` |
| `last_verified` | 上次脚本真实跑过这条检测的时间 | `2026-07-20` |
| `drift_flag` | 本次检测值 vs 矩阵claim 是否出现不一致 | `true` / `false` |

### 2.2 每个维度的证据类型划分（可自动 vs 只能人工）

| 维度 | 能不能自动检测 | 说明 |
|---|---|---|
| **BUILD** | 大部分可自动 | 代码/文件存在性、skills/tools清单、git commit记录 |
| **GOVERN** | 部分可自动 | 规则/标准文档是否存在可自动查；"谁来负责"这类归属声明只能读取当前写的是谁，不能判断对不对 |
| **VERIFY** | 大部分可自动 | 测试脚本能不能跑、跑完exit code、用例数，是最容易自动化的一类 |
| **OWN** | 基本不能自动 | archive_gate.mark_confirmed 这类"是否被Mark确认"是人工事实，脚本只能读取当前值、记录变化，不能替Mark判断 |

这条划分本身就是D-20260709-001原则1（确定性检查优先）的直接应用——**能查证据的就查证据，查不到证据的就老实标"待人工"，不让AI去猜"这个阶段现在算不算OWN到位了"**。

---

## 三、七个阶段的具体检测项设计

按矩阵现有7个阶段，逐条给出BUILD/VERIFY两个最容易自动化的维度的具体检测方法（GOVERN/OWN大部分是manual，列出但不展开脚本细节）。

### 阶段1 · OB背景上下文
- BUILD(auto)：检查OB `04_定义Agent_Define_Agent/agents/agent.py` 里 `skills/knowledge_retrieval.py` 是否存在，`vault`路径下概念笔记原子数量（对应矩阵写的"6963原子"这类具体数字，用`find`统计笔记文件数，跟矩阵声明的数字比对，数字对不上就是drift）
- VERIFY(auto)：PTA/VNW/AIT代码里 grep 是否出现对`knowledge_retrieval`或`get_context`的真实调用（区分"声明依赖"和"代码依赖"，矩阵已经写了"业务Agent零调用"，这条检测就是验证这句话到现在还成不成立）
- GOVERN/OWN(manual)：OB后续建设权责在另一项目，本项目只读

### 阶段2 · VNW发现→SOP
- BUILD(auto)：读`VNW/02_配置项目_Configure_Project/settings.json`的`skills`数组，跟矩阵声明的"5段流程完成几段"比对（目前skills只有3项，对应完成前两段的说法）
- VERIFY(auto)：跑`test_integration.py`（如有），记录exit code + 用例数，跟上次记录比较是否退步
- GOVERN(auto可部分)：检查`settings.json.migration_note`字段是否有更新（有更新说明本周有实质进展记录）

### 阶段3 · VNW→AIT移交
- BUILD(auto)：grep VNW/AIT代码目录，看有没有出现"SOP标记"相关的字段/函数名（矩阵已写"无代码"，这条就是持续确认这句话没有变化——变化了就是重要信号，应该被检测出来主动提示，而不是要等人手动发现）
- VERIFY(auto)：同上，检测是否新增了任何`test_*handoff*`或类似命名的测试文件

### 阶段4 · AIT三轨道建造
- BUILD(auto)：`AIT/config.json`的`version`字段+`skills_used`数组变化
- VERIFY(auto)：是否有新增测试文件；L3-COM案例文档（`02_过程成果-工作产出/.../L3-COM.../`）的文件mtime有没有变化（判断"唯一真实案例"是否还在更新）

### 阶段5 · PTA协同执行
- BUILD/VERIFY(auto，本阶段是全矩阵里唯一有生产自动化的，最值得做实时检测)：
  - 运行`test_pta_integration.sh`/`test_integration.py`，记录用例数+通过数
  - 检查launchd任务（`daily_sensing`）最近一次真实运行的日志时间戳，判断"生产自动化"这句话是否仍然成立（这是矩阵里"运行"两个字最该被自动验证的地方，如果daily_sensing哪天停了，这应该是全矩阵里最先被发现的drift）
- OWN(manual)：`archive_gate.mark_confirmed`字段值——脚本读取并记录，不判断

### 阶段6 · 方法论双循环
- BUILD(auto)：检查`05_Agent库/草稿/`下有没有出现"方法论转正Agent"的实际目录结构（目前应为不存在，持续确认）
- GOVERN(auto可部分)：`Agent验证标准清单_v1.0.md`的最后更新时间

### 阶段7 · 部门接管复制
- 这一阶段目前几乎全部是组织性事实（有没有部门Owner、AIT有没有真实交付包），BUILD维度勉强可以查"AIT/`SOP_manual.md`这类交付物文件是否存在"，其余维度基本manual

---

## 四、输出产物设计

**不直接改写矩阵原文档（HTML报告是对外汇报用的正式版本，脚本不应该自动改它）**，而是每周产出一份独立的检测报告，供Jasper人工比对后决定要不要更新正式矩阵：

```
05_Agent库/草稿/_pipeline_health/
  └── 检测记录_2026-07-25.md   # 每周一份，累加式保留历史
```

报告内容结构：

```markdown
# Pipeline差距矩阵 · 周检测 2026-07-25

## 本周与矩阵声明不一致的地方（drift_flag=true）
| 阶段 | 维度 | 矩阵声明 | 本周实测 | 建议 |
|---|---|---|---|---|
| 5 PTA协同执行 | VERIFY | 24项集成测试全过 | 实测22项通过2项失败 | 需要人工核实，可能是环境问题或真实回归 |

## 本周无变化（跟上次检测一致，未发现drift）
（列出，证明"没问题"也是有检测在跑，不是没做）

## 本周无法检测（evidence_type=manual）
（如实列出，不假装做了检测）
```

---

## 五、调度与通知设计

- **技术选型**：复用PTA已验证过的launchd方案（`10_部署与运行/`下已有plist范例），不重新选型
- **频率**：每周一次，建议排在周五（跟章程里"能力整改看板"周五复盘节奏对齐），检测报告产出后你周五复盘时直接读这份报告，不用现场现查
- **通知**：复用`PTA/05_集成工具_Integrate_Tools/tools/wecom_notify.py`，默认关闭，只有出现`drift_flag=true`的项才推送（没有drift就不用打扰你），配置方式跟现有企业微信通知一致（不进git、不进任何会被--daily-scan扫描的目录）
- **只读原则**：这个检测脚本只允许读文件/跑测试/查git log，不允许修改任何Agent目录下的文件，只能写自己的`_pipeline_health/`报告目录——跟VNW"不写源项目、只写专属workspace"是同一条隔离纪律，避免检测工具本身变成新的误操作风险源

---

## 六、归属：PTA提供引擎，检测项外置成数据（2026-07-21更新，Jasper拍板）

不做独立脚本，也不等方法论转正Agent。理由：调度（launchd）、通知（wecom_notify.py）、文件diff（file_diff.py）这套基础设施PTA已经生产验证过，重新搭是纯重复实现，违反迁移方法论"该复用的不要重新造"这条原则。

但PTA自己的设计原则是"不硬编码项目特定逻辑"（`pta_tasks.json`外置正是为此）——这28个检测项是本项目特有的判断，不能直接写进PTA源码，否则PTA不再是通用引擎。所以采用跟`pta_tasks.json`同样的外置模式：

- **PTA新增能力**：`--pipeline-check`，跟`--daily-scan`平级、不是它的子功能——本检测全部是确定性检查（文件存在性/测试exit code/字段读取），不需要`daily_sensing`那套LLM关系分析（`tools/llm_client.py`），混进`daily_sensing`反而降低确定性、且平白产生DeepSeek调用费用
- **检测项定义外置**：`05_Agent库/草稿/_pipeline_health/checks.json`（结构类比`pta_tasks.json`：`{stage_id, dimension, claim, evidence_type, evidence_source}`的列表），PTA的`--pipeline-check`读这份文件、逐条查证据、出报告、drift触发`wecom_notify`
- **独立调度**：新增一条launchd定时任务，每周（不是每天），跟`daily_sensing`现有的每日plist是两条独立条目，不共用触发节奏
- **PTA代码侧改动范围**：新增`skills/pipeline_health.py`（读取checks.json、跑检测、写报告，纯Python+文件操作，不依赖LLM）+ `agents/agent.py`新增`--pipeline-check`分支，这是PTA的功能扩展，不是新Agent，走的是PTA现有版本迭代节奏（类比v2.3.0新增daily_sensing的方式）

---

## 七、交给work的实现任务清单

1. 建`05_Agent库/草稿/_pipeline_health/`目录（新增，不动现有任何文件），写入`checks.json`（本文档第三节列出的每个`evidence_type=auto`检测项，按`{stage_id, dimension, claim, evidence_type, evidence_source}`结构）
2. PTA内新增`skills/pipeline_health.py`：读取`checks.json`（复用`tools/task_knowledge.py`同款的"显式路径 > project_root下 > 默认"加载优先级，不用重新发明加载逻辑），逐条查证据，输出第四节格式的周报到`_pipeline_health/检测记录_YYYY-MM-DD.md`
3. `agents/agent.py`新增`--pipeline-check [--project-root PATH]`分支，drift触发时调用已有的`tools/wecom_notify.py`（默认关闭，同现有约定）
4. 复用（不重写）`tools/file_diff.py`、`tools/git_ops.py`
5. 参照PTA `10_部署与运行/`下的launchd plist范例，**新增一条独立的每周五触发定时任务**（不是改`daily_sensing`现有的每日plist）
6. 第一次运行必须`--dry-run`，人工核对输出格式和检测项跑得通再正式启用（跟PTA daily_sensing v2.3.0上线时的做法一致）
7. 更新PTA `settings.json`的`migration_note`字段，记一笔"vX.X.X：新增`--pipeline-check`，检测项外置`_pipeline_health/checks.json`，跟`daily_sensing`共用工具层但独立调度"——延续PTA一贯的版本变更记录习惯
8. 按Agent搭建SOP第6步补执行记录，说明依据本规格文档

---

> 版本：v1.0 | 生成时间：2026-07-21
> 待Jasper确认后交work执行；不确认前不建议直接开工
