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
    vector_build_timeout: int = 8,
) -> dict:
    """调用 obsidian-mcp-server 的 hybridSearch，返回 {results, has_vector} 或 {error}。

    mode: "hybrid" | "keyword" | "vector" | "graph"（同 obsidian-mcp-server 的定义）

    vector_build_timeout: buildVectorIndex 自己的超时上限（秒），独立于外层
    subprocess 的 timeout。2026-07-18 真实复现过的问题：embedding_config.json
    配置真实key后，"没有key"这条优雅降级路径不再触发，缓存未命中时
    buildVectorIndex 会老老实实现算全量embedding（vault 7000+文件，预计
    20-60分钟），而不是像之前"没配key直接抛异常→秒级捕获降级"那样快速失败。
    这里给 buildVectorIndex 单独包一层 Promise.race 超时——命中缓存的正常
    情况几秒内跑完不受影响；缓存未命中需要现算的情况，8秒内跑不完就当作
    "这次拿不到向量"直接降级，而不是让整个请求跟着现算全量embedding的
    时间陪跑。真正需要一次性构建向量索引，走专门的 --backfill 之类的入口，
    不应该是普通一次查询请求的副作用。
    """
    query_json = json.dumps(query, ensure_ascii=False)
    options_json = json.dumps({"mode": mode, "maxResults": max_results}, ensure_ascii=False)

    # 只有 mode 真的需要向量（hybrid/vector）才尝试 buildVectorIndex——之前不管
    # mode 是什么都无条件尝试，真实复现过：vault 涨到7000+文件后，缓存不匹配时
    # buildVectorIndex 会现算全量embedding，连 keyword/graph 这种压根不需要向量
    # 的请求也被拖到60秒超时（本该几百毫秒内返回）。keyword/graph 模式直接跳过，
    # 不影响 hybrid/vector 模式原有的"缓存未命中则现算+优雅降级"行为。
    needs_vector = mode in ("hybrid", "vector")
    vector_build_ms = vector_build_timeout * 1000
    vector_setup = (
        (
            f"let vectorIndex = null;"
            f"try {{"
            f"  const withTimeout = (p, ms) => Promise.race(["
            f"    p, new Promise((_, rej) => setTimeout(() => rej(new Error('vector_build_timeout')), ms))"
            f"  ]);"
            f"  vectorIndex = await withTimeout(vec.buildVectorIndex(idx, {{ useCache: true }}), {vector_build_ms});"
            f"  if (!vectorIndex.embeddings || vectorIndex.embeddings.length === 0) vectorIndex = null;"
            f"}} catch (e) {{ vectorIndex = null; }}"
        )
        if needs_vector
        else "let vectorIndex = null;"
    )

    script = (
        f"import('{vault_mjs}').then(async v => {{"
        f"const vec = await import('{vector_mjs}');"
        f"const idx = v.buildIndex('{vault_path}');"
        f"{vector_setup}"
        f"const results = await vec.hybridSearch(idx, vectorIndex, {query_json}, {options_json});"
        f"console.log(JSON.stringify({{ results, hasVector: !!vectorIndex }}));"
        f"process.exit(0);"  # buildVectorIndex超时放弃后，被丢弃的embedding请求可能还在
        # 后台跑，不强制退出的话Node事件循环会一直等它，subprocess.run()就白等了——
        # 拿到结果就立刻退出，不等任何遗留的后台异步任务
        f"}}).catch(e => {{ console.log(JSON.stringify({{error: e.message}})); process.exit(1); }});"
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
