#!/usr/bin/env python3
"""只读校验OB发布清单并生成VNW候选影响回执。不会应用更新或调用模型。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "ob-vnw.input-manifest.v1"
KNOWLEDGE_TYPES = {
    "PROCESS_BLUEPRINT": ["A", "B", "C", "F"],
    "L4_DELIVERY": ["A", "C", "D", "E", "F"],
    "D1_D6_ASSESSMENT": ["D", "E", "F"],
    "SOP": ["A", "B", "C", "F"],
    "BUSINESS_RULE": ["B", "C", "D", "E", "F"],
    "ORG_ROLE": ["B", "F"],
    "TASK_DECOMPOSITION": ["C", "D", "E", "F"],
    "AI_FEASIBILITY": ["C", "D", "E", "F"],
    "KPI_QUALITY": ["D", "E", "F"],
    "VALUE_NODE_MAPPING": ["A", "B", "C", "E", "F"],
    "L2_CAPABILITY": ["E", "F"],
    "METHODOLOGY": ["F"],
    "AGENT_DESIGN": ["C", "D", "E", "F"],
    "DATA_MAPPING": ["F"],
}
LIFECYCLE = {"DRAFT", "UNDER_REVIEW", "CONFIRMED", "DEPRECATED"}
EVIDENCE = {"PRIMARY_SSOT", "CORROBORATING", "CONTEXT_ONLY"}
MAPPING = {"EXPLICIT_IN_CONTENT", "STRUCTURED_FIELD", "MANUAL_CONFIRMED"}
LOCATORS = {"WHOLE_FILE", "MD_SECTION", "LINE_RANGE", "CSV_ROW_RANGE", "XLSX_RANGE", "JSON_POINTER", "PAGE_RANGE"}
L3_RE = re.compile(r"^L3-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
L4_RE = re.compile(r"^L4-[A-Z0-9]+(?:-[A-Z0-9]+)*-[0-9]+$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_item(item: object, index: int, root: Path) -> tuple[list[str], dict]:
    errors: list[str] = []
    prefix = f"sources[{index}]"
    if not isinstance(item, dict):
        return [f"{prefix}: 必须是对象"], {"source_id": "", "valid": False}
    required = {"source_id", "relative_path", "title", "sha256", "mtime", "size_bytes", "version", "l3_codes", "l4_codes", "knowledge_types", "lifecycle_status", "evidence_level", "mapping_basis", "locators"}
    missing = sorted(required - item.keys())
    errors.extend(f"{prefix}.{key}: 缺少必填字段" for key in missing)
    source_id = str(item.get("source_id", ""))
    relative = str(item.get("relative_path", ""))
    if not source_id.startswith("OB-EA-"):
        errors.append(f"{prefix}.source_id: 必须以OB-EA-开头")
    rel_path = Path(relative)
    if not relative or rel_path.is_absolute() or ".." in rel_path.parts:
        errors.append(f"{prefix}.relative_path: 必须是OB根目录内的安全相对路径")
        source_path = None
    else:
        source_path = (root / rel_path).resolve()
        try:
            source_path.relative_to(root.resolve())
        except ValueError:
            errors.append(f"{prefix}.relative_path: 路径越出OB根目录")
            source_path = None
    declared_hash = str(item.get("sha256", ""))
    if not SHA_RE.fullmatch(declared_hash):
        errors.append(f"{prefix}.sha256: 必须是64位小写SHA-256")
    if source_path is not None:
        if not source_path.is_file():
            errors.append(f"{prefix}.relative_path: 源文件不存在")
        else:
            actual_hash = sha256(source_path)
            if actual_hash != declared_hash:
                errors.append(f"{prefix}.sha256: 与实际文件不一致")
            if item.get("size_bytes") != source_path.stat().st_size:
                errors.append(f"{prefix}.size_bytes: 与实际文件不一致")
            try:
                declared_mtime = datetime.fromisoformat(str(item.get("mtime", "")).replace("Z", "+00:00")).timestamp()
                if abs(declared_mtime - source_path.stat().st_mtime) > 0.01:
                    errors.append(f"{prefix}.mtime: 与实际文件修改时间不一致")
            except (TypeError, ValueError):
                errors.append(f"{prefix}.mtime: 必须是ISO 8601时间")
    l3_codes = item.get("l3_codes", [])
    l4_codes = item.get("l4_codes", [])
    if not isinstance(l3_codes, list) or any(not isinstance(x, str) or not L3_RE.fullmatch(x) for x in l3_codes):
        errors.append(f"{prefix}.l3_codes: 编码格式无效")
        l3_codes = []
    if not isinstance(l4_codes, list) or any(not isinstance(x, str) or not L4_RE.fullmatch(x) for x in l4_codes):
        errors.append(f"{prefix}.l4_codes: 编码格式无效")
        l4_codes = []
    types = item.get("knowledge_types", [])
    if not isinstance(types, list) or not types or any(x not in KNOWLEDGE_TYPES for x in types):
        errors.append(f"{prefix}.knowledge_types: 缺失或含未知枚举")
        types = []
    if item.get("lifecycle_status") not in LIFECYCLE:
        errors.append(f"{prefix}.lifecycle_status: 未知枚举")
    if item.get("evidence_level") not in EVIDENCE:
        errors.append(f"{prefix}.evidence_level: 未知枚举")
    if item.get("mapping_basis") not in MAPPING:
        errors.append(f"{prefix}.mapping_basis: 未知枚举")
    locators = item.get("locators", [])
    if not isinstance(locators, list) or not locators:
        errors.append(f"{prefix}.locators: 至少提供一个定位")
    else:
        for loc_index, locator in enumerate(locators):
            if not isinstance(locator, dict) or locator.get("locator_type") not in LOCATORS or not locator.get("value"):
                errors.append(f"{prefix}.locators[{loc_index}]: 类型或定位值无效")
    if item.get("lifecycle_status") == "CONFIRMED" and not l3_codes and not set(types) & {"METHODOLOGY", "DATA_MAPPING"}:
        errors.append(f"{prefix}: 已确认业务知识必须关联至少一个L3")
    panels = sorted({panel for kind in types for panel in KNOWLEDGE_TYPES.get(kind, [])})
    publishable = item.get("lifecycle_status") == "CONFIRMED"
    return errors, {
        "source_id": source_id,
        "valid": not errors,
        "publishable": publishable and not errors,
        "lifecycle_status": item.get("lifecycle_status", ""),
        "evidence_level": item.get("evidence_level", ""),
        "affected_panels_candidate": panels,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"无法读取清单: {exc}", file=sys.stderr)
        return 2
    errors: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version必须为{SCHEMA_VERSION}")
    if manifest.get("publisher") != "OB_AGENT":
        errors.append("publisher必须为OB_AGENT")
    root = Path(str(manifest.get("ob_root_path", ""))).expanduser()
    if not root.is_dir():
        errors.append("ob_root_path不存在或不是目录")
    items = manifest.get("sources", [])
    if not isinstance(items, list):
        errors.append("sources必须是数组")
        items = []
    results = []
    seen_ids: set[str] = set()
    affected: dict[str, set[str]] = {}
    for index, item in enumerate(items):
        item_errors, result = validate_item(item, index, root)
        errors.extend(item_errors)
        source_id = result["source_id"]
        if source_id in seen_ids:
            duplicate = f"sources[{index}].source_id: 重复的{source_id}"
            errors.append(duplicate)
            result["errors"].append(duplicate)
            result["valid"] = result["publishable"] = False
        seen_ids.add(source_id)
        results.append(result)
        if result["publishable"]:
            for code in item.get("l3_codes", []):
                affected.setdefault(code, set()).update(result["affected_panels_candidate"])
    receipt = {
        "schema_version": "ob-vnw.vnw-receipt.v1",
        "release_id": str(manifest.get("release_id", "UNKNOWN")),
        "consumer": "VNW_AGENT",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_VALIDATE",
        "status": "VALIDATION_FAILED" if errors else "READY_FOR_REVIEW",
        "summary": {"total": len(results), "valid": sum(r["valid"] for r in results), "invalid": sum(not r["valid"] for r in results), "publishable": sum(r["publishable"] for r in results)},
        "source_results": results,
        "affected_l3": [{"l3_code": code, "affected_panels": sorted(panels), "reanalysis_candidate": True} for code, panels in sorted(affected.items())],
        "errors": errors,
    }
    output = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(output, encoding="utf-8")
    print(output, end="")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
