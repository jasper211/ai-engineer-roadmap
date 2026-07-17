#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：加载 embedding 服务配置（OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_EMBEDDING_MODEL），
供调用 vector.mjs 的 node 子进程使用。

配置文件（02_配置项目_Configure_Project/embedding_config.json）不进 git（同目录
.gitignore 已排除，同 wecom_config.json 的先例），只在这台机器本地存在，真实
key 由 Jasper 自己填入，不经我手。文件不存在或还是模板占位符时，返回原始
环境变量（不报错）——这样向量层继续走已经验证过的"无 API key 优雅降级为
关键词+图谱"路径，不会因为没配置就崩溃。

2026-07-16：Jasper 提供硅基流动（SiliconFlow）的 API key，模型固定
BAAI/bge-m3——这跟此前 obsidian-mcp-server 真实构建过一次的 .vector-cache.json
（3061 chunks）用的是同一个模型，只是那次的 key/base_url 是在另一个终端会话
的环境里配置的，没有留在这个会话可见的地方。
"""

import json
import os
from pathlib import Path

CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "02_配置项目_Configure_Project" / "embedding_config.json"
)

_ENV_KEYS = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_EMBEDDING_MODEL")


def load_embedding_env() -> dict:
    """返回合并了 embedding_config.json 真实值的环境变量字典，供
    subprocess.run(..., env=...) 直接使用。"""
    env = dict(os.environ)
    if not CONFIG_PATH.exists():
        return env
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return env
    for key in _ENV_KEYS:
        value = config.get(key, "")
        if value and not value.startswith("REPLACE_WITH"):
            env[key] = value
    return env


def has_real_credentials() -> bool:
    """快速判断是否已经配置了真实（非占位符）的 API key，不发起任何调用。"""
    env = load_embedding_env()
    return bool(env.get("OPENAI_API_KEY"))
