#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-RUN · 主编排器（Orchestrator）
功能：串联 S01(意图解析) → S02(执行编排) → S03(进度监控) → S05(归档复盘)，
      并持久化 .pta_state.json 实现跨会话的状态记忆。这是 PTA 从"5 个独立脚本，
      靠人/AI 终端手动依次调用"变成"一句话指令 → 自动跑完流程 → 记得上次做到哪"的入口。

      文档同步（S04，含真实 git push）默认不自动触发：必须显式传 --sync 且提供
      --message，还需搭配 --execute。这是刻意设计，不是遗漏——S02 原本会给任何
      execute/sequential 任务自动追加一个真实 git push 步骤且无法关闭，本编排器
      通过 --no-sync 把这一步从自动执行计划里摘出来，改成独立、显式确认的阶段，
      避免无人值守/AI 终端在未经确认的情况下推送到共享仓库。

运行：
  python3 PTA-RUN_主编排器.py --status
      查看当前/历史任务状态（"回顾下进度，继续推进"场景）

  python3 PTA-RUN_主编排器.py "按顺序完成 P1-03, P1-04"
      默认 dry-run：只解析意图 + 生成执行计划 + 出进度报告，不产生真实副作用

  python3 PTA-RUN_主编排器.py "按顺序完成 P1-03, P1-04" --execute
      真实执行任务步骤（仍不含 git push）

  python3 PTA-RUN_主编排器.py "按顺序完成 P1-03, P1-04" --execute --sync -m "commit msg"
      真实执行 + 执行后追加真实文档同步（git add/commit/push）

  python3 PTA-RUN_主编排器.py --discover --project-root /path/to/other/project
      对该项目跑一次 PTA-DISCOVER 增量文档任务发现（v1.5.0 起），结果计入
      .pta_state.json——下次 --status 会看到"文档里发现了几条新任务"，而不需要
      单独去读 PTA-DISCOVER 的报告文件。这一步仍然只产出人工可审阅的发现摘要，
      不会自动写入任何项目的 pta_tasks.json。
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PTA_DIR = Path(__file__).resolve().parent
STATE_PATH = PTA_DIR / ".pta_state.json"
RUNS_DIR = PTA_DIR / ".pta_runs"

S01 = PTA_DIR / "PTA-S01_意图解析器.py"
S02 = PTA_DIR / "PTA-S02_执行调度器.py"
S03 = PTA_DIR / "PTA-S03_进度追踪器.py"
S04 = PTA_DIR / "PTA-S04_文档同步器.py"
S05 = PTA_DIR / "PTA-S05_归档复盘器.py"
DISCOVER = PTA_DIR / "PTA-DISCOVER_文档任务发现器.py"

EMPTY_STATE = {"version": 1, "current_task": None, "task_history": [], "context": {}}


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[警告] 状态文件损坏，已重置: {STATE_PATH}")
    return dict(EMPTY_STATE)


def _save_state(state: dict) -> None:
    if STATE_PATH.exists():
        STATE_PATH.replace(STATE_PATH.with_name(STATE_PATH.name + ".bak"))
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(cmd) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0 and result.stderr:
        print(result.stderr, file=sys.stderr)
    return result


def cmd_status() -> None:
    state = _load_state()
    print("=" * 60)
    print("[PTA-RUN] 当前状态")
    print("=" * 60)

    cur = state.get("current_task")
    if cur:
        print(f"当前任务: {cur.get('task_id')} · {cur.get('status')}"
              f"（{cur.get('mode', '?')}，{cur.get('success_rate', '?')}）")
    else:
        print("当前任务: 无")

    history = state.get("task_history", [])
    print(f"\n历史任务（共 {len(history)} 条，最近 5 条）:")
    if not history:
        print("  （空）")
    for h in history[-5:]:
        print(f"  - [{h.get('timestamp', '')[:19]}] {h.get('task_id')}: "
              f"{h.get('summary', '')} → {h.get('status')} ({h.get('success_rate', '?')})")

    discoveries = state.get("discoveries", {})
    if discoveries:
        print(f"\n文档任务发现（PTA-DISCOVER，共 {len(discoveries)} 个项目有记录）:")
        for project, d in discoveries.items():
            print(f"  - {project}")
            print(f"    最近一次: [{d.get('last_run', '')[:19]}] 处理了 {d.get('files_scanned', 0)} 个新增/变更文件，"
                  f"发现 {d.get('tasks_found', 0)} 条任务（低置信度 {d.get('low_confidence', 0)} 条）")
            for t in d.get("preview", []):
                print(f"      · [{t.get('status')}] {t.get('name')} (owner: {t.get('owner')})")
            print(f"    完整报告: {d.get('report_path', '')}")
        print("  ⚠️ 以上仅供人工审阅，未经确认不会写入任何项目的 pta_tasks.json")

    ctx = state.get("context", {})
    if ctx:
        print(f"\n上下文: {json.dumps(ctx, ensure_ascii=False)}")

    print("=" * 60)


def run_discover(project_root: str, force: bool) -> None:
    resolved_root = str(Path(project_root).resolve())
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / f"discover-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.json"

    cmd = ["python3", str(DISCOVER), "--project", resolved_root, "--scan",
           "--output", str(report_path)]
    if force:
        cmd.append("--force")
    r = _run(cmd)

    if r.returncode != 0:
        print("[错误] PTA-DISCOVER 运行失败，状态未更新。")
        sys.exit(1)

    if not report_path.exists():
        print("[PTA-RUN] 本次没有新增/变更的文件需要处理，状态保持不变。")
        return

    report = json.loads(report_path.read_text(encoding="utf-8"))
    tasks = report.get("tasks", [])
    low_confidence = sum(1 for t in tasks if t.get("confidence", 1.0) < 0.7)
    preview = sorted(tasks, key=lambda t: -t.get("confidence", 0))[:5]

    state = _load_state()
    discoveries = state.setdefault("discoveries", {})
    discoveries[resolved_root] = {
        "last_run": datetime.now().isoformat(),
        "files_scanned": report.get("files_scanned", 0),  # PTA-DISCOVER 自身已做增量过滤，
        # 这里的数字就是"本次新增/变更"，不是项目全量文件数
        "tasks_found": len(tasks),
        "low_confidence": low_confidence,
        "preview": [
            {"name": t.get("name"), "owner": t.get("owner"), "status": t.get("status")}
            for t in preview
        ],
        "report_path": str(report_path),
    }
    _save_state(state)

    print(f"\n[PTA-RUN] 文档任务发现完成: {resolved_root}")
    print(f"  本次处理 {report.get('files_scanned', 0)} 个新增/变更文件，"
          f"发现 {len(tasks)} 条任务（低置信度 {low_confidence} 条）")
    print(f"  完整报告: {report_path}")
    print(f"  状态已记入 .pta_state.json，下次 --status 会显示")


def run_instruction(instruction: str, execute: bool, sync: bool, message: str,
                     project_root: str = None, task_map: str = None) -> None:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 目标项目的任务知识库定位参数：不传则退回本项目内置的 pta_tasks_default.json
    knowledge_args = []
    if project_root:
        knowledge_args += ["--project-root", project_root]
    if task_map:
        knowledge_args += ["--task-map", task_map]

    state = _load_state()

    # ---------- L3-PTA-01 任务解析 ----------
    task_path = run_dir / "task.json"
    r = _run(["python3", str(S01), instruction, "--output", str(task_path)] + knowledge_args)
    if r.returncode != 0 or not task_path.exists():
        print("[错误] S01 意图解析失败，终止。")
        sys.exit(1)
    task_package = json.loads(task_path.read_text(encoding="utf-8"))
    task_id = task_package["task_id"]
    items = task_package.get("items", [])
    # S02 --output 写入的是 execute_plan() 的结果摘要（plan_id/status/steps 等），
    # 不含 task_name 字段；task_name 需和 S02.create_plan() 保持同样的推导方式：
    # 取任务包第一个 item 的 name。
    task_name = items[0].get("name", "Unknown") if items else "Unknown"

    if task_package.get("needs_clarification"):
        print("\n⚠️ 指令不够明确，需要澄清后才能继续：")
        for q in task_package.get("clarification_questions", []):
            print(f"  - {q}")
        state["current_task"] = {
            "task_id": task_id,
            "status": "blocked_clarification",
            "raw_input": instruction,
            "mode": "n/a",
            "success_rate": "n/a",
            "timestamp": datetime.now().isoformat(),
        }
        _save_state(state)
        return

    # ---------- L3-PTA-02 执行编排（--no-sync：把文档同步摘出去，见文件头说明）----------
    plan_path = run_dir / "plan.json"
    s02_cmd = ["python3", str(S02), "--input", str(task_path), "--output", str(plan_path),
               "--no-sync"] + knowledge_args
    if not execute:
        s02_cmd.append("--dry-run")
    r = _run(s02_cmd)
    if r.returncode != 0 or not plan_path.exists():
        print("[错误] S02 执行编排失败，终止。")
        sys.exit(1)

    # ---------- L3-PTA-03 进度监控 ----------
    report_path = run_dir / "report.json"
    r = _run(["python3", str(S03), "--plan", str(plan_path), "--output", str(report_path)])
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}

    # ---------- 状态记忆更新 ----------
    entry = {
        "task_id": task_id,
        "summary": instruction[:60],
        "status": report.get("status", "unknown"),
        "success_rate": f"{report.get('completed', 0)}/{report.get('total', 0)}",
        "mode": "execute" if execute else "dry-run",
        "timestamp": datetime.now().isoformat(),
        "run_dir": str(run_dir),
    }
    state["current_task"] = entry
    history = state.setdefault("task_history", [])
    history.append(entry)
    state["task_history"] = history[-50:]
    state.setdefault("context", {})["last_run"] = run_id
    _save_state(state)

    # ---------- L3-PTA-05 归档复盘（本地写入，无 git 动作，始终执行）----------
    _run(["python3", str(S05), "--plan", str(plan_path), "--task-id", task_id,
          "--task-name", task_name, "--no-lessons"])

    # ---------- L3-PTA-04 产出同步（唯一含真实 git push 的阶段，需显式确认）----------
    if sync:
        if not execute:
            print("\n⚠️ --sync 需搭配 --execute 一起使用（dry-run 没有真实产出可同步），已跳过。")
        elif not message:
            print("\n⚠️ --sync 需要提供 --message，已跳过。")
        else:
            _run(["python3", str(S04), "--task-id", task_id, "--task-name", task_name,
                  "--message", message])
    else:
        print(f"\nℹ️ 未同步文档。如需同步（会真实 git push）："
              f"\n  python3 {S04.name} --task-id {task_id} --task-name \"{task_name}\" -m \"...\"")

    print(f"\n运行产物目录: {run_dir}")


def main():
    parser = argparse.ArgumentParser(description="PTA-RUN · 主编排器（S01→S02→S03→S05 自动串联 + 状态记忆）")
    parser.add_argument("instruction", nargs="?", help="自然语言指令，缺省则等价于 --status")
    parser.add_argument("--status", action="store_true", help="查看当前/历史任务状态")
    parser.add_argument("--execute", action="store_true", help="真实执行任务步骤（默认仅 dry-run 出计划+报告）")
    parser.add_argument("--sync", action="store_true",
                         help="执行后调用 S04 做真实文档同步（git add/commit/push），需搭配 --execute 和 --message")
    parser.add_argument("--message", "-m", help="--sync 时的 git 提交信息")
    parser.add_argument("--project-root",
                         help="目标项目根目录（不传则默认本项目；传了会去该目录下找 pta_tasks.json）")
    parser.add_argument("--task-map", help="显式指定任务知识库 JSON 文件路径（优先级高于 --project-root）")
    parser.add_argument("--discover", action="store_true",
                         help="对 --project-root 指定的项目跑一次 PTA-DISCOVER 增量文档任务发现，"
                              "结果计入 .pta_state.json，供 --status 查看")
    parser.add_argument("--force", action="store_true", help="--discover 时忽略增量记录，全部重新处理")
    args = parser.parse_args()

    if args.discover:
        if not args.project_root:
            print("[错误] --discover 需要搭配 --project-root 指定要扫描的项目目录")
            sys.exit(1)
        run_discover(args.project_root, args.force)
        return

    if args.status or not args.instruction:
        cmd_status()
        return

    run_instruction(args.instruction, args.execute, args.sync, args.message,
                     project_root=args.project_root, task_map=args.task_map)


if __name__ == "__main__":
    main()
