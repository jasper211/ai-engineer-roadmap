"""OB知识库补充材料准入策略。

MCP检索由外层调用，本模块只接收get_note返回的结构并执行Jasper已拍板的准入规则。
"""
from __future__ import annotations

from tools.evidence import EvidenceClass, EvidenceRecord, EvidenceStatus, SourceRef


BLOCK_MARKERS = ("待复核", "源文档", "已被删除")


def note_is_eligible(note: dict) -> tuple[bool, str]:
    frontmatter = note.get("frontmatter") or {}
    content = note.get("content") or ""
    status = str(frontmatter.get("status", "")).strip()
    if any(marker in content for marker in BLOCK_MARKERS):
        return False, "笔记含待复核或源失效标记"
    if status and status != "生效":
        return False, f"笔记状态不是生效：{status}"
    if not note.get("path"):
        return False, "笔记缺少path"
    return True, ""


def supplemental_from_note(note: dict, field_name: str, value, heading: str = "") -> EvidenceRecord:
    eligible, reason = note_is_eligible(note)
    if not eligible:
        raise ValueError(reason)
    frontmatter = note.get("frontmatter") or {}
    return EvidenceRecord(
        field_name=field_name,
        value=value,
        evidence_class=EvidenceClass.SUPPLEMENTAL,
        source=SourceRef(
            source_system="OB",
            source_object=note["path"],
            source_key=heading or note.get("name", ""),
            source_field=field_name,
            source_version=str(frontmatter.get("as_of", "")),
        ),
        status=EvidenceStatus.ACTIVE,
        confidence=str(frontmatter.get("confidence", "UNSTATED")),
    )

