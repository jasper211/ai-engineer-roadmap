import unittest
from hkia_adapter import HKIAClient

class TestAnnualExtension(unittest.TestCase):
    def setUp(self): self.client=HKIAClient.open_readonly()
    def tearDown(self): self.client.close()
    def test_health_has_annual_market(self):
        r=self.client.query({'query_type':'healthcheck'})
        counts={x['db_id']:x['row_count'] for x in r['data']}
        self.assertEqual(counts['annual_market'],2942)
    def test_l1_series(self):
        r=self.client.query({'query_type':'annual_market_series','metric_id':'ANNUAL_L1_NB_PREMIUM_TOTAL','period':'2024','entity_scope':'market_total'})
        self.assertTrue(r['ok']); self.assertEqual(len(r['data']),5)
        self.assertAlmostEqual(r['data'][-1]['value'],206887.7267342371)
    def test_l5_rate_is_not_amount(self):
        r=self.client.query({'query_type':'annual_market_series','metric_id':'ANNUAL_L5_NONLINKED_WHOLELIFE_TERMINATION','period':'2024','entity_scope':'market_total'})
        self.assertTrue(r['ok']); self.assertTrue(all(x['unit']=='percentage_point' for x in r['data']))
    def test_l16_component(self):
        r=self.client.query({'query_type':'annual_company_components','metric_id':'ANNUAL_L16_PREMIUM_SINGLE_COMPONENT','period':'2024','entity_scope':'insurer','filters':{'entity':'AIA International'}})
        self.assertTrue(r['ok']); self.assertEqual(r['data'][0]['value'],10677251.0)
    def test_table_name_cannot_be_injected(self):
        r=self.client.query({'query_type':'annual_market_series','metric_id':'MISSING; DROP TABLE x','period':'2024'})
        self.assertFalse(r['ok']); self.assertEqual(r['error_code'],'VALIDATION_ERROR')

if __name__=='__main__': unittest.main()
