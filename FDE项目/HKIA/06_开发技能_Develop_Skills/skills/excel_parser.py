#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：解析长期业务Excel里的头条表，输出未标准化的原始字段记录
（category/metric_name/value）。

覆盖3张表：
- "新造业务"/"有效业务"（市场总量，按类别/产品类型细分）
- "新造业务·按保险公司"（Table L1，市场份额用）——有效业务的按保险公司拆分
  （Table L3/L3-1+L3-2）demo暂不做，见流程设计文档

真实结构（打开13份真实文件核实过，见03_规划项目结构/流程设计.md 3.2节）：
- 旧制度(2023~2024Q2)按監管類別A-F分类，sheet名 "Form HKLQ1-1"/"Form HKLQ2-1"
- 新制度(2024Q3起)按產品類型分类，sheet名含"LT QR (NB)"/"LT QR (IF)"（2024Q3
  过渡期这份文件多了"B.LT.QR.N "前缀，之后就没有了——用包含匹配定位sheet，
  不用精确字符串匹配）
- 两套制度分类口径不同，不强行统一，用 schema_version 字段区分
  ("pre_rbc"/"post_rbc")，调用方（normalizer）负责标注

表格内部是交叉表：行=类别/业务种类（或保险公司名），列=多层表头。两类表格
在细节上有真实差异，各自有专门的解析函数，见下方注释。
"""
import re
from pathlib import Path

import pandas as pd

LABEL_COLS = 2  # 列0/1是行标签，列2起才是指标数值
GRAND_TOTAL_TEXTS = {"總額", "市場總額"}  # 头条表用"總額"，按公司拆分表用"市場總額"

NB_CANDIDATES = {
    "exact": [("Form HKLQ1-1", "pre_rbc")],
    "regex": [(r"LT QR \(NB\)$", "post_rbc")],
}
IF_CANDIDATES = {
    "exact": [("Form HKLQ2-1", "pre_rbc")],
    "regex": [(r"LT QR \(IF\)$", "post_rbc")],
}
NB_BY_INSURER_CANDIDATES = {
    # sheet名"Table L1"新旧制度都一样，跟"Form HKLQ1-1" vs "Form LT QR (NB)"
    # 不同——这张表本身分不出schema，直接沿用已经从头条表判定出来的
    # schema_version，不独立猜测（用 None 占位，调用方不使用这个值）。
    "exact": [("Table L1", None)],
    "regex": [],
}


class SheetNotFoundError(Exception):
    pass


class SheetStructureError(Exception):
    pass


def _has_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in s)


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


def _build_metric_names(df: pd.DataFrame, header_rows: list, n_cols: int) -> dict:
    """构建每列的复合指标名：同一行内空白格只在"上一级分组边界"没变的前提下才
    继承左边格子的文字（forward-fill），避免跨越更高层表头已经划开的分组边界
    渗透过来。只取含中文字符的文字——个别表格的英文表头会因为单元格换行被
    拆到单独一行（如"Single"/"Revenue"/"Premiums"三行各占一行、只有第一行带
    中文"整付保費收入"），这些纯英文续行不是新的表头层级，跳过不加进指标名。
    """
    prefixes = {c: [] for c in range(LABEL_COLS, n_cols)}
    for r in header_rows:
        snapshot = {c: tuple(prefixes[c]) for c in range(LABEL_COLS, n_cols)}
        carry_text, carry_from_col = None, None
        for c in range(LABEL_COLS, n_cols):
            txt = _clean_zh(df.iloc[r, c])
            if txt and not _has_cjk(txt) and prefixes[c]:
                continue  # 纯英文续行，且这一列已经有过带中文的文字了，跳过
            if txt:
                prefixes[c].append(txt)
                carry_text, carry_from_col = txt, c
            elif carry_from_col is not None and snapshot[carry_from_col] == snapshot[c]:
                prefixes[c].append(carry_text)
    return {c: "/".join(parts) if parts else f"col{c}" for c, parts in prefixes.items()}


def _find_first_data_row(df: pd.DataFrame, sheet_label: str) -> int:
    """表头区行数在新旧制度、不同表格类型之间都不一样（"業務種類"/"Name of
    Insurer"锚点行之后，有的紧接着就是数据，有的还有2~3行细分表头才到数据），
    不能靠"锚点行+1"或固定行号锁定。真正稳妥的信号是：第一个"看起来像数据"的
    单元格——要么是真数字，要么是按公司拆分表里"没有业务"的占位符"-"（这是
    字符串，不是空值，不能用isna()判断，也不能靠"锚点+1"这种位置假设，因为
    这个占位符经常紧跟在表头锚点后面的头几家保险公司身上）。表头行本身的
    文字（"整付保費"、"(千港元)"等）都不是数字也不是"-"，不会被误判。"""
    n_rows, n_cols = df.shape
    for r in range(n_rows):
        for c in range(LABEL_COLS, n_cols):
            v = df.iloc[r, c]
            if isinstance(v, (int, float)) and not pd.isna(v):
                return r
            if isinstance(v, str) and v.strip() == "-":
                return r
    raise SheetStructureError(f"[{sheet_label}] 找不到任何数据行，表格结构跟预期不符")


def _parse_headline_grid(df: pd.DataFrame, sheet_label: str) -> list:
    """头条表（新造/有效业务市场总量）：行标签需要forward-fill（类别字母只在
    该类别第一行出现），一路走到唯一的总额行（精确匹配"總額"，不能用
    "contains"——"類別 A 總額"这类分类小计也含"總額"字样，但不是终点）。"""
    n_rows, n_cols = df.shape
    first_data_row = _find_first_data_row(df, sheet_label)

    header_rows = [r for r in range(first_data_row) if not _is_decorative_row(df, r)]
    if not header_rows:
        raise SheetStructureError(f"[{sheet_label}] 表头区域没有识别到任何有效表头行")
    metric_names = _build_metric_names(df, header_rows, n_cols)

    # 新制度表格里，同一个产品名（如"終身壽險"）会在"分紅業務"和"其他業務"
    # 两个分组下各出现一次——只用列1本身的文字做category会让两次出现撞成同一
    # 个category，把不同分组的数字错误地摞在一起。用last_section单独跟踪最近
    # 一个"全行metric都是空"的标签行（分紅業務/其他業務/相連長期这类分组标题
    # 正是这样：自己没有数字，数字都在它下面的子行里），当作分组前缀。
    # 已知局限：如果某个真实叶子行（如某产品当季数据全为空）恰好也全空，会被
    # 误当成分组标题、污染后续的last_section——这个demo没有再进一步排除这种
    # 情况，只影响这些空行之后、下一个真分组标题出现之前的小计行的category
    # 前缀，不影响任何真实数值本身的正确性。
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

        if own_label_1 in GRAND_TOTAL_TEXTS:
            category = own_label_1
        else:
            if not metric_values and own_label_1:
                last_section = own_label_1
            parts = [l for l in labels if l]
            if last_section and last_section not in parts:
                parts = [last_section] + parts
            category = " / ".join(parts)

        for c, v in metric_values:
            records.append({"category": category, "metric_name": metric_names[c], "value": v})
        if own_label_1 in GRAND_TOTAL_TEXTS:
            break
    else:
        raise SheetStructureError(
            f"[{sheet_label}] 扫到表尾也没找到唯一的总额行，"
            f"可能漏了数据或表格比预期长，不能默认已经解析完整"
        )
    return records


def _parse_insurer_grid(df: pd.DataFrame, sheet_label: str) -> list:
    """按保险公司拆分表（Table L1）：每一行是一家独立的保险公司，不能用
    forward-fill——某家公司中文名缺失（如"American Family Life"没有中文名）
    不代表它延续上一行的中文名，那是另一家公司。没有业务的公司用占位符"-"
    （字符串），产生零条记录，不是错误。表尾"市場總額/Market Total"是全市场
    合计，作为最后一条记录保留（可用来跟头条表的"總額"交叉核对）。"""
    n_rows, n_cols = df.shape
    first_data_row = _find_first_data_row(df, sheet_label)

    header_rows = [r for r in range(first_data_row) if not _is_decorative_row(df, r)]
    if not header_rows:
        raise SheetStructureError(f"[{sheet_label}] 表头区域没有识别到任何有效表头行")
    metric_names = _build_metric_names(df, header_rows, n_cols)

    records = []
    found_grand_total = False
    for r in range(first_data_row, n_rows):
        row = df.iloc[r]
        name_zh = _clean_zh(row.iloc[1])
        name_en = _clean_zh(row.iloc[0])
        insurer = name_zh or name_en
        if not insurer:
            continue  # 空行（分隔用），跳过

        metric_values = [
            (c, row.iloc[c]) for c in range(LABEL_COLS, n_cols)
            if isinstance(row.iloc[c], (int, float)) and not pd.isna(row.iloc[c])
        ]
        for c, v in metric_values:
            records.append({"category": insurer, "metric_name": metric_names[c], "value": v})

        if insurer in GRAND_TOTAL_TEXTS:
            found_grand_total = True
            break
    if not found_grand_total:
        raise SheetStructureError(
            f"[{sheet_label}] 扫到表尾也没找到'市場總額'行，"
            f"可能漏了保险公司或表格比预期长，不能默认已经解析完整"
        )
    return records


class ExcelParser:
    """解析单份长期业务Excel的头条表 + 按保险公司拆分表。"""

    def parse(self, file_path: Path) -> dict:
        """返回 {"new_business": [...], "in_force": [...],
        "new_business_by_insurer": [...], "schema_version": "pre_rbc"/"post_rbc"}
        三张表理论上schema_version应该一致，如果不一致会抛错——那说明这份文件
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

            # 按公司拆分表(Table L1)是可选的——2024Q3(RBC过渡期那一份文件)
            # 官网原始Excel里根本没有这张sheet，不能因为它缺失就让整份文件的
            # 头条表数据也解析失败，只是这一期没有按公司拆分的数据可用。
            nb_ins_sheet = None
            nb_ins_records = []
            try:
                nb_ins_sheet, _ = _find_sheet(xls.sheet_names, NB_BY_INSURER_CANDIDATES)
                nb_ins_df = xls.parse(nb_ins_sheet, header=None)
                nb_ins_records = _parse_insurer_grid(nb_ins_df, f"{file_path.name}/{nb_ins_sheet}")
            except SheetNotFoundError:
                pass

        return {
            "new_business": _parse_headline_grid(nb_df, f"{file_path.name}/{nb_sheet}"),
            "in_force": _parse_headline_grid(if_df, f"{file_path.name}/{if_sheet}"),
            "new_business_by_insurer": nb_ins_records,
            "schema_version": nb_schema,
            "nb_sheet_name": nb_sheet,
            "if_sheet_name": if_sheet,
            "nb_insurer_sheet_name": nb_ins_sheet,
        }
