"""VNW流程模型证据包。

所有进入模型的值必须先成为EvidenceRecord。该模块不读取任何外部来源，
只定义来源等级、状态、稳定ID和确定性校验。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class EvidenceClass(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    SUPPLEMENTAL = "SUPPLEMENTAL"
    DERIVED = "DERIVED"
    CONSENSUS = "CONSENSUS"


class EvidenceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"
    STALE = "STALE"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class SourceRef:
    source_system: str
    source_object: str
    source_key: str
    source_field: str
    source_version: str = ""
    observed_at: str = ""


@dataclass(frozen=True)
class EvidenceRecord:
    field_name: str
    value: Any
    evidence_class: EvidenceClass
    source: SourceRef
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    confidence: str = "HIGH"
    transform_rule: str = ""
    conflict_note: str = ""
    evidence_id: str = ""

    def __post_init__(self) -> None:
        if self.evidence_class is EvidenceClass.DERIVED and not self.transform_rule:
            raise ValueError("DERIVED证据必须提供transform_rule")
        if self.evidence_class is EvidenceClass.SUPPLEMENTAL and self.status is not EvidenceStatus.ACTIVE:
            raise ValueError("非ACTIVE材料不得作为SUPPLEMENTAL进入业务模型")
        if not self.evidence_id:
            payload = {
                "field_name": self.field_name,
                "value": self.value,
                "evidence_class": self.evidence_class.value,
                "source": asdict(self.source),
                "status": self.status.value,
                "transform_rule": self.transform_rule,
            }
            digest = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()[:20]
            object.__setattr__(self, "evidence_id", f"EVD-{digest}")

    def to_dict(self) -> dict:
        result = asdict(self)
        result["evidence_class"] = self.evidence_class.value
        result["status"] = self.status.value
        return result


def authoritative(field_name: str, value: Any, table: str, key: str, field: str) -> EvidenceRecord:
    return EvidenceRecord(
        field_name=field_name,
        value=value,
        evidence_class=EvidenceClass.AUTHORITATIVE,
        source=SourceRef(
            source_system="PostgreSQL",
            source_object=f"process_analytics.{table}",
            source_key=key,
            source_field=field,
        ),
        status=EvidenceStatus.MISSING if value in (None, "") else EvidenceStatus.ACTIVE,
    )

