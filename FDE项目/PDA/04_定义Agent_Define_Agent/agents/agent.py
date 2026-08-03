#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDA 主循环入口。demo 阶段是一次性全量流程，不做常驻监控/调度。

用法：
    python3 agent.py --run       # 跑一次：读取底表 -> 清洗 -> 聚合 -> 生成看板
    python3 agent.py --enrich    # 读取底表 -> 清洗 -> 加S8的13个衍生字段 -> 存CSV
    python3 agent.py --status    # 查看上次运行的记录
"""
import argparse
import sys
import datetime as dt
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
for sub in ("06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(AGENT_ROOT / sub))

from skills.data_loader import DataLoader
from skills.cleaner import Cleaner
from skills.aggregator import Aggregator
from skills.dashboard_generator import DashboardGenerator
from skills.report_enricher import ReportEnricher
from memory.workspace import Workspace

RAW_DATA_DIR = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "raw_data"
AGENT_VERSION = "v0.2.0"


def run():
    load_result = DataLoader(RAW_DATA_DIR).load()
    df = Cleaner().clean(load_result.df, load_result.export_date)
    agg = Aggregator().aggregate(df)

    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    future_dated_count = int(df["future_dated"].sum())

    html = DashboardGenerator().render(
        agg,
        source_file_name=load_result.source_file.name,
        export_date=load_result.export_date.strftime("%Y-%m-%d") if load_result.export_date is not None else "未知",
        raw_rows=load_result.raw_row_count,
        header_rows_dropped=load_result.header_echo_rows_dropped,
        record_count=len(df),
        future_dated_count=future_dated_count,
        generated_at=generated_at,
        agent_version=AGENT_VERSION,
    )

    workspace = Workspace()
    run_info = {
        "agent_version": AGENT_VERSION,
        "source_file": load_result.source_file.name,
        "export_date": load_result.export_date.strftime("%Y-%m-%d") if load_result.export_date is not None else None,
        "raw_row_count": load_result.raw_row_count,
        "header_rows_dropped": load_result.header_echo_rows_dropped,
        "record_count": len(df),
        "entity_count": len(agg["entities"]),
        "future_dated_count": future_dated_count,
        "premium_total": sum(v["premium"] for v in agg["by_entity_all"].values()),
        "ape_total": sum(v["ape"] for v in agg["by_entity_all"].values()),
        "generated_at": generated_at,
    }
    dashboard_path = workspace.dashboard_path
    workspace.save_run(html, run_info)

    print(f"✅ 读取 {load_result.source_file.name}：原始 {load_result.raw_row_count} 行，"
          f"剔除表头残留 {load_result.header_echo_rows_dropped} 行，有效记录 {len(df)} 条")
    print(f"   覆盖牌照端 {len(agg['entities'])} 家，future_dated {future_dated_count} 条")
    print(f"   总保费(港币口径) {run_info['premium_total']:,.2f}，总APE {run_info['ape_total']:,.2f}")
    print(f"看板已生成: {dashboard_path}")


def enrich():
    load_result = DataLoader(RAW_DATA_DIR).load()
    df = Cleaner().clean(load_result.df, load_result.export_date)
    enriched = ReportEnricher().enrich(df)

    workspace = Workspace()
    out_path = workspace.data_dir / "S8_衍生字段.csv"
    enriched.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"✅ 已对 {len(enriched)} 条记录加上13个S8衍生字段")
    print("   12个字段已用真实『业绩分析报表_0724.xlsx』S8 sheet逐行核验100%匹配")
    print("   『首年折扣(标准化)』：来源字段已确认=SQ_rate，但仍是原样透传，"
          "真正的标准化分档规则待Jasper提供（见 S8衍生字段_反推标准_v0.1.md 三节）")
    print(f"输出: {out_path}")


def show_status():
    workspace = Workspace()
    info = workspace.load_last_run()
    if info is None:
        print("尚未运行过，先跑 --run")
        return
    for k, v in info.items():
        print(f"{k}: {v}")
    print(f"看板文件: {workspace.dashboard_path}")


def main():
    ap = argparse.ArgumentParser(description="PDA Agent")
    ap.add_argument("--run", action="store_true", help="跑一次全量清洗+聚合+看板生成")
    ap.add_argument("--enrich", action="store_true", help="清洗+加S8的13个衍生字段，存CSV")
    ap.add_argument("--status", action="store_true", help="查看上次运行记录")
    args = ap.parse_args()

    if args.run:
        run()
    elif args.enrich:
        enrich()
    elif args.status:
        show_status()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
