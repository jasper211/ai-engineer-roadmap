#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：读取 raw_data/ 下的业绩数据底表 Excel，剔除表头残留行，做列完整性校验。

对应 流程设计.md L3-PDA-01。真实底表核实发现原始 sheet 第一行是正常表头
（被 pandas 当列名消费），第二行是表头的中文值残留在数据里（policy_id=='订单编号'），
必须显式剔除，不能假设 pandas 读出来的第一行就是数据。
"""
import re
from pathlib import Path
from dataclasses import dataclass, field

import pandas as pd

EXPECTED_COLUMNS = [
    "policy_id", "policy_no", "policy_status", "issuing_entity", "business_category",
    "segment_code", "market_segment", "key_account", "company_name", "partner_code",
    "carrier_code", "product_category", "product_id", "premium_term", "payment_mode",
    "currency_code", "premium_orig", "premium", "ape", "sum_assured",
    "Is_Premium_Financing", "customer_type", "SQ_rate", "res_date", "sign_date",
    "submit_date", "issue_date", "referral_code", "tr_register_number", "tr_name",
]

HEADER_ECHO_MARKER = "订单编号"  # policy_id 字段的表头中文值，用来识别残留表头行


class MissingColumnsError(Exception):
    """底表缺少必需列时抛出——不静默跳过，让上游知道数据结构变了。"""


@dataclass
class LoadResult:
    df: pd.DataFrame
    source_file: Path
    export_date: "pd.Timestamp | None"  # 从文件名解析出的导出日期，供 cleaner 判断 future_dated
    header_echo_rows_dropped: int
    raw_row_count: int


def _parse_export_date(file_path: Path) -> "pd.Timestamp | None":
    """从文件名里的 YYYYMMDD 提取导出日期，取不到就退化用文件 mtime。"""
    m = re.search(r"(20\d{6})", file_path.stem)
    if m:
        try:
            return pd.Timestamp(m.group(1))
        except ValueError:
            pass
    return pd.Timestamp(file_path.stat().st_mtime, unit="s").normalize()


class DataLoader:
    """负责底表发现+读取+列完整性校验，不做任何清洗（清洗是cleaner的职责）。"""

    def __init__(self, raw_data_dir: Path):
        self.raw_data_dir = Path(raw_data_dir)

    def discover_files(self) -> "list[Path]":
        files = sorted(self.raw_data_dir.glob("*.xlsx")) + sorted(self.raw_data_dir.glob("*.xls"))
        return files

    def load(self, file_path: "Path | None" = None) -> LoadResult:
        if file_path is None:
            files = self.discover_files()
            if not files:
                raise FileNotFoundError(f"{self.raw_data_dir} 下没有找到任何 .xlsx/.xls 底表文件")
            file_path = files[-1]  # 按文件名排序取最新的一份

        df = pd.read_excel(file_path, sheet_name=0)

        missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
        if missing:
            raise MissingColumnsError(f"{file_path.name} 缺少预期列: {missing}")

        raw_row_count = len(df)
        echo_mask = df["policy_id"] == HEADER_ECHO_MARKER
        dropped = int(echo_mask.sum())
        df = df[~echo_mask].reset_index(drop=True)

        return LoadResult(
            df=df,
            source_file=file_path,
            export_date=_parse_export_date(file_path),
            header_echo_rows_dropped=dropped,
            raw_row_count=raw_row_count,
        )
