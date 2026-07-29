#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：VNW引用原件同步——把VNW项目自检需要、但性质上不该走OB白名单原子
提炼的EA项目源文件（L3流程蓝图/D1-D6打分方法论定义/D1-D6全量打分表/
岗位L4映射材料），原样镜像进vault的`EA流程架构项目/_VNW引用原件/`，
不做任何提炼、不改内容，只做"存在性+最新版本"同步。

背景（2026-07-28 Jasper裁定）：这批内容跟现有白名单收录的"成型的方法论
文档和结果文档"性质不同——是项目组成员产出的工作材料（L3蓝图、数据字典、
打分表、HR岗位设计），不该被LLM二次提炼成知识原子，但VNW需要能通过OB
检索到这些内容的最新版本。跟`方法论知识库/行业学习/raw/`同理——都是
"人工/机制放入原文，AI只读不改"，但这里是自动同步机制放入，不是Jasper
手工放入，所以单独建目录，不跟raw/混用。

版本判断：L3流程库是目录镜像，同一L3编码可能有多个历史版本文件（如
V1.0/V1.1/V1.2），复用`table_reader.py`的`group_latest_versions()`同款
正则规则，只镜像最新版本，不搬运历史版本进vault。DICT数据字典/D1-D6
打分表/HR岗位设计文档是单文件镜像，按最新mtime直接覆盖同步。

增量判断：复用`file_diff.py`的`hash_file()`按内容哈希比对，没变化的文件
不重复写入（vault侧mtime保持不变，git diff也不会出现无意义的改动）。
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "05_集成工具_Integrate_Tools"))

from tools.file_diff import hash_file
from tools.table_reader import group_latest_versions

EA_PROJECT_ROOT = Path("/Users/a112233/Desktop/流程架构项目_jasper")
VAULT_DEST_DIR = Path(
    "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault/EA流程架构项目/_VNW引用原件"
)
MANIFEST_PATH = VAULT_DEST_DIR / "_manifest.json"

# 每条：(来源, 类型)。dir_latest_version=按group_latest_versions()只取每个
# 编码的最新版本；file=单文件直接镜像。新增引用源只需要在这里加一条，
# 不需要改下面的同步逻辑。
VNW_REFERENCE_SOURCES = [
    (EA_PROJECT_ROOT / "02_过程成果-工作产出/L3流程库", "dir_latest_version"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/治理规范/DICT_流程数据库数据字典_V2_项目交付.md", "file"),
    (EA_PROJECT_ROOT / "02_过程成果-工作产出/规则分析（Jasper）/Agent与Skill体系/L4两阶段复核_全量368条_合并版_v1.0.csv", "file"),
    (EA_PROJECT_ROOT / "HR工作材料/D_EA项目组织优化/2026-07-20_68L3岗位族归属设计_v6.1_SUBMITTED.md", "file"),
    # 2026-07-29新增(Jasper确认路径)：价值节点(VN)+KPI权威数据，全部是版本号
    # 直接写死在文件名里的单文件，没有像L3流程库那样的"同编码多版本目录"
    # 结构，只能"file"整份镜像；出新版本时需要手动把这里的文件名换成新版本。
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据/D1_价值节点清单_V3.44.xlsx", "file"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据/D2_价值节点_L3映射表_V2.11.csv", "file"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据/dim_kpi_v3.3_权威层.csv", "file"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据/kpi_registry_154_v2.1.csv", "file"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据/kpi_crosswalk_154_to_43_v2.1.csv", "file"),
]


def _load_manifest() -> Dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"files": {}}


def _save_manifest(manifest: Dict):
    manifest["updated_at"] = datetime.now().isoformat()
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _sync_one_file(src: Path, dest_dir: Path, manifest: Dict, summary: Dict):
    if not src.exists():
        summary["missing"].append(str(src))
        return
    dest = dest_dir / src.name
    new_hash = hash_file(src)
    old_entry = manifest["files"].get(str(src))
    if old_entry and old_entry.get("hash") == new_hash and dest.exists():
        summary["unchanged"] += 1
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    manifest["files"][str(src)] = {
        "dest": str(dest.relative_to(VAULT_DEST_DIR)),
        "hash": new_hash,
        "synced_at": datetime.now().isoformat(),
    }
    action = "更新" if old_entry else "新增"
    summary["changed"].append(f"{action}: {src.name}")


def sync_all(dry_run: bool = False) -> Dict:
    manifest = _load_manifest()
    summary = {"changed": [], "unchanged": 0, "missing": [], "dry_run": dry_run}

    for source, kind in VNW_REFERENCE_SOURCES:
        if kind == "file":
            if dry_run:
                if not source.exists():
                    summary["missing"].append(str(source))
                else:
                    old_hash = manifest["files"].get(str(source), {}).get("hash")
                    new_hash = hash_file(source)
                    if old_hash != new_hash:
                        summary["changed"].append(f"[dry-run会更新]: {source.name}")
                    else:
                        summary["unchanged"] += 1
                continue
            _sync_one_file(source, VAULT_DEST_DIR, manifest, summary)

        elif kind == "dir_latest_version":
            if not source.exists():
                summary["missing"].append(str(source))
                continue
            # 只取"流程蓝图_L3-*.md"命名的真正蓝图文件——L3流程库/这个目录里
            # 混杂着大量分析报告/构建说明/研究笔记等其他.md文件（真实统计过：
            # 240个.md里只有81个是流程蓝图_L3-前缀），不过滤会把无关内容也
            # 同步进vault，偏离VNW这次要的"L3蓝图完整性核对"范围。
            all_files = sorted(source.glob("流程蓝图_L3-*.md"))
            latest_files = group_latest_versions(all_files)
            for f in latest_files:
                if dry_run:
                    old_hash = manifest["files"].get(str(f), {}).get("hash")
                    new_hash = hash_file(f)
                    if old_hash != new_hash:
                        summary["changed"].append(f"[dry-run会更新]: {f.name}")
                    else:
                        summary["unchanged"] += 1
                    continue
                _sync_one_file(f, VAULT_DEST_DIR, manifest, summary)

    if not dry_run:
        _save_manifest(manifest)

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = sync_all(dry_run=args.dry_run)
    print(f"{'[dry-run] ' if args.dry_run else ''}变更: {len(result['changed'])} | "
          f"未变化: {result['unchanged']} | 源缺失: {len(result['missing'])}")
    for c in result["changed"]:
        print(f"  {c}")
    if result["missing"]:
        print("缺失的源文件:")
        for m in result["missing"]:
            print(f"  {m}")
