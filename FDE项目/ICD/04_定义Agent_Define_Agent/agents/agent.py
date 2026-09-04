#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD Agent · 主循环入口（CLI）

本阶段（T002）提供最小可运行骨架，三个命令：
  --status           报告结构化项目状态（agent_id/version/stage/险企数/源数/
                     各 access_status 数量/数据库是否存在及路径）
  --validate-config  严格校验 settings.json 与 source_registry.json；
                     非法 JSON、重复险企、未知险企引用、UNVERIFIED 带 URL/format
                     等一律非零退出
  --init-db          从已验收 data_contract 的 DDL 建 12 张表，导入险企/数据源/
                     错误代码基础数据；幂等，不删除 fetch_run 或业务表已有行

约束（对齐任务书 T002）：
- 本任务不访问网络、不解析真实披露文件。
- 所有路径从 Path(__file__) 推导，不依赖当前工作目录（cwd）。
- 仅使用 Python 标准库；异常输出不含凭证或完整请求头。
- 数据库默认写入 ICD 专属 07_接入记忆_Integrate_Memory/data/icd.db；
  测试必须用 --db-path 指向临时目录，不污染默认数据库。

目录方法论：agents/tools/memory 各自嵌套在编号目录里，编号只是给人看的顺序
标识，import 用的仍是不带编号前缀的包名——因此 sys.path 要把
05_集成工具_Integrate_Tools 与 07_接入记忆_Integrate_Memory 两个编号目录
（而不是 ICD 根目录）加进去。
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

AGENTS_DIR = Path(__file__).resolve().parent          # 04_定义Agent_Define_Agent/agents/
DEFINE_DIR = AGENTS_DIR.parent                         # 04_定义Agent_Define_Agent/
ICD_DIR = DEFINE_DIR.parent                            # FDE项目/ICD/

for _pkg_dir in (
    "05_集成工具_Integrate_Tools",
    "07_接入记忆_Integrate_Memory",
    "06_开发技能_Develop_Skills",
):
    sys.path.insert(0, str(ICD_DIR / _pkg_dir))        # 让 tools/memory/skills 能被当作包 import

from memory import workspace
from skills import fetch_disclosure, parse_disclosure, rbc_index_discovery
from tools import config_loader, fetch_recorder, sqlite_store

SETTINGS_PATH = ICD_DIR / "02_配置项目_Configure_Project" / "settings.json"
REGISTRY_PATH = ICD_DIR / "02_配置项目_Configure_Project" / "source_registry.json"


def _resolve_settings(args) -> Path:
    return Path(args.settings).resolve() if args.settings else SETTINGS_PATH


def _resolve_registry(args) -> Path:
    return Path(args.registry).resolve() if args.registry else REGISTRY_PATH


# ---------------------------------------------------------------------------
# --status
# ---------------------------------------------------------------------------
def cmd_status(args) -> int:
    settings_path = _resolve_settings(args)
    registry_path = _resolve_registry(args)
    db_path = workspace.resolve_db_path(args.db_path)

    result = {
        "agent_id": None,
        "version": None,
        "stage": None,
        "insurer_count": None,
        "source_count": None,
        "access_status_counts": {},
        "database": {"exists": db_path.exists(), "path": str(db_path)},
        "errors": [],
    }

    try:
        settings = config_loader.load_json(settings_path)
        result["agent_id"] = settings.get("agent_id")
        result["version"] = settings.get("version")
        result["stage"] = settings.get("stage") or settings.get("status")
    except Exception as e:  # noqa: BLE001 —— 状态输出 best-effort，不因单文件失败崩溃
        result["errors"].append(f"settings 加载失败: {e}")

    try:
        registry = config_loader.load_json(registry_path)
        insurers = registry.get("insurers", [])
        sources = registry.get("sources", [])
        result["insurer_count"] = len(insurers)
        result["source_count"] = len(sources)
        counts = {}
        for s in sources:
            st = s.get("access_status")
            counts[st] = counts.get(st, 0) + 1
        result["access_status_counts"] = counts
    except Exception as e:  # noqa: BLE001
        result["errors"].append(f"registry 加载失败: {e}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# --validate-config
# ---------------------------------------------------------------------------
def cmd_validate_config(args) -> int:
    settings_path = _resolve_settings(args)
    registry_path = _resolve_registry(args)

    errors: List[str] = []
    try:
        settings = config_loader.load_json(settings_path)
        errors.extend(config_loader.validate_settings(settings))
    except Exception as e:  # noqa: BLE001
        errors.append(f"settings 校验失败: {e}")

    try:
        registry = config_loader.load_json(registry_path)
        errors.extend(config_loader.validate_registry(registry))
    except Exception as e:  # noqa: BLE001
        errors.append(f"registry 校验失败: {e}")

    if errors:
        for msg in errors:
            print(f"[ERROR] {msg}", file=sys.stderr)
        print(f"配置校验失败：{len(errors)} 处错误", file=sys.stderr)
        return 1

    print("配置校验通过：settings 与 source_registry 均合规")
    return 0


# ---------------------------------------------------------------------------
# --init-db
# ---------------------------------------------------------------------------
def cmd_init_db(args) -> int:
    # 关键门禁：在解析任何 DB 路径、创建目录或连接 SQLite 之前，先完整校验
    # settings 与 registry。任何违规一律非零退出，绝不触碰默认或覆盖数据库
    # （对齐 Codex Round 1 返工要求：写路径不得绕过严格配置门禁）。
    settings_path = _resolve_settings(args)
    registry_path = _resolve_registry(args)

    errors: List[str] = []
    registry = None

    try:
        settings = config_loader.load_json(settings_path)
        errors.extend(config_loader.validate_settings(settings))
    except Exception as e:  # noqa: BLE001
        errors.append(f"settings 校验失败: {e}")

    try:
        registry = config_loader.load_json(registry_path)
        errors.extend(config_loader.validate_registry(registry))
    except Exception as e:  # noqa: BLE001
        errors.append(f"registry 校验失败: {e}")

    if errors:
        for msg in errors:
            print(f"[ERROR] {msg}", file=sys.stderr)
        print(f"配置校验失败：{len(errors)} 处错误；数据库未创建、未修改", file=sys.stderr)
        return 1

    # 校验通过后才解析 DB 路径（resolve 仅做路径规整，无目录/文件副作用）
    db_path = workspace.resolve_db_path(args.db_path)
    # 主体隔离迁移需要 raw_data 根（移动误归属快照）；resolve 无副作用。
    raw_root = workspace.resolve_raw_data_root(args.raw_data_root)

    try:
        summary = sqlite_store.init_db(db_path, registry, raw_data_root=raw_root)
    except sqlite_store.SchemaMigrationRequired as e:
        print(f"[ERROR] Schema 迁移需要处理: {e}", file=sys.stderr)
        print("数据库未修改。请按 data_contract.md 3.6 迁移说明重建旧版 fulfillment_ratio 表后再初始化。", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        # 异常信息仅输出异常类型与消息，绝不输出凭证/请求头
        print(f"[ERROR] 数据库初始化失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    summary["database"] = {"path": str(db_path), "exists": True}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# --fetch
# ---------------------------------------------------------------------------
RESULT_EXIT_CODE = {
    "OK": 0,
    "UNCHANGED": 0,
    "DRY_RUN": 0,
    "REJECTED": 2,
    "HTTP_ERROR": 3,
    "NETWORK_ERROR": 4,
    "SNAPSHOT_ERROR": 5,
    "DB_ERROR": 5,
}


def cmd_fetch(args) -> int:
    # 写路径门禁：在解析 DB / raw_data 路径、连接 SQLite 之前先完整校验配置。
    settings_path = _resolve_settings(args)
    registry_path = _resolve_registry(args)

    errors: List[str] = []
    try:
        settings = config_loader.load_json(settings_path)
        errors.extend(config_loader.validate_settings(settings))
    except Exception as e:  # noqa: BLE001
        errors.append(f"settings 校验失败: {e}")
    try:
        registry = config_loader.load_json(registry_path)
        errors.extend(config_loader.validate_registry(registry))
    except Exception as e:  # noqa: BLE001
        errors.append(f"registry 校验失败: {e}")

    if errors:
        for msg in errors:
            print(f"[ERROR] {msg}", file=sys.stderr)
        print("配置校验失败；未抓取、未写入快照或数据库", file=sys.stderr)
        return 1

    db_path = workspace.resolve_db_path(args.db_path)
    raw_root = workspace.resolve_raw_data_root(args.raw_data_root)

    try:
        conn = sqlite_store.connect(db_path)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] 数据库连接失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    try:
        src = fetch_recorder.get_source(conn, args.fetch)
    except sqlite3.OperationalError as e:
        conn.close()
        print(f"[ERROR] 数据库未初始化（请先 --init-db）: {e}", file=sys.stderr)
        return 1

    if src is None:
        conn.close()
        print(f"[ERROR] 未找到 source_id={args.fetch}（请先 --init-db 且确认源存在）", file=sys.stderr)
        return 1

    result = fetch_disclosure.fetch_one_source(
        conn, src, raw_root, dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    code = RESULT_EXIT_CODE.get(result.get("result"), 1)
    conn.close()
    return code


# ---------------------------------------------------------------------------
# --parse
# ---------------------------------------------------------------------------
PARSE_EXIT_CODE = {
    "OK": 0,
    "STRUCTURE_MISMATCH": 2,
    "ZERO_RECORD": 3,
    "NO_FETCH_RUN": 1,
    "SNAPSHOT_MISSING": 1,
    "UNSUPPORTED_FORMAT": 1,
    "DB_ERROR": 5,
}


def cmd_parse(args) -> int:
    # 写路径门禁：在解析 DB / raw_data 路径、连接 SQLite 之前先完整校验配置。
    settings_path = _resolve_settings(args)
    registry_path = _resolve_registry(args)

    errors: List[str] = []
    try:
        settings = config_loader.load_json(settings_path)
        errors.extend(config_loader.validate_settings(settings))
    except Exception as e:  # noqa: BLE001
        errors.append(f"settings 校验失败: {e}")
    try:
        registry = config_loader.load_json(registry_path)
        errors.extend(config_loader.validate_registry(registry))
    except Exception as e:  # noqa: BLE001
        errors.append(f"registry 校验失败: {e}")

    if errors:
        for msg in errors:
            print(f"[ERROR] {msg}", file=sys.stderr)
        print("配置校验失败；未解析、未写入数据库", file=sys.stderr)
        return 1

    db_path = workspace.resolve_db_path(args.db_path)
    raw_root = workspace.resolve_raw_data_root(args.raw_data_root)

    try:
        conn = sqlite_store.connect(db_path)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] 数据库连接失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    try:
        src = fetch_recorder.get_source(conn, args.parse)
    except sqlite3.OperationalError as e:
        conn.close()
        print(f"[ERROR] 数据库未初始化（请先 --init-db）: {e}", file=sys.stderr)
        return 1

    if src is None:
        conn.close()
        print(f"[ERROR] 未找到 source_id={args.parse}（请先 --init-db 且确认源存在）", file=sys.stderr)
        return 1

    result = parse_disclosure.parse_one_source(conn, src, raw_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    code = PARSE_EXIT_CODE.get(result.get("result"), 1)
    conn.close()
    return code


# ---------------------------------------------------------------------------
# --discover（T008：只读，从索引快照确定性发现目标 PDF 链接）
# ---------------------------------------------------------------------------
def cmd_discover(args) -> int:
    # 只读命令：校验配置 → 读取该源最新成功抓取的索引快照 → 确定性发现 PDF 链接。
    settings_path = _resolve_settings(args)
    registry_path = _resolve_registry(args)

    errors: List[str] = []
    try:
        settings = config_loader.load_json(settings_path)
        errors.extend(config_loader.validate_settings(settings))
    except Exception as e:  # noqa: BLE001
        errors.append(f"settings 校验失败: {e}")
    try:
        registry = config_loader.load_json(registry_path)
        errors.extend(config_loader.validate_registry(registry))
    except Exception as e:  # noqa: BLE001
        errors.append(f"registry 校验失败: {e}")

    if errors:
        for msg in errors:
            print(f"[ERROR] {msg}", file=sys.stderr)
        print("配置校验失败；未发现、未写入任何数据", file=sys.stderr)
        return 1

    db_path = workspace.resolve_db_path(args.db_path)
    raw_root = workspace.resolve_raw_data_root(args.raw_data_root)

    try:
        conn = sqlite_store.connect(db_path)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] 数据库连接失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    try:
        src = fetch_recorder.get_source(conn, args.discover)
    except sqlite3.OperationalError as e:
        conn.close()
        print(f"[ERROR] 数据库未初始化（请先 --init-db）: {e}", file=sys.stderr)
        return 1
    if src is None:
        conn.close()
        print(f"[ERROR] 未找到 source_id={args.discover}（请先 --init-db 且确认源存在）", file=sys.stderr)
        return 1

    run = parse_disclosure._latest_ok_run(conn, args.discover)
    if run is None:
        conn.close()
        print(json.dumps({
            "source_id": args.discover, "result": "NO_FETCH_RUN",
            "message": "未找到可发现索引的成功抓取（请先 --fetch 该索引源）",
        }, ensure_ascii=False, indent=2))
        return 1

    try:
        fpath = parse_disclosure._snapshot_file(raw_root, run["snapshot_path"])
    except ValueError as e:
        conn.close()
        print(json.dumps({"source_id": args.discover, "result": "SNAPSHOT_MISSING", "message": str(e)}, ensure_ascii=False, indent=2))
        return 1
    if not fpath.exists():
        conn.close()
        print(json.dumps({"source_id": args.discover, "result": "SNAPSHOT_MISSING", "message": f"快照不存在: {fpath}"}, ensure_ascii=False, indent=2))
        return 1
    try:
        html = fpath.read_bytes()
    except OSError as e:
        conn.close()
        print(json.dumps({"source_id": args.discover, "result": "SNAPSHOT_MISSING", "message": f"快照读取失败: {e}"}, ensure_ascii=False, indent=2))
        return 1

    # 从 parser_hint 提取已登记目标文件名（消歧选择器，可选；无则要求唯一候选）
    hint = None
    hint_text = src.get("parser_hint") or ""
    m = re.search(r"([A-Za-z0-9][\w\s%.-]*\.pdf)", hint_text, re.IGNORECASE)
    if m:
        hint = m.group(1).strip()

    candidates = rbc_index_discovery.extract_disclosure_pdf_candidates(html)
    conn.close()
    try:
        url = rbc_index_discovery.discover_disclosure_pdf(html, filename_hint=hint)
    except rbc_index_discovery.RbcIndexDiscoveryError as e:
        print(json.dumps({
            "source_id": args.discover, "result": "AMBIGUOUS_OR_NO_MATCH",
            "message": str(e), "candidate_count": len(candidates), "filename_hint": hint,
        }, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps({
        "source_id": args.discover, "result": "OK",
        "discovered_pdf_url": url, "candidate_count": len(candidates),
        "filename_hint": hint, "run_id": run["run_id"],
    }, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agent.py",
        description="ICD Agent CLI：--status / --validate-config / --init-db / --fetch / --discover / --parse",
    )
    parser.add_argument("--status", action="store_true", help="报告结构化项目状态")
    parser.add_argument("--validate-config", action="store_true", help="严格校验配置")
    parser.add_argument("--init-db", action="store_true", help="初始化 SQLite（幂等）")
    parser.add_argument("--fetch", type=int, metavar="SOURCE_ID", help="按 source_id 抓取单个数据源（写快照与 fetch_run）")
    parser.add_argument("--dry-run", action="store_true", help="配合 --fetch：只抓取并计算哈希，不写快照与数据库")
    parser.add_argument("--parse", type=int, metavar="SOURCE_ID", help="按 source_id 解析最新成功抓取的快照（写 fulfillment_ratio 与 parse_result）")
    parser.add_argument("--discover", type=int, metavar="SOURCE_ID", help="按 source_id 读取最新索引快照，确定性发现目标 PDF 链接（只读，不写数据）")
    parser.add_argument("--db-path", help="SQLite 路径覆盖（测试用临时目录；默认 data/icd.db）")
    parser.add_argument("--raw-data-root", help="raw_data 根目录覆盖（测试用临时目录；默认 07_接入记忆_Integrate_Memory/raw_data）")
    parser.add_argument("--settings", help="settings.json 路径覆盖（默认读取配置目录）")
    parser.add_argument("--registry", help="source_registry.json 路径覆盖（默认读取配置目录）")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    if args.validate_config:
        return cmd_validate_config(args)
    if args.init_db:
        return cmd_init_db(args)
    if args.fetch is not None:
        return cmd_fetch(args)
    if args.parse is not None:
        return cmd_parse(args)
    if args.discover is not None:
        return cmd_discover(args)
    # 默认（含 --status 或无参数）都走状态报告
    return cmd_status(args)


if __name__ == "__main__":
    sys.exit(main())
