# -*- coding: utf-8 -*-
import re, html, os

BASE = "Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/VNW/14_延伸任务_P&L分析"
OUT  = "Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/VNW/99_汇报产出/流程Owner汇报_P&L场景_PNL-001_v1.2.html"

CSS = """
body{font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif;margin:0;background:#f2f5f9;color:#152a45;line-height:1.7}
.wrap{max-width:1050px;margin:0 auto;padding:22px 14px 80px}
.mast{background:linear-gradient(135deg,#0b2d4b,#1667a8);color:#fff;padding:26px 30px;border-radius:18px;margin-bottom:20px}
.mast h1{margin:0;font-size:22px}.mast .tag{margin-top:8px;font-size:13px;opacity:.9}.mast .meta{margin-top:12px;font-size:12px;opacity:.85}
section{background:#fff;border:1px solid #dbe2ea;border-radius:16px;padding:20px 24px;margin-bottom:16px}
h1{font-size:21px}h2{font-size:18px;color:#0b2d4b;border-left:5px solid #1667a8;padding-left:12px;margin:22px 0 12px}
h3{font-size:15px;color:#1667a8;margin:16px 0 8px}h4{font-size:13.5px;color:#0b2d4b;margin:12px 0 6px}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:8px 0}
th{background:#0b2d4b;color:#fff;padding:7px 9px;text-align:left}
td{padding:7px 9px;border-bottom:1px solid #e2e8f0;vertical-align:top}
tr:nth-child(even) td{background:#f8fafd}
blockquote{background:#eef4fb;border-left:4px solid #1667a8;padding:9px 13px;margin:10px 0;border-radius:6px;font-size:13px}
ul,ol{padding-left:20px;margin:6px 0}li{margin:3px 0;font-size:13px}
code{background:#eef2f7;padding:1px 5px;border-radius:4px;font-size:12px}
a{color:#1667a8;text-decoration:none}a:hover{text-decoration:underline}
hr{border:none;border-top:1px solid #dbe2ea;margin:16px 0}
.toc{columns:2;column-gap:26px;font-size:13px}.toc li{margin:2px 0}
"""

def inline(s):
    s = html.escape(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'\*(.+?)\*', r'<i>\1</i>', s)
    s = re.sub(r'`([^`]+?)`', r'<code>\1</code>', s)
    return s

def split_row(row):
    if row.startswith('|') and row.endswith('|'):
        row = row[1:-1]
    parts = [] ; buf = '' ; depth = 0
    for ch in row:
        if ch == '|':
            if depth == 0:
                parts.append(buf.strip()); buf = ''
            else:
                buf += ch
        elif ch == '`':
            depth = 1 - depth
            buf += ch
        else:
            buf += ch
    parts.append(buf.strip())
    return parts

def md_to_html(txt):
    out = []
    lines = txt.split('\n')
    i = 0
    in_table = False; in_list = None; in_bq = False
    table_rows = []
    def flush_table():
        nonlocal table_rows, in_table
        if not table_rows: return
        head = split_row(table_rows[0])
        out.append('<table><thead><tr>' + ''.join('<th>%s</th>'%inline(c) for c in head) + '</tr></thead><tbody>')
        for r in table_rows[1:]:
            out.append('<tr>' + ''.join('<td>%s</td>'%inline(c) for c in split_row(r)) + '</tr>')
        out.append('</tbody></table>')
        table_rows = []; in_table = False
    while i < len(lines):
        line = lines[i]
        if line.startswith('|'):
            if not in_table:
                in_table = True; table_rows = []
            stripped = line.replace('|','').replace(':',' ').replace('-',' ').strip()
            if set(stripped) <= set(' '):
                i += 1; continue
            table_rows.append(line); i += 1; continue
        if in_table:
            flush_table()
        hm = re.match(r'^(#{1,4})\s+(.*)$', line)
        if hm:
            lvl = len(hm.group(1))
            t = inline(hm.group(2))
            out.append('<h%d>%s</h%d>' % (lvl, t, lvl)); i += 1; continue
        if line.startswith('>'):
            c = re.sub(r'^>\s?', '', line)
            if not in_bq:
                out.append('<blockquote>'); in_bq = True
            out.append(inline(c) + '<br>')
            i += 1
            if i >= len(lines) or not lines[i].startswith('>'):
                out.append('</blockquote>'); in_bq = False
            continue
        if re.match(r'^\s*[-*]\s+', line):
            if in_list != 'ul':
                out.append('<ul>'); in_list = 'ul'
            out.append('<li>' + inline(re.sub(r'^\s*[-*]\s+','',line)) + '</li>'); i += 1; continue
        if re.match(r'^\s*\d+\.\s+', line):
            if in_list != 'ol':
                out.append('<ol>'); in_list = 'ol'
            out.append('<li>' + inline(re.sub(r'^\s*\d+\.\s+','',line)) + '</li>'); i += 1; continue
        if in_list and line.strip()=='':
            out.append('</'+in_list+'>'); in_list=None; i+=1; continue
        if re.match(r'^\s*(---+|\*\*\*+)\s*$', line):
            out.append('<hr>'); i+=1; continue
        if line.strip()=='':
            i += 1; continue
        out.append('<p>' + inline(line) + '</p>')
        i += 1
    if in_table: flush_table()
    if in_list: out.append('</'+in_list+'>')
    return '\n'.join(out)

files = [
    (os.path.join(BASE,"流程Owner汇报_主文_master_v1.2.md"), "master"),
    (os.path.join(BASE,"任务书落地指引_08-10至08-11/指引1_启动与接口对齐_v1.md"), "guide1"),
    (os.path.join(BASE,"任务书落地指引_08-10至08-11/指引2_永明TA流程底稿_v1.md"), "guide2"),
    (os.path.join(BASE,"任务书落地指引_08-10至08-11/指引3_转介流程底稿_v1.md"), "guide3"),
    (os.path.join(BASE,"任务书落地指引_08-10至08-11/指引4_三张BM卡审核_v1.md"), "guide4"),
]
body = []
for path, aid in files:
    with open(path, encoding='utf-8') as f:
        h = md_to_html(f.read())
    h = re.sub(r'\[指引\d[^\]]*\]\([^)]*\)', '指引全文见下方', h)
    body.append('<section id="%s">\n%s\n</section>' % (aid, h))

page = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>流程 Owner 汇报 · P&L PNL-001 · master v1.2 · 附4份任务书落地指引</title>
<style>%s</style></head><body><div class="wrap">
<div class="mast"><h1>流程 Owner 汇报 · P&L 定期核算（PNL-001）<br><span style="font-size:14px;opacity:.85">master v1.2 · 对位执行计划 v1.9 流程部分 · 附 4 份任务书落地指引</span></h1>
<div class="tag">主体：流程 Owner（赵琦 Jasper）｜PMO：TERRESA｜升级：Mark｜协作：财务 Roy/Chaya · 产品 连总 · 数据 Carrie · HR 袁林</div>
<div class="meta">本周（08/10-08/11）：永明TA / 转介两试点流程底稿 + 三张候选业务模型卡（BM-TRN/BM-MKT/BM-REF）流程侧审核</div></div>
<div class="toc"><b>目录</b><ul>
<li><a href="#master">§A 定位（对位执行计划 v1.9）</a></li>
<li><a href="#guide1">指引1 启动与接口对齐（08/10 EOD）</a></li>
<li><a href="#guide2">指引2 永明TA流程底稿（08/11 13:00）</a></li>
<li><a href="#guide3">指引3 转介流程底稿（08/11 13:00）</a></li>
<li><a href="#guide4">指引4 三张BM卡审核（08/11 15:00）</a></li>
</ul></div>
%s
<div style="font-size:11px;color:#5d6b7e;background:#fff;border:1px solid #dbe2ea;border-radius:12px;padding:12px 16px;margin-top:8px">
<b>依据与边界</b>：本文为 VNW 延伸任务派生产物，不写回 P&L 专案、不改 VNW 权威源。对位执行计划 v1.9（§6.1 分类轴/§6.2 候选模型卡/§6.3 EA价值流/WS1采集验证）与任务书 v1.3（5 任务/边界/依赖/C-01~C-05）。业务事实处标「待确认：对应 Owner/日期」；财务口径标「待口径冻结/待财务负责人确认」；Gate 过门需人工确证。</div>
</div></body></html>""" % (CSS, ''.join(body))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(page)
print("OK", OUT, os.path.getsize(OUT), "bytes")
print("sections:", page.count('<section id='), "tables:", page.count('<table>'))
