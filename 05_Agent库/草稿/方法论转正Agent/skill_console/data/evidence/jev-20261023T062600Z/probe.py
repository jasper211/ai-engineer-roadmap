import os,json,subprocess,datetime
from pathlib import Path
root=Path('/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/方法论转正Agent/skill_console/data/evidence')
out=root/('jev-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir();print('OUTPUT',out,flush=True)
key=os.environ.get('TYPESAFE_API_KEY','');print('credential_available',bool(key),flush=True)
if not key: (out/'receipt.json').write_text('{"status":"missing_credentials"}');raise SystemExit
if any(x in key for x in '\n\r"\\'):raise SystemExit('Invalid credential format')
requests=[('models','GET','models',None),('synthetic','POST','systemone',{'model':'jev-latest','state':{'document':'这是虚构测试：某监管机构发布征求意见稿，尚未生效，征求行业意见。'},'questions':{'formal_effective':{'type':'noul','instructions':'文件是否已正式生效？'},'document_type':{'type':'choice','instructions':'判断文件性质','criteria':{'正式规则':None,'征求意见稿':None,'普通新闻':None}},'priority':{'type':'score','instructions':'按文件明确的生效状态评估处理优先级','criteria':['仅观察','需要评审','立即执行']}}})]
receipts=[]
for name,method,endpoint,payload in requests:
 args=['/usr/bin/curl','-sS','--max-time','45','--proto','=https','--config','-','-X',method,'https://api.typesafe.ai/v1/'+endpoint,'-o',str(out/(name+'-response.json')),'-w','%{http_code}']
 if payload:
  (out/(name+'-request.json')).write_text(json.dumps(payload,ensure_ascii=False));args+=['-H','Content-Type: application/json','--data-binary','@'+str(out/(name+'-request.json'))]
 r=subprocess.run(args,input='header = "Authorization: Bearer '+key+'"\n',text=True,capture_output=True)
 (out/(name+'-stderr.txt')).write_text(r.stderr);receipts.append({'test':name,'http':r.stdout,'exit':r.returncode});print(receipts[-1],flush=True)
(out/'receipt.json').write_text(json.dumps(receipts,indent=2))
