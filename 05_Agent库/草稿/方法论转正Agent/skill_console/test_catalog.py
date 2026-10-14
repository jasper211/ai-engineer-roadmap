import json, tempfile, unittest
from pathlib import Path
import app, catalog_update
class Catalog(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.old=app.DATA; app.DATA=Path(self.tmp.name)
 def tearDown(self):
  app.DATA=self.old; self.tmp.cleanup()
 def test_preserve_and_repeat(self):
  candidates=json.loads(Path(__file__).with_name('candidate_catalog.json').read_text())
  item=dict(candidates[0]);item['source_url']='https://github.com/test/old';item['tags']=['未安装','原有标签'];item['installation_result']={'evidence':'保留凭据'}
  item['material_id']=app.intake({'links':item['source_url']})[0]['id'];sid=app.save_analysis(item)
  with app.db() as c:c.execute("UPDATE skills SET status='已接入' WHERE id=?",(sid,))
  old=app.snapshot();catalog_update.update(candidates);new=app.snapshot()
  self.assertEqual(len(new['skills']),3);self.assertEqual(len(new['categories']),7)
  saved=next(s for s in new['skills'] if s['id']==sid)
  self.assertEqual(saved['status'],'已接入');self.assertEqual(saved['body']['tags'],['原有标签']);self.assertEqual(saved['body']['installation_result'],item['installation_result'])
  self.assertTrue(all(e in new['events'] for e in old['events']))
  self.assertEqual(catalog_update.update(candidates),[])
  for s in new['skills']:
   if s['id']!=sid:
    self.assertEqual(s['status'],'备选')
    with self.assertRaises(ValueError):app.action({'id':s['id'],'action':'approve'})
