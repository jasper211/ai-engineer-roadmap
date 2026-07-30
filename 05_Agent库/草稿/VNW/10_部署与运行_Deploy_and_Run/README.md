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
