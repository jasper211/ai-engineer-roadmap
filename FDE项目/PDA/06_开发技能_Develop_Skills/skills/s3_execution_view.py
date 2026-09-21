#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：复刻《业绩分析报表》S3_执行管理端 全部20个子板块（A/B/C/D/E/F/G/H/J-O）。

对应 01_初始化项目_Initialize_Project/S3_执行管理端_反推标准_v0.1.md。

最重要的发现：S3的"周"= `dt.strftime('%YW%U')`（周日起始的%U惯例周，不是ISO周），
用连续3周的真实数字精确核验过，两种猜测（ISO周、从年初简单按7天分段）都对不上。

E/F节（未批核与待签分布，按sign_ym+KA+is_pf切分）发现：真实报表的月份列比当前数据能
反推出的月份多2列全0列（2025-10/2025-11），这2列在当前筛选条件下完全没有匹配记录，
无法从现有数据反推出来——判断是报表生成时残留的PivotTable历史列（曾经有数据、后来
状态流转清零，但透视表列本身没跟着收缩），不是业务规则，属已知的展示层小差异。
"""
import pandas as pd

from skills.s2_business_view import SEGMENT_GROUPS, LAPSE_STATUSES, UNAPPROVED_STATUSES, PEER_SEGMENTS


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

    # ---- E/F. 未批核与待签分布（status IN 未批核4态+排期，按sign_ym+KA，is_pf区分常规/融资） ----
    def _pending_distribution(self, is_pf: int):
        statuses = UNAPPROVED_STATUSES + ["排期"]
        pop = self.df[(self.df["policy_status"].isin(statuses)) & (self.df["Is_Premium_Financing"] == is_pf)].copy()
        is_mga = pop["segment_code"] == "MGA业务"
        pop["_ka"] = pop["key_account"].where(~is_mga, pop["key_account"] + "(MGA)")
        pop["_sym"] = pop["sign_date"].dt.strftime("%Y-%m")
        months = sorted(pop["_sym"].dropna().unique())

        triples = []
        for ka, g in pop.groupby("_ka", observed=True):
            ape_row, cnt_row = {"KEY ACCOUNT": ka}, {"KEY ACCOUNT": ka}
            ape_total, cnt_total = 0.0, 0
            for m in months:
                sub = g[g["_sym"] == m]
                ape_row[m] = float(sub["ape"].sum())
                cnt_row[m] = int(len(sub))
                ape_total += ape_row[m]
                cnt_total += cnt_row[m]
            ape_row["合计"], cnt_row["合计"] = ape_total, cnt_total
            triples.append((ape_total, ape_row, cnt_row))
        triples.sort(key=lambda t: t[0], reverse=True)
        ape_rows = [t[1] for t in triples]
        cnt_rows = [t[2] for t in triples]

        ape_total_row, cnt_total_row = {"KEY ACCOUNT": "合计"}, {"KEY ACCOUNT": "合计"}
        for m in months + ["合计"]:
            ape_total_row[m] = sum(r[m] for r in ape_rows)
            cnt_total_row[m] = sum(r[m] for r in cnt_rows)
        ape_rows.append(ape_total_row)
        cnt_rows.append(cnt_total_row)
        return ape_rows, cnt_rows

    def section_e_ape(self):
        return self._pending_distribution(0)[0]

    def section_e_count(self):
        return self._pending_distribution(0)[1]

    def section_f_ape(self):
        return self._pending_distribution(1)[0]

    def section_f_count(self):
        return self._pending_distribution(1)[1]

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

    # ---- J-L/M-O. 周度预约/签单/批核业绩—同行/银行（按KA，同行含MGA拆分） ----
    def _weekly_by_ka(self, population: pd.DataFrame, mode: str, date_col: str, year: int = 2026):
        if mode == "res":
            pop = population[~population["policy_status"].isin(LAPSE_STATUSES)]
        elif mode == "sign":
            pop = population[~population["policy_status"].isin(LAPSE_STATUSES + ["排期"])]
        elif mode == "issue":
            pop = population[population["policy_status"] == "生效"]
        else:
            raise ValueError(mode)
        pop = pop.copy()
        is_mga = pop["segment_code"] == "MGA业务"
        pop["_ka"] = pop["key_account"].where(~is_mga, pop["key_account"] + "(MGA)")
        pop["_wk"] = week_label(pop[date_col])
        weeks = sorted(w for w in pop.loc[pop[date_col].dt.year == year, "_wk"].unique() if not w.endswith("W00"))

        triples = []
        for ka, g in pop.groupby("_ka", observed=True):
            ape_row, cnt_row = {"KEY ACCOUNT": ka}, {"KEY ACCOUNT": ka}
            ape_total, cnt_total = 0.0, 0
            for w in weeks:
                sub = g[g["_wk"] == w]
                ape_row[w] = float(sub["ape"].sum())
                cnt_row[w] = int(len(sub))
                ape_total += ape_row[w]
                cnt_total += cnt_row[w]
            if ape_total == 0 and cnt_total == 0:
                continue
            ape_row["合计"], cnt_row["合计"] = ape_total, cnt_total
            triples.append((ape_total, ape_row, cnt_row))
        triples.sort(key=lambda t: t[0], reverse=True)
        ape_rows = [t[1] for t in triples]
        cnt_rows = [t[2] for t in triples]

        ape_total_row, cnt_total_row = {"KEY ACCOUNT": "合计"}, {"KEY ACCOUNT": "合计"}
        for w in weeks + ["合计"]:
            ape_total_row[w] = sum(r[w] for r in ape_rows)
            cnt_total_row[w] = sum(r[w] for r in cnt_rows)
        ape_rows.append(ape_total_row)
        cnt_rows.append(cnt_total_row)
        return ape_rows, cnt_rows

    def _peer_df(self):
        return self.df[self.df["segment_code"].isin(PEER_SEGMENTS)]

    def _bank_df(self):
        return self.df[self.df["segment_code"] == "BK业务"]

    def section_j_ape(self):
        return self._weekly_by_ka(self._peer_df(), "res", "res_date")[0]

    def section_j_count(self):
        return self._weekly_by_ka(self._peer_df(), "res", "res_date")[1]

    def section_k_ape(self):
        return self._weekly_by_ka(self._peer_df(), "sign", "sign_date")[0]

    def section_k_count(self):
        return self._weekly_by_ka(self._peer_df(), "sign", "sign_date")[1]

    def section_l_ape(self):
        return self._weekly_by_ka(self._peer_df(), "issue", "issue_date")[0]

    def section_l_count(self):
        return self._weekly_by_ka(self._peer_df(), "issue", "issue_date")[1]

    def section_m_ape(self):
        return self._weekly_by_ka(self._bank_df(), "res", "res_date")[0]

    def section_m_count(self):
        return self._weekly_by_ka(self._bank_df(), "res", "res_date")[1]

    def section_n_ape(self):
        return self._weekly_by_ka(self._bank_df(), "sign", "sign_date")[0]

    def section_n_count(self):
        return self._weekly_by_ka(self._bank_df(), "sign", "sign_date")[1]

    def section_o_ape(self):
        return self._weekly_by_ka(self._bank_df(), "issue", "issue_date")[0]

    def section_o_count(self):
        return self._weekly_by_ka(self._bank_df(), "issue", "issue_date")[1]

    def build_core(self) -> dict:
        """A/B/C/D/E/F/G/H/J-O——全部20个子板块。"""
        return {
            "A": self.funnel(),
            "B": self.section_b(), "C": self.section_c(), "D": self.section_d(),
            "E_ape": self.section_e_ape(), "E_count": self.section_e_count(),
            "F_ape": self.section_f_ape(), "F_count": self.section_f_count(),
            "G": self.section_g(), "H": self.section_h(),
            "J_ape": self.section_j_ape(), "J_count": self.section_j_count(),
            "K_ape": self.section_k_ape(), "K_count": self.section_k_count(),
            "L_ape": self.section_l_ape(), "L_count": self.section_l_count(),
            "M_ape": self.section_m_ape(), "M_count": self.section_m_count(),
            "N_ape": self.section_n_ape(), "N_count": self.section_n_count(),
            "O_ape": self.section_o_ape(), "O_count": self.section_o_count(),
        }
