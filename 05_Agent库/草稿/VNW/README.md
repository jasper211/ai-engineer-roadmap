# VNW · 价值节点驱动工作流 Agent

> 工程基线：v0.6.0 · 2026-07-30  
> 阶段状态：第一阶段主体完成，正在进行合格 L3 的批量分析、质量验收与封版。

VNW 已形成“全量权威数据 → 可追溯事实快照 → Gate M/E/A → 统一分析包 →
固定面板 A–F → 本地工作坊”的只读闭环。所有 L3 使用同一输入优先级、分析契约和
展示逻辑；输入不足时显示缺口，不用模板文字补造分析。

## 01–11 工程说明书

| 层 | 职责 |
|---|---|
| 01 初始化项目 | 产品目标、三阶段范围、成功标准 |
| 02 配置项目 | 模型、本地运行和只读连接配置 |
| 03 规划项目结构 | Gate、统一页面模板、系统路线 |
| 04 定义 Agent | Agent 职责、边界和命令入口 |
| 05 集成工具 | 数据库、OB、证据、指纹、快照和模型适配 |
| 06 开发技能 | 快照、蓝图、同步和统一分析执行器 |
| 07 接入记忆 | 快照、运行包、分析包和审计产物 |
| 08 设计提示词 | 全 L3 共用分析模型和输出契约 |
| 09 测试与调试 | 自动化测试与跨域回归样本 |
| 10 部署与运行 | 完整生产链和 React 前端 |
| 11 监控与优化 | 数据、分析和运行质量监控 |

## 常用命令

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --status
python3 04_定义Agent_Define_Agent/agents/agent.py --watch-dir /path/to/value-node-list --domain PAY
python3 04_定义Agent_Define_Agent/agents/agent.py --build-model-snapshots
python3 04_定义Agent_Define_Agent/agents/agent.py --build-all-model-snapshots
python3 04_定义Agent_Define_Agent/agents/agent.py --prepare-l3-analysis L3-COM
python3 04_定义Agent_Define_Agent/agents/agent.py --run-analysis-dir <运行包目录>
python3 -m unittest discover -s 09_测试与调试_Test_and_Debug/tests -v
```

默认不会修改被监控目录。首次发现文件会处理；内容未变化会跳过；`--force` 可强制重跑；`--domain ALL` 处理全域。

每个字段携带来源对象、键、字段、证据等级和稳定证据 ID；数据源还可记录数据库
记录键、CSV/XLSX 行号和 Markdown 行号。只有蓝图索引但尚未解析正文时，步骤、
箭头和决策点保持为空。V1 不写回数据库或知识库，工作坊判断保存在浏览器本地且
不得伪装成权威事实。

蓝图解析目前支持两类真实结构：`步骤N：`代码块和 `[Step N]` 主干步骤，并读取 `【判断节点N】` 或 `§4 判断节点/QN` 的显式分支。每个步骤与判断保留蓝图文件、版本、文件 hash 和原文行号；相邻顺序边只能由显式步骤编号派生。数据库与蓝图结构不一致时显示差异，不自动补画。

全量模式对固定权威表各执行一次只读查询，在内存中按 L3 分组后批量构建，避免逐个
L3 重复连接数据库。当前快照集合为 67 个 L3；具体 Gate 数量以每次重建生成的
`model_snapshots/index.json` 为准，不在说明书中固化可能过期的统计值。

2026-07-29 修正两处此前误判并接入正式 pipeline（非一次性脚本）：
- 蓝图覆盖判定改为 `load_blueprint_index_from_dir()` 直接扫描 EA 项目 L3 流程库实际文件，取代手工维护、已确认过期的 `L3蓝图覆盖清单_v1.0.csv`（67 个里曾有 18 个漏记，16 个是索引漏收而非文件缺失）。
- D1-D6 六维评分改为 DB 值优先、DB 为空时用 `L4两阶段复核_全量368条_合并版_v1.0.csv`（368 条 L4 全覆盖）补充，补充值以 `EvidenceClass.SUPPLEMENTAL` 单独标注可溯源，不与 `dim_process` 的 AUTHORITATIVE 证据混同。此前"仅 6 个 L3 做过 D1-D6 打分"是数据库同步滞后造成的误判，打分工作本身已对 368 条全覆盖。
- 两项修正使 Gate A 通过数从 2（L3-CPM、L3-EO）升至 30；剩余 37 个未通过 Gate A 的 L3 卡在价值节点覆盖/熔断状态（A-003/A-004），与 D1-D6 无关——`dim_vn` 93 个价值节点仅覆盖 366 条 L4 中的 136 条，是价值节点体系本身覆盖稀疏，不是本次修正范围。

## 当前分析包状态

统一分析执行链已经走通，COM、IRI、IBRD、HRA、HRM 等样本用于跨结构、跨业务域
校准。其他合格 L3 仍需按同一模型分批运行、证据抽检并发布。存在基础快照不等于已经
形成 COM 深度的模型分析。

## 统一前端与数据路径

- 正式前端：`10_部署与运行_Deploy_and_Run/frontend/`
- VNW 权威数据底座：`07_接入记忆_Integrate_Memory/data_foundation/`
- 数据同步技能：`06_开发技能_Develop_Skills/skills/sync_data_foundation.py`
- 规则识别方法论参考：`03_规划项目结构_Plan_Project_Structure/references/`

原独立目录“规则前端设计”已合并进 VNW，不再作为运行入口。

## 数据底座 → 前端展示

`06_开发技能_Develop_Skills/skills/sync_data_foundation.py` 是目前唯一真正处理业务数据的脚本：一键全量重建各数据表，写入两处物理数据底座副本，并额外导出 JSON 到前端 `10_部署与运行_Deploy_and_Run/frontend/public/data/`。

前端（React+Vite+TS）读取同步技能导出的 JSON。数据更新流程固定为：源头更新 → 重跑 `sync_data_foundation.py` → 前端本地 `npm run dev` 立即生效；线上发布仍需单独执行部署动作，不由数据同步脚本自动触发。

完整模型链路为：

```text
源数据同步 → 快照重建 → Gate判断 → 分析包准备 → 模型运行/导入
→ 输出校验与发布 → 前端构建/加载
```

**权威数据源分级（2026-07-26 拍板，重要）**：公司数据仓库（PostgreSQL，`process_analytics` schema）是标准化的权威数据源，跟 01-05 层文件材料（本项目/OB 知识库背后的原始素材）冲突时以数据仓库为准；数据仓库没有的字段/表，才用文件材料补充。连接参数在本地未提交文件 `06_开发技能_Develop_Skills/skills/db_config_local.py` 里，不进版本库。T1/T12/T20/T25/T26 及新增 T29/T30 已切换为数据仓库权威源，详见 [执行记录.md](./执行记录.md) 2026-07-26 各条记录。
