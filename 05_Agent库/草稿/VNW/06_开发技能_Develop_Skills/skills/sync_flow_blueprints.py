#!/usr/bin/env python3
"""把流程蓝图与 T20 L4 评估连接为前端可用的节点上下文。

运行顺序：
1. sync_data_foundation.py
2. sync_flow_blueprints.py

本脚本只读 L3 流程库和前端现有 T1/T20 JSON，只写前端 flow_context.json。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

L3_DIR = Path("/Users/a112233/Desktop/流程架构项目_jasper/02_过程成果-工作产出/L3流程库")
VNW_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = VNW_ROOT / "10_部署与运行_Deploy_and_Run" / "frontend" / "public" / "data"


def clean(value: str) -> str:
    return re.sub(r"(E2E|流程)$", "", (value or "").replace(" ", "").strip())


def latest_blueprints() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in L3_DIR.glob("流程蓝图_L3-*.md"):
        match = re.match(r"流程蓝图_L3-(.+?)_(.+)_V(\d+)\.(\d+)\.md$", path.name)
        if not match:
            continue
        code, _, major, minor = match.groups()
        current = result.get(code)
        if current is None:
            result[code] = path
            continue
        old = re.search(r"_V(\d+)\.(\d+)\.md$", current.name)
        if old and (int(major), int(minor)) > (int(old.group(1)), int(old.group(2))):
            result[code] = path
    return result


def table_value(text: str, label: str) -> str:
    match = re.search(rf"\|\s*(?:\*\*)?{re.escape(label)}(?:\*\*)?\s*\|\s*(.*?)\s*\|", text)
    return match.group(1).strip() if match else ""


def parse_l4s(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not re.match(r"\|\s*L4-[A-Za-z0-9-]+\s*\|", line):
            continue
        cells = [cell.strip().strip("《》") for cell in line.strip("|").split("|")]
        if len(cells) >= 3:
            rows.append({"l4_code": cells[0], "l4_name": cells[1], "blueprint_deliverable": cells[2]})
    return rows


def parse_steps(text: str, l4s: list[dict]) -> list[dict]:
    """优先读取蓝图主干步骤代码块；没有统一步骤结构时退化为 L4 顺序。"""
    steps = []
    block = re.search(r"##\s*(?:§3|三、).*?(?:主干步骤|流程步骤详述)(.*?)(?=\n---|\n##\s)", text, re.S)
    if block:
        matches = list(re.finditer(r"\[Step\s*(\d+)\]\s*([^\n]+)(.*?)(?=\n\[Step\s*\d+\]|\Z)", block.group(1), re.S))
        for match in matches:
            body = match.group(3)
            l4_match = re.search(r"(L4-[A-Za-z0-9-]+)", body)
            activities = [
                line.strip(" ·\t") for line in body.splitlines()
                if line.strip().startswith("·")
            ]
            steps.append({
                "step_id": f"STEP-{int(match.group(1)):02d}",
                "step_name": match.group(2).strip(),
                "l4_code": l4_match.group(1) if l4_match else "",
                "activities": activities,
            })
    if not steps:
        steps = [{
            "step_id": f"STEP-{index:02d}",
            "step_name": item["l4_name"],
            "l4_code": item["l4_code"],
            "activities": [],
        } for index, item in enumerate(l4s, 1)]
    return steps


def parse_node_l4_map(text: str) -> dict[str, list[str]]:
    """只采纳蓝图中显式出现于同一行的 VN→L4 对应关系。"""
    result: dict[str, list[str]] = {}
    for line in text.splitlines():
        vn_match = re.search(r"(VN-[A-Z0-9]+-\d+)", line)
        if not vn_match:
            continue
        codes = re.findall(r"(L4-[A-Za-z0-9-]+)", line)
        if codes:
            result[vn_match.group(1)] = list(dict.fromkeys(codes))
    return result


def main() -> None:
    nodes = json.loads((DATA_DIR / "node_index.json").read_text())
    tiers = json.loads((DATA_DIR / "l4_tier.json").read_text())
    tier_by_code = {row["l4_code"]: row for row in tiers}
    blueprints = []

    for code, path in latest_blueprints().items():
        text = path.read_text(encoding="utf-8", errors="replace")
        l3_name = table_value(text, "L3名称")
        parsed_l4s = parse_l4s(text)
        l4s = []
        for item in parsed_l4s:
            assessment = tier_by_code.get(item["l4_code"], {})
            l4s.append({**item, **{
                key: assessment.get(key, "") for key in (
                    "automation_tier", "final_tier", "judgment_basis", "action_nature",
                    "action_singularity", "physical_deliverable_ideal", "candidate_agent",
                )
            }})
        blueprints.append({
            "l3_code": f"L3-{code}",
            "l3_name": l3_name,
            "status": table_value(text, "流程状态"),
            "owner": table_value(text, "主责岗位"),
            "collaborators": table_value(text, "协作岗位"),
            "trigger": table_value(text, "触发条件"),
            "exit": table_value(text, "退出条件"),
            "upstream": table_value(text, "关联上游L3"),
            "downstream": table_value(text, "关联下游L3"),
            "source_file": path.name,
            "l4s": l4s,
            "steps": parse_steps(text, parsed_l4s),
            "node_l4_map": parse_node_l4_map(text),
        })

    contexts = []
    for node in nodes:
        target = clean(node.get("l3_flow", ""))
        candidates = [bp for bp in blueprints if clean(bp["l3_name"]) == target]
        if not candidates:
            node_code = node["node_id"].removeprefix("VN-").rsplit("-", 1)[0]
            candidates = [bp for bp in blueprints if bp["l3_code"] == f"L3-{node_code}"]
        contexts.append({"node_id": node["node_id"], "blueprint": candidates[0] if candidates else None})

    (DATA_DIR / "flow_context.json").write_text(
        json.dumps(contexts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    matched = sum(row["blueprint"] is not None for row in contexts)
    print(f"flow_context.json: {matched}/{len(nodes)} 个节点关联流程蓝图")


if __name__ == "__main__":
    main()
