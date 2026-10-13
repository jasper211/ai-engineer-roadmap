import argparse,asyncio,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from importlib.metadata import version
import truststore
truststore.inject_into_ssl()
from crawl4ai import AsyncWebCrawler,BrowserConfig,CrawlerRunConfig,CacheMode
from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy
from crawl4ai.async_configs import HTTPCrawlerConfig

async def run(args):
    out=Path(args.output).resolve()
    out.mkdir(parents=True,exist_ok=False)
    manifest=out/'manifest.json'
    if manifest.exists(): raise SystemExit('Choose a new output directory; manifest already exists.')
    report={'started_at':datetime.now(timezone.utc).isoformat(),'crawl4ai_version':version('crawl4ai'),'mode':args.mode,'pages':[]}
    config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS,check_robots_txt=True,page_timeout=60000,wait_until='domcontentloaded',delay_before_return_html=2.0)
    browser=BrowserConfig(headless=True,chrome_channel="chrome",ignore_https_errors=False)
    manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('Starting Crawl4AI '+args.mode,flush=True)
    strategy=AsyncHTTPCrawlerStrategy(browser_config=HTTPCrawlerConfig(verify_ssl=True)) if args.mode=='http' else None
    async with AsyncWebCrawler(config=browser,crawler_strategy=strategy) as crawler:
        for i,url in enumerate(args.urls,1):
            row={'requested_url':url,'collected_at':datetime.now(timezone.utc).isoformat()}
            try:
                print('Collecting '+url,flush=True)
                result=await asyncio.wait_for(crawler.arun(url=url,config=config),timeout=90)
                md=result.markdown.raw_markdown if result.markdown else ''
                row.update(success=result.success,status_code=result.status_code,final_url=getattr(result,'redirected_url',None) or result.url,error=result.error_message,markdown_chars=len(md),title=(result.metadata or {}).get('title'))
                for suffix,body in [('md',md),('html',result.html or '')]:
                    path=out/f'{i:02d}.{suffix}';path.write_text(body,encoding='utf-8')
                    row[suffix]={'path':str(path),'sha256':hashlib.sha256(body.encode()).hexdigest()}
            except Exception as exc: row.update(success=False,error=type(exc).__name__+': '+str(exc))
            report['pages'].append(row)
            manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps({k:v for k,v in row.items() if k not in ('md','html')},ensure_ascii=False),flush=True)
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if all(x.get('success') and x.get('markdown_chars',0)>0 for x in report['pages']) else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('urls',nargs='+');p.add_argument('--mode',choices=['http','browser'],default='http');a=p.parse_args()
    for url in a.urls:
        u=urlparse(url)
        if u.scheme not in ('https','http') or not u.hostname or u.username or u.password: p.error('Use explicit HTTP(S) URLs without embedded credentials.')
    sys.exit(asyncio.run(run(a)))
