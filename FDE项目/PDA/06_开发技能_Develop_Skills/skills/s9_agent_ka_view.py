#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：复刻《业绩分析报表》S9_代理人与KA业务 全部10个顶层板块（A-J，H/I/J各含6张周度子表）。

对应 01_初始化项目_Initialize_Project/S9_代理人与KA业务_反推标准_v0.1.md。四条S9专属规则：
1. A节 = S2-A同一份业务细分年度汇总，只取5条"代理人"业务线(天领业务/成事家办/合伙转介业务/
   ICLUB业务/IFA业务)，不含BK业务/同行经代/永明经代，直接复用S2的segment_summary()。
2. B/C/F节的KA汇总 = 单一segment过滤+按key_account分组，同S2-K/O规则；2026批核APE并列时
   用总APE降序做二级排序。
3. D/E/G节标题"(含流失单)"具有误导性——实测口径跟S2月度趋势的res/sign/issue三态完全一致
   (排除流失类)，月份范围固定2026-01~2026-08。
4. H/I/J节KA周度明细每张子表(预约/签单/批核×APE/件数)各自独立过滤0贡献KA、独立按自身
   合计降序排序，不跟随业务细分固定顺序；周定义跟S3完全一致(%YW%U)。
"""
import pandas as pd

from skills.s2_business_view import SEGMENT_GROUPS, LAPSE_STATUSES, S2BusinessViewBuilder, _stage_agg
from skills.s3_execution_view import week_label

AGENT_SEGMENTS = ["天领业务", "成事家办", "合伙转介业务", "ICLUB业务", "IFA业务"]
KA_SEGMENTS = ["ICLUB业务", "合伙转介业务", "IFA业务"]
_MONTHS = [f"2026-{m:02d}" for m in range(1, 9)]


class S9AgentKaViewBuilder:
    def __init__(self, df: pd.DataFrame, fact_target: pd.DataFrame):
        self.df = df
        self.fact_target = fact_target

    # ---- A. 业务细分年度汇总（代理人+KA） ----
    def section_a(self) -> list:
        s2a = {r["业务细分"]: r for r in S2BusinessViewBuilder(self.df, self.fact_target).segment_summary(carrier=None)}
        rows = [s2a[label] for label in AGENT_SEGMENTS]
        keys = ["目标APE", "2026批核APE", "批核件数", "未批核APE", "未批核件数",
                "待签APE", "待签件数", "合计APE", "合计件数"]
        totals = {k: 0.0 if "APE" in k else 0 for k in keys}
        for r in rows:
            for k in keys:
                totals[k] += r[k]
        totals_row = {"业务细分": "合计", **totals,
                      "达成率": totals["2026批核APE"] / totals["目标APE"] if totals["目标APE"] else None}
        rows.append(totals_row)
        return rows

    # ---- B/C/F. 单一业务细分—KA业绩分析 ----
    def _ka_summary(self, segment_label: str) -> list:
        g = self.df[self.df["segment_code"].isin(SEGMENT_GROUPS[segment_label])]
        rows = []
        for ka, gg in g.groupby("key_account", observed=True):
            stat = _stage_agg(gg)
            total_count = stat["批核件数"] + stat["未批核件数"] + stat["待签件数"]
            if total_count == 0:
                continue
            total_ape = stat["2026批核APE"] + stat["未批核APE"] + stat["待签APE"]
            rows.append({"KEY ACCOUNT": ka, **stat, "总APE": total_ape, "总件数": total_count})
        rows.sort(key=lambda r: r["总APE"], reverse=True)
        rows.sort(key=lambda r: r["2026批核APE"], reverse=True)
        total = {"KEY ACCOUNT": "合计"}
        for k in ["2026批核APE", "批核件数", "未批核APE", "未批核件数", "待签APE", "待签件数", "总APE", "总件数"]:
            total[k] = sum(r[k] for r in rows)
        rows.append(total)
        return rows

    def section_b(self):
        return self._ka_summary("天领业务")

    def section_c(self):
        return self._ka_summary("成事家办")

    def section_f(self) -> dict:
        return {seg: self._ka_summary(seg) for seg in KA_SEGMENTS}

    # ---- D/E/G. 月度明细（标题写"含流失单"，实测=S2的res/sign/issue三态口径） ----
    def _monthly_detail(self, population: pd.DataFrame) -> list:
        res_pop = population[~population["policy_status"].isin(LAPSE_STATUSES)]
        sign_pop = population[~population["policy_status"].isin(LAPSE_STATUSES + ["排期"])]
        issue_pop = population[population["policy_status"] == "生效"]
        rows = []
        for name, pop, date_col in [("预约", res_pop, "res_date"), ("签单", sign_pop, "sign_date"),
                                     ("批核", issue_pop, "issue_date")]:
            month = pop[date_col].dt.strftime("%Y-%m")
            for metric in ["APE", "件数"]:
                row = {"指标": f"{name} {metric}"}
                total = 0.0
                for m in _MONTHS:
                    g = pop[month == m]
                    v = float(g["ape"].sum()) if metric == "APE" else int(len(g))
                    row[m] = v
                    total += v
                row["合计"] = total
                rows.append(row)
        return rows

    def section_d(self):
        return self._monthly_detail(self.df[self.df["segment_code"].isin(SEGMENT_GROUPS["天领业务"])])

    def section_e(self):
        return self._monthly_detail(self.df[self.df["segment_code"].isin(SEGMENT_GROUPS["成事家办"])])

    def section_g(self):
        codes = [c for s in KA_SEGMENTS for c in SEGMENT_GROUPS[s]]
        return self._monthly_detail(self.df[self.df["segment_code"].isin(codes)])

    # ---- H/I/J. KA周度明细：预约/签单/批核 × APE/件数，各自独立过滤0贡献KA+按自身合计降序 ----
    def _weekly_by_ka(self, population: pd.DataFrame, year: int = 2026) -> dict:
        res_pop = population[~population["policy_status"].isin(LAPSE_STATUSES)]
        sign_pop = population[~population["policy_status"].isin(LAPSE_STATUSES + ["排期"])]
        issue_pop = population[population["policy_status"] == "生效"]

        result = {}
        for name, pop, date_col in [("预约", res_pop, "res_date"), ("签单", sign_pop, "sign_date"),
                                     ("批核", issue_pop, "issue_date")]:
            pop = pop.copy()
            pop["_wk"] = week_label(pop[date_col])
            weeks = sorted(w for w in pop.loc[pop[date_col].dt.year == year, "_wk"].unique() if not w.endswith("W00"))
            for metric in ["APE", "件数"]:
                rows = []
                for ka, g in pop.groupby("key_account", observed=True):
                    row = {"KEY ACCOUNT": ka}
                    total = 0.0
                    for w in weeks:
                        sub = g[g["_wk"] == w]
                        v = float(sub["ape"].sum()) if metric == "APE" else int(len(sub))
                        row[w] = v
                        total += v
                    if total == 0:
                        continue
                    row["合计"] = total
                    rows.append(row)
                rows.sort(key=lambda r: r["合计"], reverse=True)
                total_row = {"KEY ACCOUNT": "合计"}
                for w in weeks + ["合计"]:
                    total_row[w] = sum(r[w] for r in rows)
                rows.append(total_row)
                result[f"{name}_{metric}"] = rows
        return result

    def section_h(self):
        return self._weekly_by_ka(self.df[self.df["segment_code"].isin(SEGMENT_GROUPS["天领业务"])])

    def section_i(self):
        return self._weekly_by_ka(self.df[self.df["segment_code"].isin(SEGMENT_GROUPS["成事家办"])])

    def section_j(self):
        codes = [c for s in KA_SEGMENTS for c in SEGMENT_GROUPS[s]]
        return self._weekly_by_ka(self.df[self.df["segment_code"].isin(codes)])

    def build_all(self) -> dict:
        f = self.section_f()
        out = {
            "A": self.section_a(), "B": self.section_b(), "C": self.section_c(),
            "D": self.section_d(), "E": self.section_e(),
            "F_ICLUB业务": f["ICLUB业务"], "F_合伙转介业务": f["合伙转介业务"], "F_IFA业务": f["IFA业务"],
            "G": self.section_g(),
        }
        for prefix, method in [("H", self.section_h), ("I", self.section_i), ("J", self.section_j)]:
            for k, v in method().items():
                out[f"{prefix}_{k}"] = v
        return out
