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

版本判断：三种来源类型。
- `dir_latest_version`：整个目录镜像，同一L3编码可能有多个历史版本文件，
  复用`table_reader.py`的`group_latest_versions()`只镜像最新版本。
- `file_latest_version`：单份材料但版本号写在文件名末尾（`..._V3.44.xlsx`
  这种紧贴扩展名的写法），同目录下按`名称前缀+版本号`匹配同款文件，自动
  取最大版本号，不需要人工去改这里的文件名。
- `file`：版本号不在文件名末尾（例如`DICT_..._V2_项目交付.md`、
  `2026-07-20_68L3岗位族归属设计_v6.1_SUBMITTED.md`——后面还带日期/状态
  后缀，版本判断跟"文件名前缀"纠缠在一起，自动匹配容易把无关文件误判成
  "新版本"），只能整份镜像；这批文件出新版本时，**新文件名需要人工加进
  `VNW_REFERENCE_SOURCES`**，这里不会自动发现，是本机制唯一的人工触点
  （2026-07-29 Jasper提出的"非白名单文件谁来盯更新"疑问，答案就是这条：
  内容更新走每日自动同步，但"这份材料存在新版本/换了文件名"这件事，仍然
  需要维护这些文件的同事或Jasper自己注意到并说一声）。

历史版本清理：`_prune_stale()`在每次同步后，删除manifest里记录过、但本轮
不再产生的镜像文件（比如L3蓝图V1.0→V1.1后，vault里的V1.0旧文件会被移除，
不会永久堆积）。只清理这个脚本自己写进manifest的文件，不碰README.md/
_manifest.json或人工放进这个目录的其他内容。

增量判断：复用`file_diff.py`的`hash_file()`按内容哈希比对，没变化的文件
不重复写入（vault侧mtime保持不变，git diff也不会出现无意义的改动）。
"""

import json
import re
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

# 每条：(来源, 类型[, 额外参数])。
# - dir_latest_version：来源=目录，按group_latest_versions()只取每个编码的
#   最新版本。
# - file_latest_version：来源=目录，额外参数=文件名前缀（版本号紧跟在
#   前缀后、扩展名前，如"D1_价值节点清单_V"+"3.44"+".xlsx"），自动匹配
#   同前缀文件里版本号最大的一份，出新版本不需要改这里。
# - file：来源=精确文件路径，版本号不在文件名末尾、自动匹配不安全，只能
#   整份镜像，出新版本需要人工把新文件名加进这里。
VNW_REFERENCE_SOURCES = [
    (EA_PROJECT_ROOT / "02_过程成果-工作产出/L3流程库", "dir_latest_version"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/治理规范/DICT_流程数据库数据字典_V2_项目交付.md", "file"),
    # 2026-07-29新增(Jasper确认路径)：价值节点(VN)+KPI权威数据。
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据", "file_latest_version", "D1_价值节点清单_V"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据", "file_latest_version", "D2_价值节点_L3映射表_V"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据", "file_latest_version", "kpi_registry_154_v"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据", "file_latest_version", "kpi_crosswalk_154_to_43_v"),
    (EA_PROJECT_ROOT / "03_发布成果-交付物/权威数据/dim_kpi_v3.3_权威层.csv", "file"),
    (EA_PROJECT_ROOT / "02_过程成果-工作产出/规则分析（Jasper）/Agent与Skill体系", "file_latest_version", "L4两阶段复核_全量368条_合并版_v"),
    (EA_PROJECT_ROOT / "HR工作材料/D_EA项目组织优化/2026-07-20_68L3岗位族归属设计_v6.1_SUBMITTED.md", "file"),
]

VERSION_SUFFIX_RE = re.compile(r"^(\d+(?:\.\d+)*)(\.\w+)$")


def _latest_by_prefix(dir_path: Path, prefix: str) -> Path | None:
    """在dir_path里找文件名以prefix开头、prefix后紧跟"版本号+扩展名"的文件，
    返回版本号最大的一份。跟table_reader.py的group_latest_versions()同一
    套"版本号紧贴扩展名"假设，只是这里从一个已知前缀出发，不需要在混杂着
    大量其他文档的`权威数据/`目录里做全目录分组。"""
    best: tuple[tuple, Path] | None = None
    for f in Path(dir_path).glob(f"{prefix}*"):
        rest = f.name[len(prefix):]
        m = VERSION_SUFFIX_RE.match(rest)
        if not m:
            continue
        ver_tuple = tuple(int(x) for x in m.group(1).split("."))
        if best is None or ver_tuple > best[0]:
            best = (ver_tuple, f)
    return best[1] if best else None


def _load_manifest() -> Dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"files": {}}


def _save_manifest(manifest: Dict):
    manifest["updated_at"] = datetime.now().isoformat()
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _sync_one_file(src: Path, dest_dir: Path, manifest: Dict, summary: Dict, produced: set):
    if not src.exists():
        summary["missing"].append(str(src))
        return
    dest = dest_dir / src.name
    produced.add(dest.name)
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


def _prune_stale(manifest: Dict, produced: set, summary: Dict, dry_run: bool) -> None:
    """删除manifest里记录过、但本轮不再产生的镜像文件——版本升级后旧版本
    不会永久堆积在vault里。只删这个脚本自己写进manifest的文件。"""
    stale_srcs = [
        src for src, entry in manifest["files"].items()
        if Path(entry["dest"]).name not in produced
    ]
    for src in stale_srcs:
        entry = manifest["files"][src]
        dest_path = VAULT_DEST_DIR / entry["dest"]
        if dry_run:
            summary["changed"].append(f"[dry-run会清理旧版本]: {entry['dest']}")
            continue
        if dest_path.exists():
            dest_path.unlink()
        del manifest["files"][src]
        summary["changed"].append(f"清理旧版本: {entry['dest']}")


def sync_all(dry_run: bool = False) -> Dict:
    manifest = _load_manifest()
    summary = {"changed": [], "unchanged": 0, "missing": [], "dry_run": dry_run}
    produced: set = set()

    for entry in VNW_REFERENCE_SOURCES:
        source, kind = entry[0], entry[1]

        if kind == "file":
            if dry_run:
                produced.add(source.name)
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
            _sync_one_file(source, VAULT_DEST_DIR, manifest, summary, produced)

        elif kind == "file_latest_version":
            prefix = entry[2]
            target = _latest_by_prefix(source, prefix)
            if target is None:
                summary["missing"].append(f"{source}/{prefix}*")
                continue
            if dry_run:
                produced.add(target.name)
                old_hash = manifest["files"].get(str(target), {}).get("hash")
                new_hash = hash_file(target)
                if old_hash != new_hash:
                    summary["changed"].append(f"[dry-run会更新]: {target.name}")
                else:
                    summary["unchanged"] += 1
                continue
            _sync_one_file(target, VAULT_DEST_DIR, manifest, summary, produced)

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
                    produced.add(f.name)
                    old_hash = manifest["files"].get(str(f), {}).get("hash")
                    new_hash = hash_file(f)
                    if old_hash != new_hash:
                        summary["changed"].append(f"[dry-run会更新]: {f.name}")
                    else:
                        summary["unchanged"] += 1
                    continue
                _sync_one_file(f, VAULT_DEST_DIR, manifest, summary, produced)

    _prune_stale(manifest, produced, summary, dry_run)

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
