#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：进度追踪（原 PTA-S03_进度追踪器.py 的 ProgressTracker 类迁移，逻辑不变；
输入从"读计划文件"改为直接接收计划 dict，不再依赖磁盘中转）
"""

from datetime import datetime
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict


@dataclass
class ProgressReport:
    report_time: str
    plan_id: str
    task_id: str
    status: str
    completed: int
    total: int
    progress_pct: float
    steps: List[Dict]
    alerts: List[str]
    estimated_end: str


class ProgressTracker:
    """进度追踪器：监控执行状态，生成报告"""

    def __init__(self, plan: Dict):
        self.plan = plan

    def _calculate_progress(self) -> Tuple[int, int, float]:
        steps = self.plan.get("steps", [])
        total = len(steps)
        completed = sum(1 for s in steps if s.get("status") == "completed")
        if total == 0:
            return 0, 0, 0.0
        return completed, total, (completed / total) * 100

    def _detect_alerts(self) -> List[str]:
        alerts = []
        steps = self.plan.get("steps", [])
        for step in steps:
            if step.get("status") == "failed":
                alerts.append(f"Step {step.get('seq')}: {step.get('description')} - 失败: {step.get('error', 'Unknown')}")
            if step.get("status") == "running" and step.get("start_time"):
                try:
                    start = datetime.fromisoformat(step["start_time"])
                    elapsed = (datetime.now() - start).total_seconds()
                    if elapsed > 300:
                        alerts.append(f"Step {step.get('seq')}: {step.get('description')} - 运行超时 ({elapsed:.0f}s)")
                except Exception:
                    pass
        completed, total, pct = self._calculate_progress()
        if total > 0 and pct < 30 and completed > 0:
            alerts.append(f"整体进度缓慢: {pct:.1f}%")
        return alerts

    def _estimate_end(self) -> str:
        completed, total, pct = self._calculate_progress()
        if completed == 0:
            return "未知（尚未开始）"
        if completed == total:
            return "已完成"
        steps = self.plan.get("steps", [])
        total_elapsed, completed_count = 0, 0
        for step in steps:
            if step.get("status") == "completed" and step.get("start_time") and step.get("end_time"):
                try:
                    start = datetime.fromisoformat(step["start_time"])
                    end = datetime.fromisoformat(step["end_time"])
                    total_elapsed += (end - start).total_seconds()
                    completed_count += 1
                except Exception:
                    pass
        if completed_count == 0:
            return "计算中..."
        avg_time = total_elapsed / completed_count
        estimated_seconds = avg_time * (total - completed)
        if estimated_seconds < 60:
            return f"约 {estimated_seconds:.0f} 秒"
        elif estimated_seconds < 3600:
            return f"约 {estimated_seconds/60:.1f} 分钟"
        return f"约 {estimated_seconds/3600:.1f} 小时"

    def generate_report(self) -> ProgressReport:
        completed, total, pct = self._calculate_progress()
        alerts = self._detect_alerts()
        steps = self.plan.get("steps", [])
        has_failed = any(s.get("status") == "failed" for s in steps)
        all_completed = bool(steps) and all(s.get("status") == "completed" for s in steps)

        if all_completed:
            status = "已完成"
        elif has_failed:
            status = "部分失败"
        elif completed > 0:
            status = "进行中"
        else:
            status = "待开始"

        icon_map = {"completed": "✅", "failed": "❌", "running": "🔄", "pending": "⏳"}
        step_details = [{
            "seq": s.get("seq"), "description": s.get("description"), "status": s.get("status"),
            "icon": icon_map.get(s.get("status"), "❓"), "tool": s.get("tool"),
        } for s in steps]

        return ProgressReport(
            report_time=datetime.now().isoformat(), plan_id=self.plan.get("plan_id", "Unknown"),
            task_id=self.plan.get("task_id", "Unknown"), status=status, completed=completed,
            total=total, progress_pct=pct, steps=step_details, alerts=alerts,
            estimated_end=self._estimate_end(),
        )

    def print_report(self, report: ProgressReport):
        print(f"\n{'='*60}\n[skills.progress_tracking] 进度报告\n{'='*60}")
        print(f"总体进度: {report.completed}/{report.total} ({report.progress_pct:.1f}%)｜状态: {report.status}")
        for step in report.steps:
            print(f"  {step['icon']} Step {step['seq']}: [{step['tool']}] {step['description']}")
        if report.alerts:
            print(f"\n⚠️ 异常预警:")
            for alert in report.alerts:
                print(f"  - {alert}")
        print(f"\n预计完成: {report.estimated_end}\n{'='*60}")

    def to_dict(self, report: ProgressReport) -> dict:
        return asdict(report)
