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
L4_HEADING = re.compile(r"^###\s+((?:L4-)?[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-\d+)\s+(.+?)\s*$", re.I)
NUMBERED_FLOW_ITEM = re.compile(r"(?:^|→)\s*(\d+)[.、]\s*([^→]+?)(?=\s*→\s*\d+[.、]|$)")
RETIRED_CONTEXT = re.compile(r"废弃|删除|原L4|历史|不再使用|已移除")


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _clean_branch(value: str) -> str:
    return value.strip().strip("|").strip().lstrip("├└─ ").strip()


def parse_blueprint(path: Path, db_l4_codes: set[str]) -> dict:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    all_blueprint_l4s: set[str] = set()
    retired_l4s: set[str] = set()
    for line in lines:
        codes = set(L4_RE.findall(line))
        if RETIRED_CONTEXT.search(line):
            retired_l4s.update(codes)
        else:
            all_blueprint_l4s.update(codes)

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

    # COM等蓝图使用“[COM-16] 名称”表达显式主链路，不使用Step编号。
    if not steps:
        in_main_chain = False
        chain_sequence = 0
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.match(r"^###\s*3\.1\s+主链路", stripped):
                in_main_chain = True
                continue
            if in_main_chain and re.match(r"^###\s*3\.[2-9]", stripped):
                break
            if not in_main_chain:
                continue
            chain_match = re.match(r"^\[(COM-\d+)\]\s*(.+?)(?:──|$)", stripped)
            if not chain_match:
                continue
            chain_sequence += 1
            short_code = chain_match.group(1)
            steps.append({
                "step_id": f"STEP-{chain_sequence:02d}",
                "sequence": chain_sequence,
                "step_name": chain_match.group(2).strip(),
                "l4_codes": [f"L4-{short_code}"],
                "activities": [stripped],
                "source_line": number,
            })

    # CRR等蓝图以三级L4标题划分阶段，并把任务写在Markdown步骤表格中。
    # 同时兼容CPM-01这类省略“L4-”前缀的标题，但必须能与数据库L4精确匹配。
    # 一个L4形成一个流程阶段，表格的每行活动保留为任务拆分依据。
    if not steps:
        table_sequence = 0
        index = 0
        while index < len(lines):
            heading = L4_HEADING.match(lines[index].strip())
            if not heading:
                index += 1
                continue
            heading_code = heading.group(1).upper()
            l4_code = heading_code if heading_code.startswith("L4-") else f"L4-{heading_code}"
            if l4_code not in db_l4_codes:
                index += 1
                continue
            activities = []
            cursor = index + 1
            in_step_table = False
            while cursor < len(lines):
                stripped = lines[cursor].strip()
                if stripped.startswith("### ") or stripped.startswith("## "):
                    break
                if stripped.startswith("|"):
                    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                    if len(cells) >= 2 and cells[0] == "步骤" and cells[1] == "活动":
                        in_step_table = True
                    elif in_step_table and len(cells) >= 2 and cells[0].isdigit():
                        activities.append(cells[1])
                cursor += 1
            if activities:
                table_sequence += 1
                steps.append({
                    "step_id": f"STEP-{table_sequence:02d}",
                    "sequence": table_sequence,
                    "step_name": heading.group(2).strip(),
                    "l4_codes": [l4_code],
                    "activities": activities,
                    "source_line": index + 1,
                })
            index = max(cursor, index + 1)

    # SFC等蓝图只显式给出编号阶段链路，尚未给出阶段与L4的对应关系。
    # 可据此形成“待完善模型”的流程骨架，但绝不按名称相似度猜测L4映射。
    if not steps:
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            if "→" not in stripped:
                continue
            items = list(NUMBERED_FLOW_ITEM.finditer(stripped))
            if len(items) < 2:
                continue
            for sequence, item in enumerate(items, 1):
                step_name = item.group(2).strip().rstrip("。；;")
                steps.append({
                    "step_id": f"STEP-{sequence:02d}",
                    "sequence": sequence,
                    "step_name": step_name,
                    "l4_codes": [],
                    "activities": [step_name],
                    "source_line": number,
                })
            break

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
    all_blueprint_l4s.update(parsed_l4s)
    missing_in_blueprint = sorted(db_l4_codes - all_blueprint_l4s)
    extra_in_blueprint = sorted(all_blueprint_l4s - db_l4_codes)
    structure_status = "PARSED" if steps else "INDEX_ONLY"
    if db_l4_codes and not all_blueprint_l4s and not steps:
        structure_status = "CONFLICT"

    blueprint_value_nodes = []
    for number, line in enumerate(lines, 1):
        if not re.match(r"^\|\s*VN-[A-Z0-9-]+\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        blueprint_value_nodes.append({
            "vn_id": cells[0],
            "vn_name": cells[1],
            "priority": cells[2].replace("*", ""),
            "deliverable": cells[3],
            "l4_codes": [f"L4-{code}" for code in re.findall(r"COM-\d+", cells[4])],
            "status_text": cells[5],
            "source_line": number,
        })

    raci = []
    in_raci = False
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if "RACI矩阵" in stripped and stripped.startswith("##"):
            in_raci = True
            continue
        if in_raci and stripped.startswith("## "):
            break
        if not in_raci or not re.match(r"^\|\s*COM-\d+\s*\|", stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 6:
            raci.append({
                "l4_code": f"L4-{cells[0]}",
                "l4_name": cells[1],
                "accountable": cells[2],
                "responsible": cells[3],
                "consulted": cells[4],
                "informed": cells[5],
                "source_line": number,
            })

    return {
        "structure_status": structure_status,
        "source_path": str(path),
        "source_hash": source_hash,
        "steps": steps if structure_status == "PARSED" else [],
        "decisions": decisions if structure_status == "PARSED" else [],
        "edges": edges if structure_status == "PARSED" else [],
        "blueprint_value_nodes": blueprint_value_nodes,
        "raci": raci,
        "diagnostics": {
            "db_l4_count": len(db_l4_codes),
            "blueprint_l4_count": len(all_blueprint_l4s),
            "parsed_step_l4_count": len(parsed_l4s),
            "unmapped_step_count": sum(1 for step in steps if not step["l4_codes"]),
            "missing_in_blueprint": missing_in_blueprint,
            "extra_in_blueprint": extra_in_blueprint,
            "retired_l4s_ignored": sorted(retired_l4s - db_l4_codes),
        },
    }
