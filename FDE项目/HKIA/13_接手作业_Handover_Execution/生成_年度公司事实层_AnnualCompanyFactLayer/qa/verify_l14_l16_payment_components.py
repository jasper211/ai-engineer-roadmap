#!/usr/bin/env python3
import sqlite3
from pathlib import Path
DB=Path(__file__).resolve().parents[1]/'data/annual_company_fact_layer_2022_2024.db'
con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
checks=[]
n=con.execute('select count(*) n from company_payment_facts').fetchone()['n']; checks.append(('component_rows_positive',n>0,n))
u=con.execute("select count(*) n from company_payment_facts where record_status='unparsed'").fetchone()['n']; checks.append(('no_unparsed',u==0,u))
# L14 + L15 = L16 at the same insurer/payment/metric grain. Missing company rows are treated as absent, not zero.
rows=con.execute('''select a.report_year,a.insurer_name_source,a.metric_id,a.payment_basis,a.value av,b.value bv,c.value cv
 from company_payment_facts a join company_payment_facts b using(report_year,insurer_name_source,metric_id,payment_basis,entity_scope)
 join company_payment_facts c using(report_year,insurer_name_source,metric_id,payment_basis,entity_scope)
 where a.table_id='L14' and b.table_id='L15' and c.table_id='L16' and a.value is not null and b.value is not null and c.value is not null''').fetchall()
bad=[r for r in rows if abs(r['av']+r['bv']-r['cv'])>0.001]; checks.append(('L14_plus_L15_equals_L16',not bad,f'checked={len(rows)} bad={len(bad)}'))
markets=con.execute("select count(*) n from company_payment_facts where entity_scope='market_total'").fetchone()['n']; checks.append(('market_controls_retained',markets==36,markets))
for name,ok,detail in checks: print(('PASS' if ok else 'FAIL'),name,detail)
if any(not x[1] for x in checks): raise SystemExit(1)
