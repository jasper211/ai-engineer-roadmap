#!/usr/bin/env python3
"""Build L2 non-linked and L3 linked annual market detail facts, 2022-2024."""
from __future__ import annotations
import hashlib, re, sqlite3
from pathlib import Path
from openpyxl import load_workbook

HERE=Path(__file__).resolve(); HKIA_ROOT=HERE.parents[3]
SRC=HKIA_ROOT/'12_分析框架验证_Validate_Framework/01_sources/raw/SRC-REG-IA-LTA'
DB=HERE.parents[1]/'data/annual_market_fact_layer_2022_2024.db'

def file_for(year, table):
    return next(p for p in (SRC/str(year)/'full_annual_set').glob('Table-L*.xlsx')
                if re.match(rf'Table-L{table}(?:_|-)',p.name))

def sv(v):
    if v is None or (isinstance(v,str) and not v.strip()): return None,'blank'
    if isinstance(v,str):
        if 'N.A' in v.upper() or '不適用' in v: return None,'not_applicable'
        if v.strip()=='-': return 0.0,'reported_zero'
        return None,'unparsed'
    if isinstance(v,(int,float)): return float(v),'reported_zero' if float(v)==0 else 'reported'
    return None,'unparsed'

def add(out,ws,year,table,metric,unit,participation,product,row,col,source,checksum):
    value,status=sv(ws.cell(row,col).value); oy=ws.cell(row-2 if table=='L2' else row-2,col).value
    # Year headers are not uniformly two rows above data, so caller supplies via worksheet lookup later.
    raise AssertionError('use add_with_year')

def emit(out,ws,year,table,metric,unit,participation,product,component,row,col,year_row,source,checksum):
    oy=ws.cell(year_row,col).value
    if not isinstance(oy,int): raise ValueError(f'bad year {source}:{ws.cell(year_row,col).coordinate}={oy!r}')
    value,status=sv(ws.cell(row,col).value); loc=ws.cell(row,col).coordinate
    fid=':'.join(map(str,(table,year,oy,metric,participation,product,component,loc)))
    out.append((fid,year,oy,table,'inforce',metric,unit,'non_linked' if table=='L2' else 'linked',
                participation,product,component,value,status,'certified','rbc' if year>=2024 else 'pre_rbc',
                source.name,source.name,ws.title,loc,checksum))

def parse_l2(year):
    p=file_for(year,2); h=hashlib.sha256(p.read_bytes()).hexdigest(); ws=load_workbook(p,data_only=True).active
    shift=1 if year==2024 else 0; out=[]
    blocks=[('policy_count','count',6+shift,[8+shift,9+shift,10+shift,11+shift],13+shift),
            ('office_or_revenue_premium','HKD_million',17+shift,[20+shift,21+shift,22+shift,23+shift],25+shift),
            ('sums_assured','HKD_million',29+shift,[32+shift,33+shift,34+shift,35+shift],37+shift),
            ('net_liability_or_current_estimate','HKD_million',41+shift,[44+shift,45+shift,46+shift,47+shift],49+shift)]
    products=['whole_life','endowment','term','other']
    for metric,unit,yrrow,drows,totalrow in blocks:
        for participation,startcol in [('participating',4),('other',11)]:
            for row,product in zip(drows,products):
                for col in range(startcol,startcol+5): emit(out,ws,year,'L2',metric,unit,participation,product,'product',row,col,yrrow,p,h)
            for col in range(startcol,startcol+5): emit(out,ws,year,'L2',metric,unit,participation,'all_products','subtotal',totalrow,col,yrrow,p,h)
    return out

def parse_l3(year):
    p=file_for(year,3); h=hashlib.sha256(p.read_bytes()).hexdigest(); ws=load_workbook(p,data_only=True).active
    shift=1 if year==2024 else 0; out=[]
    blocks=[('policy_count','count',6+shift,[8+shift,9+shift,10+shift],12+shift),
            ('office_or_revenue_premium','HKD_million',16+shift,[19+shift,20+shift,21+shift],23+shift),
            ('net_liability_or_current_estimate','HKD_million',27+shift,[30+shift,31+shift,32+shift],34+shift)]
    products=['whole_life','endowment','other']
    for metric,unit,yrrow,drows,totalrow in blocks:
        for row,product in zip(drows,products):
            for col in range(6,11): emit(out,ws,year,'L3',metric,unit,'not_applicable',product,'product',row,col,yrrow,p,h)
        for col in range(6,11): emit(out,ws,year,'L3',metric,unit,'not_applicable','all_products','subtotal',totalrow,col,yrrow,p,h)
    return out

def main():
    rows=[r for y in (2022,2023,2024) for r in (parse_l2(y)+parse_l3(y))]
    con=sqlite3.connect(DB); con.executescript('''
    DROP TABLE IF EXISTS market_detail_facts;
    CREATE TABLE market_detail_facts(
      fact_id TEXT PRIMARY KEY,report_year INTEGER NOT NULL,observation_year INTEGER NOT NULL,
      table_id TEXT NOT NULL,section TEXT NOT NULL,metric_id TEXT NOT NULL,unit TEXT NOT NULL,
      linked_status TEXT NOT NULL,participation_status TEXT NOT NULL,insurance_type TEXT NOT NULL,
      component_type TEXT NOT NULL,value REAL,record_status TEXT NOT NULL,certification TEXT NOT NULL,
      schema_version TEXT NOT NULL,source_asset_id TEXT NOT NULL,source_file TEXT NOT NULL,
      source_sheet TEXT NOT NULL,source_locator TEXT NOT NULL,checksum_sha256 TEXT NOT NULL);
    CREATE INDEX idx_l23_period ON market_detail_facts(observation_year,table_id,metric_id);
    ''')
    con.executemany('INSERT INTO market_detail_facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',rows); con.commit()
    print('rows',len(rows),'by_table',con.execute('select table_id,count(*) from market_detail_facts group by table_id').fetchall(),
          'statuses',con.execute('select record_status,count(*) from market_detail_facts group by record_status').fetchall())
    con.close()
if __name__=='__main__': main()
