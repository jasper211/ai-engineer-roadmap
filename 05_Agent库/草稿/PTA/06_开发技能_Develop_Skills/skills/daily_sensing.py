#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：每日主动巡检（Daily Sensing）

对应 Jasper 的原话："每天自动检测文件项目，提炼出更新了什么，更新的这些之间
的逻辑是什么，然后提炼出什么任务，这些任务和我的关系是什么"——这是 PTA 从
"被动执行引擎"升级成"主动感知+执行"闭环的第一步。执行前必须经过人工确认
（详见 agents/agent.py 的 --daily-scan 模式与 08_设计提示词/prompts/
daily_sensing_system.md 的安全边界说明），不做全自动执行。

数据流：tools.file_diff 做本地增量 diff（免费、确定性）→ 只把变化的 diff 片段
（不是整份文件）喂给 tools.llm_client 做一次合并的"变化摘要+关系分析+相关性
判断"→ 建议任务铸造成 RPT-YYYYMMDD-NN 格式的 ID（符合 skills/intent_parsing.py
的 TASK_ID_PATTERN），连同本地合成的占位 steps 一起交给调用方去 merge 进目标
项目的 pta_tasks.json——Jasper 确认执行时，走的是完全不变的现有执行管线。

本技能不直接读写 memory.workspace 的任何文件，跟 skills/progress_tracking.py
的设计一致：调用方（agent.py）负责加载/保存 daily_sensing_state.json，
本技能只接收状态 dict、返回更新后的状态 dict。
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tools.file_diff import snapshot_dir, diff_snapshots, unified_diff_text, read_content_truncated
from tools.llm_client import call_deepseek, DEFAULT_MODEL
from tools.office_text import OFFICE_EXTRACTORS

SKILLS_DIR = Path(__file__).resolve().parent
PTA_DIR = SKILLS_DIR.parent.parent
DEFAULT_SYSTEM_PROMPT_PATH = PTA_DIR / "08_设计提示词_Design_Prompts" / "prompts" / "daily_sensing_system.md"

# .docx/.xlsx 走 tools.file_diff.read_content_truncated 内部对 tools.office_text
# 的分流抽取，不是直接当文本 decode——原始格式是 zip+XML，直接 decode 会是乱码。
DEFAULT_SCAN_EXTENSIONS = {".md", ".txt", ".csv", ".py", ".js", ".mjs", ".ts",
                            ".json", ".sh", ".yaml", ".yml"} | set(OFFICE_EXTRACTORS)

# PTA 自己写进目标项目的输出产物，不是项目本身的原生内容——如果不排除，
# 下次扫描会把刚写进 pta_tasks.json 的建议任务当成"新变化"，反过来分析出
# 一堆"关于任务的任务"，真实复现过这个自我递归的 bug。
PTA_OWN_ARTIFACTS = {"pta_tasks.json", "pta_tasks.json.bak"}

MAX_CHARS_PER_FILE = 6000
MAX_DIFF_LINES = 50


@dataclass
class ChangeItem:
    file: str
    summary: str


@dataclass
class RelationshipItem:
    description: str
    related_files: List[str] = field(default_factory=list)


#: signal_to 只能取这四个值——Mark 不在名单里，需要 Mark 裁定的事项走
#: needs_mark_alignment，不是"转给 Mark"。
FOUR_PARTIES = ("Jasper", "Terresa", "HR", "Carrie")


@dataclass
class SuggestedTask:
    task_id: str
    name: str
    rationale: str
    priority: str
    signal_to: List[str] = field(default_factory=list)
    needs_mark_alignment: bool = False
    relevance_reason: str = ""
    related_files: List[str] = field(default_factory=list)
    is_new: bool = True


@dataclass
class DailyBriefing:
    generated_at: str
    project_root: str
    files_added: int = 0
    files_changed: int = 0
    files_removed: int = 0
    changes: List[ChangeItem] = field(default_factory=list)
    relationships: List[RelationshipItem] = field(default_factory=list)
    suggested_tasks: List[SuggestedTask] = field(default_factory=list)
    focus_note: str = ""
    skipped_llm_call: bool = False


def _read_truncated(path: Path, max_chars: int = MAX_CHARS_PER_FILE) -> str:
    return read_content_truncated(path, max_chars)


def _read_pta_focus(project_root: Path) -> Optional[str]:
    focus_path = Path(project_root) / "pta_focus.md"
    if focus_path.exists():
        return _read_truncated(focus_path, max_chars=2000)
    return None


def _task_fingerprint(name: str) -> str:
    """只用任务名做去重键，不掺 related_files——related_files 是 LLM 每次分析时
    自己生成的列表，同一件事在两次独立的 LLM 调用之间，顺序或取舍可能有细微
    差异，之前把它也纳入指纹哈希，导致真实巡检里同一个建议任务被判定成"新任务"
    重复铸造了好几次 RPT ID（2026-07-15 真实复现：5 组内容完全相同的任务分别
    拿到了两个不同 ID）。任务名本身已经是 LLM 生成的语义描述，足够作为"是不是
    同一件事"的判断依据。"""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def _mint_rpt_id(date_str: str, used_today: set) -> str:
    n = 1
    while True:
        candidate = f"RPT-{date_str}-{n:02d}"
        if candidate not in used_today:
            used_today.add(candidate)
            return candidate
        n += 1


class DailySensor:
    """每日巡检：本地 diff → 合并 LLM 分析 → 建议任务铸造。"""

    def __init__(self, project_root: Path, api_key: Optional[str] = None,
                 model: str = DEFAULT_MODEL, extensions: Optional[set] = None,
                 system_prompt_path: Path = DEFAULT_SYSTEM_PROMPT_PATH):
        import os
        self.project_root = Path(project_root)
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.model = model
        self.extensions = extensions or DEFAULT_SCAN_EXTENSIONS
        self.system_prompt_path = system_prompt_path

    def _load_system_prompt(self) -> str:
        if not self.system_prompt_path.exists():
            raise RuntimeError(f"找不到系统提示词文件: {self.system_prompt_path}")
        return self.system_prompt_path.read_text(encoding="utf-8")

    def scan(self, previous_state: dict, force: bool = False,
              recent_task_history: Optional[List[dict]] = None) -> "tuple[DailyBriefing, dict, Dict[str, dict]]":
        """
        Args:
            previous_state: memory.workspace.load_daily_sensing_state() 加载的状态 dict
            force: 忽略上次的哈希基线，把当前所有文件都当"新增"重新分析一遍
            recent_task_history: 可选，state.json 里最近几条 task_history，作为弱相关性信号

        Returns:
            (briefing, updated_state, task_map_entries)
            - updated_state 交给调用方存回 daily_sensing_state.json
            - task_map_entries 交给调用方 merge 进目标项目的 pta_tasks.json
        """
        old_hashes = {} if force else previous_state.get("file_hashes", {})
        old_snapshot_shape = {path: {"hash": h} for path, h in old_hashes.items()}

        current_snapshot = snapshot_dir(self.project_root, extensions=self.extensions,
                                          exclude_files=PTA_OWN_ARTIFACTS)
        diff = diff_snapshots(old_snapshot_shape, current_snapshot)

        generated_at = datetime.now().isoformat()

        if diff.is_empty():
            # 无变化：不产生任何 LLM 调用成本。但之前"仍待确认"的建议任务不能就
            # 这样从简报里消失——v1 没有"确认执行"回写指纹状态的机制（见模块
            # docstring/README 里记录的 v2 待办），所以只要指纹还在状态里，就
            # 一直当作"仍待确认"重新展示，而不是重新分析一遍（省成本，也因为
            # 没有新变化可分析）。
            pending_tasks = [
                SuggestedTask(
                    task_id=fp["task_id"], name=fp.get("name", ""),
                    rationale="沿用上次巡检的建议，本次无新变化未重新分析",
                    priority=fp.get("priority", "P2"), signal_to=fp.get("signal_to", []),
                    needs_mark_alignment=fp.get("needs_mark_alignment", False),
                    relevance_reason="沿用上次判断", related_files=[], is_new=False,
                )
                for fp in previous_state.get("suggested_task_fingerprints", {}).values()
                if fp.get("status") == "pending"
            ]
            briefing = DailyBriefing(
                generated_at=generated_at, project_root=str(self.project_root),
                suggested_tasks=pending_tasks, skipped_llm_call=True,
            )
            return briefing, previous_state, {}

        old_contents = previous_state.get("file_contents", {})
        updated_contents = dict(old_contents)
        diff_hunks = []  # [{"file":..., "diff_text":...}]

        for path in diff.added:
            new_content = _read_truncated(self.project_root / path)
            updated_contents[path] = new_content
            diff_hunks.append({"file": path, "diff_text": f"（新增文件）\n{new_content[:1000]}"})

        for path in diff.changed:
            new_content = _read_truncated(self.project_root / path)
            old_content = old_contents.get(path, "")
            diff_hunks.append({
                "file": path,
                "diff_text": unified_diff_text(old_content, new_content, max_lines=MAX_DIFF_LINES),
            })
            updated_contents[path] = new_content

        for path in diff.removed:
            updated_contents.pop(path, None)

        focus_text = _read_pta_focus(self.project_root)
        focus_note = "" if focus_text else "未找到 pta_focus.md，相关性判断基于通用项目优先级"

        user_parts = []
        for item in diff_hunks:
            user_parts.append(f"### 文件: {item['file']}\n{item['diff_text']}")
        if diff.removed:
            user_parts.append(f"### 已删除的文件\n{', '.join(diff.removed)}")
        if focus_text:
            user_parts.append(f"### 四方关注领域\n{focus_text}")
        if recent_task_history:
            history_lines = [f"- {h.get('summary','')} → {h.get('status','')}" for h in recent_task_history[-5:]]
            user_parts.append("### Jasper 最近让 PTA 做过的事\n" + "\n".join(history_lines))
        user_content = "\n\n".join(user_parts)

        if not self.api_key:
            raise RuntimeError("未设置 DEEPSEEK_API_KEY 环境变量。请先: export DEEPSEEK_API_KEY=sk-xxx")

        system_prompt = self._load_system_prompt()
        raw = call_deepseek(system_prompt, user_content, self.api_key, model=self.model)
        parsed = json.loads(raw)

        changes = [ChangeItem(file=c.get("file", ""), summary=c.get("summary", ""))
                   for c in parsed.get("changes", [])]
        relationships = [RelationshipItem(description=r.get("description", ""),
                                            related_files=r.get("related_files", []))
                          for r in parsed.get("relationships", [])]

        date_str = datetime.now().strftime("%Y%m%d")
        existing_fp = previous_state.get("suggested_task_fingerprints", {})
        used_today = {v["task_id"] for v in existing_fp.values()
                      if v.get("task_id", "").startswith(f"RPT-{date_str}-")}
        updated_fp = dict(existing_fp)

        suggested_tasks = []
        task_map_entries: Dict[str, dict] = {}
        now_iso = generated_at

        for t in parsed.get("suggested_tasks", []):
            name = t.get("name", "")
            priority = t.get("priority", "P2")
            related_files = t.get("related_files", [])
            # signal_to 只信任四方名单里的值——模型偶尔可能把 Mark 也塞进这个
            # 列表（提示词里说了不该这样，但不能只靠提示词兜底），这里再过滤一次。
            signal_to = [p for p in t.get("signal_to", []) if p in FOUR_PARTIES]
            needs_mark_alignment = bool(t.get("needs_mark_alignment", False))
            fingerprint = _task_fingerprint(name)

            if fingerprint in existing_fp:
                task_id = existing_fp[fingerprint]["task_id"]
                is_new = False
                updated_fp[fingerprint] = {**existing_fp[fingerprint], "last_suggested": now_iso,
                                             "name": name, "priority": priority, "signal_to": signal_to,
                                             "needs_mark_alignment": needs_mark_alignment}
            else:
                task_id = _mint_rpt_id(date_str, used_today)
                is_new = True
                updated_fp[fingerprint] = {"task_id": task_id, "first_suggested": now_iso,
                                             "last_suggested": now_iso, "status": "pending",
                                             "name": name, "priority": priority, "signal_to": signal_to,
                                             "needs_mark_alignment": needs_mark_alignment}

            suggested_tasks.append(SuggestedTask(
                task_id=task_id, name=name, rationale=t.get("rationale", ""),
                priority=priority, signal_to=signal_to, needs_mark_alignment=needs_mark_alignment,
                relevance_reason=t.get("relevance_reason", ""), related_files=related_files, is_new=is_new,
            ))

            task_map_entries[task_id] = {
                "name": name,
                "steps": [{
                    "action": "manual_review", "tool": "bash",
                    "command": f"echo '请人工核对: {name}'",
                    "description": f"{t.get('rationale', '')}，需人工确认后再决定实际执行步骤",
                }],
            }

        briefing = DailyBriefing(
            generated_at=generated_at, project_root=str(self.project_root),
            files_added=len(diff.added), files_changed=len(diff.changed), files_removed=len(diff.removed),
            changes=changes, relationships=relationships, suggested_tasks=suggested_tasks,
            focus_note=focus_note, skipped_llm_call=False,
        )

        updated_state = {
            "file_hashes": {path: info["hash"] for path, info in current_snapshot.items()},
            "file_contents": updated_contents,
            "suggested_task_fingerprints": updated_fp,
        }

        return briefing, updated_state, task_map_entries


def to_dict(briefing: DailyBriefing) -> dict:
    return asdict(briefing)


_CIRCLED_DIGITS = "①②③④⑤⑥⑦⑧⑨⑩"


def format_text(briefing: DailyBriefing) -> str:
    lines = [f"今日巡检简报 · {briefing.project_root}", f"生成时间: {briefing.generated_at}"]

    if briefing.skipped_llm_call:
        lines.append("- 未检测到任何文件变化，本次不做分析（零 API 调用）")
    else:
        total = briefing.files_added + briefing.files_changed + briefing.files_removed
        lines.append(f"- 检测到 {total} 处变更"
                      f"（新增 {briefing.files_added} / 变更 {briefing.files_changed} / 删除 {briefing.files_removed}）")
        for c in briefing.changes:
            lines.append(f"  · {c.file}: {c.summary}")

        if briefing.relationships:
            lines.append("- 关联分析：")
            for r in briefing.relationships:
                lines.append(f"  · {r.description}（涉及: {', '.join(r.related_files)}）")

        if briefing.focus_note:
            lines.append(f"- ⚠️ {briefing.focus_note}")

    # 建议任务：无论本次是否真的跑了 LLM 分析都要展示——diff 为空时，previous_state
    # 里"仍待确认"的建议任务由调用方（scan()的空 diff 分支）原样带进了这个列表，
    # 不能因为跳过了 LLM 调用就把它们从简报里漏掉。
    if briefing.suggested_tasks:
        lines.append("- 建议任务：")
        for i, t in enumerate(briefing.suggested_tasks):
            marker = _CIRCLED_DIGITS[i] if i < len(_CIRCLED_DIGITS) else f"({i + 1})"
            tag = "[新]" if t.is_new else "[仍待确认]"
            signal = f"通知: {', '.join(t.signal_to)}" if t.signal_to else "通知: （无）"
            lines.append(f"  {tag} {marker} {t.task_id} · {t.name}（{t.priority}，{signal}）")
            lines.append(f"      理由: {t.rationale}")
            if t.relevance_reason:
                lines.append(f"      信号依据: {t.relevance_reason}")
            if t.needs_mark_alignment:
                lines.append("      ⚠️ 需 Terresa/HR/Jasper 先内部对齐，再线下带方案找 Mark")
            if t.related_files:
                # 补上源文件路径——没有这个，"跟进XX裁定清单"这类任务名脱离了
                # 当天的扫描上下文就没法追溯回具体是哪些文档，不好落地推进。
                lines.append(f"      涉及文件: {', '.join(t.related_files)}")
        lines.append("")
        lines.append("确认执行某条建议任务，运行：")
        lines.append(f'  agent.py "执行 <任务ID>" --project-root {briefing.project_root} --execute')
        lines.append("不确认就是不管它——同一条建议下次巡检还会出现，标记为「仍待确认」，不会重复生成新ID。")
    elif not briefing.skipped_llm_call:
        lines.append("- 本次没有产生需要关注的建议任务")

    return "\n".join(lines)
