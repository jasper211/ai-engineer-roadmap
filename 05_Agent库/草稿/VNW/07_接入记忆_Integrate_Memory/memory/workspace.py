"""VNW专属工作区状态持久化；不写入被监控项目。"""
from __future__ import annotations

import json
from pathlib import Path


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.outputs = self.root / "outputs"
        self.state_file = self.root / "state.json"
        self.outputs.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        if not self.state_file.exists():
            return {"version": 1, "files": {}, "runs": []}
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def save(self, state: dict) -> None:
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_file)
