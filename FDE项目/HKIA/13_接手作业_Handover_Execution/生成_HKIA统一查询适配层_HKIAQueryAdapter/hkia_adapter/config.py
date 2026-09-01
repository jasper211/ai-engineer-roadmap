"""配置模块：解析 data_sources.json / metric_catalog.json / release_policies.json。
路径只在本模块解析为绝对路径，业务函数不散落硬编码。"""
from __future__ import annotations
import json, os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


class ConfigError(Exception):
    pass


@dataclass
class DataSource:
    db_id: str
    path_abs: str
    layer: str
    certification: str
    tables: Dict[str, Dict[str, Any]]
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    version: str
    hkia_root: str
    sources: Dict[str, DataSource]
    _source_abs: Dict[str, str] = field(default_factory=dict)
    _raw: Dict[str, Any] = field(default_factory=dict)

    def abs_path(self, db_id: str) -> str:
        return self._source_abs[db_id]

    def source_names(self) -> List[str]:
        return list(self.sources.keys())


def _resolve(root: str, rel: str) -> str:
    p = rel
    if not os.path.isabs(p):
        p = os.path.join(root, rel)
    # normalize but keep absolute
    return os.path.abspath(p)


def _pkg_assets_dir():
    return Path(__file__).resolve().parent / "_assets" / "config"


def load_config(hkia_root: str = None, cfg_dir: str = None) -> Config:
    base_dir = Path(__file__).resolve().parents[1]  # HKIAQueryAdapter/
    if cfg_dir is None:
        # 优先源码树 config；缺省时回退到包内 _assets/config（安装态）
        src_dir = base_dir / "config"
        cfg_dir = src_dir if (src_dir / "data_sources.json").exists() else _pkg_assets_dir()
    else:
        cfg_dir = Path(cfg_dir)

    ds_file = cfg_dir / "data_sources.json"
    if not ds_file.exists():
        # 最后兜底到包内资产
        ds_file = _pkg_assets_dir() / "data_sources.json"
    if not ds_file.exists():
        raise ConfigError(f"data_sources.json 不存在: {ds_file}")

    ds = json.loads(ds_file.read_text(encoding="utf-8"))
    if hkia_root is None:
        hkia_root = ds.get("hkia_root", "")
    sources = {}
    src_abs = {}
    for db_id, s in ds.get("sources", {}).items():
        rel = s.get("path_rel", "")
        abs_path = _resolve(hkia_root, rel)
        sources[db_id] = DataSource(
            db_id=db_id,
            path_abs=abs_path,
            layer=s.get("layer", ""),
            certification=s.get("certification", "provisional"),
            tables=s.get("tables", {}),
            extra={k: v for k, v in s.items() if k not in ("db_id", "path_rel", "layer", "certification", "tables")},
        )
        src_abs[db_id] = abs_path
    return Config(version=ds.get("version", "?"), hkia_root=hkia_root,
                  sources=sources, _source_abs=src_abs, _raw=ds)
