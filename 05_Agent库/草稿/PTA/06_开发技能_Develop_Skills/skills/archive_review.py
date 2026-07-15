#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：归档复盘（原 PTA-S05_归档复盘器.py 的 ArchiveReviewer 类迁移）

迁移改动：
1. 输入从"读计划文件路径"改为直接接收计划 dict（与 progress_tracking 一致，
   不再依赖磁盘中转，agent.py 主循环里计划本来就是内存对象）。
2. execution_record 生成的唯一归属定为本文件——原 S04 里同名但从未被真实调用
   的重复实现已在迁移 skills/doc_sync.py 时删除，不存在"两处不同实现"的风险。
3. project_root 由调用方（agents/agent.py）显式传入并在整个调用链路内全程复用
   同一个内存对象，不再有"CLI 参数在多级 subprocess 之间转发时漏传"的可能——
   这正是旧架构里 PTA-RUN 调 S05 漏传 --project-root、导致执行记录写进错误
   项目目录那个真实 bug 的结构性解法。
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ReviewReport:
    task_id: str
    task_name: str
    completion_time: str
    execution_summary: Dict
    lessons_learned: List[str]
    improvements: List[str]


class ArchiveReviewer:
    """归档复盘器：生成执行记录，沉淀经验教训"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.execution_dir = project_root / "01_execution"
        self.lessons_file = project_root / "F3_教训库.md"

    def _generate_execution_summary(self, plan: Dict) -> Dict:
        steps = plan.get("steps", [])
        completed = sum(1 for s in steps if s.get("status") == "completed")
        failed = sum(1 for s in steps if s.get("status") == "failed")
        total = len(steps)

        failure_reasons = [f"Step {s['seq']}: {s['error']}" for s in steps
                            if s.get("status") == "failed" and s.get("error")]

        total_time = 0
        for step in steps:
            if step.get("start_time") and step.get("end_time"):
                try:
                    start = datetime.fromisoformat(step["start_time"])
                    end = datetime.fromisoformat(step["end_time"])
                    total_time += (end - start).total_seconds()
                except Exception:
                    pass

        return {
            "total_steps": total, "completed": completed, "failed": failed,
            "success_rate": (completed / total * 100) if total > 0 else 0,
            "failure_reasons": failure_reasons, "total_time_seconds": total_time,
            "total_time_formatted": self._format_time(total_time),
        }

    def _format_time(self, seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            return f"{seconds/60:.1f}分钟"
        return f"{seconds/3600:.1f}小时"

    def _extract_lessons(self, plan: Dict) -> List[str]:
        lessons = []
        for step in plan.get("steps", []):
            if step.get("status") == "failed":
                error = step.get("error", "")
                if "不存在" in error or "not found" in error.lower():
                    lessons.append(f"执行前需验证文件/脚本存在性: {step.get('description')}")
                elif "超时" in error or "timeout" in error.lower():
                    lessons.append(f"考虑增加超时时间或优化性能: {step.get('description')}")
                elif "权限" in error or "permission" in error.lower():
                    lessons.append(f"检查权限配置: {step.get('description')}")
                else:
                    lessons.append(f"失败经验: {step.get('description')} - {error[:50]}")
            elif step.get("status") == "completed":
                if step.get("tool") == "browser-use":
                    lessons.append(f"browser-use 适合: {step.get('description')}")
                elif step.get("tool") == "python":
                    lessons.append(f"Python 脚本稳定: {step.get('description')}")
        return list(set(lessons))

    def _generate_improvements(self, summary: Dict) -> List[str]:
        improvements = []
        if summary["failed"] > 0:
            improvements.append("增加前置检查（文件存在性、权限验证）")
            improvements.append("完善错误处理机制")
        if summary["success_rate"] < 80:
            improvements.append("优化任务分解粒度，减少单步骤复杂度")
        if summary["total_time_seconds"] > 300:
            improvements.append("考虑并行执行独立步骤")
        if not improvements:
            improvements.append("当前流程良好，继续保持")
        return improvements

    def generate_execution_record(self, task_id: str, task_name: str,
                                    plan: Dict, outputs: List[Dict] = None) -> Path:
        summary = self._generate_execution_summary(plan)
        lessons = self._extract_lessons(plan)
        improvements = self._generate_improvements(summary)

        record_dir = self.execution_dir / f"{task_id}_{task_name.replace(' ', '_')}"
        record_dir.mkdir(parents=True, exist_ok=True)
        record_path = record_dir / "任务执行记录.md"

        if outputs:
            outputs_table = "\n".join([
                f"| {o.get('name', '')} | {o.get('path', '')} | {o.get('description', '')} |"
                for o in outputs
            ])
        else:
            outputs_table = "| 执行计划 | 见执行日志 | 自动化生成的执行步骤和结果 |"

        steps_log = "\n".join([
            f"- Step {s.get('seq')}: {s.get('description')} - {s.get('status', 'unknown')}"
            f"{' (Error: ' + s.get('error', '')[:50] + ')' if s.get('error') else ''}"
            for s in plan.get("steps", [])
        ])

        content = f"""# {task_id} · {task_name} · 任务执行记录

> 自动生成时间: {datetime.now().isoformat()}
> 生成工具: skills.archive_review

---

## 任务信息

| 字段 | 内容 |
|------|------|
| 任务编号 | {task_id} |
| 任务名称 | {task_name} |
| 完成时间 | {datetime.now().isoformat()} |
| 执行结果 | {summary['completed']}/{summary['total_steps']} 成功 ({summary['success_rate']:.0f}%) |
| 总耗时 | {summary['total_time_formatted']} |

## 执行摘要

| 指标 | 数值 |
|------|------|
| 总步骤 | {summary['total_steps']} |
| 完成 | {summary['completed']} |
| 失败 | {summary['failed']} |
| 成功率 | {summary['success_rate']:.1f}% |

## 步骤执行日志

{steps_log}

## 产出清单

| 产出 | 路径 | 说明 |
|------|------|------|
{outputs_table}

## 经验教训

{chr(10).join(['- ' + l for l in lessons]) if lessons else '- 无特别经验'}

## 改进建议

{chr(10).join(['- ' + i for i in improvements]) if improvements else '- 无改进建议'}

---

> 归档时间: {datetime.now().isoformat()}
> 下次复盘: 同类任务执行 3 次后
"""
        record_path.write_text(content, encoding="utf-8")
        return record_path

    def update_lessons_library(self, lessons: List[str]):
        if not lessons:
            return
        existing_lessons = []
        if self.lessons_file.exists():
            content = self.lessons_file.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.strip().startswith("- LE-"):
                    existing_lessons.append(line.strip())

        new_entries = []
        for i, lesson in enumerate(lessons, start=len(existing_lessons) + 1):
            lesson_id = f"LE-{datetime.now().strftime('%Y%m%d')}-{i:03d}"
            new_entries.append(f"- {lesson_id}: {lesson}")

        with open(self.lessons_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n## {datetime.now().strftime('%Y-%m-%d')} 新增\n\n")
            for entry in new_entries:
                f.write(entry + "\n")

    def review(self, task_id: str, task_name: str, plan: Dict,
               outputs: List[Dict] = None, update_lessons: bool = True) -> Dict:
        print(f"\n{'='*60}\n[skills.archive_review] 归档复盘开始\n{'='*60}")
        print(f"任务: {task_id} · {task_name}")

        record_path = self.generate_execution_record(task_id, task_name, plan, outputs)
        print(f"\n✅ 执行记录已生成: {record_path}")

        lessons = self._extract_lessons(plan)
        if lessons:
            print(f"\n📚 提取经验教训 ({len(lessons)} 条):")
            for lesson in lessons:
                print(f"  - {lesson}")

        if update_lessons and lessons:
            self.update_lessons_library(lessons)
            print(f"\n✅ 教训库已更新: {self.lessons_file}")

        summary = self._generate_execution_summary(plan)
        improvements = self._generate_improvements(summary)
        print(f"\n💡 改进建议:")
        for imp in improvements:
            print(f"  - {imp}")

        print(f"\n{'='*60}\n[skills.archive_review] 归档复盘完成\n{'='*60}")

        return {
            "task_id": task_id, "task_name": task_name, "record_path": str(record_path),
            "lessons_count": len(lessons), "improvements": improvements,
            "success_rate": summary["success_rate"],
        }
