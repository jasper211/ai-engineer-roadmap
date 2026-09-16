"""WPS 365开放平台只读客户端。

V1只读：只实现GET与读取语义的POST（列举/查找），不提供任何写接口。
凭证走企业自建应用的client_credentials，token缓存在本地文件，不入库。

接口事实来自开放平台文档（2026-09核对）：
  token   POST https://openapi.wps.cn/oauth2/token  (form, 有效期7200s)
  多维表格 /v7/coop/dbsheet/{file_id}/schema | /sheets/{sheet_id}/records
  传统表格 /v7/sheets/{file_id}/worksheets | /worksheets/{ws}/range_data/find
  智能表格 /v7/airsheet/... 同传统表格，仅前缀与权限不同
  云文档   /v7/links/{link_id}/meta | /v7/files/{file_id}/meta | /v7/doclibs
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


BASE = "https://openapi.wps.cn"
TOKEN_PATH = "/oauth2/token"
TOKEN_EARLY_REFRESH = 300  # 提前5分钟换新token，避免边界失效
DEFAULT_TIMEOUT = 30

# 响应里游标字段名在各接口间不统一，按此顺序探测
CURSOR_KEYS = ("next_cursor", "cursor", "next_page_token", "page_token", "next")

# python.org的解释器不带CA根证书，按序回退到系统证书，否则握手就失败
CA_CANDIDATES = ("/etc/ssl/cert.pem", "/usr/local/etc/ca-certificates/cert.pem",
                 "/opt/homebrew/etc/ca-certificates/cert.pem")


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    env_ca = os.environ.get("SSL_CERT_FILE")
    for candidate in ((env_ca,) if env_ca else ()) + CA_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


class WPSError(Exception):
    """开放平台返回的业务错误或HTTP错误。"""

    def __init__(self, message: str, code: Any = None, payload: Any = None):
        super().__init__(message)
        self.code = code
        self.payload = payload


class WPSClient:
    def __init__(
        self,
        app_id: str,
        app_key: str,
        token_cache: str | Path | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        if not app_id or not app_key:
            raise ValueError("缺少app_id/app_key，先配置wps_config.json或环境变量")
        self._app_id = app_id
        self._app_key = app_key
        self._timeout = timeout
        self._token_cache = Path(token_cache) if token_cache else None
        self._token: str = ""
        self._expires_at: float = 0.0
        self._ssl = _ssl_context()

    # ---------- 凭证 ----------

    def token(self) -> str:
        now = time.time()
        if self._token and now < self._expires_at:
            return self._token
        if self._load_cached_token(now):
            return self._token

        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._app_id,
                "client_secret": self._app_key,
            }
        ).encode()
        data = self._raw_request(
            "POST",
            BASE + TOKEN_PATH,
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if "access_token" not in data:
            raise WPSError(f"取token失败：{data}", code=data.get("code"), payload=data)
        self._token = data["access_token"]
        self._expires_at = now + int(data.get("expires_in", 7200)) - TOKEN_EARLY_REFRESH
        self._save_cached_token()
        return self._token

    def _load_cached_token(self, now: float) -> bool:
        if not self._token_cache or not self._token_cache.exists():
            return False
        try:
            cached = json.loads(self._token_cache.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        if cached.get("app_id") != self._app_id:
            return False
        if now >= float(cached.get("expires_at", 0)):
            return False
        self._token = cached.get("access_token", "")
        self._expires_at = float(cached["expires_at"])
        return bool(self._token)

    def _save_cached_token(self) -> None:
        if not self._token_cache:
            return
        self._token_cache.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "app_id": self._app_id,
            "access_token": self._token,
            "expires_at": self._expires_at,
        }
        self._token_cache.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(self._token_cache, 0o600)

    # ---------- HTTP ----------

    def _raw_request(self, method: str, url: str, body: bytes | None, headers: dict) -> dict:
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout, context=self._ssl) as resp:
                text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise WPSError(f"HTTP {exc.code} {url}\n{detail}", code=exc.code) from exc
        except urllib.error.URLError as exc:
            raise WPSError(f"网络不可达 {url}：{exc.reason}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise WPSError(f"响应不是JSON：{text[:300]}") from exc

    def call(self, method: str, path: str, *, params: dict | None = None,
             json_body: dict | None = None) -> dict:
        """调用开放平台接口，返回data段；非0 code直接抛错。"""
        url = BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Authorization": f"Bearer {self.token()}",
            "Content-Type": "application/json",
        }
        body = json.dumps(json_body, ensure_ascii=False).encode() if json_body is not None else None
        payload = self._raw_request(method, url, body, headers)
        code = payload.get("code")
        if code not in (None, 0):
            raise WPSError(
                f"接口失败 {path} code={code} msg={payload.get('msg')}",
                code=code,
                payload=payload,
            )
        return payload.get("data", payload)

    # ---------- 云文档：定位文件 ----------

    def link_meta(self, link_id: str) -> dict:
        """分享链接 /l/{link_id} → file_id、drive_id。权限 kso.file_link.readwrite。"""
        return self.call("GET", f"/v7/links/{link_id}/meta")

    def file_meta(self, file_id: str) -> dict:
        """文件元信息，含名称/类型/修改时间。权限 kso.file.read。"""
        return self.call("GET", f"/v7/files/{file_id}/meta")

    def doclibs(self) -> dict:
        """团队文档库列表，取 items[].drive.id。权限 kso.doclib.read。"""
        return self.call("GET", "/v7/doclibs")

    def children(self, drive_id: str, parent_id: str = "0", *,
                 filter_exts: str | None = None, page_size: int = 50) -> dict:
        """列出盘内文件，根目录 parent_id 传 0。权限 kso.file.read。"""
        params: dict[str, Any] = {"page_size": page_size}
        if filter_exts:
            params["filter_exts"] = filter_exts
        return self.call("GET", f"/v7/drives/{drive_id}/files/{parent_id}/children", params=params)

    # ---------- 多维表格 dbsheet ----------

    def dbsheet_schema(self, file_id: str) -> dict:
        """多维表格结构，数据表ID在 sheets[].id。权限 kso.dbsheet.read。"""
        return self.call("GET", f"/v7/coop/dbsheet/{file_id}/schema")

    def dbsheet_records(self, file_id: str, sheet_id: str, *, page_size: int = 100,
                        max_pages: int = 200) -> list[dict]:
        """列举一张数据表的全部记录，自动翻页直到游标耗尽。"""
        path = f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/records"
        records: list[dict] = []
        cursor: Any = None
        seen: set[str] = set()
        for _ in range(max_pages):
            body: dict[str, Any] = {
                "prefer_id": False,
                "show_fields_info": False,
                "text_value": "text",
                "page_size": page_size,
            }
            if cursor is not None:
                body["cursor"] = cursor
            data = self.call("POST", path, json_body=body)
            page = data.get("records") or data.get("items") or []
            records.extend(page)
            cursor = _next_cursor(data)
            # 游标缺失、为空、或原地打转都视作到底，避免死循环
            if not cursor or str(cursor) in seen or not page:
                break
            seen.add(str(cursor))
        return records

    # ---------- 传统表格 sheets / 智能表格 airsheet ----------

    def worksheets(self, file_id: str, kind: str = "sheets") -> dict:
        """工作表列表，ID在 sheets[].sheet_id。权限 kso.sheets.read / kso.airsheet.read。"""
        return self.call("GET", f"/v7/{_prefix(kind)}/{file_id}/worksheets")

    def range_data(self, file_id: str, worksheet_id: Any, *, kind: str = "sheets",
                   row_from: int = 0, row_to: int = 999, col_from: int = 0,
                   col_to: int = 49) -> dict:
        """读一块选区的全部单元格。condition传空数组=不筛选、输出全部。"""
        body = {
            "range": {
                "row_from": row_from,
                "row_to": row_to,
                "col_from": col_from,
                "col_to": col_to,
            },
            "filter": {"condition": [], "search": [], "duplicates": {"col": []}},
        }
        return self.call(
            "POST",
            f"/v7/{_prefix(kind)}/{file_id}/worksheets/{worksheet_id}/range_data/find",
            json_body=body,
        )


def _prefix(kind: str) -> str:
    if kind == "sheets":
        return "sheets"
    if kind == "airsheet":
        return "airsheet"
    raise ValueError(f"单元格类接口只支持 sheets/airsheet，收到 {kind}")


def _next_cursor(data: dict) -> Any:
    for key in CURSOR_KEYS:
        if data.get(key):
            return data[key]
    return None


def client_from_config(config_path: str | Path, token_cache: str | Path | None = None) -> WPSClient:
    """凭证优先读环境变量WPS_APP_ID/WPS_APP_KEY，其次读配置文件。"""
    app_id = os.environ.get("WPS_APP_ID", "")
    app_key = os.environ.get("WPS_APP_KEY", "")
    if not (app_id and app_key):
        path = Path(config_path)
        if not path.exists():
            raise WPSError(f"未配置凭证：既无环境变量，也找不到 {path}")
        conf = json.loads(path.read_text(encoding="utf-8"))
        app_id = conf.get("app_id", "")
        app_key = conf.get("app_key", "")
    return WPSClient(app_id, app_key, token_cache=token_cache)
