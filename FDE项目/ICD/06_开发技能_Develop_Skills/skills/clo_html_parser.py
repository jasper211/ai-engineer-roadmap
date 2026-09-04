#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/clo_html_parser.py · 中国人寿（海外）CLO 分红实现率 HTML 解析与标准化
（L3-ICD-03 解析层 · format=html 分支 · insurer=CLO）

职责边界：纯函数，把 CLO `fulfillment_ratio` 原始 HTML 字节解析为标准化的
观测记录列表。不访问网络、不读库、不写库（入库由 tools/ratio_writer +
skills/parse_disclosure 负责）。

== 真实页面结构（2026-09-03 实测，source_id=9，report_year=2025）==

关键发现（先抓取后实现，以当前真实页面为准）：

1. 该页面的分红实现率数据**不在静态 <table> 里**，而是内嵌在页面一个
   <script> 块中、由 JavaScript 客户端渲染到空容器 <div id="part1/2/3"> 的
   三个数组里：
       var policyYears = [ ... 11 个观察期标签 ... ]
       var dataSets1 = [ [产品名, 产品类型, 币种/披露分组, 11个值], ... ]   ← Annual Dividend
       var dataSets2 = [ ... ]                                             ← Terminal Dividend
       var dataSets3 = []                                                  ← Accumulated Interest（本年空）
   页面里的 6 个静态 <table> 是「Historical Crediting Interest Rate for
   Universal Life Plans」（Reporting year: 2021），是**万能寿险结算利率**，
   属另一种披露口径，不属于 fulfillment_ratio，必须忽略。

2. 段落锚点（静态 HTML）：
       <h3>Reporting year: 2025</h3>
       <h3>1) Participating Plans - with Annual Dividend</h3>   → dataSets1 → AD
       <h3>2) Participating Plans - with Terminal Dividend</h3> → dataSets2 → TD
       <!-- 3) Plans with Accumulated Interest -->（注释掉）   → dataSets3 → OTHER（空）

3. 每个 dataSets 行固定为 len(policyYears)+3 个字符串元素：
       [0] 产品原始名（原样保留，含可能的尾部空格，如 "3-Year Pay 12-Year Saving Plan "）
       [1] 产品类型（如 "Product type - Participating endowment"，非契约字段，不落库）
       [2] 币种/披露分组原文（"Applied to all currencies plan" / "Applied to RMB plan"）
       [3..] 11 个值，与 policyYears 一一对应；值为百分比（"100%"/"70%"）或 "NA"。

4. 观察期标签："Policy Year 1 (2024)"…"Policy Year 10 (2015)"、
   "Policy Year 10+ (2014 or before)"。括号内是纯四位数字年 → 整数年；
   "2014 or before" 是开放区间 → observation_year 写 NULL，原文保留。

== 标准化约定（对齐 data_contract.md 与 T004 三项决策） ==
- metric_type / metric_type_raw：
    dataSets1 → ("AD", "Annual Dividend")
    dataSets2 → ("TD", "Terminal Dividend")
    dataSets3 → ("OTHER", "Accumulated Interest")
  AD/TD/RB/TB/TCV/OTHER 不得合并；未知指标不猜测（本页只有上述三类，第三类本年空）。
- scope_currency_raw：保存币种/披露分组原文，不拆分、不映射。
- report_year：段落标题 "Reporting year: 2025" 中的年份整数。
- observation_year_raw / observation_year：数字年写整数；"2014 or before" 开放区间写 NULL。
- raw_value 原样保存；数字百分比 → 小数比率，非数值 "NA" → normalized=None 并计
  VALUE_UNPARSEABLE（软失败），保留原文。

== 确定性要求 ==
- 通过变量名定位并解析 JS 数组字面量（平衡括号 + 字符串字面量 tokenizer），
  绝不使用"全页百分号正则"猜业务数据。
- 结构漂移（缺变量/缺段落/行宽与 policyYears 不一致/含非字符串 token/
  数组未闭合/报告年度缺失）→ CloParseError（STRUCTURE_MISMATCH）。
- 零产品、零业务记录 → ZERO_RECORD（明确失败，除非注册表 allows_empty=true）。
"""

import re
from typing import List, Optional

# 段落锚点：确认当前页为分红实现率页（Universal Life 结算利率表不属于本解析器）
SECTION_ANCHOR_AD = "Participating Plans - with Annual Dividend"
SECTION_ANCHOR_TD = "Participating Plans - with Terminal Dividend"

# JS 数组变量名（按当前真实页面）
VAR_POLICY_YEARS = "policyYears"
VAR_AD = "dataSets1"          # Annual Dividend
VAR_TD = "dataSets2"          # Terminal Dividend
VAR_OTHER = "dataSets3"       # Accumulated Interest（本年空）

# 三个数组 → (metric_type, metric_type_raw)
DATASET_METRICS = [
    (VAR_AD, "AD", "Annual Dividend"),
    (VAR_TD, "TD", "Terminal Dividend"),
    (VAR_OTHER, "OTHER", "Accumulated Interest"),
]

# 百分比：整数或小数 + '%'（沿用 T004/T005 口径）
_PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
# 括号内的纯四位数字年份："(2024)" → 2024；"(2014 or before)" 不匹配
_YEAR_IN_PAREN_RE = re.compile(r"\((\d{4})\)")
# 报告年度："Reporting year: 2025"
_REPORT_YEAR_RE = re.compile(r"Reporting year:\s*(\d{4})")
# JS 变量声明："var policyYears = "（兼容 let/const，防轻微重构即误判漂移）
_VAR_DECL_RE = r"\b(?:var|let|const)\s+%s\s*=\s*"


class CloParseError(Exception):
    """CLO HTML 结构不符合预期（缺变量/缺段落/行宽不符/含非字符串/数组未闭合/报告年度缺失），
    对应 STRUCTURE_MISMATCH 硬失败。"""


def parse_ratio(value_str) -> Optional[float]:
    """把值字符串解析为小数比率；无法解析返回 None。

    - "100%" -> 1.0， "70%" -> 0.70， "112%" -> 1.12（超过 100% 合法）
    - "NA" / "" / None -> None（官网"未适用/未到该保单年度"占位，保留原文计 VALUE_UNPARSEABLE）
    """
    if value_str is None:
        return None
    s = str(value_str).strip()
    m = _PCT_RE.match(s)
    if m:
        return float(m.group(1)) / 100.0
    return None


def parse_observation_year(label) -> tuple:
    """把观察期标签解析为 (observation_year_raw, observation_year)。

    - "Policy Year 1 (2024)" → ("Policy Year 1 (2024)", 2024)
    - "Policy Year 10+ (2014 or before)" → ("Policy Year 10+ (2014 or before)", None)
      （开放区间，整数年写 NULL，不虚构单年）
    """
    label = str(label).strip()
    m = _YEAR_IN_PAREN_RE.search(label)
    if m:
        return (label, int(m.group(1)))
    return (label, None)


def standardize_metric(raw: str) -> tuple:
    """官网指标原始名 → (metric_type, metric_type_raw)。

    本页只出现三类：Annual Dividend / Terminal Dividend / Accumulated Interest。
    其余未知名 → OTHER 且原文保留，绝不猜测合并到 AD/TD/RB/TB/TCV。
    """
    raw = str(raw).strip()
    mapping = {
        "Annual Dividend": "AD",
        "Terminal Dividend": "TD",
    }
    return (mapping.get(raw, "OTHER"), raw)


def _extract_js_array(text: str, start: int):
    """从 text[start]（须为 '['）解析一个 JS 数组字面量，返回 (value, end_index)。

    value 是嵌套列表，叶节点为字符串。只接受双引号字符串字面量、'['、']' 与空白/逗号；
    出现任何其它字符（数字/标识符/运算符等）→ CloParseError（结构漂移，避免静默跳过）。
    支持 '\\\\' 与 '\\"' 转义；其余转义按后一字符直取（本页数据无其它转义）。
    """
    i = start
    if i >= len(text) or text[i] != "[":
        raise CloParseError("JS 数组起始 '[' 缺失")
    stack = []
    root = []
    current = root
    i += 1
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n,":
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf: List[str] = []
            while j < n:
                cc = text[j]
                if cc == "\\":
                    if j + 1 < n:
                        buf.append(text[j + 1])
                        j += 2
                        continue
                    j += 1
                    continue
                if cc == '"':
                    break
                buf.append(cc)
                j += 1
            current.append("".join(buf))
            i = j + 1
            continue
        if c == "[":
            new = []
            current.append(new)
            stack.append(current)
            current = new
            i += 1
            continue
        if c == "]":
            if not stack:
                return root, i + 1
            current = stack.pop()
            i += 1
            continue
        raise CloParseError(f"JS 数组含非字符串/非结构字符 {c!r}（结构漂移）")
    raise CloParseError("JS 数组未闭合")


def _find_var_array(text: str, name: str):
    """定位 `(var|let|const) name = [...]` 并解析数组字面量；缺失返回 None。"""
    m = re.search(_VAR_DECL_RE % re.escape(name), text)
    if not m:
        return None
    value, _end = _extract_js_array(text, m.end())
    return value


def _extract_report_year(text: str) -> int:
    """从段落标题 "Reporting year: YYYY" 提取报告年度（取段落锚点之前最近的一处）。"""
    anchor = text.find(SECTION_ANCHOR_AD)
    if anchor == -1:
        raise CloParseError(f"缺少段落锚点 {SECTION_ANCHOR_AD!r}")
    matches = list(_REPORT_YEAR_RE.finditer(text[:anchor]))
    if not matches:
        raise CloParseError("段落锚点之前缺少 'Reporting year: YYYY'")
    return int(matches[-1].group(1))


def _validate_rows(dataset: List, name: str, width: int):
    """校验单个 dataSet 数组：每个元素是 list 且宽度 = width（name/type/scope + N 值）。"""
    if not isinstance(dataset, list):
        raise CloParseError(f"{name} 不是数组")
    for ri, row in enumerate(dataset):
        if not isinstance(row, list):
            raise CloParseError(f"{name}[{ri}] 不是数组（结构漂移）")
        if len(row) != width:
            raise CloParseError(
                f"{name}[{ri}] 宽度 {len(row)} != 期望 {width}（policyYears {width - 3} 列 + 3 元数据）"
            )
        if not all(isinstance(v, str) for v in row):
            raise CloParseError(f"{name}[{ri}] 含非字符串元素（结构漂移）")


def _records_for_dataset(dataset: List, metric_type: str, metric_type_raw: str,
                         report_year: int, obs_labels: List[str]):
    """把一个 dataSet 展开为标准观测记录列表。"""
    records: List[dict] = []
    for row in dataset:
        name = row[0]
        scope = row[2]
        values = row[3:]
        for obs_label, val in zip(obs_labels, values):
            obs_raw, obs_year = parse_observation_year(obs_label)
            records.append({
                "product_name_raw": name,
                "metric_type": metric_type,
                "metric_type_raw": metric_type_raw,
                "report_year": report_year,
                "observation_year_raw": obs_raw,
                "observation_year": obs_year,
                "scope_currency_raw": scope,
                "raw_value": val,
                "normalized_value": parse_ratio(val),
                "product_id": None,
            })
    return records


def parse_clo_html(body: bytes) -> dict:
    """解析 CLO 分红实现率 HTML 字节 → 标准化结果。

    返回：
      {"status": "OK" | "ZERO_RECORD", "report_year": int, "product_count": int,
       "records": [record...], "value_unparseable": int}

    结构漂移（缺变量/缺段落/行宽不符/报告年度缺失/数组未闭合/非字符串）→ CloParseError。
    零产品、零业务记录 → ZERO_RECORD。
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        raise CloParseError(f"HTML 非 UTF-8: {type(e).__name__}")

    # 段落锚点：确认是分红实现率页（避免误解析万能寿险结算利率页）
    if SECTION_ANCHOR_AD not in text or SECTION_ANCHOR_TD not in text:
        raise CloParseError(
            "缺少分红实现率段落锚点（Participating Plans - with Annual/Terminal Dividend）"
        )

    report_year = _extract_report_year(text)

    # 观察期标签
    obs_labels = _find_var_array(text, VAR_POLICY_YEARS)
    if obs_labels is None:
        raise CloParseError(f"缺少 JS 变量 {VAR_POLICY_YEARS!r}")
    if not isinstance(obs_labels, list) or not obs_labels:
        raise CloParseError("policyYears 为空或不是数组")
    if not all(isinstance(v, str) for v in obs_labels):
        raise CloParseError("policyYears 含非字符串元素（结构漂移）")
    obs_width = len(obs_labels)

    # 三个数据集
    datasets = []
    for var_name, metric_type, metric_type_raw in DATASET_METRICS:
        ds = _find_var_array(text, var_name)
        if ds is None:
            raise CloParseError(f"缺少 JS 变量 {var_name!r}")
        _validate_rows(ds, var_name, obs_width + 3)
        datasets.append((ds, metric_type, metric_type_raw))

    # 零产品（三个数据集全空）→ ZERO_RECORD
    total_products = sum(len(ds) for ds, _m, _r in datasets)
    if total_products == 0:
        return {
            "status": "ZERO_RECORD",
            "report_year": report_year,
            "product_count": 0,
            "records": [],
            "value_unparseable": 0,
        }

    # 展开记录（保留原文；不合并 AD/TD/OTHER，不猜未知指标）
    records: List[dict] = []
    for ds, metric_type, metric_type_raw in datasets:
        records.extend(_records_for_dataset(
            ds, metric_type, metric_type_raw, report_year, obs_labels,
        ))

    if not records:
        return {
            "status": "ZERO_RECORD",
            "report_year": report_year,
            "product_count": total_products,
            "records": [],
            "value_unparseable": 0,
        }

    value_unparseable = sum(1 for r in records if r["normalized_value"] is None)
    return {
        "status": "OK",
        "report_year": report_year,
        "product_count": total_products,
        "records": records,
        "value_unparseable": value_unparseable,
    }
