#!/usr/bin/env python3
"""Sun Life 与 BOC Life 官方分红实现率静态 HTML 解析器。"""

import re
from typing import Optional

from lxml import html


class MultiHtmlParseError(Exception):
    """页面结构与已验证的官方披露结构不一致。"""


_PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*%$")
_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def _text(node) -> str:
    return " ".join("".join(node.itertext()).split())


def _ratio(raw: str) -> Optional[float]:
    match = _PCT_RE.fullmatch(raw.strip())
    return float(match.group(1)) / 100.0 if match else None


def _observation(label: str):
    clean = " ".join(label.split())
    # Before/or before/及 earlier describe an open interval, never a single year.
    if re.search(r"before|or before|及\s*20\d{2}|或之前", clean, re.I):
        return clean, None
    years = _YEAR_RE.findall(clean)
    return clean, int(years[-1]) if len(years) == 1 else None


def _record(product: str, metric: str, metric_raw: str, report_year: int,
            observation_raw: str, raw_value: str, scope: Optional[str] = None):
    obs_raw, obs_year = _observation(observation_raw)
    return {
        "product_name_raw": product.strip(),
        "metric_type": metric,
        "metric_type_raw": metric_raw.strip(),
        "report_year": report_year,
        "observation_year_raw": obs_raw,
        "observation_year": obs_year,
        "scope_currency_raw": scope.strip() if scope else None,
        "raw_value": raw_value.strip(),
        "normalized_value": _ratio(raw_value),
        "product_id": None,
    }


def _finish(records, products, report_year):
    if report_year is None or not records or not products:
        raise MultiHtmlParseError("未找到完整的报告年度、产品和分红实现率记录")
    return {
        "status": "OK",
        "report_year": report_year,
        "product_count": len(products),
        "record_count": len(records),
        "value_unparseable": sum(r["normalized_value"] is None for r in records),
        "records": records,
    }


def parse_sun_html(body: bytes) -> dict:
    """解析 Sun Life 中文官方页内 `div.data` 下的分红实现率表。

    只接受标题含“报告年度”及“分红实现率”的表，明确排除同页总现金价值比率。
    周年红利、归原红利、终期/特别红利分别映射 AD、RB、TB。
    """
    try:
        doc = html.fromstring(body.decode("utf-8"))
    except Exception as exc:
        raise MultiHtmlParseError("HTML 无法解析") from exc
    if "各产品的分红实现率" not in _text(doc):
        raise MultiHtmlParseError("缺少 Sun Life 分红实现率页面锚点")

    candidates = []
    for table in doc.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " data ")]//table'):
        previous = table.xpath("preceding::p[normalize-space()][1]")
        title = _text(previous[0]) if previous else ""
        if "分红实现率" not in title or "报告年度" not in title or "总现金价值" in title:
            continue
        year_match = _YEAR_RE.search(title)
        if not year_match:
            raise MultiHtmlParseError("Sun Life 表格标题缺少报告年度")
        candidates.append((int(year_match.group(1)), title, table))
    if not candidates:
        raise MultiHtmlParseError("Sun Life 未找到分红实现率表")
    # 页面可能保留少量旧年度表；本采集运行只写最新披露年度，避免混入旧版残留。
    report_year = max(x[0] for x in candidates)
    records, products = [], set()
    for candidate_year, title, table in candidates:
        if candidate_year != report_year:
            continue
        if "周年红利" in title:
            metric, metric_raw = "AD", "周年红利"
        elif "归原红利" in title:
            metric, metric_raw = "RB", "归原红利"
        elif "终期红利" in title or "特别红利" in title:
            metric, metric_raw = "TB", "终期红利或特别红利"
        else:
            raise MultiHtmlParseError(f"未知 Sun Life 红利类型: {title}")
        rows = table.xpath(".//tr")
        if len(rows) < 2:
            raise MultiHtmlParseError("Sun Life 分红表缺少数据行")
        headers = [_text(x) for x in rows[0].xpath("./th|./td")]
        if len(headers) < 4 or headers[0] != "产品" or "产品种类" not in headers[1]:
            raise MultiHtmlParseError("Sun Life 分红表头结构漂移")
        observations = headers[2:]
        for row in rows[1:]:
            cells = [_text(x) for x in row.xpath("./th|./td")]
            if len(cells) != len(headers):
                raise MultiHtmlParseError("Sun Life 分红表行宽与表头不一致")
            product, product_type = cells[0], cells[1]
            if not product:
                raise MultiHtmlParseError("Sun Life 产品名为空")
            products.add(product)
            for obs, value in zip(observations, cells[2:]):
                records.append(_record(product, metric, metric_raw, report_year, obs, value, product_type))
    return _finish(records, products, report_year)


def parse_boc_html(body: bytes) -> dict:
    """解析 BOC Life 页面桌面版披露表；忽略同内容的移动版重复表。"""
    try:
        doc = html.fromstring(body.decode("utf-8"))
    except Exception as exc:
        raise MultiHtmlParseError("HTML 无法解析") from exc
    if "Fulfillment Ratio" not in _text(doc):
        raise MultiHtmlParseError("缺少 BOC Life 分红实现率页面锚点")

    records, products, years = [], set(), set()
    figures = doc.xpath('//figure[contains(@class,"fulfilment-tabs-tables__table--desktop")]')
    if not figures:
        raise MultiHtmlParseError("BOC Life 桌面版分红表缺失")
    for figure in figures:
        tables = figure.xpath(".//table")
        panels = figure.xpath('ancestor::div[contains(concat(" ",normalize-space(@class)," ")," panel ")][1]')
        titles = figure.xpath('preceding::p[contains(@class,"fulfilment-tabs-tables__table-title")][1]')
        if len(tables) != 1 or not panels or not titles:
            raise MultiHtmlParseError("BOC Life 产品面板结构漂移")
        product_nodes = panels[0].xpath('.//a[contains(@class,"panel__trigger")][1]')
        product = _text(product_nodes[0]) if product_nodes else ""
        title = _text(titles[0])
        match = re.search(r"Fulfillment ratios for (annual|terminal) dividends for reporting year (20\d{2})", title, re.I)
        if not product or not match:
            raise MultiHtmlParseError("BOC Life 产品名或表格标题不可识别")
        metric = "AD" if match.group(1).lower() == "annual" else "TD"
        metric_raw = f"{match.group(1).title()} Dividends"
        report_year = int(match.group(2)); years.add(report_year); products.add(product)
        rows = tables[0].xpath(".//tr")
        if len(rows) < 3:
            raise MultiHtmlParseError("BOC Life 分红表缺少表头或数据")
        observations = [_text(x) for x in rows[1].xpath("./th|./td")]
        if len(observations) != 11:
            raise MultiHtmlParseError("BOC Life 观察期列数不是 11")
        for row in rows[2:]:
            nodes = row.xpath("./th|./td")
            cells = [_text(x) for x in nodes]
            if len(cells) == 2 and int(nodes[1].get("colspan") or 1) == 11:
                cells = [cells[0]] + [cells[1]] * 11
            if len(cells) != 12:
                raise MultiHtmlParseError("BOC Life 数据行宽与 11 个观察期不一致")
            product_type = cells[0]
            for obs, value in zip(observations, cells[1:]):
                records.append(_record(product, metric, metric_raw, report_year, obs, value, product_type))
    if len(years) != 1:
        raise MultiHtmlParseError(f"BOC Life 报告年度不唯一: {sorted(years)}")
    return _finish(records, products, next(iter(years)))
