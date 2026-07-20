#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：批量+增量概念笔记提炼编排——把 project_filters（候选筛选）、file_diff
（增量检测）、concept_note_extraction（单文件提炼）、atom_embeddings（语义
去重）串起来，支持"项目文件持续更新，OB 定期发现变化并提炼"这条完整链路。

铁律（2026-07-16 跟 Jasper 对齐）：本模块对目标项目文件只读，不修改、不移动、
不删除——所有写操作只发生在 vault（知识原子）和 OB 自己的工作区（扫描快照/
embedding 缓存）。

过时原子标记（2026-07-16 新增，02层规则分析开工前先补）：源文档更新/删除后，
旧版本产出但新版本不再包含的原子，此前会静默变成孤儿——vault 里留着过时
内容，没人知道该不该删。这里的做法：快照除了记 hash，还记"这份文档上次产出
了哪些原子（atom_slugs）"；文档变更时对比新旧 atom_slugs 集合，旧有新无的
原子调用 ConceptNoteExtractor.mark_atom_stale() 追加"待复核"标记（不自动
删除——对 vault 内容做删除是更大的动作，不该由批量任务自动执行，交给 Jasper
自己决定）；文档被删除时同理，把它名下全部原子都标记待复核。

处理顺序遵循 project_filters 返回的优先级顺序（不是 diff_snapshots 默认的
字母排序）——EA 项目要求按 00→03→08→01→02/规则分析（Jasper）的价值分层
顺序处理，这里用"从优先级列表里筛出 added/changed 子集，保留原顺序"的方式
实现，不直接用 diff_snapshots 返回的已排序列表。
"""

from pathlib import Path
from typing import Dict, List, Optional

from tools import file_diff, project_filters
from tools.atom_embeddings import AtomEmbeddingStore
from skills.concept_note_extraction import ConceptNoteExtractor
from memory import workspace as ws


class BatchConceptExtractor:
    """给定一个项目，扫描候选文件、增量比对、逐个提炼知识原子。"""

    def __init__(self, project_name: str, project_root: str, vault_path: str,
                 vector_mjs: str, api_key: str):
        self.project_name = project_name
        self.project_root = project_root
        self.vault_path = vault_path
        self.vector_mjs = vector_mjs
        self.api_key = api_key

    def scan_and_extract(self, dry_run: bool = False, max_files: Optional[int] = None) -> Dict:
        """完整流程：加载快照 → 筛选候选 → 增量比对 → 按优先级顺序处理 → 更新快照。

        dry_run=True 时只报告"将会处理哪些文件"，不调用 LLM、不写 vault、
        不更新快照——用于第一次对着真实项目验证筛选规则/增量逻辑是否符合
        预期，不产生真实 API 费用。
        """
        candidates = project_filters.get_candidates(self.project_name, self.project_root)

        old_snapshot = ws.load_extraction_snapshot(self.project_name)
        new_snapshot = file_diff.snapshot_files(self.project_root, candidates)
        diff = file_diff.diff_snapshots(old_snapshot, new_snapshot)

        added_set = set(diff.added)
        changed_set = set(diff.changed)
        # 按 candidates 的优先级顺序筛出待处理文件，不用 diff 自己排过序的列表
        to_process = [f for f in candidates if f in added_set or f in changed_set]
        if max_files is not None:
            to_process = to_process[:max_files]

        summary = {
            "project": self.project_name,
            "scanned": len(candidates),
            "added": len(diff.added),
            "changed": len(diff.changed),
            "removed": len(diff.removed),
            "to_process": len(to_process),
            "dry_run": dry_run,
            "files": list(to_process),
            "processed": 0,
            "atoms_created": 0,
            "atoms_updated": 0,
            "atoms_needs_calibration": 0,
            "atoms_marked_stale": 0,
            "errors": [],
        }

        if dry_run:
            return summary

        embedding_store = AtomEmbeddingStore(
            cache_dir=ws.atom_embeddings_dir(self.project_name),
            project_name=self.project_name,
            vector_mjs=self.vector_mjs,
        )
        extractor = ConceptNoteExtractor(
            vault_path=self.vault_path,
            project_name=self.project_name,
            api_key=self.api_key,
            embedding_store=embedding_store,
        )

        # 处理完一个文件立刻更新快照里对应的条目——中断/分批执行（max_files）
        # 不会导致已成功处理过的文件在下次运行时被重复提炼
        running_snapshot = dict(old_snapshot)

        table_extensions = {".xlsx", ".csv"}
        for rel_path in to_process:
            abs_path = Path(self.project_root) / rel_path
            try:
                if abs_path.suffix.lower() in table_extensions:
                    # 表格（03层权威数据）走专门的行批量提炼路径，不读成纯文本
                    # 喂给文档提示词——见concept_note_extraction.py.process_table_file()
                    result = extractor.process_table_file(rel_path, abs_path)
                else:
                    content = file_diff.read_content_truncated(abs_path, max_chars=20000)
                    result = extractor.process_document(rel_path, content)
                summary["processed"] += 1
                new_atom_slugs = []
                for r in result["results"]:
                    if r["action"] == "created":
                        summary["atoms_created"] += 1
                    elif r["action"] == "needs_calibration":
                        summary["atoms_needs_calibration"] += 1
                    else:
                        summary["atoms_updated"] += 1
                    new_atom_slugs.append(Path(r["path"]).stem)
                # 表格文件的分批错误（process_table_file内部已经per-batch
                # try/except过，不会抛异常到这里）——仍然要让Jasper看到哪些
                # 批次没成功，即便文件整体判定为"已处理"（已成功的批次不该
                # 因为个别批次失败就被当成整个文件没处理过，见函数内注释）
                for block_error in result.get("errors", []):
                    summary["errors"].append({"file": rel_path, **block_error})

                # 这份文档如果是"变更"（不是首次新增），对比它上次产出的原子
                # 集合——旧有新无的，说明新版本内容不再支持这个原子，标记待复核
                old_atom_slugs = old_snapshot.get(rel_path, {}).get("atom_slugs", [])
                stale_slugs = set(old_atom_slugs) - set(new_atom_slugs)
                for slug in stale_slugs:
                    if extractor.mark_atom_stale(slug, f"源文档「{rel_path}」已更新，此原子未出现在最新提炼结果中"):
                        summary["atoms_marked_stale"] += 1

                entry = dict(new_snapshot[rel_path])
                entry["atom_slugs"] = new_atom_slugs
                running_snapshot[rel_path] = entry
                ws.save_extraction_snapshot(self.project_name, running_snapshot)
            except Exception as e:
                summary["errors"].append({"file": rel_path, "error": str(e)})

        # removed 的文件：源文档被删除了，它名下产出过的原子全部标记待复核
        # （不自动删除原子本身，删不删由 Jasper 决定），然后从快照里摘掉记录
        for rel_path in diff.removed:
            old_atom_slugs = old_snapshot.get(rel_path, {}).get("atom_slugs", [])
            for slug in old_atom_slugs:
                if extractor.mark_atom_stale(slug, f"源文档「{rel_path}」已被删除"):
                    summary["atoms_marked_stale"] += 1
            running_snapshot.pop(rel_path, None)
        if diff.removed:
            ws.save_extraction_snapshot(self.project_name, running_snapshot)

        return summary
