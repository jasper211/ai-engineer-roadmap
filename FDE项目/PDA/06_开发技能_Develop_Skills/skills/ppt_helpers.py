#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ppt_helpers.py — 结构化定位PPT元素的通用工具函数。

移植自 raw_data/业绩报表PPT/apply_w14_patches.py 里"不依赖具体模板坐标"的部分
（映射报告 v0.1 第6.3节点名的可复用函数）。设计原则：
  - 按标题关键词找页，不按页码索引
  - 按表头文字找表，不按shape id
  - 按图表内类别内容找图，不按shape id
这样模板稍作排版调整（挪动一个文本框）不会让整页失效，是旧代码库里唯一
体现"参数化定位"思想的部分，新Skill的所有页面都应该用这套范式，不要回到
旧update_ppt.py那种手测EMU坐标再硬编码的方式。
"""
from typing import Optional


def set_tf(tf, text: str):
    """替换text_frame全部内容为text，保留第一个run的字体/颜色格式。"""
    ref = None
    for para in tf.paragraphs:
        for r in para.runs:
            ref = r
            break
        if ref:
            break
    for para in list(tf.paragraphs):
        for r in list(para.runs):
            r._r.getparent().remove(r._r)
    para = tf.paragraphs[0]
    nr = para.add_run()
    nr.text = text
    if ref is not None:
        if ref.font.size:
            nr.font.size = ref.font.size
        if ref.font.bold is not None:
            nr.font.bold = ref.font.bold
        if ref.font.name:
            nr.font.name = ref.font.name
        try:
            if ref.font.color and ref.font.color.rgb:
                nr.font.color.rgb = ref.font.color.rgb
        except Exception:
            pass


def set_cell(cell, text: str):
    set_tf(cell.text_frame, text)


def strip_manual_dlbls(chart):
    """删除<c:dLbl>里手动覆盖的<c:tx>——修复PowerPoint里手改过的旧数据标签
    在重新patch数值后仍显示旧文本的问题。"""
    ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
    for dlbl in chart._chartSpace.findall(".//c:dLbl", ns):
        for tx in dlbl.findall("c:tx", ns):
            dlbl.remove(tx)


def find_slide_with_all(prs, keywords: list) -> Optional[int]:
    """返回第一张文本里同时包含全部keywords的slide索引，找不到返回None。"""
    for idx, slide in enumerate(prs.slides):
        text = " ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)
        if all(kw in text for kw in keywords):
            return idx
    return None


def find_table_by_header(slide, header_signature: str, min_cols: int = 1):
    """按左上角单元格文字找表格（至少min_cols列）。"""
    for sh in slide.shapes:
        if not sh.has_table:
            continue
        t = sh.table
        if t.rows[0].cells[0].text.strip() == header_signature and len(t.columns) >= min_cols:
            return t
    return None


def find_table_exact_cols(slide, header_signature: str, exact_cols: int):
    for sh in slide.shapes:
        if not sh.has_table:
            continue
        t = sh.table
        if t.rows[0].cells[0].text.strip() == header_signature and len(t.columns) == exact_cols:
            return t
    return None


def iter_charts(slide):
    """遍历slide上全部图表，yield (chart对象, 类别标签list)。"""
    for sh in slide.shapes:
        if not sh.has_chart:
            continue
        ch = sh.chart
        cats = []
        for plot in ch.plots:
            try:
                cats = list(plot.categories)
                break
            except Exception:
                pass
        yield ch, cats


def fmt_m(v, decimals=2):
    return f"{v/1e6:.{decimals}f}M"


def find_text_shape_above(slide, shape, keywords: list = None):
    """找shape正上方、水平方向有重叠的最近文本框（用于定位KPI卡片的标签）。"""
    if shape.top is None or shape.left is None:
        return None
    best_sh = None
    best_dy = 10**9
    for sh in slide.shapes:
        if sh is shape or not sh.has_text_frame:
            continue
        if sh.top is None or sh.left is None:
            continue
        if sh.top >= shape.top:
            continue
        if (sh.left + (sh.width or 0)) < shape.left:
            continue
        if sh.left > (shape.left + (shape.width or 0)):
            continue
        if keywords is not None:
            txt = sh.text_frame.text
            if not any(kw in txt for kw in keywords):
                continue
        dy = shape.top - sh.top
        if dy < best_dy:
            best_dy = dy
            best_sh = sh
    return best_sh


def _para_text(para):
    return "".join(r.text for r in para.runs)


def _set_para_text(para, new_text):
    runs = list(para.runs)
    if not runs:
        return
    runs[0].text = new_text
    for r in runs[1:]:
        r.text = ""


def apply_substitutions(slide, subs, tag: str = "") -> tuple:
    """段落级精确匹配替换。subs是[(旧段落文本, 新段落文本), ...]列表，
    段落全部run拼接后的文本必须跟旧文本完全相等（避免子串误命中）。
    旧文本必须是从当前这份template.pptx里实际读出来的原文——不能凭SLIDE*_SUBS
    这类历史表格里的字符串假设照搬，那些表是针对"上一周已patch过的deck"写的，
    段落切分方式可能跟pristine模板不一致（已在页1验证时踩过这个坑，
    见 PPT生成_旧流水线映射与新架构设计_v0.1.md）。
    返回 (命中数, 未命中的旧文本集合)。"""
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
    return hits, misses


def clone_column_right(slide, src_col_left, tol=30000, x_offset=390000):
    """把left≈src_col_left的全部shape克隆一份，整体右移x_offset。
    用于月度明细网格这类"每月一列独立文本框"的展开（不是真正的<a:tbl>表格，
    没法用python-pptx的表格API加列）。返回[(原shape, 新XML元素), ...]。"""
    from copy import deepcopy

    spTree = slide.shapes._spTree
    src_shapes = []
    for shp in slide.shapes:
        if shp.left is None:
            continue
        if abs(shp.left - src_col_left) <= tol:
            src_shapes.append(shp)
    created = []
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    for src in src_shapes:
        new_xml = deepcopy(src._element)
        for off in new_xml.iter(f"{{{ns_a}}}off"):
            try:
                x = int(off.get("x"))
                off.set("x", str(x + x_offset))
            except (TypeError, ValueError):
                pass
        spTree.append(new_xml)
        created.append((src, new_xml))
    return created


def set_shape_text_xml(sp_element, new_text):
    """直接改写一个克隆出来的<p:sp> XML元素里的文本（clone_column_right产出的
    是原始lxml元素，不是python-pptx Shape对象，不能用shape.text_frame）。"""
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    t_elems = list(sp_element.iter(f"{{{ns_a}}}t"))
    if not t_elems:
        return False
    t_elems[0].text = new_text
    for extra in t_elems[1:]:
        extra.text = ""
    return True


def set_table_row_count(table, target_data_rows: int, header_rows: int = 1, protect_tail_rows: int = 1,
                         template_row_idx: int = 1):
    """把table的数据行数量调整为target_data_rows（不含表头header_rows行、不含
    末尾受保护行protect_tail_rows，例如"合计"行）。多则删，少则克隆
    template_row_idx这一行（默认第1个数据行，结构/样式跟其余数据行一致）补足，
    新行插在受保护尾行之前。用于第8/9/10/11页这类"KA数量随数据变化"的真实
    <a:tbl>表格（跟S1月度网格那种手搭文本框列不同，这里是真表格，用lxml
    直接操作<a:tr>而不是python-pptx的高层API——python-pptx本身不提供插入行
    的公开方法）。返回调整后的数据行python-pptx Row对象list（不含表头/受保护尾行）。"""
    from copy import deepcopy
    from pptx.oxml.ns import qn

    tbl = table._tbl
    trs = tbl.findall(qn("a:tr"))
    n_data_now = len(trs) - header_rows - protect_tail_rows
    if n_data_now < 0:
        raise ValueError("table has fewer rows than header_rows+protect_tail_rows")
    src_tr = trs[header_rows + template_row_idx] if template_row_idx < n_data_now else trs[header_rows]

    if target_data_rows > n_data_now:
        insert_before = trs[header_rows + n_data_now]  # 第一个受保护尾行（或表末尾）
        for _ in range(target_data_rows - n_data_now):
            new_tr = deepcopy(src_tr)
            insert_before.addprevious(new_tr)
    elif target_data_rows < n_data_now:
        start_idx = header_rows + target_data_rows
        remove_count = n_data_now - target_data_rows
        for tr in trs[start_idx:start_idx + remove_count]:
            tbl.remove(tr)

    return list(table.rows)[header_rows:header_rows + target_data_rows]


def find_shapes_below(slide, label_shape, max_count: int = 2, x_tol: int = 300000):
    """返回label_shape正下方、同一列最近的最多max_count个文本框。"""
    if label_shape.top is None:
        return []
    below = []
    for sh in slide.shapes:
        if sh is label_shape or not sh.has_text_frame:
            continue
        if sh.top is None or sh.left is None:
            continue
        if sh.top <= label_shape.top:
            continue
        if abs(sh.left - label_shape.left) > x_tol:
            continue
        below.append((sh.top, sh))
    below.sort(key=lambda x: x[0])
    return [sh for _, sh in below[:max_count]]
