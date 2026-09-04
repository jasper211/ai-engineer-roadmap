#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/pdf_text.py · PDF 文本层/表格提取（format=pdf 基础能力）

职责边界：只负责"把 PDF 原始字节提取为页面文本 + 表格"，并做 PDF 签名与文字层
校验。不解析业务口径、不访问网络、不写库、不执行 PDF 内嵌代码（pdfplumber/pdfminer
只做解析，不运行 PDF 内嵌 JavaScript/动作）。

依赖（对齐任务书 T007 允许范围）：pdfplumber（基于 pdfminer.six，维护活跃）。
依赖声明见项目根 requirements.txt；未安装时抛出明确错误，不静默回退。

失败语义（对齐 data_contract.md 错误代码种子）：
- 非 PDF 字节（缺 %PDF 签名，如 HTML 错误页）→ PdfNotPdfError → STRUCTURE_MISMATCH。
- PDF 文字层为空（扫描件/无文字层）→ PdfNoTextError → PDF_NO_TEXT，绝不 OCR 猜数。
- 其他解析异常（损坏/加密/无法解析）→ PdfExtractionError → STRUCTURE_MISMATCH。
"""

import io
from typing import Any, Dict, List

# %PDF 签名：PDF 文件头以 "%PDF-" 开头（允许前导 BOM/空白少量容差，但必须在文件前部）
_PDF_SIGNATURE = b"%PDF-"


class PdfTextError(Exception):
    """PDF 提取失败基类。"""


class PdfNotPdfError(PdfTextError):
    """非 PDF 字节（缺少 %PDF 签名，如 HTML 错误页）。"""


class PdfNoTextError(PdfTextError):
    """PDF 文字层为空（扫描件/无文字层），不得 OCR 猜数。"""


class PdfExtractionError(PdfTextError):
    """PDF 解析器抛出异常（损坏/加密/无法解析）。"""


def has_pdf_signature(data: bytes) -> bool:
    """校验 PDF 签名：前 1024 字节内须含 "%PDF-"（HTML 错误页等不得当 PDF）。"""
    head = data[:1024]
    return _PDF_SIGNATURE in head


def extract_pages(data: bytes) -> List[Dict[str, Any]]:
    """把 PDF 原始字节提取为页面列表：[{"text": str, "tables": [[cell,...],...]}, ...]。

    先校验 %PDF 签名，再提取；提取后校验文字层非空。任一失败抛 PdfTextError 子类。
    """
    if not has_pdf_signature(data):
        raise PdfNotPdfError("非 PDF 字节（缺少 %PDF 签名，HTML 错误页不得当 PDF）")

    try:
        import pdfplumber
    except ImportError as e:  # 依赖缺失 → 明确报错，不静默依赖全局环境
        raise PdfExtractionError(f"缺少 pdfplumber 依赖（请先 pip install -r requirements.txt）: {e}")

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages: List[Dict[str, Any]] = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                pages.append({"text": text, "tables": tables})
    except PdfTextError:
        raise
    except Exception as e:  # noqa: BLE001 —— pdfplumber 抛出的解析异常统一折叠
        raise PdfExtractionError(f"PDF 解析失败: {type(e).__name__}: {e}")

    # 文字层验证：全部页面均无文字 → 扫描件/无文字层（PDF_NO_TEXT），绝不 OCR 猜数
    total_chars = sum(len((p["text"] or "").strip()) for p in pages)
    if total_chars == 0:
        raise PdfNoTextError("PDF 文字层为空（扫描件/无文字层），不得 OCR 猜数")
    return pages
