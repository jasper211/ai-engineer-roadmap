#!/usr/bin/env python3
"""
apply_w14_patches.py — Weekly report patch applier (config-driven).

All configuration lives in the CONFIG block at the top of this file.
No business-specific identifiers are hardcoded in the logic below.

Key design principles:
  1. Current week is AUTO-DETECTED from the rightmost non-zero column of
     the first weekly CSV section (override via CONFIG.current_week if needed)
  2. Slides are located by TITLE KEYWORDS, not by slide index
  3. Tables are located by HEADER CELL signature, not by shape id
  4. Charts are located by CATEGORY CONTENT (entity names from CSV), not shape id
  5. Entity names (banks, branches, KAs, recipients) are READ FROM CSV,
     not hardcoded in Python whitelists
  6. KPI card captions are identified by the text of the LABEL SHAPE
     above them ("未批核" / "待签"), not by matching specific numeric values

Usage:
    python3 apply_w14_patches.py
"""
from __future__ import annotations
import csv, re, sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE


# ============================================================================
# CONFIG — everything that might change between runs lives here
# ============================================================================

@dataclass
class Config:
    # --- Paths (relative to this script) ---
    here: Path = Path(__file__).parent
    s2_csv: str = "S2-业务端视角.csv"
    s3_csv: str = "S3-执行管理端.csv"
    weekly_src: str = "周业绩汇报PPT_AUTO_UPDATED.pptx"
    heat_src: str = "热力图.pptx"
    weekly_out_suffix: str = "_updated"
    heat_out_suffix: str = "_重建"

    # --- Reporting window ---
    # If None → auto-detect rightmost non-zero column from S3 weekly heat section
    current_week: Optional[str] = None
    year_prefix: str = "2026"

    # --- Week-to-month mapping ---
    # If None → distribute CSV weeks evenly across CSV-derived month labels.
    # For exact calendar-month alignment, specify a list of tuples:
    # [('Jan-26',1,4),('Feb-26',5,8),('Mar-26',9,13),('Apr-26',14,14)]
    weeks_per_month_override: Optional[list] = None

    # --- Heat matrix business-line order (must match CSV left-column spelling) ---
    heat_business_order: list = field(default_factory=lambda: [
        '天领业务','成事家办','BK业务','同行经代','永明经代','合伙转介业务','ICLUB业务',
    ])
    heat_row_colors: dict = field(default_factory=lambda: {
        '天领业务':    (0xB6,0xCC,0xDC),
        '成事家办':    (0xE4,0xE4,0xE4),
        'BK业务':     (0xA5,0xAD,0xC8),
        '同行经代':    (0xF4,0xC2,0x9F),
        '永明经代':    (0x9D,0xC5,0xB0),
        '合伙转介业务': (0xE8,0xE8,0xE8),
        'ICLUB业务':  (0xCF,0xB8,0xDE),
    })
    heat_title_bar_rgb: tuple = (0x7E,0x1F,0x1F)
    heat_sowhat_bar_rgb: tuple = (0x2E,0x5E,0x3E)

    # --- CSV section markers (structural, not entity-specific) ---
    s2_recipient_section: str = 'J. 同行推荐人分析'
    s2_peer_ka_section:   str = 'K. 同行业绩分析'
    s2_branch_section:    str = 'S-APE'
    s2_peer_monthly_appt: str = 'L-APE'; s2_peer_monthly_appt_cnt: str = 'L-件数'
    s2_peer_monthly_sign: str = 'M-APE'; s2_peer_monthly_sign_cnt: str = 'M-件数'
    s2_peer_monthly_app:  str = 'N-APE'; s2_peer_monthly_app_cnt:  str = 'N-件数'
    s3_peer_appt: str = 'J-APE';  s3_peer_appt_cnt: str = 'J-件数'
    s3_peer_sign: str = 'K-APE';  s3_peer_sign_cnt: str = 'K-件数'
    s3_peer_app:  str = 'L-APE';  s3_peer_app_cnt:  str = 'L-件数'
    s3_bank_appt: str = 'M-APE';  s3_bank_appt_cnt: str = 'M-件数'
    s3_bank_sign: str = 'N-APE';  s3_bank_sign_cnt: str = 'N-件数'
    s3_bank_app:  str = 'O-APE';  s3_bank_app_cnt:  str = 'O-件数'
    s3_heat_appt: str = 'B-APE';  s3_heat_appt_cnt: str = 'B-件数'
    s3_heat_sign: str = 'C-APE';  s3_heat_sign_cnt: str = 'C-件数'
    s3_heat_app:  str = 'D-APE';  s3_heat_app_cnt:  str = 'D-件数'

    # --- Slide discovery (by title keywords, not by index) ---
    slide_peer_common_kw:  list = field(default_factory=lambda: ['同行'])
    slide_peer_p1_marker:  str = 'U 同行推荐'    # chart U lives on peer page 1
    slide_peer_p2_marker:  str = 'X  W01'       # trend chart X lives on peer page 2
    slide_bank_common_kw:  list = field(default_factory=lambda: ['银行'])
    slide_bank_p2_marker:  str = 'BK W'         # weekly KPI cards on bank page 2

    # --- Table / chart structural signatures ---
    ka_table_header_signature:    str = 'KEY ACCOUNT'
    ka_table_min_columns:         int = 8       # 9-col table (KA + 8 metric columns)
    month_table_header_signature: str = '月份'
    y_table_expected_columns:     int = 4
    bank_ka_table_columns:        int = 7

    # --- Heat matrix region geometry (EMU, per 13.33" × 7.5" slide) ---
    heat_q_region: tuple = (0,       560000,  6200000,  3650000)
    heat_r_region: tuple = (6200000, 560000,  12192000, 3650000)
    heat_s_region: tuple = (0,       3650000, 6200000,  6760000)


CFG = Config()

_SECTION_HEADER_RE = re.compile(r'^[A-Z](?:-[A-Za-z\u4e00-\u9fff]+)?\.?\s')


# ============================================================================
# CSV helpers — fully structural
# ============================================================================

def load_rows(path: Path):
    """Read a CSV, auto-detecting UTF-8 vs GBK encoding."""
    import io
    raw_bytes = Path(path).read_bytes()
    text = None
    for enc in ('utf-8-sig', 'utf-8', 'gb18030', 'gbk', 'cp936'):
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw_bytes.decode('utf-8', errors='replace')
    return list(csv.reader(io.StringIO(text)))


def _find_section_start(rows, marker: str) -> int:
    for i, r in enumerate(rows):
        if r and r[0].strip().startswith(marker):
            return i
    return -1


def _find_header_row(rows, start: int):
    for j in range(start + 1, min(start + 5, len(rows))):
        r = rows[j]
        if not r or not r[0].strip(): continue
        c0 = r[0].strip()
        if c0.startswith('📌'): continue
        # Skip corrupted 📌 rows (rendered as ??? or \ufffd when file had
        # mixed encoding — see data_loader for the same fix)
        first_char = c0.lstrip('"').lstrip("'")[:1]
        if first_char in ('\ufffd', '?'):
            if '\ufffd\ufffd' in c0 or '???' in c0:
                continue
        return j, r
    return start + 1, (rows[start + 1] if start + 1 < len(rows) else [])


def _is_new_section(cell: str, current_marker: str) -> bool:
    cell = cell.strip()
    if not cell: return False
    if cell.startswith(current_marker): return False
    return bool(_SECTION_HEADER_RE.match(cell))


def iter_section_body(rows, marker: str):
    start = _find_section_start(rows, marker)
    if start < 0: return
    hdr_i, _ = _find_header_row(rows, start)
    for j in range(hdr_i + 1, len(rows)):
        rr = rows[j]
        if not rr or not rr[0].strip(): continue
        c0 = rr[0].strip()
        if c0.startswith('📌'): continue
        # Skip corrupted 📌 rows as well
        first_char = c0.lstrip('"').lstrip("'")[:1]
        if first_char in ('\ufffd', '?'):
            if '\ufffd\ufffd' in c0 or '???' in c0:
                continue
        if _is_new_section(c0, marker): return
        yield rr


def parse_section_weekly_col(rows, marker: str, week_label: str) -> dict:
    start = _find_section_start(rows, marker)
    if start < 0: return {}
    _, hdr = _find_header_row(rows, start)
    try: col = hdr.index(week_label)
    except ValueError: return {}
    out = {}
    for rr in iter_section_body(rows, marker):
        name = rr[0].strip()
        if name == '合计': continue
        try: out[name] = float(rr[col].replace(',', '')) if col < len(rr) else 0
        except ValueError: out[name] = 0
    return out


def parse_section_weekly_all(rows, marker: str):
    """Returns (week_labels, {name: [per-week values]})"""
    start = _find_section_start(rows, marker)
    if start < 0: return [], {}
    _, hdr = _find_header_row(rows, start)
    try: tot_col = hdr.index('合计')
    except ValueError: tot_col = len(hdr)
    week_cols = list(range(1, tot_col))
    week_labels = [hdr[c].strip() for c in week_cols]
    out = {}
    for rr in iter_section_body(rows, marker):
        name = rr[0].strip()
        if name == '合计': continue
        vals = []
        for c in week_cols:
            try: vals.append(float(rr[c].replace(',','')) if c < len(rr) and rr[c].strip() else 0)
            except ValueError: vals.append(0)
        out[name] = vals
    return week_labels, out


def parse_section_records(rows, marker: str) -> list:
    """Each body row → dict with 'name' + named columns from header."""
    start = _find_section_start(rows, marker)
    if start < 0: return []
    _, hdr = _find_header_row(rows, start)
    out = []
    for rr in iter_section_body(rows, marker):
        name = rr[0].strip()
        if name == '合计': break
        d = {'name': name}
        for k, h in enumerate(hdr[1:], start=1):
            hh = h.strip()
            if not hh: continue
            v = rr[k].strip().replace(',', '') if k < len(rr) else ''
            try: d[hh] = float(v) if v else 0
            except ValueError: d[hh] = 0
        out.append(d)
    return out


def list_section_names(rows, marker: str) -> list:
    return [rr[0].strip() for rr in iter_section_body(rows, marker) if rr[0].strip() != '合计']


def auto_detect_current_week(rows, marker: str) -> str:
    labels, data = parse_section_weekly_all(rows, marker)
    if not labels: return ''
    last_with_data = -1
    for i in range(len(labels)):
        if any((vals[i] if i<len(vals) else 0) != 0 for vals in data.values()):
            last_with_data = i
    return labels[last_with_data] if last_with_data >= 0 else labels[-1]


def derive_monthly_buckets(s2rows, s2_monthly_marker: str, n_weeks: int, year: int = 2026):
    """
    Derive (month_label, w_start_1based, w_end_inclusive) triples by mapping
    each ISO week of `year` to the calendar month it predominantly belongs to.

    A week is assigned to the month containing its Thursday (ISO convention —
    the Thursday rule ensures every week belongs to exactly one month, and the
    assignment matches how most business calendars bucket weeks).
    """
    from datetime import date, timedelta

    # Pull month labels from monthly CSV section (to use same label format)
    start = _find_section_start(s2rows, s2_monthly_marker)
    month_labels_by_num = {}
    if start >= 0:
        _, hdr = _find_header_row(s2rows, start)
        try: tot_col = hdr.index('合计')
        except ValueError: tot_col = len(hdr)
        months_en = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        for c in range(1, tot_col):
            raw = hdr[c].strip()
            m = re.match(r'(\d{4})-(\d{1,2})', raw)
            if m:
                mm = int(m.group(2))
                month_labels_by_num[mm] = f"{months_en[mm-1]}-{m.group(1)[-2:]}"

    # For each ISO week 1..n_weeks of `year`, find the month of its Thursday
    week_to_month = {}
    for wk in range(1, n_weeks + 1):
        # ISO week `wk` of `year` → Thursday date
        jan4 = date(year, 1, 4)  # always in week 1 per ISO 8601
        week1_monday = jan4 - timedelta(days=jan4.isoweekday() - 1)
        thursday = week1_monday + timedelta(weeks=wk-1, days=3)
        week_to_month[wk] = thursday.month

    # Group consecutive weeks by month
    buckets = []
    if not week_to_month: return []
    cur_month = week_to_month[1]; cur_start = 1
    for wk in range(2, n_weeks + 1):
        m = week_to_month[wk]
        if m != cur_month:
            label = month_labels_by_num.get(cur_month, f"M{cur_month:02d}")
            buckets.append((label, cur_start, wk - 1))
            cur_month = m; cur_start = wk
    label = month_labels_by_num.get(cur_month, f"M{cur_month:02d}")
    buckets.append((label, cur_start, n_weeks))
    return buckets


# ============================================================================
# PPT helpers
# ============================================================================

def set_tf(tf, text: str):
    ref = None
    for para in tf.paragraphs:
        for r in para.runs:
            ref = r; break
        if ref: break
    for para in list(tf.paragraphs):
        for r in list(para.runs):
            r._r.getparent().remove(r._r)
    para = tf.paragraphs[0]
    nr = para.add_run(); nr.text = text
    if ref is not None:
        if ref.font.size: nr.font.size = ref.font.size
        if ref.font.bold is not None: nr.font.bold = ref.font.bold
        if ref.font.name: nr.font.name = ref.font.name
        try:
            if ref.font.color and ref.font.color.rgb:
                nr.font.color.rgb = ref.font.color.rgb
        except Exception:
            pass


def set_cell(cell, text: str):
    set_tf(cell.text_frame, text)


def strip_manual_dlbls(chart):
    """Remove manual <c:tx> overrides inside <c:dLbl> — fixes stale hardcoded labels
    left behind by manual edits in PowerPoint."""
    ns = {'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart'}
    for dlbl in chart._chartSpace.findall('.//c:dLbl', ns):
        for tx in dlbl.findall('c:tx', ns):
            dlbl.remove(tx)


def find_slide_with_all(prs, keywords: list) -> Optional[int]:
    for idx, slide in enumerate(prs.slides):
        text = ' '.join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)
        if all(kw in text for kw in keywords):
            return idx
    return None


def find_table_by_header(slide, header_signature: str, min_cols: int = 1):
    for sh in slide.shapes:
        if not sh.has_table: continue
        t = sh.table
        if t.rows[0].cells[0].text.strip() == header_signature and len(t.columns) >= min_cols:
            return t
    return None


def find_table_exact_cols(slide, header_signature: str, exact_cols: int):
    for sh in slide.shapes:
        if not sh.has_table: continue
        t = sh.table
        if t.rows[0].cells[0].text.strip() == header_signature and len(t.columns) == exact_cols:
            return t
    return None


def iter_charts(slide):
    for sh in slide.shapes:
        if not sh.has_chart: continue
        ch = sh.chart
        cats = []
        for plot in ch.plots:
            try: cats = list(plot.categories); break
            except Exception: pass
        yield ch, cats


def fmt_m(v, decimals=2): return f"{v/1e6:.{decimals}f}M"


def find_text_shape_above(slide, shape, keywords: list = None):
    """Find the closest text shape above `shape` with horizontal overlap.
    If `keywords` is given, only return shapes whose text contains any of them."""
    if shape.top is None or shape.left is None: return None
    best_sh = None; best_dy = 10**9
    for sh in slide.shapes:
        if sh is shape or not sh.has_text_frame: continue
        if sh.top is None or sh.left is None: continue
        if sh.top >= shape.top: continue
        if (sh.left + (sh.width or 0)) < shape.left: continue
        if sh.left > (shape.left + (shape.width or 0)): continue
        if keywords is not None:
            txt = sh.text_frame.text
            if not any(kw in txt for kw in keywords): continue
        dy = shape.top - sh.top
        if dy < best_dy:
            best_dy = dy; best_sh = sh
    return best_sh


def find_shapes_below(slide, label_shape, max_count: int = 2, x_tol: int = 300000):
    """Return up to max_count text shapes immediately below `label_shape` in same column."""
    if label_shape.top is None: return []
    below = []
    for sh in slide.shapes:
        if sh is label_shape or not sh.has_text_frame: continue
        if sh.top is None or sh.left is None: continue
        if sh.top <= label_shape.top: continue
        if abs(sh.left - label_shape.left) > x_tol: continue
        below.append((sh.top, sh))
    below.sort(key=lambda x: x[0])
    return [sh for _, sh in below[:max_count]]


# ============================================================================
# WEEKLY DECK PATCHES
# ============================================================================

def patch_weekly_deck(cfg: Config):
    src = cfg.here / cfg.weekly_src
    if not src.exists():
        print(f"[skip] weekly src not found: {src.name}"); return
    out = cfg.here / (src.stem + cfg.weekly_out_suffix + src.suffix)

    s2rows = load_rows(cfg.here / cfg.s2_csv)
    s3rows = load_rows(cfg.here / cfg.s3_csv)

    # --- Auto-detect current week if not set ---
    current_week = cfg.current_week or auto_detect_current_week(s3rows, cfg.s3_heat_appt)
    if not current_week:
        print("[err] could not detect current week"); return
    # "2026W14" -> "W14"
    week_short = current_week.replace(cfg.year_prefix, '')
    print(f"[info] current week = {current_week} (short: {week_short})")

    # --- Parse S2 sections ---
    recipient_records = parse_section_records(s2rows, cfg.s2_recipient_section)
    peer_ka_records   = parse_section_records(s2rows, cfg.s2_peer_ka_section)

    # Branch records: use 合计 column, filter zero entries, sort desc
    branch_records = parse_section_records(s2rows, cfg.s2_branch_section)
    branches = sorted(
        [(d['name'], d.get('合计', 0) / 1e6) for d in branch_records if d.get('合计', 0) > 0],
        key=lambda x: -x[1]
    )

    # --- Parse S3 weekly sections ---
    j_ape_w = parse_section_weekly_col(s3rows, cfg.s3_peer_appt, current_week)
    k_ape_w = parse_section_weekly_col(s3rows, cfg.s3_peer_sign, current_week)
    l_ape_w = parse_section_weekly_col(s3rows, cfg.s3_peer_app,  current_week)

    wk_labels_j, j_ape_all = parse_section_weekly_all(s3rows, cfg.s3_peer_appt)
    _,           j_cnt_all = parse_section_weekly_all(s3rows, cfg.s3_peer_appt_cnt)
    _,           k_ape_all = parse_section_weekly_all(s3rows, cfg.s3_peer_sign)
    _,           k_cnt_all = parse_section_weekly_all(s3rows, cfg.s3_peer_sign_cnt)
    _,           l_ape_all = parse_section_weekly_all(s3rows, cfg.s3_peer_app)
    _,           l_cnt_all = parse_section_weekly_all(s3rows, cfg.s3_peer_app_cnt)

    # --- Bank W-column (dynamic entity list) ---
    bank_entities = list_section_names(s3rows, cfg.s3_bank_appt)
    bank_w = {}
    for bank in bank_entities:
        bank_w[bank] = {
            'appt_ape': parse_section_weekly_col(s3rows, cfg.s3_bank_appt,     current_week).get(bank, 0),
            'appt_cnt': parse_section_weekly_col(s3rows, cfg.s3_bank_appt_cnt, current_week).get(bank, 0),
            'sign_ape': parse_section_weekly_col(s3rows, cfg.s3_bank_sign,     current_week).get(bank, 0),
            'sign_cnt': parse_section_weekly_col(s3rows, cfg.s3_bank_sign_cnt, current_week).get(bank, 0),
            'app_ape':  parse_section_weekly_col(s3rows, cfg.s3_bank_app,      current_week).get(bank, 0),
            'app_cnt':  parse_section_weekly_col(s3rows, cfg.s3_bank_app_cnt,  current_week).get(bank, 0),
        }
    bank_tot = {k: sum(b[k] for b in bank_w.values())
                for k in ['appt_ape','appt_cnt','sign_ape','sign_cnt','app_ape','app_cnt']}

    p = Presentation(src)

    # --- Discover slides by keywords ---
    peer_p1 = find_slide_with_all(p, cfg.slide_peer_common_kw + [cfg.slide_peer_p1_marker])
    peer_p2 = find_slide_with_all(p, cfg.slide_peer_common_kw + [cfg.slide_peer_p2_marker])
    bank_p2 = find_slide_with_all(p, cfg.slide_bank_common_kw + [cfg.slide_bank_p2_marker])
    print(f"[info] slides discovered: peer_p1={peer_p1} peer_p2={peer_p2} bank_p2={bank_p2}")

    # ======== Peer slide 1 ========
    if peer_p1 is not None:
        s = p.slides[peer_p1]

        # --- KA detail table ---
        ka_t = find_table_by_header(s, cfg.ka_table_header_signature, min_cols=cfg.ka_table_min_columns)
        if ka_t is not None and peer_ka_records:
            n = len(ka_t.rows); body = n - 2
            for i in range(body):
                row = ka_t.rows[i + 1]
                if i < len(peer_ka_records):
                    d = peer_ka_records[i]
                    set_cell(row.cells[0], d['name'])
                    set_cell(row.cells[1], f"{d.get('2026批核APE',0)/1e6:.2f}" if d.get('2026批核APE',0)>0 else "—")
                    set_cell(row.cells[2], f"{int(d.get('批核件数',0))}"     if d.get('批核件数',0)>0 else "—")
                    set_cell(row.cells[3], f"{d.get('未批核APE',0)/1e6:.2f}"  if d.get('未批核APE',0)>0 else "—")
                    set_cell(row.cells[4], f"{int(d.get('未批核件数',0))}"    if d.get('未批核件数',0)>0 else "—")
                    set_cell(row.cells[5], f"{d.get('待签APE',0)/1e6:.2f}"    if d.get('待签APE',0)>0 else "—")
                    set_cell(row.cells[6], f"{int(d.get('待签件数',0))}"      if d.get('待签件数',0)>0 else "—")
                    set_cell(row.cells[7], f"{d.get('总APE',0)/1e6:.2f}")
                    set_cell(row.cells[8], f"{int(d.get('总件数',0))}")
                else:
                    for c in range(9): set_cell(row.cells[c], "")
            tot = {k: sum(d.get(k,0) for d in peer_ka_records)
                   for k in ['2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','总APE','总件数']}
            last = n - 1
            set_cell(ka_t.rows[last].cells[0], "合计")
            set_cell(ka_t.rows[last].cells[1], f"{tot['2026批核APE']/1e6:.2f}")
            set_cell(ka_t.rows[last].cells[2], f"{int(tot['批核件数'])}")
            set_cell(ka_t.rows[last].cells[3], f"{tot['未批核APE']/1e6:.2f}")
            set_cell(ka_t.rows[last].cells[4], f"{int(tot['未批核件数'])}")
            set_cell(ka_t.rows[last].cells[5], f"{tot['待签APE']/1e6:.2f}")
            set_cell(ka_t.rows[last].cells[6], f"{int(tot['待签件数'])}")
            set_cell(ka_t.rows[last].cells[7], f"{tot['总APE']/1e6:.2f}")
            set_cell(ka_t.rows[last].cells[8], f"{int(tot['总件数'])}")

            # --- KPI card captions: identify by the label shape above ---
            wpk_avg = (tot['未批核APE']/tot['未批核件数']/10000) if tot['未批核件数'] else 0
            dq_avg  = (tot['待签APE']/tot['待签件数']/10000)   if tot['待签件数']   else 0
            metric_keywords = ['未批核', '待签', '批核']
            for sh in s.shapes:
                if not sh.has_text_frame: continue
                t = sh.text_frame.text
                if '件均' not in t or '件' not in t: continue
                label_above = find_text_shape_above(s, sh, keywords=metric_keywords)
                if label_above is None: continue
                label_text = label_above.text_frame.text
                # 未批核 label excludes plain 批核, 待签 label is distinct
                if '未批核' in label_text:
                    set_tf(sh.text_frame, f"{int(tot['未批核件数'])}件  |  件均{wpk_avg:.1f}万")
                elif '待签' in label_text:
                    set_tf(sh.text_frame, f"{int(tot['待签件数'])}件  |  件均{dq_avg:.1f}万")

        # --- U chart (recipient dimension) ---
        recipient_names = {d['name'] for d in recipient_records}
        peer_ka_names = {d['name'] for d in peer_ka_records}
        u_updated = False
        v_updated = False
        for ch, cats in iter_charts(s):
            cats_set = set(cats)
            if not u_updated and (cats_set & recipient_names) and not (cats_set - recipient_names - {None, '', 'None'}):
                data = CategoryChartData()
                data.categories = [d['name'] for d in recipient_records]
                data.add_series('批核 APE(M)',   [round(d.get('2026批核APE',0)/1e6,2) for d in recipient_records])
                data.add_series('未批核 APE(M)', [round(d.get('未批核APE',0)/1e6,2)  for d in recipient_records])
                data.add_series('待签 APE(M)',   [round(d.get('待签APE',0)/1e6,2)    for d in recipient_records])
                ch.replace_data(data)
                strip_manual_dlbls(ch)
                u_updated = True
            elif not v_updated and (cats_set & peer_ka_names):
                top_n = len(cats)
                top = peer_ka_records[:top_n]
                cats_bar = list(reversed([d['name'] for d in top]))
                lk = {d['name']: d for d in top}
                data = CategoryChartData()
                data.categories = cats_bar
                data.add_series('批核 APE(M)',   [round(lk[k].get('2026批核APE',0)/1e6,2) for k in cats_bar])
                data.add_series('未批核 APE(M)', [round(lk[k].get('未批核APE',0)/1e6,2)  for k in cats_bar])
                data.add_series('待签 APE(M)',   [round(lk[k].get('待签APE',0)/1e6,2)    for k in cats_bar])
                ch.replace_data(data)
                strip_manual_dlbls(ch)
                v_updated = True

    # ======== Peer slide 2 ========
    if peer_p2 is not None:
        s = p.slides[peer_p2]

        # --- W monthly table (read directly from S2 monthly sections — no week aggregation) ---
        def parse_monthly_totals(marker: str) -> list:
            """Return [(month_label, total_value), ...] from the 合计 row."""
            start = _find_section_start(s2rows, marker)
            if start < 0: return []
            _, hdr = _find_header_row(s2rows, start)
            try: tot_col = hdr.index('合计')
            except ValueError: tot_col = len(hdr)
            # Find 合计 row
            for rr in iter_section_body(s2rows, marker):
                if rr[0].strip() == '合计':
                    out = []
                    months_en = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
                    for c in range(1, tot_col):
                        raw = hdr[c].strip()
                        m = re.match(r'(\d{4})-(\d{1,2})', raw)
                        label = f"{months_en[int(m.group(2))-1]}-{m.group(1)[-2:]}" if m else raw
                        try: v = float(rr[c].replace(',','')) if c<len(rr) else 0
                        except ValueError: v = 0
                        out.append((label, v))
                    return out
            return []

        appt_ape = parse_monthly_totals(cfg.s2_peer_monthly_appt)
        appt_cnt = parse_monthly_totals(cfg.s2_peer_monthly_appt_cnt)
        sign_ape = parse_monthly_totals(cfg.s2_peer_monthly_sign)
        sign_cnt = parse_monthly_totals(cfg.s2_peer_monthly_sign_cnt)
        app_ape  = parse_monthly_totals(cfg.s2_peer_monthly_app)
        app_cnt  = parse_monthly_totals(cfg.s2_peer_monthly_app_cnt)

        mt = find_table_by_header(s, cfg.month_table_header_signature)
        if mt is not None and appt_ape:
            totals = [0]*6
            for i, (label, v1) in enumerate(appt_ape):
                if i + 1 >= len(mt.rows): break
                v2 = appt_cnt[i][1] if i < len(appt_cnt) else 0
                v3 = sign_ape[i][1] if i < len(sign_ape) else 0
                v4 = sign_cnt[i][1] if i < len(sign_cnt) else 0
                v5 = app_ape[i][1]  if i < len(app_ape)  else 0
                v6 = app_cnt[i][1]  if i < len(app_cnt)  else 0
                row = mt.rows[i + 1]
                set_cell(row.cells[0], label)
                set_cell(row.cells[1], f"{v1/1e6:.2f}")
                set_cell(row.cells[2], str(int(v2)))
                set_cell(row.cells[3], f"{v3/1e6:.2f}")
                set_cell(row.cells[4], str(int(v4)))
                set_cell(row.cells[5], f"{v5/1e6:.2f}")
                set_cell(row.cells[6], str(int(v6)))
                for k, v in enumerate([v1,v2,v3,v4,v5,v6]):
                    totals[k] += v
            last = len(mt.rows) - 1
            set_cell(mt.rows[last].cells[0], "合计")
            set_cell(mt.rows[last].cells[1], f"{totals[0]/1e6:.2f}")
            set_cell(mt.rows[last].cells[2], str(int(totals[1])))
            set_cell(mt.rows[last].cells[3], f"{totals[2]/1e6:.2f}")
            set_cell(mt.rows[last].cells[4], str(int(totals[3])))
            set_cell(mt.rows[last].cells[5], f"{totals[4]/1e6:.2f}")
            set_cell(mt.rows[last].cells[6], str(int(totals[5])))

        # --- Y 本周快报 (4-col KA table) ---
        yt = find_table_exact_cols(s, cfg.ka_table_header_signature, cfg.y_table_expected_columns)
        if yt is not None:
            kas = set()
            for d in (j_ape_w, k_ape_w, l_ape_w):
                for k, v in d.items():
                    if v > 0: kas.add(k)
            def tot_fn(k): return j_ape_w.get(k,0)+k_ape_w.get(k,0)+l_ape_w.get(k,0)
            ordered = sorted(kas, key=tot_fn, reverse=True)
            n = len(yt.rows); body = n - 2
            for i in range(body):
                row = yt.rows[i + 1]
                if i < len(ordered):
                    k = ordered[i]
                    set_cell(row.cells[0], k)
                    set_cell(row.cells[1], fmt_m(j_ape_w.get(k,0)))
                    set_cell(row.cells[2], fmt_m(k_ape_w.get(k,0)))
                    set_cell(row.cells[3], fmt_m(l_ape_w.get(k,0)))
                else:
                    for c in range(4): set_cell(row.cells[c], "")
            tj = sum(j_ape_w.get(k,0) for k in ordered)
            tk = sum(k_ape_w.get(k,0) for k in ordered)
            tl = sum(l_ape_w.get(k,0) for k in ordered)
            last = n - 1
            set_cell(yt.rows[last].cells[0], "合计")
            set_cell(yt.rows[last].cells[1], fmt_m(tj))
            set_cell(yt.rows[last].cells[2], fmt_m(tk))
            set_cell(yt.rows[last].cells[3], fmt_m(tl))

    # ======== Bank slide 2 ========
    if bank_p2 is not None:
        s = p.slides[bank_p2]

        def avg_w(ape, cnt): return (ape/cnt/10000) if cnt else 0

        # --- KPI cards: label shapes that start with "BK W" and contain 预约/签单/批核 ---
        metric_by_keyword = {
            '预约': ('appt_ape', 'appt_cnt'),
            '签单': ('sign_ape', 'sign_cnt'),
            '批核': ('app_ape',  'app_cnt'),
        }
        for sh in list(s.shapes):
            if not sh.has_text_frame: continue
            t = sh.text_frame.text.strip()
            if not (t.startswith('BK W') and len(t) < 15): continue
            metric_kw = next((kw for kw in metric_by_keyword if kw in t), None)
            if not metric_kw: continue
            ape_key, cnt_key = metric_by_keyword[metric_kw]
            ape_val = bank_tot[ape_key]; cnt_val = bank_tot[cnt_key]
            set_tf(sh.text_frame, f"BK {week_short}{metric_kw}")
            below = find_shapes_below(s, sh, max_count=2)
            if len(below) >= 1:
                set_tf(below[0].text_frame, f"{ape_val/1e6:.2f}M")
            if len(below) >= 2:
                if cnt_val:
                    set_tf(below[1].text_frame, f"{int(cnt_val)}件 | 件均{avg_w(ape_val,cnt_val):.1f}W")
                else:
                    set_tf(below[1].text_frame, "0件 | 件均0W")

        # --- AC bank KA table ---
        ac_t = find_table_exact_cols(s, cfg.ka_table_header_signature, cfg.bank_ka_table_columns)
        if ac_t is not None:
            for r in range(1, len(ac_t.rows) - 1):
                name = ac_t.rows[r].cells[0].text.strip()
                if name in bank_w:
                    b = bank_w[name]
                    set_cell(ac_t.rows[r].cells[1], fmt_m(b['appt_ape']))
                    set_cell(ac_t.rows[r].cells[2], str(int(b['appt_cnt'])))
                    set_cell(ac_t.rows[r].cells[3], fmt_m(b['sign_ape']))
                    set_cell(ac_t.rows[r].cells[4], str(int(b['sign_cnt'])))
                    set_cell(ac_t.rows[r].cells[5], fmt_m(b['app_ape']))
                    set_cell(ac_t.rows[r].cells[6], str(int(b['app_cnt'])))
            last = len(ac_t.rows) - 1
            set_cell(ac_t.rows[last].cells[1], fmt_m(bank_tot['appt_ape']))
            set_cell(ac_t.rows[last].cells[2], str(int(bank_tot['appt_cnt'])))
            set_cell(ac_t.rows[last].cells[3], fmt_m(bank_tot['sign_ape']))
            set_cell(ac_t.rows[last].cells[4], str(int(bank_tot['sign_cnt'])))
            set_cell(ac_t.rows[last].cells[5], fmt_m(bank_tot['app_ape']))
            set_cell(ac_t.rows[last].cells[6], str(int(bank_tot['app_cnt'])))

        # --- AD branch chart ---
        branch_names = {b[0] for b in branches}
        for ch, cats in iter_charts(s):
            if set(cats) & branch_names:
                data = CategoryChartData()
                data.categories = [b[0] for b in branches]
                data.add_series('批核APE(M)', [round(v, 2) for _, v in branches])
                ch.replace_data(data)
                strip_manual_dlbls(ch)
                break

    p.save(out)
    print(f"[✓] Weekly deck → {out.name}")


# ============================================================================
# HEAT MATRIX REBUILD
# ============================================================================

def patch_heat_matrix(cfg: Config):
    src = cfg.here / cfg.heat_src
    if not src.exists():
        print(f"[skip] heat src not found: {src.name}"); return
    out = cfg.here / (src.stem + cfg.heat_out_suffix + src.suffix)

    s3rows = load_rows(cfg.here / cfg.s3_csv)
    order = cfg.heat_business_order
    row_colors = cfg.heat_row_colors

    data = {}
    for cfg_key, out_key in [
        (cfg.s3_heat_appt,     'appt_ape'),  (cfg.s3_heat_appt_cnt, 'appt_cnt'),
        (cfg.s3_heat_sign,     'sign_ape'),  (cfg.s3_heat_sign_cnt, 'sign_cnt'),
        (cfg.s3_heat_app,      'app_ape'),   (cfg.s3_heat_app_cnt,  'app_cnt'),
    ]:
        _, d = parse_section_weekly_all(s3rows, cfg_key)
        data[out_key] = d

    p = Presentation(src)
    slide = p.slides[0]

    Q_REGION = cfg.heat_q_region
    R_REGION = cfg.heat_r_region
    S_REGION = cfg.heat_s_region

    def in_region(sh, reg):
        if sh.left is None or sh.top is None: return False
        l,t,r,b = reg
        cx = sh.left + (sh.width or 0)//2
        cy = sh.top + (sh.height or 0)//2
        return l<=cx<=r and t<=cy<=b

    for sh in list(slide.shapes):
        if in_region(sh,Q_REGION) or in_region(sh,R_REGION) or in_region(sh,S_REGION):
            sh._element.getparent().remove(sh._element)

    TITLE_BAR = RGBColor(*cfg.heat_title_bar_rgb)
    SO_WHAT_BAR = RGBColor(*cfg.heat_sowhat_bar_rgb)

    def cell_color(base, ratio):
        if ratio <= 0: return None
        r,g,b = base
        t = 0.65 + 0.35*ratio
        return RGBColor(int(255-(255-r)*t), int(255-(255-g)*t), int(255-(255-b)*t))

    def add_text(left, top, w, h, text, size=9, bold=False, color=RGBColor(0x20,0x20,0x20), align=PP_ALIGN.CENTER):
        tb = slide.shapes.add_textbox(left, top, w, h)
        tf = tb.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Emu(0)
        tf.word_wrap = False
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para = tf.paragraphs[0]; para.alignment = align
        run = para.add_run(); run.text = text
        run.font.size = Pt(size); run.font.bold = bold
        run.font.color.rgb = color; run.font.name = 'Calibri'
        return tb

    def add_rect(left, top, w, h, fill, line=None):
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, w, h)
        if fill is None: shp.fill.background()
        else: shp.fill.solid(); shp.fill.fore_color.rgb = fill
        if line is None: shp.line.fill.background()
        else: shp.line.color.rgb = line; shp.line.width = Emu(3175)
        shp.shadow.inherit = False
        return shp

    def draw_matrix(region, title, ape_key, cnt_key, so_what):
        left0, top0, right0, bottom0 = region
        right0 -= Emu(40000)
        width = right0 - left0
        title_h = Emu(270000)
        add_rect(left0, top0, width, title_h, TITLE_BAR, line=TITLE_BAR)
        add_text(left0+Emu(80000), top0, width, title_h, title, size=11, bold=True,
                 color=RGBColor(0xFF,0xFF,0xFF), align=PP_ALIGN.LEFT)

        label_w = Emu(680000)
        cells_left = left0 + label_w
        n_weeks = max((len(v) for v in data[ape_key].values()), default=14)
        cell_w = (width - label_w) // n_weeks
        header_top = top0 + title_h + Emu(20000)
        header_h = Emu(170000)
        for i in range(n_weeks):
            add_text(cells_left+cell_w*i, header_top, cell_w, header_h,
                     f"W{i+1:02d}", size=8, bold=(i>=n_weeks-2),
                     color=RGBColor(0x66,0x66,0x66))

        body_top = header_top + header_h + Emu(10000)
        so_what_h = Emu(560000)
        avail = bottom0 - body_top - so_what_h - Emu(60000)
        row_h = min(Emu(265000), avail // (len(order)+1))

        ape = data[ape_key]
        all_vals = [v for n in order for v in ape.get(n,[0]*n_weeks) if v>0]
        vmax = max(all_vals) if all_vals else 1

        for ri, name in enumerate(order):
            rt = body_top + row_h*ri
            add_text(left0+Emu(20000), rt, label_w-Emu(30000), row_h, name, size=9, bold=True,
                     color=RGBColor(0x30,0x30,0x30), align=PP_ALIGN.LEFT)
            vals = ape.get(name, [0]*n_weeks)
            cnts = data[cnt_key].get(name, [0]*n_weeks)
            base = row_colors.get(name, (0xBB,0xBB,0xBB))
            for i in range(n_weeks):
                cl = cells_left + cell_w*i
                v = vals[i] if i<len(vals) else 0
                c = cnts[i] if i<len(cnts) else 0
                if v > 0:
                    col = cell_color(base, min(v/vmax, 1.0))
                    add_rect(cl+Emu(6000), rt+Emu(6000), cell_w-Emu(12000), row_h-Emu(12000),
                             col, line=RGBColor(0xFF,0xFF,0xFF))
                    add_text(cl, rt+Emu(8000), cell_w, Emu(130000),
                             f"{v/1e6:.1f}M", size=8, bold=True, color=RGBColor(0x2C,0x3E,0x50))
                    add_text(cl, rt+row_h-Emu(125000), cell_w, Emu(115000),
                             f"{int(c)}件", size=7, color=RGBColor(0x7A,0x7A,0x7A))

        # Totals row
        tot_rt = body_top + row_h*len(order)
        add_text(left0+Emu(20000), tot_rt, label_w-Emu(30000), row_h, "合计", size=10, bold=True,
                 color=RGBColor(0x20,0x20,0x20), align=PP_ALIGN.LEFT)
        for i in range(n_weeks):
            tv = sum((ape.get(n,[0]*n_weeks)[i] if i<len(ape.get(n,[])) else 0) for n in order)
            tc = sum((data[cnt_key].get(n,[0]*n_weeks)[i] if i<len(data[cnt_key].get(n,[])) else 0) for n in order)
            cl = cells_left + cell_w*i
            if tv > 0:
                add_rect(cl+Emu(6000), tot_rt+Emu(6000), cell_w-Emu(12000), row_h-Emu(12000),
                         RGBColor(0xEC,0xEC,0xEC), line=RGBColor(0xFF,0xFF,0xFF))
                add_text(cl, tot_rt+Emu(8000), cell_w, Emu(130000),
                         f"{tv/1e6:.1f}M", size=8, bold=True, color=RGBColor(0x2C,0x3E,0x50))
                add_text(cl, tot_rt+row_h-Emu(125000), cell_w, Emu(115000),
                         f"{int(tc)}件", size=7, color=RGBColor(0x7A,0x7A,0x7A))

        # So What panel
        sw_top = bottom0 - so_what_h - Emu(20000)
        add_rect(left0, sw_top, width, so_what_h, RGBColor(0xEE,0xF2,0xF7), line=RGBColor(0xC8,0xD2,0xDE))
        add_rect(left0, sw_top, Emu(55000), so_what_h, SO_WHAT_BAR, line=SO_WHAT_BAR)
        add_text(left0+Emu(100000), sw_top+Emu(15000), width-Emu(130000), Emu(95000),
                 "So What：", size=8, bold=True, color=SO_WHAT_BAR, align=PP_ALIGN.LEFT)
        tb = slide.shapes.add_textbox(left0+Emu(100000), sw_top+Emu(115000),
                                      width-Emu(130000), so_what_h-Emu(130000))
        tf = tb.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Emu(0)
        tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.NONE
        para = tf.paragraphs[0]; para.alignment = PP_ALIGN.LEFT; para.line_spacing = 1.15
        run = para.add_run(); run.text = so_what
        run.font.size = Pt(6.5); run.font.color.rgb = RGBColor(0x55,0x55,0x55); run.font.name = 'Calibri'

    def gen_sowhat(ape_key, cnt_key, title_word):
        ape = data[ape_key]; cnt = data[cnt_key]
        n_weeks = max((len(v) for v in ape.values()), default=14)
        line_tot = {n:(sum(ape.get(n,[])), sum(cnt.get(n,[]))) for n in order}
        grand = sum(v for v,_ in line_tot.values())
        if grand == 0: return f"{title_word}数据暂缺。"
        top = max(line_tot.items(), key=lambda x:x[1][0])
        top_pct = top[1][0]/grand*100
        wt = [sum((ape.get(n,[0]*n_weeks)[i] if i<len(ape.get(n,[])) else 0) for n in order) for i in range(n_weeks)]
        peak_w = wt.index(max(wt))+1; peak_v = max(wt)/1e6
        nonzero = [(i,v) for i,v in enumerate(wt) if v>0]
        low_i, low_v = min(nonzero, key=lambda x:x[1]) if nonzero else (0,0)
        return (f"{title_word}总量{grand/1e6:.1f}M。"
                f"{top[0]}领跑，累计{top[1][0]/1e6:.1f}M/{int(top[1][1])}件，占比{top_pct:.0f}%。"
                f"周度峰值W{peak_w:02d} {peak_v:.1f}M，低谷W{low_i+1:02d} {low_v/1e6:.1f}M，波动较大需关注节奏。")

    draw_matrix(Q_REGION, "Q  周度预约业绩热力矩阵（APE in M）", 'appt_ape', 'appt_cnt',
                gen_sowhat('appt_ape','appt_cnt','预约'))
    draw_matrix(R_REGION, "R  周度签单业绩热力矩阵（APE in M）", 'sign_ape', 'sign_cnt',
                gen_sowhat('sign_ape','sign_cnt','签单'))
    draw_matrix(S_REGION, "S  周度批核业绩热力矩阵（APE in M）", 'app_ape', 'app_cnt',
                gen_sowhat('app_ape','app_cnt','批核'))

    p.save(out)
    print(f"[✓] Heat matrix → {out.name}")


# ============================================================================
if __name__ == "__main__":
    for f in [CFG.here / CFG.s2_csv, CFG.here / CFG.s3_csv]:
        if not f.exists():
            print(f"[err] missing input: {f}"); sys.exit(1)
    patch_weekly_deck(CFG)
    patch_heat_matrix(CFG)
    print("\nDone.")
