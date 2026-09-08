#!/usr/bin/env python3
"""T021 交换包：完整记录、证据、内容寻址、幂等和健康发布门禁。"""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ICD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ICD / "05_集成工具_Integrate_Tools"))
from tools import icd_export  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    db = ICD / "07_接入记忆_Integrate_Memory/data/icd.db"
    raw = ICD / "07_接入记忆_Integrate_Memory/raw_data"
    before = sha(db)
    bundle = icd_export.build(db, raw)
    assert len(bundle["fulfillment"]) == 13039 and len(bundle["rbc"]) == 8
    assert all({"run_id", "sha256", "source_url", "raw_value"} <= set(x) for x in bundle["fulfillment"])
    with tempfile.TemporaryDirectory() as td:
        first = icd_export.write(bundle, td)
        assert first["contract_version"] == "1.0.0"
        assert first["release_status"] == "PARTIAL_COVERAGE"
        assert first["record_counts"]["fulfillment_ratio"] == 13039
        root = Path(first["path"])
        manifest = json.loads((root / "manifest.json").read_text())
        for name, meta in manifest["files"].items():
            assert sha(root / name) == meta["sha256"]
        second = icd_export.write(bundle, td)
        assert second["bundle_id"] == first["bundle_id"] and second["reused"] is True

        proc = subprocess.run([
            sys.executable, str(ICD / "04_定义Agent_Define_Agent/agents/agent.py"),
            "--export", "--db-path", str(db), "--raw-data-root", str(raw),
            "--exports-root", str(Path(td) / "cli")
        ], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["record_counts"]["rbc_statement"] == 8

        broken = Path(td) / "broken.db"
        shutil.copyfile(db, broken)
        conn = sqlite3.connect(broken)
        conn.execute("UPDATE fetch_run SET snapshot_path='raw_data/missing.pdf' WHERE run_id=(SELECT MIN(run_id) FROM fetch_run WHERE fetch_status='OK')")
        conn.commit(); conn.close()
        try:
            icd_export.build(broken, raw)
        except ValueError as exc:
            assert "CRITICAL" in str(exc)
        else:
            raise AssertionError("CRITICAL 健康状态必须阻止发布")
    assert sha(db) == before
    print("T021 focused tests: PASS (contract, counts, evidence, hashes, idempotence, health gate)")


if __name__ == "__main__":
    main()
