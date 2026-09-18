"""
data_loader.py — Parse the four S1..S4 CSV files into clean, named tables.

Each CSV is divided into blocks, each starting with a letter-dot header such as
"A. ...", "B. ...", "C-APE. ...", "E-件数. ...". This module walks each file,
splits into blocks, and returns a dict {block_key: pandas.DataFrame}.

Usage:
    S1, S2, S3, S4 = load_all("S1-...csv", "S2-...csv", "S3-...csv", "S4-...csv")
    S1["A"]       # 目标达成率 DataFrame
    S2["A"]       # 业务细分年度汇总—全业务
    S3["A-APE"]   # 阶段周追踪漏斗 (APE)
"""
from pathlib import Path
import re
import pandas as pd
import io

HEADER_RE = re.compile(r"^([A-Z](?:-[^.\s]+)?)\.\s")


def _read_text_any_encoding(path: str) -> str:
    """Read a text file, trying common encodings in order.
    Handles both UTF-8 (with/without BOM) and GBK/GB18030 (Excel default on
    Chinese Windows). Raises UnicodeDecodeError only if all encodings fail.
    """
    data = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "cp936"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    # Last resort — replace undecodable bytes so we at least don't crash
    return data.decode("utf-8", errors="replace")


def parse_blocks(path: str) -> dict:
    raw = _read_text_any_encoding(path).splitlines()
    blocks = {}
    cur_lines, cur_key = [], None
    for line in raw:
        stripped = line.lstrip("\ufeff")
        m = HEADER_RE.match(stripped)
        if m:
            if cur_key is not None:
                blocks[cur_key] = cur_lines
            cur_key = m.group(1)
            cur_lines = []
        elif cur_key is not None:
            cur_lines.append(line)
    if cur_key is not None:
        blocks[cur_key] = cur_lines

    out = {}
    for key, lines in blocks.items():
        # remove note lines (📌 / replacement-char-corrupted 📌 / blank rows)
        data_lines = []
        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                continue
            # Normal 📌 marker
            if stripped.startswith("📌"):
                continue
            # Corrupted 📌 (shows up as ??? / \ufffd when GBK-decoded mixed-encoding file)
            first_char = stripped.lstrip('"').lstrip("'")[:1]
            if first_char in ("\ufffd", "?"):
                # likely the corrupted note row — check that it has very few
                # commas (a real data row always has 5+)
                if stripped.count(",") < 4 or "\ufffd\ufffd" in stripped or "???" in stripped:
                    continue
            data_lines.append(ln)
        if len(data_lines) < 2:
            continue
        csv_text = "\n".join(data_lines)
        try:
            df = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
        except Exception:
            continue
        # strip quotes / whitespace from every cell
        for c in df.columns:
            df[c] = df[c].astype(str).str.strip().str.strip('"')
        df.columns = [c.strip() for c in df.columns]
        # drop all-empty tail columns
        df = df.loc[:, ~(df.columns.str.match(r"^Unnamed"))]
        out[key] = df
    return out


def num(v) -> float:
    """Turn a messy string like '1,234', '32.2%', '\"45,864,040\"' into float."""
    if v is None:
        return 0.0
    s = str(v).strip().strip('"').replace(",", "").replace("%", "")
    if s in ("", "-", "—", "nan", "None"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_all(s1_path, s2_path, s3_path, s4_path):
    return (parse_blocks(s1_path), parse_blocks(s2_path),
            parse_blocks(s3_path), parse_blocks(s4_path))
