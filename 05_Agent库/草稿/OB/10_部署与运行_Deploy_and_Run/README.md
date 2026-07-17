# 10_部署与运行 · OB

`com.jasper.ob-sync-agent.plist` 是从旧游离目录迁移过来的 launchd 模板，
**内容尚未更新**——目前仍指向旧的部署路径
（`~/Library/Application Support/jasper/ob-sync-agent/ob_sync_agent.py`），
不是这次迁移后的新入口 `04_定义Agent_Define_Agent/agents/agent.py --sync-check`。

**当前真实运行状态**：launchd 里实际加载的 `com.jasper.ob-sync-agent` 任务，
运行的是旧的部署副本，跟这次 01-11 骨架迁移的新代码是两回事——迁移新代码
本身不影响这个任务继续按原样每小时运行。

**切换步骤（待 Jasper 确认后执行，未做）**：
1. 把这份 plist 的 `ProgramArguments` 改成调用新的
   `agent.py --sync-check --output <path> --auto-fix --quiet`
2. `launchctl unload`/`load` 重新加载
3. 确认新任务真实跑过至少一次、报告输出符合预期后，再考虑删除旧部署副本
   （`~/Library/Application Support/jasper/ob-sync-agent/`）

在此之前，旧部署副本的 `VAULT_PATH` 已于 2026-07-15 单独修复（见迁移记录），
所以即使不切换，现有每小时巡检也是用正确路径在跑，不是阻塞项。

---

## `com.jasper.ob-daily-extract.plist`（2026-07-16 新增，未安装）

批量+增量概念笔记提炼的定时任务模板——每天凌晨 2 点依次对三个项目跑
`agent.py --extract-project <项目名> --max-files 20`（`--max-files 20` 是
单次成本上限，不是"每天只处理20个文件"的硬限制——增量机制下没处理完的
文件会累积到下一天继续按优先级处理）。

**这份 plist 只是模板，故意不自动安装**，原因：
1. 涉及真实 DeepSeek API 费用，是否开始每天自动跑需要 Jasper 自己拍板，
   不是我能替他决定的自动化开销。
2. 模板里的 `DEEPSEEK_API_KEY` 是占位符 `__FILL_IN_YOUR_OWN_KEY__`，需要
   Jasper 自己填入真实 key（不能由 AI 代填真实密钥）。

**安装步骤（Jasper 自己决定何时执行）**：
1. 编辑本文件，把 `__FILL_IN_YOUR_OWN_KEY__` 换成真实的 `DEEPSEEK_API_KEY`
2. `cp` 到 `~/Library/LaunchAgents/com.jasper.ob-daily-extract.plist`
3. `launchctl load ~/Library/LaunchAgents/com.jasper.ob-daily-extract.plist`
4. 建议先手动跑一次 `--dry-run` 确认候选文件列表符合预期，再让定时任务
   真正生效（`RunAtLoad` 故意设为 `false`，不会一装上就立刻跑一次真实
   提炼，只会等到下一个 `StartCalendarInterval` 触发时间）
