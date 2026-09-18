# -*- coding: utf-8 -*-
"""Update all 25 So What + 2 stale labels on the W27 working copy (0710 期).
Grounded in S1-S4 CSVs (data 2026-06 complete / W27; July partial). Pace=516M/6=86.0M (图内节奏线).
环比洞察 vs 上期(0703/W26): 达成率51.7->53.6%(+1.9pct); 同行经代74->79%; 姜通批核率68->75%; 待签5.6->18.0M; 永明经代未批22->12%.
Run: <py> update_sowhat_0710.py            (validate)
     <py> update_sowhat_0710.py --apply    (apply + save)
"""
import sys, io, shutil, unicodedata
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pptx import Presentation

SRC = "周业绩汇报PPT_W27_20260710.pptx"

def width_units(s):
    return sum(1.0 if unicodedata.east_asian_width(c) in ("W", "F") else 0.5 for c in s)

EDITS = {
    # ---- SLIDE 1 ----
    (0, 44): "2026 全业务批核 596.7M、达成率 53.6%（较上期 +1.9pct），缺口 516M。6 月预约 84.4M/签单 85.7M 高位，批核 62.2M，7 月已批 24.3M。",
    (0, 80): "批核 596.7M 占 80.4% 为主力;未批核 97.8M+待签 18.0M=115.8M 在途待转化(待签环比 5.6→18.0M 跳升),另流失 29.7M/84件需止损。",
    (0, 85): "经代批核 500.3M 独占 83.8% 为唯一主力,且握最大在途未批核 83.8M;代理人 71.8M、KA 24.6M 体量小。资源应优先压注经代催核转化,同时定向扩量代理人与 KA。",
    (0, 136): "2 月批核峰值 143.7M 为全年最高，此后回落至 6 月 62.2M；预约/签单上半年维持 80–86M 高位，前端动能仍在。剩余目标 516M，需后续月均 86.0M 方可达成年度 1113M。",
    # ---- SLIDE 2 ----
    (1, 62): "6 月预约 84.4M（环比 +3.0%）、签单 85.7M（-0.5%）前端走强，批核 62.2M（-14.6%）回落；累计达成率升至 53.6%（较上期 +1.9pct），后端放款仍是瓶颈。",
    (1, 96): "截至 W27，已批核 596.7M（达成率 53.6%），距全年目标 1113M 还差 516M，需月均 86.0M、最低月底线 69.5M。批核节奏放缓，达标压力集中下半年。",
    # ---- SLIDE 3 ----
    (2, 33): "永明累计批核 504.3M、达成率 51.7%（较上期 +1.9pct）,缺口 472M。TOP10 产品签单 130.2M/160 件,卓金保险计划II 以 27.6M/46 件领跑(件均59.9万)。大单储蓄险为基本盘,需保头部供给。",
    # ---- SLIDE 4 ----
    (3, 87): "BK 113.8% 唯一超额,同行经代 79.0%（较上期 +5pct）势头最强;永明经代 43.0%、天领 33.1% 目标大仍落后为战略风险;IFA/合伙/成事≤11% 待激活。",
    (3, 132): "已批 596.7M+在途 115.8M=712.5M,距目标 1113M 仍差 400M。BK 批核最大 227.6M,永明经代/同行经代次之;缺口主压永明经代与天领,靠放量+在途填补。",
    (3, 30): "同行经代 6 月预约 38.6M/签单 36.4M 跃居各线首位(超永明经代)；BK 批核由 2 月峰 93.9M 落至 6 月 6.2M。各线节奏分化，需差异管理。",
    # ---- SLIDE 5 ----
    (4, 91): "同行经代未批占比最高(22%/37.8M)催核优先;永明经代未批降至12%(20.9M)催核见效;合伙转介52%但仅4.6M。按未批规模推进。",
    (4, 132): "管道 712.5M:已批 596.7M(83.8%)、未批 97.8M(13.7%)、待签 18.0M(2.5%)。在途 115.8M 转化可推高达成约 10pct。",
    (4, 141): "BK 批核 227.6M/目标 200M=113.8% 超额。永明经代目标最大(340M)批 146.3M、缺口 194M 最大;天领 63.9/193M、同行经代 126.3/160M 亦缺口显著,是冲刺重点。",
    # ---- SLIDE 6 ----
    (5, 33): "全流程:预约 424.8M→签单 407.8M→递交 410.2M→批核 593.6M。批核高于预约因含跨周积压释放;预约→签单留存约 96% 高效,前端获客是天花板,需扩预约入口。",
    (5, 41): "周度脉冲明显:批核 W08 峰 67.0M 为存量集中放款,签单 W21 峰 33.8M、预约 W05 峰 28.2M,W07 普遍低谷。四阶段节奏错位,需平滑执行。",
    (5, 83): "W27 预约 23.2M/54件回升、签单 10.0M/30件、批核 16.0M/43件。在途未批 97.8M/233件为批核核心储量。",
    (5, 245): "TOP10 KA 累计批核 468.0M，占全业务 78.4%，高度集中。民生银行 187.5M/172 件居首，是最核心单一客户，亦是最大集中风险点。",
    # ---- SLIDE 7 ----
    (6, 253): "整体平均 30.3 天、P90 74.7 天,SLA 达标率 88.7%。BK 件均 116万但平均 71.8 天/P90 145 天、达标率仅 47.4%,唯一超 SLA,大额件审核慢;天领 19.7 天最优。>90天积压 83 件占 21.2% APE,需专项提速。",
    (6, 8): "预约累计 424.8M/1070件,同行经代领跑 129.1M/367件(占30%),永明经代 122.2M 次之。W05 单周 28.2M 为年内峰值,近周回升。",
    (6, 9): "签单累计 407.8M/1038件,同行经代领跑 122.4M/352件(占30%),永明经代 119.4M 次之。W21 单周 33.8M 为年内峰值,签单稳健。",
    (6, 10): "批核累计 593.6M/1121件,BK 领跑 227.6M/196件(38%),永明经代 146.3M 次之。W08 峰 67.0M 为年内最高,近周批核回落。",
    # ---- SLIDE 8 (combined, keep prefix) ----
    (7, 11): "So What：  姜通批核 113.5M/307件、战略合作 39.2M/116件,合计占同行批核 74.7%。姜通件均≈37万为大单驱动,战略合作走量为流量驱动。头部高度集中,需差异化对接与风险分散。",
    (7, 20): "So What：  Mark 批核 13.3M/批核率 100% 件质量最高;姜通在途未批核 37.8M、批核率升至 75%（较上期 68%）质量改善;白博文 5.4M 待跟。头部推荐人质量分化,持续催核提速。",
    # ---- SLIDE 9 (combined, keep prefix) ----
    (8, 64): "So What：  W27 同行批核 13.59M、预约 11.37M 均高于签单 7.25M,批核放量、签单短期走弱;管道厚,需盯后续签单与批核延续性。",
    (8, 95): "So What：  6 月同行预约 6152 万、签单 6025 万创年内新高（预约环比 +26.4%），批核 3822 万落后于前端，签单积压待批,需紧盯下半年放款节奏。",
    # ---- stale non-SoWhat labels ----
    (1, 76): "1–6 月已批核",
    (2, 15): "目标976M  |  缺口472M",
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
    for shape, newtext in pending:
        runs = shape.text_frame.paragraphs[0].runs
        runs[0].text = newtext
        for extra in runs[1:]:
            extra.text = ""
    prs.save(SRC)
    print("\nSAVED %s" % SRC)

if __name__ == "__main__":
    main()
