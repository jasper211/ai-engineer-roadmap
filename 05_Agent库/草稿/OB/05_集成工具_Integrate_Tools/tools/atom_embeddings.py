#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：知识原子的语义去重——升级 concept_note_extraction.py MVP 阶段"标题
精确匹配去重"的局限（真实验证过：LLM 猜的关联标题跟实际写入的原子标题
不完全一致时，精确匹配会漏判，产出同义不同名的重复原子）。

设计（2026-07-16 跟 Jasper 对齐，不引入专门向量数据库）：
- 复用 obsidian-mcp-server/src/vector.mjs 的 getEmbeddings()（同一个
  BAAI/bge-m3 模型/同一个 OPENAI_BASE_URL 配置），走跟 retrieval_bridge.py
  一样的"Python调subprocess跑node脚本"桥接方式，不在 Python 侧重新实现
  一遍 embedding API 调用。
- 本地缓存按项目分文件（atom_slug -> embedding），量级是"原子数"不是
  "文档chunk数"，一个平文件 JSON 足够，不需要专门的向量数据库。
- 优雅降级：本机当前未配置 OPENAI_API_KEY（跟本轮 hybrid_search 向量层
  同样的情况），embed_text() 会返回 {"error": ...}；find_similar_atom()
  遇到这种情况返回 None（退化为"只有精确匹配去重"，不崩溃），跟
  vector.mjs 自己"无 API key 时降级为关键词+图谱"是同一条设计原则。
"""

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from tools.embedding_config import load_embedding_env


def embed_text(vector_mjs: str, text: str, timeout: int = 30) -> dict:
    """调用 vector.mjs 的 getEmbeddings() 生成单条文本的 embedding。
    返回 {"embedding": [...]} 或 {"error": "..."}（含"未设置 OPENAI_API_KEY"
    这种预期内的降级场景，调用方按 error 字段判断是否要走精确匹配兜底）。
    真实凭证从 02_配置项目_Configure_Project/embedding_config.json 读取
    （不进git），未配置时 load_embedding_env() 原样返回当前环境变量，
    行为等价于此前"本机无OPENAI_API_KEY"的优雅降级路径。"""
    text_json = json.dumps(text, ensure_ascii=False)
    script = (
        f"import('{vector_mjs}').then(async v => {{"
        f"const emb = await v.getEmbeddings([{text_json}]);"
        f"console.log(JSON.stringify({{ embedding: emb[0] }}));"
        f"}}).catch(e => console.log(JSON.stringify({{error: e.message}})));"
    )
    output = ""
    try:
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.path.dirname(vector_mjs),
            env=load_embedding_env(),
        )
        output = result.stdout.strip() or result.stderr.strip()
        return json.loads(output)
    except FileNotFoundError:
        return {"error": f"vector.mjs 不存在: {vector_mjs}"}
    except subprocess.TimeoutExpired:
        return {"error": f"超过 {timeout} 秒未响应"}
    except json.JSONDecodeError as e:
        return {"error": f"输出解析失败: {e}; 原始输出: {output[:300]}"}
    except Exception as e:
        return {"error": str(e)}


def embed_texts_batched(vector_mjs: str, texts: List[str], timeout: int = 600) -> dict:
    """一次node子进程内完成多条文本的embedding（内部经getEmbeddingsBatched按
    10条/批调API），用于回填大批量已有原子的embedding——如果对每条文本各起
    一个embed_text()子进程，光是node启动开销就要乘以原子数，回填几千个原子
    时不现实。返回 {"embeddings": [...]}（顺序对应texts）或 {"error": ...}。
    真实凭证同embed_text()，从embedding_config.json加载。"""
    texts_json = json.dumps(texts, ensure_ascii=False)
    script = (
        f"import('{vector_mjs}').then(async v => {{"
        f"const embs = await v.getEmbeddingsBatched({texts_json});"
        f"console.log(JSON.stringify({{ embeddings: embs }}));"
        f"}}).catch(e => console.log(JSON.stringify({{error: e.message}})));"
    )
    output = ""
    try:
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.path.dirname(vector_mjs),
            env=load_embedding_env(),
        )
        output = result.stdout.strip() or result.stderr.strip()
        return json.loads(output)
    except FileNotFoundError:
        return {"error": f"vector.mjs 不存在: {vector_mjs}"}
    except subprocess.TimeoutExpired:
        return {"error": f"超过 {timeout} 秒未响应"}
    except json.JSONDecodeError as e:
        return {"error": f"输出解析失败: {e}; 原始输出: {output[:300]}"}
    except Exception as e:
        return {"error": str(e)}


def _parse_atom_file(path: Path) -> Optional[tuple]:
    """从已写入vault的原子.md文件解析标题+摘要，格式跟
    ConceptNoteExtractor.write_atom() 的写入格式配套（frontmatter后是
    '# 标题\\n\\n摘要...\\n\\n## 关联概念'）。回填embedding时直接读已有内容，
    不重新调LLM提炼。解析失败（格式不符预期）返回None，调用方应跳过而非报错
    ——理论上不会发生（写入格式是自己控制的），但真实vault里如果有人手动
    编辑过原子文件、格式跑偏，不该让整个回填任务因为一个文件中断。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if text.startswith("---\n"):
        parts = text.split("---\n", 2)
        body = parts[2] if len(parts) >= 3 else text
    else:
        body = text
    lines = body.strip().split("\n")
    if not lines or not lines[0].startswith("# "):
        return None
    title = lines[0][2:].strip()
    rest = "\n".join(lines[1:])
    summary = rest.split("## 关联概念")[0].strip()
    return title, summary


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class AtomEmbeddingStore:
    """按项目分文件的原子 embedding 缓存 + 线性余弦相似度查找。

    量级是"原子数"（预期几十到几百），不是"文档chunk数"（几千），线性扫描
    足够，不需要 ANN 索引/专门向量数据库。"""

    def __init__(self, cache_dir: str, project_name: str, vector_mjs: str):
        self.cache_path = Path(cache_dir) / f"atom_embeddings_{project_name}.json"
        self.vector_mjs = vector_mjs
        self._data: Dict[str, dict] = self._load()

    def _load(self) -> Dict[str, dict]:
        if not self.cache_path.exists():
            return {}
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)

    def find_similar_atom(self, title: str, summary: str, threshold: float = 0.85) -> Optional[str]:
        """给定候选原子的标题+摘要，返回已有原子里语义最相似且超过阈值的
        atom_slug；没有可用 embedding（无 API key/调用失败）或都不够相似
        时返回 None——调用方应把 None 理解为"退化到精确匹配去重"，不是
        "确认没有相似原子"。"""
        result = embed_text(self.vector_mjs, f"{title}\n{summary}")
        if "error" in result:
            return None
        new_embedding = result["embedding"]

        best_slug, best_score = None, 0.0
        for slug, entry in self._data.items():
            score = _cosine_similarity(new_embedding, entry["embedding"])
            if score > best_score:
                best_slug, best_score = slug, score

        # 无论是否命中相似原子，都把这个新原子的 embedding 存下来，
        # 供下一次比对使用——不命中也要存，否则永远只能跟"第一个原子"之前
        # 存过的那批比，新原子之间不会互相发现相似
        return best_slug if best_score >= threshold else None

    def content_similarity(self, existing_slug: str, new_title: str, new_summary: str) -> Optional[float]:
        """给定"即将被更新的原子"（existing_slug）和"新提炼出的内容"，算
        两者的语义相似度——用于write_atom()判断这次"更新"是不是真的只是
        改写同一件事，还是内容实质变了（该走待校准流程，不该悄悄覆盖）。

        复用缓存里已经存过的旧原子embedding（存的时候就是"上一次的
        title+summary"），不用重新embed旧内容，只embed新内容算一次。
        旧原子没有缓存过embedding（比如embedding功能是后来才接入的存量
        原子）或新内容embed失败时返回None——调用方按None处理成"没法判断，
        走默认的直接更新路径"，不阻塞正常流程。"""
        if existing_slug not in self._data:
            return None
        result = embed_text(self.vector_mjs, f"{new_title}\n{new_summary}")
        if "error" in result:
            return None
        return _cosine_similarity(result["embedding"], self._data[existing_slug]["embedding"])

    def store_embedding(self, atom_slug: str, title: str, summary: str) -> bool:
        """计算并存储一个原子的 embedding，返回是否成功（失败=无可用API）。"""
        result = embed_text(self.vector_mjs, f"{title}\n{summary}")
        if "error" in result:
            return False
        self._data[atom_slug] = {"embedding": result["embedding"], "title": title}
        self._save()
        return True

    def backfill_missing(self, vault_path: str, project_name: str, chunk_size: int = 200) -> dict:
        """给vault里已存在、但embedding缓存里还没有的原子文件回填embedding。

        真实gap（2026-07-16发现）：EA项目00→03→08→01四层的4059个原子是在
        SiliconFlow凭证配置之前提炼的，store_embedding()当时因为没API key
        静默失败（优雅降级设计的副作用），从没被写进缓存——导致它们没法
        参与后续新原子的语义去重比对，find_similar_atom()只能扫到"配置凭证
        之后"新写入的原子。这里只读已有原子文件内容算embedding，不重新调
        LLM提炼（不产生DeepSeek费用，只有embedding API费用）。

        按chunk_size分批、每批完成后立刻_save()——不是攒够全部原子再一次性
        存盘：几千个原子如果一次性subprocess调用中途超时/网络中断，不分批
        存盘会导致这批已经算好的embedding全部丢失，下次重跑还得从头来。"""
        project_dir = Path(vault_path) / project_name
        all_files = list(project_dir.glob("*.md"))
        to_backfill = []  # (slug, title, embed_text)
        unparseable = 0
        for md_file in all_files:
            slug = md_file.stem
            if slug in self._data:
                continue
            parsed = _parse_atom_file(md_file)
            if parsed is None:
                unparseable += 1
                continue
            title, atom_summary = parsed
            to_backfill.append((slug, title, f"{title}\n{atom_summary}"))

        result = {
            "total_atom_files": len(all_files),
            "already_cached": len(all_files) - len(to_backfill) - unparseable,
            "to_backfill": len(to_backfill),
            "backfilled": 0,
            "skipped_unparseable": unparseable,
            "errors": [],
        }
        if not to_backfill:
            return result

        for i in range(0, len(to_backfill), chunk_size):
            chunk = to_backfill[i:i + chunk_size]
            texts = [t for _, _, t in chunk]
            emb_result = embed_texts_batched(self.vector_mjs, texts, timeout=max(60, len(texts) * 3))
            if "error" in emb_result:
                result["errors"].append({"chunk_start": i, "chunk_size": len(chunk), "error": emb_result["error"]})
                continue
            embeddings = emb_result["embeddings"]
            for (slug, title, _), emb in zip(chunk, embeddings):
                self._data[slug] = {"embedding": emb, "title": title}
                result["backfilled"] += 1
            self._save()

        return result
