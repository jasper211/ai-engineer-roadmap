#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ppt_data_loader.py — 读取 07_接入记忆_Integrate_Memory/data/ 下 S1-S9 各板块CSV，
供 PPT 生成技能使用。

新版数据布局是"一个专题视角一个文件夹，一个字母板块一个CSV文件"（例如
S1_总览仪表盘/A.csv、S3_执行管理端/E_ape.csv、S9_代理人与KA业务/H_批核_APE.csv），
跟旧版"一个S表一个CSV、内部用字母块头分隔多个板块"的单文件格式不同——不复用旧版
data_loader.py 的字母块头解析逻辑，直接按文件名 stem 建字典更简单可靠。

调用方按实际文件名 stem 取用（见各 build_slideN() 注释里列出的具体 key），
本模块不对文件名做归一化，避免猜错命名规则。
"""
from pathlib import Path
import pandas as pd


def load_sheet(sheet_dir: Path) -> dict:
    """返回 {文件名stem: DataFrame}，例如 'A'、'E_ape'、'H_批核_APE'。
    dtype=str 保留原始字符串，数值清洗统一走 num()。"""
    out = {}
    for csv_path in sorted(Path(sheet_dir).glob("*.csv")):
        out[csv_path.stem] = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    return out


def load_all(data_root: Path, sheets: list = None) -> dict:
    """返回 {'S1_总览仪表盘': {letter: df, ...}, 'S2_业务端视角': {...}, ...}。
    sheets 非None时只加载指定的文件夹名列表。"""
    data_root = Path(data_root)
    out = {}
    for d in sorted(data_root.iterdir()):
        if not d.is_dir() or not d.name.startswith("S"):
            continue
        if sheets is not None and d.name not in sheets:
            continue
        out[d.name] = load_sheet(d)
    return out


def num(v) -> float:
    """把 '1,234' / '32.2%' / '"45,864,040"' 这类脏字符串转成float，跟旧版
    data_loader.py::num() 同一套容错规则，保持数值清洗口径一致。"""
    if v is None:
        return 0.0
    s = str(v).strip().strip('"').replace(",", "").replace("%", "")
    if s in ("", "-", "—", "nan", "None"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def row_by(df: pd.DataFrame, key_col: str, key_val: str) -> dict:
    """按第一列(或指定key_col)取值等于key_val的那一行，返回 {列名: 原始字符串} 字典。
    找不到返回空字典。"""
    matches = df[df[key_col].astype(str).str.strip() == key_val]
    if matches.empty:
        return {}
    return matches.iloc[0].to_dict()
