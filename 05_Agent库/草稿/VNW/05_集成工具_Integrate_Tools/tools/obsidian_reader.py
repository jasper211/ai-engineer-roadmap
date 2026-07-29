"""OB知识材料进入VNW补充层前的资格检查。"""
from __future__ import annotations

from collections.abc import Mapping

from tools.evidence import EvidenceClass, EvidenceRecord, EvidenceStatus, SourceRef


def note_is_eligible(note: Mapping) -> bool:
    content = str(note.get("content") or "")
    status = str(note.get("status") or "")
    if status and status != "生效":
        return False
    if "待复核" in content or "已被删除" in content:
        return False
    return not ("源文档" in content and "删除" in content)


def supplemental_from_note(field_name: str, value, note: Mapping) -> EvidenceRecord:
    if not note_is_eligible(note):
        raise ValueError("待复核、已删除或非生效OB材料不得进入V1补充层")
    return EvidenceRecord(
        field_name=field_name,
        value=value,
        evidence_class=EvidenceClass.SUPPLEMENTAL,
        status=EvidenceStatus.ACTIVE,
        source=SourceRef(
            source_system="OB知识库",
            source_object=str(note.get("path") or ""),
            source_key=str(note.get("note_id") or note.get("path") or ""),
            source_field="content",
            source_version=str(note.get("version") or ""),
        ),
    )
