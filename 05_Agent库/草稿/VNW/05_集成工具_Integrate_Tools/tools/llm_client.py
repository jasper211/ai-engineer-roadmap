"""VNW自包含的JSON模型客户端。

凭证只从环境变量或VNW私有配置读取，禁止跨Agent读取密钥文件。
"""
from __future__ import annotations

import json
import http.client
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-pro"


def _ssl_context() -> ssl.SSLContext:
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


def call_json_model(
    system_prompt: str,
    user_content: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
    max_tokens: int = 32768,
) -> str:
    if not api_key:
        raise ValueError("缺少模型API Key")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=240, context=_ssl_context()) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code == 429 and attempt < max_retries:
                time.sleep(2 ** (attempt + 1))
                last_error = f"HTTP {error.code}: {detail}"
                continue
            raise RuntimeError(f"模型请求失败 HTTP {error.code}: {detail}") from error
        except (
            urllib.error.URLError,
            TimeoutError,
            http.client.IncompleteRead,
            http.client.RemoteDisconnected,
        ) as error:
            if attempt < max_retries:
                time.sleep(2 ** (attempt + 1))
                last_error = f"{type(error).__name__}: {error}"
                continue
            raise RuntimeError(f"模型网络错误：{error}") from error
    raise RuntimeError(f"模型请求失败：{last_error}")
