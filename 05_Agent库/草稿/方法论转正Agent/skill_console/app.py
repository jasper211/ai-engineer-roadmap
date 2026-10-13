#!/usr/bin/env python3
"""Local skill library. Browser intake and agent CLI share SQLite."""
import argparse, base64, json, os, sqlite3, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('SKILL_CONSOLE_DATA', str(ROOT / 'data')))
CATEGORIES = ['研究与知识', '文档与办公', '数据与分析', '开发与自动化', '设计与媒体', '业务专用', '待分类']

def now(): return datetime.now(timezone.utc).isoformat()
def db():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATA / 'library.sqlite3', timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''CREATE TABLE IF NOT EXISTS materials(id TEXT PRIMARY KEY, kind TEXT, source TEXT UNIQUE, note TEXT, status TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS skills(id TEXT PRIMARY KEY, material_id TEXT, title TEXT, category TEXT, status TEXT, body TEXT, updated TEXT);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, skill_id TEXT, action TEXT, body TEXT, created TEXT);''')
    return c

def snapshot():
    with db() as c:
        materials = [dict(r) for r in c.execute('SELECT * FROM materials ORDER BY created DESC')]
        skills = [{**dict(r), 'body':json.loads(r['body'])} for r in c.execute('SELECT * FROM skills ORDER BY updated DESC')]
        events = [dict(r) for r in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]
    return dict(materials=materials, skills=skills, events=events, categories=CATEGORIES)

def github_url(value):
    u=urlparse(value.strip())
    if u.scheme!='https' or u.hostname!='github.com' or u.username or u.password or u.port or len(u.path.strip('/').split('/'))<2:
        raise ValueError('请提供完整的 HTTPS GitHub 仓库或文件链接。')
    return 'https://github.com'+u.path.rstrip('/')

def intake(payload):
    note=str(payload.get('note',''))[:4000]
    sources=[]
    for line in payload.get('links','').splitlines():
        if line.strip(): sources.append(('link',github_url(line),None))
    files=payload.get('images',[])
    if len(files)>8: raise ValueError('每次最多 8 张图片。')
    for f in files:
        raw=base64.b64decode(f['data'],validate=True)
        if len(raw)>8*1024*1024: raise ValueError('每张图片最大 8 MB。')
        if raw.startswith(b'\x89PNG\r\n\x1a\n'): ext='.png'
        elif raw.startswith(b'\xff\xd8\xff'): ext='.jpg'
        elif raw[:4]==b'RIFF' and raw[8:12]==b'WEBP': ext='.webp'
        else: raise ValueError('仅支持 PNG、JPEG、WebP 图片。')
        import hashlib
        sources.append(('image',hashlib.sha256(raw).hexdigest()+ext,raw))
    if not sources: raise ValueError('请填写链接或添加图片。')
    added=[]
    with db() as c:
        for kind,source,raw in sources:
            found=c.execute('SELECT id FROM materials WHERE source=?',(source,)).fetchone()
            if found: added.append(dict(id=found['id'],duplicate=True));continue
            mid=uuid.uuid4().hex
            if raw:
                (DATA/'uploads').mkdir(exist_ok=True)
                (DATA/'uploads'/source).write_bytes(raw)
            c.execute('INSERT INTO materials VALUES(?,?,?,?,?,?)',(mid,kind,source,note,'待识别' if kind=='image' else '待分析',now()))
            added.append(dict(id=mid,duplicate=False))
    return added

def save_analysis(p):
    required=['material_id','title','category','source_url','revision','skill_path','kind','summary','purpose','inputs_outputs','workflow','examples','dependencies','limitations','compatibility','license','evidence']
    if any(k not in p for k in required): raise ValueError('缺少分析字段：'+', '.join(k for k in required if k not in p))
    if p['category'] not in CATEGORIES: raise ValueError('分类无效')
    if p['kind'] not in ['skill','reference','tool','unverified']: raise ValueError('类型须为 skill/reference/tool/unverified')
    github_url(p['source_url'])
    sid=p.get('id') or uuid.uuid4().hex
    with db() as c:
        if not c.execute('SELECT 1 FROM materials WHERE id=?',(p['material_id'],)).fetchone(): raise ValueError('素材不存在')
        old=c.execute('SELECT * FROM skills WHERE id=?',(sid,)).fetchone()
        if old and old['status']=='已接入': raise ValueError('已接入版本保留，请另建版本记录')
        c.execute('INSERT OR REPLACE INTO skills VALUES(?,?,?,?,?,?,?)',(sid,p['material_id'],p['title'],p['category'],{'skill':'备选','reference':'参考资料','tool':'工具备选','unverified':'来源待核实'}[p['kind']],json.dumps(p,ensure_ascii=False),now()))
        c.execute('UPDATE materials SET status=? WHERE id=?',('来源待核实' if p['kind']=='unverified' else '已分析',p['material_id']))
        c.execute('INSERT INTO events(skill_id,action,body,created) VALUES(?,?,?,?)',(sid,'分析录入',json.dumps(p,ensure_ascii=False),now()))
    return sid

def action(p):
    sid=p['id']; act=p['action']
    with db() as c:
        row=c.execute('SELECT * FROM skills WHERE id=?',(sid,)).fetchone()
        if not row: raise ValueError('条目不存在')
        body=json.loads(row['body'])
        if act=='approve':
            if row['status'] not in ['备选','接入失败']: raise ValueError('当前状态不能确认接入')
            if body['kind']!='skill' or not body.get('install_ready') or not body.get('revision') or not body.get('skill_path'): raise ValueError('尚未完成接入适配检查')
            status='已确认 · 待执行'
        elif act=='withdraw':
            if row['status']!='已确认 · 待执行': raise ValueError('仅待执行请求可撤回')
            status='备选'
        else: raise ValueError('未知操作')
        c.execute('UPDATE skills SET status=?,updated=? WHERE id=?',(status,now(),sid))
        c.execute('INSERT INTO events(skill_id,action,body,created) VALUES(?,?,?,?)',(sid,act,json.dumps({'source_url':body['source_url'],'revision':body['revision'],'skill_path':body['skill_path']},ensure_ascii=False),now()))
    return status

def record_result(p):
    if not p.get('evidence') or not p.get('revision'): raise ValueError('必须提供执行凭据与版本')
    with db() as c:
        r=c.execute('SELECT * FROM skills WHERE id=?',(p['id'],)).fetchone()
        if not r or r['status']!='已确认 · 待执行': raise ValueError('没有有效的待执行确认')
        b=json.loads(r['body'])
        if b['revision']!=p['revision']: raise ValueError('结果版本与确认不一致')
        if p.get('success'):
            target=Path(p['installed_path']).resolve()
            if not (target/'SKILL.md').is_file(): raise ValueError('安装路径缺少 SKILL.md')
            if not p.get('verified'): raise ValueError('尚未完成验证')
        status='已接入' if p.get('success') else '接入失败'
        b['installation_result']=p
        c.execute('UPDATE skills SET status=?,body=?,updated=? WHERE id=?',(status,json.dumps(b,ensure_ascii=False),now(),p['id']))
        c.execute('INSERT INTO events(skill_id,action,body,created) VALUES(?,?,?,?)',(p['id'],status,json.dumps(p,ensure_ascii=False),now()))
    return status

class Handler(BaseHTTPRequestHandler):
    def send(self,status,body,kind='application/json; charset=utf-8'):
        if not isinstance(body,bytes): body=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-ancestors 'none'");self.end_headers();self.wfile.write(body)
    def trusted(self):
        expected=f'127.0.0.1:{self.server.server_port}'
        return self.headers.get('Host')==expected and self.headers.get('Origin') in [None,'http://'+expected]
    def do_GET(self):
        if not self.trusted(): return self.send(403,{'error':'仅允许本机来源'})
        path=urlparse(self.path).path
        if path=='/api/state':return self.send(200,snapshot())
        if path.startswith('/uploads/'):
            name=path.removeprefix('/uploads/')
            if '/' in name or '\\' in name or not name or name.startswith('.'):return self.send(404,{'error':'不存在'})
            file=DATA/'uploads'/name
            if file.is_file():return self.send(200,file.read_bytes(),{'.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp'}.get(file.suffix,'application/octet-stream'))
        pages={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if path in pages:
            file,kind=pages[path];return self.send(200,(ROOT/file).read_bytes(),kind)
        self.send(404,{'error':'不存在'})
    def do_POST(self):
        if not self.trusted() or self.headers.get('Content-Type')!='application/json':return self.send(403,{'error':'请求来源或格式不允许'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>90*1024*1024:raise ValueError('素材过大')
            p=json.loads(self.rfile.read(size))
            if self.path=='/api/intake':result=intake(p)
            elif self.path=='/api/action':result=action(p)
            else:return self.send(404,{'error':'不存在'})
            self.send(200,{'result':result})
        except (ValueError,KeyError,TypeError) as e:self.send(400,{'error':str(e)})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['serve','list','intake','analyze','result']);parser.add_argument('--file');parser.add_argument('--port',type=int,default=8769);args=parser.parse_args()
    if args.command=='serve':
        db().close(); server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);print(f'http://127.0.0.1:{args.port}',flush=True);server.serve_forever()
    elif args.command=='list':print(json.dumps(snapshot(),ensure_ascii=False,indent=2))
    else:
        p=json.loads(Path(args.file).read_text()); result={'intake':intake,'analyze':save_analysis,'result':record_result}[args.command](p);print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
