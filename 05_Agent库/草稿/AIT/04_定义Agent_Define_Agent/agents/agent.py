#!/usr/bin/env python3
"""AIT命令行入口。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
VNW_ROOT = AGENT_ROOT.parent / "VNW"
for relative in ("06_开发技能_Develop_Skills",):
    sys.path.insert(0, str(AGENT_ROOT / relative))

from skills.track_router import build_and_write


def parse_args():
    parser = argparse.ArgumentParser(description="AIT · AI 协同转型 Agent")
    parser.add_argument("--build-track-assignments", action="store_true", help="按决策确认记录跑轨道判定")
    parser.add_argument("--l3-code", action="append", help="要处理的L3编码；不传则处理decisions目录下全部")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.build_track_assignments:
        decisions_dir = AGENT_ROOT / "07_接入记忆_Integrate_Memory/decisions"
        snapshot_dir = VNW_ROOT / ".vnw_workspace/model_snapshots"
        output_dir = AGENT_ROOT / ".ait_workspace/track_assignments"

        codes = args.l3_code or [p.stem for p in decisions_dir.glob("*.json")]
        results = []
        for code in codes:
            decisions_path = decisions_dir / f"{code}.json"
            snapshot_path = snapshot_dir / f"{code}.json"
            if not decisions_path.exists():
                print(f"跳过{code}：没有决策确认记录", file=sys.stderr)
                continue
            if not snapshot_path.exists():
                print(f"跳过{code}：VNW model_snapshots里没有这个L3的快照", file=sys.stderr)
                continue
            out_path = build_and_write(decisions_path, snapshot_path, output_dir)
            results.append(str(out_path))
        print(json.dumps({"status": "built", "outputs": results}, ensure_ascii=False, indent=2))
        return 0
    print("错误：请传入 --build-track-assignments", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
