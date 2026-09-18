# -*- coding: utf-8 -*-
"""Round 2: refresh the remaining 18 So What boxes (kept in round 1).
Grounded in S1-S4 CSVs (data through 2026-06 / W25). Pace = 547M/7 = 78.1M.
Run: python update_sowhat_0626_r2.py            (validate)
     python update_sowhat_0626_r2.py --apply    (apply + save)
"""
import sys, shutil, unicodedata
from pptx import Presentation

SRC = "周业绩汇报PPT_FINAL.pptx"

def width_units(s):
    u = 0.0
    for ch in s:
        u += 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.5
    return u

EDITS = {
    (0, 80): "批核 566.1M 占 79.7% 为主力;未批核 100.0M+待签 16.3M=116.4M 在途待转化(占批核21%),另流失 27.4M/73件需止损。推进在途+控流失可拉升达成。",
    (0, 85): "经代批核 471.6M 独占 83.3% 为唯一主力,且握最大在途未批核 90.5M;代理人 69.9M、KA 24.5M 体量小。资源应优先压注经代催核转化,同时定向扩量代理人与 KA。",
    (2, 33): "永明累计批核 478.2M、达成率 49.0%,缺口 498M。TOP10 产品签单 93.7M/103 件高度集中,卓金保险计划II 以 14.6M/21 件领跑(件均69.6万)。大单储蓄险为基本盘,需保障头部产品持续供给。",
    (3, 87): "BK 达成率 112.9% 唯一超额达标,同行经代 71.1% 次之。永明经代目标最大(340M)却仅 38.8%、天领 32.7%,落后象限为最大战略风险;IFA/合伙/成事均<10% 待激活。",
    (3, 132): "已批 566.1M+在途 116.4M=682.5M,距目标 1113M 仍差 431M。BK 批核最大 225.8M,永明经代/同行经代次之;缺口主压永明经代与天领,靠放量+在途填补。",
    (4, 91): "永明经代未批核占比最高(22%/37.6M),同行经代次之(21%/31.4M),催核优先;BK 已批 91% 最干净。按未批规模排序推进。",
    (4, 132): "管道 682.5M:已批 566.1M(82.9%)、未批 100.0M(14.7%)、待签 16.3M(2.4%)。在途 116.4M 转化可推高达成约 10pct。",
    (4, 141): "BK 批核 225.8M/目标 200M=112.9% 超额。永明经代目标最大(340M)仅批 132.0M、缺口 208M 最大;天领 63/193M、同行经代 114/160M 亦缺口显著,是冲刺重点。",
    (5, 33): "全流程:预约 392.4M→签单 376.9M→递交 372.3M→批核 563.0M。批核高于预约因含跨周积压释放;预约→签单留存约 96% 高效,前端获客是天花板,需扩预约入口。",
    (5, 41): "周度脉冲明显:批核 W08 峰 67.0M 为存量集中放款,签单 W21 峰 33.9M、预约 W25 峰 29.4M,W07 普遍低谷。四阶段节奏错位,需平滑执行。",
    (5, 83): "W25 预约 29.4M/76件(+75.7%)强反弹,签单 23.6M、批核 16.0M。在途未批核 100.0M/250件为后续批核核心储量。",
    (6, 253): "整体平均 31.3 天、P90 80.8 天,SLA 达标率 87.8%。BK 件均 118万但平均 72.9 天/P90 146 天、达标率仅 46.6%,唯一超 SLA,大额件审核慢;天领 19.7 天最优。>90天积压 83 件占 22.3% APE,需专项提速。",
    (6, 8): "预约累计 392.4M/986件,永明经代领跑 126.8M/356件(32%),同行经代 103.9M 次之。W25 单周 29.4M 创年内峰值,前端回升。",
    (6, 9): "签单累计 376.9M/952件,永明经代领跑 121.5M/341件(32%),同行经代 101.1M 次之。W21 单周 33.9M 创年内峰值,签单稳健。",
    (6, 10): "批核累计 563.0M/1021件,BK 领跑 222.6M/190件(40%),永明经代 132.0M 次之。W08 峰 67.0M 为年内最高,近周批核回落。",
    (7, 11): "So What：  姜通批核 96.0M/262件、战略合作 36.2M/105件,合计占同行批核 73.7%。姜通件均≈37万为大单驱动,战略合作走量为流量驱动。头部高度集中,需差异化对接与风险分散。",
    (7, 20): "So What：  Mark 批核 13.3M、未批核 0,批核率 100% 件质量最高;姜通在途未批核最大 39.6M、批核率约 71%,高瑶 5.3M 待跟。头部推荐人质量分化,需对姜通件质量专项排查并催核提速。",
    (8, 64): "So What：  W25 同行预约 16.93M、签单 18.12M 均高于批核 12.41M,前端蓄力足、签单领先批核,管道渐厚;需紧盯后续批核能否跟上放量。",
}

def main():
    apply = "--apply" in sys.argv
    prs = Presentation(SRC)
    ok = True; pending = []
    for (si, sid), newtext in EDITS.items():
        shape = next((sh for sh in prs.slides[si].shapes if sh.shape_id == sid), None)
        if shape is None:
            print("!! MISSING slide%d id%d" % (si+1, sid)); ok = False; continue
        old = shape.text_frame.text.strip()
        wo, wn = width_units(old), width_units(newtext)
        over = wn > wo + 0.01
        if over: ok = False
        print("S%d id%-3d %s old_w=%.1f new_w=%.1f (Δ%.1f)" % (si+1, sid, "OVER" if over else "OK ", wo, wn, wn-wo))
        if over: print("      NEW: %s" % newtext)
        pending.append((shape, newtext))
    if not apply:
        print("\n[validate] %s" % ("ALL FIT -> run --apply" if ok else "SOME OVER -- trim")); return
    if not ok:
        print("\nABORT: over budget"); return
    shutil.copyfile(SRC, SRC.replace(".pptx", "_bak_pre_r2.pptx"))
    for shape, newtext in pending:
        runs = shape.text_frame.paragraphs[0].runs
        runs[0].text = newtext
        for extra in runs[1:]:
            extra.text = ""
    prs.save(SRC)
    print("\nSAVED %s (backup _bak_pre_r2)" % SRC)

if __name__ == "__main__":
    main()
