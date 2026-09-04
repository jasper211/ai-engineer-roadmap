#!/usr/bin/env python3
"""T013 AXA/FWD Next.js 目录、证据包与离线解析聚焦测试。"""
import json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'06_开发技能_Develop_Skills'))
sys.path.insert(0,str(ROOT/'05_集成工具_Integrate_Tools'))
from skills.nextjs_ratio import collect, parse_bundle, NextRatioError

def page(data):
    return ("<html><head><meta charset='utf-8'></head><script id='__NEXT_DATA__' type='application/json'>"+
            json.dumps(data,ensure_ascii=False)+"</script></html>").encode()

class Result:
    fetch_status='OK'; http_status=200; error_code=None; note=''
    def __init__(self,url,body): self.final_url=url; self.body=body

axa_index={'props':{'pageProps':{'sliceZone':{'slices':[{}, {}, {}, {}, {'value':{'items':[
    {'target':{'href':'/en/fulfilment-ratios-total-value-ratios-plan-a'}}]}}]}}}}
def cell(content,index,**kw): return {'content':f'<p>{content}</p>','actualColIndex':index,**kw}
axa_product={'props':{'pageProps':{'title':'Plan A | AXA','sliceZone':{'includes':{
 'tab-fulfilment-ratios-plan-a':[{'type':'DataTable','value':{'data':[
   [[cell('',0,startNew='Section'),cell('Policy Year 1 (2024)',1),cell('Policy Year 2 (2023)',2)]],
   [[cell('HKD Policy Currency – Annual Dividend',0,startNew='Section'),cell('101%',1),cell('Not Applicable (d)',2)]]
 ]}}]}}}}}

axa_pages={'https://axa.test/index':page(axa_index),'https://axa.test/en/fulfilment-ratios-total-value-ratios-plan-a':page(axa_product)}
out=collect('https://axa.test/index','AXA',lambda u:Result(u,axa_pages[u]),workers=2)
assert out.fetch_status=='OK' and b'__NEXT_DATA__' not in out.body
x=parse_bundle(out.body)
assert (x['report_year'],x['product_count'],x['record_count'],x['value_unparseable'])==(2025,1,2,1)
assert x['records'][0]['metric_type']=='AD' and x['records'][0]['normalized_value']==1.01

fwd_path='/regulatory-disclosures/fulfillment-ratios/plan-b/'
fwd_index={'props':{'pageProps':{'data':{'data':{'layout':[{'dataComponent':{'body':[{}, {}, {},
 {'table_content_section':{'table':[{'sections':[{'rows':[{'columns':[{'content':f'<a href="{fwd_path}">B</a>'}]}]}]}]}}]}}]}}}}}
headers=[{'content':'<p>非保證類別</p>'},{'content':'<p>保單貨幣</p>'},{'content':'<p>保單年度1 (2024年發出的保單)</p>'}]
fwd_product={'props':{'pageProps':{'data':{'data':{'layout':[{'dataComponent':{'body':[{}, {}, {},
 {'table_content_section':{'description':'<h4>計劃 B</h4><h5>2025年度分紅實現率</h5>','table':[{
 'headers':headers,'sections':[{'rows':[{'columns':[{'content':'<p>特別紅利</p>'},{'content':'<p>港幣</p>'},{'content':'<p>88%</p>'}]}]}]}]}}]}}]}}}}}
fwd_pages={'https://fwd.test/index':page(fwd_index),'https://fwd.test'+fwd_path:page(fwd_product)}
out=collect('https://fwd.test/index','FWD',lambda u:Result(u,fwd_pages[u]),workers=2)
x=parse_bundle(out.body)
assert x['report_year']==2025 and x['record_count']==1 and x['records'][0]['metric_type']=='TB'
assert x['records'][0]['observation_year']==2024 and x['records'][0]['normalized_value']==.88

bad=json.loads(out.body); bad['pages'][0]['path']='/regulatory-disclosures/fulfillment-ratios/tampered/'
try: parse_bundle(json.dumps(bad).encode())
except NextRatioError: pass
else: raise AssertionError('index/page evidence mismatch must fail')
print('T013 focused tests: PASS (AXA/FWD discovery, bundle, parse, mapping, drift)')
