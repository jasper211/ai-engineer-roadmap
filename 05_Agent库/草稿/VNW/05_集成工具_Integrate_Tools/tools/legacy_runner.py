"""以隔离子进程调用Phase1已验证脚本，保留其原CLI行为。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_signal_extractor(script: Path, workbook: Path, output_dir: Path, domain: str | None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(script), "--input", str(workbook), "--output", str(output_dir)]
    command += ["--domain", domain] if domain else ["--all"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"信号提取失败（exit={completed.returncode}）：{detail}")
    outputs = sorted(output_dir.glob("*_价值节点信号提取基线_auto_v1.0.md"))
    if not outputs:
        raise RuntimeError("信号提取脚本返回成功，但未生成预期Markdown产物")
    return {"command": command, "output": str(outputs[-1].resolve()), "stdout": completed.stdout}
