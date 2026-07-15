# 11 · 监控与优化 Monitor and Optimize

> 对应方法论：`codex logs` / `codex eval` —— 监控运行状态，评估效果，持续优化 Agent 性能。

## 两类不同性质的内容，不要混为一谈

- **`PTA-MONITOR_自我监控.py`** —— 真正对应方法论第11步的本意：监控 **PTA 自己**
  被调用得怎么样（成功率、澄清触发率、按项目/时间的调用明细），数据直接读
  `07_接入记忆_Integrate_Memory/memory/workspace.py` 写的 `state.json`，不需要
  额外埋点。

  ```bash
  python3 11_监控与优化_Monitor_and_Optimize/PTA-MONITOR_自我监控.py                          # 汇总所有用过 PTA 的项目
  python3 11_监控与优化_Monitor_and_Optimize/PTA-MONITOR_自我监控.py --project-root /path      # 只看某个项目
  ```

- **其余脚本**是"PTA 帮你分析别的项目"的能力扩展，跟这一步的方法论定位是
  两回事。**迁移进度（分三批，按风险递增）**：
  - ✅ **批1已完成**：`PTA-DASH_项目仪表盘.py` → `06_开发技能_Develop_Skills/skills/project_dashboard.py`
    （`agent.py --dashboard --project-root <path> --person <name>`）；
    `PTA-EXT_外部项目分析器.py` → `05_集成工具_Integrate_Tools/tools/dir_scan.py`
    （`agent.py --dir-scan --project-root <path>`）。原脚本移入 `_retired_flat_structure/`，
    迁移时顺带修复了一个隐藏 bug：原 EXT 只排除隐藏目录，`node_modules` 这类
    非隐藏但该跳过的目录会被误统计进报告。
  - ✅ **批2已完成**：`PTA-DISCOVER_文档任务发现器.py` → `06_开发技能_Develop_Skills/skills/document_task_discovery.py`
    （`agent.py --discover --scan --project-root <path>`，需要 `DEEPSEEK_API_KEY`）；
    `PTA-SCAN_智能项目扫描器_v2.py` → `06_开发技能_Develop_Skills/skills/rule_based_task_scan.py`
    （`agent.py --rule-scan --project-root <path>`，零 LLM 调用）。原脚本移入
    `_retired_flat_structure/`。迁移时的两处修复：① SCAN 真正切到了 sha256——
    改用 `tools/file_diff.py` 的 `snapshot_dir`/`diff_snapshots`（此前自己维护
    一套 md5 哈希/快照逻辑，旧 `scan_snapshot.json` 快照因此直接失效，首次运行
    会重扫）；② 删除了 SCAN 的 `--schedule` 内部忙等循环——那个模式下会把报告
    直接写进目标项目自己的目录，违反隔离原则，且跟本项目已确立的"外部调度器
    （launchd）驱动单次调用"架构不一致（daily-scan 就是这个模式），如需定时跑
    参照 `10_部署与运行/` 的 launchd 方式。DISCOVER 迁移时顺带修了一个新发现的
    bug：内容去重跳过的重复文件此前没有被记进增量状态，下次运行会被重新当
    候选文件排队。
  - ✅ **批3已完成**：`PTA-INTEL_智能项目分析器_v3.py` / `PTA-INTEL-RW_智能项目分析器_v3.py`
    → `06_开发技能_Develop_Skills/skills/project_intelligence.py`
    （`agent.py --intel --intel-mode {analyze,query,cross} --project-root <path>`）。
    深入对比后发现这两个脚本表面同构（都是 analyze/query/cross 三模式），但
    数据模型完全不同——通用版猜 Markdown/CSV 结构（`TaskItem`），Rw 专用版
    精确读固定台账 CSV 的固定列名（`TrackItem`，字段语义如 `source_work_id`/
    `today_action`/`escalation` 完全对不上通用版）。**这次"合并"合并的是入口层，
    不是数据模型**：两套解析器/分析器/CrossDocumentAnalyzer 原样保留（改名
    `Generic*`/`Rw*` 避免类名冲突），新增 `ProjectIntelligence` 统一入口，
    自动探测目标项目目录下有没有 `RwProjectParser.TRACKING_FILES` 列的那几份
    固定台账 CSV 文件名来选后端。原脚本移入 `_retired_flat_structure/`。

    **明确删除的部分**（不是迁移遗漏）：原 `PTA-INTEL`（不是 INTEL-RW，两边本就
    不对称）内嵌了一套 `agent_status` 跨 Agent 状态上报，会把分析结果写进 PTA
    工作区和目标项目之外的第三方路径（Jasper 全局的"Agent健康报告.md"/
    "Agent运行仪表盘.md"）。这违反了本项目已确立的 workspace 隔离原则，迁移时
    直接不保留这部分。

    **顺带修的一个真实 bug**：迁移到共享的 `tools.file_diff.read_content_truncated`
    时发现，原 PTA-SCAN/PTA-INTEL-RW 都在编码候选列表里显式试过 `utf-8-sig`
    处理 Excel 导出 CSV 常见的 BOM 问题，但批2迁移 SCAN 时改用的共享函数没有
    覆盖这一点——是一个当时没测出来的回归。这次统一在 `read_content_truncated`
    里做了 BOM 剥离修复，批2的 `rule_based_task_scan.py` 也一并受益。
