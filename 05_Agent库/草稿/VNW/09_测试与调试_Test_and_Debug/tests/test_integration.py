#!/usr/bin/env python3
"""VNW v0.1确定性集成测试（不依赖真实Excel内容）。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
for relative in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(AGENT_ROOT / relative))
from memory.workspace import Workspace
from skills.minimum_loop import run


class MinimumLoopTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "D1_价值节点清单_fixture.xlsx"
        self.input.write_bytes(b"first")
        self.workspace = Workspace(self.root / "workspace")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def fake_extractor(_script, workbook, output_dir, domain):
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{domain or '全'}域_价值节点信号提取基线_auto_v1.0.md"
        output.write_text(f"source={workbook.name}", encoding="utf-8")
        return {"output": str(output), "command": ["fake"], "stdout": "ok"}

    def execute(self, state, force=False):
        return run(watch_dirs=[self.root], patterns=["D1_价值节点清单_*.xlsx"], state=state,
                   extractor_script=self.root / "legacy.py", output_dir=self.workspace.outputs,
                   domain="PAY", force=force, extractor=self.fake_extractor)

    def test_changed_file_is_processed_and_persistable(self):
        result = self.execute(self.workspace.load())
        self.assertEqual("processed", result["status"])
        self.assertTrue(Path(result["extraction"]["output"]).is_file())
        self.workspace.save(result["state"])
        self.assertEqual(1, len(self.workspace.load()["files"]))

    def test_unchanged_file_is_skipped(self):
        first = self.execute(self.workspace.load())
        second = self.execute(first["state"])
        self.assertEqual("unchanged", second["status"])
        self.assertEqual(1, len(second["state"]["runs"]))

    def test_content_change_reopens_loop(self):
        first = self.execute(self.workspace.load())
        self.input.write_bytes(b"second")
        second = self.execute(first["state"])
        self.assertEqual("processed", second["status"])
        self.assertNotEqual(first["change"]["fingerprint"], second["change"]["fingerprint"])
        self.assertNotEqual(first["extraction"]["output"], second["extraction"]["output"])
        self.assertTrue(Path(first["extraction"]["output"]).is_file())
        self.assertTrue(Path(second["extraction"]["output"]).is_file())

    def test_failure_does_not_advance_state(self):
        def fail(*_args):
            raise RuntimeError("expected")
        with self.assertRaises(RuntimeError):
            run(watch_dirs=[self.root], patterns=["*.xlsx"], state=self.workspace.load(),
                extractor_script=self.root / "x", output_dir=self.workspace.outputs,
                domain="PAY", extractor=fail)
        self.assertFalse(self.workspace.state_file.exists())

    def test_status_entrypoint(self):
        agent = AGENT_ROOT / "04_定义Agent_Define_Agent/agents/agent.py"
        completed = subprocess.run([sys.executable, str(agent), "--status", "--workspace", str(self.workspace.root)], capture_output=True, text=True)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("VNW", json.loads(completed.stdout)["agent_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
