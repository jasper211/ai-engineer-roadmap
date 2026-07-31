#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：把聚合结果渲染成可交互 HTML 看板。

对应 流程设计.md L3-PDA-04。CSS/Chart.js 渲染逻辑直接复用阶段一原型
（业绩数据多维分析看板.html）——那部分本身没有 bug，核实底表时也没发现
视觉/交互层的问题，改的只是数据来源和 footer 的统计口径说明（阶段一原型
硬编码"11条future_dated"，改为动态注入真实数字，不再重蹈硬编码的坑）。

用 __TOKEN__ 占位符 + str.replace 而不是 str.format，因为模板里的 CSS/JS
本身大量使用花括号，用 format 会跟 CSS 规则语法冲突。
"""
import json
from pathlib import Path

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>业绩数据多维分析 · 牌照端视角</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;700;900&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
<style>
  :root{
    --ink:#0e1420;
    --ink-2:#141c2b;
    --card:#182236;
    --card-hi:#1e2b42;
    --line:#2a3650;
    --text:#eef1f0;
    --text-dim:#93a1b8;
    --text-faint:#5f6d87;
    --jade:#2fa88a;
    --jade-soft:rgba(47,168,138,0.16);
    --brass:#c9a15a;
    --brass-soft:rgba(201,161,90,0.16);
    --rose:#c96a5a;
    --rose-soft:rgba(201,106,90,0.14);
    --serif:'Noto Serif SC', serif;
    --sans:'Inter', -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    --mono:'IBM Plex Mono', 'PingFang SC', monospace;
  }
  *{box-sizing:border-box; margin:0; padding:0;}
  body{
    background:
      radial-gradient(ellipse 900px 500px at 12% -10%, rgba(47,168,138,0.10), transparent 60%),
      radial-gradient(ellipse 700px 500px at 100% 0%, rgba(201,161,90,0.08), transparent 55%),
      var(--ink);
    color:var(--text);
    font-family:var(--sans);
    line-height:1.5;
    padding-bottom:80px;
  }
  .wrap{max-width:1240px; margin:0 auto; padding:0 28px;}

  header.hero{
    padding:52px 0 34px;
    border-bottom:1px solid var(--line);
    position:relative;
  }
  .seal{
    position:absolute; right:28px; top:44px;
    width:88px; height:88px; border-radius:50%;
    border:1.5px solid var(--brass);
    display:flex; align-items:center; justify-content:center;
    color:var(--brass); font-family:var(--serif); font-weight:700;
    font-size:12px; letter-spacing:2px; text-align:center;
    opacity:0.85;
  }
  .seal::before{
    content:""; position:absolute; inset:6px; border:1px solid var(--brass); border-radius:50%; opacity:0.5;
  }
  .eyebrow{
    font-family:var(--mono); font-size:12px; letter-spacing:3px; text-transform:uppercase;
    color:var(--jade); margin-bottom:14px; display:flex; align-items:center; gap:10px;
  }
  .eyebrow::before{content:"◆"; font-size:9px;}
  h1{
    font-family:var(--serif); font-weight:900; font-size:40px; letter-spacing:1px;
    color:var(--text); max-width:820px;
  }
  .sub{color:var(--text-dim); font-size:15px; margin-top:12px; max-width:640px;}

  .kpi-row{
    display:grid; grid-template-columns:repeat(5,1fr); gap:1px;
    background:var(--line); border:1px solid var(--line); margin-top:36px; border-radius:4px; overflow:hidden;
  }
  .kpi{background:var(--ink-2); padding:20px 22px;}
  .kpi .label{font-size:12px; color:var(--text-faint); letter-spacing:1px;}
  .kpi .val{font-family:var(--mono); font-weight:600; font-size:24px; margin-top:8px; color:var(--text);}
  .kpi .val small{font-size:13px; color:var(--text-dim); font-weight:400; margin-left:3px;}
  .kpi.accent .val{color:var(--jade);}

  section{padding:56px 0 0;}
  .section-head{display:flex; align-items:baseline; justify-content:space-between; margin-bottom:22px; flex-wrap:wrap; gap:10px;}
  .section-head h2{font-family:var(--serif); font-size:22px; font-weight:700;}
  .section-head .note{font-size:12.5px; color:var(--text-faint); font-family:var(--mono);}
  .idx{color:var(--brass); font-family:var(--mono); font-size:13px; margin-right:10px;}

  .rank-card{background:var(--card); border:1px solid var(--line); border-radius:6px; padding:26px 26px 10px;}
  .rank-row{display:grid; grid-template-columns:180px 1fr 130px; align-items:center; gap:16px; padding:10px 0; border-bottom:1px dashed var(--line);}
  .rank-row:last-child{border-bottom:none;}
  .rank-name{font-size:13.5px; color:var(--text); cursor:pointer; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
  .rank-name .n{color:var(--brass); font-family:var(--mono); margin-right:8px; font-size:12px;}
  .rank-bar-track{height:20px; background:var(--ink-2); border-radius:3px; overflow:hidden; position:relative;}
  .rank-bar-fill{height:100%; background:linear-gradient(90deg, var(--jade), #4fc9a8); border-radius:3px; transition:width .4s ease;}
  .rank-val{font-family:var(--mono); font-size:12.5px; color:var(--text-dim); text-align:right;}

  .chip-row{display:flex; flex-wrap:wrap; gap:10px; margin-bottom:8px;}
  .chip{
    border:1px solid var(--line); background:var(--card); color:var(--text-dim);
    padding:9px 16px; border-radius:20px; font-size:13px; cursor:pointer;
    transition:all .15s ease; font-family:var(--sans); white-space:nowrap;
  }
  .chip:hover{border-color:var(--jade); color:var(--text);}
  .chip.active{background:var(--jade-soft); border-color:var(--jade); color:var(--jade); font-weight:600;}

  .grid2{display:grid; grid-template-columns:1.3fr 1fr; gap:18px; margin-bottom:18px;}
  .grid3{display:grid; grid-template-columns:repeat(3,1fr); gap:18px; margin-bottom:18px;}
  .grid4{display:grid; grid-template-columns:repeat(4,1fr); gap:18px;}
  @media (max-width:900px){ .grid2,.grid3,.grid4{grid-template-columns:1fr;} .kpi-row{grid-template-columns:repeat(2,1fr);} }

  .card{background:var(--card); border:1px solid var(--line); border-radius:6px; padding:20px 22px;}
  .card h3{font-size:13.5px; font-weight:600; color:var(--text-dim); letter-spacing:.3px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center;}
  .card h3 span.tag{font-family:var(--mono); font-size:10.5px; color:var(--text-faint); font-weight:400;}
  .chart-box{position:relative; height:230px;}
  .chart-box.tall{height:280px;}

  .stat-mini{display:flex; flex-direction:column; justify-content:center; height:230px;}
  .stat-mini .big{font-family:var(--mono); font-size:34px; font-weight:600; color:var(--brass);}
  .stat-mini .cap{color:var(--text-faint); font-size:12px; margin-top:6px;}
  .stat-mini .bars{margin-top:18px; display:flex; flex-direction:column; gap:10px;}
  .stat-mini .barline{display:flex; align-items:center; gap:10px; font-size:12px;}
  .stat-mini .barline .lbl{width:64px; color:var(--text-dim); flex-shrink:0;}
  .stat-mini .barline .track{flex:1; height:8px; background:var(--ink-2); border-radius:3px; overflow:hidden;}
  .stat-mini .barline .fill{height:100%; background:var(--brass);}
  .stat-mini .barline .v{width:56px; text-align:right; font-family:var(--mono); color:var(--text-dim); flex-shrink:0;}

  footer{margin-top:70px; padding:30px 0; border-top:1px solid var(--line);}
  footer .cols{display:grid; grid-template-columns:2fr 1fr; gap:40px;}
  footer h4{font-family:var(--serif); font-size:14px; color:var(--brass); margin-bottom:10px;}
  footer p, footer li{font-size:12.5px; color:var(--text-faint); line-height:1.8;}
  footer ul{padding-left:18px;}
  footer .meta{font-family:var(--mono); font-size:11.5px; color:var(--text-faint); text-align:right;}

  ::-webkit-scrollbar{height:6px; width:6px;}
  ::-webkit-scrollbar-thumb{background:var(--line); border-radius:3px;}
</style>
</head>
<body>
<div class="wrap">

  <header class="hero">
    <div class="seal">牌照端<br>数据看板</div>
    <div class="eyebrow">Performance Data · PDA Agent __AGENT_VERSION__</div>
    <h1>业绩数据多维分析<br>牌照端（Issuing Entity）视角</h1>
    <p class="sub">基于业绩数据底表（__SOURCE__，截至 __EXPORT_DATE__ 导出）清洗后的 __RECORDS__ 条有效保单记录，围绕 __ENTITIES__ 家持牌主体构建业务规模、结构、客户、效率四类分析视图。由 PDA Agent 自动清洗聚合生成，已修复阶段一原型的日期类型解析问题。</p>

    <div class="kpi-row" id="kpiRow"></div>
  </header>

  <section>
    <div class="section-head">
      <h2><span class="idx">01</span>牌照端业绩总览</h2>
      <div class="note">按保费（港币口径）降序排列 · 点击任一牌照端可下钻明细</div>
    </div>
    <div class="rank-card">
      <div id="rankList"></div>
    </div>
  </section>

  <section>
    <div class="section-head">
      <h2><span class="idx">02</span>选择牌照端查看明细</h2>
      <div class="note" id="selNote">当前：全部牌照端合计</div>
    </div>
    <div class="chip-row" id="chipRow"></div>
  </section>

  <section>
    <div class="grid2">
      <div class="card">
        <h3>业绩趋势（按签单月份）<span class="tag">PREMIUM · MONTHLY</span></h3>
        <div class="chart-box tall"><canvas id="chartTrend"></canvas></div>
      </div>
      <div class="card">
        <h3>保单状态结构<span class="tag">STATUS GROUP</span></h3>
        <div class="chart-box tall"><canvas id="chartStatus"></canvas></div>
      </div>
    </div>

    <div class="grid3">
      <div class="card">
        <h3>业务类型结构<span class="tag">BUSINESS CATEGORY</span></h3>
        <div class="chart-box"><canvas id="chartBcat"></canvas></div>
      </div>
      <div class="card">
        <h3>市场细分结构<span class="tag">MARKET SEGMENT</span></h3>
        <div class="chart-box"><canvas id="chartMkt"></canvas></div>
      </div>
      <div class="card">
        <h3>产品品类结构<span class="tag">PRODUCT CATEGORY</span></h3>
        <div class="chart-box"><canvas id="chartProd"></canvas></div>
      </div>
    </div>

    <div class="grid4">
      <div class="card">
        <h3>承保保司分布<span class="tag">CARRIER</span></h3>
        <div class="chart-box"><canvas id="chartCarrier"></canvas></div>
      </div>
      <div class="card">
        <h3>客户分群<span class="tag">PI / NONPI</span></h3>
        <div class="chart-box"><canvas id="chartCust"></canvas></div>
      </div>
      <div class="card">
        <h3>币种结构<span class="tag">CURRENCY</span></h3>
        <div class="chart-box"><canvas id="chartCcy"></canvas></div>
      </div>
      <div class="card">
        <div class="stat-mini">
          <div class="cap" style="margin-bottom:2px;">签单→批核平均周期</div>
          <div class="big" id="cycleVal">—</div>
          <div class="cap">天（有批核日期的保单）</div>
          <div class="bars">
            <div class="barline"><div class="lbl">融资单占比</div><div class="track"><div class="fill" id="finFill" style="width:0%"></div></div><div class="v" id="finVal">0%</div></div>
            <div class="barline"><div class="lbl">生效占比</div><div class="track"><div class="fill" id="effFill" style="width:0%; background:var(--jade);"></div></div><div class="v" id="effVal">0%</div></div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <footer>
    <div class="cols">
      <div>
        <h4>数据说明 · Agent 清洗规则</h4>
        <ul>
          <li>原始底表 __RAW_ROWS__ 行，剔除表头残留行 __HEADER_ROWS__ 行，保留有效记录 __RECORDS__ 条</li>
          <li>保单状态归并为三档：生效 / 在途（待批核·pending·排期·已签单·尚欠保费）/ 终止（取消投保·退保·搁置受保·拒保）</li>
          <li>保费口径统一使用 premium 字段（已折算港币），跨币种可比</li>
          <li>signal：company_name 缺失 419 条、issue_date 缺失 704 条、__FUTURE_DATED__ 条签单日期晚于导出日，均为在途保单的合理缺失，建议业务侧复核</li>
          <li>日期字段（res_date/sign_date/submit_date）里混有 Excel 序列号整数，已按序列号规则换算为正确日期，不再静默产出 1970 年附近的错误时间戳（阶段一原型未处理此问题）</li>
          <li>本页由 PDA Agent 每次运行重新清洗生成，不是人工静态快照 — 对应规划中的阶段二（实时同步）与阶段三（知识库问答）尚未接入</li>
        </ul>
      </div>
      <div class="meta">
        SOURCE __SOURCE__<br>
        RECORDS __RECORDS__ / ENTITIES __ENTITIES__<br>
        GENERATED __GENERATED__<br>
        PDA Agent __AGENT_VERSION__ — PHASE 1 OF 3
      </div>
    </div>
  </footer>
</div>

<script>
const DATA = __DATA_JSON__;
const fmtMoney = n => {
  if(n>=100000000) return (n/100000000).toFixed(2)+'亿';
  if(n>=10000) return (n/10000).toFixed(1)+'万';
  return Math.round(n).toLocaleString();
};
const fmtPct = n => (n*100).toFixed(1)+'%';

const PALETTE = ['#2fa88a','#c9a15a','#c96a5a','#5b8fc9','#9a7ec9','#c9c05b','#5bc9c0','#c98fb0','#7ea6c9','#a6c97e','#c98f5b','#8c8c8c'];

function sumAgg(rows){
  return rows.reduce((a,r)=>({premium:a.premium+r.premium, ape:a.ape+r.ape, count:a.count+r.count}), {premium:0,ape:0,count:0});
}

const entityTotals = DATA.entities.map(e => ({
  entity: e,
  ...( DATA.by_entity_all[e] || {premium:0,ape:0,count:0} )
})).sort((a,b)=>b.premium-a.premium);

const grandTotal = sumAgg(Object.values(DATA.by_entity_all));
const effTotal = sumAgg(Object.values(DATA.by_entity_effective));

const kpiRow = document.getElementById('kpiRow');
const kpis = [
  {label:'总保费（港币口径）', val: fmtMoney(grandTotal.premium)},
  {label:'总 APE', val: fmtMoney(grandTotal.ape)},
  {label:'保单总数', val: grandTotal.count.toLocaleString()},
  {label:'生效保单占比', val: fmtPct(effTotal.count/grandTotal.count), accent:true},
  {label:'覆盖牌照端', val: DATA.entities.length + ' 家'},
];
kpiRow.innerHTML = kpis.map(k=>`<div class="kpi ${k.accent?'accent':''}"><div class="label">${k.label}</div><div class="val">${k.val}</div></div>`).join('');

const rankList = document.getElementById('rankList');
const maxPremium = entityTotals[0].premium;
function renderRank(){
  rankList.innerHTML = entityTotals.map((r,i)=>`
    <div class="rank-row" data-entity="${r.entity}">
      <div class="rank-name"><span class="n">${String(i+1).padStart(2,'0')}</span>${r.entity}</div>
      <div class="rank-bar-track"><div class="rank-bar-fill" style="width:${(r.premium/maxPremium*100).toFixed(1)}%"></div></div>
      <div class="rank-val">${fmtMoney(r.premium)} · ${r.count}件</div>
    </div>`).join('');
  rankList.querySelectorAll('.rank-row').forEach(el=>{
    el.addEventListener('click', ()=> selectEntity(el.dataset.entity));
  });
}
renderRank();

const chipRow = document.getElementById('chipRow');
function renderChips(selected){
  const all = [{k:null, label:'全部合计'}, ...DATA.entities.map(e=>({k:e,label:e}))];
  chipRow.innerHTML = all.map(o=>`<div class="chip ${selected===o.k?'active':''}" data-k="${o.k===null?'':o.k}">${o.label}</div>`).join('');
  chipRow.querySelectorAll('.chip').forEach(el=>{
    el.addEventListener('click', ()=> selectEntity(el.dataset.k || null));
  });
}

Chart.defaults.color = '#93a1b8';
Chart.defaults.font.family = "'Inter','PingFang SC',sans-serif";
Chart.defaults.font.size = 11.5;
Chart.defaults.borderColor = '#2a3650';

let charts = {};
function makeDonut(id){
  const ctx = document.getElementById(id);
  return new Chart(ctx, {
    type:'doughnut',
    data:{labels:[], datasets:[{data:[], backgroundColor:PALETTE, borderColor:'#182236', borderWidth:2}]},
    options:{responsive:true, maintainAspectRatio:false, cutout:'62%',
      plugins:{legend:{position:'right', labels:{boxWidth:10, padding:10, font:{size:11}}}}}
  });
}
function makeBar(id, horizontal){
  const ctx = document.getElementById(id);
  return new Chart(ctx, {
    type:'bar',
    data:{labels:[], datasets:[{data:[], backgroundColor:'#2fa88a', borderRadius:3, barThickness:16}]},
    options:{responsive:true, maintainAspectRatio:false, indexAxis: horizontal?'y':'x',
      plugins:{legend:{display:false}},
      scales:{ x:{grid:{color:'#20293c'}}, y:{grid:{display:false}} }}
  });
}
function makeLine(id){
  const ctx = document.getElementById(id);
  return new Chart(ctx, {
    type:'line',
    data:{labels:[], datasets:[{data:[], borderColor:'#2fa88a', backgroundColor:'rgba(47,168,138,0.15)', fill:true, tension:0.35, pointRadius:2}]},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{ x:{grid:{display:false}}, y:{grid:{color:'#20293c'}, ticks:{callback:v=>fmtMoney(v)}} }}
  });
}

charts.trend = makeLine('chartTrend');
charts.status = makeDonut('chartStatus');
charts.bcat = makeBar('chartBcat', true);
charts.mkt = makeBar('chartMkt', true);
charts.prod = makeBar('chartProd', true);
charts.carrier = makeDonut('chartCarrier');
charts.cust = makeDonut('chartCust');
charts.ccy = makeDonut('chartCcy');

function filterAggByEntity(aggDict, entity){
  const out = {};
  for(const k in aggDict){
    const parts = k.split('|');
    const ent = parts[0];
    const sub = parts.slice(1).join('|');
    if(entity && ent !== entity) continue;
    if(!entity){
      if(!out[sub]) out[sub] = {premium:0,ape:0,count:0};
      out[sub].premium += aggDict[k].premium;
      out[sub].ape += aggDict[k].ape;
      out[sub].count += aggDict[k].count;
    } else {
      out[sub] = aggDict[k];
    }
  }
  return out;
}

function updateDonut(chart, subMap, topN){
  let entries = Object.entries(subMap).sort((a,b)=>b[1].premium-a[1].premium);
  if(topN && entries.length>topN){
    const head = entries.slice(0,topN);
    const restSum = entries.slice(topN).reduce((a,[,v])=>a+v.premium,0);
    entries = [...head, ['其他', {premium:restSum}]];
  }
  chart.data.labels = entries.map(([k])=>k);
  chart.data.datasets[0].data = entries.map(([,v])=>v.premium);
  chart.update();
}
function updateBar(chart, subMap){
  const entries = Object.entries(subMap).sort((a,b)=>b[1].premium-a[1].premium);
  chart.data.labels = entries.map(([k])=>k);
  chart.data.datasets[0].data = entries.map(([,v])=>v.premium);
  chart.update();
}

function selectEntity(entity){
  renderChips(entity);
  document.getElementById('selNote').textContent = '当前：' + (entity || '全部牌照端合计');

  const monthMap = {};
  DATA.months.forEach(m=>monthMap[m]=0);
  for(const k in DATA.by_entity_month){
    const parts = k.split('|');
    const ent = parts[0], m = parts[1];
    if(entity && ent!==entity) continue;
    monthMap[m] = (monthMap[m]||0) + DATA.by_entity_month[k].premium;
  }
  charts.trend.data.labels = DATA.months;
  charts.trend.data.datasets[0].data = DATA.months.map(m=>monthMap[m]||0);
  charts.trend.update();

  updateDonut(charts.status, filterAggByEntity(DATA.by_entity_status, entity));
  updateBar(charts.bcat, filterAggByEntity(DATA.by_entity_bcat, entity));
  updateBar(charts.mkt, filterAggByEntity(DATA.by_entity_mkt, entity));
  updateBar(charts.prod, filterAggByEntity(DATA.by_entity_prod, entity));
  updateDonut(charts.carrier, filterAggByEntity(DATA.by_entity_carrier, entity));
  updateDonut(charts.cust, filterAggByEntity(DATA.by_entity_cust, entity));
  updateDonut(charts.ccy, filterAggByEntity(DATA.by_entity_ccy, entity));

  let cycleVal = '—';
  if(entity && DATA.cycle_avg[entity]!==undefined) cycleVal = DATA.cycle_avg[entity];
  else if(!entity){
    const vals = Object.values(DATA.cycle_avg);
    cycleVal = (vals.reduce((a,b)=>a+b,0)/vals.length).toFixed(1);
  }
  document.getElementById('cycleVal').textContent = cycleVal;

  let finPct = 0, effPct = 0;
  if(entity){
    const fin = DATA.fin_by_entity[entity] || [0,1];
    finPct = fin[0]/fin[1];
    const all = (DATA.by_entity_all[entity]||{count:0}).count;
    const eff = (DATA.by_entity_effective[entity]||{count:0}).count;
    effPct = all? eff/all : 0;
  } else {
    let finN=0, finD=0;
    for(const e of DATA.entities){ const f=DATA.fin_by_entity[e]||[0,0]; finN+=f[0]; finD+=f[1]; }
    finPct = finD? finN/finD : 0;
    effPct = grandTotal.count? effTotal.count/grandTotal.count : 0;
  }
  document.getElementById('finFill').style.width = (finPct*100).toFixed(1)+'%';
  document.getElementById('finVal').textContent = fmtPct(finPct);
  document.getElementById('effFill').style.width = (effPct*100).toFixed(1)+'%';
  document.getElementById('effVal').textContent = fmtPct(effPct);
}

selectEntity(null);
</script>
</body>
</html>
"""


class DashboardGenerator:
    """接收 aggregator 产出的聚合 dict + 运行元信息，渲染出 HTML 字符串/写文件。"""

    def render(
        self,
        agg: dict,
        *,
        source_file_name: str,
        export_date: str,
        raw_rows: int,
        header_rows_dropped: int,
        record_count: int,
        future_dated_count: int,
        generated_at: str,
        agent_version: str = "v0.1.0",
    ) -> str:
        html = _TEMPLATE
        html = html.replace("__DATA_JSON__", json.dumps(agg, ensure_ascii=False))
        html = html.replace("__SOURCE__", source_file_name)
        html = html.replace("__EXPORT_DATE__", export_date)
        html = html.replace("__RAW_ROWS__", str(raw_rows))
        html = html.replace("__HEADER_ROWS__", str(header_rows_dropped))
        html = html.replace("__RECORDS__", str(record_count))
        html = html.replace("__ENTITIES__", str(len(agg["entities"])))
        html = html.replace("__FUTURE_DATED__", str(future_dated_count))
        html = html.replace("__GENERATED__", generated_at)
        html = html.replace("__AGENT_VERSION__", agent_version)
        return html

    def write(self, html: str, out_path: Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        return out_path
