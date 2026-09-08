#!/usr/bin/env python3
"""T022 消费者验收：正常包、篡改、语义错误和 CLI。"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ICD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ICD / "05_集成工具_Integrate_Tools"))
from tools import icd_export_validator  # noqa: E402

BUNDLE = ICD / "07_接入记忆_Integrate_Memory/exports/icd-exchange-v1-147a281d97570988"


def main():
    ok = icd_export_validator.validate(BUNDLE)
    assert ok["result"] == "ACCEPTED" and ok["exit_code"] == 0, ok["errors"]
    proc = subprocess.run([
        sys.executable, str(ICD / "04_定义Agent_Define_Agent/agents/agent.py"),
        "--validate-export", str(BUNDLE)
    ], capture_output=True, text=True)
    assert proc.returncode == 0 and json.loads(proc.stdout)["result"] == "ACCEPTED"

    with tempfile.TemporaryDirectory() as td:
        tampered = Path(td) / BUNDLE.name
        shutil.copytree(BUNDLE, tampered)
        path = tampered / "rbc_statement.json"
        path.write_bytes(path.read_bytes() + b" ")
        bad = icd_export_validator.validate(tampered)
        assert bad["result"] == "REJECTED"
        assert any("SHA-256" in x for x in bad["errors"])

    with tempfile.TemporaryDirectory() as td:
        semantic = Path(td) / BUNDLE.name
        shutil.copytree(BUNDLE, semantic)
        path = semantic / "fulfillment_ratio.jsonl"
        lines = path.read_text().splitlines()
        row = json.loads(lines[0]); row["normalized_value"] = "100%"
        lines[0] = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        body = ("\n".join(lines) + "\n").encode()
        path.write_bytes(body)
        manifest_path = semantic / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][path.name] = {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        bad = icd_export_validator.validate(semantic)
        assert any("normalized_value 类型错误" in x for x in bad["errors"])
    print("T022 focused tests: PASS (valid bundle, hash tamper, semantic tamper, CLI)")


if __name__ == "__main__":
    main()
