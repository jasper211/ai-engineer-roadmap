#!/usr/bin/env python3
"""T019 业务分析：只读、统计口径、证据字段和报告输出。"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ICD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ICD / "05_集成工具_Integrate_Tools"))
from tools import icd_analysis  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = ICD / "07_接入记忆_Integrate_Memory/data/icd.db"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = root / "copy.db"
        shutil.copyfile(source, db)
        before = digest(db)
        report = icd_analysis.build(db)
        assert digest(db) == before
        assert len(report["fulfillment_summary"]) == 9
        assert len(report["rbc_summary"]) == 8
        assert report["rbc_summary"][0]["solvency_ratio"] >= report["rbc_summary"][-1]["solvency_ratio"]
        assert all(x["numeric_count"] + x["non_numeric_count"] == x["observation_count"] for x in report["fulfillment_summary"])
        paths = icd_analysis.write(report, root / "reports")
        assert Path(paths["json_path"]).is_file() and Path(paths["markdown_path"]).is_file()
        assert json.loads(Path(paths["json_path"]).read_text())["report_type"] == "ICD_BUSINESS_ANALYSIS"
        proc = subprocess.run([
            sys.executable, str(ICD / "04_定义Agent_Define_Agent/agents/agent.py"),
            "--analyze", "--db-path", str(db), "--reports-root", str(root / "cli-reports")
        ], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["rbc_entities"] == 8
        assert digest(db) == before
    print("T019 focused tests: PASS (readonly, aggregates, evidence, JSON/Markdown, CLI)")


if __name__ == "__main__":
    main()
