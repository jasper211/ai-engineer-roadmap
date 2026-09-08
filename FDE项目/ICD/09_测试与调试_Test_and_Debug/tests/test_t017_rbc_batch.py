#!/usr/bin/env python3
"""T017 RBC 批次：官方快照、跨行标度和无文字层安全失败。"""

import hashlib
import sys
from pathlib import Path

ICD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ICD / '06_开发技能_Develop_Skills'))
from skills import pdf_text, rbc_parser  # noqa: E402

CASES = [
    ('AXA',14,'d3bada8339bf1e169df0661fecda89f47539a9c5c97f4738472d220a89363095','AXA China Region Insurance Company Limited','204%',2.04,'10,636,247','5,189,682',10636247000.0,5189682000.0),
    ('SUN',16,'317089452d81b18ccc32137a1b6be7246acf5eea12224085451cd339f13f4a0a','Sun Life Hong Kong Limited','229 %',2.29,'20,981,085','9,165,514',20981085000.0,9165514000.0),
]


def path(code, source, digest):
    return ICD/'07_接入记忆_Integrate_Memory/raw_data'/code/str(source)/f'{digest}.pdf'


def main():
    for code,source,digest,legal,raw,ratio,cb,pca,cb_abs,pca_abs in CASES:
        body=path(code,source,digest).read_bytes()
        assert hashlib.sha256(body).hexdigest()==digest
        row=rbc_parser.parse_rbc(body)['records'][0]
        assert row['legal_entity_name_raw']==legal
        assert row['solvency_ratio_raw']==raw and row['solvency_ratio']==ratio
        assert row['capital_base_raw']==cb and row['prescribed_capital_amount_raw']==pca
        assert row['amount_unit_raw']=='in HKD thousands' and row['amount_scale']=='thousands'
        assert row['capital_base']==cb_abs and row['prescribed_capital_amount']==pca_abs
    yhash='529938a06940ca9d3429f9f89ac95b586faec99fb5f4d695e2526a3b7b7b9e1d'
    body=path('YFL',15,yhash).read_bytes(); assert hashlib.sha256(body).hexdigest()==yhash
    try: rbc_parser.parse_rbc(body)
    except pdf_text.PdfNoTextError: pass
    else: raise AssertionError('YFL 无文字层 PDF 必须安全失败')
    print('T017 focused tests: PASS (AXA/SUN values+scale, YFL PDF_NO_TEXT fail-closed)')


if __name__=='__main__': main()
