#!/usr/bin/env python3
"""WPS云文档同步器：定时落快照 + 随时现拉。

用法：
  python3 wps_sync.py doctor                 校验凭证，换一次token
  python3 wps_sync.py resolve <链接或link_id>  分享链接 → file_id/类型，产出可粘贴的源条目
  python3 wps_sync.py ls [drive_id] [parent_id]  列盘内文件
  python3 wps_sync.py pull <alias>           现拉最新内容，打到stdout，不落地
  python3 wps_sync.py sync [alias ...]       全量拉取并落快照，内容变了才留新版本
  python3 wps_sync.py status                 各源上次同步时间与内容指纹

快照布局：snapshots/<alias>/latest.json、_meta.json、history/<UTC时间戳>.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wps_client import WPSClient, WPSError, client_from_config  # noqa: E402


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "wps_config.json"
SOURCES_PATH = HERE / "wps_sources.json"
TOKEN_CACHE = HERE / ".token_cache.json"
SNAPSHOT_DIR = HERE / "snapshots"

DEFAULT_RANGE = {"row_from": 0, "row_to": 999, "col_from": 0, "col_to": 49}


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
    raise WPSError(f"源 {src.get('alias')} 的 kind 不支持：{kind}（可选 dbsheet/sheets/airsheet/file）")


# ---------- 快照 ----------

def write_snapshot(alias: str, content: Any) -> tuple[bool, str]:
    """内容指纹变了才写新版本。返回（是否有变化，指纹）。"""
    folder = SNAPSHOT_DIR / alias
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
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed, digest


# ---------- 命令 ----------

def cmd_doctor() -> int:
    client = client_from_config(CONFIG_PATH, token_cache=TOKEN_CACHE)
    token = client.token()
    print(f"凭证OK，access_token={token[:12]}…（长度{len(token)}）")
    if SOURCES_PATH.exists():
        sources = load_sources()
        print(f"源清单 {len(sources)} 条：" + ", ".join(s.get("alias", "?") for s in sources))
    else:
        print(f"还没有源清单，先复制 wps_sources.example.json → {SOURCES_PATH.name}")
    return 0


def cmd_resolve(target: str) -> int:
    client = client_from_config(CONFIG_PATH, token_cache=TOKEN_CACHE)
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
    client = client_from_config(CONFIG_PATH, token_cache=TOKEN_CACHE)
    if not drive_id:
        print(json.dumps(client.doclibs(), ensure_ascii=False, indent=2))
        print("\n取 items[].drive.id 作为 drive_id，再跑：wps_sync.py ls <drive_id>")
        return 0
    print(json.dumps(client.children(drive_id, parent_id), ensure_ascii=False, indent=2))
    return 0


def cmd_pull(alias: str) -> int:
    client = client_from_config(CONFIG_PATH, token_cache=TOKEN_CACHE)
    src = pick_sources([alias])[0]
    content = fetch_source(client, src)
    print(json.dumps({"alias": alias, "fetched_at": now_utc(), "content": content},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_sync(aliases: list[str]) -> int:
    client = client_from_config(CONFIG_PATH, token_cache=TOKEN_CACHE)
    failures = 0
    for src in pick_sources(aliases):
        alias = src.get("alias", "?")
        try:
            content = fetch_source(client, src)
        except WPSError as exc:
            failures += 1
            print(f"✗ {alias}：{exc}")
            continue
        changed, digest = write_snapshot(alias, content)
        print(f"{'● 有更新' if changed else '○ 无变化'} {alias}  hash={digest}")
    return 1 if failures else 0


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
        if cmd == "doctor":
            return cmd_doctor()
        if cmd == "resolve":
            return cmd_resolve(rest[0]) if rest else _usage("resolve 需要一个分享链接或link_id")
        if cmd == "ls":
            return cmd_ls(rest[0] if rest else None, rest[1] if len(rest) > 1 else "0")
        if cmd == "pull":
            return cmd_pull(rest[0]) if rest else _usage("pull 需要一个源别名")
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
