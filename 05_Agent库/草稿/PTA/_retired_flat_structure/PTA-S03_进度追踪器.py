#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-S03 · 进度追踪器
功能：监控任务执行状态，生成进度报告，检测异常并预警
运行：python3 pta_s03_tracker.py --plan execution_plan.json [--watch]
"""

import json
import time
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# ============================================================
# 配置区
# ============================================================

# 进度报告模板
PROGRESS_TEMPLATE = """
{'='*60}
[PTA-S03] 进度报告
{'='*60}
报告时间: {report_time}
计划 ID: {plan_id}
任务: {task_id}
{'='*60}

总体进度: {completed}/{total} ({progress_pct}%)
状态: {status}

{'步骤详情:' if steps else '无步骤'}
{step_details}

{'异常预警:' if alerts else '无异常'}
{alert_details}

{'='*60}
预计完成: {estimated_end}
{'='*60}
"""

# ============================================================


@dataclass
class ProgressReport:
    """进度报告"""
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
    
    def __init__(self, plan_path: Path):
        self.plan_path = plan_path
        self.plan = self._load_plan()
    
    def _load_plan(self) -> Dict:
        """加载执行计划"""
        return json.loads(self.plan_path.read_text(encoding="utf-8"))
    
    def _calculate_progress(self) -> Tuple[int, int, float]:
        """计算进度"""
        steps = self.plan.get("steps", [])
        total = len(steps)
        completed = sum(1 for s in steps if s.get("status") == "completed")
        failed = sum(1 for s in steps if s.get("status") == "failed")
        
        if total == 0:
            return 0, 0, 0.0
        
        # 完成率 = 完成 / 总数
        # 如果有失败，进度为完成 / 总数，但状态为 failed
        progress_pct = (completed / total) * 100
        
        return completed, total, progress_pct
    
    def _detect_alerts(self) -> List[str]:
        """检测异常"""
        alerts = []
        steps = self.plan.get("steps", [])
        
        for step in steps:
            if step.get("status") == "failed":
                alerts.append(f"Step {step.get('seq')}: {step.get('description')} - 失败: {step.get('error', 'Unknown')}")
            
            # 检测超时（步骤运行超过 5 分钟）
            if step.get("status") == "running" and step.get("start_time"):
                try:
                    start = datetime.fromisoformat(step["start_time"])
                    elapsed = (datetime.now() - start).total_seconds()
                    if elapsed > 300:  # 5 分钟
                        alerts.append(f"Step {step.get('seq')}: {step.get('description')} - 运行超时 ({elapsed:.0f}s)")
                except:
                    pass
        
        # 检测整体进度滞后
        completed, total, pct = self._calculate_progress()
        if total > 0 and pct < 30 and completed > 0:
            alerts.append(f"整体进度缓慢: {pct:.1f}%")
        
        return alerts
    
    def _estimate_end(self) -> str:
        """估算完成时间"""
        completed, total, pct = self._calculate_progress()
        
        if completed == 0:
            return "未知（尚未开始）"
        
        if completed == total:
            return "已完成"
        
        # 简单估算：基于平均步骤时间
        steps = self.plan.get("steps", [])
        total_elapsed = 0
        completed_count = 0
        
        for step in steps:
            if step.get("status") == "completed" and step.get("start_time") and step.get("end_time"):
                try:
                    start = datetime.fromisoformat(step["start_time"])
                    end = datetime.fromisoformat(step["end_time"])
                    elapsed = (end - start).total_seconds()
                    total_elapsed += elapsed
                    completed_count += 1
                except:
                    pass
        
        if completed_count == 0:
            return "计算中..."
        
        avg_time = total_elapsed / completed_count
        remaining = total - completed
        estimated_seconds = avg_time * remaining
        
        if estimated_seconds < 60:
            return f"约 {estimated_seconds:.0f} 秒"
        elif estimated_seconds < 3600:
            return f"约 {estimated_seconds/60:.1f} 分钟"
        else:
            return f"约 {estimated_seconds/3600:.1f} 小时"
    
    def generate_report(self) -> ProgressReport:
        """生成进度报告"""
        completed, total, pct = self._calculate_progress()
        alerts = self._detect_alerts()
        
        # 确定状态
        steps = self.plan.get("steps", [])
        has_failed = any(s.get("status") == "failed" for s in steps)
        all_completed = all(s.get("status") == "completed" for s in steps)
        
        if all_completed:
            status = "已完成"
        elif has_failed:
            status = "部分失败"
        elif completed > 0:
            status = "进行中"
        else:
            status = "待开始"
        
        # 步骤详情
        step_details = []
        for step in steps:
            status_icon = {
                "completed": "✅",
                "failed": "❌",
                "running": "🔄",
                "pending": "⏳",
            }.get(step.get("status"), "❓")
            
            step_details.append({
                "seq": step.get("seq"),
                "description": step.get("description"),
                "status": step.get("status"),
                "icon": status_icon,
                "tool": step.get("tool"),
            })
        
        return ProgressReport(
            report_time=datetime.now().isoformat(),
            plan_id=self.plan.get("plan_id", "Unknown"),
            task_id=self.plan.get("task_id", "Unknown"),
            status=status,
            completed=completed,
            total=total,
            progress_pct=pct,
            steps=step_details,
            alerts=alerts,
            estimated_end=self._estimate_end(),
        )
    
    def print_report(self, report: ProgressReport):
        """打印进度报告"""
        print(f"\n{'='*60}")
        print(f"[PTA-S03] 进度报告")
        print(f"{'='*60}")
        print(f"报告时间: {report.report_time}")
        print(f"计划 ID: {report.plan_id}")
        print(f"任务: {report.task_id}")
        print(f"{'='*60}")
        print(f"\n总体进度: {report.completed}/{report.total} ({report.progress_pct:.1f}%)")
        print(f"状态: {report.status}")
        
        if report.steps:
            print(f"\n步骤详情:")
            for step in report.steps:
                print(f"  {step['icon']} Step {step['seq']}: [{step['tool']}] {step['description']}")
        
        if report.alerts:
            print(f"\n⚠️ 异常预警:")
            for alert in report.alerts:
                print(f"  - {alert}")
        else:
            print(f"\n✅ 无异常")
        
        print(f"\n{'='*60}")
        print(f"预计完成: {report.estimated_end}")
        print(f"{'='*60}")
    
    def watch(self, interval: int = 10):
        """持续监控模式"""
        print(f"[PTA-S03] 启动持续监控，间隔: {interval}s")
        print(f"按 Ctrl+C 停止\n")
        
        try:
            while True:
                # 重新加载计划（可能被其他进程更新）
                self.plan = self._load_plan()
                
                report = self.generate_report()
                self.print_report(report)
                
                if report.status in ["已完成", "部分失败"]:
                    print(f"\n[PTA-S03] 任务已结束，停止监控")
                    break
                
                print(f"\n等待 {interval}s 后刷新...")
                time.sleep(interval)
        
        except KeyboardInterrupt:
            print(f"\n[PTA-S03] 监控已停止")


def main():
    parser = argparse.ArgumentParser(description="PTA-S03 · 进度追踪器")
    parser.add_argument("--plan", "-p", required=True, help="执行计划 JSON 文件路径")
    parser.add_argument("--watch", "-w", action="store_true", help="持续监控模式")
    parser.add_argument("--interval", "-i", type=int, default=10, help="监控间隔（秒）")
    parser.add_argument("--output", "-o", help="输出报告 JSON 文件路径")
    args = parser.parse_args()
    
    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"[错误] 计划文件不存在: {plan_path}")
        return 1
    
    tracker = ProgressTracker(plan_path)
    
    if args.watch:
        tracker.watch(args.interval)
    else:
        report = tracker.generate_report()
        tracker.print_report(report)
        
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n报告已保存: {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
