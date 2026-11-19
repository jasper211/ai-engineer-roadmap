#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：LLM 调用封装（从 PTA-DISCOVER_文档任务发现器.py 抽取的 DeepSeek 调用逻辑）

抽取原因：`skills/daily_sensing.py` 也需要调用 DeepSeek，如果两处各自内联一份
重试/SSL 回退逻辑，以后遇到新的 API 坑（限流策略变化、换 base_url 等）容易
改出两份不一致的实现。这里抽成通用函数——`system_prompt` 从 PTA-DISCOVER
原来的模块级全局变量，改成显式参数，调用方自己决定提示词内容。

PTA-DISCOVER 本身也改为 import 这个模块（不再内联同一套逻辑），逻辑本身
原样不变，只是挪了位置——迁移时做过前后 `--dry-run` 输出比对，确认候选文件
扫描/去重这部分行为没有被这次重构影响（dry-run 不触发真实 API 调用，
只能验证到这一步；真实 API 调用路径另有一次人工验证）。
"""

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
# deepseek-chat/deepseek-reasoner 官方已宣布2026-07-24 15:59 UTC起完全下线
# （届时会路由到 deepseek-v4-flash 的非思考/思考模式，不是继续可用）——这次换
# 成 deepseek-v4-pro 既是 Jasper 要更强模型的明确要求，也顺带避开三天后的
# 硬性下线时间点，两者刚好同时满足。
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
        "/etc/ssl/cert.pem",  # macOS 系统自带
        "/usr/local/etc/ca-certificates/cert.pem",  # Homebrew (Intel)
        "/opt/homebrew/etc/ca-certificates/cert.pem",  # Homebrew (Apple Silicon)
    ):
        if Path(candidate).exists():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()  # 用默认路径，找不到就让它照常报错


_SSL_CONTEXT = build_ssl_context()

# --- 用量台账：每一次付费调用都留一行，便于事后归因 ---------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_USAGE_LOG = Path(
    os.environ.get("PTA_LLM_USAGE_LOG", str(_PROJECT_ROOT / "_runtime" / "llm_usage.jsonl"))
)


def _log_usage(record: dict) -> None:
    """追加一行 JSON。任何失败都吞掉：记账不能弄坏一次真实运行。"""
    try:
        _USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        record["at"] = datetime.now(UTC).isoformat()
        with _USAGE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass



def call_deepseek(system_prompt: str, user_content: str, api_key: str,
                   model: str = DEFAULT_MODEL, max_retries: int = 2,
                   temperature: float = 0, json_mode: bool = True) -> str:
    """调用 DeepSeek Chat Completions（OpenAI 兼容接口），返回 message.content 字符串。

    json_mode=True 时请求 `response_format: json_object`（PTA-DISCOVER 和
    daily_sensing 都要求模型输出严格 JSON，这里做成可选参数而不是写死，
    给以后非 JSON 场景留余地）。
    """
    body_dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
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
            # 60秒对deepseek-chat够用，但换成deepseek-v4-pro（带"思考模式"的
            # 推理模型）后真实跑EA项目6天累积diff时超时了——推理模型响应本来
            # 就比非推理的chat模型慢，尤其是大上下文，180秒是留了余量而不是
            # 精确计算出来的，之后如果还不够可能要考虑分批而不是继续加大超时。
            _started_at = time.monotonic()
            with urllib.request.urlopen(req, timeout=180, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                _usage = data.get("usage") or {}
                _log_usage({
                    "status": 200, "model": model, "attempt": attempt,
                    "request_id": resp.headers.get("x-request-id"),
                    "prompt_tokens": _usage.get("prompt_tokens"),
                    "completion_tokens": _usage.get("completion_tokens"),
                    "total_tokens": _usage.get("total_tokens"),
                    "duration_ms": int((time.monotonic() - _started_at) * 1000),
                })
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            _log_usage({"status": e.code, "model": model, "attempt": attempt, "detail": detail[:300]})
            if e.code == 429 and attempt < max_retries:
                wait = 2 ** (attempt + 1)
                print(f"  [限流] 429，{wait}s 后重试...")
                time.sleep(wait)
                last_err = f"HTTP {e.code}: {detail}"
                continue
            raise RuntimeError(f"DeepSeek API 请求失败 HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            _log_usage({"status": 0, "model": model, "attempt": attempt, "detail": str(e)[:300]})
            raise RuntimeError(f"DeepSeek API 网络错误: {e}") from e
    raise RuntimeError(f"DeepSeek API 请求失败（已重试 {max_retries} 次）: {last_err}")
