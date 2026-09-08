#!/usr/bin/env python3
"""T014 保诚标准履行率 HTML 聚焦测试。"""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'06_开发技能_Develop_Skills'))
from skills.pru_html_parser import parse_pru_html, PruHtmlParseError

PAGE='''<html><meta charset="utf-8"><body>
<h4>測試計劃 - 分期繳費 產品類別 : 分紅保險計劃</h4>
<h5>2025 報告年度的歸原紅利現金價值分紅實現率</h5>
<table><tr><th rowspan="2">貨幣</th><th colspan="2">保單生效年期</th></tr>
<tr><th>1 (2024)</th><th>10+ (2015 之前)</th></tr>
<tr><th>美元</th><td>101%</td><td>尚未推出</td></tr></table>
</body></html>'''.encode()
x=parse_pru_html(PAGE)
assert (x['report_year'],x['product_count'],x['record_count'],x['value_unparseable'])==(2025,1,2,1)
assert x['records'][0]['metric_type']=='RB' and x['records'][0]['normalized_value']==1.01
assert x['records'][0]['observation_year']==2024
assert x['records'][1]['observation_year'] is None and x['records'][1]['raw_value']=='尚未推出'
assert x['records'][0]['product_name_raw']=='測試計劃 - 分期繳費'

for bad in (b'<html></html>', PAGE.replace(b'<td>101%</td><td>',b'<td>')):
    try: parse_pru_html(bad)
    except PruHtmlParseError: pass
    else: raise AssertionError('structure drift must fail')
print('T014 PRU focused tests: PASS (mapping, raw placeholders, year semantics, drift)')
