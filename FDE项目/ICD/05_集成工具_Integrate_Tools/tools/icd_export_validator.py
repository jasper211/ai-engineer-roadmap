"""ICD 交换包消费者验收器：不信任生产方，独立验证文件与语义契约。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List


FILES = {"fulfillment_ratio.jsonl", "rbc_statement.json", "coverage_status.json", "health.json"}
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
PERCENT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*%\s*$")
COVERAGE = {"FULL", "PARTIAL", "MISSING", "BLOCKED", "UNVERIFIED"}


def _error(errors: List[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _read_json(path: Path, errors: List[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name} 无法读取为 JSON: {exc}")
        return None


def validate(bundle_path: Path | str) -> Dict[str, Any]:
    root = Path(bundle_path).resolve()
    errors: List[str] = []
    if not root.is_dir():
        return {"result": "REJECTED", "bundle_path": str(root), "errors": ["交换包目录不存在"], "exit_code": 2}
    manifest = _read_json(root / "manifest.json", errors)
    if not isinstance(manifest, dict):
        return {"result": "REJECTED", "bundle_path": str(root), "errors": errors or ["manifest 必须是对象"], "exit_code": 2}
    _error(errors, manifest.get("contract_version") == "1.0.0", "不支持的 contract_version")
    _error(errors, manifest.get("bundle_id") == root.name, "bundle_id 与目录名不一致")
    _error(errors, manifest.get("release_status") in {"READY", "PARTIAL_COVERAGE"}, "非法 release_status")
    meta = manifest.get("files")
    _error(errors, isinstance(meta, dict) and set(meta) == FILES, "manifest.files 文件集合不符合 v1 契约")
    if isinstance(meta, dict):
        identity_body = (json.dumps(
            {"contract_version": "1.0.0", "files": meta}, ensure_ascii=False,
            sort_keys=True, separators=(",", ":")
        ) + "\n").encode()
        expected_id = f"icd-exchange-v1-{hashlib.sha256(identity_body).hexdigest()[:16]}"
        _error(errors, manifest.get("bundle_id") == expected_id, "bundle_id 无法由文件元数据独立重算")
    if isinstance(meta, dict):
        for name in FILES:
            path, item = root / name, meta.get(name)
            if not path.is_file():
                errors.append(f"缺少文件: {name}"); continue
            if not isinstance(item, dict):
                errors.append(f"缺少文件元数据: {name}"); continue
            body = path.read_bytes()
            _error(errors, item.get("bytes") == len(body), f"{name} 字节数不一致")
            _error(errors, item.get("sha256") == hashlib.sha256(body).hexdigest(), f"{name} SHA-256 不一致")

    fulfillment = []
    try:
        for line_no, line in enumerate((root / "fulfillment_ratio.jsonl").read_text(encoding="utf-8").splitlines(), 1):
            try: fulfillment.append(json.loads(line))
            except json.JSONDecodeError as exc: errors.append(f"fulfillment_ratio.jsonl 第{line_no}行非法 JSON: {exc}")
    except OSError as exc:
        errors.append(f"fulfillment_ratio.jsonl 无法读取: {exc}")
    rbc = _read_json(root / "rbc_statement.json", errors)
    coverage = _read_json(root / "coverage_status.json", errors)
    health = _read_json(root / "health.json", errors)
    _error(errors, isinstance(rbc, list), "rbc_statement.json 必须是数组")
    _error(errors, isinstance(coverage, list), "coverage_status.json 必须是数组")
    _error(errors, isinstance(health, dict), "health.json 必须是对象")

    f_required = {"insurer_code", "product_name_raw", "metric_type", "report_year", "observation_year_raw", "scope_currency_raw", "raw_value", "normalized_value", "unit", "run_id", "source_url", "fetched_at", "sha256", "snapshot_path"}
    keys = set()
    for i, row in enumerate(fulfillment):
        if not isinstance(row, dict): errors.append(f"分红记录[{i}]必须是对象"); continue
        _error(errors, f_required <= set(row), f"分红记录[{i}]缺少必需字段")
        _error(errors, isinstance(row.get("run_id"), int) and not isinstance(row.get("run_id"), bool) and row["run_id"] > 0, f"分红记录[{i}] run_id 非正整数")
        _error(errors, row.get("unit") == "percent", f"分红记录[{i}] unit 非 percent")
        _error(errors, row.get("normalized_value") is None or isinstance(row.get("normalized_value"), (int, float)), f"分红记录[{i}] normalized_value 类型错误")
        _error(errors, isinstance(row.get("sha256"), str) and HASH_RE.fullmatch(row["sha256"]) is not None, f"分红记录[{i}] sha256 非法")
        match = PERCENT_RE.fullmatch(str(row.get("raw_value", "")))
        if match and isinstance(row.get("normalized_value"), (int, float)):
            _error(errors, abs(row["normalized_value"] - float(match.group(1)) / 100) < 1e-9,
                   f"分红记录[{i}] 原文百分比与标准值不一致")
        key = tuple(row.get(x) for x in ("insurer_code", "product_name_raw", "metric_type", "scope_currency_raw", "report_year", "observation_year_raw"))
        if key in keys: errors.append(f"分红自然键重复: {key!r}")
        keys.add(key)

    r_required = {"insurer_code", "legal_entity_name_raw", "report_year", "solvency_ratio", "solvency_ratio_raw", "run_id", "source_url", "sha256"}
    rkeys = set()
    for i, row in enumerate(rbc if isinstance(rbc, list) else []):
        if not isinstance(row, dict): errors.append(f"RBC记录[{i}]必须是对象"); continue
        _error(errors, r_required <= set(row), f"RBC记录[{i}]缺少必需字段")
        _error(errors, isinstance(row.get("solvency_ratio"), (int, float)) and not isinstance(row.get("solvency_ratio"), bool) and row["solvency_ratio"] >= 0, f"RBC记录[{i}] solvency_ratio 非法")
        _error(errors, isinstance(row.get("sha256"), str) and HASH_RE.fullmatch(row["sha256"]) is not None, f"RBC记录[{i}] sha256 非法")
        match = PERCENT_RE.fullmatch(str(row.get("solvency_ratio_raw", "")))
        _error(errors, bool(match) and abs(row["solvency_ratio"] - float(match.group(1)) / 100) < 1e-9,
               f"RBC记录[{i}] 原文百分比与标准值不一致")
        key = (row.get("insurer_code"), row.get("report_year"))
        if key in rkeys: errors.append(f"RBC自然键重复: {key!r}")
        rkeys.add(key)

    for i, row in enumerate(coverage if isinstance(coverage, list) else []):
        _error(errors, isinstance(row, dict) and row.get("coverage_status") in COVERAGE, f"coverage[{i}] 状态非法")
    counts = manifest.get("record_counts", {})
    _error(errors, counts.get("fulfillment_ratio") == len(fulfillment), "分红记录数与 manifest 不一致")
    _error(errors, counts.get("rbc_statement") == len(rbc if isinstance(rbc, list) else []), "RBC 记录数与 manifest 不一致")
    _error(errors, counts.get("coverage_status") == len(coverage if isinstance(coverage, list) else []), "coverage 记录数与 manifest 不一致")
    gaps = [x for x in coverage if isinstance(x, dict) and x.get("coverage_status") != "FULL"] if isinstance(coverage, list) else []
    if manifest.get("release_status") == "READY":
        _error(errors, not gaps and health.get("status") == "HEALTHY", "READY 包仍含覆盖缺口或健康状态非 HEALTHY")
    if manifest.get("release_status") == "PARTIAL_COVERAGE":
        _error(errors, bool(gaps) and health.get("status") == "DEGRADED", "PARTIAL_COVERAGE 与 coverage/health 不一致")

    return {"result": "ACCEPTED" if not errors else "REJECTED", "bundle_path": str(root),
            "contract_version": manifest.get("contract_version"), "record_counts": counts,
            "errors": errors, "exit_code": 0 if not errors else 2}
