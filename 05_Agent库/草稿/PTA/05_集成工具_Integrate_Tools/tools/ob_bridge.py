#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：OB 背景检索桥接——PTA 作为 OB 的薄客户端。

设计依据（OB侧 skills/knowledge_retrieval.py 顶部注释）：PTA 只知道"什么时候
该问、问完怎么用"，不直接耦合 MCP 协议细节，也不重新实现图遍历/向量检索逻辑。

用 subprocess 调用 OB 自己的 agent.py --retrieve，而不是 import OB 的 Python
包：PTA 和 OB 各自都有 agents/skills/tools 同名包，且都靠 sys.path.insert 把
自己的 05/06/07 编号目录插到最前面识别 import——两边在同一个 Python 进程里先后
import 会互相污染 sys.modules 缓存（"tools.xxx" 具体解析到哪个项目的代码，取决
于谁先 import，不会报错，是静默污染），跨进程调用没有这个风险，代价只是每次
多一个 python 子进程，背景检索本来也不是高频路径，可接受。

OB 不存在/调用失败/超时都优雅返回 None——背景检索失败不该让调用方的主流程也
跟着失败，这跟 OB 自己在向量索引不可用时优雅降级为关键词+图谱是同一条设计
精神：宁可"这次没有背景"，不能让不相关的故障拖垮正在做的事。
"""

import subprocess
from pathlib import Path
from typing import Optional

OB_AGENT_PY = Path(
    "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/"
    "AI工程能力整改项目/05_Agent库/草稿/OB/04_定义Agent_Define_Agent/agents/agent.py"
)

DEFAULT_TIMEOUT = 25  # hybrid 模式在向量索引不可用时会自动降级为关键词+图谱，
                       # 实测 <1秒；这里留足余量，不是指望真的等满


def get_background(query: str, mode: str = "hybrid", max_results: int = 5,
                    timeout: int = DEFAULT_TIMEOUT) -> Optional[str]:
    """返回 OB 已经格式化好、可以直接拼进 LLM 提示词的背景文本（含信任标注）。
    找不到 OB / 调用异常 / 超时 / 空查询，一律返回 None，不抛异常。"""
    query = (query or "").strip()
    if not query or not OB_AGENT_PY.exists():
        return None
    try:
        result = subprocess.run(
            ["python3", str(OB_AGENT_PY), "--retrieve", query,
             "--mode", mode, "--max-results", str(max_results)],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    if not text or "未检索到相关背景" in text or "背景检索失败" in text:
        return None
    return text
