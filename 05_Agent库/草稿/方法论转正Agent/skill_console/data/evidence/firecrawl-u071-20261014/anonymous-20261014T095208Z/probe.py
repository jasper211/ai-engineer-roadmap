import json,subprocess,datetime
from pathlib import Path
root=Path('/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/方法论转正Agent/skill_console/data/evidence/firecrawl-u071-20261014')
out=root/('anonymous-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
urls=['https://www.ia.org.hk/en/legislative_framework/circulars/reg_matters/files/20240522_Circular.pdf','https://www.ia.org.hk/en/legislative_framework/circulars/reg_matters/circulars_on_regulatory_matters_2024.html']
rows=[]
for i,url in enumerate(urls,1):
 payload=json.dumps({'url':url,'formats':['markdown'],'timeout':30000,'maxAge':0})
 (out/f'{i}-request.json').write_text(payload)
 r=subprocess.run(['/usr/bin/curl','-sS','--max-time','45','--proto','=https','-X','POST','https://api.firecrawl.dev/v2/scrape','-H','Content-Type: application/json','--data-binary','@-','-D',str(out/f'{i}-headers.txt'),'-o',str(out/f'{i}-response.json'),'-w','%{http_code}'],input=payload,capture_output=True,text=True)
 (out/f'{i}-stderr.txt').write_text(r.stderr)
 body=(out/f'{i}-response.json').read_text() if (out/f'{i}-response.json').exists() else ''
 try:j=json.loads(body)
 except:j={}
 row={'url':url,'api_http_status':r.stdout,'curl_exit':r.returncode,'success':j.get('success'),'error':j.get('error'),'markdown_chars':len(j.get('data',{}).get('markdown',''))}
 rows.append(row);print(json.dumps(row),flush=True)
(out/'receipt.json').write_text(json.dumps({'auth':'none; official documented trial','results':rows},indent=2));print('OUTPUT',out)
