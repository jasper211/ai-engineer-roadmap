#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HKIA 主循环入口。demo 阶段是一次性全量流程，不做常驻监控/调度。

用法：
    python3 agent.py --run-demo     # 跑一次：发现本地文件 -> 解析 -> 标准化 -> 入库
    python3 agent.py --status       # 查看本地数据库现状
"""
import argparse
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
for sub in ("06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(AGENT_ROOT / sub))

from skills.report_discovery import ReportDiscovery
from skills.excel_parser import ExcelParser, SheetNotFoundError, SheetStructureError
from skills.normalizer import Normalizer
from memory.workspace import Workspace

RAW_DATA_DIR = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "raw_data"


def run_demo():
    discovery = ReportDiscovery(RAW_DATA_DIR)
    reports, problems = discovery.discover()

    if problems:
        print("⚠️ 完整性校验发现问题（不会静默跳过）：")
        for p in problems:
            print(f"  - {p}")
        if not reports:
            print("没有任何可解析的文件，终止。")
            return
        print(f"仍将继续处理已找到的 {len(reports)} 份文件。\n")

    parser = ExcelParser()
    normalizer = Normalizer()
    workspace = Workspace()
    workspace.reset()

    ok_count, fail_count = 0, 0
    for report in reports:
        label = f"{report.year}Q{report.quarter} ({report.file_path.name})"
        try:
            parsed = parser.parse(report.file_path)
            rows = normalizer.normalize(
                parsed,
                year=report.year,
                quarter=report.quarter,
                period_type=report.period_type,
                source_report=report.file_path.name,
            )
            workspace.insert_rows(rows)
            print(f"✅ {label}: schema={parsed['schema_version']} "
                  f"写入 {len(rows)} 条记录")
            ok_count += 1
        except (SheetNotFoundError, SheetStructureError) as e:
            print(f"❌ {label}: 解析失败 - {e}")
            fail_count += 1

    print(f"\n完成：{ok_count} 期成功，{fail_count} 期失败，"
          f"数据库共 {workspace.row_count()} 条记录")
    print(f"数据库文件: {workspace.db_path}")


def show_status():
    workspace = Workspace()
    if not workspace.db_path.exists():
        print("数据库尚未创建，先跑 --run-demo")
        return
    print(f"数据库: {workspace.db_path}")
    print(f"总记录数: {workspace.row_count()}")
    print(f"已入库期数: {workspace.distinct_periods()}")


def main():
    ap = argparse.ArgumentParser(description="HKIA Agent")
    ap.add_argument("--run-demo", action="store_true", help="跑一次全量解析入库")
    ap.add_argument("--status", action="store_true", help="查看本地数据库现状")
    args = ap.parse_args()

    if args.run_demo:
        run_demo()
    elif args.status:
        show_status()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
