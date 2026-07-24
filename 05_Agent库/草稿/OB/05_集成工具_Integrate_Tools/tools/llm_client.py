#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：LLM 调用封装（移植自 PTA 的 tools/llm_client.py，逻辑不变）。

不做成跨 Agent import——每个 Agent 自己的 tools/ 保持自包含，是已确立的
惯例（PTA/OB 各自维护一份，不是共享一个外部包）。这份逻辑本身已经在 PTA 上
真实跑过多次、修过真实的 SSL 证书路径坑（build_ssl_context 的存在就是那次
修复的痕迹），直接复用已验证过的实现，不重新发明。
"""

import json
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
# 2026-07-22更新：旧别名"deepseek-chat"（当前暗中指向deepseek-v4-flash
# 非思考模式）将在2026-07-24 15:59 UTC下线（DeepSeek官方文档确认），改用
# 正式模型ID。Jasper明确选择pro档（deepseek-v4-pro，1.6T总参数/49B激活
# 参数，质量对标顶级闭源模型），不是更快更便宜的flash档——本次调整前
# vault里已有的原子都是flash跑出来的，这个模型切换之后新提炼的原子在
# 质量基准上跟旧原子会不一致，是已知的、有意识的取舍，不是bug。
DEFAULT_MODEL = "deepseek-v4-pro"


def build_ssl_context() -> ssl.SSLContext:
    """构造 HTTPS 用的 SSL 上下文。有些 Python 安装（尤其是 Homebrew 装的）默认证书路径
    是坏的（openssl@3 的 cert.pem 不存在），urlopen 会报 CERTIFICATE_VERIFY_FAILED。
    这里按优先级找一个真实存在的 CA 证书包，而不是绕过证书校验。"""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for candidate in (
        "/etc/ssl/cert.pem",
        "/usr/local/etc/ca-certificates/cert.pem",
        "/opt/homebrew/etc/ca-certificates/cert.pem",
    ):
        if Path(candidate).exists():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


_SSL_CONTEXT = build_ssl_context()


def call_deepseek(system_prompt: str, user_content: str, api_key: str,
                   model: str = DEFAULT_MODEL, max_retries: int = 2,
                   temperature: float = 0, json_mode: bool = True,
                   max_tokens: int = 8192) -> str:
    """调用 DeepSeek Chat Completions（OpenAI 兼容接口），返回 message.content 字符串。

    max_tokens 显式设置为8192（deepseek-chat文档标注的输出上限）——此前
    没传这个参数，走API默认值，真实复现过：源文档本身信息密度高（比如一份
    包含几十个价值节点的表格布局dump），提炼出的atoms数组太长，输出在还没
    走完整个JSON结构时被默认的更低output限制截断，产出'Unterminated
    string'这类"JSON从中间断掉"的错误——这跟已经修过的"字符串内容转义
    错误"是不同性质的问题，转义修复函数救不了从根上就不完整的JSON，
    只能从源头把输出上限提高。"""
    body_dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body_dict["response_format"] = {"type": "json_object"}
    body = json.dumps(body_dict).encode("utf-8")

    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            # 2026-07-24：超时从60秒提到180秒——deepseek-v4-pro（1.6T参数，
            # 比flash大得多）响应明显更慢，切pro后真实批次里出现大量
            # "read operation timed out"（读响应体阶段超时，不是连接超时），
            # 60秒对pro不够用，flash时期够用是因为那是个小得多的模型。
            with urllib.request.urlopen(req, timeout=180, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and attempt < max_retries:
                wait = 2 ** (attempt + 1)
                print(f"  [限流] 429，{wait}s 后重试...")
                time.sleep(wait)
                last_err = f"HTTP {e.code}: {detail}"
                continue
            raise RuntimeError(f"DeepSeek API 请求失败 HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            # 真实批量提炼时复现过：连续大量请求会偶发 SSL 连接中断
            # （UNEXPECTED_EOF_WHILE_READING）/读超时，这类网络抖动通常是
            # 暂时性的——之前只对 HTTP 429 限流重试，URLError 直接抛异常，
            # 188 个文件的批次里 17 个因为这个原因失败，比例不低。这里补上
            # 同样的重试逻辑，不区分"是不是SSL的错"，只要是 URLError 就重试。
            # 2026-07-24补充：单独加 TimeoutError——urllib的"读响应体阶段
            # 超时"（跟"连接阶段超时"不同）抛出的是裸 TimeoutError，不会被
            # urllib.error.URLError 接住，之前完全没有重试，切pro模型后
            # 这类超时变得频繁（pro生成慢），真实复现过91个文件的批次里
            # 10+个因为这个原因直接失败、一次重试都没有。
            if attempt < max_retries:
                wait = 2 ** (attempt + 1)
                print(f"  [网络错误] {e}，{wait}s 后重试...")
                time.sleep(wait)
                last_err = f"{type(e).__name__}: {e}"
                continue
            raise RuntimeError(f"DeepSeek API 网络错误（已重试 {max_retries} 次）: {e}") from e
    raise RuntimeError(f"DeepSeek API 请求失败（已重试 {max_retries} 次）: {last_err}")
