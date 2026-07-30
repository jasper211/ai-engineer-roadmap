#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：解析长期业务Excel里的"新造业务"+"有效业务"两张头条表，输出未标准化的
原始字段记录（category/metric_name/value）。

只解析这2张表，其余sheet（分币种/保费年期/渠道/再保险等）demo阶段不碰。

真实结构（打开13份真实文件核实过，见03_规划项目结构/流程设计.md 3.2节）：
- 旧制度(2023~2024Q2)按監管類別A-F分类，sheet名 "Form HKLQ1-1"/"Form HKLQ2-1"
- 新制度(2024Q3起)按產品類型分类，sheet名含"LT QR (NB)"/"LT QR (IF)"（2024Q3
  过渡期这份文件多了"B.LT.QR.N "前缀，之后就没有了——用包含匹配定位sheet，
  不用精确字符串匹配）
- 两套制度分类口径不同，不强行统一，用 schema_version 字段区分
  ("pre_rbc"/"post_rbc")，调用方（normalizer）负责标注

表格内部是交叉表：行=类别/业务种类（有跨行合并单元格，需forward-fill），
列=多层表头（有跨列合并单元格，pandas读入时合并单元格的文字只出现在
左上角那一格，同一行内空白格要在"同一个上级分组"范围内才能继承左边格子的
文字，不能一路无脑往右填——这是本模块最容易出错的地方，见parse_sheet内注释。
"""
import re
from pathlib import Path

import pandas as pd

LABEL_COLS = 2  # 列0/1是行标签（类别、业务种类/产品类型），列2起才是指标数值
GRAND_TOTAL_TEXT = "總額"

NB_CANDIDATES = {
    "exact": [("Form HKLQ1-1", "pre_rbc")],
    "regex": [(r"LT QR \(NB\)$", "post_rbc")],
}
IF_CANDIDATES = {
    "exact": [("Form HKLQ2-1", "pre_rbc")],
    "regex": [(r"LT QR \(IF\)$", "post_rbc")],
}


class SheetNotFoundError(Exception):
    pass


class SheetStructureError(Exception):
    pass


def _clean_zh(cell) -> str:
    """双语文案格式是'中文\\nEnglish'，只取中文部分做标签/指标名。"""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return ""
    return str(cell).strip().split("\n")[0].strip()


def _is_decorative_row(df: pd.DataFrame, r: int) -> bool:
    """标题行/期间行/分节说明行整行只有<=1个非空格；标题行例外——它正好有2个
    非空格（标题正文 + 右上角"表格 XXX"表号），用文字特征单独排除。"""
    row = df.iloc[r]
    if row.notna().sum() < 2:
        return True
    for v in row:
        if pd.notna(v) and ("統計數字" in str(v) or re.match(r"^表格?\s", str(v))):
            return True
    return False


def _find_sheet(sheet_names: list, candidates: dict) -> "tuple[str, str]":
    for exact, schema in candidates["exact"]:
        if exact in sheet_names:
            return exact, schema
    for pattern, schema in candidates["regex"]:
        for name in sheet_names:
            if re.search(pattern, name):
                return name, schema
    raise SheetNotFoundError(f"找不到匹配的sheet，实际sheet列表: {sheet_names}")


def _parse_grid(df: pd.DataFrame, sheet_label: str) -> list:
    """把原始网格(header=None)解析成 [{category, metric_name, value}, ...]。"""
    n_rows, n_cols = df.shape

    first_data_row = None
    for r in range(n_rows):
        for c in range(LABEL_COLS, n_cols):
            v = df.iloc[r, c]
            if isinstance(v, (int, float)) and not pd.isna(v):
                first_data_row = r
                break
        if first_data_row is not None:
            break
    if first_data_row is None:
        raise SheetStructureError(f"[{sheet_label}] 找不到任何数据行，表格结构跟预期不符")

    header_rows = [r for r in range(first_data_row) if not _is_decorative_row(df, r)]
    if not header_rows:
        raise SheetStructureError(f"[{sheet_label}] 表头区域没有识别到任何有效表头行")

    # 构建每列的复合指标名：同一行内空白格只在"上一级分组边界"没变的前提下才
    # 继承左边格子的文字（forward-fill），避免跨越更高层表头已经划开的分组
    # 边界（例："此期間末的有效業務"跟"此期間收入帳內的可收取的保費"是两个不同
    # 分组，后面一行里分组内部再细分时，不能让前一分组的文字借着某格空白
    # 渗透过来）。
    prefixes = {c: [] for c in range(LABEL_COLS, n_cols)}
    for r in header_rows:
        snapshot = {c: tuple(prefixes[c]) for c in range(LABEL_COLS, n_cols)}
        carry_text, carry_from_col = None, None
        for c in range(LABEL_COLS, n_cols):
            txt = _clean_zh(df.iloc[r, c])
            if txt:
                prefixes[c].append(txt)
                carry_text, carry_from_col = txt, c
            elif carry_from_col is not None and snapshot[carry_from_col] == snapshot[c]:
                prefixes[c].append(carry_text)
    metric_names = {c: "/".join(parts) if parts else f"col{c}" for c, parts in prefixes.items()}

    # 数据行：forward-fill行标签列（类别字母只在该类别第一行出现），一路走到
    # 唯一的总表总额行（精确匹配"總額"，不能用"contains"——"類別 A 總額"这类
    # 分类小计也含"總額"字样，但不是终点）。
    #
    # 新制度表格里，同一个产品名（如"終身壽險"）会在"分紅業務"和"其他業務"
    # 两个分组下各出现一次——只用列1本身的文字做category会让两次出现撞成同一
    # 个category，把不同分组的数字错误地摞在一起。用last_section单独跟踪最近
    # 一个"全行metric都是空"的标签行（分紅業務/其他業務/相連長期这类分组标题
    # 正是这样：自己没有数字，数字都在它下面的子行里），当作分组前缀。
    # 已知局限：如果某个真实叶子行（如某产品当季数据全为空）恰好也全空，会被
    # 误当成分组标题、污染后续的last_section——这个demo没有再进一步排除这种
    # 情况，真实数据里出现过（相連長期分组下几个产品行全空），只影响这些空行
    # 之后、下一个真分组标题出现之前的小计行的category前缀，不影响任何真实数
    # 值本身的正确性。
    records = []
    last_labels = [""] * LABEL_COLS
    last_section = ""
    for r in range(first_data_row, n_rows):
        row = df.iloc[r]
        own_label_1 = _clean_zh(row.iloc[LABEL_COLS - 1])
        metric_values = [
            (c, row.iloc[c]) for c in range(LABEL_COLS, n_cols)
            if isinstance(row.iloc[c], (int, float)) and not pd.isna(row.iloc[c])
        ]

        labels = []
        for lc in range(LABEL_COLS):
            txt = _clean_zh(row.iloc[lc])
            if txt:
                last_labels[lc] = txt
            labels.append(last_labels[lc])

        if own_label_1 == GRAND_TOTAL_TEXT:
            category = GRAND_TOTAL_TEXT
        else:
            if not metric_values and own_label_1:
                last_section = own_label_1
            parts = [l for l in labels if l]
            if last_section and last_section not in parts:
                parts = [last_section] + parts
            category = " / ".join(parts)

        for c, v in metric_values:
            records.append({
                "category": category,
                "metric_name": metric_names[c],
                "value": v,
            })
        if own_label_1 == GRAND_TOTAL_TEXT:
            break
    else:
        raise SheetStructureError(
            f"[{sheet_label}] 扫到表尾也没找到唯一的'{GRAND_TOTAL_TEXT}'行，"
            f"可能漏了数据或表格比预期长，不能默认已经解析完整"
        )

    return records


class ExcelParser:
    """解析单份长期业务Excel的新造/有效两张头条表。"""

    def parse(self, file_path: Path) -> dict:
        """返回 {"new_business": [...], "in_force": [...], "schema_version": "pre_rbc"/"post_rbc"}
        两张表理论上schema_version应该一致，如果不一致会抛错——那说明这份文件
        本身结构有问题，不能装作没看见继续跑。"""
        engine = "xlrd" if file_path.suffix.lower() == ".xls" else "openpyxl"
        with pd.ExcelFile(file_path, engine=engine) as xls:
            nb_sheet, nb_schema = _find_sheet(xls.sheet_names, NB_CANDIDATES)
            if_sheet, if_schema = _find_sheet(xls.sheet_names, IF_CANDIDATES)
            if nb_schema != if_schema:
                raise SheetStructureError(
                    f"{file_path.name}: 新造业务sheet判定为{nb_schema}，"
                    f"有效业务sheet判定为{if_schema}，同一份文件不该有两种schema"
                )

            nb_df = xls.parse(nb_sheet, header=None)
            if_df = xls.parse(if_sheet, header=None)

        return {
            "new_business": _parse_grid(nb_df, f"{file_path.name}/{nb_sheet}"),
            "in_force": _parse_grid(if_df, f"{file_path.name}/{if_sheet}"),
            "schema_version": nb_schema,
            "nb_sheet_name": nb_sheet,
            "if_sheet_name": if_sheet,
        }
