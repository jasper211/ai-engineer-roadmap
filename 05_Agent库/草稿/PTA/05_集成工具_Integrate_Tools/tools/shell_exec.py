#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：步骤执行器（原 PTA-S02_执行调度器.py 里的 _exec_bash/_exec_python/_exec_browser_use
下放到这里，成为独立工具——skills/execution_planning.py 只负责"分解成哪些步骤"，
这里只负责"每种步骤具体怎么跑"，两者解耦。）
"""

import subprocess
from pathlib import Path
from typing import Optional, Tuple


def exec_bash(command: Optional[str], cwd: Path, dry_run: bool = False, timeout: int = 300) -> Tuple[bool, str]:
    """执行 Bash 命令"""
    if not command:
        return False, "无命令"
    if dry_run:
        return True, f"[DRY-RUN] {command}"
    try:
        result = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return (True, result.stdout) if result.returncode == 0 else (False, result.stderr)
    except subprocess.TimeoutExpired:
        return False, "命令超时"
    except Exception as e:
        return False, str(e)


def exec_python(script: Optional[str], args: Optional[list], project_root: Path,
                 dry_run: bool = False, timeout: int = 300) -> Tuple[bool, str]:
    """执行 Python 脚本：先在 project_root 直接找，找不到再递归查找（覆盖嵌套子任务目录）"""
    if not script:
        return False, "无脚本"

    script_path = project_root / script
    if not script_path.exists():
        matches = [m for m in project_root.rglob(script) if ".git" not in m.parts]
        if matches:
            script_path = matches[0]

    if not script_path.exists():
        return False, f"脚本不存在: {script}"

    cmd = ["python3", str(script_path)] + (args or [])
    if dry_run:
        return True, f"[DRY-RUN] {' '.join(cmd)}"
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=timeout)
        return (True, result.stdout) if result.returncode == 0 else (False, result.stderr)
    except subprocess.TimeoutExpired:
        return False, "脚本超时"
    except Exception as e:
        return False, str(e)


def exec_browser_use(description: str, dry_run: bool = False) -> Tuple[bool, str]:
    """执行 browser-use 操作（占位——真实调用走 browser-use MCP，这里只做提示）"""
    if dry_run:
        return True, f"[DRY-RUN] browser-use: {description}"
    return True, f"[browser-use] 请手动执行: {description}\n提示: 使用 browser-use MCP 进行网页操作"


EXECUTORS = {"bash": exec_bash, "python": exec_python, "browser-use": exec_browser_use}
