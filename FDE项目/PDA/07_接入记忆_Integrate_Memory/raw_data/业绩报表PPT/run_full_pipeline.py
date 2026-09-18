#!/usr/bin/env python3
"""
run_full_pipeline.py — one-click 0404 → 0411 weekly deck updater.

Input files (must be in same dir):
  - 周业绩汇报PPT_20260404_更新.pptx  (or any template renamed to template.pptx)
  - S1-总览仪表盘.csv
  - S2-业务端视角.csv
  - S3-执行管理端.csv
  - S4-产品端视角.csv

Output:
  - 周业绩汇报PPT_FINAL.pptx

Pipeline stages:
  1. update_ppt.py        — charts, KPI text, slide-7 W14 column clone
  2. apply_w14_patches.py — KA tables, U/V charts, bank dashboard, W table, etc.
  3. final_gap_patch.py   — slide-3 license table, slide-3 TOP10 product table,
                            slide-7 Q/R/S heat matrix rebuild, T-table dedupe
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

TEMPLATE_SRC = HERE / "周业绩汇报PPT_20260404_更新.pptx"
if not TEMPLATE_SRC.exists():
    TEMPLATE_SRC = HERE / "template.pptx"

STAGE1_OUT = HERE / "周业绩汇报PPT_AUTO_UPDATED.pptx"
STAGE2_OUT = HERE / "周业绩汇报PPT_AUTO_UPDATED_updated.pptx"
STAGE3_OUT = HERE / "周业绩汇报PPT_FINAL.pptx"


def run(label, argv):
    print(f"\n{'='*70}\n▶ {label}\n{'='*70}")
    r = subprocess.run(argv, cwd=HERE)
    if r.returncode != 0:
        print(f"❌ {label} failed with rc={r.returncode}")
        sys.exit(r.returncode)


def main():
    if not TEMPLATE_SRC.exists():
        print(f"❌ Template not found: {TEMPLATE_SRC}")
        sys.exit(1)

    # update_ppt.py hard-codes SRC_PPT='template.pptx' — stage it
    if TEMPLATE_SRC.name != 'template.pptx':
        shutil.copy(TEMPLATE_SRC, HERE / 'template.pptx')

    run("Stage 1 — update_ppt.py",      [sys.executable, "update_ppt.py"])
    run("Stage 2 — apply_w14_patches.py",[sys.executable, "apply_w14_patches.py"])
    run("Stage 3 — final_gap_patch.py",  [sys.executable, "final_gap_patch.py"])

    # Clean up intermediate stage outputs — keep only the final deck
    cleaned = []
    for f in (STAGE1_OUT, STAGE2_OUT):
        if f.exists():
            try:
                f.unlink()
                cleaned.append(f.name)
            except OSError as e:
                print(f"⚠️  Could not remove {f.name}: {e}")

    print(f"\n{'='*70}")
    print(f"✅ Pipeline complete")
    print(f"   Final deck: {STAGE3_OUT.name}")
    if cleaned:
        print(f"   Cleaned up: {', '.join(cleaned)}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
