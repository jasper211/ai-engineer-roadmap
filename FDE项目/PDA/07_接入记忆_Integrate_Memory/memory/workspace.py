#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDA 专属工作区：本地文件读写，物理隔离在本 Agent 目录下
（07_接入记忆_Integrate_Memory/data/），不写入原始 Downloads 目录或其他 Agent 目录。

demo 阶段是一次性全量重跑，不做增量/去重——每次 --run 直接覆盖上一次的看板和运行元信息。
"""
import json
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"


class Workspace:
    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.dashboard_path = self.data_dir / "业绩数据多维分析看板.html"
        self.run_info_path = self.data_dir / "last_run.json"

    def save_run(self, dashboard_html: str, run_info: dict) -> None:
        self.dashboard_path.write_text(dashboard_html, encoding="utf-8")
        self.run_info_path.write_text(
            json.dumps(run_info, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_last_run(self) -> "dict | None":
        if not self.run_info_path.exists():
            return None
        return json.loads(self.run_info_path.read_text(encoding="utf-8"))
