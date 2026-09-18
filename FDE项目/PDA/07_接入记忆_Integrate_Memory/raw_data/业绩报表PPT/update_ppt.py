"""
update_ppt.py — main driver.

Reloads S1..S4 CSVs, opens the template PPT, replaces every chart's underlying
data, rewrites every KPI text token, and saves a new .pptx file.

Usage:
    python3 update_ppt.py

You only need to edit the CSV_* / SRC_PPT / OUT_PPT constants if filenames change.
Everything else is driven by the data inside the CSVs.
"""
# ---- Monkey-patch: tolerate non-standard grouping='none' in line charts ----
# The source deck uses <c:grouping val="none"/> which python-pptx chokes on.
# We patch the type inspector to default to standard line chart in that case.
import pptx.chart.plot as _plot_mod
from pptx.enum.chart import XL_CHART_TYPE as _XL
_orig_diff = _plot_mod.PlotTypeInspector._differentiate_line_chart_type
def _patched_line_type(cls, plot):
    try:
        return _orig_diff(plot)
    except (KeyError, Exception):
        # detect markers
        has_none = bool(plot._element.xpath(
            'c:ser/c:marker/c:symbol[@val="none"]'))
        return _XL.LINE if has_none else _XL.LINE_MARKERS
_plot_mod.PlotTypeInspector._differentiate_line_chart_type = classmethod(_patched_line_type)
# ----------------------------------------------------------------------------
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu
from data_loader import load_all, num
from chart_updates import (
    slide1_chart_business_type, slide1_chart_monthly_trend,
    slide2_appointment, slide2_signed, slide2_approved, slide2_forecast_chart,
    slide3_sunlife_trend,
    slide4_channel_trend,
    slide5_donut, slide5_target_vs_actual,
    slide6_weekly_trend,
    slide8_referrer, slide8_top10_ka,
    slide9_peer_weekly,
    slide10_bk_appointment, slide10_bk_signed, slide10_bk_approved,
    slide10_bk_ka, slide10_donut_target,
    slide11_bank_weekly, slide11_branch_ranking,
    to_m, to_w,
)

# ============================================================================
# Config
# ============================================================================
SRC_PPT = "template.pptx"
OUT_PPT = "周业绩汇报PPT_AUTO_UPDATED.pptx"

CSV_S1 = "S1-总览仪表盘.csv"
CSV_S2 = "S2-业务端视角.csv"
CSV_S3 = "S3-执行管理端.csv"
CSV_S4 = "S4-产品端视角.csv"

# ── Auto-derive report date and current week from data ──────────────────────
# REPORT_DATE: taken from the latest issue_date in S1 subtitle (dynamic)
# CURRENT_WEEK: taken from the last week column in S3 A-APE block
import csv as _csv_init, re as _re_init

def _derive_current_week():
    with open(CSV_S3, encoding="utf-8-sig") as _f:
        for _row in _csv_init.reader(_f):
            _wks = [c for c in _row if _re_init.match(r"2026W\d+", c)]
            if _wks:
                _latest = _wks[-1]           # e.g. "2026W18"
                return _latest[4:]           # "W18"
    return "W18"                             # fallback

CURRENT_WEEK = _derive_current_week()        # e.g. "W18" — fully dynamic

# REPORT_DATE: last day of current month derived from CURRENT_MONTH_COL (set below after S1 loads)
# We temporarily set it; it will be updated after _issue_yms is resolved.
REPORT_DATE = ""                             # placeholder — set dynamically after S1 load

# ============================================================================
# Load data
# ============================================================================
S1, S2, S3, S4 = load_all(CSV_S1, CSV_S2, CSV_S3, CSV_S4)

# ── Auto-derive current/prev month from S1-E (批核月 list) ──────────────
# S1["E"] rows: first column is issue_ym like "2026-01". Use the latest.
_issue_yms = sorted(
    [r for r in S1["E"].iloc[:, 0].tolist()
     if str(r).startswith("2026-")],
)
CURRENT_MONTH_COL = _issue_yms[-1] if _issue_yms else "2026-05"  # e.g. "2026-05"
_cm_parts = CURRENT_MONTH_COL.split("-")
_cm_month = int(_cm_parts[1])
PREV_MONTH_COL = f"{_cm_parts[0]}-{_cm_month-1:02d}" if _cm_month > 1 else f"{int(_cm_parts[0])-1}-12"
CURRENT_WEEK_COL = f"2026{CURRENT_WEEK}"  # e.g. "2026W18"
_cw_num = int(CURRENT_WEEK[1:])
PREV_WEEK_COL = f"2026W{_cw_num-1:02d}"   # e.g. "2026W17"

# ── Dynamic report metadata ─────────────────────────────────────────────────
import calendar as _calendar
CURRENT_MONTH = _cm_month                   # e.g. 5
REMAINING_M = 12 - CURRENT_MONTH + 1       # months remaining incl. current (e.g. 8 for May)

# REPORT_DATE: last day of current month
_last_day = _calendar.monthrange(int(_cm_parts[0]), _cm_month)[1]
REPORT_DATE = f"{_cm_parts[0]}-{_cm_month:02d}-{_last_day:02d}"

print(f"  Dynamic config: CURRENT_MONTH={CURRENT_MONTH} ({CURRENT_MONTH_COL})")
print(f"  CURRENT_WEEK={CURRENT_WEEK} | REMAINING_M={REMAINING_M} | REPORT_DATE={REPORT_DATE}")


def row_by(df, col, val):
    if df is None or len(df) == 0 or col not in df.columns:
        return None
    sub = df[df[col].astype(str) == val]
    return sub.iloc[0] if len(sub) else None


def _safe(r, key, default=0):
    """Get a value from a row safely. Returns default if row is None or key missing."""
    if r is None:
        return default
    try:
        return r[key]
    except (KeyError, IndexError):
        return default


def safe_cell(df, lookup_col, lookup_val, value_col, default=0):
    """One-shot safe lookup: row_by(df, lookup_col, lookup_val)[value_col]."""
    r = row_by(df, lookup_col, lookup_val)
    return _safe(r, value_col, default)


# ============================================================================
# Extract every KPI value needed in the deck
# ============================================================================

# --- S1 A: targets -----------------------------------------------------------
_a_full = row_by(S1["A"], "指标", "2026全业务目标")
_a_sun  = row_by(S1["A"], "指标", "2026永明业务目标")

FULL_TARGET_YUAN = num(_safe(_a_full, "目标APE"))
FULL_ISSUED_YUAN = num(_safe(_a_full, "已达成APE"))
FULL_RATE        = num(_safe(_a_full, "目标达成率"))
SUN_TARGET_YUAN  = num(_safe(_a_sun, "目标APE"))
SUN_ISSUED_YUAN  = num(_safe(_a_sun, "已达成APE"))
SUN_RATE         = num(_safe(_a_sun, "目标达成率"))

FULL_TARGET_M = FULL_TARGET_YUAN / 1_000_000
FULL_ISSUED_M = FULL_ISSUED_YUAN / 1_000_000
FULL_GAP_M    = FULL_TARGET_M - FULL_ISSUED_M
SUN_TARGET_M  = SUN_TARGET_YUAN / 1_000_000
SUN_ISSUED_M  = SUN_ISSUED_YUAN / 1_000_000
# FIX 1: Sun Life 缺口 = 目标 - 已达成（与全业务逻辑一致，直接用 S1 A 数据）
SUN_GAP_M     = SUN_TARGET_M - SUN_ISSUED_M

# --- S1 B: status summary ----------------------------------------------------
_b = S1["B"]
_b_issued = row_by(_b, "指标行", "批核(2026)")
_b_unbat  = row_by(_b, "指标行", "未批核(跨年)")
_b_pend   = row_by(_b, "指标行", "待签(跨年)")
_b_lost   = row_by(_b, "指标行", "流失(2026)")

ISSUED_APE_M  = to_m(_safe(_b_issued, "APE"))
ISSUED_CNT    = int(num(_safe(_b_issued, "件数")))
UNBAT_APE_M   = to_m(_safe(_b_unbat, "APE"))
UNBAT_CNT     = int(num(_safe(_b_unbat, "件数")))
UNBAT_AVG_W   = round(num(_safe(_b_unbat, "件均APE")) / 10_000, 1)
PEND_APE_M    = to_m(_safe(_b_pend, "APE"))
PEND_CNT      = int(num(_safe(_b_pend, "件数")))
PEND_AVG_W    = round(num(_safe(_b_pend, "件均APE")) / 10_000, 1)
LOST_APE_M    = to_m(_safe(_b_lost, "APE"))
LOST_CNT      = int(num(_safe(_b_lost, "件数")))

# --- Share percentages for pipeline (B 模块：批核/未批核/待签/流失) ----------------
# B 保单阶段分布的管道占比分母 = 批核 + 未批核 + 待签 + 流失（含流失，反映全口径）
_pipe_total_b = ISSUED_APE_M + UNBAT_APE_M + PEND_APE_M + LOST_APE_M
ISSUED_SHARE = ISSUED_APE_M / _pipe_total_b * 100 if _pipe_total_b else 0
UNBAT_SHARE  = UNBAT_APE_M  / _pipe_total_b * 100 if _pipe_total_b else 0
PEND_SHARE   = PEND_APE_M   / _pipe_total_b * 100 if _pipe_total_b else 0
LOST_SHARE   = LOST_APE_M   / _pipe_total_b * 100 if _pipe_total_b else 0

# FIX 4: K 保单总量构成甜甜圈的管道占比分母 = 批核 + 未批核 + 待签（不含流失）
# 这与 B 模块保持语义区分：B 展示含流失的全口径分布，K 展示在途保单的构成
_pipe_total_k = ISSUED_APE_M + UNBAT_APE_M + PEND_APE_M
ISSUED_SHARE_K = ISSUED_APE_M / _pipe_total_k * 100 if _pipe_total_k else 0
UNBAT_SHARE_K  = UNBAT_APE_M  / _pipe_total_k * 100 if _pipe_total_k else 0
PEND_SHARE_K   = PEND_APE_M   / _pipe_total_k * 100 if _pipe_total_k else 0

# --- S2 A: channel rollup ----------------------------------------------------
def _channel_kpis(S2_A, name):
    r = row_by(S2_A, "业务细分", name)
    if r is None:
        return {"issued_m":0,"issued_cnt":0,"unbat_m":0,"unbat_cnt":0,
                "pend_m":0,"pend_cnt":0,"rate":0,"target_m":0,"total_m":0}
    return {
        "issued_m": to_m(_safe(r, "2026批核APE")),
        "issued_cnt": int(num(_safe(r, "批核件数"))),
        "unbat_m":  to_m(_safe(r, "未批核APE")),
        "unbat_cnt":int(num(_safe(r, "未批核件数"))),
        "pend_m":   to_m(_safe(r, "待签APE")),
        "pend_cnt": int(num(_safe(r, "待签件数"))),
        "rate":     num(_safe(r, "达成率")),
        "target_m": to_m(_safe(r, "目标APE")),
        "total_m":  to_m(_safe(r, "合计APE")),
    }

CH_BK    = _channel_kpis(S2["A"], "BK业务")
CH_YMJD  = _channel_kpis(S2["A"], "永明经代")
CH_THJD  = _channel_kpis(S2["A"], "同行经代")
CH_TL    = _channel_kpis(S2["A"], "天领业务")
CH_ICLUB = _channel_kpis(S2["A"], "ICLUB业务")
CH_CSJB  = _channel_kpis(S2["A"], "成事家办")
CH_HHZJ  = _channel_kpis(S2["A"], "合伙转介业务")
CH_IFA   = _channel_kpis(S2["A"], "IFA业务")

# --- S3 A-APE / A-件数: current week + Q1 totals -----------------------------
_week_col = f"2026{CURRENT_WEEK}"

def _week_stage(stage, df):
    row = df[df.iloc[:, 0] == stage].iloc[0]
    return row

W_APE = {s: to_m(_week_stage(s, S3["A-APE"])[_week_col])
         for s in ["预约", "签单", "递交", "批核"]}
W_CNT = {s: int(num(_week_stage(s, S3["A-件数"])[_week_col]))
         for s in ["预约", "签单", "递交", "批核"]}

# Q1+part of Q2 totals across the 14 weeks (for funnel on slide 6)
def _stage_total(stage, df):
    row = df[df.iloc[:, 0] == stage].iloc[0]
    return to_m(row["合计"]) if "合计" in df.columns else sum(
        to_m(row[c]) for c in df.columns if c.startswith("2026W")
    )

def _stage_total_cnt(stage, df):
    row = df[df.iloc[:, 0] == stage].iloc[0]
    return int(num(row["合计"])) if "合计" in df.columns else sum(
        int(num(row[c])) for c in df.columns if c.startswith("2026W")
    )

FUNNEL_APE = {s: _stage_total(s, S3["A-APE"]) for s in ["预约","签单","递交","批核"]}
FUNNEL_CNT = {s: _stage_total_cnt(s, S3["A-件数"]) for s in ["预约","签单","递交","批核"]}

# --- S2 J / K: peer referrer + KA --------------------------------------------
_peer_total_row = row_by(S2["J"], "推荐人", "合计")
# J block: 推荐人汇总 (used for U 推荐人分析 chart data)
_PEER_J_ISSUED_M   = to_m(_safe(_peer_total_row, "2026批核APE"))
_PEER_J_ISSUED_CNT = int(num(_safe(_peer_total_row, "批核件数")))
_PEER_J_UNBAT_M    = to_m(_safe(_peer_total_row, "未批核APE"))
_PEER_J_UNBAT_CNT  = int(num(_safe(_peer_total_row, "未批核件数")))
_PEER_J_PEND_M     = to_m(_safe(_peer_total_row, "待签APE"))
_PEER_J_PEND_CNT   = int(num(_safe(_peer_total_row, "待签件数")))

# K block: 同行全渠道KA汇总 — drives V section KPI cards and V table
_peer_k_total_row = row_by(S2["K"], "KEY ACCOUNT", "合计")
PEER_ISSUED_M   = to_m(_safe(_peer_k_total_row, "2026批核APE"))
PEER_ISSUED_CNT = int(num(_safe(_peer_k_total_row, "批核件数")))
PEER_UNBAT_M    = to_m(_safe(_peer_k_total_row, "未批核APE"))
PEER_UNBAT_CNT  = int(num(_safe(_peer_k_total_row, "未批核件数")))
PEER_PEND_M     = to_m(_safe(_peer_k_total_row, "待签APE"))
PEER_PEND_CNT   = int(num(_safe(_peer_k_total_row, "待签件数")))

# avg (万)
def _avg_w(ape_m, cnt):
    if cnt == 0:
        return 0.0
    return round(ape_m * 1e6 / cnt / 10_000, 1)

PEER_ISSUED_AVG_W = _avg_w(PEER_ISSUED_M, PEER_ISSUED_CNT)
PEER_UNBAT_AVG_W  = _avg_w(PEER_UNBAT_M, PEER_UNBAT_CNT)
PEER_PEND_AVG_W   = _avg_w(PEER_PEND_M, PEER_PEND_CNT)

# peer current week (from S3 J/K/L-APE 合计 row, column _week_col)
def _sum_peer_week(df, col):
    if df is None or len(df) == 0 or col not in df.columns:
        return 0.0
    sub = df[df.iloc[:, 0] == "合计"]
    if len(sub) == 0:
        return 0.0
    return to_m(sub.iloc[0][col])

PEER_W_APP_M  = _sum_peer_week(S3["J-APE"], _week_col)
PEER_W_SGN_M  = _sum_peer_week(S3["K-APE"], _week_col)
PEER_W_APR_M  = _sum_peer_week(S3["L-APE"], _week_col)

def _sum_peer_week_cnt(df, col):
    if df is None or len(df) == 0 or col not in df.columns:
        return 0
    sub = df[df.iloc[:, 0] == "合计"]
    if len(sub) == 0:
        return 0
    return int(num(sub.iloc[0][col]))

PEER_W_APP_CNT = _sum_peer_week_cnt(S3["J-件数"], _week_col)
PEER_W_SGN_CNT = _sum_peer_week_cnt(S3["K-件数"], _week_col)
PEER_W_APR_CNT = _sum_peer_week_cnt(S3["L-件数"], _week_col)

# peer "本月" = April values from S2 L/M/N-APE totals
PEER_APR_APP_M  = to_m(safe_cell(S2["L-APE"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL))
PEER_APR_SGN_M  = to_m(safe_cell(S2["M-APE"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL))
PEER_APR_APR_M  = to_m(safe_cell(S2["N-APE"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL))
PEER_APR_APP_CNT = int(num(safe_cell(S2["L-件数"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL)))
PEER_APR_SGN_CNT = int(num(safe_cell(S2["M-件数"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL)))
PEER_APR_APR_CNT = int(num(safe_cell(S2["N-件数"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL)))

# --- Bank (slide 10/11) ------------------------------------------------------
_o = S2["O"]
BK_TOTAL = row_by(_o, "KEY ACCOUNT", "合计")
BK_ISSUED_M   = to_m(_safe(BK_TOTAL, "2026批核APE"))
BK_ISSUED_CNT = int(num(_safe(BK_TOTAL, "批核件数")))
BK_UNBAT_M    = to_m(_safe(BK_TOTAL, "未批核APE"))
BK_UNBAT_CNT  = int(num(_safe(BK_TOTAL, "未批核件数")))
BK_PEND_M     = to_m(_safe(BK_TOTAL, "待签APE"))
BK_PEND_CNT   = int(num(_safe(BK_TOTAL, "待签件数")))
BK_RATE       = CH_BK["rate"]
BK_UNBAT_AVG_W = _avg_w(BK_UNBAT_M, BK_UNBAT_CNT)
BK_PEND_AVG_W  = _avg_w(BK_PEND_M, BK_PEND_CNT)

# Bank April totals (from S2 P/Q/R-APE totals, col 2026-04)
BK_APR_APP_M = to_m(safe_cell(S2["P-APE"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL))
BK_APR_SGN_M = to_m(safe_cell(S2["Q-APE"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL))
BK_APR_APR_M = to_m(safe_cell(S2["R-APE"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL))
BK_APR_APP_CNT = int(num(safe_cell(S2["P-件数"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL)))
BK_APR_SGN_CNT = int(num(safe_cell(S2["Q-件数"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL)))
BK_APR_APR_CNT = int(num(safe_cell(S2["R-件数"], "KEY ACCOUNT", "合计", CURRENT_MONTH_COL)))

# Bank current-week (from S3 M/N/O-APE 合计 row, col _week_col)
BK_W_APP_M = to_m(row_by(S3["M-APE"], "KEY ACCOUNT", "合计")[_week_col])
BK_W_SGN_M = to_m(row_by(S3["N-APE"], "KEY ACCOUNT", "合计")[_week_col])
BK_W_APR_M = to_m(row_by(S3["O-APE"], "KEY ACCOUNT", "合计")[_week_col])
BK_W_APP_CNT = int(num(row_by(S3["M-件数"], "KEY ACCOUNT", "合计")[_week_col]))
BK_W_SGN_CNT = int(num(row_by(S3["N-件数"], "KEY ACCOUNT", "合计")[_week_col]))
BK_W_APR_CNT = int(num(row_by(S3["O-件数"], "KEY ACCOUNT", "合计")[_week_col]))

# --- Pacing line for slide 2 -------------------------------------------------
# 实际批核 to date → 剩余缺口 ÷ REMAINING_M
PACE_LINE = round(FULL_GAP_M / REMAINING_M, 1) if REMAINING_M else 0
# MIN_LINE: 最低月底线 — 固定为 69.5M（手动设定，不随年度目标变动）
MIN_LINE  = 69.5

# --- Pipeline KPIs for slide 5 'donut' labels --------------------------------
# FIX 4: K 甜甜圈分母仅用批核+未批核+待签（不含流失），与 B 模块区分
PIPE_TOTAL_M = _pipe_total_k   # K 模块：批核+未批核+待签

print("=" * 70)
print(f"Data loaded. Week={CURRENT_WEEK}. Key numbers:")
print(f"  Full target rate: {FULL_RATE:.1f}%  | Issued: {ISSUED_APE_M:.1f}M / {ISSUED_CNT} 件")
print(f"  Unbat: {UNBAT_APE_M:.1f}M / {UNBAT_CNT} 件    Pend: {PEND_APE_M:.1f}M / {PEND_CNT} 件")
print(f"  Sun rate: {SUN_RATE:.1f}%  | Sun Issued: {SUN_ISSUED_M:.1f}M  | Sun Gap: {SUN_GAP_M:.0f}M")
print(f"  BK rate: {BK_RATE:.1f}%  | BK Issued: {BK_ISSUED_M:.1f}M")
print(f"  Week funnel: 预约 {W_APE['预约']:.1f}M / {W_CNT['预约']}件")
print(f"               签单 {W_APE['签单']:.1f}M / {W_CNT['签单']}件")
print(f"               递交 {W_APE['递交']:.1f}M / {W_CNT['递交']}件")
print(f"               批核 {W_APE['批核']:.1f}M / {W_CNT['批核']}件")
print(f"  Pace line:  {PACE_LINE}M / month (剩余 {REMAINING_M} 月)")
print(f"  Pipe total (K donut, excl. 流失): {PIPE_TOTAL_M:.1f}M")
print(f"  Pipe total (B stage dist, incl. 流失): {_pipe_total_b:.1f}M")
print("=" * 70)


# ============================================================================
# Open template
# ============================================================================
prs = Presentation(SRC_PPT)


# ============================================================================
# CHART REPLACEMENTS
# ============================================================================
def _find_shape(slide, name_or_predicate):
    if callable(name_or_predicate):
        for s in slide.shapes:
            if name_or_predicate(s):
                return s
    else:
        for s in slide.shapes:
            if s.name == name_or_predicate:
                return s
    return None


from chart_xml_patch import patch_chart, patch_chart_dlbls

def _cd_to_spec(chart_data):
    """Extract (categories, series_names, series_values) from CategoryChartData."""
    # Category objects don't implement __str__; use .label
    cats = [getattr(c, "label", None) or c.label if hasattr(c, "label") else str(c)
            for c in chart_data.categories]
    # simpler: use the raw categories list
    cats = [c.label for c in chart_data.categories]
    names, vals = [], []
    for s in chart_data._series:
        names.append(s.name)
        vals.append([None if v is None else float(v) for v in s.values])
    return cats, names, vals

def _replace_chart(slide, shape_name, chart_data):
    if chart_data is None:
        print(f"  ! chart data unavailable, skipping: {shape_name}")
        return False
    shp = _find_shape(slide, shape_name)
    if shp is None or not shp.has_chart:
        print(f"  ! chart not found: {shape_name}")
        return False
    cats, names, vals = _cd_to_spec(chart_data)
    patch_chart(shp.chart.part, vals, categories=cats, series_names=names)
    return True

def _replace_chart_dlbls(slide, shape_name, series_index, labels):
    """Update custom rich-text data labels on one chart series."""
    shp = _find_shape(slide, shape_name)
    if shp is None or not shp.has_chart:
        return False
    n = patch_chart_dlbls(shp.chart.part, series_index, labels)
    return n > 0


slides = list(prs.slides)  # 0-indexed: slides[0] = slide 1

# ── Safe slide accessor — prevents IndexError when PPT has fewer slides ──
class _NullSlide:
    shapes = []
    def __getattr__(self, name): return lambda *a, **k: None
def _s(idx):
    return slides[idx] if idx < len(slides) else _NullSlide()

# ── Dynamic slide finder — works regardless of slide count / order ────────
# Instead of hardcoding indices (which differ between full 11-slide deck and
# 6-slide review extract), find each slide by unique text content.
def _find_slide(keyword, fallback_idx=None):
    """Return the slide containing `keyword` in any text shape, or fallback."""
    for sl in slides:
        for sh in sl.shapes:
            if not sh.has_text_frame: continue
            txt = "".join(r.text for p in sh.text_frame.paragraphs for r in p.runs)
            if keyword in txt:
                return sl
    if fallback_idx is not None and fallback_idx < len(slides):
        print(f"  ! slide not found by keyword {repr(keyword)}, using slides[{fallback_idx}]")
        return slides[fallback_idx]
    return _NullSlide()

def _find_slide_with_chart(chart_name):
    """Return the slide that contains a graphic frame named `chart_name`."""
    for sl in slides:
        for sh in sl.shapes:
            if sh.name == chart_name and sh.has_chart:
                return sl
    return _NullSlide()

def _chart_slide(chart_name, preferred_slide=None):
    """Return preferred_slide if it contains chart_name, else search all slides.

    Using preferred_slide avoids wrong-slide selection when the same chart name
    (e.g. Chart_YY) appears on multiple slides (e.g. Slide 2 AND Slide 10 BK).
    """
    # If a preferred slide is given and it actually has this chart, use it directly.
    if preferred_slide is not None and not isinstance(preferred_slide, _NullSlide):
        for sh in preferred_slide.shapes:
            if sh.name == chart_name and sh.has_chart:
                return preferred_slide
    # Fall back to global search
    found = _find_slide_with_chart(chart_name)
    if isinstance(found, _NullSlide) and preferred_slide is not None:
        return preferred_slide
    return found

# Identify key slides by unique marker text
_SL_SUNLIFE  = _find_slide("G.  永明业绩汇报数据-2026", fallback_idx=2)  # 永明汇报 (Slide 3)
_SL_FORECAST = _find_slide("达标节奏线",                fallback_idx=1)  # F批核路径管控 (Slide 2)
_SL_BUBBLE   = _find_slide("H  全业务目标缺口分解",     fallback_idx=3)  # G气泡+H瀑布 (Slide 4)
_SL_BIZ_VIEW = _find_slide("J  保单阶段构成",          fallback_idx=4)  # 业务端视角 (Slide 5)
_SL_EXEC     = _find_slide("M  全流程转化漏斗",         fallback_idx=5)  # 执行管理端 (Slide 6)
_SL_PIPELINE = _find_slide("同行W",                     fallback_idx=6)  # 同行业绩分析
_SL_BK       = _find_slide("BK批核",                    fallback_idx=9)  # BK页
_SL_BK_WK    = _find_slide("BK W",                      fallback_idx=10) # BK周趋势

# For backward-compat with code that still uses slides[N] directly:
# Re-assign slides indices to point to the correct found slides
# (only if we can confirm the mapping by finding them dynamically)
def _slide_idx(slide):
    """Return 0-based index of a slide in the presentation."""
    for i, sl in enumerate(slides):
        if sl is slide: return i
    return -1

print(f"  Slide map: 永明汇报=slides[{_slide_idx(_SL_SUNLIFE)}]  "
      f"F路径管控=slides[{_slide_idx(_SL_FORECAST)}]  "
      f"G/H气泡瀑布=slides[{_slide_idx(_SL_BUBBLE)}]  "
      f"业务视角=slides[{_slide_idx(_SL_BIZ_VIEW)}]  "
      f"执行管理=slides[{_slide_idx(_SL_EXEC)}]  "
      f"BK=slides[{_slide_idx(_SL_BK)}]")

# ── Helper: remove stale manual dLbl offsets after any chart data replace ─
# When chart data changes, individual <dLbl> elements with manualLayout x/y
# offsets (calibrated to old proportions) cause labels to drift. Fix: strip
# all per-dLbl overrides and set global dLblPos='outEnd' (above bar/outside
# line point) so labels auto-position correctly with the new data.
def _fix_chart_dlbls_positions(slide, chart_name):
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart:
        print(f"  ! [dLbls fix] chart not found: {chart_name}")
        return
    from lxml import etree as _etree_dlbl
    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    root = shp.chart.part._element
    patched = 0
    for ser in root.findall(f".//{{{NS_C}}}ser"):
        dLbls = ser.find(f"{{{NS_C}}}dLbls")
        if dLbls is None:
            continue
        delete_el = dLbls.find(f"{{{NS_C}}}delete")
        if delete_el is not None and delete_el.get("val") == "1":
            continue
        # Remove all individual <dLbl> overrides (stale manualLayout offsets)
        for dLbl in dLbls.findall(f"{{{NS_C}}}dLbl"):
            dLbls.remove(dLbl)
        # Set global position to outEnd (visible above bar / outside line point)
        pos_el = dLbls.find(f"{{{NS_C}}}dLblPos")
        if pos_el is not None:
            pos_el.set("val", "outEnd")
        else:
            pos_el = _etree_dlbl.SubElement(dLbls, f"{{{NS_C}}}dLblPos")
            pos_el.set("val", "outEnd")
        patched += 1
    print(f"  [dLbls fix] {chart_name}: {patched} series patched")

# Slide 1 — first slide of full deck (slides[0])
# Has Chart 0 = 全业务业务类型 bar, Chart 1 = 全业务月度趋势 line
print("\n[Slide 1 — 全业务]")

# ── Extend Slide 1 D monthly detail table: clone new month columns ──────────
def _extend_s1_monthly_detail_cols():
    """Clone the Apr (rightmost) column shapes to add May, Jun... columns."""
    from copy import deepcopy as _s1dc
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    slide = _s(0)
    spTree = slide.shapes._spTree
    APR_X_K = 10129
    COL_GAP_K = 567
    MO_LABELS = {1:"26-Jan",2:"26-Feb",3:"26-Mar",4:"26-Apr",5:"26-May",
                 6:"26-Jun",7:"26-Jul",8:"26-Aug",9:"26-Sep",10:"26-Oct",11:"26-Nov",12:"26-Dec"}
    HEADER_Y_K = 3995
    # DATA_ROW_INFO references M_APE_APPT etc. — built lazily at call time
    # so the global dicts are already populated when this function runs.
    DATA_ROW_INFO = {
        4251: (M_APE_APPT, lambda v: f"{v:.1f}"),
        4507: (M_CNT_APPT, lambda v: f"{int(v)}件"),
        4818: (M_APE_SIGN, lambda v: f"{v:.1f}"),
        5074: (M_CNT_SIGN, lambda v: f"{int(v)}件"),
        5385: (M_APE_ISSU, lambda v: f"{v:.1f}"),
        5641: (M_CNT_ISSU, lambda v: f"{int(v)}件"),
    }
    # Months already present in the PPT (check header shapes)
    existing_month_nums = set()
    for sh in slide.shapes:
        if not sh.has_text_frame or sh.left is None: continue
        if abs(sh.left - APR_X_K * 1000) > 100_000: continue
        if abs(sh.top - HEADER_Y_K * 1000) > 100_000: continue
        txt = sh.text_frame.text.strip()
        for mo_num, mo_lbl in MO_LABELS.items():
            if txt == mo_lbl:
                existing_month_nums.add(mo_num)
    # Also add months 1-4 as always present (in case label check misses them)
    existing_month_nums.update([1, 2, 3, 4])
    # Use _ALL_MONTH_NUMS if available (called after it's defined), else fall back
    try:
        _mo_nums = _ALL_MONTH_NUMS
    except NameError:
        import csv as _csv_fb, re as _re_fb
        _mo_nums = []
        with open(CSV_S1, encoding='utf-8-sig') as _f_fb:
            for _r_fb in _csv_fb.reader(_f_fb):
                if _r_fb and _re_fb.match(r'^2026-\d{2}$', _r_fb[0].strip()):
                    _mo_nums.append(int(_r_fb[0][5:7]))
        _mo_nums = sorted(set(_mo_nums))
    new_months = sorted(m for m in _mo_nums if m not in existing_month_nums)
    if not new_months:
        print("  [S1 D-extend] No new months to add")
        return
    # Find all Apr column shapes (source shapes to clone)
    apr_shapes = []
    for sh in slide.shapes:
        if sh.left is None or sh.top is None: continue
        if abs(sh.left - APR_X_K * 1000) > 80_000: continue
        if sh.top < HEADER_Y_K * 1000 - 100_000: continue
        apr_shapes.append(sh)
    for idx_new, new_mo in enumerate(new_months):
        dst_x_emu = (APR_X_K + (idx_new + 1) * COL_GAP_K) * 1000
        x_offset_emu = dst_x_emu - APR_X_K * 1000
        for src_sh in apr_shapes:
            new_el = _s1dc(src_sh._element)
            for off in new_el.iter(f"{{{NS_A}}}off"):
                try: off.set("x", str(int(off.get("x", 0)) + x_offset_emu))
                except: pass
            spTree.append(new_el)
            new_sh = slide.shapes[-1]
            if not new_sh.has_text_frame: continue
            sh_top_k = src_sh.top // 1000
            if abs(sh_top_k - HEADER_Y_K) < 150:
                # Month label header
                tf = new_sh.text_frame
                if tf.paragraphs and tf.paragraphs[0].runs:
                    tf.paragraphs[0].runs[0].text = MO_LABELS[new_mo]
                    for r in tf.paragraphs[0].runs[1:]: r.text = ""
            else:
                # Data cell — find matching row
                best_dy = None
                best_info = None
                for dy_k, row_info in DATA_ROW_INFO.items():
                    dist = abs(sh_top_k - dy_k)
                    if best_dy is None or dist < best_dy:
                        best_dy = dist; best_info = row_info
                if best_dy is None or best_dy > 200: continue
                data_dict, fmt = best_info
                val = data_dict.get(new_mo, 0)
                tf = new_sh.text_frame
                if tf.paragraphs and tf.paragraphs[0].runs:
                    tf.paragraphs[0].runs[0].text = fmt(val)
                    for r in tf.paragraphs[0].runs[1:]: r.text = ""
        print(f"  [S1 D-extend] Added col {MO_LABELS[new_mo]} at x={dst_x_emu//1000}K")

_replace_chart(_s(0), "Chart 0", slide1_chart_business_type(S1))
# DO NOT call _replace_chart for Chart 1 here.
# slide1_chart_monthly_trend(S1) only produces 预约/签单 for 2026 (4 points),
# not the full 16-month series (2025 + 2026). Replacing would WIPE the 2025
# historical data already embedded in the template, leaving gaps in 预约/签单 lines.
# Instead, _patch_s1_monthly_trend (called later) only updates 2026 data points.

def _patch_s1_monthly_trend(slide, chart_name):
    """
    Fix the full-business D chart (slides[0] Chart 1) by directly patching
    numCache values from S1 C/D/E blocks for ALL months 2025-01 to 2026-04.
    slide1_chart_monthly_trend(S1) produces wrong Apr 2026 values (0.7/3/4).
    This patch overwrites every data point with the correct S1 values.
    Series: 预约 APE(M) ← S1 C block, 签单 APE(M) ← S1 D block, 批核 APE(M) ← S1 E block
    """
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart:
        print(f"  ! [D-s1 patch] chart not found: {chart_name}")
        return

    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    root = shp.chart.part._element

    # Read S1 C/D/E blocks — all rows with YYYY-MM keys
    def _read_s1_block_ape(block_letter):
        """Read {year-month: APE_M} dict from S1 block (C/D/E).
        FIX: stops at next block header to avoid reading D/E data into C block."""
        result = {}
        in_block = False; hdr = None
        import csv as _csv2, re as _re
        with open(CSV_S1, encoding="utf-8-sig") as _f:
            for _row in _csv2.reader(_f):
                if not _row: continue
                first = _row[0].strip()
                # Block header: "C. 月度业绩走势..." or "D. ..." or "E. ..."
                if first.startswith(f"{block_letter}.") and "月度业绩" in first:
                    in_block = True; continue
                if not in_block: continue
                if first.startswith("📌"): continue
                # Stop at next block header (e.g. D., E., F. etc.)
                if in_block and _re.match(r"^[A-Z]\.", first) and not first.startswith(f"{block_letter}."):
                    break
                # Column header row: contains "年月"
                if hdr is None and any("年月" in c for c in _row):
                    hdr = [c.strip() for c in _row]; continue
                if not first: break
                if hdr is None: continue
                # Data rows: YYYY-MM format
                if _re.match(r"^\d{4}-\d{2}$", first):
                    try:
                        ape_idx = hdr.index("APE") if "APE" in hdr else 2
                        result[first] = float(_row[ape_idx].replace(",","").strip()) / 1e6
                    except (ValueError, IndexError):
                        pass
        return result

    c_ape = _read_s1_block_ape("C")   # 预约
    d_ape = _read_s1_block_ape("D")   # 签单
    e_ape = _read_s1_block_ape("E")   # 批核

    from lxml import etree as _etree_lxml_m  # needed for adding new month points

    # Build ordered month list from the chart's existing CATEGORY labels only.
    # Use c:cat/c:strRef/c:strCache to avoid picking up series name strCache (c:tx).
    all_months = []
    for ser in root.findall(f".//{{{NS_C}}}ser")[:1]:
        for sc in ser.findall(f"{{{NS_C}}}cat//{{{NS_C}}}strCache"):
            for pt in sc.findall(f"{{{NS_C}}}pt"):
                v = pt.find(f"{{{NS_C}}}v")
                if v is not None and v.text:
                    all_months.append(v.text)  # e.g. "25-Jan", "26-Apr"

    # Map display labels to YYYY-MM keys
    MONTH_ABBR = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
                  "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
    def _label_to_key(label):
        # "25-Jan" → "2025-01", "26-Apr" → "2026-04"
        import re as _re
        m = _re.match(r"^(\d{2})-([A-Za-z]{3})$", label)
        if m:
            yr = "20" + m.group(1)
            mo = MONTH_ABBR.get(m.group(2).capitalize(), "00")
            return f"{yr}-{mo}"
        return None

    # Map series name → S1 block data (primary matching by name)
    # Also maps by series order (index 0=预约, 1=签单, 2=批核) as fallback
    series_by_name = {
        "预约 APE(M)": c_ape,   "预约": c_ape,   "Appointment": c_ape,
        "签单 APE(M)": d_ape,   "签单": d_ape,   "Signed": d_ape,
        "批核 APE(M)": e_ape,   "批核": e_ape,   "Issued": e_ape,
        "实际批核": e_ape,       "批核APE": e_ape,
    }
    series_by_idx = [c_ape, d_ape, e_ape]  # fallback: 0=预约, 1=签单, 2=批核

    patched_series = 0
    for ser_idx, ser in enumerate(root.findall(f".//{{{NS_C}}}ser")):
        # Try name match first
        tx = ser.find(f".//{{{NS_C}}}tx")
        ser_name = ""
        if tx is not None:
            v_el = tx.find(f".//{{{NS_C}}}v")
            if v_el is not None: ser_name = v_el.text or ""

        data_dict = None
        for sn, dd in series_by_name.items():
            if sn in ser_name or ser_name in sn:
                data_dict = dd; break
        # Fallback: use position (only for first 3 series)
        if data_dict is None and ser_idx < len(series_by_idx):
            data_dict = series_by_idx[ser_idx]

        if data_dict is None: continue

        # Find new months in data_dict that are NOT yet in all_months
        new_2026_months = sorted(
            k for k in data_dict
            if k.startswith("2026") and _label_to_key(
                f"{k[2:4]}-{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(k[5:7])-1]}"
            ) not in set(all_months)
        )
        # Build new category labels for any missing 2026 months
        MONTH_NUM_TO_ABBR = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                              7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        new_labels = []
        for k in new_2026_months:
            mo_num = int(k[5:7])
            label = f"{k[2:4]}-{MONTH_NUM_TO_ABBR[mo_num]}"
            if label not in all_months:
                new_labels.append((k, label))

        # Patch numCache: update existing 2026 months + add new ones
        for nc in ser.findall(f".//{{{NS_C}}}numCache"):
            # Update existing points
            for pt in nc.findall(f"{{{NS_C}}}pt"):
                idx = int(pt.get("idx", "0"))
                label = all_months[idx] if idx < len(all_months) else None
                if label is None: continue
                key = _label_to_key(label)
                # Only patch 2026 months — leave 2025 values untouched
                if key and key.startswith("2026") and key in data_dict:
                    v_node = pt.find(f"{{{NS_C}}}v")
                    if v_node is not None:
                        v_node.text = f"{data_dict[key]:.2f}"

            # Add new month points
            if new_labels:
                ptCount = nc.find(f"{{{NS_C}}}ptCount")
                if ptCount is not None:
                    ptCount.set("val", str(len(all_months) + len(new_labels)))
                for k, label in new_labels:
                    new_idx = len(all_months) + new_labels.index((k, label))
                    new_pt = _etree_lxml_m.SubElement(nc, f"{{{NS_C}}}pt")
                    new_pt.set("idx", str(new_idx))
                    new_v = _etree_lxml_m.SubElement(new_pt, f"{{{NS_C}}}v")
                    new_v.text = f"{data_dict[k]:.2f}"

        # Add new month categories (only for first series to avoid duplication)
        if ser_idx == 0 and new_labels:
            for ser2 in root.findall(f".//{{{NS_C}}}ser"):
                for sc in ser2.findall(f"{{{NS_C}}}cat//{{{NS_C}}}strCache"):
                    ptCount = sc.find(f"{{{NS_C}}}ptCount")
                    if ptCount is not None:
                        ptCount.set("val", str(len(all_months) + len(new_labels)))
                    for k, label in new_labels:
                        new_idx = len(all_months) + new_labels.index((k, label))
                        new_pt = _etree_lxml_m.SubElement(sc, f"{{{NS_C}}}pt")
                        new_pt.set("idx", str(new_idx))
                        new_v = _etree_lxml_m.SubElement(new_pt, f"{{{NS_C}}}v")
                        new_v.text = label
            all_months.extend([lbl for _, lbl in new_labels])
            print(f"  [D-s1 patch] Added {len(new_labels)} new month(s): {[lbl for _, lbl in new_labels]}")

        patched_series += 1

    print(f"  [D-s1 patch] {chart_name}: {patched_series} series patched (2026 months only)")
    _dbg_months = sorted(k for k in c_ape if k.startswith("2026"))
    for _dbg_m in _dbg_months:
        print(f"    {_dbg_m}: 预约={c_ape.get(_dbg_m,0):.1f}M 签单={d_ape.get(_dbg_m,0):.1f}M 批核={e_ape.get(_dbg_m,0):.1f}M")

# Patch slides[0] Chart 1 with correct S1 values (fixes Apr break and any wrong values)
_patch_s1_monthly_trend(_s(0), "Chart 1")
_fix_chart_dlbls_positions(_s(0), "Chart 1")

def _fix_2026_highlight(slide, chart_name, rect_name, text_name,
                        num_total, num_highlight):
    """Resize the '2026' highlight rectangle to cover the last num_highlight months."""
    chart_shp = _find_shape(slide, chart_name)
    rect_shp  = _find_shape(slide, rect_name)
    text_shp  = _find_shape(slide, text_name)
    if not (chart_shp and rect_shp):
        return False
    plot_width = int(chart_shp.width * 0.945)
    plot_left  = chart_shp.left + int(chart_shp.width * 0.05)
    bucket_w   = plot_width / num_total
    new_width  = int(bucket_w * num_highlight)
    new_left   = int(plot_left + plot_width - new_width)
    rect_shp.left  = new_left
    rect_shp.width = new_width
    if text_shp:
        text_shp.left  = new_left
        text_shp.width = new_width
    return True

# 动态计算总月数和2026高亮月数
# total months from 2025-01 to CURRENT_MONTH_COL
_cm_year, _cm_mo = int(CURRENT_MONTH_COL[:4]), int(CURRENT_MONTH_COL[5:7])
_num_total_months = (_cm_year - 2025) * 12 + _cm_mo  # e.g. 2026-05 → 17
_num_2026_months  = _cm_mo                              # e.g. 5
_fix_2026_highlight(_s(0), "Chart 1", "Shape 83", "Text 84",
                    _num_total_months, _num_2026_months)

# Slide 2 — F批核路径管控 + E monthly charts
# Chart 1 = F forecast/批核路径管控 bar chart (on _SL_FORECAST = slides[1])
# Chart_YY/QD/PH = E monthly appointment/signed/approved bar charts (also on slides[1])
# Use _SL_FORECAST as preferred_slide to ensure Chart 1 goes to slides[1], not slides[0].
print("\n[Slide 2 — F forecast + E monthly]")
_replace_chart(_chart_slide("Chart 1",   _SL_FORECAST), "Chart 1",   slide2_forecast_chart(S1))
_replace_chart(_chart_slide("Chart_YY",  _SL_FORECAST), "Chart_YY",  slide2_appointment(S1))
_replace_chart(_chart_slide("Chart_QD",  _SL_FORECAST), "Chart_QD",  slide2_signed(S1))
_replace_chart(_chart_slide("Chart_PH",  _SL_FORECAST), "Chart_PH",  slide2_approved(S1))

# ── Extend E charts to ALL available 2026 months (slide2_* only produce Jan-Apr) ──
def _extend_monthly_bar_chart(slide, chart_name, s1_block_letter):
    """
    Full-rebuild E-style horizontal bar chart from S1 block for ALL available 2026 months.

    Fix: completely replace strCache + numCache from scratch so pt idx values are always
    sequential 0..N-1.  The old append approach produced idx=8 for May when the previous
    run left stale pts in the chart, causing PowerPoint to render May bars as blank.
    """
    import csv as _csv_ext, re as _re_ext
    from lxml import etree as _et_ext
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart: return
    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    root = shp.chart.part._element
    sers = root.findall(f".//{{{NS_C}}}ser")
    if not sers: return
    _MO_ZH = {1:"1月",2:"2月",3:"3月",4:"4月",5:"5月",6:"6月",
              7:"7月",8:"8月",9:"9月",10:"10月",11:"11月",12:"12月"}
    all_data = {}  # {month_num: ape_M}
    in_blk = False; hdr = None
    with open(CSV_S1, encoding='utf-8-sig') as _f:
        for _row in _csv_ext.reader(_f):
            if not _row: continue
            first = _row[0].strip()
            if first.startswith(f'{s1_block_letter}.') and '月度业绩' in first:
                in_blk = True; continue
            if not in_blk: continue
            if first.startswith('📌'): continue
            if _re_ext.match(r'^[A-Z]\.', first) and not first.startswith(f'{s1_block_letter}.'): break
            if hdr is None and any('年月' in c for c in _row):
                hdr = [c.strip() for c in _row]; continue
            if not first: break
            if hdr and _re_ext.match(r'^2026-\d{2}$', first):
                mo = int(first[5:7])
                try:
                    ape_idx = hdr.index('APE') if 'APE' in hdr else 2
                    all_data[mo] = float(_row[ape_idx].replace(',','')) / 1e6
                except: pass
    if not all_data: return
    months_sorted = sorted(all_data.keys())
    labels = [_MO_ZH[m] for m in months_sorted]
    n = len(months_sorted)
    for ser in sers:
        # Full rebuild strCache (categories)
        for sc in ser.findall(f"{{{NS_C}}}cat//{{{NS_C}}}strCache"):
            for pt in sc.findall(f"{{{NS_C}}}pt"): sc.remove(pt)
            ptc = sc.find(f"{{{NS_C}}}ptCount")
            if ptc is not None: ptc.set("val", str(n))
            for idx, lbl in enumerate(labels):
                pt = _et_ext.SubElement(sc, f"{{{NS_C}}}pt")
                pt.set("idx", str(idx))
                _et_ext.SubElement(pt, f"{{{NS_C}}}v").text = lbl
        # Full rebuild numCache (values)
        for nc in ser.findall(f".//{{{NS_C}}}numCache"):
            for pt in nc.findall(f"{{{NS_C}}}pt"): nc.remove(pt)
            ptc = nc.find(f"{{{NS_C}}}ptCount")
            if ptc is not None: ptc.set("val", str(n))
            for idx, mo in enumerate(months_sorted):
                pt = _et_ext.SubElement(nc, f"{{{NS_C}}}pt")
                pt.set("idx", str(idx))
                _et_ext.SubElement(pt, f"{{{NS_C}}}v").text = f"{all_data.get(mo, 0):.2f}"
        # Fix <c:f> formula range end row
        for f_el in ser.findall(f".//{{{NS_C}}}f"):
            if f_el.text and _re_ext.search(r'\d+$', f_el.text):
                f_el.text = _re_ext.sub(r'\d+$', str(n + 1), f_el.text)
    print(f"  [E-extend] {chart_name}: full rebuild {n} months ({labels})")


_extend_monthly_bar_chart(_chart_slide("Chart_YY", _SL_FORECAST), "Chart_YY", "C")
_extend_monthly_bar_chart(_chart_slide("Chart_QD", _SL_FORECAST), "Chart_QD", "D")
_extend_monthly_bar_chart(_chart_slide("Chart_PH", _SL_FORECAST), "Chart_PH", "E")

# Update E chart data labels (dLbl) to match new APE and 件数 values for ALL months.
# Fix: (1) remove stale manualLayout offsets that cause labels to overlap when bar count changes;
#      (2) inject a new dLbl for May (idx=4) if one doesn't already exist.
def _update_e_chart_dlbls(slide, chart_name, s1_block_letter):
    """
    Rewrite in-chart dLbl rich-text for each bar (all available 2026 months).
    Also removes stale manualLayout overrides and injects missing month labels.
    """
    from copy import deepcopy as _dc_edlbl
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart:
        print(f"  ! dLbl chart not found: {chart_name}")
        return
    df_block = S1[s1_block_letter]
    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    root = shp.chart.part._element

    # Build {month_num: (ape_M, cnt)} from block
    months_2026 = sorted(r for r in df_block.iloc[:, 0].tolist() if str(r).startswith("2026-"))
    mo_data = {}  # {idx: (ape_m, cnt)}
    for idx, ym in enumerate(months_2026):
        row = df_block[df_block.iloc[:, 0] == ym]
        if not len(row): continue
        mo_data[idx] = (to_m(row.iloc[0]["APE"]), int(num(row.iloc[0]["件数"])))

    for ser in root.findall(f".//{{{NS_C}}}ser"):
        dLbls = ser.find(f"{{{NS_C}}}dLbls")
        if dLbls is None: continue
        if (del_el := dLbls.find(f"{{{NS_C}}}delete")) is not None and del_el.get("val") == "1": continue

        # Step 1: build map of existing dLbl by idx, removing manualLayout overrides
        existing = {}
        for dl in dLbls.findall(f"{{{NS_C}}}dLbl"):
            idx_el = dl.find(f"{{{NS_C}}}idx")
            if idx_el is None: continue
            i = int(idx_el.get("val", "-1"))
            # Remove stale manualLayout (causes overlap when bar count changes)
            for child in list(dl):
                if (child.find(f".//{{{NS_C}}}manualLayout") is not None
                        or child.tag == f"{{{NS_C}}}layout"):
                    dl.remove(child)
            existing[i] = dl

        # Step 2: set global dLblPos = outEnd (prevents crowding on short bars)
        pos_el = dLbls.find(f"{{{NS_C}}}dLblPos")
        if pos_el is not None:
            pos_el.set("val", "outEnd")

        # Step 3: update text for existing dLbls + inject new ones for missing months
        template = existing.get(0) or (list(existing.values())[0] if existing else None)
        for idx, (ape_m, cnt) in mo_data.items():
            new_label = f"APE {ape_m:.1f}M / {cnt}件"
            if idx in existing:
                dl = existing[idx]
                a_ts = dl.findall(f".//{{{NS_A}}}t")
                if a_ts:
                    a_ts[0].text = new_label
                    for extra in a_ts[1:]: extra.text = ""
            elif template is not None:
                # Inject new dLbl cloned from template
                new_dl = _dc_edlbl(template)
                idx_el2 = new_dl.find(f"{{{NS_C}}}idx")
                if idx_el2 is not None: idx_el2.set("val", str(idx))
                a_ts = new_dl.findall(f".//{{{NS_A}}}t")
                if a_ts:
                    a_ts[0].text = new_label
                    for extra in a_ts[1:]: extra.text = ""
                dLbls.append(new_dl)
                print(f"  [dLbl] {chart_name}: injected idx={idx} → {new_label!r}")

    print(f"  [dLbl] {chart_name} updated ({s1_block_letter} block, {len(mo_data)} months)")

_update_e_chart_dlbls(_chart_slide("Chart_YY", _SL_FORECAST), "Chart_YY", "C")
_update_e_chart_dlbls(_chart_slide("Chart_QD", _SL_FORECAST), "Chart_QD", "D")
_update_e_chart_dlbls(_chart_slide("Chart_PH", _SL_FORECAST), "Chart_PH", "E")


# ── slides[1]: C 业务类型 bar + K donut ───────────────────────────────────
# Chart_JM (Slide 5) = L 目标 vs 已批核/未批核/待签 — 各业务细分
#   Rebuilt to show 8 business segments from S2 A block (not S1 G business-type 3-category).
#   Fix also removes stale external OLE reference that causes PowerPoint to ignore numCache.

print("\n[Slides[1]: L segment bar + K donut]")

# ── L chart: 8-segment bar — patch Chart_JM from S2 A block ───────────────
def _patch_L_segment_chart(slide, chart_name):
    """
    Rebuild L chart (各业务线对比) with data from S2 A block.
    Categories: 8 business segments sorted by 目标APE desc.
    Series: 已批核 APE(M), 未批核 APE(M), 待签 APE(M), 目标缺口 APE(M)
    Also fixes: removes externalData + replaces OLE embed with proper xlsx
    so PowerPoint uses numCache instead of stale external data.
    """
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart:
        print(f"  ! [L chart] not found: {chart_name}")
        return

    from lxml import etree as _et_l
    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"

    # Read S2 A block for all 8 segments
    _L_SEGMENTS = ["BK业务","永明经代","同行经代","天领业务","ICLUB业务","成事家办","合伙转介业务","IFA业务"]
    _s2a = S2["A"]

    issued_vals, unbat_vals, pend_vals, gap_vals = [], [], [], []
    for seg in _L_SEGMENTS:
        _row = _s2a[_s2a["业务细分"] == seg]
        if not len(_row):
            issued_vals.append(0); unbat_vals.append(0); pend_vals.append(0); gap_vals.append(0)
            continue
        r = _row.iloc[0]
        _tgt  = to_m(r.get("目标APE", 0))
        _iss  = to_m(r.get("2026批核APE", 0))
        _unb  = to_m(r.get("未批核APE", 0))
        _pnd  = to_m(r.get("待签APE", 0))
        _gap  = max(0.0, _tgt - _iss - _unb - _pnd)
        issued_vals.append(_iss); unbat_vals.append(_unb)
        pend_vals.append(_pnd);   gap_vals.append(_gap)

    # Patch chart numCache + categories
    root = shp.chart.part._element
    sers = root.findall(f".//{{{NS_C}}}ser")
    series_new_vals = {0: issued_vals, 1: unbat_vals, 2: pend_vals, 3: gap_vals}

    for ser_idx, ser in enumerate(sers):
        if ser_idx not in series_new_vals:
            continue
        new_vals = series_new_vals[ser_idx]

        # Update categories (strCache under c:cat, not under c:tx)
        for sc in ser.findall(f"{{{NS_C}}}cat//{{{NS_C}}}strCache"):
            ptCount = sc.find(f"{{{NS_C}}}ptCount")
            if ptCount is not None:
                ptCount.set("val", str(len(_L_SEGMENTS)))
            for pt in sc.findall(f"{{{NS_C}}}pt"):
                sc.remove(pt)
            for idx, cat in enumerate(_L_SEGMENTS):
                pt_el = _et_l.SubElement(sc, f"{{{NS_C}}}pt")
                pt_el.set("idx", str(idx))
                v_sub = _et_l.SubElement(pt_el, f"{{{NS_C}}}v")
                v_sub.text = cat

        # Update numCache values
        for nc in ser.findall(f".//{{{NS_C}}}numCache"):
            ptCount = nc.find(f"{{{NS_C}}}ptCount")
            if ptCount is not None:
                ptCount.set("val", str(len(new_vals)))
            for pt in nc.findall(f"{{{NS_C}}}pt"):
                nc.remove(pt)
            for idx, v in enumerate(new_vals):
                pt_el = _et_l.SubElement(nc, f"{{{NS_C}}}pt")
                pt_el.set("idx", str(idx))
                v_sub = _et_l.SubElement(pt_el, f"{{{NS_C}}}v")
                v_sub.text = f"{v:.4f}"

    # ── Fix OLE embed: remove externalData + replace with proper xlsx ────
    # When chart has externalData pointing to an OLE object, PowerPoint
    # ignores numCache and loads the old Excel data instead.
    # Solution: remove externalData element and embed a fresh xlsx.
    ext_data = root.find(f"{{{NS_C}}}externalData")
    if ext_data is not None:
        root.remove(ext_data)
        print(f"  [L chart] Removed externalData")

    # Build and embed a minimal xlsx with correct data
    try:
        import openpyxl as _opx, io as _io, zipfile as _zf
        _wb = _opx.Workbook()
        _ws = _wb.active
        _ws.title = "ChartData"
        _ws.cell(1, 1, "业务细分")
        _series_names = ["已批核 APE(M)", "未批核 APE(M)", "待签 APE(M)", "目标缺口 APE(M)"]
        _all_vals = [issued_vals, unbat_vals, pend_vals, gap_vals]
        for j, sname in enumerate(_series_names):
            _ws.cell(1, j+2, sname)
        for i, seg in enumerate(_L_SEGMENTS):
            _ws.cell(i+2, 1, seg)
            for j, vals in enumerate(_all_vals):
                _ws.cell(i+2, j+2, vals[i])
        _buf = _io.BytesIO()
        _wb.save(_buf)
        _xlsx_bytes = _buf.getvalue()

        # Write xlsx into pptx zip and update chart rels
        # We do this after prs.save() via a post-processing zip patch.
        # Store bytes for the post-save patch step.
        _CHART_JM_XLSX_BYTES = _xlsx_bytes
        _CHART_JM_PART = shp.chart.part
        print(f"  [L chart] xlsx prepared ({len(_xlsx_bytes)} bytes) for post-save embed")
    except Exception as _e:
        print(f"  [L chart] xlsx prep error: {_e}")
        _CHART_JM_XLSX_BYTES = None
        _CHART_JM_PART = None

    tx = sers[0].find(f".//{{{NS_C}}}tx") if sers else None
    print(f"  [L chart] {chart_name}: {len(_L_SEGMENTS)} segments, {len(sers)} series patched")
    for i, (sname, vals) in enumerate(zip(_series_names, _all_vals)):
        print(f"    {sname}: {[round(v,1) for v in vals]}")
    return _CHART_JM_XLSX_BYTES, _CHART_JM_PART

_L_XLSX_BYTES, _L_CHART_PART = None, None
_l_result = _patch_L_segment_chart(_SL_BIZ_VIEW, "Chart_JM")
if _l_result:
    _L_XLSX_BYTES, _L_CHART_PART = _l_result

# ── K donut: slide1 business_type donut (Chart 0 on slides[1]) ────────────
_replace_chart(_SL_BIZ_VIEW, "Chart 0", slide5_donut(S2))
_fix_chart_dlbls_positions(_SL_BIZ_VIEW, "Chart 0")

# ── D chart: 预约/签单/批核 月度趋势 — direct patch from S2 monthly blocks ──
# slide1_chart_monthly_trend(S1) reads S1 blocks but misses Apr (reads wrong col).
# Fix: after calling the function, overwrite the numCache values directly from S2.
def _patch_monthly_trend_chart(slide, chart_name):
    """
    Patch D monthly trend chart (chart1) with correct values from S2 F/G/H-APE blocks.
    Series: 预约 APE(M) <- S2 F-APE 合计, 签单 APE(M) <- S2 G-APE 合计, 批核 APE(M) <- S2 H-APE 合计
    Categories: 26-Jan, 26-Feb, 26-Mar, 26-Apr
    """
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart:
        print(f"  ! [D chart] not found: {chart_name}")
        return

    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    root = shp.chart.part._element

    # Dynamically get all 2026 months from S2 F-APE block HEADER row (not data rows!)
    _MONTH_NUM_TO_ABBR_D = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                             7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    MONTHS = []
    import csv as _csv_pm, re as _re_pm
    _in_blk_pm = False
    with open(CSV_S2, encoding='utf-8-sig') as _f_pm:
        for _row_pm in _csv_pm.reader(_f_pm):
            if not _row_pm: continue
            _first_pm = _row_pm[0].strip()
            if _first_pm.startswith('F-APE.'): _in_blk_pm = True; continue
            if not _in_blk_pm: continue
            if _first_pm.startswith('📌'): continue
            if _first_pm == '业务细分':
                MONTHS = [c.strip() for c in _row_pm[1:]
                          if _re_pm.match(r'^2026-\d{2}$', c.strip())]
                break
            if _first_pm and _first_pm != '业务细分':
                break  # hit data without finding header — stop
    if not MONTHS:
        MONTHS = [CURRENT_MONTH_COL]
    CAT_LABELS = [
        f"{m[2:4]}-{_MONTH_NUM_TO_ABBR_D[int(m[5:7])]}"
        for m in MONTHS
    ]

    def _read_s2_monthly(block_label):
        """Read 合计 row from S2 block (F-APE/G-APE/H-APE)."""
        import csv as _csv
        in_block = False; hdr = None
        with open(CSV_S2, encoding="utf-8-sig") as f:
            for row in _csv.reader(f):
                if not row: continue
                first = row[0].strip()
                if first.startswith(block_label):
                    in_block = True; continue
                if not in_block: continue
                if first.startswith("📌"): continue
                if first == "业务细分":
                    hdr = [c.strip() for c in row]; continue
                if first == "合计" and hdr is not None:
                    result = {}
                    for col, val in zip(hdr[1:], row[1:]):
                        try: result[col] = float(val.replace(",","").strip())
                        except: result[col] = 0.0
                    return result
                if not first and hdr is not None:
                    break
        return {}

    f_ape = _read_s2_monthly("F-APE")   # 预约
    g_ape = _read_s2_monthly("G-APE")   # 签单
    h_ape = _read_s2_monthly("H-APE")   # 批核

    # Values in M
    yy_vals = [f_ape.get(m, 0) / 1e6 for m in MONTHS]
    qd_vals = [g_ape.get(m, 0) / 1e6 for m in MONTHS]
    ph_vals = [h_ape.get(m, 0) / 1e6 for m in MONTHS]

    series_data = [
        ("预约 APE(M)", yy_vals),
        ("签单 APE(M)", qd_vals),
        ("批核 APE(M)", ph_vals),
    ]

    # Patch numCache values directly for each series
    for ser in root.findall(f".//{{{NS_C}}}ser"):
        # Get series name
        tx = ser.find(f".//{{{NS_C}}}tx")
        if tx is None: continue
        v_el = tx.find(f".//{{{NS_C}}}v")
        if v_el is None: continue
        ser_name = v_el.text or ""

        matched_vals = None
        for name, vals in series_data:
            if name in ser_name or ser_name in name:
                matched_vals = vals; break
        if matched_vals is None: continue

        # Update numCache ptCount and pt values
        for nc in ser.findall(f".//{{{NS_C}}}numCache"):
            # Update ptCount
            ptCount = nc.find(f"{{{NS_C}}}ptCount")
            if ptCount is not None:
                ptCount.set("val", str(len(matched_vals)))
            # Remove existing pts and rebuild
            for pt in nc.findall(f"{{{NS_C}}}pt"):
                nc.remove(pt)
            from lxml import etree as _et2
            for idx, v in enumerate(matched_vals):
                pt_el = _et2.SubElement(nc, f"{{{NS_C}}}pt")
                pt_el.set("idx", str(idx))
                v_sub = _et2.SubElement(pt_el, f"{{{NS_C}}}v")
                v_sub.text = f"{v:.2f}"

        # Update strCache for CATEGORIES only (c:cat/c:strRef/c:strCache).
        # DO NOT touch c:tx/c:strRef/c:strCache (series name) — that would corrupt the legend!
        for sc in ser.findall(f"{{{NS_C}}}cat//{{{NS_C}}}strCache"):
            ptCount = sc.find(f"{{{NS_C}}}ptCount")
            if ptCount is not None:
                ptCount.set("val", str(len(CAT_LABELS)))
            for pt in sc.findall(f"{{{NS_C}}}pt"):
                sc.remove(pt)
            from lxml import etree as _et3
            for idx, cat in enumerate(CAT_LABELS):
                pt_el = _et3.SubElement(sc, f"{{{NS_C}}}pt")
                pt_el.set("idx", str(idx))
                v_sub = _et3.SubElement(pt_el, f"{{{NS_C}}}v")
                v_sub.text = cat

        print(f"  [D chart] {ser_name}: {[round(v,2) for v in matched_vals]}")

    _fix_chart_dlbls_positions(slide, chart_name)
    print(f"  [D chart] {chart_name} patched from S2 F/G/H-APE monthly blocks")

# Call slide1_chart_monthly_trend first (preserves any styling it sets),
# then overwrite the values with correct S2 data.
# 永明汇报 D chart: 永明月度预约/签单/批核 APE 趋势
# Use slide3_sunlife_trend(S2) which reads S2 永明-specific monthly data.
# Then _patch_monthly_trend_chart overwrites numCache directly from S2 F/G/H blocks
# to ensure Apr values are correct (slide3_sunlife_trend may produce stale Apr data).
_replace_chart(_SL_SUNLIFE, "Chart 0", slide3_sunlife_trend(S2))
_patch_monthly_trend_chart(_SL_SUNLIFE, "Chart 0")
_fix_chart_dlbls_positions(_SL_SUNLIFE, "Chart 0")

# Slide 3+ — channel/bubble charts
# Chart K doesn't exist in template — skip it (slide5_target_vs_actual goes to _SL_BIZ_VIEW instead)
print("\n[Slide 3]")
# (channel trend charts handled below via C9013-C9037)

CHANNEL_ORDER = ["永明经代","天领业务","BK业务","合伙转介业务","成事家办","同行经代","ICLUB业务"]
# Chart 0-6 don't exist; channel charts use names C9013-C9037 on Slide 4 (slides[3])
# Skip Chart 0-6 loop — already handled by C9013-C9037 below

# Slide 4 I — 业务线月度三线趋势 charts (confirmed names from xlsx embed log)
_I_CHART_MAP = [
    ("C9013", "天领业务"),
    ("C9017", "成事家办"),
    ("C9021", "BK业务"),
    ("C9025", "同行经代"),
    ("C9029", "永明经代"),
    ("C9033", "合伙转介业务"),
    ("C9037", "ICLUB业务"),
]
print("\n[Slide 4 I charts]")
# Update I-chart section title dynamically (e.g. "Jan-Mar 2026" → "Jan-May 2026")
_I_MO_ABBR = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
              7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
import re as _re_i4
for _sh_i4 in _SL_BUBBLE.shapes:
    if not _sh_i4.has_text_frame: continue
    for _p_i4 in _sh_i4.text_frame.paragraphs:
        _ptxt_i4 = ''.join(r.text for r in _p_i4.runs)
        if 'Jan' in _ptxt_i4 and '2026' in _ptxt_i4 and _p_i4.runs:
            _new_i4 = _re_i4.sub(
                r'Jan[–\-][A-Za-z]+ 2026',
                f'Jan–{_I_MO_ABBR[_cm_month]} 2026',
                _ptxt_i4
            )
            if _new_i4 != _ptxt_i4:
                _p_i4.runs[0].text = _new_i4
                for r in _p_i4.runs[1:]: r.text = ""
                print(f"  [I title] {_ptxt_i4[:50]} → {_new_i4[:50]}")
for chart_name, seg in _I_CHART_MAP:
    _replace_chart(_chart_slide(chart_name), chart_name, slide4_channel_trend(S2, seg))

# ── Slide 4 I: extend channel trend charts to ALL available 2026 months ──────
# slide4_channel_trend() only produces Jan-Apr; this function adds May onward.
# Reads S2 C-APE/D-APE/E-APE (全业务 monthly) per business segment.
def _extend_i_channel_chart(slide, chart_name, seg_name):
    """
    Full-rebuild an I-chart (C9013-C9037) with ALL available 2026 months from S2 C/D/E-APE.

    Fix: completely replace strCache + numCache instead of appending.
    The old append approach retained the English Jan/Feb/Mar/Apr categories from
    slide4_channel_trend() and appended Chinese 1月-5月, producing 9 duplicate pts.
    Full rebuild always produces clean sequential idx 0..N-1.
    """
    import csv as _csv_ic, re as _re_ic
    from lxml import etree as _et_ic
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart:
        return
    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    root = shp.chart.part._element
    sers = root.findall(f".//{{{NS_C}}}ser")
    if not sers:
        return

    _MO_ZH_IC = {1:"1月",2:"2月",3:"3月",4:"4月",5:"5月",6:"6月",
                 7:"7月",8:"8月",9:"9月",10:"10月",11:"11月",12:"12月"}

    def _read_seg_monthly(block_prefix, seg):
        res = {}
        in_b = False; hdr = None
        with open(CSV_S2, encoding="utf-8-sig") as _f2:
            for _r2 in _csv_ic.reader(_f2):
                if not _r2: continue
                first2 = _r2[0].strip()
                if first2.startswith(block_prefix + ".") or first2.startswith(block_prefix + "-"):
                    in_b = True; continue
                if not in_b: continue
                if first2.startswith("📌"): continue
                if first2 == "业务细分":
                    hdr = [c.strip() for c in _r2]; continue
                if not first2 and hdr: break
                if hdr and first2 == seg:
                    for col, val in zip(hdr[1:], _r2[1:]):
                        if _re_ic.match(r"^2026-\d{2}$", col):
                            try: res[int(col[5:7])] = float(val.replace(",", ""))
                            except: res[int(col[5:7])] = 0.0
                    break
        return res

    _BLOCK_MAP_IC = {
        "预约": "C-APE", "签单": "D-APE", "批核": "E-APE",
        "Appointment": "C-APE", "Signed": "D-APE", "Issued": "E-APE",
    }
    _BLOCK_ORDER_IC = ["C-APE", "D-APE", "E-APE"]

    # All available months from CSV
    all_months = sorted(_read_seg_monthly("C-APE", seg_name).keys())
    if not all_months:
        return
    labels = [_MO_ZH_IC[m] for m in all_months]
    n = len(all_months)

    for si, ser in enumerate(sers):
        tx = ser.find(f".//{{{NS_C}}}tx")
        sname = ""
        if tx is not None:
            v = tx.find(f".//{{{NS_C}}}v")
            if v is not None: sname = v.text or ""
        block = next((b for k, b in _BLOCK_MAP_IC.items() if k in sname or sname in k), None)
        if block is None and si < len(_BLOCK_ORDER_IC):
            block = _BLOCK_ORDER_IC[si]
        if block is None:
            continue

        seg_data = _read_seg_monthly(block, seg_name)

        # Full rebuild strCache (categories)
        for sc in ser.findall(f"{{{NS_C}}}cat//{{{NS_C}}}strCache"):
            for pt in sc.findall(f"{{{NS_C}}}pt"): sc.remove(pt)
            ptc = sc.find(f"{{{NS_C}}}ptCount")
            if ptc is not None: ptc.set("val", str(n))
            for idx, lbl in enumerate(labels):
                pt = _et_ic.SubElement(sc, f"{{{NS_C}}}pt")
                pt.set("idx", str(idx))
                _et_ic.SubElement(pt, f"{{{NS_C}}}v").text = lbl

        # Full rebuild numCache (values)
        for nc in ser.findall(f".//{{{NS_C}}}numCache"):
            for pt in nc.findall(f"{{{NS_C}}}pt"): nc.remove(pt)
            ptc = nc.find(f"{{{NS_C}}}ptCount")
            if ptc is not None: ptc.set("val", str(n))
            for idx, mo in enumerate(all_months):
                val = seg_data.get(mo, 0.0) / 1e6
                pt = _et_ic.SubElement(nc, f"{{{NS_C}}}pt")
                pt.set("idx", str(idx))
                _et_ic.SubElement(pt, f"{{{NS_C}}}v").text = f"{val:.4f}"

        # Fix <c:f> formula range
        for f_el in ser.findall(f".//{{{NS_C}}}f"):
            if f_el.text and _re_ic.search(r"\d+$", f_el.text):
                f_el.text = _re_ic.sub(r"\d+$", str(n + 1), f_el.text)

    print(f"  [I-extend] {chart_name} ({seg_name}): full rebuild {n} months ({labels})")

for chart_name, seg in _I_CHART_MAP:
    _extend_i_channel_chart(_chart_slide(chart_name), chart_name, seg)


# ── Slide 4 G: 气泡图 — 按数据更新气泡位置和大小 ──────────────────────
print("\n[Slide 4 G/H shapes]")
import math as _math

# Calibrated coordinate system (verified from actual bubble positions):
#   X: origin=488568 EMU at 0M, k=8686.8 EMU/M  (目标APE)
#   Y: origin=6291921 EMU at 0%, k=49530.4 EMU/%  (达成率, y decreases upward)
_G_OX = 488569;  _G_KX = 8686.8
_G_OY = 6291920; _G_KY = 49530.4
_G_PLOT_TOP = 1290574   # physical top of plot area

def _g_cx(tgt_m):    return int(_G_OX + tgt_m * _G_KX)
def _g_cy(rate_pct): return max(int(_G_OY - rate_pct * _G_KY), _G_PLOT_TOP + 5000)
def _g_sz(cnt):      return max(int(22947.0 * _math.sqrt(max(cnt,0)) + 121697.0), 109728)

_G_SEGS = [
    ("BK业务",       "Shape 65", "Text 66"),
    ("永明经代",     "Shape 67", "Text 68"),
    ("同行经代",     "Shape 69", "Text 70"),
    ("天领业务",     "Shape 71", "Text 72"),
    ("ICLUB业务",    "Shape 73", "Text 74"),
    ("成事家办",     "Shape 75", "Text 76"),
    ("合伙转介业务", "Shape 77", "Text 78"),
    ("IFA业务",      "Shape 79", "Text 80"),
]

# G bubble chart + H waterfall: in full 11-slide deck these are on Slide 4 (slides[3]).
# _SL_BUBBLE is found by "H  全业务目标缺口分解" text unique to this slide.
_slide4 = _SL_BUBBLE
_s2a = S2["A"]
for seg, bubble_name, lbl_name in _G_SEGS:
    row = _s2a[_s2a["业务细分"] == seg]
    if not len(row):
        print(f"  [G] {seg}: no S2 row, skip")
        continue
    r = row.iloc[0]
    # FIX A: 目标APE stored as raw yuan — must convert to M via to_m()
    # Without this, _g_cx() overflows to INT_MAX and bubbles disappear off-screen
    tgt_m    = to_m(r.get("目标APE", 0))
    rate_raw = num(str(r.get("达成率","0")).strip().replace("%",""))
    # FIX A2: 达成率 may be stored as decimal fraction (0.31) or percent (31.0)
    # If value <= 1.5, assume it's a fraction and convert to percent
    rate_pct = rate_raw * 100 if rate_raw <= 1.5 else rate_raw
    cnt      = int(num(r.get("批核件数", 0)))

    cx = _g_cx(tgt_m); cy = _g_cy(rate_pct); sz = _g_sz(cnt)

    # FIX: Clamp bubble so its bottom edge never crosses the plot frame bottom (y=6136894).
    # Without clamping, low-rate bubbles overflow the chart border.
    _G_PLOT_BOTTOM = 6136894
    if cy + sz // 2 > _G_PLOT_BOTTOM:
        cy = _G_PLOT_BOTTOM - sz // 2 - 5000
    if cy - sz // 2 < _G_PLOT_TOP:
        cy = _G_PLOT_TOP + sz // 2 + 5000

    for sh in _slide4.shapes:
        if sh.name == bubble_name:
            sh.left = cx - sz//2; sh.top = cy - sz//2
            sh.width = sz;        sh.height = sz
            print(f"  [G] {seg:12s} tgt={tgt_m:.0f}M rate={rate_pct:.1f}% cnt={cnt} sz={sz} ✓")
            break

    # FIX: Move label WITH bubble — label tracks bubble center with fixed x-offset.
    # All labels are positioned at cx + _LBL_OFFSET_X (left of center) and just below bubble.
    # Previously labels used cx - sh.width//2 which was off by ~170K EMU causing drift.
    _LBL_OFFSET_X = -342900   # verified from PPT scan: label.left = bubble_cx - 342900
    _LBL_GAP_Y    =  15000    # small gap between bubble bottom and label top
    for sh in _slide4.shapes:
        if sh.name == lbl_name and sh.has_text_frame:
            lbl_top = cy + sz // 2 + _LBL_GAP_Y
            # If label would overflow plot bottom, flip label above bubble
            if lbl_top + (sh.height or 164592) > _G_PLOT_BOTTOM + 50000:
                lbl_top = cy - sz // 2 - (sh.height or 164592) - _LBL_GAP_Y
            sh.left = cx + _LBL_OFFSET_X
            sh.top  = lbl_top
            break

# ── Slide 4 H: Waterfall — 柱形高度/位置/标签全部重算，标签统一在柱上方 ─
# Coordinate system:
#   _WF_BOTTOM = 5625084  (y at 0M baseline)
#   _WF_TOP_REF = 1554480 (y at target M)
#   EMU/M = (_WF_BOTTOM - _WF_TOP_REF) / target_M
_WF_BOTTOM = 5625084; _WF_TOP_REF = 1554480
_s1a = S1["A"]
_wf_tgt_row = _s1a[_s1a["指标"] == "2026全业务目标"]
_WF_MAX  = num(_wf_tgt_row["目标APE"].iloc[0]) / 1e6 if len(_wf_tgt_row) else 1113.0
_WF_HTOT = _WF_BOTTOM - _WF_TOP_REF    # total EMU for full range
_EPM     = _WF_HTOT / _WF_MAX          # EMU per M

def _top_at(m_level): return int(_WF_BOTTOM - m_level * _EPM)
def _bar_h(m_val):    return max(int(abs(m_val) * _EPM), 800)

# Waterfall segment values
_wv_bk = CH_BK["issued_m"];    _wv_ym = CH_YMJD["issued_m"]
_wv_th = CH_THJD["issued_m"];  _wv_tl = CH_TL["issued_m"]
_wv_ic = CH_ICLUB["issued_m"]; _wv_cs = CH_CSJB["issued_m"]
_wv_hh = CH_HHZJ["issued_m"];  _wv_ub = UNBAT_APE_M; _wv_pd = PEND_APE_M
_wv_gap = _WF_MAX - (_wv_bk+_wv_ym+_wv_th+_wv_tl+_wv_ic+_wv_cs+_wv_hh+_wv_ub+_wv_pd)

# Bar shapes — FIXED order from PPT left-position scan:
# Shape 102(BK), Shape 106(永明), Shape_313(同行),
# Shape_315×4 sorted by left: 5488940(天领),5778500(ICLUB),6057900(成事),6337300(合伙)
# Shape 114(未批核), Shape 118(待签), Shape 121(缺口)
_s315 = sorted([sh for sh in _slide4.shapes if sh.name=="Shape_315"], key=lambda s:s.left)

# Bar table: (shape_name_or_None, s315_idx, val_m, lbl_name, lbl_left)
_WF_BAR_TABLE = [
    ("Shape 102",  None, _wv_bk,  "Text 103", 4480433),   # BK
    ("Shape 106",  None, _wv_ym,  "Text 107", 4785106),   # 永明 ← was Shape_313, wrong!
    ("Shape_313",  None, _wv_th,  "Text 107", 5092446),   # 同行
    (None,         0,    _wv_tl,  "Text_314", 5525135),   # 天领  (S315 left=5488940)
    (None,         1,    _wv_ic,  "Text_314", 5805805),   # ICLUB (S315 left=5778500)
    (None,         2,    _wv_cs,  "Text_314", 6128385),   # 成事  (S315 left=6057900)
    (None,         3,    _wv_hh,  "Text_314", 6356985),   # 合伙  (S315 left=6337300)
    ("Shape 114",  None, _wv_ub,  "Text 115", 6517767),   # 未批核
    ("Shape 118",  None, _wv_pd,  "Text 119", 6850380),   # 待签
    ("Shape 121",  None, _wv_gap, "Text 122", 7118223),   # 缺口
]

_LBL_H = 182880; _LBL_GAP = 40000
_cum = _WF_MAX

for sh_name, s315_idx, val_m, lbl_name, lbl_left in _WF_BAR_TABLE:
    bar_top = _top_at(_cum)
    bar_h   = _bar_h(val_m)
    _cum   -= val_m
    bar_ok  = False

    # Update bar shape size/position
    if sh_name is not None:
        for sh in _slide4.shapes:
            if sh.name == sh_name:
                sh.top = bar_top; sh.height = bar_h; bar_ok = True; break
    elif s315_idx is not None and s315_idx < len(_s315):
        sh = _s315[s315_idx]
        sh.top = bar_top; sh.height = bar_h; bar_ok = True

    # FIX B: Labels always above bar — never center-inside-bar.
    # When labels are centered inside the bar, they blend with the bar color and become invisible.
    lbl_new_top = bar_top - _LBL_H - _LBL_GAP

    lbl_txt = ("−" if val_m >= 0 else "+") + f"{abs(val_m):.0f}" if lbl_name != "Text 122" else f"{val_m:.0f}"
    for sh in _slide4.shapes:
        if not sh.has_text_frame: continue
        if sh.name != lbl_name: continue
        if abs(sh.left - lbl_left) > 120000: continue
        sh.top = lbl_new_top
        if sh.text_frame.paragraphs and sh.text_frame.paragraphs[0].runs:
            sh.text_frame.paragraphs[0].runs[0].text = lbl_txt
            # 缺口标签(Text 122)在柱子上方白色区域，白字不可见 → 改为红色匹配柱子颜色
            if lbl_name == "Text 122":
                sh.text_frame.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
            for rr in sh.text_frame.paragraphs[0].runs[1:]: rr.text = ""
        break

    seg_name = {None: sh_name, 0:'天领', 1:'ICLUB', 2:'成事', 3:'合伙'}.get(s315_idx, sh_name)
    print(f"  [H] {str(seg_name):10s} {val_m:7.1f}M top={bar_top} h={bar_h} lbl={lbl_txt!r} {'✓' if bar_ok else '(lbl only)'}")

# ── Remaining chart replacements — names confirmed from xlsx embed log ────
# All use preferred_slide to avoid name conflicts (Chart_YY/QD/PH/0/1 exist on
# multiple slides; preferred_slide ensures we target the right one each time).

# BK page charts (Slide 10, slides[9]=_SL_BK)
print("\n[Slide 10 — BK charts]")
_replace_chart(_chart_slide("Chart_YY", _SL_BK), "Chart_YY", slide10_bk_appointment(S2))
_replace_chart(_chart_slide("Chart_QD", _SL_BK), "Chart_QD", slide10_bk_signed(S2))
_replace_chart(_chart_slide("Chart_PH", _SL_BK), "Chart_PH", slide10_bk_approved(S2))
_replace_chart(_chart_slide("Chart 1",  _SL_BK), "Chart 1",  slide10_bk_ka(S2))
_replace_chart(_chart_slide("Chart 0",  _SL_BK), "Chart 0",  slide10_donut_target(S2))
_fix_chart_dlbls_positions(_chart_slide("Chart 0", _SL_BK), "Chart 0")

# Extend BK Z charts to all available 2026 months
def _extend_bk_monthly_chart(slide, chart_name, ape_block, cnt_block):
    """
    Full-rebuild a Z bank monthly bar chart from S2 P/Q/R-APE blocks for ALL available months.

    Fix: completely replace strCache + numCache from scratch (sequential idx 0..N-1).
    Same root cause as _extend_monthly_bar_chart: the old append approach produced
    idx=8 for May, which PowerPoint renders as blank bars.
    """
    import csv as _csv_bk2, re as _re_bk2
    from lxml import etree as _et_bk2
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart: return
    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    root = shp.chart.part._element
    sers = root.findall(f".//{{{NS_C}}}ser")
    if not sers: return
    _MO_ZH2 = {1:"1月",2:"2月",3:"3月",4:"4月",5:"5月",6:"6月",
               7:"7月",8:"8月",9:"9月",10:"10月",11:"11月",12:"12月"}
    # Read available months from S2 ape_block header
    all_months = []
    _in_b2 = False
    with open(CSV_S2, encoding="utf-8-sig") as _f2:
        for _r2 in _csv_bk2.reader(_f2):
            if not _r2: continue
            first2 = _r2[0].strip()
            if first2.startswith(ape_block): _in_b2 = True; continue
            if not _in_b2: continue
            if first2.startswith("📌"): continue
            if first2 == "KEY ACCOUNT":
                all_months = [int(c[5:7]) for c in _r2[1:]
                              if _re_bk2.match(r"^2026-\d{2}$", c.strip())]
                break
    if not all_months: return

    def _bk_ka_data(block):
        res = {}; _in_b3 = False; hdr3 = None
        with open(CSV_S2, encoding="utf-8-sig") as _f3:
            for _r3 in _csv_bk2.reader(_f3):
                if not _r3: continue
                first3 = _r3[0].strip()
                if first3.startswith(block): _in_b3 = True; continue
                if not _in_b3: continue
                if first3.startswith("📌"): continue
                if first3 == "KEY ACCOUNT": hdr3 = [c.strip() for c in _r3]; continue
                if not first3 and hdr3: break
                if hdr3 and first3:
                    kd = {}
                    for col, val in zip(hdr3[1:], _r3[1:]):
                        if _re_bk2.match(r"^2026-\d{2}$", col):
                            try: kd[int(col[5:7])] = float(val.replace(",", ""))
                            except: kd[int(col[5:7])] = 0.0
                    res[first3] = kd
        return res

    ape_d = _bk_ka_data(ape_block)
    months_sorted = sorted(all_months)
    labels = [_MO_ZH2[m] for m in months_sorted]
    n = len(months_sorted)

    for ser in sers:
        tx = ser.find(f".//{{{NS_C}}}tx")
        sname = ""
        if tx is not None:
            v = tx.find(f".//{{{NS_C}}}v")
            if v is not None: sname = v.text or ""
        ka_key = next((k for k in ape_d if k in sname or sname in k), None)
        if ka_key is None:
            for ka_test in ["民生银行", "平安银行"]:
                if any(part in sname for part in ka_test.replace("银行", "")):
                    ka_key = ka_test; break

        # Full rebuild strCache
        for sc in ser.findall(f"{{{NS_C}}}cat//{{{NS_C}}}strCache"):
            for pt in sc.findall(f"{{{NS_C}}}pt"): sc.remove(pt)
            ptc = sc.find(f"{{{NS_C}}}ptCount")
            if ptc is not None: ptc.set("val", str(n))
            for idx, lbl in enumerate(labels):
                pt = _et_bk2.SubElement(sc, f"{{{NS_C}}}pt")
                pt.set("idx", str(idx))
                _et_bk2.SubElement(pt, f"{{{NS_C}}}v").text = lbl

        # Full rebuild numCache
        for nc in ser.findall(f".//{{{NS_C}}}numCache"):
            for pt in nc.findall(f"{{{NS_C}}}pt"): nc.remove(pt)
            ptc = nc.find(f"{{{NS_C}}}ptCount")
            if ptc is not None: ptc.set("val", str(n))
            for idx, mo in enumerate(months_sorted):
                val = (ape_d.get(ka_key, {}).get(mo, 0) / 1e6) if ka_key else 0.0
                pt = _et_bk2.SubElement(nc, f"{{{NS_C}}}pt")
                pt.set("idx", str(idx))
                _et_bk2.SubElement(pt, f"{{{NS_C}}}v").text = f"{val:.4f}"

        # Fix <c:f> formula range
        for f_el in ser.findall(f".//{{{NS_C}}}f"):
            if f_el.text and _re_bk2.search(r"\d+$", f_el.text):
                f_el.text = _re_bk2.sub(r"\d+$", str(n + 1), f_el.text)

    print(f"  [BK-extend] {chart_name}: full rebuild {n} months ({labels})")

# DISABLED: _extend_bk_monthly_chart overwrites embedded xlsx (Y-axis scale bug)
# _extend_bk_monthly_chart(_chart_slide("Chart_YY", _SL_BK), "Chart_YY", "P-APE", "P-件数")
# _extend_bk_monthly_chart(_chart_slide("Chart_QD", _SL_BK), "Chart_QD", "Q-APE", "Q-件数")
# _extend_bk_monthly_chart(_chart_slide("Chart_PH", _SL_BK), "Chart_PH", "R-APE", "R-件数")


# 执行管理端 (Slide 6, slides[5]=_SL_EXEC): Chart 0 = weekly trend
print("\n[Slide 6 — 执行管理端]")
_replace_chart(_chart_slide("Chart 0", _SL_EXEC), "Chart 0", slide6_weekly_trend(S3))

# Slide 8 (slides[7]): Chart 0 = referrer, Chart 1 = top10_ka
print("\n[Slide 8]")
_SL_8 = _s(7)
_replace_chart(_chart_slide("Chart 0", _SL_8), "Chart 0", slide8_referrer(S2))
_replace_chart(_chart_slide("Chart 1", _SL_8), "Chart 1", slide8_top10_ka(S2))

# ── Slide 8 V: 同行 KEY ACCOUNT 表格 (Table 1) ──────────────────────────────
# S2 K block only includes KAs with 批核APE > 0.
# KAs with 批核=0 but 未批核>0 are found by comparing:
#   - J合计 vs K合计: the difference identifies missing KAs
#   - L-APE block: 富仕德财富, 裕承资产 appear here with signed APE = their 未批核 value
#   - 松石保险 and any remaining: backfilled from J合计 − K合计 − known L-APE extras
# 合计 row: always from J block 合计 (covers ALL channel KAs).
# Table grows dynamically via XML clone if CSV has more rows than PPT slots.

def _build_peer_ka_table_data(s2_dict):
    """
    Returns (ka_records, total_dict) for the Slide 8 V table.

    ka_records: list of dicts with keys matching K block columns,
                sorted by 2026批核APE desc then 未批核APE desc.
    total_dict: dict from J block 合计 row.
    """
    import csv as _csv_mod

    CSV_S2_PATH = CSV_S2  # uses the module-level constant

    # ── Read K block (批核APE > 0 KAs) ────────────────────────────────────
    k_records = []
    k_names = set()
    with open(CSV_S2_PATH, encoding="utf-8-sig") as _f:
        _in = False; _hdr = None
        for _row in _csv_mod.reader(_f):
            if not _row: continue
            _first = _row[0].strip()
            if _first.startswith("K. 同行业绩分析"): _in = True; continue
            if not _in: continue
            if _first.startswith("📌"): continue
            if _first == "KEY ACCOUNT": _hdr = [c.strip() for c in _row]; continue
            if not _first and _hdr: break
            if _first.startswith("L-APE"): break
            if _hdr is None: continue
            rec = {h: _row[i].strip() if i < len(_row) else "0"
                   for i, h in enumerate(_hdr)}
            if rec["KEY ACCOUNT"] == "合计": continue
            k_records.append(rec)
            k_names.add(rec["KEY ACCOUNT"])

    # ── Read L-APE block (预约同行) to find zero-批核 KAs ─────────────────
    # KAs in L-APE but absent from K have been reserved/signed but not approved.
    # Their L-APE 合计 column is their 未批核APE (same as M-APE 合计).
    l_ape_extras = {}   # name → 未批核APE in yuan
    l_cnt_extras = {}   # name → 未批核件数
    with open(CSV_S2_PATH, encoding="utf-8-sig") as _f:
        _in = False; _hdr = None
        for _row in _csv_mod.reader(_f):
            if not _row: continue
            _first = _row[0].strip()
            if _first.startswith("L-APE."): _in = True; continue
            if not _in: continue
            if _first.startswith("📌"): continue
            if _first == "KEY ACCOUNT": _hdr = [c.strip() for c in _row]; continue
            if not _first and _hdr: break
            if _first.startswith("L-件数"): break
            if _hdr is None: continue
            if _first in ("合计", ""): continue
            if _first not in k_names:
                # 合计 column = total signed APE → proxy for 未批核APE
                try:
                    col_idx = _hdr.index("合计")
                    l_ape_extras[_first] = float(_row[col_idx].replace(",", "") or "0")
                except (ValueError, IndexError):
                    l_ape_extras[_first] = 0.0

    with open(CSV_S2_PATH, encoding="utf-8-sig") as _f:
        _in = False; _hdr = None
        for _row in _csv_mod.reader(_f):
            if not _row: continue
            _first = _row[0].strip()
            if _first.startswith("L-件数."): _in = True; continue
            if not _in: continue
            if _first.startswith("📌"): continue
            if _first == "KEY ACCOUNT": _hdr = [c.strip() for c in _row]; continue
            if not _first and _hdr: break
            if _first.startswith("M-APE"): break
            if _hdr is None: continue
            if _first in ("合计", ""): continue
            if _first in l_ape_extras:
                try:
                    col_idx = _hdr.index("合计")
                    l_cnt_extras[_first] = int(float(_row[col_idx].replace(",", "") or "0"))
                except (ValueError, IndexError):
                    l_cnt_extras[_first] = 0

    # ── Read J block 合计 ──────────────────────────────────────────────────
    total_dict = None
    with open(CSV_S2_PATH, encoding="utf-8-sig") as _f:
        _in = False; _hdr = None
        for _row in _csv_mod.reader(_f):
            if not _row: continue
            _first = _row[0].strip()
            if _first.startswith("J. 同行推荐人分析"): _in = True; continue
            if not _in: continue
            if _first.startswith("📌"): continue
            if not _hdr: _hdr = [c.strip() for c in _row]; continue
            if _first == "合计":
                _rec = {h: _row[i].strip() if i < len(_row) else "0"
                        for i, h in enumerate(_hdr)}
                total_dict = {
                    "2026批核APE":  float(_rec.get("2026批核APE", "0").replace(",","")),
                    "批核件数":     float(_rec.get("批核件数", "0").replace(",","")),
                    "未批核APE":    float(_rec.get("未批核APE", "0").replace(",","")),
                    "未批核件数":   float(_rec.get("未批核件数", "0").replace(",","")),
                    "待签APE":      float(_rec.get("待签APE", "0").replace(",","")),
                    "待签件数":     float(_rec.get("待签件数", "0").replace(",","")),
                    "总APE":        float(_rec.get("总APE", "0").replace(",","")),
                    "总件数":       float(_rec.get("总件数", "0").replace(",","")),
                }
                break
            if not _first: break

    # ── Derive 松石保险 / any remaining gap from J合计 − K合计 − L-APE extras ─
    if total_dict:
        k_unbat_total = sum(float(r.get("未批核APE", "0").replace(",","")) for r in k_records)
        l_unbat_total = sum(l_ape_extras.values())
        j_unbat_total = total_dict["未批核APE"]
        residual_ape = j_unbat_total - k_unbat_total - l_unbat_total

        k_unbat_cnt   = sum(float(r.get("未批核件数", "0").replace(",","")) for r in k_records)
        l_unbat_cnt   = sum(l_cnt_extras.values())
        j_unbat_cnt   = total_dict["未批核件数"]
        residual_cnt  = int(round(j_unbat_cnt - k_unbat_cnt - l_unbat_cnt))

        if residual_ape > 1000 and residual_cnt > 0:
            # Distribute residual as a single "松石保险" row (or split if cnt>1)
            l_ape_extras["松石保险"] = residual_ape
            l_cnt_extras["松石保险"] = residual_cnt

    # ── Build extra rows from L-APE extras ────────────────────────────────
    # Sort extras: largest 未批核APE first
    extra_records = []
    for ka_name, unbat_ape in sorted(l_ape_extras.items(), key=lambda x: -x[1]):
        unbat_cnt = l_cnt_extras.get(ka_name, 0)
        extra_records.append({
            "KEY ACCOUNT": ka_name,
            "2026批核APE": "0", "批核件数": "0",
            "未批核APE":   str(int(unbat_ape)),
            "未批核件数":  str(unbat_cnt),
            "待签APE": "0", "待签件数": "0",
            "总APE":   str(int(unbat_ape)),
            "总件数":  str(unbat_cnt),
        })

    all_records = k_records + extra_records

    # Fallback 合计 if J block missing
    if total_dict is None:
        total_dict = {
            "2026批核APE":  sum(float(r.get("2026批核APE","0").replace(",","")) for r in all_records),
            "批核件数":     sum(float(r.get("批核件数","0").replace(",","")) for r in all_records),
            "未批核APE":    sum(float(r.get("未批核APE","0").replace(",","")) for r in all_records),
            "未批核件数":   sum(float(r.get("未批核件数","0").replace(",","")) for r in all_records),
            "待签APE":      sum(float(r.get("待签APE","0").replace(",","")) for r in all_records),
            "待签件数":     sum(float(r.get("待签件数","0").replace(",","")) for r in all_records),
            "总APE":        sum(float(r.get("总APE","0").replace(",","")) for r in all_records),
            "总件数":       sum(float(r.get("总件数","0").replace(",","")) for r in all_records),
        }

    print(f"  [Slide8 V] KA rows: {len(k_records)} from K + {len(extra_records)} extras "
          f"= {len(all_records)} total")
    return all_records, total_dict


def _update_slide8_peer_ka_table(slide):
    """
    Rebuild Table 1 (同行 KA 表格) on Slide 8 using complete data from S2.
    Dynamically adds rows to the PPT table if more data rows are needed.
    """
    tbl_shape = None
    for sh in slide.shapes:
        if sh.has_table and sh.name == "Table 1":
            tbl_shape = sh
            break
    if tbl_shape is None:
        print("  [Slide8 V table] Table 1 not found, skipping")
        return

    from lxml import etree as _et_tbl
    from copy import deepcopy
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

    def _fmt_ape(v):
        try:
            m = float(str(v).replace(",", "")) / 1_000_000
        except (ValueError, TypeError):
            m = 0.0
        return f"{m:.2f}" if m > 0 else "—"

    def _fmt_cnt(v):
        try:
            c = int(float(str(v).replace(",", "")))
        except (ValueError, TypeError):
            c = 0
        return str(c) if c > 0 else "—"

    def _tr_set(tr_el, col_idx, text):
        """Set text in cell col_idx of a raw <a:tr> lxml element."""
        tcs = tr_el.findall(f"{{{NS_A}}}tc")
        if col_idx >= len(tcs):
            return
        t_els = tcs[col_idx].findall(f".//{{{NS_A}}}t")
        if t_els:
            t_els[0].text = text
            for extra in t_els[1:]:
                extra.text = ""
        else:
            p_els = tcs[col_idx].findall(f".//{{{NS_A}}}p")
            if p_els:
                r_el = _et_tbl.SubElement(p_els[0], f"{{{NS_A}}}r")
                t_el = _et_tbl.SubElement(r_el, f"{{{NS_A}}}t")
                t_el.text = text

    # Build data
    ka_records, total_dict = _build_peer_ka_table_data(S2)
    n_ka = len(ka_records)

    # Get current table rows via lxml (direct, avoids python-pptx row cache issues)
    tbl_el = tbl_shape.table._tbl
    tr_list = tbl_el.findall(f"{{{NS_A}}}tr")
    # row 0 = header, row -1 = 合计, rows 1..-2 = data+blank slots
    n_data_slots = len(tr_list) - 2  # current data slot count

    # Add rows if needed (need n_ka data rows + 1 blank separator)
    needed = n_ka + 1
    if needed > n_data_slots:
        extra_n = needed - n_data_slots
        template_tr = tr_list[1]  # clone row 1 (styled data row)
        insert_before = tr_list[-1]  # before 合计
        for _ in range(extra_n):
            new_tr = deepcopy(template_tr)
            for t in new_tr.findall(f".//{{{NS_A}}}t"):
                t.text = ""
            tbl_el.insert(list(tbl_el).index(insert_before), new_tr)
        tr_list = tbl_el.findall(f"{{{NS_A}}}tr")
        print(f"  [Slide8 V table] Added {extra_n} rows → {len(tr_list)} total rows")

    data_trs = tr_list[1:-1]  # exclude header and 合计

    # Fill data rows
    written = 0
    for i, tr in enumerate(data_trs):
        if i < n_ka:
            rec = ka_records[i]
            _tr_set(tr, 0, str(rec.get("KEY ACCOUNT", "")).strip())
            _tr_set(tr, 1, _fmt_ape(rec.get("2026批核APE", 0)))
            _tr_set(tr, 2, _fmt_cnt(rec.get("批核件数", 0)))
            _tr_set(tr, 3, _fmt_ape(rec.get("未批核APE", 0)))
            _tr_set(tr, 4, _fmt_cnt(rec.get("未批核件数", 0)))
            _tr_set(tr, 5, _fmt_ape(rec.get("待签APE", 0)))
            _tr_set(tr, 6, _fmt_cnt(rec.get("待签件数", 0)))
            _tr_set(tr, 7, _fmt_ape(rec.get("总APE", 0)))
            _tr_set(tr, 8, _fmt_cnt(rec.get("总件数", 0)))
            written += 1
        else:
            for c in range(9):
                _tr_set(tr, c, "")  # blank separator

    # Update 合计 row (always last)
    total_tr = tr_list[-1]
    _tr_set(total_tr, 0, "合计")
    _tr_set(total_tr, 1, _fmt_ape(total_dict.get("2026批核APE", 0)))
    _tr_set(total_tr, 2, _fmt_cnt(total_dict.get("批核件数", 0)))
    _tr_set(total_tr, 3, _fmt_ape(total_dict.get("未批核APE", 0)))
    _tr_set(total_tr, 4, _fmt_cnt(total_dict.get("未批核件数", 0)))
    _tr_set(total_tr, 5, _fmt_ape(total_dict.get("待签APE", 0)))
    _tr_set(total_tr, 6, _fmt_cnt(total_dict.get("待签件数", 0)))
    _tr_set(total_tr, 7, _fmt_ape(total_dict.get("总APE", 0)))
    _tr_set(total_tr, 8, _fmt_cnt(total_dict.get("总件数", 0)))

    print(f"  [Slide8 V table] wrote {written}/{n_ka} KA rows | "
          f"合计: 批={total_dict.get('2026批核APE',0)/1e6:.1f}M/{int(total_dict.get('批核件数',0))}件 "
          f"未批={total_dict.get('未批核APE',0)/1e6:.1f}M/{int(total_dict.get('未批核件数',0))}件")

_update_slide8_peer_ka_table(_SL_8)


# Slide 9 (slides[8]): Chart 0 = peer_weekly (同行)
print("\n[Slide 9]")
_SL_9 = _s(8)
_replace_chart(_chart_slide("Chart 0", _SL_9), "Chart 0", slide9_peer_weekly(S3))

# ── Extend Slide 9 W月度分析表 (SumTable2109) — add May and beyond ───────────
def _extend_s9_monthly_table():
    """Add missing month rows to Slide 9 W peer monthly analysis table."""
    import csv as _csv_s9t, re as _re_s9t
    from copy import deepcopy as _s9dc
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    slide9 = _s(8)
    tbl_sh = next((sh for sh in slide9.shapes if sh.has_table and sh.name == 'SumTable2109'), None)
    if tbl_sh is None:
        print("  [S9 W-extend] SumTable2109 not found"); return
    tbl_el = tbl_sh.table._tbl
    tr_list = tbl_el.findall(f"{{{NS_A}}}tr")
    # Detect existing month rows (skip header row 0 and 合计 row -1)
    _MO_ABBR_S9 = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    existing_labels = set()
    for tr in tr_list[1:-1]:
        tcs = tr.findall(f"{{{NS_A}}}tc")
        if tcs:
            lbl = ''.join(t.text or '' for t in tcs[0].findall(f".//{{{NS_A}}}t")).strip()
            if lbl: existing_labels.add(lbl)
    # Read S2 L/M/N monthly data (peer channel)
    def _s9_read_peer_month(ape_blk, cnt_blk):
        """Returns {month_label: (ape_M, cnt)} label like 'May-26'"""
        res = {}
        def _blk(blk, is_ape):
            in_b = False; hdr = None
            with open(CSV_S2, encoding='utf-8-sig') as _f2:
                for _r2 in _csv_s9t.reader(_f2):
                    if not _r2: continue
                    first2 = _r2[0].strip()
                    if first2.startswith(blk): in_b = True; continue
                    if not in_b: continue
                    if first2.startswith('📌'): continue
                    if first2 == 'KEY ACCOUNT': hdr = [c.strip() for c in _r2]; continue
                    if first2 == '合计' and hdr:
                        for col, val in zip(hdr[1:], _r2[1:]):
                            if _re_s9t.match(r'^2026-\d{2}$', col):
                                mo = int(col[5:7])
                                lbl = f"{_MO_ABBR_S9[mo]}-26"
                                try: v = float(val.replace(',',''))
                                except: v = 0.0
                                if lbl not in res: res[lbl] = [0.0, 0]
                                if is_ape: res[lbl][0] = v / 1e6
                                else: res[lbl][1] = int(v)
                        break
                    if not first2 and hdr: break
        _blk(ape_blk, True); _blk(cnt_blk, False)
        return res
    app_d = _s9_read_peer_month('L-APE', 'L-件数')
    sgn_d = _s9_read_peer_month('M-APE', 'M-件数')
    apr_d = _s9_read_peer_month('N-APE', 'N-件数')
    all_lbls = sorted(set(list(app_d)+list(sgn_d)+list(apr_d)),
                      key=lambda x: list(_MO_ABBR_S9.values()).index(x.split('-')[0]) if x.split('-')[0] in _MO_ABBR_S9.values() else 99)
    new_lbls = [l for l in all_lbls if l not in existing_labels]
    if not new_lbls:
        print("  [S9 W-extend] No new rows to add"); return
    def _cell_set(tr_el, ci, text):
        tcs = tr_el.findall(f"{{{NS_A}}}tc")
        if ci >= len(tcs): return
        t_els = tcs[ci].findall(f".//{{{NS_A}}}t")
        if t_els:
            t_els[0].text = text
            for x in t_els[1:]: x.text = ""
    total_tr = tr_list[-1]
    template_tr = tr_list[-2]
    for new_lbl in new_lbls:
        new_tr = _s9dc(template_tr)
        am, ac = app_d.get(new_lbl, (0.0, 0))
        sm, sc = sgn_d.get(new_lbl, (0.0, 0))
        pm, pc = apr_d.get(new_lbl, (0.0, 0))
        _cell_set(new_tr, 0, new_lbl)
        _cell_set(new_tr, 1, f"{am:.2f}"); _cell_set(new_tr, 2, str(ac))
        _cell_set(new_tr, 3, f"{sm:.2f}"); _cell_set(new_tr, 4, str(sc))
        _cell_set(new_tr, 5, f"{pm:.2f}"); _cell_set(new_tr, 6, str(pc))
        tbl_el.insert(list(tbl_el).index(total_tr), new_tr)
        print(f"  [S9 W-extend] +{new_lbl}: app={am:.2f}/{ac}, sgn={sm:.2f}/{sc}, apr={pm:.2f}/{pc}")
    # Recalculate 合计
    tr_list2 = tbl_el.findall(f"{{{NS_A}}}tr")
    tots = [0.0]*6
    for tr in tr_list2[1:-1]:
        tcs = tr.findall(f"{{{NS_A}}}tc")
        vals = [''.join(t.text or '' for t in tcs[i].findall(f".//{{{NS_A}}}t")).strip()
                if i < len(tcs) else '' for i in range(7)]
        for j, v in enumerate(vals[1:]):
            try: tots[j] += float(v)
            except: pass
    total_tr = tr_list2[-1]
    for ci, v in enumerate(tots):
        _cell_set(total_tr, ci+1, f"{v:.2f}" if ci % 2 == 0 else str(int(v)))
    print(f"  [S9 W-extend] 合计 recalculated")

_extend_s9_monthly_table()

# Slide 11 / Bank page (slides[10]): Chart 1 = bank_weekly, Chart 0 = branch_ranking
print("\n[Slide 11]")
_SL_11 = _s(10)
_replace_chart(_chart_slide("Chart 1", _SL_11), "Chart 1", slide11_bank_weekly(S3))
_replace_chart(_chart_slide("Chart 0", _SL_11), "Chart 0", slide11_branch_ranking(S2))


# ============================================================================
# TEXT REPLACEMENTS
# PowerPoint), we do two passes:
#   1. Exact single-run replacement via run.text = new
#   2. Paragraph-level replacement: if the concatenated paragraph text matches
#      an "old", we put all new text in the first run and clear subsequent runs.
# ============================================================================

# Build the list of text replacements. Order matters: longer/more-specific first
# so we don't accidentally substring-match.

def fmt_m(v):        return f"{v:.1f}M"
def fmt_pct(v):      return f"{v:.1f}%"
def fmt_cnt(v):      return f"{int(v)} 件"
def fmt_cnt_n(v):    return f"{int(v)}件"
def fmt_w(v):        return f"{v:.1f}万"


# --- Per-slide replacement tables -------------------------------------------
# Each entry: (old_paragraph_text, new_paragraph_text)
# The matcher is paragraph-level (concatenated runs in one <a:p>) and literal.
# Use exact strings copied from the extracted text-run dump.

# SLIDE 1
SLIDE1_SUBS = [
    # cover date
    ("全维度业绩分析仪表盘  |   生成日期：2026-04-04",
     f"全维度业绩分析仪表盘  |   生成日期：{REPORT_DATE}"),
    # Module A - 全业务
    ("31.5%", fmt_pct(FULL_RATE)),               # rate callout
    ("350M",  f"{FULL_ISSUED_M:.0f}M"),          # 已批核 APE big
    ("533 件", f"{ISSUED_CNT} 件"),              # 批核件数
    ("-763M", f"-{FULL_GAP_M:.0f}M"),           # 剩余缺口
    ("已批 350M /", f"已批 {FULL_ISSUED_M:.0f}M /"),
    ("763M", f"{FULL_GAP_M:.0f}M"),
    # Module A - 永明
    ("30.4%", fmt_pct(SUN_RATE)),
    ("已批 297M /", f"已批 {SUN_ISSUED_M:.0f}M /"),
    ("679", f"{SUN_GAP_M:.0f}"),
    # Module B - pipeline KPI
    ("350.4M", f"{ISSUED_APE_M:.1f}M"),
    # B 模块占比分母含流失（_pipe_total_b）
    (f"533 件  |  占比 66.5%", f"{ISSUED_CNT} 件  |  占比 {ISSUED_SHARE:.1f}%"),
    ("167.9M", f"{UNBAT_APE_M:.1f}M"),
    ("242 件  |  占比 30.2%", f"{UNBAT_CNT} 件  |  占比 {UNBAT_SHARE:.1f}%"),
    ("3.9M", f"{PEND_APE_M:.1f}M"),
    ("12 件  |  占比 1.5%", f"{PEND_CNT} 件  |  占比 {PEND_SHARE:.1f}%"),
    ("6.4M", f"{LOST_APE_M:.1f}M"),
    ("14 件  |  占比 1.7%", f"{LOST_CNT} 件  |  占比 {LOST_SHARE:.1f}%"),
    # Module D — 2026 monthly detail (only the Jan-Mar actual values are from S1)
    # 2026-01..04 predicted
]

# Pull 2026 monthly values out of S1 for slides 1 and 2
# Pull 2026 monthly values out of S1 for slides 1 and 2 — dynamic month list
_ALL_2026_MONTHS = sorted(
    m for m in S1["C"].iloc[:, 0].tolist()
    if str(m).startswith("2026-")
)
_ALL_MONTH_NUMS = [int(m.split("-")[1]) for m in _ALL_2026_MONTHS]

def _s1_month(block, ym, col, as_m=True):
    r = S1[block]
    sub = r[r.iloc[:, 0] == ym]
    if not len(sub):
        return 0
    return to_m(sub.iloc[0][col]) if as_m else int(num(sub.iloc[0][col]))

M_APE_APPT = {m: _s1_month("C", f"2026-{m:02d}", "APE") for m in _ALL_MONTH_NUMS}
M_CNT_APPT = {m: _s1_month("C", f"2026-{m:02d}", "件数", as_m=False) for m in _ALL_MONTH_NUMS}
M_APE_SIGN = {m: _s1_month("D", f"2026-{m:02d}", "APE") for m in _ALL_MONTH_NUMS}
M_CNT_SIGN = {m: _s1_month("D", f"2026-{m:02d}", "件数", as_m=False) for m in _ALL_MONTH_NUMS}
M_APE_ISSU = {m: _s1_month("E", f"2026-{m:02d}", "APE") for m in _ALL_MONTH_NUMS}
M_CNT_ISSU = {m: _s1_month("E", f"2026-{m:02d}", "件数", as_m=False) for m in _ALL_MONTH_NUMS}

# ── Extend Slide 1 D monthly detail columns — call here, after M_* dicts are ready ──
_extend_s1_monthly_detail_cols()

# Slide 1 D-block monthly detail table (Jan..Apr)
# Slide 1 D-block monthly detail table — dynamic over all available 2026 months
# Old values (Jan=53.9, Feb=56.1, Mar=80.0, Apr=0.8) are replaced per-month
_SLIDE1_MONTH_OLD_APPT = {1:"53.9", 2:"56.1", 3:"80.0", 4:"0.8",  5:"0.0"}
_SLIDE1_MONTH_OLD_SIGN = {1:"47.9", 2:"60.8", 3:"80.6", 4:"3.1",  5:"0.0"}
_SLIDE1_MONTH_OLD_ISSU = {1:"116.8",2:"143.7",3:"85.9", 4:"4.1",  5:"0.0"}
_SLIDE1_MONTH_OLD_APPT_CNT = {1:"133件",2:"107件",3:"199件",4:"6件",  5:"0件"}
_SLIDE1_MONTH_OLD_SIGN_CNT = {1:"115件",2:"118件",3:"195件",4:"10件", 5:"0件"}
_SLIDE1_MONTH_OLD_ISSU_CNT = {1:"203件",2:"180件",3:"139件",4:"11件", 5:"0件"}

SLIDE1_SUBS += []
for _m in _ALL_MONTH_NUMS:
    _old_a = _SLIDE1_MONTH_OLD_APPT.get(_m, "0.0")
    _old_s = _SLIDE1_MONTH_OLD_SIGN.get(_m, "0.0")
    _old_i = _SLIDE1_MONTH_OLD_ISSU.get(_m, "0.0")
    _old_ac = _SLIDE1_MONTH_OLD_APPT_CNT.get(_m, "0件")
    _old_sc = _SLIDE1_MONTH_OLD_SIGN_CNT.get(_m, "0件")
    _old_ic = _SLIDE1_MONTH_OLD_ISSU_CNT.get(_m, "0件")
    SLIDE1_SUBS += [
        (_old_a,  f"{M_APE_APPT.get(_m,0):.1f}"),
        (_old_s,  f"{M_APE_SIGN.get(_m,0):.1f}"),
        (_old_i,  f"{M_APE_ISSU.get(_m,0):.1f}"),
        (_old_ac, f"{M_CNT_APPT.get(_m,0)}件"),
        (_old_sc, f"{M_CNT_SIGN.get(_m,0)}件"),
        (_old_ic, f"{M_CNT_ISSU.get(_m,0)}件"),
    ]

# SLIDE 2 – path-to-target
SLIDE2_SUBS = [
    # F-chart bottom KPI cards — each paragraph is a standalone number
    ("354.5M", f"{FULL_ISSUED_M:.1f}M"),
    ("763M",   f"{FULL_GAP_M:.0f}M"),
    ("84.8M",  f"{PACE_LINE}M"),
    ("69.5M",  f"{MIN_LINE}M"),
    # F-chart bottom KPI cards — small-text labels combine % with Chinese
    ("31.5% 达成率",    f"{FULL_RATE:.1f}% 达成率"),
    ("68.1% 目标剩余",  f"{100-FULL_RATE:.1f}% 目标剩余"),
    # In-chart annotations (pace line + min line text overlays)
    ("达标节奏线  84.8M/月（剩余 763M ÷ 9mo）",
     f"达标节奏线  {PACE_LINE}M/月（剩余 {FULL_GAP_M:.0f}M ÷ {REMAINING_M}mo）"),
    ("最低月底线  69.5M",
     f"最低月底线  {MIN_LINE}M"),
    # Also handle split-paragraph case
    ("84.8M/月（剩余 763M ÷ 9mo）",
     f"{PACE_LINE}M/月（剩余 {FULL_GAP_M:.0f}M ÷ {REMAINING_M}mo）"),
]

# SLIDE 3 – Sunlife
# --- Sunlife pipeline aggregates from S2 B 合计 row
sun_total = row_by(S2["B"], "业务细分", "合计")
SUN_UNBAT_M   = to_m(_safe(sun_total, "未批核APE"))
SUN_UNBAT_CNT = int(num(_safe(sun_total, "未批核件数")))
SUN_PEND_M    = to_m(_safe(sun_total, "待签APE"))
SUN_PEND_CNT  = int(num(_safe(sun_total, "待签件数")))
# FIX 2: 永明批核件数直接从 S2 B 合计行读取，不用硬编码或比例估算
SUN_ISSUED_CNT_B = int(num(_safe(sun_total, "批核件数")))
SUN_UNBAT_AVG_W = _avg_w(SUN_UNBAT_M, SUN_UNBAT_CNT)
SUN_PEND_AVG_W  = _avg_w(SUN_PEND_M,  SUN_PEND_CNT)

SLIDE3_SUBS = [
    ("296.9M", f"{SUN_ISSUED_M:.1f}M"),
    # FIX 2: 批核件数使用 SUN_ISSUED_CNT_B（从S2 B合计行），不再使用硬编码"526件"
    ("504件  |  达成率30.4%",
     f"{SUN_ISSUED_CNT_B}件  |  达成率{SUN_RATE:.1f}%"),
    ("目标\n976M", f"目标\n{SUN_TARGET_M:.0f}M"),
    ("976M", f"{SUN_TARGET_M:.0f}M"),
    # FIX 1: 缺口使用 SUN_GAP_M = SUN_TARGET_M - SUN_ISSUED_M
    ("|  缺口679M", f"|  缺口{SUN_GAP_M:.0f}M"),
    ("30.4%", fmt_pct(SUN_RATE)),
]

SLIDE3_SUBS += [
    ("163.6M", f"{SUN_UNBAT_M:.1f}M"),
    # 未批核/待签 paragraphs are a single string each — replace whole
    ("未批核235件|  件均69.7万",
     f"未批核{SUN_UNBAT_CNT}件|  件均{SUN_UNBAT_AVG_W:.1f}万"),
    ("待签9件  |  件均43.3万",
     f"待签{SUN_PEND_CNT}件  |  件均{SUN_PEND_AVG_W:.1f}万"),
    # FIX 2: 件数文本替换同样使用 SUN_ISSUED_CNT_B
    ("504件", f"{SUN_ISSUED_CNT_B}件"),
]

# Sunlife licenses (Module G) – from S1 H block
_s1h = S1["H"]
def _lic(name, col):
    r = _s1h[_s1h.iloc[:, 0] == name]
    if not len(r):
        # Try alternate spellings (e.g. UNINWIN vs UNIWIN in template vs CSV)
        alt_names = {"UNIWIN": "UNINWIN", "UNINWIN": "UNIWIN"}
        if name in alt_names:
            r = _s1h[_s1h.iloc[:, 0] == alt_names[name]]
    return to_m(r.iloc[0][col]) if len(r) else 0.0

JF_JAN  = _lic("JF", "2026-01");  JF_FEB = _lic("JF", "2026-02")
JF_MAR  = _lic("JF", PREV_MONTH_COL);  JF_APR = _lic("JF", CURRENT_MONTH_COL)
JF_UNB  = _lic("JF", "未批核");    JF_SUB = _lic("JF", "本月已递交")

UW_JAN  = _lic("UNIWIN", "2026-01");  UW_FEB = _lic("UNIWIN", "2026-02")
UW_MAR  = _lic("UNIWIN", PREV_MONTH_COL);  UW_APR = _lic("UNIWIN", CURRENT_MONTH_COL)
UW_UNB  = _lic("UNIWIN", "未批核");    UW_SUB = _lic("UNIWIN", "本月已递交")

DWNB_JAN = _lic("DW-Non-Bank", "2026-01"); DWNB_FEB = _lic("DW-Non-Bank", "2026-02")
DWNB_MAR = _lic("DW-Non-Bank", PREV_MONTH_COL); DWNB_APR = _lic("DW-Non-Bank", CURRENT_MONTH_COL)
DWNB_UNB = _lic("DW-Non-Bank", "未批核");   DWNB_SUB = _lic("DW-Non-Bank", "本月已递交")

SUB_JAN  = _lic("Sub Total", "2026-01"); SUB_FEB = _lic("Sub Total", "2026-02")
SUB_MAR  = _lic("Sub Total", PREV_MONTH_COL); SUB_APR = _lic("Sub Total", CURRENT_MONTH_COL)
SUB_UNB  = _lic("Sub Total", "未批核");   SUB_SUB = _lic("Sub Total", "本月已递交")

DWB_JAN  = _lic("DW Bank", "2026-01"); DWB_FEB = _lic("DW Bank", "2026-02")
DWB_MAR  = _lic("DW Bank", PREV_MONTH_COL); DWB_APR = _lic("DW Bank", CURRENT_MONTH_COL)
DWB_UNB  = _lic("DW Bank", "未批核");   DWB_SUB = _lic("DW Bank", "本月已递交")

EG_JAN  = _lic("EG", "2026-01");  EG_FEB = _lic("EG", "2026-02")
EG_MAR  = _lic("EG", PREV_MONTH_COL);  EG_APR = _lic("EG", CURRENT_MONTH_COL)
EG_UNB  = _lic("EG", "未批核");   EG_SUB = _lic("EG", "本月已递交")

SLIDE3_SUBS += [
    # JF row  (original values: 45.86 / 14.90 / 15.05 / 49.44 / 1.13)
    ("45.86M", f"{JF_JAN:.2f}M"),
    ("14.90M", f"{JF_FEB:.2f}M"),
    ("15.05M", f"{JF_MAR:.2f}M"),
    ("49.44M", f"{JF_UNB:.2f}M"),
    ("1.13M",  f"{JF_SUB:.2f}M"),
    # UNIWIN  (original: 21.65 / 15.146? note deck has 8.88 twice – keep S1 values)
    ("21.65M", f"{UW_JAN:.2f}M"),
    ("8.88M",  f"{UW_FEB:.2f}M"),
    ("18.22M", f"{UW_UNB:.2f}M"),
    # DW-Non-Bank
    ("0.40M",  f"{DWNB_JAN:.2f}M"),
    ("0.08M",  f"{DWNB_FEB:.2f}M"),
    ("14.52M", f"{DWNB_UNB:.2f}M"),
    # Sub Total
    ("67.92M", f"{SUB_JAN:.2f}M"),
    ("30.12M", f"{SUB_FEB:.2f}M"),
    ("23.93M", f"{SUB_MAR:.2f}M"),
    ("82.18M", f"{SUB_UNB:.2f}M"),
    # DW Bank
    ("18.26M", f"{DWB_JAN:.2f}M"),
    ("93.94M", f"{DWB_FEB:.2f}M"),
    ("58.70M", f"{DWB_MAR:.2f}M"),
    ("81.49M", f"{DWB_UNB:.2f}M"),
    ("0.78M",  f"{DWB_SUB:.2f}M"),
]

# --- Sunlife product ranking (Slide 3 module I) from S4 block C filtered to 永明
_s4c = S4.get("C", __import__("pandas").DataFrame())
if len(_s4c) == 0 or "保司" not in _s4c.columns or "APE" not in _s4c.columns:
    _ym_top10 = []
else:
    _yongming_products = _s4c[_s4c["保司"] == "永明"].copy()
    _yongming_products["_ape"] = _yongming_products["APE"].apply(num)
    _yongming_products = _yongming_products.sort_values("_ape", ascending=False).head(10)
    _ym_top10 = _yongming_products.to_dict("records")

# SLIDE 4 — channel KPIs (exact-paragraph matching)
SLIDE4_SUBS = [
    ("31.5%", fmt_pct(FULL_RATE)),
    ("350M", f"{FULL_ISSUED_M:.0f}M"),
    ("1,113M", f"{FULL_TARGET_M:,.0f}M"),
    ("763M", f"{FULL_GAP_M:.0f}M"),
    ("533件", f"{ISSUED_CNT}件"),
    # waterfall labels (exact)
    ("−170", f"−{CH_BK['issued_m']:.0f}"),
    ("−86",  f"−{CH_YMJD['issued_m']:.0f}"),
    ("−51",  f"−{CH_THJD['issued_m']:.0f}"),
    ("−167", f"−{UNBAT_APE_M:.0f}"),
    # removed: handled by coordinate write to avoid overwriting labels
    ("592",  f"{FULL_GAP_M - UNBAT_APE_M - PEND_APE_M:.0f}"),
    ("1,113", f"{FULL_TARGET_M:,.0f}"),
    ("已达成仅 31.5%  |  剩余缺口 763M  |  需 9 个月完成 68.5%",
     f"已达成仅 {FULL_RATE:.1f}%  |  剩余缺口 {FULL_GAP_M:.0f}M  |  需 {REMAINING_M} 个月完成 {100-FULL_RATE:.1f}%"),
]

# SLIDE 5 — pipeline breakdown (per-channel stacked labels)
def _stack_label(ch):
    return f"{ch['issued_m']:.1f}▌{ch['unbat_m']:.1f}▌{ch['pend_m']:.1f}"
def _stack_pct(ch):
    tot = ch["issued_m"] + ch["unbat_m"] + ch["pend_m"]
    if tot == 0:
        return 0, 0
    return round(ch["issued_m"]/tot*100), round(ch["unbat_m"]/tot*100)

_bk_is, _bk_un = _stack_pct(CH_BK)
_ym_is, _ym_un = _stack_pct(CH_YMJD)
_th_is, _th_un = _stack_pct(CH_THJD)
_tl_is, _tl_un = _stack_pct(CH_TL)
_ic_is, _ic_un = _stack_pct(CH_ICLUB)
_cs_is, _cs_un = _stack_pct(CH_CSJB)
_hh_is, _hh_un = _stack_pct(CH_HHZJ)

# FIX 4: K 甜甜圈使用 PIPE_TOTAL_M（批核+未批核+待签，不含流失）
SLIDE5_SUBS = [
    # BK
    ("170.9▌81.5▌0.8", _stack_label(CH_BK)),
    ("合计 253.2M", f"合计 {CH_BK['total_m']:.1f}M"),
    # 永明经代
    ("86.1▌43.1▌1.5", _stack_label(CH_YMJD)),
    ("合计 124.3M", f"合计 {CH_YMJD['total_m']:.1f}M"),
    # 同行经代
    ("50.8▌21.4▌0.0", _stack_label(CH_THJD)),
    ("合计 71.7M", f"合计 {CH_THJD['total_m']:.1f}M"),
    # 天领业务
    ("23.7▌15.3▌1.6", _stack_label(CH_TL)),
    ("合计 38.1M", f"合计 {CH_TL['total_m']:.1f}M"),
    # ICLUB
    ("14.6▌1.8▌0.0", _stack_label(CH_ICLUB)),
    ("合计 18.0M", f"合计 {CH_ICLUB['total_m']:.1f}M"),
    # 成事家办
    ("2.2▌1.1▌0.6", _stack_label(CH_CSJB)),
    ("合计 3.9M",  f"合计 {CH_CSJB['total_m']:.1f}M"),
    # 合伙转介
    ("2.3▌3.3▌0.0", _stack_label(CH_HHZJ)),
    ("合计 5.6M",  f"合计 {CH_HHZJ['total_m']:.1f}M"),

    # Donut center — K 模块分母为批核+未批核+待签（PIPE_TOTAL_M，不含流失）
    ("350.4M", f"{ISSUED_APE_M:.1f}M"),
    ("533件  65.1%", f"{ISSUED_CNT}件  {ISSUED_SHARE_K:.1f}%"),
    ("67.1%  占管道总量", f"{ISSUED_SHARE_K:.1f}%  占管道总量"),
    ("管道 522.2M 中占", f"管道 {PIPE_TOTAL_M:.1f}M 中占"),
    ("533件", f"{ISSUED_CNT}件"),
    ("67.1%", f"{ISSUED_SHARE_K:.1f}%"),
    ("167.9M", f"{UNBAT_APE_M:.1f}M"),
    ("239件  31.4%", f"{UNBAT_CNT}件  {UNBAT_SHARE_K:.1f}%"),
    ("32.2%  占管道总量", f"{UNBAT_SHARE_K:.1f}%  占管道总量"),
    ("242件", f"{UNBAT_CNT}件"),
    ("32.2%", f"{UNBAT_SHARE_K:.1f}%"),
    ("3.9M", f"{PEND_APE_M:.1f}M"),
    ("12件   0.7%", f"{PEND_CNT}件   {PEND_SHARE_K:.1f}%"),
    ("0.7%  占管道总量", f"{PEND_SHARE_K:.1f}%  占管道总量"),
    ("46件", f"{PEND_CNT}件"),
    ("0.7%", f"{PEND_SHARE_K:.1f}%"),
]

# SLIDE 6 — funnel + week report
SLIDE6_SUBS = [
    # Module M funnel
    ("184.1M", f"{FUNNEL_APE['预约']:.1f}M"),
    ("429件",  f"{FUNNEL_CNT['预约']}件"),
    ("181.2M", f"{FUNNEL_APE['签单']:.1f}M"),
    ("422件",  f"{FUNNEL_CNT['签单']}件"),
    ("164.5M", f"{FUNNEL_APE['递交']:.1f}M"),
    ("414件",  f"{FUNNEL_CNT['递交']}件"),
    ("347.3M", f"{FUNNEL_APE['批核']:.1f}M"),
    ("532件",  f"{FUNNEL_CNT['批核']}件"),

    # Module O current-week report — header + values
    ("O 本周业绩快报 — W13（2026）", f"O 本周业绩快报 — {CURRENT_WEEK}（2026）"),
    ("6.0M",  f"{W_APE['预约']:.1f}M"),
    ("22件",  f"{W_CNT['预约']}件"),
    ("17.5M", f"{W_APE['签单']:.1f}M"),
    ("40件",  f"{W_CNT['签单']}件"),
    ("13.5M", f"{W_APE['批核']:.1f}M"),
    ("45件",  f"{W_CNT['批核']}件"),
    ("167.9M", f"{UNBAT_APE_M:.1f}M"),
    ("242件",  f"{UNBAT_CNT}件"),
    ("3.9M",   f"{PEND_APE_M:.1f}M"),
    ("12件",   f"{PEND_CNT}件"),
]

# SLIDE 8 — peer KPIs (top cards)
SLIDE8_SUBS = [
    ("174.8M", f"{PEER_ISSUED_M:.1f}M"),
    ("61.1M",  f"{PEER_UNBAT_M:.1f}M"),
    ("4.8M",   f"{PEER_PEND_M:.1f}M"),
    ("402件  |  件均43.5万",
     f"{PEER_ISSUED_CNT}件  |  件均{PEER_ISSUED_AVG_W:.1f}万"),
    ("105件  |",  f"{PEER_UNBAT_CNT}件  |"),
    ("11件  |",   f"{PEER_PEND_CNT}件  |"),
    ("46.5",      f"{PEER_UNBAT_AVG_W:.1f}"),
    ("43.3",      f"{PEER_PEND_AVG_W:.1f}"),
]

# SLIDE 9 — peer week + month
SLIDE9_SUBS = [
    ("Y  W13 本周快报  |  同行", f"Y  {CURRENT_WEEK} 本周快报  |  同行"),
    ("X  W01–W12 同行 预约/签单/批核 趋势（M）",
     f"X  W01–{CURRENT_WEEK} 同行 预约/签单/批核 趋势（M）"),
    ("W13预约", f"{CURRENT_WEEK}预约"),
    ("W13签单", f"{CURRENT_WEEK}签单"),
    ("W13批核", f"{CURRENT_WEEK}批核"),
    ("3.6M", f"{PEER_W_APP_M:.2f}M"),
    ("7.5M", f"{PEER_W_SGN_M:.2f}M"),
    ("10.0M", f"{PEER_W_APR_M:.2f}M"),
    ("0.11M", f"{PEER_APR_APP_M:.2f}M"),
    ("0.86M", f"{PEER_APR_SGN_M:.2f}M"),
    ("3.51M", f"{PEER_APR_APR_M:.2f}M"),
    # 同行本月 KPI cards (top-left, format "X件 | 件均Y.YW")
    ("2件 | 件均5.7W",
     f"{PEER_APR_APP_CNT}件 | 件均{_avg_w(PEER_APR_APP_M, PEER_APR_APP_CNT):.1f}W"),
    ("3件 | 件均28.6W",
     f"{PEER_APR_SGN_CNT}件 | 件均{_avg_w(PEER_APR_SGN_M, PEER_APR_SGN_CNT):.1f}W"),
    ("8件 | 件均43.8W",
     f"{PEER_APR_APR_CNT}件 | 件均{_avg_w(PEER_APR_APR_M, PEER_APR_APR_CNT):.1f}W"),
    # 同行 W weekly KPI cards (top-right, format "X件| 件均Y.YW")
    ("12件| 件均29.8W",
     f"{PEER_W_APP_CNT}件| 件均{_avg_w(PEER_W_APP_M, PEER_W_APP_CNT):.1f}W"),
    ("21件| 件均35.94W",
     f"{PEER_W_SGN_CNT}件| 件均{_avg_w(PEER_W_SGN_M, PEER_W_SGN_CNT):.1f}W"),
    ("32件| 件均31.39W",
     f"{PEER_W_APR_CNT}件| 件均{_avg_w(PEER_W_APR_M, PEER_W_APR_CNT):.1f}W"),
]

# SLIDE 10 — Bank overview top cards + April KPIs
# Note: we cannot use "0.0M" as a key (it appears many times), so we use the
# exact KPI-card paragraph text which is more specific.
SLIDE10_SUBS = [
    # Top cards — full-paragraph rules
    ("170.9M", f"{BK_ISSUED_M:.1f}M"),
    ("134件 | 达成率85.4%", f"{BK_ISSUED_CNT}件 | 达成率{BK_RATE:.1f}%"),
    ("81.5M", f"{BK_UNBAT_M:.1f}M"),
    ("66件 |件均123.4W", f"{BK_UNBAT_CNT}件 |件均{BK_UNBAT_AVG_W:.1f}W"),
    ("0.78M", f"{BK_PEND_M:.2f}M"),
    ("2件 | 件均39W", f"{BK_PEND_CNT}件 | 件均{BK_PEND_AVG_W:.0f}W"),
    # April "本月" cards
    ("0件| 件均0W", f"{BK_APR_APP_CNT}件| 件均{_avg_w(BK_APR_APP_M, BK_APR_APP_CNT):.0f}W"),
    ("3件| 件均52W", f"{BK_APR_SGN_CNT}件| 件均{_avg_w(BK_APR_SGN_M, BK_APR_SGN_CNT):.0f}W"),
    ("0件 | 件均0W", f"{BK_APR_APR_CNT}件 | 件均{_avg_w(BK_APR_APR_M, BK_APR_APR_CNT):.0f}W"),
    ("1.56M", f"{BK_APR_SGN_M:.2f}M"),
    # donut center percentages
    ("15%", f"{100-BK_RATE:.0f}%"),
    ("85%", f"{BK_RATE:.0f}%"),
    # right-side mini KPIs
    ("142.1M", f"{to_m(safe_cell(_o, 'KEY ACCOUNT', '民生银行', '2026批核APE')):.1f}M"),
    ("28.8M",  f"{to_m(safe_cell(_o, 'KEY ACCOUNT', '平安银行', '2026批核APE')):.1f}M"),
    ("121件", f"{int(num(safe_cell(_o, 'KEY ACCOUNT', '民生银行', '批核件数')))}件"),
    ("13件", f"{int(num(safe_cell(_o, 'KEY ACCOUNT', '平安银行', '批核件数')))}件"),
    ("29.1M", f"{200 - BK_ISSUED_M:.1f}M"),
]

# SLIDE 11 — BK current week
SLIDE11_SUBS = [
    ("W13", CURRENT_WEEK),
    ("AB  W01–W13 银行 预约/签单/批核  APE趋势（M）",
     f"AB  W01–{CURRENT_WEEK} 银行 预约/签单/批核  APE趋势（M）"),
    ("AC W13 银行 KA 本周业绩详情（M）",
     f"AC {CURRENT_WEEK} 银行 KA 本周业绩详情（M）"),
    # Current week KPI-card values (exact)
    ("3.51M", f"{BK_W_SGN_M:.2f}M"),
    ("1.79M", f"{BK_W_APR_M:.2f}M"),
    ("6件", f"{BK_W_SGN_CNT}件"),
    ("58.5W", f"{_avg_w(BK_W_SGN_M, BK_W_SGN_CNT):.1f}W"),
    ("3件", f"{BK_W_APR_CNT}件"),
    ("59.8W", f"{_avg_w(BK_W_APR_M, BK_W_APR_CNT):.1f}W"),
    # KA table (民生/平安) weekly rows — these are exact cell texts
]


SLIDE1_SUBS += [
    # Top box "已批 350M / 剩余缺口 763M"
    (f"已批 350M / 剩余缺口 763M",
     f"已批 {FULL_ISSUED_M:.0f}M / 剩余缺口 {FULL_GAP_M:.0f}M"),
    # Yongming progress bar (note: no space between 缺口 and number in source)
    ("已批 297M / 剩余缺口679M",
     f"已批 {SUN_ISSUED_M:.0f}M / 剩余缺口 {SUN_GAP_M:.0f}M"),
    # So-What narrative refreshes
    ("未批核（167.9M，242 件）与待签（3.9M，12 件）合计 171.8M 在管道中，占批核 APE 的 49%。未批核融资占比 16.7% 为最大风险敞口，若能快速推进至生效，可直接拉升达成率逾 15 个百分点。",
     f"未批核（{UNBAT_APE_M:.1f}M，{UNBAT_CNT} 件）与待签（{PEND_APE_M:.1f}M，{PEND_CNT} 件）合计 {UNBAT_APE_M+PEND_APE_M:.1f}M 在管道中，占批核 APE 的 {(UNBAT_APE_M+PEND_APE_M)/ISSUED_APE_M*100:.0f}%。若能快速推进至生效，可直接拉升达成率逾 {(UNBAT_APE_M+PEND_APE_M)/FULL_TARGET_M*100:.0f} 个百分点。"),
]

SLIDE2_SUBS += [
    ("含4月初达 354.5M（达成率 31.8%），完成全年目标 1,113M 还需约 763M（剩余8个月月均需 95.3M）。4月 W13 批核 13.5M 节后回暖；若 4–12 月维持 80–100M 节奏，全年可达标。",
     f"截至 {CURRENT_WEEK}，已批核 {ISSUED_APE_M:.1f}M（达成率 {FULL_RATE:.1f}%），完成全年目标 {FULL_TARGET_M:,.0f}M 还需约 {FULL_GAP_M:.0f}M（剩余 {REMAINING_M} 个月月均需 {PACE_LINE}M）。若 {CURRENT_MONTH}–12 月维持 80–100M 节奏，全年可达标。"),
]

SLIDE3_SUBS += [
    # 永明 待签 single value (Text 22)
    ("3.9M", f"{SUN_PEND_M:.1f}M"),
    # JF row all values (exact)
    ("45.86M", f"{JF_JAN:.2f}M"),
    ("14.90M", f"{JF_FEB:.2f}M"),
    ("15.05M", f"{JF_MAR:.2f}M"),
    ("49.44M", f"{JF_UNB:.2f}M"),
    # UNIWIN
    ("21.65M", f"{UW_JAN:.2f}M"),
    ("15.15M", f"{UW_FEB:.2f}M"),
    # Sub Total
    ("67.92M", f"{SUB_JAN:.2f}M"),
    ("30.12M", f"{SUB_FEB:.2f}M"),
    ("23.93M", f"{SUB_MAR:.2f}M"),
    ("82.18M", f"{SUB_UNB:.2f}M"),
    # DW Bank
    ("18.26M", f"{DWB_JAN:.2f}M"),
    ("93.94M", f"{DWB_FEB:.2f}M"),
    ("58.70M", f"{DWB_MAR:.2f}M"),
    ("81.49M", f"{DWB_UNB:.2f}M"),
]

SLIDE4_SUBS += [
    # Waterfall: -2 for 成事/合伙 (both ~2M, keep same)
    # So-what refreshes
    ("BK贡献最大批核（170.9M），但仍距目标29M。全部已批核+在途（522M）仍距目标591M。如未批核（167.9M）和待签（3.9M）能快速推进，可直接减少缺口约31%，是最快的短期行动杠杆。",
     f"BK贡献最大批核（{CH_BK['issued_m']:.1f}M），已超目标 {CH_BK['issued_m']-CH_BK['target_m']:.0f}M。全部已批核+在途（{ISSUED_APE_M+UNBAT_APE_M+PEND_APE_M:.0f}M）仍距目标 {FULL_TARGET_M-ISSUED_APE_M-UNBAT_APE_M-PEND_APE_M:.0f}M。如未批核（{UNBAT_APE_M:.1f}M）和待签（{PEND_APE_M:.1f}M）能快速推进，可直接减少缺口约 {(UNBAT_APE_M+PEND_APE_M)/FULL_GAP_M*100:.0f}%，是最快的短期行动杠杆。"),
]

SLIDE5_SUBS += [
    # FIX 4: So-What 文案中管道总值使用 K 分母（不含流失）
    ("管道总值522.2M中，批核占67.1%（350.4M）。剩余171.8M（未批167.9M+待签3.9M）若转化可直接推高达成率15%+。",
     f"管道总值 {PIPE_TOTAL_M:.1f}M 中，批核占 {ISSUED_SHARE_K:.1f}%（{ISSUED_APE_M:.1f}M）。剩余 {UNBAT_APE_M+PEND_APE_M:.1f}M（未批 {UNBAT_APE_M:.1f}M+待签 {PEND_APE_M:.1f}M）若转化可直接推高达成率 {(UNBAT_APE_M+PEND_APE_M)/FULL_TARGET_M*100:.0f}%+。"),
    ("BK业务批核170.9M逼近目标（200M），达成率85.4%。永明经代目标最大（340M）但实际仅86.1M，是最大绝对缺口（253.9M）。合伙转介与IFA批核几乎为零，战略价值存疑。",
     f"BK业务批核 {CH_BK['issued_m']:.1f}M 已超目标（200M），达成率 {CH_BK['rate']:.1f}%。永明经代目标最大（340M）但实际仅 {CH_YMJD['issued_m']:.1f}M，是最大绝对缺口（{340 - CH_YMJD['issued_m'] - CH_YMJD['unbat_m'] - CH_YMJD['pend_m']:.0f}M）。合伙转介与IFA批核几乎为零，战略价值存疑。"),
]

SLIDE6_SUBS += [
    (f"W13（4月初）预约6.0M/22件，为节后正常低位；签单17.5M/40件仍强劲，递交39.7M/90件创单周新高——大量3月签单件正集中递交；批核13.5M/45件恢复正常。未批核167.9M（242件）是Q2批核的核心转化库存。",
     f"{CURRENT_WEEK} 预约 {W_APE['预约']:.1f}M/{W_CNT['预约']}件；签单 {W_APE['签单']:.1f}M/{W_CNT['签单']}件；递交 {W_APE['递交']:.1f}M/{W_CNT['递交']}件；批核 {W_APE['批核']:.1f}M/{W_CNT['批核']}件。未批核 {UNBAT_APE_M:.1f}M（{UNBAT_CNT}件）是 Q2 批核的核心转化库存。"),
]

SLIDE10_SUBS += [
    # Split-run paragraph under 批核 card
    ("134件 | 达成率85.4%", f"{BK_ISSUED_CNT}件 | 达成率{BK_RATE:.1f}%"),
    ("达成率 85.4%", f"达成率 {BK_RATE:.1f}%"),
    # So-what
    ("Q1批核170.9M达成85.4%；未批核81.5M构成Q2储量；本月签单1.56M偏低，需修复预约动能",
     f"YTD 批核 {BK_ISSUED_M:.1f}M 达成 {BK_RATE:.1f}%；未批核 {BK_UNBAT_M:.1f}M 构成 Q2 储量；本月签单 {BK_APR_SGN_M:.2f}M，需修复预约动能"),
    # 民生 批核 mini-KPI 143.7M (also appears as '143.7' in other charts but full para match is fine)
]

SLIDE11_SUBS += [
    ("银行W13：民生签单2.73M/批核1.79M，预约归零（节后假期影响）；平安签单0.78M，批核零产出。W13递交39.7M（含大量3月积压件）是Q2批核的最大利好信号，预计未来2-4周内将集中释放批核。",
     f"银行 {CURRENT_WEEK}：民生 + 平安合计 签单 {BK_W_SGN_M:.2f}M/{BK_W_SGN_CNT}件、批核 {BK_W_APR_M:.2f}M/{BK_W_APR_CNT}件、预约 {BK_W_APP_M:.2f}M/{BK_W_APP_CNT}件。未批核 {BK_UNBAT_M:.1f}M（{BK_UNBAT_CNT}件）是 Q2 批核的核心储量。"),
]
def _para_text(p):
    return "".join(r.text for r in p.runs)

def _set_para_text(p, new_text):
    if not p.runs:
        return
    # put whole new text in first run, clear the rest
    p.runs[0].text = new_text
    for r in p.runs[1:]:
        r.text = ""

def apply_substitutions(slide, subs, tag=""):
    """Paragraph-level EXACT match replacement.
    Each sub is (old_paragraph_text, new_paragraph_text). The paragraph's
    concatenated run text must exactly equal `old` (ignoring leading/trailing
    whitespace). This avoids substring collisions.
    """
    sub_map = {old.strip(): new for old, new in subs if old}
    hits = 0
    misses = set(sub_map.keys())

    def _process_paragraphs(paragraphs):
        nonlocal hits
        for para in paragraphs:
            text = _para_text(para)
            key = text.strip()
            if not key:
                continue
            if key in sub_map:
                _set_para_text(para, sub_map[key])
                hits += 1
                misses.discard(key)

    for shape in slide.shapes:
        if shape.has_text_frame:
            _process_paragraphs(shape.text_frame.paragraphs)
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    _process_paragraphs(cell.text_frame.paragraphs)
    print(f"  [{tag}] {hits} subs applied  ({len(misses)} rules unused)")


def set_shape_text(slide, shape_name, new_text):
    """Directly replace all text of a named shape with new_text."""
    for shp in slide.shapes:
        if shp.name == shape_name and shp.has_text_frame:
            tf = shp.text_frame
            if tf.paragraphs and tf.paragraphs[0].runs:
                tf.paragraphs[0].runs[0].text = new_text
                for r in tf.paragraphs[0].runs[1:]:
                    r.text = ""
                # clear extra paragraphs
                for p in tf.paragraphs[1:]:
                    for r in p.runs:
                        r.text = ""
            return True
    return False


def clone_column_right(slide, src_col_left, tol=30000, x_offset=390000):
    """
    Clone every shape whose left ≈ src_col_left by x_offset.
    Returns the list of newly created shape elements along with their
    original source shapes (src, clone) for further editing.
    """
    from copy import deepcopy
    from lxml import etree
    spTree = slide.shapes._spTree
    src_shapes = []
    for shp in slide.shapes:
        if shp.left is None:
            continue
        if abs(shp.left - src_col_left) <= tol:
            src_shapes.append(shp)
    created = []
    for src in src_shapes:
        sp_xml = src._element
        new_xml = deepcopy(sp_xml)
        # Shift horizontal offset of <a:off x="..."/>
        ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
        for off in new_xml.iter(f"{{{ns_a}}}off"):
            try:
                x = int(off.get("x"))
                off.set("x", str(x + x_offset))
            except (TypeError, ValueError):
                pass
        # Append to shape tree
        spTree.append(new_xml)
        created.append((src, new_xml))
    return created


def set_shape_text_xml(sp_element, new_text):
    """Rewrite the text content of a cloned <p:sp> XML element."""
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    # Find first <a:t>
    t_elems = list(sp_element.iter(f"{{{ns_a}}}t"))
    if not t_elems:
        return False
    t_elems[0].text = new_text
    # Clear additional <a:t> in same paragraph
    for extra in t_elems[1:]:
        extra.text = ""
    return True


def set_shape_text_at(slide, left, top, new_text, tol=50000):
    """Find a text shape near (left, top) EMU coords and replace its text.
    Handles shapes with empty runs by creating a new run via lxml.
    Returns True if shape was found (even if text was empty before).
    """
    best = None
    best_dist = None
    for shp in slide.shapes:
        if not shp.has_text_frame:
            continue
        if shp.left is None or shp.top is None:
            continue
        dx = abs(shp.left - left)
        dy = abs(shp.top - top)
        if dx > tol or dy > tol:
            continue
        d = dx + dy
        if best is None or d < best_dist:
            best = shp
            best_dist = d
    if best is None:
        return False
    tf = best.text_frame
    if tf.paragraphs and tf.paragraphs[0].runs:
        # Normal case: runs exist, just update text
        tf.paragraphs[0].runs[0].text = new_text
        for r in tf.paragraphs[0].runs[1:]:
            r.text = ""
        for p in tf.paragraphs[1:]:
            for r in p.runs:
                r.text = ""
    else:
        # Runs are empty (previously cleared or never set): add a run via lxml
        try:
            from lxml import etree as _et_ssat
            NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
            txBody = tf._txBody
            # Get first paragraph, or create one
            p_els = txBody.findall(f"{{{NS_A}}}p")
            if not p_els:
                p_el = _et_ssat.SubElement(txBody, f"{{{NS_A}}}p")
            else:
                p_el = p_els[0]
                # Clear any empty runs/text in other paragraphs
                for extra_p in p_els[1:]:
                    for r in extra_p.findall(f"{{{NS_A}}}r"):
                        t = r.find(f"{{{NS_A}}}t")
                        if t is not None: t.text = ""
            # Add a new run with the text
            r_el = _et_ssat.SubElement(p_el, f"{{{NS_A}}}r")
            t_el = _et_ssat.SubElement(r_el, f"{{{NS_A}}}t")
            t_el.text = new_text
        except Exception:
            pass  # silently ignore if lxml fails
    return True

print("\n--- TEXT UPDATES ---")
apply_substitutions(_s(0),        SLIDE1_SUBS, "Slide 1")   # 全维度业绩分析仪表盘
apply_substitutions(_SL_FORECAST, SLIDE2_SUBS, "Slide 2")   # F批核路径管控
apply_substitutions(_SL_SUNLIFE,  SLIDE3_SUBS, "Slide 3")   # 永明业绩汇报
apply_substitutions(_SL_BUBBLE,   SLIDE4_SUBS, "Slide 4")   # G气泡+H瀑布
apply_substitutions(slides[4], SLIDE5_SUBS, "Slide 5")
apply_substitutions(slides[5], SLIDE6_SUBS, "Slide 6")
apply_substitutions(_s(7), SLIDE8_SUBS, "Slide 8")
apply_substitutions(_s(8), SLIDE9_SUBS, "Slide 9")
apply_substitutions(_s(9), SLIDE10_SUBS, "Slide 10")
apply_substitutions(_s(10), SLIDE11_SUBS, "Slide 11")

# ── F图 达标节奏线 & 最低月底线 位置动态调整 ─────────────────────────────────
# 节奏线文字标注的y坐标需要随PACE_LINE/MIN_LINE的数值变化而移动
# 比例：图表y轴每1M对应约99859 EMU（由两条线之间的坐标差推算）
# 基准：PACE_LINE=75.7M → Text 66 top=2645410 (从原始模板测量)
#       MIN_LINE=69.5M  → Text 68 top=3264535
_PACE_EMU_PER_M = 99859          # EMU per 1M on F chart y-axis
_PACE_REF_M     = 75.7           # 基准PACE_LINE值（对应下面的基准坐标）
_PACE_REF_TOP   = 2645410        # 基准top坐标（对应75.7M时）
_MIN_REF_M      = 69.5           # 基准MIN_LINE值
_MIN_REF_TOP    = 3264535        # 基准top坐标（对应69.5M时）

def _move_line_label(slide, shape_name_hint, ref_top, ref_m, new_m, emuPerM,
                     left_tol=200000):
    """找节奏线/底线的文字标注形状，根据新数值移动其top坐标。"""
    for sh in slide.shapes:
        if not sh.has_text_frame or sh.top is None: continue
        if abs(sh.top - ref_top) > 300000: continue   # 在基准附近
        txt = "".join(r.text for p in sh.text_frame.paragraphs for r in p.runs)
        if not txt: continue
        new_top = int(ref_top + (ref_m - new_m) * emuPerM)
        sh.top = new_top

_move_line_label(_SL_FORECAST, "节奏线", _PACE_REF_TOP, _PACE_REF_M, PACE_LINE, _PACE_EMU_PER_M)
_move_line_label(_SL_FORECAST, "底线",   _MIN_REF_TOP,  _MIN_REF_M,  MIN_LINE,  _PACE_EMU_PER_M)
print(f"  [F图] 节奏线 {PACE_LINE}M → top={int(_PACE_REF_TOP + (_PACE_REF_M - PACE_LINE) * _PACE_EMU_PER_M)}")
print(f"  [F图] 底线   {MIN_LINE}M → top={int(_MIN_REF_TOP  + (_MIN_REF_M  - MIN_LINE)  * _PACE_EMU_PER_M)}")

# --- Shape-targeted updates for paragraphs that can't use exact-match (duplicates) ---
print("\n--- SHAPE-TARGETED UPDATES ---")

# Slide 7: week header shapes T6012, T7012, T8012 = current week
# (T6011/T7011/T8011 = previous week). We leave the previous-week headers
# alone since the matrix is historical; only the rightmost W13 column header
# needs updating to W14 when week advances.
set_shape_text(_s(6), "T6012", CURRENT_WEEK)
set_shape_text(_s(6), "T7012", CURRENT_WEEK)
set_shape_text(_s(6), "T8012", CURRENT_WEEK)

# Slide 9: peer current-week card headers
set_shape_text(_s(8), "Text 44", f"同行{CURRENT_WEEK}预约")
set_shape_text(_s(8), "Text 49", f"同行{CURRENT_WEEK}签单")
set_shape_text(_s(8), "Text 54", f"同行{CURRENT_WEEK}批核")

# Slide 10: BK 本月 cards (these have duplicate "0.0M" text)
# From the inventory:
#   Text 22 = BK 本月预约 value    (April appointment)
#   Text 27 = BK 本月签单 value    (handled by 1.56M rule)
#   Text 32 = BK 本月批核 value    (April approved)
set_shape_text(_s(9), "Text 22", f"{BK_APR_APP_M:.2f}M")
set_shape_text(_s(9), "Text 32", f"{BK_APR_APR_M:.2f}M")

# --- Slide 5: Channel donut percentages (issued%/unbat%) ---
# Each channel has 1-2 percentage shapes at fixed (y, x) positions.
# Use shape-targeted update to avoid paragraph-text collisions across rows.
_S5_DONUT_MAP = {
    # y_position → (channel_dict, has_unbat)
    2055876: (CH_ICLUB, False),  # ICLUB — issued% only (single donut)
    2654173: (CH_THJD,  True),   # 同行经代
    3237230: (CH_CSJB,  True),   # 成事家办
    3881374: (CH_HHZJ,  True),   # 合伙转介业务
    4509770: (CH_BK,    True),   # BK业务
    5131562: (CH_TL,    True),   # 天领业务
    5735574: (CH_YMJD,  True),   # 永明经代
}

def _set_text_at(slide, target_y, target_x, new_text, x_tol=80000, y_tol=20000):
    for sh in slide.shapes:
        if not sh.has_text_frame: continue
        if sh.top is None or sh.left is None: continue
        if abs(sh.top - target_y) < y_tol and abs(sh.left - target_x) < x_tol:
            tf = sh.text_frame
            if tf.paragraphs and tf.paragraphs[0].runs:
                tf.paragraphs[0].runs[0].text = new_text
                for r in tf.paragraphs[0].runs[1:]:
                    r.text = ""
            return True
    return False

for y_pos, (ch, has_unbat) in _S5_DONUT_MAP.items():
    issued_m = ch['issued_m']
    unbat_m  = ch['unbat_m']
    pend_m   = ch['pend_m']
    tot = issued_m + unbat_m + pend_m
    if tot == 0:
        continue
    issued_pct = round(issued_m / tot * 100)
    unbat_pct  = round(unbat_m  / tot * 100)
    # issued% always at x=1616456
    _set_text_at(slides[4], y_pos, 1616456, f"{issued_pct}%")
    # unbat% column — varies in x (2592692, 2595912, 2653916, 2668155, 2688406, 2075658)
    # Find by y only: within same row, the second %-shape with x>2000000 is unbat
    if has_unbat:
        for sh in slides[4].shapes:
            if not sh.has_text_frame: continue
            if sh.top is None or sh.left is None: continue
            if abs(sh.top - y_pos) < 20000 and 2_000_000 < sh.left < 2_800_000:
                t = sh.text_frame.text.strip()
                if t.endswith('%') and len(t) < 6:
                    tf = sh.text_frame
                    if tf.paragraphs and tf.paragraphs[0].runs:
                        tf.paragraphs[0].runs[0].text = f"{unbat_pct}%"
                        for r in tf.paragraphs[0].runs[1:]:
                            r.text = ""
                    break

# ======================================================================
# Dynamic 环比 labels — WoW for O quick report + E chart MoM annotations
# + M chart alert box
# ======================================================================

def _wow_pct(cur, prev):
    """Week-over-week % change."""
    if prev == 0: return 0.0
    return (cur / prev - 1) * 100

def _set_shape_text_color(slide, shape_name, text, rgb):
    """Set text and font color of a named shape."""
    for sh in slide.shapes:
        if sh.name == shape_name and sh.has_text_frame:
            tf = sh.text_frame
            if tf.paragraphs and tf.paragraphs[0].runs:
                tf.paragraphs[0].runs[0].text = text
                tf.paragraphs[0].runs[0].font.color.rgb = rgb
                for r in tf.paragraphs[0].runs[1:]:
                    r.text = ""
            return True
    return False

def _arrow_text(pct):
    """▲ for positive, ▼ for negative, with formatted %."""
    if pct >= 0:
        return f"▲ 环比+{pct:.1f}%"
    else:
        return f"▼ 环比{pct:.1f}%"

def _arrow_color(pct):
    """Green for positive, Red for negative."""
    GREEN = RGBColor(0x1A, 0x7A, 0x3F)
    RED   = RGBColor(0xC0, 0x39, 0x2B)
    return GREEN if pct >= 0 else RED

# --- Week column indices for prev/current ---
_prev_week_col = PREV_WEEK_COL  # use pre-computed module-level var

# --- Issue 1: M chart red alert box ---
# Dynamically find the week with min appointment APE and generate alert
# If min is current or prev week (recent), show alert; otherwise delete
_appt_ape = S3['A-APE']
_appt_row = _appt_ape[_appt_ape['阶段'] == '预约'].iloc[0]
_week_cols_all = [c for c in _appt_ape.columns if c.startswith('2026W')]
_min_week, _min_val = None, float('inf')
for w in _week_cols_all:
    v = num(_appt_row[w])
    if 0 < v < _min_val:
        _min_val = v
        _min_week = w

# Delete the M chart red alert box — it's hardcoded and misleading
# User requested: if can't be dynamic, delete it. We'll make it dynamic instead.
if _min_week and _min_val < 5_000_000:  # threshold: < 5M is alert-worthy
    _min_w_label = _min_week.replace('2026', '')
    _alert_text = f"▲ {_min_w_label}预约仅{_min_val/1e6:.1f}M — 断崖式下跌，需复盘执行断层原因"
    _set_shape_text_color(slides[5], "Text 27", _alert_text, RGBColor(0xC0, 0x39, 0x2B))
else:
    # No alert needed — clear the text
    _set_shape_text_color(slides[5], "Text 27", "", RGBColor(0xC0, 0x39, 0x2B))

# --- Issue 2: O 本周快报 status column ---
# 预约 WoW
_prev_app_ape = num(_appt_row.get(_prev_week_col, 0))
_cur_app_ape  = W_APE['预约'] * 1e6  # W_APE is in M
_wow_app = _wow_pct(_cur_app_ape, _prev_app_ape)
_set_shape_text_color(slides[5], "Text 52", _arrow_text(_wow_app), _arrow_color(_wow_app))

# 签单 WoW
_sign_ape = S3['A-APE']
_sign_row = _sign_ape[_sign_ape['阶段'] == '签单'].iloc[0]
_prev_sgn = num(_sign_row.get(_prev_week_col, 0))
_cur_sgn  = W_APE['签单'] * 1e6
_wow_sgn = _wow_pct(_cur_sgn, _prev_sgn)
_set_shape_text_color(slides[5], "Text 58", _arrow_text(_wow_sgn), _arrow_color(_wow_sgn))

# 批核 WoW
_apr_ape = S3['A-APE']
_apr_row = _apr_ape[_apr_ape['阶段'] == '批核'].iloc[0]
_prev_apr = num(_apr_row.get(_prev_week_col, 0))
_cur_apr  = W_APE['批核'] * 1e6
_wow_apr = _wow_pct(_cur_apr, _prev_apr)
_set_shape_text_color(slides[5], "Text 64", _arrow_text(_wow_apr), _arrow_color(_wow_apr))

# 未批核 and 待签 status rows — keep as-is (static labels)
# Text 70 = "⚠ 待转化优先", Text 76 = "→ 尽快推进"

# --- Issue 3: E chart 环比 annotations (Slide 2) ---
_E_CHART_NAMES = {'Chart_YY': '预约', 'Chart_QD': '签单', 'Chart_PH': '批核'}
_ANN_NAMES = {'预约': 'Ann_YY', '签单': 'Ann_QD', '批核': 'Ann_PH'}

# Find each chart's bounding box
_e_chart_info = {}
for sh in _SL_BIZ_VIEW.shapes:
    if sh.has_chart and sh.name in _E_CHART_NAMES:
        stage = _E_CHART_NAMES[sh.name]
        cats = list(sh.chart.plots[0].categories) if sh.chart.plots else []
        _e_chart_info[stage] = {
            'top': sh.top, 'height': sh.height,
            'left': sh.left, 'width': sh.width,
            'months': cats,
            'n_bars': len(cats),
        }

# ── Update Ann shapes by name (robust: no yband dependency) ─────────────
# Each stage has 3 Ann shapes sorted top→bottom = most-recent→oldest MoM
def _update_ann_shapes(slide, stage, s1_block):
    ann_name = _ANN_NAMES[stage]
    ann_shs = sorted(
        [sh for sh in slide.shapes if sh.name == ann_name and sh.has_text_frame],
        key=lambda s: s.top
    )
    # build mom list from S1 block: 2026 months with env 环比增长%
    df = S1[s1_block]
    mom_vals = []
    for _, r in df.iterrows():
        m = str(r.iloc[0]).strip()
        if not m.startswith('2026'):
            continue
        try:
            month_num = int(m.split('-')[1])
        except (ValueError, IndexError):
            continue
        if month_num < 2:
            continue
        pct_str = str(r.get('环比增长%', '')).strip().replace('%', '')
        if not pct_str:
            continue
        try:
            pct = float(pct_str)
            mom_vals.append((month_num, pct))
        except ValueError:
            continue
    # sort descending by month (most recent first → top ann shape)
    mom_vals.sort(key=lambda x: -x[0])
    GREEN = RGBColor(0x1A, 0x7A, 0x3F)
    RED   = RGBColor(0xC0, 0x39, 0x2B)
    # Clone additional shapes if we have more months than existing Ann shapes
    from copy import deepcopy as _ann_dc
    if len(mom_vals) > len(ann_shs) and ann_shs:
        _spTree = slide.shapes._spTree
        for _ in range(len(mom_vals) - len(ann_shs)):
            _new_el = _ann_dc(ann_shs[0]._element)
            _spTree.append(_new_el)
        ann_shs = sorted(
            [sh for sh in slide.shapes if sh.name == ann_name and sh.has_text_frame],
            key=lambda s: s.top
        )
    for i, sh in enumerate(ann_shs):
        tf = sh.text_frame
        if not tf.paragraphs or not tf.paragraphs[0].runs:
            continue
        if i < len(mom_vals):
            month_num, pct = mom_vals[i]
            arrow = '▲' if pct >= 0 else '▼'
            new_text = f"{arrow} 环比 {pct:+.1f}%"
            color = GREEN if pct >= 0 else RED
            tf.paragraphs[0].runs[0].text = new_text
            tf.paragraphs[0].runs[0].font.color.rgb = color
            for r in tf.paragraphs[0].runs[1:]:
                r.text = ""
        else:
            tf.paragraphs[0].runs[0].text = ""
            for r in tf.paragraphs[0].runs[1:]:
                r.text = ""
    print(f"  [Ann] {stage}: {len(mom_vals)} mom vals → {len(ann_shs)} shapes")

_update_ann_shapes(_SL_BIZ_VIEW, '预约', 'C')
_update_ann_shapes(_SL_BIZ_VIEW, '签单', 'D')
_update_ann_shapes(_SL_BIZ_VIEW, '批核', 'E')

def _bar_y_top(stage, month_num):
    info = _e_chart_info.get(stage)
    if not info: return None
    plot_top = info['top'] + Emu(120000)
    plot_bottom = info['top'] + info['height'] - Emu(280000)
    plot_h = plot_bottom - plot_top
    bar_h = plot_h / info['n_bars']

    months = info['months']
    target_str = f"{month_num}月"
    prev_str = f"{month_num - 1}月"
    if target_str not in months or prev_str not in months:
        if target_str not in months:
            return None
        months_tb = list(reversed(months))
        bar_idx = months_tb.index(target_str)
        return int(plot_top + bar_h * bar_idx + bar_h * 0.5)

    months_tb = list(reversed(months))
    cur_idx = months_tb.index(target_str)
    prev_idx = months_tb.index(prev_str)
    cur_y_center = plot_top + bar_h * cur_idx + bar_h * 0.5
    prev_y_center = plot_top + bar_h * prev_idx + bar_h * 0.5
    return int((cur_y_center + prev_y_center) / 2)

_e_mom_values = {}
for s1_key, stage in [('C', '预约'), ('D', '签单'), ('E', '批核')]:
    df = S1[s1_key]
    mom_list = []
    for _, r in df.iterrows():
        m = str(r.iloc[0]).strip()
        if not m.startswith('2026'):
            continue
        try:
            month_num = int(m.split('-')[1])
        except (ValueError, IndexError):
            continue
        if month_num < 2:
            continue
        pct_str = str(r.get('环比增长%', '')).strip().replace('%', '')
        if pct_str:
            try:
                pct = float(pct_str)
                mom_list.append((month_num, pct))
            except ValueError:
                continue
    _e_mom_values[stage] = mom_list

_E_COLORS = {
    '预约': RGBColor(0x92, 0x2B, 0x21),
    '签单': RGBColor(0xC8, 0x89, 0x0A),
    '批核': RGBColor(0x1A, 0x6B, 0x3A),
}

_E_YBANDS = {'预约': (560000, 2200000), '签单': (2400000, 4000000), '批核': (4400000, 6000000)}

for stage, mom_vals in _e_mom_values.items():
    info = _e_chart_info.get(stage)
    if not info: continue

    yband = _E_YBANDS[stage]
    existing = []
    for sh in _SL_BIZ_VIEW.shapes:
        if sh.has_text_frame and sh.top and yband[0] <= sh.top <= yband[1]:
            txt = sh.text_frame.text.strip()
            if '环比' in txt:
                existing.append(sh)
    existing.sort(key=lambda s: s.top)

    needed = len(mom_vals)
    available = len(existing)

    if needed > available and existing:
        from copy import deepcopy
        spTree = _SL_BIZ_VIEW.shapes._spTree
        template_sh = existing[0]
        for _ in range(needed - available):
            new_el = deepcopy(template_sh._element)
            spTree.append(new_el)
        existing = []
        for sh in _SL_BIZ_VIEW.shapes:
            if sh.has_text_frame and sh.top and yband[0] <= sh.top <= yband[1]:
                txt = sh.text_frame.text.strip()
                if '环比' in txt:
                    existing.append(sh)

    sorted_mom = sorted(mom_vals, key=lambda x: -x[0])

    for i, sh in enumerate(existing):
        if i < len(sorted_mom):
            month_num, pct = sorted_mom[i]
            bar_y = _bar_y_top(stage, month_num)
            if bar_y is not None:
                sh.top = bar_y - sh.height // 2

            arrow = '▲' if pct >= 0 else '▼'
            new_text = f"{arrow} 环比 {pct:+.1f}%"
            new_color = _E_COLORS[stage]

            if sh.text_frame.paragraphs and sh.text_frame.paragraphs[0].runs:
                sh.text_frame.paragraphs[0].runs[0].text = new_text
                sh.text_frame.paragraphs[0].runs[0].font.color.rgb = new_color
                for r in sh.text_frame.paragraphs[0].runs[1:]:
                    r.text = ""
        else:
            if sh.text_frame.paragraphs and sh.text_frame.paragraphs[0].runs:
                sh.text_frame.paragraphs[0].runs[0].text = ""
                for r in sh.text_frame.paragraphs[0].runs[1:]:
                    r.text = ""

# ------------------------------------------------------------------------
# Slide 7: Q/R/S 热力矩阵 — clone W13 column → W14, then fill with S3 data
# ------------------------------------------------------------------------
from heatmatrix_cloner import _clone_column, remove_cloned_columns

# Matrix descriptors
# Each tuple: (prefixes, w13_header_left, top_range, matrix_tag)
MATRICES = [
    (('T7','R7'), 5371168, (800000,  3800000), 'Q'),   # 预约  (top-left)
    (('T8','R8'), 11446941,(800000,  3800000), 'R'),   # 签单  (top-right)
    (('T6','R6'), 5339384, (3900000, 6200000), 'S'),   # 批核  (bottom-left)
]

_s7 = _s(6)

# Step 1: idempotent cleanup — remove any _W14 clones from previous runs
for prefixes, *_ in MATRICES:
    remove_cloned_columns(_s7, prefixes, suffix='_W14')

# Step 2: clone W13 column → W14 for each matrix
COLUMN_GAP = 390000
for prefixes, anchor, top_rng, tag in MATRICES:
    _clone_column(_s7, anchor_left=anchor, column_gap=COLUMN_GAP,
                  name_prefixes=prefixes, top_range=top_rng)

# Step 3: populate data
def _scan_column_cells(slide, anchor_left, prefixes, top_range):
    cells = []
    for shp in slide.shapes:
        if shp.left is None or shp.top is None: continue
        if abs(shp.left - anchor_left) > 10000: continue
        if not (top_range[0] <= shp.top <= top_range[1]): continue
        if not any(shp.name.startswith(p) for p in prefixes): continue
        if not shp.name.startswith(('T6','T7','T8')): continue  # text only
        if not shp.has_text_frame: continue
        t = "".join(r.text for p in shp.text_frame.paragraphs for r in p.runs).strip()
        cells.append((shp.top, shp.name, t, shp.height))
    cells.sort()
    return cells

def _matrix_data_rows(s3_ape_block, s3_cnt_block):
    df_ape = S3[s3_ape_block]
    df_cnt = S3[s3_cnt_block]
    week_cols = [c for c in df_ape.columns if c.startswith('2026W')]
    rows = []
    for _, r_ape in df_ape.iterrows():
        name = r_ape.iloc[0]
        if name == '合计' or not name: continue
        r_cnt = df_cnt[df_cnt.iloc[:,0] == name]
        if not len(r_cnt): continue
        r_cnt = r_cnt.iloc[0]
        apes = [num(r_ape[c])/1e6 for c in week_cols]
        cnts = [int(num(r_cnt[c])) for c in week_cols]
        rows.append((name, apes, cnts))
    tot_ape = df_ape[df_ape.iloc[:,0]=='合计']
    tot_cnt = df_cnt[df_cnt.iloc[:,0]=='合计']
    if len(tot_ape) and len(tot_cnt):
        apes = [num(tot_ape.iloc[0][c])/1e6 for c in week_cols]
        cnts = [int(num(tot_cnt.iloc[0][c])) for c in week_cols]
        rows.append(('合计', apes, cnts))
    return rows, week_cols

MATRIX_DATA = {
    'Q': _matrix_data_rows('B-APE', 'B-件数'),
    'R': _matrix_data_rows('C-APE', 'C-件数'),
    'S': _matrix_data_rows('D-APE', 'D-件数'),
}

def _fmt_cell(ape, cnt):
    if cnt == 0 and ape < 0.05:
        return ("", "")
    if cnt == 0:
        return (f"{ape:.1f}M", "")
    return (f"{ape:.1f}M", f"{cnt}件")

for prefixes, anchor, top_rng, tag in MATRICES:
    rows, week_cols = MATRIX_DATA[tag]
    col_x = anchor + COLUMN_GAP   # W14 x-coordinate
    w14_cells = []
    for shp in _s7.shapes:
        if not shp.name.endswith('_W14'): continue
        if not shp.has_text_frame: continue
        if not any(shp.name.startswith(p) for p in prefixes if p.startswith('T')):
            continue
        if shp.top is None: continue
        if not (top_rng[0] <= shp.top <= top_rng[1]): continue
        if shp.top < top_rng[0] + 200000: continue
        w14_cells.append((shp.top, shp.name, shp.height))
    w14_cells.sort()
    pairs = []
    i = 0
    while i < len(w14_cells):
        t1, n1, h1 = w14_cells[i]
        if i+1 < len(w14_cells):
            t2, n2, h2 = w14_cells[i+1]
            if t2 - t1 < 250000:
                if h1 >= h2:
                    pairs.append((n1, n2))
                else:
                    pairs.append((n2, n1))
                i += 2
                continue
        pairs.append((n1, None))
        i += 1
    w14_idx = 13
    wrote = 0
    for r_idx, (ape_name, cnt_name) in enumerate(pairs):
        if r_idx >= len(rows): break
        ch_name, apes, cnts = rows[r_idx]
        if w14_idx >= len(apes): break
        ape_val, cnt_val = _fmt_cell(apes[w14_idx], cnts[w14_idx])
        for shp in _s7.shapes:
            if shp.name == ape_name and shp.has_text_frame:
                if shp.text_frame.paragraphs and shp.text_frame.paragraphs[0].runs:
                    shp.text_frame.paragraphs[0].runs[0].text = ape_val
                    for r in shp.text_frame.paragraphs[0].runs[1:]:
                        r.text = ""
                    wrote += 1
            if cnt_name and shp.name == cnt_name and shp.has_text_frame:
                if shp.text_frame.paragraphs and shp.text_frame.paragraphs[0].runs:
                    shp.text_frame.paragraphs[0].runs[0].text = cnt_val
                    for r in shp.text_frame.paragraphs[0].runs[1:]:
                        r.text = ""
    print(f"  [{tag}] W14: wrote {wrote} cells ({len(pairs)} pairs detected)")

# Step 4: fix the W14 column header text (was cloned as "W13")
for shp in _s7.shapes:
    if shp.name in ('T6012_W14', 'T7012_W14', 'T8012_W14'):
        if shp.has_text_frame and shp.text_frame.paragraphs and shp.text_frame.paragraphs[0].runs:
            shp.text_frame.paragraphs[0].runs[0].text = CURRENT_WEEK

print("  [Slide 7] heat matrices: W14 column cloned + data populated")

# ------------------------------------------------------------------------
# Slide 11: Bank 本周 W14 KPI 卡片 + AC 表 (real PPT Table object)
# ------------------------------------------------------------------------
def _bk_w14(block, ka):
    """Read S3 bank block W14 value for a specific KA."""
    df = S3[block]
    row = df[df.iloc[:, 0] == ka]
    if not len(row):
        return 0
    return num(row.iloc[0][CURRENT_WEEK_COL])

# Bank W14 values
MS_APP_M   = _bk_w14("M-APE", "民生银行") / 1e6
MS_APP_CNT = int(_bk_w14("M-件数", "民生银行"))
MS_SGN_M   = _bk_w14("N-APE", "民生银行") / 1e6
MS_SGN_CNT = int(_bk_w14("N-件数", "民生银行"))
MS_APR_M   = _bk_w14("O-APE", "民生银行") / 1e6
MS_APR_CNT = int(_bk_w14("O-件数", "民生银行"))

PA_APP_M   = _bk_w14("M-APE", "平安银行") / 1e6
PA_APP_CNT = int(_bk_w14("M-件数", "平安银行"))
PA_SGN_M   = _bk_w14("N-APE", "平安银行") / 1e6
PA_SGN_CNT = int(_bk_w14("N-件数", "平安银行"))
PA_APR_M   = _bk_w14("O-APE", "平安银行") / 1e6
PA_APR_CNT = int(_bk_w14("O-件数", "平安银行"))

TOT_APP_M   = MS_APP_M + PA_APP_M
TOT_APP_CNT = MS_APP_CNT + PA_APP_CNT
TOT_SGN_M   = MS_SGN_M + PA_SGN_M
TOT_SGN_CNT = MS_SGN_CNT + PA_SGN_CNT
TOT_APR_M   = MS_APR_M + PA_APR_M
TOT_APR_CNT = MS_APR_CNT + PA_APR_CNT

# Top KPI cards (shape-name targeted — header + value)
def _fmtM(v): return f"{v:.2f}M"
def _fmtI(v): return str(v)

set_shape_text(_s(10), "Text 21", f" BK {CURRENT_WEEK}预约")
set_shape_text(_s(10), "Text 22", _fmtM(TOT_APP_M))
set_shape_text(_s(10), "Text 26", f"BK {CURRENT_WEEK}签单")
set_shape_text(_s(10), "Text 27", _fmtM(TOT_SGN_M))
set_shape_text(_s(10), "Text 31", f"BK {CURRENT_WEEK}批核")
set_shape_text(_s(10), "Text 32", _fmtM(TOT_APR_M))

def _avg_w(ape_m, cnt):
    return (ape_m * 1e6 / cnt / 10000) if cnt else 0

set_shape_text(_s(10), "Text 23",
    f"{TOT_APP_CNT}件| 件均{_avg_w(TOT_APP_M, TOT_APP_CNT):.1f}W")
set_shape_text(_s(10), "Text 28",
    f"{TOT_SGN_CNT}件| 件均{_avg_w(TOT_SGN_M, TOT_SGN_CNT):.1f}W")
set_shape_text(_s(10), "Text 33",
    f"{TOT_APR_CNT}件 | 件均{_avg_w(TOT_APR_M, TOT_APR_CNT):.1f}W")

# AC table (real python-pptx Table object called "Table 1")
def _update_ac_table(slide):
    """Update the W14 bank KA weekly detail table."""
    for shp in slide.shapes:
        if not shp.has_table: continue
        if shp.name != "Table 1": continue
        tbl = shp.table
        def set_cell(r, c, text):
            cell = tbl.cell(r, c)
            if cell.text_frame.paragraphs and cell.text_frame.paragraphs[0].runs:
                cell.text_frame.paragraphs[0].runs[0].text = text
                for rn in cell.text_frame.paragraphs[0].runs[1:]:
                    rn.text = ""
        # 民生银行
        set_cell(1, 1, _fmtM(MS_APP_M))
        set_cell(1, 2, _fmtI(MS_APP_CNT))
        set_cell(1, 3, _fmtM(MS_SGN_M))
        set_cell(1, 4, _fmtI(MS_SGN_CNT))
        set_cell(1, 5, _fmtM(MS_APR_M))
        set_cell(1, 6, _fmtI(MS_APR_CNT))
        # 平安银行
        set_cell(2, 1, _fmtM(PA_APP_M))
        set_cell(2, 2, _fmtI(PA_APP_CNT))
        set_cell(2, 3, _fmtM(PA_SGN_M))
        set_cell(2, 4, _fmtI(PA_SGN_CNT))
        set_cell(2, 5, _fmtM(PA_APR_M))
        set_cell(2, 6, _fmtI(PA_APR_CNT))
        # 银行合计
        set_cell(3, 1, _fmtM(TOT_APP_M))
        set_cell(3, 2, _fmtI(TOT_APP_CNT))
        set_cell(3, 3, _fmtM(TOT_SGN_M))
        set_cell(3, 4, _fmtI(TOT_SGN_CNT))
        set_cell(3, 5, _fmtM(TOT_APR_M))
        set_cell(3, 6, _fmtI(TOT_APR_CNT))
        return True
    return False

_update_ac_table(_s(10))
print(f"  [Slide 11] AC table + KPI cards updated for {CURRENT_WEEK}")

# ============================================================================
# Slide 3: G 永明牌照表 — 直接从 CSV S1 H block 逐行匹配写入
# 绕过 _lic() / data_loader 解析，避免行偏移导致数据错位
# ALICE数据列（二级来源）不更新，只更新6个主列：Jan/Feb/Mar/Apr/未批核/本月已递交
# ============================================================================
def _fmt_m(v):
    return f"{v:.2f}M" if v > 0 else "0M"

print("\n--- G 牌照表直接写入 ---")

# ── Step 1: 直接从 CSV 读取 H block ─────────────────────────────────
# 按行顺序读取（位置匹配），不依赖行名称，支持行数随时间变化。
# ALICE列（人工输入的二级数据）完全不写入，只写入CSV中存在的列。

_s1_csv_path = CSV_S1

def _read_h_block_ordered(csv_path):
    """
    从 S1 CSV 的 H block 中读取数据，返回：
      rows_ordered: list of {col_name: float} — 按 CSV 行顺序，支持任意行数
      months:       [YYYY-MM, ...] — 月份列名，动态读取
      extra_cols:   [未批核, 本月已递交, ...] — 非月份的数据列
    行名仅用于日志，不作为匹配依据。行数、列数、年份均动态读取。
    """
    import csv as _csv, re as _re
    rows_ordered = []; row_names = []; months = []; extra_cols = []
    in_block = False; header = None
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for line in _csv.reader(f):
            if not line: continue
            first = str(line[0]).strip()
            if "永明业绩汇报数据" in first and "Sunlife" in first:
                in_block = True; continue
            if not in_block: continue
            if first.startswith("📌") or first.startswith("\U0001f4cc"): continue
            if first == "牌照":
                header = [c.strip() for c in line]
                for col in header[1:]:
                    if _re.match(r"^\d{4}-\d{2}$", col):
                        months.append(col)
                    elif col:
                        extra_cols.append(col)
                continue
            if not first: break
            if header is None: continue
            row_data = {}
            for col_name, val_str in zip(header[1:], line[1:]):
                try:
                    row_data[col_name] = float(str(val_str).replace(",", "").strip())
                except (ValueError, AttributeError):
                    row_data[col_name] = 0.0
            rows_ordered.append(row_data)
            row_names.append(first)
    return rows_ordered, row_names, months, extra_cols

_h_rows, _h_names, _h_months, _h_extra = _read_h_block_ordered(_s1_csv_path)

print(f"  H block rows ({len(_h_rows)}): {_h_names}")
print(f"  H block months: {_h_months}  extra: {_h_extra}")
for i, (nm, rd) in enumerate(zip(_h_names, _h_rows)):
    _j = rd.get(_h_months[0], 0)/1e6 if _h_months else 0
    _c = rd.get(_h_months[-1], 0)/1e6 if _h_months else 0
    print(f"  row{i} {nm}: first={_j:.2f}M  last={_c:.2f}M")

# ── Step 2 (FIXED): 按列索引写入G表，完全不依赖x坐标 ─────────────────────────
# 每行按x排序所有形状，取第[1,3,5,7,9,11]个（跳过行名和ALICE列）
# 这是最可靠的方式：只需y坐标定位行，列顺序天然固定

_G_ROW_Y_CENTERS = [1809750, 2056765, 2303780, 2555240, 2807970, 3054985]
_G_COL_INDICES   = [1, 3, 5, 7, 9, 11]   # 在按x排序后，数据列的位置索引

def _g_write_all_rows(slide, h_rows, h_names, h_months, h_extra):
    from lxml import etree as _lxml_gw
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ROW_TOL_Y = 80000

    def _write(sh, text):
        txBody = sh.text_frame._txBody
        ep = txBody.find(f".//{{{NS_A}}}rPr")
        sz   = ep.get("sz",   "850")   if ep is not None else "850"
        lang = ep.get("lang", "en-US") if ep is not None else "en-US"
        p = txBody.find(f"{{{NS_A}}}p")
        if p is None:
            p = _lxml_gw.SubElement(txBody, f"{{{NS_A}}}p")
        for c in list(p):
            if c.tag.split("}")[-1] in ("r", "endParaRPr"):
                p.remove(c)
        r_el = _lxml_gw.SubElement(p, f"{{{NS_A}}}r")
        rp   = _lxml_gw.SubElement(r_el, f"{{{NS_A}}}rPr")
        rp.set("lang", lang); rp.set("sz", sz); rp.set("dirty", "0")
        t_el = _lxml_gw.SubElement(r_el, f"{{{NS_A}}}t")
        t_el.text = text

    def _fmt(v):
        try:
            m = float(str(v).replace(",", "")) / 1_000_000
            return f"{m:.2f}M" if m > 0 else "0M"
        except:
            return "0M"

    rolling = h_months[-4:] if len(h_months) >= 4 else h_months
    # 数据列对应的CSV列名: [m0,m1,m2,m3,e0,e1]
    col_names = list(rolling) + list(h_extra[:2])
    # col_names = [2026-02, 2026-03, 2026-04, 2026-05, 未批核, 本月已递交]

    total_written = 0
    for row_idx, y_center in enumerate(_G_ROW_Y_CENTERS):
        row_data = h_rows[row_idx] if row_idx < len(h_rows) else None
        row_label = h_names[row_idx] if row_idx < len(h_names) else str(row_idx)

        # 收集该行所有文本形状，按x排序
        row_shapes = sorted(
            [sh for sh in slide.shapes
             if sh.has_text_frame and sh.left is not None and sh.top is not None
             and abs(sh.top - y_center) <= ROW_TOL_Y],
            key=lambda s: s.left
        )

        written = 0
        for data_pos, col_name in zip(_G_COL_INDICES, col_names):
            if data_pos >= len(row_shapes):
                continue
            sh = row_shapes[data_pos]
            val = row_data.get(col_name, 0.0) if row_data else 0.0
            text = _fmt(val)
            _write(sh, text)
            written += 1

        total_written += written
        print(f"  [G] {row_label}: {written} cols written | "
              f"shapes_in_row={len(row_shapes)} | "
              f"rolling={rolling}")

    return total_written

_g_total_written = _g_write_all_rows(
    _SL_SUNLIFE, _h_rows, _h_names, _h_months, _h_extra
)
print(f"  [G] 写入完成: {_g_total_written} 个单元格")

# ------------------------------------------------------------------------
# Slide 6: P KEY ACCOUNT TOP10 排名 — rebuild from S2 I block
# ------------------------------------------------------------------------
P_ROW_Y = [4114800, 4315968, 4517136, 4718304, 4919472,
           5120640, 5321808, 5522976, 5724144, 5925312]
P_X_NUM   = 4242816
P_X_KA    = 4553712
P_X_SEG   = 5468112
P_X_APE_I = 6254496
P_X_CNT_I = 7095744
P_X_APE_U = 7662672
P_X_CNT_U = 8503920
P_X_APE_P = 9070848
P_X_CNT_P = 9765792
P_X_APE_T = 10332720
P_X_CNT_T = 11210544

# Get TOP10 KAs from S2 I (already sorted by 2026批核APE desc in CSV)
top10_ka = S2["I"].head(10)
for i, (_, r) in enumerate(top10_ka.iterrows()):
    if i >= 10: break
    y = P_ROW_Y[i]
    ka_name = str(r["KEY ACCOUNT"]).strip()
    seg     = str(r["业务细分"]).strip()
    iss_m   = to_m(r["2026批核APE"])
    iss_c   = int(num(r["批核件数"]))
    unb_m   = to_m(r["未批核APE"])
    unb_c   = int(num(r["未批核件数"]))
    pnd_m   = to_m(r["待签APE"])
    pnd_c   = int(num(r["待签件数"]))
    tot_m   = to_m(r["合计APE"])
    tot_c   = int(num(r["合计件数"]))
    set_shape_text_at(slides[5], P_X_NUM,   y, str(i+1),        tol=30000)
    set_shape_text_at(slides[5], P_X_KA,    y, ka_name,         tol=30000)
    set_shape_text_at(slides[5], P_X_SEG,   y, seg,             tol=30000)
    set_shape_text_at(slides[5], P_X_APE_I, y, f"{iss_m:.1f}M", tol=30000)
    set_shape_text_at(slides[5], P_X_CNT_I, y, str(iss_c),      tol=30000)
    set_shape_text_at(slides[5], P_X_APE_U, y, f"{unb_m:.1f}M", tol=30000)
    set_shape_text_at(slides[5], P_X_CNT_U, y, str(unb_c),      tol=30000)
    set_shape_text_at(slides[5], P_X_APE_P, y, f"{pnd_m:.1f}M", tol=30000)
    set_shape_text_at(slides[5], P_X_CNT_P, y, str(pnd_c),      tol=30000)
    set_shape_text_at(slides[5], P_X_APE_T, y, f"{tot_m:.1f}M", tol=30000)
    set_shape_text_at(slides[5], P_X_CNT_T, y, str(tot_c),      tol=30000)

# TOP10 合计 row
_p_iss = top10_ka["2026批核APE"].apply(num).sum() / 1e6
_p_iss_c = int(top10_ka["批核件数"].apply(num).sum())
_p_unb = top10_ka["未批核APE"].apply(num).sum() / 1e6
_p_unb_c = int(top10_ka["未批核件数"].apply(num).sum())
_p_pnd = top10_ka["待签APE"].apply(num).sum() / 1e6
_p_pnd_c = int(top10_ka["待签件数"].apply(num).sum())
_p_tot = top10_ka["合计APE"].apply(num).sum() / 1e6
_p_tot_c = int(top10_ka["合计件数"].apply(num).sum())
P_TOTAL_Y = 6099810
set_shape_text_at(slides[5], P_X_APE_I, P_TOTAL_Y, f"{_p_iss:.1f}M", tol=30000)
set_shape_text_at(slides[5], P_X_CNT_I, P_TOTAL_Y, f"{_p_iss_c}件",  tol=30000)
set_shape_text_at(slides[5], P_X_APE_U, P_TOTAL_Y, f"{_p_unb:.1f}M", tol=30000)
set_shape_text_at(slides[5], P_X_CNT_U, P_TOTAL_Y, f"{_p_unb_c}件",  tol=30000)
set_shape_text_at(slides[5], P_X_APE_P, P_TOTAL_Y, f"{_p_pnd:.1f}M", tol=30000)
set_shape_text_at(slides[5], P_X_CNT_P, P_TOTAL_Y, f"{_p_pnd_c}件",  tol=30000)
set_shape_text_at(slides[5], P_X_APE_T, P_TOTAL_Y, f"{_p_tot:.1f}M", tol=30000)
set_shape_text_at(slides[5], P_X_CNT_T, P_TOTAL_Y, f"{_p_tot_c}件",  tol=30000)

# ------------------------------------------------------------------------
# Slide 7: Q/R/S 热力矩阵 — 动态克隆 W13 列 → W14 列，并写入数据（第二段落，保留原有逻辑）
# ------------------------------------------------------------------------
MATRICES = [
    # Q 预约 matrix at top-left  → T7xxx / shapes at L≈5371168 for W13
    (5371168,  182880,  800000,  "B-APE", "B-件数", "Q 预约"),
    # R 签单 matrix at top-right → T8xxx / shapes at L≈11446941 for W13
    (11446941, 6254496, 800000,  "C-APE", "C-件数", "R 签单"),
    # S 批核 matrix at bottom-left → T6xxx / shapes at L≈5339384 for W13
    (5339384,  182880,  3900000, "D-APE", "D-件数", "S 批核"),
]

print("\n--- SLIDE 7 — W14 列克隆 + 数据写入 ---")
_s7 = _s(6)
for w13_left, name_left, top_min, ape_block, cnt_block, tag in MATRICES:
    # Step 1: compute name+ape maps FIRST (before cloning)
    def _rows_in_col(slide, col_left, tol=50000, top_min=0):
        rows = []
        for shp in slide.shapes:
            if shp.left is None or shp.top is None:
                continue
            if abs(shp.left - col_left) > tol:
                continue
            if shp.top < top_min:
                continue
            if shp.height is None or not (170000 < shp.height < 200000):
                continue
            if not shp.has_text_frame:
                continue
            t = "".join(r.text for p in shp.text_frame.paragraphs for r in p.runs).strip()
            rows.append((shp.top, t))
        rows.sort()
        return rows

    def _rows_with_names(slide, apecol_left, namecol_left, tol=50000, top_min=0):
        names = []
        for shp in slide.shapes:
            if shp.left is None or shp.top is None:
                continue
            if abs(shp.left - namecol_left) > tol:
                continue
            if not shp.has_text_frame:
                continue
            t = "".join(r.text for p in shp.text_frame.paragraphs for r in p.runs).strip()
            if t and len(t) < 10 and shp.top > top_min:
                names.append((shp.top, t))
        names.sort()
        return names

    names = _rows_with_names(_s7, w13_left, name_left, top_min=top_min)
    ape_rows = _rows_in_col(_s7, w13_left, top_min=top_min)
    if not ape_rows:
        print(f"  [{tag}] no W13 column found at L={w13_left}, skipping")
        continue

    y_to_name = {}
    for name_top, name_text in names:
        best = min(ape_rows, key=lambda r: abs(r[0] - name_top))
        if abs(best[0] - name_top) < 200000:
            y_to_name[best[0]] = name_text

    created = clone_column_right(_s7, w13_left, x_offset=390000)

    df_ape = S3[ape_block]
    df_cnt = S3[cnt_block]
    col = CURRENT_WEEK_COL

    def _lookup(line_name):
        r_ape = df_ape[df_ape.iloc[:, 0] == line_name]
        r_cnt = df_cnt[df_cnt.iloc[:, 0] == line_name]
        if not len(r_ape) or not len(r_cnt):
            return None, None
        return to_m(r_ape.iloc[0][col]), int(num(r_cnt.iloc[0][col]))

    def _lookup_merged(line_name):
        if line_name == "成事+合伙":
            a1, c1 = _lookup("成事家办")
            a2, c2 = _lookup("合伙转介业务")
            if a1 is None: a1 = 0
            if a2 is None: a2 = 0
            if c1 is None: c1 = 0
            if c2 is None: c2 = 0
            return round((a1 or 0) + (a2 or 0), 2), (c1 or 0) + (c2 or 0)
        return _lookup(line_name)

    cloned_sorted = sorted(created, key=lambda x: (x[0].top or 0, x[0].left or 0))

    hits = 0
    for src_shape, new_xml in cloned_sorted:
        if not src_shape.has_text_frame:
            continue
        src_text = "".join(
            r.text for p in src_shape.text_frame.paragraphs for r in p.runs
        ).strip()
        if src_text == "W13":
            set_shape_text_xml(new_xml, CURRENT_WEEK)
            hits += 1
            continue
        src_top = src_shape.top
        src_h   = src_shape.height
        if src_h is None:
            continue
        if 170000 < src_h < 200000:
            line = y_to_name.get(src_top)
            if not line:
                continue
            ape_val, _ = _lookup_merged(line)
            if ape_val is None:
                continue
            set_shape_text_xml(new_xml, f"{ape_val:.1f}M" if ape_val else "")
            hits += 1
        elif 90000 < src_h < 140000:
            ape_keys = list(y_to_name.keys())
            if not ape_keys:
                continue
            nearest = min(ape_keys, key=lambda y: abs(y - (src_top - 174000)))
            line = y_to_name.get(nearest)
            if not line:
                continue
            _, cnt_val = _lookup_merged(line)
            if cnt_val is None:
                continue
            set_shape_text_xml(new_xml, f"{cnt_val}件" if cnt_val else "")
            hits += 1
    print(f"  [{tag}] cloned {len(created)} shapes, wrote {hits} cells")

# ============================================================================
# Slide 3: I 永明 2026 签单产品排名 TOP10
# FIX 3 (complete rewrite): Discount column has TWO problems:
#   a) Wide background rectangle (Shape 105 etc, x=6270625, cx=5601335) accidentally
#      contains discount % text — it appears leftmost because it spans the full row width.
#      CLEAR this shape's text.
#   b) Correct discount position is Text 110 at x≈8834882 (between product name and count).
#      WRITE discount value there with matching Calibri sz=800 font.
# ============================================================================
I_ROW_Y = [
    4407535,  # row 1  (y from PPT scan)
    4608830,  # row 2
    4810125,  # row 3  (approx, pattern +201295)
    5034280,  # row 4
    5239385,  # row 5
    5456555,  # row 6
    5660390,  # row 7
    5868035,  # row 8
    6085840,  # row 9  (approx)
    6287135,  # row 10 (approx)
]
I_X_BG_RECT  = 6270625   # wide background rect — CLEAR this
I_X_RANK     = 6515100
I_X_CARRIER  = 6771132
I_X_PRODUCT  = 7228332
I_X_DISCOUNT = 8834882   # correct Text 110 discount position (between product and count)
I_X_COUNT    = 9624822
I_X_APE      = 10283190
I_X_AVG      = 11179302

# ── Step A: Clear wide background rects on slides[0] (Sunlife slide) ────────
# FIX: I table is on slides[0] (Sunlife slide1), NOT slides[2]
_cleared_bg = 0
for sh in _SL_SUNLIFE.shapes:
    if not sh.has_text_frame: continue
    if sh.left is None or sh.top is None: continue
    if abs(sh.left - I_X_BG_RECT) > 30000: continue
    if not (4200000 <= sh.top <= 6400000): continue
    txt = "".join(r.text for p in sh.text_frame.paragraphs for r in p.runs).strip()
    if txt:
        for p in sh.text_frame.paragraphs:
            for r in p.runs:
                r.text = ""
        _cleared_bg += 1
print(f"  [I] Cleared {_cleared_bg} background rect shapes (stale discount %)")

# ── Step B: Build a font-matched writer for discount cells ─────────────────
def _write_discount(slide, left_x, top_y, text, tol=60000):
    """Write discount value into Text 110 shape at x≈8834882 with correct font."""
    from lxml import etree
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    for sh in slide.shapes:
        if sh.left is None or sh.top is None: continue
        if abs(sh.left - left_x) > tol: continue
        if abs(sh.top - top_y) > tol: continue
        if not sh.has_text_frame: continue
        tf = sh.text_frame
        txBody = tf._txBody
        for p_el in txBody.findall(f"{{{NS_A}}}p"):
            txBody.remove(p_el)
        p_xml = (
            f'<a:p xmlns:a="{NS_A}">'
            f'<a:r>'
            f'<a:rPr lang="en-US" sz="800" dirty="0">'
            f'<a:solidFill><a:srgbClr val="374151"/></a:solidFill>'
            f'<a:latin typeface="Calibri" panose="020F0502020204030204" pitchFamily="34" charset="0"/>'
            f'<a:ea typeface="Calibri" panose="020F0502020204030204" pitchFamily="34" charset="-122"/>'
            f'<a:cs typeface="Calibri" panose="020F0502020204030204" pitchFamily="34" charset="-120"/>'
            f'</a:rPr>'
            f'<a:t>{text}</a:t>'
            f'</a:r>'
            f'</a:p>'
        )
        txBody.append(etree.fromstring(p_xml))
        return True
    return False

for row_idx, rec in enumerate(_ym_top10):
    if row_idx >= 10:
        break
    y = I_ROW_Y[row_idx]
    term = rec.get("年期", "")
    pname = rec.get("产品名称", "")
    display = f"{pname}（{term}年）" if term else pname
    cnt = int(num(rec.get("件数", 0)))
    ape_m = num(rec.get("APE", 0)) / 1e6
    ape_avg_w = num(rec.get("APE件均", 0)) / 10000
    discount_raw = rec.get("折扣", "")
    discount_str = str(discount_raw).strip() if discount_raw else ""
    if discount_str and not discount_str.endswith("%"):
        try:
            dv = float(discount_str)
            discount_str = f"{int(round(dv * 100))}%" if dv <= 1 else f"{int(round(dv))}%"
        except ValueError:
            pass

    # FIX: all I table writes go to slides[0]
    set_shape_text_at(_SL_SUNLIFE, I_X_PRODUCT, y, display, tol=30000)
    set_shape_text_at(_SL_SUNLIFE, I_X_COUNT,   y, str(cnt), tol=30000)
    set_shape_text_at(_SL_SUNLIFE, I_X_APE,     y, f"{ape_m:.2f}M", tol=30000)
    set_shape_text_at(_SL_SUNLIFE, I_X_AVG,     y, f"{ape_avg_w:.1f}万", tol=30000)
    if discount_str:
        ok = _write_discount(_SL_SUNLIFE, I_X_DISCOUNT, y, discount_str, tol=60000)
        if not ok:
            print(f"  [I] row {row_idx+1}: discount shape not found at x={I_X_DISCOUNT} y={y}")

# Footer: 合计件数 + APE
if _ym_top10:
    _top10_total_cnt = sum(int(num(r.get("件数", 0))) for r in _ym_top10)
    _top10_total_ape = sum(num(r.get("APE", 0)) for r in _ym_top10) / 1e6
    set_shape_text_at(_SL_SUNLIFE, 9606534, 6540119, f"{_top10_total_cnt}件", tol=40000)
    set_shape_text_at(_SL_SUNLIFE, 10246614, 6540119, f"{_top10_total_ape:.1f}M", tol=40000)

print("  Done.")


# ============================================================================
# Save
# ============================================================================
# ═══════════════════════════════════════════════════════════════════════
# Embed/refresh xlsx for ALL charts so "Edit Data" works in PowerPoint
# ═══════════════════════════════════════════════════════════════════════
print("\n--- EMBEDDING XLSX FOR ALL CHARTS ---")

try:
    import openpyxl
    from openpyxl import Workbook as _OWB
    import io, zipfile
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.opc.packuri import PackURI

    def _embed_xlsx_for_chart(chart_part, chart_data_obj):
        """Create a minimal xlsx workbook and embed it in the chart part."""
        wb = _OWB()
        ws = wb.active
        ws.title = "ChartData"

        NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
        root = chart_part._element

        # Extract categories and series from chart XML
        sers = root.findall(".//{%s}ser" % NS_C)
        if not sers:
            return False

        # Build table: row 0 = headers (series names), col 0 = categories
        cats = []
        cat_el = sers[0].find(".//{%s}cat" % NS_C) if sers else None
        if cat_el is not None:
            for v in cat_el.findall(".//{%s}v" % NS_C):
                if v.text and v.text not in cats:
                    cats.append(v.text)

        # Write header row
        ws.cell(row=1, column=1, value="")
        for j, ser in enumerate(sers):
            name_v = ser.find(".//{%s}tx" % NS_C)
            ser_name = ""
            if name_v is not None:
                v_el = name_v.find(".//{%s}v" % NS_C)
                ser_name = v_el.text if v_el is not None else ""
            ws.cell(row=1, column=j+2, value=ser_name)

        # Write category + data rows
        for i, cat in enumerate(cats):
            ws.cell(row=i+2, column=1, value=cat)

        for j, ser in enumerate(sers):
            pts = ser.findall(".//{%s}pt" % NS_C)
            val_pts = {}
            # Only numeric value points (not category strings)
            val_el = ser.find(".//{%s}val" % NS_C)
            if val_el is None:
                val_el = ser.find(".//{%s}yVal" % NS_C)
            if val_el is not None:
                for pt in val_el.findall(".//{%s}pt" % NS_C):
                    idx = int(pt.get("idx", -1))
                    v = pt.find("{%s}v" % NS_C)
                    if v is not None and v.text:
                        try:
                            val_pts[idx] = float(v.text)
                        except ValueError:
                            val_pts[idx] = v.text
            for i in range(len(cats)):
                val = val_pts.get(i, None)
                ws.cell(row=i+2, column=j+2, value=val)

        # Save workbook to bytes
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        xlsx_bytes = buf.read()

        # Check if chart already has an xlsx relationship
        existing_xlsx = [
            r for r in chart_part.rels.values()
            if "spreadsheets" in str(r.target_ref) or "xl/" in str(r.target_ref)
        ]

        if existing_xlsx:
            # Update existing embedded xlsx
            rel = existing_xlsx[0]
            xlsx_part = rel.target_part
            xlsx_part._blob = xlsx_bytes
        else:
            # Add new xlsx part
            # Use a simple approach: add to the package
            xlsx_partname = PackURI("/ppt/embeddings/ChartData_%s.xlsx" % id(chart_part))
            from pptx.opc.part import Part
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            xlsx_part = Part(xlsx_partname, content_type, xlsx_bytes)
            # Add relationship from chart to xlsx
            XLSX_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package"
            chart_part.relate_to(xlsx_part, XLSX_RT)

            # Also update the chart XML to reference the xlsx
            # Find or create <c:externalData> element
            ext_data = root.find("{%s}externalData" % NS_C)
            if ext_data is None:
                from lxml import etree
                # Get the rId for the new relationship
                rId = [k for k, v in chart_part.rels.items() if v.target_part is xlsx_part]
                if rId:
                    ext_data = etree.SubElement(root, "{%s}externalData" % NS_C)
                    ext_data.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", rId[0])
                    ext_data.set("autoUpdate", "1")
        return True

    # Process all slides and charts
    total_embedded = 0
    for si, slide in enumerate(prs.slides):
        for sh in slide.shapes:
            if not getattr(sh, "has_chart", False):
                continue
            try:
                chart_part = sh.chart.part
                ok = _embed_xlsx_for_chart(chart_part, None)
                if ok:
                    total_embedded += 1
                    print(f"  ✓ Slide {si+1} [{sh.name}] xlsx embedded/updated")
            except Exception as e:
                print(f"  ⚠ Slide {si+1} [{sh.name}] xlsx error: {e}")

    print(f"  Total: {total_embedded} charts processed")
except Exception as e:
    print(f"  ⚠ xlsx embedding failed: {e}")

# ── Update Z chart data labels (Slide 10: Chart_YY/QD/PH) ──────────────────
# Bank monthly data labels: "民生 X.XXM/N件" and "平安 X.XXM/N件" per month.
# Data sourced from S2 P-APE/P-件数, Q-APE/Q-件数, R-APE/R-件数.
print("\n--- Z CHART DATA LABELS (Slide 10 bank monthly) ---")

def _update_z_chart_dlbls(slide, chart_name, ka_data):
    """
    Update per-bar data labels on a bank monthly bar chart.
    ka_data: dict {ka_name: [(ape_yuan, cnt), ...]} in series order.
    Label format: "民生 X.XXM/N件" or "平安 X.XXM/N件" (0 → "民生 0M").

    Fix: also injects new <dLbl> elements for months added by _extend_bk_monthly_chart
    (previously only existing <dLbl> elements were updated, so new months had no label).
    """
    from lxml import etree as _et_zdlbl
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart:
        print(f"  ! [Z dlbl] chart not found: {chart_name}")
        return
    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    root = shp.chart.part._element
    sers = root.findall(f".//{{{NS_C}}}ser")
    for ser in sers:
        tx = ser.find(f".//{{{NS_C}}}tx")
        ser_name = ""
        if tx is not None:
            v_el = tx.find(f".//{{{NS_C}}}v")
            if v_el is not None:
                ser_name = v_el.text or ""
        ka_vals = ka_data.get(ser_name, [])
        if not ka_vals:
            continue
        short = ser_name.replace("银行", "")
        ser_dlbls = ser.find(f"{{{NS_C}}}dLbls")
        if ser_dlbls is None:
            continue

        # Build map of existing dLbl idx values
        existing_dlbl_idxs = {}
        for dl in ser_dlbls.findall(f"{{{NS_C}}}dLbl"):
            idx_el = dl.find(f"{{{NS_C}}}idx")
            if idx_el is None:
                continue
            idx = int(idx_el.get("val", "-1"))
            existing_dlbl_idxs[idx] = dl

        # Find a template <dLbl> to clone for new months (use first existing one)
        _template_dl = ser_dlbls.findall(f"{{{NS_C}}}dLbl")[0] if ser_dlbls.findall(f"{{{NS_C}}}dLbl") else None

        for idx in range(len(ka_vals)):
            ape_yuan, cnt = ka_vals[idx]
            ape_m = ape_yuan / 1e6
            label = f"{short} {ape_m:.2f}M/{cnt}件" if ape_m > 0 else f"{short} 0M"

            if idx in existing_dlbl_idxs:
                # Update existing label
                dl = existing_dlbl_idxs[idx]
                a_ts = dl.findall(f".//{{{NS_A}}}t")
                if a_ts:
                    a_ts[0].text = label
                    for extra in a_ts[1:]:
                        extra.text = ""
            elif _template_dl is not None:
                # Inject new <dLbl> for this month (cloned from template)
                from copy import deepcopy as _zdlbl_dc
                new_dl = _zdlbl_dc(_template_dl)
                # Set the idx
                idx_el2 = new_dl.find(f"{{{NS_C}}}idx")
                if idx_el2 is not None:
                    idx_el2.set("val", str(idx))
                else:
                    idx_el2 = _et_zdlbl.SubElement(new_dl, f"{{{NS_C}}}idx")
                    idx_el2.set("val", str(idx))
                # Set the label text
                a_ts2 = new_dl.findall(f".//{{{NS_A}}}t")
                if a_ts2:
                    a_ts2[0].text = label
                    for extra in a_ts2[1:]:
                        extra.text = ""
                # Insert before </dLbls> (in idx order: find insertion point)
                all_dls = ser_dlbls.findall(f"{{{NS_C}}}dLbl")
                insert_before = None
                for existing_dl in all_dls:
                    ex_idx_el = existing_dl.find(f"{{{NS_C}}}idx")
                    if ex_idx_el is not None and int(ex_idx_el.get("val", "0")) > idx:
                        insert_before = existing_dl
                        break
                if insert_before is not None:
                    insert_pos = list(ser_dlbls).index(insert_before)
                    ser_dlbls.insert(insert_pos, new_dl)
                else:
                    # Append before any non-dLbl children (e.g. showVal, showLegendKey)
                    non_dlbl = [c for c in ser_dlbls if c.tag != f"{{{NS_C}}}dLbl"]
                    if non_dlbl:
                        ser_dlbls.insert(list(ser_dlbls).index(non_dlbl[0]), new_dl)
                    else:
                        ser_dlbls.append(new_dl)
                print(f"  [Z dlbl] {chart_name} {ser_name}: injected dLbl idx={idx} → {label!r}")

    print(f"  [Z dlbl] {chart_name} updated ({len(ka_vals)} months)")

# Load bank monthly APE/件数 from S2 P/Q/R blocks
def _s2_bank_month_vals(ape_block, cnt_block, ka_name):
    """Return list of (ape_yuan, cnt) for each month column."""
    df_ape = S2[ape_block]
    df_cnt = S2[cnt_block]
    month_cols = [c for c in df_ape.columns if c.startswith("2026-")]
    r_ape = df_ape[df_ape["KEY ACCOUNT"] == ka_name]
    r_cnt = df_cnt[df_cnt["KEY ACCOUNT"] == ka_name]
    if not len(r_ape) or not len(r_cnt):
        return []
    result = []
    for col in month_cols:
        ape_yuan = num(r_ape.iloc[0][col])
        cnt_val  = int(num(r_cnt.iloc[0][col]))
        result.append((ape_yuan, cnt_val))
    return result

_BK_KAS = ["民生银行", "平安银行"]
_Z_CHART_BLOCKS = {
    "Chart_YY": ("P-APE", "P-件数"),
    "Chart_QD": ("Q-APE", "Q-件数"),
    "Chart_PH": ("R-APE", "R-件数"),
}
for _z_chart, (_z_ape_blk, _z_cnt_blk) in _Z_CHART_BLOCKS.items():
    _z_ka_data = {}
    for _ka in _BK_KAS:
        _z_ka_data[_ka] = _s2_bank_month_vals(_z_ape_blk, _z_cnt_blk, _ka)
    _update_z_chart_dlbls(_SL_BK, _z_chart, _z_ka_data)


# ============================================================================
# ★ INTEGRATED FIXES — run immediately before save ★
# 修复三个已知错误，完全独立于 data_loader / chart_updates，直接读CSV写PPT
#
# Fix 1: D 三线图 — 补全签单/批核缺失的当月数据点 + 纠正预约/签单2026年数值
# Fix 2: E 环比标签 — 用lxml重建段落，解决多run形状写入失败 + 极端错误值问题
# Fix 3: G 永明汇报表 — 用lxml强制写入EG行/Sub Total行，防止被后续逻辑覆盖
# ============================================================================

print("\n\n" + "="*70)
print("▶ INTEGRATED FIXES (Fix 1/2/3)")
print("="*70)

import csv as _fix_csv
import re as _fix_re
from lxml import etree as _fix_et

_FIX_NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
_FIX_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

# ── 通用工具 ─────────────────────────────────────────────────────────────
def _fix_read_s1_block(block_letter):
    """从 CSV_S1 读取指定块(C/D/E)，返回 (rows, header)。
    在遇到下一个块标题时停止，防止跨块污染。"""
    rows, header = [], None
    in_block = False
    with open(CSV_S1, encoding="utf-8-sig") as _f:
        for _row in _fix_csv.reader(_f):
            if not _row:
                if in_block:
                    break
                continue
            first = _row[0].strip()
            if first.startswith(f"{block_letter}.") and "月度业绩" in first:
                in_block = True; continue
            if not in_block: continue
            # 遇到下一个块标题停止（如 D. / E. / F. 等）
            if _fix_re.match(r"^[A-Z]\.", first) and not first.startswith(f"{block_letter}."):
                break
            if first.startswith("📌"): continue
            if header is None and any("年月" in c for c in _row):
                header = [c.strip() for c in _row]; continue
            if not first: break
            if header is None: continue
            if _fix_re.match(r"^\d{4}-\d{2}$", first):
                rows.append({header[i]: (_row[i].strip() if i < len(_row) else "")
                             for i in range(len(header))})
    return rows, header


def _fix_set_text_lxml(sh, text, color_hex=None):
    """用lxml直接重建段落内容，彻底避免多run/缓存问题。"""
    if not sh.has_text_frame: return False
    txBody = sh.text_frame._txBody
    existing_rpr = txBody.find(f".//{{{_FIX_NS_A}}}rPr")
    sz   = existing_rpr.get("sz",   "850")   if existing_rpr is not None else "850"
    lang = existing_rpr.get("lang", "en-US") if existing_rpr is not None else "en-US"
    p_el = txBody.find(f"{{{_FIX_NS_A}}}p")
    if p_el is None:
        p_el = _fix_et.SubElement(txBody, f"{{{_FIX_NS_A}}}p")
    for child in list(p_el):
        if child.tag.split("}")[-1] in ("r", "endParaRPr"):
            p_el.remove(child)
    r_el = _fix_et.SubElement(p_el, f"{{{_FIX_NS_A}}}r")
    rPr  = _fix_et.SubElement(r_el, f"{{{_FIX_NS_A}}}rPr")
    rPr.set("lang", lang); rPr.set("sz", sz); rPr.set("dirty", "0")
    if color_hex:
        sf = _fix_et.SubElement(rPr, f"{{{_FIX_NS_A}}}solidFill")
        sc = _fix_et.SubElement(sf,  f"{{{_FIX_NS_A}}}srgbClr")
        sc.set("val", color_hex)
    t_el = _fix_et.SubElement(r_el, f"{{{_FIX_NS_A}}}t")
    t_el.text = text
    return True


def _fix_set_at(slide, tx, ty, text, tol=35000, color_hex=None):
    """按坐标找形状，用lxml写入。"""
    best, best_dist = None, None
    for sh in slide.shapes:
        if not sh.has_text_frame or sh.left is None or sh.top is None: continue
        dx, dy = abs(sh.left - tx), abs(sh.top - ty)
        if dx > tol or dy > tol: continue
        d = dx + dy
        if best is None or d < best_dist:
            best, best_dist = sh, d
    if best is None: return False
    return _fix_set_text_lxml(best, text, color_hex)


# ── Fix 1: D 三线图 (Slide 1 Chart 1) ─────────────────────────────────────
print("\n[Fix 1] D 三线图 — 补全所有系列2026数据点")

_MONTH_ABBR = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
               "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
_NUM_TO_ABBR = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

def _fix_label_to_key(label):
    m = _fix_re.match(r"^(\d{2})-([A-Za-z]{3})$", label)
    if m:
        return f"20{m.group(1)}-{_MONTH_ABBR.get(m.group(2).capitalize(),'00')}"
    return None

def _fix_get_ape(block_letter):
    rows, header = _fix_read_s1_block(block_letter)
    if not header: return {}
    ym_col = header[0]
    result = {}
    for rec in rows:
        ym = rec.get(ym_col, "")
        if not _fix_re.match(r"^\d{4}-\d{2}$", ym): continue
        try:
            result[ym] = float(rec.get("APE","0").replace(",","")) / 1e6
        except ValueError:
            pass
    return result

_fix_c_ape = _fix_get_ape("C")   # 预约
_fix_d_ape = _fix_get_ape("D")   # 签单
_fix_e_ape = _fix_get_ape("E")   # 批核

_fix_series_map = {
    "预约 APE(M)": _fix_c_ape, "预约": _fix_c_ape,
    "签单 APE(M)": _fix_d_ape, "签单": _fix_d_ape,
    "批核 APE(M)": _fix_e_ape, "批核": _fix_e_ape,
}
_fix_series_idx = [_fix_c_ape, _fix_d_ape, _fix_e_ape]

_fix_slide1 = slides[0]
for _sh in _fix_slide1.shapes:
    if not _sh.has_chart or _sh.name != "Chart 1": continue
    _root = _sh.chart.part._element
    _sers = _root.findall(f".//{{{_FIX_NS_C}}}ser")

    # 读取现有category列表（取第一个series的strCache）
    _cats = []
    for _ser0 in _sers[:1]:
        for _sc in _ser0.findall(f"{{{_FIX_NS_C}}}cat//{{{_FIX_NS_C}}}strCache"):
            for _pt in _sc.findall(f"{{{_FIX_NS_C}}}pt"):
                _v = _pt.find(f"{{{_FIX_NS_C}}}v")
                if _v is not None and _v.text:
                    _cats.append(_v.text)

    # 确认category中包含所有CSV里存在的2026月份
    _csv_2026 = sorted(k for k in (_fix_c_ape | _fix_d_ape | _fix_e_ape) if k.startswith("2026"))
    _cat_needs_add = []
    for _ym in _csv_2026:
        mo = int(_ym[5:7])
        lbl = f"{_ym[2:4]}-{_NUM_TO_ABBR[mo]}"
        if lbl not in _cats:
            _cats.append(lbl)
            _cat_needs_add.append((_ym, lbl))
    if _cat_needs_add:
        print(f"  需新增category: {[lbl for _,lbl in _cat_needs_add]}")

    _new_total = len(_cats)   # e.g. 16（含所有需要显示的月份）

    for _si, _ser in enumerate(_sers):
        _tx = _ser.find(f".//{{{_FIX_NS_C}}}tx")
        _sname = ""
        if _tx is not None:
            _v = _tx.find(f".//{{{_FIX_NS_C}}}v")
            if _v is not None: _sname = _v.text or ""
        _data = next((d for sn,d in _fix_series_map.items() if sn in _sname or _sname in sn), None)
        if _data is None and _si < len(_fix_series_idx):
            _data = _fix_series_idx[_si]
        if _data is None: continue

        # 更新<c:f>范围（★关键：PowerPoint以<c:f>行数为准决定渲染多少点）
        _f_el = _ser.find(f"{{{_FIX_NS_C}}}val/{{{_FIX_NS_C}}}numRef/{{{_FIX_NS_C}}}f")
        if _f_el is not None and _f_el.text:
            import re as _re_f
            _f_el.text = _re_f.sub(r'\d+$', str(_new_total + 1), _f_el.text)

        _cat_f_el = _ser.find(f"{{{_FIX_NS_C}}}cat/{{{_FIX_NS_C}}}strRef/{{{_FIX_NS_C}}}f")
        if _cat_f_el is not None and _cat_f_el.text:
            import re as _re_f2
            _cat_f_el.text = _re_f2.sub(r'\d+$', str(_new_total + 1), _cat_f_el.text)

        for _nc in _ser.findall(f".//{{{_FIX_NS_C}}}numCache"):
            _existing = {int(_pt.get("idx","0")): _pt for _pt in _nc.findall(f"{{{_FIX_NS_C}}}pt")}
            # ★ 遍历所有category，对每个2026月份：已有则更新，缺失则添加
            for _idx, _lbl in enumerate(_cats):
                _key = _fix_label_to_key(_lbl)
                if not _key or not _key.startswith("2026") or _key not in _data: continue
                if _idx in _existing:
                    _vn = _existing[_idx].find(f"{{{_FIX_NS_C}}}v")
                    if _vn is not None: _vn.text = f"{_data[_key]:.2f}"
                else:
                    _ptc = _nc.find(f"{{{_FIX_NS_C}}}ptCount")
                    if _ptc is not None: _ptc.set("val", str(_new_total))
                    _npt = _fix_et.SubElement(_nc, f"{{{_FIX_NS_C}}}pt")
                    _npt.set("idx", str(_idx))
                    _nv  = _fix_et.SubElement(_npt, f"{{{_FIX_NS_C}}}v")
                    _nv.text = f"{_data[_key]:.2f}"
                    print(f"  [{_sname}] 补充 {_lbl}: {_data[_key]:.2f}M")

        # 补充category strCache（每个series都要更新）
        for _ym, lbl in _cat_needs_add:
            _new_idx = _cats.index(lbl)
            for _sc in _ser.findall(f"{{{_FIX_NS_C}}}cat//{{{_FIX_NS_C}}}strCache"):
                _existing_cat_idxs = {int(_pt.get("idx","0"))
                                       for _pt in _sc.findall(f"{{{_FIX_NS_C}}}pt")}
                if _new_idx in _existing_cat_idxs: continue
                _ptc = _sc.find(f"{{{_FIX_NS_C}}}ptCount")
                if _ptc is not None: _ptc.set("val", str(len(_cats)))
                _npt = _fix_et.SubElement(_sc, f"{{{_FIX_NS_C}}}pt")
                _npt.set("idx", str(_new_idx))
                _nv  = _fix_et.SubElement(_npt, f"{{{_FIX_NS_C}}}v")
                _nv.text = lbl

    _fix_2026_months_all = sorted(k for k in (_fix_c_ape | _fix_d_ape | _fix_e_ape) if k.startswith("2026"))
    print(f"  Fix 1 完成: 预约2026={[round(_fix_c_ape.get(m,0),2) for m in _fix_2026_months_all]}")
    print(f"             签单2026={[round(_fix_d_ape.get(m,0),2) for m in _fix_2026_months_all]}")
    print(f"             批核2026={[round(_fix_e_ape.get(m,0),2) for m in _fix_2026_months_all]}")
    break


# ── Fix 2: E 图表环比标签 (Slide 2 Ann_YY/QD/PH) ──────────────────────────
# Issues fixed:
#   A. Ann_QD shapes are at y≈1026pt (inside Chart_YY zone) instead of Chart_QD zone
#   B. Only 3 Ann shapes per chart, but 5 bars need 4 MoM annotations
#   C. 4th MoM (Feb vs Jan) was silently dropped — now shown as 4th annotation
#   D. All repositioned to correct even distribution within each chart plot area
print("\n[Fix 2] E 环比标签 — 克隆缺失标注 + 全量重新定位")

def _fix_get_mom(block_letter):
    """Return [(month_num, pct_float)] sorted newest-first for all 2026 months ≥ Feb."""
    rows, header = _fix_read_s1_block(block_letter)
    if not header: return []
    ym_col = header[0]
    vals = []
    for rec in rows:
        ym = rec.get(ym_col, "")
        if not ym.startswith("2026"): continue
        try:
            mo = int(ym.split("-")[1])
        except (ValueError, IndexError): continue
        if mo < 2: continue          # Jan has no MoM vs Dec 2025 in this report
        pct_str = rec.get("环比增长%","").strip().replace("%","")
        if not pct_str: continue
        try:
            vals.append((mo, float(pct_str)))
        except ValueError: pass
    return sorted(vals, key=lambda x: -x[0])   # newest month first

_fix_c_mom = _fix_get_mom("C")
_fix_d_mom = _fix_get_mom("D")
_fix_e_mom = _fix_get_mom("E")
print(f"  MoM data: YY={_fix_c_mom}, QD={_fix_d_mom}, PH={_fix_e_mom}")

def _ensure_ann_shapes(slide, ann_name, n_needed):
    """
    Ensure there are exactly n_needed Ann shapes with the given name.
    If fewer exist, clone the last one to make up the difference.
    Returns list of shapes sorted by current top (arbitrary for same-y shapes).
    """
    from copy import deepcopy as _dc
    shs = [sh for sh in slide.shapes if sh.name == ann_name and sh.has_text_frame]
    n_existing = len(shs)
    if n_existing == 0:
        print(f"  ! {ann_name}: no shapes found, cannot create")
        return []
    if n_existing >= n_needed:
        return sorted(shs, key=lambda s: s.top)

    # Clone the last shape to fill gap
    template_sh = shs[-1]
    sp_tree = slide.shapes._spTree
    for _ in range(n_needed - n_existing):
        new_sp = _dc(template_sh._element)
        # Assign unique id
        all_ids = {int(sp.attrib.get("id", 0)) for sp in sp_tree.iter()
                   if sp.attrib.get("id")}
        new_id = max(all_ids) + 1 if all_ids else 999
        cNvPr = new_sp.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr")
        if cNvPr is None:
            cNvPr = new_sp.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}cNvPr")
        for elem in new_sp.iter():
            if elem.attrib.get("name") == ann_name and elem.attrib.get("id"):
                elem.set("id", str(new_id))
                break
        sp_tree.append(new_sp)
        shs.append(slide.shapes[-1])  # newly appended shape
        print(f"  {ann_name}: cloned new shape (id={new_id}), total={len(shs)}")

    return sorted(shs, key=lambda s: s.top)

def _reposition_and_label_anns(slide, chart_name, ann_name, mom_vals):
    """
    Full fix for one E chart's Ann annotations:
    1. Ensure enough Ann shapes exist (clone if needed)
    2. Compute correct y positions evenly in chart plot area (newest bar = top)
    3. Write correct MoM text and color for each shape
    4. Position x-coordinate at right side of chart for visibility
    """
    n_mom = len(mom_vals)
    if n_mom == 0:
        return

    chart_sh = next((sh for sh in slide.shapes if sh.name == chart_name and sh.has_chart), None)
    if chart_sh is None:
        print(f"  ! {chart_name} not found"); return

    n_bars = n_mom + 1   # 4 MoM pairs → 5 bars
    shs = _ensure_ann_shapes(slide, ann_name, n_mom)
    if not shs:
        return

    # Plot area bounds (empirically: ~12% top margin, ~5% bottom margin)
    plot_top    = chart_sh.top    + int(chart_sh.height * 0.12)
    plot_bottom = chart_sh.top    + int(chart_sh.height * 0.95)
    plot_h      = plot_bottom - plot_top
    bar_h       = plot_h / n_bars

    # x position: right side of chart area, ~80% width in
    ann_left_emu = chart_sh.left + int(chart_sh.width * 0.72)
    ann_width_emu = int(chart_sh.width * 0.28)

    # Place annotation i at midpoint between bar i and bar i+1 (from top)
    # Bar 0 = newest month (top), bar n_bars-1 = oldest (bottom)
    for i, sh in enumerate(shs[:n_mom]):
        y_mid_emu = plot_top + int((i + 1.0) * bar_h)   # midpoint between bar i and i+1
        new_top = y_mid_emu - sh.height // 2
        new_top = max(plot_top, min(new_top, plot_bottom - sh.height))
        sh.top  = new_top
        sh.left = ann_left_emu
        sh.width = ann_width_emu

        # Write text
        if i < len(mom_vals):
            mo, pct = mom_vals[i]
            arrow = "▲" if pct >= 0 else "▼"
            text  = f"{arrow} 环比 {pct:+.1f}%"
            color = "1A7A3F" if pct >= 0 else "C0392B"
        else:
            text, color = "", "666666"
        _fix_set_text_lxml(sh, text, color)
        print(f"  {ann_name}[{i}] → top={new_top//914:.0f}pt: {text!r}")

_reposition_and_label_anns(_SL_FORECAST, "Chart_YY", "Ann_YY", _fix_c_mom)
_reposition_and_label_anns(_SL_FORECAST, "Chart_QD", "Ann_QD", _fix_d_mom)
_reposition_and_label_anns(_SL_FORECAST, "Chart_PH", "Ann_PH", _fix_e_mom)

# ── Count actual bars for the Ann reposition (kept for compatibility) ──────
import csv as _ann_csv, re as _ann_re
_ann_months = []
_ann_in_blk = False
with open(CSV_S1, encoding="utf-8-sig") as _ann_f:
    for _ann_row in _ann_csv.reader(_ann_f):
        if not _ann_row: continue
        _ann_first = _ann_row[0].strip()
        if _ann_first.startswith("C.") and "月度业绩" in _ann_first: _ann_in_blk = True; continue
        if not _ann_in_blk: continue
        if _ann_first.startswith("📌"): continue
        if _ann_re.match(r"^[A-Z]\.", _ann_first) and not _ann_first.startswith("C."): break
        if not _ann_first: break
        if _ann_re.match(r"^2026-\d{2}$", _ann_first): _ann_months.append(_ann_first)
_n_e_bars = len(_ann_months)
print(f"  [Ann] {_n_e_bars} E-chart bars, {len(_fix_c_mom)} MoM annotations each")


# ── Fix 3: G 永明汇报表 EG行 / Sub Total行 (Slide 3) ──────────────────────
print("\n[Fix 3] G表 — 强制写入EG行 / Sub Total行")

def _fix_read_h_block():
    rows, row_names, header = [], [], None
    in_block = False
    with open(CSV_S1, encoding="utf-8-sig") as _f:
        for _row in _fix_csv.reader(_f):
            if not _row: continue
            first = _row[0].strip()
            if "永明业绩汇报数据" in first and "Sunlife" in first:
                in_block = True; continue
            if not in_block: continue
            if first.startswith("📌"): continue
            if first == "牌照":
                header = [c.strip() for c in _row]; continue
            if not first: break
            if header is None: continue
            row_data = {}
            for col, val in zip(header[1:], _row[1:]):
                try: row_data[col] = float(str(val).replace(",","").strip())
                except (ValueError, AttributeError): row_data[col] = 0.0
            rows.append(row_data)
            row_names.append(first)
    return rows, row_names, header

_fix_h_rows, _fix_h_names, _fix_h_hdr = _fix_read_h_block()
_fix_months_h  = [c for c in (_fix_h_hdr[1:] if _fix_h_hdr else []) if _fix_re.match(r"^\d{4}-\d{2}$", c)]
_fix_extras_h  = [c for c in (_fix_h_hdr[1:] if _fix_h_hdr else []) if c and not _fix_re.match(r"^\d{4}-\d{2}$", c)]

def _fix_resolve(alias):
    # Rolling window: use last 4 months (same as _resolve_col_g fix)
    _rolling_h = _fix_months_h[-4:] if len(_fix_months_h) >= 4 else _fix_months_h
    if alias.startswith("m"):
        i = int(alias[1:]); return _rolling_h[i] if i < len(_rolling_h) else None
    if alias.startswith("e"):
        i = int(alias[1:]); return _fix_extras_h[i]  if i < len(_fix_extras_h)  else None
    return None

def _fix_fmt(v): return f"{v/1e6:.2f}M" if v > 0 else "0M"

# EG行坐标 (y≈2555240)
_FIX_EG_COORDS = [
    ("m0", 734060, 2555240), ("m1", 2442845, 2555240),
    ("m2", 4234815, 2555240), ("m3", 6050915, 2538730),
    ("e0", 7709535, 2536190), ("e1", 9572625, 2536190),
]
# Sub Total行坐标 (y≈2807970)
_FIX_SUB_COORDS = [
    ("m0", 740410, 2807970), ("m1", 2449195, 2807970),
    ("m2", 4551045, 2785110), ("m3", 6367145, 2768600),
    ("e0", 7715885, 2788920), ("e1", 9578975, 2788920),
]

def _fix_write_row(slide, coords, row_data, row_label):
    ok_count = 0
    for alias, lx, ty in coords:
        col = _fix_resolve(alias)
        if col is None: continue
        text = _fix_fmt(row_data.get(col, 0.0))
        ok = _fix_set_at(slide, lx, ty, text, tol=35000)
        ok_count += ok
    print(f"  {row_label}: {ok_count}/{len(coords)} 格写入成功")

_eg_idx  = next((i for i,n in enumerate(_fix_h_names) if n == "EG"),        None)
_sub_idx = next((i for i,n in enumerate(_fix_h_names) if n == "Sub Total"), None)

if _eg_idx  is not None: _fix_write_row(_SL_SUNLIFE, _FIX_EG_COORDS,  _fix_h_rows[_eg_idx],  "EG")
if _sub_idx is not None: _fix_write_row(_SL_SUNLIFE, _FIX_SUB_COORDS, _fix_h_rows[_sub_idx], "Sub Total")

# ── Fix 4: K 甜甜圈标签字体缩小 (Slide 5 Chart 0) ─────────────────────────
print("\n[Fix 4] K 甜甜圈 — 数据标签字体缩小")
_fix_slide5 = slides[4]
for _sh5 in _fix_slide5.shapes:
    if not _sh5.has_chart or _sh5.name != "Chart 0": continue
    _root5 = _sh5.chart.part._element
    _patched_sz = 0
    for _dLbls in _root5.findall(f".//{{{_FIX_NS_C}}}dLbls"):
        for _rpr in _dLbls.findall(f".//{{{_FIX_NS_A}}}rPr"):
            old_sz = _rpr.get("sz")
            if old_sz and int(old_sz) > 900:
                _rpr.set("sz", "800")   # 8pt
                _patched_sz += 1
        # 也检查 txPr/p/pPr/defRPr
        for _defrpr in _dLbls.findall(f".//{{{_FIX_NS_A}}}defRPr"):
            old_sz = _defrpr.get("sz")
            if old_sz and int(old_sz) > 900:
                _defrpr.set("sz", "800")
                _patched_sz += 1
    print(f"  Chart 0 甜甜圈: {_patched_sz} 处字体改为8pt")
    break

print("\n[Integrated Fixes] 全部完成 ✓")
print("="*70 + "\n")
# ============================================================================
# END INTEGRATED FIXES
# ============================================================================


# ============================================================================
# FIX A: Label_QD 遮挡 Chart_YY 问题 (Slide 2)
# Label_QD (E 签单标题框) top=1987pt，但 Chart_YY 底部=2360pt → 重叠372pt
# 修复：将 Label_QD 移到 Chart_QD 正上方（Chart_QD.top - label.h - gap）
# ============================================================================
print("\n[Fix A] Label_QD 位置修复 — 移出 Chart_YY 覆盖区域")
def _fix_label_qd_position(slide):
    from pptx.util import Pt
    # 找到相关 shape
    chart_yy = next((sh for sh in slide.shapes if sh.name == "Chart_YY" and sh.has_chart), None)
    chart_qd = next((sh for sh in slide.shapes if sh.name == "Chart_QD" and sh.has_chart), None)
    label_qd = next((sh for sh in slide.shapes if sh.name == "Label_QD"), None)
    label_ph = next((sh for sh in slide.shapes if sh.name == "Label_PH"), None)
    chart_ph = next((sh for sh in slide.shapes if sh.name == "Chart_PH" and sh.has_chart), None)

    if label_qd is None or chart_qd is None:
        print("  ! Label_QD or Chart_QD not found")
        return

    # 目标: Label_QD.top = Chart_YY.bottom + 62pt (与 Label_PH 距 Chart_QD 的间距一致)
    chart_yy_bottom = (chart_yy.top + chart_yy.height) if chart_yy else None
    chart_qd_bottom = chart_qd.top + chart_qd.height

    gap_pt = 62  # 914 EMU per point
    gap_emu = gap_pt * 914

    if chart_yy_bottom is not None:
        new_label_qd_top = chart_yy_bottom + gap_emu
        old_top = label_qd.top
        label_qd.top = new_label_qd_top
        print(f"  Label_QD: top {old_top//914:.0f}pt → {new_label_qd_top//914:.0f}pt ✓")
    else:
        print("  ! Chart_YY not found, cannot compute Label_QD position")
        return

    # 同步修复 Label_PH 和 Chart_PH：
    # Label_PH 应在 Chart_QD 底部 + gap
    if label_ph is not None:
        new_label_ph_top = chart_qd_bottom + gap_emu
        old_ph = label_ph.top
        label_ph.top = new_label_ph_top
        print(f"  Label_PH: top {old_ph//914:.0f}pt → {new_label_ph_top//914:.0f}pt ✓")

        # Chart_PH: Label_PH.top + label_ph.h + gap
        if chart_ph is not None:
            new_chart_ph_top = new_label_ph_top + label_ph.height + gap_emu
            old_cph = chart_ph.top
            chart_ph.top = new_chart_ph_top
            print(f"  Chart_PH: top {old_cph//914:.0f}pt → {new_chart_ph_top//914:.0f}pt ✓")

_fix_label_qd_position(_SL_FORECAST)

# ============================================================================
# FIX B: F 图 2026批核APE路径 — 写入5月实际批核 APE (Slide 2, Chart 1)
# 实际批核系列 idx=4 (5月) 值为 None，需写入 S1 E block 的5月APE
# ============================================================================

# ============================================================================
# FIX B (enhanced): F 图 — 写入5月实际值 + 清除5月预测值 + 移动预测边框
# ============================================================================
print("\n[Fix B] F 图 5月实际写入 + 预测边框右移")

def _fix_f_chart_may_and_forecast(slide):
    """
    1. Remove externalData OLE from F chart (Chart 1) so numCache is used.
    2. Write actual May APE into 实际批核 series idx=4.
    3. Clear 预测 APE series idx=4 (May now has actual, not forecast).
    4. Shift the forecast shading shape (Shape 63) and label (Text 64) right
       by one bar-width so they start at June instead of May.
    """
    import csv as _ffcm_csv, re as _ffcm_re
    from lxml import etree as _ffcm_et
    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"

    # ── F chart data fix ─────────────────────────────────────────────────
    shp = _find_shape(slide, "Chart 1")
    if shp is None or not shp.has_chart:
        print("  ! Chart 1 not found"); return

    root = shp.chart.part._element

    # Remove externalData if present
    ext_data = root.find(f"{{{NS_C}}}externalData")
    if ext_data is not None:
        root.remove(ext_data)
        print("  F chart: removed externalData OLE reference")

    # Read S1 E block for all available months APE
    ape_by_mo = {}
    in_blk = False; hdr = None
    with open(CSV_S1, encoding="utf-8-sig") as _f:
        for _row in _ffcm_csv.reader(_f):
            if not _row: continue
            first = _row[0].strip()
            if first.startswith("E.") and "月度业绩" in first: in_blk = True; continue
            if not in_blk: continue
            if first.startswith("📌"): continue
            if _ffcm_re.match(r"^[A-Z]\.", first) and not first.startswith("E."): break
            if hdr is None and any("年月" in c for c in _row):
                hdr = [c.strip() for c in _row]; continue
            if not first: break
            if hdr and _ffcm_re.match(r"^2026-\d{2}$", first):
                mo = int(first[5:7])
                try:
                    ape_idx = hdr.index("APE") if "APE" in hdr else 2
                    ape_by_mo[mo] = float(_row[ape_idx].replace(",", "")) / 1e6
                except: pass

    # Months with actual data
    actual_months = sorted(ape_by_mo.keys())
    n_actual = len(actual_months)
    print(f"  F chart: {n_actual} actual months ({actual_months})")

    sers = root.findall(f".//{{{NS_C}}}ser")
    for ser in sers:
        tx = ser.find(f".//{{{NS_C}}}tx")
        sname = ""
        if tx is not None:
            v_el = tx.find(f".//{{{NS_C}}}v")
            if v_el is not None: sname = v_el.text or ""

        for nc in ser.findall(f".//{{{NS_C}}}numCache"):
            pts = {p.get("idx"): p for p in nc.findall(f"{{{NS_C}}}pt")}

            if "实际" in sname or ("批核" in sname and "预测" not in sname):
                # Write all actual months
                for mo in actual_months:
                    idx_str = str(mo - 1)  # idx=0=Jan, idx=1=Feb...
                    if idx_str in pts:
                        v_el = pts[idx_str].find(f"{{{NS_C}}}v")
                        if v_el is None:
                            v_el = _ffcm_et.SubElement(pts[idx_str], f"{{{NS_C}}}v")
                        old = v_el.text
                        v_el.text = f"{ape_by_mo[mo]:.2f}"
                        if old != v_el.text:
                            print(f"  F 实际 idx={idx_str} ({mo}月): {old!r} → {v_el.text}M")
                    else:
                        # Create the pt
                        pt_el = _ffcm_et.SubElement(nc, f"{{{NS_C}}}pt")
                        pt_el.set("idx", idx_str)
                        v_sub = _ffcm_et.SubElement(pt_el, f"{{{NS_C}}}v")
                        v_sub.text = f"{ape_by_mo[mo]:.2f}"
                        print(f"  F 实际 idx={idx_str} ({mo}月): added {v_sub.text}M")

            elif "预测" in sname:
                # Clear forecast values for months that have actual data
                for mo in actual_months:
                    idx_str = str(mo - 1)
                    if idx_str in pts:
                        v_el = pts[idx_str].find(f"{{{NS_C}}}v")
                        if v_el is not None:
                            nc.remove(pts[idx_str])  # remove the pt entirely
                            print(f"  F 预测 idx={idx_str} ({mo}月): cleared (actual exists)")

    # ── Forecast shading shape position fix ──────────────────────────────
    # The shaded forecast rectangle and its label need to start at the FIRST
    # month WITHOUT actual data (i.e. n_actual+1 month bar).
    # Chart 1 layout: 12 bars, plot area = chart_left+10%..chart_right-3%
    chart_sh = _find_shape(slide, "Chart 1")
    if chart_sh is None: return

    chart_left_pt = chart_sh.left // 914
    chart_w_pt    = chart_sh.width // 914
    plot_left_pt  = chart_left_pt + int(chart_w_pt * 0.105)
    plot_right_pt = chart_left_pt + chart_w_pt - int(chart_w_pt * 0.03)
    plot_w_pt     = plot_right_pt - plot_left_pt
    bar_w_pt      = plot_w_pt / 12

    # Forecast zone starts at bar (n_actual+1), i.e. first month without actual
    # bar index is 0-based: bar 0=Jan, bar 4=May (if n_actual=5, forecast starts at bar 5=Jun)
    forecast_bar_idx = n_actual  # 0-based index of first forecast bar
    new_shade_left_pt = int(plot_left_pt + forecast_bar_idx * bar_w_pt)
    new_shade_left_emu = new_shade_left_pt * 914

    print(f"  F forecast zone: starts at bar {forecast_bar_idx} ({forecast_bar_idx+1}月)")
    print(f"  Shape 63 target left: {new_shade_left_pt}pt ({new_shade_left_emu} EMU)")

    # Move Shape 63 (forecast shade) and its width
    for sh in slide.shapes:
        if sh.name == "Shape 63":
            old_left = sh.left
            old_w = sh.width
            delta = new_shade_left_emu - old_left
            sh.left = new_shade_left_emu
            # Shrink width by delta to keep right edge fixed
            sh.width = max(old_w - delta, 914)  # at least 1pt
            print(f"  Shape 63: left {old_left//914:.0f}→{new_shade_left_pt}pt width {old_w//914:.0f}→{sh.width//914:.0f}pt")
            break

    # Move Text 64 (预测区间 label) to be centered in the forecast zone
    forecast_zone_w_emu = int(bar_w_pt * (12 - forecast_bar_idx)) * 914
    for sh in slide.shapes:
        if sh.name == "Text 64" and sh.has_text_frame:
            sh.left  = new_shade_left_emu
            sh.width = forecast_zone_w_emu
            print(f"  Text 64: left={new_shade_left_pt}pt width={forecast_zone_w_emu//914:.0f}pt")
            break

_fix_f_chart_may_and_forecast(_SL_FORECAST)

# ============================================================================
# FIX G: 永明汇报 G 表 — 4个月滚动展示（更新表头月份标签）
# 
# G 表有 4 个月份数据列（m0-m3），数据内容由 _resolve_col_g/_fix_resolve
# 以 _h_months[-4:] 滚动窗口填充（Feb-May 当有5个月时）。
# 但列头文本形状（Text36/37/38 + Text38-Apr位置）仍显示固定的 Jan/Feb/Mar/Apr 标签。
# 此处将其更新为动态月份标签，与 rolling window 保持一致。
# ============================================================================
# ── Fix G: 永明汇报 G 表月份列头滚动更新 ────────────────────────────────────
# Updates the 4 month column header text shapes to match the rolling window
# (_h_months[-4:] → e.g. Feb-26 / Mar-26 / Apr-26 / May-26 when 5 months available).
print("\n[Fix G] G表月份列头 — 滚动更新为最近4个月标签")

def _fix_g_table_rolling_headers(slide, h_months):
    """Update G table column header shapes to show the rolling last-4 months."""
    if not h_months:
        print("  ! h_months empty"); return

    _MO_ABBR_G = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                  7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

    rolling = h_months[-4:] if len(h_months) >= 4 else h_months
    # Build target labels: "Feb-26 批核APE（M）"
    labels = []
    for ym in rolling:
        try:
            mo = int(ym[5:7]); yr = ym[2:4]
            labels.append(f"{_MO_ABBR_G[mo]}-{yr} 批核APE（M）")
        except: labels.append(ym)

    print(f"  Rolling window: {rolling}")
    print(f"  Header labels:  {labels}")

    # Header shapes identified by approximate x-position (EMU) and top ~1700-1800pt
    # m0≈784860, m1≈2430780, m2≈4222750, m3≈6478905 (from template scan)
    HEADER_X = [784860, 2430780, 4222750, 6478905]
    TOP_MIN = 1700 * 914; TOP_MAX = 1800 * 914
    TOL = 250000  # ±273pt tolerance

    for target_x, new_label in zip(HEADER_X, labels[:4]):
        best_sh = None; best_dist = 9999999
        for sh in slide.shapes:
            if sh.left is None or sh.top is None: continue
            if not (TOP_MIN <= sh.top <= TOP_MAX): continue
            if not sh.has_text_frame: continue
            txt = sh.text_frame.text.strip()
            # Only match shapes that look like month headers
            if not any(m in txt for m in ['Jan','Feb','Mar','Apr','May','Jun',
                                          'Jul','Aug','Sep','Oct','Nov','Dec']):
                continue
            dist = abs(sh.left - target_x)
            if dist < TOL and dist < best_dist:
                best_sh = sh; best_dist = dist
        if best_sh is not None:
            old = best_sh.text_frame.text.strip()
            _fix_set_text_lxml(best_sh, new_label, "FFFFFF")
            print(f"  G m{HEADER_X.index(target_x)}: {old!r} → {new_label!r} (x≈{best_sh.left//914}pt)")
        else:
            print(f"  ! G header x≈{target_x//914}pt: not found")

_fix_g_table_rolling_headers(_SL_SUNLIFE, _h_months)




# ============================================================================
# FIX C: Z 银行月度走势 — 移除 externalData OLE (Slide 10)
# 
# 根因：Chart_YY/QD/PH 有 <c:externalData> OLE 引用，PowerPoint 忽略 numCache
# 直接读取嵌入 xlsx（内含错误的原始值）。修复：删除 externalData 节点，
# 并收集正确的 xlsx bytes 供 post-save 阶段嵌入。
# ============================================================================
print("\n[Fix C] Z 银行月度走势 — 移除 externalData OLE")

def _fix_z_remove_ole_and_embed(slide, chart_name, ape_block, cnt_block):
    """Remove externalData OLE from Z chart; collect xlsx bytes for post-save embed."""
    import csv as _fzc_csv, re as _fzc_re, io as _fzc_io
    from lxml import etree as _fzc_et
    NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    shp = _find_shape(slide, chart_name)
    if shp is None or not shp.has_chart:
        print(f"  ! {chart_name} not found"); return None
    root = shp.chart.part._element

    # Remove externalData
    ext_data = root.find(f"{{{NS_C}}}externalData")
    if ext_data is not None:
        root.remove(ext_data)
        print(f"  {chart_name}: removed externalData OLE")

    KAS = ["民生银行", "平安银行"]
    MO_ZH = {1:"1月",2:"2月",3:"3月",4:"4月",5:"5月",6:"6月",
              7:"7月",8:"8月",9:"9月",10:"10月",11:"11月",12:"12月"}

    def _read_bk(block):
        res = {}; in_b = False; hdr = None
        with open(CSV_S2, encoding="utf-8-sig") as _f:
            for _r in _fzc_csv.reader(_f):
                if not _r: continue
                first = _r[0].strip()
                if first.startswith(block): in_b = True; continue
                if not in_b: continue
                if first.startswith("📌"): continue
                if first == "KEY ACCOUNT": hdr = [c.strip() for c in _r]; continue
                if not first and hdr: break
                if hdr and first in KAS:
                    kd = {}
                    for col, val in zip(hdr[1:], _r[1:]):
                        if _fzc_re.match(r"^2026-\d{2}$", col):
                            try: kd[int(col[5:7])] = float(val.replace(",",""))
                            except: kd[int(col[5:7])] = 0.0
                    res[first] = kd
        return res

    ape_d = _read_bk(ape_block)
    months = sorted(set().union(*[set(v.keys()) for v in ape_d.values()]))

    try:
        import openpyxl as _opx
        wb = _opx.Workbook(); ws = wb.active; ws.title = "ChartData"
        ws.cell(1, 1, "月份")
        for j, ka in enumerate(KAS): ws.cell(1, j+2, ka)
        for i, mo in enumerate(months):
            ws.cell(i+2, 1, MO_ZH.get(mo, f"{mo}月"))
            for j, ka in enumerate(KAS):
                ws.cell(i+2, j+2, round(ape_d.get(ka, {}).get(mo, 0) / 1e6, 4))
        buf = _fzc_io.BytesIO(); wb.save(buf)
        print(f"  {chart_name}: xlsx prepared ({len(months)} months)")
        return buf.getvalue(), shp.chart.part
    except Exception as _e:
        print(f"  {chart_name}: xlsx prep error: {_e}"); return None

_Z_XLSX_DATA = []
for _zn, _zape, _zcnt in [("Chart_YY","P-APE","P-件数"),
                           ("Chart_QD","Q-APE","Q-件数"),
                           ("Chart_PH","R-APE","R-件数")]:
    _res = _fix_z_remove_ole_and_embed(_SL_BK, _zn, _zape, _zcnt)
    if _res: _Z_XLSX_DATA.append((_zn, _res[0], _res[1]))


prs.save(OUT_PPT)
print(f"\n✅ Saved: {OUT_PPT}")

# ── Post-save: fix Chart_JM (L chart) OLE embed via zip patch ──────────────
# PowerPoint ignores numCache when chart has an externalData/OLE reference.
# We already removed externalData from the XML above; now we also need to
# replace the chart's rels file to point to a valid embedded xlsx.
if _L_XLSX_BYTES:
    print("\n--- POST-SAVE: Fix Chart_JM OLE embed ---")
    import zipfile as _zf_post, io as _io_post, shutil as _shu_post, os as _os_post

    _tmp = OUT_PPT + ".tmp"
    _WB_NAME = "Workbook_JM.xlsx"

    # Find chart16.xml (the one corresponding to Chart_JM on slide 5)
    # Identify by checking which chart file has no xlsx rel (was OLE external)
    with _zf_post.ZipFile(OUT_PPT, "r") as _zin:
        _all = {n: _zin.read(n) for n in _zin.namelist()}

    # Find the chart file that belongs to Chart_JM: it's the one on slide5
    # slide5 rels → find chart target
    _slide5_rels_path = None
    for _n in _all:
        if "slides/_rels/slide5.xml.rels" in _n:
            _slide5_rels_path = _n
            break

    _target_chart_xml = None
    if _slide5_rels_path:
        import xml.etree.ElementTree as _ET_post
        _rels_root = _ET_post.fromstring(_all[_slide5_rels_path])
        # slide5 has two chart rels; Chart_JM = the one linked to shape "Chart_JM"
        # Heuristic: Chart_JM is chart16 (has 4 series with 8 categories)
        # Verify by checking numCache ptCount=8 in each candidate chart
        _chart_rels = [
            r.get("Target","").replace("../","ppt/")
            for r in _rels_root
            if "chart" in r.get("Type","").lower()
        ]
        for _cr in _chart_rels:
            if _cr in _all:
                _c_xml = _all[_cr].decode("utf-8", errors="replace")
                if "BK业务" in _c_xml or "永明经代" in _c_xml:
                    _target_chart_xml = _cr
                    break

    if _target_chart_xml:
        _chart_base = _target_chart_xml.replace("ppt/charts/", "").replace(".xml","")
        _rels_path  = f"ppt/charts/_rels/{_chart_base}.xml.rels"
        _xlsx_path  = f"ppt/embeddings/{_WB_NAME}"

        # Replace chart rels: point to new xlsx
        _new_rels = (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            f"<Relationship Id=\"rId1\" "
            f"Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/package\" "
            f"Target=\"../embeddings/{_WB_NAME}\"/>"
            "</Relationships>"
        )
        _all[_rels_path] = _new_rels.encode("UTF-8")
        _all[_xlsx_path] = _L_XLSX_BYTES

        # Update Content_Types.xml
        _ct = _all["[Content_Types].xml"].decode("utf-8")
        if _WB_NAME not in _ct:
            _ct_override = (
                f'<Override PartName="/ppt/embeddings/{_WB_NAME}" '
                f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"/>'
            )
            _ct = _ct.replace("</Types>", _ct_override + "</Types>")
            _all["[Content_Types].xml"] = _ct.encode("utf-8")

        with _zf_post.ZipFile(_tmp, "w", _zf_post.ZIP_DEFLATED) as _zout:
            for _n, _data in _all.items():
                _zout.writestr(_n, _data)
        _os_post.replace(_tmp, OUT_PPT)
        print(f"  [L OLE fix] {_target_chart_xml} → embedded {_WB_NAME} ({len(_L_XLSX_BYTES)} bytes)")
        print(f"  ✅ L chart OLE fix applied")
    else:
        print("  ! [L OLE fix] could not identify Chart_JM file in zip, skip")
else:
    print("  [L OLE fix] No xlsx bytes available, skip")

# ── POST-SAVE: N图 & H图 embedded xlsx 全量更新 ──────────────────────────────
# PowerPoint 读 embedded xlsx 而非 numCache。
# N图(周度APE): Workbook6.xlsx 只有W01-W12，导致W13-W17被截断/显示旧值
# H图(永明月度): Workbook4.xlsx Apr行是旧值，已在此处一并修复
print("\n--- POST-SAVE: N图/H图 embedded xlsx 全量更新 ---")
try:
    import zipfile as _zf_nh, io as _io_nh, csv as _csv_nh
    import openpyxl as _opx_nh, xml.etree.ElementTree as _ET_nh, os as _os_nh

    with _zf_nh.ZipFile(OUT_PPT, "r") as _zin_nh:
        _nh_all = {n: _zin_nh.read(n) for n in _zin_nh.namelist()}

    # ── 读取 S3 A块（N图数据源）────────────────────────────────────────────
    _n_data = {"预约": {}, "签单": {}, "递交": {}, "批核": {}}
    with open(CSV_S3, encoding="utf-8-sig") as _f_nh:
        _nh_lines = list(_csv_nh.reader(_f_nh))
    _nh_hdr = _nh_lines[2]   # 阶段, 2026W01, ..., 2026W17, 合计
    _nh_wks = [h for h in _nh_hdr[1:] if h.startswith("2026W")]
    for _nh_row in _nh_lines[3:7]:
        _stage = _nh_row[0]
        if _stage not in _n_data: continue
        for _wi, _wk in enumerate(_nh_wks, 1):
            try: _n_data[_stage][_wk] = round(float(_nh_row[_wi].replace(",",""))/1e6, 2)
            except: _n_data[_stage][_wk] = 0.0

    # ── 读取 S2 F/G/H块（H图数据源）────────────────────────────────────────
    def _nh_s2_total(block_label):
        _in_b = False; _hdr2 = None
        with open(CSV_S2, encoding="utf-8-sig") as _f2:
            for _row2 in _csv_nh.reader(_f2):
                if not _row2: continue
                _first2 = _row2[0].strip()
                if _first2.startswith(block_label): _in_b = True; continue
                if not _in_b: continue
                if _first2.startswith("📌"): continue
                if _first2 == "业务细分": _hdr2 = [c.strip() for c in _row2]; continue
                if _first2 == "合计" and _hdr2:
                    result2 = {}
                    for _col2, _val2 in zip(_hdr2[1:], _row2[1:]):
                        try: result2[_col2] = float(_val2.replace(",","").strip())
                        except: result2[_col2] = 0.0
                    return result2
                if not _first2 and _hdr2: break
        return {}

    _h_f_ape = _nh_s2_total("F-APE")
    _h_g_ape = _nh_s2_total("G-APE")
    _h_h_ape = _nh_s2_total("H-APE")
    _h_months = sorted(
        m for m in _nh_s2_total("F-APE").keys()
        if __import__('re').match(r'^2026-\d{2}$', m)
    )
    if not _h_months:
        _h_months = ["2026-01","2026-02","2026-03","2026-04","2026-05"]
    _MONTH_ABBR_H = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                     7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    _h_labels = [
        f"{m[2:4]}-{_MONTH_ABBR_H[int(m[5:7])]}"
        for m in _h_months
    ]

    # ── 定位 slide6(N图) 和 slide3(H图) 的 chart → xlsx 文件名 ─────────────
    _nh_prs  = _ET_nh.fromstring(_nh_all["ppt/presentation.xml"])
    _nh_sids = [el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                for el in _nh_prs.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId")]
    _nh_rels_root = _ET_nh.fromstring(_nh_all["ppt/_rels/presentation.xml.rels"])
    _nh_rels = {el.get("Id"): el.get("Target") for el in _nh_rels_root}

    def _nh_get_slide_chart_xlsx(slide_idx):
        """返回 slide_idx(0-based) 对应的所有 chart→xlsx 映射 {xlsx_path: chart_name}"""
        _sf = "ppt/" + _nh_rels.get(_nh_sids[slide_idx], "").lstrip("./")
        _srf = _sf.replace("slides/slide", "slides/_rels/slide").replace(".xml", ".xml.rels")
        if _srf not in _nh_all: return {}
        _sr = _ET_nh.fromstring(_nh_all[_srf])
        _result = {}
        for _rel in _sr:
            if "chart" not in _rel.get("Type","").lower(): continue
            _ct = "ppt/" + _rel.get("Target","").lstrip("../")
            _crf = _ct.replace("charts/chart","charts/_rels/chart").replace(".xml",".xml.rels")
            if _crf not in _nh_all: continue
            _cr = _ET_nh.fromstring(_nh_all[_crf])
            for _cr_rel in _cr:
                _tgt = _cr_rel.get("Target","")
                if "embeddings" in _tgt and _tgt.endswith(".xlsx"):
                    _xlsx_f = "ppt/" + _tgt.lstrip("../")
                    _result[_xlsx_f] = _ct
        return _result

    # slide 6 (index 5) → N图; slide 3 (index 2) → H图
    _n_xlsx_map = _nh_get_slide_chart_xlsx(5)
    _h_xlsx_map = _nh_get_slide_chart_xlsx(2)

    # ── 重建 N图 xlsx ────────────────────────────────────────────────────────
    for _nx_path in _n_xlsx_map:
        _wb_n = _opx_nh.Workbook(); _ws_n = _wb_n.active; _ws_n.title = "Sheet1"
        _ws_n.cell(1,1,""); _ws_n.cell(1,2,"预约"); _ws_n.cell(1,3,"签单")
        _ws_n.cell(1,4,"递交"); _ws_n.cell(1,5,"批核")
        for _ri, _wk in enumerate(_nh_wks, 2):
            _ws_n.cell(_ri, 1, _wk.replace("2026",""))
            _ws_n.cell(_ri, 2, _n_data["预约"].get(_wk, 0))
            _ws_n.cell(_ri, 3, _n_data["签单"].get(_wk, 0))
            _ws_n.cell(_ri, 4, _n_data["递交"].get(_wk, 0))
            _ws_n.cell(_ri, 5, _n_data["批核"].get(_wk, 0))
        _buf_n = _io_nh.BytesIO(); _wb_n.save(_buf_n)
        _nh_all[_nx_path] = _buf_n.getvalue()
        print(f"  N图 {_nx_path}: {len(_nh_wks)}周数据写入 ✓")

    # 同步更新 N图 numCache（确保与xlsx一致）
    for _si_n, _sl_n in enumerate(prs.slides):
        if _si_n != 5: continue
        for _sh_n in _sl_n.shapes:
            if not _sh_n.has_chart or _sh_n.name != "Chart 0": continue
            _root_n = _sh_n.chart.part._element
            _ser_order = ["预约","签单","递交","批核"]
            for _sni, _ser_n in enumerate(_root_n.findall(f".//{{{_FIX_NS_C}}}ser")):
                _tx_n = _ser_n.find(f".//{{{_FIX_NS_C}}}tx")
                _sname_n = _tx_n.find(f".//{{{_FIX_NS_C}}}v").text if _tx_n is not None else ""
                _stage_n = next((s for s in _ser_order if s in _sname_n), None)
                if _stage_n is None and _sni < len(_ser_order):
                    _stage_n = _ser_order[_sni]
                if _stage_n is None: continue
                for _nc_n in _ser_n.findall(f".//{{{_FIX_NS_C}}}numCache"):
                    for _pt_n in _nc_n.findall(f"{{{_FIX_NS_C}}}pt"):
                        _idx_n = int(_pt_n.get("idx","0"))
                        if _idx_n < len(_nh_wks):
                            _vn_n = _pt_n.find(f"{{{_FIX_NS_C}}}v")
                            if _vn_n is not None:
                                _vn_n.text = str(_n_data[_stage_n][_nh_wks[_idx_n]])
            break

    # ── 重建 H图 xlsx ────────────────────────────────────────────────────────
    for _hx_path in _h_xlsx_map:
        _wb_h = _opx_nh.Workbook(); _ws_h = _wb_h.active; _ws_h.title = "Sheet1"
        _ws_h.cell(1,1,""); _ws_h.cell(1,2,"预约 APE(M)")
        _ws_h.cell(1,3,"签单 APE(M)"); _ws_h.cell(1,4,"批核 APE(M)")
        for _ri_h, (_cat_h, _ym_h) in enumerate(zip(_h_labels, _h_months), 2):
            _ws_h.cell(_ri_h, 1, _cat_h)
            _ws_h.cell(_ri_h, 2, round(_h_f_ape.get(_ym_h, 0)/1e6, 2))
            _ws_h.cell(_ri_h, 3, round(_h_g_ape.get(_ym_h, 0)/1e6, 2))
            _ws_h.cell(_ri_h, 4, round(_h_h_ape.get(_ym_h, 0)/1e6, 2))
        _buf_h = _io_nh.BytesIO(); _wb_h.save(_buf_h)
        _nh_all[_hx_path] = _buf_h.getvalue()
        _last_m = _h_months[-1] if _h_months else 'N/A'
        print(f"  H图 {_hx_path}: {len(_h_months)}个月数据写入，最新月={_last_m}，批核={round(_h_h_ape.get(_last_m,0)/1e6,2)}M ✓")

    # ── 重新打包 ─────────────────────────────────────────────────────────────
    # 先保存更新了numCache的prs到文件（N图numCache已在内存中修改）
    prs.save(OUT_PPT)   # 覆盖保存（numCache已更新）
    with _zf_nh.ZipFile(OUT_PPT, "r") as _zin2:
        _nh_all2 = {n: _zin2.read(n) for n in _zin2.namelist()}
    # 把新的xlsx覆盖进去
    for _k, _v in _nh_all.items():
        if "embeddings" in _k and _k.endswith(".xlsx"):
            _nh_all2[_k] = _v
    _tmp_nh = OUT_PPT + ".nhtmp"
    with _zf_nh.ZipFile(_tmp_nh, "w", _zf_nh.ZIP_DEFLATED) as _zout_nh:
        for _n, _d in _nh_all2.items(): _zout_nh.writestr(_n, _d)
    _os_nh.replace(_tmp_nh, OUT_PPT)
    print("  N图/H图 embedded xlsx 全量更新完成 ✓")
except Exception as _e_nh:
    print(f"  ⚠ N图/H图更新失败: {_e_nh}")
    import traceback; traceback.print_exc()

# ── Post-save: G表全行（列索引法，在2nd prs.save后，最终保障）─────────────────
# 作为最后保障再写一次，防止prs.save覆盖了内存写入
# 使用列索引法（与_g_write_all_rows相同），通过XML直接操作
print("\n--- POST-SAVE: G表 列索引法最终写入 ---")
try:
    import zipfile as _zf_gf, csv as _csv_gf, re as _re_gf
    import xml.etree.ElementTree as _ET_gf

    # 读S1 H block
    def _gf_read_h():
        rows, names, header = [], [], None
        in_block = False
        with open(CSV_S1, encoding="utf-8-sig") as _f:
            for _row in _csv_gf.reader(_f):
                if not _row: continue
                first = _row[0].strip()
                if "永明业绩汇报数据" in first and "Sunlife" in first:
                    in_block = True; continue
                if not in_block: continue
                if first.startswith("📌"): continue
                if first == "牌照": header = [c.strip() for c in _row]; continue
                if not first: break
                if header is None: continue
                rd = {}
                for col, val in zip(header[1:], _row[1:]):
                    try: rd[col] = float(str(val).replace(",","").strip())
                    except: rd[col] = 0.0
                rows.append(rd); names.append(first)
        months = [c for c in (header[1:] if header else []) if _re_gf.match(r"^\d{4}-\d{2}$", c)]
        extras = [c for c in (header[1:] if header else []) if c and not _re_gf.match(r"^\d{4}-\d{2}$", c)]
        return rows, names, months, extras

    _gf_rows, _gf_names, _gf_months, _gf_extras = _gf_read_h()
    _gf_rolling = _gf_months[-4:] if len(_gf_months) >= 4 else _gf_months
    _gf_col_names = list(_gf_rolling) + list(_gf_extras[:2])
    # = [2026-02, 2026-03, 2026-04, 2026-05, 未批核, 本月已递交]

    def _gf_fmt(v): return f"{v/1e6:.2f}M" if v > 0 else "0M"

    # 定位slide文件
    with _zf_gf.ZipFile(OUT_PPT, "r") as _zin_gf:
        _gf_all = {n: _zin_gf.read(n) for n in _zin_gf.namelist()}

    _gf_prs_root = _ET_gf.fromstring(_gf_all["ppt/presentation.xml"])
    _gf_ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
               "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    _gf_sids = [el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                for el in _gf_prs_root.findall(".//p:sldIdLst/p:sldId", _gf_ns)]
    _gf_rels_root = _ET_gf.fromstring(_gf_all["ppt/_rels/presentation.xml.rels"])
    _gf_rels = {el.get("Id"): el.get("Target") for el in _gf_rels_root}

    # 找永明汇报slide（包含"G.  永明业绩汇报数据-2026"）
    _gf_slide_fname = None
    for _gf_sid in _gf_sids:
        _gf_tgt = _gf_rels.get(_gf_sid, "")
        _gf_fname = "ppt/" + _gf_tgt.lstrip("./")
        if _gf_fname in _gf_all:
            _gf_txt = _gf_all[_gf_fname].decode("utf-8", errors="replace")
            if "永明业绩汇报数据" in _gf_txt and "Sunlife" in _gf_txt:
                _gf_slide_fname = _gf_fname
                break
    if _gf_slide_fname is None:
        print("  ⚠ 找不到永明汇报slide，跳过")
    else:
        NS_C_GF = "http://schemas.openxmlformats.org/drawingml/2006/main"
        NS_P_GF = "http://schemas.openxmlformats.org/presentationml/2006/main"
        NS_A_GF = "http://schemas.openxmlformats.org/drawingml/2006/main"

        _gf_slide_root = _ET_gf.fromstring(_gf_all[_gf_slide_fname])

        # 收集所有文本形状，提取(x, y, element)
        _gf_shapes = []
        for sp in _gf_slide_root.iter("{http://schemas.openxmlformats.org/presentationml/2006/main}sp"):
            xfrm = sp.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")
            if xfrm is None: continue
            off = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}off")
            if off is None: continue
            try:
                sx = int(off.get("x", 0))
                sy = int(off.get("y", 0))
            except: continue
            txBody = sp.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}txBody")
            if txBody is None: continue
            _gf_shapes.append((sx, sy, txBody))

        # G表行y中心和容差
        _GF_ROW_Y = [1809750, 2056765, 2303780, 2555240, 2807970, 3054985]
        _GF_TOL_Y = 80000
        _GF_COL_IDX = [1, 3, 5, 7, 9, 11]

        _gf_changed = 0
        for _ri, _ry in enumerate(_GF_ROW_Y):
            _rd = _gf_rows[_ri] if _ri < len(_gf_rows) else None
            # 找该行所有形状，按x排序
            _row_sps = sorted(
                [(sx, txBody) for sx, sy, txBody in _gf_shapes if abs(sy - _ry) <= _GF_TOL_Y],
                key=lambda x: x[0]
            )
            for _di, _cn in zip(_GF_COL_IDX, _gf_col_names):
                if _di >= len(_row_sps): continue
                _, txBody = _row_sps[_di]
                val = _rd.get(_cn, 0.0) if _rd else 0.0
                text = _gf_fmt(val)
                # 找第一个<a:t>并替换
                for t_el in txBody.iter(f"{{{NS_A_GF}}}t"):
                    t_el.text = text
                    break
                _gf_changed += 1

        # 写回
        _gf_all[_gf_slide_fname] = _ET_gf.tostring(
            _gf_slide_root, encoding="unicode", xml_declaration=False
        ).encode("utf-8")

        _gf_tmp = OUT_PPT + ".gftmp"
        with _zf_gf.ZipFile(_gf_tmp, "w", _zf_gf.ZIP_DEFLATED) as _zout_gf:
            for _n, _d in _gf_all.items():
                _zout_gf.writestr(_n, _d)
        import os as _os_gf
        _os_gf.replace(_gf_tmp, OUT_PPT)
        print(f"  G表列索引写入完成: {_gf_changed} 格 | rolling={_gf_rolling} ✓")
except Exception as _gf_err:
    print(f"  ⚠ G表列索引写入失败: {_gf_err}")
    import traceback; traceback.print_exc()

# ── Post-save ZIP PATCH: Z 银行月度走势 embedded xlsx ────────────────────────
# Fix C prepared correct xlsx bytes; now embed them into the pptx zip.
try:
    import zipfile as _zf_z, io as _io_z, os as _os_z
    if _Z_XLSX_DATA:
        with _zf_z.ZipFile(OUT_PPT, "r") as _zin_z:
            _z_all = {n: _zin_z.read(n) for n in _zin_z.namelist()}

        for _zchrt_name, _zxlsx_bytes, _zchrt_part in _Z_XLSX_DATA:
            # Find the embedding path for this chart part
            _z_chart_path = _zchrt_part.partname.lstrip("/")
            _z_chart_rels_path = _z_chart_path.replace("charts/chart", "charts/_rels/chart") + ".rels"
            # Check existing rels for xlsx embedding
            if _z_chart_rels_path in _z_all:
                import re as _re_zembed
                _rels_xml = _z_all[_z_chart_rels_path].decode("utf-8")
                # Find existing xlsx embedding (oleObject or spreadsheetml)
                _embed_matches = _re_zembed.findall(r'Target="([^"]*\.xlsx)"', _rels_xml)
                if not _embed_matches:
                    # Add a new relationship and embed path
                    _embed_path = f"ppt/charts/embeddings/{_zchrt_name}_data.xlsx"
                    _embed_rel_id = f"rId_z_{_zchrt_name}"
                    _new_rel = (f'<Relationship Id="{_embed_rel_id}" ' 
                                f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/package" ' 
                                f'Target="../embeddings/{_zchrt_name}_data.xlsx"/>')
                    _rels_xml = _rels_xml.replace("</Relationships>", f"{_new_rel}</Relationships>")
                    _z_all[_z_chart_rels_path] = _rels_xml.encode("utf-8")
                    _z_all[_embed_path] = _zxlsx_bytes
                    print(f"  Z xlsx embed: added {_embed_path}")
                else:
                    # Overwrite existing xlsx
                    for _em in _embed_matches:
                        _em_full = _em if _em.startswith("ppt/") else f"ppt/charts/{_em.lstrip('../')}"
                        _z_all[_em_full] = _zxlsx_bytes
                        print(f"  Z xlsx embed: overwrote {_em_full} for {_zchrt_name}")
            else:
                _embed_path = f"ppt/charts/embeddings/{_zchrt_name}_data.xlsx"
                _z_all[_embed_path] = _zxlsx_bytes
                print(f"  Z xlsx embed: created {_embed_path}")

        _z_tmp = OUT_PPT + ".ztmp"
        with _zf_z.ZipFile(_z_tmp, "w", _zf_z.ZIP_DEFLATED) as _zout_z:
            for _n, _d in _z_all.items(): _zout_z.writestr(_n, _d)
        _os_z.replace(_z_tmp, OUT_PPT)
        print("  Z 银行月度走势 embedded xlsx 更新完成 ✓")
    else:
        print("  Z xlsx: no data to embed (Fix C skipped)")
except Exception as _e_z:
    print(f"  ⚠ Z xlsx embed failed: {_e_z}")
    import traceback; traceback.print_exc()
# ── 清理中间过程文件 ────────────────────────────────────────────────────────
import os as _os_cleanup
for _cf in [OUT_PPT + s for s in [".gtmp",".tmp",".nhtmp",".ztmp",".gftmp"]] + [OUT_PPT.replace(".pptx","_updated.pptx")]:
    if _os_cleanup.path.exists(_cf):
        try: _os_cleanup.remove(_cf); print(f"  [cleanup] {_cf}")
        except: pass
print(f"\n✅ 完成: {OUT_PPT}")
