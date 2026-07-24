#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三个项目每日巡检完成后的跨项目关系分析。

只消费已经落盘的文件变化事实，不重新扫描文件；输出是关系线索，不修改项目、
不生成执行命令。无变化时不调用LLM。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List

from tools.llm_client import call_deepseek, DEFAULT_MODEL

SYSTEM_PROMPT = """你是 Jasper 的个人三项目关系分析助手。输入包含：
1) EA流程架构项目（核心业务主线）；2) Jasper工作文档（AI技术试验田）；
3) Rw权益项目（真实项目全貌案例）的本轮文件变化。

分析六类方向：Jasper技术→EA应用、EA方法→Rw验证、Rw事实→EA校准、
Rw问题→Jasper技术需求、EA问题→Jasper技术支撑、Jasper能力→Rw案例验证。
只依据输入文件事实，不因关键词相同就断言因果；证据不足时写“待核对线索”。
严格输出JSON：
{"relations":[{"from_project":"项目名","to_project":"项目名",
"analysis":"关系分析","shared_domains":["域"],"evidence_files":["文件"],
"confidence":"高|中|线索","needs_review":true}]}
没有可靠线索时返回空数组。"""


def analyze_cross_project_relations(project_reports: List[dict], api_key: str,
                                    output_path: Path, model: str = DEFAULT_MODEL) -> dict:
    source_times = {p["project_name"]: p.get("generated_at", "") for p in project_reports}
    facts = []
    for project in project_reports:
        changes = project.get("changes", [])
        if not changes:
            continue
        facts.append({
            "project_name": project["project_name"],
            "changes": [{
                "file": c.get("file", ""), "change_type": c.get("change_type", "changed"),
                "summary": c.get("summary", ""), "domain": c.get("domain", "其他"),
            } for c in changes],
            "internal_relationships": project.get("relationships", []),
        })
    relations = []
    if len(facts) >= 2:
        raw = call_deepseek(SYSTEM_PROMPT, json.dumps(facts, ensure_ascii=False),
                            api_key, model=model)
        relations = json.loads(raw).get("relations", [])
    result = {
        "generated_at": datetime.now().isoformat(),
        "source_report_timestamps": source_times,
        "relations": relations,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
