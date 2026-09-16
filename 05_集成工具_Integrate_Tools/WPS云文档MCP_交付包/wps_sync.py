#!/usr/bin/env python3
"""WPS云文档同步器：定时落快照 + 随时现拉。

用法：
  python3 wps_sync.py auth                   走用户授权，拿用户token（团队文档库必需）
  python3 wps_sync.py authurl                只打印授权链接，不起本地服务
  python3 wps_sync.py code <code>            手工粘贴回调地址栏里的code换token
  python3 wps_sync.py doctor                 校验凭证，换一次token
  python3 wps_sync.py resolve <链接或link_id>  分享链接 → file_id/类型，产出可粘贴的源条目
  python3 wps_sync.py ls [drive_id] [parent_id]  列盘内一层文件
  python3 wps_sync.py tree [drive_id] [folder_id] 递归打印目录树，看清有哪些表
  python3 wps_sync.py discover <alias>       文件夹源会同步哪些文件（只看不抓）
  python3 wps_sync.py pull <alias>           现拉最新内容，打到stdout，不落地
  python3 wps_sync.py sync [alias ...] [--force]  同步落快照；默认按云端mtime跳过未改动的
  python3 wps_sync.py status                 各源上次同步时间与内容指纹

快照布局：snapshots/<alias>/latest.json、_meta.json、history/<UTC时间戳>.json
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.parse
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wps_client import WPSClient, WPSError, client_from_config  # noqa: E402


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "wps_config.json"
SOURCES_PATH = HERE / "wps_sources.json"
TOKEN_CACHE = HERE / ".token_cache.json"
USER_TOKEN = HERE / ".user_token.json"
DEFAULT_REDIRECT = "http://localhost:9527/callback"
DEFAULT_SCOPES = [
    "kso.user_base.read", "kso.doclib.readwrite", "kso.file.read",
    "kso.dbsheet.read", "kso.sheets.read",
    "kso.airsheet.read", "kso.airsheet.readwrite", "kso.file_link.readwrite",
]
AUTH_TIMEOUT = 300
SNAPSHOT_DIR = HERE / "snapshots"

DEFAULT_RANGE = {"row_from": 0, "row_to": 999, "col_from": 0, "col_to": 49}


def make_client() -> WPSClient:
    return client_from_config(CONFIG_PATH, token_cache=TOKEN_CACHE, user_token_path=USER_TOKEN)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_sources() -> list[dict]:
    if not SOURCES_PATH.exists():
        raise WPSError(f"找不到源清单 {SOURCES_PATH}，先从 wps_sources.example.json 复制一份")
    conf = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return conf.get("sources", [])


def pick_sources(aliases: list[str]) -> list[dict]:
    sources = load_sources()
    if not aliases:
        return sources
    by_alias = {s["alias"]: s for s in sources}
    missing = [a for a in aliases if a not in by_alias]
    if missing:
        raise WPSError(f"源清单里没有这些别名：{', '.join(missing)}")
    return [by_alias[a] for a in aliases]


def safe_alias(alias: str) -> str:
    """别名会当成目录路径用，过滤掉空段与上跳段，避免写到快照目录之外。"""
    parts = []
    for seg in alias.replace("\\", "/").split("/"):
        seg = seg.strip().replace(":", "_")
        if seg and seg not in (".", ".."):
            parts.append(seg)
    return "/".join(parts) or "unnamed"


def expand_folder(client: WPSClient, src: dict) -> tuple[list[dict], list[dict]]:
    """把一个文件夹源展开成"清单 + 每个文件一个子源"。

    drive_id 填 all（或留空）时遍历全部团队盘。默认只挑三类表格，
    其余文件不抓内容——文字文档没有读正文的接口。
    """
    alias = src["alias"]
    drive_id = str(src.get("drive_id") or "all")
    folder_id = str(src.get("folder_id", "0"))
    max_depth = int(src.get("max_depth", 8))
    kinds = set(src.get("kinds") or ["dbsheet", "sheets", "airsheet"])

    drives = client.list_drives() if drive_id == "all" else [(drive_id, drive_id)]

    listing: list[dict] = []
    subs: list[dict] = []
    for did, dname in drives:
        for item in client.walk(did, folder_id, max_depth=max_depth):
            path = f"{dname}/{item['_path']}" if len(drives) > 1 else item["_path"]
            listing.append({"path": path, "id": item.get("id", item.get("file_id")),
                            "ext": item["_ext"], "kind": item["_kind"]})
            if item["_is_folder"] or item["_kind"] not in kinds:
                continue
            file_id = str(item.get("id", item.get("file_id", "")))
            if not file_id:
                continue
            sub = {"alias": f"{alias}/{path}", "kind": item["_kind"], "file_id": file_id,
                   "_mtime": item.get("mtime")}
            if src.get("range"):
                sub["range"] = src["range"]
            subs.append(sub)
    return listing, subs


def content_hash(content: Any) -> str:
    blob = json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


# ---------- 各形态的拉取 ----------

def fetch_dbsheet(client: WPSClient, src: dict) -> dict:
    file_id = src["file_id"]
    schema = client.dbsheet_schema(file_id)
    wanted = set(src.get("sheets") or [])
    tables = []
    for sheet in schema.get("sheets", []):
        sheet_id = sheet.get("id")
        name = sheet.get("name", "")
        if wanted and not (str(sheet_id) in wanted or name in wanted):
            continue
        records = client.dbsheet_records(file_id, sheet_id, page_size=src.get("page_size", 100))
        tables.append({"sheet_id": sheet_id, "name": name, "record_count": len(records),
                       "records": records})
    return {"schema_sheets": [{"id": s.get("id"), "name": s.get("name")}
                              for s in schema.get("sheets", [])],
            "tables": tables}


def fetch_cells(client: WPSClient, src: dict, kind: str) -> dict:
    file_id = src["file_id"]
    rng = {**DEFAULT_RANGE, **(src.get("range") or {})}
    listing = client.worksheets(file_id, kind=kind)
    wanted = set(src.get("worksheets") or [])
    sheets = []
    for ws in listing.get("sheets", []):
        ws_id = ws.get("sheet_id", ws.get("id"))
        name = ws.get("name", "")
        if wanted and not (str(ws_id) in wanted or name in wanted):
            continue
        data = client.range_data(file_id, ws_id, kind=kind, **rng)
        sheets.append({"worksheet_id": ws_id, "name": name, "range": rng, "data": data})
    return {"worksheet_index": [{"id": w.get("sheet_id", w.get("id")), "name": w.get("name")}
                                for w in listing.get("sheets", [])],
            "worksheets": sheets}


def fetch_file(client: WPSClient, src: dict) -> dict:
    """文字文档等无正文读取接口的形态，只跟踪元信息（改没改、谁改的、什么时候）。"""
    return {"file_meta": client.file_meta(src["file_id"])}


def fetch_source(client: WPSClient, src: dict) -> dict:
    kind = src.get("kind")
    if kind == "dbsheet":
        return fetch_dbsheet(client, src)
    if kind in ("sheets", "airsheet"):
        return fetch_cells(client, src, kind)
    if kind == "file":
        return fetch_file(client, src)
    if kind == "folder":
        raise WPSError("folder源由sync/discover展开，不能直接抓取")
    raise WPSError(f"源 {src.get('alias')} 的 kind 不支持：{kind}"
                   "（可选 folder/dbsheet/sheets/airsheet/file）")


# ---------- 快照 ----------

def write_snapshot(alias: str, content: Any, source_mtime: Any = None) -> tuple[bool, str]:
    """内容指纹变了才写新版本。返回（是否有变化，指纹）。"""
    folder = SNAPSHOT_DIR / safe_alias(alias)
    (folder / "history").mkdir(parents=True, exist_ok=True)
    meta_path = folder / "_meta.json"
    digest = content_hash(content)

    previous = {}
    if meta_path.exists():
        previous = json.loads(meta_path.read_text(encoding="utf-8"))
    changed = previous.get("content_hash") != digest

    payload = {"alias": alias, "fetched_at": now_utc(), "content_hash": digest, "content": content}
    if changed:
        # 文件名带上指纹：同一秒内发生两次变更时不会互相覆盖留档
        stamp = now_utc().replace(":", "").replace("-", "")
        (folder / "history" / f"{stamp}_{digest}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    meta_path.write_text(json.dumps({
        "alias": alias,
        "content_hash": digest,
        "last_checked_at": now_utc(),
        "last_changed_at": now_utc() if changed else previous.get("last_changed_at"),
        "previous_hash": previous.get("content_hash"),
        "source_mtime": source_mtime if source_mtime is not None else previous.get("source_mtime"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed, digest


# ---------- 命令 ----------

class _CallbackHandler(BaseHTTPRequestHandler):
    """只为接住一次授权回调，拿到code就收工。"""

    result: dict = {}

    def do_GET(self):  # noqa: N802
        query = urllib.parse.urlparse(self.path).query
        params = {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}
        if "code" in params or "error" in params:
            _CallbackHandler.result = params
            note = "授权成功，回到终端继续。" if "code" in params else f"授权失败：{params}"
        else:
            note = "等待授权回调…"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            f"<html><body style='font-family:system-ui;padding:48px'>"
            f"<h2>{note}</h2></body></html>".encode()
        )

    def log_message(self, *args):
        pass


def cmd_auth() -> int:
    conf = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    redirect_uri = conf.get("redirect_uri") or DEFAULT_REDIRECT
    scopes = conf.get("auth_scopes") or DEFAULT_SCOPES
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise WPSError(f"redirect_uri 不合法：{redirect_uri}")

    client = make_client()
    state = uuid.uuid4().hex
    url = client.auth_url(redirect_uri, scopes, state)

    _CallbackHandler.result = {}
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        httpd = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    except OSError as exc:
        raise WPSError(f"本地端口 {port} 起不来：{exc}。换个端口改 wps_config.json 的 redirect_uri，"
                       "并同步改开发者后台的回调配置") from exc
    httpd.timeout = 10

    print(f"回调地址：{redirect_uri}（必须与开发者后台「安全配置 > 用户授权回调配置」完全一致）")
    print(f"申请scope：{', '.join(scopes)}\n")
    print("在浏览器里完成授权（已尝试自动打开，没开就手动复制）：\n")
    print(url + "\n")
    webbrowser.open(url)

    deadline = time.time() + AUTH_TIMEOUT
    while not _CallbackHandler.result and time.time() < deadline:
        httpd.handle_request()
    httpd.server_close()

    result = _CallbackHandler.result
    if not result:
        raise WPSError(f"{AUTH_TIMEOUT}秒内没等到回调，授权未完成")
    if "error" in result:
        raise WPSError(f"授权被拒绝或失败：{result}")
    if result.get("state") != state:
        raise WPSError("state不匹配，可能遭遇CSRF，已中止")

    client.exchange_code(result["code"], redirect_uri)
    print(f"用户token已保存到 {USER_TOKEN.name}（refresh_token有效期365天，之后自动续）\n")
    return cmd_doctor()


def _auth_settings() -> tuple[str, list[str]]:
    conf = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return (conf.get("redirect_uri") or DEFAULT_REDIRECT,
            conf.get("auth_scopes") or DEFAULT_SCOPES)


def cmd_authurl() -> int:
    """回调地址不是localhost、或本地端口起不来时用：手动走完授权，再用 code 命令换token。"""
    redirect_uri, scopes = _auth_settings()
    state = uuid.uuid4().hex
    print(make_client().auth_url(redirect_uri, scopes, state))
    print(f"\n浏览器打开上面的链接完成授权。授权后会跳到：\n  {redirect_uri}?code=XXXX&state={state}")
    print("\n那个页面打不开也没关系，从地址栏把 code= 后面的值复制下来，然后跑：")
    print("  python3 wps_sync.py code <粘贴的code>")
    print("\ncode 十分钟内有效且只能用一次。")
    return 0


def cmd_code(code: str) -> int:
    redirect_uri, _ = _auth_settings()
    make_client().exchange_code(code.strip(), redirect_uri)
    print(f"用户token已保存到 {USER_TOKEN.name}（refresh_token有效期365天，之后自动续）\n")
    return cmd_doctor()


def cmd_doctor() -> int:
    client = make_client()
    token = client.token()
    who = "用户身份（数据范围跟随你本人）" if client.uses_user_token() else "租户身份（应用自身权限）"
    print(f"凭证OK，{who}，access_token={token[:12]}…（长度{len(token)}）")
    if SOURCES_PATH.exists():
        sources = load_sources()
        print(f"源清单 {len(sources)} 条：" + ", ".join(s.get("alias", "?") for s in sources))
    else:
        print(f"还没有源清单，先复制 wps_sources.example.json → {SOURCES_PATH.name}")
    return 0


def cmd_resolve(target: str) -> int:
    client = make_client()
    link_id = target.rstrip("/").split("/l/")[-1] if "/l/" in target else target
    meta = client.link_meta(link_id)
    file_id = meta.get("file_id")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if file_id:
        detail = client.file_meta(file_id)
        print("\n—— 文件信息 ——")
        print(json.dumps(detail, ensure_ascii=False, indent=2))
        print("\n—— 可粘进 wps_sources.json 的条目（kind按上面的文件类型改）——")
        print(json.dumps({"alias": "改成你要的别名", "kind": "dbsheet",
                          "file_id": file_id, "note": detail.get("name", "")},
                         ensure_ascii=False, indent=2))
    return 0


def cmd_ls(drive_id: str | None, parent_id: str) -> int:
    client = make_client()
    if not drive_id:
        for did, name in client.list_drives():
            print(f"{did}\t{name}")
        print("\n拿上面的 drive_id 再跑：wps_sync.py tree <drive_id>")
        return 0
    print(json.dumps(client.children(drive_id, parent_id), ensure_ascii=False, indent=2))
    return 0


def cmd_pull(alias: str) -> int:
    client = make_client()
    src = pick_sources([alias])[0]
    content = fetch_source(client, src)
    print(json.dumps({"alias": alias, "fetched_at": now_utc(), "content": content},
                     ensure_ascii=False, indent=2))
    return 0


def _meta_of(alias: str) -> dict:
    meta_path = SNAPSHOT_DIR / safe_alias(alias) / "_meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _sync_one(client: WPSClient, src: dict, *, force: bool = False) -> bool:
    """同步单个文件源，返回是否失败。

    展开自文件夹的源带着云端mtime：和上次快照记录的一致就整份跳过，
    省掉最贵的内容抓取。force=True 时无视mtime强制重拉。
    """
    alias = src.get("alias", "?")
    mtime = src.get("_mtime")
    if not force and mtime is not None:
        previous = _meta_of(alias)
        if previous.get("source_mtime") == mtime and previous.get("content_hash"):
            print(f"  · 跳过 {alias}（云端未改动）")
            return False
    try:
        content = fetch_source(client, src)
    except WPSError as exc:
        print(f"  ✗ {alias}：{exc}")
        return True
    changed, digest = write_snapshot(alias, content, source_mtime=mtime)
    print(f"  {'● 有更新' if changed else '○ 无变化'} {alias}  hash={digest}")
    return False


def cmd_sync(aliases: list[str]) -> int:
    force = "--force" in aliases
    aliases = [a for a in aliases if a != "--force"]
    client = make_client()
    failures = 0
    for src in pick_sources(aliases):
        alias = src.get("alias", "?")
        if src.get("kind") != "folder":
            failures += _sync_one(client, src, force=force)
            continue

        # 文件夹源：先落一份目录清单（文件增删改名本身就是变更），再逐个同步
        try:
            listing, subs = expand_folder(client, src)
        except WPSError as exc:
            failures += 1
            print(f"✗ {alias} 展开失败：{exc}")
            continue
        changed, digest = write_snapshot(f"{alias}/_清单", {"files": listing})
        print(f"{alias}：发现 {len(listing)} 个条目，其中 {len(subs)} 个可读表格 "
              f"（清单{'有变动' if changed else '无变动'} hash={digest}）")
        for sub in subs:
            failures += _sync_one(client, sub, force=force)
    return 1 if failures else 0


def cmd_tree(drive_id: str | None, folder_id: str) -> int:
    client = make_client()
    drives = client.list_drives() if not drive_id else [(drive_id, drive_id)]
    total = readable = 0
    for did, dname in drives:
        print(f"\n▼ 盘 {dname}  drive_id={did}")
        for item in client.walk(did, folder_id):
            depth = item["_path"].count("/")
            name = item["_path"].rsplit("/", 1)[-1]
            total += 1
            if item["_is_folder"]:
                print(f"{'  ' * depth}📁 {name}/")
            else:
                mark = item["_kind"] if item["_kind"] != "file" else "—"
                readable += item["_kind"] in ("dbsheet", "sheets", "airsheet")
                print(f"{'  ' * depth}   {name}  [{mark}]")
    print(f"\n共 {total} 个条目，{readable} 个是能结构化读取的表格。")
    print("把要同步的文件夹按 wps_sources.example.json 里的 folder 源写进 wps_sources.json 即可。")
    return 0


def cmd_discover(alias: str) -> int:
    client = make_client()
    src = pick_sources([alias])[0]
    if src.get("kind") != "folder":
        print(f"{alias} 不是 folder 源，无需展开")
        return 0
    listing, subs = expand_folder(client, src)
    print(f"{alias} 展开结果：{len(listing)} 个条目，将同步 {len(subs)} 个\n")
    for sub in subs:
        print(f"  [{sub['kind']:<8}] {sub['alias']}")
    skipped = [i for i in listing if not i["kind"] in ("dbsheet", "sheets", "airsheet", "folder")]
    if skipped:
        print(f"\n跳过 {len(skipped)} 个非表格文件（无读正文接口），例如：")
        for item in skipped[:5]:
            print(f"  {item['path']}  [{item['ext'] or '无扩展名'}]")
    return 0


def cmd_status() -> int:
    if not SNAPSHOT_DIR.exists():
        print("还没有任何快照，先跑一次 sync")
        return 0
    for meta_path in sorted(SNAPSHOT_DIR.glob("*/_meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        print(f"{meta['alias']:<24} 上次检查 {meta.get('last_checked_at')} "
              f"上次变更 {meta.get('last_changed_at')} hash={meta.get('content_hash')}")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "auth":
            return cmd_auth()
        if cmd == "authurl":
            return cmd_authurl()
        if cmd == "code":
            return cmd_code(rest[0]) if rest else _usage("code 需要一个授权码")
        if cmd == "doctor":
            return cmd_doctor()
        if cmd == "resolve":
            return cmd_resolve(rest[0]) if rest else _usage("resolve 需要一个分享链接或link_id")
        if cmd == "ls":
            return cmd_ls(rest[0] if rest else None, rest[1] if len(rest) > 1 else "0")
        if cmd == "pull":
            return cmd_pull(rest[0]) if rest else _usage("pull 需要一个源别名")
        if cmd == "tree":
            return cmd_tree(rest[0] if rest else None, rest[1] if len(rest) > 1 else "0")
        if cmd == "discover":
            return cmd_discover(rest[0]) if rest else _usage("discover 需要一个源别名")
        if cmd == "sync":
            return cmd_sync(rest)
        if cmd == "status":
            return cmd_status()
    except WPSError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    print(__doc__)
    return 2


def _usage(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
