"""比较工作簿SHA-256与上次成功状态，不直接持久化。"""
from __future__ import annotations

from pathlib import Path
from tools.file_fingerprint import discover_workbooks, sha256_file


def detect(watch_dirs: list[Path], patterns: list[str], previous_state: dict, force: bool = False) -> dict:
    workbooks = discover_workbooks(watch_dirs, patterns)
    if not workbooks:
        return {"status": "no_input", "workbook": None, "fingerprint": None, "changed": False}
    workbook = workbooks[0]
    fingerprint = sha256_file(workbook)
    previous = previous_state.get("files", {}).get(str(workbook))
    return {
        "status": "changed" if force or not previous or previous.get("sha256") != fingerprint else "unchanged",
        "workbook": str(workbook), "fingerprint": fingerprint,
        "changed": force or not previous or previous.get("sha256") != fingerprint,
    }
