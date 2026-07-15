#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：Git 操作封装（原 PTA-S04_文档同步器.py 里的 _run_git/sync_git 下放到这里，
独立成通用工具，不再跟"看板/执行记录"这些业务概念绑在一起）。

⚠️ 安全约束（继承自原 S04 的事故教训，不可放松）：
- 绝不 git add .，只 add 调用方显式列出的文件列表
- 默认真实执行（dry_run=False），不是要传额外参数才危险——按 D-20260709-001
  复核发现的教训，这条约束必须在文档和代码里保持一致，不能靠"记得传参数"
"""

import subprocess
from pathlib import Path
from typing import List, Tuple, Optional

GIT_REMOTE = "origin"
GIT_BRANCH = "main"


def run_git(args: List[str], cwd: Path, timeout: int = 30) -> Tuple[int, str, str]:
    """运行任意 git 命令，返回 (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Git 命令超时"
    except FileNotFoundError:
        return -1, "", "Git 未安装"


def sync_git(cwd: Path, message: str, files: Optional[List[str]], dry_run: bool = False) -> dict:
    """
    Git 同步：add（逐个文件）→ commit → push。

    Args:
        cwd: 目标 git 仓库根目录
        message: 提交信息
        files: 要 add 的具体文件列表，为空则跳过（不做 git add .）
        dry_run: True 时只打印将要执行的操作，不真实执行

    Returns:
        {"status": "dry_run"|"skipped"|"success"|"failed", "details": str}
    """
    print(f"\n[git_ops] Git 同步开始（cwd={cwd}）...")

    if dry_run:
        print(f"  [DRY-RUN] 将执行: git add {files or '(无文件)'} + commit '{message}' + push")
        return {"status": "dry_run", "details": ""}

    if not files:
        details = "没有已知需要同步的文件，未显式传 files"
        print(f"  ℹ️ {details}")
        return {"status": "skipped", "details": details}

    for f in files:
        returncode, _, stderr = run_git(["add", f], cwd)
        if returncode != 0:
            print(f"  ❌ git add 失败: {stderr}")
            return {"status": "failed", "details": f"git add 失败: {stderr}"}

    returncode, stdout, stderr = run_git(["commit", "-m", message], cwd)
    if returncode != 0:
        if "nothing to commit" in stderr or "nothing to commit" in stdout:
            print(f"  ℹ️ 无变更需要提交")
            return {"status": "skipped", "details": "无变更需要提交"}
        print(f"  ❌ git commit 失败: {stderr}")
        return {"status": "failed", "details": f"git commit 失败: {stderr}"}

    commit_hash = stdout.strip().split()[-1] if stdout else "unknown"
    print(f"  ✅ git commit 成功: {commit_hash[:8]}")

    returncode, _, stderr = run_git(["push", GIT_REMOTE, GIT_BRANCH], cwd)
    if returncode != 0:
        print(f"  ❌ git push 失败: {stderr}")
        return {"status": "failed", "details": f"git push 失败: {stderr}"}

    print(f"  ✅ git push 成功")
    return {"status": "success", "details": f"commit: {commit_hash[:8]}"}
