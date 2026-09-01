"""公司身份/沿革桥：加载 v2.1 桥 CSV，提供 entity_key/record_status 解析，
禁止裸公司名跨年度拼接。identity_mode 必须显式选择 entity 或 lineage。"""
from __future__ import annotations
import csv, os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .models import ValidationError

BRIDGE_DIR = Path(__file__).resolve().parents[1] / ".." / "生成_跨年度同口径桥_CrossYearBridge" / "bridge"
MAP_FILE = "可比公司映射_2024L16_2025L1_v2.csv"
EXCL_FILE = "排除清单_2024_2025_v2.csv"


class IdentityBridge:
    def __init__(self, map_path=None, excl_path=None, version="2.1"):
        self.map_path = Path(map_path) if map_path else (BRIDGE_DIR / MAP_FILE)
        self.excl_path = Path(excl_path) if excl_path else (BRIDGE_DIR / EXCL_FILE)
        self.version = version
        self._entity_of_2024: Dict[str, str] = {}   # 2024源名 -> entity_key
        self._entity_of_2025: Dict[str, str] = {}   # 2025源名 -> entity_key
        self._bridges: List[dict] = []
        self._load()

    def _load(self):
        if not self.map_path.exists():
            raise FileNotFoundError(f"桥映射缺失: {self.map_path}")
        with open(self.map_path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                s24 = r.get("source_2024") or ""
                s25 = r.get("source_2025") or ""
                ek = r.get("entity_key") or ""
                self._bridges.append(r)
                if s24: self._entity_of_2024[s24] = ek
                if s25: self._entity_of_2025[s25] = ek
        if self.excl_path.exists():
            with open(self.excl_path, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    s24 = r.get("source_2024") or ""
                    s25 = r.get("source_2025") or ""
                    ek = r.get("entity_key") or ""
                    if s24: self._entity_of_2024.setdefault(s24, ek)
                    if s25: self._entity_of_2025.setdefault(s25, ek)

    def entity_for_2024(self, name: str) -> Optional[str]:
        return self._entity_of_2024.get(name)

    def entity_for_2025(self, name: str) -> Optional[str]:
        return self._entity_of_2025.get(name)

    def verify_entity_alignment(self, std: Dict[str, str]):
        """校验 v2.1 桥 entity_key 与标准层一致(用于测试)。"""
        bad = []
        for s, ek in self._entity_of_2024.items():
            if s in std and std[s] != ek:
                bad.append((s, ek, std[s]))
        for s, ek in self._entity_of_2025.items():
            if s in std and std[s] != ek:
                bad.append((s, ek, std[s]))
        return bad

    def bridges(self) -> List[dict]:
        return self._bridges


def require_identity_mode(req_identity_mode: Optional[str]):
    """所有公司跨期/跨年度请求必须显式选择 identity_mode。默认禁止裸公司名关联。"""
    if req_identity_mode not in ("entity", "lineage"):
        raise ValidationError("公司跨期/跨年度请求必须显式选择 identity_mode='entity' 或 'lineage'；不支持裸公司名默认关联。")
