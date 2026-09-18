#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：复刻《业绩分析报表》S3_执行管理端 的核心板块（A/B/C/D/G/H，20个子板块中的12个）。

对应 01_初始化项目_Initialize_Project/S3_执行管理端_反推标准_v0.1.md。
E/F（未批核待签分布透视表）、J-O（同行/银行周度趋势）本版本未实现。

最重要的发现：S3的"周"= `dt.strftime('%YW%U')`（周日起始的%U惯例周，不是ISO周），
用连续3周的真实数字精确核验过，两种猜测（ISO周、从年初简单按7天分段）都对不上。
"""
import pandas as pd

from skills.s2_business_view import SEGMENT_GROUPS, LAPSE_STATUSES, UNAPPROVED_STATUSES


def week_label(series: pd.Series) -> pd.Series:
    return series.dt.strftime("%YW%U")


class S3ExecutionViewBuilder:
    def __init__(self, df: pd.DataFrame):
        """df: cleaner处理后的DataFrame，用segment_code原始字段（同S2，不需要业务大类）。"""
        self.df = df

    # ---- A-APE/A-件数. 阶段周追踪漏斗 ----
    def funnel(self, year: int = 2026) -> dict:
        df = self.df.copy()
        res_ok = df[~df["policy_status"].isin(LAPSE_STATUSES)]
        sign_ok = df[~df["policy_status"].isin(LAPSE_STATUSES + ["排期"])]
        submit_ok = df[~df["policy_status"].isin(LAPSE_STATUSES)]
        issue_ok = df[df["policy_status"] == "生效"]

        stages = {
            "预约": (res_ok, "res_date"),
            "签单": (sign_ok, "sign_date"),
            "递交": (submit_ok, "submit_date"),
            "批核": (issue_ok, "issue_date"),
        }
        # W00(%U惯例，元旦到第一个周日之间的零头天数)报表不展示，从W01开始
        all_weeks = sorted(w for w in week_label(df[df["res_date"].dt.year == year]["res_date"]).unique()
                            if not w.endswith("W00"))
        result = {}
        for stage, (g, col) in stages.items():
            wk = week_label(g[col])
            g = g.assign(_wk=wk)
            row = {}
            for w in all_weeks:
                sub = g[g["_wk"] == w]
                row[w] = {"ape": float(sub["ape"].sum()), "count": int(len(sub))}
            result[stage] = row
        return result

    # ---- B/C/D. 周度预约/签单/批核业绩（按业务细分，含MGA折算） ----
    def _weekly_by_segment(self, date_col: str, mode: str, year: int = 2026, population: pd.DataFrame = None) -> list:
        df = self.df if population is None else population
        if mode == "res":
            df = df[~df["policy_status"].isin(LAPSE_STATUSES)]
        elif mode == "sign":
            df = df[~df["policy_status"].isin(LAPSE_STATUSES + ["排期"])]
        elif mode == "issue":
            df = df[df["policy_status"] == "生效"]
        else:
            raise ValueError(mode)

        wk = week_label(df[date_col])
        df = df.assign(_wk=wk)
        weeks = sorted(w for w in df.loc[df[date_col].dt.year == year, "_wk"].unique() if not w.endswith("W00"))

        rows = []
        for label, codes in SEGMENT_GROUPS.items():
            row = {"业务细分": label}
            for w in weeks:
                sub = df[(df["_wk"] == w) & (df["segment_code"].isin(codes))]
                row[w] = {"ape": float(sub["ape"].sum()), "count": int(len(sub))}
            rows.append(row)
        total = {"业务细分": "合计"}
        for w in weeks:
            total[w] = {
                "ape": sum(r[w]["ape"] for r in rows),
                "count": sum(r[w]["count"] for r in rows),
            }
        rows.append(total)
        return rows

    def section_b(self):
        return self._weekly_by_segment("res_date", "res")

    def section_c(self):
        return self._weekly_by_segment("sign_date", "sign")

    def section_d(self):
        return self._weekly_by_segment("issue_date", "issue")

    # ---- G. 签批时效分析-2026批核 ----
    def section_g(self) -> list:
        df = self.df
        rows = []
        for label, codes in SEGMENT_GROUPS.items():
            g = df[(df["segment_code"].isin(codes)) & (df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)]
            if len(g) == 0:
                rows.append({"业务细分": label, "件数": 0, "件均APE": None, "平均时效(天)": None,
                              "中位时效(天)": None, "P90时效(天)": None, "最大时效(天)": None, "SLA达标率≤60": None})
                continue
            tat = (g["issue_date"] - g["sign_date"]).dt.days
            rows.append({
                "业务细分": label, "件数": int(len(g)), "件均APE": float(g["ape"].mean()),
                "平均时效(天)": round(float(tat.mean()), 1), "中位时效(天)": float(tat.median()),
                "P90时效(天)": float(tat.quantile(0.9)), "最大时效(天)": int(tat.max()),
                "SLA达标率≤60": float((tat <= 60).mean()),
            })
        all_b26 = df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)]
        tat_all = (all_b26["issue_date"] - all_b26["sign_date"]).dt.days
        rows.append({
            "业务细分": "合计", "件数": int(len(all_b26)), "件均APE": float(all_b26["ape"].mean()),
            "平均时效(天)": round(float(tat_all.mean()), 1), "中位时效(天)": float(tat_all.median()),
            "P90时效(天)": float(tat_all.quantile(0.9)), "最大时效(天)": int(tat_all.max()),
            "SLA达标率≤60": float((tat_all <= 60).mean()),
        })
        return rows

    # ---- H. 签批时效分档-2026批核（排除TAT<0异常值；合计行=全量，不是6档相加） ----
    def section_h(self) -> list:
        df = self.df[(self.df["policy_status"] == "生效") & (self.df["issue_date"].dt.year == 2026)].copy()
        tat = (df["issue_date"] - df["sign_date"]).dt.days
        df["_tat"] = tat

        def bucket(t):
            if t < 0:
                return None  # 真实脏数据(批核日早于签单日)，不计入任何分档
            if t <= 7:
                return "≤7天"
            if t <= 14:
                return "8-14天"
            if t <= 30:
                return "15-30天"
            if t <= 60:
                return "31-60天"
            if t <= 90:
                return "61-90天"
            return ">90天"

        df["_bucket"] = df["_tat"].apply(bucket)
        total_count, total_ape = len(df), float(df["ape"].sum())

        rows = []
        for label in ["≤7天", "8-14天", "15-30天", "31-60天", "61-90天", ">90天"]:
            g = df[df["_bucket"] == label]
            rows.append({
                "时效分档": label, "件数": int(len(g)), "APE": float(g["ape"].sum()),
                "件数占比": len(g) / total_count if total_count else 0.0,
                "APE占比": float(g["ape"].sum()) / total_ape if total_ape else 0.0,
            })
        rows.append({"时效分档": "合计", "件数": total_count, "APE": total_ape, "件数占比": 1.0, "APE占比": 1.0})
        return rows

    def build_core(self) -> dict:
        """A/B/C/D/G/H——已核验或高置信度板块。E/F/J-O未实现，见标准文档三节。"""
        return {
            "A": self.funnel(),
            "B": self.section_b(), "C": self.section_c(), "D": self.section_d(),
            "G": self.section_g(), "H": self.section_h(),
        }
