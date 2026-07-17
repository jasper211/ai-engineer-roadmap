#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：把Desktop唯一真源vault单向同步成iCloud镜像副本，供手机端Obsidian读取。

背景（2026-07-17架构调整）：vault原本直接建在iCloud专属容器里，Jasper提出
要把知识库分享给其他协同者、且iCloud同步延迟影响OB自己读写的实时性，改为
Desktop为唯一真源，iCloud容器改为单向同步生成的镜像——**不要在iCloud镜像
路径下直接编辑，下次同步会被覆盖**。

排除规则（复用.gitignore的教训）：
- .git：Desktop真源自己的版本控制，镜像副本不需要
- .smart-env：Smart Connections插件本地缓存，2026-07-16实测过443MB/8355个
  文件是导致iCloud同步卡死的元凶，插件在任何vault位置运行都会自动重建，
  不需要跨端同步
- .obsidian：应用本地会话状态（workspace布局/最近打开/插件运行时缓存），
  两端各自维护自己的，不做跨端覆盖——iCloud镜像文件夹需要一份能让手机端
  识别成vault的最小.obsidian，用--bootstrap一次性从Desktop复制过去，
  之后的常规同步不再碰这个文件夹
- .DS_Store/__pycache__：系统/语言运行时垃圾文件

不是双向同步：iCloud端如果被手动改过内容，下次跑同步会被Desktop版本覆盖
（Jasper已确认接受这个取舍——Desktop是唯一真源，手机端定位为"查看为主"）。
"""

import argparse
import shutil
import sys
from pathlib import Path

DESKTOP_VAULT = Path("/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault")
ICLOUD_VAULT = Path("/Users/a112233/Library/Mobile Documents/iCloud~md~obsidian/Documents/第二大脑Obsidian")

EXCLUDE_DIRS = {".git", ".smart-env", ".obsidian", "__pycache__"}
EXCLUDE_FILES = {".DS_Store"}


def bootstrap_obsidian_config():
    """一次性把Desktop真源的.obsidian复制到iCloud镜像，让手机端能把这个
    文件夹识别成vault打开。只在iCloud端完全没有.obsidian时才做，不覆盖
    已存在的（避免清掉手机端自己的会话状态/插件配置）。"""
    dst = ICLOUD_VAULT / ".obsidian"
    if dst.exists():
        print(f"iCloud端已有.obsidian（{dst}），跳过bootstrap，避免覆盖手机端自己的配置")
        return
    src = DESKTOP_VAULT / ".obsidian"
    if not src.exists():
        print("Desktop真源没有.obsidian，无法bootstrap")
        return
    shutil.copytree(src, dst)
    print(f"已bootstrap .obsidian 到 {dst}（仅此一次，后续同步不再触碰这个文件夹）")


def sync(dry_run: bool = False) -> dict:
    ICLOUD_VAULT.mkdir(parents=True, exist_ok=True)
    stats = {"copied": 0, "skipped_unchanged": 0, "removed": 0}

    src_files = set()
    for src_path in DESKTOP_VAULT.rglob("*"):
        rel = src_path.relative_to(DESKTOP_VAULT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if src_path.name in EXCLUDE_FILES:
            continue
        if src_path.is_dir():
            continue
        src_files.add(rel)
        dst_path = ICLOUD_VAULT / rel
        if dst_path.exists() and dst_path.stat().st_mtime >= src_path.stat().st_mtime:
            stats["skipped_unchanged"] += 1
            continue
        if dry_run:
            stats["copied"] += 1
            continue
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        stats["copied"] += 1

    # 镜像端多出来的文件（Desktop真源已删除的）也要清掉，保持真正镜像
    for dst_path in ICLOUD_VAULT.rglob("*"):
        rel = dst_path.relative_to(ICLOUD_VAULT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if dst_path.name in EXCLUDE_FILES:
            continue
        if dst_path.is_dir():
            continue
        if rel not in src_files:
            if not dry_run:
                dst_path.unlink()
            stats["removed"] += 1

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Desktop真源 -> iCloud镜像 单向同步")
    parser.add_argument("--bootstrap", action="store_true", help="首次运行：复制.obsidian让手机端能识别vault")
    parser.add_argument("--dry-run", action="store_true", help="只统计会同步什么，不实际写入")
    args = parser.parse_args()

    if not DESKTOP_VAULT.exists():
        print(f"错误：Desktop真源不存在 {DESKTOP_VAULT}", file=sys.stderr)
        sys.exit(1)

    if args.bootstrap:
        bootstrap_obsidian_config()

    result = sync(dry_run=args.dry_run)
    prefix = "将同步" if args.dry_run else "已同步"
    print(f"{prefix}: 新增/更新 {result['copied']} | 跳过未变化 {result['skipped_unchanged']} | 清理已删除 {result['removed']}")
