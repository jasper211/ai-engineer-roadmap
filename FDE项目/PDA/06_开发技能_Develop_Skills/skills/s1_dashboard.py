#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：复刻《业绩分析报表》S1_总览仪表盘 的 A-H 八个板块。

对应 01_初始化项目_Initialize_Project/S1_总览仪表盘_反推标准_v0.1.md——每条规则都是
拿真实底表跟 raw_data/业绩分析报表_0724.xlsx 的 S1 sheet 逐项核对出来的。

依赖：
- 清洗后的底表 DataFrame，且已经过 report_enricher 加上"业务大类"字段
  （凡按业务类型分组的地方必须用这个衍生字段，不能用原始 business_category，
  否则MGA业务会漏算，见标准文档"业务类型维度"一节）
- fact_target 快照（tools/fact_target_sync.py 同步下来的CSV），提供目标APE

有一条规则是"实证但原因未确认"：全业务/永明业务的目标APE，都要从 fact_target
里排除 segment_code IN ('NGP','TA')。这是拿真实KPI数字反推出来的，不是我编的，
但为什么要排除这两个segment，业务原因还没找Jasper确认，见标准文档。
"""
import pandas as pd

NON_LAPSE_LOSS_STATUSES = ["取消投保", "退保", "搁置受保"]  # "流失"口径：明确不含"拒保"
UNAPPROVED_STATUSES = ["尚欠保费", "已签单", "pending", "待批核"]  # "未批核"口径
EXCLUDED_TARGET_SEGMENTS = ("NGP", "TA")  # 实证得出，原因待Jasper确认


def _agg(g: pd.DataFrame) -> dict:
    return {
        "count": int(len(g)),
        "ape": float(g["ape"].sum()),
        "premium": float(g["premium"].sum()),
    }


class S1DashboardBuilder:
    def __init__(self, df: pd.DataFrame, fact_target: pd.DataFrame, report_month: str):
        """df: cleaner+report_enricher处理后的DataFrame（需含'业务大类'列）。
        fact_target: fact_target_sync产出的快照DataFrame。
        report_month: 报表"当月"，形如'2026-07'——用于H节"本月已递交"。"""
        self.df = df
        self.fact_target = fact_target
        self.report_month = report_month

    # ---- A. 目标达成率 ----
    def _target_ape(self, target_category: str, carrier_code: str = None) -> float:
        t = self.fact_target[
            (self.fact_target["target_category"] == target_category)
            & (~self.fact_target["segment_code"].isin(EXCLUDED_TARGET_SEGMENTS))
        ]
        if carrier_code:
            t = t[t["carrier_code"] == carrier_code]
        return float(pd.to_numeric(t["target_ape"]).sum())

    def section_a(self) -> list:
        df = self.df
        all_2026 = df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)]
        sl_2026 = all_2026[all_2026["carrier_code"] == "香港永明金融有限公司"]

        rows = []
        for label, achieved, target_cat, carrier in [
            ("2026全业务目标", all_2026["ape"].sum(), "全业务规划", None),
            ("2026永明业务目标", sl_2026["ape"].sum(), "永明业务规划", "SLHK"),
        ]:
            target = self._target_ape(target_cat, carrier)
            rows.append({
                "指标": label,
                "目标APE": target,
                "已达成APE": float(achieved),
                "目标达成率": float(achieved) / target if target else None,
            })
        return rows

    # ---- B. 顶部KPI汇总 ----
    def section_b(self) -> list:
        df = self.df
        groups = {
            "批核(2025)": df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2025)],
            "批核(2026)": df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)],
            "未批核(跨年)": df[df["policy_status"].isin(UNAPPROVED_STATUSES)],
            "待签(跨年)": df[df["policy_status"] == "排期"],
            "流失(2026)": df[df["policy_status"].isin(NON_LAPSE_LOSS_STATUSES) & (df["sign_date"].dt.year == 2026)],
        }
        rows = []
        for label, g in groups.items():
            count = len(g)
            ape = float(g["ape"].sum())
            rows.append({
                "指标行": label,
                "件数": count,
                "APE": ape,
                "年总保费(HKD)": float(g["premium"].sum()),
                "件均APE": ape / count if count else 0.0,
                "融资占比": float((g["Is_Premium_Financing"] == 1).mean()) if count else 0.0,
            })
        return rows

    # ---- C/D/E. 月度业绩走势 ----
    def _monthly_trend(self, date_col: str, exclude_statuses: list) -> list:
        df = self.df
        if exclude_statuses:
            df = df[~df["policy_status"].isin(exclude_statuses)]
        month = df[date_col].dt.strftime("%Y-%m")
        # 报表固定只看"当前年-1"到"当前年"两个自然年（如report_month=2026-07 → 2025+2026），
        # 不是"数据里有的全部月份"——真实报表2025-01起，即便底表有更早(2024)的数据也不展示
        report_year = int(self.report_month[:4])
        window = month.dropna()
        window = window[window.str[:4].astype(int).isin([report_year - 1, report_year])]
        months = sorted(window.unique())
        by_month = {m: _agg(df[month == m]) for m in months}

        rows = []
        for i, m in enumerate(months):
            cur = by_month[m]
            count, ape, premium = cur["count"], cur["ape"], cur["premium"]
            mom = None
            if i > 0:
                prev_ape = by_month[months[i - 1]]["ape"]
                mom = (ape / prev_ape - 1) if prev_ape else None
            yoy = None
            prior_year_month = f"{int(m[:4]) - 1}-{m[5:]}"
            if prior_year_month in by_month:
                py_ape = by_month[prior_year_month]["ape"]
                yoy = (ape / py_ape - 1) if py_ape else None
            rows.append({
                "年月": m, "件数": count, "APE": ape, "年总保费(HKD)": premium,
                "件均APE": ape / count if count else 0.0,
                "环比增长%": mom, "同比增长%": yoy,
            })
        return rows

    def section_c(self) -> list:
        """按预约时间。报表footnote写'排除取消预约'，当前数据没有这个status值，等同不过滤。"""
        return self._monthly_trend("res_date", exclude_statuses=[])

    def section_d(self) -> list:
        """按签单时间。排除'排期'（'取消预约'同样不存在，等同不过滤）。"""
        return self._monthly_trend("sign_date", exclude_statuses=["排期"])

    def section_e(self) -> list:
        """按批核时间。仅status=生效。"""
        df = self.df[self.df["policy_status"] == "生效"]
        return S1DashboardBuilder(df, self.fact_target, self.report_month)._monthly_trend("issue_date", [])

    # ---- F. 保单状态分布-2026 ----
    def section_f(self) -> list:
        df = self.df
        specs = [
            ("A.批核(2026)", "status=生效+issue_year=2026",
             df[(df["policy_status"] == "生效") & (df["issue_date"].dt.year == 2026)]),
            ("B.排期", "status=排期", df[df["policy_status"] == "排期"]),
            ("C.已签单", "status=已签单", df[df["policy_status"] == "已签单"]),
            ("D.待批核", "status=待批核", df[df["policy_status"] == "待批核"]),
            ("E.pending", "status=pending", df[df["policy_status"] == "pending"]),
            ("F.尚欠保费", "status=尚欠保费", df[df["policy_status"] == "尚欠保费"]),
            ("G.失效", "status=失效+sign_year=2026", df.iloc[0:0]),  # 恒为0，当前数据没有"失效"这个status
            ("H.退保", "status=退保+sign_year=2026",
             df[(df["policy_status"] == "退保") & (df["sign_date"].dt.year == 2026)]),
            ("I.取消投保", "status=取消投保+sign_year=2026",
             df[(df["policy_status"] == "取消投保") & (df["sign_date"].dt.year == 2026)]),
            ("J.搁置受保", "status=搁置受保+sign_year=2026",
             df[(df["policy_status"] == "搁置受保") & (df["sign_date"].dt.year == 2026)]),
        ]
        raw_rows = [{"保单状态": label, "统计说明": desc, **_agg(g)} for label, desc, g in specs]
        total_count = sum(r["count"] for r in raw_rows)
        total_ape = sum(r["ape"] for r in raw_rows)
        total_premium = sum(r["premium"] for r in raw_rows)

        rows = []
        for r in raw_rows:
            rows.append({
                "保单状态": r["保单状态"], "统计说明": r["统计说明"], "件数": r["count"],
                "APE": r["ape"], "年总保费(HKD)": r["premium"],
                "件数占比": r["count"] / total_count if total_count else 0.0,
                "APE占比": r["ape"] / total_ape if total_ape else 0.0,
                "年总保费占比": r["premium"] / total_premium if total_premium else 0.0,
            })
        rows.append({
            "保单状态": "合计", "统计说明": "", "件数": total_count, "APE": total_ape,
            "年总保费(HKD)": total_premium, "件数占比": 1.0, "APE占比": 1.0, "年总保费占比": 1.0,
        })
        return rows

    # ---- G. 业务类型维度-2026（必须用"业务大类"，不是原始business_category） ----
    def section_g(self) -> list:
        df = self.df
        rows = []
        totals = {"2026批核APE": 0.0, "批核件数": 0, "未批核APE": 0.0, "未批核件数": 0,
                   "待签APE": 0.0, "待签件数": 0, "合计APE": 0.0, "合计件数": 0}
        for bc in sorted(df["业务大类"].dropna().unique()):
            sub = df[df["业务大类"] == bc]
            b26 = sub[(sub["policy_status"] == "生效") & (sub["issue_date"].dt.year == 2026)]
            unapp = sub[sub["policy_status"].isin(UNAPPROVED_STATUSES)]
            pending_sign = sub[sub["policy_status"] == "排期"]
            row = {
                "业务类型": bc,
                "2026批核APE": float(b26["ape"].sum()), "批核件数": int(len(b26)),
                "未批核APE": float(unapp["ape"].sum()), "未批核件数": int(len(unapp)),
                "待签APE": float(pending_sign["ape"].sum()), "待签件数": int(len(pending_sign)),
            }
            row["合计APE"] = row["2026批核APE"] + row["未批核APE"] + row["待签APE"]
            row["合计件数"] = row["批核件数"] + row["未批核件数"] + row["待签件数"]
            for k in totals:
                totals[k] += row[k]
            rows.append(row)
        rows.append({"业务类型": "合计", **totals})
        return rows

    # ---- H. 永明业绩汇报数据 ----
    def section_h(self) -> list:
        df = self.df[self.df["carrier_code"] == "香港永明金融有限公司"]
        yitai = df[df["issuing_entity"] == "怡泰财富管理有限公司"]

        def entity_slice(name):
            if name == "JF":
                return df[df["issuing_entity"] == "九富保险服务有限公司"]
            if name == "UNIWIN":
                return df[df["issuing_entity"] == "众和恒富理财集团有限公司"]
            if name == "DW Bank":
                return yitai[yitai["market_segment"] == "银行网点"]
            if name == "DW-Non-Bank":
                return yitai[yitai["market_segment"] != "银行网点"]
            if name == "EG":
                return df[df["key_account"] == "EGA"]
            raise ValueError(name)

        months = sorted(df["issue_date"].dt.strftime("%Y-%m").dropna().unique())
        licenses = ["JF", "UNIWIN", "DW-Non-Bank", "EG"]  # Sub Total成员，DW Bank单列在外

        def row_for(name):
            g = entity_slice(name)
            r = {"牌照": name}
            for m in months:
                sub = g[(g["policy_status"] == "生效") & (g["issue_date"].dt.strftime("%Y-%m") == m)]
                r[m] = float(sub["ape"].sum())
            unapp = g[g["policy_status"].isin(UNAPPROVED_STATUSES)]
            r["未批核"] = float(unapp["ape"].sum())
            submitted = g[g["submit_date"].dt.strftime("%Y-%m") == self.report_month]
            r["本月已递交"] = float(submitted["ape"].sum())
            return r

        rows = [row_for(name) for name in licenses]
        sub_total = {"牌照": "Sub Total"}
        for key in rows[0]:
            if key == "牌照":
                continue
            sub_total[key] = sum(r[key] for r in rows)
        rows.append(sub_total)
        rows.append(row_for("DW Bank"))
        return rows

    def build_all(self) -> dict:
        return {
            "A": self.section_a(), "B": self.section_b(),
            "C": self.section_c(), "D": self.section_d(), "E": self.section_e(),
            "F": self.section_f(), "G": self.section_g(), "H": self.section_h(),
        }
