#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/pru_rbc_parser.py · Prudential RBC 披露声明 PDF 解析（向后兼容适配层）

T008 起，Prudential 专用解析逻辑已泛化并迁入 skills/rbc_parser.py（可复用 RBC Capital
Adequacy 解析能力，供 PRUGI / AIACO 等不同版式共用）。本文件保留为**受限适配层**与
向后兼容垫片：对既有调用方（skills/parse_disclosure 与 T007 测试）继续暴露原名字
`parse_pru_rbc` / `PruRbcParseError` / `extract_rbc`，实现直接委托给通用解析器，不重复
任何解析逻辑、不写死任何具体比率。
"""

from skills.rbc_parser import (  # noqa: F401
    CAPITAL_BASE_LABEL,
    PCA_LABEL,
    RATIO_LABEL,
    SECTION_HEADING,
    RbcParseError,
    _apply_scale,
    _build_risk_breakdown,
    _clean_legal_name,
    _extract_amount,
    _extract_currency_and_unit,
    _extract_legal_entity_name,
    _extract_ratio,
    _norm,
    _norm_keep_case,
    _parse_amount,
    _parse_pct_to_ratio,
    extract_rbc,
    parse_rbc,
)

# 向后兼容别名（T007 及更早调用方使用）。
# 注意：必须是别名而非子类——T007 测试以 `except PruRbcParseError` 捕获解析器抛出的
# rbc_parser.RbcParseError，别名保证二者是同一异常类型。
PruRbcParseError = RbcParseError


def parse_pru_rbc(body: bytes):
    """解析 Prudential RBC PDF 字节（委托通用 rbc_parser.parse_rbc）。"""
    return parse_rbc(body)


__all__ = [
    "PruRbcParseError",
    "RbcParseError",
    "parse_pru_rbc",
    "parse_rbc",
    "extract_rbc",
    "_parse_pct_to_ratio",
    "_parse_amount",
    "_apply_scale",
    "_norm",
    "_norm_keep_case",
    "_clean_legal_name",
    "_extract_legal_entity_name",
    "_extract_currency_and_unit",
    "_extract_ratio",
    "_extract_amount",
    "_build_risk_breakdown",
    "SECTION_HEADING",
    "RATIO_LABEL",
    "PCA_LABEL",
    "CAPITAL_BASE_LABEL",
]
