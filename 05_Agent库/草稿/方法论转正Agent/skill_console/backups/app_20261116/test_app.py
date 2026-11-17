import os,tempfile,unittest
os.environ['SKILL_CONSOLE_DATA']=tempfile.mkdtemp(prefix='skill-console-test-')
import app
class Workflow(unittest.TestCase):
 def test_full_flow(self):
  payload={'links':'https://github.com/example/skills','note':'test'}
  first=app.intake(payload)[0];self.assertFalse(first['duplicate']);self.assertTrue(app.intake(payload)[0]['duplicate'])
  p={k:'test' for k in ['title','summary','purpose','inputs_outputs','workflow','examples','dependencies','limitations','compatibility','license','evidence']}
  p.update(material_id=first['id'],category='研究与知识',source_url=payload['links'],revision='a'*40,skill_path='skills/test',kind='skill',install_ready=True)
  sid=app.save_analysis(p);self.assertEqual(app.snapshot()['skills'][0]['status'],'备选')
  self.assertEqual(app.action({'id':sid,'action':'approve'}),'已确认 · 待执行')
  self.assertEqual(app.action({'id':sid,'action':'withdraw'}),'备选')
  p.update(id=sid,install_ready=False);app.save_analysis(p)
  with self.assertRaises(ValueError):app.action({'id':sid,'action':'approve'})
  self.assertEqual(app.snapshot()['materials'][0]['status'],'已分析')
  p.update(install_ready=True);app.save_analysis(p);app.action({'id':sid,'action':'approve'})
  target=app.DATA/'installed-test';target.mkdir();(target/'SKILL.md').write_text('test')
  result={'id':sid,'revision':'b'*40,'success':True,'evidence':'test only','installed_path':str(target),'verified':True}
  with self.assertRaises(ValueError):app.record_result(result)
  result['revision']='a'*40
  self.assertEqual(app.record_result(result),'已接入')
 def test_reject_sources_and_images(self):
  for url in ['http://github.com/a/b','https://github.com.evil.test/a/b','https://github.com','https://user@github.com/a/b']:
   with self.assertRaises(ValueError):app.github_url(url)
  with self.assertRaises(ValueError):app.intake({'images':[{'data':'aGVsbG8='}]})
if __name__=='__main__':unittest.main()
