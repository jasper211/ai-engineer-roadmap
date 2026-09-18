#!/usr/bin/env python3
"""WPS 企业云文档 → 自有服务器 · 全量镜像同步

每轮结束后，本地镜像目录与 WPS 云端保持一致：新增会下载、修改会重下、
云端删除的本地也删。可选 rsync 推到远程服务器。

与「按需读」的 MCP 方案是互补关系：这里产出的是**服务器上的完整副本**，
适合批量分析、全文检索、离线使用；要「此刻最新」仍应走 MCP 直接查云端。

设计要点（都是踩过坑之后定的）：
- **用用户授权，不用 client_credentials**。实测应用身份读云文档返回
  `403 企业套餐权益不足（需商业高级版/旗舰版）`，这是付费门槛不是配置问题。
  用户授权的 refresh_token 有效期 365 天且自动续，无人值守同样成立。
- **认证全部委托给 wps365-cli**，本脚本不碰 token、不实现刷新。
- **遍历全部团队库**：企业通常有多个 drive，只配一个会漏掉其余。
- **下载用 `/v7/drives/{drive}/files/{file}/download`**，实测可用；
  `batch_download` 未验证通过，不采用。
- **并发 + 断点续传**：串行下载 30G 需约 21 小时，一天一轮跑不完；
  状态库记录已下载项，中断后下轮自动接着来。

依赖：python3、wps365-cli、curl、rsync（推远程时才需要）。无需 pip 安装任何包。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MIRROR = HERE / "mirror"
STATE_DB = HERE / "sync_state.db"
LOG_FILE = HERE / "sync.log"

# 可结构化读取的表格/文档类扩展名，--only-docs 时用
DOC_EXTS = {"xlsx", "xls", "et", "csv", "docx", "doc", "pptx", "ppt",
            "pdf", "txt", "md", "ksheet", "dbt", "otl"}

_print_lock = threading.Lock()


def log(msg: str, quiet: bool = False) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with _print_lock:
        if not quiet:
            print(line, flush=True)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


# ---------------------------------------------------------------- CLI 封装

class Cli:
    """所有认证都交给 wps365-cli：它管 token 刷新，我们只管调。"""

    def __init__(self, path: str | None = None, timeout: int = 60):
        self.path = path or self._find()
        self.timeout = timeout
        self._token = None
        self._token_at = 0.0
        self._lock = threading.Lock()

    @staticmethod
    def _find() -> str:
        for c in (os.environ.get("WPS365_CLI"),
                  str(Path.home() / ".local/bin/wps365-cli"),
                  "/usr/local/bin/wps365-cli"):
            if c and Path(c).exists():
                return c
        found = shutil.which("wps365-cli")
        if found:
            return found
        raise SystemExit("找不到 wps365-cli。安装：curl -fsSL https://open-docs.wpscdn.cn/cli/install.sh | bash")

    def api(self, method: str, path: str, *query: str) -> dict:
        args = [self.path, f"--timeout={self.timeout}s", "api", method, path, *query]
        proc = subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=self.timeout + 30)
        raw = (proc.stdout or "").strip()
        if not raw.startswith("{"):
            raise RuntimeError((proc.stderr or raw).strip()[:300])
        payload = json.loads(raw)
        if payload.get("code") not in (0, None):
            raise RuntimeError(f"code={payload.get('code')} msg={payload.get('msg')}")
        return payload.get("data", payload)

    def token(self) -> str:
        """token 缓存 1 小时；CLI 内部会在过期时用 refresh_token 自动续。"""
        with self._lock:
            if self._token and time.time() - self._token_at < 3600:
                return self._token
            proc = subprocess.run([self.path, "auth", "token"], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=60)
            tok = (proc.stdout or "").strip().strip('"')
            if not tok:
                raise SystemExit("拿不到访问令牌，请先执行 wps365-cli auth login --device")
            self._token, self._token_at = tok, time.time()
            return tok

    def drives(self) -> list[tuple[str, str]]:
        data = self.api("get", "/v7/doclibs", "--query=page_size=100")
        out = []
        for item in data.get("items") or []:
            drive = item.get("drive") or {}
            did = str(drive.get("id") or "")
            if did:
                out.append((did, str(drive.get("name") or did)))
        return out

    def children(self, drive_id: str, parent_id: str) -> list[dict]:
        items, token = [], ""
        for _ in range(500):
            q = ["--query=page_size=200"]
            if token:
                q.append(f"--query=page_token={token}")
            data = self.api("get", f"/v7/drives/{drive_id}/files/{parent_id}/children", *q)
            items.extend(data.get("items") or [])
            token = data.get("next_page_token") or ""
            if not token:
                break
        return items

    def download_url(self, drive_id: str, file_id: str) -> str:
        return self.api("get", f"/v7/drives/{drive_id}/files/{file_id}/download")["url"]


# ---------------------------------------------------------------- 状态库

class State:
    """记录云端每个文件的指纹，用于判断增量与检测删除。

    seen_this_run：每轮开始清零，扫描到就置 1；扫完仍为 0 的即云端已删。
    """

    def __init__(self, path: Path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY, drive_id TEXT, name TEXT,
                size INTEGER, mtime INTEGER, version INTEGER,
                rel_path TEXT, downloaded_at TEXT, seen INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_seen ON files(seen);
        """)
        self.conn.commit()

    def begin_run(self):
        with self.lock:
            self.conn.execute("UPDATE files SET seen = 0")
            self.conn.commit()

    def get(self, file_id: str) -> dict | None:
        with self.lock:
            cur = self.conn.execute("SELECT * FROM files WHERE file_id=?", (file_id,))
            row = cur.fetchone()
            return dict(zip([d[0] for d in cur.description], row)) if row else None

    def mark_seen(self, info: dict, rel: str):
        with self.lock:
            self.conn.execute("""
                INSERT INTO files (file_id, drive_id, name, size, mtime, version, rel_path, seen)
                VALUES (?,?,?,?,?,?,?,1)
                ON CONFLICT(file_id) DO UPDATE SET
                    drive_id=excluded.drive_id, name=excluded.name, size=excluded.size,
                    mtime=excluded.mtime, version=excluded.version,
                    rel_path=excluded.rel_path, seen=1
            """, (info["id"], info.get("drive_id"), info.get("name"), info.get("size"),
                  info.get("mtime"), info.get("version"), rel))
            self.conn.commit()

    def mark_downloaded(self, file_id: str):
        with self.lock:
            self.conn.execute("UPDATE files SET downloaded_at=? WHERE file_id=?",
                              (datetime.now(timezone.utc).isoformat(), file_id))
            self.conn.commit()

    def vanished(self) -> list[dict]:
        with self.lock:
            cur = self.conn.execute("SELECT * FROM files WHERE seen=0")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def drop(self, file_id: str):
        with self.lock:
            self.conn.execute("DELETE FROM files WHERE file_id=?", (file_id,))
            self.conn.commit()

    def count(self) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]


# ---------------------------------------------------------------- 工具

def is_folder(item: dict) -> bool:
    for k in ("is_folder", "isFolder"):
        if isinstance(item.get(k), bool):
            return item[k]
    return str(item.get("type", "")).lower() in ("folder", "dir")


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def safe_name(name: str) -> str:
    """文件名里的分隔符和控制字符会写出目录外或写失败，统一替换。"""
    out = "".join("_" if c in '/\\:*?"<>|' or ord(c) < 32 else c for c in name).strip(" .")
    return out or "unnamed"


def needs_download(info: dict, prev: dict | None, local: Path) -> bool:
    if prev is None or not prev.get("downloaded_at"):
        return True
    if info.get("version") != prev.get("version"):
        return True
    if info.get("mtime") != prev.get("mtime"):
        return True
    if not local.exists():
        return True
    size = info.get("size")
    return bool(size) and local.stat().st_size != size


# ---------------------------------------------------------------- 主流程

class Mirror:
    def __init__(self, args):
        self.args = args
        self.cli = Cli()
        self.state = State(STATE_DB)
        self.root = Path(args.mirror).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._guard_syncthing()
        self.stats = {"scanned": 0, "downloaded": 0, "skipped": 0,
                      "failed": 0, "deleted": 0, "bytes": 0}
        self.stop = threading.Event()

    def _guard_syncthing(self):
        """镜像目录若是 Syncthing 的 folder，确保下载中的临时文件不会被同步出去。

        下载用 `xxx.part` 暂存后原子替换。Syncthing 会把 .part 当成正式文件立刻
        分发给各端，产生一堆半截文件；替换完成后又变成删除+新增，白白放大流量。
        """
        if not (self.root / ".stfolder").exists():
            return
        ignore = self.root / ".stignore"
        needed = ["*.part", ".stversions"]
        try:
            existing = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
            missing = [rule for rule in needed if rule not in existing]
            if missing:
                with open(ignore, "a", encoding="utf-8") as fh:
                    if existing and existing[-1].strip():
                        fh.write("\n")
                    fh.write("// 由 wps_mirror.py 添加：排除下载中的临时文件\n")
                    fh.write("\n".join(missing) + "\n")
                log(f"检测到 Syncthing folder，已在 .stignore 补充规则：{', '.join(missing)}")
        except OSError as exc:
            log(f"[警告] 无法写入 .stignore（{exc}）。请手动添加 *.part，"
                "否则下载中的半截文件会被同步出去。")

    # ---- Phase 1: 扫描 ----
    def scan_drive(self, drive_id: str, drive_name: str) -> list[tuple[dict, str]]:
        """逐层并发遍历一个库。串行时每个目录一次往返，深目录会慢到不可用。"""
        found: list[tuple[dict, str]] = []
        level = [("0", safe_name(drive_name))]
        for depth in range(self.args.max_depth + 1):
            if not level or self.stop.is_set():
                break
            nxt = []
            with ThreadPoolExecutor(max_workers=self.args.scan_workers) as pool:
                jobs = {pool.submit(self.cli.children, drive_id, pid): prefix
                        for pid, prefix in level}
                for job in as_completed(jobs):
                    prefix = jobs[job]
                    try:
                        items = job.result()
                    except Exception as exc:
                        log(f"  [警告] 列目录失败 {prefix}: {str(exc)[:120]}")
                        continue
                    for item in items:
                        name = safe_name(str(item.get("name", "")))
                        rel = f"{prefix}/{name}"
                        if is_folder(item):
                            cid = str(item.get("id") or "")
                            if cid:
                                nxt.append((cid, rel))
                        else:
                            item["drive_id"] = drive_id
                            found.append((item, rel))
            level = nxt
            log(f"  [{drive_name}] 第{depth}层完成，累计文件 {len(found)}，待展开目录 {len(nxt)}")
        return found

    # ---- Phase 2: 下载 ----
    def fetch_one(self, info: dict, rel: str) -> str:
        local = self.root / rel
        prev = self.state.get(info["id"])
        if not needs_download(info, prev, local):
            return "skip"
        local.parent.mkdir(parents=True, exist_ok=True)
        tmp = local.with_suffix(local.suffix + ".part")
        for attempt in range(3):
            if self.stop.is_set():
                return "stopped"
            try:
                url = self.cli.download_url(info["drive_id"], info["id"])
                # 临时地址必须带 Bearer 头，裸请求返回 403 userNotLogin
                proc = subprocess.run(
                    ["curl", "-fsSL", "--max-time", str(self.args.download_timeout),
                     "-H", f"Authorization: Bearer {self.cli.token()}", "-o", str(tmp), url],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=self.args.download_timeout + 60)
                if proc.returncode != 0:
                    raise RuntimeError((proc.stderr or "").strip()[:150])
                tmp.replace(local)          # 原子替换，避免中断留下坏文件
                self.state.mark_downloaded(info["id"])
                self.stats["bytes"] += local.stat().st_size
                return "ok"
            except Exception as exc:
                msg = str(exc)
                if "429" in msg or "limit" in msg.lower() or "频" in msg:
                    log(f"  [限流] {rel} —— 暂停后重试")
                    time.sleep(30 * (attempt + 1))
                elif attempt < 2:
                    time.sleep(3 * (attempt + 1))
                else:
                    log(f"  [失败] {rel}: {msg[:150]}")
                    tmp.unlink(missing_ok=True)
                    return "fail"
        return "fail"

    # ---- Phase 3: 清理云端已删 ----
    def cleanup(self):
        gone = self.state.vanished()
        for row in gone:
            rel = row.get("rel_path") or ""
            path = self.root / rel if rel else None
            if path and path.exists():
                try:
                    path.unlink()
                    self.stats["deleted"] += 1
                    log(f"  [删除] {rel}（云端已移除）")
                except OSError as exc:
                    log(f"  [警告] 删除失败 {rel}: {exc}")
            self.state.drop(row["file_id"])
        # 清理空目录。跳过点号开头的目录——Syncthing 用 .stfolder 标记 folder 根，
        # 被删掉会判定该 folder 失效并停止同步；.stversions 是它的版本库。
        for d in sorted((p for p in self.root.rglob("*") if p.is_dir()),
                        key=lambda p: len(p.parts), reverse=True):
            if any(part.startswith(".") for part in d.relative_to(self.root).parts):
                continue
            try:
                d.rmdir()
            except OSError:
                pass

    # ---- Phase 4: 推远程 ----
    def push(self) -> bool:
        if not self.args.remote:
            return True
        cmd = ["rsync", "-az", "--delete", "--partial", "--stats"]
        if self.args.ssh_key:
            cmd += ["-e", f"ssh -i {self.args.ssh_key} -o StrictHostKeyChecking=accept-new"]
        cmd += [str(self.root) + "/", self.args.remote]
        log(f"rsync → {self.args.remote}")
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=self.args.rsync_timeout)
        if proc.returncode != 0:
            log(f"[错误] rsync 失败({proc.returncode}): {(proc.stderr or '')[:300]}")
            return False
        for line in (proc.stdout or "").splitlines():
            if "transferred" in line.lower() or "Total file size" in line:
                log(f"  {line.strip()}")
        return True

    # ---- 编排 ----
    def run(self) -> int:
        t0 = time.time()
        log("=" * 62)
        log("WPS 云文档 → 服务器 · 全量镜像同步")
        log("=" * 62)

        drives = self.cli.drives()
        if self.args.drives:
            want = {d.strip() for d in self.args.drives.split(",")}
            drives = [d for d in drives if d[0] in want or d[1] in want]
        if not drives:
            log("[错误] 没有可同步的文档库。若这里为空，多半是授权账号不在企业内。")
            return 1
        log(f"目标库 {len(drives)} 个：{'、'.join(n for _, n in drives)}")
        log(f"镜像目录 {self.root}")
        if self.args.only_docs:
            log("过滤：仅同步文档/表格类（跳过图片等）")

        self.state.begin_run()

        # Phase 1
        log("\n[1/4] 扫描云端目录…")
        all_files: list[tuple[dict, str]] = []
        for did, dname in drives:
            log(f"  扫描库：{dname}")
            all_files.extend(self.scan_drive(did, dname))
        self.stats["scanned"] = len(all_files)
        log(f"  云端文件合计 {len(all_files)} 个")

        if self.args.only_docs:
            all_files = [(i, r) for i, r in all_files if ext_of(r) in DOC_EXTS]
            log(f"  过滤后待处理 {len(all_files)} 个")

        for info, rel in all_files:
            self.state.mark_seen(info, rel)

        if self.args.dry_run:
            self._report(all_files)
            self._summary(t0)
            return 0

        # Phase 2
        log(f"\n[2/4] 下载新增/变更（并发 {self.args.download_workers}）…")
        done = 0
        with ThreadPoolExecutor(max_workers=self.args.download_workers) as pool:
            jobs = {pool.submit(self.fetch_one, i, r): r for i, r in all_files}
            for job in as_completed(jobs):
                rel = jobs[job]
                try:
                    result = job.result()
                except Exception as exc:
                    result = "fail"
                    log(f"  [失败] {rel}: {str(exc)[:120]}")
                if result == "ok":
                    self.stats["downloaded"] += 1
                elif result == "skip":
                    self.stats["skipped"] += 1
                elif result == "fail":
                    self.stats["failed"] += 1
                done += 1
                if done % 50 == 0:
                    log(f"  进度 {done}/{len(all_files)}"
                        f"（新下 {self.stats['downloaded']}，跳过 {self.stats['skipped']}，"
                        f"失败 {self.stats['failed']}）")

        # Phase 3
        log("\n[3/4] 清理云端已删除的文件…")
        self.cleanup()
        log(f"  删除 {self.stats['deleted']} 个")

        # Phase 4
        log("\n[4/4] 推送到远程服务器…")
        ok = self.push() if self.args.remote else True
        if not self.args.remote:
            log("  未配置 --remote，跳过（本地镜像已是最新）")

        self._summary(t0)
        return 0 if (ok and self.stats["failed"] == 0) else 1

    def _report(self, files: list[tuple[dict, str]]):
        """试运行报告：按类型和库拆开，用来判断该同步什么、跳过什么。"""
        from collections import defaultdict
        by_ext: dict[str, list[int]] = defaultdict(list)
        by_drive: dict[str, list[int]] = defaultdict(list)
        for info, rel in files:
            size = int(info.get("size") or 0)
            by_ext[ext_of(rel) or "(无扩展名)"].append(size)
            by_drive[rel.split("/", 1)[0]].append(size)
        total = sum(sum(v) for v in by_ext.values())

        log(f"\n[试运行] 共 {len(files)} 个文件，合计 {total/1e9:.2f} GB，未下载任何内容\n")
        log("按文件类型（Top 15）：")
        log(f"  {'类型':<12}{'数量':>8}{'总大小':>12}   占比")
        for ext, sizes in sorted(by_ext.items(), key=lambda kv: -sum(kv[1]))[:15]:
            tot = sum(sizes)
            log(f"  .{ext:<11}{len(sizes):>8}{tot/1e9:>10.2f}GB{tot/total*100:>7.1f}%" if total else "")
        docs = sum(sum(v) for k, v in by_ext.items() if k in DOC_EXTS)
        log(f"\n  文档/表格类合计 {docs/1e9:.2f} GB"
            f"（占 {docs/total*100:.1f}%）—— 用 --only-docs 只同步这部分" if total else "")

        log("\n按文档库：")
        log(f"  {'库名':<22}{'文件数':>8}{'大小':>12}")
        for name, sizes in sorted(by_drive.items(), key=lambda kv: -sum(kv[1])):
            log(f"  {name:<22}{len(sizes):>8}{sum(sizes)/1e9:>10.2f}GB")

    def _summary(self, t0: float):
        log("\n" + "=" * 62)
        log(f"云端文件   {self.stats['scanned']}")
        log(f"本次下载   {self.stats['downloaded']}（{self.stats['bytes']/1e6:.1f} MB）")
        log(f"未变跳过   {self.stats['skipped']}")
        log(f"下载失败   {self.stats['failed']}")
        log(f"本地删除   {self.stats['deleted']}")
        log(f"状态库记录 {self.state.count()}")
        log(f"总耗时     {time.time()-t0:.0f} 秒")
        log("=" * 62)
        if self.stats["failed"]:
            log("有文件下载失败：本轮不影响已成功的部分，下次运行会自动重试这些文件。")


def main() -> int:
    ap = argparse.ArgumentParser(description="WPS 云文档 → 服务器全量镜像同步")
    ap.add_argument("--mirror", default=os.environ.get("WPS_MIRROR_DIR", str(DEFAULT_MIRROR)),
                    help="本地镜像目录")
    ap.add_argument("--remote", default=os.environ.get("WPS_REMOTE", ""),
                    help="rsync 目标，如 user@host:/data/wps/（留空则只做本地镜像）")
    ap.add_argument("--ssh-key", default=os.environ.get("WPS_SSH_KEY", ""))
    ap.add_argument("--drives", default=os.environ.get("WPS_DRIVES", ""),
                    help="只同步指定库（drive_id 或库名，逗号分隔），默认全部")
    ap.add_argument("--only-docs", action="store_true",
                    help="只同步文档/表格类，跳过图片等（30G 里图片常占大头）")
    ap.add_argument("--scan-workers", type=int, default=6, help="目录遍历并发数")
    ap.add_argument("--download-workers", type=int, default=4, help="下载并发数")
    ap.add_argument("--max-depth", type=int, default=12)
    ap.add_argument("--download-timeout", type=int, default=600)
    ap.add_argument("--rsync-timeout", type=int, default=7200)
    ap.add_argument("--dry-run", action="store_true", help="只统计不下载")
    args = ap.parse_args()
    try:
        return Mirror(args).run()
    except KeyboardInterrupt:
        log("\n已中断。进度保存在状态库，下次运行会接着来。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
