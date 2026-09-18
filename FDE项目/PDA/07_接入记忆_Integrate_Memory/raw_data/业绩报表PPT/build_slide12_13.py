"""
build_slide12_13.py
────────────────────────────────────────────────────────────────────────
修改 PPT：
  • 将第10、11页完整复制为第12、13页（保留原页）
  • 第12页改版为综合 BK 仪表盘：
      ─ 顶部：保留 6 个月度 KPI 卡片（来自原第10页）
      ─ 左侧中部：3 个周度 KPI 卡片 + AB 周度趋势图（来自第13页左上第一部分）
      ─ 左侧下部：AC KA 明细表（来自第13页左侧第三个图）
      ─ 右侧：2 个新图（各分行生效年保费 + 每月生效年保费），
               数据来源 S2_业务端视角 S 表与 T 表

用法:
  python build_slide12_13.py <input.pptx> <s2_excel.xlsx> [output.pptx]
"""

import copy
import sys
import io
from pathlib import Path

import openpyxl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.font_manager as _fm

# ── CJK 字体配置 ─────────────────────────────────────────────────────
# ── CJK 字体配置（Windows / Linux 自动适配）────────────────────────
import os as _os
_CJK_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑（Win10/11）
    "C:/Windows/Fonts/simhei.ttf",      # 黑体
    "C:/Windows/Fonts/simsun.ttc",      # 宋体
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux
    "/System/Library/Fonts/PingFang.ttc",  # macOS
]
_CJK_FONT_PATH = next((p for p in _CJK_CANDIDATES if _os.path.exists(p)), None)
try:
    if _CJK_FONT_PATH:
        _fm.fontManager.addfont(_CJK_FONT_PATH)
        _cjk_prop = _fm.FontProperties(fname=_CJK_FONT_PATH)
        _CJK_FONT_NAME = _cjk_prop.get_name()
        plt.rcParams["font.sans-serif"] = [_CJK_FONT_NAME, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
except Exception:
    pass
import numpy as np
from lxml import etree
from pptx import Presentation
from pptx.util import Emu, Pt

# ── 参数 ─────────────────────────────────────────────────────────────
PPTX_IN  = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/mnt/user-data/uploads/周业绩汇报PPT_FINAL_5_22.pptx")
EXCEL_IN = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/mnt/user-data/uploads/业绩分析报表_0522.xlsx")
PPTX_OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/mnt/user-data/outputs/周业绩汇报PPT_WITH_SLIDE12.pptx")

# Relationship namespace
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

# ── 幻灯片坐标常量（EMU）─────────────────────────────────────────────
SLIDE_W = 12192000
SLIDE_H = 6858000

# 第10页上：月度 KPI 卡片区底部（Text 8 等 t≈1068070 + h≈149225 + margin）
KPI_CARDS_BOTTOM = 1310000   # 约 1.43 英寸

# 第11页左侧：周度 KPI 卡片 t 起始
WEEKLY_KPI_SRC_TOP = 588645  # Shape 19 原始 top

# 目标：周度 KPI 卡片在第12页的起始 top
WEEKLY_KPI_DST_TOP = 1400000

# 偏移量 = 目标 - 原始
TOP_OFFSET = WEEKLY_KPI_DST_TOP - WEEKLY_KPI_SRC_TOP  # 811355

# 左半部分 / 右半部分分界（EMU）
LEFT_HALF_LIMIT = 6080000

# ── 新布局：每月（右侧中间，紧接顶部卡片）+ 各分行（全宽底部）──────
# 每月生效年保费：右侧，从第一行右3卡片下方开始，高度更大
MONTHLY_L =  6200000
MONTHLY_T =  1400000   # 紧接在周度 KPI 卡片右侧空间下方
MONTHLY_W =  5900000
MONTHLY_H =  3500000   # 更高

# 各分行生效年保费：全宽底部
BRANCH_L  =   100000
BRANCH_T  =  5050000   # 靠近底部
BRANCH_W  = 12000000
BRANCH_H  =  1680000

# 不复制到第12页左侧的形状（AB 趋势图整体、So What、标题等）
SKIP_NAMES_LEFT = {
    # AB 周度趋势图（不要此图）
    "Shape 36",    # AB 区块标题背景
    "Text 37",     # AB 区块标题文字
    "Chart 1",     # AB 周度趋势折线图
    "s3010",       # AB 图背景矩形
    "文本框 51",   # 重复轴标签
    # So What 文字
    "sw_bg_4007", "sw_4007",
    "Shape 42", "Text 43",
    # 顶部元素已在第10页有
    "Shape 0", "Text 1", "Text 2",
}

# ── AC 表格区域重新定位参数 ──────────────────────────────────────────
WEEKLY_KPI_DST_BOTTOM = WEEKLY_KPI_DST_TOP + 762000   # 2162000 EMU
AC_SRC_TOP   = 4627245   # Shape 40 在 slide11 的原始 top
AC_DST_TOP   = 2320000   # AC 表格：紧接周度 KPI 卡片下方左侧
AC_OFFSET    = AC_DST_TOP - AC_SRC_TOP                  # ≈ 392755
AC_SECTION_T_THRESHOLD = 4200000  # t 超过此值 → AC 区域

# ── 读取 Excel 数据 ──────────────────────────────────────────────────
def load_branch_data(excel_path):
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb["S2_业务端视角"]
    rows = list(ws.iter_rows(values_only=True))

    # 找 S-APE 与 T-件数 块的起始行（0-indexed）
    s_start = t_start = None
    for i, row in enumerate(rows):
        v = str(row[0]) if row[0] else ""
        if "S-APE" in v and s_start is None:
            s_start = i
        if "T-件数" in v and t_start is None:
            t_start = i

    # ── S-APE 表头 ──
    s_hdr = rows[s_start + 2]  # ['合作伙伴(分行)', '2026-01', ..., '合计', ...]
    mo_idx = [i for i, h in enumerate(s_hdr) if h and str(h).startswith("2026-")]
    tot_idx = next(i for i, h in enumerate(s_hdr) if h == "合计")

    # 月份标签（只取非零的月份列名）
    month_labels = [str(s_hdr[i]) for i in mo_idx]

    # 分支数据（排除 合计 行、空行）
    branches = []
    for row in rows[s_start + 3: t_start - 1]:
        name = str(row[0]).strip() if row[0] else ""
        if not name or name == "合计":
            continue
        monthly = [float(row[j] or 0) for j in mo_idx]
        total   = float(row[tot_idx] or 0)
        if total > 0:
            branches.append({"name": name, "monthly": monthly, "total": total})

    branches.sort(key=lambda x: x["total"], reverse=True)

    # ── T-件数 表 ──
    t_hdr = rows[t_start + 2]
    t_mo_idx  = [i for i, h in enumerate(t_hdr) if h and str(h).startswith("2026-")]
    t_tot_idx = next(i for i, h in enumerate(t_hdr) if h == "合计")

    cnt_map = {}
    for row in rows[t_start + 3:]:
        name = str(row[0]).strip() if row[0] else ""
        if not name or name == "合计":
            break
        monthly = [int(row[j] or 0) for j in t_mo_idx]
        total   = int(row[t_tot_idx] or 0)
        cnt_map[name] = {"monthly": monthly, "total": total}

    # 合计行（最后一行）
    s_total_row = rows[t_start - 2]  # 合计行在 T 块之前
    # 从 S-APE 块直接获取各月合计
    for row in rows[s_start + 3: t_start - 1]:
        name = str(row[0]).strip() if row[0] else ""
        if name == "合计":
            monthly_ape_total = [float(row[j] or 0) for j in mo_idx]
            break
    else:
        monthly_ape_total = [sum(b["monthly"][i] for b in branches) for i in range(len(mo_idx))]

    for row in rows[t_start + 3:]:
        name = str(row[0]).strip() if row[0] else ""
        if name == "合计":
            monthly_cnt_total = [int(row[j] or 0) for j in t_mo_idx]
            break
    else:
        monthly_cnt_total = [
            sum(cnt_map[b["name"]]["monthly"][i] for b in branches if b["name"] in cnt_map)
            for i in range(len(t_mo_idx))
        ]

    return branches, cnt_map, month_labels, monthly_ape_total, monthly_cnt_total


# ── 图表样式常量（浅色主题，与 PPT 原有图表背景一致）──────────────────
BG_DARK    = "#FFFFFF"   # 图表外框：白色
BG_PANEL   = "#EEF3FA"   # 绘图区：极浅蓝灰
BAR_CLR    = "#2B5BA8"   # 柱状：与 PPT 配色一致的深蓝
LINE_CLR   = "#F5A623"   # 折线：橙色
DOT_CLR    = "#F5A623"
TEXT_W     = "#1A2744"   # 文字：深色（浅背景下可读）
AXIS_MINOR = "#555555"   # 轴标签：深灰
GRID_CLR   = "#D9E5F5"   # 网格：淡蓝灰


def _shorten(name, maxlen=6):
    """缩短分行名称以适应 X 轴标签。"""
    replacements = [
        ("分行", ""), ("团队", ""), ("香港", "港"), ("分行许菁", "(许)"),
        ("分行徐艳", "(徐)"), ("分行钟丽丽", "(钟)"), ("分行朱慧娟", "(朱)"),
        ("分行高凯", "(高凯)"), ("分行高原", "(高原)"), ("分行王慧娟", "(王)"),
        ("上海张江支行", "上海张江"),
    ]
    s = name
    for old, new in replacements:
        s = s.replace(old, new)
    if len(s) > maxlen:
        s = s[:maxlen]
    return s


def make_branch_chart(branches, cnt_map, dpi=150, figsize=(12.8, 2.75)):
    """各分行生效年保费：柱状 APE + 折线 件数。"""
    names    = [_shorten(b["name"]) for b in branches]
    ape_vals = [b["total"] / 10000 for b in branches]          # 万
    cnt_vals = [cnt_map.get(b["name"], {}).get("total", 0) for b in branches]

    n = len(names)
    x = np.arange(n)

    fig, ax1 = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor(BG_DARK)
    ax1.set_facecolor(BG_PANEL)

    bars = ax1.bar(x, ape_vals, color=BAR_CLR, width=0.55, zorder=2)
    # 数据标签（只对 top-10 显示，避免拥挤）
    for i, (bar, val) in enumerate(zip(bars, ape_vals)):
        if val > 0:
            ax1.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(ape_vals) * 0.015,
                f"{int(round(val))}",
                ha="center", va="bottom", color=TEXT_W,
                fontsize=7, fontweight="bold"
            )

    ax1.set_ylabel("APE（万港元）", color=TEXT_W, fontsize=8)
    ax1.tick_params(axis="y", labelcolor=AXIS_MINOR, labelsize=7)
    ax1.tick_params(axis="x", labelcolor=TEXT_W, labelsize=7.5, rotation=35)
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, ha="right")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax1.spines[:].set_visible(False)
    ax1.grid(axis="y", color=GRID_CLR, linewidth=0.5, zorder=0)
    ax1.set_xlim(-0.6, n - 0.4)
    ax1.set_ylim(0, max(ape_vals) * 1.22)

    ax2 = ax1.twinx()
    ax2.set_facecolor("none")
    ax2.plot(x, cnt_vals, color=LINE_CLR, marker="o", markersize=4.5,
             linewidth=1.5, zorder=3, linestyle="--")
    for xi, cv in zip(x, cnt_vals):
        if cv > 0:
            ax2.text(xi, cv + max(cnt_vals) * 0.06, str(cv),
                     ha="center", va="bottom", color=LINE_CLR, fontsize=6)
    ax2.set_ylabel("件数", color=LINE_CLR, fontsize=7)
    ax2.tick_params(axis="y", labelcolor=LINE_CLR, labelsize=6)
    ax2.spines[:].set_visible(False)
    ax2.set_ylim(0, max(cnt_vals) * 1.35 if cnt_vals else 1)

    # 图例
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    legend_elems = [
        Patch(facecolor=BAR_CLR, label="APE"),
        Line2D([0], [0], color=LINE_CLR, marker="o", markersize=4, linestyle="--", label="件数"),
    ]
    ax1.legend(handles=legend_elems, loc="upper right", framealpha=0.2,
               labelcolor=TEXT_W, fontsize=6, facecolor=BG_DARK)

    # 标题区域（用 suptitle 模拟顶部 label）
    fig.suptitle("各分行生效年保费   单位：万港元", color=TEXT_W, fontsize=8,
                 x=0.02, ha="left", y=0.98, fontweight="bold")

    plt.tight_layout(rect=[0, 0, 1, 0.93])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG_DARK, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def make_monthly_chart(month_labels, monthly_ape, monthly_cnt, dpi=150, figsize=(6.1, 2.85)):
    """每月生效年保费：柱状 APE + 折线 件数 + 环比标注。"""
    # 只取 1-5 月（排除 2026-06 等为零的月份）
    active = [(lbl, a, c) for lbl, a, c in zip(month_labels, monthly_ape, monthly_cnt)
              if a > 0 or c > 0]
    if not active:
        active = list(zip(month_labels[:5], monthly_ape[:5], monthly_cnt[:5]))

    labels_zh = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
    mo_names = []
    ape_vals = []
    cnt_vals = []
    for lbl, a, c in active:
        try:
            mo = int(lbl.split("-")[1])
            mo_names.append(labels_zh[mo - 1])
        except Exception:
            mo_names.append(lbl)
        ape_vals.append(a / 10000)  # 万
        cnt_vals.append(c)

    n = len(mo_names)
    x = np.arange(n)

    fig, ax1 = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor(BG_DARK)
    ax1.set_facecolor(BG_PANEL)

    bars = ax1.bar(x, ape_vals, color=BAR_CLR, width=0.45, zorder=2)
    max_ape = max(ape_vals) if ape_vals else 1
    for bar, val in zip(bars, ape_vals):
        if val > 0:
            ax1.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max_ape * 0.02,
                f"{int(round(val))}",
                ha="center", va="bottom", color=TEXT_W, fontsize=7, fontweight="bold"
            )

    ax1.set_ylabel("APE（万港元）", color=TEXT_W, fontsize=7)
    ax1.tick_params(axis="y", labelcolor=AXIS_MINOR, labelsize=6)
    ax1.tick_params(axis="x", labelcolor=TEXT_W, labelsize=8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(mo_names)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax1.spines[:].set_visible(False)
    ax1.grid(axis="y", color=GRID_CLR, linewidth=0.5, zorder=0)
    ax1.set_xlim(-0.6, n - 0.4)
    ax1.set_ylim(0, max_ape * 1.3)

    ax2 = ax1.twinx()
    ax2.set_facecolor("none")
    ax2.plot(x, cnt_vals, color=LINE_CLR, marker="o", markersize=5,
             linewidth=1.8, zorder=3, linestyle="--")

    # 环比标注（从第2个月开始）
    max_cnt = max(cnt_vals) if cnt_vals else 1
    for i in range(1, n):
        prev = ape_vals[i - 1]
        curr = ape_vals[i]
        if prev > 0:
            pct = (curr - prev) / prev * 100
            color = "#E74C3C" if pct < 0 else "#2ECC71"
            label = f"{pct:+.0f}%"
            ax2.text(i, cnt_vals[i] + max_cnt * 0.12, label,
                     ha="center", va="bottom", color=color, fontsize=6.5, fontweight="bold")

    for xi, cv in zip(x, cnt_vals):
        ax2.text(xi, cv - max_cnt * 0.12, str(cv),
                 ha="center", va="top", color=LINE_CLR, fontsize=6)

    ax2.set_ylabel("件数", color=LINE_CLR, fontsize=7)
    ax2.tick_params(axis="y", labelcolor=LINE_CLR, labelsize=6)
    ax2.spines[:].set_visible(False)
    ax2.set_ylim(0, max_cnt * 1.55 if max_cnt else 1)

    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    legend_elems = [
        Patch(facecolor=BAR_CLR, label="生效APE"),
        Line2D([0], [0], color=LINE_CLR, marker="o", markersize=4, linestyle="--", label="件数"),
    ]
    ax1.legend(handles=legend_elems, loc="upper right", framealpha=0.2,
               labelcolor=TEXT_W, fontsize=6, facecolor=BG_DARK)

    fig.suptitle("每月生效年保费   单位：万港元", color=TEXT_W, fontsize=8,
                 x=0.02, ha="left", y=0.98, fontweight="bold")

    plt.tight_layout(rect=[0, 0, 1, 0.93])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG_DARK, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ── 幻灯片复制辅助函数 ───────────────────────────────────────────────
def duplicate_slide(prs, slide_idx):
    """将 slide[slide_idx] 完整复制并追加到 prs 末尾，返回新幻灯片。"""
    src = prs.slides[slide_idx]
    layout = src.slide_layout
    new_slide = prs.slides.add_slide(layout)

    # 清空由 layout 自动插入的占位符
    sp_tree = new_slide.shapes._spTree
    for child in list(sp_tree):
        tag = child.tag.split("}")[-1]
        if tag not in ("nvGrpSpPr", "grpSpPr"):
            sp_tree.remove(child)

    # 逐一复制源形状
    src_tree = src.shapes._spTree
    for elem in src_tree:
        tag = elem.tag.split("}")[-1]
        if tag in ("nvGrpSpPr", "grpSpPr"):
            continue
        new_elem = copy.deepcopy(elem)
        _remap_relationships(new_elem, src, new_slide)
        sp_tree.append(new_elem)

    return new_slide


def _remap_relationships(elem, src_slide, tgt_slide):
    """将 elem 中所有 r:id 引用从 src_slide.part 映射到 tgt_slide.part。"""
    src_rels = src_slide.part.rels  # dict[rId, Relationship]
    for sub in elem.iter():
        r_id = sub.get(f"{{{NS_R}}}id")
        if r_id and r_id in src_rels:
            rel = src_rels[r_id]
            try:
                new_rid = tgt_slide.part.relate_to(rel.target_part, rel.reltype)
                sub.set(f"{{{NS_R}}}id", new_rid)
            except Exception:
                pass


def _set_top(elem, new_top):
    """将 XML 元素中的 xfrm/off y 属性设为 new_top。"""
    for xfrm in elem.findall(f".//{{{NS_A}}}xfrm") + elem.findall(f".//{{{NS_P}}}xfrm"):
        off = xfrm.find(f"{{{NS_A}}}off")
        if off is not None:
            off.set("y", str(new_top))
            return True
    return False


def _shift_top(elem, delta):
    """将 XML 元素中的 xfrm/off y 属性增加 delta。"""
    for xfrm in elem.findall(f".//{{{NS_A}}}xfrm") + elem.findall(f".//{{{NS_P}}}xfrm"):
        off = xfrm.find(f"{{{NS_A}}}off")
        if off is not None:
            cur = int(off.get("y", "0"))
            off.set("y", str(cur + delta))
            return True
    return False


def _get_top(shp):
    return shp.top or 0


def _get_left(shp):
    return shp.left or 0


# ── 主流程 ───────────────────────────────────────────────────────────
def main():
    prs = Presentation(PPTX_IN)

    # ── 防呆：按标题找银行仪表盘页，而非硬编码索引 ──────────────────
    def _find_slide(keyword):
        for i, s in enumerate(prs.slides):
            for shp in s.shapes:
                if shp.has_text_frame and keyword in shp.text_frame.text:
                    return i, s
        return None, None

    idx10, slide10 = _find_slide("银行业绩分析仪表盘")
    # 第11页是 Bank View 的周度详情页（紧接在银行仪表盘后面）
    if idx10 is not None and idx10 + 1 < len(prs.slides):
        slide11 = prs.slides[idx10 + 1]
    else:
        slide11 = None

    if slide10 is None:
        print("❌ 找不到'银行业绩分析仪表盘'页，请确认输入的是 run_full_pipeline.py 的输出")
        import sys; sys.exit(1)
    print(f"  找到银行仪表盘：第 {idx10+1} 页")

    # ── 1. 复制第10、11页为第12、13页 ──────────────────────────────
    print("复制第10页 → 第12页 ...")
    slide12 = duplicate_slide(prs, 9)   # copy of slide 10
    print("复制第11页 → 第13页 ...")
    slide13 = duplicate_slide(prs, 10)  # copy of slide 11

    # ── 2. 整理第12页：删除月度图表区，仅保留顶部卡片 ───────────────
    print("整理第12页 ...")
    sp_tree12 = slide12.shapes._spTree
    to_remove = []
    for shp in list(slide12.shapes):
        t = _get_top(shp)
        # 保留：t < KPI_CARDS_BOTTOM（包括 KPI 卡片、标题栏、内部文件标注）
        if t < KPI_CARDS_BOTTOM:
            continue
        to_remove.append(shp._element)

    for elem in to_remove:
        try:
            sp_tree12.remove(elem)
        except Exception:
            pass
    print(f"  已删除 {len(to_remove)} 个形状")

    # ── 3. 从第11页左侧复制形状到第12页（带偏移）────────────────────
    print("从第11页复制左侧内容到第12页 ...")
    copied = 0

    for shp in slide11.shapes:
        l = _get_left(shp)
        t = _get_top(shp)
        name = shp.name

        # 只处理左半部分形状
        if l > LEFT_HALF_LIMIT:
            continue
        # 跳过指定名称形状（AB 图、So What、顶部重复元素等）
        if name in SKIP_NAMES_LEFT:
            continue
        # 跳过 So What 文字（含 sw_ 前缀或 "So What" 文本）
        if name.startswith("sw_") or "So What" in (shp.text_frame.text if shp.has_text_frame else ""):
            continue
        # 跳过 Shape 78（底部分割线）
        if name == "Shape 78":
            continue

        new_elem = copy.deepcopy(shp._element)
        _remap_relationships(new_elem, slide11, slide12)

        # 根据原始 top 决定使用哪个偏移量
        # AC 区域（表格及其标题）使用单独计算的偏移，紧接在周度 KPI 下方
        if t > AC_SECTION_T_THRESHOLD:
            _shift_top(new_elem, AC_OFFSET)
        else:
            _shift_top(new_elem, TOP_OFFSET)

        sp_tree12.append(new_elem)
        copied += 1

    print(f"  已从第11页复制 {copied} 个形状到第12页左侧")

    # ── 4. 生成新图并插入第12页右侧 ──────────────────────────────────
    print("读取 Excel 数据 ...")
    branches, cnt_map, month_labels, monthly_ape, monthly_cnt = load_branch_data(EXCEL_IN)
    print(f"  共 {len(branches)} 个有效分行，{len(month_labels)} 个月份列")

    print("生成各分行生效年保费图 ...")
    chart1_buf = make_branch_chart(branches, cnt_map)

    print("生成每月生效年保费图 ...")
    chart2_buf = make_monthly_chart(month_labels, monthly_ape, monthly_cnt)

    # 插入图片到第12页
    from pptx.util import Emu as E
    # 每月生效年保费 → 右侧中间（顶部6卡片右侧下方，更高）
    slide12.shapes.add_picture(
        chart2_buf,
        left=E(MONTHLY_L), top=E(MONTHLY_T),
        width=E(MONTHLY_W), height=E(MONTHLY_H)
    )
    # 各分行生效年保费 → 全宽底部
    slide12.shapes.add_picture(
        chart1_buf,
        left=E(BRANCH_L), top=E(BRANCH_T),
        width=E(BRANCH_W), height=E(BRANCH_H)
    )
    print("  两张新图已插入第12页（每月右侧中间 + 各分行全宽底部）")

    # ── 5. 保存 ─────────────────────────────────────────────────────
    PPTX_OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(PPTX_OUT)
    print(f"\n✅ 已保存至 {PPTX_OUT}")
    print(f"   共 {len(prs.slides)} 页（原 11 页 + 新增第12、13页）")


if __name__ == "__main__":
    main()
