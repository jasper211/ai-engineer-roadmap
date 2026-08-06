#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主装配：组合所有页面输出最终 HTML。"""
import sys, re
from pathlib import Path
SCRIPT = Path(__file__).resolve().parent
REPORT = SCRIPT.parent / "report"
sys.path.insert(0, str(REPORT))

from report_lib import CSS, BASE, nsec
from pages_p1_p2 import (cover, toc, p03_layers, p04_dims, p05_workflow,
                         p06_antipattern, p07_lenses, p08_evidence)
from pages_p3_p4 import (p09_time, p10_breakpoint, p11_measure, p12_source,
                         p13_total, p14_structure, p15_yoy,
                         p16_ind_total, p17_ind_measure, p18_ind_quantity_price, p19_ind_trend)
from pages_p4b import (p20_group_new, p21_group_inforce, p22_group_note,
                       p23_ret_total, p24_ret_fund, p25_ret_contrib)
from pages_p5 import (p26_rank_single, p27_rank_ape, p28_rank_inforce,
                      p29_increment, p30_transfer, p31_outlier)
from pages_p6_p7 import (p32_conclusion_who, p33_lens_roots, p34_dod, p35_conclusion,
                         p36_formula, p37_evidence_index, p38_sources, p39_disclaimer)

NAV = """
<nav>
<a href='#sec01'>封面</a><a href='#sec02'>目录</a>
<a>▌一 方法</a><a href='#sec03'>L0-L5</a><a href='#sec04'>十维度</a><a href='#sec05'>七步</a><a href='#sec06'>反模式</a><a href='#sec07'>三镜</a><a href='#sec08'>证据</a>
<a>▌二 口径</a><a href='#sec09'>时间</a><a href='#sec10'>断点</a><a href='#sec11'>口径</a><a href='#sec12'>来源</a>
<a>▌三 总览</a><a href='#sec13'>规模</a><a href='#sec14'>结构</a><a href='#sec15'>同比</a>
<a>▌四 个人</a><a href='#sec16'>总量</a><a href='#sec17'>双口径</a><a href='#sec18'>量价</a><a href='#sec19'>趋势</a>
<a>四 团体</a><a href='#sec20'>新造</a><a href='#sec21'>有效</a><a href='#sec22'>注释</a>
<a>四 退休</a><a href='#sec23'>数量</a><a href='#sec24'>基金</a><a href='#sec25'>供款</a>
<a>▌五 公司</a><a href='#sec26'>整付</a><a href='#sec27'>年度化</a><a href='#sec28'>保单</a><a href='#sec29'>增量</a><a href='#sec30'>转移</a><a href='#sec31'>异常</a>
<a>▌六 综合</a><a href='#sec32'>谁增</a><a href='#sec33'>三镜</a><a href='#sec34'>DoD</a><a href='#sec35'>结论</a>
<a>▌附录</a><a href='#sec36'>公式</a><a href='#sec37'>证据</a><a href='#sec38'>来源</a><a href='#sec39'>免责</a>
<b class='pg'>39 屏</b></nav>
"""

def build():
    sections = [
        cover(), toc(),
        p03_layers(), p04_dims(), p05_workflow(), p06_antipattern(), p07_lenses(), p08_evidence(),
        p09_time(), p10_breakpoint(), p11_measure(), p12_source(),
        p13_total(), p14_structure(), p15_yoy(),
        p16_ind_total(), p17_ind_measure(), p18_ind_quantity_price(), p19_ind_trend(),
        p20_group_new(), p21_group_inforce(), p22_group_note(),
        p23_ret_total(), p24_ret_fund(), p25_ret_contrib(),
        p26_rank_single(), p27_rank_ape(), p28_rank_inforce(), p29_increment(), p30_transfer(), p31_outlier(),
        p32_conclusion_who(), p33_lens_roots(), p34_dod(), p35_conclusion(),
        p36_formula(), p37_evidence_index(), p38_sources(), p39_disclaimer(),
    ]
    body = "".join(sections)
    # 后处理：按出现顺序为各 H1 徽章顺序编号（对齐 secNN 序号）
    badge = {"n": 0}
    def _renum(m):
        badge["n"] += 1
        return f"<span class='no' data-h1>{badge['n']:02d}</span>"
    body = re.sub(r"<span class='no' data-h1>#</span>", _renum, body)
    html = ("<!DOCTYPE html><html lang='zh-HK'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>香港长期保险行业全行业分析 2023Q1–2026Q1</title>"
            f"<style>{CSS}</style></head><body>"
            f"{NAV}" + body + "</body></html>")
    out = REPORT / "香港长期保险行业2023-2026Q1全行业分析.html"
    out.write_text(html, encoding="utf-8")
    print(f"完成：共 {badge['n']} 屏（39 页内容），写入\n  {out}\n  （{len(html)/1024:.0f} KB）")

if __name__ == "__main__":
    build()
