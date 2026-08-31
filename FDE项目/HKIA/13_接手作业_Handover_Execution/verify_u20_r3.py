"""Read-only r3: independently reconcile supplied bridge rows to SQLite sources."""
import ast
import csv
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

B = Path(__file__).resolve().parent
BR = B / '生成_跨年度同口径桥_CrossYearBridge'
base = json.loads(subprocess.run([sys.executable, str(B/'verify_u20_call.py')], capture_output=True, text=True, check=True).stdout)
out = {'baseline': base, 'checks': {}, 'evidence': {}}
checks, ev = out['checks'], out['evidence']
def read_csv(name):
    with (BR/'bridge'/name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
matched = read_csv('可比公司映射_2024L16_2025L1.csv')
excluded = read_csv('排除清单_2024_2025.csv')
claimed = json.loads((BR/'bridge/桥覆盖率与差异.json').read_text())
c = sqlite3.connect(':memory:', uri=True)
for alias, layer in [('ann','annual'),('prov25','provisional'),('std','standard')]:
    c.execute(f'ATTACH DATABASE ? AS {alias}', (Path(base['connections'][layer]['path']).as_uri()+'?mode=ro',))
c.execute('PRAGMA query_only=ON')
guide = (B/'U20调用指引_v1.md').read_text()
blocks = re.findall(r'```python\n(.*?)```', guide, re.S)
# Test the current ATTACH call nodes, not text in warnings/history. Do not execute arbitrary code.
env = {'annual_path': Path(base['connections']['annual']['path']), 'provisional_path': Path(base['connections']['provisional']['path'])}
attach = sqlite3.connect(':memory:', uri=True)
attach_results = []
for block in blocks:
    for node in ast.walk(ast.parse(block)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != 'execute' or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value,str) and first.value.startswith('ATTACH DATABASE'):
            # Only accept known, read-only templates before evaluating the path expression.
            expected = "ATTACH DATABASE ? AS ann" if ' AS ann' in first.value else "ATTACH DATABASE ? AS prov25"
            alias = 'ann' if expected.endswith(' ann') else 'prov25'
            key = 'annual_path' if alias == 'ann' else 'provisional_path'
            expression = ast.unparse(node.args[1])
            if first.value != expected or expression != f"({key}.resolve().as_uri() + '?mode=ro',)":
                raise ValueError('Unexpected ATTACH expression: '+expression)
            attach.execute(first.value, (env[key].resolve().as_uri()+'?mode=ro',))
            attach_results.append(alias)
checks['current_guide_readonly_attach'] = sorted(attach_results) == ['ann','prov25'] and attach.execute('SELECT count(*) FROM ann.company_facts').fetchone()[0] == 7097 and attach.execute('SELECT count(*) FROM prov25.provisional_company_facts').fetchone()[0] == 414
attach.close()
rows24 = c.execute("SELECT insurer_name_source,value_raw FROM ann.company_facts WHERE report_year=2024 AND table_id='L16' AND metric_sem='premium_single' AND entity_scope='insurer'").fetchall()
rows25 = c.execute("SELECT insurer_name_en,value FROM prov25.provisional_company_facts WHERE year=2025 AND metric_sem='nb_total_single_premium' AND entity_scope='insurer'").fetchall()
d24,d25 = dict(rows24),dict(rows25)
checks['source_names_unique'] = len(d24)==len(rows24) and len(d25)==len(rows25)
def close(a,b):
    return a is not None and b is not None and math.isclose(float(a),float(b),rel_tol=0,abs_tol=0.00001)
errors=[]
for i,r in enumerate(matched,2):
    for year,d,nk,vk in [(2024,d24,'company_2024_name','premium_2024_hkd_thousand'),(2025,d25,'company_2025_name','premium_2025_L1_total_hkd_thousand')]:
        name=r[nk]
        if name not in d or not close(d.get(name),r[vk]):
            errors.append({'csv_row':i,'year':year,'name':name,'csv_value':r[vk],'db_value':d.get(name),'issue':'missing_name' if name not in d else 'value_mismatch'})
ev['matched_errors']=errors
checks['matched_rows_equal_both_source_layers']=not errors
checks['matched_names_unique']=all(len({r[k] for r in matched})==len(matched) for k in ['company_2024_name','company_2025_name'])
checks['excluded_names_unique']=len({r['company'] for r in excluded})==len(excluded)
ex_errors=[]
missing=[]
for i,r in enumerate(excluded,2):
    for year,d in [(2024,d24),(2025,d25)]:
        name=r['company']
        if name not in d:
            missing.append({'csv_row':i,'year':year,'name':name,'encoded_value':r[f'premium_{year}'],'reason':r['exclusion_reason']})
        elif not close(d[name],r[f'premium_{year}']):
            ex_errors.append({'csv_row':i,'year':year,'name':name,'db_value':d[name],'csv_value':r[f'premium_{year}']})
ev['excluded_value_errors']=ex_errors
ev['missing_source_rows_encoded_as_values']=missing
checks['excluded_existing_values_match']=not ex_errors
checks['missing_rows_distinguished_from_zero']=not missing
totals={}
for year,d in [(2024,d24),(2025,d25)]:
    key = 'premium_2024_hkd_thousand' if year==2024 else 'premium_2025_L1_total_hkd_thousand'
    names=[r[f'company_{year}_name'] for r in matched]+[r['company'] for r in excluded]
    ev[f'uncovered_source_names_{year}']=sorted(set(d)-set(names))
    checks[f'all_source_names_covered_{year}']=set(d)<=set(names)
    checks[f'matched_excluded_disjoint_{year}']=not (set(r[f'company_{year}_name'] for r in matched)&set(r['company'] for r in excluded))
    mt=c.execute("SELECT value_raw FROM ann.company_facts WHERE report_year=2024 AND table_id='L16' AND metric_sem='premium_single' AND entity_scope='market_total'").fetchone()[0] if year==2024 else c.execute("SELECT value FROM prov25.provisional_company_facts WHERE year=2025 AND metric_sem='nb_total_single_premium' AND entity_scope='market_total'").fetchone()[0]
    sm=math.fsum(float(r[key]) for r in matched)
    se=math.fsum(float(r[f'premium_{year}']) for r in excluded)
    totals[year]={'market':mt,'matched':sm,'excluded':se,'gap':mt-sm-se,'matched_amount_coverage_percent':sm/mt*100,'source_company_count':len(d)}
    checks[f'amount_reconciliation_{year}']=close(mt,sm+se)
checks['reported_2024_coverage_matches']=round(totals[2024]['matched_amount_coverage_percent'],2)==claimed['coverage_2024_percent']
checks['reported_matched_count']=len(matched)==claimed['matched_companies']
ev['totals_hkd_thousand']=totals
ev['matched_count']=len(matched)
ev['excluded_count']=len(excluded)
ev['positive_excluded_2024']=[r for r in excluded if float(r['premium_2024'])>0]
ev['axa_identity_reference']=c.execute("SELECT DISTINCT source_abbrev,entity_key,business_lineage,bridge_class FROM std.company_facts WHERE source_abbrev LIKE '%AXA%'").fetchall()
ev['axa_actual_2025_values']={k:v for k,v in d25.items() if 'AXA' in k}
checks['bridge_has_entity_lineage_provenance_fields']=all(k in matched[0] for k in ['entity_key','business_lineage','bridge_class','source_reference'])
ev['guide_unresolved_select_placeholders']=[line for b in blocks for line in b.splitlines() if 'SELECT ...' in line]
checks['guide_query_examples_no_placeholders']=not ev['guide_unresolved_select_placeholders']
checks['guide_retracts_same_scope_release']='待验证的异口径试算' in guide and '撤回「同口径增长可发布」' in guide
subset=(BR/'方案2子集_分红相连口径_v1.md').read_text()
checks['subset_document_no_conflicting_release_statement']='市场级可用 `+65.4%`' not in subset and '初步同口径参考' not in subset
ev['review_boundary']='Same-scope equivalence remains explicitly unaccepted in the submitted documents; no new product definition proof or source workbook subcomponent recalculation was supplied in this bridge directory.'
out['input_sha256']={str(p.relative_to(B)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [B/'U20调用指引_v1.md',*sorted((BR/'bridge').glob('*'))] if p.is_file()}
c.close()
out['status']='PASS' if all(checks.values()) else 'PARTIAL'
p=B/'U20调用验证结果_20260831_r3.json'
p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'output':str(p),'baseline_checks':len(base['checks']),'checks':checks,'evidence':ev},ensure_ascii=False,indent=2))
sys.exit(0 if all(checks.values()) else 1)
