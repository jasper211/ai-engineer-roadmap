#!/usr/bin/env python3
"""
final_gap_patch.py — close the last gaps left by update_ppt.py + apply_w14_patches.py

Covers:
  1. Slide 3 — Sunlife license table (JF / UNIWIN / DW-Non-Bank / Sub Total / DW Bank × 6 cols)
  2. Slide 3 — TOP10 product table (10 rows + 合计 row × 7 cols)
  3. Slide 7 — Q / R / S heat-matrix titles

Non-goals:
  - ALICE-口径 columns on the license table (external data source, not in CSV)
  - TA / 3 Items Total rows (ALICE-only, external)
  - So What text (human commentary)
"""
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from data_loader import parse_blocks, num

# Reuse data loader from apply_w14_patches for the S3 weekly sections
from apply_w14_patches import load_rows, parse_section_weekly_all, CFG as W14_CFG
from sowhat_slots import find_sowhat_slots
import sowhat_generators as SW_GEN

IN_PPT  = "周业绩汇报PPT_AUTO_UPDATED_updated.pptx"
OUT_PPT = "周业绩汇报PPT_FINAL.pptx"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def to_m(v):
    return round(num(v) / 1_000_000, 2)

def fmt_m(v, zero_style="keep"):
    """Format as '45.86M'. For zero, default to '0M' to match REF style.
       Some cells use '0' in the template — caller can override via zero_style='bare'."""
    if v == 0:
        return "0" if zero_style == "bare" else "0M"
    return f"{v:.2f}M"

def set_shape_text(shape, new_text):
    """Replace text of a shape preserving the first run's formatting."""
    tf = shape.text_frame
    if not tf.paragraphs:
        tf.text = new_text
        return
    p = tf.paragraphs[0]
    if not p.runs:
        p.text = new_text
        return
    # keep first run, wipe its text, remove subsequent runs
    first_run = p.runs[0]
    first_run.text = new_text
    # Delete extra runs in the same paragraph
    from lxml import etree
    r_el = first_run._r
    for sib in list(r_el.itersiblings()):
        if sib.tag.endswith("}r"):
            sib.getparent().remove(sib)
    # Delete all paragraphs after the first
    p_el = p._p
    for sib in list(p_el.itersiblings()):
        if sib.tag.endswith("}p"):
            sib.getparent().remove(sib)


def find_shape(slide, row_y_target, center_x_target, y_tol=80000, x_tol=80000):
    """Find the shape whose top is within y_tol of row_y_target and whose
       horizontal center is within x_tol of center_x_target.
       Returns the closest match (by euclidean distance in EMU)."""
    best = None
    best_dist = None
    for sh in slide.shapes:
        if not sh.has_text_frame or sh.left is None or sh.top is None:
            continue
        cx = sh.left + (sh.width or 0) // 2
        dy = sh.top - row_y_target
        dx = cx - center_x_target
        if abs(dy) > y_tol or abs(dx) > x_tol:
            continue
        dist = dx*dx + dy*dy
        if best_dist is None or dist < best_dist:
            best = sh
            best_dist = dist
    return best


def find_shape_in_xrange(slide, row_y_target, x_min, x_max, y_tol=120000,
                          exclude_texts=()):
    """Find shape in [x_min, x_max] center_x range at row_y. If multiple,
       return the one with the widest textbox (usually the real data cell,
       not a stray marker)."""
    candidates = []
    for sh in slide.shapes:
        if not sh.has_text_frame or sh.left is None or sh.top is None:
            continue
        if abs(sh.top - row_y_target) > y_tol:
            continue
        cx = sh.left + (sh.width or 0) // 2
        if not (x_min <= cx <= x_max):
            continue
        t = sh.text_frame.text.strip()
        if t in exclude_texts:
            continue
        candidates.append((sh.width or 0, sh))
    if not candidates:
        return None
    candidates.sort(reverse=True)  # widest first
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Slide 3 — license table (block A)
# ---------------------------------------------------------------------------

# Row y-centers (top coords, EMU) measured from the template.
# The row-label column ("JF" / "UNIWIN" / …) sits at a slightly different y
# than its data cells in some rows, so we match against the DATA cell y.
LICENSE_ROWS = [
    # (csv_row_name, y_target)  — y坐标从PPT形状扫描确认
    ("JF",           1809750),
    ("UNIWIN",       2056765),
    ("DW-Non-Bank",  2303780),
    ("EG",           2555240),   # 之前缺失此行，导致EG数据漏写、下方行全部错位
    ("Sub Total",    2807970),   # 之前错误值2540000实为EG行坐标
    ("DW Bank",      3054985),   # 之前错误值2797810实为Sub Total坐标
]

# Column center_x-targets (EMU) — measured.
# FIXED: use rolling window (last 4 months) so May-26 replaces Jan-26 when 5 months exist
_LICENSE_COL_X = [1599565, 3308350, 5100320, 6916420]  # x-positions for 4 month cols
_LICENSE_EXTRA_X = [8575040, 10428922]                  # x-positions for 未批核, 本月已递交

def _get_license_cols(s1_h_df):
    """Return LICENSE_COLS with rolling window: last 4 months from CSV."""
    import re as _re_lc
    all_months = sorted([
        c for c in s1_h_df.columns
        if _re_lc.match(r"^\d{4}-\d{2}$", str(c))
    ])
    rolling = all_months[-4:] if len(all_months) >= 4 else all_months
    cols = list(zip(rolling, _LICENSE_COL_X[:len(rolling)]))
    cols += [("未批核", _LICENSE_EXTRA_X[0]), ("本月已递交", _LICENSE_EXTRA_X[1])]
    return cols


def patch_license_table(slide, S1_H):
    """
    Rewrite system-side cells (Jan..Apr, 未批核, 本月已递交) for 5 license rows.
    ALICE columns are LEFT ALONE.
    Returns (hits, misses).
    """
    hits = misses = 0
    for csv_row, row_y in LICENSE_ROWS:
        row_df = S1_H[S1_H["牌照"] == csv_row]
        if len(row_df) == 0:
            print(f"  [license] csv row missing: {csv_row}")
            misses += len(LICENSE_COLS)
            continue
        row = row_df.iloc[0]
        for csv_col, col_x in _get_license_cols(S1_H):
            raw = row.get(csv_col)
            if raw is None:
                continue
            val_m = to_m(raw)
            new_txt = fmt_m(val_m)
            sh = find_shape(slide, row_y, col_x)
            if sh is None:
                print(f"  [license] MISS ({csv_row}, {csv_col}) "
                      f"target=(y={row_y}, x={col_x})")
                misses += 1
                continue
            set_shape_text(sh, new_txt)
            hits += 1
    return hits, misses


# ---------------------------------------------------------------------------
# Slide 3 — TOP10 product table (block B)
# ---------------------------------------------------------------------------

# Row y-targets for the 10 data rows (from dump: y=4436618 .. 6312967, step~208k)
TOP10_ROW_Y_START = 4436618
TOP10_ROW_Y_STEP  = 208483
TOP10_TOTAL_Y     = 6502273

# Column center_x-targets (EMU)
TOP10_COL_RANK     =  6610000
TOP10_COL_CARRIER  =  6970000
TOP10_COL_PRODUCT  =  7900000     # between 778–861 — fuzzy
TOP10_COL_DISCOUNT =  9170000     # 修正：实际Text 110形状cx约9136~9189，原值8870000导致误选产品名列
TOP10_COL_COUNT    =  9910000
TOP10_COL_APE      = 10690000
TOP10_COL_AVG      = 11550000


def format_discount(v):
    """S4 discount may be:
       - '8%' (string with % sign — pass through after normalizing)
       - '0.07' (decimal — convert to percent)
       - '' / '-' / NaN — display as '-'."""
    s = str(v).strip()
    if s in ("", "-", "—", "nan", "None"):
        return "-"
    # If already in percent form (e.g. '8%', '20%', '100%'), normalize and return
    if s.endswith("%"):
        try:
            f = float(s.rstrip("%").strip())
            if f <= 0:
                return "-"
            return f"{round(f):.0f}%"
        except ValueError:
            return "-"
    # Otherwise treat as decimal (0.07 → 7%)
    try:
        f = float(s)
    except ValueError:
        return "-"
    if f <= 0:
        return "-"
    return f"{round(f*100):.0f}%"


def fmt_avg_wan(ape_yuan, count):
    """件均(万) = APE / 件数 / 10000, rounded to 1 decimal."""
    if count == 0:
        return "0.0万"
    avg_wan = ape_yuan / count / 10000
    return f"{avg_wan:.1f}万"


def patch_top10_table(slide, S4_C):
    """Rewrite TOP10 rows (rank 1..10) + 合计 row.
       Filter: 永明 (Sunlife) products only, sorted by APE desc."""
    hits = misses = 0
    if S4_C is None or len(S4_C) == 0 or "APE" not in S4_C.columns or "保司" not in S4_C.columns:
        print("  ! S4 C section missing required columns — skipping TOP10 product table")
        return hits, misses
    df = S4_C.copy()
    df["_ape"] = df["APE"].apply(num)
    df = df[df["保司"] == "永明"]
    df = df.sort_values("_ape", ascending=False).head(10).reset_index(drop=True)

    for i in range(10):
        row_y = TOP10_ROW_Y_START + i * TOP10_ROW_Y_STEP
        if i < len(df):
            rec = df.iloc[i]
            carrier   = str(rec.get("保司", "")).strip()
            product   = str(rec.get("产品名称", "")).strip()
            year      = str(rec.get("年期", "")).strip()
            # 年期格式化为整数：'5.0' → '5'，'1.0' → '1'
            try:
                year = str(int(float(year))) if year else ""
            except (ValueError, TypeError):
                pass
            disc      = format_discount(rec.get("首年折扣", ""))
            count_i   = int(num(rec.get("件数", 0)))
            ape_yuan  = num(rec.get("APE", 0))
            ape_m     = round(ape_yuan / 1_000_000, 2)
            avg_w     = fmt_avg_wan(ape_yuan, count_i)
            prod_disp = f"{product}（{year}年）" if year else product

            cells = [
                (TOP10_COL_RANK,     str(i+1), 'point'),
                (TOP10_COL_CARRIER,  carrier, 'point'),
                (None,               prod_disp, 'xrange_product'),
                (TOP10_COL_DISCOUNT, disc, 'point'),
                (TOP10_COL_COUNT,    str(count_i), 'point'),
                (TOP10_COL_APE,      f"{ape_m:.2f}M", 'point'),
                (TOP10_COL_AVG,      avg_w, 'point'),
            ]
        else:
            # blank row
            cells = [
                (TOP10_COL_RANK,     str(i+1), 'point'),
                (TOP10_COL_CARRIER,  "-", 'point'),
                (None,               "-", 'xrange_product'),
                (TOP10_COL_DISCOUNT, "-", 'point'),
                (TOP10_COL_COUNT,    "-", 'point'),
                (TOP10_COL_APE,      "-", 'point'),
                (TOP10_COL_AVG,      "-", 'point'),
            ]

        for col_x, new_txt, kind in cells:
            if kind == 'xrange_product':
                sh = find_shape_in_xrange(
                    slide, row_y, 7_300_000, 8_700_000, y_tol=120000,
                    exclude_texts=('-', '产品名称（签单期）'))
                if sh is None:
                    print(f"  [top10] MISS row={i+1} (product name)")
                    misses += 1
                    continue
            else:
                # 折扣列用更严格的x_tol，避免误选产品名列的宽形状
                x_tol_use = 100000 if col_x == TOP10_COL_DISCOUNT else 300000
                sh = find_shape(slide, row_y, col_x, y_tol=120000, x_tol=x_tol_use)
                if sh is None:
                    print(f"  [top10] MISS row={i+1} x={col_x}")
                    misses += 1
                    continue
            set_shape_text(sh, new_txt)
            hits += 1

    # 合计 row: 件数 + APE only (no rank/carrier/product/discount/avg cells)
    total_count = int(df["件数"].apply(num).sum())
    total_ape_m = df["_ape"].sum() / 1_000_000
    total_cells = [
        (TOP10_COL_COUNT, f"{total_count}件"),
        (TOP10_COL_APE,   f"{total_ape_m:.1f}M"),  # REF uses 1 decimal here
    ]
    for col_x, new_txt in total_cells:
        sh = find_shape(slide, TOP10_TOTAL_Y, col_x, y_tol=150000, x_tol=500000)
        if sh is None:
            print(f"  [top10] MISS total x={col_x}")
            misses += 1
            continue
        set_shape_text(sh, new_txt)
        hits += 1

    return hits, misses


# ---------------------------------------------------------------------------
# Slide 7 — heat matrix titles
# ---------------------------------------------------------------------------

SLIDE7_TITLE_UPDATES = [
    # (substring_to_match, new_title)
    ("渠道贡献构成",       "Q  周度预约业绩热力矩阵（APE in M）"),
    ("模块B/C",            "R  周度签单业绩热力矩阵（APE in M）"),
    ("S  批核业绩热力矩阵", "S  周度批核业绩热力矩阵（APE in M）"),
]


# ---------------------------------------------------------------------------
# So What — data-driven blurbs for every label in the deck
# ---------------------------------------------------------------------------

def patch_all_sowhat(prs, ctx):
    """Walk every 'So What' slot and overwrite its content text with fresh,
       data-driven Chinese narrative generated from the current CSVs.
       Returns (hits, misses, orphans)."""
    slots = find_sowhat_slots(prs)
    hits = misses = orphans = 0
    for slot in slots:
        if slot['type'] == 'ORPHAN' or slot['content'] is None:
            orphans += 1
            continue
        label = slot['label']
        gen = SW_GEN.lookup_generator(slot['slide'], label.top, label.left)
        if gen is None:
            # No registered generator for this slot
            misses += 1
            print(f"  [so-what] no generator for slide {slot['slide']+1} "
                  f"y={label.top} x={label.left}")
            continue
        try:
            new_text = gen(ctx)
        except Exception as e:
            print(f"  [so-what] generator crashed on slide {slot['slide']+1}: {e}")
            misses += 1
            continue

        if slot['type'] == 'MERGED':
            # Label and content in one shape — write "So What：" + new_text
            set_shape_text(label, f"So What：  {new_text}")
        else:
            # Separate content shape — overwrite it
            set_shape_text(slot['content'], new_text)
        hits += 1

    return hits, misses, orphans


def dedupe_t_table_ghosts(slide):
    """
    update_ppt.py's heatmatrix_cloner accidentally clones 8 cells from the
    T 时效 table (at x~11821170) when building the W14 heat-matrix column.
    Remove those duplicates so slide 7 matches the reference.

    Heuristic: find shapes at left >= 11_700_000 that have the same text as
    another shape in the T-area (left >= 11_400_000, top >= 4_000_000) —
    the originals stay at x ~= 11_497_845, ghosts land at x ~= 11_821_170.
    """
    ghosts = []
    for sh in list(slide.shapes):
        if not sh.has_text_frame or sh.left is None or sh.top is None:
            continue
        if sh.left < 11_700_000 or sh.top < 4_000_000:
            continue
        t = sh.text_frame.text.strip()
        if not t or len(t) > 5:
            continue
        # Look for a sibling at the same y with the same text but smaller x
        for other in slide.shapes:
            if other is sh or not other.has_text_frame:
                continue
            if other.left is None or other.top is None:
                continue
            if abs(other.top - sh.top) > 15000:
                continue
            if other.left >= sh.left:
                continue
            if other.text_frame.text.strip() == t:
                ghosts.append(sh)
                break

    for g in ghosts:
        g._element.getparent().remove(g._element)
    return len(ghosts)


def patch_slide7_titles(slide):
    hits = 0
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        t = sh.text_frame.text.strip()
        if not t or len(t) > 80:
            continue
        for marker, new_title in SLIDE7_TITLE_UPDATES:
            if marker in t and t != new_title:
                set_shape_text(sh, new_title)
                print(f"  [slide7 title] {t!r} → {new_title!r}")
                hits += 1
                break
    return hits


# ---------------------------------------------------------------------------
# Slide 7 — rebuild Q / R / S heat matrices in place
# ---------------------------------------------------------------------------
#
# Design:
#   1. For each matrix, identify the region (bounding box) on slide 7
#   2. Remember the "So What" shapes inside that region (they stay untouched)
#   3. Delete every OTHER shape inside the region (title bar, row labels,
#      week headers, data cells, rectangles …)
#   4. Redraw the matrix from scratch using fresh S3 data and 7-row business
#      order — stopping at the top of the So What panel so we don't overlap
#   5. Leave the right-bottom quadrant alone (T 时效 table lives there)

# Regions on slide 7 (EMU). These clip the right edge of S so we don't collide
# with the T 时效 table (x > ~6_200_000).
HEAT_REGIONS = {
    # Aligned with T table: same width (5888736), same title bar height (256032)
    # T outer box: left=6163056, width=5888736 → right=12051792
    'Q': (182_880,    560_000,   6_071_616,  3_150_000),   # 182880+5888736=6071616
    'R': (6_163_056,  560_000,  12_051_792,  3_150_000),   # 6163056+5888736=12051792
    'S': (182_880,  3_657_600,   6_071_616,  6_250_000),   # same width as Q
}

# 7-row order for the heat matrix rows (from W14 config)
# Each entry: (csv_lookup_name, display_name)
HEAT_ORDER = [
    ('天领业务',      '天领业务'),
    ('成事家办',      '成事家办'),
    ('BK业务',       'BK业务'),
    ('同行经代',      '同行经代'),
    ('永明经代',      '永明经代'),
    ('合伙转介业务',   '合伙转介'),   # CSV has "合伙转介业务", REF displays "合伙转介"
    ('ICLUB业务',    'ICLUB业务'),
]
HEAT_ROW_COLORS = {
    # Deep saturated base colors matching the 0404 template style.
    # Background opacity is scaled per cell so higher APE → darker cell.
    '天领业务':     (0x29, 0x80, 0xB9),   # 蓝 (was 模板里的 '天领')
    '成事家办':     (0x37, 0x41, 0x51),   # 深灰
    'BK业务':      (0x1F, 0x38, 0x64),   # 深蓝(navy)
    '同行经代':     (0xE6, 0x7E, 0x22),   # 橙
    '永明经代':     (0x1A, 0x7A, 0x3F),   # 深绿
    '合伙转介业务':  (0x94, 0xA3, 0xB8),   # 灰蓝
    'ICLUB业务':   (0x8E, 0x44, 0xAD),   # 紫
}
HEAT_TITLE_BAR = (0x7E, 0x1F, 0x1F)

# Alpha scaling: low values → more transparent (washed out); high values → full opacity.
# Range is [MIN_ALPHA_PCT, 100%] mapped linearly over v/vmax in each matrix.
HEAT_ALPHA_MIN = 0.25   # min cell opacity for tiny non-zero values
HEAT_ALPHA_MAX = 1.00   # max cell opacity (= row max value)
# Text color threshold: if cell opacity >= this, use white text; else use base color
HEAT_TEXT_WHITE_THRESHOLD = 0.55

# Preserved shape names from the template So-What panels (identified by y-position)
# y=3197987 for Q/R so what, y=6291072 for S so what
SOWHAT_Y_BANDS = [
    (3_100_000, 3_700_000),  # Q + R so what
    (6_200_000, 6_800_000),  # S so what
]


def _is_sowhat_shape(sh):
    """A shape is preserved if its top falls in a So-What y-band AND it's not
       a title/matrix element. Specifically: we keep anything whose top is in
       the band AND contains 'So What' text OR is textually unrelated to a
       matrix (has non-numeric content > 40 chars)."""
    if sh.top is None:
        return False
    for y0, y1 in SOWHAT_Y_BANDS:
        if y0 <= sh.top <= y1:
            if sh.has_text_frame:
                t = sh.text_frame.text.strip()
                if 'So What' in t or len(t) > 40:
                    return True
            return True  # keep rectangles/decorations too
    return False


def _shape_in_region(sh, region):
    if sh.left is None or sh.top is None:
        return False
    l, t, r, b = region
    cx = sh.left + (sh.width or 0) // 2
    cy = sh.top + (sh.height or 0) // 2
    return l <= cx <= r and t <= cy <= b


def _shape_in_t_table(sh):
    """Bottom-right quadrant: T 时效 table. Never touch."""
    if sh.left is None or sh.top is None:
        return False
    return sh.left >= 6_100_000 and sh.top >= 3_650_000


def rebuild_heat_matrix_on_slide7(slide, s3_rows):
    """
    Clear Q/R/S matrix shapes on slide 7 (preserving So-What + T-table),
    then redraw each matrix from fresh data.

    Returns a dict of stats.
    """
    # --- Load data
    data = {}
    weeks = None
    for section, out_key in [
        (W14_CFG.s3_heat_appt,     'appt_ape'),
        (W14_CFG.s3_heat_appt_cnt, 'appt_cnt'),
        (W14_CFG.s3_heat_sign,     'sign_ape'),
        (W14_CFG.s3_heat_sign_cnt, 'sign_cnt'),
        (W14_CFG.s3_heat_app,      'app_ape'),
        (W14_CFG.s3_heat_app_cnt,  'app_cnt'),
    ]:
        w, d = parse_section_weekly_all(s3_rows, section)
        if weeks is None:
            weeks = w
        data[out_key] = d

    n_weeks = len(weeks)

    # --- 15-week sliding window: always show the most recent 15 weeks ---
    HEAT_WINDOW = 15
    if n_weeks > HEAT_WINDOW:
        start_idx = n_weeks - HEAT_WINDOW
        weeks = weeks[start_idx:]
        for key in data:
            trimmed = {}
            for biz, vals in data[key].items():
                trimmed[biz] = vals[start_idx:]
            data[key] = trimmed
        n_weeks = len(weeks)

    # --- Capture so-what shapes so we don't delete them
    preserved_ids = set()
    for sh in slide.shapes:
        if _is_sowhat_shape(sh) or _shape_in_t_table(sh):
            preserved_ids.add(id(sh._element))

    # --- Delete Q/R/S shapes that are NOT preserved
    deleted = 0
    for region_key, region in HEAT_REGIONS.items():
        for sh in list(slide.shapes):
            if id(sh._element) in preserved_ids:
                continue
            if _shape_in_region(sh, region):
                sh._element.getparent().remove(sh._element)
                deleted += 1

    # --- Helper drawers (clone of patch_heat_matrix logic)
    def add_text(left, top, w, h, text, size=9, bold=False,
                 color=RGBColor(0x20, 0x20, 0x20), align=PP_ALIGN.CENTER):
        tb = slide.shapes.add_textbox(left, top, w, h)
        tf = tb.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Emu(0)
        tf.word_wrap = False
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para = tf.paragraphs[0]
        para.alignment = align
        run = para.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = 'Calibri'
        return tb

    def add_rect(left, top, w, h, fill, line=None, alpha=None):
        """Add a rectangle. If `alpha` is given (0.0–1.0), inject <a:alpha>
           into the solidFill so the shape renders partially transparent."""
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, w, h)
        if fill is None:
            shp.fill.background()
        else:
            shp.fill.solid()
            shp.fill.fore_color.rgb = fill
            if alpha is not None and alpha < 1.0:
                # Inject <a:alpha val="NNNNN"/> under <a:srgbClr>
                from lxml import etree
                NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
                srgb = shp._element.find(f'.//{{{NS_A}}}solidFill/{{{NS_A}}}srgbClr')
                if srgb is not None:
                    alpha_el = etree.SubElement(srgb, f'{{{NS_A}}}alpha')
                    alpha_el.set('val', str(int(max(0.0, min(1.0, alpha)) * 100000)))
        if line is None:
            shp.line.fill.background()
        else:
            shp.line.color.rgb = line
            shp.line.width = Emu(3175)
        shp.shadow.inherit = False
        return shp

    def value_to_alpha(v, vmax):
        """Map a value [0, vmax] linearly into [HEAT_ALPHA_MIN, HEAT_ALPHA_MAX]."""
        if vmax <= 0 or v <= 0:
            return HEAT_ALPHA_MIN
        ratio = min(v / vmax, 1.0)
        return HEAT_ALPHA_MIN + (HEAT_ALPHA_MAX - HEAT_ALPHA_MIN) * ratio

    def draw_matrix(region, title_text, ape_key, cnt_key):
        left0, top0, right0, bottom0 = region
        width = right0 - left0   # exact match with T table width
        title_h = Emu(256032)

        # Title bar + title text
        add_rect(left0, top0, width, title_h,
                 RGBColor(*HEAT_TITLE_BAR), line=RGBColor(*HEAT_TITLE_BAR))
        add_text(left0 + Emu(80000), top0, width, title_h,
                 title_text, size=11, bold=True,
                 color=RGBColor(0xFF, 0xFF, 0xFF), align=PP_ALIGN.LEFT)

        # Week header row
        label_w = Emu(680000)
        cells_left = left0 + label_w
        cell_w = (width - label_w) // n_weeks
        header_top = top0 + title_h + Emu(20000)
        header_h = Emu(170000)
        for i in range(n_weeks):
            # Use actual week label (e.g. "2026W03" → "W03")
            wlabel = weeks[i].replace('2026', '') if i < len(weeks) else f"W{i+1:02d}"
            add_text(cells_left + cell_w * i, header_top, cell_w, header_h,
                     wlabel, size=8, bold=(i >= n_weeks - 2),
                     color=RGBColor(0x66, 0x66, 0x66))

        # Body
        body_top = header_top + header_h + Emu(10000)
        avail = bottom0 - body_top - Emu(30000)
        row_h = min(Emu(265000), avail // (len(HEAT_ORDER) + 1))

        ape = data[ape_key]
        cnt = data[cnt_key]

        for ri, (lookup, display) in enumerate(HEAT_ORDER):
            rt = body_top + row_h * ri
            add_text(left0 + Emu(20000), rt, label_w - Emu(30000), row_h,
                     display, size=9, bold=True,
                     color=RGBColor(0x30, 0x30, 0x30), align=PP_ALIGN.LEFT)
            vals = ape.get(lookup, [0] * n_weeks)
            cnts = cnt.get(lookup, [0] * n_weeks)
            base = HEAT_ROW_COLORS.get(lookup, (0xBB, 0xBB, 0xBB))
            base_rgb = RGBColor(*base)
            # Per-row max for alpha scaling — makes each row's max value
            # fully opaque, regardless of other rows' peaks.
            row_max = max([v for v in vals if v > 0] or [1])
            for i in range(n_weeks):
                cl = cells_left + cell_w * i
                v = vals[i] if i < len(vals) else 0
                c = cnts[i] if i < len(cnts) else 0
                if v > 0:
                    alpha = value_to_alpha(v, row_max)
                    add_rect(cl + Emu(6000), rt + Emu(6000),
                             cell_w - Emu(12000), row_h - Emu(12000),
                             base_rgb,
                             line=RGBColor(0xFF, 0xFF, 0xFF),
                             alpha=alpha)
                    # Text color: white on opaque cells, base color on
                    # washed-out (low value) cells to preserve contrast.
                    if alpha >= HEAT_TEXT_WHITE_THRESHOLD:
                        tcol = RGBColor(0xFF, 0xFF, 0xFF)
                    else:
                        tcol = base_rgb
                    add_text(cl, rt + Emu(8000), cell_w, Emu(130000),
                             f"{v/1e6:.1f}M", size=8, bold=True,
                             color=tcol)
                    add_text(cl, rt + row_h - Emu(125000), cell_w, Emu(115000),
                             f"{int(c)}件", size=7,
                             color=tcol)

        # Totals row
        tot_rt = body_top + row_h * len(HEAT_ORDER)
        add_text(left0 + Emu(20000), tot_rt, label_w - Emu(30000), row_h,
                 "合计", size=10, bold=True,
                 color=RGBColor(0x20, 0x20, 0x20), align=PP_ALIGN.LEFT)
        for i in range(n_weeks):
            tv = sum((ape.get(lookup, [0] * n_weeks)[i]
                      if i < len(ape.get(lookup, [])) else 0)
                     for lookup, _ in HEAT_ORDER)
            tc = sum((cnt.get(lookup, [0] * n_weeks)[i]
                      if i < len(cnt.get(lookup, [])) else 0)
                     for lookup, _ in HEAT_ORDER)
            cl = cells_left + cell_w * i
            if tv > 0:
                add_rect(cl + Emu(6000), tot_rt + Emu(6000),
                         cell_w - Emu(12000), row_h - Emu(12000),
                         RGBColor(0xEC, 0xEC, 0xEC),
                         line=RGBColor(0xFF, 0xFF, 0xFF))
                add_text(cl, tot_rt + Emu(8000), cell_w, Emu(130000),
                         f"{tv/1e6:.1f}M", size=8, bold=True,
                         color=RGBColor(0x2C, 0x3E, 0x50))
                add_text(cl, tot_rt + row_h - Emu(125000), cell_w, Emu(115000),
                         f"{int(tc)}件", size=7,
                         color=RGBColor(0x7A, 0x7A, 0x7A))

    draw_matrix(HEAT_REGIONS['Q'],
                "Q  周度预约业绩热力矩阵（APE in M）",
                'appt_ape', 'appt_cnt')
    draw_matrix(HEAT_REGIONS['R'],
                "R  周度签单业绩热力矩阵（APE in M）",
                'sign_ape', 'sign_cnt')
    draw_matrix(HEAT_REGIONS['S'],
                "S  周度批核业绩热力矩阵（APE in M）",
                'app_ape', 'app_cnt')

    return {'deleted': deleted, 'n_weeks': n_weeks}


# ---------------------------------------------------------------------------
# T 签批时效 table — rewrite from S3 section G
# ---------------------------------------------------------------------------

# T table row y-positions (from template inspection)
T_TABLE_ROW_YS = [4224655, 4480560, 4736465, 4992370, 5248910, 5504815, 5760720, 6060440]
T_TABLE_TOTAL_Y = 6360160
# T table column x-positions: 业务线, 件数, 件均APE(万), 平均时效, P90, 中位, 最大
T_TABLE_COL_XS = [6348095, 7130480, 7841440, 8788100, 9621920, 10537020, 11451490]
# S3 G row order (user requested: same as CSV)
T_TABLE_ROW_ORDER = ['天领业务', '成事家办', 'BK业务', '同行经代', '永明经代', '合伙转介业务', 'ICLUB业务', 'IFA业务']
# Display names
T_TABLE_DISPLAY = {
    '天领业务': '天领业务', '成事家办': '成事家办', 'BK业务': 'BK业务',
    '同行经代': '同行经代', '永明经代': '永明经代', '合伙转介业务': '合伙转介',
    'ICLUB业务': 'ICLUB', 'IFA业务': 'IFA业务',
}


def update_t_table(slide, S3):
    """Overwrite the T 签批时效 table with S3 G data.
    Strategy: for each row y-band, find shapes at the 7 known column x-positions
    and overwrite them. Remove any stale duplicate shapes from prior runs."""
    if 'G' not in S3:
        print("  [T] S3 G not found, skipping")
        return 0

    g = S3['G']
    lookup = {}
    for _, row in g.iterrows():
        name = str(row.get('业务细分', '')).strip()
        if name:
            lookup[name] = row

    hits = 0
    y_tol = 100000

    # Known column x-positions from the 0404 template
    # 业务线, 件数, 件均APE(万), 平均时效, P90, 中位, 最大
    COL_XS = [6327775, 7130480, 7841440, 8788100, 9621920, 10537020, 11451490]
    x_tol = 120000

    def set_text(sh, text):
        for para in sh.text_frame.paragraphs:
            if para.runs:
                para.runs[0].text = str(text)
                for r in para.runs[1:]:
                    r.text = ""
            else:
                run = para.add_run()
                run.text = str(text)

    def find_shape_at(target_y, target_x):
        """Find the CLOSEST text shape to (target_y, target_x)."""
        best, best_dist = None, float('inf')
        for sh in slide.shapes:
            if not sh.has_text_frame or sh.top is None or sh.left is None:
                continue
            dy = abs(sh.top - target_y)
            dx = abs(sh.left - target_x)
            if dy < y_tol and dx < x_tol:
                dist = dy + dx
                if dist < best_dist:
                    best, best_dist = sh, dist
        return best

    # Also remove stale duplicate shapes from prior pipeline runs
    # (shapes at x < 6300000 in the T-table area that don't belong to template)
    stale_removed = 0
    for sh in list(slide.shapes):
        if sh.has_text_frame and sh.top and sh.left:
            if 4200000 < sh.top < 6500000:
                # Don't remove So What shapes
                t = sh.text_frame.text.strip()
                if 'So What' in t or len(t) > 60:
                    continue
                # Shapes to the LEFT of the label column (stale duplicates from prior runs)
                if 6200000 < sh.left < 6320000:
                    sh._element.getparent().remove(sh._element)
                    stale_removed += 1
                # Shapes to the RIGHT of the 最大时效 column (stale from old template layout)
                elif sh.left > 11500000:
                    sh._element.getparent().remove(sh._element)
                    stale_removed += 1
    if stale_removed:
        print(f"  removed {stale_removed} stale T-table shapes")

    def make_vals(biz_name, row_data):
        display = T_TABLE_DISPLAY.get(biz_name, biz_name)
        if row_data is not None:
            cnt = int(num(row_data.get('件数', 0)))
            avg_ape_wan = round(num(row_data.get('件均APE', 0)) / 10000) if cnt > 0 else 0
            avg_tat = round(num(row_data.get('平均时效(天)', 0))) if cnt > 0 else 0
            p90 = round(num(row_data.get('P90时效(天)', 0))) if cnt > 0 else 0
            median = round(num(row_data.get('中位时效(天)', 0))) if cnt > 0 else 0
            max_tat = round(num(row_data.get('最大时效(天)', 0))) if cnt > 0 else 0
            return [display, str(cnt), str(avg_ape_wan), str(avg_tat),
                    str(p90), str(median), str(max_tat)]
        return [display, '0', '0', '0', '0', '0', '0']

    def set_font_color(sh, rgb_color):
        """Set all run font colors in a shape."""
        for para in sh.text_frame.paragraphs:
            for run in para.runs:
                run.font.color.rgb = rgb_color

    # Find the business line with the MAX average TAT (for red highlight)
    max_tat_biz = None
    max_tat_val = 0
    for biz_name in T_TABLE_ROW_ORDER:
        rd = lookup.get(biz_name)
        if rd is not None:
            avg = num(rd.get('平均时效(天)', 0))
            if avg > max_tat_val:
                max_tat_val = avg
                max_tat_biz = biz_name

    RED = RGBColor(0xC0, 0x39, 0x2B)
    BLACK = RGBColor(0x20, 0x20, 0x20)

    # Write each business line row
    for ri, biz_name in enumerate(T_TABLE_ROW_ORDER):
        if ri >= len(T_TABLE_ROW_YS):
            break
        ry = T_TABLE_ROW_YS[ri]
        vals = make_vals(biz_name, lookup.get(biz_name))
        is_max_row = (biz_name == max_tat_biz)
        row_color = RED if is_max_row else BLACK
        for ci, val in enumerate(vals):
            if ci < len(COL_XS):
                sh = find_shape_at(ry, COL_XS[ci])
                if sh:
                    set_text(sh, val)
                    set_font_color(sh, row_color)
                    hits += 1

    # Write 合计 row
    tot_vals = make_vals('合计', lookup.get('合计'))
    tot_vals[0] = '合计'
    for ci, val in enumerate(tot_vals):
        if ci < len(COL_XS):
            sh = find_shape_at(T_TABLE_TOTAL_Y, COL_XS[ci])
            if sh:
                set_text(sh, val)
                hits += 1

    return hits


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print(f"Loading {IN_PPT} …")
    prs = Presentation(IN_PPT)

    print("Loading CSVs …")
    S1 = parse_blocks("S1-总览仪表盘.csv")
    S3 = parse_blocks("S3-执行管理端.csv")
    S4 = parse_blocks("S4-产品端视角.csv")
    s3_rows = load_rows("S3-执行管理端.csv")

    slide3 = prs.slides[2]
    slide7 = prs.slides[6]

    print("\n[Slide 3] License table")
    h, m = patch_license_table(slide3, S1["H"])
    print(f"  license: {h} hits, {m} misses")

    print("\n[Slide 3] TOP10 product table")
    h, m = patch_top10_table(slide3, S4.get("C"))
    print(f"  top10: {h} hits, {m} misses")

    print("\n[Slide 7] Update T 签批时效 table from S3 G")
    n_t = update_t_table(slide7, S3)
    print(f"  updated {n_t} cells")

    print("\n[Slide 7] Rebuild Q/R/S heat matrices")
    stats = rebuild_heat_matrix_on_slide7(slide7, s3_rows)
    print(f"  deleted {stats['deleted']} old shapes; rebuilt 3 matrices × "
          f"({len(HEAT_ORDER)} rows × {stats['n_weeks']} weeks + totals)")

    print("\n[Slide 7] Dedupe T 时效 table ghost cells")
    n = dedupe_t_table_ghosts(slide7)
    print(f"  removed {n} ghost cells")

    print("\n[ALL SLIDES] Regenerate So What blurbs from live CSV data")
    # Auto-detect the current week from the rightmost non-zero column in S3 A-APE
    _week_cols = [c for c in S3['A-APE'].columns if c.startswith('2026W')]
    _detected_week = 'W14'
    if _week_cols:
        # The last column whose 预约 value is non-zero is current week
        _appt_row = S3['A-APE'][S3['A-APE']['阶段'] == '预约'].iloc[0]
        for c in reversed(_week_cols):
            try:
                if num(_appt_row[c]) > 0:
                    _detected_week = c.replace('2026', '')  # '2026W15' -> 'W15'
                    break
            except Exception:
                pass
    print(f"  detected current week: {_detected_week}")
    ctx = {
        'S1': S1,
        'S2': parse_blocks("S2-业务端视角.csv"),
        'S3': S3,
        'S4': S4,
        's3_rows': s3_rows,
        'current_week': _detected_week,
    }
    hits, misses, orphans = patch_all_sowhat(prs, ctx)
    print(f"  so-what: {hits} updated, {misses} missing generators, "
          f"{orphans} orphan labels")

    prs.save(OUT_PPT)
    print(f"\n✅ Saved: {OUT_PPT}")

    # ── POST-SAVE: 修复H图(永明月度趋势)的embedded xlsx ──────────────────────
    # PowerPoint读embedded xlsx而非numCache，xlsx里Apr数据是旧值(0.7/3/4)
    # 需要用S2 F/G/H合计行的正确值更新Workbook4.xlsx
    print("\n--- POST-SAVE: H图 embedded xlsx 修复 ---")
    try:
        import zipfile as _zf_h, io as _io_h, csv as _csv_h
        import openpyxl as _opx_h, xml.etree.ElementTree as _ET_h, os as _os_h

        def _read_s2_total_h(block_label):
            in_b = False; hdr = None
            with open("S2-业务端视角.csv", encoding="utf-8-sig") as _f:
                for _row in _csv_h.reader(_f):
                    if not _row: continue
                    first = _row[0].strip()
                    if first.startswith(block_label): in_b = True; continue
                    if not in_b: continue
                    if first.startswith("📌"): continue
                    if first == "业务细分": hdr = [c.strip() for c in _row]; continue
                    if first == "合计" and hdr:
                        result = {}
                        for col, val in zip(hdr[1:], _row[1:]):
                            try: result[col] = float(val.replace(",", "").strip())
                            except: result[col] = 0.0
                        return result
                    if not first and hdr: break
            return {}

        _f_ape = _read_s2_total_h("F-APE")
        _g_ape = _read_s2_total_h("G-APE")
        _h_ape = _read_s2_total_h("H-APE")
        _months = ["2026-01", "2026-02", "2026-03", "2026-04"]
        _cat_labels = ["26-Jan", "26-Feb", "26-Mar", "26-Apr"]

        # 重建 embedded xlsx
        _wb = _opx_h.Workbook()
        _ws = _wb.active; _ws.title = "Sheet1"
        _ws.cell(1,1,""); _ws.cell(1,2,"预约 APE(M)"); _ws.cell(1,3,"签单 APE(M)"); _ws.cell(1,4,"批核 APE(M)")
        for _i, (_cat, _ym) in enumerate(zip(_cat_labels, _months), 2):
            _ws.cell(_i,1,_cat)
            _ws.cell(_i,2, round(_f_ape.get(_ym,0)/1e6, 2))
            _ws.cell(_i,3, round(_g_ape.get(_ym,0)/1e6, 2))
            _ws.cell(_i,4, round(_h_ape.get(_ym,0)/1e6, 2))
        _buf = _io_h.BytesIO(); _wb.save(_buf)

        # 找H图的embedded xlsx文件名（chart7.xml对应的xlsx）
        with _zf_h.ZipFile(OUT_PPT, "r") as _zin:
            _all_h = {n: _zin.read(n) for n in _zin.namelist()}

        # 找slide3对应的chart，再找其embedded xlsx
        _prs_root = _ET_h.fromstring(_all_h["ppt/presentation.xml"])
        _sld_ids = [el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                    for el in _prs_root.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId")]
        _rels_root = _ET_h.fromstring(_all_h["ppt/_rels/presentation.xml.rels"])
        _rels = {el.get("Id"): el.get("Target") for el in _rels_root}
        _slide3_f = "ppt/" + _rels.get(_sld_ids[2], "slides/slide3.xml").lstrip("./")
        _sl3_rels_f = _slide3_f.replace("slides/slide", "slides/_rels/slide").replace(".xml", ".xml.rels")
        _sl3_rels = _ET_h.fromstring(_all_h[_sl3_rels_f])
        # chart7.xml → find its embedded xlsx via chart7.xml.rels
        for _rel in _sl3_rels:
            if "chart" in _rel.get("Type", "").lower():
                _chart_target = _rel.get("Target","").lstrip("../")
                _chart_fname = "ppt/" + _chart_target
                _chart_rels_f = _chart_fname.replace("charts/chart", "charts/_rels/chart").replace(".xml", ".xml.rels")
                if _chart_rels_f not in _all_h: continue
                _chart_rels = _ET_h.fromstring(_all_h[_chart_rels_f])
                for _cr in _chart_rels:
                    _tgt = _cr.get("Target","")
                    if "embeddings" in _tgt and _tgt.endswith(".xlsx"):
                        _xlsx_fname = "ppt/" + _tgt.lstrip("../")
                        _all_h[_xlsx_fname] = _buf.getvalue()
                        print(f"  更新: {_xlsx_fname}")
                        print(f"  Apr: 预约={_f_ape.get('2026-04',0)/1e6:.2f}M 签单={_g_ape.get('2026-04',0)/1e6:.2f}M 批核={_h_ape.get('2026-04',0)/1e6:.2f}M")

        _tmp_h = OUT_PPT + ".htmp"
        with _zf_h.ZipFile(_tmp_h, "w", _zf_h.ZIP_DEFLATED) as _zout:
            for _n, _d in _all_h.items(): _zout.writestr(_n, _d)
        _os_h.replace(_tmp_h, OUT_PPT)
        print("  H图 embedded xlsx 修复完成 ✓")
    except Exception as _e_h:
        print(f"  ⚠ H图修复失败: {_e_h}")


if __name__ == "__main__":
    main()
