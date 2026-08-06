#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_lib.py —— HKIA 2023Q1→2026Q1 报告公共库
包含：样式、页面包装、格式化、洞察辅助、数据读档。
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "scripts" / "data" / "report_data_2023_2026Q1.json"
D = json.load(open(DATA, encoding="utf-8"))

# 全局计数
_PAGE = {"n": 0}
_TOTAL = {"n": 39}   # 预期总屏数，页脚展示
_CURRENT = {"n": 1}  # 当前页编号（由 pg 设置，H1 徽章读取）

def nsec():
    _PAGE["n"] += 1
    _CURRENT["n"] = _PAGE["n"]
    return _PAGE["n"]

def npg_badge():
    return _CURRENT["n"]

def total():
    _TOTAL["n"] += 1
    return _TOTAL["n"]

# ---------------- 样式 ----------------
CSS = """
:root{--ink:#1a2233;--mut:#5b6675;--line:#e3e7ef;--bg:#f6f8fb;--brand:#0d5c8c;--brand2:#1f7ab6;
--accent:#c8860a;--ok:#1e7d4f;--warn:#b26a00;--bad:#b3372d;--hint:#6b54a3;--page:#fff;--shadow:0 2px 10px rgba(26,34,51,.08)}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
line-height:1.62;font-size:15px}a{color:var(--brand2);text-decoration:none}
.page{max-width:1200px;margin:26px auto;background:var(--page);border-radius:10px;box-shadow:var(--shadow);
padding:44px 60px;page-break-after:always}
.pghead{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid var(--brand);
padding-bottom:8px;margin-bottom:24px;color:var(--mut);font-size:12.5px}.pghead b{color:var(--brand)}
.cover{min-height:82vh;display:flex;flex-direction:column;justify-content:center}
.cover .kicker{color:var(--accent);letter-spacing:4px;font-weight:600;font-size:13px;margin-bottom:14px}
.cover h1{font-size:34px;line-height:1.22;margin:0 0 8px}.cover h2{font-size:19px;color:var(--mut);font-weight:500;margin:0 0 30px}
.cover .meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:26px}
.cover .meta .m{border-left:4px solid var(--brand);padding:6px 14px;background:var(--bg);border-radius:4px}
.cover .meta .m small{display:block;color:var(--mut)}
h1.ph{font-size:25px;margin:4px 0 16px;padding-bottom:12px;border-bottom:2px solid var(--line);display:flex;align-items:center;gap:12px}
h1.ph .no{background:var(--brand);color:#fff;min-width:42px;height:42px;border-radius:8px;display:inline-flex;
align-items:center;justify-content:center;font-size:18px;padding:0 10px;flex:none}
h2{font-size:18px;color:var(--brand);margin:26px 0 10px;border-left:4px solid var(--accent);padding-left:10px}
h3{font-size:15px;color:#33415c;margin:18px 0 6px}p{margin:9px 0}small{color:var(--mut)}
.lead{font-size:15.5px;color:#33415c;background:var(--bg);border-left:4px solid var(--brand);padding:11px 15px;border-radius:4px;margin:14px 0}
.tag{display:inline-flex;font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:20px;letter-spacing:.4px;vertical-align:middle;margin-left:4px}
.tag.c{background:#eaf4ff;color:var(--brand2)}.tag.p{background:#fdf3e3;color:var(--warn)}
.tag.i{background:#f0eefa;color:var(--hint)}.tag.f{background:#e9f7ef;color:var(--ok)}
.tag.w{background:#fdecea;color:var(--bad)}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13.6px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right}
th{background:#f2f5fa;color:#33415c;font-weight:650}th:first-child,td:first-child{text-align:left}
tr:hover td{background:#f8fafd}td.neg{color:var(--bad)}td.pos{color:var(--ok)}
td.anom{background:#fdecea;color:var(--bad);font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:18px 0}
.kpi{background:var(--bg);border-top:3px solid var(--brand);border-radius:6px;padding:11px 14px}
.kpi .k{font-size:12px;color:var(--mut)}.kpi .v{font-size:19px;font-weight:700}.kpi .d{font-size:12.5px;color:var(--mut)}
.kpi .d.up{color:var(--ok)}.kpi .d.dn{color:var(--bad)}
.insight{background:#eef6fc;border-left:4px solid var(--brand2);border-radius:4px;padding:10px 15px;margin:12px 0}
.insight b{color:var(--brand)}.spec{background:#fbf7ed;border:1px solid #efdcaa;border-left:4px solid var(--accent);border-radius:6px;padding:13px 17px;margin:13px 0}.spec b{color:var(--accent)}
.warnbox{background:#fdecea;border-left:4px solid var(--bad);border-radius:4px;padding:10px 15px;margin:12px 0;font-size:14px}
.notebox{background:#f0f4f8;border-left:4px solid var(--mut);border-radius:4px;padding:10px 15px;margin:12px 0;font-size:14px}
.toc{columns:2;column-gap:34px;font-size:14px}.toc .lv{break-inside:avoid;margin-bottom:4px}.toc .l1{font-weight:700;color:var(--brand);margin-top:10px}.toc a{color:#33415c}
.pgfoot{margin-top:30px;border-top:1px solid var(--line);padding-top:10px;color:var(--mut);font-size:11.5px;display:flex;justify-content:space-between}
nav{position:sticky;top:0;z-index:50;background:rgba(246,248,251,.97);padding:8px 12px;display:flex;gap:5px;overflow-x:auto;border-bottom:1px solid var(--line);font-size:12.5px}
nav a{padding:4px 9px;border-radius:16px;white-space:nowrap;color:#33415c}nav a:hover{background:var(--brand);color:#fff}
nav b.pg{color:var(--mut);margin-left:auto;white-space:nowrap}
.chart{background:#fbfcfe;border:1px dashed #c7d2de;border-radius:8px;padding:14px 16px;margin:12px 0;font-size:13px;color:#33415c}
.chart .cap{color:var(--mut);font-size:11.5px;margin-top:6px}
.bar{display:flex;align-items:center;gap:8px;margin:3px 0}
.bar .lab{width:170px;font-size:12.5px;color:#33415c;text-align:right;flex:none}
.bar .track{flex:1;background:#eef1f6;border-radius:4px;height:16px;position:relative}
.bar .fill{height:16px;border-radius:4px;background:linear-gradient(90deg,var(--brand2),var(--brand))}
.bar .v{margin-left:8px;font-size:12px;color:var(--mut);width:90px;flex:none;text-align:left}
@media print{nav{display:none}.page{margin:0;box-shadow:none;border-radius:0}}
"""

# ---------------- 格式化 ----------------
def fmt_hkd(v):
    """千港元 → 亿港元。"""
    if v is None: return "—"
    return f"{v/1e6:,.2f} 亿HK$"
def fmt_int(v):
    return "—" if v is None else f"{v:,.0f}"
def fmt_rate(r):
    if r is None: return "—"
    return ("+" if r > 0 else "") + f"{r*100:.1f}%"
def yi(v):
    return None if v is None else round(v / 1e6, 3)

# ---------------- 数据读档 ----------------
M = D["market"]
def mval(metric, period):
    return M.get(metric, {}).get(period, {}).get("value")
def series(metric):
    return {pt: mval(metric, pt) for pt in D["summary"]["periods"]}
Y = D["yoy"]
def yval(fr, to, metric):
    return Y.get(f"{fr}→{to}|{metric}")
R = D["rankings"]
I = D["increments"]
def rankings_for(metric):
    return [r for r in R if r["metric"] == metric]
def increments_for(metric):
    return [r for r in I if r["metric"] == metric]

# ---------------- HTML 原子 ----------------
def H1(t): return f"<h1 class='ph'><span class='no' data-h1>#</span>{t}</h1>"
def H2(t): return f"<h2>{t}</h2>"
def H3(t): return f"<h3>{t}</h3>"
def P(t): return f"<p>{t}</p>"
def LEAD(t): return f"<div class='lead'>{t}</div>"
def INS(t): return f"<div class='insight'><b>Insight</b> · {t}</div>"
def SPEC(t): return f"<div class='spec'><b>Spec</b> · {t}</div>"
def WARN(t): return f"<div class='warnbox'> {t}</div>"
def NOTE(t): return f"<div class='notebox'> {t}</div>"
def CHART(title, body, cap=""):
    return f"<div class='chart'><b>图表</b> · {title}{body}<div class='cap'>{cap}</div></div>"
def BAR(lab, pct, valtxt):
    return f"<div class='bar'><span class='lab'>{lab}</span><div class='track'><div class='fill' style='width:{min(pct,100):.1f}%'></div></div><span class='v'>{valtxt}</span></div>"
def TAG(cls):
    return {"c":"<span class='tag c'>certified</span>","p":"<span class='tag p'>provisional</span>",
            "i":"<span class='tag i'>inference</span>","f":"<span class='tag f'>fact</span>",
            "w":"<span class='tag w'>异常复核</span>"}[cls]

def table(headers, rows, anom_cols=None, align_neg=False):
    anom_cols = anom_cols or set()
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for r in rows:
        tds = []
        for i, v in enumerate(r):
            cls = ""
            if i in anom_cols and v is not None and ("44.9" in str(v) or "4487" in str(v) or "14864" in str(v)):
                cls = "anom"
            elif align_neg and i > 0 and isinstance(v, str) and v.startswith("-"):
                cls = "neg"
            tds.append(f"<td class='{cls}'>" + ("" if v is None else str(v)) + "</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>"

# ---------------- 页面包装 ----------------
def pg(title, body, tag="p", tagtxt="自动生成 · 接手方"):
    n = nsec()
    aid = f"sec{n:02d}"
    return (f"<section class='page' id='{aid}'>"
            f"<div class='pghead'><span><b>HKIA 全行业分析</b> · {title}</span><span>{tagtxt}</span></div>"
            f"{body}"
            f"<div class='pgfoot'>"
            f"<span><b>{title}</b> · 证据分级 {TAG(tag)}</span>"
            f"<span>屏 {n:02d} / 39 · 香港长期保险 2023Q1–2026Q1</span></div></section>")
