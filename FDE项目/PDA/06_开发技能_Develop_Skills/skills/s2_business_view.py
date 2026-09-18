#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：复刻《业绩分析报表》S2_业务端视角 的核心板块（A/B/C-H/I/J/K/O，20个板块中18个）。

对应 01_初始化项目_Initialize_Project/S2_业务端视角_反推标准_v0.1.md。
S/T节（按partner_code分组的银行各分行明细）是新维度，尚未验证，本版本不实现。

两条贯穿全表的关键规则（跟S1不同，S2专属）：
1. "同行经代"分组 = segment_code IN ('同行经代','MGA业务')——MGA业务在segment层面
   折进"同行经代"，不是"永明经代"，也不是S1用的"业务大类"重分类逻辑，是独立的规则。
   但对应fact_target查目标值时，"同行经代"只取BRK这一个编码的目标，不含TA(MGA的目标)。
2. "流失类" = 取消投保/退保/搁置受保，不含拒保——跟S1"流失"口径一致。
"""
import pandas as pd

LAPSE_STATUSES = ["取消投保", "退保", "搁置受保"]  # "流失类"，明确不含"拒保"
UNAPPROVED_STATUSES = ["尚欠保费", "已签单", "pending", "待批核"]

# 业务细分显示名 -> 原始segment_code取值集合（"同行经代"折入MGA业务）
SEGMENT_GROUPS = {
    "天领业务": ["天领业务"],
    "成事家办": ["成事家办"],
    "BK业务": ["BK业务"],
    "同行经代": ["同行经代", "MGA业务"],
    "永明经代": ["永明经代"],
    "合伙转介业务": ["合伙转介业务"],
    "ICLUB业务": ["ICLUB业务"],
    "IFA业务": ["IFA业务"],
}
# 业务细分显示名 -> fact_target的segment_code（查目标值用，"同行经代"只取BRK不含TA）
SEGMENT_TARGET_CODE = {
    "天领业务": "SLC", "成事家办": "GTD", "BK业务": "BK", "同行经代": "BRK",
    "永明经代": "SLBRK", "合伙转介业务": "REF", "ICLUB业务": "ICLUB", "IFA业务": "IFA",
}
PEER_SEGMENTS = ["永明经代", "同行经代", "MGA业务"]  # K节"同行" = segment IN(永明经代,同行经代[含MGA])


def _stage_agg(g: pd.DataFrame) -> dict:
    b26 = g[(g["policy_status"] == "生效") & (g["issue_date"].dt.year == 2026)]
    unapp = g[g["policy_status"].isin(UNAPPROVED_STATUSES)]
    pending = g[g["policy_status"] == "排期"]
    return {
        "2026批核APE": float(b26["ape"].sum()), "批核件数": int(len(b26)),
        "未批核APE": float(unapp["ape"].sum()), "未批核件数": int(len(unapp)),
        "待签APE": float(pending["ape"].sum()), "待签件数": int(len(pending)),
    }


class S2BusinessViewBuilder:
    def __init__(self, df: pd.DataFrame, fact_target: pd.DataFrame):
        """df: cleaner处理后的DataFrame（本节不需要report_enricher的业务大类字段，
        用的是segment_code原始字段 + SEGMENT_GROUPS折算）。"""
        self.df = df
        self.fact_target = fact_target

    def _target_ape(self, segment_label: str, target_category: str, carrier_code: str = None) -> float:
        code = SEGMENT_TARGET_CODE[segment_label]
        t = self.fact_target[
            (self.fact_target["target_category"] == target_category)
            & (self.fact_target["segment_code"] == code)
        ]
        if carrier_code:
            t = t[t["carrier_code"] == carrier_code]
        return float(pd.to_numeric(t["target_ape"]).sum())

    # ---- A/B. 业务细分年度汇总（carrier=None时是A，否则是B） ----
    def segment_summary(self, carrier: str = None) -> list:
        df = self.df if carrier is None else self.df[self.df["carrier_code"] == carrier]
        target_category = "全业务规划" if carrier is None else "永明业务规划"
        rows = []
        totals = {k: 0.0 if "APE" in k else 0 for k in
                  ["2026批核APE", "批核件数", "未批核APE", "未批核件数", "待签APE", "待签件数"]}
        for label, codes in SEGMENT_GROUPS.items():
            g = df[df["segment_code"].isin(codes)]
            stat = _stage_agg(g)
            target = self._target_ape(label, target_category, "SLHK" if carrier else None)
            row = {"业务细分": label, "目标APE": target, "达成率": stat["2026批核APE"] / target if target else None, **stat}
            row["合计APE"] = row["2026批核APE"] + row["未批核APE"] + row["待签APE"]
            row["合计件数"] = row["批核件数"] + row["未批核件数"] + row["待签件数"]
            for k in totals:
                totals[k] += stat[k]
            rows.append(row)
        target_total = sum(self._target_ape(l, target_category, "SLHK" if carrier else None) for l in SEGMENT_GROUPS)
        totals_row = {"业务细分": "合计", "目标APE": target_total,
                      "达成率": totals["2026批核APE"] / target_total if target_total else None, **totals}
        totals_row["合计APE"] = totals_row["2026批核APE"] + totals_row["未批核APE"] + totals_row["待签APE"]
        totals_row["合计件数"] = totals_row["批核件数"] + totals_row["未批核件数"] + totals_row["待签件数"]
        rows.append(totals_row)
        return rows

    # ---- C-H（及L-T中已验证的月度趋势通用逻辑） ----
    def monthly_trend(self, population: pd.DataFrame, date_col: str, mode: str, year: int = 2026) -> list:
        """mode: 'res'(排除流失类) / 'sign'(排除排期+流失类) / 'issue'(仅生效)。
        年份固定只看`year`一年（S2月度趋势板块不像S1那样跨两年），跟真实报表列范围一致。"""
        df = population
        if mode == "res":
            df = df[~df["policy_status"].isin(LAPSE_STATUSES)]
        elif mode == "sign":
            df = df[~df["policy_status"].isin(LAPSE_STATUSES + ["排期"])]
        elif mode == "issue":
            df = df[df["policy_status"] == "生效"]
        else:
            raise ValueError(mode)

        month = df[date_col].dt.strftime("%Y-%m")
        months = [f"{year}-{m:02d}" for m in range(1, 13)]
        by_month = {m: df[month == m] for m in months}
        rows = []
        for label, codes in SEGMENT_GROUPS.items():
            row = {"业务细分": label}
            total_ape, total_count = 0.0, 0
            for m in months:
                g = by_month[m][by_month[m]["segment_code"].isin(codes)]
                row[m] = {"ape": float(g["ape"].sum()), "count": int(len(g))}
                total_ape += row[m]["ape"]
                total_count += row[m]["count"]
            row["合计"] = {"ape": total_ape, "count": total_count}
            rows.append(row)
        total_row = {"业务细分": "合计"}
        for m in months + ["合计"]:
            total_row[m] = {
                "ape": sum(r[m]["ape"] for r in rows),
                "count": sum(r[m]["count"] for r in rows),
            }
        rows.append(total_row)
        return rows

    def section_c(self):
        return self.monthly_trend(self.df, "res_date", "res")

    def section_d(self):
        return self.monthly_trend(self.df, "sign_date", "sign")

    def section_e(self):
        return self.monthly_trend(self.df, "issue_date", "issue")

    def section_f(self):
        return self.monthly_trend(self.df[self.df["carrier_code"] == "香港永明金融有限公司"], "res_date", "res")

    def section_g(self):
        return self.monthly_trend(self.df[self.df["carrier_code"] == "香港永明金融有限公司"], "sign_date", "sign")

    def section_h(self):
        return self.monthly_trend(self.df[self.df["carrier_code"] == "香港永明金融有限公司"], "issue_date", "issue")

    # ---- I. KEY ACCOUNT排名TOP20（含"XX(MGA)"拆分） ----
    def section_i(self, top_n: int = 20) -> list:
        df = self.df.copy()
        is_mga = df["segment_code"] == "MGA业务"
        df["_ka_label"] = df["key_account"].where(~is_mga, df["key_account"] + "(MGA)")
        rows = []
        for ka, g in df.groupby("_ka_label", observed=True):
            stat = _stage_agg(g)
            if stat["批核件数"] == 0 and stat["未批核件数"] == 0 and stat["待签件数"] == 0:
                continue
            rows.append({"KEY ACCOUNT": ka, "业务细分": g["segment_code"].iloc[0], **stat})
        rows.sort(key=lambda r: r["2026批核APE"], reverse=True)
        top = rows[:top_n]
        total = {"KEY ACCOUNT": "合计", "业务细分": ""}
        for k in ["2026批核APE", "批核件数", "未批核APE", "未批核件数", "待签APE", "待签件数"]:
            total[k] = sum(r[k] for r in top)
        top.append(total)
        return top

    # ---- J. 同行推荐人分析（referral_code，不限carrier） ----
    def section_j(self) -> list:
        names = ["姜通", "战略合作", "高瑶", "白博文", "Mark", "魏子璐"]
        rows = []
        for name in names:
            g = self.df[self.df["referral_code"] == name]
            stat = _stage_agg(g)
            total_ape = stat["2026批核APE"] + stat["未批核APE"] + stat["待签APE"]
            total_count = stat["批核件数"] + stat["未批核件数"] + stat["待签件数"]
            rows.append({"推荐人": name, **stat, "总APE": total_ape, "总件数": total_count})
        rows.sort(key=lambda r: r["2026批核APE"], reverse=True)
        total = {"推荐人": "合计"}
        for k in ["2026批核APE", "批核件数", "未批核APE", "未批核件数", "待签APE", "待签件数", "总APE", "总件数"]:
            total[k] = sum(r[k] for r in rows)
        rows.append(total)
        return rows

    # ---- K. 同行业绩分析（segment IN 永明经代/同行经代[含MGA]，按key_account，MGA同样拆分成"XX(MGA)"） ----
    def section_k(self) -> list:
        df = self.df[self.df["segment_code"].isin(PEER_SEGMENTS)].copy()
        is_mga = df["segment_code"] == "MGA业务"
        df["_ka_label"] = df["key_account"].where(~is_mga, df["key_account"] + "(MGA)")
        rows = []
        for ka, g in df.groupby("_ka_label", observed=True):
            stat = _stage_agg(g)
            total_count = stat["批核件数"] + stat["未批核件数"] + stat["待签件数"]
            if total_count == 0:
                continue
            total_ape = stat["2026批核APE"] + stat["未批核APE"] + stat["待签APE"]
            rows.append({"KEY ACCOUNT": ka, **stat, "总APE": total_ape, "总件数": total_count})
        rows.sort(key=lambda r: r["2026批核APE"], reverse=True)
        total = {"KEY ACCOUNT": "合计"}
        for k in ["2026批核APE", "批核件数", "未批核APE", "未批核件数", "待签APE", "待签件数", "总APE", "总件数"]:
            total[k] = sum(r[k] for r in rows)
        rows.append(total)
        return rows

    # ---- O. 银行业绩分析（segment=BK业务，按key_account） ----
    def section_o(self) -> list:
        df = self.df[self.df["segment_code"] == "BK业务"]
        rows = []
        for ka, g in df.groupby("key_account", observed=True):
            stat = _stage_agg(g)
            total_count = stat["批核件数"] + stat["未批核件数"] + stat["待签件数"]
            if total_count == 0:
                continue
            total_ape = stat["2026批核APE"] + stat["未批核APE"] + stat["待签APE"]
            rows.append({"KEY ACCOUNT": ka, **stat, "总APE": total_ape, "总件数": total_count})
        rows.sort(key=lambda r: r["2026批核APE"], reverse=True)
        total = {"KEY ACCOUNT": "合计"}
        for k in ["2026批核APE", "批核件数", "未批核APE", "未批核件数", "待签APE", "待签件数", "总APE", "总件数"]:
            total[k] = sum(r[k] for r in rows)
        rows.append(total)
        return rows

    # ---- L-N/P-R. 同行/银行 月度趋势（跟C/D/E同规则，范围收窄——模式推算，未逐月核验） ----
    def peer_monthly_trend(self, date_col: str, mode: str, year: int = 2026):
        return self.monthly_trend(self.df[self.df["segment_code"].isin(PEER_SEGMENTS)], date_col, mode, year)

    def bank_monthly_trend(self, date_col: str, mode: str, year: int = 2026):
        return self.monthly_trend(self.df[self.df["segment_code"] == "BK业务"], date_col, mode, year)

    def build_core(self) -> dict:
        """A/B/C-H/I/J/K/O——18个已核验或高置信度板块。S/T(partner_code维度)未实现，见标准文档三节。"""
        return {
            "A": self.segment_summary(carrier=None),
            "B": self.segment_summary(carrier="香港永明金融有限公司"),
            "C": self.section_c(), "D": self.section_d(), "E": self.section_e(),
            "F": self.section_f(), "G": self.section_g(), "H": self.section_h(),
            "I": self.section_i(), "J": self.section_j(), "K": self.section_k(), "O": self.section_o(),
        }
