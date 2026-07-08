#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-S04 · 文档同步器
功能：任务完成后自动同步文档（Git 提交 + 看板更新 + 执行记录）
运行：python3 pta_s04_sync.py [--message "提交信息"] [--kanban] [--git]
"""

import os
import re
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ============================================================
# 配置区
# ============================================================

# 项目根目录（实验环境）
PROJECT_ROOT = Path("/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目")

# 看板文件路径
KANBAN_PATH = PROJECT_ROOT / "能力整改看板.md"

# 执行记录目录
EXECUTION_DIR = PROJECT_ROOT / "01_execution"

# Git 配置
GIT_REMOTE = "origin"
GIT_BRANCH = "main"

# ============================================================


class DocumentSyncer:
    """文档同步器：自动完成 Git 提交、看板更新、执行记录生成"""
    
    def __init__(self, project_root: Path, dry_run: bool = False):
        self.project_root = project_root
        self.dry_run = dry_run
        self.kanban_path = project_root / "能力整改看板.md"
        self.execution_dir = project_root / "01_execution"
        self.results = {
            "git": {"status": "pending", "details": ""},
            "kanban": {"status": "pending", "details": ""},
            "execution_record": {"status": "pending", "details": ""},
        }
    
    def _run_git(self, args: List[str], cwd: Path = None) -> Tuple[int, str, str]:
        """运行 Git 命令"""
        cwd = cwd or self.project_root
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Git 命令超时"
        except FileNotFoundError:
            return -1, "", "Git 未安装"
    
    def sync_git(self, message: str, files: List[str] = None) -> bool:
        """
        Git 同步：add → commit → push
        
        Args:
            message: 提交信息
            files: 指定文件列表（None 则添加所有变更）
        """
        print(f"\n[PTA-S04] Git 同步开始...")
        
        if self.dry_run:
            print(f"  [DRY-RUN] 将执行: git add + commit '{message}' + push")
            self.results["git"]["status"] = "dry_run"
            return True
        
        # Step 1: git add
        if files:
            for f in files:
                returncode, stdout, stderr = self._run_git(["add", f])
                if returncode != 0:
                    self.results["git"]["status"] = "failed"
                    self.results["git"]["details"] = f"git add 失败: {stderr}"
                    print(f"  ❌ git add 失败: {stderr}")
                    return False
        else:
            returncode, stdout, stderr = self._run_git(["add", "."])
            if returncode != 0:
                self.results["git"]["status"] = "failed"
                self.results["git"]["details"] = f"git add 失败: {stderr}"
                print(f"  ❌ git add 失败: {stderr}")
                return False
        
        # Step 2: git commit
        returncode, stdout, stderr = self._run_git(["commit", "-m", message])
        if returncode != 0:
            if "nothing to commit" in stderr or "nothing to commit" in stdout:
                self.results["git"]["status"] = "skipped"
                self.results["git"]["details"] = "无变更需要提交"
                print(f"  ℹ️ 无变更需要提交")
                return True
            else:
                self.results["git"]["status"] = "failed"
                self.results["git"]["details"] = f"git commit 失败: {stderr}"
                print(f"  ❌ git commit 失败: {stderr}")
                return False
        
        commit_hash = stdout.strip().split()[-1] if stdout else "unknown"
        print(f"  ✅ git commit 成功: {commit_hash[:8]}")
        
        # Step 3: git push
        returncode, stdout, stderr = self._run_git(["push", GIT_REMOTE, GIT_BRANCH])
        if returncode != 0:
            self.results["git"]["status"] = "failed"
            self.results["git"]["details"] = f"git push 失败: {stderr}"
            print(f"  ❌ git push 失败: {stderr}")
            return False
        
        self.results["git"]["status"] = "success"
        self.results["git"]["details"] = f"commit: {commit_hash[:8]}"
        print(f"  ✅ git push 成功")
        return True
    
    def update_kanban(self, task_id: str, status: str = "已完成", progress: str = None) -> bool:
        """
        更新看板
        
        Args:
            task_id: 任务编号（如 P1-01, P0-02）
            status: 新状态（已完成/进行中/待启动）
            progress: 进度更新（如 55%→60%）
        """
        print(f"\n[PTA-S04] 看板更新开始...")
        
        if not self.kanban_path.exists():
            self.results["kanban"]["status"] = "failed"
            self.results["kanban"]["details"] = "看板文件不存在"
            print(f"  ❌ 看板文件不存在: {self.kanban_path}")
            return False
        
        content = self.kanban_path.read_text(encoding="utf-8")
        
        # 查找任务行并更新状态
        # 匹配格式: - [ ] P1-01 · 任务名称 或 - [x] P1-01 · 任务名称
        pattern = rf"(- \[([ x])\]) ({re.escape(task_id)})"
        
        def replace_status(match):
            checkbox = match.group(1)
            current_status = match.group(2)
            task = match.group(3)
            
            if status == "已完成":
                new_checkbox = "- [x]"
            elif status == "进行中":
                new_checkbox = "- [ ]"
            else:
                new_checkbox = checkbox
            
            return f"{new_checkbox} {task}"
        
        new_content = re.sub(pattern, replace_status, content)
        
        # 更新进度（如果提供）
        if progress:
            # 匹配进度百分比
            progress_pattern = rf"(\| {re.escape(task_id)}.*?\|)(\d+%)(\|)"
            new_content = re.sub(progress_pattern, rf"\1{progress}\3", new_content)
        
        if self.dry_run:
            print(f"  [DRY-RUN] 将更新看板: {task_id} → {status}")
            self.results["kanban"]["status"] = "dry_run"
            return True
        
        self.kanban_path.write_text(new_content, encoding="utf-8")
        
        self.results["kanban"]["status"] = "success"
        self.results["kanban"]["details"] = f"{task_id} → {status}"
        print(f"  ✅ 看板更新成功: {task_id} → {status}")
        return True
    
    def generate_execution_record(self, task_id: str, task_name: str, 
                                   outputs: List[Dict], lessons: List[str] = None) -> bool:
        """
        生成执行记录
        
        Args:
            task_id: 任务编号
            task_name: 任务名称
            outputs: 产出清单 [{"name": "", "path": "", "description": ""}]
            lessons: 经验教训列表
        """
        print(f"\n[PTA-S04] 执行记录生成开始...")
        
        record_dir = self.execution_dir / f"{task_id}_{task_name.replace(' ', '_')}"
        record_dir.mkdir(parents=True, exist_ok=True)
        
        record_path = record_dir / "任务执行记录.md"
        
        now = datetime.now().isoformat()
        
        outputs_table = "\n".join([
            f"| {o['name']} | {o['path']} | {o.get('description', '')} |"
            for o in outputs
        ])
        
        lessons_section = ""
        if lessons:
            lessons_list = "\n".join([f"- {l}" for l in lessons])
            lessons_section = f"""
### 踩坑记录

{lessons_list}
"""
        
        content = f"""# {task_id} · {task_name} · 任务执行记录

> 自动生成时间: {now}
> 生成工具: PTA-S04 文档同步器

---

## 任务信息

| 字段 | 内容 |
|------|------|
| 任务编号 | {task_id} |
| 任务名称 | {task_name} |
| 完成时间 | {now} |

## 产出清单

| 产出 | 路径 | 说明 |
|------|------|------|
| {outputs_table}

{lessons_section}

---

> 归档时间: {now}
"""
        
        if self.dry_run:
            print(f"  [DRY-RUN] 将生成执行记录: {record_path}")
            self.results["execution_record"]["status"] = "dry_run"
            return True
        
        record_path.write_text(content, encoding="utf-8")
        
        self.results["execution_record"]["status"] = "success"
        self.results["execution_record"]["details"] = str(record_path)
        print(f"  ✅ 执行记录生成成功: {record_path}")
        return True
    
    def sync(self, task_id: str, task_name: str, git_message: str,
             kanban_status: str = "已完成", kanban_progress: str = None,
             outputs: List[Dict] = None, lessons: List[str] = None,
             git_files: List[str] = None) -> Dict:
        """
        一键同步：Git + 看板 + 执行记录
        
        Returns:
            同步结果字典
        """
        print(f"\n{'='*60}")
        print(f"[PTA-S04] 文档同步开始")
        print(f"{'='*60}")
        print(f"任务: {task_id} · {task_name}")
        print(f"模式: {'DRY-RUN' if self.dry_run else '实际执行'}")
        print(f"{'='*60}")
        
        # 1. Git 同步
        git_success = self.sync_git(git_message, git_files)
        
        # 2. 看板更新
        kanban_success = self.update_kanban(task_id, kanban_status, kanban_progress)
        
        # 3. 执行记录
        if outputs:
            record_success = self.generate_execution_record(task_id, task_name, outputs, lessons)
        else:
            self.results["execution_record"]["status"] = "skipped"
            self.results["execution_record"]["details"] = "未提供产出清单"
            record_success = True
        
        # 汇总
        all_success = git_success and kanban_success and record_success
        
        print(f"\n{'='*60}")
        print(f"[PTA-S04] 同步结果")
        print(f"{'='*60}")
        print(f"Git 同步: {self.results['git']['status']} - {self.results['git']['details']}")
        print(f"看板更新: {self.results['kanban']['status']} - {self.results['kanban']['details']}")
        print(f"执行记录: {self.results['execution_record']['status']} - {self.results['execution_record']['details']}")
        print(f"{'='*60}")
        
        return {
            "success": all_success,
            "task_id": task_id,
            "task_name": task_name,
            "results": self.results,
            "timestamp": datetime.now().isoformat(),
        }


def main():
    parser = argparse.ArgumentParser(description="PTA-S04 · 文档同步器")
    parser.add_argument("--task-id", required=True, help="任务编号（如 P1-01）")
    parser.add_argument("--task-name", required=True, help="任务名称")
    parser.add_argument("--message", "-m", required=True, help="Git 提交信息")
    parser.add_argument("--status", default="已完成", help="看板状态（已完成/进行中/待启动）")
    parser.add_argument("--progress", help="进度更新（如 55 pct to 60 pct）")
    parser.add_argument("--files", nargs="*", help="指定 Git 添加的文件")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式（不实际执行）")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="项目根目录")
    args = parser.parse_args()
    
    syncer = DocumentSyncer(Path(args.project_root), dry_run=args.dry_run)
    result = syncer.sync(
        task_id=args.task_id,
        task_name=args.task_name,
        git_message=args.message,
        kanban_status=args.status,
        kanban_progress=args.progress,
        git_files=args.files,
    )
    
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
