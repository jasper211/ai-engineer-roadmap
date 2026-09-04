#!/usr/bin/env python3
"""AXA/FWD Next.js 履行率：目录发现、多页证据采集及离线解析。"""

import base64
import gzip
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

from lxml import html


class NextRatioError(Exception):
    pass


@dataclass
class CollectOutcome:
    fetch_status: str
    body: bytes = b""
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    error_code: Optional[str] = None
    note: str = ""


def _next_data(body: bytes):
    try:
        doc = html.fromstring(body)
        values = doc.xpath('//script[@id="__NEXT_DATA__"]/text()')
        return json.loads(values[0])
    except Exception as exc:
        raise NextRatioError("页面缺少有效 __NEXT_DATA__") from exc


def _text(fragment):
    if not fragment:
        return ""
    try:
        return " ".join(html.fromstring(fragment).text_content().split())
    except Exception:
        return " ".join(str(fragment).split())


def discover(body: bytes, insurer: str):
    return _discover_data(_next_data(body), insurer)


def _discover_data(data, insurer: str):
    links = []
    if insurer == "AXA":
        items = data["props"]["pageProps"]["sliceZone"]["slices"][4]["value"]["items"]
        links = [(item.get("target") or {}).get("href") for item in items]
        links = [u for u in links if isinstance(u, str) and u.startswith("/en/fulfilment-ratios-total-value-ratios-")]
    elif insurer == "FWD":
        rows = data["props"]["pageProps"]["data"]["data"]["layout"][0]["dataComponent"]["body"][3]["table_content_section"]["table"][0]["sections"][0]["rows"]
        for row in rows:
            fragment = row["columns"][0]["content"]
            links.extend(html.fromstring(fragment).xpath("//a/@href"))
        links = [u for u in links if u.startswith("/regulatory-disclosures/fulfillment-ratios/")]
    else:
        raise NextRatioError(f"不支持的 Next.js 险企: {insurer}")
    unique = list(dict.fromkeys(links))
    if not unique or len(unique) != len(links) or len(unique) > 128:
        raise NextRatioError(f"{insurer} 产品目录为空、重复或超过上限: {len(unique)}/{len(links)}")
    return unique


def _pack(data):
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.b64encode(gzip.compress(raw, compresslevel=9)).decode("ascii")


def _unpack(value):
    try:
        return json.loads(gzip.decompress(base64.b64decode(value, validate=True)))
    except Exception as exc:
        raise NextRatioError("Next.js 压缩证据无法还原") from exc


def collect(index_url, insurer, page_fetch, workers=8):
    index = page_fetch(index_url)
    if index.fetch_status != "OK":
        return CollectOutcome(index.fetch_status, http_status=index.http_status, final_url=index.final_url,
                              error_code=index.error_code, note=index.note)
    try:
        paths = discover(index.body, insurer)
        results = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs = {pool.submit(page_fetch, urljoin(index.final_url or index_url, path)): path for path in paths}
            for future in as_completed(jobs):
                path = jobs[future]
                response = future.result()
                if response.fetch_status != "OK":
                    raise NextRatioError(f"产品页抓取失败 {path}: {response.fetch_status}/{response.error_code}")
                results[path] = _next_data(response.body)
        pages = [{"path": path, "next_data_gzip_b64": _pack(results[path])} for path in paths]
        bundle = {"schema_version": 1, "insurer": insurer, "index_url": index.final_url or index_url,
                  "index_next_data_gzip_b64": _pack(_next_data(index.body)), "pages": pages}
        body = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return CollectOutcome("OK", body, 200, index.final_url or index_url,
                              note=f"{insurer} official product pages={len(pages)}")
    except Exception as exc:
        return CollectOutcome("NETWORK_ERROR", error_code="NETWORK_CONNECTION",
                              note=f"{insurer} 多页证据采集失败: {type(exc).__name__}: {exc}")


_PCT = re.compile(r"^(\d+(?:\.\d+)?)%$")
_YEAR = re.compile(r"(20\d{2})")


def _metric(raw):
    s = raw.lower()
    if "annual" in s or "週年" in raw or "周年" in raw: return "AD"
    if "reversionary" in s or "歸原" in raw or "归原" in raw: return "RB"
    if "terminal dividend" in s or "終期紅利" in raw or "终期红利" in raw: return "TD"
    if "terminal bonus" in s or "特別紅利" in raw or "特别红利" in raw: return "TB"
    return "OTHER"


def _record(product, metric_raw, scope, label, issue_year, raw, report_year):
    match = _PCT.fullmatch(raw.strip())
    return {"product_name_raw": product, "metric_type": _metric(metric_raw), "metric_type_raw": metric_raw,
            "report_year": report_year, "observation_year_raw": label, "observation_year": issue_year,
            "scope_currency_raw": scope, "raw_value": raw,
            "normalized_value": float(match.group(1)) / 100 if match else None, "product_id": None}


def _parse_axa(data):
    pp = data["props"]["pageProps"]
    product = pp["title"].split(" | ", 1)[0].strip()
    includes = pp["sliceZone"]["includes"]
    keys = [k for k in includes if k.startswith("tab-fulfilment-ratios-")]
    if len(keys) != 1: raise NextRatioError(f"AXA 产品履行率区块数量异常: {len(keys)}")
    tables = [i["value"] for i in includes[keys[0]] if i.get("type") == "DataTable"]
    if len(tables) != 1: raise NextRatioError(f"AXA 履行率表数量异常: {len(tables)}")
    rows = [row for group in tables[0]["data"] for row in group]
    header = rows[0]
    years = {}
    for cell in header[1:]:
        text = _text(cell.get("content")); found = _YEAR.findall(text)
        if found: years[cell.get("actualColIndex")] = (text, int(found[0]))
    report_year = max(y for _, y in years.values()) + 1
    records = []
    for row in rows[1:]:
        if not row: continue
        metric_scope = _text(row[0].get("content"))
        if not metric_scope: continue
        for cell in row[1:]:
            col = cell.get("actualColIndex"); raw = _text(cell.get("content"))
            span = int(cell.get("mergeRight") or 0)
            for idx in range(col, col + span + 1):
                if idx in years:
                    label, issue = years[idx]
                    records.append(_record(product, metric_scope, metric_scope, label, issue, raw, report_year))
    return records, product, report_year


def _parse_fwd(data):
    body = data["props"]["pageProps"]["data"]["data"]["layout"][0]["dataComponent"]["body"][3]["table_content_section"]
    desc = _text(body["description"]); match = re.search(r"(20\d{2})年度", desc)
    product = _text(html.tostring(html.fromstring(body["description"]).xpath("//h4")[0], encoding="unicode"))
    if not match or not product: raise NextRatioError("FWD 产品名或报告年度缺失")
    report_year = int(match.group(1)); table = body["table"][0]
    years = []
    for h in table["headers"][2:]:
        text = _text(h["content"]); found = _YEAR.findall(text)
        years.append((text, int(found[0]) if found else None))
    records = []; inherited = ""
    for section in table["sections"]:
        for row in section["rows"]:
            cells = row["columns"]
            metric = _text(cells[0]["content"]) or inherited
            if metric: inherited = metric
            scope = _text(cells[1]["content"])
            if len(cells) - 2 != len(years): raise NextRatioError(f"FWD 表格行宽异常: {product}")
            for (label, issue), cell in zip(years, cells[2:]):
                records.append(_record(product, metric, scope, label, issue, _text(cell["content"]), report_year))
    return records, product, report_year


def parse_bundle(body: bytes):
    try: bundle = json.loads(body)
    except Exception as exc: raise NextRatioError("Next.js 证据包不是有效 JSON") from exc
    insurer = bundle.get("insurer"); pages = bundle.get("pages")
    if bundle.get("schema_version") != 1 or insurer not in ("AXA", "FWD") or not isinstance(pages, list) or not pages:
        raise NextRatioError("Next.js 证据包结构不完整")
    index_data = _unpack(bundle.get("index_next_data_gzip_b64"))
    # 目录证据必须可还原；产品 path 列表与证据页一一对应。
    if not isinstance(index_data, dict): raise NextRatioError("Next.js 目录证据异常")
    paths = [p.get("path") for p in pages]
    if len(paths) != len(set(paths)): raise NextRatioError("Next.js 产品页路径重复")
    if paths != _discover_data(index_data, insurer): raise NextRatioError("产品页证据与官方目录不一致")
    parsed_pages=[]; years=set()
    for page in pages:
        data = _unpack(page.get("next_data_gzip_b64"))
        recs, product, year = _parse_axa(data) if insurer == "AXA" else _parse_fwd(data)
        if not recs: raise NextRatioError(f"{insurer} 产品零记录: {page.get('path')}")
        parsed_pages.append((page["path"], product, recs)); years.add(year)
    if len(years) != 1: raise NextRatioError(f"{insurer} 报告年度不唯一")
    counts={}
    for _, product, _ in parsed_pages: counts[product]=counts.get(product,0)+1
    all_records=[]
    for path, product, recs in parsed_pages:
        # 官方 CMS 偶有不同产品页复用同一标题；仅在冲突时附页面 uid，防止入库身份碰撞。
        if counts[product] > 1:
            unique_name=f"{product} [{path.rstrip('/').rsplit('/',1)[-1]}]"
            for record in recs: record["product_name_raw"]=unique_name
        all_records.extend(recs)
    return {"status":"OK", "report_year":next(iter(years)), "product_count":len(pages),
            "record_count":len(all_records),
            "value_unparseable":sum(r["normalized_value"] is None for r in all_records), "records":all_records}
