#!/usr/bin/env python3
"""T011: Sun Life / BOC Life 静态 HTML 解析确定性测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "06_开发技能_Develop_Skills"))

from skills.multi_html_parser import MultiHtmlParseError, parse_boc_html, parse_sun_html


SUN = b"""<html><body><h1>\xe5\x90\x84\xe4\xba\xa7\xe5\x93\x81\xe7\x9a\x84\xe5\x88\x86\xe7\xba\xa2\xe5\xae\x9e\xe7\x8e\xb0\xe7\x8e\x87</h1>
<div class='data'><p>\xe5\x90\x84\xe4\xba\xa7\xe5\x93\x81\xe7\x9a\x84 2025 \xe6\x8a\xa5\xe5\x91\x8a\xe5\xb9\xb4\xe5\xba\xa6\xe7\x9a\x84\xe5\xbd\x92\xe5\x8e\x9f\xe7\xba\xa2\xe5\x88\xa9\xe4\xb9\x8b\xe5\x88\x86\xe7\xba\xa2\xe5\xae\x9e\xe7\x8e\xb0\xe7\x8e\x87</p><table>
<tr><th>\xe4\xba\xa7\xe5\x93\x81</th><th>\xe4\xba\xa7\xe5\x93\x81\xe7\xa7\x8d\xe7\xb1\xbb</th><th>\xe7\xac\xac 1 \xe4\xb8\xaa\xe4\xbf\x9d\xe5\x8d\x95\xe5\xb9\xb4\xe5\xba\xa6\xef\xbc\x88\xe4\xba\x8e 2024\xe5\xb9\xb4\xe5\xbc\x80\xe5\xa7\x8b\xe7\x94\x9f\xe6\x95\x88\xe4\xb9\x8b\xe4\xbf\x9d\xe5\x8d\x95\xef\xbc\x89</th><th>10+\xef\xbc\x882014\xe5\xb9\xb4\xe6\x88\x96\xe4\xb9\x8b\xe5\x89\x8d\xef\xbc\x89</th></tr>
<tr><td>\xe8\xae\xa1\xe5\x88\x92A</td><td>\xe5\x88\x86\xe7\xba\xa2\xe7\xbb\x88\xe8\xba\xab\xe4\xba\xba\xe5\xaf\xbf</td><td>120%</td><td>\xe4\xb8\x8d\xe9\x80\x82\xe7\x94\xa8</td></tr>
</table></div></body></html>"""

BOC = b"""<html><body><h1>Fulfillment Ratio</h1><div class='panel'>
<div><a class='panel__trigger'>PLAN A</a></div><p class='fulfilment-tabs-tables__table-title'>Fulfillment ratios for annual dividends for reporting year 2025</p>
<figure class='fulfilment-tabs-tables__table--desktop'><table><tr><th rowspan='2'>Product Type</th><th colspan='11'>Policy Year</th></tr>
<tr><td>1(2024)</td><td>2(2023)</td><td>3(2022)</td><td>4(2021)</td><td>5(2020)</td><td>6(2019)</td><td>7(2018)</td><td>8(2017)</td><td>9(2016)</td><td>10(2015)</td><td>10+(Before 2015)</td></tr>
<tr><td>Participating Whole Life</td><td>100%</td><td>N/A</td><td>90%</td><td>91%</td><td>92%</td><td>93%</td><td>94%</td><td>95%</td><td>96%</td><td>97%</td><td>Closed to sales</td></tr>
</table></figure></div></body></html>"""


def must_fail(fn, payload):
    try:
        fn(payload)
    except MultiHtmlParseError:
        return
    raise AssertionError("expected MultiHtmlParseError")


sun = parse_sun_html(SUN)
assert sun["report_year"] == 2025 and sun["record_count"] == 2
assert sun["records"][0]["metric_type"] == "RB"
assert sun["records"][0]["normalized_value"] == 1.2
assert sun["records"][1]["observation_year"] is None
assert sun["value_unparseable"] == 1

boc = parse_boc_html(BOC)
assert boc["report_year"] == 2025 and boc["record_count"] == 11
assert boc["records"][0]["metric_type"] == "AD"
assert boc["records"][0]["normalized_value"] == 1.0
assert boc["records"][-1]["observation_year"] is None
assert boc["records"][0]["scope_currency_raw"] == "Participating Whole Life"

must_fail(parse_sun_html, SUN.replace(b"2025", b"xxxx"))
must_fail(parse_boc_html, BOC.replace(b"<td>10+(Before 2015)</td>", b""))

print("T011 focused tests: PASS (Sun/B0C normal, raw values, open interval, drift failures)")
