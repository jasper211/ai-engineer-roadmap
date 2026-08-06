#!/usr/bin/env python3
"""VNW命令行入口。"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = AGENT_ROOT.parents[2]
for relative in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(AGENT_ROOT / relative))

from memory.workspace import Workspace
from skills.minimum_loop import run

# 2026-07-29:哪些L3已经有独立的深度demo(按COM标准测试版模板)。只收录
# 经Jasper确认符合当前标准的版本——L3-EO/IRI/IBRD在这之前也各出过一版
# demo，但那些是标准定下来之前的探索版本，没有按COM这版模板重做过，
# 不放进来，避免机会台里显示"已有demo"却打开一份不符合当前标准的旧版本。
DEMO_REGISTRY = {
    "L3-COM": "L3流程模型_demo_L3-COM_标准测试版_20260728.html",
}
DEMO_SOURCE_DIR = AGENT_ROOT / "03_规划项目结构_Plan_Project_Structure"


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
    parser.add_argument("--build-db-catalog", action="store_true", help="只读构建数据库现状目录(process_analytics+业务数据仓库表结构+行数)")
    parser.add_argument("--sync-business-scenarios", action="store_true", help="同步人工authoring的业务数据场景记录到前端，并基于model_snapshots机械派生流程现状/数据治理/任务清单/流程优化四环")
    parser.add_argument("--build-table-analysis", action="store_true", help="构建业务数据入口②五层分析结构(基于已有db_catalog.json，不重新查库)")
    parser.add_argument("--refresh-business-data", action="store_true", help="实时查库刷新db_catalog+重建入口②五层分析+重建数据血缘图，一条命令覆盖表数量变化(如新增表)")
    parser.add_argument("--build-data-lineage", action="store_true", help="用视图SQL定义/外键约束/命名ETL流水线三类真实证据构建104张表的数据血缘图")
    parser.add_argument("--build-table-root-cause-analysis", action="store_true", help="调用AI模型基于data_lineage.json真实血缘生成表级根因分析草稿(L3上下游+任务聚类、L4隐藏产出候选)，MODEL_DRAFT标注")
    parser.add_argument("--check-source-updates", action="store_true", help="候选重建并输出L3/面板影响清单，不更新前端")
    parser.add_argument("--apply-source-updates", action="store_true", help="安全发布源头变化后的事实快照与影响报告")
    parser.add_argument("--l3-code", action="append", help="要构建的L3编码；可重复传入")
    parser.add_argument("--blueprint-index", type=Path, help="L3蓝图覆盖清单CSV")
    parser.add_argument("--prepare-l3-analysis", action="append", help="从现有快照准备统一模型运行包；可重复传入L3编码")
    parser.add_argument("--prepare-analysis-repair", action="append", help="为已有分析包准备任务与负责人决策模块修复；可重复传入L3编码")
    parser.add_argument("--prepare-analysis-l4-refresh", help="为已有分析包准备一批L4分析刷新")
    parser.add_argument("--prepare-segmented-analysis", help="为无完整分析包的大型L3初始化/继续分段L4分析")
    parser.add_argument("--prepare-segmented-repair", help="为分段暂存包准备任务与负责人决策模块")
    parser.add_argument("--finalize-segmented-analysis", help="校验并发布已完成的分段分析包")
    parser.add_argument("--analysis-l4-code", action="append", help="L4分批刷新目标；单批最多6个")
    parser.add_argument("--run-analysis-dir", type=Path, help="调用模型运行指定分析运行包并校验发布")
    parser.add_argument("--import-analysis-output", type=Path, help="导入外部模型JSON；需同时提供--run-analysis-dir")
    parser.add_argument("--analysis-model", help="覆盖配置中的模型名称")
    return parser.parse_args()


def _sync_to_frontend(snapshot_dir: Path) -> dict:
    """把model_snapshots和已注册的demo文件拷进frontend/public，供L3Models/
    L3ModelDetail用fetch读取。之前这一步是Codex手动做的一次性拷贝，导致
    public里的index.json停在7月26号的旧快照(Gate A=1)，7月29号这次D1-D6/
    蓝图判定修好之后前端却读不到——加进主流程，每次构建快照都自动同步，
    不再依赖有人记得手动拷。"""
    frontend_data_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots"
    if frontend_data_dir.exists():
        shutil.rmtree(frontend_data_dir)
    shutil.copytree(snapshot_dir, frontend_data_dir)

    demo_dest_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/demos"
    demo_dest_dir.mkdir(parents=True, exist_ok=True)
    copied_demos = []
    missing_demos = []
    for l3_code, filename in DEMO_REGISTRY.items():
        src = DEMO_SOURCE_DIR / filename
        if src.exists():
            shutil.copy2(src, demo_dest_dir / filename)
            copied_demos.append(filename)
        else:
            missing_demos.append(filename)

    return {
        "snapshot_files_synced": True, "demos_synced": copied_demos, "demos_missing": missing_demos,
    }


def _load_table_to_l4_index() -> tuple[dict, list[str]]:
    """--build-table-analysis/--build-data-lineage/--refresh-business-data共用：从
    model_snapshots反查全部L3快照，建立table->L4关联索引。表数量变化(新增/删除表)、
    L3数量变化会在下次跑这里时自动体现，不需要改代码。"""
    from skills.table_analysis import build_table_to_l4_index

    snapshot_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots"
    model_index = json.loads((snapshot_dir / "index.json").read_text(encoding="utf-8"))
    l3_codes = [item["l3_code"] for item in model_index["models"]]

    def load_l3_snapshot(l3_code: str) -> dict | None:
        path = snapshot_dir / f"{l3_code}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    return build_table_to_l4_index(l3_codes, load_l3_snapshot), l3_codes


def _build_and_write_table_analysis(db_catalog: dict) -> dict:
    from skills.table_analysis import build_table_analysis

    table_to_l4_index, l3_codes = _load_table_to_l4_index()
    # shared_master_data/utility_support/field_anchored全部来自data_lineage.json
    # 里已经算好的信号——读盘复用而不是重算，容忍首次运行时该文件还不存在(此时
    # 这些字段全部留空，不影响其余五层分析)。
    lineage_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/data_lineage.json"
    shared_master_data: dict = {}
    utility_support_info: dict = {}
    field_anchor_info: dict = {}
    if lineage_path.exists():
        lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
        shared_master_data = lineage.get("shared_master_data", {})
        field_anchor_links = lineage.get("field_anchor_links", {})
        for node in lineage.get("nodes", []):
            key = f"{node['schema']}.{node['table']}"
            if node["zombie_flag"] == "utility_support":
                utility_support_info[key] = node.get("utility_support_reason", "")
            elif node["zombie_flag"] == "field_anchored":
                field_anchor_info[key] = field_anchor_links.get(key, [])
    # table_root_cause_analysis.json是AI辅助推理产出的L3/L4草稿(MODEL_DRAFT)，
    # 读盘合并进来；容忍首次运行时该文件还不存在(此时L3/L4全部落BLOCKED兜底)。
    root_cause_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/table_root_cause_analysis.json"
    root_cause_index: dict = {}
    if root_cause_path.exists():
        root_cause_data = json.loads(root_cause_path.read_text(encoding="utf-8"))
        root_cause_index = {item["key"]: item for item in root_cause_data.get("tables", [])}

    analysis = build_table_analysis(
        db_catalog, table_to_l4_index, l3_codes,
        shared_master_data, utility_support_info, field_anchor_info, root_cause_index,
    )
    output_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/table_analysis.json"
    output_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"table_count": len(analysis["tables"]), "output": str(output_path)}


def _build_and_write_data_lineage(db_catalog: dict) -> dict:
    """三类真实证据(视图SQL定义/外键约束/命名ETL流水线同批日志)查库建血缘图，
    再结合business_data_bridge的已确认L4关联算出DERIVED候选提示，写盘。"""
    from skills.data_lineage import (
        UTILITY_SUPPORT_TABLES,
        build_field_anchor_links,
        build_field_index,
        build_lineage_graph,
        classify_shared_master_data,
        extract_field_column_lineage,
        extract_foreign_keys,
        extract_pipeline_groups,
        extract_view_dependencies,
        flag_zombie_tables,
        suggest_l4_candidates,
    )
    from skills.sync_data_foundation import db_query
    from skills.table_analysis import business_label

    known_tables = {(t["schema"], t["table"]) for t in db_catalog["tables"] if t["schema"] != "process_analytics"}
    edges = (
        extract_view_dependencies(db_query, known_tables)
        + extract_foreign_keys(db_query, known_tables)
        + extract_pipeline_groups(db_query, known_tables)
    )
    graph = build_lineage_graph(db_catalog, business_label, edges)

    table_to_l4_index, _ = _load_table_to_l4_index()
    graph["suggested_l4_candidates"] = suggest_l4_candidates(edges, table_to_l4_index, known_tables)
    graph["shared_master_data"] = classify_shared_master_data(graph["suggested_l4_candidates"])
    graph["field_lineage"] = extract_field_column_lineage(db_query, known_tables)
    graph["field_index"] = build_field_index(db_catalog, db_query)
    field_anchor_links = build_field_anchor_links(graph["field_index"])
    graph["field_anchor_links"] = field_anchor_links
    flag_zombie_tables(
        graph["nodes"], table_to_l4_index, graph["suggested_l4_candidates"],
        field_anchor_links, UTILITY_SUPPORT_TABLES,
    )

    output_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/data_lineage.json"
    output_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    zombie_count = sum(1 for n in graph["nodes"] if n["zombie_flag"] == "suspected_zombie")
    field_anchored_count = sum(1 for n in graph["nodes"] if n["zombie_flag"] == "field_anchored")
    utility_support_count = sum(1 for n in graph["nodes"] if n["zombie_flag"] == "utility_support")
    return {
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "suspected_zombie_count": zombie_count,
        "field_anchored_count": field_anchored_count,
        "utility_support_count": utility_support_count,
        "shared_master_data_count": len(graph["shared_master_data"]),
        "edge_type_counts": graph["edge_type_counts"],
        "suggested_candidate_table_count": len(graph["suggested_l4_candidates"]),
        "field_lineage_resolved_views": len(graph["field_lineage"]["resolved_views"]),
        "field_lineage_unparsed_views": len(graph["field_lineage"]["unparsed_views"]),
        "field_index_shared_field_count": len(graph["field_index"]["fields"]),
        "output": str(output_path),
    }


def main() -> int:
    args = parse_args()
    settings = load_settings()
    workspace = Workspace(args.workspace or AGENT_ROOT / settings["workspace_dir"])
    state = workspace.load()
    if args.status:
        print(json.dumps({"agent_id": settings["agent_id"], "version": settings["version"], "workspace": str(workspace.root), "tracked_files": len(state.get("files", {})), "last_run": state.get("runs", [])[-1:]}, ensure_ascii=False, indent=2))
        return 0
    if (args.prepare_l3_analysis or args.prepare_analysis_repair
            or args.prepare_analysis_l4_refresh or args.prepare_segmented_analysis
            or args.prepare_segmented_repair or args.finalize_segmented_analysis
            or args.run_analysis_dir or args.import_analysis_output):
        from skills.l3_analysis_runner import L3AnalysisRunner

        runner = L3AnalysisRunner(AGENT_ROOT)
        if args.prepare_l3_analysis:
            snapshot_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots"
            prepared = []
            for code in args.prepare_l3_analysis:
                normalized = code.upper() if code.upper().startswith("L3-") else f"L3-{code.upper()}"
                snapshot_path = snapshot_dir / f"{normalized}.json"
                if not snapshot_path.exists():
                    raise FileNotFoundError(f"缺少模型快照：{snapshot_path}")
                run_dir = runner.prepare(snapshot_path)
                prepared.append({"l3_code": normalized, "run_dir": str(run_dir), "status": "PREPARED"})
            print(json.dumps({"status": "prepared", "runs": prepared}, ensure_ascii=False, indent=2))
            return 0
        if args.prepare_analysis_repair:
            snapshot_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots"
            package_dir = AGENT_ROOT / "07_接入记忆_Integrate_Memory/analysis_packages"
            prepared = []
            for code in args.prepare_analysis_repair:
                normalized = code.upper() if code.upper().startswith("L3-") else f"L3-{code.upper()}"
                snapshot_path = snapshot_dir / f"{normalized}.json"
                package_path = package_dir / f"{normalized}.model.json"
                if not snapshot_path.exists() or not package_path.exists():
                    raise FileNotFoundError(f"缺少快照或现有分析包：{normalized}")
                run_dir = runner.prepare_repair(snapshot_path, package_path)
                prepared.append({"l3_code": normalized, "run_dir": str(run_dir), "status": "PREPARED"})
            print(json.dumps({"status": "repair_prepared", "runs": prepared}, ensure_ascii=False, indent=2))
            return 0
        if args.prepare_analysis_l4_refresh:
            normalized = (
                args.prepare_analysis_l4_refresh.upper()
                if args.prepare_analysis_l4_refresh.upper().startswith("L3-")
                else f"L3-{args.prepare_analysis_l4_refresh.upper()}"
            )
            snapshot_path = (
                AGENT_ROOT
                / f"10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots/{normalized}.json"
            )
            package_path = (
                AGENT_ROOT
                / f"07_接入记忆_Integrate_Memory/analysis_packages/{normalized}.model.json"
            )
            if not package_path.exists():
                package_path = (
                    AGENT_ROOT
                    / f"07_接入记忆_Integrate_Memory/analysis_packages/{normalized}.reviewed.json"
                )
            if not snapshot_path.exists() or not package_path.exists():
                raise FileNotFoundError(f"缺少快照或现有分析包：{normalized}")
            run_dir = runner.prepare_l4_refresh(
                snapshot_path, package_path, args.analysis_l4_code or []
            )
            print(json.dumps({
                "status": "l4_refresh_prepared",
                "l3_code": normalized,
                "target_l4_codes": args.analysis_l4_code or [],
                "run_dir": str(run_dir),
            }, ensure_ascii=False, indent=2))
            return 0
        if args.prepare_segmented_analysis:
            normalized = (
                args.prepare_segmented_analysis.upper()
                if args.prepare_segmented_analysis.upper().startswith("L3-")
                else f"L3-{args.prepare_segmented_analysis.upper()}"
            )
            snapshot_path = AGENT_ROOT / f"10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots/{normalized}.json"
            if not snapshot_path.exists():
                raise FileNotFoundError(f"缺少模型快照：{snapshot_path}")
            run_dir = runner.prepare_segmented_l4(
                snapshot_path, args.analysis_l4_code or []
            )
            print(json.dumps({
                "status": "segmented_l4_prepared", "l3_code": normalized,
                "target_l4_codes": args.analysis_l4_code or [],
                "run_dir": str(run_dir),
            }, ensure_ascii=False, indent=2))
            return 0
        if args.prepare_segmented_repair:
            normalized = (
                args.prepare_segmented_repair.upper()
                if args.prepare_segmented_repair.upper().startswith("L3-")
                else f"L3-{args.prepare_segmented_repair.upper()}"
            )
            snapshot_path = AGENT_ROOT / f"10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots/{normalized}.json"
            package_path = runner.segmented_package_path(normalized)
            if not snapshot_path.exists() or not package_path.exists():
                raise FileNotFoundError(f"缺少快照或分段暂存包：{normalized}")
            run_dir = runner.prepare_repair(snapshot_path, package_path)
            print(json.dumps({
                "status": "segmented_repair_prepared", "l3_code": normalized,
                "run_dir": str(run_dir),
            }, ensure_ascii=False, indent=2))
            return 0
        if args.finalize_segmented_analysis:
            normalized = (
                args.finalize_segmented_analysis.upper()
                if args.finalize_segmented_analysis.upper().startswith("L3-")
                else f"L3-{args.finalize_segmented_analysis.upper()}"
            )
            snapshot_path = AGENT_ROOT / f"10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots/{normalized}.json"
            output = runner.finalize_segmented(snapshot_path)
            print(json.dumps({
                "status": "segmented_analysis_published", "l3_code": normalized,
                "analysis_package": str(output),
            }, ensure_ascii=False, indent=2))
            return 0
        if args.import_analysis_output and not args.run_analysis_dir:
            parser_error = "--import-analysis-output必须与--run-analysis-dir同时使用"
            print(f"错误：{parser_error}", file=sys.stderr)
            return 2
        if args.run_analysis_dir:
            from datetime import datetime, timezone

            from skills.l3_analysis_runner import record_rerun_history

            response = args.import_analysis_output or runner.run(args.run_analysis_dir, model=args.analysis_model)
            try:
                output = runner.validate_and_publish(args.run_analysis_dir, response)
            except ValueError as exc:
                run_dir_path = Path(args.run_analysis_dir)
                request_json = json.loads((run_dir_path / "request.json").read_text(encoding="utf-8"))
                record_rerun_history(AGENT_ROOT, {
                    "l3_code": request_json.get("l3_code", run_dir_path.name.split("_")[0]),
                    "run_dir": run_dir_path.name,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "rejected",
                    "trigger_reason": "重跑后模型输出未通过契约校验，未发布，旧分析保持不变",
                    "error": str(exc),
                    "diff": None,
                })
                raise
            print(json.dumps({"status": "published", "analysis_package": str(output)}, ensure_ascii=False, indent=2))
            return 0
    if args.sync_business_scenarios:
        from skills.business_scenario_analysis import build_scenario_analysis
        from skills.business_scenario_sync import sync_business_scenarios

        scenario_source_dir = AGENT_ROOT / "07_接入记忆_Integrate_Memory/business_scenarios"
        scenario_dest_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/business_scenarios"
        index = sync_business_scenarios(scenario_source_dir, scenario_dest_dir)

        # 场景记录同步完后，紧接着派生入口①后四环(流程现状/数据治理/任务
        # 清单/流程优化)——全部基于model_snapshots真实数据机械推导，不
        # 触碰scenario_dest_dir里刚同步的人工authoring记录。
        snapshot_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots"
        model_index_data = json.loads((snapshot_dir / "index.json").read_text(encoding="utf-8"))
        model_index = {m["l3_code"]: m for m in model_index_data["models"]}
        snapshot_cache: dict[str, dict | None] = {}

        def load_snapshot(l3_code: str) -> dict | None:
            if l3_code not in snapshot_cache:
                path = snapshot_dir / f"{l3_code}.json"
                snapshot_cache[l3_code] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            return snapshot_cache[l3_code]

        analysis_dest_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/business_scenario_analysis"
        analysis_dest_dir.mkdir(parents=True, exist_ok=True)
        analyzed_scenarios = []
        for entry in index["scenarios"]:
            scenario = json.loads((scenario_dest_dir / entry["file"]).read_text(encoding="utf-8"))
            analysis = build_scenario_analysis(scenario, model_index, load_snapshot)
            (analysis_dest_dir / f"{scenario['scenario_id']}.json").write_text(
                json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
            )
            analyzed_scenarios.append(scenario["scenario_id"])

        print(json.dumps({
            "status": "synced", "scenario_count": len(index["scenarios"]), "analyzed_scenarios": analyzed_scenarios,
        }, ensure_ascii=False, indent=2))
        return 0
    if args.build_table_analysis:
        catalog_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/db_catalog.json"
        db_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        result = _build_and_write_table_analysis(db_catalog)
        print(json.dumps({"status": "built", **result}, ensure_ascii=False, indent=2))
        return 0
    if args.build_data_lineage:
        catalog_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/db_catalog.json"
        db_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        result = _build_and_write_data_lineage(db_catalog)
        print(json.dumps({"status": "built", **result}, ensure_ascii=False, indent=2))
        return 0
    if args.build_table_root_cause_analysis:
        from skills.table_root_cause_analysis import (
            run_table_root_cause_analysis,
            write_table_root_cause_analysis,
        )

        catalog_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/db_catalog.json"
        lineage_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/data_lineage.json"
        db_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        data_lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
        table_to_l4_index, _ = _load_table_to_l4_index()

        result = run_table_root_cause_analysis(AGENT_ROOT, db_catalog, data_lineage, table_to_l4_index)
        output_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/table_root_cause_analysis.json"
        write_table_root_cause_analysis(result, output_path)
        print(json.dumps({
            "status": "published",
            "table_count": len(result["tables"]),
            "output": str(output_path),
        }, ensure_ascii=False, indent=2))
        return 0
    if args.build_db_catalog:
        from skills.db_catalog import build_catalog
        from skills.sync_data_foundation import db_query

        catalog = build_catalog(db_query)
        catalog_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/db_catalog.json"
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "built", "table_count": len(catalog["tables"]), "output": str(catalog_path)}, ensure_ascii=False, indent=2))
        return 0
    if args.refresh_business_data:
        from skills.db_catalog import build_catalog
        from skills.sync_data_foundation import db_query

        catalog = build_catalog(db_query)
        catalog_path = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/db_catalog.json"
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        lineage_result = _build_and_write_data_lineage(catalog)
        result = _build_and_write_table_analysis(catalog)
        print(json.dumps({
            "status": "refreshed",
            "db_catalog_table_count": len(catalog["tables"]),
            **result,
            "data_lineage": lineage_result,
        }, ensure_ascii=False, indent=2))
        return 0
    if args.build_model_snapshots or args.build_all_model_snapshots or args.check_source_updates or args.apply_source_updates:
        from skills.l3_model_builder import (
            L3ModelBuilder,
            load_blueprint_index,
            load_blueprint_index_from_dir,
            load_d1d6_supplement,
            load_skill_feasibility,
            load_analysis_packages,
            load_rule_records,
            load_sop_records,
            load_prepared_analysis_codes,
        )
        from skills.position_bridge import L3_POSITION_CATEGORY
        from skills.business_data_bridge import L4_BUSINESS_TABLE_MAP, load_business_table_row_counts
        from skills.sync_data_foundation import db_query
        from tools.postgres_reader import BulkPostgresL3Reader, PostgresL3Reader

        if args.build_all_model_snapshots or args.check_source_updates or args.apply_source_updates:
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
        skill_feasibility_xlsx = Path(
            "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault/"
            "EA流程架构项目/_VNW引用原件/L4流程_Skill封装可行性评估_确认最终版_v2.xlsx"
        )
        skill_feasibility = (
            load_skill_feasibility(skill_feasibility_xlsx)
            if skill_feasibility_xlsx.exists() else {}
        )
        foundation_dir = AGENT_ROOT / "07_接入记忆_Integrate_Memory/data_foundation/A_自动同步_当前有效"
        sop_csv = foundation_dir / "T19_SOP生产进度_全域_v2.0.csv"
        rule_csv = foundation_dir / "T5_规则清单_全域_v3.0.csv"
        sop_dir = Path("/Users/a112233/Desktop/流程架构项目_jasper/02_过程成果-工作产出/规则分析（Jasper）/05_SOP")
        builder = L3ModelBuilder(
            reader,
            blueprint_index,
            blueprint_dir=blueprint_dir,
            d1d6_supplement=d1d6_supplement,
            skill_feasibility=skill_feasibility,
            demo_registry=DEMO_REGISTRY,
            analysis_packages=load_analysis_packages(
                AGENT_ROOT / "07_接入记忆_Integrate_Memory/analysis_packages"
            ),
            sop_records=load_sop_records(sop_csv, sop_dir) if sop_csv.exists() and sop_dir.exists() else [],
            rule_records=load_rule_records(rule_csv) if rule_csv.exists() else [],
            prepared_analysis_codes=load_prepared_analysis_codes(
                AGENT_ROOT / "07_接入记忆_Integrate_Memory/analysis_runs"
            ),
            l3_position_category=L3_POSITION_CATEGORY,
            business_table_map=L4_BUSINESS_TABLE_MAP,
            business_table_counts=load_business_table_row_counts(db_query),
            analysis_confirmations_dir=AGENT_ROOT / "07_接入记忆_Integrate_Memory/analysis_confirmations",
        )
        source_update_mode = args.check_source_updates or args.apply_source_updates
        snapshot_dir = workspace.root / ("source_update_candidate" if source_update_mode else "model_snapshots")
        if source_update_mode and snapshot_dir.exists():
            shutil.rmtree(snapshot_dir)
        results = builder.build_and_write(codes, snapshot_dir)
        if source_update_mode:
            from skills.source_update import compare_snapshot_sets, write_update_report

            current_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots"
            report = compare_snapshot_sets(current_dir, snapshot_dir)
            index_path = snapshot_dir / "index.json"
            candidate_index = json.loads(index_path.read_text(encoding="utf-8"))
            candidate_index["source_update_summary"] = {
                "generated_at": report["generated_at"],
                "changed_l3_count": report["changed_l3_count"],
                "reanalyze_l3_count": report["reanalyze_l3_count"],
                "blocked_l3_count": report["blocked_l3_count"],
                "applied": bool(args.apply_source_updates),
            }
            index_path.write_text(json.dumps(candidate_index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            report_dir = workspace.root / "source_updates"
            write_update_report(report, report_dir / ("latest.json" if args.apply_source_updates else "latest_check.json"))
            frontend_update_dir = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/source_updates"
            if args.check_source_updates:
                write_update_report({**report, "applied": False}, frontend_update_dir / "pending.json")
                print(json.dumps({"status": "checked", "applied": False, "report": report}, ensure_ascii=False, indent=2))
                return 0
            archive_dir = report_dir / "history" / report["generated_at"].replace(":", "").replace("+", "_")
            if current_dir.exists():
                shutil.copytree(current_dir, archive_dir / "before_snapshots")
            write_update_report(report, archive_dir / "report.json")
            frontend_sync = _sync_to_frontend(snapshot_dir)
            frontend_report = AGENT_ROOT / "10_部署与运行_Deploy_and_Run/frontend/public/data/source_updates/latest.json"
            write_update_report(report, frontend_report)
            write_update_report({**report, "applied": True}, frontend_update_dir / "pending.json")
            from skills.source_update import build_history_index
            history_index = build_history_index(report_dir / "history")
            write_update_report(history_index, frontend_update_dir / "history_index.json")
            canonical_dir = workspace.root / "model_snapshots"
            if canonical_dir.exists():
                shutil.rmtree(canonical_dir)
            shutil.copytree(snapshot_dir, canonical_dir)
            print(json.dumps({"status": "source_updates_applied", "report": report, "frontend_sync": frontend_sync}, ensure_ascii=False, indent=2))
            return 0
        frontend_sync = _sync_to_frontend(snapshot_dir)
        print(json.dumps({"status": "built", "snapshots": results, "frontend_sync": frontend_sync}, ensure_ascii=False, indent=2))
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
