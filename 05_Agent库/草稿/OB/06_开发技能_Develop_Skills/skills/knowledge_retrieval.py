#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：检索服务——OB 对 PTA 等业务 Agent 暴露的薄客户端检索接口。

设计依据（见 01_初始化项目/需求定义.md 四、③服务接口形式）：PTA 只知道
"什么时候该问、问完怎么用"，不直接耦合 MCP 协议细节——本模块就是那层薄封装。
底层调用 obsidian-mcp-server 的 hybridSearch（关键词+图谱+向量 RRF 融合，
2026-07-15 已校准 5 个真实 bug，见 tools/retrieval_bridge.py 顶部说明）。

现状说明（不是 bug，是当前 vault 内容阶段性现状）：vault 重置（删除 symlink
镜像、只留概念笔记）尚未执行，本模块现在检索到的"原子"实际上是原始项目
文档的片段，不是提炼过的知识原子——接口形状已经按"未来是概念笔记"设计好，
vault 重置 + 概念笔记提炼上线后，调用方不需要改代码，返回内容会自然变得
更精炼。
"""

from typing import Dict, List, Optional

from tools import retrieval_bridge


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
            atoms.append({
                "content": r.get("content", ""),
                "source": r.get("notePath", ""),
                "note_name": r.get("noteName", ""),
                "heading": r.get("heading", ""),
                "score": r.get("score", 0),
                "matched_by": r.get("sources", []),
                "tags": r.get("tags", []),
            })

        return {
            "query": query, "mode_requested": mode, "mode_effective": mode_effective,
            "has_vector": has_vector, "atoms": atoms,
        }

    @staticmethod
    def format_for_prompt(context: Dict) -> str:
        """把背景上下文包格式化成一段可以直接拼进 LLM 提示词的文本。"""
        if context.get("error"):
            return f"（背景检索失败：{context['error']}，本次分析不含项目背景上下文）"
        if not context["atoms"]:
            return "（未检索到相关背景，本次分析不含项目背景上下文）"

        lines = [f"# 相关背景（检索模式：{context['mode_effective']}）", ""]
        for i, atom in enumerate(context["atoms"], 1):
            lines.append(f"## {i}. {atom['note_name']}（来源：{atom['source']}）")
            if atom["heading"]:
                lines.append(f"> {atom['heading']}")
            lines.append(atom["content"])
            lines.append("")
        return "\n".join(lines)
