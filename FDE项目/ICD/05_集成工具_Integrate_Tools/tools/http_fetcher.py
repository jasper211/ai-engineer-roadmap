#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · tools/http_fetcher.py · 标准库 HTTP GET（无浏览器、无凭证、无完整请求头）

职责边界：只做"抓原始字节"。不解析 JSON/HTML/PDF 业务内容，不落盘，不写库。

安全约束（对齐任务书 T003 功能要求）：
- 固定可识别 User-Agent；连接/读取超时分离；有限重定向；最大响应体限制。
- 不记录 Cookie / Authorization / 完整请求头；日志只保留安全元数据。
- 网络失败（未收到 HTTP 响应）→ http_status=None；HTTP 4xx/5xx/超限 → http_status 非空。

三态映射（对齐 data_contract.md fetch_run CHECK 约束）：
- 拿到字节 → fetch_status='OK'
- 收到 HTTP 响应但不可用（4xx/5xx/超限）→ fetch_status='HTTP_ERROR'，http_status 非空
- 网络层失败 → fetch_status='NETWORK_ERROR'，http_status=None

仅用 Python 标准库；本模块单线程设计（CLI 逐源串行），超时经模块级 _Timeouts
注入到连接类，抓取结束后恢复。
"""

import http.client
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

# 固定可识别 UA：标明来源、用途、纯标准库、不带 Cookie
USER_AGENT = (
    "ICD-Disclosure-Fetcher/0.1.0 "
    "(stdlib-urllib; HK insurer public disclosure collection; no-cookies)"
)

CONNECT_TIMEOUT = 10.0   # 秒：TCP 连接建立
READ_TIMEOUT = 30.0      # 秒：读响应体
MAX_REDIRECTS = 5        # 有限重定向
MAX_BODY_BYTES = 20 * 1024 * 1024  # 20 MiB 上限


class _Timeouts:
    """单线程下按次注入的连接/读取超时（默认用模块常量）。"""
    connect = CONNECT_TIMEOUT
    read = READ_TIMEOUT


class _TimeoutConnectionMixin:
    """连接阶段用 _Timeouts.connect，读取阶段切到 _Timeouts.read。"""

    def connect(self):
        saved = getattr(self, "timeout", None)
        try:
            self.timeout = _Timeouts.connect
            super().connect()
        finally:
            self.timeout = saved
            sock = getattr(self, "sock", None)
            if sock is not None:
                try:
                    sock.settimeout(_Timeouts.read)
                except Exception:  # noqa: BLE001 —— 尽力而为，不影响主流程
                    pass


class _HTTPConnection(_TimeoutConnectionMixin, http.client.HTTPConnection):
    pass


class _HTTPSConnection(_TimeoutConnectionMixin, http.client.HTTPSConnection):
    pass


class _ConnectTimeoutHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_HTTPConnection, req)


class _ConnectTimeoutHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(
            _HTTPSConnection, req,
            context=self._context, check_hostname=self._check_hostname,
        )


class _LimitedRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS
    max_repeats = MAX_REDIRECTS


def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        _ConnectTimeoutHTTPHandler(),
        _ConnectTimeoutHTTPSHandler(),
        _LimitedRedirectHandler(),
    )


@dataclass
class FetchOutcome:
    fetch_status: str                              # 'OK' | 'HTTP_ERROR' | 'NETWORK_ERROR'
    http_status: Optional[int] = None              # 网络失败为 None
    final_url: Optional[str] = None                # 重定向后的最终 URL
    body: bytes = b""                              # 仅 OK 非空
    error_code: Optional[str] = None               # NETWORK_*/HTTP_* 映射，无匹配则 None
    note: str = ""                                 # 安全元数据描述（不含凭证/请求头）


def _map_http_error(status: Optional[int]) -> Optional[str]:
    if status == 403:
        return "HTTP_403"
    if status == 404:
        return "HTTP_404"
    if status is not None and status >= 500:
        return "HTTP_5XX"
    return None


def _map_network_error(reason) -> str:
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "NETWORK_TIMEOUT"
    return "NETWORK_CONNECTION"


def _read_capped(resp, cap: int):
    """读满响应体但总字节数不得超过 cap；超限返回 (None, 已读字节数)。"""
    chunks = []
    total = 0
    while True:
        n = min(65536, cap + 1 - total)
        chunk = resp.read(n)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > cap:
            return None, total
    return b"".join(chunks), total


def fetch(
    url: str,
    *,
    max_bytes: Optional[int] = None,
    connect_timeout: Optional[float] = None,
    read_timeout: Optional[float] = None,
) -> FetchOutcome:
    """抓取一个 URL 的原始字节；返回 FetchOutcome。只抛 KeyboardInterrupt/系统异常，
    业务层面的 HTTP/网络失败一律折叠进 FetchOutcome（不向上抛）。"""
    cap = max_bytes if max_bytes is not None else MAX_BODY_BYTES
    eff_connect = connect_timeout if connect_timeout is not None else CONNECT_TIMEOUT
    eff_read = read_timeout if read_timeout is not None else READ_TIMEOUT

    old = (_Timeouts.connect, _Timeouts.read)
    _Timeouts.connect, _Timeouts.read = eff_connect, eff_read
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        )
        opener = _build_opener()

        try:
            resp = opener.open(req)
        except urllib.error.HTTPError as e:
            # 4xx/5xx/重定向超限：有 HTTP 状态码，无可用字节
            status = getattr(e, "code", None)
            return FetchOutcome(
                "HTTP_ERROR", status, e.geturl(), b"",
                _map_http_error(status), f"HTTP {status}",
            )
        except urllib.error.URLError as e:
            reason = e.reason
            code = _map_network_error(reason)
            return FetchOutcome(
                "NETWORK_ERROR", None, None, b"", code,
                f"网络失败: {type(reason).__name__}: {reason}",
            )
        except socket.timeout as e:
            return FetchOutcome(
                "NETWORK_ERROR", None, None, b"", "NETWORK_TIMEOUT",
                f"超时: {e}",
            )
        except (ConnectionError, OSError) as e:
            return FetchOutcome(
                "NETWORK_ERROR", None, None, b"", "NETWORK_CONNECTION",
                f"连接失败: {type(e).__name__}: {e}",
            )

        with resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", None)
            final_url = resp.geturl() if hasattr(resp, "geturl") else url
            body, total = _read_capped(resp, cap)
            if body is None:
                return FetchOutcome(
                    "HTTP_ERROR", status, final_url, b"", None,
                    f"响应体超过上限 {cap} 字节（已读 >= {total}）",
                )
            return FetchOutcome("OK", status, final_url, body, None, "")
    finally:
        _Timeouts.connect, _Timeouts.read = old
