"""Independent read-only acceptance of r3fix v2 CSV/JSON and guide SQL."""
import ast
import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

B = Path(__file__).resolve().parent
BR = B/'生成_跨年度同口径桥_CrossYearBridge'
baseline = json.loads(subprocess.run([sys.executable,str(B/'verify_u20_call.py')],capture_output=True,text=True,check=True).stdout)
db = {}
for key in ('annual','provisional','standard'):
    db[key] = sqlite3.connect(Path(baseline['connections'][key]['path']).as_uri()+'?mode=ro',uri=True)
    db[key].execute('PRAGMA query_only=ON')
def read_csv(name):
    with (BR/'bridge'/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))
matched=read_csv('可比公司映射_2024L16_2025L1_v2.csv')
excluded=read_csv('排除清单_2024_2025_v2.csv')
claimed=json.loads((BR/'bridge/桥覆盖率与差异_v2.json').read_text())
sql24="SELECT insurer_name_source,value_raw FROM company_facts WHERE report_year=2024 AND table_id='L16' AND metric_sem='premium_single' AND entity_scope='insurer'"
sql25="SELECT insurer_name_en,value FROM provisional_company_facts WHERE year=2025 AND metric_sem='nb_total_single_premium' AND entity_scope='insurer'"
sources={2024:dict(db['annual'].execute(sql24)),2025:dict(db['provisional'].execute(sql25))}
identity=defaultdict(set)
for name,key in db['standard'].execute('SELECT DISTINCT source_abbrev,entity_key FROM company_facts'):
    identity[name].add(key)
checks={}
ev={'row_errors':[],'identity_errors':[],'totals':{},'status_counts':{}}
checks['counts_match_manifest']=len(matched)==claimed['matched_count']==22 and len(excluded)==claimed['excluded_count']==46
def near(a,b):
    return math.isclose(a,b,rel_tol=0,abs_tol=0.00001)
for group,rows in [('matched',matched),('excluded',excluded)]:
    for i,r in enumerate(rows,2):
        for year,d in sources.items():
            name=r[f'source_{year}']; raw=r[f'premium_{year}_hkd_thousand']; status=r[f'record_status_{year}']
            if status=='missing':
                ok=not name and raw==''
            else:
                value=d.get(name)
                ok=value is not None and raw!='' and near(value,float(raw)) and status==('reported_zero' if value==0 else 'reported_value')
            if not ok:
                ev['row_errors'].append(dict(group=group,csv_row=i,year=year,name=name,status=status,value=raw,db_value=d.get(name)))
        names=[r[f'source_{y}'] for y in (2024,2025) if r[f'source_{y}']]
        expected=set.intersection(*(identity[n] for n in names)) if names else set()
        if r['entity_key'] not in expected:
            ev['identity_errors'].append(dict(group=group,csv_row=i,names=names,csv_key=r['entity_key'],standard_keys={n:sorted(identity[n]) for n in names},claimed_evidence=r.get('evidence')))
checks['all_values_and_record_status_match']=not ev['row_errors']
checks['matched_entity_keys_match_standard']=not any(e['group']=='matched' for e in ev['identity_errors'])
checks['excluded_entity_keys_match_standard']=not any(e['group']=='excluded' for e in ev['identity_errors'])
checks['axa_two_bridges_verified']=all(r['entity_key'] in identity[r['source_2024']] & identity[r['source_2025']] for r in matched+excluded if r['source_2024'] in ('AXA China (Bermuda)','AXA China (HK)')) and sum(r['source_2024'] in ('AXA China (Bermuda)','AXA China (HK)') for r in matched+excluded)==2
for year,d in sources.items():
    allrows=matched+excluded
    names=[r[f'source_{year}'] for r in allrows if r[f'source_{year}']]
    checks[f'unique_complete_source_names_{year}']=len(names)==len(set(names)) and set(names)==set(d)
    ev['status_counts'][year]={g:dict(Counter(r[f'record_status_{year}'] for r in rows)) for g,rows in [('matched',matched),('excluded',excluded)]}
    sm=math.fsum(float(r[f'premium_{year}_hkd_thousand']) for r in matched)
    se=math.fsum(float(r[f'premium_{year}_hkd_thousand']) for r in excluded if r[f'premium_{year}_hkd_thousand']!='')
    mt=db['annual'].execute(sql24.replace('insurer_name_source,value_raw','value_raw').replace("entity_scope='insurer'","entity_scope='market_total'")).fetchone()[0] if year==2024 else db['provisional'].execute(sql25.replace('insurer_name_en,value','value').replace("entity_scope='insurer'","entity_scope='market_total'")).fetchone()[0]
    coverage=sm/mt*100
    ev['totals'][year]=dict(market=mt,matched=sm,excluded=se,gap=mt-sm-se,coverage_pct=coverage)
    checks[f'amount_reconciles_{year}']=near(mt,sm+se)
    checks[f'coverage_matches_claim_{year}']=abs(coverage-claimed[f'coverage_{year}_pct'])<0.0001
    checks[f'gap_matches_claim_{year}']=near(mt-sm-se,claimed[f'reconciliation_{year}_close_diff'])
guide=(B/'U20调用指引_v1.md').read_text()
blocks=re.findall(r'```python\n(.*?)```',guide,re.S)
attached=sqlite3.connect(':memory:',uri=True)
for alias,layer in [('ann','annual'),('prov25','provisional')]:
    attached.execute(f'ATTACH DATABASE ? AS {alias}',(Path(baseline['connections'][layer]['path']).as_uri()+'?mode=ro',))
attached.execute('PRAGMA query_only=ON')
ev['guide_sql_results']=[]
for idx,block in enumerate(blocks):
    for node in ast.walk(ast.parse(block)):
        if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute) or node.func.attr!='execute' or not node.args or not isinstance(node.args[0],ast.Constant):
            continue
        sql=node.args[0].value
        if not isinstance(sql,str) or not sql.strip().upper().startswith('SELECT'):continue
        owner=node.func.value.id
        connection={'ann':db['annual'],'prov':db['provisional'],'conn':attached}[owner]
        try:
            rows=connection.execute(sql).fetchall()
            expected=sources[2025 if 'provisional_company_facts' in sql else 2024]
            ev['guide_sql_results'].append(dict(block=idx+1,owner=owner,sql=sql,count=len(rows),correct=dict(rows)==expected and len(rows)==len(expected)))
        except sqlite3.Error as e:
            ev['guide_sql_results'].append(dict(block=idx+1,sql=sql,error=str(e),correct=False))
checks['guide_four_selects_execute_correctly']=len(ev['guide_sql_results'])==4 and all(r['correct'] for r in ev['guide_sql_results'])
checks['guide_uses_readonly_uri']=all('?mode=ro' in b for b in blocks) and 'ATTACH DATABASE ? AS ann' in guide and 'ATTACH DATABASE ? AS prov25' in guide
ev['guide_configuration_note']='ROOT still uses /Users/... placeholder; SQL was executed against actual read-only paths, no arbitrary document Python executed.'
subset=(BR/'方案2子集_分红相连口径_v1.md').read_text()
checks['subset_conflict_removed']='市场级可用 `+65.4%`' not in subset and '初步同口径参考' not in subset and '均不得作为同口径增长率发布' in subset
record=(B/'U20桥修复验证记录_r3fix_v1.md').read_text()
checks['same_scope_release_remains_blocked']='仍未验收、不得发布' in record and '非同口径可比覆盖率' in claimed['caveat']
ev['boundary']='Source name/value/status validation is not a product scope bridge or certification of natural growth. Missing names cannot independently prove the real-world identity of absent entities.'
for c in db.values():c.close()
attached.close()
files=[B/'U20桥修复验证记录_r3fix_v1.md',B/'U20调用指引_v1.md',BR/'方案2子集_分红相连口径_v1.md',*sorted((BR/'bridge').glob('*_v2.*'))]
out=dict(baseline=baseline,checks=checks,evidence=ev,input_sha256={str(p.relative_to(B)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},status='PASS' if all(checks.values()) else 'PARTIAL')
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=B/'U20桥修复独立验证_r3fix_result.json')
args=parser.parse_args()
args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(baseline_passed=sum(baseline['checks'].values()),checks=checks,evidence=ev),ensure_ascii=False,indent=2))
sys.exit(0 if all(checks.values()) else 1)
