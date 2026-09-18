"""
chart_xml_patch.py — surgical update of chart values via XML manipulation.

Works for ALL chart types, avoiding python-pptx's replace_data() failures on
charts with non-standard grouping values or missing embedded xlsx.

Strategy:
  For each chart we want to update, we locate the series elements by position,
  and rewrite:
    - <c:numCache>  (numeric values for each series / axis)
    - <c:strCache>  (category labels)

Each series has two numRef/strRef parent elements:
  - c:cat → c:numRef or c:strRef → c:strCache (categories)
  - c:val → c:numRef → c:numCache (values)

We also update <c:ptCount> and rewrite <c:pt idx="N"><c:v>...</c:v></c:pt>
inside each cache.
"""
import re
from lxml import etree

NS = {
    "c":  "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "a":  "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r":  "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
C = NS["c"]


def _qn(tag):
    return f"{{{C}}}{tag}"


def _find_series(root):
    """Return list of <c:ser> elements (across all chart-type containers)."""
    return root.findall(".//c:ser", NS)


def _rewrite_cache(cache_elem, new_values, numeric=True):
    """Rewrite a cache element in-place:
       remove existing <c:pt>, set <c:ptCount>, add new <c:pt> entries."""
    # clear existing <c:pt>
    for pt in list(cache_elem.findall("c:pt", NS)):
        cache_elem.remove(pt)
    # set / create ptCount
    pc = cache_elem.find("c:ptCount", NS)
    if pc is None:
        pc = etree.SubElement(cache_elem, _qn("ptCount"))
        cache_elem.insert(0, pc)
    pc.set("val", str(len(new_values)))
    # add new <c:pt idx=""><c:v>...</c:v></c:pt>
    for i, v in enumerate(new_values):
        pt = etree.SubElement(cache_elem, _qn("pt"))
        pt.set("idx", str(i))
        vel = etree.SubElement(pt, _qn("v"))
        if v is None:
            vel.text = ""
        elif numeric:
            vel.text = f"{float(v)}"
        else:
            vel.text = str(v)


def _rewrite_ref_with_cache(ref_elem, new_values, numeric=True):
    """Given a <c:numRef> or <c:strRef>, update its <c:numCache>/<c:strCache>.
       We do NOT touch <c:f> (formula string)."""
    cache_name = "numCache" if numeric else "strCache"
    cache = ref_elem.find(f"c:{cache_name}", NS)
    if cache is None:
        # create one
        cache = etree.SubElement(ref_elem, _qn(cache_name))
    _rewrite_cache(cache, new_values, numeric=numeric)


def _rewrite_series_values(ser, new_values):
    """Update the <c:val>/<c:numRef>/<c:numCache> of a <c:ser>."""
    val = ser.find("c:val", NS)
    if val is None:
        return
    ref = val.find("c:numRef", NS)
    if ref is None:
        # some charts use c:numLit — simpler
        lit = val.find("c:numLit", NS)
        if lit is not None:
            _rewrite_cache(lit, new_values, numeric=True)
        return
    _rewrite_ref_with_cache(ref, new_values, numeric=True)


def _rewrite_series_categories(ser, new_cats):
    """Update the <c:cat>/<c:strRef>/<c:strCache> of a <c:ser>."""
    cat = ser.find("c:cat", NS)
    if cat is None:
        return
    ref = cat.find("c:strRef", NS)
    if ref is None:
        ref = cat.find("c:numRef", NS)
    if ref is None:
        lit = cat.find("c:strLit", NS)
        if lit is not None:
            _rewrite_cache(lit, new_cats, numeric=False)
        return
    numeric = (ref.tag == _qn("numRef"))
    _rewrite_ref_with_cache(ref, new_cats, numeric=numeric)


def _rewrite_series_name(ser, new_name):
    """Update <c:tx>/<c:strRef>/<c:strCache> → 1 element with series name."""
    if new_name is None:
        return
    tx = ser.find("c:tx", NS)
    if tx is None:
        return
    ref = tx.find("c:strRef", NS)
    if ref is None:
        v = tx.find("c:v", NS)
        if v is not None:
            v.text = new_name
        return
    cache = ref.find("c:strCache", NS)
    if cache is None:
        cache = etree.SubElement(ref, _qn("strCache"))
    _rewrite_cache(cache, [new_name], numeric=False)


def patch_chart(chart_part, series_spec, categories=None, series_names=None):
    """
    chart_part     -- python-pptx ChartPart object
    series_spec    -- list[list[float]] one inner list per series
    categories     -- list[str] (applied to every series)
    series_names   -- optional list[str] renaming each series
    """
    # ChartPart inherits from XmlPart, whose `.blob` is re-serialized from
    # `self._element` (an lxml tree) on every read. So we mutate _element
    # directly — writing back to _blob has no effect.
    root = chart_part._element
    series = _find_series(root)

    # pad / trim
    n = min(len(series), len(series_spec))
    for i in range(n):
        ser = series[i]
        _rewrite_series_values(ser, series_spec[i])
        if categories is not None:
            _rewrite_series_categories(ser, categories)
        if series_names is not None and i < len(series_names):
            _rewrite_series_name(ser, series_names[i])


# ---------------------------------------------------------------------------
# Custom rich-text data-label support
# ---------------------------------------------------------------------------
# When a bar/line in a chart has a <c:dLbl> with a <c:tx><c:rich>...</c:rich>
# block, PowerPoint renders that custom text instead of the numeric value —
# even when <c:showVal val="1"/> is set. This function rewrites the inline
# <a:t> runs of each <c:dLbl> so the labels track fresh data.
#
# The input `labels` is a list of strings, one per series-point in order
# (matching <c:idx val="N"/>). Each label string replaces the ENTIRE rich
# text content of that dLbl.

def patch_chart_dlbls(chart_part, series_index, labels):
    """
    Rewrite custom-rich data-labels for one series.

    chart_part     -- python-pptx ChartPart
    series_index   -- which series (0-based) to update
    labels         -- list[str]; index i → text for <c:dLbl idx=i>
    """
    root = chart_part._element
    series = _find_series(root)
    if series_index >= len(series):
        return 0
    ser = series[series_index]

    # Find all <c:dLbl> inside this series
    dlbls = ser.findall("c:dLbls/c:dLbl", NS)
    hits = 0
    for dlbl in dlbls:
        idx_elem = dlbl.find("c:idx", NS)
        if idx_elem is None:
            continue
        try:
            idx = int(idx_elem.get("val"))
        except (TypeError, ValueError):
            continue
        if idx >= len(labels):
            continue

        new_text = labels[idx]
        tx = dlbl.find("c:tx", NS)
        if tx is None:
            continue
        rich = tx.find("c:rich", NS)
        if rich is None:
            continue
        p = rich.find("a:p", NS)
        if p is None:
            continue

        # Find all existing <a:r> and their <a:t>. We'll collapse them into
        # a single run holding the new text (preserving the FIRST run's
        # formatting by keeping its <a:rPr>).
        runs = p.findall("a:r", NS)
        if not runs:
            continue
        first_run = runs[0]
        # set first run's text to new_text
        first_t = first_run.find("a:t", NS)
        if first_t is None:
            first_t = etree.SubElement(first_run, f"{{{NS['a']}}}t")
        first_t.text = new_text
        # remove subsequent runs
        for extra in runs[1:]:
            p.remove(extra)
        hits += 1
    return hits
