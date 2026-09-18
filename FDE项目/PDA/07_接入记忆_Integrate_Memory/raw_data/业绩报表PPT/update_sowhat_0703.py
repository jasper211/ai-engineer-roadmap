# -*- coding: utf-8 -*-
"""Update all 25 So What + 2 stale labels in 周业绩汇报PPT_FINAL.pptx (0703 期).
Grounded in S1-S4 CSVs (data through 2026-06 complete / W26; July partial).
Pace = 剩余538M / 6mo = 89.6M/月 (与图内节奏线一致). 最低月底线 69.5M.
Run: <py> update_sowhat_0703.py            (validate width budget)
     <py> update_sowhat_0703.py --apply    (apply + save, backup first)
"""
import sys, io, shutil, unicodedata
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pptx import Presentation

SRC = "周业绩汇报PPT_FINAL.pptx"

def width_units(s):
    u = 0.0
    for ch in s:
        u += 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.5
    return u

def firstrun(sh):
    for para in sh.text_frame.paragraphs:
        if para.runs:
            return para.runs[0]
    return None

EDITS = {
    # ---- SLIDE 1 ----
    (0, 44): "2026 全业务批核 575.1M、达成率 51.7%，缺口 538M。6 月预约 84.6M/签单 85.9M 创近月新高，批核 62.0M 环比降 14.8%，前端旺、放款节奏待提速。",
    (0, 80): "批核 575.1M 占 79.9% 为主力;未批核 110.3M+待签 5.6M=115.9M 在途待转化(占批核20%),另流失 28.6M/79件需止损。推进在途+控流失可拉升达成。",
    (0, 85): "经代批核 479.8M 独占 83.4% 为唯一主力,且握最大在途未批核 95.7M;代理人 70.7M、KA 24.6M 体量小。资源应优先压注经代催核转化,同时定向扩量代理人与 KA。",
    (0, 136): "2 月批核峰值 143.7M 为全年最高，此后回落至 6 月 62.0M；预约/签单上半年维持 80–86M 高位，前端动能仍在。剩余目标 538M，需后续月均 89.6M 方可达成年度 1113M。",
    # ---- SLIDE 2 ----
    (1, 62): "6 月预约 84.6M（环比 +3.3%）、签单 85.9M（-0.2%）前端走强，批核 62.0M（-14.8%）回落；件均 APE 约 36 万,前端旺但后端批核走弱,需关注放款转化。",
    (1, 96): "截至 W26，已批核 575.1M（达成率 51.7%），距全年目标 1113M 还差 538M，需月均 89.6M、最低月底线 69.5M。批核节奏放缓，达标压力集中下半年。",
    # ---- SLIDE 3 ----
    (2, 33): "永明累计批核 485.7M、达成率 49.8%,缺口 490M。TOP10 产品签单 93.5M/111 件高度集中,卓金保险计划II 以 14.6M/21 件领跑(件均69.6万)。大单储蓄险为基本盘,需保障头部产品持续供给。",
    # ---- SLIDE 4 ----
    (3, 87): "BK 达成率 113.0% 唯一超额达标,同行经代 74.0% 次之。永明经代目标最大(340M)却仅 39.8%、天领 33.0%,落后象限为最大战略风险;IFA/合伙/成事均≤10% 待激活。",
    (3, 132): "已批 575.1M+在途 115.9M=691.1M,距目标 1113M 仍差 422M。BK 批核最大 226.1M,永明经代/同行经代次之;缺口主压永明经代与天领,靠放量+在途填补。",
    (3, 30): "永明经代 6 月预约 33.7M/签单 33.4M 居各线首位，前端最强；BK 批核由 2 月峰 93.9M 落至 6 月 6.2M，存量见底。各线节奏分化，需差异管理。",
    # ---- SLIDE 5 ----
    (4, 91): "永明经代/同行经代未批占比高(22%/22%),绝对额最大(40.0M/33.7M),催核优先;合伙转介占比51%但仅4.4M。按未批规模推进。",
    (4, 132): "管道 691.1M:已批 575.1M(83.2%)、未批 110.3M(16.0%)、待签 5.6M(0.8%)。在途 115.9M 转化可推高达成约 10pct。",
    (4, 141): "BK 批核 226.1M/目标 200M=113.0% 超额。永明经代目标最大(340M)仅批 135.4M、缺口 205M 最大;天领 63.6/193M、同行经代 118.4/160M 亦缺口显著,是冲刺重点。",
    # ---- SLIDE 6 ----
    (5, 33): "全流程:预约 401.0M→签单 396.4M→递交 396.4M→批核 572.0M。批核高于预约因含跨周积压释放;预约→签单留存约 99% 高效,前端获客是天花板,需扩预约入口。",
    (5, 41): "周度脉冲明显:批核 W08 峰 67.0M 为存量集中放款,签单 W21 峰 33.8M、预约 W05 峰 28.2M,W07 普遍低谷。四阶段节奏错位,需平滑执行。",
    (5, 83): "W26 预约 12.5M/44件、签单 17.0M/50件、批核 5.7M/24件较 W25 回落。在途未批 110.3M/267件为批核核心储量。",
    (5, 245): "TOP10 KA 累计批核 472.7M，占全业务 82.2%，高度集中。民生银行 186.0M/169 件居首，是最核心单一客户，亦是最大集中风险点。",
    # ---- SLIDE 7 ----
    (6, 253): "整体平均 30.9 天、P90 77.1 天,SLA 达标率 88.2%。BK 件均 117万但平均 72.3 天/P90 146 天、达标率仅 47.2%,唯一超 SLA,大额件审核慢;天领 19.8 天最优。>90天积压 83 件占 22.0% APE,需专项提速。",
    (6, 8): "预约累计 401.0M/1022件,永明经代领跑 130.8M/375件(占33%),同行经代 108.6M 次之。W05 单周 28.2M 为年内峰值,近周回落。",
    (6, 9): "签单累计 396.4M/1008件,永明经代领跑 127.5M/364件(占32%),同行经代 107.9M 次之。W21 单周 33.8M 为年内峰值,签单稳健。",
    (6, 10): "批核累计 572.0M/1059件,BK 领跑 222.9M/192件(39%),永明经代 135.4M 次之。W08 峰 67.0M 为年内最高,近周批核回落。",
    # ---- SLIDE 8 (combined, keep prefix) ----
    (7, 11): "So What：  姜通批核 100.2M/278件、战略合作 37.1M/108件,合计占同行批核 73.8%。姜通件均≈36万为大单驱动,战略合作走量为流量驱动。头部高度集中,需差异化对接与风险分散。",
    (7, 20): "So What：  Mark 批核 13.3M、未批核 0,批核率 100% 件质量最高;姜通在途未批核最大 46.3M、批核率约 68%,白博文 5.6M 待跟。头部推荐人质量分化,需对姜通件质量专项排查并催核提速。",
    # ---- SLIDE 9 (combined, keep prefix) ----
    (8, 64): "So What：  W26 同行预约 10.93M、签单 10.60M 均高于批核 4.61M,前端与签单领先、批核偏低,管道渐厚;需紧盯后续周次批核能否跟上。",
    (8, 95): "So What：  6 月同行预约 6243 万、签单 6115 万双双刷新年内新高（预约环比 +27.1%），批核 3812 万落后于前端，签单积压待批,需紧盯下半年放款节奏。",
    # ---- stale non-SoWhat labels ----
    (1, 76): "1–6 月已批核",
    (2, 15): "目标976M  |  缺口490M",
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
    shutil.copyfile(SRC, SRC.replace(".pptx", "_bak_pre_0703.pptx"))
    for shape, newtext in pending:
        runs = shape.text_frame.paragraphs[0].runs
        runs[0].text = newtext
        for extra in runs[1:]:
            extra.text = ""
    prs.save(SRC)
    print("\nSAVED %s (backup _bak_pre_0703)" % SRC)

if __name__ == "__main__":
    main()
