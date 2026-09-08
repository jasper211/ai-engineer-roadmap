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


def merge_ob_collaboration_release(
    report: dict,
    receipt_path: Path,
    manifest_path: Path,
    unregistered_path: Path | None = None,
) -> dict:
    """Merge a validated OB release into the read-only pending report.

    The collaboration receipt is not a fact snapshot and must not be presented as
    one.  This function only adds a review candidate to the existing update desk;
    it never applies the manifest, calls a model, or writes either source system.
    Draft/context-only sources are deliberately excluded from source objects.
    """
    result = json.loads(json.dumps(report, ensure_ascii=False))
    receipt_path, manifest_path = Path(receipt_path), Path(manifest_path)
    if not receipt_path.exists() or not manifest_path.exists():
        return result

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result["ob_collaboration"] = {
            "status": "INVALID",
            "error": str(exc),
            "application_mode": "MANUAL_REVIEW_REQUIRED",
        }
        return result

    release_id = str(receipt.get("release_id") or "")
    if not release_id or release_id != str(manifest.get("release_id") or ""):
        result["ob_collaboration"] = {
            "status": "INVALID",
            "release_id": release_id,
            "error": "receipt and manifest release_id do not match",
            "application_mode": "MANUAL_REVIEW_REQUIRED",
        }
        return result

    source_by_id = {
        str(item.get("source_id")): item
        for item in manifest.get("sources", [])
        if item.get("source_id")
    }
    publishable_ids = {
        str(item.get("source_id"))
        for item in receipt.get("source_results", [])
        if item.get("valid") and item.get("publishable") and item.get("source_id")
    }
    publishable_objects = sorted({
        str(source_by_id[source_id].get("relative_path") or source_id)
        for source_id in publishable_ids
        if source_id in source_by_id
    })

    existing = {item.get("l3_code"): item for item in result.get("changes", [])}
    for affected in receipt.get("affected_l3", []):
        code = str(affected.get("l3_code") or "")
        if not code:
            continue
        panels = sorted({str(value) for value in affected.get("affected_panels", []) if value})
        action = "REANALYSIS_REQUIRED" if affected.get("reanalysis_candidate") else "FACTS_REFRESHED"
        if code in existing:
            item = existing[code]
            item["affected_panels"] = sorted(set(item.get("affected_panels", [])) | set(panels))
            item["changed_scopes"] = sorted(set(item.get("changed_scopes", [])) | {"ob_knowledge"})
            item["added_source_objects"] = sorted(set(item.get("added_source_objects", [])) | set(publishable_objects))
            item["origins"] = sorted(set(item.get("origins", ["SSOT_SNAPSHOT"])) | {"OB_COLLABORATION"})
            if action == "REANALYSIS_REQUIRED":
                item["action"] = action
        else:
            item = {
                "l3_code": code,
                "status": "CHANGED",
                "action": action,
                "changed_scopes": ["ob_knowledge"],
                "affected_panels": panels,
                "previous_analysis_input_hash": "",
                "current_analysis_input_hash": "",
                "added_source_objects": publishable_objects,
                "removed_source_objects": [],
                "origins": ["OB_COLLABORATION"],
                "release_id": release_id,
            }
            result.setdefault("changes", []).append(item)
            existing[code] = item

    unregistered_count = 0
    if unregistered_path and Path(unregistered_path).exists():
        try:
            unregistered = json.loads(Path(unregistered_path).read_text(encoding="utf-8"))
            if isinstance(unregistered, list):
                unregistered_count = len(unregistered)
            elif isinstance(unregistered, dict):
                rows = unregistered.get("files") or unregistered.get("items") or unregistered.get("unregistered_files") or []
                unregistered_count = len(rows) if isinstance(rows, list) else int(unregistered.get("count", 0) or 0)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            unregistered_count = 0

    result["changes"] = sorted(result.get("changes", []), key=lambda item: item.get("l3_code", ""))
    result["changed_l3_count"] = len(result["changes"])
    result["reanalyze_l3_count"] = sum(item.get("action") == "REANALYSIS_REQUIRED" for item in result["changes"])
    result["blocked_l3_count"] = sum(item.get("action") == "BLOCKED_INPUT" for item in result["changes"])
    result["ob_collaboration"] = {
        "status": "READY_FOR_REVIEW",
        "release_id": release_id,
        "published_at": manifest.get("published_at", ""),
        "processed_at": receipt.get("processed_at", ""),
        "valid_source_count": sum(bool(item.get("valid")) for item in receipt.get("source_results", [])),
        "publishable_source_count": len(publishable_ids),
        "context_only_source_count": sum(
            bool(item.get("valid")) and not bool(item.get("publishable"))
            for item in receipt.get("source_results", [])
        ),
        "unregistered_file_count": unregistered_count,
        "application_mode": "MANUAL_REVIEW_REQUIRED",
    }
    return result


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
