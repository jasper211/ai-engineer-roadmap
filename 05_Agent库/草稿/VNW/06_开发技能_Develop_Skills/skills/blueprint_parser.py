"""解析已确认L3流程蓝图中的显式步骤、判断分支和回退关系。"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


STEP_EN = re.compile(r"^\[Step\s*(\d+)\]\s*(.+?)\s*$", re.I)
STEP_ZH = re.compile(r"^步骤\s*(\d+)[：:]\s*(.+?)\s*$")
L4_RE = re.compile(r"L4-[A-Za-z0-9-]+")
DECISION_INLINE = re.compile(r"【判断节点\s*(\d+)】\s*(.+?)[？?]?\s*$")
DECISION_HEADING = re.compile(r"^###\s*(Q\d+)[：:]\s*(.+?)(?:（Step\s*(\d+)后）)?\s*$", re.I)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _clean_branch(value: str) -> str:
    return value.strip().strip("|").strip().lstrip("├└─ ").strip()


def parse_blueprint(path: Path, db_l4_codes: set[str]) -> dict:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    all_blueprint_l4s = set(L4_RE.findall(text))

    steps: list[dict] = []
    current: dict | None = None
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        match = STEP_EN.match(stripped) or STEP_ZH.match(stripped)
        if match:
            current = {
                "step_id": f"STEP-{int(match.group(1)):02d}",
                "sequence": int(match.group(1)),
                "step_name": match.group(2).strip(),
                "l4_codes": [],
                "activities": [],
                "source_line": number,
            }
            steps.append(current)
            continue
        if current is None:
            continue
        if stripped.startswith("## ") or STEP_EN.match(stripped) or STEP_ZH.match(stripped):
            current = None
            continue
        codes = L4_RE.findall(stripped)
        if codes:
            current["l4_codes"] = list(dict.fromkeys([*current["l4_codes"], *codes]))
            if "执行" in stripped or "→" in stripped:
                current["activities"].append(stripped.lstrip("└├─ ·"))

    decisions: list[dict] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        inline = DECISION_INLINE.search(stripped)
        heading = DECISION_HEADING.match(stripped)
        if not inline and not heading:
            continue
        decision_id = f"Q{inline.group(1)}" if inline else heading.group(1).upper()
        question = (inline.group(2) if inline else heading.group(2)).strip().rstrip("？?")
        after_step = ""
        if heading and heading.group(3):
            after_step = f"STEP-{int(heading.group(3)):02d}"
        elif steps:
            prior = [step for step in steps if step["source_line"] < index + 1]
            if prior:
                after_step = prior[-1]["step_id"]
        branches = []
        for branch_line_no in range(index + 1, min(index + 8, len(lines))):
            branch_line = lines[branch_line_no].strip()
            if branch_line.startswith("### ") or DECISION_INLINE.search(branch_line):
                break
            if "→" not in branch_line:
                continue
            if branch_line.startswith("|"):
                cells = [cell.strip() for cell in branch_line.strip("|").split("|")]
                if len(cells) < 2 or set(cells[0]) <= {"-", ":"}:
                    continue
                label, target = cells[0], cells[1].lstrip("→").strip()
            else:
                parts = _clean_branch(branch_line).split("→", 1)
                if len(parts) != 2:
                    continue
                label, target = parts[0].strip(), parts[1].strip()
            target_step = ""
            step_match = re.search(r"(?:步骤|Step)\s*(\d+)", target, re.I)
            if step_match:
                target_step = f"STEP-{int(step_match.group(1)):02d}"
            target_l4 = next(iter(L4_RE.findall(target)), "")
            branches.append({
                "label": label,
                "target_text": target,
                "target_step": target_step,
                "target_l4": target_l4,
                "is_return": "返回" in target or "重新" in target,
                "source_line": branch_line_no + 1,
            })
        decisions.append({
            "decision_id": decision_id,
            "question": question,
            "after_step": after_step,
            "branches": branches,
            "source_line": index + 1,
        })

    edges = [
        {
            "edge_id": f"SEQ-{left['step_id']}-{right['step_id']}",
            "from": left["step_id"],
            "to": right["step_id"],
            "edge_type": "SEQUENCE",
            "label": "",
            "source_rule": "蓝图显式编号步骤的相邻顺序",
        }
        for left, right in zip(steps, steps[1:])
    ]
    for decision in decisions:
        for branch in decision["branches"]:
            if branch["target_step"] or branch["target_l4"]:
                edges.append({
                    "edge_id": f"{decision['decision_id']}-{len(edges) + 1}",
                    "from": decision["decision_id"],
                    "to": branch["target_step"] or branch["target_l4"],
                    "edge_type": "RETURN" if branch["is_return"] else "DECISION",
                    "label": branch["label"],
                    "source_rule": f"蓝图第{branch['source_line']}行显式分支",
                })

    parsed_l4s = {code for step in steps for code in step["l4_codes"]}
    missing_in_blueprint = sorted(db_l4_codes - all_blueprint_l4s)
    extra_in_blueprint = sorted(all_blueprint_l4s - db_l4_codes)
    structure_status = "PARSED" if steps else "INDEX_ONLY"
    if db_l4_codes and not all_blueprint_l4s:
        structure_status = "CONFLICT"

    return {
        "structure_status": structure_status,
        "source_path": str(path),
        "source_hash": source_hash,
        "steps": steps if structure_status == "PARSED" else [],
        "decisions": decisions if structure_status == "PARSED" else [],
        "edges": edges if structure_status == "PARSED" else [],
        "diagnostics": {
            "db_l4_count": len(db_l4_codes),
            "blueprint_l4_count": len(all_blueprint_l4s),
            "parsed_step_l4_count": len(parsed_l4s),
            "missing_in_blueprint": missing_in_blueprint,
            "extra_in_blueprint": extra_in_blueprint,
        },
    }
