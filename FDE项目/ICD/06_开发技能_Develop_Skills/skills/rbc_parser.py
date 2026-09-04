#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/rbc_parser.py · RBC 披露声明 PDF 通用解析与标准化
（L3-ICD-03 解析层 · format=pdf 分支 · 复用 RBC Capital Adequacy 能力）

职责边界：纯函数，把「风险为本资本（RBC）披露声明」PDF 的原始字节解析为一条标准化
rbc_statement 记录（+ 可选原始风险分解 JSON）。不访问网络、不读库、不写库（入库由
tools/rbc_writer + skills/parse_disclosure 负责）。不执行 PDF 内嵌代码。

== 泛化说明（对齐任务书 T008 功能要求 4）==
本模块由 T007 的 Prudential 专用解析器泛化而来，是**可复用**的 RBC Capital Adequacy
解析能力，供不同版式的 RBC 披露声明共用（当前覆盖 Prudential General Insurance 香港
PRUGI 与 AIA Company Limited AIACO 两家，见 skills/parse_disclosure 分流）。
针对不同版式的**受限适配**仅体现在语义锚点的兼容性上（法律主体标签的英式/美式拼写、
标签独占一行或与值同行、ratio/金额在文本或表格中的任一位置），绝不为某一家险企复制
一份仅改名字的硬编码解析器，也绝不写死任何具体比率（290%/304% 等一律从 PDF 独立提取）。

== 语义邻域（对齐任务书 T007 功能要求 3 / T008 功能要求 5）==
只在明确的「Capital adequacy / Ratio of capital base to prescribed capital amount」
语义邻域内提取，绝不全页百分号正则猜数：
- report_year：来自披露时点 "31 December YYYY"（唯一且非空）。
- legal_entity_name_raw：来自 "Authorized/Authorised insurer's name" 邻域的法律主体
  逐字原文（主体是核心归属，缺失即 RbcParseError → STRUCTURE_MISMATCH）。
- solvency_ratio：来自 "Ratio of capital base to prescribed capital amount" 标签
  紧邻的百分比（如 "304%" → 3.04，原文 "304%"）。
- currency / amount_unit_raw / amount_scale：来自 "Unit: in HKD thousands"
  （币种代码 + 千/百万标度 + 单位原文）。
- capital_base：来自 "Capital base" 行（币种金额，按披露明示标度折算为绝对币值，
  原文保留在 capital_base_raw）。
- prescribed_capital_amount：来自 "Prescribed capital amount" 行（同上报原文）。
- risk_breakdown_json：PCA 子风险表 + 资本基础组成表原文（含标度），无损保留。

== 口径说明（重要，供审计）==
披露金额以 "Unit: in HKD thousands"（千港元）给出；rbc_statement 的
capital_base/prescribed_capital_amount 语义为「币种金额」，故按披露明示标度 ×1000
折算为绝对 HKD 入库（非猜数，标度来自 PDF 明示单位）；原文数值与标度原样保留在
risk_breakdown_json，保证无损可复现。

== 确定性要求 ==
- 结构漂移（缺 Capital adequacy 段落 / 缺 ratio 标签 / 报告年度缺失或不一致）→
  RbcParseError（STRUCTURE_MISMATCH）。
- 核心比率缺失或歧义（0 个或 >1 个不同候选百分比）→ RbcParseError（STRUCTURE_MISMATCH）。
- 无法确认的可选金额写 NULL，不推算、不编造。
- 文本跨行断词通过空白折叠归一后匹配。
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from skills import pdf_text


class RbcParseError(Exception):
    """RBC PDF 结构不符/缺失/歧义，对应 STRUCTURE_MISMATCH 硬失败。"""


# 语义锚点（小写归一后匹配）
SECTION_HEADING = "capital adequacy"
RATIO_LABEL = "ratio of capital base to prescribed capital amount"
PCA_LABEL = "prescribed capital amount"
CAPITAL_BASE_LABEL = "capital base"

# 法律主体标签：英式 "Authorised insurer's name" / 美式 "Authorized insurer's name"，
# 允许弯/直撇号（\u2019 / '）。标签可能带章节字母前缀 "(a) " 或尾随冒号。
_LEGAL_LABEL_RE = re.compile(
    r"authori[sz]ed\s+insurer[\u2019']?s\s+name", re.IGNORECASE
)
# 同行抽取：标签后紧跟名称（名称以字母开头，延伸到行尾）。
_LEGAL_SAME_LINE_RE = re.compile(
    r"authori[sz]ed\s+insurer[\u2019']?s\s+name\s*:?\s*([A-Za-z][^\n]*)",
    re.IGNORECASE,
)
_COMPANY_NAME_RE = re.compile(r"company\s+name\s*:?\s*([A-Za-z][^\n]*)", re.IGNORECASE)

# 年份："31 December 2024"（大小写不敏感）
_YEAR_RE = re.compile(r"31\s+december\s+(\d{4})", re.IGNORECASE)
# 币种/标度："Unit: in HKD thousands"
_UNIT_RE = re.compile(r"unit\s*:\s*in\s+([A-Za-z]{3})\s*(thousands|millions)?", re.IGNORECASE)
# 百分比：整数或小数 + '%'
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# ratio 标签后紧跟的候选窗口长度（折叠空白后的字符数，足够覆盖标签→比率值）
_RATIO_WINDOW = 200


def _norm(s) -> str:
    """折叠所有空白为单空格、去首尾、转小写（用于标签/文本匹配）。"""
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _norm_keep_case(s) -> str:
    """折叠所有空白为单空格、去首尾（保留大小写，用于原文保留）。"""
    return re.sub(r"\s+", " ", str(s)).strip()


def _clean_legal_name(s) -> str:
    """清洗法律主体名称：去掉尾随 "(the "Company")" 之类的指代标注。

    只针对 "the Company" 引用做精确裁剪，绝不动合法的名称内括号（如
    "FWD Life Insurance Company (Bermuda) Limited" 中的 "(Bermuda)"）。
    """
    s = _norm_keep_case(s)
    s = re.sub(
        r"\s*\(\s*the\s+[\u201c\u201d'\"]?company[\u201c\u201d'\"]?\s*\)\s*$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    return s.strip()


def _parse_pct_to_ratio(pct_raw) -> Optional[float]:
    """'290%' → 2.90；无法解析返回 None。"""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%", str(pct_raw).strip())
    if m:
        return float(m.group(1)) / 100.0
    return None


def _parse_amount(s) -> Optional[float]:
    """把披露金额字符串解析为数值；'-'/空/N.A. → None（未披露，不推算）。

    支持千分位逗号；括号表示负数（仅用于风险分解组件，不用于资本基础/规定资本额总额）。
    """
    if s is None:
        return None
    raw = str(s).strip()
    if raw in ("", "-", "—", "N/A", "n/a", "N.A."):
        return None
    neg = raw.startswith("(") and raw.endswith(")")
    if neg:
        raw = raw[1:-1].strip()
    raw = raw.replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return None
    return -val if neg else val


def _apply_scale(val: float, scale: str) -> float:
    """按披露标度把数值折算为绝对币值（thousands→×1000，millions→×1e6，否则原值）。"""
    if scale == "thousands":
        return val * 1000.0
    if scale == "millions":
        return val * 1000000.0
    return val


def _extract_currency_and_unit(full_text: str, all_tables) -> Tuple[str, str, Optional[str]]:
    """'Unit: in HKD thousands' → ('HKD', 'thousands', 'in HKD thousands')。

    未找到时回落 ('HKD', '', None)：币种默认 HKD，标度空（视为绝对），单位原文 NULL。
    """
    def _from_match(m):
        if not m:
            return None
        currency = m.group(1).upper()
        scale = (m.group(2) or "").lower()
        unit_raw = f"in {currency} {scale}".strip() if scale else f"in {currency}"
        return currency, scale, unit_raw

    found = _from_match(_UNIT_RE.search(full_text))
    if found:
        return found
    for tbl in all_tables:
        for row in tbl:
            for cell in row:
                if cell:
                    found = _from_match(_UNIT_RE.search(str(cell)))
                    if found:
                        return found
    return "HKD", "", None


def _extract_legal_entity_name(full_text: str) -> str:
    """从 'Authorized/Authorised insurer's name' 邻域提取法律主体逐字原文。

    兼容三种版式（对齐 T008 泛化要求）：
    1. 标签独占一行（可能带 "(a) " 章节字母前缀或尾随冒号）→ 取下一非空行；
    2. 标签与名称同行（"Authorized insurer's name: X" 或 "…name X"）；
    3. 回退 'Company Name:'（Statement of Compliance 段）。
    找不到即 RbcParseError（主体身份是核心归属，缺失不可安全归属）。
    """
    text = full_text.replace("\u2019", "'").replace("\u2018", "'")
    lines = [l.strip() for l in text.splitlines()]

    # 1) 标签独占一行 → 下一非空行
    for i, line in enumerate(lines):
        stripped = re.sub(r"^\([a-z]\)\s*", "", line, flags=re.IGNORECASE).rstrip(":")
        if _LEGAL_LABEL_RE.fullmatch(stripped):
            for j in range(i + 1, len(lines)):
                cand = lines[j].strip()
                if cand:
                    return _clean_legal_name(cand)
            break

    # 2) 标签与名称同行
    m = _LEGAL_SAME_LINE_RE.search(text)
    if m and m.group(1).strip():
        return _clean_legal_name(m.group(1))

    # 3) 回退 Company Name:
    m = _COMPANY_NAME_RE.search(text)
    if m and m.group(1).strip():
        return _clean_legal_name(m.group(1))

    raise RbcParseError("未找到 'Authorized/Authorised insurer's name'（法律主体名称缺失，不可安全归属）")


def _extract_ratio(full_text: str, all_tables) -> Tuple[str, float]:
    """在 ratio 标签邻域提取唯一百分比。

    0 个 → 缺失（RbcParseError）；>1 个不同值 → 歧义（RbcParseError）。
    返回 (原始字符串, 小数比率)。
    """
    candidates: Dict[float, str] = {}

    def add(pct_str):
        v = _parse_pct_to_ratio(pct_str)
        if v is not None:
            candidates.setdefault(v, str(pct_str).strip())

    # 1) 文本路径：ratio 标签后紧跟窗口内的所有百分比（折叠空白，处理跨行断词）
    norm = _norm(full_text)
    idx = 0
    while True:
        i = norm.find(RATIO_LABEL, idx)
        if i < 0:
            break
        tail = norm[i + len(RATIO_LABEL): i + len(RATIO_LABEL) + _RATIO_WINDOW]
        for m in _PCT_RE.finditer(tail):
            add(m.group(0))
        idx = i + len(RATIO_LABEL)

    # 2) 表格路径：ratio 标签行的所有百分比
    for tbl in all_tables:
        for row in tbl:
            if not row or not row[0]:
                continue
            if RATIO_LABEL in _norm(row[0]):
                for cell in row:
                    if cell:
                        for m in _PCT_RE.finditer(str(cell)):
                            add(m.group(0))

    if not candidates:
        raise RbcParseError("偿付能力比率缺失（未找到 ratio 标签紧邻的百分比）")
    if len(candidates) > 1:
        raise RbcParseError(
            f"偿付能力比率歧义：存在 {sorted(candidates.keys())} 多个候选比率"
        )
    v = next(iter(candidates))
    return candidates[v], v


def _extract_amount(all_tables, full_text: str, label: str, scale: str) -> Tuple[Optional[str], Optional[float]]:
    """按精确标签（折叠空白、小写）提取金额；返回 (原文, 绝对币值或 None)。"""
    raw: Optional[str] = None

    # 1) 表格路径：label 单元格精确匹配
    for tbl in all_tables:
        for row in tbl:
            if not row or len(row) < 2:
                continue
            if _norm(row[0]) == label:
                raw = str(row[1]).strip() if row[1] is not None else None
                break
        if raw is not None:
            break

    # 2) 文本路径：行首精确匹配（折叠空白），仅当表格路径未命中
    if raw is None:
        for line in full_text.splitlines():
            nline = _norm_keep_case(line)
            nl = _norm(nline)
            if nl == label or nl.startswith(label + " "):
                tail = nline[len(label):].strip()
                if tail:
                    raw = tail
                    break

    if raw is None:
        return None, None
    val = _parse_amount(raw)
    if val is None:
        return raw, None
    return raw, _apply_scale(val, scale)


def _build_risk_breakdown(all_tables, currency: str, scale: str,
                          pca_raw, capital_base_raw) -> str:
    """把 PCA 子风险表 + 资本基础组成表原文无损序列化为 JSON 字符串。"""
    pca_components: List[Dict[str, str]] = []
    cap_components: List[Dict[str, str]] = []
    for tbl in all_tables:
        if not tbl:
            continue
        labels = [_norm(r[0]) if (r and r[0] is not None) else "" for r in tbl]
        if any(lbl == PCA_LABEL for lbl in labels):
            for row in tbl:
                if not row or len(row) < 2:
                    continue
                pca_components.append({
                    "label": _norm_keep_case(row[0]),
                    "raw": ("" if row[1] is None else str(row[1]).strip()),
                })
        if any(lbl == CAPITAL_BASE_LABEL for lbl in labels):
            for row in tbl:
                if not row or len(row) < 2:
                    continue
                cap_components.append({
                    "label": _norm_keep_case(row[0]),
                    "raw": ("" if row[1] is None else str(row[1]).strip()),
                })

    doc = {
        "currency": currency,
        "unit": f"in {currency} {scale}".strip() if scale else f"in {currency}",
        "prescribed_capital_amount_raw": pca_raw,
        "capital_base_raw": capital_base_raw,
        "prescribed_capital_components": pca_components,
        "capital_base_components": cap_components,
    }
    return json.dumps(doc, ensure_ascii=False)


def extract_rbc(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从 PDF 提取的页面（text + tables）做 Capital Adequacy 语义邻域解析。

    pages: [{"text": str, "tables": [[cell,...],...]}, ...]
    返回：{"status": "OK", "report_year": int, "records": [record],
           "product_count": None, "value_unparseable": 0}
    结构不符/缺失/歧义 → RbcParseError（STRUCTURE_MISMATCH）。
    """
    full_text = "\n".join((p.get("text") or "") for p in pages)
    all_tables: List[List[Optional[str]]] = [row for p in pages for row in (p.get("tables") or [])]

    norm_text = _norm(full_text)

    # 1) Capital adequacy 段落锚点
    if SECTION_HEADING not in norm_text:
        raise RbcParseError("未找到 'Capital adequacy' 段落（结构漂移/非 RBC 披露）")

    # 2) 报告年度：唯一且非空
    years = set(_YEAR_RE.findall(full_text))
    for tbl in all_tables:
        for row in tbl:
            for cell in row:
                if cell:
                    years.update(_YEAR_RE.findall(str(cell)))
    if not years:
        raise RbcParseError("报告年度缺失（未找到 '31 December YYYY'）")
    if len(years) != 1:
        raise RbcParseError(f"报告年度不一致或歧义: {sorted(years)}")
    report_year = int(years.pop())

    # 3) 法律主体原文（核心归属；缺失即 STRUCTURE_MISMATCH）
    legal_entity_name_raw = _extract_legal_entity_name(full_text)

    # 4) 币种 + 金额标度
    currency, scale, unit_raw = _extract_currency_and_unit(full_text, all_tables)
    amount_scale = scale or None  # 未明示标度 → NULL（视为绝对）

    # 5) 偿付能力比率（核心）
    ratio_raw, ratio_value = _extract_ratio(full_text, all_tables)

    # 6) 资本基础 / 规定资本额（可选金额；无法确认写 NULL；同时保留披露原文）
    capital_base_raw, capital_base = _extract_amount(all_tables, full_text, CAPITAL_BASE_LABEL, scale)
    pca_raw, prescribed = _extract_amount(all_tables, full_text, PCA_LABEL, scale)

    # 7) 风险分解原文（lossless）
    risk_breakdown_json = _build_risk_breakdown(all_tables, currency, scale, pca_raw, capital_base_raw)

    record = {
        "report_year": report_year,
        "legal_entity_name_raw": legal_entity_name_raw,
        "solvency_ratio": ratio_value,
        "solvency_ratio_raw": ratio_raw,
        "capital_base": capital_base,
        "capital_base_raw": capital_base_raw,
        "prescribed_capital_amount": prescribed,
        "prescribed_capital_amount_raw": pca_raw,
        "currency": currency,
        "amount_unit_raw": unit_raw,
        "amount_scale": amount_scale,
        "risk_breakdown_json": risk_breakdown_json,
    }
    return {
        "status": "OK",
        "report_year": report_year,
        "product_count": None,
        "records": [record],
        "value_unparseable": 0,
    }


def parse_rbc(body: bytes) -> Dict[str, Any]:
    """解析 RBC 披露声明 PDF 字节 → 标准化结果（先提取文字层，再做语义邻域解析）。"""
    pages = pdf_text.extract_pages(body)
    return extract_rbc(pages)
