import json,hashlib,subprocess,datetime,importlib.util,os
from pathlib import Path
base=Path('/Users/a112233/Desktop/Jasper工作文档（不含EA项目）')
root=base/'Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/方法论转正Agent/skill_console/data/evidence/firecrawl-u071-20261014'
u=base/'项目工作区/Rw权益项目工作区/原子服务设计/U071_新规解读包'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=root/stamp;out.mkdir()
files=[p for p in u.rglob('*') if p.is_file()]
before={str(p.relative_to(u)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(out/'u071-before.json').write_text(json.dumps(before,indent=2))
url=json.loads((u/'runs/p0_20261014_attempt02/receipt.json').read_text())['official_url']
(out/'historical-receipt.json').write_bytes((u/'runs/p0_20261014_attempt02/receipt.json').read_bytes())
targets=[('original_pdf',url,'历史失败的同一URL'),('candidate_listing','https://www.ia.org.hk/en/legislative_framework/circulars/reg_matters/circulars_on_regulatory_matters_2024.html','新增年度栏目候选URL；历史回执没有HTML URL，不宣称同页重放')]
results=[]
for name,address,note in targets:
 folder=out/name;folder.mkdir()
 cmd=['/usr/bin/curl','--silent','--show-error','--location','--proto','=https','--proto-redir','=https','--max-time','40','--max-filesize','30000000','--dump-header',str(folder/'headers.txt'),'--output',str(folder/'response.bin'),'--write-out','%{json}',address]
 r=subprocess.run(cmd,capture_output=True,text=True)
 (folder/'curl-metadata.json').write_text(r.stdout);(folder/'stderr.txt').write_text(r.stderr)
 try:meta=json.loads(r.stdout)
 except:meta={}
 data=(folder/'response.bin').read_bytes() if (folder/'response.bin').exists() else b''
 results.append(dict(target=name,url=address,note=note,method='curl default HTTPS with certificate verification',exit_code=r.returncode,http_status=meta.get('http_code'),final_url=meta.get('url_effective'),content_type=meta.get('content_type'),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),pdf_magic=data.startswith(b'%PDF-'),elapsed_seconds=meta.get('time_total')))
 print(json.dumps(results[-1],ensure_ascii=False),flush=True)
spec=importlib.util.spec_from_file_location('u071_adapter',u/'source_adapter.py');mod=importlib.util.module_from_spec(spec)
try:
 spec.loader.exec_module(mod)
 replay=mod.intake(url,out/'existing_adapter_replay')
except Exception as e:replay={'status':'environment_blocked','error':str(e)}
(out/'existing-adapter-result.json').write_text(json.dumps(replay,ensure_ascii=False,indent=2))
fire={'status':'not_run_missing_credentials','api_key_in_environment':bool(os.environ.get('FIRECRAWL_API_KEY')),'connected_tool_available':False,'endpoint':'https://api.firecrawl.dev/v2/scrape','docs':'https://docs.firecrawl.dev/api-reference/endpoint/scrape','note':'未发起Firecrawl请求，未安装或部署；不可据此判断其能否解决403'}
(out/'firecrawl-receipt.json').write_text(json.dumps(fire,ensure_ascii=False,indent=2))
after={str(p.relative_to(u)):hashlib.sha256(p.read_bytes()).hexdigest() for p in u.rglob('*') if p.is_file()}
# Imported Python may create pycache; bytecode disabled by caller.
(out/'u071-after.json').write_text(json.dumps(after,indent=2))
receipt={'time_utc':stamp,'results':results,'existing_adapter':replay,'firecrawl':fire,'u071_unchanged':before==after,'comparison_complete':False}
(out/'comparison.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print('EVIDENCE',out);print('UNCHANGED',before==after)
