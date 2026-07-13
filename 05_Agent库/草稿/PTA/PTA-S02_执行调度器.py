#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-S02 · 执行调度器
功能：将结构化任务包分解为可执行步骤，调度工具（Python/browser-use/Git）执行
运行：python3 pta_s02_scheduler.py --input task_package.json [--dry-run]
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict

# ============================================================
# 配置区
# ============================================================

# 项目根目录
PROJECT_ROOT = Path("/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目")

# 任务到执行步骤的映射（知识库）
TASK_EXECUTION_MAP = {
    "P0-02": {
        "name": "前端 Vercel 部署",
        "steps": [
            {"action": "check_build", "tool": "bash", "command": "cd app_v2 && npm run build", "description": "检查前端构建"},
            {"action": "deploy_vercel", "tool": "bash", "command": "cd app_v2 && vercel --prod", "description": "部署到 Vercel"},
            {"action": "verify_url", "tool": "browser-use", "description": "验证部署 URL 可访问"},
        ]
    },
    "P0-03": {
        "name": "MCP Server 公开",
        "steps": [
            {"action": "test_local", "tool": "bash", "command": "cd process-db-mcp && node src/test-local.mjs", "description": "本地测试 MCP Server"},
            {"action": "git_push", "tool": "bash", "command": "cd process-db-mcp && git push", "description": "推送到 GitHub"},
            {"action": "verify_repo", "tool": "browser-use", "description": "验证 GitHub 仓库可访问"},
        ]
    },
    "P1-01": {
        "name": "PAY-COM 价值节点一致性校验",
        "steps": [
            {"action": "run_validation", "tool": "python", "script": "validate_vn_consistency.py", "description": "运行一致性校验脚本"},
            {"action": "generate_report", "tool": "python", "script": "generate_html_report.py", "description": "生成 HTML 报告"},
            {"action": "screenshot", "tool": "browser-use", "description": "browser-use 截图证据"},
        ]
    },
    "P1-02": {
        "name": "价值节点信号提取自动化",
        "steps": [
            {"action": "extract_signals", "tool": "python", "script": "extract_signals.py", "args": ["--domain", "PAY"], "description": "提取 PAY 域信号"},
            {"action": "verify_output", "tool": "bash", "command": "ls -la outputs/", "description": "验证输出文件"},
        ]
    },
    "P1-03": {
        "name": "信号提取扩展到全量72节点",
        "steps": [
            {"action": "extract_all", "tool": "python", "script": "extract_signals.py", "args": ["--all"], "description": "全量信号提取"},
            {"action": "verify_count", "tool": "bash", "command": "wc -l outputs/*baseline*.md", "description": "验证节点数量"},
        ]
    },
    "P1-04": {
        "name": "访谈规则继承",
        "steps": [
            {"action": "merge_rules", "tool": "python", "script": "merge_interview_rules.py", "description": "合并访谈规则"},
            {"action": "verify_coverage", "tool": "bash", "command": "grep -c 'A类' outputs/*.md", "description": "验证规则覆盖率"},
        ]
    },
    "P2-01": {
        "name": "PTA Agent 搭建",
        "steps": [
            {"action": "develop_s01", "tool": "python", "script": "PTA-S01_意图解析器.py", "description": "开发意图解析器"},
            {"action": "develop_s02", "tool": "python", "script": "PTA-S02_执行调度器.py", "description": "开发执行调度器"},
            {"action": "develop_s04", "tool": "python", "script": "PTA-S04_文档同步器.py", "description": "开发文档同步器"},
            {"action": "test_integration", "tool": "bash", "command": "bash test_pta_integration.sh", "description": "集成测试"},
        ]
    },
    "P2-02": {
        "name": "模型选型矩阵",
        "steps": [
            {"action": "research_models", "tool": "browser-use", "description": "调研主流模型能力"},
            {"action": "create_matrix", "tool": "python", "script": "create_model_matrix.py", "description": "生成选型矩阵"},
        ]
    },
    "P2-03": {
        "name": "Skill 公开发布",
        "steps": [
            {"action": "package_skill", "tool": "bash", "command": "mkdir -p skill_package && cp -r scripts/* skill_package/", "description": "打包 Skill"},
            {"action": "publish", "tool": "bash", "command": "git push", "description": "发布到 GitHub"},
        ]
    },
}

# 工具执行器映射
TOOL_EXECUTORS = {
    "bash": "_exec_bash",
    "python": "_exec_python",
    "browser-use": "_exec_browser_use",
}

# ============================================================


@dataclass
class ExecutionStep:
    """执行步骤"""
    seq: int
    action: str
    tool: str
    command: Optional[str] = None
    script: Optional[str] = None
    args: Optional[List[str]] = None
    description: str = ""
    status: str = "pending"  # pending / running / completed / failed
    output: str = ""
    error: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None


@dataclass
class ExecutionPlan:
    """执行计划"""
    plan_id: str
    task_id: str
    task_name: str
    steps: List[ExecutionStep]
    status: str = "pending"  # pending / running / completed / failed
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class ExecutionScheduler:
    """执行调度器：将任务包分解为执行步骤并调度执行"""
    
    def __init__(self, project_root: Path, dry_run: bool = False):
        self.project_root = project_root
        self.dry_run = dry_run
        self.step_counter = 0
    
    def _generate_plan_id(self) -> str:
        """生成计划 ID"""
        now = datetime.now()
        return f"P-{now.strftime('%Y%m%d')}-{now.hour:02d}{now.minute:02d}"
    
    def _get_task_execution_steps(self, task_id: str) -> Optional[List[Dict]]:
        """从知识库获取任务的执行步骤"""
        task_info = TASK_EXECUTION_MAP.get(task_id.upper())
        if task_info:
            return task_info["steps"]
        return None
    
    def create_plan(self, task_package: Dict, include_sync: bool = True) -> ExecutionPlan:
        """
        根据任务包创建执行计划

        Args:
            task_package: PTA-S01 输出的结构化任务包（JSON/dict）
            include_sync: 是否自动追加文档同步步骤（会触发 PTA-S04 的真实 git push，
                          无人值守/编排器场景应传 False，同步改为显式的独立确认步骤）

        Returns:
            ExecutionPlan: 执行计划
        """
        task_id = task_package.get("task_id", "UNKNOWN")
        items = task_package.get("items", [])
        task_type = task_package.get("type", "execute")
        constraints = task_package.get("constraints", [])
        
        steps = []
        
        for item in items:
            item_id = item.get("id", "")
            item_name = item.get("name", "")
            
            # 从知识库获取执行步骤
            execution_steps = self._get_task_execution_steps(item_id)
            
            if execution_steps:
                for step_def in execution_steps:
                    self.step_counter += 1
                    steps.append(ExecutionStep(
                        seq=self.step_counter,
                        action=step_def["action"],
                        tool=step_def["tool"],
                        command=step_def.get("command"),
                        script=step_def.get("script"),
                        args=step_def.get("args"),
                        description=step_def.get("description", ""),
                    ))
            else:
                # 未知任务，创建通用步骤
                self.step_counter += 1
                steps.append(ExecutionStep(
                    seq=self.step_counter,
                    action="manual_execution",
                    tool="bash",
                    command=f"echo '请手动执行任务: {item_name}'",
                    description=f"手动执行: {item_name}",
                ))
        
        # 如果约束包含 sync，添加文档同步步骤（会触发真实 git push，需 include_sync=True 且经人工确认）
        if include_sync and ("sync" in constraints or task_type in ["execute", "sequential"]):
            self.step_counter += 1
            steps.append(ExecutionStep(
                seq=self.step_counter,
                action="sync_documents",
                tool="python",
                script="PTA-S04_文档同步器.py",
                args=["--task-id", task_id, "--task-name", item_name, "--message", f"feat: complete {task_id}"],
                description="同步文档（Git + 看板 + 执行记录）",
            ))
        
        return ExecutionPlan(
            plan_id=self._generate_plan_id(),
            task_id=task_id,
            task_name=items[0].get("name", "Unknown") if items else "Unknown",
            steps=steps,
        )
    
    def _exec_bash(self, step: ExecutionStep) -> Tuple[bool, str]:
        """执行 Bash 命令"""
        if not step.command:
            return False, "无命令"
        
        if self.dry_run:
            return True, f"[DRY-RUN] {step.command}"
        
        try:
            result = subprocess.run(
                step.command,
                shell=True,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "命令超时"
        except Exception as e:
            return False, str(e)
    
    def _exec_python(self, step: ExecutionStep) -> Tuple[bool, str]:
        """执行 Python 脚本"""
        if not step.script:
            return False, "无脚本"
        
        script_path = self.project_root / step.script
        if not script_path.exists():
            # 尝试在子目录中查找
            for subdir in ["05_Agent库/草稿/PTA", "01_execution", "scripts"]:
                alt_path = self.project_root / subdir / step.script
                if alt_path.exists():
                    script_path = alt_path
                    break

        if not script_path.exists():
            # 兜底：递归查找（覆盖 01_execution/P1-02_xxx/ 等嵌套子任务目录）
            matches = [
                m for m in self.project_root.rglob(step.script)
                if ".git" not in m.parts
            ]
            if matches:
                script_path = matches[0]

        if not script_path.exists():
            return False, f"脚本不存在: {step.script}"
        
        cmd = ["python3", str(script_path)]
        if step.args:
            cmd.extend(step.args)
        
        if self.dry_run:
            return True, f"[DRY-RUN] {' '.join(cmd)}"
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "脚本超时"
        except Exception as e:
            return False, str(e)
    
    def _exec_browser_use(self, step: ExecutionStep) -> Tuple[bool, str]:
        """执行 browser-use 操作（模拟）"""
        if self.dry_run:
            return True, f"[DRY-RUN] browser-use: {step.description}"
        
        # browser-use 需要 MCP 调用，这里返回提示
        return True, f"[browser-use] 请手动执行: {step.description}\n提示: 使用 browser-use MCP 进行网页操作"
    
    def execute_step(self, step: ExecutionStep) -> bool:
        """执行单个步骤"""
        step.status = "running"
        step.start_time = datetime.now().isoformat()
        
        print(f"\n  Step {step.seq}: {step.description}")
        print(f"  Tool: {step.tool}")
        
        # 选择执行器
        executor_name = TOOL_EXECUTORS.get(step.tool, "_exec_bash")
        executor = getattr(self, executor_name, self._exec_bash)
        
        success, output = executor(step)
        
        step.end_time = datetime.now().isoformat()
        step.output = output
        
        if success:
            step.status = "completed"
            print(f"  ✅ 完成")
            if output:
                print(f"  Output: {output[:200]}..." if len(output) > 200 else f"  Output: {output}")
        else:
            step.status = "failed"
            step.error = output
            print(f"  ❌ 失败: {output}")
        
        return success
    
    def execute_plan(self, plan: ExecutionPlan) -> Dict:
        """
        执行完整计划
        
        Returns:
            执行结果摘要
        """
        print(f"\n{'='*60}")
        print(f"[PTA-S02] 执行计划开始")
        print(f"{'='*60}")
        print(f"计划 ID: {plan.plan_id}")
        print(f"任务: {plan.task_id} · {plan.task_name}")
        print(f"步骤数: {len(plan.steps)}")
        print(f"模式: {'DRY-RUN' if self.dry_run else '实际执行'}")
        print(f"{'='*60}")
        
        plan.status = "running"
        plan.start_time = datetime.now().isoformat()
        
        completed = 0
        failed = 0
        
        for step in plan.steps:
            success = self.execute_step(step)
            if success:
                completed += 1
            else:
                failed += 1
                # 失败时是否继续？默认继续（记录错误）
                print(f"  ⚠️ 步骤失败，继续执行后续步骤...")
        
        plan.status = "completed" if failed == 0 else "failed"
        plan.end_time = datetime.now().isoformat()
        
        print(f"\n{'='*60}")
        print(f"[PTA-S02] 执行计划完成")
        print(f"{'='*60}")
        print(f"完成: {completed}/{len(plan.steps)}")
        print(f"失败: {failed}/{len(plan.steps)}")
        print(f"状态: {plan.status}")
        print(f"{'='*60}")
        
        return {
            "plan_id": plan.plan_id,
            "task_id": plan.task_id,
            "status": plan.status,
            "completed": completed,
            "failed": failed,
            "total": len(plan.steps),
            "steps": [asdict(s) for s in plan.steps],
        }
    
    def to_json(self, plan: ExecutionPlan) -> str:
        """将执行计划转换为 JSON"""
        data = asdict(plan)
        data["steps"] = [asdict(s) for s in plan.steps]
        return json.dumps(data, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="PTA-S02 · 执行调度器")
    parser.add_argument("--input", "-i", required=True, help="输入任务包 JSON 文件路径")
    parser.add_argument("--output", "-o", help="输出执行计划 JSON 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式")
    parser.add_argument("--no-sync", action="store_true", help="不自动追加文档同步（git push）步骤")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="项目根目录")
    args = parser.parse_args()

    # 读取任务包
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[错误] 输入文件不存在: {input_path}")
        sys.exit(1)

    task_package = json.loads(input_path.read_text(encoding="utf-8"))

    # 创建调度器
    scheduler = ExecutionScheduler(Path(args.project_root), dry_run=args.dry_run)

    # 创建执行计划
    plan = scheduler.create_plan(task_package, include_sync=not args.no_sync)
    
    print(f"\n{'='*60}")
    print(f"[PTA-S02] 执行计划已生成")
    print(f"{'='*60}")
    print(f"计划 ID: {plan.plan_id}")
    print(f"任务: {plan.task_id}")
    print(f"步骤:")
    for step in plan.steps:
        print(f"  {step.seq}. [{step.tool}] {step.description}")
    print(f"{'='*60}")
    
    # 执行计划
    result = scheduler.execute_plan(plan)
    
    # 保存结果
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已保存: {output_path}")


if __name__ == "__main__":
    main()
