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
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


BASE = "https://openapi.wps.cn"
TOKEN_PATH = "/oauth2/token"
AUTH_PATH = "/oauth2/auth"
TOKEN_EARLY_REFRESH = 300  # 提前5分钟换新token，避免边界失效
DEFAULT_TIMEOUT = 30
WALK_WORKERS = 6  # 并发列目录；再高容易触发平台限流

# 响应里游标字段名在各接口间不统一，按此顺序探测
CURSOR_KEYS = ("next_cursor", "cursor", "next_page_token", "page_token", "next")

# 云文档扩展名 → 该用哪套读取接口。名称在响应里可能叫ext/ftype/file_type，统一探测
EXT_KIND = {
    "db": "dbsheet", "dbt": "dbsheet",
    "et": "sheets", "xlsx": "sheets", "xls": "sheets", "csv": "sheets",
    "ksheet": "airsheet",
}
FOLDER_MARKS = ("folder", "dir", "directory")

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
        user_token_path: str | Path | None = None,
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
        # 存在用户token文件就走用户身份：数据范围跟随该用户，不必逐个盘配数据权限
        self._user_token_path = Path(user_token_path) if user_token_path else None
        self._token_lock = threading.Lock()

    # ---------- 凭证 ----------

    def uses_user_token(self) -> bool:
        return bool(self._user_token_path and self._user_token_path.exists())

    def token(self) -> str:
        with self._token_lock:
            return self._token_locked()

    def _token_locked(self) -> str:
        if self.uses_user_token():
            return self._user_access_token()
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

    # ---------- 用户授权 ----------

    def auth_url(self, redirect_uri: str, scopes: list[str], state: str) -> str:
        """构造授权跳转链接。scope必须已在开发者后台勾选申请，否则授权页会报错。"""
        query = urllib.parse.urlencode({
            "response_type": "code",
            "client_id": self._app_id,
            "redirect_uri": redirect_uri,
            "scope": ",".join(scopes),
            "state": state,
        })
        return f"{BASE}{AUTH_PATH}?{query}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """用回调拿到的code换用户access_token，落盘后续自动刷新。code十分钟内一次性有效。"""
        data = self._form_token({
            "grant_type": "authorization_code",
            "client_id": self._app_id,
            "client_secret": self._app_key,
            "code": code,
            "redirect_uri": redirect_uri,
        })
        self._save_user_token(data)
        return data

    def _form_token(self, fields: dict) -> dict:
        body = urllib.parse.urlencode(fields).encode()
        data = self._raw_request("POST", BASE + TOKEN_PATH, body=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
        if "access_token" not in data:
            raise WPSError(f"换取token失败：{data}", code=data.get("code"), payload=data)
        return data

    def _user_access_token(self) -> str:
        store = json.loads(self._user_token_path.read_text(encoding="utf-8"))
        now = time.time()
        if store.get("access_token") and now < float(store.get("expires_at", 0)):
            return store["access_token"]
        if now >= float(store.get("refresh_expires_at", 0)):
            raise WPSError("refresh_token已过期（总有效期365天），需重新跑 wps_sync.py auth 授权")
        refreshed = self._form_token({
            "grant_type": "refresh_token",
            "refresh_token": store["refresh_token"],
            "client_id": self._app_id,
            "client_secret": self._app_key,
        })
        # 刷新会返回新的refresh_token，旧的立即失效，必须覆盖保存
        self._save_user_token(refreshed)
        return refreshed["access_token"]

    def _save_user_token(self, data: dict) -> None:
        now = time.time()
        payload = {
            "app_id": self._app_id,
            "access_token": data["access_token"],
            "expires_at": now + int(data.get("expires_in", 7200)) - TOKEN_EARLY_REFRESH,
            "refresh_token": data.get("refresh_token", ""),
            "refresh_expires_at": now + int(data.get("refresh_expires_in", 31536000)) - 86400,
            "saved_at": now,
        }
        self._user_token_path.parent.mkdir(parents=True, exist_ok=True)
        self._user_token_path.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(self._user_token_path, 0o600)

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
        """团队文档库列表。按当前用户返回，租户token调用会报"用户不在企业内"，
        仅在拿到用户token时可用。page_size必填。权限 kso.doclib.readwrite。"""
        return self.call("GET", "/v7/doclibs", params={"page_size": 100})

    def drives(self) -> dict:
        """企业驱动盘列表，租户token可用。权限 kso.drive.readwrite。"""
        return self.call("GET", "/v7/drives", params={"page_size": 100})

    def list_drives(self) -> list[tuple[str, str]]:
        """拿到可遍历的盘 [(drive_id, 名称)]。先走企业级/v7/drives，
        不可用时退回用户级/v7/doclibs，两边响应结构都做字段容错。"""
        errors = []
        for source, getter in (("drives", self.drives), ("doclibs", self.doclibs)):
            try:
                data = getter()
            except WPSError as exc:
                errors.append(f"{source}: {exc.payload or exc}")
                continue
            items = data.get("items") or data.get("drives") or data.get("list") or []
            found = []
            for item in items:
                drive = item.get("drive") if isinstance(item.get("drive"), dict) else {}
                did = str(item.get("id") or item.get("drive_id") or drive.get("id") or "")
                name = str(item.get("name") or drive.get("name") or did)
                if did:
                    found.append((did, name))
            if found:
                return found
        raise WPSError("拿不到任何驱动盘。" + " | ".join(errors))

    def children(self, drive_id: str, parent_id: str = "0", *,
                 filter_exts: str | None = None, page_size: int = 50) -> dict:
        """列出盘内文件，根目录 parent_id 传 0。权限 kso.file.read。"""
        params: dict[str, Any] = {"page_size": page_size}
        if filter_exts:
            params["filter_exts"] = filter_exts
        return self.call("GET", f"/v7/drives/{drive_id}/files/{parent_id}/children", params=params)

    def children_all(self, drive_id: str, parent_id: str = "0", *,
                     filter_exts: str | None = None, page_size: int = 50,
                     max_pages: int = 200) -> list[dict]:
        """列出一层目录的全部条目，自动翻页。"""
        items: list[dict] = []
        cursor: Any = None
        seen: set[str] = set()
        for _ in range(max_pages):
            params: dict[str, Any] = {"page_size": page_size}
            if filter_exts:
                params["filter_exts"] = filter_exts
            if cursor is not None:
                # 云文档接口实测返回 next_page_token，请求侧对应 page_token
                params["page_token"] = cursor
            data = self.call("GET", f"/v7/drives/{drive_id}/files/{parent_id}/children",
                             params=params)
            page = data.get("items") or data.get("files") or []
            items.extend(page)
            cursor = _next_cursor(data)
            if not cursor or str(cursor) in seen or not page:
                break
            seen.add(str(cursor))
        return items

    def walk(self, drive_id: str, parent_id: str = "0", *, max_depth: int = 8,
             workers: int = WALK_WORKERS, on_progress=None) -> list[dict]:
        """递归遍历目录树，返回扁平文件清单。

        每项附加：_path（盘内相对路径）、_ext、_kind（该用哪套读取接口）、_is_folder。
        逐层并发列目录——串行时每个目录一次往返，深目录会慢到不可用。
        返回前按_path排序：并发完成顺序不定，不排序会让快照指纹每次都变、误报"有更新"。
        """
        found: list[dict] = []
        level = [(str(parent_id), "")]
        for depth in range(max_depth + 1):
            if not level:
                break
            next_level: list[tuple[str, str]] = []
            with ThreadPoolExecutor(max_workers=workers) as pool:
                jobs = {pool.submit(self.children_all, drive_id, pid): prefix
                        for pid, prefix in level}
                for job in as_completed(jobs):
                    prefix = jobs[job]
                    for item in job.result():
                        name = str(item.get("name", item.get("fname", "")))
                        path = f"{prefix}/{name}" if prefix else name
                        is_folder = _is_folder(item)
                        ext = "" if is_folder else _ext_of(item, name)
                        found.append({
                            **item,
                            "_path": path,
                            "_ext": ext,
                            "_kind": "folder" if is_folder else EXT_KIND.get(ext, "file"),
                            "_is_folder": is_folder,
                        })
                        child_id = str(item.get("id", item.get("file_id", "")))
                        if is_folder and child_id and depth < max_depth:
                            next_level.append((child_id, path))
            if on_progress:
                on_progress(depth, len(found), len(next_level))
            level = next_level
        return sorted(found, key=lambda x: x["_path"])

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


def _is_folder(item: dict) -> bool:
    """响应里标识文件夹的字段各接口不统一，逐个探测。"""
    for key in ("is_folder", "isFolder", "folder"):
        if isinstance(item.get(key), bool):
            return item[key]
    for key in ("type", "ftype", "file_type", "kind"):
        if str(item.get(key, "")).lower() in FOLDER_MARKS:
            return True
    return False


def _ext_of(item: dict, name: str = "") -> str:
    """取扩展名：先看字段，没有就从文件名后缀推断。"""
    for key in ("ext", "file_ext", "fext", "ftype", "file_type"):
        value = str(item.get(key, "")).strip().lstrip(".").lower()
        if value and value not in FOLDER_MARKS:
            return value
    name = name or str(item.get("name", ""))
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


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


def client_from_config(config_path: str | Path, token_cache: str | Path | None = None,
                       user_token_path: str | Path | None = None) -> WPSClient:
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
    return WPSClient(app_id, app_key, token_cache=token_cache,
                     user_token_path=user_token_path)
