"""
chart_updates.py — build CategoryChartData for every chart in the PPT.

Each function returns a CategoryChartData object that python-pptx can feed back
into the existing chart via `chart.replace_data(...)`. This preserves all
formatting (colors, legend, axis style) and keeps the chart editable by the
user (Edit Data in Excel still works).
"""
from pptx.chart.data import CategoryChartData
from data_loader import num


def _row(df, col_match_value, col_name):
    """Return first row where any column matches col_match_value."""
    first_col = df.columns[0]
    sub = df[df[first_col] == col_match_value]
    if len(sub) == 0:
        return 0.0
    return num(sub.iloc[0][col_name])


def _total_row(df):
    first_col = df.columns[0]
    sub = df[df[first_col] == "合计"]
    return sub.iloc[0] if len(sub) else None


def to_m(v):
    return round(num(v) / 1_000_000, 2)


def to_w(v):
    """Convert raw APE to 万 (10,000)."""
    return round(num(v) / 10_000, 2)


# --------------------------------------------------------------------------
# Slide 1
# --------------------------------------------------------------------------

def slide1_chart_business_type(S1):
    """C. 业务类型业绩 — 分组堆叠柱: 经代/代理人/KA × 批核/未批核/待签"""
    g = S1["G"]
    cats = ["经代业务", "代理人业务", "KA 业务"]
    mapping = {"经代业务": "经代业务", "代理人业务": "代理人业务", "KA 业务": "KA业务"}
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("批核 APE",
                  [to_m(_row(g, mapping[c], "2026批核APE")) for c in cats])
    cd.add_series("未批核 APE",
                  [to_m(_row(g, mapping[c], "未批核APE")) for c in cats])
    cd.add_series("待签 APE",
                  [to_m(_row(g, mapping[c], "待签APE")) for c in cats])
    return cd


def slide1_chart_monthly_trend(S1):
    """D. 预约/签单/批核月度趋势 (2025-01 .. 2026-04)"""
    cC, cD, cE = S1["C"], S1["D"], S1["E"]
    months = [m for m in cC.iloc[:, 0] if m and m.startswith("202")]
    # Build label like '25-Jan'
    def label(ym):
        y, m = ym.split("-")
        mn = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        return f"{y[-2:]}-{mn[int(m)-1]}"
    cats = [label(m) for m in months]

    def col_for(df, ym, col):
        row = df[df.iloc[:, 0] == ym]
        return to_m(row.iloc[0][col]) if len(row) else 0.0

    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("预约 APE(M)", [col_for(cC, m, "APE") for m in months])
    cd.add_series("签单 APE(M)", [col_for(cD, m, "APE") for m in months])
    cd.add_series("批核 APE(M)", [col_for(cE, m, "APE") for m in months])
    return cd


# --------------------------------------------------------------------------
# Slide 2 — single-series 2026 monthly bars
# --------------------------------------------------------------------------

def _slide2_bars(S1, block_letter, series_name):
    df = S1[block_letter]
    df26 = df[df.iloc[:, 0].astype(str).str.startswith("2026")]
    cats = ["1月", "2月", "3月", "4月"]
    vals = [0.0] * 4
    for _, r in df26.iterrows():
        m_idx = int(r.iloc[0].split("-")[1]) - 1
        if 0 <= m_idx < 4:
            vals[m_idx] = to_m(r["APE"])
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series(series_name, vals)
    return cd, vals


def slide2_appointment(S1):
    cd, _ = _slide2_bars(S1, "C", "预约 APE(M)")
    return cd


def slide2_signed(S1):
    cd, _ = _slide2_bars(S1, "D", "签单 APE(M)")
    return cd


def slide2_approved(S1):
    cd, _ = _slide2_bars(S1, "E", "批核 APE(M)")
    return cd


def slide2_forecast_chart(S1):
    """F. 实际批核 + 预测区间 (12 months, 2026).

    Keep the existing forecast values (5-12月) -- they are manually set by the
    team. We update columns 1-4 with actuals. Preserved forecast defaults are
    the values that were in the original deck.
    """
    cE = S1["E"]
    actuals = [0.0] * 12
    for _, r in cE.iterrows():
        ym = str(r.iloc[0])
        if ym.startswith("2026-"):
            m_idx = int(ym.split("-")[1]) - 1
            if 0 <= m_idx < 12:
                actuals[m_idx] = to_m(r["APE"])
    # Forecast = original deck values for May..Dec
    forecast = [None, None, None, None, 80.0, 88.0, 95.0, 100.0, 100.0, 100.0, 100.0, 96.0]
    cd = CategoryChartData()
    cd.categories = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]
    cd.add_series("实际批核 APE(M)",
                  [v if i < 4 else None for i, v in enumerate(actuals)])
    cd.add_series("预测 APE(M)", forecast)
    return cd


# --------------------------------------------------------------------------
# Slide 3 — Sunlife monthly trend
# --------------------------------------------------------------------------

def slide3_sunlife_trend(S2):
    """H. 永明月度预约/签单/批核 APE 趋势 (26-Jan..26-Apr)."""
    fA, gA, hA = S2["F-APE"], S2["G-APE"], S2["H-APE"]
    cats = ["26-Jan", "26-Feb", "26-Mar", "26-Apr"]
    months = ["2026-01", "2026-02", "2026-03", "2026-04"]

    def total(df, col):
        row = df[df.iloc[:, 0] == "合计"]
        return to_m(row.iloc[0][col]) if len(row) else 0.0

    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("预约 APE(M)", [total(fA, m) for m in months])
    cd.add_series("签单 APE(M)", [total(gA, m) for m in months])
    cd.add_series("批核 APE(M)", [total(hA, m) for m in months])
    return cd


# --------------------------------------------------------------------------
# Slide 4 — small-multiples (7 charts, one per business channel, Jan..Apr)
# --------------------------------------------------------------------------

def slide4_channel_trend(S2, channel_name):
    cA, cD, cE = S2["C-APE"], S2["D-APE"], S2["E-APE"]
    months = ["2026-01", "2026-02", "2026-03", "2026-04"]

    def val(df, col):
        row = df[df.iloc[:, 0] == channel_name]
        return to_m(row.iloc[0][col]) if len(row) else 0.0

    cd = CategoryChartData()
    cd.categories = ["Jan", "Feb", "Mar", "Apr"]
    cd.add_series("预约", [val(cA, m) for m in months])
    cd.add_series("签单", [val(cD, m) for m in months])
    cd.add_series("批核", [val(cE, m) for m in months])
    return cd


# --------------------------------------------------------------------------
# Slide 5
# --------------------------------------------------------------------------

def slide5_donut(S2):
    """K. 甜甜圈: 已批核 / 未批核 / 待签 (全业务合计)."""
    total = _total_row(S2["A"])
    cd = CategoryChartData()
    cd.categories = ["已批核", "未批核", "待签"]
    cd.add_series("APE构成",
                  [to_m(total["2026批核APE"]),
                   to_m(total["未批核APE"]),
                   to_m(total["待签APE"])])
    return cd


def slide5_target_vs_actual(S2):
    """L. 目标 vs 已批核/未批核/待签 APE — 各业务线对比."""
    df = S2["A"]
    df = df[df["业务细分"].isin([
        "永明经代", "天领业务", "BK业务", "合伙转介业务",
        "成事家办", "同行经代", "ICLUB业务", "IFA业务"
    ])]
    # Map display names used in the chart (trim 业务 suffix on some)
    name_map = {
        "永明经代": "永明经代", "天领业务": "天领业务", "BK业务": "BK业务",
        "合伙转介业务": "合伙转介", "成事家办": "成事家办", "同行经代": "同行经代",
        "ICLUB业务": "ICLUB", "IFA业务": "IFA业务",
    }
    order = ["永明经代", "天领业务", "BK业务", "合伙转介业务",
             "成事家办", "同行经代", "ICLUB业务", "IFA业务"]
    cats = [name_map[k] for k in order]
    issued, unbat, pend, gap = [], [], [], []
    for k in order:
        row = df[df["业务细分"] == k].iloc[0]
        i = to_m(row["2026批核APE"])
        u = to_m(row["未批核APE"])
        p = to_m(row["待签APE"])
        t = to_m(row["目标APE"])
        issued.append(i); unbat.append(u); pend.append(p)
        gap.append(round(t - (i + u + p), 2))
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("已批核 APE(M)", issued)
    cd.add_series("未批核 APE(M)", unbat)
    cd.add_series("待签 APE(M)",   pend)
    cd.add_series("目标缺口 APE(M)", gap)
    return cd


# --------------------------------------------------------------------------
# Slide 6 — weekly 4-line trend (W01..W14)
# --------------------------------------------------------------------------

def slide6_weekly_trend(S3):
    a = S3["A-APE"]
    # weekly columns W01..W14
    week_cols = [c for c in a.columns if c.startswith("2026W")]
    cats = [c.replace("2026", "") for c in week_cols]  # W01..W14
    cd = CategoryChartData()
    cd.categories = cats
    for stage in ["预约", "签单", "递交", "批核"]:
        row = a[a.iloc[:, 0] == stage].iloc[0]
        cd.add_series(stage, [to_m(row[c]) for c in week_cols])
    return cd


# --------------------------------------------------------------------------
# Slide 8
# --------------------------------------------------------------------------

def slide8_referrer(S2):
    """U. 同行推荐人分析. Units: 万 (per original chart)."""
    j = S2["J"]
    j = j[j.iloc[:, 0] != "合计"]
    # sort by 2026批核APE desc
    j = j.copy()
    j["_sort"] = j["2026批核APE"].apply(num)
    j = j.sort_values("_sort", ascending=False)
    cats = j.iloc[:, 0].tolist()
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("批核APE(万)",   [to_w(v) for v in j["2026批核APE"]])
    cd.add_series("未批核APE(万)", [to_w(v) for v in j["未批核APE"]])
    cd.add_series("待签APE(万)",   [to_w(v) for v in j["待签APE"]])
    return cd


def slide8_top10_ka(S2):
    """V. TOP10 同行 KA (by 批核APE desc)."""
    k = S2["K"]
    k = k[k.iloc[:, 0] != "合计"].copy()
    k["_sort"] = k["2026批核APE"].apply(num)
    k = k.sort_values("_sort", ascending=False).head(10)
    cats = k.iloc[:, 0].tolist()
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("批核APE(万)",   [to_w(v) for v in k["2026批核APE"]])
    cd.add_series("未批核APE(万)", [to_w(v) for v in k["未批核APE"]])
    cd.add_series("待签APE(万)",   [to_w(v) for v in k["待签APE"]])
    return cd


# --------------------------------------------------------------------------
# Slide 9 — peer weekly trend
# --------------------------------------------------------------------------

def slide9_peer_weekly(S3):
    """X. 同行 W01..W14 预约/签单/批核. Sum 合计 rows of J/K/L-APE."""
    j, k, l = S3["J-APE"], S3["K-APE"], S3["L-APE"]
    week_cols = [c for c in j.columns if c.startswith("2026W")]
    cats = [c.replace("2026", "") for c in week_cols]

    def totals(df):
        row = df[df.iloc[:, 0] == "合计"].iloc[0]
        return [to_m(row[c]) for c in week_cols]

    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("同行预约(M)", totals(j))
    cd.add_series("同行签单(M)", totals(k))
    cd.add_series("同行批核(M)", totals(l))
    return cd


# --------------------------------------------------------------------------
# Slide 10
# --------------------------------------------------------------------------

def _slide10_bank_monthly(df):
    # FIXED: read all available months dynamically so embedded xlsx is correct
    _MO_ZH = {1:"1月",2:"2月",3:"3月",4:"4月",5:"5月",6:"6月",
              7:"7月",8:"8月",9:"9月",10:"10月",11:"11月",12:"12月"}
    months = sorted([c for c in df.columns if c.startswith("2026-")])
    cats = [_MO_ZH.get(int(c[5:7]), c) for c in months]

    def val(bank, month):
        row = df[df.iloc[:, 0] == bank]
        return to_m(row.iloc[0][month]) if len(row) else 0.0

    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("民生银行", [val("民生银行", m) for m in months])
    cd.add_series("平安银行", [val("平安银行", m) for m in months])
    return cd


def slide10_bk_appointment(S2):   return _slide10_bank_monthly(S2["P-APE"])
def slide10_bk_signed(S2):        return _slide10_bank_monthly(S2["Q-APE"])
def slide10_bk_approved(S2):      return _slide10_bank_monthly(S2["R-APE"])


def slide10_bk_ka(S2):
    """AA. 银行 KA 堆叠 (民生/平安 × 批核/未批核/待签)."""
    o = S2["O"]
    cats = ["民生银行", "平安银行"]
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("批核APE(M)",   [to_m(_row(o, c, "2026批核APE")) for c in cats])
    cd.add_series("未批核APE(M)", [to_m(_row(o, c, "未批核APE"))   for c in cats])
    cd.add_series("待签APE(M)",   [to_m(_row(o, c, "待签APE"))     for c in cats])
    return cd


def slide10_donut_target(S2):
    """AB. 银行 目标达成 (已批核/目标剩余)."""
    bk = S2["A"][S2["A"]["业务细分"] == "BK业务"].iloc[0]
    issued = to_m(bk["2026批核APE"])
    remain = to_m(bk["目标APE"]) - issued
    cd = CategoryChartData()
    cd.categories = ["已批核", "目标剩余"]
    cd.add_series("APE构成", [issued, remain])
    return cd


# --------------------------------------------------------------------------
# Slide 11
# --------------------------------------------------------------------------

def slide11_bank_weekly(S3):
    """AB. 银行周度 预约/签单/批核 (W01..W14)."""
    m, n, o = S3["M-APE"], S3["N-APE"], S3["O-APE"]
    week_cols = [c for c in m.columns if c.startswith("2026W")]
    cats = [c.replace("2026", "") for c in week_cols]

    def totals(df):
        row = df[df.iloc[:, 0] == "合计"].iloc[0]
        return [to_m(row[c]) for c in week_cols]

    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("银行预约(M)", totals(m))
    cd.add_series("银行签单(M)", totals(n))
    cd.add_series("银行批核(M)", totals(o))
    return cd


def slide11_branch_ranking(S2):
    """AD. 各分行 2026 批核APE 排名 (降序, 单位: M)."""
    s = S2["S-APE"]
    s = s[s.iloc[:, 0] != "合计"].copy()
    s["_sort"] = s["合计"].apply(num)
    s = s.sort_values("_sort", ascending=False)
    # Keep non-zero rows (match original chart behavior: 17 entries)
    s = s[s["_sort"] > 0]
    cats = s.iloc[:, 0].tolist()
    vals = [to_m(v) for v in s["合计"]]
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("批核APE(M)", vals)
    return cd
