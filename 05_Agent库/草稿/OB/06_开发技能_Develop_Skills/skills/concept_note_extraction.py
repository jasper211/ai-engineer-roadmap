#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：概念笔记提炼——把一份项目文档拆解成若干独立的知识原子，写回 vault。

全新能力，MVP 设计（详见 03_规划项目结构/流程设计.md 四、已知的关键设计缺口，
以下是本次落地时的具体决策，记录下来供后续复核）：

1. **原子粒度**：由 LLM 按 prompts/concept_note_extraction_system.md 的定义
   判断——一个原子是一条规则/决策/定义/经验教训/背景说明，不是整篇摘要，
   也不是按标题机械切分（那是 obsidian-mcp-server 的 chunkNote 做的事，
   服务于向量检索；这里服务的是"知识图谱里一个有意义的节点"，目的不同）。
2. **去重/更新策略**：先按原子标题 slugify 精确匹配文件名（最快路径），
   未命中再交给 `tools/atom_embeddings.py` 查语义相似（2026-07-16 升级，
   见 write_atom() 里的 embedding_store 参数）——真实验证过 MVP 阶段纯精确
   匹配的局限：LLM 猜的关联标题（"经验代码化"）跟实际写入的原子标题
   （"经验代码化原则"）不完全一致时会漏判成两个原子。语义相似度调用需要
   OPENAI_API_KEY（本机当前未配置，同 hybrid_search 向量层一样会优雅降级
   ——降级时等价于退回纯精确匹配去重，不会崩溃，也不会误判）。
3. **写入路径**：直接用 Python 文件 IO 写入 vault 对应项目目录，不经过 MCP——
   现有 obsidian-mcp-server 的 MCP 连接是只读的，扩展它支持写入是更大的
   改造，这里先用 OB Agent 自己对本地文件系统的直接访问权限完成写入
   （跟 ob_sync_agent.py 读 vault 目录是同一种访问方式，不是新增的权限面）。

不在本次范围内：文档变更检测（复用 PTA 的 file_diff sha256 diff 思路，OB 自己
实现一份）、批量扫描三个项目目录的编排逻辑——本模块只负责"给定一份文档内容，
提炼+写入"这一步，调用方（agent.py 或未来的批量脚本）负责决定喂哪些文档。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tools.llm_client import call_deepseek, DEFAULT_MODEL

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "08_设计提示词_Design_Prompts" / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "concept_note_extraction_system.md"


def _repair_json_escapes(text: str) -> str:
    """修复LLM输出里非法的JSON转义序列。真实复现过：源文档含正则表达式片段
    （如 `\\d{2}`）时，LLM把这类原文引用进summary字段，产出的反斜杠不是
    JSON合法转义字符（合法集合是 " \\ / b f n r t u），json.loads 直接报
    'Invalid \\escape' 整个提炼失败。这里把"反斜杠后面不是合法转义字符"的
    情况原样转成字面反斜杠（\\\\），不影响本来就合法的转义序列。"""
    return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)


def _slugify(title: str) -> str:
    """把原子标题转成安全的文件名（保留中文，去掉文件系统不允许的字符）。"""
    cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]', "", title).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "未命名概念"


class ConceptNoteExtractor:
    """给定源文档内容，提炼知识原子并写入 vault 对应项目目录。"""

    def __init__(self, vault_path: str, project_name: str, api_key: str, model: str = DEFAULT_MODEL,
                 embedding_store=None):
        self.vault_path = Path(vault_path)
        self.project_name = project_name
        self.api_key = api_key
        self.model = model
        self.system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        # Optional[tools.atom_embeddings.AtomEmbeddingStore]——不传则完全等价于
        # MVP 阶段的纯精确匹配去重，行为不变
        self.embedding_store = embedding_store

    def extract_atoms(self, content: str) -> List[Dict]:
        """调用 LLM 提炼知识原子，返回列表（未写入磁盘）。"""
        response = call_deepseek(self.system_prompt, content, self.api_key, model=self.model)
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # 源文档含正则表达式/路径等反斜杠内容时，LLM 引用原文可能产出
            # 非法JSON转义（真实复现过），先尝试修复一次再重新解析，不是
            # 第一次失败就放弃整份文档的提炼
            data = json.loads(_repair_json_escapes(response))
        return data.get("atoms", [])

    def _atom_path(self, atom_title: str) -> Path:
        return self.vault_path / self.project_name / f"{_slugify(atom_title)}.md"

    def write_atom(self, atom: Dict, source_path: str) -> Dict:
        """把一个原子写成 .md 文件（frontmatter + 正文 + 关联概念的 wikilink）。
        先按标题精确匹配；未命中且配置了 embedding_store 时，再查语义相似——
        命中则写入相似原子对应的文件（视为更新而非新建同义重复原子）。"""
        path = self._atom_path(atom["title"])
        existed = path.exists()

        if not existed and self.embedding_store is not None:
            similar_slug = self.embedding_store.find_similar_atom(
                atom["title"], atom.get("summary", "")
            )
            if similar_slug is not None:
                path = self.vault_path / self.project_name / f"{similar_slug}.md"
                existed = path.exists()

        path.parent.mkdir(parents=True, exist_ok=True)

        related = atom.get("related_concepts", [])
        related_block = "\n".join(f"- [[{r}]]" for r in related) if related else "（暂无）"

        content = (
            "---\n"
            "type: concept_atom\n"
            f"concept_type: {atom.get('concept_type', '未分类')}\n"
            f"project: {self.project_name}\n"
            f"source: {source_path}\n"
            f"extracted_at: {datetime.now().isoformat(timespec='seconds')}\n"
            "---\n\n"
            f"# {atom['title']}\n\n"
            f"{atom.get('summary', '')}\n\n"
            "## 关联概念\n\n"
            f"{related_block}\n"
        )
        path.write_text(content, encoding="utf-8")

        if self.embedding_store is not None:
            # 用实际落盘的文件名 slug（而不是本次 atom["title"] 的 slug——
            # 语义命中时两者可能不同）作为 embedding 缓存的 key，保持
            # "缓存 key == vault 文件名"这条一致性，下次查相似时才对得上
            self.embedding_store.store_embedding(path.stem, atom["title"], atom.get("summary", ""))

        return {"action": "updated" if existed else "created", "path": str(path), "title": atom["title"]}

    def mark_atom_stale(self, atom_slug: str, reason: str) -> bool:
        """给一个原子文件追加"待复核"标记，不删除、不覆盖原有内容——真实场景：
        源文档更新后，旧版本产出但新版本不再包含的原子会变成静默过时的孤儿，
        没人知道该不该删。这里只做标记，删不删由 Jasper 自己决定，不自动删除
        （对vault内容做删除是更大的动作，不该由批量任务自动执行）。已经标记
        过的不重复追加（用文件里有没有这个标记字符串判断，不用额外状态）。
        返回 False 表示原子文件不存在，或已经标记过。"""
        path = self.vault_path / self.project_name / f"{atom_slug}.md"
        if not path.exists():
            return False
        existing_content = path.read_text(encoding="utf-8")
        marker = "⚠️ **待复核**"
        if marker in existing_content:
            return False
        note = (
            f"\n\n---\n{marker}：{reason}"
            f"（标记时间：{datetime.now().isoformat(timespec='seconds')}）\n"
        )
        path.write_text(existing_content + note, encoding="utf-8")
        return True

    def process_document(self, source_path: str, content: str) -> Dict:
        """完整流程：提炼 + 写入，返回汇总结果。"""
        atoms = self.extract_atoms(content)
        results = [self.write_atom(a, source_path) for a in atoms]
        return {"source": source_path, "atom_count": len(atoms), "results": results}
