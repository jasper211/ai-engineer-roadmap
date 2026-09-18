# -*- coding: utf-8 -*-
"""Update So What narratives + stale labels in 周业绩汇报PPT_FINAL.pptx
Grounded in S1-S4 CSVs (data through 2026-06 / W25). Pace基准 = 547M/7 = 78.1M (图内节奏线).
Run: python update_sowhat_0626.py            (validate width budget only)
     python update_sowhat_0626.py --apply    (apply + save)
"""
import sys, shutil, unicodedata
from pptx import Presentation

SRC = "周业绩汇报PPT_FINAL.pptx"

def width_units(s):
    """approx rendered width: CJK/full-width=1.0, others=0.5"""
    u = 0.0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            u += 1.0
        else:
            u += 0.5
    return u

# edits keyed by (slide_index_0based, shape_id) -> new full text
EDITS = {
    # ---- SLIDE 1 ----
    (0, 44): "2026 全业务批核 566.1M、达成率 50.9%，缺口 547M。6 月预约 78.8M/签单 69.9M 维持高位，批核回落至 55.9M 为年内低点，放款节奏待提速。",
    (0, 136): "2 月批核峰值 143.7M 为全年最高，此后逐月回落至 6 月 55.9M；预约/签单上半年维持 70–86M 高位，前端动能仍在。剩余目标 547M，需后续月均 78.1M 方可达成年度 1113M。",
    # ---- SLIDE 2 ----
    (1, 62): "6 月预约 78.8M（环比 -4.1%）、签单 69.9M（-18.9%）、批核 55.9M（-23.3%）三项同步回落；件均 APE 维持 36–39 万，量缩价稳，需重点关注后端批核连续走弱趋势。",
    (1, 96): "截至 W25，已批核 566.1M（达成率 50.9%），距全年目标 1113M 还差 547M，需月均 78.1M、最低月底线 69.5M。当前批核节奏放缓，达标压力集中下半年。",
    # ---- SLIDE 4 ----
    (3, 30): "永明经代 6 月预约 31.7M/签单 28.9M 居各线首位，前端最强；BK 批核由 2 月峰 93.9M 落至 6 月 5.9M，存量见底。各线节奏分化，需差异管理。",
    # ---- SLIDE 6 ----
    (5, 245): "TOP10 KA 累计批核 465.1M，占全业务 82.2%，高度集中。民生银行 185.7M/167 件居首，是最核心单一客户，亦是最大集中风险点。",
    # ---- SLIDE 9 ---- (combined: keep 'So What：' prefix)
    (8, 95): "So What：  6 月同行预约 5626 万、签单 5262 万双双刷新年内新高（预约环比 +12.4%），批核 3270 万落后于前端，签单积压待批，需紧盯下半年放款节奏。",
    # ---- stale non-SoWhat labels ----
    (1, 76): "1–6 月已批核",
    (2, 15): "目标976M  |  缺口498M",
}

def main():
    apply = "--apply" in sys.argv
    prs = Presentation(SRC)
    # build id->shape index per slide
    ok = True
    pending = []
    for (si, sid), newtext in EDITS.items():
        slide = prs.slides[si]
        shape = next((sh for sh in slide.shapes if sh.shape_id == sid), None)
        if shape is None:
            print("!! MISSING slide%d id%d" % (si+1, sid)); ok = False; continue
        old = shape.text_frame.text.strip()
        wo, wn = width_units(old), width_units(newtext)
        flag = "OK " if wn <= wo + 0.01 else "OVER"
        if wn > wo + 0.01: ok = False
        print("S%d id%-3d %s  old_w=%.1f new_w=%.1f (Δ%.1f)" % (si+1, sid, flag, wo, wn, wn-wo))
        print("      OLD: %s" % old)
        print("      NEW: %s" % newtext)
        pending.append((shape, newtext))
    if not apply:
        print("\n[validate only] %s. Re-run with --apply to write." % ("ALL FIT" if ok else "SOME OVER -- trim first"))
        return
    if not ok:
        print("\nABORT: some texts exceed width budget; trim before applying.")
        return
    shutil.copyfile(SRC, SRC.replace(".pptx", "_bak_pre_sowhat.pptx"))
    for shape, newtext in pending:
        runs = shape.text_frame.paragraphs[0].runs
        runs[0].text = newtext
        for extra in runs[1:]:
            extra.text = ""
    prs.save(SRC)
    print("\nSAVED %s (backup: %s)" % (SRC, SRC.replace('.pptx', '_bak_pre_sowhat.pptx')))

if __name__ == "__main__":
    main()
