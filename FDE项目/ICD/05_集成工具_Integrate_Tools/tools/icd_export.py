"""ICD 下游交换包：稳定契约、最新成功版本、证据字段与内容哈希。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from tools import icd_health, icd_query


CONTRACT_VERSION = "1.0.0"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(db_path: Path | str, raw_root: Path | str) -> Dict[str, Any]:
    health = icd_health.check(db_path, raw_root)
    if health["status"] == "CRITICAL":
        raise ValueError("ICD 健康状态为 CRITICAL，禁止发布交换包")
    # checked_at 是执行噪声，不属于数据版本；导出包移除它，避免同一数据连续导出
    # 产生不同内容哈希。时效判断结论和 stale 列表仍完整保留。
    health = dict(health)
    health.pop("checked_at", None)
    with icd_query.ICDClient.open_readonly(db_path) as client:
        fulfillment = []
        for code in sorted({x["insurer_code"] for x in client.coverage(disclosure_type="fulfillment_ratio")["data"]}):
            fulfillment.extend(client.fulfillment(insurer_code=code, limit=5000)["data"])
        fulfillment.sort(key=lambda x: (
            x["insurer_code"], x["product_name_raw"], x["metric_type"],
            x["scope_currency_raw"], x["report_year"], x["observation_year_raw"]
        ))
        rbc = client.rbc(limit=1000)["data"]
        coverage = client.coverage()["data"]
    return {"health": health, "fulfillment": fulfillment, "rbc": rbc, "coverage": coverage}


def write(bundle: Dict[str, Any], output_root: Path | str) -> Dict[str, Any]:
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    fulfillment_bytes = b"".join(_json_bytes(row) for row in bundle["fulfillment"])
    files = {
        "fulfillment_ratio.jsonl": fulfillment_bytes,
        "rbc_statement.json": _json_bytes(bundle["rbc"]),
        "coverage_status.json": _json_bytes(bundle["coverage"]),
        "health.json": _json_bytes(bundle["health"]),
    }
    file_meta = {name: {"sha256": _sha(body), "bytes": len(body)} for name, body in files.items()}
    identity = _sha(_json_bytes({"contract_version": CONTRACT_VERSION, "files": file_meta}))[:16]
    bundle_id = f"icd-exchange-v1-{identity}"
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "bundle_id": bundle_id,
        "release_status": "READY" if bundle["health"]["status"] == "HEALTHY" else "PARTIAL_COVERAGE",
        "data_as_of": max((x.get("fetched_at") or "" for x in bundle["fulfillment"] + bundle["rbc"]), default=""),
        "record_counts": {"fulfillment_ratio": len(bundle["fulfillment"]), "rbc_statement": len(bundle["rbc"]), "coverage_status": len(bundle["coverage"])},
        "files": file_meta,
        "consumer_rules": [
            "normalized_value 和 solvency_ratio 均为小数；1.0=100%",
            "normalized_value=null 不等于0",
            "仅含每个自然业务键的最新成功版本",
            "PARTIAL_COVERAGE 必须连同 coverage_status.json 展示缺口",
            "每条业务记录的 run_id/sha256/source_url 是证据链，不得删除",
        ],
    }
    files["manifest.json"] = _json_bytes(manifest)
    final = root / bundle_id
    if final.exists():
        for name, body in files.items():
            if not (final / name).is_file() or (final / name).read_bytes() != body:
                raise OSError(f"已存在交换包内容不一致: {final}")
        return {**manifest, "path": str(final), "reused": True}
    temp = root / f".tmp-{uuid.uuid4().hex}"
    try:
        temp.mkdir()
        for name, body in files.items():
            path = temp / name
            with path.open("wb") as fh:
                fh.write(body); fh.flush(); os.fsync(fh.fileno())
        os.replace(temp, final)
    except BaseException:
        if temp.exists():
            shutil.rmtree(temp)
        raise
    return {**manifest, "path": str(final), "reused": False}
