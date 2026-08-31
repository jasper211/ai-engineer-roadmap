"""Read-only U20 acceptance probe. Run from any directory; JSON goes to stdout."""
import json
import argparse
from datetime import datetime, timezone
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
PATHS = {
    'raw': BASE.parent / '07_接入记忆_Integrate_Memory/data/hkia.db',
    'standard': BASE / '生成_标准事实层_StandardFactLayer/data/standard_fact_layer_2023_2026Q1.db',
    'annual': BASE / '生成_年度公司事实层_AnnualCompanyFactLayer/data/annual_company_fact_layer_2022_2024.db',
    'provisional': BASE / '生成_2025provisional公司事实层_AnnualProvisionalCompanyLayer/data/annual_provisional_company_2025.db',
    'financial': BASE / '生成_行业财务事实层_FinancialFactLayer/data/financial_fact_layer.db',
}
EXPECTED = {'raw': {'long_term_business': 59516}, 'standard': {'market_facts': 72, 'company_facts': 4914, 'schema_metrics': 18, 'annual_facts': 18}, 'annual': {'company_facts': 7097}, 'provisional': {'provisional_company_facts': 414}, 'financial': {'financial_facts': 408}}
db = {}
result = {'connections': {}, 'queries': {}, 'checks': {}}
for name, path in PATHS.items():
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    db[name] = conn
    counts = {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in EXPECTED[name]}
    result['connections'][name] = {'path': str(path), 'counts': counts, 'counts_match': counts == EXPECTED[name], 'quick_check': conn.execute('PRAGMA quick_check').fetchone()[0]}

def query(name, sql):
    return [dict(row) for row in db[name].execute(sql)]

QUERIES = {
 'Q1': ('standard', "SELECT period,metric_id,value,unit FROM market_facts WHERE metric_id='NB_IND_TOTAL_ANNUALIZED_PREMIUM' ORDER BY period"),
 'Q2': ('annual', "SELECT insurer_name_source,value_raw FROM company_facts WHERE report_year=2024 AND table_id='L16' AND metric_sem='premium_single' AND entity_scope='insurer' ORDER BY value_raw DESC LIMIT 10"),
 'Q3': ('provisional', "SELECT insurer_name_en,value FROM provisional_company_facts WHERE metric_sem='nb_total_single_premium' AND entity_scope='insurer' ORDER BY value DESC LIMIT 10"),
 'Q4': ('financial', "SELECT item_label_zh,value_hkd_million FROM financial_facts WHERE period='2026Q1' AND fund_scope='long_term' AND item_id IN ('debt_securities','equities_portfolio','cash_and_deposits') ORDER BY value_hkd_million DESC"),
}
for name, (layer, sql) in QUERIES.items():
    result['queries'][name] = {'sql': sql, 'rows': query(layer, sql)}
result['unit_inventory'] = {name: query(name, f'SELECT unit, COUNT(*) AS n FROM "{table}" GROUP BY unit') for name, table in [('raw','long_term_business'), ('standard','market_facts'), ('annual','company_facts'), ('provisional','provisional_company_facts'), ('financial','financial_facts')]}
result['certification_inventory'] = query('provisional','SELECT DISTINCT year, certification FROM provisional_company_facts') + query('standard','SELECT DISTINCT period, certification FROM annual_facts')
result['L11_routes'] = query('annual', "SELECT report_year,metric_sem,unit,COUNT(*) AS n FROM company_facts WHERE table_id='L11' GROUP BY report_year,metric_sem,unit")
result['bridge_inventory'] = query('standard', "SELECT DISTINCT source_abbrev,entity_key,business_lineage,bridge_class FROM company_facts WHERE source_abbrev LIKE '%AXA%' OR source_abbrev LIKE '%Chubb%' OR source_abbrev LIKE '%Canada%' OR source_abbrev LIKE '%MyPace%' OR source_abbrev IN ('FTLife','CTF Life')")

def to_hkd_million(value, unit):
    factors = {'hkd_thousand': 0.001, '千港元': 0.001, 'hkd_million': 1.0}
    normalized = str(unit).strip().lower()
    if normalized not in factors:
        raise ValueError('Count/unknown unit cannot enter monetary aggregation: ' + str(unit))
    return None if value is None else value * factors[normalized]

def certification(layer, period):
    # Not derived from year alone: 2023Q1 is still provisional.
    if layer == 'annual' and int(period) in (2022, 2023, 2024):
        return 'certified'
    if layer in ('standard_quarterly', 'provisional'):
        return 'provisional'
    return 'unclassified_requires_source'

result['checks']['unit_conversion'] = to_hkd_million(1000,'HKD_thousand') == 1
try:
    to_hkd_million(1000, 'count')
    result['checks']['count_rejected'] = False
except ValueError:
    result['checks']['count_rejected'] = True
result['checks']['null_preserved'] = to_hkd_million(None,'HKD_thousand') is None
result['checks']['quarterly_2023_not_certified'] = certification('standard_quarterly','2023Q1') == 'provisional'
result['checks']['annual_2024_certified'] = certification('annual',2024) == 'certified'
result['checks']['five_db_counts_match'] = all(v['counts_match'] for v in result['connections'].values())
result['checks']['query_row_counts'] = [len(result['queries'][q]['rows']) for q in QUERIES] == [4,10,10,3]
result['checks']['all_quick_checks_ok'] = all(v['quick_check'] == 'ok' for v in result['connections'].values())
for unit in ('HKD_thousand', 'hkd_thousand', '千港元', 'HKD_million'):
    result['checks']['unit_alias_' + unit] = to_hkd_million(1000, unit) == (1000 if unit == 'HKD_million' else 1)
for unit in ('', None, 'count', 'unsupported'):
    try:
        to_hkd_million(1, unit)
        result['checks']['reject_' + str(unit)] = False
    except ValueError:
        result['checks']['reject_' + str(unit)] = True

# Query with metadata retained: top-N guide SQL alone drops critical labels.
annual = query('annual', "SELECT report_year,table_id,subject,metric_sem,unit,value_raw FROM company_facts WHERE report_year=2024 AND table_id='L16' AND metric_sem='premium_single' AND entity_scope='insurer' ORDER BY value_raw DESC LIMIT 10")
provisional = query('provisional', "SELECT year,certification,table_id,subject,metric_sem,unit,value FROM provisional_company_facts WHERE year=2025 AND metric_sem='nb_total_single_premium' AND entity_scope='insurer' ORDER BY value DESC LIMIT 10")
financial_labels = query('financial', 'SELECT certification, COUNT(*) AS n FROM financial_facts GROUP BY certification')
financial_sample = query('financial', "SELECT period,fund_scope,item_id,value_hkd_million,unit,certification FROM financial_facts WHERE period='2026Q1' AND fund_scope='long_term' AND item_id IN ('debt_securities','equities_portfolio','cash_and_deposits') ORDER BY value_hkd_million DESC")
result['financial_certification_inventory'] = financial_labels
result['checks']['financial_certification_populated'] = sum(r['n'] for r in financial_labels) == 408 and all(r['certification'] == 'provisional' for r in financial_labels)
result['consumer_samples'] = {
    'Q1': [dict(r, value_hkd_million=to_hkd_million(r['value'], r['unit']), certification=certification('standard_quarterly', r['period']), label_basis='quarterly source layer; not a DB certification column') for r in result['queries']['Q1']['rows']],
    'Q2': [dict(r, value_hkd_million=to_hkd_million(r['value_raw'], r['unit']), certification=certification('annual', r['report_year']), label_basis='annual source layer; not a DB certification column') for r in annual],
    'Q3': [dict(r, value_hkd_million=to_hkd_million(r['value'], r['unit'])) for r in provisional],
    'Q4': financial_sample,
}
result['checks']['actual_annual_unit_conversion'] = result['consumer_samples']['Q2'][0]['value_hkd_million'] == annual[0]['value_raw'] / 1000
result['checks']['actual_provisional_label'] = all(r['certification'] == 'provisional' for r in provisional)

def comparable(left, right, *, reviewed_schema_bridge=False):
    # Matching money units or names alone does not establish comparability.
    required = ('metric', 'unit', 'scope', 'period_basis', 'schema')
    if any(k not in left or k not in right for k in required):
        return False
    return all(left[k] == right[k] for k in required[:-1]) and (left['schema'] == right['schema'] or reviewed_schema_bridge)

base = dict(metric='single_premium', unit='HKD_million', scope='individual_life', period_basis='annual', schema='RBC')
result['checks']['scope_mismatch_rejected'] = not comparable(base, dict(base, scope='individual_long_term_including_annuity'))
result['checks']['unreviewed_schema_bridge_rejected'] = not comparable(base, dict(base, schema='pre_RBC'))
result['checks']['L11_policy_vs_scheme_rejected'] = not comparable(dict(base, metric='policy_count', unit='count'), dict(base, metric='scheme_count', unit='count'))
result['checks']['missing_metadata_rejected'] = not comparable({}, {})
bridges = result['bridge_inventory']
ctf = [r for r in bridges if r['source_abbrev'] in ('FTLife','CTF Life')]
result['checks']['ctf_rename_same_entity'] = len({r['source_abbrev'] for r in ctf}) == 2 and len({r['entity_key'] for r in ctf}) == 1
transfer = [r for r in bridges if r['source_abbrev'] in ('Canada Life Assurance','MyPace Life')]
result['checks']['transfer_distinct_entity_same_lineage'] = len({r['entity_key'] for r in transfer}) == 2 and len({r['business_lineage'] for r in transfer}) == 1
result['limitations'] = ['Proxy probe only: U20 production application has not been inspected or modified.', 'Cross-layer annual/provisional identity mapping and schema bridge are not validated; comparison is blocked by default.', 'Guide counts are snapshot expectations, not automatic future-refresh targets.', 'Query execution and metadata checks do not re-audit source spreadsheet extraction.']
result['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
for conn in db.values():
    conn.close()
payload = json.dumps(result, ensure_ascii=False, indent=2)
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path)
args = parser.parse_args()
if args.output:
    args.output.write_text(payload + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'checks': result['checks']}, ensure_ascii=False, indent=2))
else:
    print(payload)
raise SystemExit(0 if all(result['checks'].values()) else 1)
