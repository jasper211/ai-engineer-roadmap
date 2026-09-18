#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDA 主循环入口。demo 阶段是一次性全量流程，不做常驻监控/调度。

用法：
    python3 agent.py --run           # 跑一次：读取底表 -> 清洗 -> 聚合 -> 生成看板
    python3 agent.py --enrich        # 读取底表 -> 清洗 -> 加S8的13个衍生字段 -> 存CSV
    python3 agent.py --sync-targets  # 只读同步fact_target目标APE快照（需要db_config_local.py）
    python3 agent.py --s1            # 复刻S1_总览仪表盘的A-H八个板块 -> 存CSV
    python3 agent.py --s2            # 复刻S2_业务端视角的核心板块(A/B/C-H/I/J/K/O) -> 存CSV
    python3 agent.py --s3            # 复刻S3_执行管理端的核心板块(A/B/C/D/G/H) -> 存CSV
    python3 agent.py --s4            # 复刻S4_产品端视角全部板块(A/B/C/D/E) -> 存CSV
    python3 agent.py --s5            # 复刻S5_财务端视角全部板块(A/B/C/D/E/F/G/H) -> 存CSV
    python3 agent.py --status        # 查看上次运行的记录
"""
import argparse
import sys
import datetime as dt
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
for sub in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(AGENT_ROOT / sub))

from skills.data_loader import DataLoader
from skills.cleaner import Cleaner
from skills.aggregator import Aggregator
from skills.dashboard_generator import DashboardGenerator
from skills.report_enricher import ReportEnricher
from skills.s1_dashboard import S1DashboardBuilder
from skills.s2_business_view import S2BusinessViewBuilder
from skills.s3_execution_view import S3ExecutionViewBuilder
from skills.s4_product_view import S4ProductViewBuilder
from skills.s5_finance_view import S5FinanceViewBuilder
from memory.workspace import Workspace

RAW_DATA_DIR = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "raw_data"
FACT_TARGET_SNAPSHOT = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "data" / "fact_target_snapshot.csv"
AGENT_VERSION = "v0.7.0"


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


def sync_targets():
    from tools.fact_target_sync import sync
    n = sync(FACT_TARGET_SNAPSHOT)
    print(f"✅ 已同步 fact_target {n} 行到 {FACT_TARGET_SNAPSHOT}")


def build_s1():
    if not FACT_TARGET_SNAPSHOT.exists():
        print(f"❌ 找不到 {FACT_TARGET_SNAPSHOT}，先跑 --sync-targets")
        return
    load_result = DataLoader(RAW_DATA_DIR).load()
    df = Cleaner().clean(load_result.df, load_result.export_date)
    df = ReportEnricher().enrich(df)

    import pandas as pd
    fact_target = pd.read_csv(FACT_TARGET_SNAPSHOT)
    report_month = load_result.export_date.strftime("%Y-%m") if load_result.export_date is not None else dt.datetime.now().strftime("%Y-%m")
    s1 = S1DashboardBuilder(df, fact_target, report_month=report_month).build_all()

    workspace = Workspace()
    out_dir = workspace.data_dir / "S1_总览仪表盘"
    out_dir.mkdir(parents=True, exist_ok=True)
    for section, rows in s1.items():
        pd.DataFrame(rows).to_csv(out_dir / f"{section}.csv", index=False, encoding="utf-8-sig")

    print(f"✅ S1_总览仪表盘 A-H 八个板块已生成（report_month={report_month}）")
    print("   A-H 全部已用真实『业绩分析报表_0724.xlsx』核验，见 S1_总览仪表盘_反推标准_v0.1.md")
    print(f"输出目录: {out_dir}")


def build_s2():
    if not FACT_TARGET_SNAPSHOT.exists():
        print(f"❌ 找不到 {FACT_TARGET_SNAPSHOT}，先跑 --sync-targets")
        return
    load_result = DataLoader(RAW_DATA_DIR).load()
    df = Cleaner().clean(load_result.df, load_result.export_date)

    import pandas as pd
    fact_target = pd.read_csv(FACT_TARGET_SNAPSHOT)
    s2 = S2BusinessViewBuilder(df, fact_target).build_core()

    workspace = Workspace()
    out_dir = workspace.data_dir / "S2_业务端视角"
    out_dir.mkdir(parents=True, exist_ok=True)
    for section, rows in s2.items():
        if section in ("C", "D", "E", "F", "G", "H"):
            flat = []
            for r in rows:
                flat_row = {"业务细分": r["业务细分"]}
                for k, v in r.items():
                    if k == "业务细分":
                        continue
                    flat_row[f"{k}_APE"] = v["ape"]
                    flat_row[f"{k}_件数"] = v["count"]
                flat.append(flat_row)
            pd.DataFrame(flat).to_csv(out_dir / f"{section}.csv", index=False, encoding="utf-8-sig")
        else:
            pd.DataFrame(rows).to_csv(out_dir / f"{section}.csv", index=False, encoding="utf-8-sig")

    print("✅ S2_业务端视角 核心板块(A/B/C-H/I/J/K/O)已生成")
    print("   A/B/C/I/J/K/O 已用真实『业绩分析报表_0724.xlsx』核验，D-H为同规则参数化推算")
    print("   S/T(partner_code维度)未实现，见 S2_业务端视角_反推标准_v0.1.md")
    print(f"输出目录: {out_dir}")


def build_s3():
    load_result = DataLoader(RAW_DATA_DIR).load()
    df = Cleaner().clean(load_result.df, load_result.export_date)
    s3 = S3ExecutionViewBuilder(df).build_core()

    import pandas as pd
    workspace = Workspace()
    out_dir = workspace.data_dir / "S3_执行管理端"
    out_dir.mkdir(parents=True, exist_ok=True)
    for section, rows in s3.items():
        if section == "A":
            flat = []
            for stage, weeks in rows.items():
                flat_row = {"阶段": stage}
                for w, v in weeks.items():
                    flat_row[f"{w}_APE"] = v["ape"]
                    flat_row[f"{w}_件数"] = v["count"]
                flat.append(flat_row)
            pd.DataFrame(flat).to_csv(out_dir / "A.csv", index=False, encoding="utf-8-sig")
        elif section in ("B", "C", "D"):
            flat = []
            for r in rows:
                flat_row = {"业务细分": r["业务细分"]}
                for k, v in r.items():
                    if k == "业务细分":
                        continue
                    flat_row[f"{k}_APE"] = v["ape"]
                    flat_row[f"{k}_件数"] = v["count"]
                flat.append(flat_row)
            pd.DataFrame(flat).to_csv(out_dir / f"{section}.csv", index=False, encoding="utf-8-sig")
        else:
            pd.DataFrame(rows).to_csv(out_dir / f"{section}.csv", index=False, encoding="utf-8-sig")

    print("✅ S3_执行管理端 核心板块(A/B/C/D/G/H)已生成")
    print("   全部已用真实『业绩分析报表_0724.xlsx』核验，关键发现：周定义=%YW%U(周日起始)")
    print("   E/F(未批核待签透视表)/J-O(同行/银行周度趋势)未实现，见 S3_执行管理端_反推标准_v0.1.md")
    print(f"输出目录: {out_dir}")


def build_s4():
    load_result = DataLoader(RAW_DATA_DIR).load()
    df = Cleaner().clean(load_result.df, load_result.export_date)
    s4 = S4ProductViewBuilder(df).build_all()

    import pandas as pd
    workspace = Workspace()
    out_dir = workspace.data_dir / "S4_产品端视角"
    out_dir.mkdir(parents=True, exist_ok=True)
    for section, rows in s4.items():
        pd.DataFrame(rows).to_csv(out_dir / f"{section}.csv", index=False, encoding="utf-8-sig")

    print("✅ S4_产品端视角 全部5个板块(A/B/C/D/E)已生成")
    print("   全部已用真实『业绩分析报表_0724.xlsx』核验")
    print(f"输出目录: {out_dir}")


def build_s5():
    load_result = DataLoader(RAW_DATA_DIR).load()
    df = Cleaner().clean(load_result.df, load_result.export_date)
    s5 = S5FinanceViewBuilder(df).build_all()

    import pandas as pd
    workspace = Workspace()
    out_dir = workspace.data_dir / "S5_财务端视角"
    out_dir.mkdir(parents=True, exist_ok=True)
    for section, rows in s5.items():
        pd.DataFrame(rows).to_csv(out_dir / f"{section}.csv", index=False, encoding="utf-8-sig")

    print("✅ S5_财务端视角 全部8个板块（A/B-保费/B-件数/C-APE/C-件数/D/E/F/G/H）已生成")
    print("   全部已用真实『业绩分析报表_0724.xlsx』核验")
    print(f"输出目录: {out_dir}")


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
    ap.add_argument("--sync-targets", action="store_true", dest="sync_targets", help="只读同步fact_target目标APE快照")
    ap.add_argument("--s1", action="store_true", help="复刻S1_总览仪表盘A-H八个板块，存CSV")
    ap.add_argument("--s2", action="store_true", help="复刻S2_业务端视角核心板块，存CSV")
    ap.add_argument("--s3", action="store_true", help="复刻S3_执行管理端核心板块，存CSV")
    ap.add_argument("--s4", action="store_true", help="复刻S4_产品端视角全部板块，存CSV")
    ap.add_argument("--s5", action="store_true", help="复刻S5_财务端视角全部板块，存CSV")
    ap.add_argument("--status", action="store_true", help="查看上次运行记录")
    args = ap.parse_args()

    if args.run:
        run()
    elif args.enrich:
        enrich()
    elif args.sync_targets:
        sync_targets()
    elif args.s1:
        build_s1()
    elif args.s2:
        build_s2()
    elif args.s3:
        build_s3()
    elif args.s4:
        build_s4()
    elif args.s5:
        build_s5()
    elif args.status:
        show_status()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
