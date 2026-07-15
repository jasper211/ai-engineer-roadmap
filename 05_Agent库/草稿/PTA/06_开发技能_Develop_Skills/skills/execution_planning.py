#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：执行编排（原 PTA-S02_执行调度器.py 的 ExecutionScheduler 类迁移，逻辑不变；
具体"每种步骤怎么跑"下放到 tools/shell_exec.py，这里只负责"分解成哪些步骤+调度"）
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from tools import shell_exec


@dataclass
class ExecutionStep:
    seq: int
    action: str
    tool: str
    command: Optional[str] = None
    script: Optional[str] = None
    args: Optional[List[str]] = None
    description: str = ""
    status: str = "pending"
    output: str = ""
    error: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None


@dataclass
class ExecutionPlan:
    plan_id: str
    task_id: str
    task_name: str
    steps: List[ExecutionStep]
    status: str = "pending"
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class ExecutionScheduler:
    """执行调度器：将任务包分解为执行步骤并调度执行"""

    def __init__(self, project_root: Path, dry_run: bool = False, task_map: Optional[Dict[str, dict]] = None):
        self.project_root = project_root
        self.dry_run = dry_run
        self.step_counter = 0
        self.task_map = task_map or {}

    def _generate_plan_id(self) -> str:
        now = datetime.now()
        return f"P-{now.strftime('%Y%m%d')}-{now.hour:02d}{now.minute:02d}"

    def _get_task_execution_steps(self, task_id: str) -> Optional[List[Dict]]:
        task_info = self.task_map.get(task_id.upper())
        return task_info.get("steps") if task_info else None

    def create_plan(self, task_package: Dict, include_sync: bool = False) -> ExecutionPlan:
        """
        根据任务包创建执行计划。

        include_sync 默认 False：文档同步（真实 git push）在新架构里由 agent.py 主循环
        显式调用 skills.doc_sync，不再由这里自动追加到计划步骤里——这条设计在原 S02
        里就存在（PTA-RUN 调用时传 --no-sync），这次直接把默认值也改成 False，
        避免"忘记传参数就自动加了个会推送的步骤"这种情况。
        """
        task_id = task_package.get("task_id", "UNKNOWN")
        items = task_package.get("items", [])
        steps = []

        for item in items:
            item_id = item.get("id", "")
            item_name = item.get("name", "")
            execution_steps = self._get_task_execution_steps(item_id)

            if execution_steps:
                for step_def in execution_steps:
                    self.step_counter += 1
                    steps.append(ExecutionStep(
                        seq=self.step_counter, action=step_def["action"], tool=step_def["tool"],
                        command=step_def.get("command"), script=step_def.get("script"),
                        args=step_def.get("args"), description=step_def.get("description", ""),
                    ))
            else:
                self.step_counter += 1
                steps.append(ExecutionStep(
                    seq=self.step_counter, action="manual_execution", tool="bash",
                    command=f"echo '请手动执行任务: {item_name}'",
                    description=f"手动执行: {item_name}",
                ))

        return ExecutionPlan(
            plan_id=self._generate_plan_id(), task_id=task_id,
            task_name=items[0].get("name", "Unknown") if items else "Unknown",
            steps=steps,
        )

    def execute_step(self, step: ExecutionStep) -> bool:
        step.status = "running"
        step.start_time = datetime.now().isoformat()
        print(f"\n  Step {step.seq}: {step.description}")
        print(f"  Tool: {step.tool}")

        if step.tool == "bash":
            success, output = shell_exec.exec_bash(step.command, self.project_root, self.dry_run)
        elif step.tool == "python":
            success, output = shell_exec.exec_python(step.script, step.args, self.project_root, self.dry_run)
        elif step.tool == "browser-use":
            success, output = shell_exec.exec_browser_use(step.description, self.dry_run)
        else:
            success, output = shell_exec.exec_bash(step.command, self.project_root, self.dry_run)

        step.end_time = datetime.now().isoformat()
        step.output = output

        if success:
            step.status = "completed"
            print(f"  ✅ 完成")
        else:
            step.status = "failed"
            step.error = output
            print(f"  ❌ 失败: {output}")
        return success

    def execute_plan(self, plan: ExecutionPlan) -> Dict:
        print(f"\n{'='*60}\n[skills.execution_planning] 执行计划开始\n{'='*60}")
        print(f"计划 ID: {plan.plan_id}｜任务: {plan.task_id} · {plan.task_name}｜"
              f"步骤数: {len(plan.steps)}｜模式: {'DRY-RUN' if self.dry_run else '实际执行'}")

        plan.status = "running"
        plan.start_time = datetime.now().isoformat()
        completed = failed = 0

        for step in plan.steps:
            if self.execute_step(step):
                completed += 1
            else:
                failed += 1
                print(f"  ⚠️ 步骤失败，继续执行后续步骤...")

        plan.status = "completed" if failed == 0 else "failed"
        plan.end_time = datetime.now().isoformat()
        print(f"\n完成: {completed}/{len(plan.steps)}｜失败: {failed}/{len(plan.steps)}｜状态: {plan.status}")

        return {
            "plan_id": plan.plan_id, "task_id": plan.task_id, "status": plan.status,
            "completed": completed, "failed": failed, "total": len(plan.steps),
            "steps": [asdict(s) for s in plan.steps],
        }

    def to_dict(self, plan: ExecutionPlan) -> dict:
        data = asdict(plan)
        data["steps"] = [asdict(s) for s in plan.steps]
        return data
