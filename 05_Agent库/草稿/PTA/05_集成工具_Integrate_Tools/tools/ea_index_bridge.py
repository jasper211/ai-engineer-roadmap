#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：EA全库索引桥接——PTA 作为 Mark「OB-000」EA 全文索引器的薄客户端。

跟 tools/ob_bridge.py 同一种设计：subprocess 调用外部脚本，不 import 它的代码
（这个索引器本来就是 Mark 团队独立维护的资产，跟 PTA/OB 各自的 05/06/07 编号
包体系毫无关系，也不需要考虑 sys.modules 缓存污染问题——纯粹是"这份索引不是
PTA 的东西，PTA 只是个薄客户端"）。索引脚本/数据库不存在、查询失败、超时，
一律优雅返回 None/降级结果，不抛异常、不影响任务看板其他功能正常渲染。

背景：Mark 的 AI 执行终端在 2026-08-01 为 EA 项目全库（约3065个受管文件）建了
一份 SQLite FTS5（trigram）全文索引，详见 EA 项目
`08_任务与跟进/AI上下文/index_EA全库知识入口_v1.0.md`。这份索引不做语义/向量
检索，但胜在覆盖面（PTA 的 daily_sensing 只看"最近变化"，Jasper 自己的 OB
Agent 白名单很窄，两者都不覆盖"这份文件在全库范围内还跟哪些文档有关系"这个
问题）。EA 治理类文档普遍靠显式编号互相引用（CUR-/AUD25-/AUD21-/DEC-ACC.../
GOV-T-/ACC- 等），这些编号本身就是确定性的关联线索——不需要语义判断，直接
把编号当关键词去全库搜，命中的文件就是"关联文档"，比 LLM 语义检索更便宜也
更可验证（可以拿真实编号复现结果，不是模型的主观判断）。
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

INDEXER_SCRIPT_RELATIVE = Path("06_Scripts库/草稿/已完成_OB000_EA全库索引器_v0.1.py")

DEFAULT_TIMEOUT = 15  # 单次query在本地是FTS5关键词查询，实测远小于1秒；
                       # 留白余量给冷启动（首次连接334MB的db文件）用，不是指望真的等满

# 覆盖 EA 治理文档目前实际在用的编号体系（见 EA接管_Mark决策队列_v0.1.md /
# EA接管_审计问题闭环台账_v0.1.md 等真实文件）。只做字面正则匹配，不做语义
# 判断——找不到已知模式的编号，宁可漏掉也不误报。
REFERENCE_ID_PATTERNS = [
    re.compile(r"\bCUR-\d+\b"),
    re.compile(r"\bAUD2[15]-\d+\b"),
    re.compile(r"\bDEC-ACC\d+-\d+\b"),
    re.compile(r"\bGOV-T-\d+\b"),
    re.compile(r"\bACC-\d+\b"),
    re.compile(r"\bBASE-\d+\b"),
    re.compile(r"\bRPT-\d{8}-\d+\b"),
]


def find_indexer_script(project_root: Path) -> Optional[Path]:
    """索引脚本只在 EA 项目里存在；其他项目（Rw/Jasper工作文档）调用这个桥接
    自然拿到 None，调用方据此优雅跳过"关联文档"这个功能，不报错。"""
    candidate = Path(project_root) / INDEXER_SCRIPT_RELATIVE
    return candidate if candidate.exists() else None


def extract_reference_ids(text: str) -> List[str]:
    """从文件全文里提取治理编号，按首次出现顺序去重（不排序，保留文档里
    "先提到哪个编号"这层信息，方便人工核对时按阅读顺序对照）。"""
    if not text:
        return []
    found: List[str] = []
    for pattern in REFERENCE_ID_PATTERNS:
        for match in pattern.findall(text):
            if match not in found:
                found.append(match)
    return found


def query_related_by_ids(project_root: Path, ids: List[str], limit_per_id: int = 5,
                          timeout: int = DEFAULT_TIMEOUT) -> Optional[List[Dict]]:
    """对每个编号各查一次 Mark 的索引（`query <id> --json`），按文件路径合并
    去重——同一份文档命中多个编号时，matched_ids 累积成列表，excerpt 保留第一次
    命中的片段（够定位就行，不需要为每个编号都存一份摘录）。

    只要有任意一个编号查询成功就返回列表（哪怕只查到 1 个编号有结果）；索引
    脚本不存在，或全部编号查询都失败（脚本崩、db损坏等），才返回 None——
    这个 None 是"这个功能这次不可用"的信号，不是"关联文档是空列表"。
    """
    script = find_indexer_script(project_root)
    if script is None or not ids:
        return None

    aggregated: Dict[str, Dict] = {}
    any_success = False
    for ref_id in ids:
        try:
            result = subprocess.run(
                ["python3", str(script), "--root", str(project_root),
                 "query", ref_id, "--limit", str(limit_per_id), "--json"],
                capture_output=True, text=True, timeout=timeout,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode != 0:
            continue
        try:
            hits = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
        any_success = True
        for hit in hits:
            path = hit.get("path", "")
            if not path:
                continue
            entry = aggregated.setdefault(path, {
                "path": path, "extension": hit.get("extension", ""),
                "matched_ids": [], "excerpt": hit.get("excerpt", ""),
            })
            if ref_id not in entry["matched_ids"]:
                entry["matched_ids"].append(ref_id)

    if not any_success:
        return None
    return sorted(aggregated.values(), key=lambda d: (-len(d["matched_ids"]), d["path"]))
