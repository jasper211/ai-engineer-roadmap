"""
heatmatrix_cloner.py — duplicate heat-matrix columns by cloning XML shapes.

The QRS heat matrices on slide 7 are built from discrete text boxes + rectangles.
Each column has ~15 shapes sharing an x-coordinate. To add a W14 / W15 / …
column, we deep-clone every shape of the anchor (W13) column at an X offset.

Shapes are identified by XML `<p:nvSpPr>/<p:cNvPr name="...">` prefixes:
    T6xxx / R6xxx   →   S 批核矩阵
    T7xxx / R7xxx   →   Q 预约矩阵
    T8xxx / R8xxx   →   R 签单矩阵

After cloning, we edit cell text via set_shape_text_at(new_x, cell_y, text).
"""
from copy import deepcopy
from lxml import etree

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _emu_add_x(sp_elem, dx):
    """Shift the x position of a p:sp or similar element by dx EMU."""
    off = sp_elem.find(f".//{{{NS_A}}}xfrm/{{{NS_A}}}off")
    if off is not None:
        cur = int(off.get("x", "0"))
        off.set("x", str(cur + dx))


def _clone_column(slide, anchor_left, column_gap, name_prefixes,
                  left_range=(0, 999_999_999),
                  top_range=(0, 999_999_999)):
    """
    Find all shapes at anchor_left (within ±5000 tol) whose name starts with
    any of name_prefixes AND whose center y is within top_range AND whose
    left is within left_range. Clone them at new_left = anchor_left + column_gap.
    Returns list of (new_shape_element, original_top).
    """
    spTree = slide.shapes._spTree  # internal, but stable
    new_shapes = []

    # Collect existing shapes at anchor position
    targets = []
    for shp in slide.shapes:
        if shp.left is None or shp.top is None:
            continue
        if not (left_range[0] <= shp.left <= left_range[1]):
            continue
        if not (top_range[0] <= shp.top <= top_range[1]):
            continue
        if abs(shp.left - anchor_left) > 10000:
            continue
        if not any(shp.name.startswith(p) for p in name_prefixes):
            continue
        targets.append(shp)

    for shp in targets:
        # Deep-clone the underlying XML element
        new_el = deepcopy(shp._element)
        # Shift x
        _emu_add_x(new_el, column_gap)
        # Give it a new name to avoid collisions (append _W14)
        cNvPr = new_el.find(f".//{{{NS_P}}}cNvPr")
        if cNvPr is not None:
            cNvPr.set("name", cNvPr.get("name", "cloned") + "_W14")
            # strip id attribute — PowerPoint will regenerate
            cNvPr.set("id", "0")
        # Append to spTree
        spTree.append(new_el)
        new_shapes.append((new_el, shp.top))
    return new_shapes


def add_w14_column_to_matrix(slide, matrix_name_prefixes, w13_header_left,
                              header_top, matrix_top_range):
    """
    Duplicate the W13 column of one matrix to create a W14 column.
    Returns the new_left (x coordinate of the W14 column).
    """
    column_gap = 390000
    new_left = w13_header_left + column_gap
    _clone_column(
        slide,
        anchor_left=w13_header_left,
        column_gap=column_gap,
        name_prefixes=matrix_name_prefixes,
        top_range=matrix_top_range,
    )
    return new_left


def remove_cloned_columns(slide, name_prefixes, suffix="_W14"):
    """Remove any previously-cloned columns (idempotent cleanup).
    Removes shapes whose cNvPr name ends with `suffix`."""
    spTree = slide.shapes._spTree
    to_remove = []
    for sp in spTree.findall(f".//{{{NS_P}}}sp"):
        cNvPr = sp.find(f".//{{{NS_P}}}cNvPr")
        if cNvPr is not None:
            name = cNvPr.get("name", "")
            if name.endswith(suffix) and any(
                name.startswith(p) for p in name_prefixes
            ):
                to_remove.append(sp)
    for sp in to_remove:
        sp.getparent().remove(sp)
    return len(to_remove)
