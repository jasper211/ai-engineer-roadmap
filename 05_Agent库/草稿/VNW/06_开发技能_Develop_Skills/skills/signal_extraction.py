"""Phase1信号提取能力的Agent适配层。"""
from pathlib import Path
from tools.legacy_runner import run_signal_extractor


def extract(script: Path, workbook: Path, output_dir: Path, domain: str | None) -> dict:
    if not script.is_file():
        raise FileNotFoundError(f"找不到Phase1信号提取脚本：{script}")
    return run_signal_extractor(script, workbook, output_dir, domain)
