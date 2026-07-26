#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方法论转正Agent · 待审区候选转正/拒绝工具。

这是"raw/只能人工放入资料"这条规则的唯一合规写入通道——本工具本身不
自动运行、不被launchd调度，必须由人工在命令行显式敲一条命令，逐条针对
`_待审_GitHub发现/`里的候选文件做决定。这跟"人工直接打开候选文件、复制
内容手动另存到raw/"是等价的两条路径，本工具只是帮人工把frontmatter字段
补全这件容易漏填的事自动化，转正/拒绝的判断权始终在人工。

不是唯一路径：待审区的候选文件本身就是完整可读的md（摘要+原文摘录+链接），
Jasper随时可以完全绕开本工具手动操作。
"""

import argparse
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

VAULT_PENDING_DIR = Path(
    "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault"
    "/方法论知识库/行业学习/_待审_GitHub发现"
)
VAULT_RAW_DIR = Path(
    "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault"
    "/方法论知识库/行业学习/raw"
)
PROCESSED_DIR = VAULT_PENDING_DIR / "_已处理"

DEFAULT_STALENESS_DAYS = 90

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def _parse_frontmatter(text: str) -> tuple:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("候选文件没有合法的frontmatter")
    fm_text, body = m.group(1), m.group(2)
    fm = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = v.strip()
    return fm, body


def _field(fm: dict, key: str, override: str | None) -> str:
    if override:
        return override
    return fm.get(key, "")


def promote(filename: str, info_type_override=None, evidence_basis_override=None, staleness_days=None):
    src = VAULT_PENDING_DIR / filename
    if not src.exists():
        print(f"❌ 候选文件不存在: {src}")
        return 1
    text = src.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)

    # 从候选正文里提取"# 摘要"和"## 原始信息"两段，作为raw/新文件的正文来源
    summary_m = re.search(r"# 摘要\n\n(.+?)\n\n## 原始信息", body, re.S)
    origin_m = re.search(r"## 原始信息\n\n(.+?)\n\n## 人工确认后如何操作", body, re.S)
    summary = summary_m.group(1).strip() if summary_m else ""
    origin = origin_m.group(1).strip() if origin_m else ""

    collected_at = datetime.now().isoformat()
    staleness_days = staleness_days or DEFAULT_STALENESS_DAYS
    staleness_review_date = (datetime.now() + timedelta(days=staleness_days)).strftime("%Y-%m-%d")
    source_url = fm.get("source_url", "")
    info_type = _field(fm, "info_type_suggestion", info_type_override)
    evidence_basis = _field(fm, "evidence_basis_suggestion", evidence_basis_override)

    raw_title = fm.get("source_repo", filename)
    raw_filename = f"{datetime.now().strftime('%Y-%m-%d')}_GitHub_{re.sub(r'[/\\\\]', '-', raw_title)}.md"
    raw_path = VAULT_RAW_DIR / raw_filename

    raw_content = f"""---
source_url: {source_url}
collected_at: {collected_at}
staleness_review_date: {staleness_review_date}
info_type: {info_type}
evidence_basis: {evidence_basis}
---

# {raw_title}

{summary}

## 原始信息

{origin}
"""
    raw_path.write_text(raw_content, encoding="utf-8")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    text = text.replace("status: pending_review", "status: promoted", 1)
    (PROCESSED_DIR / filename).write_text(text, encoding="utf-8")
    src.unlink()

    print(f"✅ 已转正到 raw/{raw_filename}")
    print(f"   候选文件已归档到 _已处理/{filename}")
    return 0


def reject(filename: str, reason: str):
    src = VAULT_PENDING_DIR / filename
    if not src.exists():
        print(f"❌ 候选文件不存在: {src}")
        return 1
    text = src.read_text(encoding="utf-8")
    text = text.replace("status: pending_review", f"status: rejected", 1)
    text = text.rstrip("\n") + f"\n\n## 拒绝理由\n\n{reason}\n"

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / filename).write_text(text, encoding="utf-8")
    src.unlink()

    print(f"⏭️ 已拒绝并归档到 _已处理/{filename}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="待审区候选转正/拒绝")
    parser.add_argument("filename", help="_待审_GitHub发现/ 下的候选文件名")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--promote", action="store_true", help="确认转正到raw/")
    group.add_argument("--reject", action="store_true", help="拒绝，不转正")
    parser.add_argument("--reason", default="", help="拒绝理由（--reject时建议填写）")
    parser.add_argument("--info-type", default=None, help="覆盖info_type建议值")
    parser.add_argument("--evidence-basis", default=None, help="覆盖evidence_basis建议值")
    parser.add_argument("--staleness-days", type=int, default=None, help="覆盖默认90天审核周期")
    args = parser.parse_args()

    if args.promote:
        return promote(args.filename, args.info_type, args.evidence_basis, args.staleness_days)
    return reject(args.filename, args.reason or "（未填写理由）")


if __name__ == "__main__":
    raise SystemExit(main())
