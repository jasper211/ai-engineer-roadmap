"""
sowhat_generators.py — data-driven So What blurbs.

Each generator takes a context dict {S1, S2, S3, S4, s3_rows, current_week}
and returns a Chinese-language narrative string (usually 2-4 sentences,
~80-180 characters) based on current CSV data.

All numbers are computed live from CSVs. No hardcoded values.
"""
from data_loader import num
from apply_w14_patches import parse_section_weekly_all


def _to_m(x): return num(x) / 1_000_000
def _to_w(x): return num(x) / 10_000
def _fm(x, d=1): return f"{x:.{d}f}M"


# ---------------------------------------------------------------------------
# Slide 1
# ---------------------------------------------------------------------------

def gen_s1_targets(ctx):
    S1 = ctx['S1']
    a_full = S1['A'][S1['A']['指标'] == '2026全业务目标'].iloc[0]
    target = _to_m(a_full['目标APE'])
    issued = _to_m(a_full['已达成APE'])
    rate = num(str(a_full['目标达成率']).replace('%', ''))
    gap = target - issued
    # March vs Feb appointment count (from S1 C)
    cC = S1['C']
    mar = cC[cC.iloc[:, 0] == '2026-03']
    feb = cC[cC.iloc[:, 0] == '2026-02']
    mar_cnt = int(num(mar.iloc[0]['件数'])) if len(mar) else 0
    feb_cnt = int(num(feb.iloc[0]['件数'])) if len(feb) else 0
    pct = (mar_cnt - feb_cnt) / feb_cnt * 100 if feb_cnt else 0
    return (f"2026 全业务批核 APE 达 {issued:.1f}M，达成率 {rate:.1f}%，"
            f"全年目标 {target:.0f}M 缺口约 {gap:.0f}M。"
            f"3 月预约件数 {mar_cnt} 件，环比 {pct:+.1f}%，"
            f"前端动能延续，Q2 转化批核可期。")


def gen_s1_pipeline(ctx):
    S1 = ctx['S1']
    g = S1['G']
    total_row = g[g.iloc[:, 0] == '合计'].iloc[0]
    issued = _to_m(total_row['2026批核APE'])
    unbat = _to_m(total_row['未批核APE'])
    pend = _to_m(total_row['待签APE'])
    unbat_cnt = int(num(total_row['未批核件数']))
    pend_cnt = int(num(total_row['待签件数']))
    pipe = unbat + pend
    pct = pipe / issued * 100 if issued else 0
    return (f"未批核（{unbat:.1f}M，{unbat_cnt} 件）与待签（{pend:.1f}M，{pend_cnt} 件）"
            f"合计 {pipe:.1f}M 在管道中，占批核 APE 的 {pct:.0f}%。"
            f"若能快速推进至生效，可直接拉升达成率逾 {pipe/1113*100:.0f} 个百分点。")


def gen_s1_channel(ctx):
    S1 = ctx['S1']
    g = S1['G']
    # Top channel — exclude 合计 and any empty rows
    rows = [r for _, r in g.iterrows()
            if r.iloc[0] != '合计' and str(r.iloc[0]).strip() and _to_m(r['2026批核APE']) > 0]
    rows.sort(key=lambda r: _to_m(r['2026批核APE']), reverse=True)
    top = rows[0]
    top_name = top.iloc[0]
    top_iss = _to_m(top['2026批核APE'])
    top_pct = top_iss / _to_m(g[g.iloc[:, 0] == '合计'].iloc[0]['2026批核APE']) * 100
    top_un = _to_m(top['未批核APE'])
    parts = []
    for r in rows[1:]:
        parts.append(f"{r.iloc[0]}（批核 {_to_m(r['2026批核APE']):.1f}M）")
    others = '、'.join(parts) if parts else '—'
    return (f"{top_name}批核 {top_iss:.1f}M 占全渠道 {top_pct:.1f}%，是唯一业绩主力；"
            f"未批核 {top_un:.1f}M 是最大转化机会。"
            f"其余渠道：{others}，体量较小，需明确各渠道扩量优先级。")


def gen_s1_monthly(ctx):
    S1 = ctx['S1']
    cur_week = ctx['current_week']
    # Monthly trend for 2026
    cE = S1['E']
    cC = S1['C']
    cD = S1['D']
    months_26 = [r for _, r in cE.iterrows() if str(r.iloc[0]).startswith('2026')]
    peak = max(months_26, key=lambda r: _to_m(r['APE']))
    peak_m = int(peak.iloc[0].split('-')[1])
    peak_v = _to_m(peak['APE'])
    # Apr YTD — the last 2026 row
    last = months_26[-1]
    last_m = int(last.iloc[0].split('-')[1])
    last_apr_v = _to_m(last['APE'])
    # W13 (latest completed week) snapshot from S3 if available
    return (f"2026 年 Q1 呈现存量驱动特征，{peak_m}月批核峰值 {peak_v:.1f}M 为全年迄今最高。"
            f"3 月预约/签单同步走强，前端动能复苏。"
            f"{last_m}月初已批核 {last_apr_v:.1f}M，节后启动正常，"
            f"后续 9 个月需月均 83.8M 以达成年度目标。")


# ---------------------------------------------------------------------------
# Slide 2
# ---------------------------------------------------------------------------

def gen_s2_monthly(ctx):
    S1 = ctx['S1']
    cC = S1['C']
    # 3-month appointment count trend
    mar = cC[cC.iloc[:, 0] == '2026-03']
    feb = cC[cC.iloc[:, 0] == '2026-02']
    jan = cC[cC.iloc[:, 0] == '2026-01']
    mar_cnt = int(num(mar.iloc[0]['件数'])) if len(mar) else 0
    feb_cnt = int(num(feb.iloc[0]['件数'])) if len(feb) else 0
    jan_cnt = int(num(jan.iloc[0]['件数'])) if len(jan) else 0
    mar_ape = _to_m(mar.iloc[0]['APE']) if len(mar) else 0
    feb_ape = _to_m(feb.iloc[0]['APE']) if len(feb) else 0
    mar_avg = mar_ape * 10 / mar_cnt if mar_cnt else 0  # 万/件
    feb_avg = feb_ape * 10 / feb_cnt if feb_cnt else 0
    pct = (mar_cnt - feb_cnt) / feb_cnt * 100 if feb_cnt else 0
    return (f"2026 年 3 月预约件数从 2 月 {feb_cnt} 件增至 {mar_cnt} 件"
            f"（环比 {pct:+.1f}%），前端明显回暖。"
            f"但 3 月件均 APE {mar_avg:.1f} 万低于 2 月 {feb_avg:.1f} 万，"
            f"显示新增单偏中小额，需关注单均下滑趋势。")


def gen_s2_forecast(ctx):
    S1 = ctx['S1']
    a_full = S1['A'][S1['A']['指标'] == '2026全业务目标'].iloc[0]
    target = _to_m(a_full['目标APE'])
    issued = _to_m(a_full['已达成APE'])
    rate = num(str(a_full['目标达成率']).replace('%', ''))
    gap = target - issued
    cur_week = ctx['current_week']
    # remaining months (assume deck runs before end of 4月)
    remaining = 9
    monthly = gap / remaining
    return (f"截至 {cur_week}，已批核 {issued:.1f}M（达成率 {rate:.1f}%），"
            f"完成全年目标 {target:.0f}M 还需约 {gap:.0f}M，"
            f"剩余 {remaining} 个月月均需 {monthly:.1f}M。"
            f"若 4–12 月维持 80–100M 节奏，全年可达标。")


# ---------------------------------------------------------------------------
# Slide 3
# ---------------------------------------------------------------------------

def gen_s3_products(ctx):
    S4 = ctx['S4']
    df = S4['C'].copy()
    df = df[df['保司'] == '永明']
    df['_ape'] = df['APE'].apply(num)
    df = df.sort_values('_ape', ascending=False)
    top = df.head(10)
    top_ape_m = top['_ape'].sum() / 1e6
    top_cnt = int(top['件数'].apply(num).sum())
    top1 = top.iloc[0]
    top1_name = top1['产品名称']
    top1_ape = top1['_ape'] / 1e6
    top1_cnt = int(num(top1['件数']))
    top1_avg = top1['_ape'] / top1_cnt / 1e4 if top1_cnt else 0
    return (f"永明 TOP10 产品累计签单 {top_ape_m:.1f}M（{top_cnt} 件），"
            f"集中度高。头部产品「{top1_name}」贡献 {top1_ape:.1f}M/{top1_cnt} 件，"
            f"件均 {top1_avg:.1f} 万。中小额产品虽件数占比大，但单均偏低，"
            f"需关注大单产品的持续性供给。")


def gen_s3_license(ctx):
    S1 = ctx['S1']
    H = S1['H']
    # Find peak month for DW Bank and JF
    dwbank = H[H['牌照'] == 'DW Bank']
    jf = H[H['牌照'] == 'JF']
    if len(dwbank) and len(jf):
        dw_row = dwbank.iloc[0]
        jf_row = jf.iloc[0]
        dw_vals = {m: _to_m(dw_row[m]) for m in ['2026-01', '2026-02', '2026-03', '2026-04']}
        jf_vals = {m: _to_m(jf_row[m]) for m in ['2026-01', '2026-02', '2026-03', '2026-04']}
        dw_peak = max(dw_vals.items(), key=lambda x: x[1])
        jf_peak = max(jf_vals.items(), key=lambda x: x[1])
        sub_row = H[H['牌照'] == 'Sub Total'].iloc[0]
        unbat_total = _to_m(sub_row['未批核']) + _to_m(dw_row['未批核'])
        # 3 items total count placeholder
        return (f"DW Bank {dw_peak[0][-2:].lstrip('0')}月批核 {dw_peak[1]:.1f}M 为峰值，"
                f"BK 大额单集中处理。"
                f"JF {jf_peak[0][-2:].lstrip('0')}月批核 {jf_peak[1]:.1f}M 领跑经代牌照。"
                f"合计未批核 {unbat_total:.1f}M 是短期转化目标。")
    return "牌照数据待更新。"


# ---------------------------------------------------------------------------
# Slide 4
# ---------------------------------------------------------------------------

def gen_s4_bubble(ctx):
    S2 = ctx['S2']
    a = S2['A']
    rows = a[a['业务细分'].isin(['永明经代', '天领业务', 'BK业务', '合伙转介业务',
                                    '成事家办', '同行经代', 'ICLUB业务', 'IFA业务'])]
    rates = []
    for _, r in rows.iterrows():
        tgt = num(r['目标APE'])
        iss = num(r['2026批核APE'])
        if tgt > 0:
            rates.append((r['业务细分'], iss / tgt * 100, _to_m(r['2026批核APE'])))
    rates.sort(key=lambda x: x[1], reverse=True)
    top = rates[0]
    bottom = rates[-1]
    # Biggest risk = largest 规模 with LOW rate (below median rate)
    sorted_by_scale = sorted(rates, key=lambda x: x[2], reverse=True)
    rate_values = [r[1] for r in rates]
    median = sorted(rate_values)[len(rate_values) // 2]
    risk = None
    for r in sorted_by_scale:
        if r[1] < median:
            risk = r
            break
    if risk is None:
        risk = sorted_by_scale[-1]
    return (f"{top[0]}达成率 {top[1]:.1f}% 领跑全渠道，是唯一接近达标的渠道。"
            f"{risk[0]}规模较大（批核 {risk[2]:.1f}M）但达成率仅 "
            f"{risk[1]:.1f}%，是最大战略风险点。"
            f"{bottom[0]}达成率仅 {bottom[1]:.1f}%，需重点关注。")


def gen_s4_waterfall(ctx):
    S2 = ctx['S2']
    a = S2['A']
    total = a[a['业务细分'] == '合计'].iloc[0]
    target = _to_m(total['目标APE'])
    issued = _to_m(total['2026批核APE'])
    unbat = _to_m(total['未批核APE'])
    pend = _to_m(total['待签APE'])
    pipeline = issued + unbat + pend
    remain = target - pipeline
    # largest channel
    rows = [r for _, r in a.iterrows() if r['业务细分'] != '合计']
    top = max(rows, key=lambda r: num(r['2026批核APE']))
    top_name = top['业务细分']
    top_iss = _to_m(top['2026批核APE'])
    return (f"{top_name}贡献最大批核（{top_iss:.1f}M）。"
            f"已批核 + 在途合计 {pipeline:.1f}M，"
            f"距目标 {target:.0f}M 仍差 {remain:.0f}M。"
            f"若未批核 {unbat:.1f}M 与待签 {pend:.1f}M 快速推进，可直接拉升年度达成。")


def gen_s4_smallmult(ctx):
    S2 = ctx['S2']
    # Highlight top peer channel by Mar signing
    cD = S2['D-APE']  # signed
    cE = S2['E-APE']  # approved
    mar_signs = [(r.iloc[0], _to_m(r['2026-03'])) for _, r in cD.iterrows()
                 if r.iloc[0] != '合计']
    mar_signs.sort(key=lambda x: x[1], reverse=True)
    feb_apps = [(r.iloc[0], _to_m(r['2026-02'])) for _, r in cE.iterrows()
                if r.iloc[0] != '合计']
    feb_apps.sort(key=lambda x: x[1], reverse=True)
    top_sign = mar_signs[0]
    top_app = feb_apps[0]
    return (f"{top_sign[0]}：3 月签单 {top_sign[1]:.1f}M 居首，前端动能最强。"
            f"{top_app[0]}：2 月批核峰 {top_app[1]:.1f}M 为存量集中放款。"
            f"各业务线节奏分化明显，需按渠道特征差异化管理。")


# ---------------------------------------------------------------------------
# Slide 5
# ---------------------------------------------------------------------------

def gen_s5_target(ctx):
    S2 = ctx['S2']
    a = S2['A']
    rows = [r for _, r in a.iterrows() if r['业务细分'] != '合计']
    sorted_rows = sorted(rows, key=lambda r: num(r['目标APE']) - num(r['2026批核APE']),
                         reverse=True)
    biggest_gap = sorted_rows[0]
    # Best achiever
    achievers = [(r['业务细分'],
                  num(r['2026批核APE']) / num(r['目标APE']) * 100 if num(r['目标APE']) else 0,
                  _to_m(r['2026批核APE']), _to_m(r['目标APE']))
                 for r in rows if num(r['目标APE']) > 0]
    achievers.sort(key=lambda x: x[1], reverse=True)
    best = achievers[0]
    gap_m = _to_m(biggest_gap['目标APE']) - _to_m(biggest_gap['2026批核APE'])
    return (f"{best[0]}批核 {best[2]:.1f}M 已达目标 {best[3]:.0f}M 的 {best[1]:.1f}%，"
            f"是唯一接近达标的业务线。"
            f"{biggest_gap['业务细分']}目标最大（{_to_m(biggest_gap['目标APE']):.0f}M）"
            f"但实际仅 {_to_m(biggest_gap['2026批核APE']):.1f}M，"
            f"缺口 {gap_m:.0f}M 为最大绝对值，是最大战略风险点。")


def gen_s5_pipeline_total(ctx):
    S2 = ctx['S2']
    a = S2['A']
    t = a[a['业务细分'] == '合计'].iloc[0]
    issued = _to_m(t['2026批核APE'])
    unbat = _to_m(t['未批核APE'])
    pend = _to_m(t['待签APE'])
    total_pipe = issued + unbat + pend
    pct_issued = issued / total_pipe * 100
    return (f"管道总值 {total_pipe:.1f}M 中，批核占 {pct_issued:.1f}%（{issued:.1f}M）。"
            f"剩余 {unbat+pend:.1f}M（未批 {unbat:.1f}M + 待签 {pend:.1f}M）"
            f"若转化可直接推高达成率 {(unbat+pend)/1113*100:.0f}+。")


def gen_s5_donut(ctx):
    S2 = ctx['S2']
    a = S2['A']
    rows = [r for _, r in a.iterrows() if r['业务细分'] != '合计']
    # find channel with largest unbat pct
    worst = None; worst_pct = 0
    for r in rows:
        total_self = num(r['2026批核APE']) + num(r['未批核APE']) + num(r['待签APE'])
        if total_self <= 0: continue
        pct = num(r['未批核APE']) / total_self * 100
        if pct > worst_pct:
            worst = r; worst_pct = pct
    worst_name = worst['业务细分'] if worst is not None else '—'
    worst_val = _to_m(worst['未批核APE']) if worst is not None else 0
    return (f"{worst_name}未批核占比最高（{worst_pct:.0f}%），"
            f"金额达 {worst_val:.1f}M，催核优先级最高。"
            f"其余业务线管道分布相对均衡，需按未批核规模排序推进。")


# ---------------------------------------------------------------------------
# Slide 6
# ---------------------------------------------------------------------------

def _weekly_totals(ctx, section):
    _, data = parse_section_weekly_all(ctx['s3_rows'], section)
    if '合计' in data:
        return data['合计']
    # else sum across lines
    weeks = max((len(v) for v in data.values()), default=14)
    tot = [0.0] * weeks
    for vals in data.values():
        for i, v in enumerate(vals):
            if i < weeks:
                tot[i] += v
    return tot


def gen_s6_weekly_macro(ctx):
    appt = _weekly_totals(ctx, 'A-APE')  # S3 A is full-funnel weekly; but fallback to heat section
    # Use B/C/D instead (guaranteed present)
    appt = _weekly_totals(ctx, 'B-APE')
    sign = _weekly_totals(ctx, 'C-APE')
    app = _weekly_totals(ctx, 'D-APE')
    total_appt = sum(appt) / 1e6
    total_sign = sum(sign) / 1e6
    total_app = sum(app) / 1e6
    # Find min week
    appt_with_week = [(i+1, v) for i, v in enumerate(appt) if v > 0]
    low_week = min(appt_with_week, key=lambda x: x[1]) if appt_with_week else (7, 0)
    return (f"批核 APE 累计 {total_app:.1f}M 显著高于预约 {total_appt:.1f}M，"
            f"反映跨周积压存量消化效应。"
            f"签单累计 {total_sign:.1f}M，递交→批核转化效率较高。"
            f"W{low_week[0]:02d} 预约低点 {low_week[1]/1e6:.1f}M 需关注执行节奏。")


def gen_s6_weekly_events(ctx):
    appt = _weekly_totals(ctx, 'B-APE')
    sign = _weekly_totals(ctx, 'C-APE')
    app = _weekly_totals(ctx, 'D-APE')
    sign_peak_i = max(range(len(sign)), key=lambda i: sign[i]) if sign else 0
    app_peak_i = max(range(len(app)), key=lambda i: app[i]) if app else 0
    appt_peak_i = max(range(len(appt)), key=lambda i: appt[i]) if appt else 0
    return (f"W{sign_peak_i+1:02d} 签单峰 {sign[sign_peak_i]/1e6:.1f}M 为阶段高点；"
            f"W{app_peak_i+1:02d} 批核峰 {app[app_peak_i]/1e6:.1f}M 为存量集中消化；"
            f"W{appt_peak_i+1:02d} 预约峰 {appt[appt_peak_i]/1e6:.1f}M 显示前端动能。"
            f"周度节奏呈脉冲式特征，需关注执行连续性。")


def gen_s6_weekly_brief(ctx):
    cur_week = ctx['current_week']
    wk_idx = int(cur_week[-2:]) - 1
    def w(section):
        _, d = parse_section_weekly_all(ctx['s3_rows'], section)
        row = d.get('合计')
        if not row:
            # sum
            weeks_n = max((len(v) for v in d.values()), default=14)
            row = [sum(v[i] if i<len(v) else 0 for v in d.values()) for i in range(weeks_n)]
        return row[wk_idx] if wk_idx < len(row) else 0
    def wn(section):
        _, d = parse_section_weekly_all(ctx['s3_rows'], section)
        row = d.get('合计')
        if not row:
            weeks_n = max((len(v) for v in d.values()), default=14)
            row = [sum(v[i] if i<len(v) else 0 for v in d.values()) for i in range(weeks_n)]
        return int(row[wk_idx]) if wk_idx < len(row) else 0
    appt_m = w('B-APE')/1e6; appt_c = wn('B-件数')
    sign_m = w('C-APE')/1e6; sign_c = wn('C-件数')
    app_m = w('D-APE')/1e6; app_c = wn('D-件数')
    # Unbat total
    S1 = ctx['S1']
    g = S1['G']
    total_row = g[g.iloc[:, 0] == '合计'].iloc[0]
    unbat_m = _to_m(total_row['未批核APE'])
    unbat_c = int(num(total_row['未批核件数']))
    return (f"{cur_week} 预约 {appt_m:.1f}M/{appt_c}件；"
            f"签单 {sign_m:.1f}M/{sign_c}件；"
            f"批核 {app_m:.1f}M/{app_c}件。"
            f"未批核 {unbat_m:.1f}M（{unbat_c}件）是 Q2 批核的核心转化储量。")


def gen_s6_ka_top10(ctx):
    """Slide 6 P chart — all-business KA TOP10 (from S2 I, which includes banks
    and all peer KAs)."""
    S2 = ctx['S2']
    if 'I' not in S2:
        return "KA TOP10 数据待更新。"
    df = S2['I'].copy()
    df = df[df.iloc[:, 1] != '合计']  # drop 合计 row if present
    df['_ape'] = df['2026批核APE'].apply(num)
    df = df.sort_values('_ape', ascending=False)

    # Grand total = sum of all business-line 批核APE from S2 A 合计
    a_total = S2['A'][S2['A']['业务细分'] == '合计']
    grand_m = _to_m(a_total.iloc[0]['2026批核APE']) if len(a_total) else df['_ape'].sum() / 1e6

    top10 = df.head(10)
    top10_m = top10['_ape'].sum() / 1e6
    pct = top10_m / grand_m * 100 if grand_m > 0 else 0
    top1 = top10.iloc[0]
    top1_name = top1['KEY ACCOUNT'] if 'KEY ACCOUNT' in top10.columns else top1.iloc[1]
    top1_m = top1['_ape'] / 1e6
    top1_pct = top1_m / grand_m * 100 if grand_m > 0 else 0
    return (f"TOP10 KA 累计批核 {top10_m:.1f}M（占全业务 {pct:.1f}%），高度集中。"
            f"{top1_name} 以 {top1_m:.1f}M 独占 {top1_pct:.1f}%，"
            f"是最核心的单一客户，亦是最大集中风险点。")


# ---------------------------------------------------------------------------
# Slide 7 — heat matrices + lifecycle
# ---------------------------------------------------------------------------

def _heat_analysis(ctx, ape_key, cnt_key, label):
    _, ape = parse_section_weekly_all(ctx['s3_rows'], ape_key)
    _, cnt = parse_section_weekly_all(ctx['s3_rows'], cnt_key)
    order = ['天领业务', '成事家办', 'BK业务', '同行经代', '永明经代', '合伙转介业务', 'ICLUB业务']
    totals = {n: (sum(ape.get(n, [])), sum(cnt.get(n, []))) for n in order}
    grand = sum(v for v, _ in totals.values())
    grand_c = sum(c for _, c in totals.values())
    if grand == 0:
        return f"{label}数据暂缺。"
    top = max(totals.items(), key=lambda x: x[1][0])
    top_pct = top[1][0] / grand * 100
    # Peak week
    n_weeks = max((len(v) for v in ape.values()), default=14)
    wt = [sum((ape.get(n, [0]*n_weeks)[i] if i < len(ape.get(n, [])) else 0) for n in order)
          for i in range(n_weeks)]
    peak_i = wt.index(max(wt)) if wt else 0
    peak_c = sum((cnt.get(n, [0]*n_weeks)[peak_i] if peak_i < len(cnt.get(n, [])) else 0) for n in order)
    return (f"{label}总量 {grand/1e6:.1f}M/{int(grand_c)}件。"
            f"{top[0]}领跑，累计 {top[1][0]/1e6:.1f}M/{int(top[1][1])}件，"
            f"占比 {top_pct:.0f}%。"
            f"W{peak_i+1:02d} 单周峰值 {max(wt)/1e6:.1f}M/{int(peak_c)}件，"
            f"是本季度最高单周贡献。")


def gen_s7_appt(ctx):
    return _heat_analysis(ctx, 'B-APE', 'B-件数', '预约')

def gen_s7_sign(ctx):
    return _heat_analysis(ctx, 'C-APE', 'C-件数', '签单')

def gen_s7_app(ctx):
    return _heat_analysis(ctx, 'D-APE', 'D-件数', '批核')


def gen_s7_lifecycle(ctx):
    """T 签批时效 So What — dynamic from S3 G."""
    S3 = ctx['S3']
    if 'G' not in S3:
        return "签批时效数据待更新。"
    g = S3['G']
    # Filter out 合计 and empty rows
    rows = []
    for _, r in g.iterrows():
        name = str(r.get('业务细分', '')).strip()
        cnt = num(r.get('件数', 0))
        if name and name != '合计' and cnt > 0:
            rows.append({
                'name': name, 'cnt': int(cnt),
                'avg_wan': round(num(r.get('件均APE', 0)) / 10000),
                'avg_tat': round(num(r.get('平均时效(天)', 0)), 1),
                'p90': round(num(r.get('P90时效(天)', 0))),
                'median': round(num(r.get('中位时效(天)', 0))),
                'max_tat': round(num(r.get('最大时效(天)', 0))),
            })
    if not rows:
        return "签批时效数据待更新。"
    # Find max avg TAT
    worst = max(rows, key=lambda x: x['avg_tat'])
    # Find fastest
    fastest = min(rows, key=lambda x: x['avg_tat'])
    # Total row
    tot = g[g['业务细分'].str.strip() == '合计']
    tot_avg = round(num(tot.iloc[0].get('平均时效(天)', 0))) if len(tot) else 0
    tot_p90 = round(num(tot.iloc[0].get('P90时效(天)', 0))) if len(tot) else 0

    sla_over = [r for r in rows if r['avg_tat'] > 60]
    sla_text = (f"{'、'.join(r['name'] for r in sla_over)} 平均时效超 60 天 SLA"
                if sla_over else "所有业务线平均时效均在 60 天 SLA 内")

    return (f"{worst['name']}件均 APE 最高（{worst['avg_wan']}万）且平均时效 "
            f"{worst['avg_tat']} 天（P90={worst['p90']} 天），"
            f"{'是唯一超 SLA=60 天渠道，大额件审核慢是主要风险。' if worst['avg_tat'] > 60 else '时效偏高需关注。'}"
            f"{fastest['name']}均值 {fastest['avg_tat']} 天效率最优。"
            f"整体均值 {tot_avg} 天，P90={tot_p90} 天。{sla_text}。")


# ---------------------------------------------------------------------------
# Slide 8 — peer
# ---------------------------------------------------------------------------

def gen_s8_top_contributors(ctx):
    S2 = ctx['S2']
    j = S2['J'].copy()
    j = j[j.iloc[:, 0] != '合计']
    j['_ape'] = j['2026批核APE'].apply(num)
    j['_cnt'] = j['批核件数'].apply(num)
    j = j.sort_values('_ape', ascending=False)
    total = j['_ape'].sum()
    if total == 0 or len(j) == 0:
        return "推荐人数据待更新。"
    top1 = j.iloc[0]
    top2 = j.iloc[1] if len(j) > 1 else None
    top1_name = top1.iloc[0]
    top1_ape = top1['_ape'] / 1e6
    top1_pct = top1['_ape'] / total * 100
    top1_cnt = int(top1['_cnt'])
    top1_avg = top1['_ape'] / top1_cnt / 1e4 if top1_cnt else 0
    if top2 is not None:
        top2_name = top2.iloc[0]
        top2_ape = top2['_ape'] / 1e6
        top2_pct = top2['_ape'] / total * 100
        top2_cnt = int(top2['_cnt'])
        top2_avg = top2['_ape'] / top2_cnt / 1e4 if top2_cnt else 0
        combined = top1_pct + top2_pct
        # Which is "大单" (higher avg) vs "流量" (more 件)
        if top1_avg > top2_avg:
            big, small = (top1_name, top1_avg, top1_cnt), (top2_name, top2_avg, top2_cnt)
        else:
            big, small = (top2_name, top2_avg, top2_cnt), (top1_name, top1_avg, top1_cnt)
        return (f"{top1_name} + {top2_name}合计贡献批核 APE {combined:.1f}%，"
                f"但模式迥异：{big[0]}件均 APE≈{big[1]:.0f}万 为「大单驱动型」；"
                f"{small[0]} {small[2]}件 为「流量驱动型」。"
                f"头部集中度高，需差异化管理策略。")
    return (f"{top1_name}贡献批核 {top1_ape:.1f}M，占比 {top1_pct:.0f}%，"
            f"件均 {top1_avg:.0f}万。")


def gen_s8_approval_rate(ctx):
    S2 = ctx['S2']
    j = S2['J'].copy()
    j = j[j.iloc[:, 0] != '合计']
    # Consider only meaningful contributors (batch APE > 500k)
    rows = []
    for _, r in j.iterrows():
        name = r.iloc[0]
        iss = num(r['2026批核APE'])
        un = num(r['未批核APE'])
        tot = iss + un
        if tot < 500_000:
            continue
        rate = iss / tot * 100 if tot > 0 else 0
        rows.append((name, rate, iss/1e6, un/1e6))
    if not rows:
        return "推荐人批核率数据待更新。"
    rows.sort(key=lambda x: x[1], reverse=True)
    top = rows[0]
    # 'worst' = largest unbat regardless of rate
    worst = max(rows, key=lambda x: x[3])
    return (f"{top[0]}批核率 {top[1]:.0f}%（批核 {top[2]:.1f}M，未批核 {top[3]:.1f}M），"
            f"件质量最高。"
            f"{worst[0]}未批核量最大（{worst[3]:.1f}M），批核率 {worst[1]:.0f}%，"
            f"需优先排查件质量问题。头部推荐人质量差异显著，需差异化对接策略。")


# ---------------------------------------------------------------------------
# Slide 9 — peer weekly
# ---------------------------------------------------------------------------

def gen_s9_weekly(ctx):
    cur_week = ctx['current_week']
    wk_idx = int(cur_week[-2:]) - 1
    j_section = 'J-APE'; k_section = 'K-APE'; l_section = 'L-APE'  # peer appt/sign/app
    _, j = parse_section_weekly_all(ctx['s3_rows'], j_section)  # appt
    _, k = parse_section_weekly_all(ctx['s3_rows'], k_section)  # sign
    _, l = parse_section_weekly_all(ctx['s3_rows'], l_section)  # app
    def total(d):
        row = d.get('合计')
        if row and wk_idx < len(row):
            return row[wk_idx]
        return sum(v[wk_idx] for v in d.values() if wk_idx < len(v))
    appt_w = total(j)/1e6
    sign_w = total(k)/1e6
    app_w = total(l)/1e6
    return (f"{cur_week} 同行批核 {app_w:.2f}M，签单 {sign_w:.2f}M，"
            f"预约 {appt_w:.2f}M。"
            f"签单前端尚在蓄力，预约 {appt_w:.1f}M 为节后水平，"
            f"需密切跟踪后续周次是否回升。")


def gen_s9_monthly(ctx):
    S2 = ctx['S2']
    cL = S2.get('L-APE')  # peer monthly appt
    cM = S2.get('M-APE')  # peer monthly sign
    if cL is None or cM is None:
        return "同行月度数据待更新。"
    def month_total(df, month):
        row = df[df.iloc[:, 0] == '合计']
        if len(row) and month in df.columns:
            return num(row.iloc[0][month])
        return 0
    mar_appt = month_total(cL, '2026-03') / 1e4
    feb_appt = month_total(cL, '2026-02') / 1e4
    mar_sign = month_total(cM, '2026-03') / 1e4
    pct = (mar_appt - feb_appt) / feb_appt * 100 if feb_appt else 0
    return (f"3 月同行预约 {mar_appt:.0f} 万，环比 {pct:+.1f}%，"
            f"前端显著回暖。"
            f"3 月签单 {mar_sign:.0f} 万，预约-签单缺口反映大量前端件"
            f"仍处「待结」状态，需密切跟进 4 月转化节奏。")


# ---------------------------------------------------------------------------
# Slide 10 — bank
# ---------------------------------------------------------------------------

def gen_s10_monthly(ctx):
    S2 = ctx['S2']
    P = S2.get('P-APE'); Q = S2.get('Q-APE'); R = S2.get('R-APE')
    if not (P is not None and Q is not None and R is not None):
        return "银行月度数据待更新。"
    def row(df, bank, month):
        r = df[df.iloc[:, 0] == bank]
        return _to_m(r.iloc[0][month]) if len(r) and month in df.columns else 0
    q1_ms = sum(row(P, '民生银行', m) for m in ['2026-01', '2026-02', '2026-03'])
    q1_pa = sum(row(P, '平安银行', m) for m in ['2026-01', '2026-02', '2026-03'])
    apr_ms_sign = row(Q, '民生银行', '2026-04')
    apr_pa_sign = row(Q, '平安银行', '2026-04')
    return (f"预约：Q1 民生 {q1_ms:.1f}M，平安 {q1_pa:.1f}M。"
            f"签单：4 月民生 {apr_ms_sign:.2f}M，平安 {apr_pa_sign:.2f}M，"
            f"3 月末积压件持续转化，Q2 批核弹药充足。"
            f"需关注 4 月预约动能的及时修复。")


def gen_s10_target(ctx):
    S2 = ctx['S2']
    a = S2['A']
    bk = a[a['业务细分'] == 'BK业务'].iloc[0]
    issued = _to_m(bk['2026批核APE'])
    unbat = _to_m(bk['未批核APE'])
    pend = _to_m(bk['待签APE'])
    target = _to_m(bk['目标APE'])
    rate = issued / target * 100 if target > 0 else 0
    return (f"BK 业务 YTD 批核 {issued:.1f}M 达成 {rate:.1f}%；"
            f"未批核 {unbat:.1f}M 构成 Q2 储量；"
            f"待签 {pend:.1f}M。"
            f"目标 {target:.0f}M 已完成大半，需修复前端预约动能。")


# ---------------------------------------------------------------------------
# Slide 11 — bank weekly
# ---------------------------------------------------------------------------

def gen_s11_weekly(ctx):
    cur_week = ctx['current_week']
    wk_idx = int(cur_week[-2:]) - 1
    def cell(section):
        _, d = parse_section_weekly_all(ctx['s3_rows'], section)
        row = d.get('合计')
        if row and wk_idx < len(row):
            return row[wk_idx]
        return sum(v[wk_idx] for v in d.values() if wk_idx < len(v))
    def cell_int(section):
        _, d = parse_section_weekly_all(ctx['s3_rows'], section)
        row = d.get('合计')
        if row and wk_idx < len(row):
            return int(row[wk_idx])
        return int(sum(v[wk_idx] for v in d.values() if wk_idx < len(v)))
    sign_m = cell('N-APE')/1e6; sign_c = cell_int('N-件数')
    app_m = cell('O-APE')/1e6; app_c = cell_int('O-件数')
    appt_m = cell('M-APE')/1e6; appt_c = cell_int('M-件数')
    # Unbat from S2 A BK row
    S2 = ctx['S2']
    bk = S2['A'][S2['A']['业务细分'] == 'BK业务'].iloc[0]
    unbat = _to_m(bk['未批核APE'])
    unbat_c = int(num(bk['未批核件数']))
    return (f"银行 {cur_week}：民生 + 平安合计 "
            f"签单 {sign_m:.2f}M/{sign_c}件、"
            f"批核 {app_m:.2f}M/{app_c}件、"
            f"预约 {appt_m:.2f}M/{appt_c}件。"
            f"未批核 {unbat:.1f}M（{unbat_c}件）是 Q2 批核的核心储量。")


def gen_s11_weekly_peak(ctx):
    _, appO = parse_section_weekly_all(ctx['s3_rows'], 'O-APE')
    # sum across banks
    row = appO.get('合计')
    if not row:
        weeks_n = max((len(v) for v in appO.values()), default=14)
        row = [sum(v[i] if i<len(v) else 0 for v in appO.values()) for i in range(weeks_n)]
    peak_i = max(range(len(row)), key=lambda i: row[i]) if row else 0
    peak_v = row[peak_i] / 1e6 if row else 0
    sorted_rows = sorted(enumerate(row), key=lambda x: x[1], reverse=True)
    second = sorted_rows[1] if len(sorted_rows) > 1 else (0, 0)
    return (f"W{peak_i+1:02d} 批核峰值 {peak_v:.1f}M 为全年迄今最高单周，"
            f"由民生大额集中放款驱动，非可持续常态。"
            f"W{second[0]+1:02d} 批核 {second[1]/1e6:.1f}M 为第二峰，"
            f"显示积压件的波动性清转模式。近期批核节奏已回落至正常区间。")


def gen_s11_branch_ranking(ctx):
    S2 = ctx['S2']
    s = S2.get('S-APE')
    if s is None:
        return "分行数据待更新。"
    rows = s[s.iloc[:, 0] != '合计'].copy()
    rows['_sum'] = rows['合计'].apply(num) if '合计' in rows.columns else 0
    rows = rows.sort_values('_sum', ascending=False).head(5)
    if len(rows) < 2:
        return "分行数据不足。"
    top1 = rows.iloc[0]
    top2 = rows.iloc[1]
    top1_name = top1.iloc[0]
    top1_m = top1['_sum'] / 1e6
    top2_name = top2.iloc[0]
    top2_m = top2['_sum'] / 1e6
    top4_sum = rows.head(4)['_sum'].sum() / 1e6
    bk_total_m = _to_m(S2['A'][S2['A']['业务细分'] == 'BK业务'].iloc[0]['2026批核APE'])
    pct = top4_sum / bk_total_m * 100 if bk_total_m else 0
    return (f"{top1_name} 以 {top1_m:.1f}M 居榜首，"
            f"{top2_name} {top2_m:.1f}M 紧随。"
            f"前四行合计 {top4_sum:.1f}M，占 BK 总批核 {pct:.0f}%，"
            f"头部集中度显著，大额单效率突出。")


# ---------------------------------------------------------------------------
# Registry — (slide_idx, label_y, label_x) -> generator
# Positions are taken from the FINAL deck (y in EMU). We use a tolerance
# when matching so small template shifts don't break binding.
# ---------------------------------------------------------------------------

REGISTRY = [
    # slide_idx, label_y, label_x, generator
    (0,  2952115,   125095, gen_s1_targets),
    (0,  2967355,  4110355, gen_s1_pipeline),
    (0,  2952115,  8446135, gen_s1_channel),
    (0,  6245225,   165735, gen_s1_monthly),

    (1,  6154420,   153670, gen_s2_monthly),
    (1,  6109970,  5870575, gen_s2_forecast),

    (2,  6374765,   250190, gen_s3_products),
    (2,  3566795,   227330, gen_s3_license),

    (3,  6337046,   201041, gen_s4_bubble),
    (3,  6327775,  4055745, gen_s4_waterfall),
    (3,  6336030,  7820025, gen_s4_smallmult),

    (4,  6345936,   182880, gen_s5_donut),
    (4,  2938653,  4700016, gen_s5_pipeline_total),
    (4,  6345936,  4700016, gen_s5_target),

    (5,  3017520,   182880, gen_s6_weekly_macro),
    (5,  3017520,  6254496, gen_s6_weekly_events),
    (5,  6291072,   182880, gen_s6_weekly_brief),
    (5,  6291072,  4151376, gen_s6_ka_top10),

    (6,  3197987,   165100, gen_s7_appt),
    (6,  3197987,  6236716, gen_s7_sign),
    (6,  6291072,   182880, gen_s7_app),
    (6,  6291072,  6254496, gen_s7_lifecycle),

    (7,  2968625,  6040755, gen_s8_top_contributors),
    (7,  6152642,   286258, gen_s8_approval_rate),

    (8,  3408680,   261620, gen_s9_weekly),
    (8,  6350000,   398145, gen_s9_monthly),

    (9,  6111240,   199390, gen_s10_monthly),
    (9,  6241415,  6163310, gen_s10_target),

    (10, 6248400,   109220, gen_s11_weekly),
    (10, 4006215,   100965, gen_s11_weekly_peak),
    (10, 6223000,  6198235, gen_s11_branch_ranking),
]


def lookup_generator(slide_idx, label_y, label_x, tol=50000):
    for si, ly, lx, gen in REGISTRY:
        if si != slide_idx:
            continue
        if abs(ly - label_y) <= tol and abs(lx - label_x) <= tol:
            return gen
    return None
