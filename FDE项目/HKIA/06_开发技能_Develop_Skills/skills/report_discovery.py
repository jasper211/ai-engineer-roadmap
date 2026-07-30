#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：扫描 raw_data/ 目录，把长期业务13期Excel跟期数对上号，并做完整性校验。

文件名格式在官网本身就不统一（2023~2024Q2是"NqYYlong.xls"，2024Q3起是
"NqYY_long.xlsx"或"NqYYlong.xlsx"混用），正则里下划线设为可选，不假设任何一种
写法是"标准"写法。
"""
import re
from dataclasses import dataclass
from pathlib import Path

EXPECTED_PERIODS = [
    (2023, 1), (2023, 2), (2023, 3), (2023, 4),
    (2024, 1), (2024, 2), (2024, 3), (2024, 4),
    (2025, 1), (2025, 2), (2025, 3), (2025, 4),
    (2026, 1),
]

PERIOD_TYPE_BY_QUARTER = {1: "YTD_Q1", 2: "YTD_H1", 3: "YTD_9M", 4: "YTD_FY"}

FILENAME_PATTERN = re.compile(r"^(\d)q(\d{2})_?long\.(xlsx|xls)$", re.IGNORECASE)


@dataclass
class ReportFile:
    year: int
    quarter: int
    period_type: str
    file_path: Path
    file_ext: str


class ReportDiscovery:
    """扫描本地raw_data目录，匹配13期长期业务文件，报出缺失/多余项。"""

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
            year = 2000 + int(m.group(2))
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
