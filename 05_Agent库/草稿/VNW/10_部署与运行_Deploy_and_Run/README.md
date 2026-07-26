# 部署与运行

## 前端唯一入口

`frontend/` 是 VNW 的正式治理工作台，也是原“规则前端设计”目录合并后的唯一有效版本。旧 `app`、`app_v2_base`、构建产物和重复数据副本不再保留。

```bash
cd frontend
npm install
npm run dev
npm run build
```

前端运行时读取 `frontend/public/data/`。数据由
`06_开发技能_Develop_Skills/skills/sync_data_foundation.py` 从业务源重建，同时同步到：

- `07_接入记忆_Integrate_Memory/data_foundation/`：VNW 权威数据底座
- `frontend/public/data/`：前端运行副本
- EA 项目的“前端展示数据底座”：业务工作区镜像

VNW 主循环仍只提供显式单次运行，尚未安装常驻监听或定时任务。
