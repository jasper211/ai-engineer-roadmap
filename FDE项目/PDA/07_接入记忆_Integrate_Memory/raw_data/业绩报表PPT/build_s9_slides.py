"""
build_s9_slides.py
────────────────────────────────────────────────────────────────────────
• 删除最后一页（原第13页，slide11的备份）
• 新增三页 S9 分析页：
    Page A — 代理人业务·天领业务
    Page B — 代理人业务·成事家办
    Page C — KA业务（ICLUB+合伙转介+IFA）

每页布局：
  左上：3 个 KPI 卡片（批核APE / 未批核APE / 待签APE）
  左中下：KA明细表（8列）
  右上：月度明细分析图（预约/签单/批核 × 月份，柱+折线双轴）
  右下：本周快报表（KEY ACCOUNT × 预约/签单/批核）

用法：
  python build_s9_slides.py <input.pptx> <s9_excel.xlsx> [output.pptx]
"""

import sys, io, copy
from pathlib import Path
import openpyxl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.font_manager as _fm
import numpy as np
from lxml import etree
from pptx import Presentation
from pptx.util import Emu as E, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── CJK font ────────────────────────────────────────────────────────
# ── CJK 字体配置（Windows / Linux 自动适配）────────────────────────
import os as _os2
_CJK_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
_CJK = next((p for p in _CJK_CANDIDATES if _os2.path.exists(p)), None)
try:
    if _CJK:
        _fm.fontManager.addfont(_CJK)
        _cjk_name = _fm.FontProperties(fname=_CJK).get_name()
        plt.rcParams.update({"font.sans-serif": [_cjk_name, "DejaVu Sans"],
                             "axes.unicode_minus": False})
except Exception:
    pass

# ── args ─────────────────────────────────────────────────────────────
PPTX_IN  = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/mnt/user-data/outputs/周业绩汇报PPT_WITH_SLIDE12.pptx")
EXCEL_IN = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/mnt/user-data/uploads/业绩分析报表_0528.xlsx")
PPTX_OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/mnt/user-data/outputs/周业绩汇报PPT_S9.pptx")

NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

# ── slide dimensions ─────────────────────────────────────────────────
SW = 12192000;  SH = 6858000

# ── colour palette ───────────────────────────────────────────────────
CLR_TITLE_BG  = RGBColor(0x1B, 0x2A, 0x4A)   # dark navy (header bar)
CLR_CARD_BORDER = {
    "批核":  RGBColor(0x1A, 0x5E, 0x42),       # green
    "未批核": RGBColor(0x1A, 0x5E, 0x42),
    "待签":  RGBColor(0x5D, 0x1A, 0x1A),       # dark red
}
CLR_VALUE = {
    "批核":   RGBColor(0x1B, 0x6B, 0x3A),
    "未批核":  RGBColor(0x1B, 0x6B, 0x3A),
    "待签":   RGBColor(0x8B, 0x1A, 0x1A),
}
CLR_TBL_HDR   = RGBColor(0x1B, 0x4F, 0x72)
CLR_TBL_TOTAL = RGBColor(0x1B, 0x4F, 0x72)
CLR_TBL_ROW1  = RGBColor(0xFF, 0xFF, 0xFF)
CLR_TBL_ROW2  = RGBColor(0xF2, 0xF7, 0xFF)
CLR_WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
CLR_DARK      = RGBColor(0x1A, 0x27, 0x44)
CLR_ACCENT    = RGBColor(0x4A, 0x7A, 0xBF)    # medium blue for approved APE
CLR_UNBAT     = RGBColor(0xE8, 0x96, 0x2C)    # orange for unapproved
CLR_PEND      = RGBColor(0x8B, 0x1A, 0x1A)    # red for pending

# matplotlib chart colours
MC_BG   = "#FFFFFF";  MC_PANEL = "#EEF3FA"
MC_BAR  = "#2B5BA8";  MC_LINE  = "#F5A623"
MC_TEXT = "#1A2744";  MC_AXIS  = "#555555"
MC_GRID = "#D9E5F5";  MC_BAR2  = "#E8962C"

# ── layout constants (EMU) ───────────────────────────────────────────
TITLE_H   = 380000
TITLE_T   = 0

# KPI row  (3 cards, left side)
KPI_T  = 430000;  KPI_H  = 800000
KPI_W  = 1900000; KPI_GAP = 60000
KPI_L0 = 100000

# KA table (left side, below KPI cards)
TBL_L  = 100000;  TBL_T  = 1310000
TBL_W  = 6000000; TBL_H  = 5220000   # fills to bottom

# Right panel
RPL = 6280000
RPW = SW - RPL - 80000               # ~5832000
MONTHLY_T  = 430000;  MONTHLY_H = 3000000
WEEKLY_T   = 3550000; WEEKLY_H  = 3180000

# ══════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════

def _num(v):
    if v is None: return 0.0
    try: return float(v)
    except: return 0.0


def _to_m(v): return round(_num(v) / 1_000_000, 2)


def load_s9(excel_path):
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb["S9_代理人与KA业务"]
    rows = list(ws.iter_rows(values_only=True))

    # ── section index map ──
    sec = {}  # label → 0-based start row index of header
    for i, row in enumerate(rows):
        v = str(row[0]).strip() if row[0] else ""
        if v.startswith("A."):   sec["A"] = i
        elif v.startswith("B."): sec["B"] = i
        elif v.startswith("C."): sec["C"] = i
        elif v.startswith("D."): sec["D"] = i
        elif v.startswith("E."): sec["E"] = i
        elif v.startswith("G."): sec["G"] = i
        elif v.startswith("H."): sec["H"] = i
        elif v.startswith("I."): sec["I"] = i
        elif v.startswith("J."): sec["J"] = i

    # ── A: annual summary ──
    a_hdr = rows[sec["A"] + 2]   # ['业务细分','目标APE','达成率','2026批核APE','批核件数','未批核APE',...]
    a_data = {}
    for row in rows[sec["A"] + 3:]:
        name = str(row[0]).strip() if row[0] else ""
        if not name or name == "合计": break
        a_data[name] = {
            "批核APE":    _num(row[3]),
            "批核件数":   _num(row[4]),
            "未批核APE":  _num(row[5]),
            "未批核件数": _num(row[6]),
            "待签APE":    _num(row[7]),
            "待签件数":   _num(row[8]),
            "合计APE":   _num(row[9]),
            "合计件数":  _num(row[10]),
        }

    # ── B / C: KA breakdown (天领 / 成事家办) ──
    def _parse_ka_block(start):
        hdr = rows[start + 2]  # KEY ACCOUNT, 批核APE, 批核件数, ...
        out = []
        for row in rows[start + 3:]:
            name = str(row[0]).strip() if row[0] else ""
            if not name: break
            out.append({
                "KEY ACCOUNT": name,
                "2026批核APE": _num(row[1]),
                "批核件数":    _num(row[2]),
                "未批核APE":  _num(row[3]),
                "未批核件数": _num(row[4]),
                "待签APE":    _num(row[5]),
                "待签件数":   _num(row[6]),
                "合计APE":   _num(row[7]),
                "合计件数":  _num(row[8]),
            })
        return out

    b_ka = _parse_ka_block(sec["B"])
    c_ka = _parse_ka_block(sec["C"])

    # ── F: KA (ICLUB + 合伙转介 + IFA) merged KA table ──
    # Parse F-ICLUB, F-合伙转介, F-IFA and merge by KEY ACCOUNT
    f_ka_map = {}
    f_blocks = []
    for i, row in enumerate(rows):
        v = str(row[0]).strip() if row[0] else ""
        if v.startswith("F-") and "KA汇总" in v:
            f_blocks.append(i)
    for bi in f_blocks:
        hdr_i = bi + 2
        for row in rows[hdr_i + 1:]:
            name = str(row[0]).strip() if row[0] else ""
            if not name: break  # stop on blank, not zero
            if name == "合计": continue
            d = {
                "2026批核APE": _num(row[1]),
                "批核件数":    _num(row[2]),
                "未批核APE":  _num(row[3]),
                "未批核件数": _num(row[4]),
                "待签APE":    _num(row[5]),
                "待签件数":   _num(row[6]),
                "合计APE":   _num(row[7]),
                "合计件数":  _num(row[8]),
            }
            if name in f_ka_map:
                for k in d: f_ka_map[name][k] += d[k]
            else:
                f_ka_map[name] = d
    f_ka = [{"KEY ACCOUNT": k, **v} for k, v in f_ka_map.items()]
    # sort by 合计APE desc, add synthetic 合计 row
    f_ka.sort(key=lambda x: -x["合计APE"])
    ka_total = {k: sum(r[k] for r in f_ka) for k in
                ["2026批核APE","批核件数","未批核APE","未批核件数","待签APE","待签件数","合计APE","合计件数"]}
    ka_total["KEY ACCOUNT"] = "合计"

    # ── monthly blocks (D, E, G) ──
    def _parse_monthly(start):
        hdr = rows[start + 2]   # ['指标', '2026-01', ...]
        months = [str(h) for h in hdr[1:] if h and str(h).startswith("2026-")]
        data = {}
        for row in rows[start + 3:]:
            ind = str(row[0]).strip() if row[0] else ""
            if not ind: break
            data[ind] = [_num(row[1 + i]) for i in range(len(months))]
        return months, data

    d_months, d_data = _parse_monthly(sec["D"])
    e_months, e_data = _parse_monthly(sec["E"])
    g_months, g_data = _parse_monthly(sec["G"])

    # ── weekly blocks (H, I, J) ──
    def _parse_weekly(start):
        """Parse one weekly section (H/I/J) and return:
           week_cols, sub_tables dict:
             {'预约APE': {ka: [w1..wN]}, '签单APE': {...}, '批核APE': {...}}
        """
        sub_labels = ["预约—APE", "签单—APE", "批核—APE"]
        result = {}
        week_cols = None
        i = start + 2
        end = len(rows)
        while i < end:
            v = str(rows[i][0]).strip() if rows[i][0] else ""
            for sl in sub_labels:
                if v.startswith(sl):
                    # skip 📌 line
                    j = i + 1
                    while j < end and (not rows[j][0] or str(rows[j][0]).startswith("📌")):
                        j += 1
                    hdr = rows[j]
                    if week_cols is None:
                        week_cols = [str(h) for h in hdr[1:] if h and str(h).startswith("2026W")]
                    ka_dict = {}
                    for row in rows[j + 1:]:
                        name = str(row[0]).strip() if row[0] else ""
                        if not name: break
                        ka_dict[name] = [_num(row[1 + k]) for k in range(len(week_cols))]
                    key = sl.replace("—", "").replace(" ", "")  # 预约APE / 签单APE / 批核APE
                    result[key] = ka_dict
                    break
            i += 1
            # Stop when we hit the next top-level section
            if v and len(v) > 1 and v[1] == '.' and v[0].isupper() and i > start + 5:
                break
        return week_cols, result

    h_weeks, h_data = _parse_weekly(sec["H"])
    i_weeks, i_data = _parse_weekly(sec["I"])
    j_weeks, j_data = _parse_weekly(sec["J"])

    # Parse F sub-tables separately for split display
    def _parse_f_block(header_start):
        hdr_i = header_start + 2
        out = []
        for row in rows[hdr_i + 1:]:
            name = str(row[0]).strip() if row[0] else ""
            if not name: break  # stop on blank row only, not on zero value
            out.append({
                "KEY ACCOUNT": name,
                "2026批核APE": _num(row[1]),
                "批核件数":    _num(row[2]),
                "未批核APE":  _num(row[3]),
                "未批核件数": _num(row[4]),
                "待签APE":    _num(row[5]),
                "待签件数":   _num(row[6]),
                "合计APE":   _num(row[7]),
                "合计件数":  _num(row[8]),
            })
        return out

    f_iclub = _parse_f_block(f_blocks[0]) if len(f_blocks) > 0 else []
    f_hezhu = _parse_f_block(f_blocks[1]) if len(f_blocks) > 1 else []
    f_ifa   = _parse_f_block(f_blocks[2]) if len(f_blocks) > 2 else []

    # ── KA KPI: sum ICLUB+合伙转介+IFA from A table ──────────────────
    ka_keys = ["ICLUB业务", "合伙转介业务", "IFA业务"]
    ka_kpi = {"批核APE": 0, "批核件数": 0, "未批核APE": 0, "未批核件数": 0,
               "待签APE": 0, "待签件数": 0}
    for k in ka_keys:
        if k in a_data:
            ka_kpi["批核APE"]   += a_data[k]["批核APE"]
            ka_kpi["批核件数"]   += a_data[k]["批核件数"]
            ka_kpi["未批核APE"]  += a_data[k]["未批核APE"]
            ka_kpi["未批核件数"] += a_data[k]["未批核件数"]
            ka_kpi["待签APE"]    += a_data[k]["待签APE"]
            ka_kpi["待签件数"]   += a_data[k]["待签件数"]

    # ── KA current-month KPIs from G table ────────────────────────────
    g_start = sec["G"]
    g_hdr   = rows[g_start + 2]   # ['指标', '2026-01', ...]
    g_months = [h for h in g_hdr[1:] if h and str(h).startswith("2026-")]
    # find last month with non-zero data
    g_data_rows = {}
    for row in rows[g_start + 3:]:
        ind = str(row[0]).strip() if row[0] else ""
        if not ind: break
        g_data_rows[ind] = [_num(row[1 + i]) for i in range(len(g_months))]

    cur_mo_idx = 0
    for mi in range(len(g_months) - 1, -1, -1):
        if (g_data_rows.get("批核 APE", [0]*len(g_months))[mi] or
            g_data_rows.get("预约 APE", [0]*len(g_months))[mi]) > 0:
            cur_mo_idx = mi
            break

    ka_monthly_kpi = {
        "预约APE":   g_data_rows.get("预约 APE",  [0]*len(g_months))[cur_mo_idx],
        "预约件数":  g_data_rows.get("预约 件数",  [0]*len(g_months))[cur_mo_idx],
        "签单APE":   g_data_rows.get("签单 APE",  [0]*len(g_months))[cur_mo_idx],
        "签单件数":  g_data_rows.get("签单 件数",  [0]*len(g_months))[cur_mo_idx],
        "批核APE":   g_data_rows.get("批核 APE",  [0]*len(g_months))[cur_mo_idx],
        "批核件数":  g_data_rows.get("批核 件数",  [0]*len(g_months))[cur_mo_idx],
        "月份标签":  str(g_months[cur_mo_idx]) if cur_mo_idx < len(g_months) else "本月",
    }

    # ── Merge 天领+成事家办 monthly (D+E) ────────────────────────────
    merged_months = d_months  # same month list
    merged_monthly = {}
    for k in set(list(d_data.keys()) + list(e_data.keys())):
        d_vals = d_data.get(k, [0]*len(d_months))
        e_vals = e_data.get(k, [0]*len(e_months))
        n = len(merged_months)
        merged_monthly[k] = [(_num(d_vals[i] if i < len(d_vals) else 0) +
                               _num(e_vals[i] if i < len(e_vals) else 0))
                              for i in range(n)]

    # ── Merge 天领+成事家办 weekly (H+I) ──────────────────────────────
    def _merge_weekly(wa, wb_data):
        """Merge two weekly dicts: {stage: {ka: [w1..wN]}}"""
        result = {}
        all_stages = set(list(wa.keys()) + list(wb_data.keys()))
        for stage in all_stages:
            a_kas = wa.get(stage, {})
            b_kas = wb_data.get(stage, {})
            merged_kas = {"合计": [0]*len(h_weeks)}
            all_kas = set(list(a_kas.keys()) + list(b_kas.keys()))
            for ka in all_kas:
                a_v = a_kas.get(ka, [0]*len(h_weeks))
                b_v = b_kas.get(ka, [0]*len(h_weeks))
                n = len(h_weeks)
                merged_kas[ka] = [(_num(a_v[i] if i < len(a_v) else 0) +
                                   _num(b_v[i] if i < len(b_v) else 0))
                                  for i in range(n)]
            # recompute 合计
            for i in range(len(h_weeks)):
                merged_kas["合计"][i] = sum(
                    merged_kas[k][i] for k in merged_kas if k != "合计")
            result[stage] = merged_kas
        return result

    merged_weekly_data = _merge_weekly(h_data, i_data)

    # ── Agent KPIs (天领+成事家办 combined from A table) ──────────────
    agent_keys = ["天领业务", "成事家办"]
    agent_kpi = {"批核APE": 0, "批核件数": 0, "未批核APE": 0, "未批核件数": 0,
                 "待签APE": 0, "待签件数": 0, "合计APE": 0, "合计件数": 0}
    for k in agent_keys:
        if k in a_data:
            for f in agent_kpi: agent_kpi[f] += a_data[k][f]

    # ── Agent current-month KPIs (from merged_monthly) ────────────────
    cur_mo_agent = 0
    for mi in range(len(merged_months)-1, -1, -1):
        if merged_monthly.get("批核 APE", [0]*len(merged_months))[mi] > 0:
            cur_mo_agent = mi; break
    mo_str_agent = str(merged_months[cur_mo_agent])
    try:    mo_label_agent = f"{int(mo_str_agent.split('-')[1])}月"
    except: mo_label_agent = "本月"
    agent_monthly_kpi = {
        "预约APE":   merged_monthly.get("预约 APE",  [0]*len(merged_months))[cur_mo_agent],
        "预约件数":  merged_monthly.get("预约 件数",  [0]*len(merged_months))[cur_mo_agent],
        "签单APE":   merged_monthly.get("签单 APE",  [0]*len(merged_months))[cur_mo_agent],
        "签单件数":  merged_monthly.get("签单 件数",  [0]*len(merged_months))[cur_mo_agent],
        "批核APE":   merged_monthly.get("批核 APE",  [0]*len(merged_months))[cur_mo_agent],
        "批核件数":  merged_monthly.get("批核 件数",  [0]*len(merged_months))[cur_mo_agent],
        "月份标签":  mo_str_agent,
        "月份中文":  mo_label_agent,
    }

    return {
        "a_data": a_data,
        "b_ka": b_ka, "c_ka": c_ka,
        "f_ka": f_ka, "f_ka_total": ka_total,
        "f_iclub": f_iclub, "f_hezhu": f_hezhu, "f_ifa": f_ifa,
        "ka_kpi": ka_kpi, "ka_monthly_kpi": ka_monthly_kpi,
        "agent_kpi": agent_kpi, "agent_monthly_kpi": agent_monthly_kpi,
        "d": (d_months, d_data),
        "e": (e_months, e_data),
        "de_merged": (merged_months, merged_monthly),
        "hi_merged": (h_weeks, merged_weekly_data),
        "g": (g_months, g_data),
        "h": (h_weeks, h_data),
        "i": (i_weeks, i_data),
        "j": (j_weeks, j_data),
    }


# ══════════════════════════════════════════════════════════════════════
# CHART GENERATORS
# ══════════════════════════════════════════════════════════════════════

def _make_monthly_chart(months, data, title, dpi=150, figsize=(6.1, 3.1)):
    """月度明细柱状+折线双轴图（APE 柱 + 件数折线）。"""
    active_months = [m for m in months if
                     (data.get("预约 APE", [0]*len(months))[months.index(m)] or 0) > 0 or
                     (data.get("批核 APE", [0]*len(months))[months.index(m)] or 0) > 0]
    if not active_months:
        active_months = months

    labels_zh = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]
    def _lbl(m):
        try: return labels_zh[int(m.split("-")[1]) - 1]
        except: return m

    x_labels = [_lbl(m) for m in active_months]
    idxs = [months.index(m) for m in active_months]

    appt = [(data.get("预约 APE", [0]*len(months))[i] or 0) / 10000 for i in idxs]
    sign = [(data.get("签单 APE", [0]*len(months))[i] or 0) / 10000 for i in idxs]
    biz  = [(data.get("批核 APE", [0]*len(months))[i] or 0) / 10000 for i in idxs]
    cnt  = [(data.get("批核 件数", [0]*len(months))[i] or 0) for i in idxs]

    n = len(x_labels); x = np.arange(n); w = 0.28
    fig, ax1 = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor(MC_BG); ax1.set_facecolor(MC_PANEL)

    b1 = ax1.bar(x - w, appt, width=w, color="#A8C4E8", label="预约APE", zorder=2)
    b2 = ax1.bar(x,     sign, width=w, color=MC_BAR2,  label="签单APE", zorder=2)
    b3 = ax1.bar(x + w, biz,  width=w, color=MC_BAR,   label="批核APE", zorder=2)
    max_ape = max(max(appt,default=0), max(sign,default=0), max(biz,default=0))

    for bar, val in zip(b3, biz):
        if val > 0:
            ax1.text(bar.get_x()+bar.get_width()/2, bar.get_height()+max_ape*0.02,
                     f"{int(round(val))}", ha="center", va="bottom",
                     color=MC_TEXT, fontsize=6.5, fontweight="bold")

    ax1.set_ylabel("APE（万元）", color=MC_TEXT, fontsize=7.5)
    ax1.tick_params(axis="y", labelcolor=MC_AXIS, labelsize=6.5)
    ax1.tick_params(axis="x", labelcolor=MC_TEXT, labelsize=8)
    ax1.set_xticks(x); ax1.set_xticklabels(x_labels)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_: f"{int(v):,}"))
    ax1.spines[:].set_visible(False)
    ax1.grid(axis="y", color=MC_GRID, linewidth=0.5, zorder=0)
    ax1.set_xlim(-0.6, n-0.4); ax1.set_ylim(0, max_ape*1.3 if max_ape else 1)

    ax2 = ax1.twinx(); ax2.set_facecolor("none")
    ax2.plot(x+w/2, cnt, color=MC_LINE, marker="o", markersize=5,
             linewidth=1.8, zorder=3, linestyle="--", label="批核件数")
    max_cnt = max(cnt) if cnt else 1
    for xi, cv in zip(x+w/2, cnt):
        if cv > 0:
            ax2.text(xi, cv+max_cnt*0.08, str(int(cv)), ha="center", va="bottom",
                     color=MC_LINE, fontsize=6.5)
    ax2.set_ylabel("件数", color=MC_LINE, fontsize=7.5)
    ax2.tick_params(axis="y", labelcolor=MC_LINE, labelsize=6.5)
    ax2.spines[:].set_visible(False)
    ax2.set_ylim(0, max_cnt*1.5 if max_cnt else 1)

    from matplotlib.lines import Line2D; from matplotlib.patches import Patch
    leg = [Patch(facecolor="#A8C4E8",label="预约APE"), Patch(facecolor=MC_BAR2,label="签单APE"),
           Patch(facecolor=MC_BAR,label="批核APE"),
           Line2D([0],[0],color=MC_LINE,marker="o",markersize=4,linestyle="--",label="批核件数")]
    ax1.legend(handles=leg,loc="upper right",framealpha=0.3,
               labelcolor=MC_TEXT,fontsize=6,facecolor=MC_BG,ncol=2)
    fig.suptitle(title,color=MC_TEXT,fontsize=8.5,x=0.02,ha="left",y=0.99,fontweight="bold")
    plt.tight_layout(rect=[0,0,1,0.94])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=MC_BG, dpi=dpi, bbox_inches="tight")
    plt.close(fig); buf.seek(0)
    return buf



# ══════════════════════════════════════════════════════════════════════
# PPT SHAPE HELPERS
# ══════════════════════════════════════════════════════════════════════

def _rgb_to_xml(r, g, b):
    return f"{r:02X}{g:02X}{b:02X}"


def _set_cell_text(cell, text, bold=False, font_size=None, font_color=None,
                   align=PP_ALIGN.LEFT):
    tf = cell.text_frame
    tf.word_wrap = True
    if not tf.paragraphs:
        tf.add_paragraph()
    p = tf.paragraphs[0]
    p.alignment = align
    if not p.runs:
        p.add_run()
    run = p.runs[0]
    run.text = str(text)
    run.font.bold = bold
    if font_size: run.font.size = Pt(font_size)
    if font_color: run.font.color.rgb = font_color


def _fill_cell(cell, rgb: RGBColor):
    from pptx.oxml.ns import qn
    from lxml import etree
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    solidFill = etree.SubElement(tcPr, qn("a:solidFill"))
    srgb = etree.SubElement(solidFill, qn("a:srgbClr"))
    srgb.set("val", str(rgb))


def add_kpi_card(slide, left, top, width, height, label, value, sub_text, color: RGBColor):
    """Draw a KPI card: label (small) / value (large) / sub_text (small)."""
    from pptx.oxml.ns import qn
    from pptx.util import Pt
    # Outer border rectangle
    shp = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        E(left), E(top), E(width), E(height)
    )
    shp.fill.background()
    line = shp.line
    line.color.rgb = color
    line.width = E(30000)

    # Left accent bar
    bar = slide.shapes.add_shape(1, E(left), E(top), E(30000), E(height))
    bar.fill.solid()
    bar.fill.fore_color.rgb = color
    bar.line.fill.background()

    # Label text
    lbl = slide.shapes.add_textbox(E(left + 50000), E(top + 60000),
                                    E(width - 70000), E(180000))
    tf = lbl.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = label
    run.font.size = Pt(9)
    run.font.color.rgb = CLR_DARK
    run.font.bold = False

    # Value text
    val_box = slide.shapes.add_textbox(E(left + 50000), E(top + 220000),
                                        E(width - 70000), E(320000))
    tf2 = val_box.text_frame
    p2 = tf2.paragraphs[0]
    r2 = p2.add_run()
    r2.text = value
    r2.font.size = Pt(22)
    r2.font.bold = True
    r2.font.color.rgb = color

    # Sub text
    sub_box = slide.shapes.add_textbox(E(left + 50000), E(top + 560000),
                                        E(width - 70000), E(180000))
    tf3 = sub_box.text_frame
    p3 = tf3.paragraphs[0]
    r3 = p3.add_run()
    r3.text = sub_text
    r3.font.size = Pt(8)
    r3.font.color.rgb = CLR_AXIS = RGBColor(0x55, 0x55, 0x55)




def add_six_kpi_cards(slide, ka_kpi, ka_monthly_kpi, top=430000):
    """6 full-width KPI cards — pixel-perfect Bank View replica.

    Per card (left→right × 6):
      Shape_bg   : white rect  w=1828800 h=762000  fill=FFFFFF  border=E8ECF0 (1pt)
      Shape_bar  : accent bar  w=76200   h=762000  fill=accent_color
      Text_label : small grey  t=+54610  h=182245  color=64748B  9pt
      Text_value : big bold    t=+228600 h=297815  color=accent_color  22pt bold
      Text_sub   : small grey  t=+539115 h=149225  color=64748B  8pt
    """
    from pptx.oxml.ns import qn as _qn_pptx

    CARD_W  = 1828800
    CARD_H  = 762000
    BAR_W   = 76200
    MARGIN  = 182880
    STEP    = 1993265          # distance between card lefts
    LBL_OFF = 109835           # text left offset from card left
    TXT_W   = 1682750

    T_LBL  = top + 54610      # label top
    T_VAL  = top + 228600     # value top
    T_SUB  = top + 539115     # sub top
    H_LBL  = 182245
    H_VAL  = 297815
    H_SUB  = 149225

    # accent colours  (accent bar + value text)
    ACCENTS = [
        "1B4F72",  # KA批核      — dark blue
        "117A65",  # KA未批核    — green
        "00796B",  # KA待签      — teal
        "9B2335",  # 本月预约    — dark red
        "6B2737",  # 本月签单    — maroon
        "6C3483",  # 本月批核    — purple
    ]

    mo_lbl = ka_monthly_kpi["月份标签"]   # e.g. "2026-05"
    try:    mo_str = f"{int(mo_lbl.split('-')[1])}月"
    except: mo_str = "本月"

    def _ape_str(v):
        m = v / 1_000_000
        return f"{m:.2f}M" if m < 10 else f"{m:.1f}M"

    def _sub_str(ape, cnt):
        cnt_i = int(cnt)
        avg   = f"{ape/cnt/10000:.1f}W" if cnt > 0 else "0W"
        return f"{cnt_i}件 | 件均{avg}"

    cards = [
        ("KA批核",
         _ape_str(ka_kpi["批核APE"]),
         _sub_str(ka_kpi["批核APE"], ka_kpi["批核件数"])),
        ("KA未批核",
         _ape_str(ka_kpi["未批核APE"]),
         _sub_str(ka_kpi["未批核APE"], ka_kpi["未批核件数"])),
        ("KA待签",
         _ape_str(ka_kpi["待签APE"]),
         _sub_str(ka_kpi["待签APE"], ka_kpi["待签件数"])),
        (f"KA {mo_str}预约",
         _ape_str(ka_monthly_kpi["预约APE"]),
         _sub_str(ka_monthly_kpi["预约APE"], ka_monthly_kpi["预约件数"])),
        (f"KA {mo_str}签单",
         _ape_str(ka_monthly_kpi["签单APE"]),
         _sub_str(ka_monthly_kpi["签单APE"], ka_monthly_kpi["签单件数"])),
        (f"KA {mo_str}批核",
         _ape_str(ka_monthly_kpi["批核APE"]),
         _sub_str(ka_monthly_kpi["批核APE"], ka_monthly_kpi["批核件数"])),
    ]

    from lxml import etree
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

    def _rgb(hex6):
        return RGBColor(int(hex6[:2],16), int(hex6[2:4],16), int(hex6[4:],16))

    for ci, ((label, val_str, sub_str), accent_hex) in enumerate(zip(cards, ACCENTS)):
        card_l = MARGIN + ci * STEP
        accent = _rgb(accent_hex)

        # ── Background rect ────────────────────────────────────────
        bg = slide.shapes.add_shape(1, E(card_l), E(top), E(CARD_W), E(CARD_H))
        bg.fill.solid(); bg.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        bg.line.color.rgb = RGBColor(0xE8, 0xEC, 0xF0)
        bg.line.width = E(9525)   # ~0.75 pt

        # ── Accent bar ─────────────────────────────────────────────
        bar = slide.shapes.add_shape(1, E(card_l), E(top), E(BAR_W), E(CARD_H))
        bar.fill.solid(); bar.fill.fore_color.rgb = accent
        bar.line.fill.background()

        # ── Label textbox ──────────────────────────────────────────
        tb_lbl = slide.shapes.add_textbox(
            E(card_l + LBL_OFF), E(T_LBL), E(TXT_W), E(H_LBL))
        tf = tb_lbl.text_frame; p = tf.paragraphs[0]
        r = p.add_run(); r.text = label
        r.font.size = Pt(9); r.font.bold = False
        r.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

        # ── Value textbox ──────────────────────────────────────────
        tb_val = slide.shapes.add_textbox(
            E(card_l + LBL_OFF), E(T_VAL), E(TXT_W), E(H_VAL))
        tf2 = tb_val.text_frame; p2 = tf2.paragraphs[0]
        r2 = p2.add_run(); r2.text = val_str
        r2.font.size = Pt(22); r2.font.bold = True
        r2.font.color.rgb = accent

        # ── Sub textbox ────────────────────────────────────────────
        tb_sub = slide.shapes.add_textbox(
            E(card_l + LBL_OFF), E(T_SUB), E(TXT_W), E(H_SUB))
        tf3 = tb_sub.text_frame; p3 = tf3.paragraphs[0]
        r3 = p3.add_run(); r3.text = sub_str
        r3.font.size = Pt(8); r3.font.bold = False
        r3.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    return CARD_H   # caller uses this to find where next section starts


def add_title_bar(slide, title, subtitle=""):
    """Full-width dark title bar at top."""
    bar = slide.shapes.add_shape(1, E(0), E(0), E(SW), E(TITLE_H))
    bar.fill.solid()
    bar.fill.fore_color.rgb = CLR_TITLE_BG
    bar.line.fill.background()

    tb = slide.shapes.add_textbox(E(150000), E(60000), E(8000000), E(280000))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.size = Pt(16)
    r.font.bold = True
    r.font.color.rgb = CLR_WHITE

    if subtitle:
        tb2 = slide.shapes.add_textbox(E(SW - 2200000), E(80000), E(2100000), E(220000))
        tf2 = tb2.text_frame
        p2 = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.RIGHT
        r2 = p2.add_run()
        r2.text = subtitle
        r2.font.size = Pt(8)
        r2.font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)


def add_section_header(slide, left, top, width, height, text, bg: RGBColor):
    hdr = slide.shapes.add_shape(1, E(left), E(top), E(width), E(height))
    hdr.fill.solid()
    hdr.fill.fore_color.rgb = bg
    hdr.line.fill.background()
    tb = slide.shapes.add_textbox(E(left + 80000), E(top + 30000),
                                   E(width - 100000), E(height - 40000))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    r.font.size = Pt(10)
    r.font.bold = True
    r.font.color.rgb = CLR_WHITE


def add_ka_table(slide, left, top, width, height, ka_rows, include_total=True):
    """
    Draw a table with columns:
    KEY ACCOUNT | 批核APE | 批核件数 | 未批核APE | 未批核件数 | 待签APE | 待签件数 | 合计APE | 合计件数
    """
    COLS = ["KEY ACCOUNT", "批核APE(万)", "批核\n件数", "未批核APE(万)", "未批核\n件数",
            "待签APE(万)", "待签\n件数", "合计APE(万)", "合计\n件数"]
    # add 合计 row if needed
    if include_total:
        total = {
            "KEY ACCOUNT": "合计",
            "2026批核APE": sum(r["2026批核APE"] for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "批核件数":    sum(r["批核件数"]    for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "未批核APE":  sum(r["未批核APE"]   for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "未批核件数": sum(r["未批核件数"]   for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "待签APE":    sum(r["待签APE"]     for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "待签件数":   sum(r["待签件数"]     for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "合计APE":   sum(r["合计APE"]     for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "合计件数":  sum(r["合计件数"]     for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
        }
        display_rows = [r for r in ka_rows if r["KEY ACCOUNT"] != "合计"] + [total]
    else:
        display_rows = ka_rows

    nrows = len(display_rows) + 1   # +1 header
    ncols = 9
    tbl_shape = slide.shapes.add_table(nrows, ncols, E(left), E(top), E(width), E(height))
    tbl = tbl_shape.table

    # Column widths (proportional)
    col_ws = [0.20, 0.10, 0.065, 0.12, 0.065, 0.10, 0.065, 0.12, 0.065]
    total_w = sum(col_ws)
    for ci, cw in enumerate(col_ws):
        tbl.columns[ci].width = E(int(width * cw / total_w))

    # Header row
    for ci, hdr in enumerate(COLS):
        cell = tbl.cell(0, ci)
        _fill_cell(cell, CLR_TBL_HDR)
        _set_cell_text(cell, hdr, bold=True, font_size=7.5,
                       font_color=CLR_WHITE, align=PP_ALIGN.CENTER)

    # Data rows
    def _fmt_ape(v): return f"{v/10000:.0f}" if v >= 10000 else f"{v/10000:.1f}"
    def _fmt_cnt(v): return str(int(v)) if v else "0"

    for ri, row in enumerate(display_rows):
        is_total = row["KEY ACCOUNT"] == "合计"
        bg = CLR_TBL_TOTAL if is_total else (CLR_TBL_ROW2 if ri % 2 else CLR_TBL_ROW1)
        vals = [
            row["KEY ACCOUNT"],
            _fmt_ape(row["2026批核APE"]),
            _fmt_cnt(row["批核件数"]),
            _fmt_ape(row["未批核APE"]),
            _fmt_cnt(row["未批核件数"]),
            _fmt_ape(row["待签APE"]),
            _fmt_cnt(row["待签件数"]),
            _fmt_ape(row["合计APE"]),
            _fmt_cnt(row["合计件数"]),
        ]
        for ci, val in enumerate(vals):
            cell = tbl.cell(ri + 1, ci)
            _fill_cell(cell, bg)
            align = PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER
            fc = CLR_WHITE if is_total else CLR_DARK
            _set_cell_text(cell, val, bold=is_total, font_size=7.5,
                           font_color=fc, align=align)



def add_ka_table_compact(slide, left, top, width, height, ka_rows, include_total=True):
    """精简版 KA 表：KEY ACCOUNT | 批核APE(万) | 未批核APE(万) | 待签APE(万) | 合计APE(万)
    去掉件数列，适合在小宽度内显示。
    """
    COLS = ["KEY ACCOUNT", "批核APE(万)", "未批核APE(万)", "待签APE(万)", "合计APE(万)"]
    if include_total:
        total = {
            "KEY ACCOUNT": "合计",
            "2026批核APE": sum(r["2026批核APE"] for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "未批核APE":   sum(r["未批核APE"]   for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "待签APE":     sum(r["待签APE"]     for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
            "合计APE":    sum(r["合计APE"]     for r in ka_rows if r["KEY ACCOUNT"] != "合计"),
        }
        display_rows = [r for r in ka_rows if r["KEY ACCOUNT"] != "合计"] + [total]
    else:
        display_rows = ka_rows

    nrows = len(display_rows) + 1
    ncols = 5
    tbl = slide.shapes.add_table(nrows, ncols,
                                  E(left), E(top), E(width), E(height)).table

    col_ws = [0.32, 0.17, 0.17, 0.17, 0.17]
    for ci, cw in enumerate(col_ws):
        tbl.columns[ci].width = E(int(width * cw))

    for ci, hdr in enumerate(COLS):
        cell = tbl.cell(0, ci)
        _fill_cell(cell, CLR_TBL_HDR)
        _set_cell_text(cell, hdr, bold=True, font_size=7,
                       font_color=CLR_WHITE, align=PP_ALIGN.CENTER)

    def _fmt(v): return f"{v/10000:.0f}" if v >= 10000 else (f"{v/10000:.1f}" if v > 0 else "—")

    for ri, row in enumerate(display_rows):
        is_total = row["KEY ACCOUNT"] == "合计"
        bg = CLR_TBL_TOTAL if is_total else (CLR_TBL_ROW2 if ri % 2 else CLR_TBL_ROW1)
        vals = [
            row["KEY ACCOUNT"],
            _fmt(row["2026批核APE"]),
            _fmt(row["未批核APE"]),
            _fmt(row["待签APE"]),
            _fmt(row["合计APE"]),
        ]
        for ci, val in enumerate(vals):
            cell = tbl.cell(ri + 1, ci)
            _fill_cell(cell, bg)
            align = PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER
            fc = CLR_WHITE if is_total else CLR_DARK
            _set_cell_text(cell, val, bold=is_total, font_size=7,
                           font_color=fc, align=align)


def add_weekly_table(slide, left, top, width, height, week_data, week_cols, title, current_week):
    """
    Draw 本周快报 table: KEY ACCOUNT × 预约(M) / 签单(M) / 批核(M)
    using the current_week column from week_data.
    """
    appt_d = week_data.get("预约APE", {})
    sign_d = week_data.get("签单APE", {})
    appr_d = week_data.get("批核APE", {})

    # Get index for current_week
    try:
        wi = week_cols.index(current_week)
    except ValueError:
        wi = len(week_cols) - 1

    def _get(d, ka): return d.get(ka, [0] * len(week_cols))[wi] if d.get(ka) else 0

    # Collect all KA with any activity
    all_ka = set(appt_d) | set(sign_d) | set(appr_d)
    all_ka.discard("合计")
    rows_data = []
    for ka in all_ka:
        a = _get(appt_d, ka); s = _get(sign_d, ka); p = _get(appr_d, ka)
        rows_data.append({"ka": ka, "appt": a, "sign": s, "appr": p})  # 全量显示
    rows_data.sort(key=lambda x: -(x["appt"] + x["sign"] + x["appr"]))

    # Add total
    tj = sum(r["appt"] for r in rows_data)
    tk = sum(r["sign"] for r in rows_data)
    tl = sum(r["appr"] for r in rows_data)

    # Section header
    wk_short = current_week.replace("2026", "")  # W20
    add_section_header(slide, left, top, width, 300000,
                       f"{wk_short} 本周快报 | {title}",
                       RGBColor(0x4A, 0x1F, 0x6A))  # purple

    tbl_top = top + 310000
    tbl_h   = height - 310000
    nrows = len(rows_data) + 2  # header + data + total
    ncols = 4
    tbl_shape = slide.shapes.add_table(nrows, ncols,
                                        E(left), E(tbl_top),
                                        E(width), E(tbl_h))
    tbl = tbl_shape.table
    # Column widths
    col_ws = [0.40, 0.20, 0.20, 0.20]
    for ci, cw in enumerate(col_ws): tbl.columns[ci].width = E(int(width * cw))

    for ci, hdr in enumerate(["KEY ACCOUNT", "预约(M)", "签单(M)", "批核(M)"]):
        cell = tbl.cell(0, ci)
        _fill_cell(cell, CLR_TBL_HDR)
        _set_cell_text(cell, hdr, bold=True, font_size=8, font_color=CLR_WHITE,
                       align=PP_ALIGN.CENTER)

    def _fmt_m(v): return f"{v/1_000_000:.2f}M"

    for ri, row in enumerate(rows_data):
        bg = CLR_TBL_ROW2 if ri % 2 else CLR_TBL_ROW1
        vals = [row["ka"], _fmt_m(row["appt"]), _fmt_m(row["sign"]), _fmt_m(row["appr"])]
        for ci, val in enumerate(vals):
            cell = tbl.cell(ri + 1, ci)
            _fill_cell(cell, bg)
            align = PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER
            _set_cell_text(cell, val, font_size=8, font_color=CLR_DARK, align=align)

    # Total row
    last = nrows - 1
    for ci, val in enumerate(["合计", _fmt_m(tj), _fmt_m(tk), _fmt_m(tl)]):
        cell = tbl.cell(last, ci)
        _fill_cell(cell, CLR_TBL_TOTAL)
        align = PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER
        _set_cell_text(cell, val, bold=True, font_size=8, font_color=CLR_WHITE, align=align)


def _get_current_week(week_cols):
    """Return the last week column that has any data."""
    return week_cols[-1] if week_cols else "2026W19"


# ══════════════════════════════════════════════════════════════════════
# SLIDE BUILDER
# ══════════════════════════════════════════════════════════════════════

def _a_data_sum(a_data, keys):
    """Sum A-table values across multiple business lines."""
    total = {"批核APE": 0, "批核件数": 0, "未批核APE": 0, "未批核件数": 0,
             "待签APE": 0, "待签件数": 0, "合计APE": 0, "合计件数": 0}
    for k in keys:
        if k in a_data:
            for f in total: total[f] += a_data[k][f]
    return total


def build_s9_slide(prs, data, biz_keys, ka_rows,
                   monthly_data, weekly_data,
                   page_title, section_subtitle, chart_title, table_title):
    """Add one S9 analysis slide to prs."""
    layout = prs.slide_layouts[0]   # blank layout
    slide = prs.slides.add_slide(layout)

    # 1. Title bar
    add_title_bar(slide, page_title, "内部文件 · 仅供使用")

    # 2. KPI cards (left top)
    kpi_info = [
        ("批核APE",   data["批核APE"],   data["批核件数"],   "批核"),
        ("未批核APE", data["未批核APE"],  data["未批核件数"], "未批核"),
        ("待签APE",   data["待签APE"],   data["待签件数"],   "待签"),
    ]
    for i, (field, ape, cnt, key) in enumerate(kpi_info):
        card_l = KPI_L0 + i * (KPI_W + KPI_GAP)
        color = CLR_VALUE[key]
        ape_m = ape / 1_000_000
        ape_str = f"{ape_m:.1f}M" if ape_m >= 10 else f"{ape_m:.2f}M"
        sub = f"{int(cnt)}件 | 件均{ape/cnt/10000:.1f}W" if cnt > 0 else "0件"
        add_kpi_card(slide, card_l, KPI_T, KPI_W, KPI_H,
                     f"{section_subtitle} {field}", ape_str, sub, color)

    # 3. KA table section header
    add_section_header(slide, TBL_L, TBL_T, TBL_W, 300000,
                       f"KA 业绩明细 | {section_subtitle}",
                       RGBColor(0x1B, 0x4F, 0x72))

    # 4. KA table
    ka_display = [r for r in ka_rows if r["KEY ACCOUNT"] != "合计"]
    table_row_h = max(1, len(ka_display) + 2)   # header + data + total
    add_ka_table(slide, TBL_L, TBL_T + 310000, TBL_W,
                 min(TBL_H - 310000, table_row_h * 320000 + 100000),
                 ka_display, include_total=True)

    # 5. Monthly chart
    months, mdata = monthly_data
    chart_buf = _make_monthly_chart(months, mdata, chart_title)
    slide.shapes.add_picture(chart_buf, E(RPL), E(MONTHLY_T), E(RPW), E(MONTHLY_H))

    # 6. Weekly table
    week_cols, wdata = weekly_data
    current_week = _get_current_week(week_cols)
    add_weekly_table(slide, RPL, WEEKLY_T, RPW, WEEKLY_H,
                     wdata, week_cols, table_title, current_week)

    return slide



# ══════════════════════════════════════════════════════════════════════
# KA业务 SPLIT-TABLE HELPERS
# ══════════════════════════════════════════════════════════════════════


def build_chengshi_slide(prs, cs_data, d):
    """成事家办页：6个全宽 KPI 卡片（KA汇总 + 本月）+ 成事家办明细。"""
    layout = prs.slide_layouts[0]
    slide  = prs.slides.add_slide(layout)

    add_title_bar(slide,
                  "代理人业务分析仪表盘  |成事家办 Agent Business View",
                  "内部文件 · 仅供使用")

    # ── 6 KPI 卡片（全宽）──────────────────────────────────────────
    card_h = add_six_kpi_cards(slide, d["ka_kpi"], d["ka_monthly_kpi"], top=430000)

    # 卡片底部下方为内容区起始
    content_top = 430000 + card_h + 80000   # ≈ 1230000

    # ── 成事家办 3 小卡片（批核/未批核/待签）— Bank View 同款样式 ──────
    # 与上方 6 卡片等宽等高，只用前3格位置
    CARD_W  = 1828800; CARD_H = 762000; BAR_W = 76200
    MARGIN  = 182880;  STEP   = 1993265; LBL_OFF = 109835; TXT_W = 1682750
    T_LBL  = content_top + 54610
    T_VAL  = content_top + 228600
    T_SUB  = content_top + 539115

    ACCENTS_CS = ["1B4F72", "117A65", "00796B"]   # 批核/未批核/待签

    cs_cards = [
        ("成事家办 批核APE",  cs_data["批核APE"],  cs_data["批核件数"]),
        ("成事家办 未批核APE",cs_data["未批核APE"], cs_data["未批核件数"]),
        ("成事家办 待签APE",  cs_data["待签APE"],  cs_data["待签件数"]),
    ]

    for i, ((label, ape, cnt), accent_hex) in enumerate(zip(cs_cards, ACCENTS_CS)):
        card_l = MARGIN + i * STEP
        accent = RGBColor(int(accent_hex[:2],16), int(accent_hex[2:4],16), int(accent_hex[4:],16))
        ape_m  = ape / 1_000_000
        val_str = f"{ape_m:.2f}M" if ape_m < 10 else f"{ape_m:.1f}M"
        sub_str = f"{int(cnt)}件 | 件均{ape/cnt/10000:.1f}W" if cnt > 0 else "0件 | 件均0W"

        bg = slide.shapes.add_shape(1, E(card_l), E(content_top), E(CARD_W), E(CARD_H))
        bg.fill.solid(); bg.fill.fore_color.rgb = RGBColor(0xFF,0xFF,0xFF)
        bg.line.color.rgb = RGBColor(0xE8,0xEC,0xF0); bg.line.width = E(9525)

        bar = slide.shapes.add_shape(1, E(card_l), E(content_top), E(BAR_W), E(CARD_H))
        bar.fill.solid(); bar.fill.fore_color.rgb = accent; bar.line.fill.background()

        for (tt, hh, txt, pt, bold) in [
            (T_LBL, 182245, label,   9,  False),
            (T_VAL, 297815, val_str, 22, True),
            (T_SUB, 149225, sub_str, 8,  False),
        ]:
            tb = slide.shapes.add_textbox(E(card_l+LBL_OFF), E(tt), E(TXT_W), E(hh))
            p  = tb.text_frame.paragraphs[0]; r = p.add_run(); r.text = txt
            r.font.size = Pt(pt); r.font.bold = bold
            r.font.color.rgb = accent if bold else RGBColor(0x64,0x74,0x8B)

    tbl_top = content_top + CARD_H + 180000  # 往下留间距

    # ── 成事家办 KA 明细表 ──────────────────────────────────────────
    add_section_header(slide, TBL_L, tbl_top, TBL_W, 290000,
                       "KA 业绩明细 | 成事家办", RGBColor(0x1B,0x4F,0x72))
    ka_rows = [r for r in d["c_ka"] if r["KEY ACCOUNT"] != "合计"]
    nrows_tbl = len(ka_rows) + 2
    tbl_h = min(SH - tbl_top - 290000 - 60000, nrows_tbl * 300000 + 80000)
    add_ka_table(slide, TBL_L, tbl_top + 300000, TBL_W, tbl_h,
                 ka_rows, include_total=True)

    # ── 月度图（右上）──────────────────────────────────────────────
    months, mdata = d["e"]
    chart_buf = _make_monthly_chart(months, mdata,
                                    "成事家办 2026年月度明细分析（含流失单）")
    slide.shapes.add_picture(chart_buf,
                              E(RPL), E(content_top),
                              E(RPW), E(MONTHLY_H))

    # ── 本周快报（右下）────────────────────────────────────────────
    week_cols, wdata = d["i"]
    current_week = _get_current_week(week_cols)
    add_weekly_table(slide,
                     RPL, content_top + MONTHLY_H + 80000,
                     RPW, SH - (content_top + MONTHLY_H + 80000) - 60000,
                     wdata, week_cols, "成事家办", current_week)
    return slide



def add_bank_view_3_cards(slide, data_list, top=None, content_top=None):
    """Draw exactly 3 Bank-View-style KPI cards (same geometry as add_six_kpi_cards).
    data_list: list of (label, ape, cnt, accent_hex)  — exactly 3 items.
    Cards span only first 3 slots (left half).
    """
    if top is None: top = content_top
    CARD_W=1828800; CARD_H=762000; BAR_W=76200
    MARGIN=182880; STEP=1993265; LBL_OFF=109835; TXT_W=1682750
    T_LBL=top+54610; T_VAL=top+228600; T_SUB=top+539115
    for i,(label,ape,cnt,accent_hex) in enumerate(data_list):
        card_l=MARGIN+i*STEP
        accent=RGBColor(int(accent_hex[:2],16),int(accent_hex[2:4],16),int(accent_hex[4:],16))
        ape_m=ape/1_000_000
        val_str=f"{ape_m:.2f}M" if ape_m<10 else f"{ape_m:.1f}M"
        avg_w=f"{ape/cnt/10000:.1f}W" if cnt>0 else "0W"
        sub_str=f"{int(cnt)}件 | 件均{avg_w}"
        bg=slide.shapes.add_shape(1,E(card_l),E(top),E(CARD_W),E(CARD_H))
        bg.fill.solid(); bg.fill.fore_color.rgb=RGBColor(0xFF,0xFF,0xFF)
        bg.line.color.rgb=RGBColor(0xE8,0xEC,0xF0); bg.line.width=E(9525)
        bar=slide.shapes.add_shape(1,E(card_l),E(top),E(BAR_W),E(CARD_H))
        bar.fill.solid(); bar.fill.fore_color.rgb=accent; bar.line.fill.background()
        for (tt,hh,txt,pt,bold) in [(T_LBL,182245,label,9,False),
                                     (T_VAL,297815,val_str,22,True),
                                     (T_SUB,149225,sub_str,8,False)]:
            tb=slide.shapes.add_textbox(E(card_l+LBL_OFF),E(tt),E(TXT_W),E(hh))
            p=tb.text_frame.paragraphs[0]; r=p.add_run(); r.text=txt
            r.font.size=Pt(pt); r.font.bold=bold
            r.font.color.rgb=accent if bold else RGBColor(0x64,0x74,0x8B)
    return CARD_H


def add_ka_table_no_cnt(slide, left, top, width, height, ka_rows, include_total=True):
    """KA table with 5 cols only: KEY ACCOUNT | 批核APE | 未批核APE | 待签APE | 合计APE
    Compact for side-by-side display, no 件数 columns.
    """
    COLS=["KEY ACCOUNT","批核APE(万)","未批核APE(万)","待签APE(万)","合计APE(万)"]
    if include_total:
        total={
            "KEY ACCOUNT":"合计",
            "2026批核APE":sum(r["2026批核APE"] for r in ka_rows if r["KEY ACCOUNT"]!="合计"),
            "未批核APE":  sum(r["未批核APE"]   for r in ka_rows if r["KEY ACCOUNT"]!="合计"),
            "待签APE":    sum(r["待签APE"]     for r in ka_rows if r["KEY ACCOUNT"]!="合计"),
            "合计APE":   sum(r["合计APE"]     for r in ka_rows if r["KEY ACCOUNT"]!="合计"),
        }
        display=[r for r in ka_rows if r["KEY ACCOUNT"]!="合计"]+[total]
    else:
        display=ka_rows
    nrows=len(display)+1; ncols=5
    tbl=slide.shapes.add_table(nrows,ncols,E(left),E(top),E(width),E(height)).table
    col_ws=[0.30,0.175,0.175,0.175,0.175]
    for ci,cw in enumerate(col_ws): tbl.columns[ci].width=E(int(width*cw))
    for ci,hdr in enumerate(COLS):
        cell=tbl.cell(0,ci); _fill_cell(cell,CLR_TBL_HDR)
        _set_cell_text(cell,hdr,bold=True,font_size=7,font_color=CLR_WHITE,align=PP_ALIGN.CENTER)
    def _fmt(v): return f"{v/10000:.0f}" if v>=10000 else (f"{v/10000:.1f}" if v>0 else "—")
    for ri,row in enumerate(display):
        is_total=row["KEY ACCOUNT"]=="合计"
        bg=CLR_TBL_TOTAL if is_total else (CLR_TBL_ROW2 if ri%2 else CLR_TBL_ROW1)
        vals=[row["KEY ACCOUNT"],_fmt(row["2026批核APE"]),_fmt(row["未批核APE"]),
              _fmt(row["待签APE"]),_fmt(row["合计APE"])]
        for ci,val in enumerate(vals):
            cell=tbl.cell(ri+1,ci); _fill_cell(cell,bg)
            align=PP_ALIGN.LEFT if ci==0 else PP_ALIGN.CENTER
            fc=CLR_WHITE if is_total else CLR_DARK
            _set_cell_text(cell,val,bold=is_total,font_size=7,font_color=fc,align=align)


def build_agent_combined_slide(prs, d):
    """合并天领+成事家办为一页代理人业务仪表盘。"""
    layout=prs.slide_layouts[0]
    slide=prs.slides.add_slide(layout)
    add_title_bar(slide,"代理人业务分析仪表盘  Agent Business View","内部文件 · 仅供使用")

    agent_kpi=d["agent_kpi"]; agent_mo=d["agent_monthly_kpi"]
    mo_lbl=agent_mo["月份中文"]

    # ── Row 1: 6 KPI cards (代理人业务合计) ───────────────────────────
    def _ape(v): m=v/1_000_000; return f"{m:.2f}M" if m<10 else f"{m:.1f}M"
    def _sub(a,c): return f"{int(c)}件 | 件均{a/c/10000:.1f}W" if c>0 else "0件 | 件均0W"
    CARD_W=1828800; CARD_H=762000; BAR_W=76200
    MARGIN=182880; STEP=1993265; LBL_OFF=109835; TXT_W=1682750
    R1_TOP=430000
    row1=[
        ("代理人业务批核",  agent_kpi["批核APE"],  agent_kpi["批核件数"],  "1B4F72"),
        ("代理人业务未批核",agent_kpi["未批核APE"],agent_kpi["未批核件数"],"117A65"),
        ("代理人业务待签",  agent_kpi["待签APE"],  agent_kpi["待签件数"],  "00796B"),
        (f"代理人{mo_lbl}预约",agent_mo["预约APE"],agent_mo["预约件数"],"9B2335"),
        (f"代理人{mo_lbl}签单",agent_mo["签单APE"],agent_mo["签单件数"],"6B2737"),
        (f"代理人{mo_lbl}批核",agent_mo["批核APE"],agent_mo["批核件数"],"6C3483"),
    ]
    for ci,(label,ape,cnt,hex6) in enumerate(row1):
        card_l=MARGIN+ci*STEP
        accent=RGBColor(int(hex6[:2],16),int(hex6[2:4],16),int(hex6[4:],16))
        T_LBL=R1_TOP+54610; T_VAL=R1_TOP+228600; T_SUB=R1_TOP+539115
        bg=slide.shapes.add_shape(1,E(card_l),E(R1_TOP),E(CARD_W),E(CARD_H))
        bg.fill.solid(); bg.fill.fore_color.rgb=RGBColor(0xFF,0xFF,0xFF)
        bg.line.color.rgb=RGBColor(0xE8,0xEC,0xF0); bg.line.width=E(9525)
        bar=slide.shapes.add_shape(1,E(card_l),E(R1_TOP),E(BAR_W),E(CARD_H))
        bar.fill.solid(); bar.fill.fore_color.rgb=accent; bar.line.fill.background()
        for (tt,hh,txt,pt,bold) in [
            (T_LBL,182245,label,9,False),(T_VAL,297815,_ape(ape),22,True),
            (T_SUB,149225,_sub(ape,cnt),8,False)]:
            tb=slide.shapes.add_textbox(E(card_l+LBL_OFF),E(tt),E(TXT_W),E(hh))
            p=tb.text_frame.paragraphs[0]; r2=p.add_run(); r2.text=txt
            r2.font.size=Pt(pt); r2.font.bold=bold
            r2.font.color.rgb=accent if bold else RGBColor(0x64,0x74,0x8B)

    R2_TOP=R1_TOP+CARD_H+80000   # ≈ 1272000

    # ── Row 2: 3 weekly KPI cards (merged 天领+成事家办 current week) ─
    weeks, wdata=d["hi_merged"]
    cur_wk=_get_current_week(weeks)
    try: wi=weeks.index(cur_wk)
    except: wi=len(weeks)-1
    wk_short=cur_wk.replace("2026","")

    def _wval(stage, wi):
        row_ka=wdata.get(stage,{}).get("合计",[0]*len(weeks))
        return row_ka[wi] if wi<len(row_ka) else 0

    row2=[
        (f"代理人 {wk_short}预约",_wval("预约APE",wi),_wval("预约APE件数" if "预约APE件数" in wdata else "预约APE",wi),"1B4F72"),
        (f"代理人 {wk_short}签单",_wval("签单APE",wi),0,"117A65"),
        (f"代理人 {wk_short}批核",_wval("批核APE",wi),0,"00796B"),
    ]

    # Use simpler weekly card — just APE value from merged 合计 row
    def _mk_weekly_card(ci, label, ape_val, hex6):
        card_l=MARGIN+ci*STEP
        accent=RGBColor(int(hex6[:2],16),int(hex6[2:4],16),int(hex6[4:],16))
        ape_m=ape_val/1_000_000
        val_str=f"{ape_m:.2f}M" if ape_m<10 else f"{ape_m:.1f}M"
        T_LBL=R2_TOP+54610; T_VAL=R2_TOP+228600; T_SUB=R2_TOP+539115
        bg=slide.shapes.add_shape(1,E(card_l),E(R2_TOP),E(CARD_W),E(CARD_H))
        bg.fill.solid(); bg.fill.fore_color.rgb=RGBColor(0xFF,0xFF,0xFF)
        bg.line.color.rgb=RGBColor(0xE8,0xEC,0xF0); bg.line.width=E(9525)
        bar=slide.shapes.add_shape(1,E(card_l),E(R2_TOP),E(BAR_W),E(CARD_H))
        bar.fill.solid(); bar.fill.fore_color.rgb=accent; bar.line.fill.background()
        for (tt,hh,txt,pt,bold) in [
            (T_LBL,182245,label,9,False),(T_VAL,297815,val_str,22,True),(T_SUB,149225,"",8,False)]:
            tb=slide.shapes.add_textbox(E(card_l+LBL_OFF),E(tt),E(TXT_W),E(hh))
            p=tb.text_frame.paragraphs[0]; r2=p.add_run(); r2.text=txt
            r2.font.size=Pt(pt); r2.font.bold=bold
            r2.font.color.rgb=accent if bold else RGBColor(0x64,0x74,0x8B)

    for ci,(label,ape_val,_,hex6) in enumerate(row2):
        _mk_weekly_card(ci, label, ape_val, hex6)

    TBL_TOP=R2_TOP+CARD_H+120000   # ≈ 2714000
    LEFT_W=TBL_W    # same as other slides

    # ── Two KA tables stacked vertically (can overflow below page) ──────
    TBL_W_AGENT = TBL_W   # full left-panel width
    ROW_H_AGENT = 260000
    HDR_H_AGENT = 270000
    cur_y = TBL_TOP

    # 天领 — top
    tl_rows=[r for r in d["b_ka"] if r["KEY ACCOUNT"]!="合计"]
    n_tl=len(tl_rows)
    add_section_header(slide,TBL_L,cur_y,TBL_W_AGENT,HDR_H_AGENT,
                       "KA明细 | 天领业务",RGBColor(0x1B,0x4F,0x72))
    tl_h=(n_tl+2)*ROW_H_AGENT+60000
    add_ka_table(slide,TBL_L,cur_y+HDR_H_AGENT,TBL_W_AGENT,tl_h,
                 tl_rows, include_total=True)
    cur_y += HDR_H_AGENT + tl_h + 120000   # gap between tables

    # 成事家办 — below (may overflow page bottom)
    cs_rows=[r for r in d["c_ka"] if r["KEY ACCOUNT"]!="合计"]
    n_cs=len(cs_rows)
    add_section_header(slide,TBL_L,cur_y,TBL_W_AGENT,HDR_H_AGENT,
                       "KA明细 | 成事家办",RGBColor(0x1A,0x5E,0x42))
    cs_h=(n_cs+2)*ROW_H_AGENT+60000
    add_ka_table(slide,TBL_L,cur_y+HDR_H_AGENT,TBL_W_AGENT,cs_h,
                 cs_rows, include_total=True)

    # ── Right: merged monthly chart ────────────────────────────────────
    months, mdata=d["de_merged"]
    chart_buf=_make_monthly_chart(months,mdata,"代理人业务 2026年月度明细分析（天领+成事家办）")
    slide.shapes.add_picture(chart_buf,E(RPL),E(R2_TOP),E(RPW),E(MONTHLY_H))

    # ── Right: merged weekly table ─────────────────────────────────────
    add_weekly_table(slide, RPL, R2_TOP+MONTHLY_H+80000, RPW,
                     SH-(R2_TOP+MONTHLY_H+80000)-60000,
                     wdata, weeks, "代理人业务（天领+成事家办）", cur_wk)
    return slide


def build_ka_main_slide(prs, ka_data, d, a_data):
    """KA业务主页：
       左上   — 3 个 KPI 卡片
       左中下 — ICLUB / 合伙转介 / IFA 三张子表（并排）
       右上   — 月度明细表
       右下   — 本周快报（全量 KA）
    """
    layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    add_title_bar(slide, "KA业务分析仪表盘  |ICLUB + 合伙转介 + IFA",
                  "内部文件 · 仅供使用")

    # ── KPI cards ────────────────────────────────────────────────────
    for i, (field, key) in enumerate([("批核APE","批核"),("未批核APE","未批核"),("待签APE","待签")]):
        ape = ka_data[field]; cnt = ka_data[field.replace("APE","件数")]
        color = CLR_VALUE[key]
        ape_m = ape / 1_000_000
        ape_str = f"{ape_m:.1f}M" if ape_m >= 10 else f"{ape_m:.2f}M"
        sub = f"{int(cnt)}件 | 件均{ape/cnt/10000:.1f}W" if cnt > 0 else "0件"
        add_kpi_card(slide, KPI_L0 + i*(KPI_W+KPI_GAP), KPI_T, KPI_W, KPI_H,
                     f"KA业务 {field}", ape_str, sub, color)

    # ── 3 sub-tables stacked vertically (left panel, below KPI cards) ──
    # 竖向堆叠，可超出页面，宽度占满左半宽
    sub_w   = TBL_W - 60000
    sub_l   = TBL_L
    cur_top = TBL_T   # 紧接 KPI 卡片下方
    HDR_H   = 260000
    ROW_H   = 260000  # 每数据行高度

    iclub_rows = d["f_iclub"]
    hezhu_rows = d["f_hezhu"]
    ifa_rows   = d["f_ifa"]

    hdr_clrs = [RGBColor(0x1B, 0x4F, 0x72),
                RGBColor(0x1A, 0x5E, 0x42),
                RGBColor(0x5D, 0x1A, 0x1A)]

    for label, rows, hclr in [
        ("ICLUB业务",   iclub_rows, hdr_clrs[0]),
        ("合伙转介业务", hezhu_rows, hdr_clrs[1]),
        ("IFA业务",     ifa_rows,   hdr_clrs[2]),
    ]:
        add_section_header(slide, sub_l, cur_top, sub_w, HDR_H, label, hclr)
        cur_top += HDR_H
        display = [r for r in rows if r["KEY ACCOUNT"] != "合计"]
        n_data = len(display) if display else 0
        tbl_h = (n_data + 2) * ROW_H + 40000   # header + data + total
        if display:
            add_ka_table(slide, sub_l, cur_top, sub_w, tbl_h,
                         display, include_total=True)
        else:
            # IFA暂无数据占位
            add_ka_table(slide, sub_l, cur_top, sub_w, ROW_H * 2,
                         [], include_total=False)
        cur_top += tbl_h + 80000   # 表间距

    # ── Monthly chart (right top) ─────────────────────────────────
    months, mdata = d["g"]
    chart_buf = _make_monthly_chart(months, mdata, "KA业务 2026年月度明细分析（含流失单）")
    slide.shapes.add_picture(chart_buf, E(RPL), E(MONTHLY_T), E(RPW), E(MONTHLY_H))

    # ── Weekly table (right bottom, full KA list) ─────────────────
    week_cols, wdata = d["j"]
    current_week = _get_current_week(week_cols)
    add_weekly_table_full(slide, RPL, WEEKLY_T, RPW, WEEKLY_H,
                          wdata, week_cols, "KA业务", current_week)
    return slide


def build_ka_detail_slide(prs, d):
    """KA业务明细页：3 个分类子表（ICLUB / 合伙转介 / IFA）占满整页."""
    layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    add_title_bar(slide, "KA业务明细  |ICLUB / 合伙转介 / IFA 各业务分类",
                  "内部文件 · 仅供使用")

    # Parse 3 F-sub-tables preserved separately
    iclub_rows  = d["f_iclub"]
    hezhu_rows  = d["f_hezhu"]
    ifa_rows    = d["f_ifa"]

    # Layout: 3 columns across the full slide below title
    margin_l = 80000; margin_r = 80000; gap = 120000
    usable_w = SW - margin_l - margin_r - 2 * gap
    col_w = usable_w // 3
    col_tops = [TITLE_H + 120000] * 3
    col_lefts = [margin_l + i * (col_w + gap) for i in range(3)]
    col_h = SH - TITLE_H - 200000

    for ci, (label, rows) in enumerate([
        ("ICLUB业务", iclub_rows),
        ("合伙转介业务", hezhu_rows),
        ("IFA业务", ifa_rows),
    ]):
        left = col_lefts[ci]; top = col_tops[ci]
        add_section_header(slide, left, top, col_w, 280000,
                           label, RGBColor(0x1B, 0x4F, 0x72))
        display = [r for r in rows if r["KEY ACCOUNT"] != "合计"]
        if display:
            nrows_tbl = len(display) + 2
            add_ka_table(slide, left, top + 290000, col_w,
                         min(col_h - 290000, nrows_tbl * 310000 + 80000),
                         display, include_total=True)
        else:
            tb = slide.shapes.add_textbox(E(left), E(top + 320000),
                                          E(col_w), E(200000))
            p = tb.text_frame.paragraphs[0]
            r = p.add_run(); r.text = "暂无数据"
            r.font.size = Pt(10); r.font.color.rgb = RGBColor(0xAA,0xAA,0xAA)
    return slide


def add_weekly_table_full(slide, left, top, width, height, week_data, week_cols,
                           table_title, current_week):
    """本周快报 — 显示全部 KA（不截断），自动缩减行高以容纳更多行。"""
    appt_d = week_data.get("预约APE", {})
    sign_d = week_data.get("签单APE", {})
    appr_d = week_data.get("批核APE", {})

    try:
        wi = week_cols.index(current_week)
    except ValueError:
        wi = len(week_cols) - 1

    def _get(d, ka): return d.get(ka, [0]*len(week_cols))[wi] if d.get(ka) else 0

    all_ka = set(appt_d) | set(sign_d) | set(appr_d)
    all_ka.discard("合计")
    rows_data = []
    for ka in all_ka:
        a = _get(appt_d, ka); s = _get(sign_d, ka); p = _get(appr_d, ka)
        # Include even if zero activity to show full roster
        rows_data.append({"ka": ka, "appt": a, "sign": s, "appr": p})
    rows_data.sort(key=lambda x: -(x["appt"] + x["sign"] + x["appr"]))

    tj = sum(r["appt"] for r in rows_data)
    tk = sum(r["sign"] for r in rows_data)
    tl = sum(r["appr"] for r in rows_data)

    wk_short = current_week.replace("2026", "")
    add_section_header(slide, left, top, width, 290000,
                       f"{wk_short} 本周快报 | {table_title}",
                       RGBColor(0x4A, 0x1F, 0x6A))

    tbl_top = top + 300000
    tbl_h   = height - 300000
    nrows = len(rows_data) + 2
    ncols = 4
    tbl = slide.shapes.add_table(nrows, ncols,
                                  E(left), E(tbl_top),
                                  E(width), E(tbl_h)).table
    col_ws = [0.40, 0.20, 0.20, 0.20]
    for ci, cw in enumerate(col_ws): tbl.columns[ci].width = E(int(width * cw))

    for ci, hdr in enumerate(["KEY ACCOUNT","预约(M)","签单(M)","批核(M)"]):
        cell = tbl.cell(0, ci)
        _fill_cell(cell, CLR_TBL_HDR)
        _set_cell_text(cell, hdr, bold=True, font_size=7.5,
                       font_color=CLR_WHITE, align=PP_ALIGN.CENTER)

    def _fmt_m(v): return f"{v/1_000_000:.2f}M"

    for ri, row in enumerate(rows_data):
        bg = CLR_TBL_ROW2 if ri % 2 else CLR_TBL_ROW1
        vals = [row["ka"], _fmt_m(row["appt"]), _fmt_m(row["sign"]), _fmt_m(row["appr"])]
        for ci, val in enumerate(vals):
            cell = tbl.cell(ri + 1, ci)
            _fill_cell(cell, bg)
            _set_cell_text(cell, val, font_size=7, font_color=CLR_DARK,
                           align=PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER)

    last = nrows - 1
    for ci, val in enumerate(["合计", _fmt_m(tj), _fmt_m(tk), _fmt_m(tl)]):
        cell = tbl.cell(last, ci)
        _fill_cell(cell, CLR_TBL_TOTAL)
        _set_cell_text(cell, val, bold=True, font_size=7.5, font_color=CLR_WHITE,
                       align=PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER)

# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def _dup_slide(prs, src_idx):
    """Full copy of slide[src_idx] to new slide at end."""
    src = prs.slides[src_idx]
    layout = src.slide_layout
    new = prs.slides.add_slide(layout)
    sp_tree = new.shapes._spTree
    for child in list(sp_tree):
        if child.tag.split("}")[-1] not in ("nvGrpSpPr", "grpSpPr"):
            sp_tree.remove(child)
    src_rels = src.part.rels
    for elem in src.shapes._spTree:
        if elem.tag.split("}")[-1] in ("nvGrpSpPr", "grpSpPr"): continue
        ne = copy.deepcopy(elem)
        for sub in ne.iter():
            rid = sub.get(f"{{{NS_R}}}id")
            if rid and rid in src_rels:
                rel = src_rels[rid]
                try:
                    new_rid = new.part.relate_to(rel.target_part, rel.reltype)
                    sub.set(f"{{{NS_R}}}id", new_rid)
                except Exception: pass
        sp_tree.append(ne)
    return new


def _delete_last_slide(prs):
    """Remove the last slide from the presentation."""
    from pptx.oxml.ns import qn
    prs_xml = prs.element
    sldIdLst = prs_xml.find(qn("p:sldIdLst"))
    slide_ids = sldIdLst.findall(qn("p:sldId"))
    if not slide_ids: return
    last_id_elem = slide_ids[-1]
    rid = last_id_elem.get(f"{{{NS_R}}}id")
    # Remove the relationship
    prs.part.drop_rel(rid)
    # Remove the id element
    sldIdLst.remove(last_id_elem)
    print(f"  已删除最后一页（rId={rid}）")


def main():
    prs = Presentation(PPTX_IN)
    print(f"原始幻灯片数: {len(prs.slides)}")

    # ── 1. 删除最后一页（第13页备份） ─────────────────────────────
    print("删除最后一页 ...")
    _delete_last_slide(prs)
    print(f"  删除后幻灯片数: {len(prs.slides)}")

    # ── 2. 读取 S9 数据 ──────────────────────────────────────────
    print("读取 S9 数据 ...")
    d = load_s9(EXCEL_IN)
    a = d["a_data"]

    # ── 3. Page A: 代理人业务（天领+成事家办合并）─────────────────
    print("新增第13页：代理人业务（天领+成事家办）...")
    build_agent_combined_slide(prs, d)

    # ── 5. Page C: KA业务（主页：KPI卡片 + 月度表 + 本周快报）────────
    print("新增第15页：KA业务主页 ...")
    ka_biz_keys = ["ICLUB业务", "合伙转介业务", "IFA业务"]
    ka_data = _a_data_sum(a, ka_biz_keys)
    build_ka_main_slide(prs, ka_data, d, a)

    # （三张 KA 子表已合并到第15页左侧，无需第16页）

    # ── 6. 保存 ──────────────────────────────────────────────────
    PPTX_OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(PPTX_OUT)
    print(f"\n✅ 已保存至 {PPTX_OUT}")
    print(f"   共 {len(prs.slides)} 页（代理人13/KA综合14）")


if __name__ == "__main__":
    main()
