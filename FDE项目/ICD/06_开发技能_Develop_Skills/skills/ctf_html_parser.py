#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/ctf_html_parser.py · CTF Life 分红实现率 HTML 表格解析与标准化
（L3-ICD-03 解析层 · format=html 分支）

职责边界：纯函数，把 CTF Life `fulfillment_ratio` 原始 HTML 字节解析为标准化的
观测记录列表。不访问网络、不读库、不写库（入库由 tools/ratio_writer +
skills/parse_disclosure 负责）。

CTF Life 真实页面结构（2026 版，report_year=2025，70 个产品表格）：
  <h3>Fulfillment Ratios of Dividends/Bonuses</h3>     ← 目标段落（到下一个 <h3> 结束）
    <div class="tableStyleRatio__container ...">        ← 每个产品一个容器
      <p class="text-center fzBold">PRODUCT NAME</p>    ← 产品原始名
      <div class="tableStyleRatio__wrapper">
        <table class="tableStyleRatio">                 ← 3 层表头 + 数据行
          <thead>
            <tr><th rowspan=3>Type</th><th rowspan=3>Policy Currency</th>
                <td colspan=11>Fulfillment Ratios for Reporting Year 2025</td></tr>
            <tr><td colspan=11>Policy Year (Policy Effective in)</td></tr>
            <tr><td>1(2024)</td>...<td>10(2015)</td><td>11+(Before 2014)</td></tr>
          </thead>
          <tbody>
            <tr><td rowspan=N>Annual Dividends</td><td>USD</td><td>100%</td>...</tr>
            ...
          </tbody>
        </table>
      </div>
    </div>
  <h3>Total Cash Value Ratio</h3>                       ← 下一段落（不属于 fulfillment_ratio）

关键结构特征（必须用表格语义恢复，不得用全页百分号正则猜数据）：
- 表头 3 层：Type/Policy Currency 各 rowspan=3；报告年度与"Policy Year"各 colspan=11；
  第三层是 11 个观察期标签 `1(2024)`…`10(2015)`、`11+(Before 2014)`。
- 数据行中指标单元格可能带 rowspan（同一指标按 USD/HKD/CNY 多币种分组，例如
  Annual Dividends rowspan=2、Reversionary Bonus rowspan=3），必须按 rowspan 把
  指标名传播到每一行，币种逐行读取。
- 个别值单元格带 colspan=11（"No policy has reached the first policy anniversary..."），
  按 colspan 传播到全部 11 个观察期列，各产生一条保留原文、normalized=NULL 的记录。
- 值单元格只可能是数字百分比或非数值占位（Closed to Sales / Not yet launched /
  Zero Bonus / No Termination / No Policy / No policy has reached...）。

标准化约定（对齐 data_contract.md 与 T004 三项决策）：
- metric_type：Annual Dividends→AD、Terminal Dividends→TD、Reversionary Bonus→RB、
  Terminal Bonus→TB；其余（Policy Value、Special Bonus 等官网第五/第六口径）→OTHER，
  绝不与 AD/TD/RB/TB 合并。metric_type_raw 一律保存官网原始字符串。
- scope_currency_raw：保存 Policy Currency 原文（USD/HKD/CNY），不拆分、不映射。
- report_year：表头 "Fulfillment Ratios for Reporting Year 2025" 中的年份整数。
- observation_year_raw / observation_year：`1(2024)` → ("1(2024)", 2024)；
  `11+(Before 2014)` → ("11+(Before 2014)", None)（开放区间，不虚构单年）。
- raw_value 原样保存；数字百分比 → 小数比率，非数值 → normalized=None 并计
  VALUE_UNPARSEABLE（软失败）。
"""

import re
from html.parser import HTMLParser
from typing import List, Optional

# 段落标题：本解析器只处理"分红/红利履行率"段落，到下一个 <h3> 为止。
SECTION_HEADING = "Fulfillment Ratios of Dividends/Bonuses"

# 官网指标原始名 → 标准指标枚举（对齐 data_contract AD/TD/RB/TB/TCV/OTHER）
METRIC_MAP = {
    "Annual Dividends": "AD",
    "Terminal Dividends": "TD",
    "Reversionary Bonus": "RB",
    "Terminal Bonus": "TB",
}

# 百分比：整数或小数 + '%'（沿用 T004 口径）
_PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
# 观察期标签：数字（可选 +）后跟括号，如 "1(2024)" / "11+(Before 2014)"
_OBS_LABEL_RE = re.compile(r"^\d+\+?\s*\(.*\)$")
# 括号内的四位数字年份："1(2024)" → 2024；"11+(Before 2014)" 不匹配
_YEAR_IN_PAREN_RE = re.compile(r"\((\d{4})\)")
# 报告年度："Fulfillment Ratios for Reporting Year 2025"
_REPORT_YEAR_RE = re.compile(r"Reporting Year\s+(\d{4})")


class CtfParseError(Exception):
    """CTF HTML 结构不符合预期（缺段落/缺表头/缺观察期列/报告年度缺失），
    对应 STRUCTURE_MISMATCH 硬失败。"""


def parse_ratio(value_str) -> Optional[float]:
    """把值单元格字符串解析为小数比率；无法解析返回 None。

    - "100%" -> 1.0， "94%" -> 0.94， "112%" -> 1.12（超过 100% 合法）
    - "Closed to Sales" / "Not yet launched" / "Zero Bonus" / "No Termination" /
      "No Policy" / "No policy has reached..." / 空串 -> None
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

    - "1(2024)" → ("1(2024)", 2024)（原文标签与整数年同时保存）
    - "11+(Before 2014)" → ("11+(Before 2014)", None)（开放区间，整数年写 NULL）
    """
    label = str(label).strip()
    m = _YEAR_IN_PAREN_RE.search(label)
    if m:
        return (label, int(m.group(1)))
    return (label, None)


def standardize_metric(raw: str) -> tuple:
    """官网指标原始名 → (metric_type, metric_type_raw)。

    已知四类一一映射；其余（Policy Value / Special Bonus 及未来新增口径）→ OTHER，
    原文保留在 metric_type_raw，绝不静默合并到 AD/TD/RB/TB。
    """
    raw = str(raw).strip()
    return (METRIC_MAP.get(raw, "OTHER"), raw)


def _normalize_ws(s: str) -> str:
    """折叠空白（换行/制表/连续空格 → 单空格）并去除首尾空白。"""
    return re.sub(r"\s+", " ", s).strip()


class _CtfDocumentParser(HTMLParser):
    """单遍 HTML 解析：定位 Fulfillment Ratios 段落 → 逐产品提取名称与表格网格。

    只处理段落内 `.tableStyleRatio__container` 容器中的 `<p class=fzBold>`（产品名）
    与 `<table>`（表格）。段落外、其他段落（TCV/历史利率/保费征费/导航/页脚）一律忽略。
    HTML 注释（含被注释掉的模板单元格）由 HTMLParser 默认跳过，不计入业务记录。
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.products = []          # [{name, rows}]；rows 为原始单元格行列表
        self._in_h3 = False
        self._h3_buf = []
        self._in_section = False
        self._section_closed = False
        self._section_found = False
        # 产品容器状态
        self._container_open = False
        self._container_depth = 0
        self._in_name_p = False
        self._name_buf = []
        self._product_name = None
        # 表格状态
        self._in_table = False
        self._in_cell = False
        self._cell_tag = None
        self._cell_buf = []
        self._cell_rs = 1
        self._cell_cs = 1
        self._cur_row = None
        self._cur_rows = None

    # -- 事件处理 -----------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""

        if tag == "h3":
            self._in_h3 = True
            self._h3_buf = []
            return

        if self._in_h3:
            return  # h3 内嵌套标签不影响标题文本捕获

        if tag == "div" and "tableStyleRatio__container" in cls:
            if self._in_section and not self._section_closed:
                self._container_open = True
                self._container_depth = 1
                self._product_name = None
            return

        if self._container_open:
            if tag == "div":
                self._container_depth += 1
                return
            if tag == "p" and "fzBold" in cls:
                self._in_name_p = True
                self._name_buf = []
                return
            if tag == "table":
                self._in_table = True
                self._cur_rows = []
                return

        if self._in_table:
            if tag == "tr":
                self._cur_row = []
            elif tag in ("td", "th"):
                self._in_cell = True
                self._cell_tag = tag
                self._cell_buf = []
                self._cell_rs = int(a.get("rowspan") or 1)
                self._cell_cs = int(a.get("colspan") or 1)

    def handle_endtag(self, tag):
        if tag == "h3" and self._in_h3:
            self._in_h3 = False
            heading = _normalize_ws("".join(self._h3_buf))
            if heading == SECTION_HEADING:
                self._in_section = True
                self._section_closed = False
                self._section_found = True
            elif self._in_section:
                self._in_section = False
                self._section_closed = True
            return

        if self._in_table:
            if tag in ("td", "th") and self._in_cell:
                self._in_cell = False
                text = _normalize_ws("".join(self._cell_buf))
                if self._cur_row is not None:
                    self._cur_row.append({
                        "t": self._cell_tag, "v": text,
                        "rs": self._cell_rs, "cs": self._cell_cs,
                    })
            elif tag == "tr" and self._cur_row is not None:
                self._cur_rows.append(self._cur_row)
                self._cur_row = None
            elif tag == "table":
                self._in_table = False
                if self._container_open and self._product_name:
                    self.products.append({
                        "name": self._product_name,
                        "rows": self._cur_rows or [],
                    })
                self._cur_rows = None
            return

        if self._container_open:
            if tag == "p" and self._in_name_p:
                self._in_name_p = False
                self._product_name = _normalize_ws("".join(self._name_buf))
                return
            if tag == "div":
                self._container_depth -= 1
                if self._container_depth <= 0:
                    self._container_open = False
                return

    def handle_data(self, data):
        if self._in_h3:
            self._h3_buf.append(data)
            return
        if self._in_name_p:
            self._name_buf.append(data)
            return
        if self._in_cell:
            self._cell_buf.append(data)
            return


def _expand_grid(rows):
    """把带 rowspan/colspan 的原始单元格行展开为二维矩形网格（缺口为 None）。

    rowspan 会把单元格内容传播到跨行位置；colspan 同理。这保证：
    - 指标名 rowspan=N 时，N 个币种行都能取到同一指标；
    - colspan=11 的值单元格会传播到全部 11 个观察期列。
    """
    grid = []
    occupied = {}  # (row, col) -> True
    for ri, row in enumerate(rows):
        while len(grid) <= ri:
            grid.append([])
        col = 0
        for cell in row:
            while (ri, col) in occupied:
                col += 1
            rs = cell["rs"]
            cs = cell["cs"]
            for dy in range(rs):
                rr = ri + dy
                while len(grid) <= rr:
                    grid.append([])
                for dx in range(cs):
                    cc = col + dx
                    while len(grid[rr]) <= cc:
                        grid[rr].append(None)
                    grid[rr][cc] = cell
                    occupied[(rr, cc)] = True
            col += cs
    width = max((len(r) for r in grid), default=0)
    for r in grid:
        while len(r) < width:
            r.append(None)
    return grid


def _extract_table(name, rows, report_years):
    """从单个产品表格恢复标准化记录。返回记录列表；结构不符抛 CtfParseError。"""
    grid = _expand_grid(rows)
    if not grid:
        raise CtfParseError(f"产品 {name!r} 表格为空")

    # 1) 定位表头行（含 Type + Policy Currency）
    header_idx = None
    for yi, row in enumerate(grid):
        c0 = row[0]["v"] if (len(row) > 0 and row[0]) else ""
        c1 = row[1]["v"] if (len(row) > 1 and row[1]) else ""
        if c0 == "Type" and c1 == "Policy Currency":
            header_idx = yi
            break
    if header_idx is None:
        raise CtfParseError(f"产品 {name!r} 表格缺少 Type/Policy Currency 表头")

    # 2) 报告年度
    joined = " ".join(c["v"] for c in grid[header_idx] if c)
    m = _REPORT_YEAR_RE.search(joined)
    if not m:
        raise CtfParseError(f"产品 {name!r} 表头缺少 Reporting Year")
    report_year = int(m.group(1))
    report_years.add(report_year)

    # 3) 观察期标签行（第 3 层表头，header_idx + 2），并校验结构
    if len(grid) < header_idx + 3:
        raise CtfParseError(f"产品 {name!r} 表格缺少观察期表头行")
    obs_row = grid[header_idx + 2]
    obs_labels = [(c["v"] if c else "") for c in obs_row[2:]]
    if not obs_labels or not all(_OBS_LABEL_RE.match(lbl) for lbl in obs_labels):
        raise CtfParseError(
            f"产品 {name!r} 观察期表头结构不符: {obs_labels[:5]}"
        )

    # 4) 数据行：header_idx + 3 起，逐单元格恢复记录
    records = []
    for yi in range(header_idx + 3, len(grid)):
        row = grid[yi]
        metric_cell = row[0] if len(row) > 0 else None
        cur_cell = row[1] if len(row) > 1 else None
        metric_raw = metric_cell["v"] if metric_cell else ""
        currency = cur_cell["v"] if cur_cell else ""
        if not metric_raw and not currency:
            continue  # 空行（结构性空行），跳过
        if not metric_raw:
            # rowspan 已把指标传播到每行；此处为空说明表结构异常
            raise CtfParseError(f"产品 {name!r} 数据行缺少指标单元格")
        metric_type, metric_type_raw = standardize_metric(metric_raw)

        for xi in range(2, min(len(row), 2 + len(obs_labels))):
            cell = row[xi]
            # None = 结构性缺口（行尾缺失，无该单元格），跳过；
            # 空字符串 = 空单元格，保留原文 raw_value="" 并计为不可解析。
            if cell is None:
                continue
            val = cell["v"]
            obs_label = obs_labels[xi - 2]
            obs_raw, obs_year = parse_observation_year(obs_label)
            records.append({
                "product_name_raw": name,
                "metric_type": metric_type,
                "metric_type_raw": metric_type_raw,
                "report_year": report_year,
                "observation_year_raw": obs_raw,
                "observation_year": obs_year,
                "scope_currency_raw": currency,
                "raw_value": val,
                "normalized_value": parse_ratio(val),
                "product_id": None,
            })
    return records


def parse_ctf_html(body: bytes) -> dict:
    """解析 CTF Life 分红实现率 HTML 字节 → 标准化结果。

    返回：
      {"status": "OK" | "ZERO_RECORD", "report_year": int, "product_count": int,
       "records": [record...], "value_unparseable": int}

    结构漂移（缺段落/缺表头/缺观察期列/报告年度缺失/报告年度不一致）→ CtfParseError。
    零产品、零业务记录 → ZERO_RECORD（明确失败，除非注册表 allows_empty=true）。
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        raise CtfParseError(f"HTML 非 UTF-8: {type(e).__name__}")

    doc = _CtfDocumentParser()
    doc.feed(text)
    doc.close()

    # 段落缺失（页面结构漂移）→ 结构不符；段落存在但 0 产品 → 零产品（对齐 T004 空数据语义）
    if not doc._section_found:
        raise CtfParseError("未找到 'Fulfillment Ratios of Dividends/Bonuses' 段落")
    if not doc.products:
        return {
            "status": "ZERO_RECORD",
            "report_year": None,
            "product_count": 0,
            "records": [],
            "value_unparseable": 0,
        }

    report_years = set()
    records: List[dict] = []
    for prod in doc.products:
        records.extend(_extract_table(prod["name"], prod["rows"], report_years))

    if len(report_years) != 1:
        raise CtfParseError(f"报告年度不一致或缺失: {sorted(report_years)}")
    report_year = report_years.pop()

    if not records:
        return {
            "status": "ZERO_RECORD",
            "report_year": report_year,
            "product_count": len(doc.products),
            "records": [],
            "value_unparseable": 0,
        }

    value_unparseable = sum(1 for r in records if r["normalized_value"] is None)
    return {
        "status": "OK",
        "report_year": report_year,
        "product_count": len(doc.products),
        "records": records,
        "value_unparseable": value_unparseable,
    }
