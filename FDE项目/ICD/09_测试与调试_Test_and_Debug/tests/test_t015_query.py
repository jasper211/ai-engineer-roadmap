#!/usr/bin/env python3
"""T015 只读查询适配器定向测试。"""

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ICD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ICD / "05_集成工具_Integrate_Tools"))
from tools import icd_query, sqlite_store  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed(path):
    conn = sqlite3.connect(path)
    conn.executescript(sqlite_store.SCHEMA_SQL)
    conn.execute("INSERT INTO insurer(insurer_code,name_en) VALUES('TST','Test Life')")
    conn.execute("""INSERT INTO data_source(source_id,insurer_code,disclosure_type,entry_url,format,access_status,evidence_basis)
                    VALUES(1,'TST','fulfillment_ratio','https://official.test/ratio','json','OPEN','fixture'),
                          (2,'TST','rbc','https://official.test/rbc.pdf','pdf','OPEN','fixture')""")
    for run, source, stamp, digest in [(1,1,'2025-01-01T00:00:00Z','a'*64),(2,1,'2026-01-01T00:00:00Z','b'*64),(3,2,'2026-02-01T00:00:00Z','c'*64)]:
        conn.execute("""INSERT INTO fetch_run(run_id,source_id,fetched_at,final_url,http_status,content_hash,content_length,snapshot_path,fetch_status)
                        VALUES(?,?,?,?,200,?,10,?,'OK')""", (run,source,stamp,f'https://official.test/{run}',digest,f'raw/{run}'))
    base = ('TST',None,'Official Product','AD','Annual Dividend',2025,'2024',2024,'ALL')
    conn.execute("""INSERT INTO fulfillment_ratio(insurer_code,product_id,product_name_raw,metric_type,metric_type_raw,report_year,observation_year_raw,observation_year,scope_currency_raw,raw_value,normalized_value,unit,run_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", base+('90%',.9,'percent',1))
    conn.execute("""INSERT INTO fulfillment_ratio(insurer_code,product_id,product_name_raw,metric_type,metric_type_raw,report_year,observation_year_raw,observation_year,scope_currency_raw,raw_value,normalized_value,unit,run_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", base+('N/A',None,'percent',2))
    conn.execute("""INSERT INTO rbc_statement(insurer_code,run_id,report_year,solvency_ratio,solvency_ratio_raw,legal_entity_name_raw)
                    VALUES('TST',3,2025,3.04,'304%','Test Life Limited')""")
    conn.execute("""INSERT INTO coverage_status(insurer_code,disclosure_type,coverage_status,last_success_run_id)
                    VALUES('TST','fulfillment_ratio','FULL',2)""")
    conn.commit(); conn.close()


def main():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / 'icd.db'; seed(db); before = sha(db)
        with icd_query.ICDClient.open_readonly(db) as c:
            latest = c.fulfillment(insurer_code='TST')
            assert latest['count'] == 1 and latest['data'][0]['run_id'] == 2
            assert latest['data'][0]['raw_value'] == 'N/A' and latest['data'][0]['normalized_value'] is None
            assert latest['data'][0]['sha256'] == 'b'*64 and latest['data'][0]['source_url'].startswith('https://official.test')
            history = c.fulfillment(insurer_code='TST', product_name='Official', metric_type='AD', report_year=2025, include_history=True)
            assert [r['run_id'] for r in history['data']] == [2, 1]
            rr = c.rbc(insurer_code='TST'); assert rr['data'][0]['legal_entity_name_raw'] == 'Test Life Limited'
            assert rr['data'][0]['solvency_ratio'] == 3.04 and rr['data'][0]['sha256'] == 'c'*64
            assert c.coverage(insurer_code='TST')['data'][0]['coverage_status'] == 'FULL'
            assert c.evidence(run_id=2)['data'][0]['snapshot_path'] == 'raw/2'
            assert c.evidence(run_id=999)['count'] == 0
            try: c.fulfillment(metric_type='DROP TABLE')
            except icd_query.ICDQueryError: pass
            else: raise AssertionError('非法指标必须失败')
            try: c.fulfillment(limit=5001)
            except icd_query.ICDQueryError: pass
            else: raise AssertionError('超限必须失败')
        assert sha(db) == before, '只读查询不得修改数据库文件'
        missing = Path(td) / 'missing.db'
        try: icd_query.open_readonly(missing)
        except icd_query.ICDQueryError: pass
        else: raise AssertionError('不存在的数据库必须失败')
        assert not missing.exists(), '只读打开不得创建空库'
        agent = ICD / '04_定义Agent_Define_Agent/agents/agent.py'
        proc = subprocess.run([sys.executable,str(agent),'--query','evidence','--run-id','2','--db-path',str(db)],capture_output=True,text=True)
        assert proc.returncode == 0 and json.loads(proc.stdout)['data'][0]['sha256'] == 'b'*64
    print('T015 focused tests: PASS (readonly, latest/history, filters, evidence, invalid input, CLI)')


if __name__ == '__main__':
    main()
