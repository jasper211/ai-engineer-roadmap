# PTA 任务看板

daily_sensing 建议任务的可视化界面——两条关闭路径里，"文件回执自动识别"那条
daily_sensing 自己已经处理好了（见`skills/daily_sensing.py`），这里补的是另
一条："没有文件回执的任务，在界面上勾选关闭/继续跟踪"。

## 组成

- `api/`：纯标准库`http.server`写的本地HTTP服务，不引入FastAPI/Flask（跟本
  项目一贯的依赖习惯一致，见`server.py`顶部注释）。`views.py`是胶水层，业务
  逻辑全部复用`skills.daily_sensing`/`skills.pipeline_health`/`memory.workspace`
  已有的函数，不重新实现。
- `web/`：独立的Vite+React+TS+Tailwind项目，跟`规则前端设计/.../app_v2`
  （VNW自己的前端）是兄弟关系，只借用了它的Tailwind主题token和
  StatusBadge/PriorityBadge组件写法，不是同一个app。

## 运行方式

**开发**（前后端各自跑，改代码即时生效）：
```bash
# 终端1
python3 api/server.py --port 8787
# 终端2
cd web && npm install && npm run dev
```
打开 http://localhost:5173

**日常使用**（一个进程，Jasper自己电脑上长期开着用）：
```bash
cd web && npm run build   # 只在改了前端代码后需要重新build
cd .. && python3 api/server.py --port 8787
```
打开 http://localhost:8787——同一个Python进程既服务API也服务这份build出来的
静态前端。

## 范围

只做PTA自己的任务管理（任务看板）+ 运行状态查看（daily-scan/pipeline-check
最近运行时间）。VNW/AIT/方法论转正Agent/OB四块明确不在这次范围内——各自
现状没有变化，硬做只会是假面板，见`三大主Agent体系架构`文档的优先级排序。
