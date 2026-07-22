#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务看板 API 的胶水层——纯粹把已有的 skills/memory 函数组织成前端要的形状，
不重新实现任何业务逻辑（分桶/搁置天数计算在 skills.daily_sensing 里，
状态写回在 memory.workspace 里，检测摘要在 skills.pipeline_health 里）。

sys.path 引导方式照抄 agents/agent.py 的写法——本文件在 12_任务看板_
Task_Dashboard/api/ 下，比 agent.py 深一层，PTA_DIR 的推导多一层 parent。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List

API_DIR = Path(__file__).resolve().parent                    # 12_任务看板_Task_Dashboard/api/
DASHBOARD_DIR = API_DIR.parent                                 # 12_任务看板_Task_Dashboard/
PTA_DIR = DASHBOARD_DIR.parent                                  # PTA 项目根目录

for _pkg_dir in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(PTA_DIR / _pkg_dir))

from memory import workspace as ws
from skills.daily_sensing import list_tasks_from_state, latest_report_summary
from skills.pipeline_health import summarize_latest_report, drift_detail_from_latest_report, REPORT_DIR_RELATIVE
from skills.agent_status import detect_all_agent_statuses
from tools.ob_bridge import get_background

DAILY_SCAN_PROJECTS_PATH = PTA_DIR / "02_配置项目_Configure_Project" / "daily_scan_projects.json"
# HOME_PROJECT_ROOT 的推导跟 agent.py 完全一致（PTA -> 草稿 -> 05_Agent库 -> 项目根目录），
# pipeline-check 的报告目录相对这个根，不是相对 PTA_DIR。
HOME_PROJECT_ROOT = PTA_DIR.parent.parent.parent


def _load_watched_projects() -> List[dict]:
    if not DAILY_SCAN_PROJECTS_PATH.exists():
        return []
    try:
        data = json.loads(DAILY_SCAN_PROJECTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data.get("projects", [])


def _resolve_workspace_for_project(project_name: str) -> "tuple[Path, Path] | None":
    """按 name 找 daily_scan_projects.json 里对应的 project_root，再解析出它的
    专属工作区。找不到就返回 None——调用方（dismiss接口）据此返回404，而不是
    静默地对一个不存在的项目瞎写文件。"""
    for p in _load_watched_projects():
        if p.get("name") == project_name:
            root = Path(p["project_root"])
            return root, ws.get_project_workspace(root)
    return None


def list_projects() -> List[dict]:
    """每个已配置项目的基础信息 + 最近一次 daily-scan 时间（cmd_daily_scan
    早就写进 state.json 的 context.last_daily_scan，这里只读，不新增字段）。"""
    result = []
    for p in _load_watched_projects():
        name = p.get("name", "")
        root = Path(p.get("project_root", ""))
        entry = {"name": name, "project_root": str(root), "exists": root.exists(),
                  "last_daily_scan": None}
        if root.exists():
            workspace = ws.get_project_workspace(root)
            state = ws.load_state(workspace)
            entry["last_daily_scan"] = state.get("context", {}).get("last_daily_scan")
        result.append(entry)
    return result


def aggregate_tasks(project_filter: str = "all") -> dict:
    """跨项目聚合 list_tasks_from_state() 的结果——project_filter="all" 时
    合并所有已配置项目，否则只看指定项目（按 name 精确匹配）。"""
    projects = _load_watched_projects()
    if project_filter != "all":
        projects = [p for p in projects if p.get("name") == project_filter]

    merged = {"new": [], "aging": [], "resolved_recent": []}
    for p in projects:
        name = p.get("name", "")
        root = Path(p.get("project_root", ""))
        if not root.exists():
            continue
        workspace = ws.get_project_workspace(root)
        state = ws.load_daily_sensing_state(workspace)
        bucketed = list_tasks_from_state(state, project_name=name)
        for key in merged:
            merged[key].extend(bucketed[key])

    merged["aging"].sort(key=lambda x: x["days_pending"], reverse=True)
    merged["resolved_recent"].sort(key=lambda x: x["status_updated_at"], reverse=True)
    return merged


def dismiss_task(project_name: str, task_id: str, status: str) -> dict:
    """前端"关闭/继续跟踪"勾选的落地点——status 只应该是 "dismissed"（关闭）
    或 "pending"（重新开始跟踪，即取消关闭），由调用方（server.py 的请求体
    解析）校验取值，这里不重复校验、直接透传给 mark_suggested_task_status
    （它本来就不限定 status 取值，这个通用性正好是"toggle"交互不需要额外
    后端分支的原因）。"""
    resolved = _resolve_workspace_for_project(project_name)
    if resolved is None:
        return {"found": False, "error": f"未知项目: {project_name}"}
    _root, workspace = resolved
    found = ws.mark_suggested_task_status(workspace, task_id, status)
    return {"found": found}


def pipeline_status() -> dict:
    """pipeline-check 是全局单份报告（覆盖OB/VNW/AIT/PTA/方法论几个阶段），
    不是每个watched project各一份——报告目录固定相对HOME_PROJECT_ROOT，
    跟agent.py里cmd_pipeline_check的路径推导一致。只读最新报告，绝不
    在这里触发重新检测（那会真实改写.baseline.json）。"""
    report_dir = HOME_PROJECT_ROOT / REPORT_DIR_RELATIVE
    return summarize_latest_report(report_dir)


def pipeline_drift_detail() -> dict:
    """pipeline-status只给一个drift_count数字，前端"漂移详情"页面需要完整
    的阶段/维度/矩阵声明/本周实测/说明表格，才能真正定位到"具体是哪里在
    偏离"，不只是知道"有N处偏离"。"""
    report_dir = HOME_PROJECT_ROOT / REPORT_DIR_RELATIVE
    return drift_detail_from_latest_report(report_dir)


def activity_feed(project_filter: str = "all") -> List[dict]:
    """"今日动态"——每个已配置项目最新一份daily-scan报告的原始变化列表，
    project_filter="all"时返回全部项目各自最新一份（不合并成一个大列表，
    前端按project_name分组展示，保留"这是哪个项目的动态"这层信息）。
    从没跑过daily-scan的项目（latest_report_summary返回None）直接跳过，
    不在列表里出现空占位。"""
    projects = _load_watched_projects()
    if project_filter != "all":
        projects = [p for p in projects if p.get("name") == project_filter]

    result = []
    for p in projects:
        name = p.get("name", "")
        root = Path(p.get("project_root", ""))
        if not root.exists():
            continue
        workspace = ws.get_project_workspace(root)
        summary = latest_report_summary(workspace, project_name=name)
        if summary is not None:
            result.append(summary)
    return result


def ob_search(query: str, mode: str = "hybrid", max_results: int = 5) -> dict:
    """OB背景检索框——实时调用tools/ob_bridge.get_background()，不缓存不落盘
    （每次都是一次真实的OB subprocess调用，检索本身不是高频路径，见ob_bridge.py
    顶部注释）。找不到背景/OB不存在/调用异常都由get_background内部吞掉优雅
    返回None，这里原样透传成found=False，不是接口层面的错误。"""
    text = get_background(query, mode=mode, max_results=max_results)
    return {"query": query, "found": text is not None, "background": text}


def execution_history(project_filter: str = "all", limit: int = 30) -> List[dict]:
    """"执行记录"——跨项目合并 state.json 里的 task_history（run_instruction()
    每次真实执行/dry-run都会追加一条），按 timestamp 降序、只取最近 limit 条。
    这是纯读取，不新增任何字段，跟 state.json 里已经存在的结构完全一致，
    只是加了 project_name 标注来源、并做跨项目合并排序。"""
    projects = _load_watched_projects()
    if project_filter != "all":
        projects = [p for p in projects if p.get("name") == project_filter]

    merged = []
    for p in projects:
        name = p.get("name", "")
        root = Path(p.get("project_root", ""))
        if not root.exists():
            continue
        workspace = ws.get_project_workspace(root)
        state = ws.load_state(workspace)
        for entry in state.get("task_history", []):
            merged.append({**entry, "project_name": name})

    merged.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return merged[:limit]


def agent_monitor() -> dict:
    """Agent执行监控器：五个主Agent(PTA/VNW/AIT/方法论转正Agent/OB)的真实
    自动化状态(四态) + PTA自己的skill调用频率统计。两者分开检测、原样打包
    在一个响应里返回，前端一次请求就能渲染整个监控面板，不必再拼两次请求。"""
    return {
        "agents": detect_all_agent_statuses(),
        "skill_usage": ws.load_skill_usage_summary(),
    }
