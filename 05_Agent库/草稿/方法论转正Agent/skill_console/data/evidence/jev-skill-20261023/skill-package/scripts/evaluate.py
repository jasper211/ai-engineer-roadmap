#!/usr/bin/env python3
import argparse,datetime,hashlib,json,os,subprocess
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 raw=a.input.read_bytes();item=json.loads(raw)
 for k in ('item_id','profile','text','source_ref'):
  if not isinstance(item.get(k),str) or not item[k].strip():raise ValueError('Missing string field: '+k)
 profiles=json.loads((Path(__file__).resolve().parents[1]/'references/profiles.json').read_text())
 if item['profile'] not in profiles:raise ValueError('Unknown profile')
 if len(item['text'])>30000:raise ValueError('Input exceeds 30000 characters')
 a.output.mkdir(parents=True,exist_ok=False)
 receipt={'item_id':item['item_id'],'profile':item['profile'],'input_sha256':hashlib.sha256(raw).hexdigest(),'source_ref':item['source_ref'],'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'blocked','review_status':'pending_human_review','skill_version':'1.0.0'}
 try:
  key=os.environ.get('TYPESAFE_API_KEY','')
  if not key:raise ValueError('TYPESAFE_API_KEY is not configured')
  if any(c in key for c in '\r\n"\\'):raise ValueError('Invalid credential format')
  payload={'model':'jev-latest','state':{'document':item['text']},'questions':profiles[item['profile']]}
  request=a.output/'request.json';request.write_text(json.dumps(payload,ensure_ascii=False));receipt['request_sha256']=hashlib.sha256(request.read_bytes()).hexdigest()
  r=subprocess.run(['/usr/bin/curl','-sS','--max-time','45','--proto','=https','--config','-','-X','POST','https://api.typesafe.ai/v1/systemone','-H','Content-Type: application/json','--data-binary','@'+str(request.resolve()),'-o',str((a.output/'response.json').resolve()),'-w','%{http_code}'],input='header = "Authorization: Bearer '+key+'"\n',text=True,capture_output=True)
  receipt.update(http_status=r.stdout,curl_exit=r.returncode)
  if r.returncode or r.stdout!='200':raise ValueError('Transport/API failure; inspect status and response')
  d=json.loads((a.output/'response.json').read_text());receipt.update(model_resolved=d.get('model'),usage=d.get('usage'))
  if d.get('model')!='jev-1.14.0':raise ValueError('Model changed; revalidation required')
  ans=d.get('answers',{})
  for name,q in payload['questions'].items():
   v=ans.get(name,{})
   if v.get('type')!=q['type']:raise ValueError('Response type mismatch')
   if q['type']=='noul' and (type(v.get('noul')) not in (int,float) or not 0<=v['noul']<=1):raise ValueError('Invalid probability')
   if q['type']=='choice':
    if v.get('choice') not in q['criteria']:raise ValueError('Unknown choice')
    probs=v.get('probabilities',{})
    if set(probs)!=set(q['criteria']) or any(type(x) not in (int,float) or not 0<=x<=1 for x in probs.values()) or abs(sum(probs.values())-1)>0.02:raise ValueError('Invalid probability distribution')
  (a.output/'candidate.json').write_text(json.dumps({'item_id':item['item_id'],'source_ref':item['source_ref'],'answers':ans,'review_status':'pending_human_review'},ensure_ascii=False,indent=2));receipt['status']='candidate_created'
 except Exception as e:receipt['error']=str(e)
 (a.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False));return 0 if receipt['status']=='candidate_created' else 2
if __name__=='__main__':raise SystemExit(main())
