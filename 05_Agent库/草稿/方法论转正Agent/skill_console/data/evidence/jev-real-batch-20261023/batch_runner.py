from pathlib import Path
import json,hashlib,subprocess,datetime
base=Path('/Users/a112233/Desktop/Jasper工作文档（不含EA项目）');console=base/'Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/方法论转正Agent/skill_console';out=console/'data/evidence/jev-real-batch-20261023';out.mkdir(exist_ok=False);(out/'inputs').mkdir()
cache=base/'项目工作区/Rw权益项目工作区/U020_月度行情热点解读/15_协同规划_Coordination/交付收敛/calendar_cache';rows=[]
choices=[('0941','待确认','日历摘录缺主题语境，需补正文'),('1186','宏观与市场','LPR公告标题明确'),('1a0c','宏观与市场','国债流动性回购'),('1942','宏观与市场','统计指标发布日程'),('31fa','保险监管','保险资本规则与宏观相关性可能重叠')]
for prefix,label,note in choices:
 p=next(cache.glob(prefix+'*.json'));d=json.loads(p.read_text());e=d['result']['events'][0];text=e.get('title_quote','')+'\n'+e.get('date_quote','');rid='u20-'+p.stem[:12]
 rows.append(dict(item_id=rid,profile='u20',text=text,source_ref=d['source_url'],expected=label,note=note,snapshot=str(p),snapshot_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),scope='归档公开原文摘录；不发送生成的watch/impact解释'))
r=base/'项目工作区/Rw权益项目工作区/原子服务设计/U071_新规解读包/service_data/public/packages'
for name,note in [('ec4df4d4f4f1b75dd7a7c214','正式通函但未明确本文件已生效，不应推定'),('14bd21e691754bf6fe3cb85c','正式通函；2027落实期限不等同已经生效'),('22a65fc87a6c0b1dd06dfa03','正式发布解释说明的通函；需结合附件'),('d77fe372d5e91b42d7f82171','正式通函形式，内容是监管通讯发布；不能直接触发新规包')]:
 p=r/name/'sixpack-v1/source_evidence.json';d=json.loads(p.read_text())[0];text='\n'.join(x['text'] for x in d['pages']);rows.append(dict(item_id='u071-'+name,profile='u071',text=text,source_ref=d['url'],expected='正式文件',note=note,snapshot=str(p),snapshot_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_sha256=d['sha256'],scope='归档官方PDF主文逐页文字；附件不包含在本次输入',expected_in_force=False))
(out/'frozen-labels.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for row in rows:
 p=out/'inputs'/(row['item_id']+'.json');p.write_text(json.dumps({k:row[k] for k in ['item_id','profile','text','source_ref']},ensure_ascii=False))
print('FROZEN',len(rows),flush=True)
for row in rows:
 p=out/'inputs'/(row['item_id']+'.json');r=subprocess.run(['python3','/Users/a112233/.codex/skills/jev-evidence-triage/scripts/evaluate.py','--input',str(p),'--output',str(out/row['item_id'])],capture_output=True,text=True);print(row['item_id'],r.returncode,flush=True)
print('DONE',out)
