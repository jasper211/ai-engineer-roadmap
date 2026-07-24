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
from datetime import datetime
from pathlib import Path
from typing import Dict, List

API_DIR = Path(__file__).resolve().parent                    # 12_任务看板_Task_Dashboard/api/
DASHBOARD_DIR = API_DIR.parent                                 # 12_任务看板_Task_Dashboard/
PTA_DIR = DASHBOARD_DIR.parent                                  # PTA 项目根目录

for _pkg_dir in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(PTA_DIR / _pkg_dir))

from memory import workspace as ws
from skills.daily_sensing import list_tasks_from_state, latest_report_summary, DailySensor
from skills.pipeline_health import summarize_latest_report, drift_detail_from_latest_report, REPORT_DIR_RELATIVE
from skills.agent_status import detect_all_agent_statuses
from tools.ob_bridge import get_background
from tools.task_knowledge import load_task_map
from skills.execution_planning import ExecutionScheduler, ExecutionPlan, ExecutionStep

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


def _save_watched_projects(projects: List[dict]) -> None:
    """写回daily_scan_projects.json——保留原有的_meta字段（不重新生成，避免
    人工维护的说明文字被API写操作覆盖掉），只替换projects数组本身。"""
    existing = {}
    if DAILY_SCAN_PROJECTS_PATH.exists():
        try:
            existing = json.loads(DAILY_SCAN_PROJECTS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    existing["projects"] = projects
    DAILY_SCAN_PROJECTS_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def list_watched_projects_config() -> List[dict]:
    """给管理界面用的原始配置读取（name/project_root/exclude_dirs），区别于
    list_projects()——那个函数额外拼装了exists/last_daily_scan运行时信息，
    是给"运行状态"页面看的只读展示；这个是给"新增/删除项目"表单用的编辑态数据，
    两者关注点不同，不合并成一个函数。"""
    return _load_watched_projects()


def add_watched_project(name: str, project_root: str, exclude_dirs: List[str] = None) -> dict:
    """新增一个每日巡检项目——写进daily_scan_projects.json后，立刻为它建立
    种子基线（DailySensor.seed_baseline()，只做文件快照不调LLM），避免下一次
    真实--daily-scan把项目里全部现存文件当成"今天的变化"打包分析（这是
    v2.10.2真实踩过的坑：Rw/Jasper工作文档两个项目首次接入时都因为没有基线，
    直接跑巡检会把上千个文件当新增去分析）。

    name不能为空/不能跟已有项目重名，project_root必须是真实存在的目录——
    校验失败时返回{success: False, error}，不写文件也不建基线。"""
    name = (name or "").strip()
    project_root = (project_root or "").strip()
    if not name:
        return {"success": False, "error": "项目名称不能为空"}
    if not project_root:
        return {"success": False, "error": "project_root不能为空"}

    root = Path(project_root)
    if not root.exists() or not root.is_dir():
        return {"success": False, "error": f"目录不存在: {project_root}"}

    projects = _load_watched_projects()
    if any(p.get("name") == name for p in projects):
        return {"success": False, "error": f"项目名称已存在: {name}"}

    entry = {"name": name, "project_root": str(root)}
    if exclude_dirs:
        entry["exclude_dirs"] = exclude_dirs
    projects.append(entry)
    _save_watched_projects(projects)

    sensor = DailySensor(root, extra_exclude_dirs=set(exclude_dirs) if exclude_dirs else None)
    seeded_state = sensor.seed_baseline()
    workspace = ws.get_project_workspace(root)
    ws.save_daily_sensing_state(workspace, seeded_state)

    return {"success": True, "seeded_files": len(seeded_state["file_hashes"])}


def remove_watched_project(name: str) -> dict:
    """从daily_scan_projects.json里移除一个项目——只删配置条目，不删它已经
    产生的工作区/报告数据（那些是历史记录，删项目配置不该连带销毁历史，
    真要清理由人自己去项目工作区手动处理）。"""
    projects = _load_watched_projects()
    remaining = [p for p in projects if p.get("name") != name]
    if len(remaining) == len(projects):
        return {"success": False, "error": f"未找到项目: {name}"}
    _save_watched_projects(remaining)
    return {"success": True}


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


def decide_task(project_name: str, task_id: str, updates: dict) -> dict:
    """保存候选任务的人工决策与执行前上下文，不触发任何命令或外部通知。"""
    resolved = _resolve_workspace_for_project(project_name)
    if resolved is None:
        return {"found": False, "error": f"未知项目: {project_name}"}
    _root, workspace = resolved
    return ws.update_suggested_task_decision(workspace, task_id, updates)


def _find_task_fingerprint(workspace: Path, task_id: str) -> dict:
    state = ws.load_daily_sensing_state(workspace)
    for fp in state.get("suggested_task_fingerprints", {}).values():
        if fp.get("task_id") == task_id:
            return fp
    return {}


def _step_risk(step: dict) -> dict:
    """确定性风险标注，只提示和设门，不尝试主观判断命令是否“合理”。"""
    text = " ".join(str(step.get(k) or "") for k in ("tool", "action", "command", "script")).lower()
    critical_tokens = ("git push", "rm -", "sudo ", "curl ", "wget ", "ssh ", "osascript")
    if any(token in text for token in critical_tokens):
        return {"level": "critical", "label": "外部或不可逆动作", "requires_reconfirm": True}
    if step.get("tool") in ("bash", "python", "browser-use") and step.get("action") != "manual_review":
        return {"level": "high", "label": "可执行工具调用", "requires_reconfirm": True}
    return {"level": "low", "label": "人工核对/只读准备", "requires_reconfirm": False}


def prepare_task_execution(project_name: str, task_id: str) -> dict:
    resolved = _resolve_workspace_for_project(project_name)
    if resolved is None:
        return {"success": False, "error": f"未知项目: {project_name}"}
    root, workspace = resolved
    fp = _find_task_fingerprint(workspace, task_id)
    if not fp:
        return {"success": False, "error": f"未找到任务: {task_id}"}
    if fp.get("decision_status") != "accepted":
        return {"success": False, "error": "只有已接受的任务可以生成执行计划"}
    task_map = load_task_map(None, root)
    package = {"task_id": task_id, "items": [{"id": task_id, "name": fp.get("name", task_id)}]}
    scheduler = ExecutionScheduler(root, dry_run=True, task_map=task_map)
    plan = scheduler.to_dict(scheduler.create_plan(package, include_sync=False))
    for step in plan["steps"]:
        step["risk"] = _step_risk(step)
    levels = [s["risk"]["level"] for s in plan["steps"]]
    overall = "critical" if "critical" in levels else "high" if "high" in levels else "low"
    execution = {
        "state": "plan_ready", "prepared_at": datetime.now().isoformat(),
        "plan": plan, "risk_level": overall, "dry_run": None,
        "approved_at": None, "approval_note": "",
    }
    ws.update_suggested_task_execution(workspace, task_id, execution)
    return {"success": True, "execution": execution}


def dry_run_task_execution(project_name: str, task_id: str) -> dict:
    resolved = _resolve_workspace_for_project(project_name)
    if resolved is None:
        return {"success": False, "error": f"未知项目: {project_name}"}
    root, workspace = resolved
    fp = _find_task_fingerprint(workspace, task_id)
    execution = fp.get("execution") if fp else None
    if not execution or not execution.get("plan"):
        return {"success": False, "error": "请先生成执行计划"}
    plan_data = execution["plan"]
    steps = []
    for raw in plan_data.get("steps", []):
        clean = {k: v for k, v in raw.items() if k != "risk"}
        steps.append(ExecutionStep(**clean))
    plan = ExecutionPlan(plan_id=plan_data["plan_id"], task_id=plan_data["task_id"],
                         task_name=plan_data["task_name"], steps=steps)
    result = ExecutionScheduler(root, dry_run=True).execute_plan(plan)
    execution["dry_run"] = {**result, "run_at": datetime.now().isoformat()}
    execution["state"] = "dry_run_passed" if result["failed"] == 0 else "dry_run_failed"
    execution["approved_at"] = None
    ws.update_suggested_task_execution(workspace, task_id, execution)
    return {"success": result["failed"] == 0, "execution": execution}


def approve_task_execution(project_name: str, task_id: str, approval_note: str = "") -> dict:
    resolved = _resolve_workspace_for_project(project_name)
    if resolved is None:
        return {"success": False, "error": f"未知项目: {project_name}"}
    _root, workspace = resolved
    fp = _find_task_fingerprint(workspace, task_id)
    execution = fp.get("execution") if fp else None
    if not execution or execution.get("state") != "dry_run_passed":
        return {"success": False, "error": "只有 dry-run 通过的计划可以批准"}
    execution["state"] = "approved"
    execution["approved_at"] = datetime.now().isoformat()
    execution["approval_note"] = (approval_note or "").strip()
    execution["requires_explicit_execute"] = True
    ws.update_suggested_task_execution(workspace, task_id, execution)
    return {"success": True, "execution": execution}


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


PROJECT_ROLES = {
    "EA流程架构项目": {
        "role": "core", "label": "核心业务主线",
        "question": "业务事实发生了什么，哪些规则、SOP或裁定事项需要 Jasper 掌握？",
    },
    "Jasper工作文档": {
        "role": "lab", "label": "AI 技术试验田",
        "question": "Agent、方法论和工具发生了什么，哪些能力可以反哺 EA？",
    },
    "Rw权益项目": {
        "role": "case", "label": "真实项目全貌案例",
        "question": "真实项目发生了什么，哪些事实可以验证或修正 EA/Jasper 的方法？",
    },
}


def _infer_legacy_change_type(change: dict) -> str:
    """v2.19前报告没有change_type，旧数据只做保守推断并明确兼容，不伪造diff。"""
    if change.get("change_type") in ("added", "changed", "removed"):
        return change["change_type"]
    text = f"{change.get('summary', '')} {change.get('file', '')}"
    if any(word in text for word in ("删除", "移除")):
        return "removed"
    if any(word in text for word in ("新增", "新建", "创建")):
        return "added"
    return "changed"


def _build_cross_project_relations(projects: List[dict]) -> List[dict]:
    """从最新一次巡检的共同业务域生成待核对关系线索，不把关键词重合冒充因果。"""
    direction_notes = {
        ("Jasper工作文档", "EA流程架构项目"): "Jasper 技术试验可能形成 EA 可复用能力",
        ("EA流程架构项目", "Rw权益项目"): "EA 方法或规则可在 Rw 真实案例中核验",
        ("Rw权益项目", "EA流程架构项目"): "Rw 真实事实可能反向校准 EA 方法",
        ("Rw权益项目", "Jasper工作文档"): "Rw 暴露的问题可能转化为技术试验需求",
        ("EA流程架构项目", "Jasper工作文档"): "EA 业务问题可能需要 Jasper 技术能力支撑",
        ("Jasper工作文档", "Rw权益项目"): "Jasper 新能力可能在 Rw 案例中进行真实性验证",
    }
    result = []
    for source in projects:
        source_domains = {c.get("domain", "") for c in source.get("changes", [])
                          if c.get("domain") and c.get("domain") != "其他"}
        if not source_domains:
            continue
        for target in projects:
            if source["project_name"] == target["project_name"]:
                continue
            shared = sorted(source_domains & {
                c.get("domain", "") for c in target.get("changes", [])
                if c.get("domain") and c.get("domain") != "其他"
            })
            if not shared:
                continue
            pair = (source["project_name"], target["project_name"])
            evidence = [
                c["file"] for c in source.get("changes", []) + target.get("changes", [])
                if c.get("domain") in shared
            ][:6]
            result.append({
                "from_project": pair[0], "to_project": pair[1],
                "shared_domains": shared, "evidence_files": evidence,
                "analysis": direction_notes.get(pair, "两个项目在相同业务域出现同步变化"),
                "confidence": "线索", "needs_review": True,
            })
    return result


def command_center() -> dict:
    """个人指挥中心SSOT：三项目最新成功巡检事实 + 下游任务 + 跨项目关系线索。"""
    feed = activity_feed("all")
    task_buckets = aggregate_tasks("all")
    open_tasks = task_buckets["new"] + task_buckets["aging"]
    project_entries = []
    for entry in feed:
        name = entry["project_name"]
        changes = []
        for raw in entry.get("changes", []):
            change = dict(raw)
            change["change_type"] = _infer_legacy_change_type(change)
            change.setdefault("before_excerpt", "")
            change.setdefault("after_excerpt", "")
            change.setdefault("diff_text", "")
            changes.append(change)
        role = PROJECT_ROLES.get(name, {"role": "other", "label": "观察项目", "question": ""})
        project_tasks = [t for t in open_tasks if t.get("project_name") == name]
        project_entries.append({
            **entry, **role, "changes": changes,
            "related_tasks": project_tasks,
            "total_changes": entry.get("files_added", 0) + entry.get("files_changed", 0)
                             + entry.get("files_removed", 0),
        })
    role_order = {"core": 0, "lab": 1, "case": 2, "other": 3}
    project_entries.sort(key=lambda p: role_order.get(p["role"], 9))
    relations = _build_cross_project_relations(project_entries)
    stored_path = ws.WORKSPACE_ROOT / "_PTA指挥中心" / "cross_project_latest.json"
    if stored_path.exists():
        try:
            stored = json.loads(stored_path.read_text(encoding="utf-8"))
            current_times = {p["project_name"]: p.get("generated_at", "") for p in project_entries}
            if stored.get("source_report_timestamps") == current_times:
                relations = stored.get("relations", relations)
        except json.JSONDecodeError:
            pass
    return {
        "period_basis": "每个项目从上一次成功巡检到本次巡检之间的全部文件变化",
        "projects": project_entries,
        "cross_project_relations": relations,
    }


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
