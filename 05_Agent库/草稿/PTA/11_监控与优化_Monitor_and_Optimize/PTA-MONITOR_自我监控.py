#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-MONITOR · 自我监控

对应方法论第11步"监控与优化"的本意：不是"PTA 帮你分析别的项目"（那是本文件夹
里 DASH/DISCOVER/EXT/INTEL 等工具在做的事），而是"PTA 自己被调用得怎么样"——
对应 codex logs / codex eval 这类内省型监控。

数据来源：memory.workspace 定义的专属工作区里，每个目标项目一份的 state.json
（task_history 字段）——这是 agent.py 每次运行都会写入的真实调用记录，不需要
额外埋点，本脚本只是把已经存在的记录汇总成可读报告。

运行：
  python3 11_监控与优化_Monitor_and_Optimize/PTA-MONITOR_自我监控.py
      汇总 PTA 曾经运行过的所有项目的调用历史

  python3 11_监控与优化_Monitor_and_Optimize/PTA-MONITOR_自我监控.py --project-root /path/to/project
      只看某一个项目的调用历史
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

MONITOR_DIR = Path(__file__).resolve().parent
PTA_DIR = MONITOR_DIR.parent
sys.path.insert(0, str(PTA_DIR / "07_接入记忆_Integrate_Memory"))

from memory.workspace import WORKSPACE_ROOT, get_project_workspace  # noqa: E402


def _load_workspace_history(workspace: Path) -> list:
    state_path = workspace / "state.json"
    if not state_path.exists():
        return []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"  ⚠️ 状态文件损坏，跳过: {state_path}")
        return []
    return state.get("task_history", [])


def _parse_success_rate(rate_str: str):
    try:
        completed, total = rate_str.split("/")
        completed, total = int(completed), int(total)
        return (completed / total) if total > 0 else None
    except (ValueError, AttributeError):
        return None


def collect_all_workspaces() -> dict:
    """扫描 WORKSPACE_ROOT 下所有 `*工作区` 目录，按项目名分组返回调用历史"""
    if not WORKSPACE_ROOT.exists():
        return {}
    result = {}
    for ws_dir in sorted(WORKSPACE_ROOT.iterdir()):
        if not ws_dir.is_dir() or not ws_dir.name.endswith("工作区"):
            continue
        history = _load_workspace_history(ws_dir)
        if history:
            project_name = ws_dir.name[:-2]  # 去掉末尾"工作区"
            result[project_name] = history
    return result


def print_report(project_histories: dict):
    print("=" * 60)
    print("[PTA-MONITOR] 自我监控报告")
    print("=" * 60)

    all_entries = [(project, e) for project, entries in project_histories.items() for e in entries]

    if not all_entries:
        print("\n还没有任何调用记录——PTA 目前没有被真实运行过。")
        print("=" * 60)
        return

    print(f"\n覆盖项目数: {len(project_histories)}｜累计调用次数: {len(all_entries)}")

    status_counter = Counter(e.get("status", "unknown") for _, e in all_entries)
    mode_counter = Counter(e.get("mode", "unknown") for _, e in all_entries)

    print(f"\n按状态分布:")
    for status, count in status_counter.most_common():
        print(f"  {status}: {count} ({count/len(all_entries)*100:.0f}%)")

    print(f"\n按模式分布:")
    for mode, count in mode_counter.most_common():
        print(f"  {mode}: {count} ({count/len(all_entries)*100:.0f}%)")

    rates = [r for _, e in all_entries if (r := _parse_success_rate(e.get("success_rate", ""))) is not None]
    if rates:
        print(f"\n平均步骤成功率: {sum(rates)/len(rates)*100:.0f}%（基于 {len(rates)} 次有效记录）")

    clarification_count = status_counter.get("blocked_clarification", 0)
    if clarification_count > 0:
        pct = clarification_count / len(all_entries) * 100
        print(f"\n⚠️ 指令模糊触发澄清: {clarification_count} 次 ({pct:.0f}%)"
              f"{'——占比偏高，指令表达习惯或任务知识库覆盖可能需要优化' if pct > 20 else ''}")

    print(f"\n按项目明细:")
    for project, entries in sorted(project_histories.items(), key=lambda x: -len(x[1])):
        last = entries[-1]
        print(f"  {project}: {len(entries)} 次调用｜最近一次 [{last.get('timestamp', '')[:19]}] "
              f"{last.get('summary', '')} → {last.get('status')}")

    print(f"\n最近 5 次调用（跨项目，按时间倒序）:")
    recent = sorted(all_entries, key=lambda x: x[1].get("timestamp", ""), reverse=True)[:5]
    for project, e in recent:
        print(f"  [{e.get('timestamp', '')[:19]}] {project} · {e.get('task_id')}: "
              f"{e.get('summary', '')} → {e.get('status')} ({e.get('success_rate', '?')})")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="PTA-MONITOR · 自我监控")
    parser.add_argument("--project-root", help="只看某一个项目的调用历史（不传则汇总所有项目）")
    args = parser.parse_args()

    if args.project_root:
        resolved = Path(args.project_root).resolve()
        workspace = get_project_workspace(resolved)
        history = _load_workspace_history(workspace)
        print_report({resolved.name: history} if history else {})
    else:
        print_report(collect_all_workspaces())


if __name__ == "__main__":
    main()
