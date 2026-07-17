#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：封装对 obsidian-mcp-server 的 hybrid_search 调用（检索服务能力线①的技术底座）。

跟 mcp_bridge.py 是同一类"subprocess 调 node 脚本"的封装，但这里需要同时
import vault.mjs 和 vector.mjs 两个模块，且要处理向量索引的优雅降级：
buildVectorIndex() 在没有 OPENAI_API_KEY 且本地缓存失效/不匹配时会抛异常——
这不是 bug，是 obsidian-mcp-server 自己的设计（server.mjs 也是同样处理），
这里 catch 住转成 vectorIndex=null，让 hybridSearch 走"关键词+图谱"降级路径，
而不是让调用方自己应对 Node 异常。
"""

import json
import os
import subprocess
from typing import Optional

from tools.embedding_config import load_embedding_env


def hybrid_search(
    vault_mjs: str,
    vector_mjs: str,
    vault_path: str,
    query: str,
    mode: str = "hybrid",
    max_results: int = 5,
    timeout: int = 60,
) -> dict:
    """调用 obsidian-mcp-server 的 hybridSearch，返回 {results, has_vector} 或 {error}。

    mode: "hybrid" | "keyword" | "vector" | "graph"（同 obsidian-mcp-server 的定义）
    """
    query_json = json.dumps(query, ensure_ascii=False)
    options_json = json.dumps({"mode": mode, "maxResults": max_results}, ensure_ascii=False)

    script = (
        f"import('{vault_mjs}').then(async v => {{"
        f"const vec = await import('{vector_mjs}');"
        f"const idx = v.buildIndex('{vault_path}');"
        f"let vectorIndex = null;"
        f"try {{"
        f"  vectorIndex = await vec.buildVectorIndex(idx, {{ useCache: true }});"
        f"  if (!vectorIndex.embeddings || vectorIndex.embeddings.length === 0) vectorIndex = null;"
        f"}} catch (e) {{ vectorIndex = null; }}"
        f"const results = await vec.hybridSearch(idx, vectorIndex, {query_json}, {options_json});"
        f"console.log(JSON.stringify({{ results, hasVector: !!vectorIndex }}));"
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
        return {"error": f"obsidian-mcp-server 脚本不存在: {vector_mjs}"}
    except subprocess.TimeoutExpired:
        return {"error": f"超过 {timeout} 秒未响应"}
    except json.JSONDecodeError as e:
        return {"error": f"输出解析失败: {e}; 原始输出: {output[:300]}"}
    except Exception as e:
        return {"error": str(e)}
