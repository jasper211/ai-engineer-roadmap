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

from tools.file_diff import snapshot_dir, diff_snapshots, unified_diff_text, read_content_truncated, DEFAULT_EXCLUDE_DIRS
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
    who: str = "未知"
    domain: str = "其他"
    change_type: str = "changed"  # added / changed / removed
    before_excerpt: str = ""
    after_excerpt: str = ""
    diff_text: str = ""


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
    first_suggested: str = ""  # ISO 时间戳，供 format_text 算"搁置了几天"用


@dataclass
class ResolvedTask:
    task_id: str
    name: str
    status: str  # "done" / "dismissed"
    evidence: str = ""  # 非空时说明是"文件回执自动识别"关闭的，附上判断依据


@dataclass
class DailyBriefing:
    generated_at: str
    project_root: str
    resolved_tasks: List[ResolvedTask] = field(default_factory=list)
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
                 system_prompt_path: Path = DEFAULT_SYSTEM_PROMPT_PATH,
                 extra_exclude_dirs: Optional[set] = None):
        import os
        self.project_root = Path(project_root)
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.model = model
        self.extensions = extensions or DEFAULT_SCAN_EXTENSIONS
        self.system_prompt_path = system_prompt_path
        # snapshot_dir 的 exclude_dirs 参数是"整体替换默认值"，不是"追加"——
        # 这里做并集，确保调用方额外排除自己项目里的某个大目录（比如把
        # OB知识库_vault、无关客户项目挂在同一个大文件夹里巡检时）不会
        # 意外连 .git/node_modules 这些一直该排除的目录都跟着漏排了。
        self.exclude_dirs = DEFAULT_EXCLUDE_DIRS | (extra_exclude_dirs or set())

    def _load_system_prompt(self) -> str:
        if not self.system_prompt_path.exists():
            raise RuntimeError(f"找不到系统提示词文件: {self.system_prompt_path}")
        return self.system_prompt_path.read_text(encoding="utf-8")

    def seed_baseline(self) -> dict:
        """只做本地文件快照+内容抓取，不做 diff、不调 LLM、不产出简报——用于
        给从未跑过 daily_sensing 的项目建立起点基线。

        真实动机：Rw权益项目(1719个候选文件)、Jasper工作文档(440个候选文件)
        从未建过基线，如果直接跑 scan()，old_hashes 是空的，diff_snapshots
        会把当前全部文件判定为"新增"，打包成一次巨大的合并 LLM 调用去分析——
        这不是"今天变了什么"的正常用法，是把整个项目当天全量灌进去，语义上
        不对，也真实浪费 token。seed_baseline() 只建立"这是起点"这份记录，
        从下一次真实 --daily-scan 开始才是名副其实的增量对比。

        连 file_contents 一起存（不只是 file_hashes）：否则种子之后第一次
        真实检测到某文件变化时，diff_snapshots 的旧内容会是空字符串，展示成
        "整个文件都是新增内容"而不是真正的增量 diff，精度会打折扣。"""
        snapshot = snapshot_dir(self.project_root, extensions=self.extensions,
                                  exclude_files=PTA_OWN_ARTIFACTS, exclude_dirs=self.exclude_dirs)
        file_hashes = {path: info["hash"] for path, info in snapshot.items()}
        file_contents = {path: _read_truncated(self.project_root / path) for path in snapshot}
        return {
            "updated_at": datetime.now().isoformat(),
            "file_hashes": file_hashes,
            "file_contents": file_contents,
            "suggested_task_fingerprints": {},
        }

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
        # 先算"最近被标记完成/关闭、但还没在任何一次简报里露过面"的任务——
        # 这一步必须在 diff 是否为空的分支之前做，不然"今天文件没变化"会导致
        # 已完成的任务永远没有机会被展示一次。每条只展示一次（写回
        # shown_as_resolved=True），不是每天都重复报"这条已完成"。
        base_fp = dict(previous_state.get("suggested_task_fingerprints", {}))
        resolved_tasks = []
        for fp in base_fp.values():
            if fp.get("status") in ("done", "dismissed") and not fp.get("shown_as_resolved"):
                resolved_tasks.append(ResolvedTask(task_id=fp["task_id"], name=fp.get("name", ""),
                                                     status=fp["status"], evidence=fp.get("evidence", "")))
                fp["shown_as_resolved"] = True

        old_hashes = {} if force else previous_state.get("file_hashes", {})
        old_snapshot_shape = {path: {"hash": h} for path, h in old_hashes.items()}

        current_snapshot = snapshot_dir(self.project_root, extensions=self.extensions,
                                          exclude_files=PTA_OWN_ARTIFACTS, exclude_dirs=self.exclude_dirs)
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
                    relevance_reason="沿用上次判断", related_files=fp.get("related_files", []), is_new=False,
                    first_suggested=fp.get("first_suggested", ""),
                )
                for fp in base_fp.values()
                if fp.get("status") == "pending"
            ]
            briefing = DailyBriefing(
                generated_at=generated_at, project_root=str(self.project_root),
                suggested_tasks=pending_tasks, skipped_llm_call=True, resolved_tasks=resolved_tasks,
            )
            updated_state = dict(previous_state)
            updated_state["suggested_task_fingerprints"] = base_fp
            return briefing, updated_state, {}

        old_contents = previous_state.get("file_contents", {})
        updated_contents = dict(old_contents)
        diff_hunks = []  # [{"file":..., "diff_text":...}]
        # SSOT事实层：不依赖LLM是否遗漏某个文件。这里完整保留本轮所有新增/
        # 修改/删除文件的类型、前后内容摘录和可读diff，驾驶舱据此展示“到底变了啥”。
        local_change_details: Dict[str, dict] = {}

        for path in diff.added:
            new_content = _read_truncated(self.project_root / path)
            updated_contents[path] = new_content
            diff_text = f"（新增文件）\n{new_content[:1000]}"
            diff_hunks.append({"file": path, "diff_text": diff_text})
            local_change_details[path] = {
                "change_type": "added", "before_excerpt": "",
                "after_excerpt": new_content[:3000], "diff_text": diff_text,
            }

        for path in diff.changed:
            new_content = _read_truncated(self.project_root / path)
            old_content = old_contents.get(path, "")
            diff_text = unified_diff_text(old_content, new_content, max_lines=MAX_DIFF_LINES)
            diff_hunks.append({
                "file": path,
                "diff_text": diff_text,
            })
            local_change_details[path] = {
                "change_type": "changed", "before_excerpt": old_content[:3000],
                "after_excerpt": new_content[:3000], "diff_text": diff_text,
            }
            updated_contents[path] = new_content

        for path in diff.removed:
            old_content = old_contents.get(path, "")
            local_change_details[path] = {
                "change_type": "removed", "before_excerpt": old_content[:3000],
                "after_excerpt": "", "diff_text": f"（删除文件）\n{old_content[:1000]}",
            }
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

        # 喂给模型"当前搁置中的建议任务"，让它顺手判断今天的变化里有没有哪个
        # 文件恰好是某条任务的回执——这是"文件回执自动识别"这个能力的输入端，
        # 只有 pending 状态的任务才有意义（done/dismissed 已经关闭，不需要
        # 再被判断一遍）。
        pending_for_matching = [
            {"task_id": fp["task_id"], "name": fp.get("name", ""), "related_files": fp.get("related_files", [])}
            for fp in base_fp.values() if fp.get("status") == "pending"
        ]
        if pending_for_matching:
            lines = []
            for p in pending_for_matching:
                files_note = f"（关注文件：{', '.join(p['related_files'])}）" if p["related_files"] else ""
                lines.append(f"- {p['task_id']}: {p['name']}{files_note}")
            user_parts.append("### 当前搁置中、等待回执确认的建议任务\n" + "\n".join(lines))

        user_content = "\n\n".join(user_parts)

        if not self.api_key:
            raise RuntimeError("未设置 DEEPSEEK_API_KEY 环境变量。请先: export DEEPSEEK_API_KEY=sk-xxx")

        system_prompt = self._load_system_prompt()
        raw = call_deepseek(system_prompt, user_content, self.api_key, model=self.model)
        parsed = json.loads(raw)

        changes = []
        seen_change_files = set()
        for c in parsed.get("changes", []):
            file_path = c.get("file", "")
            facts = local_change_details.get(file_path, {})
            changes.append(ChangeItem(
                file=file_path, summary=c.get("summary", ""),
                who=c.get("who", "未知") or "未知", domain=c.get("domain", "其他") or "其他",
                change_type=facts.get("change_type", "changed"),
                before_excerpt=facts.get("before_excerpt", ""),
                after_excerpt=facts.get("after_excerpt", ""),
                diff_text=facts.get("diff_text", ""),
            ))
            seen_change_files.add(file_path)
        # 模型可能合并或漏掉“普通”变化；SSOT不能因此丢文件，缺失项用确定性事实补齐。
        for file_path, facts in local_change_details.items():
            if file_path in seen_change_files:
                continue
            changes.append(ChangeItem(
                file=file_path, summary="本轮巡检检测到文件变化，暂无语义摘要",
                change_type=facts["change_type"],
                before_excerpt=facts["before_excerpt"], after_excerpt=facts["after_excerpt"],
                diff_text=facts["diff_text"],
            ))
        relationships = [RelationshipItem(description=r.get("description", ""),
                                            related_files=r.get("related_files", []))
                          for r in parsed.get("relationships", [])]

        date_str = datetime.now().strftime("%Y%m%d")
        existing_fp = base_fp
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
                prior_status = existing_fp[fingerprint].get("status", "pending")
                # 同一件事（指纹相同）之前被标过 done/dismissed，但今天又被模型
                # 重新建议出来——说明这件事其实没真正解决/关掉，应该重新变回
                # pending，而不是被 **existing_fp 的展开悄悄保留成旧状态、
                # 但同时又出现在"建议任务"列表里，造成"已完成但又建议你做"的
                # 自相矛盾状态。
                reopened = prior_status in ("done", "dismissed")
                # 重开的任务当"新"处理，不是"搁置中"——它上一次是被判定已完成/
                # 已关闭的，今天重新出现意味着"这件事其实又/还没解决"，语义上
                # 更接近一条新发现，而不是"一直没人理会的旧任务"，不该跟真正
                # 搁置了很久的任务混进同一个"⏳搁置中"桶、还显示"已搁置0天"
                # 这种自相矛盾的文案。
                is_new = reopened
                updated_fp[fingerprint] = {**existing_fp[fingerprint], "last_suggested": now_iso,
                                             "name": name, "priority": priority, "signal_to": signal_to,
                                             "needs_mark_alignment": needs_mark_alignment,
                                             "related_files": related_files,
                                             "rationale": t.get("rationale", ""),
                                             "relevance_reason": t.get("relevance_reason", ""),
                                             "status": "pending" if reopened else prior_status}
                if reopened:
                    updated_fp[fingerprint]["first_suggested"] = now_iso  # 重新计天数，不沿用旧的搁置时长
                    updated_fp[fingerprint]["decision_status"] = "pending_review"
                    updated_fp[fingerprint]["merged_into"] = ""
                    updated_fp[fingerprint].pop("execution", None)
            else:
                task_id = _mint_rpt_id(date_str, used_today)
                is_new = True
                updated_fp[fingerprint] = {"task_id": task_id, "first_suggested": now_iso,
                                             "last_suggested": now_iso, "status": "pending",
                                             "name": name, "priority": priority, "signal_to": signal_to,
                                             "needs_mark_alignment": needs_mark_alignment,
                                             "related_files": related_files,
                                             "rationale": t.get("rationale", ""),
                                             "relevance_reason": t.get("relevance_reason", ""),
                                             "decision_status": "pending_review"}

            suggested_tasks.append(SuggestedTask(
                task_id=task_id, name=name, rationale=t.get("rationale", ""),
                priority=priority, signal_to=signal_to, needs_mark_alignment=needs_mark_alignment,
                relevance_reason=t.get("relevance_reason", ""), related_files=related_files, is_new=is_new,
                first_suggested=updated_fp[fingerprint]["first_suggested"],
            ))

            task_map_entries[task_id] = {
                "name": name,
                "steps": [{
                    "action": "manual_review", "tool": "bash",
                    "command": f"echo '请人工核对: {name}'",
                    "description": f"{t.get('rationale', '')}，需人工确认后再决定实际执行步骤",
                }],
            }

        # 文件回执自动识别：模型判断"今天的变化"满足了某条 pending 任务的
        # 要求——只信任真实存在于 pending_for_matching 里的 task_id（不让模型
        # 凭空编一个），命中的立刻标 done 并计入这次简报的 resolved_tasks，
        # 不用等下一轮才展示（下一轮才展示会让"回执生效"这件事看起来延迟了
        # 一天，体验上很怪）。
        pending_task_ids = {p["task_id"] for p in pending_for_matching}
        for r in parsed.get("resolved_pending_tasks", []):
            rid = r.get("task_id", "")
            if rid not in pending_task_ids:
                continue  # 模型编造的/不在搁置列表里的 task_id，直接丢弃
            for fp in updated_fp.values():
                if fp.get("task_id") == rid and fp.get("status") == "pending":
                    evidence = r.get("evidence", "")
                    fp["status"] = "done"
                    fp["status_updated_at"] = now_iso
                    fp["shown_as_resolved"] = True
                    # 此前只把evidence放进当次简报的ResolvedTask对象里，没有存回
                    # fingerprint本身——导致仪表盘的list_tasks_from_state()（读的
                    # 是持久化的fingerprint，不是当次简报）永远拿不到"文件回执自动
                    # 识别"的判断依据，过了当天就再也看不到为什么这条任务被关闭了。
                    fp["evidence"] = evidence
                    resolved_tasks.append(ResolvedTask(task_id=rid, name=fp.get("name", ""),
                                                         status="done", evidence=evidence))
                    break

        briefing = DailyBriefing(
            generated_at=generated_at, project_root=str(self.project_root),
            files_added=len(diff.added), files_changed=len(diff.changed), files_removed=len(diff.removed),
            changes=changes, relationships=relationships, suggested_tasks=suggested_tasks,
            focus_note=focus_note, skipped_llm_call=False, resolved_tasks=resolved_tasks,
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


def _days_since(iso_ts: str) -> int:
    if not iso_ts:
        return 0
    try:
        return max((datetime.now() - datetime.fromisoformat(iso_ts)).days, 0)
    except ValueError:
        return 0


def _days_pending(t: SuggestedTask) -> int:
    """从 first_suggested 算到现在过了几天——用于把"搁置太久没人管"的任务
    跟"今天刚发现"的任务区分开，不是所有 suggested_tasks 都一样新鲜。"""
    return _days_since(t.first_suggested)


def _bucket_tasks(briefing: DailyBriefing):
    """把 suggested_tasks 分成"今天新发现"和"搁置中"两桶，后者按搁置天数
    从久到近排序——搁置越久的任务应该排在最前面，最该被注意到，而不是
    跟今天新出现的混在一起、淹没在列表顺序里。"""
    new_tasks = [t for t in briefing.suggested_tasks if t.is_new]
    aging_tasks = sorted((t for t in briefing.suggested_tasks if not t.is_new),
                         key=_days_pending, reverse=True)
    return new_tasks, aging_tasks


def list_tasks_from_state(state: dict, project_name: str = "", resolved_within_days: int = 14) -> dict:
    """给前端仪表盘用的只读聚合——直接读 daily_sensing_state.json 里已经
    持久化的 suggested_task_fingerprints，不跑 LLM、不做任何文件 diff（那是
    scan() 的职责；仪表盘打开页面/刷新不该触发一次真实巡检，会产生真实
    API 调用费用，且跟"每天定时跑一次"的既定节奏冲突）。

    分三桶：
    - new：pending 状态且首次发现在 1 天以内——没有真正的"这次巡检有没有
      新发现"上下文（不跑 scan()，读不到），用"离首次发现是否够近"做近似，
      够仪表盘展示轻重缓急用，不追求跟 _bucket_tasks 的 is_new 语义完全一致
    - aging：pending 状态且不满足 new 的条件，按搁置天数从久到近排序
    - resolved_recent：done/dismissed 且 status_updated_at 在
      resolved_within_days 天内——**这是一个持续滚动的时间窗判断，不是
      shown_as_resolved 那个"简报只报一次"标记的复用**：shown_as_resolved
      服务的是每日推送场景（避免同一条完成消息被推两次），仪表盘是随时
      可能被打开的常驻界面，用那个标记会导致用户刷新一次页面后，"刚完成"
      的提示就再也看不到了，两者语义不同，不能共用同一套判定。
    """
    fingerprints = state.get("suggested_task_fingerprints", {})
    new_tasks, aging_tasks, resolved_recent = [], [], []

    for fp in fingerprints.values():
        status = fp.get("status", "pending")
        base_item = {
            "task_id": fp.get("task_id", ""), "name": fp.get("name", ""),
            "priority": fp.get("priority", "P2"), "signal_to": fp.get("signal_to", []),
            "needs_mark_alignment": fp.get("needs_mark_alignment", False),
            "related_files": fp.get("related_files", []), "project_name": project_name,
            "rationale": fp.get("rationale", ""),
            "relevance_reason": fp.get("relevance_reason", ""),
            "decision_status": fp.get("decision_status", "pending_review"),
            "decision_updated_at": fp.get("decision_updated_at", ""),
            "owner": fp.get("owner", ""), "due_date": fp.get("due_date", ""),
            "acceptance_criteria": fp.get("acceptance_criteria", ""),
            "decision_note": fp.get("decision_note", ""),
            "merged_into": fp.get("merged_into", ""),
            "execution": fp.get("execution"),
            "first_suggested": fp.get("first_suggested", ""),
            "last_suggested": fp.get("last_suggested", ""),
        }
        if status == "pending":
            days = _days_since(fp.get("first_suggested", ""))
            item = {**base_item, "days_pending": days}
            (new_tasks if days < 1 else aging_tasks).append(item)
        elif status in ("done", "dismissed"):
            updated_at = fp.get("status_updated_at", "")
            if updated_at and _days_since(updated_at) <= resolved_within_days:
                resolved_recent.append({**base_item, "status": status, "status_updated_at": updated_at,
                                          "evidence": fp.get("evidence", "")})

    aging_tasks.sort(key=lambda x: x["days_pending"], reverse=True)
    resolved_recent.sort(key=lambda x: x["status_updated_at"], reverse=True)
    return {"new": new_tasks, "aging": aging_tasks, "resolved_recent": resolved_recent}


def latest_report_summary(workspace: Path, project_name: str = "") -> Optional[dict]:
    """给任务看板"今日动态"用的只读读取——找该项目工作区里最新一份
    daily-scan-*.json 报告（run_id 用 YYYYMMDD-HHMMSS 命名，文件名字典序
    排序即时间序，不需要额外解析时间戳），原样把 changes/relationships/
    resolved_tasks 摘出来给前端渲染。不触发扫描——跟 list_tasks_from_state
    同样的原则，仪表盘打开页面不该产生真实 LLM 调用费用，这里只读已经
    落盘的报告文件。

    从没跑过 --daily-scan 的项目（reports/ 目录为空）返回 None，调用方
    据此展示"该项目还没有过巡检记录"，不是当成错误。"""
    reports_dir = workspace / "reports"
    if not reports_dir.exists():
        return None
    report_files = sorted(reports_dir.glob("daily-scan-*.json"))
    if not report_files:
        return None
    latest = report_files[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    return {
        "project_name": project_name,
        "generated_at": data.get("generated_at", ""),
        "files_added": data.get("files_added", 0),
        "files_changed": data.get("files_changed", 0),
        "files_removed": data.get("files_removed", 0),
        "changes": data.get("changes", []),
        "relationships": data.get("relationships", []),
        "resolved_tasks": data.get("resolved_tasks", []),
        "skipped_llm_call": data.get("skipped_llm_call", False),
    }


def _format_task_block(t: SuggestedTask, marker: str, show_age: bool) -> List[str]:
    signal = f"通知: {', '.join(t.signal_to)}" if t.signal_to else "通知: （无）"
    age_note = f"，已搁置{_days_pending(t)}天" if show_age else ""
    lines = [f"  {marker} {t.task_id} · {t.name}（{t.priority}，{signal}{age_note}）",
             f"      理由: {t.rationale}"]
    if t.relevance_reason:
        lines.append(f"      信号依据: {t.relevance_reason}")
    if t.needs_mark_alignment:
        lines.append("      ⚠️ 需 Terresa/HR/Jasper 先内部对齐，再线下带方案找 Mark")
    if t.related_files:
        lines.append(f"      涉及文件: {', '.join(t.related_files)}")
    return lines


def format_text(briefing: DailyBriefing) -> str:
    """详细版（技术向，供 Jasper 深入排查用，作为企业微信附件发送）。"""
    lines = [f"今日巡检简报 · {briefing.project_root}", f"生成时间: {briefing.generated_at}"]

    if briefing.skipped_llm_call:
        lines.append("- 未检测到任何文件变化，本次不做分析（零 API 调用）")
    else:
        total = briefing.files_added + briefing.files_changed + briefing.files_removed
        lines.append(f"- 检测到 {total} 处变更"
                      f"（新增 {briefing.files_added} / 变更 {briefing.files_changed} / 删除 {briefing.files_removed}）")

        # 按域分组展示，不是碎片化的逐文件流水账——同一域内的多处变化放在
        # 一起，才能看出"这一块今天在忙什么"，而不是要自己在几十行里拼图。
        groups: "Dict[str, List[ChangeItem]]" = {}
        for c in briefing.changes:
            groups.setdefault(c.domain, []).append(c)
        for domain, items in groups.items():
            lines.append(f"- {domain}（{len(items)}处）：")
            for c in items:
                lines.append(f"  · [{c.who}] {c.file}: {c.summary}")

        if briefing.relationships:
            lines.append("- 关联分析：")
            for r in briefing.relationships:
                lines.append(f"  · {r.description}（涉及: {', '.join(r.related_files)}）")

        if briefing.focus_note:
            lines.append(f"- ⚠️ {briefing.focus_note}")

    if briefing.resolved_tasks:
        lines.append("- ✅ 自上次简报以来已完成/关闭：")
        for r in briefing.resolved_tasks:
            if r.evidence:
                status_label = "已完成（文件回执自动识别）"
            elif r.status == "done":
                status_label = "已完成"
            else:
                status_label = "已关闭（人工判定不需要执行）"
            lines.append(f"  · {r.task_id} · {r.name} [{status_label}]")
            if r.evidence:
                lines.append(f"      识别依据: {r.evidence}（如判断有误，重新提出同一件事即可自动重开）")

    new_tasks, aging_tasks = _bucket_tasks(briefing)
    if new_tasks or aging_tasks:
        if new_tasks:
            lines.append("- 🆕 新增建议任务：")
            for i, t in enumerate(new_tasks):
                marker = _CIRCLED_DIGITS[i] if i < len(_CIRCLED_DIGITS) else f"({i + 1})"
                lines.extend(_format_task_block(t, marker, show_age=False))
        if aging_tasks:
            lines.append("- ⏳ 搁置中（按搁置天数从久到近排序）：")
            for i, t in enumerate(aging_tasks):
                marker = _CIRCLED_DIGITS[i] if i < len(_CIRCLED_DIGITS) else f"({i + 1})"
                lines.extend(_format_task_block(t, marker, show_age=True))
        lines.append("")
        lines.append("确认执行某条建议任务，运行：")
        lines.append(f'  agent.py "执行 <任务ID>" --project-root {briefing.project_root} --execute')
        lines.append("确认这条不需要执行（比如已经用别的方式处理掉了），运行：")
        lines.append(f'  agent.py --dismiss <任务ID> --project-root {briefing.project_root}')
        lines.append("两者都不做就是继续搁置——下次简报会显示它已经搁置了几天，不会静默消失，也不会重复生成新ID。")
    elif not briefing.skipped_llm_call:
        lines.append("- 本次没有产生需要关注的建议任务")

    return "\n".join(lines)


def format_text_plain(briefing: DailyBriefing) -> str:
    """通俗版（非技术向，给 Jasper 自己快速扫一眼用）：不出现文件路径/域标签
    这类技术细节，只回答"发生了什么、有什么新的要办、有什么拖了很久没办、
    有什么办完了"。跟详细版一起发——详细版走企业微信文件附件，这份走
    企业微信正文文字，各自发挥各自的用途，不是互相替代。"""
    project_name = Path(briefing.project_root).name
    lines = [f"【{project_name}】今日简报"]

    if briefing.skipped_llm_call:
        lines.append("今天这个项目没有新变化。")
    else:
        total = briefing.files_added + briefing.files_changed + briefing.files_removed
        domains = sorted({c.domain for c in briefing.changes}, key=lambda d: d != "其他")
        domain_note = "、".join(domains[:4]) if domains else ""
        lines.append(f"今天有 {total} 处更新" + (f"，主要在{domain_note}几块" if domain_note else "") + "。")

    new_tasks, aging_tasks = _bucket_tasks(briefing)
    if new_tasks:
        lines.append(f"\n🆕 新任务（{len(new_tasks)}）：")
        for i, t in enumerate(new_tasks, 1):
            lines.append(f"{i}. [{t.priority}] {t.name}")
    if aging_tasks:
        lines.append(f"\n⏳ 还没处理，已经拖着的（{len(aging_tasks)}）：")
        for i, t in enumerate(aging_tasks, 1):
            lines.append(f"{i}. {t.name}（{_days_pending(t)}天）")
    if briefing.resolved_tasks:
        lines.append(f"\n✅ 刚完成/关闭（{len(briefing.resolved_tasks)}）：")
        for i, r in enumerate(briefing.resolved_tasks, 1):
            auto_note = "（自动识别到回执）" if r.evidence else ""
            lines.append(f"{i}. {r.name}{auto_note}")

    if not (new_tasks or aging_tasks) and briefing.skipped_llm_call:
        return "\n".join(lines)

    lines.append("\n详细版见附件。")
    return "\n".join(lines)
