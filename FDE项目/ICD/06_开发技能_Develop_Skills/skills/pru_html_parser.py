#!/usr/bin/env python3
"""保诚香港官方 AEM 页面中的标准分红履行率表解析器。"""

import re
from lxml import html


class PruHtmlParseError(Exception):
    pass


_PCT = re.compile(r"^(\d+(?:\.\d+)?)%$")
_YEAR = re.compile(r"(20\d{2})")


def _text(node):
    return " ".join(node.text_content().split())


def _metric(raw):
    if "歸原紅利" in raw:
        return "RB"
    if "特別紅利" in raw:
        return "TB"
    if "終期紅利" in raw:
        return "TD"
    if any(term in raw for term in ("現金紅利", "每月入息", "每月年金")):
        return "AD"
    return "OTHER"


def _product_name(raw):
    value = re.split(r"\s*產品類別\s*[:：]", raw, maxsplit=1)[0].strip()
    if not value:
        raise PruHtmlParseError("保誠产品名为空")
    return value


def parse_pru_html(body: bytes):
    try:
        doc = html.fromstring(body)
    except Exception as exc:
        raise PruHtmlParseError("保诚 HTML 无法解析") from exc
    tables = doc.xpath("//table")
    if not tables:
        raise PruHtmlParseError("保诚页面未找到履行率表")

    records, products, report_years = [], set(), set()
    for index, table in enumerate(tables):
        h4 = table.xpath("preceding::h4[1]")
        h5 = table.xpath("preceding::h5[1]")
        rows = table.xpath(".//tr")
        if not h4 or not h5 or len(rows) < 3:
            raise PruHtmlParseError(f"保诚表 {index} 缺产品标题、指标标题或数据行")
        product = _product_name(_text(h4[0]))
        metric_raw = _text(h5[0])
        year_matches = _YEAR.findall(metric_raw)
        if len(set(year_matches)) != 1:
            raise PruHtmlParseError(f"保诚表 {index} 报告年度缺失或歧义: {metric_raw}")
        report_year = int(year_matches[0])
        headers = [_text(cell) for cell in rows[1].xpath("./th|./td")]
        if not headers:
            raise PruHtmlParseError(f"保诚表 {index} 观察期表头为空")
        observations = []
        for label in headers:
            found = _YEAR.findall(label)
            observations.append((label, int(found[0]) if found and "之前" not in label else None))
        for row in rows[2:]:
            cells = row.xpath("./th|./td")
            if len(cells) != len(observations) + 1:
                raise PruHtmlParseError(
                    f"保诚表 {index} 数据行宽异常: expected={len(observations)+1}, actual={len(cells)}"
                )
            currency = _text(cells[0])
            if not currency:
                raise PruHtmlParseError(f"保诚表 {index} 货币为空")
            for (label, observation_year), cell in zip(observations, cells[1:]):
                raw = _text(cell)
                if not raw:
                    raise PruHtmlParseError(f"保诚表 {index} 存在空值单元格")
                pct = _PCT.fullmatch(raw)
                records.append({
                    "product_name_raw": product,
                    "metric_type": _metric(metric_raw),
                    "metric_type_raw": metric_raw,
                    "report_year": report_year,
                    "observation_year_raw": label,
                    "observation_year": observation_year,
                    "scope_currency_raw": currency,
                    "raw_value": raw,
                    "normalized_value": float(pct.group(1)) / 100 if pct else None,
                    "product_id": None,
                })
        products.add(product)
        report_years.add(report_year)
    if len(report_years) != 1 or not records:
        raise PruHtmlParseError(f"保诚报告年度不唯一或零记录: {sorted(report_years)}")
    return {
        "status": "OK", "report_year": next(iter(report_years)),
        "product_count": len(products), "record_count": len(records),
        "value_unparseable": sum(r["normalized_value"] is None for r in records),
        "records": records,
    }
