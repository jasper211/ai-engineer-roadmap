#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：agent_status · 全部主Agent自动化状态监控

背景：PTA/VNW/AIT/方法论转正Agent/OB 五个agent里，只有PTA/OB接了launchd定时
任务，VNW有真实代码但纯人工触发，AIT和方法论转正Agent还完全没开始搭建。用户
需要一眼看出"哪些在自动跑、哪些还在人工跑、哪些压根没搭、哪些该跑却在失败"，
而不是靠记忆或翻各自项目文件夹去确认。

四态判定全部基于确定性检查（launchctl真实退出码 + 代码路径真实存在性），不做
猜测：
- 自动：匹配到至少一个launchd job，且所有匹配job最近一次退出码都是0（或当前
  仍在运行中）
- 死的：匹配到launchd job，但至少一个最近一次退出码非0——本该自动运行却在
  失败，这是唯一需要人工介入排查的状态
- 人工：一个launchd job都没匹配到，但code_paths里至少一条真实存在——有人在
  手动跑
- 未搭建：launchd job和code_paths都为空/都不存在

跟pipeline_health同样的原则：本技能只查证据、不做"要不要修"的判断。
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

AGENT_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent / "02_配置项目_Configure_Project" / "agent_registry.json"
)

# 与 agent_registry.json 里 path_base 字段约定一致：PTA/VNW/OB 的共同上级目录。
JASPER_DOCS_ROOT = Path.home() / "Desktop" / "Jasper工作文档（不含EA项目）"

STATUS_AUTO = "自动"
STATUS_MANUAL = "人工"
STATUS_UNBUILT = "未搭建"
STATUS_DEAD = "死的"


def _load_registry() -> List[dict]:
    if not AGENT_REGISTRY_PATH.exists():
        return []
    try:
        data = json.loads(AGENT_REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data.get("agents", [])


def _launchctl_snapshot() -> Dict[str, dict]:
    """跑一次`launchctl list`，解析成 {label: {pid, last_exit_code}}。

    只调用一次、所有agent共用这份快照，避免5个agent各自重复subprocess调用
    launchctl（这个命令本身不慢，但没必要重复5次）。任何异常（如非macOS环境）
    都优雅降级为空字典，调用方据此把所有launchd_labels当作"匹配不到"处理。"""
    try:
        result = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}

    snapshot: Dict[str, dict] = {}
    for line in result.stdout.splitlines()[1:]:  # 首行是表头 PID/Status/Label
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        pid_str, status_str, label = parts
        try:
            exit_code = int(status_str)
        except ValueError:
            exit_code = None
        snapshot[label] = {
            "pid": None if pid_str == "-" else pid_str,
            "last_exit_code": exit_code,
        }
    return snapshot


def _resolve_code_path(relative_path: str) -> Path:
    return JASPER_DOCS_ROOT / relative_path


def detect_all_agent_statuses() -> List[dict]:
    """返回全部已登记agent的真实状态列表，每项：
    {agent_id, display_name, description, status, launchd_jobs, has_code}

    launchd_jobs 是逐job明细（label/pid/last_exit_code/healthy），供前端展示
    "OB两个job里具体是哪一个在失败"这种细节，不只是一个笼统的四态标签。"""
    agents = _load_registry()
    snapshot = _launchctl_snapshot()
    results = []

    for agent in agents:
        agent_id = agent.get("agent_id", "")
        code_paths = agent.get("code_paths", [])
        launchd_labels = agent.get("launchd_labels", [])

        has_code = any(_resolve_code_path(p).exists() for p in code_paths)

        launchd_jobs = []
        for label in launchd_labels:
            job = snapshot.get(label)
            if job is None:
                continue
            exit_code = job["last_exit_code"]
            healthy = job["pid"] is not None or exit_code == 0
            launchd_jobs.append({
                "label": label,
                "pid": job["pid"],
                "last_exit_code": exit_code,
                "healthy": healthy,
            })

        if launchd_jobs:
            status = STATUS_AUTO if all(j["healthy"] for j in launchd_jobs) else STATUS_DEAD
        elif has_code:
            status = STATUS_MANUAL
        else:
            status = STATUS_UNBUILT

        results.append({
            "agent_id": agent_id,
            "display_name": agent.get("display_name", agent_id),
            "description": agent.get("description", ""),
            "status": status,
            "has_code": has_code,
            "launchd_jobs": launchd_jobs,
        })

    return results
