#!/usr/bin/env python3
import sqlite3
from pathlib import Path
DB=Path(__file__).resolve().parents[1]/'data/annual_market_fact_layer_2022_2024.db'

def main():
 c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True); checks={}
 checks['rows_780']=c.execute('select count(*) from market_detail_facts').fetchone()[0]==780
 checks['table_counts']=c.execute('select table_id,count(*) from market_detail_facts group by table_id').fetchall()==[('L2',600),('L3',180)]
 checks['no_unparsed']=c.execute("select count(*) from market_detail_facts where record_status='unparsed'").fetchone()[0]==0
 checks['unique_ids']=c.execute('select count(*)=count(distinct fact_id) from market_detail_facts').fetchone()[0]==1
 # L2 participating + other subtotal reconciles to L1 non-linked subtotal/base.
 diffs=[]
 for y,oy,metric,p,o in c.execute('''select report_year,observation_year,metric_id,
   sum(case when participation_status='participating' then value end),
   sum(case when participation_status='other' then value end)
   from market_detail_facts where table_id='L2' and component_type='subtotal'
   group by report_year,observation_year,metric_id'''):
  if p is None or o is None: continue
  if metric=='net_liability_or_current_estimate':
   l1=c.execute('''select sum(value) from market_amount_facts where report_year=? and observation_year=?
      and metric_id=? and linked_status='non_linked' and component_type='product' ''',(y,oy,metric)).fetchone()[0]
  else:
   l1=c.execute('''select value from market_amount_facts where report_year=? and observation_year=?
      and metric_id=? and linked_status='non_linked' and component_type='subtotal' ''',(y,oy,metric)).fetchone()[0]
  if l1 is not None: diffs.append(abs(p+o-l1))
 # Historical market tables display HKD million to one decimal; component sums
 # therefore allow the declared 0.1m presentation-rounding boundary.
 checks['l2_to_l1_reconcile']=len(diffs)==60 and max(diffs)<=0.100001
 # L3 subtotal reconciles to L1 linked subtotal/base for its three metrics.
 diffs=[]
 for y,oy,metric,v in c.execute('''select report_year,observation_year,metric_id,value from market_detail_facts
   where table_id='L3' and component_type='subtotal' and value is not null'''):
  comp='base' if metric=='net_liability_or_current_estimate' else 'subtotal'
  l1=c.execute('''select value from market_amount_facts where report_year=? and observation_year=?
    and metric_id=? and linked_status='linked' and component_type=?''',(y,oy,metric,comp)).fetchone()
  if l1 and l1[0] is not None: diffs.append(abs(v-l1[0]))
 checks['l3_to_l1_reconcile']=len(diffs)==45 and max(diffs)<=0.100001
 c.close()
 for n,ok in checks.items(): print(('PASS' if ok else 'FAIL'),n)
 print(f'RESULT: {sum(checks.values())}/{len(checks)}'); return 0 if all(checks.values()) else 1
if __name__=='__main__': raise SystemExit(main())
