# 安装每日巡检定时任务（手动步骤，不会被自动执行）

> **多项目场景（EA/Rw/Jasper工作文档等同时巡检）请改装
> `com.jasper.pta-multi-daily-scan.plist`**，步骤类似（同样要填python3路径+API
> Key，但不需要填`--project-root`——项目清单维护在
> `02_配置项目_Configure_Project/daily_scan_projects.json` 里，加新项目改那份
> JSON 就够，不需要再装新 plist）。以下步骤以单项目版
> `com.jasper.pta-daily-scan.plist` 为例，多项目版把第2步的文件名换掉、
> 第3步跳过"目标项目路径"占位符即可，其余一致。

这份文档描述怎么把 `com.jasper.pta-daily-scan.plist` 装成 macOS 每天自动运行
的定时任务。**这些步骤需要你自己手动做一遍**——不会有任何脚本替你跑
`launchctl load` 或写入 `~/Library/LaunchAgents/`。

## 为什么要手动做，不能自动装

1. `--project-root` 要指向哪个项目，只有你知道。
2. `DEEPSEEK_API_KEY` 是真实密钥，绝对不能写进这个仓库里的模板文件（会被
   git 追踪、可能推到 `jasper211/ai-engineer-roadmap` 远程仓库）——只能填在
   你本地 `~/Library/LaunchAgents/` 里那份不受 git 管理的副本里。
3. 装定时任务、改开机自启动配置属于系统级改动，理应由你亲自确认。

## 步骤

### 1. 确认 python3 路径

```bash
which python3
```

如果不是 `/opt/homebrew/bin/python3`（比如 Intel Mac 常见 `/usr/local/bin/python3`），
下一步复制模板后要把 `ProgramArguments` 第一项改成你机器上的实际路径。

### 2. 复制模板到 LaunchAgents（这份副本不受 git 追踪）

```bash
cp "/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA/10_部署与运行_Deploy_and_Run/com.jasper.pta-daily-scan.plist" \
   ~/Library/LaunchAgents/com.jasper.pta-daily-scan.plist
```

### 3. 编辑这份复制出来的文件，填三处占位符

用文本编辑器打开 `~/Library/LaunchAgents/com.jasper.pta-daily-scan.plist`，替换：

- `REPLACE_WITH_PTA_AGENT_PY_ABSOLUTE_PATH` → `agent.py` 的绝对路径，即：
  ```
  /Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA/04_定义Agent_Define_Agent/agents/agent.py
  ```
- `REPLACE_WITH_TARGET_PROJECT_ABSOLUTE_PATH` → 你想每天巡检的那个项目的绝对路径
  （不是 PTA 自己的路径，是你想让 PTA 帮你盯着的那个项目）。
- `REPLACE_WITH_YOUR_REAL_KEY_ONLY_IN_THE_INSTALLED_COPY` → 你的真实
  `DEEPSEEK_API_KEY`（**只填在这份 `~/Library/LaunchAgents/` 里的副本，
  不要碰这个仓库里的模板文件**）。

如果第 1 步发现 python3 路径不是 `/opt/homebrew/bin/python3`，也在这份副本里改掉。

### 4. 加载

```bash
launchctl load ~/Library/LaunchAgents/com.jasper.pta-daily-scan.plist
```

### 5. 验证已加载

```bash
launchctl list | grep jasper.pta-daily-scan
```

能看到一行输出（第二列是最近一次退出码，`0` 或 `-` 都正常，还没跑过是 `-`）
就说明装上了。

### 6. （可选）手动触发一次，不等到明早8点

```bash
launchctl start com.jasper.pta-daily-scan
```

跑完看日志：

```bash
cat /tmp/pta-daily-scan.log
cat /tmp/pta-daily-scan.err
```

真正的巡检简报（结构化 JSON + 可读 Markdown）落在目标项目的专属工作区
`reports/daily-scan-<时间戳>.md`，不是这两个 `/tmp` 日志文件——那两个只是
launchd 捕获的标准输出/错误，用来排查"任务到底有没有跑、跑的时候报错了吗"。

## 卸载

```bash
launchctl unload ~/Library/LaunchAgents/com.jasper.pta-daily-scan.plist
rm ~/Library/LaunchAgents/com.jasper.pta-daily-scan.plist
```

## 修改运行时间

编辑 `~/Library/LaunchAgents/com.jasper.pta-daily-scan.plist` 里
`StartCalendarInterval` 的 `Hour`/`Minute`，改完要 unload 再 load 一遍才生效。
