"""确定性文件发现与 SHA-256 指纹工具。"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_workbooks(watch_dirs: list[Path], patterns: list[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for directory in watch_dirs:
        if not directory.is_dir():
            continue
        for pattern in patterns:
            for path in directory.glob(pattern):
                if path.is_file() and not path.name.startswith("~$"):
                    found[str(path.resolve())] = path.resolve()
    return sorted(found.values(), key=lambda item: (item.stat().st_mtime_ns, str(item)), reverse=True)
