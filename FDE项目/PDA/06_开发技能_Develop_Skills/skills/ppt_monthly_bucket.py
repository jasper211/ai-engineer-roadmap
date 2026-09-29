#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ppt_monthly_bucket.py — 把S3周度CSV（'2026W01'...）按自然月分桶聚合，补齐
旧版S2里存在、但新版S1-S9反推里没有对应板块的"同行/银行月度"数据
（第9页W月度分析表、第10页Z银行月度走势图 依赖这个缺口，见
03_规划项目结构_Plan_Project_Structure/PPT生成_旧流水线映射与新架构设计_v0.1.md 第3节）。

⚠️ 不能直接照搬旧版 apply_w14_patches.py::derive_monthly_buckets 的ISO周算法。
settings.json v0.5.0已确认：本项目"周"的口径是 `dt.strftime('%YW%U')`
（%U = 周日起始的惯例周，week 01 = 当年第一个周日所在的那一周），
不是ISO周（周一起始）。ISO周用"周四所在月"做分桶主键，是因为ISO周编号本身
就用周四定年份；%U周没有这个语义保证，这里改用"周内第4天=周三"作为分桶
主键（周日起始的7天里，周三是居中的第4天，跟ISO的周四角色对应），
仅为业务展示上的月份归属，不是精确的会计口径。
"""
import re
from datetime import date, timedelta


def _week_u_start(year: int, week_num: int) -> date:
    """返回%U周号week_num（1-based）在year年的起始日（周日）。
    week_num=0（当年第一个周日之前的天数）本函数不处理，调用方应过滤掉。"""
    jan1 = date(year, 1, 1)
    days_to_sunday = (6 - jan1.weekday()) % 7  # weekday(): Mon=0...Sun=6
    first_sunday = jan1 + timedelta(days=days_to_sunday)
    return first_sunday + timedelta(weeks=week_num - 1)


def derive_monthly_buckets(week_labels: list) -> list:
    """
    week_labels: ['2026W01', '2026W02', ...]（不含_ape/_count后缀）
    返回 [(month_label, [week_labels_in_that_month]), ...]，month_label形如'2026-01'，
    按每周周三所在自然月分桶，桶内保留原始周顺序。
    """
    buckets = []
    cur_month = None
    cur_weeks = []
    for label in week_labels:
        m = re.match(r"(\d{4})W(\d{1,2})", label.strip())
        if not m:
            continue
        yr, wk = int(m.group(1)), int(m.group(2))
        if wk == 0:
            continue
        wed = _week_u_start(yr, wk) + timedelta(days=3)
        month_label = f"{wed.year}-{wed.month:02d}"
        if month_label != cur_month:
            if cur_month is not None:
                buckets.append((cur_month, cur_weeks))
            cur_month = month_label
            cur_weeks = []
        cur_weeks.append(label)
    if cur_month is not None:
        buckets.append((cur_month, cur_weeks))
    return buckets


def aggregate_weekly_to_monthly(df, week_labels: list, name_col: str = None):
    """
    把一张"行=KA/实体，列=周标签"的宽表DataFrame，按derive_monthly_buckets的
    月份分桶对各周求和，返回 {month_label: {row_name: 月度合计值}}。
    df的数值列要求列名跟week_labels完全一致（不含_ape/_count后缀，调用方
    自己传入对应_ape或_count的DataFrame）。
    name_col为None时用df第一列作为行名列。
    """
    from skills.ppt_data_loader import num

    if name_col is None:
        name_col = df.columns[0]
    buckets = derive_monthly_buckets(week_labels)
    out = {}
    for month_label, weeks_in_month in buckets:
        month_totals = {}
        for _, row in df.iterrows():
            name = str(row[name_col]).strip()
            if name in ("", "合计"):
                continue
            total = sum(num(row.get(w, 0)) for w in weeks_in_month if w in df.columns)
            month_totals[name] = total
        out[month_label] = month_totals
    return out
