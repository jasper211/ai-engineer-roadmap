#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：扫描 raw_data/ 目录，把长期业务Excel跟期数对上号，并做完整性校验。

文件名格式在官网本身就不统一：
- 2023~2024Q2是"NqYYlong.xls"，2024Q3起是"NqYY_long.xlsx"或"NqYYlong.xlsx"混用
  （下划线可选）
- 2015~2022这批补充历史数据里，大部分年份是2位数年份("1q22long.xls")，但
  2021年两份文件("1q2021long.xls"/"2q2021long.xls")用的是4位数年份，同一年
  剩下两份("3q21long.xls"/"4q21long.xls")又是2位数——同一年内两种写法都有，
  不是我们能假设"一个文件名格式管一整年"的情况，正则必须同时接受2位和4位年份
"""
import re
from dataclasses import dataclass
from pathlib import Path

EXPECTED_PERIODS = [
    (y, q) for y in range(2015, 2026) for q in (1, 2, 3, 4)
] + [(2026, 1)]

PERIOD_TYPE_BY_QUARTER = {1: "YTD_Q1", 2: "YTD_H1", 3: "YTD_9M", 4: "YTD_FY"}

FILENAME_PATTERN = re.compile(r"^(\d)q(\d{2}|\d{4})_?long\.(xlsx|xls)$", re.IGNORECASE)


@dataclass
class ReportFile:
    year: int
    quarter: int
    period_type: str
    file_path: Path
    file_ext: str


class ReportDiscovery:
    """扫描本地raw_data目录，匹配长期业务文件（2015Q1~2026Q1），报出缺失/多余项。"""

    def __init__(self, raw_data_dir: Path):
        self.raw_data_dir = Path(raw_data_dir)

    def discover(self) -> "tuple[list[ReportFile], list[str]]":
        """返回 (按期数排序的报表清单, 问题清单)。问题清单非空时调用方必须决定
        是否继续——不能静默跳过缺失期数或无法识别的文件。"""
        if not self.raw_data_dir.exists():
            return [], [f"目录不存在: {self.raw_data_dir}"]

        found_by_period = {}
        unmatched_files = []

        for path in sorted(self.raw_data_dir.iterdir()):
            if path.name.startswith(".") or not path.is_file():
                continue
            if path.suffix.lower() not in (".xls", ".xlsx"):
                continue
            m = FILENAME_PATTERN.match(path.name)
            if not m:
                unmatched_files.append(path.name)
                continue
            quarter = int(m.group(1))
            year_group = m.group(2)
            year = int(year_group) if len(year_group) == 4 else 2000 + int(year_group)
            if (year, quarter) in found_by_period:
                unmatched_files.append(
                    f"{path.name}（重复：{year}Q{quarter} 已经由 "
                    f"{found_by_period[(year, quarter)].file_path.name} 匹配过）"
                )
                continue
            found_by_period[(year, quarter)] = ReportFile(
                year=year,
                quarter=quarter,
                period_type=PERIOD_TYPE_BY_QUARTER[quarter],
                file_path=path,
                file_ext=path.suffix.lower(),
            )

        problems = [
            f"缺失 {y}Q{q}" for (y, q) in EXPECTED_PERIODS if (y, q) not in found_by_period
        ]
        if unmatched_files:
            problems.append(f"无法识别/重复的文件: {unmatched_files}")

        reports = [found_by_period[p] for p in EXPECTED_PERIODS if p in found_by_period]
        return reports, problems
