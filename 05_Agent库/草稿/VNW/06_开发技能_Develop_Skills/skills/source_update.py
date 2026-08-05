"""Phase 2: compare rebuilt L3 facts with the currently published snapshot set.

This module is deterministic and performs no source writes or model calls.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


SCOPES = {
    "blueprint": ("blueprint", ["A", "B", "C", "F"]),
    "l4s": ("l4_delivery", ["A", "C", "D", "E", "F"]),
    "value_nodes": ("value_nodes", ["A", "B", "E", "F"]),
    "vn_l4_mappings": ("vn_l4_mapping", ["A", "B", "C", "E", "F"]),
    "l2_capabilities": ("l2_capability", ["E", "F"]),
    "kpi_mappings": ("kpi", ["D", "F"]),
    "value_stream_mappings": ("value_stream", ["A", "F"]),
    "model_readiness": ("readiness", ["C", "D", "F"]),
    "evidence_registry": ("evidence", ["F"]),
}


def _read_models(directory: Path) -> dict[str, dict]:
    result = {}
    for path in Path(directory).glob("L3-*.json"):
        if path.name.endswith(".manifest.json"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("l3_code"):
            result[payload["l3_code"]] = payload
    return result


def _source_objects(model: dict) -> set[str]:
    return {
        str(item.get("source", {}).get("source_object", ""))
        for item in model.get("evidence_registry", [])
        if item.get("source", {}).get("source_object")
    }


def compare_snapshot_sets(before_dir: Path, after_dir: Path) -> dict:
    before = _read_models(before_dir)
    after = _read_models(after_dir)
    changes = []
    all_codes = sorted(set(before) | set(after))
    for code in all_codes:
        old, new = before.get(code), after.get(code)
        if old is None:
            scopes = [value[0] for value in SCOPES.values()]
            panels = sorted({panel for _, values in SCOPES.values() for panel in values})
            status = "ADDED"
        elif new is None:
            scopes, panels, status = ["l3_removed"], ["ALL"], "REMOVED"
        else:
            changed = [value for key, value in SCOPES.items() if old.get(key) != new.get(key)]
            scopes = [item[0] for item in changed]
            panels = sorted({panel for item in changed for panel in item[1]})
            status = "CHANGED" if scopes else "UNCHANGED"
        if status == "UNCHANGED":
            continue
        old_hash = (old or {}).get("analysis_input_hash", "")
        new_hash = (new or {}).get("analysis_input_hash", "")
        analysis_status = (new or old or {}).get("analysis", {}).get("analysis_status", "")
        if status == "REMOVED":
            action = "REMOVE_FROM_CURRENT_SET"
        elif not (new or {}).get("model_readiness", {}).get("model_generation_allowed", False):
            action = "BLOCKED_INPUT"
        elif analysis_status in {"MODEL_DRAFT", "REVIEWED"} and old_hash != new_hash:
            action = "REANALYSIS_REQUIRED"
        else:
            action = "FACTS_REFRESHED"
        changes.append({
            "l3_code": code,
            "status": status,
            "action": action,
            "changed_scopes": scopes,
            "affected_panels": panels,
            "previous_analysis_input_hash": old_hash,
            "current_analysis_input_hash": new_hash,
            "added_source_objects": sorted(_source_objects(new or {}) - _source_objects(old or {})),
            "removed_source_objects": sorted(_source_objects(old or {}) - _source_objects(new or {})),
        })
    return {
        "schema_version": "vnw.source-update.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "before_l3_count": len(before),
        "after_l3_count": len(after),
        "changed_l3_count": len(changes),
        "reanalyze_l3_count": sum(item["action"] == "REANALYSIS_REQUIRED" for item in changes),
        "blocked_l3_count": sum(item["action"] == "BLOCKED_INPUT" for item in changes),
        "changes": changes,
    }


def write_update_report(report: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _event_id_to_display_time(event_id: str) -> str:
    """事件目录名形如'2026-08-05T162215.145222_0000'(由generated_at经
    replace(":","").replace("+","_")而来)，还原成可读ISO时间仅用于展示排序，
    不追求精确时区还原。解析失败时如实返回原始目录名，不猜。"""
    try:
        date_part, rest = event_id.split("T", 1)
        time_and_us, _, _tz = rest.rpartition("_")
        hhmmss, _, micros = time_and_us.partition(".")
        hh, mm, ss = hhmmss[0:2], hhmmss[2:4], hhmmss[4:6]
        return f"{date_part}T{hh}:{mm}:{ss}.{micros or '000000'}+00:00"
    except Exception:
        return event_id


def build_history_index(history_dir: Path) -> dict:
    """扫描source_updates/history/<event_id>/目录，汇总每次'应用源头更新'的
    留存记录——原因(changed_scopes/新增移除来源对象)、内容(reanalyze/blocked
    计数、逐L3明细)、时间——供前端"重跑记录·历史留存"展示。2026-08-05之前的
    历史事件只归档了快照备份(before_snapshots)，没有保留report.json，如实
    标注"早于留存机制上线"，不倒推假造原因。"""
    entries = []
    history_dir = Path(history_dir)
    if history_dir.exists():
        for event_dir in history_dir.iterdir():
            if not event_dir.is_dir():
                continue
            report_path = event_dir / "report.json"
            if report_path.exists():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                entries.append({
                    "event_id": event_dir.name,
                    "generated_at": report["generated_at"],
                    "has_report": True,
                    "changed_l3_count": report["changed_l3_count"],
                    "reanalyze_l3_count": report["reanalyze_l3_count"],
                    "blocked_l3_count": report["blocked_l3_count"],
                    "changes": report["changes"],
                })
            else:
                entries.append({
                    "event_id": event_dir.name,
                    "generated_at": _event_id_to_display_time(event_dir.name),
                    "has_report": False,
                    "changed_l3_count": None,
                    "reanalyze_l3_count": None,
                    "blocked_l3_count": None,
                    "changes": [],
                    "note": "早于留存机制上线(2026-08-05)，仅归档了快照备份，原因/内容记录未保留",
                })
    entries.sort(key=lambda e: e["generated_at"], reverse=True)
    return {
        "schema_version": "vnw.source-update-history.v1",
        "entries": entries,
    }
