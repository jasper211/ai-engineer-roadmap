#!/usr/bin/env python3
"""
run_full_deck.py — 一键生成完整 PPT（含第12页银行仪表盘 + 第13/14页代理人/KA）

输入（与原脚本同目录）:
  周业绩汇报PPT_FINAL_5_22.pptx   或 template.pptx
  业绩分析报表_0605.xlsx           （用于 build_slide12_13）
  业绩分析报表_0605.xlsx           （用于 build_s9_slides，可与上同一份）

输出（单一文件）:
  /mnt/user-data/outputs/周业绩汇报PPT_FINAL.pptx

用法:
  python run_full_deck.py
  python run_full_deck.py <template.pptx> <excel_s2.xlsx> <excel_s9.xlsx>
"""

import sys, shutil
from pathlib import Path

HERE = Path(__file__).parent

# ── 参数 ──────────────────────────────────────────────────────────────
# 找 Stage 1 输出的 FINAL pptx，或 template.pptx
def _find_pptx(base_dir):
    for name in ["周业绩汇报PPT_FINAL.pptx", "template.pptx"]:
        p = base_dir / name
        if p.exists(): return p
    # fallback: any pptx
    candidates = sorted(base_dir.glob("*.pptx"), reverse=True)
    return candidates[0] if candidates else None

TEMPLATE  = Path(sys.argv[1]) if len(sys.argv) > 1 else _find_pptx(HERE)

# 自动找同目录下最新的 业绩分析报表_*.xlsx
def _find_latest_excel(base_dir):
    candidates = sorted(base_dir.glob("业绩分析报表_*.xlsx"), reverse=True)
    return candidates[0] if candidates else None

EXCEL_S2  = Path(sys.argv[2]) if len(sys.argv) > 2 else _find_latest_excel(HERE)
EXCEL_S9  = Path(sys.argv[3]) if len(sys.argv) > 3 else EXCEL_S2

INTER_OUT = HERE / "_tmp_with_slide12.pptx"   # 中间临时文件
FINAL_OUT = HERE / "周业绩汇报PPT_FINAL.pptx"

# ── 检查 ──────────────────────────────────────────────────────────────
missing = [name for name, p in [
    ("模板PPT",  TEMPLATE),
    ("S2 Excel", EXCEL_S2),
    ("S9 Excel", EXCEL_S9),
] if not p or not p.exists()]

if missing:
    print(f"❌ 找不到以下文件：{', '.join(missing)}")
    sys.exit(1)

print("=" * 60)
print("▶ 输入文件")
print(f"  模板 PPT : {TEMPLATE}")
print(f"  S2 Excel : {EXCEL_S2}")
print(f"  S9 Excel : {EXCEL_S9}")
print("=" * 60)

# ── 防呆：检查输入 PPT 是否已经处理过 ────────────────────────────────
from pptx import Presentation as _ChkPrs
_chk = _ChkPrs(TEMPLATE)
_n = len(_chk.slides)
_titles = [shp.text_frame.text.strip()
           for s in _chk.slides for shp in s.shapes
           if shp.has_text_frame]
if any("代理人业务分析仪表盘" in t for t in _titles):
    print("❌ 输入 PPT 已包含代理人业务页，说明它是上次 run_full_deck.py 的输出。")
    print("   请先重新运行 run_full_pipeline.py，再运行本脚本。")
    sys.exit(1)
if _n > 11:
    print(f"⚠  输入 PPT 有 {_n} 页（预期 ≤11 页）。请确认使用的是 run_full_pipeline.py 的输出。")
del _chk, _n, _titles

# ── Stage 1: 生成第12页（银行仪表盘）─────────────────────────────────
print("\n▶ Stage 1 — build_slide12_13.py（生成第12页）")
import build_slide12_13 as s12

s12.PPTX_IN  = TEMPLATE
s12.EXCEL_IN = EXCEL_S2
s12.PPTX_OUT = INTER_OUT

s12.main()
print(f"  ✓ 中间文件: {INTER_OUT}")

# ── Stage 2: 追加 S9 页（代理人 + KA）───────────────────────────────
print("\n▶ Stage 2 — build_s9_slides.py（追加代理人/KA页）")
import build_s9_slides as s9

s9.PPTX_IN  = INTER_OUT
s9.EXCEL_IN = EXCEL_S9
s9.PPTX_OUT = FINAL_OUT

s9.main()

# ── 清理中间文件 ──────────────────────────────────────────────────────
INTER_OUT.unlink(missing_ok=True)

# ── 删除第10、11页（原始 Bank View 备份页）────────────────────────────
print("\n▶ 删除第10、11页（原始 Bank View 备份）")
from pptx import Presentation as _Prs
from pptx.oxml.ns import qn as _qn
_prs = _Prs(FINAL_OUT)
print(f"  删除前：{len(_prs.slides)} 页")
# 按标题找并删除原始 Bank View 两页（不用硬编码索引）
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
sldIdLst = _prs.element.find(_qn("p:sldIdLst"))
slide_ids = list(sldIdLst.findall(_qn("p:sldId")))
to_delete_rids = []

# 找"银行业绩分析仪表盘"页及其下一页（周度详情页）
for idx, (elem, slide) in enumerate(zip(slide_ids, _prs.slides)):
    texts = [shp.text_frame.text for shp in slide.shapes if shp.has_text_frame]
    if any("银行业绩分析仪表盘" in t for t in texts):
        # 这一页
        to_delete_rids.append(elem.get(f"{{{NS_REL}}}id"))
        # 下一页（周度详情）
        if idx + 1 < len(slide_ids):
            to_delete_rids.append(slide_ids[idx + 1].get(f"{{{NS_REL}}}id"))
        break

for rid in to_delete_rids:
    for elem in list(sldIdLst.findall(_qn("p:sldId"))):
        if elem.get(f"{{{NS_REL}}}id") == rid:
            _prs.part.drop_rel(rid)
            sldIdLst.remove(elem)
            break
print(f"  删除后：{len(_prs.slides)} 页")
_prs.save(FINAL_OUT)

print()
print("=" * 60)
print(f"✅ 完成！最终文件：{FINAL_OUT}")
print(f"   共 {len(_prs.slides)} 页")
print("=" * 60)
