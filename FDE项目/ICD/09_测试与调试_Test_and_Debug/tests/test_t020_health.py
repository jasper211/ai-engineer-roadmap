#!/usr/bin/env python3
"""T020 健康检查：只读、哈希、缺口分级和 CLI 退出码。"""

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
from tools import icd_health  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    db = ICD / "07_接入记忆_Integrate_Memory/data/icd.db"
    raw = ICD / "07_接入记忆_Integrate_Memory/raw_data"
    before = digest(db)
    result = icd_health.check(db, raw)
    assert result["status"] == "DEGRADED" and result["exit_code"] == 1
    assert result["checks"]["integrity_check"] == "ok"
    assert result["checks"]["snapshot_missing"] == 0
    assert result["checks"]["snapshot_hash_mismatch"] == 0
    assert result["checks"]["business_orphan_rows"] == 0
    assert digest(db) == before

    with tempfile.TemporaryDirectory() as td:
        broken = Path(td) / "broken.db"
        shutil.copyfile(db, broken)
        conn = sqlite3.connect(broken)
        conn.execute("UPDATE fetch_run SET snapshot_path='raw_data/missing/file.pdf' WHERE run_id=(SELECT MIN(run_id) FROM fetch_run WHERE fetch_status='OK')")
        conn.commit(); conn.close()
        critical = icd_health.check(broken, raw)
        assert critical["status"] == "CRITICAL" and critical["exit_code"] == 2
        assert critical["checks"]["snapshot_missing"] == 1

    proc = subprocess.run([
        sys.executable, str(ICD / "04_定义Agent_Define_Agent/agents/agent.py"),
        "--health", "--db-path", str(db), "--raw-data-root", str(raw)
    ], capture_output=True, text=True)
    assert proc.returncode == 1, proc.stderr
    assert json.loads(proc.stdout)["status"] == "DEGRADED"
    assert digest(db) == before
    print("T020 focused tests: PASS (readonly, integrity, snapshots, severity, CLI exits)")


if __name__ == "__main__":
    main()
