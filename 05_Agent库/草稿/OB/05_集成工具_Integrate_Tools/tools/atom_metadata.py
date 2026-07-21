#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：读取知识原子的结构化frontmatter字段（entity_type/authority_layer/
confidence/decision_status/entity_ref/所属枢纽），供检索层用来标注/过滤/
排序返回结果——这是本体schema迁移(entity_type等字段)第一次被检索端真正
读取，之前这些字段只存在于vault文件里，任何调用方（含PTA等业务Agent）
都看不到。

不解析Markdown AST，用正则抽字段——跟concept_note_extraction.py/
migrate_full_vault.py一样的轻量做法，够用，不引入额外依赖。
"""

import re
from pathlib import Path
from typing import Dict, Optional

FRONTMATTER_FIELDS = [
    "concept_type", "authority_layer", "confidence", "confidence_reason",
    "decision_status", "as_of", "entity_type", "entity_ref",
]

HUB_LINK_RE = re.compile(r"## 所属枢纽\n\n((?:- \[\[.+?\]\]\n?)+)")
WIKILINK_RE = re.compile(r"\[\[(.+?)\]\]")


def read_atom_metadata(vault_path: str, note_path: str) -> Optional[Dict]:
    """给定vault根路径和note相对路径（如hybrid_search返回的notePath），
    读取该文件的结构化元数据。文件不存在/没有frontmatter时返回None
    （调用方按None判断"这条结果没有结构化元数据可用"，不当作错误处理）。"""
    full_path = Path(vault_path) / note_path
    if not full_path.exists():
        return None
    try:
        text = full_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not fm_match:
        return None
    frontmatter_raw = fm_match.group(1)

    meta = {}
    for field in FRONTMATTER_FIELDS:
        m = re.search(rf"^{field}: (.+)$", frontmatter_raw, re.M)
        if m:
            meta[field] = m.group(1).strip()

    hub_m = HUB_LINK_RE.search(text)
    meta["hubs"] = WIKILINK_RE.findall(hub_m.group(1)) if hub_m else []

    is_hub_m = re.search(r"^type: (\S+)$", frontmatter_raw, re.M)
    meta["is_hub"] = bool(is_hub_m and is_hub_m.group(1) == "entity_hub")

    return meta


AUTHORITY_RANK = {"03_已锁定": 3, "02_草稿": 2, "01_原始": 2, "08_任务跟进": 1, "00_治理": 2}


def authority_rank(authority_layer: Optional[str]) -> int:
    """权威级别转数值，用于排序——03已锁定最高，01/02/00次之，08任务跟进最低
    （任务跟进文档变动最频繁、口径最不稳定，跟L0/L1原始材料的稳定性不是一个量级）。
    未知/缺失的authority_layer返回0，排在所有已知级别之后。"""
    return AUTHORITY_RANK.get(authority_layer, 0)


def confidence_rank(confidence: Optional[str]) -> int:
    """置信度转数值：HIGH>MEDIUM>LOW>UNSTATED/缺失。"""
    return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(confidence, 0)
