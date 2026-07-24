# PTA 个人三项目指挥中心

首页以三个项目最新成功巡检之间的完整文件变化为SSOT：EA流程架构项目是核心
主视图，Jasper工作文档是AI技术试验田，Rw权益项目是真实案例观察窗口。任务、
执行建议和跨项目关系都是文件事实的下游分析，不再反客为主。

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

- 指挥中心：完整展示新增、修改、删除文件；关键变化默认展开，普通变化按需展开。
- 内容级事实：修改前后摘录、原始diff、删除前最后内容；旧报告缺失数据不伪造。
- 项目角色：EA主视图，Jasper/Rw辅视图；无变化与巡检失败明确区分。
- 关系分析：项目内变化关系 + 每日巡检结束后一次跨项目深度分析。
- 与我相关：按 Jasper 已确认的个人边界筛选。EA 只保留人机协同流程/SOP、
  信号与规则、端到端任务 Agent 化；Jasper 只有明确应用到 EA 的变化进入
  行动区，潜在能力进入待评估；Rw 暂不做个人聚焦。
- Agent监控、Pipeline漂移、执行记录、OB检索和巡检项目管理。
- 已开放执行计划预览、dry-run 与批准记录；尚未开放页面直接真实执行 PTA。

## 执行准备（v2.18.0）

已接受任务可调用 PTA 原生执行编排器生成步骤计划；每步显示工具、命令和确定性
风险标签。计划需先完成无副作用 dry-run，全部通过后才能记录批准。批准状态明确
标记为“尚未真实执行”，并保留 `requires_explicit_execute=true` 二次授权门。

## 文件SSOT与跨项目分析（v2.19.0）

`daily_sensing` 对每个变化文件确定性保存 `change_type/before_excerpt/
after_excerpt/diff_text`。即使LLM遗漏普通文件，本地事实层也会补齐，保证文件
清单完整。三个项目各自巡检后，`cross_project_sensing`只消费已落盘事实，额外
分析 Jasper技术→EA、EA方法→Rw、Rw事实→EA/Jasper 等关系方向，结果持久化；
页面刷新只读结果，不触发新的LLM调用。
