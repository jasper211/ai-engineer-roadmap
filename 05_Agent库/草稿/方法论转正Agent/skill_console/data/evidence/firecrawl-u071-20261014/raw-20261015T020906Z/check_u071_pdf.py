from pathlib import Path
import json,subprocess,re,difflib
from pypdf import PdfReader
from PIL import Image,ImageOps,ImageDraw
root=Path('/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/方法论转正Agent/skill_console/data/evidence/firecrawl-u071-20261014');out=root/'raw-20261015T020906Z'
pages=[{'page':i+1,'text':p.extract_text()} for i,p in enumerate(PdfReader(out/'source.pdf').pages)]
(out/'pages.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2))
md=(root/'anonymous-20261014T095208Z/1-content.md').read_text()
norm=lambda s: re.findall(r'[a-z0-9]+',re.sub('<[^>]*>','',s).lower())
a=norm('\n'.join(p['text'] for p in pages));b=norm(md);matcher=difflib.SequenceMatcher(None,a,b,autojunk=False)
changes=[{'type':t,'pdf':' '.join(a[i:j]),'markdown':' '.join(b[k:l])} for t,i,j,k,l in matcher.get_opcodes() if t!='equal']
(out/'text-diff.json').write_text(json.dumps(changes,indent=2))
print('PAGES',len(pages),'TOKENS',len(a),len(b),'RATIO',matcher.ratio());print(json.dumps(changes)[:8000])
for p in pages: print('PAGE',p['page'],'END',p['text'][-1200:])
subprocess.run(['pdftoppm','-scale-to','1500','-png',str(out/'source.pdf'),str(out/'page')],check=True)
imgs=[Image.open(p).convert('RGB') for p in sorted(out.glob('page-*.png'))]
thumbs=[]
for n,im in enumerate(imgs):
 im.thumbnail((650,930));tile=Image.new('RGB',(670,970),'white');tile.paste(im,((670-im.width)//2,30));ImageDraw.Draw(tile).text((10,10),f'PAGE {n+1}',fill='black');thumbs.append(tile)
canvas=Image.new('RGB',(2010,1940),'#bbb')
for n,im in enumerate(thumbs):canvas.paste(im,((n%3)*670,(n//3)*970))
canvas.save(out/'contact-sheet.png')
