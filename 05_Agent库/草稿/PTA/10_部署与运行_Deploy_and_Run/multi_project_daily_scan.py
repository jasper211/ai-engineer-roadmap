#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多项目每日巡检调度器

背景：daily_sensing 一次调用只服务一个 --project-root，launchd 一个 plist
只适合驱动一条固定命令。以前"要巡检几个项目就装几个 plist"的模式，随着
协同项目从 EA/Rw 扩展到还要加"Jasper工作文档"、以后还会继续加，维护成本
会越滚越大——每加一个项目都要新建一份 plist、重新 launchctl load。

改成这个薄封装：一个 launchd job 触发本脚本，本脚本读
02_配置项目_Configure_Project/daily_scan_projects.json 里的项目清单，
依次 subprocess 调用 agent.py --daily-scan。加新项目只需要改那份 JSON，
不需要再碰 launchd。

刻意用 subprocess 而不是直接 import agent 模块里的 cmd_daily_scan 函数：
跟 agent.py 本身"CLI 是真实对外接口"的原则一致（test_integration.py 里
Test 7/13 也是这么测的），且单个项目扫描失败（比如目录被移动/删除）只会让
那一次 subprocess 非正常退出，不会带崩整个调度器让后面排队的项目也扫不到。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent          # 10_部署与运行_Deploy_and_Run/
PTA_DIR = SCRIPT_DIR.parent                             # PTA 项目根目录
AGENT_PY = PTA_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"
DEFAULT_CONFIG_PATH = PTA_DIR / "02_配置项目_Configure_Project" / "daily_scan_projects.json"

for _pkg_dir in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(PTA_DIR / _pkg_dir))

from memory import workspace as ws
from skills.daily_sensing import latest_report_summary
from skills.cross_project_sensing import analyze_cross_project_relations


def load_projects(config_path: Path) -> list:
    if not config_path.exists():
        print(f"[错误] 找不到项目清单: {config_path}")
        return []
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[错误] 项目清单解析失败: {config_path} ({e})")
        return []
    return data.get("projects", [])


def scan_one(project: dict, notify: bool, force: bool) -> bool:
    name = project.get("name", project.get("project_root", "?"))
    root = project.get("project_root")
    if not root or not Path(root).exists():
        print(f"\n{'=' * 60}\n[跳过] {name}: project_root 不存在或未配置 ({root})\n{'=' * 60}")
        return False

    cmd = [sys.executable, str(AGENT_PY), "--daily-scan", "--project-root", root]
    if project.get("exclude_dirs"):
        cmd += ["--exclude-dirs"] + project["exclude_dirs"]
    if notify:
        cmd.append("--notify")
    if force:
        cmd.append("--force")

    print(f"\n{'=' * 60}\n[开始] {name} ({root})\n{'=' * 60}")
    result = subprocess.run(cmd)
    ok = result.returncode == 0
    print(f"[{'完成' if ok else '失败'}] {name}（returncode={result.returncode}）")
    return ok


def main():
    import argparse
    parser = argparse.ArgumentParser(description="多项目每日巡检调度器")
    parser.add_argument("--config", help="项目清单 JSON 路径（默认 daily_scan_projects.json）")
    parser.add_argument("--notify", action="store_true", help="有建议任务时推送企业微信（透传给每个 --daily-scan）")
    parser.add_argument("--force", action="store_true", help="忽略增量基线全量重扫（透传给每个 --daily-scan）")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else DEFAULT_CONFIG_PATH
    projects = load_projects(config_path)

    if not projects:
        print("[提示] 项目清单为空，无事可做。")
        return

    results = {p.get("name", p.get("project_root", "?")): scan_one(p, args.notify, args.force) for p in projects}

    # 三个项目各自巡检完成后，再做一次跨项目关系分析。页面打开时只读结果，
    # 不会因为刷新驾驶舱产生新的API费用。
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if api_key:
        reports = []
        for project in projects:
            root = Path(project.get("project_root", ""))
            if not root.exists():
                continue
            summary = latest_report_summary(ws.get_project_workspace(root), project.get("name", root.name))
            if summary is not None:
                reports.append(summary)
        try:
            analyze_cross_project_relations(
                reports, api_key,
                ws.WORKSPACE_ROOT / "_PTA指挥中心" / "cross_project_latest.json")
            print("[完成] 三项目跨项目关系分析")
        except Exception as e:
            # 关系分析失败不能抹掉三个项目各自已经成功落盘的巡检事实。
            print(f"[警告] 跨项目关系分析失败，保留各项目巡检结果: {e}")
    else:
        print("[提示] 未设置DEEPSEEK_API_KEY，跳过跨项目关系分析")

    print(f"\n{'=' * 60}\n多项目巡检完成：{sum(results.values())}/{len(results)} 个项目成功\n{'=' * 60}")
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}")


if __name__ == "__main__":
    main()
