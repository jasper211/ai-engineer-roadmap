import subprocess,json,datetime,hashlib,base64,sys
from pathlib import Path
root=Path('/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/方法论转正Agent/skill_console/data/evidence/firecrawl-u071-20261014')
out=root/('raw-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
key=''
payload={'url':'https://www.ia.org.hk/en/legislative_framework/circulars/reg_matters/files/20240522_Circular.pdf','formats':['rawBase64'],'parsers':[],'skipTlsVerification':False,'timeout':45000,'maxAge':0}
(out/'request.json').write_text(json.dumps(payload))
r=subprocess.run(['/usr/bin/curl','-sS','--max-time','55','--proto','=https','--config','-','-X','POST','https://api.firecrawl.dev/v2/scrape','-H','Content-Type: application/json','--data-binary','@'+str(out/'request.json'),'-D',str(out/'headers.txt'),'-o',str(out/'response.json'),'-w','%{http_code}'],input='',capture_output=True,text=True)
key='';k=None
(out/'stderr.txt').write_text(r.stderr)
j=json.loads((out/'response.json').read_text()) if (out/'response.json').exists() else {}
d=j.get('data',{});receipt={'api_http_status':r.stdout,'success':j.get('success'),'error':j.get('error'),'data_keys':list(d),'metadata':d.get('metadata'),'auth':'anonymous official trial; named keychain item not found'}
raw=d.get('rawBase64','')
if raw:
 if raw.startswith('data:'):raw=raw.split(',',1)[1]
 try:
  data=base64.b64decode(raw,validate=True)
  receipt.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),pdf_magic=data.startswith(b'%PDF-'))
  (out/('source.pdf' if data.startswith(b'%PDF-') else 'nonpdf.bin')).write_bytes(data)
 except Exception as e:receipt['decode_error']=str(e)
(out/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt));print('OUTPUT',out)
