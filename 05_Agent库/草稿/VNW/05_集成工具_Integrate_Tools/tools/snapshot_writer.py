"""确定性写入L3模型快照及其manifest。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def write_snapshot(payload: dict, output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    code = payload["l3_code"]
    digest = snapshot_hash(payload)
    snapshot_path = output_dir / f"{code}.json"
    manifest_path = output_dir / f"{code}.manifest.json"
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "l3_code": code,
        "schema_version": payload.get("schema_version", ""),
        "snapshot_hash": digest,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_file": snapshot_path.name,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
