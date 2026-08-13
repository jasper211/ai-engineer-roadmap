# PTA 开源包交接说明

这份 PTA 可以作为同事各自在自己电脑上部署的基础包使用，包含 PTA 主引擎、每日巡检能力，以及本地任务驾驶舱。

## 适用范围

- 把 PTA 作为一个本地项目协同 Agent 使用。
- 把任务驾驶舱作为本地可视化入口使用。
- 在各自负责的项目目录上接入 `--daily-scan` 巡检。

## 推荐环境

- Python 3.10+
- Node.js 20+
- npm 10+

## 最短部署路径

```bash
cd PTA
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash 10_部署与运行_Deploy_and_Run/quick_start.sh "按顺序完成 P2-02, P2-03"
```

## 驾驶舱启动

后端：

```bash
python3 12_任务看板_Task_Dashboard/api/server.py --port 8787
```

前端开发模式：

```bash
cd 12_任务看板_Task_Dashboard/web
npm install
npm run dev
```

打开 [http://localhost:5173](http://localhost:5173)

前端生产模式：

```bash
cd 12_任务看板_Task_Dashboard/web
npm install
npm run build
cd ..
python3 api/server.py --port 8787
```

打开 [http://localhost:8787](http://localhost:8787)

## 必配项

1. 复制 `02_配置项目_Configure_Project/.env.example` 为 `.env`
2. 设置 `PTA_WORKSPACE_ROOT`
3. 如果要启用 LLM 巡检，再设置 `DEEPSEEK_API_KEY`
4. 修改 `02_配置项目_Configure_Project/daily_scan_projects.json`，填入自己电脑上的项目绝对路径

## 企业微信通知

如需启用，复制 `02_配置项目_Configure_Project/wecom_config.example.json` 为
`wecom_config.json`，填入自己团队的 webhook 和手机号映射。这个文件不要提交进仓库。

## 给同事分发时的建议

- 优先使用 `10_部署与运行_Deploy_and_Run/export_open_source_package.py` 导出干净版本
- 不要直接把你自己本机正在运行的工作区、日志和私有配置打包给别人
- 每位同事应维护自己的 `daily_scan_projects.json`、`.env` 和企业微信配置
