#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：知识枢纽增量聚类——把"待聚类"原子（entity_type: 待聚类，即新提炼出的、
还没归入任何entity_hub的原子）尝试匹配进已有枢纽，匹配不上的原子之间做候选
聚类，用LLM判断连贯性，产出/更新entity_hub文件。这是"写入侧自动化"里此前
完全脱节的一环——批量提炼(batch_concept_extraction.py)只负责产出原子本身，
聚类此前只能靠一次性脚本(migrate_full_vault.py，本仓库已不存)全量重跑。

设计背景（详见 03_规划项目结构/写入侧自动化增强设计_v1.md）：
- 现有vault里483个entity_hub是那次一次性全量脚本(embedding阈值0.72、无条数
  上限)跑出来的，已知会产出"财务流程与凭证"这类204个原子的巨型垃圾桶枢纽——
  问题出在"没有枢纽规模上限"，不是聚类方法论本身错。本模块的LLM连贯性判断
  提示词(atom_cluster_coherence_system.md)加了"单枢纽不超过12-15个原子，
  超过必须拆分"的硬性规则，并且本模块自己也用HUB_SIZE_CAP强制这条上限，
  双重防线避免重现巨型枢纽。
- 本模块只处理"待聚类"状态的原子，不触碰既有483个枢纽的内部结构——既有
  巨型枢纽(财务流程与凭证/L3-COM/佣金管理等)的拆解是独立的"阶段B"一次性
  整理任务，不是这个增量流程该做的事。
- 跟批量提炼一样的安全设计：--dry-run 只报告会形成哪些候选组，不调用LLM。

已知简化（v1，留给后续校准，不是本次故意漏做）：
1. "原子加入已有枢纽"只做embedding阈值判断，不再额外调LLM二次确认——因为
   该枢纽在创建时已经过LLM连贯性验证，新增一个高相似度(>=0.72)原子的误判
   风险相对可控；如果后续发现真实误判案例，再补上"加入前二次LLM确认"这一步。
2. 候选聚类的连通分量(union-find)如果大小超过COHERENCE_BATCH_SIZE，直接按
   固定大小切块喂给LLM，没有做更智能的子分组——真实数据出来后如果发现这个
   切法把明显该在一起的原子切散了，需要专门优化。
3. 原子完全没有缓存embedding时（没配置OPENAI_API_KEY/embedding_config.json，
   或者是embedding功能接入之前提炼的存量原子）直接跳过、留在"待聚类"，不
   尝试退化到关键词匹配之类的替代方案——聚类这件事本身的意义就是找语义相似，
   没有embedding就没有可靠的判断依据，不该硬凑。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools.atom_embeddings import AtomEmbeddingStore, _parse_atom_file
from tools.llm_client import call_deepseek, DEFAULT_MODEL
from memory import workspace as ws

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "08_设计提示词_Design_Prompts" / "prompts"
COHERENCE_PROMPT_PATH = PROMPTS_DIR / "atom_cluster_coherence_system.md"

MATCH_THRESHOLD = 0.72   # 跟已知历史方法论(vault里entity_hub的generated_by记录)保持一致的聚类阈值
HUB_SIZE_CAP = 15        # 硬上限：既有枢纽达到这个规模后不再往里加新原子，新组建的枢纽也受此约束
COHERENCE_BATCH_SIZE = 20  # 每次LLM连贯性判断最多喂多少个候选原子


def _slugify(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]', "", title).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "未命名枢纽"


class AtomClusterer:
    """给定一个项目，扫描"待聚类"原子，尝试并入既有枢纽或组建新枢纽。"""

    def __init__(self, vault_path: str, project_name: str, vector_mjs: str, api_key: str):
        self.vault_path = Path(vault_path)
        self.project_name = project_name
        self.project_dir = self.vault_path / project_name
        self.vector_mjs = vector_mjs
        self.api_key = api_key
        self.coherence_prompt = COHERENCE_PROMPT_PATH.read_text(encoding="utf-8")

    # ---------- 读取现状 ----------

    def _load_all_notes(self) -> Tuple[List[Dict], List[Dict]]:
        """扫描project_dir下全部.md文件，分成(待聚类原子列表, 既有枢纽列表)。"""
        unclustered, hubs = [], []
        if not self.project_dir.exists():
            return unclustered, hubs
        for md_file in sorted(self.project_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
            if not fm_match:
                continue
            fm = fm_match.group(1)
            type_m = re.search(r"^type: (\S+)$", fm, re.M)
            atom_type = type_m.group(1) if type_m else None

            if atom_type == "entity_hub":
                ref_m = re.search(r"^entity_ref: (.+)$", fm, re.M)
                member_section = text.split("## 关联原子")[-1] if "## 关联原子" in text else ""
                members = re.findall(r"\[\[(.+?)\]\]", member_section)
                hubs.append({
                    "slug": md_file.stem,
                    "entity_ref": ref_m.group(1).strip() if ref_m else md_file.stem,
                    "member_slugs": members,
                    "path": md_file,
                })
            elif atom_type == "concept_atom":
                entity_type_m = re.search(r"^entity_type: (.+)$", fm, re.M)
                entity_type = entity_type_m.group(1).strip() if entity_type_m else ""
                if entity_type != "待聚类":
                    continue
                parsed = _parse_atom_file(md_file)
                if parsed is None:
                    continue
                title, summary = parsed
                unclustered.append({"slug": md_file.stem, "title": title, "summary": summary, "path": md_file})
        return unclustered, hubs

    # ---------- 步骤1：匹配既有枢纽（纯embedding，见模块docstring简化说明1） ----------

    def _match_existing_hubs(self, atoms: List[Dict], hubs: List[Dict],
                              store: AtomEmbeddingStore) -> Tuple[Dict[str, List[Dict]], List[Dict]]:
        additions: Dict[str, List[Dict]] = {}
        remaining = []
        for atom in atoms:
            best_hub_slug, best_score = None, 0.0
            for hub in hubs:
                current_size = len(hub["member_slugs"]) + len(additions.get(hub["slug"], []))
                if current_size >= HUB_SIZE_CAP:
                    continue
                for member_slug in hub["member_slugs"]:
                    score = store.similarity_between(atom["slug"], member_slug)
                    if score is not None and score > best_score:
                        best_hub_slug, best_score = hub["slug"], score
            if best_hub_slug is not None and best_score >= MATCH_THRESHOLD:
                additions.setdefault(best_hub_slug, []).append(atom)
            else:
                remaining.append(atom)
        return additions, remaining

    # ---------- 步骤2：剩余原子之间做候选聚类（union-find） ----------

    def _candidate_groups(self, atoms: List[Dict], store: AtomEmbeddingStore) -> Tuple[List[List[Dict]], List[Dict]]:
        """返回(候选组列表[每组>=2个原子], 无可用embedding而直接跳过的原子列表)。"""
        usable = []
        skipped_no_embedding = []
        for atom in atoms:
            if atom["slug"] in store._data:  # noqa: SLF001 —— 内部缓存字典，判断"是否已有embedding"没有更轻量的公开接口
                usable.append(atom)
            else:
                skipped_no_embedding.append(atom)

        n = len(usable)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        for i in range(n):
            for j in range(i + 1, n):
                score = store.similarity_between(usable[i]["slug"], usable[j]["slug"])
                if score is not None and score >= MATCH_THRESHOLD:
                    union(i, j)

        groups_by_root: Dict[int, List[Dict]] = {}
        for i in range(n):
            groups_by_root.setdefault(find(i), []).append(usable[i])

        groups = [g for g in groups_by_root.values() if len(g) >= 2]
        singletons = [g[0] for g in groups_by_root.values() if len(g) == 1]
        return groups, skipped_no_embedding + singletons

    # ---------- 步骤3：LLM连贯性判断 ----------

    def _judge_coherence(self, group: List[Dict]) -> Dict:
        """把一组候选原子(可能超过COHERENCE_BATCH_SIZE，调用方负责切块)喂给LLM，
        返回 {"groups": [...], "unclustered_titles": [...]}。"""
        payload = {"atoms": [{"title": a["title"], "summary": a["summary"]} for a in group]}
        user_content = json.dumps(payload, ensure_ascii=False)
        response = call_deepseek(self.coherence_prompt, user_content, self.api_key, model=DEFAULT_MODEL)
        return json.loads(response)

    # ---------- 步骤4：写入 ----------

    def _append_hub_section(self, atom_path: Path, hub_ref: str):
        text = atom_path.read_text(encoding="utf-8")
        # entity_type/entity_ref 字段就地替换（原子创建时是"待聚类"/"（无）"）
        text = re.sub(r"^entity_type: .+$", "entity_type: 非正式主题", text, count=1, flags=re.M)
        text = re.sub(r"^entity_ref: .+$", f"entity_ref: {hub_ref}", text, count=1, flags=re.M)
        if "## 所属枢纽" not in text:
            text = text.rstrip("\n") + f"\n\n## 所属枢纽\n\n- [[{hub_ref}]]\n"
        atom_path.write_text(text, encoding="utf-8")

    def _write_new_hub(self, hub_name: str, coherence_reason: str, atoms: List[Dict]):
        hub_path = self.project_dir / f"{_slugify(hub_name)}.md"
        member_block = "\n".join(f"- [[{a['slug']}]]" for a in sorted(atoms, key=lambda a: a["slug"]))
        content = (
            "---\n"
            "type: entity_hub\n"
            "entity_type: 非正式主题\n"
            f"entity_ref: {hub_name}\n"
            f"project: {self.project_name}\n"
            f"atom_count: {len(atoms)}\n"
            f"generated_at: {datetime.now().date().isoformat()}\n"
            "generated_by: embedding聚类(threshold=0.72，cluster_atoms.py增量) + LLM内容连贯性判断\n"
            f"coherence_reason: {coherence_reason}\n"
            "---\n\n"
            f"# {hub_name}\n\n"
            f"非正式主题枢纽，{len(atoms)}个原子经LLM判断内容连贯后自动生成。\n\n"
            "## 关联原子\n\n"
            f"{member_block}\n"
        )
        hub_path.write_text(content, encoding="utf-8")
        for atom in atoms:
            self._append_hub_section(atom["path"], hub_name)

    def _apply_hub_additions(self, hub: Dict, new_atoms: List[Dict]):
        for atom in new_atoms:
            self._append_hub_section(atom["path"], hub["entity_ref"])
        text = hub["path"].read_text(encoding="utf-8")
        new_count = len(hub["member_slugs"]) + len(new_atoms)
        text = re.sub(r"^atom_count: \d+$", f"atom_count: {new_count}", text, count=1, flags=re.M)
        member_block = "\n".join(f"- [[{s}]]" for s in sorted(hub["member_slugs"] + [a["slug"] for a in new_atoms]))
        text = re.sub(r"## 关联原子\n\n(?:- \[\[.+?\]\]\n?)+", f"## 关联原子\n\n{member_block}\n", text)
        hub["path"].write_text(text, encoding="utf-8")

    # ---------- 主流程 ----------

    def scan_and_cluster(self, dry_run: bool = False, max_llm_calls: Optional[int] = None) -> Dict:
        # 复用批量提炼(batch_concept_extraction.py)同一个embedding缓存目录
        # （memory/workspace.py.atom_embeddings_dir()）——提炼阶段store_embedding()
        # 已经把每个新原子的embedding存过一份，这里直接读同一份缓存做相似度比对，
        # 不重新计算、不产生新的embedding API调用。
        store = AtomEmbeddingStore(
            cache_dir=ws.atom_embeddings_dir(self.project_name),
            project_name=self.project_name,
            vector_mjs=self.vector_mjs,
        )
        unclustered, hubs = self._load_all_notes()

        summary = {
            "project": self.project_name,
            "unclustered_scanned": len(unclustered),
            "existing_hubs": len(hubs),
            "matched_to_existing_hub": 0,
            "new_hubs_created": 0,
            "atoms_still_unclustered": 0,
            "skipped_no_embedding": 0,
            "llm_calls": 0,
            "dry_run": dry_run,
            "plan": [],
            "errors": [],
        }

        hub_additions, remaining = self._match_existing_hubs(unclustered, hubs, store)
        for hub_slug, atoms in hub_additions.items():
            hub = next(h for h in hubs if h["slug"] == hub_slug)
            summary["plan"].append({
                "action": "add_to_existing_hub", "hub": hub["entity_ref"],
                "atoms": [a["title"] for a in atoms],
            })
            summary["matched_to_existing_hub"] += len(atoms)
            if not dry_run:
                self._apply_hub_additions(hub, atoms)

        candidate_groups, leftover = self._candidate_groups(remaining, store)
        summary["skipped_no_embedding"] = sum(1 for a in leftover if a["slug"] not in store._data)  # noqa: SLF001
        summary["atoms_still_unclustered"] += len([a for a in leftover if a["slug"] in store._data])

        for group in candidate_groups:
            chunks = [group[i:i + COHERENCE_BATCH_SIZE] for i in range(0, len(group), COHERENCE_BATCH_SIZE)]
            for chunk in chunks:
                if dry_run:
                    summary["plan"].append({
                        "action": "candidate_group_pending_llm_judgment",
                        "atoms": [a["title"] for a in chunk],
                    })
                    continue
                if max_llm_calls is not None and summary["llm_calls"] >= max_llm_calls:
                    summary["atoms_still_unclustered"] += len(chunk)
                    continue
                try:
                    result = self._judge_coherence(chunk)
                    summary["llm_calls"] += 1
                except Exception as e:
                    summary["errors"].append({"group": [a["title"] for a in chunk], "error": str(e)})
                    summary["atoms_still_unclustered"] += len(chunk)
                    continue
                title_to_atom = {a["title"]: a for a in chunk}
                for g in result.get("groups", []):
                    member_atoms = [title_to_atom[t] for t in g.get("atom_titles", []) if t in title_to_atom]
                    if len(member_atoms) < 2 or not g.get("coherent", True):
                        summary["atoms_still_unclustered"] += len(member_atoms)
                        continue
                    self._write_new_hub(g["hub_name"], g.get("coherence_reason", ""), member_atoms)
                    summary["new_hubs_created"] += 1
                for t in result.get("unclustered_titles", []):
                    if t in title_to_atom:
                        summary["atoms_still_unclustered"] += 1

        return summary
