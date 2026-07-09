#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-S05 · 归档复盘器
功能：任务完成后生成执行记录、沉淀经验教训、更新 F3 教训库
运行：python3 pta_s05_reviewer.py --plan execution_plan.json --task-id P1-01
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# ============================================================
# 配置区
# ============================================================

# 项目根目录
PROJECT_ROOT = Path("/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目")

# 执行记录目录
EXECUTION_DIR = PROJECT_ROOT / "01_execution"

# 教训库路径
LESSONS_FILE = PROJECT_ROOT / "F3_教训库.md"

# 复盘问题模板
REVIEW_QUESTIONS = [
    "任务理解是否准确？（有无偏差？）",
    "执行过程是否顺利？（有无阻塞？）",
    "产出是否符合预期？（有无遗漏？）",
    "有什么可以改进的？（工具/流程/沟通）",
]

# ============================================================


@dataclass
class ReviewReport:
    """复盘报告"""
    task_id: str
    task_name: str
    completion_time: str
    execution_summary: Dict
    lessons_learned: List[str]
    improvements: List[str]
    review_questions: Dict[str, str]


class ArchiveReviewer:
    """归档复盘器：生成执行记录，沉淀经验教训"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.execution_dir = project_root / "01_execution"
        self.lessons_file = project_root / "F3_教训库.md"
    
    def _load_plan(self, plan_path: Path) -> Dict:
        """加载执行计划"""
        return json.loads(plan_path.read_text(encoding="utf-8"))
    
    def _generate_execution_summary(self, plan: Dict) -> Dict:
        """生成执行摘要"""
        steps = plan.get("steps", [])
        
        completed = sum(1 for s in steps if s.get("status") == "completed")
        failed = sum(1 for s in steps if s.get("status") == "failed")
        total = len(steps)
        
        # 收集失败原因
        failure_reasons = []
        for step in steps:
            if step.get("status") == "failed" and step.get("error"):
                failure_reasons.append(f"Step {step['seq']}: {step['error']}")
        
        # 计算总耗时
        total_time = 0
        for step in steps:
            if step.get("start_time") and step.get("end_time"):
                try:
                    start = datetime.fromisoformat(step["start_time"])
                    end = datetime.fromisoformat(step["end_time"])
                    total_time += (end - start).total_seconds()
                except:
                    pass
        
        return {
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "success_rate": (completed / total * 100) if total > 0 else 0,
            "failure_reasons": failure_reasons,
            "total_time_seconds": total_time,
            "total_time_formatted": self._format_time(total_time),
        }
    
    def _format_time(self, seconds: float) -> str:
        """格式化时间"""
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            return f"{seconds/60:.1f}分钟"
        else:
            return f"{seconds/3600:.1f}小时"
    
    def _extract_lessons(self, plan: Dict) -> List[str]:
        """从执行过程中提取经验教训"""
        lessons = []
        steps = plan.get("steps", [])
        
        for step in steps:
            if step.get("status") == "failed":
                # 从失败中提取教训
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
                # 从成功中提取最佳实践
                if step.get("tool") == "browser-use":
                    lessons.append(f"browser-use 适合: {step.get('description')}")
                elif step.get("tool") == "python":
                    lessons.append(f"Python 脚本稳定: {step.get('description')}")
        
        return list(set(lessons))  # 去重
    
    def _generate_improvements(self, summary: Dict) -> List[str]:
        """生成改进建议"""
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
                                   plan_path: Path, outputs: List[Dict] = None) -> Path:
        """
        生成执行记录
        
        Returns:
            执行记录文件路径
        """
        plan = self._load_plan(plan_path)
        summary = self._generate_execution_summary(plan)
        lessons = self._extract_lessons(plan)
        improvements = self._generate_improvements(summary)
        
        # 创建执行记录目录
        record_dir = self.execution_dir / f"{task_id}_{task_name.replace(' ', '_')}"
        record_dir.mkdir(parents=True, exist_ok=True)
        
        record_path = record_dir / "任务执行记录.md"
        
        # 生成产出清单
        outputs_table = ""
        if outputs:
            outputs_table = "\n".join([
                f"| {o.get('name', '')} | {o.get('path', '')} | {o.get('description', '')} |"
                for o in outputs
            ])
        else:
            outputs_table = "| 执行计划 | 见执行日志 | 自动化生成的执行步骤和结果 |"
        
        # 生成步骤执行日志
        steps_log = "\n".join([
            f"- Step {s.get('seq')}: {s.get('description')} - {s.get('status', 'unknown')}"
            f"{' (Error: ' + s.get('error', '')[:50] + ')' if s.get('error') else ''}"
            for s in plan.get("steps", [])
        ])
        
        content = f"""# {task_id} · {task_name} · 任务执行记录

> 自动生成时间: {datetime.now().isoformat()}
> 生成工具: PTA-S05 归档复盘器

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
        """更新 F3 教训库"""
        if not lessons:
            return
        
        # 读取现有教训库
        existing_lessons = []
        if self.lessons_file.exists():
            content = self.lessons_file.read_text(encoding="utf-8")
            # 简单提取已有教训（以 "- LE-" 开头的行）
            for line in content.split("\n"):
                if line.strip().startswith("- LE-"):
                    existing_lessons.append(line.strip())
        
        # 生成新教训条目
        new_entries = []
        for i, lesson in enumerate(lessons, start=len(existing_lessons)+1):
            lesson_id = f"LE-{datetime.now().strftime('%Y%m%d')}-{i:03d}"
            new_entries.append(f"- {lesson_id}: {lesson}")
        
        # 追加到教训库
        with open(self.lessons_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n## {datetime.now().strftime('%Y-%m-%d')} 新增\n\n")
            for entry in new_entries:
                f.write(entry + "\n")
    
    def review(self, task_id: str, task_name: str, plan_path: Path,
               outputs: List[Dict] = None, update_lessons: bool = True) -> Dict:
        """
        执行完整复盘流程
        
        Returns:
            复盘结果摘要
        """
        print(f"\n{'='*60}")
        print(f"[PTA-S05] 归档复盘开始")
        print(f"{'='*60}")
        print(f"任务: {task_id} · {task_name}")
        print(f"{'='*60}")
        
        # 1. 生成执行记录
        record_path = self.generate_execution_record(task_id, task_name, plan_path, outputs)
        print(f"\n✅ 执行记录已生成: {record_path}")
        
        # 2. 提取经验教训
        plan = self._load_plan(plan_path)
        lessons = self._extract_lessons(plan)
        if lessons:
            print(f"\n📚 提取经验教训 ({len(lessons)} 条):")
            for lesson in lessons:
                print(f"  - {lesson}")
        
        # 3. 更新教训库
        if update_lessons and lessons:
            self.update_lessons_library(lessons)
            print(f"\n✅ 教训库已更新: {self.lessons_file}")
        
        # 4. 生成改进建议
        summary = self._generate_execution_summary(plan)
        improvements = self._generate_improvements(summary)
        print(f"\n💡 改进建议:")
        for imp in improvements:
            print(f"  - {imp}")
        
        print(f"\n{'='*60}")
        print(f"[PTA-S05] 归档复盘完成")
        print(f"{'='*60}")
        
        return {
            "task_id": task_id,
            "task_name": task_name,
            "record_path": str(record_path),
            "lessons_count": len(lessons),
            "improvements": improvements,
            "success_rate": summary["success_rate"],
        }


def main():
    parser = argparse.ArgumentParser(description="PTA-S05 · 归档复盘器")
    parser.add_argument("--plan", "-p", required=True, help="执行计划 JSON 文件路径")
    parser.add_argument("--task-id", required=True, help="任务编号")
    parser.add_argument("--task-name", required=True, help="任务名称")
    parser.add_argument("--no-lessons", action="store_true", help="不更新教训库")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="项目根目录")
    args = parser.parse_args()
    
    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"[错误] 计划文件不存在: {plan_path}")
        return 1
    
    reviewer = ArchiveReviewer(Path(args.project_root))
    result = reviewer.review(
        task_id=args.task_id,
        task_name=args.task_name,
        plan_path=plan_path,
        update_lessons=not args.no_lessons,
    )
    
    print(f"\nJSON 输出:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
