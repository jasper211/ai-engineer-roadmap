# -*- coding: utf-8 -*-
"""Update all 25 So What + 2 stale labels on the W28 working copy (0717 期, 数据已修复口径一致版).
用户已修复口径: S1/S2/G/漏斗 批核总数一致(605.2M/1157, 同行经代批核回补至129.3M)。
每框以 deck 图表实显数字为准(recon)。环比洞察(口径已一致, 可放心做):
  全业务达成率53.6->54.4%(+0.8pct); 永明51.7->52.4%(+0.7pct); 同行经代达成率79.0->80.8%(+1.8pct); 永明经代43.0->44.5%.
Pace=508M/6=84.6M(图内节奏线). 最新月6月完整+7月partial, 最新周W28.
Run: <py> update_sowhat_0717.py            (validate)
     <py> update_sowhat_0717.py --apply    (apply + save)
"""
import sys, io, unicodedata
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pptx import Presentation

SRC = "周业绩汇报PPT_W28_20260717.pptx"

def width_units(s):
    return sum(1.0 if unicodedata.east_asian_width(c) in ("W", "F") else 0.5 for c in s)

EDITS = {
    # ---- SLIDE 1 ----
    (0, 44): "2026 全业务批核 605.2M、达成率 54.4%（较上期 +0.8pct），缺口 508M。6 月预约 84.4M/签单 85.7M 高位，批核 62.1M，7 月已批 32.9M 提速。",
    (0, 80): "未批核 107.3M（235 件）+ 待签 16.0M（42 件）=123.4M 在途待转化(占批核约 20%)。管道快速推进至生效可直接拉升达成率约 11pct。",
    (0, 85): "经代批核 508.1M 独占 84.0% 为唯一主力,且握最大在途未批核 87.5M;代理人 72.2M、KA 24.9M 体量小。资源应优先压注经代催核转化,同时定向扩量代理人与 KA。",
    (0, 136): "2 月批核峰值 143.7M 为全年最高，此后回落至 6 月 62.1M；预约/签单上半年维持 80–86M 高位。剩余目标 508M，需后续月均 84.6M 方可达成年度 1113M。",
    # ---- SLIDE 2 ----
    (1, 62): "6 月预约 84.4M（环比 +3.0%）、签单 85.7M（-0.5%）前端走强，批核 62.1M（-14.8%）回落；累计达成率升至 54.4%（较上期 +0.8pct），后端放款仍是瓶颈。",
    (1, 96): "截至 W28，已批核 605.2M（达成率 54.4%），距全年目标 1113M 还差 508M，需月均 84.6M。批核节奏放缓，达标压力集中下半年。",
    # ---- SLIDE 3 ----
    (2, 33): "永明累计批核 511.6M、达成率 52.4%（较上期 +0.7pct）,缺口 464M。TOP10 产品签单 130.8M/163 件,卓金保险计划II 以 27.2M/45 件领跑(件均60.4万)。大单储蓄险为基本盘,需保头部供给。",
    # ---- SLIDE 4 ----
    (3, 87): "BK 113.8% 唯一超额;同行经代 80.8%（较上期 +1.8pct）势头最强、永明经代 44.5% 回升;天领 33.4%(批核64.5M)仍为最大战略风险;IFA/合伙/成事≤11%。",
    (3, 132): "已批 605.2M+在途 123.4M=728.5M,距目标 1113M 仍差 384M。BK 批核最大 227.6M,永明经代/同行经代次之;缺口主压永明经代与天领,靠放量+在途填补。",
    (3, 30): "同行经代 6 月预约 37.1M/签单 34.9M 跃居各线首位；BK 批核由 2 月峰 93.9M 落至 6 月 6.2M。各线节奏分化，需差异管理。",
    # ---- SLIDE 5 ----
    (4, 91): "同行经代未批绝对额最大(39.7M/22%)催核优先;BK 28.6M、天领 14.5M 次之;合伙转介占比50%但仅4.4M。按未批规模推进。",
    (4, 132): "管道 728.5M:已批 605.2M(83.1%)、未批 107.3M(14.7%)、待签 16.0M(2.2%)。在途 123.4M 转化可推高达成约 11pct。",
    (4, 141): "BK 批核 227.6M/目标 200M=113.8% 超额。永明经代目标最大(340M)批 151.2M、缺口 189M 最大;天领 64.5/193M、同行经代 129.3/160M 亦缺口显著,是冲刺重点。",
    # ---- SLIDE 6 ----
    (5, 33): "全流程:预约 440.9M→签单 425.8M→递交 424.6M→批核 602.0M。批核高于预约含跨周积压释放;预约→签单留存约 97% 高效,前端获客是天花板,需扩预约入口。",
    (5, 41): "周度脉冲明显:批核 W08 峰 67.0M 为存量集中放款,签单 W21 峰 32.8M、预约 W05 峰 28.2M,W07 普遍低谷。四阶段节奏错位,需平滑执行。",
    (5, 83): "W28 预约 20.3M/51件、签单 21.0M/43件、批核 6.9M/29件。在途未批 107.3M/235件为后续批核核心储量。",
    (5, 245): "TOP10 KA 累计批核 473.2M，占全业务 78.2%，高度集中。民生银行 187.5M/172 件居首，是最核心单一客户，亦是最大集中风险点。",
    # ---- SLIDE 7 ----
    (6, 253): "整体平均 30.2 天、P90 72.0 天,SLA 达标率 88.9%。BK 件均 116万但平均 71.8 天/P90 145 天、达标率仅 47.4%,唯一超 SLA,大额件审核慢;天领 19.7 天最优。>90天积压 84 件占 20.9% APE,需专项提速。",
    (6, 8): "预约累计 440.9M/1114件,同行经代领跑 139.9M/398件(占32%),永明经代次之。W05 单周 28.2M 为年内峰值。",
    (6, 9): "签单累计 425.8M/1077件,同行经代领跑 127.2M/367件(占30%),永明经代次之。W21 单周 32.8M 为年内峰值。",
    (6, 10): "批核累计 602.0M/1156件,BK 领跑 224.5M/195件(37%),永明经代次之。W08 峰 67.0M 为年内最高。",
    # ---- SLIDE 8 (combined) ----
    (7, 11): "So What：  姜通批核 118.7M/328件、战略合作 39.4M/119件,合计占同行批核 74.5%。姜通件均≈36万为大单驱动,战略合作走量为流量驱动。头部高度集中,需差异化对接与风险分散。",
    (7, 20): "So What：  Mark 批核 13.3M/批核率 100% 件质量最高;姜通在途未批核 37.3M、批核率 76% 稳中向好;白博文未批 6.9M 待跟。头部推荐人质量分化,持续催核提速。",
    # ---- SLIDE 9 (combined) ----
    (8, 64): "So What：  W28 同行预约 16.73M 高于签单 10.55M、批核 6.17M,前端回补、批核清淡;需盯后续周次签单与批核能否跟上。",
    (8, 95): "So What：  6 月同行预约 6009 万、签单 5881 万高位（环比 +25%），批核 3822 万落后于前端，签单积压待批,需紧盯下半年放款节奏。",
    # ---- stale non-SoWhat labels ----
    (1, 76): "1–6 月已批核",
    (2, 15): "目标976M  |  缺口464M",
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
