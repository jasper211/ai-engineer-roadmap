"""Read-only regression for the revised U20 guide. No source DB writes."""
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
baseline = subprocess.run([sys.executable, str(BASE / 'verify_u20_call.py')], text=True, capture_output=True, check=True)
result = json.loads(baseline.stdout)
guide = (BASE / 'U20调用指引_v1.md').read_text(encoding='utf-8')
revision = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'tests': {}}
c = sqlite3.connect(':memory:', uri=True)
try:
    # In-memory target prevents any accidental file creation if syntax changes.
    c.execute("ATTACH ':memory:' AS invalid_test (READ ONLY)")
    revision['guide_attach_error'] = None
except sqlite3.Error as exc:
    revision['guide_attach_error'] = str(exc)
revision['tests']['guide_attach_syntax_valid'] = '(READ ONLY)' not in guide or revision['guide_attach_error'] is None
for alias, layer in [('ann', 'annual'), ('prov25', 'provisional')]:
    uri = Path(result['connections'][layer]['path']).as_uri() + '?mode=ro'
    c.execute(f'ATTACH DATABASE ? AS {alias}', (uri,))
c.execute('PRAGMA query_only=ON')
counts = [c.execute('SELECT count(*) FROM ann.company_facts').fetchone()[0], c.execute('SELECT count(*) FROM prov25.provisional_company_facts').fetchone()[0]]
revision['corrected_uri_attach_counts'] = counts
revision['tests']['corrected_uri_attach_works'] = counts == [7097, 414]
revision['market_2024'] = c.execute("SELECT table_id,subject,value_raw,unit FROM ann.company_facts WHERE report_year=2024 AND table_id IN ('L16','L17') AND metric_sem='premium_single' AND entity_scope='market_total'").fetchall()
revision['market_2025'] = c.execute("SELECT year,subject,value,unit,certification FROM prov25.provisional_company_facts WHERE year=2025 AND metric_sem='nb_total_single_premium' AND entity_scope='market_total'").fetchall()
revision['annual_columns'] = [r[1] for r in c.execute('PRAGMA ann.table_info(company_facts)')]
revision['provisional_columns'] = [r[1] for r in c.execute('PRAGMA prov25.table_info(provisional_company_facts)')]
revision['bridge_directory_files'] = sorted(str(p.relative_to(BASE)) for p in (BASE / '生成_跨年度同口径桥_CrossYearBridge').rglob('*') if p.is_file())
revision['review_findings'] = {
    'same_scope_release_accepted': False,
    'reason': 'The supplied bridge documents compare 2024 whole L16 with 2025 participating+linked subset without a proved two-sided product definition mapping. Arithmetic alone cannot establish same scope.',
    'identity_bridge_complete': False,
    'identity_reason': 'Bridge directory contains narrative Markdown only; annual/provisional tables have no shared entity_key/business_lineage fields. A complete cross-layer mapping and reproducible coverage check were not supplied in that directory.',
}
revision['acceptance'] = 'PARTIAL: base DB consumption passed; revised ATTACH example and same-scope release gate not passed'
c.close()
result['revision_review'] = revision
output = BASE / 'U20调用验证结果_20260831_r2.json'
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'output': str(output), 'base_checks_passed': sum(result['checks'].values()), 'base_checks_total': len(result['checks']), 'revision': revision}, ensure_ascii=False, indent=2))
sys.exit(0 if all(revision['tests'].values()) and revision['review_findings']['same_scope_release_accepted'] and revision['review_findings']['identity_bridge_complete'] else 1)
