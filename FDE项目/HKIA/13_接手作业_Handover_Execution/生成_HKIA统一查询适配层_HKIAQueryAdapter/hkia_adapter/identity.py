"""公司身份/沿革桥：v2.1 桥 + 标准层 entity_key/lineage。
identity_mode=entity (同法人改名) 与 identity_mode=lineage (业务转让) 必须区分。"""
from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, List, Optional
from .models import ValidationError

BRIDGE_DIR = Path(__file__).resolve().parents[1] / ".." / "生成_跨年度同口径桥_CrossYearBridge" / "bridge"
MAP_FILE = "可比公司映射_2024L16_2025L1_v2.csv"
EXCL_FILE = "排除清单_2024_2025_v2.csv"


class IdentityBridge:
    def __init__(self, map_path=None, excl_path=None, version="2.1"):
        self.map_path = Path(map_path) if map_path else (BRIDGE_DIR / MAP_FILE)
        self.excl_path = Path(excl_path) if excl_path else (BRIDGE_DIR / EXCL_FILE)
        self.version = version
        self._entity_of_2024: Dict[str, str] = {}
        self._entity_of_2025: Dict[str, str] = {}
        self._lineage_of_2024: Dict[str, str] = {}
        self._lineage_of_2025: Dict[str, str] = {}
        self._bridges: List[dict] = []
        self._load()
        self._load_lineage()

    def _load(self):
        if not self.map_path.exists():
            raise FileNotFoundError(f"桥映射缺失: {self.map_path}")
        with open(self.map_path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                s24, s25, ek = r.get("source_2024") or "", r.get("source_2025") or "", r.get("entity_key") or ""
                self._bridges.append(r)
                if s24: self._entity_of_2024[s24] = ek
                if s25: self._entity_of_2025[s25] = ek
        if self.excl_path.exists():
            with open(self.excl_path, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    s24, s25, ek = r.get("source_2024") or "", r.get("source_2025") or "", r.get("entity_key") or ""
                    if s24: self._entity_of_2024.setdefault(s24, ek)
                    if s25: self._entity_of_2025.setdefault(s25, ek)

    def _load_lineage(self):
        """从标准层 company_facts 加载 business_lineage（若可读）。转让类事件：Canada→MyPace 等。"""
        try:
            import sqlite3
            std = Path(__file__).resolve().parents[1] / ".." / "生成_标准事实层_StandardFactLayer" / "data" / "standard_fact_layer_2023_2026Q1.db"
            if std.exists():
                c = sqlite3.connect(std)
                for ab, lg in c.execute("SELECT DISTINCT source_abbrev, business_lineage FROM company_facts WHERE business_lineage IS NOT NULL"):
                    self._lineage_of_2024.setdefault(ab, lg)
                    self._lineage_of_2025.setdefault(ab, lg)
                c.close()
        except Exception:
            pass

    def entity_for_2024(self, name: str) -> Optional[str]:
        return self._entity_of_2024.get(name)
    def entity_for_2025(self, name: str) -> Optional[str]:
        return self._entity_of_2025.get(name)
    def lineage_for(self, name: str) -> Optional[str]:
        return self._lineage_of_2024.get(name) or self._lineage_of_2025.get(name)

    def resolve(self, name: str, identity_mode: str) -> dict:
        """按 identity_mode 返回该公司的解析结果。
        entity: 同法人 (entity_key)
        lineage: 业务沿革 (business_lineage)，可能跨法人承接。"""
        if identity_mode == "lineage":
            lg = self.lineage_for(name)
            return {"identity_mode": "lineage", "entity_key": self.entity_for_2024(name) or self.entity_for_2025(name),
                    "business_lineage": lg,
                    "note": "lineage=业务转让/承接(如 Canada→MyPace), 不得解释为同一法人自然增长" if lg else None}
        # entity
        ek = self.entity_for_2024(name) or self.entity_for_2025(name)
        return {"identity_mode": "entity", "entity_key": ek, "business_lineage": None,
                "note": "entity=同一法人的源名/改名桥"}

    def bridges(self) -> List[dict]:
        return self._bridges


def require_identity_mode(req_identity_mode: Optional[str]):
    if req_identity_mode not in ("entity", "lineage"):
        raise ValidationError("公司跨期/跨年度请求必须显式选择 identity_mode='entity' 或 'lineage'；不支持裸公司名默认关联。")
