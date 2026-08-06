"""从已评审通过的L3流程模型demo导出离线分析报告(HTML+MD两版)。

demo(如L3流程模型_demo_L3-COM_标准测试版_20260728.html)是workshop现场协作
工具——多人拖拽任务卡片、调整优先级象限，状态存在浏览器localStorage里。这份
报告不一样：给不在场的负责人离线阅读(HTML)，或喂给AI工具做进一步分析(MD)。

数据源只有demo文件本身，不再读model_snapshots/analysis_packages——逐段核对
过，demo实际渲染出来的内容(六个面板+决策面板的全部文字和表格)已经是这两份
JSON的完整投影，额外还包含决策表格"为什么适合先试"这类只在demo里手写的
说明文字。demo里的raci/obControls两个JS变量含真实姓名，但从未被任何渲染逻辑
引用(死数据)，因此忠实提取demo实际显示的内容，天然就不会带出真实姓名。
"""
from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lxml import html as lxml_html

SCHEMA_VERSION = "vnw.l3-report.v1"

# demo脚本里把DOM节点重排成的真实阅读顺序(不是源码里A/B/C/D/E/F的顺序)，
# 报告按这个顺序走，和负责人在demo里实际看到的顺序保持一致。
PANEL_READING_ORDER = ["panel-a", "panel-e", "panel-c", "panel-b", "panel-d", "decision-panel", "panel-f"]

TIER_LABELS = {"Human": "暂不替代", "Hybrid": "人机协同", "Aug": "AI增强", "Auto": "可完全自动"}
QUADRANT_LABELS = {"q1": "优先验证", "q2": "治理后推进", "q3": "补数据/规则后推进", "q4": "暂缓自动化"}

# 含真实姓名、且从未被demo渲染逻辑引用的死数据——明确排除，不提取。
_SKIP_CONSTS = {"raci", "obControls"}


def _text(el) -> str:
    """按纯文本拼接。原始HTML里有两处用视觉手段(而非字面空白)分隔内容——
    决策表格用<br>换行分隔任务ID和标题，.finding卡片用CSS `b{display:block}`
    让加粗小标题独占一行——直接itertext()会把这两处内容无缝拼在一起，读不
    出原意，所以在拼接前把这两种视觉分隔显式转成换行符。"""
    raw = lxml_html.tostring(el, encoding="unicode", with_tail=False)
    raw = re.sub(r"<br\s*/?>", "\n", raw)
    if "finding" in (el.get("class") or ""):
        raw = re.sub(r"(</b>)", r"\1\n", raw, count=1)
    frag = lxml_html.fromstring(raw)
    return frag.text_content().strip()


def _find_one(tree, xpath: str):
    matches = tree.xpath(xpath)
    return matches[0] if matches else None


def _extract_js_const(script_text: str, name: str) -> Any:
    """定位`const {name}=`后的起始括号，逐字符扫描括号深度和引号状态，找到
    匹配的闭合括号后截取子串并json.loads。比正则更稳健——不受字符串内部
    标点(包括分号)干扰，对`tasks`这种后面还接.map(...)的情况也天然适用，
    因为扫描器只认括号配对，不关心后面跟了什么。"""
    marker = re.search(rf"const\s+{re.escape(name)}\s*=\s*", script_text)
    if not marker:
        raise ValueError(f"demo脚本里找不到const {name}")
    start = marker.end()
    if script_text[start] not in "[{":
        raise ValueError(f"const {name}后不是数组/对象字面量")
    open_ch, close_ch = script_text[start], "]" if script_text[start] == "[" else "}"
    depth = 0
    in_string = False
    i = start
    while i < len(script_text):
        ch = script_text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return json.loads(script_text[start:i + 1])
        i += 1
    raise ValueError(f"const {name}未找到匹配的闭合括号")


def _extract_tasks(script_text: str, l3_code: str) -> list[dict]:
    raw = _extract_js_const(script_text, "tasks")
    l4_prefix = f"L4-{l3_code.split('-', 1)[1]}-"
    return [
        {"id": row[0], "l4": l4_prefix + row[1], "name": row[2], "tier": row[3], "source": row[4], "why": row[5]}
        for row in raw
    ]


def extract_demo_content(demo_html_path: Path, l3_code: str) -> dict:
    raw = Path(demo_html_path).read_text(encoding="utf-8")
    tree = lxml_html.fromstring(raw)
    script_text = tree.xpath("//script[1]/text()")
    script_text = script_text[0] if script_text else ""

    content: dict[str, Any] = {"l3_code": l3_code}

    banner = _find_one(tree, "//section[contains(@class,'banner')]")
    content["eyebrow"] = _text(_find_one(banner, ".//div[@class='eyebrow']")) if banner is not None else ""
    content["title"] = _text(_find_one(banner, ".//h1")) if banner is not None else l3_code
    content["banner_note"] = _text(_find_one(banner, ".//p")) if banner is not None else ""
    content["path_pills"] = [_text(el) for el in (banner.xpath(".//div[@class='path']/span[@class='pill']") if banner is not None else [])]

    kpis_section = _find_one(tree, "//section[@class='kpis']")
    content["kpis"] = [
        {"value": _text(_find_one(el, ".//b")), "label": _text(el).replace(_text(_find_one(el, ".//b")), "", 1).strip()}
        for el in (kpis_section.xpath(".//div[@class='kpi']") if kpis_section is not None else [])
    ]

    terms_section = _find_one(tree, "//section[@class='terms']")
    content["terms"] = [
        {"tier": _text(_find_one(el, ".//b")), "desc": _text(el).replace(_text(_find_one(el, ".//b")), "", 1).strip()}
        for el in (terms_section.xpath(".//div[@class='term']") if terms_section is not None else [])
    ]

    def panel_notes(panel_id: str) -> dict:
        panel = _find_one(tree, f"//section[@id='{panel_id}']")
        if panel is None:
            return {"head": "", "source": "", "notes": [], "warnings": [], "ob_strips": []}
        return {
            "head": _text(_find_one(panel, ".//h2")),
            "source": _text(_find_one(panel, ".//span[@class='source']")),
            # note有时是<div>有时是<p>(面板C用<p>)，两种都要catch；<details>里的
            # note单独走detail_note字段，这里排除避免重复。
            "notes": [_text(el) for el in panel.xpath(".//*[@class='note'][not(ancestor::details)]")],
            "warnings": [_text(el) for el in panel.xpath(".//div[@class='warning']")],
            "ob_strips": [_text(el) for el in panel.xpath(".//div[@class='ob-strip']")],
        }

    content["panel_a"] = panel_notes("panel-a")
    validation_chain = _find_one(tree, "//section[@id='panel-a']//div[@class='validation-chain']")
    content["panel_a"]["validation_chain"] = [
        _text(el) for el in (validation_chain.xpath(".//div[contains(@class,'validation-node')]") if validation_chain is not None else [])
    ]

    content["panel_b"] = panel_notes("panel-b")
    collab_flow = _find_one(tree, "//section[@id='panel-b']//div[@class='collab-flow']")
    content["panel_b"]["flow_steps"] = [_text(el) for el in (collab_flow.xpath(".//span") if collab_flow is not None else [])]
    detail_note = _find_one(tree, "//section[@id='panel-b']//details//p[@class='note']")
    content["panel_b"]["detail_note"] = _text(detail_note) if detail_note is not None else ""

    content["panel_c"] = panel_notes("panel-c")
    content["panel_d"] = panel_notes("panel-d")
    content["panel_e"] = panel_notes("panel-e")
    mapline = _find_one(tree, "//section[@id='panel-e']//div[@class='mapline']")
    content["panel_e"]["mapline"] = _text(mapline) if mapline is not None else ""

    panel_f = _find_one(tree, "//section[@id='panel-f']")
    content["panel_f"] = {
        "warning": _text(_find_one(panel_f, ".//div[@class='warning']")) if panel_f is not None else "",
        "extra_inputs_table": [
            [_text(td) for td in row.xpath(".//td")]
            for row in (panel_f.xpath(".//h3[1]/following-sibling::div[1]//tbody/tr") if panel_f is not None else [])
        ],
        "evidence_list": [_text(el) for el in (panel_f.xpath(".//ul[@class='evidence-list']/li") if panel_f is not None else [])],
    }

    decision = _find_one(tree, "//section[@id='decision-panel']")
    content["decision"] = {
        "head": _text(_find_one(decision, ".//h2")) if decision is not None else "",
        "source": _text(_find_one(decision, ".//span[@class='source']")) if decision is not None else "",
        "note": _text(_find_one(decision, ".//div[@class='note']")) if decision is not None else "",
        "rows": [
            [_text(td) for td in row.xpath(".//td")]
            for row in (decision.xpath(".//table//tbody/tr") if decision is not None else [])
        ],
        "extra_head": _text(_find_one(decision, ".//h3")) if decision is not None else "",
        "findings": [_text(el) for el in (decision.xpath(".//div[@class='finding']") if decision is not None else [])],
    }

    footer = _find_one(tree, "//footer[@id='page-footer']")
    content["footer"] = _text(footer) if footer is not None else ""

    for name in ("l4s", "chain", "vns", "dbVnByL4", "deliveryMeta", "analysisMeta", "collabMeta"):
        content[name] = _extract_js_const(script_text, name)
    content["tasks"] = _extract_tasks(script_text, l3_code)

    for skipped in _SKIP_CONSTS:
        content.pop(skipped, None)

    return content


TIER_ORDER = ["Human", "Hybrid", "Aug", "Auto"]
QUADRANT_ORDER = ["q1", "q2", "q3", "q4"]


def _suffix(l4_code: str) -> str:
    return l4_code[-2:]


def _build_view(content: dict) -> dict:
    """把extract_demo_content的原始按位置数组，转成按tier/象限分组好的
    视图模型——HTML和MD渲染器共用同一份分组逻辑，只是排版不同。"""
    l4s = content["l4s"]
    by_code = {row[0]: row for row in l4s}
    delivery_meta, analysis_meta, collab_meta, db_vn = (
        content["deliveryMeta"], content["analysisMeta"], content["collabMeta"], content["dbVnByL4"]
    )

    chain_steps = [
        {"code": code, "name": by_code[code][1], "deliverable": by_code[code][2], "tier": by_code[code][4]}
        for code in content["chain"]
    ]

    deliveries = []
    for row in l4s:
        role, capabilities, ai_reshape, quality_anchor = delivery_meta[_suffix(row[0])]
        deliveries.append({
            "code": row[0], "name": row[1], "deliverable": row[2],
            "db_tier": row[3], "review_tier": row[4], "d1_d6": row[5], "total": row[6],
            "gate": row[7], "vn_exists": row[8] == "是", "fund_safety": row[9] == "是", "note": row[10],
            "role": role, "capabilities": capabilities, "ai_reshape": ai_reshape, "quality_anchor": quality_anchor,
            "tier_conflict": row[3] != row[4], "vn_bridge": db_vn.get(row[0], "—"),
        })

    tasks_by_tier: dict[str, list] = {t: [] for t in TIER_ORDER}
    for task in content["tasks"]:
        row = by_code.get(task["l4"])
        tasks_by_tier.setdefault(task["tier"], []).append({**task, "l4_name": row[1] if row else task["l4"]})

    quadrants: dict[str, list] = {q: [] for q in QUADRANT_ORDER}
    for row in l4s:
        process_context, risks_limits, recommendation, quadrant = analysis_meta[_suffix(row[0])]
        quadrants.setdefault(quadrant, []).append({
            "code": row[0], "name": row[1], "review_tier": row[4], "d1_d6": row[5], "total": row[6],
            "db_tier": row[3], "tier_conflict": row[3] != row[4],
            "process_context": process_context, "risks_limits": risks_limits, "recommendation": recommendation,
        })

    collab_rows = []
    for row in l4s:
        ai_resp, human_resp, triggers, gates, owner = collab_meta[_suffix(row[0])]
        collab_rows.append({
            "code": row[0], "name": row[1], "review_tier": row[4], "gate": row[7],
            "ai_responsibility": ai_resp, "human_responsibility": human_resp,
            "handoff_triggers": triggers, "control_gates": gates, "owner": owner,
        })

    vns = [
        {"id": v[0], "name": v[1], "l4_refs": v[2], "judgment": v[3], "is_fused": v[4],
         "priority": v[5], "kpi": v[6], "has_db_bridge": v[7]}
        for v in content["vns"]
    ]

    return {
        "chain_steps": chain_steps, "deliveries": deliveries, "vns": vns,
        "tasks_by_tier": tasks_by_tier, "quadrants": quadrants, "collab_rows": collab_rows,
    }


# 和前端实际渲染标准(tailwind.config.js的theme.extend.colors/fontFamily +
# index.css的.panel/.eyebrow/.metric-value + L3ModelDetail.tsx的tierTone/
# gateTone配色约定)保持一致，不是照抄workshop demo自己的一套配色。
_HTML_STYLE = """
:root{--bg-base:#F5F7FB;--bg-elevated:#FFFFFF;--bg-surface:#F7F9FC;--border-default:#D9E1EC;
--accent-primary:#4F46E5;--text-primary:#172033;--text-secondary:#4A5870;--text-muted:#718096}
*{box-sizing:border-box}
body{margin:0;background:var(--bg-base);color:var(--text-primary);font:14px/1.6 Inter,system-ui,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:auto;padding:28px}
.banner{background:linear-gradient(90deg,#EEF2FF,#FFFFFF 55%,#ECFEFF);border:1px solid var(--border-default);border-radius:20px;padding:22px 26px;margin-bottom:16px;box-shadow:0 12px 32px rgba(30,51,84,.08)}
h1{font-family:"Plus Jakarta Sans",Inter,sans-serif;margin:4px 0 6px;font-size:26px;font-weight:700;color:var(--text-primary)}
h2{font-family:"Plus Jakarta Sans",Inter,sans-serif;font-size:16px;margin:0 0 10px;font-weight:700;color:var(--text-primary)}
h3{font-size:12px;color:var(--text-muted);margin:16px 0 8px;font-weight:600}
.eyebrow{font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted)}
.pill{display:inline-block;padding:5px 10px;background:var(--bg-surface);border:1px solid var(--border-default);border-radius:999px;font-size:12px;margin:2px 4px 2px 0;color:var(--text-secondary)}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.kpi{flex:1;min-width:140px;background:var(--bg-elevated);border:1px solid var(--border-default);border-radius:16px;padding:13px;box-shadow:0 12px 32px rgba(30,51,84,.06)}
.kpi b{display:block;font:600 20px "JetBrains Mono",ui-monospace,monospace;color:var(--text-primary)}
.terms{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.term{flex:1;min-width:220px;padding:10px;border:1px solid var(--border-default);background:var(--bg-elevated);border-radius:10px;font-size:12px;color:var(--text-secondary)}
.panel{background:var(--bg-elevated);border:1px solid var(--border-default);border-radius:16px;padding:18px;margin:14px 0;box-shadow:0 12px 32px rgba(30,51,84,.08)}
.head{display:flex;justify-content:space-between;gap:16px;align-items:start;border-bottom:1px solid var(--border-default);padding-bottom:11px;margin-bottom:14px}
.source{font-size:11px;color:var(--text-muted);white-space:nowrap}
.note,.warning{padding:10px 12px;border-radius:10px;font-size:12.5px;margin-bottom:8px;white-space:pre-line}
.note{background:var(--bg-surface);color:var(--text-secondary)}
.warning{background:rgba(251,191,36,.1);color:#92400E;border:1px solid rgba(251,191,36,.3)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:8px;border-bottom:1px solid var(--border-default);text-align:left;vertical-align:top;white-space:pre-line}
th{color:var(--text-muted);font-weight:600;background:var(--bg-surface)}
.tier{display:inline-block;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:600;border:1px solid transparent}
.Auto{background:#D1FAE5;color:#065F46;border-color:#A7F3D0}
.Aug{background:#DBEAFE;color:#1E40AF;border-color:#BFDBFE}
.Hybrid{background:#FEF3C7;color:#92400E;border-color:#FDE68A}
.Human{background:#FFE4E6;color:#9F1239;border-color:#FECDD3}
.flow{display:flex;align-items:stretch;gap:6px;overflow-x:auto;padding:4px 2px 10px}
.step{min-width:165px;border:1px solid var(--border-default);border-radius:12px;padding:10px;background:var(--bg-elevated)}
.step .code{font:11px "JetBrains Mono",ui-monospace,monospace;color:var(--accent-primary)}
.step strong{display:block;margin:4px 0;font-size:12px;color:var(--text-primary)}
.arrow{align-self:center;color:var(--text-muted)}
.grid3{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}
.card{border:1px solid var(--border-default);border-radius:12px;padding:11px;background:var(--bg-elevated)}
.card .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.card p{font-size:11.5px;color:var(--text-secondary);margin:5px 0 0}
.card .name{font-size:13px;font-weight:600;font-family:"JetBrains Mono",ui-monospace,monospace;color:var(--text-primary)}
.tgroup{margin-bottom:14px;border-radius:14px;padding:12px}
.tgroup h3{margin-top:0}
.q1{background:#ECFDF5;border:1px solid #A7F3D0}.q2{background:#EFF6FF;border:1px solid #BFDBFE}
.q3{background:#FFFBEB;border:1px solid #FDE68A}.q4{background:#FFF1F2;border:1px solid #FECDD3}
.finding{border-left:3px solid var(--accent-primary);padding:10px 12px;background:var(--bg-surface);border-radius:8px;margin-bottom:8px;white-space:pre-line;font-size:12.5px;color:var(--text-secondary)}
footer{text-align:center;color:var(--text-muted);font-size:11px;padding:18px}
.disclaimer{background:#EEF2FF;color:#3730A3;border:1px solid #C7D2FE;border-radius:12px;padding:10px 14px;font-size:12px;margin-bottom:16px}
"""


def _esc(text: Any) -> str:
    return html_lib.escape(str(text))


def _tier_badge(tier: str) -> str:
    return f'<span class="tier {_esc(tier)}">{_esc(tier)}</span>'


def render_report_html(l3_code: str, content: dict) -> str:
    v = _build_view(content)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    flow_html = "".join(
        f'<div class="step"><span class="code">{_esc(s["code"])}</span><strong>{_esc(s["name"])}</strong>'
        f'<span>{_esc(s["deliverable"])}</span><br>{_tier_badge(s["tier"])}</div>'
        + ('<div class="arrow">→</div>' if i < len(v["chain_steps"]) - 1 else "")
        for i, s in enumerate(v["chain_steps"])
    )
    validation_html = "".join(f'<p class="note">{_esc(t)}</p>' for t in content["panel_a"]["validation_chain"])
    panel_a = f"""
    <section class="panel"><div class="head"><h2>A · 流程叙事（理想态执行路径）</h2><span class="source">{_esc(content['panel_a']['source'])}</span></div>
    {"".join(f'<div class="note">{_esc(t)}</div>' for t in content['panel_a']['ob_strips'])}
    <div class="flow">{flow_html}</div>
    {"".join(f'<div class="warning">{_esc(t)}</div>' for t in content['panel_a']['warnings'])}
    {validation_html}
    </section>"""

    delivery_cards = "".join(
        f'<div class="card"><div class="top"><span class="name">{_esc(d["code"])}</span>{_tier_badge(d["review_tier"])}</div>'
        f'<p><b>{_esc(d["deliverable"])}</b></p><p>所需能力：{_esc(d["capabilities"])}</p>'
        f'<p>AI重塑：{_esc(d["ai_reshape"])}</p><p>质量锚点：{_esc(d["quality_anchor"])}</p>'
        f'<p>D1-D6：{"/".join(map(str, d["d1_d6"]))} · {d["total"]}/18'
        f'{" · 数据库/复核Tier冲突" if d["tier_conflict"] else ""}</p></div>'
        for d in v["deliveries"]
    )
    vn_cards = "".join(
        f'<div class="card"><div class="top"><span class="name">{_esc(vn["id"])}</span>'
        f'<span class="tier {"Human" if vn["is_fused"] else "Hybrid"}">{"熔断" if vn["is_fused"] else _esc(vn["judgment"])}</span></div>'
        f'<p><b>{_esc(vn["name"])}</b></p><p>关联L4：{_esc(vn["l4_refs"])}</p><p>KPI：{_esc(vn["kpi"])}</p>'
        f'<p>{"数据库正式桥接" if vn["has_db_bridge"] else "D1/D2材料补充，待桥接"}</p></div>'
        for vn in v["vns"]
    )
    panel_e = f"""
    <section class="panel"><div class="head"><h2>E · L4交付物地图</h2><span class="source">{_esc(content['panel_e']['source'])}</span></div>
    {"".join(f'<div class="note">{_esc(t)}</div>' for t in content['panel_e']['notes'])}
    {"".join(f'<div class="note">{_esc(t)}</div>' for t in content['panel_e']['ob_strips'])}
    <p class="note">{_esc(content['panel_e']['mapline'])}</p>
    <div class="grid3">{delivery_cards}</div>
    <h3>新版VN引用源（数据库L4桥接仍未建立）</h3>
    <div class="grid3">{vn_cards}</div>
    </section>"""

    task_groups = "".join(
        f'<div class="tgroup"><h3>{_esc(tier)} · {_esc(TIER_LABELS[tier])}（{len(v["tasks_by_tier"][tier])}项）</h3>'
        f'<table><thead><tr><th>任务</th><th>所属L4</th><th>来源颗粒度</th><th>说明</th></tr></thead><tbody>'
        + "".join(
            f'<tr><td>{_esc(t["id"])} {_esc(t["name"])}</td><td>{_esc(t["l4"])} {_esc(t["l4_name"])}</td>'
            f'<td>{_esc(t["source"])}</td><td>{_esc(t["why"])}</td></tr>'
            for t in v["tasks_by_tier"][tier]
        ) + "</tbody></table></div>"
        for tier in TIER_ORDER if v["tasks_by_tier"][tier]
    )
    panel_c = f"""
    <section class="panel"><div class="head"><h2>C · AI任务清单</h2><span class="source">{_esc(content['panel_c']['source'])}</span></div>
    {"".join(f'<div class="note">{_esc(t)}</div>' for t in content['panel_c']['notes'])}
    {task_groups}
    {"".join(f'<div class="note">{_esc(t)}</div>' for t in content['panel_c']['ob_strips'])}
    </section>"""

    collab_rows_html = "".join(
        f'<tr><td>{_esc(r["code"])}<br><b>{_esc(r["name"])}</b><br>复核{_tier_badge(r["review_tier"])} · {_esc(r["gate"])}</td>'
        f'<td>{_esc(r["ai_responsibility"])}</td><td>{_esc(r["human_responsibility"])}</td>'
        f'<td>{_esc(r["handoff_triggers"])}</td><td>{_esc(r["control_gates"])}</td><td>{_esc(r["owner"])}</td></tr>'
        for r in v["collab_rows"]
    )
    panel_b = f"""
    <section class="panel"><div class="head"><h2>B · 人机协作与控制地图</h2><span class="source">{_esc(content['panel_b']['source'])}</span></div>
    {"".join(f'<div class="note">{_esc(t)}</div>' for t in content['panel_b']['notes'])}
    <table><thead><tr><th>L4活动</th><th>AI负责</th><th>人负责</th><th>何时转人工</th><th>不可绕过控制门</th><th>承接岗位族/部门</th></tr></thead>
    <tbody>{collab_rows_html}</tbody></table>
    <p class="note">{_esc(content['panel_b']['detail_note'])}</p>
    </section>"""

    quadrant_groups = "".join(
        f'<div class="tgroup {_esc(q)}"><h3>{_esc(q)} · {_esc(QUADRANT_LABELS[q])}（{len(v["quadrants"][q])}项）</h3><div class="grid3">'
        + "".join(
            f'<div class="card"><div class="top"><span class="name">{_esc(item["code"])} {_esc(item["name"])}</span></div>'
            f'<p>数据依据：D1-D6 {"/".join(map(str, item["d1_d6"]))}；复核Tier{_esc(item["review_tier"])}'
            f'{("；与数据库" + _esc(item["db_tier"]) + "冲突") if item["tier_conflict"] else ""}</p>'
            f'<p>流程背景：{_esc(item["process_context"])}</p><p>风险/限制：{_esc(item["risks_limits"])}</p>'
            f'<p><b>当前建议：{_esc(item["recommendation"])}</b></p></div>'
            for item in v["quadrants"][q]
        ) + "</div></div>"
        for q in QUADRANT_ORDER if v["quadrants"][q]
    )
    panel_d = f"""
    <section class="panel"><div class="head"><h2>D · AI机会优先级矩阵</h2><span class="source">{_esc(content['panel_d']['source'])}</span></div>
    {"".join(f'<div class="warning">{_esc(t)}</div>' for t in content['panel_d']['warnings'])}
    {"".join(f'<div class="note">{_esc(t)}</div>' for t in content['panel_d']['ob_strips'])}
    {quadrant_groups}
    </section>"""

    decision_rows_html = "".join(
        "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>"
        for row in content["decision"]["rows"]
    )
    findings_html = "".join(f'<div class="finding">{_esc(f)}</div>' for f in content["decision"]["findings"])
    panel_decision = f"""
    <section class="panel"><div class="head"><h2>{_esc(content['decision']['head'])}</h2><span class="source">{_esc(content['decision']['source'])}</span></div>
    <div class="note">{_esc(content['decision']['note'])}</div>
    <table><thead><tr><th>优先级</th><th>建议先试的任务</th><th>为什么适合先试</th><th>首轮最小范围</th><th>必须保留的人工边界</th><th>负责人需要拍板</th></tr></thead>
    <tbody>{decision_rows_html}</tbody></table>
    <h3>{_esc(content['decision']['extra_head'])}</h3>
    {findings_html}
    </section>"""

    raw_rows_html = "".join(
        f'<tr><td>{_esc(d["code"])}</td><td>{_esc(d["name"])}</td><td>{_esc(d["deliverable"])}</td>'
        f'<td>{_esc(d["db_tier"])}</td><td>{_esc(d["review_tier"])}</td>'
        f'<td>{"/".join(map(str, d["d1_d6"]))} · {d["total"]}/18</td><td>{_esc(d["vn_bridge"])}</td></tr>'
        for d in v["deliveries"]
    )
    extra_inputs_html = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in content["panel_f"]["extra_inputs_table"]
    )
    evidence_html = "".join(f"<li>{_esc(e)}</li>" for e in content["panel_f"]["evidence_list"])
    panel_f = f"""
    <section class="panel"><h2>F · 标准数据表与SSOT差异</h2>
    <table><thead><tr><th>l4_code</th><th>l4_name</th><th>deliverable</th><th>数据库Tier</th><th>复核Tier</th><th>D1-D6/总分</th><th>VN桥接</th></tr></thead>
    <tbody>{raw_rows_html}</tbody></table>
    <div class="warning">{_esc(content['panel_f']['warning'])}</div>
    <h3>新增输入与采用方式</h3>
    <table><thead><tr><th>输入文件</th><th>命中</th><th>进入页面</th><th>限制</th></tr></thead><tbody>{extra_inputs_html}</tbody></table>
    <h3>本轮采用的OB补充证据</h3>
    <ul>{evidence_html}</ul>
    </section>"""

    kpis_html = "".join(f'<div class="kpi"><b>{_esc(k["value"])}</b>{_esc(k["label"])}</div>' for k in content["kpis"])
    terms_html = "".join(f'<div class="term"><b class="tier {_esc(t["tier"])}">{_esc(t["tier"])}</b> {_esc(t["desc"])}</div>' for t in content["terms"])
    pills_html = "".join(f'<span class="pill">{_esc(p)}</span>' for p in content["path_pills"])

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(content['title'])} · 分析报告</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@600;700&display=swap" rel="stylesheet">
<style>{_HTML_STYLE}</style></head>
<body><div class="wrap">
<section class="banner"><div class="eyebrow">{_esc(content['eyebrow'])} · 分析报告导出</div>
<h1>{_esc(content['title'])}</h1><p>{pills_html}</p></section>
<div class="disclaimer">本报告由AI辅助分析生成的内容（人机协作建议、优先级矩阵、隐藏产出候选等）标注MODEL_DRAFT/工作坊共识，仍需负责人复核；完整交互版见原demo。生成日期：{generated_at}</div>
<div class="kpis">{kpis_html}</div>
<div class="terms">{terms_html}</div>
{panel_a}{panel_e}{panel_c}{panel_b}{panel_d}{panel_decision}{panel_f}
<footer>{_esc(content['footer'])}</footer>
</div></body></html>
"""


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "（无）\n"
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c).replace("\n", "<br>").replace("|", "\\|") for c in row) + " |")
    return "\n".join(lines) + "\n"


def render_report_md(l3_code: str, content: dict) -> str:
    v = _build_view(content)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = [f"# {content['title']} · 分析报告\n"]
    out.append(f"> {content['eyebrow']} · 分析报告导出 · 生成日期：{generated_at}\n")
    out.append("> 本报告由AI辅助分析生成的内容（人机协作建议、优先级矩阵、隐藏产出候选等）标注MODEL_DRAFT/工作坊共识，仍需负责人复核；完整交互版见原demo。\n")
    out.append("路径：" + " → ".join(content["path_pills"]) + "\n")
    out.append("## 关键指标\n")
    out.append(_md_table(["指标", "数值"], [[k["label"], k["value"]] for k in content["kpis"]]))
    out.append("## Tier定义\n")
    out.append(_md_table(["Tier", "定义"], [[t["tier"], t["desc"]] for t in content["terms"]]))

    out.append("\n## A · 流程叙事（理想态执行路径）\n")
    out.append(f"来源：{content['panel_a']['source']}\n")
    for t in content["panel_a"]["ob_strips"]:
        out.append(f"> {t}\n")
    out.append("流程链：" + " → ".join(f"{s['code']}({s['tier']}){s['name']}" for s in v["chain_steps"]) + "\n")
    for t in content["panel_a"]["warnings"]:
        out.append(f"⚠️ {t}\n")
    for t in content["panel_a"]["validation_chain"]:
        out.append(f"- {t}\n")

    out.append("\n## E · L4交付物地图\n")
    out.append(f"来源：{content['panel_e']['source']}\n")
    for t in content["panel_e"]["notes"] + content["panel_e"]["ob_strips"]:
        out.append(f"> {t}\n")
    out.append(f"{content['panel_e']['mapline']}\n")
    out.append(_md_table(
        ["L4", "交付物", "角色", "所需能力", "AI重塑方式", "质量锚点", "D1-D6/总分"],
        [[d["code"] + " " + d["name"], d["deliverable"], d["role"], d["capabilities"], d["ai_reshape"], d["quality_anchor"],
          "/".join(map(str, d["d1_d6"])) + f' · {d["total"]}/18' + (" · Tier冲突" if d["tier_conflict"] else "")]
         for d in v["deliveries"]]
    ))
    out.append("\n新版VN引用源（数据库L4桥接仍未建立）：\n")
    out.append(_md_table(
        ["VN", "名称", "关联L4", "综合判定", "KPI", "桥接状态"],
        [[vn["id"], vn["name"], vn["l4_refs"], "熔断" if vn["is_fused"] else vn["judgment"], vn["kpi"],
          "数据库正式桥接" if vn["has_db_bridge"] else "D1/D2材料补充，待桥接"] for vn in v["vns"]]
    ))

    out.append("\n## C · AI任务清单\n")
    for t in content["panel_c"]["notes"]:
        out.append(f"> {t}\n")
    for tier in TIER_ORDER:
        tasks = v["tasks_by_tier"][tier]
        if not tasks:
            continue
        out.append(f"\n### {tier} · {TIER_LABELS[tier]}（{len(tasks)}项）\n")
        out.append(_md_table(
            ["任务", "所属L4", "来源颗粒度", "说明"],
            [[f'{t["id"]} {t["name"]}', f'{t["l4"]} {t["l4_name"]}', t["source"], t["why"]] for t in tasks]
        ))
    for t in content["panel_c"]["ob_strips"]:
        out.append(f"> {t}\n")

    out.append("\n## B · 人机协作与控制地图\n")
    for t in content["panel_b"]["notes"]:
        out.append(f"> {t}\n")
    out.append(_md_table(
        ["L4", "AI负责", "人负责", "何时转人工", "不可绕过控制门", "承接岗位族/部门"],
        [[f'{r["code"]} {r["name"]}（复核{r["review_tier"]} · {r["gate"]}）', r["ai_responsibility"], r["human_responsibility"],
          r["handoff_triggers"], r["control_gates"], r["owner"]] for r in v["collab_rows"]]
    ))
    out.append(f"\n{content['panel_b']['detail_note']}\n")

    out.append("\n## D · AI机会优先级矩阵\n")
    for t in content["panel_d"]["warnings"] + content["panel_d"]["ob_strips"]:
        out.append(f"> {t}\n")
    for q in QUADRANT_ORDER:
        items = v["quadrants"][q]
        if not items:
            continue
        out.append(f"\n### {q} · {QUADRANT_LABELS[q]}（{len(items)}项）\n")
        out.append(_md_table(
            ["L4", "数据依据", "流程背景", "风险/限制", "当前建议"],
            [[f'{it["code"]} {it["name"]}',
              f'D1-D6 {"/".join(map(str, it["d1_d6"]))}；复核{it["review_tier"]}' + ("；与数据库" + it["db_tier"] + "冲突" if it["tier_conflict"] else ""),
              it["process_context"], it["risks_limits"], it["recommendation"]] for it in items]
        ))

    out.append(f"\n## {content['decision']['head']}\n")
    out.append(f"来源：{content['decision']['source']}\n\n{content['decision']['note']}\n")
    out.append(_md_table(
        ["优先级", "建议先试的任务", "为什么适合先试", "首轮最小范围", "必须保留的人工边界", "负责人需要拍板"],
        content["decision"]["rows"]
    ))
    out.append(f"\n### {content['decision']['extra_head']}\n")
    for f in content["decision"]["findings"]:
        out.append(f"- {f}\n")

    out.append("\n## F · 标准数据表与SSOT差异\n")
    out.append(_md_table(
        ["l4_code", "l4_name", "deliverable", "数据库Tier", "复核Tier", "D1-D6/总分", "VN桥接"],
        [[d["code"], d["name"], d["deliverable"], d["db_tier"], d["review_tier"],
          "/".join(map(str, d["d1_d6"])) + f' · {d["total"]}/18', d["vn_bridge"]] for d in v["deliveries"]]
    ))
    out.append(f"\n⚠️ {content['panel_f']['warning']}\n")
    out.append("\n### 新增输入与采用方式\n")
    out.append(_md_table(["输入文件", "命中", "进入页面", "限制"], content["panel_f"]["extra_inputs_table"]))
    out.append("\n### 本轮采用的OB补充证据\n")
    for e in content["panel_f"]["evidence_list"]:
        out.append(f"- {e}\n")

    out.append(f"\n---\n{content['footer']}\n")
    return "\n".join(out)


def export_l3_report(l3_code: str, demo_html_path: Path) -> dict:
    content = extract_demo_content(demo_html_path, l3_code)
    return {"html": render_report_html(l3_code, content), "md": render_report_md(l3_code, content)}
