"""一次性扫描所有团队库的目录树并缓存，避免反复重爬。

缓存只保留后续需要的字段，扔掉created_by/hash等大字段，否则几万项会撑到几十MB。
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wps_sync

CACHE = Path(__file__).resolve().parent / ".tree_cache.json"
KEEP = ("_path", "_ext", "_kind", "_is_folder")

client = wps_sync.make_client()
cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

for drive_id, name in client.list_drives():
    if drive_id in cache:
        print(f"[跳过] {name} 已有缓存 {len(cache[drive_id]['items'])} 项", flush=True)
        continue
    t0 = time.time()
    print(f"[开始] {name} ({drive_id})", flush=True)
    try:
        items = client.walk(drive_id, "0")
    except Exception as exc:
        print(f"[失败] {name}: {str(exc)[:200]}", flush=True)
        continue
    slim = [{**{k: it[k] for k in KEEP},
             "id": it.get("id"), "mtime": it.get("mtime"), "size": it.get("size")}
            for it in items]
    cache[drive_id] = {"name": name, "scanned_at": wps_sync.now_utc(), "items": slim}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    tables = [i for i in slim if i["_kind"] in ("dbsheet", "sheets", "airsheet")]
    exts = Counter(i["_ext"] for i in slim if not i["_is_folder"] and i["_kind"] == "file")
    print(f"[完成] {name}: {len(slim)}项 "
          f"({sum(1 for i in slim if i['_is_folder'])}目录/{len(slim)-sum(1 for i in slim if i['_is_folder'])}文件), "
          f"表格{len(tables)}个, 耗时{time.time()-t0:.0f}s", flush=True)
    if exts:
        print(f"        非表格Top5: {dict(exts.most_common(5))}", flush=True)

print(f"\n全部完成，缓存写入 {CACHE.name}（{CACHE.stat().st_size/1e6:.1f}MB）", flush=True)
