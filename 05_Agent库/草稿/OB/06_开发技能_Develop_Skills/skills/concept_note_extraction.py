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
from tools.project_filters import derive_authority_layer

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "08_设计提示词_Design_Prompts" / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "concept_note_extraction_system.md"
TABLE_SYSTEM_PROMPT_PATH = PROMPTS_DIR / "table_extraction_system.md"


def _repair_json_escapes(text: str) -> str:
    """修复LLM输出里非法的JSON转义序列。真实复现过：源文档含正则表达式片段
    （如 `\\d{2}`）时，LLM把这类原文引用进summary字段，产出的反斜杠不是
    JSON合法转义字符（合法集合是 " \\ / b f n r t u），json.loads 直接报
    'Invalid \\escape' 整个提炼失败。这里把"反斜杠后面不是合法转义字符"的
    情况原样转成字面反斜杠（\\\\），不影响本来就合法的转义序列。"""
    return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)


def _repair_unescaped_quote_at(text: str, error: json.JSONDecodeError) -> Optional[str]:
    """修复LLM输出里字符串值内部未转义的双引号。真实复现过：源文档用中文
    语境的直引号做强调（如"是否熔断"），LLM原样把这对引号写进JSON字符串值，
    没有转义——JSON字符串在遇到这个引号时提前"闭合"，后面的文本变成不合法的
    游离token，报'Expecting , delimiter'（不是'Invalid \\escape'，是完全
    不同的错误类型，_repair_json_escapes处理不了这种）。

    做法：从报错位置（error.pos）往回找最近一个"未转义的双引号"，把它转义成
    \\"。一次只修一个，调用方在循环里反复调用直到解析成功或达到重试上限——
    一份文档的summary里可能不止一处这种引号，不能假设修一次就够。找不到可修的
    引号时返回None，调用方据此判断"这个策略也救不了，放弃"。"""
    pos = error.pos
    i = pos - 1
    while i >= 0:
        if text[i] == '"' and (i == 0 or text[i - 1] != "\\"):
            return text[:i] + '\\"' + text[i + 1:]
        i -= 1
    return None


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
        self.table_system_prompt = TABLE_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        # Optional[tools.atom_embeddings.AtomEmbeddingStore]——不传则完全等价于
        # MVP 阶段的纯精确匹配去重，行为不变
        self.embedding_store = embedding_store

    def extract_atoms(self, content: str) -> List[Dict]:
        """调用 LLM 提炼知识原子，返回列表（未写入磁盘）。"""
        return self._extract_with_prompt(self.system_prompt, content)

    def extract_table_atoms(self, table_markdown: str) -> List[Dict]:
        """表格版提炼——喂一批已序列化成markdown表格的行（见tools/table_reader.py），
        用专门的table_extraction_system.md提示词（不机械按行拆、允许合并同实体
        多行）。跟extract_atoms()共用JSON解析+非法转义修复逻辑，只是换了提示词
        和输入形态，返回的atom字典格式跟文档提炼完全一致，可以直接喂给
        write_atom()复用同一套去重/写入逻辑。"""
        return self._extract_with_prompt(self.table_system_prompt, table_markdown)

    def _extract_with_prompt(self, system_prompt: str, content: str, max_quote_repairs: int = 10) -> List[Dict]:
        response = call_deepseek(system_prompt, content, self.api_key, model=self.model)
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # 源文档含正则表达式/路径等反斜杠内容时，LLM 引用原文可能产出
            # 非法JSON转义（真实复现过），先尝试修复一次再重新解析，不是
            # 第一次失败就放弃整份文档的提炼
            text = _repair_json_escapes(response)
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                # 反斜杠修复解决不了，可能是字符串值里的未转义双引号
                # （真实复现过：中文语境直引号强调，如"是否熔断"被LLM原样
                # 写进JSON值）——逐个修复直到能解析或达到重试上限，一份
                # 文档可能不止一处这种引号
                for _ in range(max_quote_repairs):
                    fixed = _repair_unescaped_quote_at(text, e)
                    if fixed is None:
                        raise
                    text = fixed
                    try:
                        data = json.loads(text)
                        break
                    except json.JSONDecodeError as e2:
                        e = e2
                else:
                    raise
        atoms = data.get("atoms", [])
        # 真实复现过：LLM偶发输出缺"title"字段的atom对象（json本身合法，
        # 只是结构不完整，_repair_*系列救不了这种）——write_atom()直接用
        # atom["title"]会KeyError崩掉整份文档，改成跳过这一条、保留其余
        # 合法的atom，不因为一条数据不完整就丢掉整份提炼结果。同一次调用
        # 里其他LLM响应实测过完全正常，这是偶发的输出质量问题，不是提示词
        # 系统性缺陷。
        valid_atoms = [a for a in atoms if isinstance(a, dict) and a.get("title")]
        return valid_atoms

    def _atom_path(self, atom_title: str) -> Path:
        return self.vault_path / self.project_name / f"{_slugify(atom_title)}.md"

    # 更新时新旧内容语义相似度低于这个阈值，判定"不是简单改写，是实质性
    #不同的说法"，改走待校准流程而不是直接覆盖。2026-07-21新增，阈值是
    # 起始估计（同一个slug的新旧版本理论上应该比"不同原子间是否相似"要求
    # 更高，那个场景真实测过0.6-0.75是合理匹配范围），没有专门跑过大样本
    # 校准，用出真实数据后可能需要调整，先用这个值让机制跑起来。
    CALIBRATION_SIMILARITY_THRESHOLD = 0.80

    def write_atom(self, atom: Dict, source_path: str) -> Dict:
        """把一个原子写成 .md 文件（frontmatter + 正文 + 关联概念的 wikilink）。
        先按标题精确匹配；未命中且配置了 embedding_store 时，再查语义相似——
        命中则写入相似原子对应的文件（视为更新而非新建同义重复原子）。

        2026-07-21新增两道刹车（Jasper提出的原子质量梳理原则）：
        ①更新不再无痕覆盖——旧内容存进"## 历史版本"区块（只留上一版，不是
        无限累积，避免文件无限膨胀），至少保证"覆盖了什么"有据可查。
        ②更新前算新旧内容语义相似度，明显不像"同一件事的改写"（低于
        CALIBRATION_SIMILARITY_THRESHOLD）时不直接覆盖主内容——旧内容原样
        保留在原地，新内容作为"待校准候选"单独列出来，新旧原子title冲突
        但内容实质不同，交给人判断怎么合并/该信哪个，批量任务不擅自替
        Jasper做这个判断。"""
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
        old_text = path.read_text(encoding="utf-8") if existed else None

        similarity = None
        if existed and self.embedding_store is not None:
            similarity = self.embedding_store.content_similarity(
                path.stem, atom["title"], atom.get("summary", "")
            )
        needs_calibration = similarity is not None and similarity < self.CALIBRATION_SIMILARITY_THRESHOLD

        related = atom.get("related_concepts", [])
        related_block = "\n".join(f"- [[{r}]]" for r in related) if related else "（暂无）"

        if needs_calibration:
            content = (
                (old_text or "").rstrip("\n")
                + f"\n\n---\n⚠️ **待校准**：源文档「{source_path}」提炼出内容差异较大的新版本"
                f"（语义相似度{similarity:.2f}，低于{self.CALIBRATION_SIMILARITY_THRESHOLD}阈值），"
                "新旧内容未自动合并，需人工判断保留哪个/如何合并"
                f"（标记时间：{datetime.now().isoformat(timespec='seconds')}）。\n\n"
                f"### 候选新内容（来自「{source_path}」）\n\n{atom.get('summary', '')}\n"
            )
            path.write_text(content, encoding="utf-8")
            return {"action": "needs_calibration", "path": str(path), "title": atom["title"], "similarity": similarity}

        history_block = ""
        if old_text:
            old_summary_m = re.search(r"^# .+?\n\n(.+?)\n\n## ", old_text, re.S)
            old_extracted_m = re.search(r"^extracted_at: (.+)$", old_text, re.M)
            if old_summary_m:
                old_extracted = old_extracted_m.group(1) if old_extracted_m else "未知时间"
                history_block = (
                    "\n## 历史版本（仅保留上一版，更早版本见git历史）\n\n"
                    f"<details><summary>{old_extracted} 的版本</summary>\n\n"
                    f"{old_summary_m.group(1).strip()}\n\n</details>\n"
                )

        # 2026-07-21新增：补齐治理/聚类字段，对齐EA项目早期迁移脚本(migrate_
        # full_vault.py，本仓库已不存)产出的完整schema——此前write_atom()只写
        # 5个基础字段，导致本流程(agent.py --extract-project)产出的原子(如
        # Jasper AI协同经验引擎的418个)跟EA项目原子是两套不同成熟度的schema，
        # 见路线图诊断"跨项目schema不一致"一节。
        # confidence/confidence_reason来自LLM按提示词新增的打分标准判断，不是
        # 硬编码；decision_status/entity_type/entity_ref三个字段仍然只能是
        # 占位符——decision_status要等治理评审通过后才该改(不该在创建时就自称
        # 已确认)，entity_type/entity_ref要等聚类脚本跑过才有值(聚类是本次
        # 之外的独立设计，见"阶段F设计"文档的聚类小节)，authority_layer则是
        # 唯一可以在写入时就确定性派生的字段(来自源文件所在分层目录，不依赖
        # LLM判断)。
        authority_layer = derive_authority_layer(self.project_name, source_path)
        confidence = atom.get("confidence") or "UNSTATED"
        confidence_reason = atom.get("confidence_reason", "")

        content = (
            "---\n"
            "type: concept_atom\n"
            f"concept_type: {atom.get('concept_type', '未分类')}\n"
            f"project: {self.project_name}\n"
            f"source: {source_path}\n"
            f"authority_layer: {authority_layer}\n"
            f"confidence: {confidence}\n"
            f"confidence_reason: {confidence_reason}\n"
            "decision_status: UNSTATED\n"
            "as_of: 未知\n"
            "entity_type: 待聚类\n"
            "entity_ref: （无）\n"
            "status: 生效\n"
            f"extracted_at: {datetime.now().isoformat(timespec='seconds')}\n"
            "---\n\n"
            f"# {atom['title']}\n\n"
            f"{atom.get('summary', '')}\n\n"
            "## 关联概念\n\n"
            f"{related_block}\n"
            f"{history_block}"
        )
        path.write_text(content, encoding="utf-8")

        if self.embedding_store is not None:
            # 用实际落盘的文件名 slug（而不是本次 atom["title"] 的 slug——
            # 语义命中时两者可能不同）作为 embedding 缓存的 key，保持
            # "缓存 key == vault 文件名"这条一致性，下次查相似时才对得上
            self.embedding_store.store_embedding(path.stem, atom["title"], atom.get("summary", ""))

        return {"action": "updated" if existed else "created", "path": str(path), "title": atom["title"],
                "similarity": similarity}

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

    def process_table_file(self, source_path: str, abs_path, batch_size: int = 25) -> Dict:
        """表格版完整流程：读取xlsx/csv的每个数据块（xlsx每个非元信息sheet
        算一块，csv整份算一块）→ 每块按batch_size行分批 → 每批调用LLM提炼
        →写入。返回结构跟process_document一致（source/atom_count/results），
        调用方（batch_concept_extraction.py）不需要区分表格还是文档来处理
        返回值。

        一份表格文件通常比一篇文档产出多得多的原子（比如300行的KPI映射表
        可能产出上百个原子），这是真实数据量决定的，不是bug。

        每批单独try/except——真实复现过：一份xlsx可能有几十批，某一批JSON
        解析失败或网络抖动，不该让同一份文件里已经成功写入的其他批次也
        白跑（之前的实现是整个文件级别一次try/except，一批出错就丢了这份
        文件所有批次的进度，包括已经成功的）。失败的批次记进errors返回，
        不重新抛异常，调用方（batch_concept_extraction.py）据此判断这份
        文件整体算不算"处理完成"。"""
        from tools import table_reader

        blocks = table_reader.read_table_blocks(Path(abs_path))
        all_results = []
        errors = []
        for block in blocks:
            rows = block["rows"]
            label_parts = block["source_label"].split(" / ", 1)
            block_source = f"{source_path} / {label_parts[1]}" if len(label_parts) > 1 else source_path
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                table_md = table_reader.serialize_rows_markdown(block["columns"], batch)
                try:
                    atoms = self.extract_table_atoms(table_md)
                    all_results.extend(self.write_atom(a, block_source) for a in atoms)
                except Exception as e:
                    errors.append({"block": block_source, "batch_start_row": i, "error": str(e)})

        return {"source": source_path, "atom_count": len(all_results), "results": all_results, "errors": errors}
