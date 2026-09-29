#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multiview_dashboard.py — S1-S9多视角业绩分析前端，替代PPT生成路线。

背景：Jasper 09-29指示"PPT那条路意义不大，直接从底表数据生成前端展示，代替PPT"——
起因是拿到业务真实在发的12页W37/W38周报后，发现①真实模板已经从11页演化到12页
（新增代理人业务/KA业务两页，BK业务合并成1页），我们对着旧11页模板做的PPT复刻
已经过时；②第6页"全流程转化漏斗"的"递交"阶段在W38报告里从563.2M/1434件直接
归零，是当前生产脚本（非本Agent产出）的真实bug，佐证了"重新从可信的底表+已验证
的S1-S9逻辑走一遍"比"死磕复刻一个还在变、还有bug的PPT模板"更有价值。

架构：单文件HTML，多视角tab切换（同一页面内切换S1总览/S2业务端/S3执行管理端/
S4产品端/同行业绩/银行业绩/代理人业务/KA业务），复用dashboard_generator.py已经
验证过的设计语言（CSS变量/kpi-row/card/grid2-3-4/chip-row/rank-card等class）和
Chart.js内联方案（不依赖外部CDN，避免dashboard_generator.py v0.1.1踩过的CDN 404坑）。
图表懒加载：每个view的Chart.js实例只在该tab第一次被激活时创建，避免
display:none的canvas初始化时宽高为0导致图表不渲染的常见坑。

当前进度：build_s1_view()已实现并用真实数据核验（S1_总览仪表盘/A-H板块）。
S2/S3/S4/同行/银行/代理人/KA共7个视角待续。
"""
import json
from pathlib import Path

from skills.ppt_data_loader import num

_VENDOR_CHART_JS = (Path(__file__).parent / "vendor" / "chart.umd.min.js").read_text(encoding="utf-8")

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _ym_label(ym: str) -> str:
    yr, mm = ym.split("-")
    return f"{yr[-2:]}-{MONTHS_EN[int(mm) - 1]}"


def build_s1_view(s1: dict) -> dict:
    """S1总览仪表盘视角。s1 = ppt_data_loader.load_sheet(S1_总览仪表盘/)。
    口径跟 ppt_generator.py::build_slide1() 完全一致（同一份S1_总览仪表盘CSV，
    同一套目标/达成/缺口/占比算法），两边算出来的数字必须对得上。"""
    A, B, F, G = s1["A"], s1["B"], s1["F"], s1["G"]

    def a_row(key):
        r = A[A["指标"] == key].iloc[0]
        return num(r["目标APE"]), num(r["已达成APE"]), num(r["目标达成率"])

    full_target, full_achv, full_rate = a_row("2026全业务目标")
    sun_target, sun_achv, sun_rate = a_row("2026永明业务目标")

    def b_row(key):
        r = B[B["指标行"] == key].iloc[0]
        return int(num(r["件数"])), num(r["APE"])

    issued_cnt, issued_ape = b_row("批核(2026)")
    unbat_cnt, unbat_ape = b_row("未批核(跨年)")
    pend_cnt, pend_ape = b_row("待签(跨年)")
    lost_cnt, lost_ape = b_row("流失(2026)")
    pipe_total = issued_ape + unbat_ape + pend_ape + lost_ape

    # 业务类型堆叠（经代/代理人/KA业务 × 批核/未批核/待签）
    biz_types = ["经代业务", "代理人业务", "KA业务"]
    g_row = {r["业务类型"]: r for _, r in G.iterrows()}
    business_type = {
        bt: {
            "batch": num(g_row[bt]["2026批核APE"]),
            "unbat": num(g_row[bt]["未批核APE"]),
            "pend": num(g_row[bt]["待签APE"]),
        }
        for bt in biz_types if bt in g_row
    }

    # 月度趋势（预约/签单/批核，全部可用月份）
    C, D, E = s1["C"], s1["D"], s1["E"]
    months = sorted(C["年月"].tolist())

    def monthly_series(df):
        by_month = {r["年月"]: num(r["APE"]) for _, r in df.iterrows()}
        return [round(by_month.get(m, 0.0), 0) for m in months]

    monthly_trend = {
        "labels": [_ym_label(m) for m in months],
        "预约": monthly_series(C),
        "签单": monthly_series(D),
        "批核": monthly_series(E),
    }

    # 保单状态明细（F板块，10个细分状态，供表格展示）
    status_detail = [
        {"状态": r["保单状态"], "件数": int(num(r["件数"])), "APE": num(r["APE"]), "APE占比": num(r["APE占比"])}
        for _, r in F.iterrows() if r["保单状态"] != "合计"
    ]

    return {
        "full_target": full_target, "full_achv": full_achv, "full_rate": full_rate,
        "full_gap": full_target - full_achv,
        "sun_target": sun_target, "sun_achv": sun_achv, "sun_rate": sun_rate,
        "sun_gap": sun_target - sun_achv,
        "issued_ape": issued_ape, "issued_cnt": issued_cnt,
        "unbat_ape": unbat_ape, "unbat_cnt": unbat_cnt,
        "pend_ape": pend_ape, "pend_cnt": pend_cnt,
        "lost_ape": lost_ape, "lost_cnt": lost_cnt,
        "pipe_total": pipe_total,
        "business_type": business_type,
        "monthly_trend": monthly_trend,
        "status_detail": status_detail,
    }


def build_s2_view(s2: dict) -> dict:
    """S2业务端视角。s2 = ppt_data_loader.load_sheet(S2_业务端视角/)，需要A/C/D/E/I。
    SEGMENT_ORDER直接import自ppt_config.py（Jasper已确认的8项业务细分顺序常量），
    不在本模块重新定义一份，避免像旧版update_ppt.py那样多处定义互相矛盾。"""
    from skills.ppt_config import SEGMENT_ORDER

    A, C, D, E, I = s2["A"], s2["C"], s2["D"], s2["E"], s2["I"]

    a_rows = {r["业务细分"]: r for _, r in A.iterrows() if r["业务细分"] != "合计"}
    segments = [s for s in SEGMENT_ORDER if s in a_rows]
    target_total = sum(num(a_rows[s]["目标APE"]) for s in segments)
    issued_total = sum(num(a_rows[s]["2026批核APE"]) for s in segments)
    unbat_total = sum(num(a_rows[s]["未批核APE"]) for s in segments)
    pend_total = sum(num(a_rows[s]["待签APE"]) for s in segments)
    overall_rate = issued_total / target_total if target_total else 0.0

    segment_bars = {
        "labels": segments,
        "target": [num(a_rows[s]["目标APE"]) for s in segments],
        "issued": [num(a_rows[s]["2026批核APE"]) for s in segments],
        "unbat": [num(a_rows[s]["未批核APE"]) for s in segments],
        "pend": [num(a_rows[s]["待签APE"]) for s in segments],
        "rate": [num(a_rows[s]["达成率"]) for s in segments],
    }

    # KEY ACCOUNT 排行（I板块，含"合计"行，需排除；本身没有预排序，独立降序排序）
    i_rows = I[I["KEY ACCOUNT"] != "合计"].copy()
    i_rows["_sort"] = i_rows["2026批核APE"].apply(num)
    i_rows = i_rows.sort_values("_sort", ascending=False)
    ka_rank = [
        {
            "rank": idx + 1, "ka": r["KEY ACCOUNT"], "segment": r["业务细分"],
            "issued": num(r["2026批核APE"]), "issued_cnt": int(num(r["批核件数"])),
            "unbat": num(r["未批核APE"]), "pend": num(r["待签APE"]),
        }
        for idx, (_, r) in enumerate(i_rows.iterrows())
    ]

    # 各业务细分渠道月度趋势（预约=C，签单=D，批核=E）
    month_cols = [c for c in C.columns if c.endswith("_APE") and c.startswith("2026-")]
    months_ym = [c[:-4] for c in month_cols]

    def seg_monthly(df, seg):
        row = df[df["业务细分"] == seg]
        if row.empty:
            return [0.0] * len(months_ym)
        row = row.iloc[0]
        return [round(num(row[f"{m}_APE"]), 0) for m in months_ym]

    monthly_by_segment = {
        seg: {
            "labels": [_ym_label(m) for m in months_ym],
            "预约": seg_monthly(C, seg),
            "签单": seg_monthly(D, seg),
            "批核": seg_monthly(E, seg),
        }
        for seg in segments
    }

    return {
        "segments": segments,
        "target_total": target_total, "issued_total": issued_total,
        "unbat_total": unbat_total, "pend_total": pend_total,
        "overall_rate": overall_rate,
        "segment_bars": segment_bars,
        "ka_rank": ka_rank,
        "monthly_by_segment": monthly_by_segment,
    }


def build_s3_view(s3: dict) -> dict:
    """S3执行管理端视角。s3 = ppt_data_loader.load_sheet(S3_执行管理端/)，需要A/G，
    E_ape/F_ape可选（未批核/待签分布，常规/融资）。
    A板块"阶段"=预约/签单/递交/批核，这正是W37/W38真实报表"递交"归零那个指标——
    本视角把"递交"跟其余3阶段并列展示为KPI+周度趋势线，用真实、非零的独立核算
    结果作为跟Jasper沟通口径的直接证据（见执行记录.md v0.15.0）。"""
    A, G = s3["A"], s3["G"]

    week_cols_ape = [c for c in A.columns if c.endswith("_APE")]
    weeks = [c[:-4] for c in week_cols_ape]  # '2026W01' 等，不含后缀

    stage_row = {r["阶段"]: r for _, r in A.iterrows()}
    stages = ["预约", "签单", "递交", "批核"]
    stage_totals = {}
    for s in stages:
        row = stage_row[s]
        ape_total = sum(num(row[f"{w}_APE"]) for w in weeks)
        cnt_total = sum(num(row[f"{w}_件数"]) for w in weeks)
        stage_totals[s] = {"ape": ape_total, "cnt": int(cnt_total)}

    weekly_trend = {
        "labels": [w.replace("2026W", "W") for w in weeks],
        **{s: [round(num(stage_row[s][f"{w}_APE"]), 0) for w in weeks] for s in stages},
    }

    timeliness = [
        {
            "业务细分": r["业务细分"], "件数": int(num(r["件数"])),
            "件均APE": num(r["件均APE"]), "平均时效": num(r["平均时效(天)"]),
            "中位时效": num(r["中位时效(天)"]), "P90时效": num(r["P90时效(天)"]),
            "最大时效": num(r["最大时效(天)"]), "SLA达标率": num(r["SLA达标率≤60"]),
        }
        for _, r in G.iterrows()
    ]

    result = {
        "weeks_count": len(weeks),
        "stage_totals": stage_totals,
        "weekly_trend": weekly_trend,
        "timeliness": timeliness,
    }

    if "E_ape" in s3:
        result["unbat_pending_regular"] = _pivot_ka_month(s3["E_ape"])
    if "F_ape" in s3:
        result["unbat_pending_financing"] = _pivot_ka_month(s3["F_ape"])

    return result


def _pivot_ka_month(df):
    """把"行=KEY ACCOUNT，列=月份+合计"的宽表转成{months, rows:[{ka, monthly, total}]}，
    按合计降序，供S3未批核/待签分布表渲染用。E_ape/F_ape通用。"""
    month_cols = [c for c in df.columns if c not in ("KEY ACCOUNT", "合计")]
    rows = []
    for _, r in df.iterrows():
        if str(r["KEY ACCOUNT"]).strip() == "合计":
            continue
        rows.append({
            "ka": r["KEY ACCOUNT"],
            "monthly": [round(num(r[m]), 0) for m in month_cols],
            "total": round(num(r["合计"]), 0),
        })
    rows.sort(key=lambda x: x["total"], reverse=True)
    return {"months": month_cols, "rows": rows}


def build_s4_view(s4: dict) -> dict:
    """S4产品端视角。s4 = ppt_data_loader.load_sheet(S4_产品端视角/)，需要A（保司分布）/
    C（产品TOP20，已按APE降序、自带排名列，不需要重新排序）。"""
    A, C = s4["A"], s4["C"]

    carrier_dist = [
        {
            "保司": r["保险公司"], "件数": int(num(r["件数"])), "APE": num(r["APE"]),
            "APE件均": num(r["APE件均"]), "件数占比": num(r["件数占比"]), "APE占比": num(r["APE占比"]),
        }
        for _, r in A.iterrows()
    ]
    product_rank = [
        {
            "排名": int(num(r["排名"])), "保司": r["保司"], "产品名称": r["产品名称"],
            "年期": r["年期"], "首年折扣": r["首年折扣"], "件数": int(num(r["件数"])),
            "APE": num(r["APE"]), "APE件均": num(r["APE件均"]),
        }
        for _, r in C.iterrows()
    ]
    return {"carrier_dist": carrier_dist, "product_rank": product_rank}


def build_peer_view(s2: dict, s3: dict) -> dict:
    """同行业绩视角。数据分散在S2（J=同行推荐人分析，K=同行KA业绩）和S3（J_ape/J_count=
    同行预约周度，K_ape/K_count=同行签单周度，L_ape/L_count=同行批核周度）。
    计算逻辑参照ppt_generator.py::build_slide8()/build_slide9()（同行排序/月度分桶算法），
    但不import那两个函数（混杂了python-pptx操作），本函数独立用纯pandas重写。"""
    from skills.ppt_monthly_bucket import derive_monthly_buckets

    J, K = s2["J"], s2["K"]

    k_total = K[K["KEY ACCOUNT"] == "合计"].iloc[0]
    issued_ape, issued_cnt = num(k_total["2026批核APE"]), int(num(k_total["批核件数"]))
    unbat_ape, unbat_cnt = num(k_total["未批核APE"]), int(num(k_total["未批核件数"]))
    pend_ape, pend_cnt = num(k_total["待签APE"]), int(num(k_total["待签件数"]))

    j_rows = J[J["推荐人"] != "合计"].copy()
    j_rows["_sort"] = j_rows["2026批核APE"].apply(num)
    j_rows = j_rows.sort_values("_sort", ascending=False)
    referrer_bar = {
        "labels": j_rows["推荐人"].tolist(),
        "批核": [num(v) for v in j_rows["2026批核APE"]],
        "未批核": [num(v) for v in j_rows["未批核APE"]],
        "待签": [num(v) for v in j_rows["待签APE"]],
    }

    k_rows = K[K["KEY ACCOUNT"] != "合计"].copy()
    k_rows["_sort"] = k_rows["2026批核APE"].apply(num)
    k_rows = k_rows.sort_values("_sort", ascending=False)
    ka_rank = [
        {
            "rank": i + 1, "ka": r["KEY ACCOUNT"], "issued": num(r["2026批核APE"]),
            "issued_cnt": int(num(r["批核件数"])), "unbat": num(r["未批核APE"]),
            "pend": num(r["待签APE"]), "total": num(r["总APE"]),
        }
        for i, (_, r) in enumerate(k_rows.iterrows())
    ]

    J_ape, K_ape, L_ape = s3["J_ape"], s3["K_ape"], s3["L_ape"]
    J_cnt, K_cnt, L_cnt = s3["J_count"], s3["K_count"], s3["L_count"]
    weeks = [c for c in J_ape.columns if c.startswith("2026W")]
    j_tot = J_ape[J_ape["KEY ACCOUNT"] == "合计"].iloc[0]
    k_tot = K_ape[K_ape["KEY ACCOUNT"] == "合计"].iloc[0]
    l_tot = L_ape[L_ape["KEY ACCOUNT"] == "合计"].iloc[0]
    j_cnt_tot = J_cnt[J_cnt["KEY ACCOUNT"] == "合计"].iloc[0]
    k_cnt_tot = K_cnt[K_cnt["KEY ACCOUNT"] == "合计"].iloc[0]
    l_cnt_tot = L_cnt[L_cnt["KEY ACCOUNT"] == "合计"].iloc[0]

    weekly_trend = {
        "labels": [w.replace("2026", "") for w in weeks],
        "预约": [round(num(j_tot.get(w, 0)), 0) for w in weeks],
        "签单": [round(num(k_tot.get(w, 0)), 0) for w in weeks],
        "批核": [round(num(l_tot.get(w, 0)), 0) for w in weeks],
    }

    buckets = derive_monthly_buckets(weeks)
    monthly_rows = []
    for month_label, weeks_in_month in buckets:
        monthly_rows.append({
            "month": month_label,
            "预约APE": sum(num(j_tot.get(w, 0)) for w in weeks_in_month),
            "预约件数": int(sum(num(j_cnt_tot.get(w, 0)) for w in weeks_in_month)),
            "签单APE": sum(num(k_tot.get(w, 0)) for w in weeks_in_month),
            "签单件数": int(sum(num(k_cnt_tot.get(w, 0)) for w in weeks_in_month)),
            "批核APE": sum(num(l_tot.get(w, 0)) for w in weeks_in_month),
            "批核件数": int(sum(num(l_cnt_tot.get(w, 0)) for w in weeks_in_month)),
        })

    return {
        "issued_ape": issued_ape, "issued_cnt": issued_cnt,
        "unbat_ape": unbat_ape, "unbat_cnt": unbat_cnt,
        "pend_ape": pend_ape, "pend_cnt": pend_cnt,
        "referrer_bar": referrer_bar,
        "ka_rank": ka_rank,
        "weekly_trend": weekly_trend,
        "monthly_rows": monthly_rows,
    }


def build_bank_view(s2: dict, s3: dict) -> dict:
    """银行业绩视角。数据分散在S2（A=BK业务目标/达成率行，O=银行KA明细）和S3（M_ape/M_count=
    银行预约周度，N_ape/N_count=银行签单周度，O_ape/O_count=银行批核周度）。
    ⚠️已知口径差异（跟ppt_generator.py::build_slide10()文档记录的发现一致）：
    S2-O(按issue事件全量口径)合计批核APE 跟 S3-O_ape(按%U周聚合口径)合计 相差约3.1M，
    是两种统计口径的真实差异、不是bug。本函数KPI/目标/银行明细统一用S2-O（全量口径），
    周度趋势图用S3（唯一有时间序列的来源），差值在返回值里显式算出，前端展示成口径说明，
    不悄悄对平。"""
    A, O = s2["A"], s2["O"]
    S = s2["S"]

    bk_row = A[A["业务细分"] == "BK业务"].iloc[0]
    target = num(bk_row["目标APE"])
    rate = num(bk_row["达成率"])

    o_total = O[O["KEY ACCOUNT"] == "合计"].iloc[0]
    issued_ape, issued_cnt = num(o_total["2026批核APE"]), int(num(o_total["批核件数"]))
    unbat_ape, unbat_cnt = num(o_total["未批核APE"]), int(num(o_total["未批核件数"]))
    pend_ape, pend_cnt = num(o_total["待签APE"]), int(num(o_total["待签件数"]))

    o_rows = O[O["KEY ACCOUNT"] != "合计"].copy()
    o_rows["_sort"] = o_rows["2026批核APE"].apply(num)
    o_rows = o_rows.sort_values("_sort", ascending=False)
    bank_bar = {
        "labels": o_rows["KEY ACCOUNT"].tolist(),
        "批核": [num(v) for v in o_rows["2026批核APE"]],
        "批核件数": [int(num(v)) for v in o_rows["批核件数"]],
        "未批核": [num(v) for v in o_rows["未批核APE"]],
        "待签": [num(v) for v in o_rows["待签APE"]],
    }

    M_ape, N_ape, O_ape = s3["M_ape"], s3["N_ape"], s3["O_ape"]

    def week_cols(df):
        return [c for c in df.columns if c.startswith("2026W")]

    weeks = sorted(
        set(week_cols(M_ape)) | set(week_cols(N_ape)) | set(week_cols(O_ape)),
        key=lambda w: int(w.replace("2026W", "")),
    )
    m_tot = M_ape[M_ape["KEY ACCOUNT"] == "合计"].iloc[0]
    n_tot = N_ape[N_ape["KEY ACCOUNT"] == "合计"].iloc[0]
    o_tot_s3 = O_ape[O_ape["KEY ACCOUNT"] == "合计"].iloc[0]

    def safe(row, col):
        return num(row[col]) if col in row.index else 0.0

    weekly_trend = {
        "labels": [w.replace("2026", "") for w in weeks],
        "预约": [round(safe(m_tot, w), 0) for w in weeks],
        "签单": [round(safe(n_tot, w), 0) for w in weeks],
        "批核": [round(safe(o_tot_s3, w), 0) for w in weeks],
    }
    o_total_s3_sum = num(o_tot_s3["合计"]) if "合计" in o_tot_s3.index else sum(safe(o_tot_s3, w) for w in weeks)

    s_rows = S[S["合作伙伴(分行)"] != "合计"].copy()
    s_rows["_tot"] = s_rows["合计"].apply(num)
    s_rows = s_rows[s_rows["_tot"] > 0].sort_values("_tot", ascending=False)
    branch_bar = {"labels": s_rows["合作伙伴(分行)"].tolist(), "合计": [num(v) for v in s_rows["_tot"]]}

    return {
        "target": target, "rate": rate,
        "issued_ape": issued_ape, "issued_cnt": issued_cnt,
        "unbat_ape": unbat_ape, "unbat_cnt": unbat_cnt,
        "pend_ape": pend_ape, "pend_cnt": pend_cnt,
        "bank_bar": bank_bar,
        "weekly_trend": weekly_trend,
        "branch_bar": branch_bar,
        "o_total_s2": issued_ape, "o_total_s3": o_total_s3_sum,
        "o_diff": issued_ape - o_total_s3_sum,
    }


def _s9_monthly_dict(df) -> dict:
    """把S9的D/E/G板块（行=指标"预约 APE"等，列=月份+合计）转成
    {labels, 预约:[...], 签单:[...], 批核:[...]}，供月度趋势线图使用。"""
    months = [c for c in df.columns if c not in ("指标", "合计")]
    idx = {r["指标"]: r for _, r in df.iterrows()}

    def series(key):
        return [round(num(idx[key][m]), 0) for m in months]

    return {
        "labels": [_ym_label(m) for m in months],
        "预约": series("预约 APE"),
        "签单": series("签单 APE"),
        "批核": series("批核 APE"),
    }


def _s9_monthly_sum(dfs: list) -> dict:
    """把多个同结构S9月度明细df逐月相加（代理人业务=天领+成事家办两个segment求和）。"""
    base = _s9_monthly_dict(dfs[0])
    for df in dfs[1:]:
        other = _s9_monthly_dict(df)
        for key in ("预约", "签单", "批核"):
            base[key] = [a + b for a, b in zip(base[key], other[key])]
    return base


def _s9_segment_group_view(s9: dict, segments: list, ka_frames: dict, monthly_trend: dict) -> dict:
    """代理人业务/KA业务视角共用的聚合逻辑：从S9-A取segments子集算KPI，
    从各自的KA明细表(B/C 或 F_*)合并排行，月度趋势由调用方传入(已经算好)。"""
    A = s9["A"]
    a_rows = {r["业务细分"]: r for _, r in A.iterrows() if r["业务细分"] != "合计"}
    target_total = sum(num(a_rows[s]["目标APE"]) for s in segments)
    issued_total = sum(num(a_rows[s]["2026批核APE"]) for s in segments)
    unbat_total = sum(num(a_rows[s]["未批核APE"]) for s in segments)
    pend_total = sum(num(a_rows[s]["待签APE"]) for s in segments)
    rate = issued_total / target_total if target_total else 0.0

    ka_rows = []
    for seg, df in ka_frames.items():
        if df is None:
            continue
        for _, r in df.iterrows():
            if str(r["KEY ACCOUNT"]).strip() == "合计":
                continue
            ka_rows.append({
                "ka": r["KEY ACCOUNT"], "segment": seg,
                "issued": num(r["2026批核APE"]), "issued_cnt": int(num(r["批核件数"])),
                "unbat": num(r["未批核APE"]), "pend": num(r["待签APE"]), "total": num(r["总APE"]),
            })
    ka_rows.sort(key=lambda x: x["issued"], reverse=True)
    for i, row in enumerate(ka_rows):
        row["rank"] = i + 1

    segment_bars = {
        "labels": segments,
        "目标": [num(a_rows[s]["目标APE"]) for s in segments],
        "批核": [num(a_rows[s]["2026批核APE"]) for s in segments],
        "未批核": [num(a_rows[s]["未批核APE"]) for s in segments],
        "待签": [num(a_rows[s]["待签APE"]) for s in segments],
        "达成率": [num(a_rows[s]["达成率"]) for s in segments],
    }

    return {
        "segments": segments, "target_total": target_total, "issued_total": issued_total,
        "unbat_total": unbat_total, "pend_total": pend_total, "rate": rate,
        "ka_rank": ka_rows, "monthly_trend": monthly_trend, "segment_bars": segment_bars,
    }


def build_agent_view(s9: dict) -> dict:
    """代理人业务视角 = S9-A的"天领业务"+"成事家办"两条纯代理人业务线（不含ICLUB/合伙转介/
    IFA这3条已被W38真实12页报告转正为独立"KA业务分析仪表盘"的业务线）。
    核实过程：S9_代理人与KA业务_反推标准_v0.1.md 1.1节明确写"A节=S2-A同一份业务细分年度
    汇总，只取5条'代理人'业务线：天领业务/成事家办/合伙转介业务/ICLUB业务/IFA业务"，
    跟本任务简报的推断一致。B=天领业务KA分析，C=成事家办KA分析，D=天领业务月度明细，
    E=成事家办月度明细，均已在反推标准文档里100%/高置信度核验过。"""
    segments = ["天领业务", "成事家办"]
    ka_frames = {"天领业务": s9.get("B"), "成事家办": s9.get("C")}
    monthly_trend = _s9_monthly_sum([s9["D"], s9["E"]])
    return _s9_segment_group_view(s9, segments, ka_frames, monthly_trend)


def build_ka_view(s9: dict) -> dict:
    """KA业务视角 = S9-A的"ICLUB业务"+"合伙转介业务"+"IFA业务"三条业务线，对应真实W38
    12页报告第12页"KA业务分析仪表盘 | ICLUB + 合伙转介 + IFA"。KA明细用F_ICLUB业务/
    F_合伙转介业务/F_IFA业务三张表合并排行；月度趋势直接用G板块（反推标准文档确认G板块
    本身就是segment IN(ICLUB,合伙转介,IFA)的合计口径，不需要再手工加总）。
    IFA业务当前批核/未批核/待签全为0（F_IFA业务.csv只有一行全零的"合计"），前端会显式
    标注这个业务线尚无实际发生额，不是数据缺失。"""
    segments = ["ICLUB业务", "合伙转介业务", "IFA业务"]
    ka_frames = {
        "ICLUB业务": s9.get("F_ICLUB业务"),
        "合伙转介业务": s9.get("F_合伙转介业务"),
        "IFA业务": s9.get("F_IFA业务"),
    }
    monthly_trend = _s9_monthly_dict(s9["G"])
    view = _s9_segment_group_view(s9, segments, ka_frames, monthly_trend)
    view["note_ifa_empty"] = num({r["业务细分"]: r for _, r in s9["A"].iterrows()}["IFA业务"]["2026批核APE"]) == 0
    return view


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>业绩数据多维分析 · 多视角前端</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;700;900&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script>__CHART_JS_INLINE__</script>
<style>
  :root{
    --ink:#0e1420; --ink-2:#141c2b; --card:#182236; --card-hi:#1e2b42; --line:#2a3650;
    --text:#eef1f0; --text-dim:#93a1b8; --text-faint:#5f6d87;
    --jade:#2fa88a; --jade-soft:rgba(47,168,138,0.16);
    --brass:#c9a15a; --brass-soft:rgba(201,161,90,0.16);
    --rose:#c96a5a; --rose-soft:rgba(201,106,90,0.14);
    --blue:#5b8fc9; --blue-soft:rgba(91,143,201,0.16);
    --serif:'Noto Serif SC', serif;
    --sans:'Inter', -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    --mono:'IBM Plex Mono', 'PingFang SC', monospace;
  }
  *{box-sizing:border-box; margin:0; padding:0;}
  body{
    background:
      radial-gradient(ellipse 900px 500px at 12% -10%, rgba(47,168,138,0.10), transparent 60%),
      radial-gradient(ellipse 700px 500px at 100% 0%, rgba(201,161,90,0.08), transparent 55%),
      var(--ink);
    color:var(--text); font-family:var(--sans); line-height:1.5; padding-bottom:80px;
  }
  .wrap{max-width:1280px; margin:0 auto; padding:0 28px;}

  header.hero{padding:44px 0 0; position:relative;}
  .eyebrow{font-family:var(--mono); font-size:12px; letter-spacing:3px; text-transform:uppercase; color:var(--jade); margin-bottom:14px; display:flex; align-items:center; gap:10px;}
  .eyebrow::before{content:"◆"; font-size:9px;}
  h1{font-family:var(--serif); font-weight:900; font-size:36px; letter-spacing:1px; color:var(--text); max-width:820px;}
  .sub{color:var(--text-dim); font-size:14px; margin-top:10px; max-width:720px;}

  .tabbar{display:flex; gap:4px; margin-top:32px; border-bottom:1px solid var(--line); overflow-x:auto;}
  .tab{
    font-family:var(--sans); font-size:13.5px; font-weight:600; color:var(--text-faint);
    padding:14px 18px; cursor:pointer; white-space:nowrap; border-bottom:2px solid transparent;
    transition:all .15s ease;
  }
  .tab:hover{color:var(--text-dim);}
  .tab.active{color:var(--jade); border-bottom-color:var(--jade);}
  .tab.disabled{color:var(--text-faint); opacity:.4; cursor:not-allowed;}

  .view{display:none; padding-top:36px;}
  .view.active{display:block;}
  .placeholder{padding:80px 0; text-align:center; color:var(--text-faint); font-family:var(--mono); font-size:13px;}

  .kpi-row{display:grid; grid-template-columns:repeat(5,1fr); gap:1px; background:var(--line); border:1px solid var(--line); border-radius:4px; overflow:hidden; margin-bottom:36px;}
  .kpi-row.cols-4{grid-template-columns:repeat(4,1fr);}
  .kpi-row.cols-3{grid-template-columns:repeat(3,1fr);}
  .kpi{background:var(--ink-2); padding:18px 20px;}
  .kpi .label{font-size:11.5px; color:var(--text-faint); letter-spacing:.5px;}
  .kpi .val{font-family:var(--mono); font-weight:600; font-size:22px; margin-top:8px; color:var(--text);}
  .kpi .val small{font-size:12px; color:var(--text-dim); font-weight:400; margin-left:3px;}
  .kpi.accent .val{color:var(--jade);}
  .kpi.warn .val{color:var(--rose);}
  @media (max-width:900px){ .kpi-row{grid-template-columns:repeat(2,1fr);} }

  section.blk{margin-bottom:40px;}
  .section-head{display:flex; align-items:baseline; justify-content:space-between; margin-bottom:18px; flex-wrap:wrap; gap:10px;}
  .section-head h2{font-family:var(--serif); font-size:19px; font-weight:700;}
  .section-head .note{font-size:12px; color:var(--text-faint); font-family:var(--mono);}
  .idx{color:var(--brass); font-family:var(--mono); font-size:12.5px; margin-right:8px;}

  .grid2{display:grid; grid-template-columns:1.3fr 1fr; gap:18px; margin-bottom:18px;}
  .grid3{display:grid; grid-template-columns:repeat(3,1fr); gap:18px; margin-bottom:18px;}
  .grid4{display:grid; grid-template-columns:repeat(4,1fr); gap:18px; margin-bottom:18px;}
  @media (max-width:900px){ .grid2,.grid3,.grid4{grid-template-columns:1fr;} }

  .card{background:var(--card); border:1px solid var(--line); border-radius:6px; padding:20px 22px;}
  .card h3{font-size:13px; font-weight:600; color:var(--text-dim); letter-spacing:.3px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center;}
  .card h3 span.tag{font-family:var(--mono); font-size:10.5px; color:var(--text-faint); font-weight:400;}
  .chart-box{position:relative; height:230px;}
  .chart-box.tall{height:280px;}

  table.dtable{width:100%; border-collapse:collapse; font-size:12.5px;}
  table.dtable th{text-align:right; color:var(--text-faint); font-weight:500; padding:8px 10px; border-bottom:1px solid var(--line); font-family:var(--mono); font-size:11px;}
  table.dtable th:first-child{text-align:left;}
  table.dtable td{text-align:right; padding:8px 10px; border-bottom:1px solid var(--line); font-family:var(--mono); color:var(--text);}
  table.dtable td:first-child{text-align:left; font-family:var(--sans); color:var(--text-dim);}
  table.dtable tr:last-child td{border-bottom:none;}
  table.dtable tr.total td{color:var(--brass); font-weight:600;}
  table.dtable tr.hi td:first-child{color:var(--jade); font-weight:600;}

  ::-webkit-scrollbar{height:6px; width:6px;}
  ::-webkit-scrollbar-thumb{background:var(--line); border-radius:3px;}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <div class="eyebrow">Performance Data · PDA Agent __AGENT_VERSION__ · Frontend</div>
    <h1>业绩数据多维分析<br>周报前端</h1>
    <p class="sub">从业绩数据底表直接生成，代替周业绩汇报PPT——每次运行重新清洗聚合，不是静态快照。数据来源 __SOURCE__。</p>
    <div class="tabbar" id="tabbar"></div>
  </header>

  <div id="views"></div>
</div>

<script>
const DATA = __DATA_JSON__;
const VIEWS = __VIEWS_META_JSON__;

Chart.defaults.color = '#93a1b8';
Chart.defaults.font.family = "'Inter','PingFang SC',sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.borderColor = '#2a3650';

const PALETTE = ['#2fa88a','#c9a15a','#c96a5a','#5b8fc9','#9a7ec9','#c9c05b','#5bc9c0','#c98fb0'];
const fmtM = n => (n/1e6).toFixed(1) + 'M';
const fmtPct = n => (n*100).toFixed(1) + '%';
const fmtCnt = n => Math.round(n).toLocaleString() + '件';

function makeLine(id, seriesNames){
  const ctx = document.getElementById(id);
  if(!ctx) return null;
  const colors = ['#2fa88a','#c9a15a','#c96a5a','#5b8fc9'];
  return new Chart(ctx, {
    type:'line',
    data:{labels:[], datasets: seriesNames.map((n,i)=>({label:n, data:[], borderColor:colors[i%colors.length], backgroundColor:'transparent', tension:0.3, pointRadius:2}))},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:seriesNames.length>1, position:'top', labels:{boxWidth:10,padding:10}}},
      scales:{ x:{grid:{display:false}}, y:{grid:{color:'#20293c'}, ticks:{callback:v=>fmtM(v)}} }}
  });
}
function makeBar(id, seriesNames, stacked){
  const ctx = document.getElementById(id);
  if(!ctx) return null;
  const colors = ['#2fa88a','#c9a15a','#c96a5a','#5b8fc9'];
  return new Chart(ctx, {
    type:'bar',
    data:{labels:[], datasets: seriesNames.map((n,i)=>({label:n, data:[], backgroundColor:colors[i%colors.length], borderRadius:3}))},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:seriesNames.length>1, position:'top', labels:{boxWidth:10,padding:10}}},
      scales:{ x:{stacked:!!stacked, grid:{display:false}}, y:{stacked:!!stacked, grid:{color:'#20293c'}, ticks:{callback:v=>fmtM(v)}} }}
  });
}
function makeDonut(id){
  const ctx = document.getElementById(id);
  if(!ctx) return null;
  return new Chart(ctx, {
    type:'doughnut',
    data:{labels:[], datasets:[{data:[], backgroundColor:PALETTE, borderColor:'#182236', borderWidth:2}]},
    options:{responsive:true, maintainAspectRatio:false, cutout:'62%',
      plugins:{legend:{position:'right', labels:{boxWidth:10, padding:10, font:{size:11}}}}}
  });
}

// ---- view: s1总览 ----
const viewInitFns = {};
viewInitFns.s1 = function(){
  const d = DATA.s1;
  const kpiRow = document.getElementById('s1_kpiRow');
  const kpis = [
    {label:'2026全业务达成率', val: fmtPct(d.full_rate), accent:true},
    {label:'已批核APE', val: fmtM(d.full_achv)},
    {label:'剩余缺口（全业务）', val: fmtM(d.full_gap)},
    {label:'永明业务达成率', val: fmtPct(d.sun_rate)},
    {label:'剩余缺口（永明）', val: fmtM(d.sun_gap)},
  ];
  kpiRow.innerHTML = kpis.map(k=>`<div class="kpi ${k.accent?'accent':''}"><div class="label">${k.label}</div><div class="val">${k.val}</div></div>`).join('');

  const pipeRow = document.getElementById('s1_pipeRow');
  const pipeKpis = [
    {label:'批核（生效）', val: fmtM(d.issued_ape), sub: `${d.issued_cnt}件 | 占比${fmtPct(d.issued_ape/d.pipe_total)}`},
    {label:'未批核', val: fmtM(d.unbat_ape), sub: `${d.unbat_cnt}件 | 占比${fmtPct(d.unbat_ape/d.pipe_total)}`},
    {label:'待签', val: fmtM(d.pend_ape), sub: `${d.pend_cnt}件 | 占比${fmtPct(d.pend_ape/d.pipe_total)}`},
    {label:'流失（2026）', val: fmtM(d.lost_ape), sub: `${d.lost_cnt}件 | 占比${fmtPct(d.lost_ape/d.pipe_total)}`},
  ];
  pipeRow.innerHTML = pipeKpis.map(k=>`<div class="kpi"><div class="label">${k.label}</div><div class="val">${k.val}<small> ${k.sub}</small></div></div>`).join('');

  const trendChart = makeLine('s1_chartTrend', ['预约','签单','批核']);
  if(trendChart){
    trendChart.data.labels = d.monthly_trend.labels;
    trendChart.data.datasets[0].data = d.monthly_trend['预约'];
    trendChart.data.datasets[1].data = d.monthly_trend['签单'];
    trendChart.data.datasets[2].data = d.monthly_trend['批核'];
    trendChart.update();
  }

  const bizChart = makeBar('s1_chartBiz', ['批核','未批核','待签'], true);
  if(bizChart){
    const cats = Object.keys(d.business_type);
    bizChart.data.labels = cats;
    bizChart.data.datasets[0].data = cats.map(c=>d.business_type[c].batch);
    bizChart.data.datasets[1].data = cats.map(c=>d.business_type[c].unbat);
    bizChart.data.datasets[2].data = cats.map(c=>d.business_type[c].pend);
    bizChart.update();
  }

  const donut = makeDonut('s1_chartPipeDonut');
  if(donut){
    donut.data.labels = ['批核','未批核','待签','流失'];
    donut.data.datasets[0].data = [d.issued_ape, d.unbat_ape, d.pend_ape, d.lost_ape];
    donut.update();
  }

  const tbody = document.getElementById('s1_statusTable');
  tbody.innerHTML = d.status_detail.map(r=>`
    <tr><td>${r['状态']}</td><td>${fmtCnt(r['件数'])}</td><td>${fmtM(r['APE'])}</td><td>${fmtPct(r['APE占比'])}</td></tr>
  `).join('');
};

function renderKaMonthTable(headId, bodyId, data){
  document.getElementById(headId).innerHTML = '<th>KEY ACCOUNT</th>' + data.months.map(m=>`<th>${m}</th>`).join('') + '<th>合计</th>';
  document.getElementById(bodyId).innerHTML = data.rows.map(r=>
    `<tr><td>${r.ka}</td>` + r.monthly.map(v=>`<td>${fmtM(v)}</td>`).join('') + `<td>${fmtM(r.total)}</td></tr>`
  ).join('');
}

// ---- view: s2业务端 ----
viewInitFns.s2 = function(){
  const d = DATA.s2;
  document.getElementById('s2_kpiRow').innerHTML = [
    {label:'8项业务目标APE合计', val: fmtM(d.target_total)},
    {label:'已批核APE合计', val: fmtM(d.issued_total), accent:true},
    {label:'整体达成率', val: fmtPct(d.overall_rate)},
    {label:'未批核APE合计', val: fmtM(d.unbat_total)},
    {label:'待签APE合计', val: fmtM(d.pend_total)},
  ].map(k=>`<div class="kpi ${k.accent?'accent':''}"><div class="label">${k.label}</div><div class="val">${k.val}</div></div>`).join('');

  const stackChart = makeBar('s2_chartSegStack', ['批核','未批核','待签'], true);
  if(stackChart){
    stackChart.data.labels = d.segment_bars.labels;
    stackChart.data.datasets[0].data = d.segment_bars.issued;
    stackChart.data.datasets[1].data = d.segment_bars.unbat;
    stackChart.data.datasets[2].data = d.segment_bars.pend;
    stackChart.update();
  }
  const rateChart = makeBar('s2_chartSegRate', ['达成率']);
  if(rateChart){
    rateChart.data.labels = d.segment_bars.labels;
    rateChart.data.datasets[0].data = d.segment_bars.rate.map(v=>Math.round(v*1000)/10);
    rateChart.options.scales.y.ticks.callback = v=>v+'%';
    rateChart.update();
  }

  document.getElementById('s2_kaTable').innerHTML = d.ka_rank.map(r=>`
    <tr class="${r.rank<=10?'hi':''}"><td>${r.rank}</td><td>${r.ka}</td><td>${r.segment}</td>
    <td>${fmtM(r.issued)}</td><td>${fmtCnt(r.issued_cnt)}</td><td>${fmtM(r.unbat)}</td><td>${fmtM(r.pend)}</td></tr>
  `).join('');

  const segGrid = document.getElementById('s2_segCharts');
  segGrid.innerHTML = d.segments.map((seg,i)=>`
    <div class="card"><h3>${seg}<span class="tag">预约/签单/批核</span></h3>
    <div class="chart-box"><canvas id="s2_segchart_${i}"></canvas></div></div>`).join('');
  d.segments.forEach((seg,i)=>{
    const ch = makeLine('s2_segchart_'+i, ['预约','签单','批核']);
    if(ch){
      const m = d.monthly_by_segment[seg];
      ch.data.labels = m.labels;
      ch.data.datasets[0].data = m['预约'];
      ch.data.datasets[1].data = m['签单'];
      ch.data.datasets[2].data = m['批核'];
      ch.update();
    }
  });
};

// ---- view: s3执行管理端 ----
viewInitFns.s3 = function(){
  const d = DATA.s3;
  const st = d.stage_totals;
  document.getElementById('s3_kpiRow').innerHTML = [
    {label:'预约合计', val: fmtM(st['预约'].ape), sub:`${st['预约'].cnt}件`},
    {label:'签单合计', val: fmtM(st['签单'].ape), sub:`${st['签单'].cnt}件`},
    {label:'递交合计', val: fmtM(st['递交'].ape), sub:`${st['递交'].cnt}件`, accent:true},
    {label:'批核合计', val: fmtM(st['批核'].ape), sub:`${st['批核'].cnt}件`},
  ].map(k=>`<div class="kpi ${k.accent?'accent':''}"><div class="label">${k.label}</div><div class="val">${k.val}<small> ${k.sub}</small></div></div>`).join('');

  const funnelChart = makeLine('s3_chartFunnel', ['预约','签单','递交','批核']);
  if(funnelChart){
    funnelChart.data.labels = d.weekly_trend.labels;
    ['预约','签单','递交','批核'].forEach((s,i)=>{ funnelChart.data.datasets[i].data = d.weekly_trend[s]; });
    funnelChart.update();
  }

  document.getElementById('s3_timelinessTable').innerHTML = d.timeliness.map(r=>`
    <tr><td>${r['业务细分']}</td><td>${fmtCnt(r['件数'])}</td><td>${fmtM(r['件均APE'])}</td>
    <td>${r['平均时效'].toFixed(1)}</td><td>${r['中位时效'].toFixed(1)}</td><td>${r['P90时效'].toFixed(1)}</td>
    <td>${r['最大时效'].toFixed(1)}</td><td>${fmtPct(r['SLA达标率'])}</td></tr>
  `).join('');

  if(d.unbat_pending_regular){
    renderKaMonthTable('s3_regHead','s3_regBody', d.unbat_pending_regular);
  }
  if(d.unbat_pending_financing){
    renderKaMonthTable('s3_finHead','s3_finBody', d.unbat_pending_financing);
  }
};

// ---- view: s4产品端 ----
viewInitFns.s4 = function(){
  const d = DATA.s4;
  document.getElementById('s4_productTable').innerHTML = d.product_rank.map(r=>`
    <tr><td>${r['排名']}</td><td>${r['保司']}</td><td>${r['产品名称']}</td><td>${r['年期']}</td>
    <td>${r['首年折扣']}</td><td>${fmtCnt(r['件数'])}</td><td>${fmtM(r['APE'])}</td><td>${fmtM(r['APE件均'])}</td></tr>
  `).join('');

  const donut = makeDonut('s4_chartCarrierDonut');
  if(donut){
    donut.data.labels = d.carrier_dist.map(c=>c['保司']);
    donut.data.datasets[0].data = d.carrier_dist.map(c=>c['APE']);
    donut.update();
  }

  document.getElementById('s4_carrierTable').innerHTML = d.carrier_dist.map(r=>`
    <tr><td>${r['保司']}</td><td>${fmtCnt(r['件数'])}</td><td>${fmtM(r['APE'])}</td>
    <td>${fmtM(r['APE件均'])}</td><td>${fmtPct(r['件数占比'])}</td><td>${fmtPct(r['APE占比'])}</td></tr>
  `).join('');
};

// ---- view: peer同行业绩 ----
viewInitFns.peer = function(){
  const d = DATA.peer;
  document.getElementById('peer_kpiRow').innerHTML = [
    {label:'批核（生效）', val: fmtM(d.issued_ape), sub:`${d.issued_cnt}件`},
    {label:'未批核', val: fmtM(d.unbat_ape), sub:`${d.unbat_cnt}件`},
    {label:'待签', val: fmtM(d.pend_ape), sub:`${d.pend_cnt}件`},
  ].map(k=>`<div class="kpi"><div class="label">${k.label}</div><div class="val">${k.val}<small> ${k.sub}</small></div></div>`).join('');

  const refChart = makeBar('peer_chartReferrer', ['批核','未批核','待签'], true);
  if(refChart){
    refChart.data.labels = d.referrer_bar.labels;
    refChart.data.datasets[0].data = d.referrer_bar['批核'];
    refChart.data.datasets[1].data = d.referrer_bar['未批核'];
    refChart.data.datasets[2].data = d.referrer_bar['待签'];
    refChart.update();
  }

  document.getElementById('peer_kaTable').innerHTML = d.ka_rank.map(r=>`
    <tr class="${r.rank<=10?'hi':''}"><td>${r.rank}</td><td>${r.ka}</td><td>${fmtM(r.issued)}</td>
    <td>${fmtCnt(r.issued_cnt)}</td><td>${fmtM(r.unbat)}</td><td>${fmtM(r.pend)}</td><td>${fmtM(r.total)}</td></tr>
  `).join('');

  const weeklyChart = makeLine('peer_chartWeekly', ['预约','签单','批核']);
  if(weeklyChart){
    weeklyChart.data.labels = d.weekly_trend.labels;
    weeklyChart.data.datasets[0].data = d.weekly_trend['预约'];
    weeklyChart.data.datasets[1].data = d.weekly_trend['签单'];
    weeklyChart.data.datasets[2].data = d.weekly_trend['批核'];
    weeklyChart.update();
  }

  document.getElementById('peer_monthlyTable').innerHTML = d.monthly_rows.map(r=>`
    <tr><td>${r.month}</td><td>${fmtM(r['预约APE'])}</td><td>${fmtCnt(r['预约件数'])}</td>
    <td>${fmtM(r['签单APE'])}</td><td>${fmtCnt(r['签单件数'])}</td><td>${fmtM(r['批核APE'])}</td><td>${fmtCnt(r['批核件数'])}</td></tr>
  `).join('');
};

// ---- view: bank银行业绩 ----
viewInitFns.bank = function(){
  const d = DATA.bank;
  document.getElementById('bank_kpiRow').innerHTML = [
    {label:'BK业务目标APE', val: fmtM(d.target)},
    {label:'达成率', val: fmtPct(d.rate), accent:true},
    {label:'已批核APE', val: fmtM(d.issued_ape)},
    {label:'剩余缺口', val: fmtM(d.target - d.issued_ape)},
  ].map(k=>`<div class="kpi ${k.accent?'accent':''}"><div class="label">${k.label}</div><div class="val">${k.val}</div></div>`).join('');

  document.getElementById('bank_pipeRow').innerHTML = [
    {label:'批核（生效）', val: fmtM(d.issued_ape), sub:`${d.issued_cnt}件`},
    {label:'未批核', val: fmtM(d.unbat_ape), sub:`${d.unbat_cnt}件`},
    {label:'待签', val: fmtM(d.pend_ape), sub:`${d.pend_cnt}件`},
  ].map(k=>`<div class="kpi"><div class="label">${k.label}</div><div class="val">${k.val}<small> ${k.sub}</small></div></div>`).join('');

  const bankStack = makeBar('bank_chartBankStack', ['批核','未批核','待签'], true);
  if(bankStack){
    bankStack.data.labels = d.bank_bar.labels;
    bankStack.data.datasets[0].data = d.bank_bar['批核'];
    bankStack.data.datasets[1].data = d.bank_bar['未批核'];
    bankStack.data.datasets[2].data = d.bank_bar['待签'];
    bankStack.update();
  }

  document.getElementById('bank_table').innerHTML = d.bank_bar.labels.map((name,i)=>`
    <tr><td>${name}</td><td>${fmtM(d.bank_bar['批核'][i])}</td><td>${fmtCnt(d.bank_bar['批核件数'][i])}</td>
    <td>${fmtM(d.bank_bar['未批核'][i])}</td><td>${fmtM(d.bank_bar['待签'][i])}</td>
    <td>${fmtM(d.bank_bar['批核'][i]+d.bank_bar['未批核'][i]+d.bank_bar['待签'][i])}</td></tr>
  `).join('');

  document.getElementById('bank_diffNote').textContent =
    `口径说明：KPI/目标/银行明细用S2-O全量口径（合计${fmtM(d.o_total_s2)}），周度趋势用S3-O_ape周聚合口径（合计${fmtM(d.o_total_s3)}），两者相差${fmtM(Math.abs(d.o_diff))}——真实口径差异，非bug`;

  const weeklyChart = makeLine('bank_chartWeekly', ['预约','签单','批核']);
  if(weeklyChart){
    weeklyChart.data.labels = d.weekly_trend.labels;
    weeklyChart.data.datasets[0].data = d.weekly_trend['预约'];
    weeklyChart.data.datasets[1].data = d.weekly_trend['签单'];
    weeklyChart.data.datasets[2].data = d.weekly_trend['批核'];
    weeklyChart.update();
  }

  const branchChart = makeBar('bank_chartBranch', ['2026批核APE']);
  if(branchChart){
    branchChart.data.labels = d.branch_bar.labels;
    branchChart.data.datasets[0].data = d.branch_bar['合计'];
    branchChart.update();
  }
};

// ---- view: agent代理人业务 ----
viewInitFns.agent = function(){
  const d = DATA.agent;
  document.getElementById('agent_kpiRow').innerHTML = [
    {label:'目标APE合计', val: fmtM(d.target_total)},
    {label:'已批核APE合计', val: fmtM(d.issued_total), accent:true},
    {label:'达成率', val: fmtPct(d.rate)},
    {label:'剩余缺口', val: fmtM(d.target_total - d.issued_total)},
  ].map(k=>`<div class="kpi ${k.accent?'accent':''}"><div class="label">${k.label}</div><div class="val">${k.val}</div></div>`).join('');

  const stack = makeBar('agent_chartSegStack', ['批核','未批核','待签'], true);
  if(stack){
    stack.data.labels = d.segment_bars.labels;
    stack.data.datasets[0].data = d.segment_bars['批核'];
    stack.data.datasets[1].data = d.segment_bars['未批核'];
    stack.data.datasets[2].data = d.segment_bars['待签'];
    stack.update();
  }

  document.getElementById('agent_kaTable').innerHTML = d.ka_rank.map(r=>`
    <tr class="${r.rank<=10?'hi':''}"><td>${r.rank}</td><td>${r.ka}</td><td>${r.segment}</td>
    <td>${fmtM(r.issued)}</td><td>${fmtCnt(r.issued_cnt)}</td><td>${fmtM(r.unbat)}</td><td>${fmtM(r.pend)}</td></tr>
  `).join('');

  const mChart = makeLine('agent_chartMonthly', ['预约','签单','批核']);
  if(mChart){
    mChart.data.labels = d.monthly_trend.labels;
    mChart.data.datasets[0].data = d.monthly_trend['预约'];
    mChart.data.datasets[1].data = d.monthly_trend['签单'];
    mChart.data.datasets[2].data = d.monthly_trend['批核'];
    mChart.update();
  }
};

// ---- view: kaKA业务 ----
viewInitFns.ka = function(){
  const d = DATA.ka;
  document.getElementById('ka_kpiRow').innerHTML = [
    {label:'目标APE合计', val: fmtM(d.target_total)},
    {label:'已批核APE合计', val: fmtM(d.issued_total), accent:true},
    {label:'达成率', val: fmtPct(d.rate)},
    {label:'剩余缺口', val: fmtM(d.target_total - d.issued_total)},
  ].map(k=>`<div class="kpi ${k.accent?'accent':''}"><div class="label">${k.label}</div><div class="val">${k.val}</div></div>`).join('');

  document.getElementById('ka_ifaNote').textContent = d.note_ifa_empty ? 'IFA业务当前批核/未批核/待签均为0（尚无实际业务发生，非数据缺失）' : '';

  const stack = makeBar('ka_chartSegStack', ['批核','未批核','待签'], true);
  if(stack){
    stack.data.labels = d.segment_bars.labels;
    stack.data.datasets[0].data = d.segment_bars['批核'];
    stack.data.datasets[1].data = d.segment_bars['未批核'];
    stack.data.datasets[2].data = d.segment_bars['待签'];
    stack.update();
  }

  document.getElementById('ka_kaTable').innerHTML = d.ka_rank.map(r=>`
    <tr class="${r.rank<=10?'hi':''}"><td>${r.rank}</td><td>${r.ka}</td><td>${r.segment}</td>
    <td>${fmtM(r.issued)}</td><td>${fmtCnt(r.issued_cnt)}</td><td>${fmtM(r.unbat)}</td><td>${fmtM(r.pend)}</td></tr>
  `).join('');

  const mChart = makeLine('ka_chartMonthly', ['预约','签单','批核']);
  if(mChart){
    mChart.data.labels = d.monthly_trend.labels;
    mChart.data.datasets[0].data = d.monthly_trend['预约'];
    mChart.data.datasets[1].data = d.monthly_trend['签单'];
    mChart.data.datasets[2].data = d.monthly_trend['批核'];
    mChart.update();
  }
};

// ---- 视角切换 ----
const tabbar = document.getElementById('tabbar');
const viewsRoot = document.getElementById('views');
const initialized = new Set();

tabbar.innerHTML = VIEWS.map(v => `<div class="tab ${v.available?'':'disabled'}" data-view="${v.key}">${v.label}</div>`).join('');
viewsRoot.innerHTML = VIEWS.map(v => v.available ? v.html : `<div class="view" data-view="${v.key}"><div class="placeholder">「${v.label}」视角待续</div></div>`).join('');

function activateView(key){
  document.querySelectorAll('.tab').forEach(el => el.classList.toggle('active', el.dataset.view===key));
  document.querySelectorAll('.view').forEach(el => el.classList.toggle('active', el.dataset.view===key));
  if(!initialized.has(key) && viewInitFns[key]){
    viewInitFns[key]();
    initialized.add(key);
  }
}
tabbar.querySelectorAll('.tab').forEach(el=>{
  el.addEventListener('click', ()=>{
    if(el.classList.contains('disabled')) return;
    activateView(el.dataset.view);
  });
});
activateView(VIEWS.find(v=>v.available).key);
</script>
</body>
</html>
"""

_S1_VIEW_HTML = r"""<div class="view" data-view="s1">
  <div class="kpi-row" id="s1_kpiRow"></div>
  <div class="kpi-row cols-4" id="s1_pipeRow"></div>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">01</span>月度趋势 & 业务类型结构</h2></div>
    <div class="grid2">
      <div class="card">
        <h3>预约 / 签单 / 批核 月度趋势<span class="tag">APE</span></h3>
        <div class="chart-box tall"><canvas id="s1_chartTrend"></canvas></div>
      </div>
      <div class="card">
        <h3>业务类型业绩（经代/代理人/KA）<span class="tag">批核/未批核/待签</span></h3>
        <div class="chart-box tall"><canvas id="s1_chartBiz"></canvas></div>
      </div>
    </div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">02</span>保单阶段分布</h2></div>
    <div class="grid2">
      <div class="card">
        <h3>批核/未批核/待签/流失 占比<span class="tag">含流失分母</span></h3>
        <div class="chart-box tall"><canvas id="s1_chartPipeDonut"></canvas></div>
      </div>
      <div class="card">
        <h3>保单状态明细（10档细分）<span class="tag">F板块</span></h3>
        <table class="dtable">
          <thead><tr><th>状态</th><th>件数</th><th>APE</th><th>APE占比</th></tr></thead>
          <tbody id="s1_statusTable"></tbody>
        </table>
      </div>
    </div>
  </section>
</div>"""


_S2_VIEW_HTML = r"""<div class="view" data-view="s2">
  <div class="kpi-row" id="s2_kpiRow"></div>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">01</span>业务细分：目标 vs 批核/未批核/待签</h2></div>
    <div class="grid2">
      <div class="card">
        <h3>8项业务细分构成<span class="tag">APE，堆叠</span></h3>
        <div class="chart-box tall"><canvas id="s2_chartSegStack"></canvas></div>
      </div>
      <div class="card">
        <h3>8项业务细分目标达成率<span class="tag">已批核/目标</span></h3>
        <div class="chart-box tall"><canvas id="s2_chartSegRate"></canvas></div>
      </div>
    </div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">02</span>KEY ACCOUNT 排行</h2><span class="note">按2026批核APE降序，前10高亮</span></div>
    <div class="card">
      <table class="dtable">
        <thead><tr><th>#</th><th>KEY ACCOUNT</th><th>业务细分</th><th>批核APE</th><th>批核件数</th><th>未批核APE</th><th>待签APE</th></tr></thead>
        <tbody id="s2_kaTable"></tbody>
      </table>
    </div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">03</span>各业务细分渠道月度趋势</h2><span class="note">预约/签单/批核，2026年各月</span></div>
    <div class="grid4" id="s2_segCharts"></div>
  </section>
</div>"""

_S3_VIEW_HTML = r"""<div class="view" data-view="s3">
  <div class="kpi-row cols-4" id="s3_kpiRow"></div>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">01</span>全流程转化漏斗：周度趋势</h2><span class="note">预约/签单/递交/批核——"递交"口径非零，见上方KPI</span></div>
    <div class="card"><div class="chart-box tall"><canvas id="s3_chartFunnel"></canvas></div></div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">02</span>签批时效（8项业务细分）</h2></div>
    <div class="card">
      <table class="dtable">
        <thead><tr><th>业务细分</th><th>件数</th><th>件均APE</th><th>平均时效(天)</th><th>中位时效(天)</th><th>P90时效(天)</th><th>最大时效(天)</th><th>SLA达标率≤60</th></tr></thead>
        <tbody id="s3_timelinessTable"></tbody>
      </table>
    </div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">03</span>未批核/待签分布（按KEY ACCOUNT × 月）</h2><span class="note">常规 / 融资两张表，is_pf标志区分</span></div>
    <div class="grid2">
      <div class="card">
        <h3>常规<span class="tag">is_pf=0</span></h3>
        <table class="dtable"><thead><tr id="s3_regHead"></tr></thead><tbody id="s3_regBody"></tbody></table>
      </div>
      <div class="card">
        <h3>融资<span class="tag">is_pf=1</span></h3>
        <table class="dtable"><thead><tr id="s3_finHead"></tr></thead><tbody id="s3_finBody"></tbody></table>
      </div>
    </div>
  </section>
</div>"""

_S4_VIEW_HTML = r"""<div class="view" data-view="s4">
  <div class="grid2">
    <div class="card">
      <h3>产品TOP20排行<span class="tag">按APE降序</span></h3>
      <table class="dtable">
        <thead><tr><th>#</th><th>保司</th><th>产品名称</th><th>年期</th><th>首年折扣</th><th>件数</th><th>APE</th><th>件均APE</th></tr></thead>
        <tbody id="s4_productTable"></tbody>
      </table>
    </div>
    <div class="card">
      <h3>保司分布<span class="tag">APE占比</span></h3>
      <div class="chart-box tall"><canvas id="s4_chartCarrierDonut"></canvas></div>
    </div>
  </div>
  <section class="blk">
    <div class="section-head"><h2><span class="idx">02</span>保司明细</h2></div>
    <div class="card">
      <table class="dtable">
        <thead><tr><th>保司</th><th>件数</th><th>APE</th><th>件均APE</th><th>件数占比</th><th>APE占比</th></tr></thead>
        <tbody id="s4_carrierTable"></tbody>
      </table>
    </div>
  </section>
</div>"""

_PEER_VIEW_HTML = r"""<div class="view" data-view="peer">
  <div class="kpi-row cols-3" id="peer_kpiRow"></div>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">01</span>同行推荐人分析</h2></div>
    <div class="card"><div class="chart-box tall"><canvas id="peer_chartReferrer"></canvas></div></div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">02</span>同行KEY ACCOUNT 排行</h2><span class="note">按2026批核APE降序，前10高亮</span></div>
    <div class="card">
      <table class="dtable">
        <thead><tr><th>#</th><th>KEY ACCOUNT</th><th>批核APE</th><th>批核件数</th><th>未批核APE</th><th>待签APE</th><th>总APE</th></tr></thead>
        <tbody id="peer_kaTable"></tbody>
      </table>
    </div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">03</span>周度趋势 & 月度分析</h2></div>
    <div class="grid2">
      <div class="card">
        <h3>预约/签单/批核 周度趋势<span class="tag">APE</span></h3>
        <div class="chart-box tall"><canvas id="peer_chartWeekly"></canvas></div>
      </div>
      <div class="card">
        <h3>月度分析表<span class="tag">按%U周三规则分桶</span></h3>
        <table class="dtable">
          <thead><tr><th>月份</th><th>预约APE</th><th>预约件数</th><th>签单APE</th><th>签单件数</th><th>批核APE</th><th>批核件数</th></tr></thead>
          <tbody id="peer_monthlyTable"></tbody>
        </table>
      </div>
    </div>
  </section>
</div>"""

_BANK_VIEW_HTML = r"""<div class="view" data-view="bank">
  <div class="kpi-row cols-4" id="bank_kpiRow"></div>
  <div class="kpi-row cols-3" id="bank_pipeRow"></div>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">01</span>银行明细 & KEY ACCOUNT构成</h2></div>
    <div class="grid2">
      <div class="card">
        <h3>各银行批核/未批核/待签<span class="tag">APE，堆叠</span></h3>
        <div class="chart-box tall"><canvas id="bank_chartBankStack"></canvas></div>
      </div>
      <div class="card">
        <h3>银行明细表</h3>
        <table class="dtable">
          <thead><tr><th>银行</th><th>批核APE</th><th>批核件数</th><th>未批核APE</th><th>待签APE</th><th>总APE</th></tr></thead>
          <tbody id="bank_table"></tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">02</span>周度趋势 & 分行排名</h2><span class="note" id="bank_diffNote"></span></div>
    <div class="grid2">
      <div class="card">
        <h3>预约/签单/批核 周度趋势<span class="tag">APE</span></h3>
        <div class="chart-box tall"><canvas id="bank_chartWeekly"></canvas></div>
      </div>
      <div class="card">
        <h3>各分行2026批核APE排名<span class="tag">S2-S</span></h3>
        <div class="chart-box tall"><canvas id="bank_chartBranch"></canvas></div>
      </div>
    </div>
  </section>
</div>"""

_AGENT_VIEW_HTML = r"""<div class="view" data-view="agent">
  <div class="kpi-row cols-4" id="agent_kpiRow"></div>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">01</span>业务细分构成</h2><span class="note">天领业务 + 成事家办</span></div>
    <div class="card"><div class="chart-box tall"><canvas id="agent_chartSegStack"></canvas></div></div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">02</span>KEY ACCOUNT 排行</h2><span class="note">按2026批核APE降序，前10高亮</span></div>
    <div class="card">
      <table class="dtable">
        <thead><tr><th>#</th><th>KEY ACCOUNT</th><th>业务细分</th><th>批核APE</th><th>批核件数</th><th>未批核APE</th><th>待签APE</th></tr></thead>
        <tbody id="agent_kaTable"></tbody>
      </table>
    </div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">03</span>月度趋势</h2><span class="note">天领+成事家办合计，2026-01至08</span></div>
    <div class="card"><div class="chart-box tall"><canvas id="agent_chartMonthly"></canvas></div></div>
  </section>
</div>"""

_KA_VIEW_HTML = r"""<div class="view" data-view="ka">
  <div class="kpi-row cols-4" id="ka_kpiRow"></div>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">01</span>业务细分构成</h2><span class="note" id="ka_ifaNote">ICLUB + 合伙转介 + IFA</span></div>
    <div class="card"><div class="chart-box tall"><canvas id="ka_chartSegStack"></canvas></div></div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">02</span>KEY ACCOUNT 排行</h2><span class="note">按2026批核APE降序，前10高亮</span></div>
    <div class="card">
      <table class="dtable">
        <thead><tr><th>#</th><th>KEY ACCOUNT</th><th>业务细分</th><th>批核APE</th><th>批核件数</th><th>未批核APE</th><th>待签APE</th></tr></thead>
        <tbody id="ka_kaTable"></tbody>
      </table>
    </div>
  </section>

  <section class="blk">
    <div class="section-head"><h2><span class="idx">03</span>月度趋势</h2><span class="note">ICLUB+合伙转介+IFA合计，2026-01至08</span></div>
    <div class="card"><div class="chart-box tall"><canvas id="ka_chartMonthly"></canvas></div></div>
  </section>
</div>"""


def render(data_root, agent_version: str, source_name: str = "业绩数据底表") -> str:
    from skills.ppt_data_loader import load_sheet

    data_root = Path(data_root)
    views_data = {}
    views_meta = []

    def add_view(key, label, available, html=""):
        views_meta.append({"key": key, "label": label, "available": available, "html": html})

    s1_dir = data_root / "S1_总览仪表盘"
    if s1_dir.exists():
        s1 = load_sheet(s1_dir)
        views_data["s1"] = build_s1_view(s1)
        add_view("s1", "S1总览", True, _S1_VIEW_HTML)
    else:
        add_view("s1", "S1总览", False)

    s2_dir = data_root / "S2_业务端视角"
    s2 = load_sheet(s2_dir) if s2_dir.exists() else None
    if s2 is not None:
        views_data["s2"] = build_s2_view(s2)
        add_view("s2", "S2业务端", True, _S2_VIEW_HTML)
    else:
        add_view("s2", "S2业务端", False)

    s3_dir = data_root / "S3_执行管理端"
    s3 = load_sheet(s3_dir) if s3_dir.exists() else None
    if s3 is not None:
        views_data["s3"] = build_s3_view(s3)
        add_view("s3", "S3执行管理端", True, _S3_VIEW_HTML)
    else:
        add_view("s3", "S3执行管理端", False)

    s4_dir = data_root / "S4_产品端视角"
    if s4_dir.exists():
        s4 = load_sheet(s4_dir)
        views_data["s4"] = build_s4_view(s4)
        add_view("s4", "S4产品端", True, _S4_VIEW_HTML)
    else:
        add_view("s4", "S4产品端", False)

    if s2 is not None and s3 is not None:
        views_data["peer"] = build_peer_view(s2, s3)
        add_view("peer", "同行业绩", True, _PEER_VIEW_HTML)
    else:
        add_view("peer", "同行业绩", False)

    if s2 is not None and s3 is not None:
        views_data["bank"] = build_bank_view(s2, s3)
        add_view("bank", "银行业绩", True, _BANK_VIEW_HTML)
    else:
        add_view("bank", "银行业绩", False)

    s9_dir = data_root / "S9_代理人与KA业务"
    s9 = load_sheet(s9_dir) if s9_dir.exists() else None
    if s9 is not None:
        views_data["agent"] = build_agent_view(s9)
        add_view("agent", "代理人业务", True, _AGENT_VIEW_HTML)
        views_data["ka"] = build_ka_view(s9)
        add_view("ka", "KA业务", True, _KA_VIEW_HTML)
    else:
        add_view("agent", "代理人业务", False)
        add_view("ka", "KA业务", False)

    html = _TEMPLATE
    html = html.replace("__CHART_JS_INLINE__", _VENDOR_CHART_JS)
    html = html.replace("__AGENT_VERSION__", agent_version)
    html = html.replace("__SOURCE__", source_name)
    html = html.replace("__DATA_JSON__", json.dumps(views_data, ensure_ascii=False))
    html = html.replace("__VIEWS_META_JSON__", json.dumps(
        [{"key": v["key"], "label": v["label"], "available": v["available"], "html": v.get("html", "")} for v in views_meta],
        ensure_ascii=False,
    ))
    return html
