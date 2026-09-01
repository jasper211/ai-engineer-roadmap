"""连接模块：只读打开 5 个 SQLite，注册 / 定位 / 关闭。"""
from __future__ import annotations
import sqlite3
from typing import Dict, List, Optional
from .config import Config, ConfigError


class ConnectionManager:
    """管理 5 个只读 SQLite 连接。mode=ro + PRAGMA query_only + read_uncommitted。
    注意：mode=ro URI 连接不开启写缓存，删除/创建 DB 后需重建连接。"""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._conns: Dict[str, sqlite3.Connection] = {}

    @staticmethod
    def _ro_connect(path: str) -> sqlite3.Connection:
        uri = "file:" + path.replace("\\", "/") + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, db_id: str) -> sqlite3.Connection:
        if db_id not in self.cfg.sources:
            raise ConfigError(f"未知数据源: {db_id}")
        if db_id not in self._conns:
            self._conns[db_id] = self._ro_connect(self.cfg.abs_path(db_id))
        return self._conns[db_id]

    def refresh(self, db_id: str):
        if db_id in self._conns:
            self._conns[db_id].close()
            del self._conns[db_id]

    def count(self, db_id: str, table: str) -> int:
        conn = self.get(db_id)
        r = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
        return int(r[0]) if r else 0

    def close_all(self):
        for c in self._conns.values():
            try:
                c.close()
            except Exception:
                pass
        self._conns = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close_all()
        return False
