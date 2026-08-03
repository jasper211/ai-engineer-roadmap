# 10 部署与运行

## 1. 唯一前端

`frontend/` 是 VNW 正式 React 工作台。独立 HTML Demo 仅作为历史样式和人工对照，
不再发展为另一套生产系统。

```bash
cd 10_部署与运行_Deploy_and_Run/frontend
npm install
npm run dev
npm run build
npm run preview
```

## 2. 完整运行顺序

### A. 同步数据底座

```bash
python3 06_开发技能_Develop_Skills/skills/sync_data_foundation.py
```

数据写入：

- `07_接入记忆_Integrate_Memory/data_foundation/`；
- `10_部署与运行_Deploy_and_Run/frontend/public/data/`；
- 已配置的 EA 前端展示数据镜像。

### B. 重建全量 L3 快照

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py \
  --build-all-model-snapshots
```

首页 Gate 和待补状态以本次生成的 `model_snapshots/index.json` 为准。

### C. 运行合格 L3 的统一分析

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py \
  --prepare-l3-analysis L3-CODE
```

随后对产生的运行包执行 `--run-analysis-dir`。分析包只有通过证据和契约校验后才发布。

### D. 验证前端

```bash
cd 10_部署与运行_Deploy_and_Run/frontend
npm run build
npm run dev
```

## 3. 数据更新语义

- 源文件变化不会自动等于页面已经更新；
- 必须重新同步、重建快照，必要时重新运行分析并构建前端；
- 快照 Hash 变化后旧分析包应显示过期，不能继续伪装为当前分析；
- 第二阶段才建设自动变化检测和实时更新编排；
- V1 不执行数据库或知识库反向写回。

## 4. 页面运行语义

- 事实快照存在：只代表基础模型数据可展示；
- 正式分析包存在且 Hash 有效：才展示模型深度分析；
- reviewed Demo：仅作兼容兜底，必须明确标注；
- 拖动任务或优先级：只写浏览器 `localStorage`；
- “恢复建议位置”不修改任何源数据。

VNW 当前只提供显式运行，不安装常驻监听、定时模型调用或自动发布。

## 5. 阶段2·源头更新闭环

只检测并生成L3/面板影响清单，不更新当前系统：

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --check-source-updates
```

检测通过后安全应用新事实快照：

```bash
python3 04_定义Agent_Define_Agent/agents/agent.py --apply-source-updates
```

应用步骤固定为：全量只读候选重建 → 逐L3对比分析输入 → 识别变化范围与
受影响面板 → 归档发布前快照 → 更新事实层与前端。本命令不调用大模型；
被标记为 `REANALYSIS_REQUIRED/INPUT_CHANGED` 的L3须另行重跑统一分析。

报告位置：`.vnw_workspace/source_updates/latest.json`；历史快照位于
`.vnw_workspace/source_updates/history/`。

### 5.1 半自动扫描

`scripts/check-source-updates.sh` 是无写回、无模型调用的只读扫描入口。
macOS任务 `com.jasper.vnw-source-check` 每1800秒执行一次，结果写入：

- `.vnw_workspace/source_updates/latest_check.json`；
- `frontend/public/data/source_updates/pending.json`。

前端首页会显示最近扫描时间、待应用L3、需重跑分析数和阻断数。
发现变化后仍需人工执行 `--apply-source-updates`；定时任务永不自动应用。

安装源模板：`com.jasper.vnw-source-check.plist`。实际后台入口使用
`~/.vnw-agent/check-source-updates.sh`，避免launchd解析中文工程路径异常。
