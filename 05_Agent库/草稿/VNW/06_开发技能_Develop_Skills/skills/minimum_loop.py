"""VNW v0.1 最小闭环：检测→提取→成功后更新记忆。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from skills.change_detection import detect
from skills.signal_extraction import extract


def run(*, watch_dirs, patterns, state, extractor_script, output_dir, domain, force=False, extractor=extract):
    change = detect(watch_dirs, patterns, state, force)
    if not change["changed"]:
        return {"status": change["status"], "change": change, "state": state}
    versioned_output_dir = Path(output_dir) / change["fingerprint"][:12]
    result = extractor(Path(extractor_script), Path(change["workbook"]), versioned_output_dir, domain)
    now = datetime.now(timezone.utc).isoformat()
    new_state = {**state, "files": dict(state.get("files", {})), "runs": list(state.get("runs", []))}
    new_state["files"][change["workbook"]] = {"sha256": change["fingerprint"], "processed_at": now, "output": result["output"]}
    new_state["runs"].append({"status": "success", "workbook": change["workbook"], "output": result["output"], "at": now})
    new_state["runs"] = new_state["runs"][-50:]
    return {"status": "processed", "change": change, "extraction": result, "state": new_state}
