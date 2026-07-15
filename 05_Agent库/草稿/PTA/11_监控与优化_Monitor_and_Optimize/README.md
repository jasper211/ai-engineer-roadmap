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
  - ⏳ **批3待做**：`PTA-INTEL_智能项目分析器_v3.py` / `PTA-INTEL-RW_智能项目分析器_v3.py`
    ——这两个是同一能力的两份高度重复实现（query 分派/CrossDocumentAnalyzer/main
    流程高度同构，只有解析层真正不同：通用 MD/CSV 猜测 vs Rw 专用 CSV 精确
    列名），确认要合并成一个技能，通过自动探测项目目录下有没有 Rw 特征 CSV
    来选解析器。
