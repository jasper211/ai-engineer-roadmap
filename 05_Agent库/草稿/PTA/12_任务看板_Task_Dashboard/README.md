# PTA 任务驾驶舱

daily_sensing 建议任务的人工决策与运行控制界面。v2.17.0 起，首页从三桶只读
看板升级为“今日指挥中心”：候选任务可接受、转交、合并或忽略，接受前要求
补齐负责人和验收标准。当前阶段只写回决策，不触发命令、Git 或外部通知。

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

## 当前范围

- 今日指挥中心：待决策、执行准备、搁置事项与风险指标。
- 候选任务决策：接受、转交、合并、忽略；编辑标题、优先级、Owner、期限、
  验收标准和备注。
- 项目态势、Agent监控、Pipeline漂移、执行记录、OB检索和巡检项目管理。
- 已开放执行计划预览、dry-run 与批准记录；尚未开放页面直接真实执行 PTA。

## 执行准备（v2.18.0）

已接受任务可调用 PTA 原生执行编排器生成步骤计划；每步显示工具、命令和确定性
风险标签。计划需先完成无副作用 dry-run，全部通过后才能记录批准。批准状态明确
标记为“尚未真实执行”，并保留 `requires_explicit_execute=true` 二次授权门。
