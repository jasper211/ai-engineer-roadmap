#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：检索服务——OB 对 PTA 等业务 Agent 暴露的薄客户端检索接口。

设计依据（见 01_初始化项目/需求定义.md 四、③服务接口形式）：PTA 只知道
"什么时候该问、问完怎么用"，不直接耦合 MCP 协议细节——本模块就是那层薄封装。
底层调用 obsidian-mcp-server 的 hybridSearch（关键词+图谱+向量 RRF 融合，
2026-07-15 已校准 5 个真实 bug，见 tools/retrieval_bridge.py 顶部说明）。

2026-07-18：接入 tools/atom_metadata.py——本体schema迁移(entity_type/
authority_layer/confidence等字段，6601个原子全量迁移+573个知识枢纽)第一次
被检索端真正读取。之前这些字段只存在于vault文件里，PTA等调用方拿到的是
"一堆语义相近的文本片段"，看不出哪条是已锁定的权威结论、哪条是未审核的
草稿猜测——这正是"AI协同时检索到过时/矛盾/低置信度结论"这类幻觉的直接
成因。本次改动：①每条结果补上authority_layer/confidence/所属枢纽等字段
②format_for_prompt()把这些字段显式标注进喂给LLM的文本，而不是让下游自己
猜。不做重排序（原始相关性排序保持不变，只做标注补充）——重排序改变的是
"哪条结果被返回"，标注补充改变的是"返回的结果被怎么理解"，后者风险小得多，
前者需要更大样本验证权威度加权是否真的改善检索质量，这次先不做。
"""

from typing import Dict, List, Optional

from tools import retrieval_bridge, atom_metadata


class KnowledgeRetriever:
    """给定查询，返回结构化的背景上下文包，供调用方注入 LLM 提示词或过滤判断使用。"""

    def __init__(self, vault_path: str, vault_mjs: str, vector_mjs: str):
        self.vault_path = vault_path
        self.vault_mjs = vault_mjs
        self.vector_mjs = vector_mjs

    def get_context(self, query: str, max_results: int = 5, mode: str = "hybrid") -> Dict:
        """返回背景上下文包：{query, mode_requested, mode_effective, atoms: [...]}。

        mode_effective 在没有可用向量索引时会从 "hybrid" 自动降级为等价的
        "关键词+图谱"结果（底层 hybridSearch 自己处理，这里只如实反映降级
        是否发生，调用方可以据此判断结果的精细程度）。

        每条atom补充结构化元数据（authority_layer/confidence/decision_status/
        entity_type/entity_ref/hubs）——读不到（文件没有frontmatter，比如
        概念/MOC/这些手工笔记）时对应字段为None，不是错误，调用方按None
        判断"这条没有结构化元数据"。
        """
        data = retrieval_bridge.hybrid_search(
            vault_mjs=self.vault_mjs,
            vector_mjs=self.vector_mjs,
            vault_path=self.vault_path,
            query=query,
            mode=mode,
            max_results=max_results,
        )

        if "error" in data:
            return {
                "query": query, "mode_requested": mode, "mode_effective": None,
                "has_vector": False, "atoms": [], "error": data["error"],
            }

        has_vector = data.get("hasVector", False)
        mode_effective = mode if (mode != "hybrid" or has_vector) else "hybrid(降级为关键词+图谱)"

        atoms = []
        for r in data.get("results", []):
            note_path = r.get("notePath", "")
            meta = atom_metadata.read_atom_metadata(self.vault_path, note_path) or {}
            atoms.append({
                "content": r.get("content", ""),
                "source": note_path,
                "note_name": r.get("noteName", ""),
                "heading": r.get("heading", ""),
                "score": r.get("score", 0),
                "matched_by": r.get("sources", []),
                "tags": r.get("tags", []),
                "authority_layer": meta.get("authority_layer"),
                "confidence": meta.get("confidence"),
                "decision_status": meta.get("decision_status"),
                "entity_type": meta.get("entity_type"),
                "entity_ref": meta.get("entity_ref"),
                "hubs": meta.get("hubs", []),
                "is_hub": meta.get("is_hub", False),
            })

        return {
            "query": query, "mode_requested": mode, "mode_effective": mode_effective,
            "has_vector": has_vector, "atoms": atoms,
        }

    @staticmethod
    def _trust_badge(atom: Dict) -> str:
        """把authority_layer/confidence拼成一个人类可读的信任标注，塞进
        format_for_prompt()的输出——这是核心机制：让下游LLM看见"这条结论
        权威级别多高、置信度多高"，而不是把所有检索结果当作同等可信。"""
        parts = []
        if atom.get("authority_layer"):
            parts.append(atom["authority_layer"])
        if atom.get("confidence") and atom["confidence"] != "UNSTATED":
            parts.append(f"confidence={atom['confidence']}")
        if atom.get("is_hub"):
            parts.append("知识枢纽")
        return f"[{' · '.join(parts)}]" if parts else "[未标注权威级别/草稿类内容]"

    @staticmethod
    def format_for_prompt(context: Dict) -> str:
        """把背景上下文包格式化成一段可以直接拼进 LLM 提示词的文本。
        每条结果带信任标注；同一个所属枢纽被多条结果命中时额外提示"这些
        结果指向同一话题枢纽，可能需要合并理解或检查是否有更新/矛盾"。"""
        if context.get("error"):
            return f"（背景检索失败：{context['error']}，本次分析不含项目背景上下文）"
        if not context["atoms"]:
            return "（未检索到相关背景，本次分析不含项目背景上下文）"

        hub_hit_count: Dict[str, int] = {}
        for atom in context["atoms"]:
            for hub in atom.get("hubs", []):
                hub_hit_count[hub] = hub_hit_count.get(hub, 0) + 1
        shared_hubs = [h for h, c in hub_hit_count.items() if c >= 2]

        lines = [f"# 相关背景（检索模式：{context['mode_effective']}）", ""]
        if shared_hubs:
            lines.append(f"> 提示：以下结果中有多条同属枢纽 {', '.join(shared_hubs)}，"
                          f"可能是同一话题的不同侧面/不同时期记录，注意甄别是否有更新或矛盾。")
            lines.append("")
        for i, atom in enumerate(context["atoms"], 1):
            badge = KnowledgeRetriever._trust_badge(atom)
            lines.append(f"## {i}. {atom['note_name']}{badge}（来源：{atom['source']}）")
            if atom["heading"]:
                lines.append(f"> {atom['heading']}")
            lines.append(atom["content"])
            lines.append("")
        return "\n".join(lines)
