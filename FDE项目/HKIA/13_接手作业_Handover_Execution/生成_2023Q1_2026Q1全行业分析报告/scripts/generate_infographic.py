#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os
from pathlib import Path
BASE=Path("/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/FDE项目/HKIA/13_接手作业_Handover_Execution/生成_2023Q1_2026Q1全行业分析报告")
S=BASE/"scripts";R=BASE/"report"
DATA=json.load(open(S/"data"/"report_data_2023_2026Q1.json",encoding="utf-8"))
CH=json.load(open(S/"data"/"channel_data_2023_2026Q1.json",encoding="utf-8"))
Q=["2023Q1","2024Q1","2025Q1","2026Q1"]
NB_S="NB_IND_TOTAL_SINGLE_PREMIUM";NB_A="NB_IND_TOTAL_ANNUALIZED_PREMIUM"
def vy(q,m):return DATA["market"][m][q]["value"]/1e5
def tot(q):return vy(q,NB_S)+vy(q,NB_A)
def real(q):return [r for r in CH["quarters"][q]["insurers"] if r["entity"]!="Market Total" and not r["entity"].startswith("註") and r["entity"]]
def nm(r):return r['entity_zh'] if r['entity_zh'] else r['entity']
def chs(q):
    ins=real(q);ks=["agents","banks","brokers","direct","others"]
    tp={k:sum((r['channels'][k][0] or 0)+(r['channels'][k][1] or 0) for r in ins) for k in ks}
    ap={k:sum((r['channels'][k][1] or 0) for r in ins) for k in ks}
    st=sum(tp.values());sa=sum(ap.values())
    return {k:dict(t=tp[k]/1e5,tp=tp[k]/st*100 if st else 0,a=ap[k]/1e5,ap=ap[k]/sa*100 if sa else 0) for k in ks}
def broc(q):return sum((r['channels']['brokers'][1] or 0) for r in real(q))/1e5
def comp(q):
    ins=real(q)
    data=[]
    for r in ins:
        ch=r['channels'];c=ch['total']
        data.append(dict(e=r['entity'],nm=nm(r),tot=((c[0] or 0)+(c[1] or 0))/1e5,
                         ape=(c[1] or 0)/1e5,si=(c[0] or 0)/1e5,
                         bro=(ch['brokers'][1] or 0)/1e5))
    return data
C26=comp("2026Q1")
def rankof(fn,metric,n=10):
    arr=[r for r in C26 if r[metric]>0];arr.sort(key=lambda r:-r[metric])
    totm=sum(r[metric] for r in C26)
    out=""
    for i,r in enumerate(arr[:n],1):
        top="class='top'" if i<=5 else ""
        out+=f"<tr {top}><td class='rank'>{i}</td><td>{r['nm']}</td><td><b>{r[metric]:,.1f}</b>億</td><td>{r[metric]/totm*100:.1f}%</td></tr>"
    return out
def dimsec(no,title,metric,note):
    arr=[r for r in C26 if r[metric]>0];arr.sort(key=lambda r:-r[metric]);top5=sum(r[metric] for r in arr[:5]);totm=sum(r[metric] for r in C26)
    tag=f"Top5 合計 {top5/totm*100:.0f}%"
    return f"<section class='sec'><div class='sechead'><span class='no'>{no}</span><h2>{title}</h2><span class='tag'>{tag}</span></div><div class='lead'>{note}</div><table><tr><th>#</th><th>公司</th><th>2026Q1</th><th>市佔</th></tr>{rankof(None,metric)}</table><div class='foot'><span>來源：IA Table L1(channel) 公司級計算</span><span>個險新單總保費 / 標準 / 整付 / 經紀</span></div></section>"
T0=tot("2026Q1");T1=tot("2025Q1");YOY=(T0/T1-1)*100;NET=T0-T1
S26=vy("2026Q1",NB_S);A26=vy("2026Q1",NB_A);S25=vy("2025Q1",NB_S);A25=vy("2025Q1",NB_A)
C25=chs("2026Q1");C23=chs("2023Q1")
brs=[broc(q) for q in Q]
bre=sorted([r for r in C26 if r['bro']>0],key=lambda r:-r['bro'])[:10];bt=sum(r['bro'] for r in C26)

css=open(os.devnull).read() if False else None
# 复用同样 CSS
css="""*{box-sizing:border-box}body{margin:0;background:#eef2f7;color:#17233b;font-family:-apple-system,"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;line-height:1.62;font-size:14.5px}
nav{position:sticky;top:0;z-index:40;background:rgba(14,64,120,.97);padding:8px 12px;display:flex;gap:4px;overflow-x:auto;border-bottom:1px solid #cfe0f0}
nav a{padding:3px 10px;border-radius:14px;white-space:nowrap;color:#eaf2fb;font-size:12px;text-decoration:none}nav a:hover{background:#fff;color:#0e4078}
.sec{max-width:1100px;margin:20px auto;background:#fff;border-radius:14px;box-shadow:0 3px 18px rgba(12,40,80,.08);padding:32px 40px;page-break-after:always}
.sechead{display:flex;align-items:center;gap:12px;border-bottom:2px solid #0e4078;padding-bottom:10px;margin-bottom:20px}
.sechead .no{background:#0e4078;color:#fff;min-width:36px;height:36px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;padding:0 10px}
.sechead h2{margin:0;font-size:21px;color:#0e4078;flex:1}.sechead .tag{font-size:11px;color:#5a6b7f;background:#eef4fb;padding:3px 11px;border-radius:14px}
.lead{background:#eef5fc;border-left:4px solid #1f7ab6;padding:11px 15px;border-radius:4px;margin:13px 0;color:#24405f;font-size:14px}.lead b{color:#0e4078}
h3.bs{font-size:15.5px;color:#33415c;border-left:4px solid #c8860a;padding-left:9px;margin:22px 0 9px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px;margin:15px 0}
.kpi{background:linear-gradient(160deg,#f7fafd,#e9f1f9);border-top:3px solid #0e4078;border-radius:10px;padding:12px 15px}
.kpi .k{font-size:11px;color:#5a6b7f;letter-spacing:.3px}.kpi .v{font-size:25px;font-weight:800;margin:2px 0;font-variant-numeric:tabular-nums}.kpi .v small{font-size:12px;font-weight:600;color:#5a6b7f}.kpi .d{font-size:12px}.kpi .d.up{color:#1e7d4f}
.hero{text-align:center;padding:14px 0 4px}.hero .kicker{color:#c8860a;letter-spacing:5px;font-weight:700;font-size:12px}.hero h1{font-size:31px;margin:8px 0;color:#0e4078}
.hero .num{font-size:62px;font-weight:900;color:#0e4078;letter-spacing:1px;line-height:1.05}.hero .num small{font-size:20px;font-weight:700;color:#33415c}.hero .yoy{font-size:34px;font-weight:900;color:#c0392b;margin-top:6px}.hero .sub{font-size:14px;color:#5a6b7f;margin-top:6px}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13.2px}th,td{padding:8px 10px;border-bottom:1px solid #e6ecf3;text-align:right}th{background:#f2f6fb;color:#0e4078;font-weight:700}th:first-child,td:first-child{text-align:left}tr:hover td{background:#f8fafd}td.top{background:#fff6e8;font-weight:700}.rank{font-weight:800;color:#0e4078}
.bar-row{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:12.5px}.bar-lbl{width:130px;text-align:right;color:#33415c;white-space:nowrap}.bar-track{flex:1;background:#eef1f6;border-radius:6px;height:20px;overflow:hidden}.bar-fill{height:100%;background:linear-gradient(90deg,#1f7ab6,#0e4078);border-radius:6px}.bar-val{width:150px;font-variant-numeric:tabular-nums}
.chwrap{display:grid;grid-template-columns:230px 1fr;gap:22px;align-items:center;margin:12px 0}.donut{width:200px;height:200px;border-radius:50%;margin:0 auto}.legend{font-size:13px}.legend .li{display:flex;align-items:center;gap:9px;margin:7px 0}.legend .sw{width:15px;height:15px;border-radius:4px;flex:none}.legend b{font-size:14px}.legend small{color:#5a6b7f;margin-left:auto}
.insight{background:#eef5fc;border-left:4px solid #1f7ab6;border-radius:5px;padding:11px 15px;margin:12px 0}.insight b{color:#0e4078}
.danger{background:#fdecea;border:1px solid #f0c6c0;border-left:4px solid #c0392b;border-radius:5px;padding:12px 16px;font-size:13.5px;margin:12px 0}.code{background:#f3f6fa;padding:1px 6px;border-radius:4px;font-family:monospace;font-size:11px}
.foot{display:flex;justify-content:space-between;color:#8a97a8;font-size:10.5px;border-top:1px solid #e6ecf3;margin-top:20px;padding-top:9px}
@media print{nav{display:none}.sec{margin:0;box-shadow:none;border-radius:0}}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}
"""
def page(sid,body):return f"<section class='sec' id='{sid}'>{body}<div class='foot'><span>香港個人長期保險 · 2026Q1 信息圖式分析</span><span>provisional · 數據源：IA 長期業務統計</span></div></section>"
def HH(no,t,tag=""):return f"<div class='sechead'><span class='no'>{no}</span><h2>{t}</h2><span class='tag'>{tag}</span></div>"

P=[]
nav="<nav><a href='#hero'>引言</a><a href='#trend'>數據驗證</a><a href='#d1'>①總保費</a><a href='#d2'>②標準</a><a href='#d3'>③大額</a><a href='#d4'>④經紀</a><a href='#channel'>渠道結構</a><a href='#apb'>件均</a><a href='#pay'>繳費結構</a><a href='#dash'>看板</a><a href='#insight'>本質洞察</a></nav>"

# 英雄
P.append(page("hero",f"""<div class='hero'><div class='kicker'>香港個人保險 · 2026Q1</div><h1>個人新單保費創歷史新高</h1><div class='num'>{T0:,.0f}<small> 億港元</small></div><div class='yoy'>同比 +{YOY:.0f}%</div><div class='sub'>淨增 ≈ {NET:,.0f} 億港元 · 整付 {S26:,.0f} 億 + 年度化(APE) {A26:,.0f} 億</div></div>
<div class='kpis'>
<div class='kpi'><div class='k'>整付保費</div><div class='v'>{S26:,.0f}<small>億</small></div><div class='d up'>+{S26/S25*100-100:.0f}%</div></div>
<div class='kpi'><div class='k'>年度化 APE</div><div class='v'>{A26:,.0f}<small>億</small></div><div class='d up'>+{A26/A25*100-100:.0f}%</div></div>
<div class='kpi'><div class='k'>總保費</div><div class='v'>{T0:,.0f}<small>億</small></div></div>
<div class='kpi'><div class='k'>經紀渠道佔比</div><div class='v'>{C25['brokers']['tp']:.1f}<small>%</small></div></div>
<div class='kpi'><div class='k'>同季 YoY</div><div class='v' style='color:#c0392b'>+{YOY:.0f}<small>%</small></div></div></div>
<div class='lead'><b>結論前置：</b>2026Q1 個人新單總保費 <b>{T0:,.0f}億</b>，同比 <b>+{YOY:.0f}%</b>、淨增 <b>{NET:,.0f}億</b>，創歷史新高。破題主引擎是 <b>經紀渠道與整付保費的雙重爆發</b>——經紀渠道總保費佔比已達 <b>{C25['brokers']['tp']:.1f}%</b>（僅次於銀行）。</div>"""))

# 趋势
s=[vy(q,NB_S) for q in Q];a=[vy(q,NB_A) for q in Q];t=[s[i]+a[i] for i in range(4)];mx=max(t)
tr=""
for i,q in enumerate(Q):
    hot="style='color:#c0392b;font-weight:800'" if q=="2026Q1" else ""
    bg="background:#c0392b" if q=="2026Q1" else ""
    tr+=f"<tr><td>{q}</td><td>{s[i]:,.1f}</td><td>{a[i]:,.1f}</td><td><b {hot}>{t[i]:,.0f}</b></td><td><div class='bar-track'><div class='bar-fill' style='width:{t[i]/mx*100:.0f}%;{bg}'></div></div></td></tr>"
P.append(page("trend",f"""{HH('01','數據驗證：同季趨勢','折線圖→表格確認')}
<div class='lead'>先看<b>趨勢</b>直觀感知增長，再讀<b>表格</b>確認精確數字，形成<b>「圖感知 → 表確認」</b>雙重驗證。</div>
<div class='kpis'>{''.join(f"<div class='kpi'><div class='k'>{q}{'🔥' if q=='2026Q1' else ''}</div><div class='v' style='{('color:#c0392b' if q=='2026Q1' else '')}'>{t[i]:,.0f}</div></div>" for i,q in enumerate(Q))}</div>
<table><tr><th>季度</th><th>整付(億)</th><th>年度化(億)</th><th>總保費(億)</th><th>視覺</th></tr>{tr}</table>
<div class='insight'><b>洞察：</b>三年同季翻倍增長。整付由 <b>{s[0]:,.1f}→{s[3]:,.1f}億（+{s[3]/s[0]*100-100:.0f}%）</b>是規模主引擎；年度化APE同期 {a[0]:,.1f}→{a[3]:,.1f}億（+{a[3]/a[0]*100-100:.0f}%）。</div>"""))

# 四维度（从 channel 公司级计算）
P.append((f"<section class='sec' id='d1'>{HH('02','① 總保費排名（整付+年度化）','Top5 集中度')}<div class='lead'>以<b>個險新單總保費（整付+年度化）</b>衡量公司整體規模份額。</div><table><tr><th>#</th><th>公司</th><th>總保費</th><th>市佔</th></tr>"+rankof(None,'tot')+"</table><div class='foot'><span>公司級總保費（IA Table L1 channel）</span></div></section>"))
P.append((f"<section class='sec' id='d2'>{HH('03','② 標準保費排名（年度化 APE）','價值質量')}<div class='lead'>以<b>年度化標準保費(APE)</b>衡量業務價值，剔除整付一次性流入干擾，看「真實業務質量」。</div><table><tr><th>#</th><th>公司</th><th>APE</th><th>市佔</th></tr>"+rankof(None,'ape')+"</table></section>"))
P.append((f"<section class='sec' id='d3'>{HH('04','③ 大額整付排名（整付保費）','資金配置')}<div class='lead'>統計<b>大額整付保單</b>的資金捕獲能力，反映高淨值一筆過配置需求的分佈。</div><table><tr><th>#</th><th>公司</th><th>整付</th><th>市佔</th></tr>"+rankof(None,'si')+"</table></section>"))

# 经纪
brbody=""
for i,r in enumerate(bre,1):
    top="class='top'" if i<=5 else ""
    brbody+=f"<tr {top}><td class='rank'>{i}</td><td>{r['nm']}</td><td><b>{r['bro']:,.2f}</b>億</td><td>{r['bro']/bt*100:.1f}%</td></tr>"
P.append(page("d4",f"""{HH('05','④ 經紀渠道排名（經紀年化 APE）','本次新增')}
<div class='lead'>統計<b>通過經紀渠道(Brokers)達成的年化保費(APE)</b>公司排名。<b>經紀是唯一在高基數下仍快速增長的渠道</b>：2026Q1 市場經紀年化約 <b>{brs[3]:,.0f}億</b>，相對 2023Q1 <b>{brs[0]:,.0f}億 +{brs[3]/brs[0]*100-100:.0f}%</b>。</div>
<div class='kpis'>{''.join(f"<div class='kpi'><div class='k'>{q}</div><div class='v'>{brs[i]:,.0f}<small>億</small></div></div>" for i,q in enumerate(Q))}</div>
<table><tr><th>#</th><th>公司</th><th>經紀年化(億)</th><th>佔經紀市場</th></tr>{brbody}</table>
<div class='insight'><b>洞察：</b>經紀年化 Top 由 <b>{bre[0]['nm']}</b>、<b>{bre[1]['nm']}</b> 領跑——以經紀/銀行轉介見長的國際壽險受益最明顯，與自有代理隊分化。</div>"""))

# 渠道
seg="";acc=0;scols={"agents":"#c8860a","banks":"#0e4078","brokers":"#c0392b","direct":"#6b54a3","others":"#b8c0cc"} ;lb={"agents":"代理","banks":"銀行","brokers":"經紀","direct":"直接","others":"其他"}
for k in scols:
    s0=acc*3.6;e0=(acc+C25[k]['tp'])*3.6;seg+=f"{scols[k]} {s0:.1f}deg {e0:.1f}deg ";acc+=C25[k]['tp']
leg="".join(f"<div class='li'><span class='sw' style='background:{scols[k]}'></span><span>{lb[k]}</span><b>{C25[k]['tp']:.1f}%</b><small>{C25[k]['t']:,.1f}億</small></div>" for k in scols)
chrow=""
for k in ["agents","banks","brokers","direct","others"]:
    chrow+=f"<tr><th>{lb[k]}</th>"+"".join(f"<td>{chs(q)[k]['tp']:.1f}%</td>" for q in Q)+"</tr>"
P.append(page("channel",f"""{HH('06','全渠道結構：經紀已居次席','個險新單 2026Q1')}
<div class='lead'>以<b>個險新單總保費</b>劃分銷售渠道。2026Q1 <b>銀行 {C25['banks']['tp']:.1f}%</b>居首、<b>經紀 {C25['brokers']['tp']:.1f}%</b>次席、代理僅 {C25['agents']['tp']:.1f}%——「銀行→經紀」雙主力格局。</div>
<div class='chwrap'><div class='donut' style='background:conic-gradient({seg});-webkit-mask:radial-gradient(transparent 0 47%,#000 48%);mask:radial-gradient(transparent 0 47%,#000 48%)'></div><div class='legend'>{leg}</div></div>
<h3 class='bs'>四季度渠道總保費佔比演變</h3>
<table><tr><th>渠道</th><th>2023Q1</th><th>2024Q1</th><th>2025Q1</th><th style='color:#c0392b'>2026Q1</th></tr>{chrow}</table>
<div class='danger'><b>重要修正：</b>外部參考信息圖中「代理38.3% / 經紀16.2%」與 IA 原始數據<b>順序相反</b>。本報告以 IA 長表 <span class='code'>Table L1 (channel)</span> 為準：<b>經紀渠道實際已是第二大渠道（{C25['brokers']['tp']:.1f}%）</b>，代理僅 {C25['agents']['tp']:.1f}%。</div>"""))

# 件均
ins=real("2026Q1");ar=[]
for r in ins:
    p=r['policies']['total'];m=r['channels']['total']
    pol=(p[0] or 0)+(p[1] or 0);prem=(m[0] or 0)+(m[1] or 0)
    if pol>=100:ar.append((nm(r),prem/pol,prem/1e5,pol))
hi=sorted(ar,key=lambda x:-x[1])[:5];lo=sorted(ar,key=lambda x:x[1])[:5]
def apt(lst):return "".join(f"<tr><td class='rank'>{i}</td><td>{e}</td><td><b>{v:,.0f}</b>千$</td><td>{pm:,.1f}億</td><td>{pol:,}</td></tr>" for i,(e,v,pm,pol)in enumerate(lst,1))
P.append(page("apb",f"""{HH('07','均件保費：高端 vs 大眾分化','新造件均 2026Q1')}
<div class='lead'>件均 = 新造總保費 ÷ 新造保單數（剔除<100張）。反映<b>客戶投保能力</b>分層。</div>
<div class='kpis'><div class='kpi' style='border-top-color:#c0392b'><div class='k'>最高件均</div><div class='v'>{hi[0][1]/1000:.1f}<small>萬</small></div></div><div class='kpi'><div class='k'>最低件均</div><div class='v'>{lo[0][1]/1000:.1f}<small>萬</small></div></div></div>
<div class='two'><div><h3 class='bs'>件均最高 Top5</h3><table><tr><th>#</th><th>公司</th><th>件均</th><th>總保費</th><th>保單數</th></tr>{apt(hi)}</table></div><div><h3 class='bs'>件均最低 Top5</h3><table><tr><th>#</th><th>公司</th><th>件均</th><th>總保費</th><th>保單數</th></tr>{apt(lo)}</table></div></div>
<div class='insight'><b>洞察：</b>整付為主的高淨值公司件均高；期繳/普惠公司件均低、件數多。市場「高端集中、大眾分散」。</div>"""))

# 缴费
row=""
for i,q in enumerate(Q):
    ti=tot(q);ss=s[i]/ti*100 if ti else 0
    row+=f"<tr><td>{q}</td><td>{s[i]:,.1f}億（{ss:.0f}%）</td><td>{a[i]:,.1f}億</td><td>{ti:,.0f}億</td></tr>"
ps=S26/T0*100
P.append(page("pay",f"""{HH('08','繳費結構：整付是絕對主力','個險新單')}
<div class='lead'>以<b>總保費</b>計，2026Q1 <b>整付佔比約 {ps:.0f}%</b>，反映客戶偏好高資金流動性/一次性配置。</div>
<table><tr><th>季度</th><th>整付</th><th>年度化(APE)</th><th>總保費</th></tr>{row}</table>
<div class='insight'><b>洞察：</b>整付佔比逐年抬升，資金型/配置型需求強於保障型——量價錯位（整付↑、APE增速緩）指向「規模不是價值全部」。</div>"""))

# 看板
cards=[("全港個人新單總保費",f"{T0:,.0f}億","+51% YoY"),("其中·整付",f"{S26:,.0f}億",f"+{S26/S25*100-100:.0f}% YoY"),("其中·年度化APE",f"{A26:,.0f}億",f"+{A26/A25*100-100:.0f}% YoY"),("整付佔比",f"{ps:.0f}%","主力"),("經紀渠道佔比",f"{C25['brokers']['tp']:.1f}%","次席"),("銀行渠道佔比",f"{C25['banks']['tp']:.1f}%","居首")]
kk="".join(f"<div class='kpi'><div class='k'>{a}</div><div class='v'>{b}</div><div class='d up'>{c}</div></div>" for a,b,c in cards)
P.append(page("dash",f"""{HH('09','核心數據看板','Dashboard')}<div class='lead'>關鍵指標一覽，方便轉發傳播。</div><div class='kpis'>{kk}</div>"""))

# 本质
P.append(page("insight",f"""{HH('10','本質洞察：為什麼爆發','數據→根因')}
<div class='lead'>把「震驚數字 → 數據驗證 → 多維拆解」收束為三個層次的本質洞察。</div>
<h3 class='bs'>層一 · 錢從哪來：整付 + 經紀 雙引擎</h3>
<div class='insight'><b>整付驅動規模：</b>2026Q1 整付 <b>{S26:,.0f}億</b>、同比 <b>+{S26/S25*100-100:.0f}%</b>、佔新單規模 <b>{ps:.0f}%</b>——一筆過繳費的資金配置型需求是規模主引擎。</div>
<div class='insight'><b>經紀渠道放大：</b>經紀渠道總保費佔比由 2023Q1 <b>{C23['brokers']['tp']:.0f}%</b>升至 2026Q1 <b>{C25['brokers']['tp']:.1f}%</b>，躍居第二主力；高淨值經紀委託配置是重要通路。</div>
<h3 class='bs'>層二 · 錢的質量：規模與價值的錯位</h3>
<div class='insight'>總保費 <b>+{YOY:.0f}%</b> 大增，但<b>年度化APE僅 {A26:,.0f}億（+{A26/A25*100-100:.0f}%）</b>。規模與標準價值增速落差揭示：<b>創新高主要是整付資金流入，價值化含量並未同步攀升</b>。</div>
<h3 class='bs'>層三 · 誰在受益</h3>
<div class='danger'><b>邊界：</b>本報告限定 <b>個人業務</b>；公司層客戶動機、經紀隊伍構成等屬待外部佐證範圍，不作過度引申。</div>
<div class='lead'><b>一句話：</b>個險規模歷史新高，本質是<b>高淨值資金型整付配置</b>經<b>銀行與經紀雙通道</b>湧入；但規模與標準價值的錯位，是判斷「創新高是否可持續」的關鍵。</div>"""))

html="<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>香港個人長期保險 2026Q1 信息圖式分析</title><style>"+css+"</style></head><body>"+nav+"".join(P)+"</body></html>"
out=R/"香港个人长期保险2026Q1信息图式分析.html"
out.write_text(html,encoding="utf-8")
print("生成:",out, round(os.path.getsize(out)/1024,1),"KB")
