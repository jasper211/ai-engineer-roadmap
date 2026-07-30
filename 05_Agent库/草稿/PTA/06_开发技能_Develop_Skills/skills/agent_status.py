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
  仍在运行中，或非0但stderr里查无崩溃痕迹——见下）
- 死的：匹配到launchd job，至少一个最近一次退出码非0，且stderr里能找到真实
  崩溃证据（Traceback）——本该自动运行却在失败，这是唯一需要人工介入排查的状态
- 人工：一个launchd job都没匹配到，但code_paths里至少一条真实存在——有人在
  手动跑
- 未搭建：launchd job和code_paths都为空/都不存在

真实教训（2026-07-30）：OB的`--sync-check`脚本设计是"6项健康检查里只要有1项不是
✅就`sys.exit(1)`"——包括"工作区有未提交改动，主动跳过pull避免冲突"这种完全
正常、非破坏性的场景。这类脚本的非0退出码≠崩溃，只看exit_code会把"跑完了、
如实报告了一个真实待办事项"误判成"死的"。修复：退出码非0时，进一步检查该
job的stderr日志（从对应~/Library/LaunchAgents/*.plist的StandardErrorPath读取）
最近内容里有没有真实Python Traceback——没有就不算"死的"，只是exit_code非0，
仍判定为健康，只是在launchd_jobs明细里附一条note说明"非0退出码但无崩溃痕迹"。
找不到stderr路径/文件不存在时，保守起见仍按"非0=不健康"处理（没有证据反驳
比误判成"死的"更安全——判定这里的初衷本来就是"宁可多提醒，不可漏报真实故障"）。

跟pipeline_health同样的原则：本技能只查证据、不做"要不要修"的判断。
"""

import json
import plistlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
CRASH_MARKER = "Traceback (most recent call last)"
STDERR_TAIL_BYTES = 20_000  # 只看文件末尾这么多字节，足够覆盖最近一次运行的完整
                             # traceback（几十行），又不会在err文件累积到几十MB
                             # 时整份读入内存

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


def _stderr_path_for_label(label: str) -> Optional[Path]:
    """从已安装的plist里读StandardErrorPath——不在registry里硬编码这条路径，
    plist本身就是唯一真源，硬编码一份容易在plist改了之后悄悄脱节（这个教训
    在pipeline-check的Weekday off-by-one上已经真实踩过一次）。"""
    plist_path = LAUNCH_AGENTS_DIR / f"{label}.plist"
    if not plist_path.exists():
        return None
    try:
        with plist_path.open("rb") as f:
            data = plistlib.load(f)
    except (OSError, ValueError):
        return None
    err_path = data.get("StandardErrorPath")
    return Path(err_path) if err_path else None


def _recent_stderr_has_crash(label: str) -> Optional[bool]:
    """True=stderr最近内容里找到了真实Python Traceback（真崩溃）；
    False=stderr存在但最近内容里没有；None=找不到stderr路径/文件不存在/
    读取失败（证据不足，调用方按"保守判定为不健康"处理，不是"判定为健康"）。"""
    err_path = _stderr_path_for_label(label)
    if err_path is None or not err_path.exists():
        return None
    try:
        with err_path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - STDERR_TAIL_BYTES))
            tail = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    return CRASH_MARKER in tail


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
            note = ""
            if not healthy:
                # 退出码非0——先别急着判"死的"，查一下stderr里有没有真实
                # Traceback。找不到证据(None)时保守维持healthy=False（宁可
                # 多提醒也不漏报真实故障）；明确查到没有traceback(False)时
                # 才翻正，这是本次要修的"OB健康检查非0退出码≠崩溃"这个问题。
                crashed = _recent_stderr_has_crash(label)
                if crashed is False:
                    healthy = True
                    note = "退出码非0，但stderr近期无崩溃痕迹（无Traceback）——可能是脚本自身设计的告警退出（比如健康检查里有一项不达标就非0退出），不代表任务真的崩溃"
            launchd_jobs.append({
                "label": label,
                "pid": job["pid"],
                "last_exit_code": exit_code,
                "healthy": healthy,
                "note": note,
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
