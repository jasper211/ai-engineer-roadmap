#!/usr/bin/env python3
"""T016 寿险 RBC：真实快照字段与法律主体 fail-closed。"""

import hashlib
import sqlite3
import sys
import tempfile
from pathlib import Path

ICD = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ICD / '05_集成工具_Integrate_Tools'), str(ICD / '06_开发技能_Develop_Skills')]
from skills import parse_disclosure, rbc_parser  # noqa: E402
from tools import sqlite_store  # noqa: E402

AIA_HASH = '2c8df3a0ffd2d0a18dc4d5c2898183cf8c78f30bf3291271ab3befd1a9c5ebb3'
PRU_HASH = 'cabaf54ae47e1eae6fa47003647cf01e54d351efb338299983fbb79afb5a761a'


def snapshot(insurer, source, digest):
    return ICD / '07_接入记忆_Integrate_Memory/raw_data' / insurer / str(source) / f'{digest}.pdf'


def main():
    cases = [
        (snapshot('AIA', 23, AIA_HASH), AIA_HASH, 'AIA International Limited', '212%', 2.12, '183,772,393', '86,668,623'),
        (snapshot('PRU', 24, PRU_HASH), PRU_HASH, 'Prudential Hong Kong Limited', '239%', 2.39, '113,845,439', '47,664,502'),
    ]
    for path, digest, legal, raw, ratio, cb, pca in cases:
        body = path.read_bytes()
        assert hashlib.sha256(body).hexdigest() == digest
        row = rbc_parser.parse_rbc(body)['records'][0]
        assert row['legal_entity_name_raw'] == legal
        assert row['solvency_ratio_raw'] == raw and row['solvency_ratio'] == ratio
        assert row['capital_base_raw'] == cb and row['prescribed_capital_amount_raw'] == pca
        assert row['amount_scale'] == 'thousands' and row['currency'] == 'HKD'

    # 用 PHKL 文件冒充 AIA 源，必须在写业务表前因法律主体不一致而失败。
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); db = root/'x.db'; conn = sqlite3.connect(db)
        conn.executescript(sqlite_store.SCHEMA_SQL)
        conn.execute("INSERT INTO insurer(insurer_code,name_en) VALUES('AIA','AIA International Limited')")
        conn.execute("INSERT INTO error_code(code,category,is_hard_failure,description) VALUES('STRUCTURE_MISMATCH','PARSE',1,'结构不匹配')")
        conn.execute("""INSERT INTO data_source(source_id,insurer_code,disclosure_type,entry_url,format,access_status,evidence_basis)
                        VALUES(1,'AIA','rbc','https://official.test/wrong.pdf','pdf','OPEN','test')""")
        rel = 'raw_data/AIA/1/wrong.pdf'; target = root/'AIA/1/wrong.pdf'; target.parent.mkdir(parents=True)
        body = cases[1][0].read_bytes(); target.write_bytes(body)
        conn.execute("""INSERT INTO fetch_run(run_id,source_id,final_url,http_status,content_hash,content_length,snapshot_path,fetch_status)
                        VALUES(1,1,'https://official.test/wrong.pdf',200,?,?,?,'OK')""", (hashlib.sha256(body).hexdigest(),len(body),rel))
        conn.commit()
        out = parse_disclosure.parse_one_source(conn, {'source_id':1,'insurer_code':'AIA','disclosure_type':'rbc','format':'pdf'}, root)
        assert out['result'] == 'STRUCTURE_MISMATCH' and '法律主体不匹配' in out['message']
        assert conn.execute('select count(*) from rbc_statement').fetchone()[0] == 0
        conn.close()
    print('T016 focused tests: PASS (official hashes, fields, scaling, legal-entity mismatch fails closed)')


if __name__ == '__main__':
    main()
