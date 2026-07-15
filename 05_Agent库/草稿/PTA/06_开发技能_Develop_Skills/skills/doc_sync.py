#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：文档同步（原 PTA-S04_文档同步器.py 迁移，做了一处简化）

简化说明：原 S04 里的 generate_execution_record() 方法，实测在 PTA-RUN 的真实
调用链路里从未被触发（PTA-RUN 调 S04 时不传 outputs，该方法内部 `if outputs:`
恒为假）——执行记录实际上始终由 S05（现 skills/archive_review.py）生成，
S04 那份是重复代码。这次迁移直接删掉这份死代码，执行记录统一只由
archive_review 负责，不再有两处"同名但实现不同"的风险。

⚠️ 安全约束不变：绝不 git add .，只 add 看板 + 调用方显式传入的文件。
"""

import re
from pathlib import Path
from typing import List, Optional

from tools import git_ops


class DocumentSyncer:
    """文档同步器：看板更新 + Git 提交（真实 git push，见 tools/git_ops.py 的安全约束）"""

    def __init__(self, project_root: Path, dry_run: bool = False):
        self.project_root = project_root
        self.dry_run = dry_run
        self.kanban_path = project_root / "能力整改看板.md"
        self.results = {"git": {"status": "pending", "details": ""},
                         "kanban": {"status": "pending", "details": ""}}

    def update_kanban(self, task_id: str, status: str = "已完成", progress: str = None) -> bool:
        print(f"\n[skills.doc_sync] 看板更新开始...")
        if not self.kanban_path.exists():
            self.results["kanban"] = {"status": "failed", "details": "看板文件不存在"}
            print(f"  ❌ 看板文件不存在: {self.kanban_path}")
            return False

        content = self.kanban_path.read_text(encoding="utf-8")
        pattern = rf"(- \[([ x])\]) ({re.escape(task_id)} · .*?)$"

        def replace_status(match):
            task = match.group(3)
            new_checkbox = "- [x]" if status == "已完成" else "- [ ]" if status == "进行中" else match.group(1)
            return f"{new_checkbox} {task}"

        new_content = re.sub(pattern, replace_status, content, flags=re.MULTILINE)
        if progress:
            progress_pattern = rf"(\| {re.escape(task_id)}.*?\|)(\d+%)(\|)"
            new_content = re.sub(progress_pattern, rf"\1{progress}\3", new_content)

        if self.dry_run:
            print(f"  [DRY-RUN] 将更新看板: {task_id} → {status}")
            self.results["kanban"] = {"status": "dry_run", "details": ""}
            return True

        self.kanban_path.write_text(new_content, encoding="utf-8")
        self.results["kanban"] = {"status": "success", "details": f"{task_id} → {status}"}
        print(f"  ✅ 看板更新成功: {task_id} → {status}")
        return True

    def sync(self, task_id: str, task_name: str, git_message: str,
              kanban_status: str = "已完成", kanban_progress: str = None,
              git_files: Optional[List[str]] = None, execution_record_path: Optional[str] = None) -> dict:
        """一键同步：看板 + Git（执行记录由 archive_review 单独生成，这里只负责把它 add 进 commit）"""
        print(f"\n{'='*60}\n[skills.doc_sync] 文档同步开始\n{'='*60}")
        print(f"任务: {task_id} · {task_name}｜模式: {'DRY-RUN' if self.dry_run else '实际执行'}")

        kanban_success = self.update_kanban(task_id, kanban_status, kanban_progress)

        add_targets: List[str] = []
        if self.kanban_path.exists():
            add_targets.append(str(self.kanban_path))
        if execution_record_path and Path(execution_record_path).exists():
            add_targets.append(execution_record_path)
        if git_files:
            add_targets.extend(git_files)

        self.results["git"] = git_ops.sync_git(self.project_root, git_message, add_targets, self.dry_run)
        git_success = self.results["git"]["status"] in ("success", "skipped", "dry_run")

        print(f"\n{'='*60}\n[skills.doc_sync] 同步结果\n{'='*60}")
        print(f"Git: {self.results['git']}")
        print(f"看板: {self.results['kanban']}")

        return {"success": git_success and kanban_success, "task_id": task_id,
                "task_name": task_name, "results": self.results}
