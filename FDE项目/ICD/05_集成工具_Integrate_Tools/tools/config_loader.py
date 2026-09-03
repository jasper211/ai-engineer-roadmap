#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · tools/config_loader.py · 配置加载与严格校验

职责边界：只负责读 settings.json / source_registry.json 并做静态校验，
不访问网络、不读数据库、不写任何文件。

校验规则（对齐任务书 T002 功能要求第 2 条与验收标准第 2 条）：
- 非法 JSON → 抛 ConfigError，调用方转非零退出。
- 注册表必须含 `insurers` / `sources` 两个数组。
- 重复险企（insurer_code 重复）→ 错误。
- 未知险企引用（source.insurer_code 不在 insurers 中）→ 错误。
- access_status 取值必须 ∈ {OPEN, PARTIAL, BLOCKED, UNVERIFIED}。
- UNVERIFIED 条目 entry_url 与 format 必须同时为 null（不得猜测）。
- disclosure_type / format / requires_browser / allows_empty 的取值域校验。

`validate_*` 返回错误字符串列表（空列表 = 合规），不做任何副作用。
"""

import json
from pathlib import Path
from typing import List

VALID_ACCESS_STATUS = {"OPEN", "PARTIAL", "BLOCKED", "UNVERIFIED"}
VALID_DISCLOSURE_TYPE = {"fulfillment_ratio", "total_cash_value_ratio", "rbc"}
VALID_FORMAT = {"json", "html", "pdf"}


class ConfigError(Exception):
    """配置无法解析或结构不合规时抛出。"""


def load_json(path: Path) -> dict:
    """读取并解析 JSON 文件；文件缺失或非法 JSON 一律抛 ConfigError。"""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"配置文件不存在: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"非法 JSON: {p}（{e}）")
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是 JSON 对象: {p}")
    return data


def load_settings(path: Path) -> dict:
    return load_json(path)


def load_registry(path: Path) -> dict:
    return load_json(path)


def validate_settings(settings: dict) -> List[str]:
    """校验 settings.json；返回错误字符串列表，空列表 = 合规。"""
    errors: List[str] = []
    agent_id = settings.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        errors.append("settings.agent_id 缺失或非字符串")
    version = settings.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("settings.version 缺失或非字符串")
    return errors


def validate_registry(registry: dict) -> List[str]:
    """校验 source_registry.json；返回错误字符串列表，空列表 = 合规。"""
    errors: List[str] = []

    insurers = registry.get("insurers")
    sources = registry.get("sources")
    if not isinstance(insurers, list):
        errors.append("registry 缺少 insurers 数组")
        return errors
    if not isinstance(sources, list):
        errors.append("registry 缺少 sources 数组")
        return errors

    # 险企：insurer_code 唯一性 + 基本字段
    known_codes = {}
    for idx, ins in enumerate(insurers):
        if not isinstance(ins, dict):
            errors.append(f"insurers[{idx}] 不是对象")
            continue
        code = ins.get("insurer_code")
        if not isinstance(code, str) or not code.strip():
            errors.append(f"insurers[{idx}] 缺少 insurer_code")
            continue
        if code in known_codes:
            errors.append(f"重复险企 insurer_code: {code}（insurers[{idx}]）")
        else:
            known_codes[code] = True
        if not isinstance(ins.get("name_en"), str) or not ins.get("name_en", "").strip():
            errors.append(f"insurers[{idx}] ({code}) 缺少 name_en")

    # 数据源：未知险企引用 / 取值域 / UNVERIFIED 语义 / 重复源
    seen_source_keys = set()
    for idx, src in enumerate(sources):
        tag = f"sources[{idx}]"
        if not isinstance(src, dict):
            errors.append(f"{tag} 不是对象")
            continue

        code = src.get("insurer_code")
        if not isinstance(code, str) or not code.strip():
            errors.append(f"{tag} 缺少 insurer_code")
            continue
        if code not in known_codes:
            errors.append(f"{tag} 引用未知险企 insurer_code: {code!r}")

        d_type = src.get("disclosure_type")
        if d_type not in VALID_DISCLOSURE_TYPE:
            errors.append(f"{tag} 非法 disclosure_type: {d_type!r}")

        status = src.get("access_status")
        if status not in VALID_ACCESS_STATUS:
            errors.append(f"{tag} 非法 access_status: {status!r}")

        entry_url = src.get("entry_url")
        fmt = src.get("format")

        # UNVERIFIED：entry_url 与 format 必须同时为 null（不得猜测）
        if status == "UNVERIFIED":
            if entry_url is not None:
                errors.append(f"{tag} access_status=UNVERIFIED 但 entry_url 非 null: {entry_url!r}")
            if fmt is not None:
                errors.append(f"{tag} access_status=UNVERIFIED 但 format 非 null: {fmt!r}")

        if fmt is not None and fmt not in VALID_FORMAT:
            errors.append(f"{tag} 非法 format: {fmt!r}")

        rb = src.get("requires_browser")
        if rb is not None and not isinstance(rb, bool):
            errors.append(f"{tag} requires_browser 必须是布尔值: {rb!r}")
        ae = src.get("allows_empty")
        if ae is not None and not isinstance(ae, bool):
            errors.append(f"{tag} allows_empty 必须是布尔值: {ae!r}")

        if not isinstance(src.get("evidence_basis"), str) or not src.get("evidence_basis", "").strip():
            errors.append(f"{tag} ({code}) 缺少 evidence_basis")

        # 重复数据源（对齐 data_source 表 UNIQUE(insurer_code, disclosure_type, entry_url)）
        key = (code, d_type, entry_url)
        if key in seen_source_keys:
            errors.append(f"{tag} 重复数据源 (insurer_code={code!r}, disclosure_type={d_type!r}, entry_url={entry_url!r})")
        seen_source_keys.add(key)

    return errors
