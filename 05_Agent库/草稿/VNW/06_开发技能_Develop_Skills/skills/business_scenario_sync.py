"""业务数据分析·场景记录同步。

场景记录（07_接入记忆_Integrate_Memory/business_scenarios/*.json）是人工authoring
的分析产出物——不是自动生成的，"提问"和"拆解口径"必须来自真实业务输入。这个脚本
只做机械同步：把场景记录复制到前端public/data，并生成一份index.json供列表页使用，
不改写场景内容本身。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path


def sync_business_scenarios(source_dir: Path, target_dir: Path) -> dict:
    target_dir.mkdir(parents=True, exist_ok=True)
    index_entries = []
    if source_dir.exists():
        for path in sorted(source_dir.glob("*.json")):
            scenario = json.loads(path.read_text(encoding="utf-8"))
            shutil.copy2(path, target_dir / path.name)
            state_counts: dict[str, int] = {}
            for component in scenario.get("components", []):
                state = component.get("state", "UNKNOWN")
                state_counts[state] = state_counts.get(state, 0) + 1
            index_entries.append({
                "scenario_id": scenario.get("scenario_id", path.stem),
                "scenario_name": scenario.get("scenario_name", ""),
                "status": scenario.get("status", "DRAFT"),
                "raised_by": scenario.get("raised_by", ""),
                "raised_at": scenario.get("raised_at", ""),
                "component_count": len(scenario.get("components", [])),
                "state_counts": state_counts,
                "file": path.name,
            })
    index = {"schema_version": "vnw.business-scenario-index.v1", "scenarios": index_entries}
    (target_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return index
