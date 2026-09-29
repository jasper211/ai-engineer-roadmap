#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ppt_chart_patch.py — 直接操作chart XML更新图表数值，绕开python-pptx对非标准
grouping/缺失内嵌xlsx的chart.replace_data()限制。

移植自 raw_data/业绩报表PPT/chart_xml_patch.py（旧流水线里写得最通用、不依赖
具体模板的一段，映射报告 v0.1 判定可直接复用，逻辑原样保留，仅补充中文注释）。

策略：定位每个c:ser的c:cat(类别)和c:val(数值)，重写各自的c:numCache/c:strCache
（<c:pt idx="N"><c:v>...</c:v></c:pt> 列表 + <c:ptCount>），不改<c:f>公式字符串。
"""
from lxml import etree

NS = {
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
C = NS["c"]


def _qn(tag):
    return f"{{{C}}}{tag}"


def _find_series(root):
    return root.findall(".//c:ser", NS)


def _rewrite_cache(cache_elem, new_values, numeric=True):
    for pt in list(cache_elem.findall("c:pt", NS)):
        cache_elem.remove(pt)
    pc = cache_elem.find("c:ptCount", NS)
    if pc is None:
        pc = etree.SubElement(cache_elem, _qn("ptCount"))
        cache_elem.insert(0, pc)
    pc.set("val", str(len(new_values)))
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
    cache_name = "numCache" if numeric else "strCache"
    cache = ref_elem.find(f"c:{cache_name}", NS)
    if cache is None:
        cache = etree.SubElement(ref_elem, _qn(cache_name))
    _rewrite_cache(cache, new_values, numeric=numeric)


def _rewrite_series_values(ser, new_values):
    val = ser.find("c:val", NS)
    if val is None:
        return
    ref = val.find("c:numRef", NS)
    if ref is None:
        lit = val.find("c:numLit", NS)
        if lit is not None:
            _rewrite_cache(lit, new_values, numeric=True)
        return
    _rewrite_ref_with_cache(ref, new_values, numeric=True)


def _rewrite_series_categories(ser, new_cats):
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
    chart_part   -- python-pptx ChartPart对象（shape.chart._chartSpace所属part，
                    实际调用用 shape.chart.part）
    series_spec  -- list[list[float]]，每个内层list对应一个系列的全部数值
    categories   -- list[str]，应用到每个系列的类别标签
    series_names -- 可选 list[str]，重命名各系列
    """
    root = chart_part._element
    series = _find_series(root)
    n = min(len(series), len(series_spec))
    for i in range(n):
        ser = series[i]
        _rewrite_series_values(ser, series_spec[i])
        if categories is not None:
            _rewrite_series_categories(ser, categories)
        if series_names is not None and i < len(series_names):
            _rewrite_series_name(ser, series_names[i])


def patch_chart_dlbls(chart_part, series_index, labels):
    """重写某个系列每个数据点的自定义富文本数据标签（<c:dLbl><c:tx><c:rich>）。
    当dLbl带自定义富文本时，PowerPoint会显示这段文本而不是showVal的数值，
    所以数值和标签要分开patch。"""
    root = chart_part._element
    series = _find_series(root)
    if series_index >= len(series):
        return 0
    ser = series[series_index]
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
        runs = p.findall("a:r", NS)
        if not runs:
            continue
        first_run = runs[0]
        first_t = first_run.find("a:t", NS)
        if first_t is None:
            first_t = etree.SubElement(first_run, f"{{{NS['a']}}}t")
        first_t.text = new_text
        for extra in runs[1:]:
            p.remove(extra)
        hits += 1
    return hits
