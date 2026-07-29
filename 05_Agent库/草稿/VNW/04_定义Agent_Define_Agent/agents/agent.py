#!/usr/bin/env python3
"""VNW命令行入口。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = AGENT_ROOT.parents[2]
for relative in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(AGENT_ROOT / relative))

from memory.workspace import Workspace
from skills.minimum_loop import run


def load_settings() -> dict:
    path = AGENT_ROOT / "02_配置项目_Configure_Project/settings.json"
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args():
    parser = argparse.ArgumentParser(description="VNW · 价值节点驱动工作流 Agent")
    parser.add_argument("--watch-dir", action="append", type=Path, help="清单目录；可重复传入")
    parser.add_argument("--workspace", type=Path, help="VNW专属状态/产物目录")
    parser.add_argument("--domain", default=None, help="域编码；ALL表示全域")
    parser.add_argument("--force", action="store_true", help="忽略指纹，强制重新生成")
    parser.add_argument("--status", action="store_true", help="仅显示配置和最近状态")
    parser.add_argument("--build-model-snapshots", action="store_true", help="只读构建L3流程模型基础快照")
    parser.add_argument("--build-all-model-snapshots", action="store_true", help="批量只读构建数据库中的全部L3模型")
    parser.add_argument("--l3-code", action="append", help="要构建的L3编码；可重复传入")
    parser.add_argument("--blueprint-index", type=Path, help="L3蓝图覆盖清单CSV")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings()
    workspace = Workspace(args.workspace or AGENT_ROOT / settings["workspace_dir"])
    state = workspace.load()
    if args.status:
        print(json.dumps({"agent_id": settings["agent_id"], "version": settings["version"], "workspace": str(workspace.root), "tracked_files": len(state.get("files", {})), "last_run": state.get("runs", [])[-1:]}, ensure_ascii=False, indent=2))
        return 0
    if args.build_model_snapshots or args.build_all_model_snapshots:
        from skills.l3_model_builder import (
            L3ModelBuilder,
            load_blueprint_index,
            load_blueprint_index_from_dir,
            load_d1d6_supplement,
        )
        from skills.sync_data_foundation import db_query
        from tools.postgres_reader import BulkPostgresL3Reader, PostgresL3Reader

        if args.build_all_model_snapshots:
            reader = BulkPostgresL3Reader.from_query(db_query)
            codes = reader.l3_codes
        else:
            reader = PostgresL3Reader(db_query)
            codes = args.l3_code or ["L3-IRI", "L3-IBRD", "L3-IBEC", "L3-EO"]
        blueprint_dir = Path("/Users/a112233/Desktop/流程架构项目_jasper/02_过程成果-工作产出/L3流程库")
        # 2026-07-29:蓝图覆盖判定改为直接扫描blueprint_dir实际文件，取代
        # 手工维护、已确认过期的L3蓝图覆盖清单_v1.0.csv(--blueprint-index
        # 仍可显式传入走旧CSV路径，兼容排查场景，默认不再使用)。
        blueprint_index = (
            load_blueprint_index(args.blueprint_index)
            if args.blueprint_index
            else load_blueprint_index_from_dir(blueprint_dir)
        )
        d1d6_csv = Path(
            "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault/"
            "EA流程架构项目/_VNW引用原件/L4两阶段复核_全量368条_合并版_v1.0.csv"
        )
        d1d6_supplement = load_d1d6_supplement(d1d6_csv) if d1d6_csv.exists() else {}
        builder = L3ModelBuilder(
            reader,
            blueprint_index,
            blueprint_dir=blueprint_dir,
            d1d6_supplement=d1d6_supplement,
        )
        results = builder.build_and_write(codes, workspace.root / "model_snapshots")
        print(json.dumps({"status": "built", "snapshots": results}, ensure_ascii=False, indent=2))
        return 0
    watch_dirs = [item.resolve() for item in (args.watch_dir or [])]
    if not watch_dirs:
        print("错误：至少提供一个 --watch-dir", file=sys.stderr)
        return 2
    domain = args.domain or settings["default_domain"]
    domain = None if domain.upper() == "ALL" else domain.upper()
    result = run(watch_dirs=watch_dirs, patterns=settings["watch_patterns"], state=state,
                 extractor_script=REPO_ROOT / settings["legacy_signal_extractor"], output_dir=workspace.outputs,
                 domain=domain, force=args.force)
    if result["status"] == "processed":
        workspace.save(result["state"])
    print(json.dumps({key: value for key, value in result.items() if key != "state"}, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "no_input" else 3


if __name__ == "__main__":
    raise SystemExit(main())
