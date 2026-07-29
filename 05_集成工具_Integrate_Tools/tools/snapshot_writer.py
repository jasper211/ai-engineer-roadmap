"""确定性写入L3模型快照和manifest。"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def write_snapshot(payload: dict, output_dir: Path) -> dict:
    if not payload.get("l3_code"):
        raise ValueError("快照缺少l3_code")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = snapshot_hash(payload)
    snapshot_path = output_dir / f"{payload['l3_code']}.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {
        "l3_code": payload["l3_code"],
        "snapshot_file": snapshot_path.name,
        "snapshot_hash": digest,
        "generated_at": datetime.now(UTC).isoformat(),
        "schema_version": payload.get("schema_version", ""),
    }
    manifest_path = output_dir / f"{payload['l3_code']}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {**manifest, "snapshot_path": str(snapshot_path), "manifest_path": str(manifest_path)}

