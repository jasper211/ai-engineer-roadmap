#!/usr/bin/env python3
"""T012 YF Life API 证据包与离线解析测试。"""
import json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'06_开发技能_Develop_Skills'))
sys.path.insert(0,str(ROOT/'05_集成工具_Integrate_Tools'))
from skills.yfl_api import collect, parse_bundle, YflApiError

PAGE='''<html><div id="container1"><div class="fulfillment_ratio" product-code="P1"><div class="ful_second_title">Ratio</div><div class="ful_second_title">Plan One</div><div class="ful_second_content">Product type: participating</div></div><div class="fulfillment_ratio" product-code="P2"><div class="ful_second_title">Ratio</div><div class="ful_second_title">Plan Two</div></div></div></html>'''.encode()
class PageResult:
 fetch_status='OK'; http_status=200; final_url='https://www.yflife.com/page'; error_code=None; note=''; body=PAGE
def page_fetch(url): return PageResult()
def post(path,payload):
 if path.endswith('/currency'):
  data=None if payload['productCode']=='P2' else [{'currency':'ALL','value':'ALL'}]
  return 200,json.dumps({'code':200,'data':data}).encode()
 return 200,json.dumps({'code':200,'data':{'header':{'rightTitle':'Fulfillment Ratio for reporting year 2025'},'years':['Policy Year 1','Policy Year 10 afterwards'],'benefits':[{'name':'Annual Dividend','values':['120%','N/A'],'sups':[None,None]}]}}).encode()

out=collect('https://www.yflife.com/page',page_fetch,post)
assert out.fetch_status=='OK'
x=parse_bundle(out.body)
assert x['report_year']==2025 and x['product_count']==1 and x['record_count']==2
assert x['records'][0]['metric_type']=='AD' and x['records'][0]['normalized_value']==1.2
assert x['records'][1]['normalized_value'] is None and x['value_unparseable']==1
try: parse_bundle(out.body.replace(b'"schema_version":1',b'"schema_version":2'))
except YflApiError: pass
else: raise AssertionError('schema drift must fail')
assert b'cookie' not in out.body.lower() and b'authorization' not in out.body.lower()
print('T012 focused tests: PASS (discovery, no-data product, bundle, mapping, drift)')
