#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：封装对 obsidian-mcp-server（Node.js）的 subprocess 调用。

迁移来源：原 ob_sync_agent.py 的 check_mcp_server() 和 check_sync_integrity()
各自独立拼接了一段几乎相同的 `node -e "import(...).then(v => {...})"` 字符串
+ 相同的 subprocess.run/超时/JSON解析/异常处理逻辑——两处独立维护同一段调用
样板，是"迁移不是照搬"该抽共享模块的场景。这里统一成 run_vault_check()，
调用方只需要提供 buildIndex 完成后要执行的那一小段 JS 表达式。
"""

import json
import os
import subprocess
from typing import Optional


def run_vault_check(server_script: str, vault_path: str, js_after_build: str, timeout: int = 30) -> dict:
    """在 vault.mjs 的 buildIndex() 基础上执行一段自定义 JS，返回其 console.log 的 JSON 输出。

    js_after_build 里可以直接引用变量名 `idx`（已经 buildIndex 过的索引对象），
    必须以 `console.log(JSON.stringify(...))` 结尾。异常统一转换成 {"error": "..."}，
    调用方不需要各自处理 FileNotFoundError/超时/JSON解析失败。
    """
    script = (
        f"import('{server_script}').then(v => {{"
        f"const idx = v.buildIndex('{vault_path}');"
        f"{js_after_build}"
        f"}}).catch(e => console.log(JSON.stringify({{error: e.message}})));"
    )
    output = ""
    try:
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.path.dirname(server_script),
        )
        output = result.stdout.strip() or result.stderr.strip()
        return json.loads(output)
    except FileNotFoundError:
        return {"error": f"Server 脚本不存在: {server_script}"}
    except subprocess.TimeoutExpired:
        return {"error": f"超过 {timeout} 秒未响应"}
    except json.JSONDecodeError as e:
        return {"error": f"输出解析失败: {e}; 原始输出: {output[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def build_index_stats(server_script: str, vault_path: str, timeout: int = 30) -> dict:
    """返回 buildIndex() 后的笔记数/标签数统计，用于巡检 MCP Server 连通性。"""
    return run_vault_check(
        server_script, vault_path,
        "console.log(JSON.stringify({notes: idx.byPath.size, tags: idx.tagIndex.size}));",
        timeout=timeout,
    )


def check_paths_indexed(server_script: str, vault_path: str, rel_paths: "list[str]", timeout: int = 30) -> dict:
    """检查给定的相对路径是否存在于 buildIndex() 后的 byPath 索引里，用于同步完整性抽查。"""
    check_entries = ", ".join(f'"{p}": idx.byPath.has("{p}")' for p in rel_paths)
    return run_vault_check(
        server_script, vault_path,
        f"const results = {{ {check_entries} }}; console.log(JSON.stringify(results));",
        timeout=timeout,
    )
