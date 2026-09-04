#!/usr/bin/env python3
"""YF Life 公开履行率 API：页面发现、证据包采集与离线解析。"""

import base64
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from lxml import html

from tools.http_fetcher import USER_AGENT


API_BASE = "https://www.yflife.com"
CURRENCY_PATH = "/aisite-applyapi/hk/support/dividend/currency"
DIVIDEND_PATH = "/aisite-applyapi/hk/support/getDividend"
_PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
_REPORT_RE = re.compile(r"reporting year\s+(20\d{2})", re.I)


class YflApiError(Exception):
    pass


@dataclass
class YflCollectOutcome:
    fetch_status: str
    body: bytes = b""
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    error_code: Optional[str] = None
    note: str = ""


def _node_text(node):
    return " ".join("".join(node.itertext()).split())


def discover_products(page: bytes):
    try:
        doc = html.fromstring(page.decode("utf-8"))
    except Exception as exc:
        raise YflApiError("YFL 官方页面 HTML 无法解析") from exc
    products = []
    for block in doc.xpath('//div[@id="container1"]//div[contains(concat(" ",normalize-space(@class)," ")," fulfillment_ratio ")][@product-code]'):
        code = (block.get("product-code") or "").strip()
        titles = block.xpath('.//div[contains(@class,"ful_second_title")]')
        name = _node_text(titles[1]) if len(titles) > 1 else ""
        types = block.xpath('.//div[contains(@class,"ful_second_content")][starts-with(normalize-space(.),"Product type:")]')
        product_type = _node_text(types[0]).split(":", 1)[-1].strip() if types else ""
        if not code or not name:
            raise YflApiError("YFL 产品代码或名称缺失")
        products.append({"product_code": code, "product_name_raw": name, "product_type_raw": product_type})
    unique = {p["product_code"]: p for p in products}
    if len(unique) != len(products) or not products:
        raise YflApiError("YFL 产品清单为空或代码重复")
    return products


def _post_json(path: str, payload: dict, timeout: float = 30.0):
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        API_BASE + path, data=data, method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise YflApiError("YFL 单个 API 响应超过 2 MiB")
        return response.status, raw


def collect(page_url: str, page_fetch: Callable[[str], object], post_json: Callable = _post_json):
    page_result = page_fetch(page_url)
    if page_result.fetch_status != "OK":
        return YflCollectOutcome(page_result.fetch_status, http_status=page_result.http_status,
                                 final_url=page_result.final_url, error_code=page_result.error_code,
                                 note=page_result.note)
    try:
        products = discover_products(page_result.body)
        calls = []
        for product in products:
            code = product["product_code"]
            status, raw = post_json(CURRENCY_PATH, {"productCode": code})
            currency_response = json.loads(raw)
            if status != 200 or currency_response.get("code") != 200 or not isinstance(currency_response.get("data"), list):
                raise YflApiError(f"YFL currency API 失败 product={code}")
            currencies = currency_response["data"]
            if not currencies:
                currencies = [{"currency": "ALL", "value": "ALL"}]
            for item in currencies:
                currency = item.get("value")
                if not isinstance(currency, str) or not currency:
                    raise YflApiError(f"YFL currency 字段异常 product={code}")
                payload = {"productCode": code, "currency": currency, "region": "HK"}
                data_status, data_raw = post_json(DIVIDEND_PATH, payload)
                response = json.loads(data_raw)
                if data_status != 200 or response.get("code") != 200 or not isinstance(response.get("data"), dict):
                    raise YflApiError(f"YFL dividend API 失败 product={code} currency={currency}")
                calls.append({"product": product, "currency": currency, "response": response})
        bundle = {
            "schema_version": 1,
            "source_page_url": page_result.final_url or page_url,
            "source_page_b64": base64.b64encode(page_result.body).decode("ascii"),
            "currency_endpoint": CURRENCY_PATH,
            "dividend_endpoint": DIVIDEND_PATH,
            "calls": calls,
        }
        body = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return YflCollectOutcome("OK", body, 200, page_result.final_url or page_url)
    except (YflApiError, ValueError, KeyError, urllib.error.URLError, OSError) as exc:
        return YflCollectOutcome("NETWORK_ERROR", error_code="NETWORK_CONNECTION",
                                 note=f"YFL API 证据包采集失败: {type(exc).__name__}: {exc}")


def _metric(raw: str):
    mapping = {
        "Annual Dividend": "AD", "Extra Bonus": "AD", "Reversionary Bonus": "RB",
        "Terminal Dividend": "TD", "Terminal Bonus": "TB",
    }
    return mapping.get(raw, "OTHER")


def parse_bundle(body: bytes):
    try:
        bundle = json.loads(body)
    except Exception as exc:
        raise YflApiError("YFL API 证据包不是有效 JSON") from exc
    if bundle.get("schema_version") != 1 or not isinstance(bundle.get("calls"), list) or not bundle["calls"]:
        raise YflApiError("YFL API 证据包结构不完整")
    # Base64 必须可还原且仍含产品栏目，保证页面→API 证据链完整。
    try:
        page = base64.b64decode(bundle["source_page_b64"], validate=True)
        discovered = {p["product_code"] for p in discover_products(page)}
    except Exception as exc:
        raise YflApiError("YFL 页面证据无法还原") from exc
    records, products, years = [], set(), set()
    for call in bundle["calls"]:
        product = call.get("product") or {}; code = product.get("product_code")
        if code not in discovered:
            raise YflApiError(f"YFL API 产品不在页面清单: {code}")
        data = (call.get("response") or {}).get("data")
        if not isinstance(data, dict):
            raise YflApiError(f"YFL API data 缺失 product={code}")
        header = (data.get("header") or {}).get("rightTitle", "")
        match = _REPORT_RE.search(header)
        obs = data.get("years"); benefits = data.get("benefits")
        if not match or not isinstance(obs, list) or not isinstance(benefits, list) or not obs:
            raise YflApiError(f"YFL 年度/观察期/红利结构异常 product={code}")
        year = int(match.group(1)); years.add(year); products.add(product["product_name_raw"])
        for benefit in benefits:
            raw_metric = benefit.get("name"); values = benefit.get("values")
            if not isinstance(raw_metric, str) or not isinstance(values, list) or len(values) != len(obs):
                raise YflApiError(f"YFL 红利值行宽异常 product={code}")
            for label, raw in zip(obs, values):
                if not isinstance(label, str) or not isinstance(raw, str):
                    raise YflApiError(f"YFL 观察期或值不是字符串 product={code}")
                pct = _PCT_RE.fullmatch(raw.strip())
                records.append({
                    "product_name_raw": product["product_name_raw"], "metric_type": _metric(raw_metric),
                    "metric_type_raw": raw_metric, "report_year": year,
                    "observation_year_raw": label, "observation_year": None,
                    "scope_currency_raw": f"{call.get('currency')} | {product.get('product_type_raw','')}",
                    "raw_value": raw, "normalized_value": float(pct.group(1)) / 100 if pct else None,
                    "product_id": None,
                })
    if len(years) != 1 or not records:
        raise YflApiError(f"YFL 报告年度不唯一或零记录: {sorted(years)}")
    return {"status": "OK", "report_year": next(iter(years)), "product_count": len(products),
            "record_count": len(records), "value_unparseable": sum(r["normalized_value"] is None for r in records),
            "records": records}
