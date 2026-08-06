#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HKIA · 2023Q1→2026Q1 全行业分析报告 · HTML 生成器
====================================================
读取 report_data_2023_2026Q1.json，按《香港长期保险统一分析Spec体系》模板
生成自包含、可分页的 HTML 报告（>=50 屏）。

报告边界（遵用户确认）：仅三大业务类——个人业务 / 团体业务 / 退休计划。
不做产品细分 / 渠道 / 货币 / 缴费年期 / MCV / 在岸离岸交叉。
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "scripts" / "data" / "report_data_2023_2026Q1.json"
OUT = BASE / "香港长期保险行业2023-2026Q1全行业分析.html"

D = json.load(open(DATA, encoding="utf-8"))

# ---------------- 样式 ----------------
CSS = """
:root{
  --ink:#1a2233;--mut:#5b6675;--line:#e3e7ef;--bg:#f6f8fb;
  --brand:#0d5c8c;--brand2:#1f7ab6;--accent:#c8860a;
  --ok:#1e7d4f;--warn:#b26a00;--bad:#b3372d;--hint:#6b54a3;--page:#fff;
  --shadow:0 2px 10px rgba(26,34,51,.08)}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,
  "Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.62;font-size:15px}
a{color:var(--brand2);text-decoration:none}
.page{max-width:1200px;margin:26px auto;background:var(--page);border-radius:10px;
  box-shadow:var(--shadow);padding:44px 60px;page-break-after:always}
.pghead{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid var(--brand);
  padding-bottom:8px;margin-bottom:26px;color:var(--mut);font-size:12.5px}
.pghead b{color:var(--brand)}
.cover{min-height:82vh;display:flex;flex-direction:column;justify-content:center}
.cover .kicker{color:var(--accent);letter-spacing:4px;font-weight:600;font-size:13px;margin-bottom:14px}
.cover h1{font-size:34px;line-height:1.22;margin:0 0 8px}
.cover h2{font-size:19px;color:var(--mut);font-weight:500;margin:0 0 30px}
.cover .meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:26px}
.cover .meta .m{border-left:4px solid var(--brand);padding:6px 14px;background:var(--bg);border-radius:4px}
.cover .meta .m small{display:block;color:var(--mut)}
h1.ph{font-size:25px;margin:4px 0 18px;padding-bottom:12px;border-bottom:2px solid var(--line);
  display:flex;align-items:center;gap:12px}
h1.ph .no{background:var(--brand);color:#fff;min-width:42px;height:42px;border-radius:8px;display:inline-flex;
  align-items:center;justify-content:center;font-size:18px;padding:0 10px;flex:none}
h2{font-size:18.5px;color:var(--brand);margin:28px 0 10px;border-left:4px solid var(--accent);padding-left:10px}
h3{font-size:15px;color:#33415c;margin:18px 0 6px}
p{margin:9px 0}
small{color:var(--mut)}
.lead{font-size:15.5px;color:#33415c;background:var(--bg);border-left:4px solid var(--brand);
  padding:11px 15px;border-radius:4px;margin:14px 0}
.tag{display:inline-block;font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:20px;letter-spacing:.4px;vertical-align:middle}
.tag.c{background:#eaf4ff;color:var(--brand2)}
.tag.p{background:#fdf3e3;color:var(--warn)}
.tag.i{background:#f0eefa;color:var(--hint)}
.tag.f{background:#e9f7ef;color:var(--ok)}
.tag.w{background:#fdecea;color:var(--bad)}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13.7px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right}
th{background:#f2f5fa;color:#33415c;font-weight:650}
th:first-child,td:first-child{text-align:left}
tr:hover td{background:#f8fafd}
td.neg{color:var(--bad)} td.pos{color:var(--ok)} td.anom{background:#fdecea;color:var(--bad);font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:18px 0}
.kpi{background:var(--bg);border-top:3px solid var(--brand);border-radius:6px;padding:11px 14px}
.kpi .k{font-size:12px;color:var(--mut)}
.kpi .v{font-size:19px;font-weight:700}
.kpi .d{font-size:12.5px;color:var(--mut)}
.kpi .d.up{color:var(--ok)}.kpi .d.dn{color:var(--bad)}
.insight{background:#eef6fc;border-left:4px solid var(--brand2);border-radius:4px;padding:10px 15px;margin:12px 0}
.insight b{color:var(--brand)}
.spec{background:#fbf7ed;border:1px solid #efdcaa;border-left:4px solid var(--accent);border-radius:6px;
  padding:13px 17px;margin:13px 0}
.spec b{color:var(--accent)}
.warnbox{background:#fdecea;border-left:4px solid var(--bad);border-radius:4px;padding:10px 15px;margin:12px 0;font-size:14px}
.notebox{background:#f0f4f8;border-left:4px solid var(--mut);border-radius:4px;padding:10px 15px;margin:12px 0;font-size:14px}
.toc{columns:2;column-gap:34px;font-size:14px}.toc .lv{break-inside:avoid;margin-bottom:5px}
.toc .l1{font-weight:700;color:var(--brand);margin-top:10px}.toc a{color:#33415c}
.pgfoot{margin-top:30px;border-top:1px solid var(--line);padding-top:10px;color:var(--mut);font-size:11.5px;display:flex;justify-content:space-between}
nav{position:sticky;top:0;z-index:50;background:rgba(246,248,251,.97);padding:8px 12px;display:flex;gap:5px;
  overflow-x:auto;border-bottom:1px solid var(--line);font-size:12.5px}
nav a{padding:4px 9px;border-radius:16px;white-space:nowrap;color:#33415c}
nav a:hover{background:var(--brand);color:#fff}
nav b.pg{color:var(--mut);margin-left:auto;white-space:nowrap}
@media print{nav{display:none}.page{margin:0;box-shadow:none;border-radius:0}}
"""
