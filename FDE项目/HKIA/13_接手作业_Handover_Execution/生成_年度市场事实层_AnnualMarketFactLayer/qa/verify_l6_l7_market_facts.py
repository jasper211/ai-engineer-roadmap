#!/usr/bin/env python3
"""QA for L6-L7 market facts with explicit pre-RBC/RBC schema checks."""
import sqlite3
from pathlib import Path

HERE=Path(__file__).resolve(); DB=HERE.parents[1]/'data/annual_market_fact_layer_2022_2024.db'; REPORT=HERE.parent/'l6_l7_market_fact_layer_qa_report.md'

def main():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row; checks=[]
    for table,expected in [('group_retirement_facts',452),('annuity_other_facts',324)]:
        n=con.execute(f'select count(*) n from {table}').fetchone()['n']; checks.append((f'{table}行数',n==expected,f'{n}/{expected}'))
        u=con.execute(f"select count(*) n from {table} where record_status='unparsed'").fetchone()['n']; checks.append((f'{table}无未解析值',u==0,f'异常={u}'))
        y=con.execute(f'select count(*) n from {table} where observation_year is null or observation_year>report_year').fetchone()['n']; checks.append((f'{table}观察期有效',y==0,f'异常={y}'))

    # Generic component-to-total checks. Compare only where at least one component is published.
    specs=[
      ("L6团体有效业务类别合计",'''select report_year,observation_year,metric_id,sum(case when component_type='class' then coalesce(value,0) end) s,sum(case when component_type='class' and value is not null then 1 else 0 end) n,max(case when component_type='total' then value end) t from group_retirement_facts where section='group_inforce' group by 1,2,3'''),
      ("L6退休计划类别合计",'''select report_year,observation_year,metric_id,payment_basis,sum(case when component_type='class' then coalesce(value,0) end) s,sum(case when component_type='class' and value is not null then 1 else 0 end) n,max(case when component_type='total' then value end) t from group_retirement_facts where section='retirement_inforce' group by 1,2,3,4'''),
      ("L6团体新造分部合计",'''select report_year,observation_year,metric_id,payment_basis,sum(case when component_type='segment' then coalesce(value,0) end) s,sum(case when component_type='segment' and value is not null then 1 else 0 end) n,max(case when component_type='total' then value end) t from group_retirement_facts where section='group_new_business' group by 1,2,3,4'''),
      ("L7年金新造缴费方式合计",'''select report_year,observation_year,metric_id,linked_status,sum(case when component_type='payment_basis' then coalesce(value,0) end) s,sum(case when component_type='payment_basis' and value is not null then 1 else 0 end) n,max(case when component_type='subtotal' then value end) t from annuity_other_facts where section='individual_annuity_new_business' group by 1,2,3,4''')]
    for name,sql in specs:
        rows=con.execute(sql).fetchall(); comparable=[r for r in rows if r['n'] and r['t'] is not None]
        bad=[r for r in comparable if abs(r['s']-r['t'])>(0 if 'count' in str(tuple(r)) else .21)]
        checks.append((name,not bad,f'可比={len(comparable)}，异常={len(bad)}'))

    # L7 individual annuity subtotal = linked + non-linked + group annuity.
    rows=con.execute('''select report_year,observation_year,metric_id,
      sum(case when insurance_type in ('individual_annuity_non_linked','individual_annuity_linked','group_annuity') then coalesce(value,0) end) s,
      max(case when insurance_type='individual_annuity_total' then value end) t
      from annuity_other_facts where section='annuity_other_inforce' group by 1,2,3''').fetchall()
    bad=[r for r in rows if r['t'] is None or abs(r['s']-r['t'])>(0 if r['metric_id']=='policy_count' else .21)]
    checks.append(('L7个人/团体年金→年金小计',not bad,f'检查={len(rows)}，异常={len(bad)}'))

    # Explicit structural assertions for the RBC break.
    newbiz=con.execute("select count(*) n from group_retirement_facts where report_year=2024 and section='group_new_business'").fetchone()['n']
    scheme=con.execute("select count(*) n from group_retirement_facts where report_year=2024 and metric_id='scheme_count'").fetchone()['n']
    old_newbiz=con.execute("select count(*) n from group_retirement_facts where report_year<2024 and section='group_new_business'").fetchone()['n']
    checks.append(('2024 RBC新增指标被隔离保存',newbiz==63 and scheme==12 and old_newbiz==0,f'团体新造={newbiz}，计划数={scheme}，旧口径误植={old_newbiz}'))
    failed=sum(not ok for _,ok,_ in checks)
    lines=['# L6–L7年度市场事实层QA报告','',f"结论：**{'PASS' if failed==0 else 'FAIL'}**。共同指标可跨期使用；2024新增或停止披露的维度必须通过`schema_version`与`record_status`识别。",'', '## Checklist','']
    lines += [f"- [{'x' if ok else ' '}] {name}：{detail}" for name,ok,detail in checks]
    lines += ['', '## 分析使用边界','', '- L6的2024团体有效业务只发布`group_life_total`，不可伪造A/C/I类别拆分。','- L6的团体新造业务与退休计划`scheme_count`仅属于2024 RBC口径，不可向前补零。','- L7在2024将部分相连、团体年金及其他险种标为N.A.；N.A.代表不可用，不等于零。','- `net_liabilities`与`current estimate`通过统一指标承接，但必须保留`schema_version`供报告披露口径。','']
    REPORT.write_text('\n'.join(lines),encoding='utf-8'); print('checks',len(checks),'failed',failed)
    if failed: raise SystemExit(1)
if __name__=='__main__': main()
