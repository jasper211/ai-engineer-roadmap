#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：项目智能分析（原 PTA-INTEL_智能项目分析器_v3.py +
PTA-INTEL-RW_智能项目分析器_v3.py 合并迁移，批3）

这两个原脚本表面上同构（都是 --mode analyze/query/cross，都有
CrossDocumentAnalyzer），但翻开数据模型会发现根本不是一回事：
  - PTA-INTEL（通用版）：扫描项目里的 .md/.csv，用正则/关键词猜结构
    （TaskItem：id/description/owner/due_date/status/workstream...）。
  - PTA-INTEL-RW（Rw 项目专用版）：精确读 Rw 项目固定几份跟踪台账 CSV 的
    固定列名（TrackItem：track_id/source_work_id/current_status/
    today_action/blocker/gate/escalation...），字段语义、query 关键词
    （"Roy 的任务"/"Gate状态"这类 Rw 特有查询）、CrossDocumentAnalyzer 的
    判断逻辑（按 source_work_id 找矛盾 vs 按 task.id）全部不同。

    强行把两套数据模型拍成一套，是这次没有必要冒的风险——Rw 那套字段是
    精确对应台账 CSV 的真实列名，通用版猜列名的模糊匹配逻辑套不上去，
    也没有人要求把两边"分析深度"拉齐。

    所以这次"合并成一个技能"，合并的是**入口层**，不是数据模型：两套
    解析器/分析器/CrossDocumentAnalyzer 原样保留（改名避免类名冲突，
    Generic前缀 / Rw前缀），新增 ProjectIntelligence 做统一入口——自动
    探测目标项目目录（或其子目录，Rw 台账 CSV 真实项目里通常嵌套在类似
    07_项目立项启动/ 这样的子目录，不在项目根目录）下有没有 Rw 特征 CSV
    （tools.rw_conventions.TRACKING_FILES 列的那几份固定文件名，重名时
    取最近修改的一份），有就用 Rw 专用解析器，没有就退回通用解析器。
    对调用方（agent.py）来说只有一个入口，不需要自己判断该用哪个，也不
    需要知道台账 CSV 实际嵌套在项目内部哪一层。

⚠️ 迁移时明确删除的部分（不是遗漏，是判断后不再保留）：原 PTA-INTEL 版
（不是 INTEL-RW 版——两边本就不对称）内嵌了一套 `agent_status` 跨 Agent
状态上报（`_update_agent_status`/`_write_dashboard`），会把分析结果写进
PTA 工作区和目标项目之外的第三份路径（Jasper 的全局"Agent健康报告.md"/
"Agent运行仪表盘.md"）。这违反了本项目已确立的 workspace 隔离原则（PTA
自己的状态只写专属工作区，不外溢到别的地方），而且这套集成从一开始就只
存在于 INTEL 版、INTEL-RW 版从未实现它，本就不是两边对齐的功能，不算是
迁移时"漏掉"了什么。
"""

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools.file_diff import read_content_truncated
from tools.rw_conventions import (TRACKING_FILES as RW_TRACKING_FILES, CHARTER_FILE as RW_CHARTER_FILE,
                                   find_rw_data_dir, is_rw_project, blocker_is_active as _blocker_is_active)

_NO_TRUNCATE = 10_000_000  # 文档/表格需要读全文做结构分析，不截断


# ============================================================
# 通用解析器的数据模型（原 PTA-INTEL）
# ============================================================

@dataclass
class TaskItem:
    id: str
    description: str
    owner: str
    due_date: str
    status: str
    workstream: str
    is_completed: bool = False
    is_blocked: bool = False


@dataclass
class RiskItem:
    level: str  # "high", "medium", "low"
    description: str
    owner: str
    mitigation: str


@dataclass
class DocumentInsight:
    doc_path: str
    doc_type: str
    phase: str
    key_points: List[str] = field(default_factory=list)
    tasks: List[TaskItem] = field(default_factory=list)
    risks: List[RiskItem] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)


@dataclass
class GenericProjectStatus:
    project_name: str
    current_phase: str
    overall_progress: float
    active_tasks: List[TaskItem] = field(default_factory=list)
    blocked_tasks: List[TaskItem] = field(default_factory=list)
    risks: List[RiskItem] = field(default_factory=list)
    recent_docs: List[DocumentInsight] = field(default_factory=list)
    summary: str = ""


class GenericDocumentParser:
    """通用文档解析器：从 Markdown 内容里正则/关键词猜结构。"""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.content = read_content_truncated(file_path, _NO_TRUNCATE)
        self.lines = self.content.split("\n") if self.content else []

    def _detect_doc_type(self) -> str:
        name = self.file_path.name.lower()
        content = self.content.lower()
        if "charter" in name or "章程" in name:
            return "charter"
        if "日报" in name or "daily" in name:
            return "daily_report"
        if "风险" in name or "risk" in name or "决策" in name:
            return "risk_register"
        if "backlog" in name or "待办" in name:
            return "backlog"
        if "台账" in name or "执行" in name or "任务" in name:
            return "task_list"
        if "验收" in name or "review" in name:
            return "review"
        if "启动" in name or "启动" in content:
            return "kickoff"
        return "general"

    def _extract_phase(self) -> str:
        patterns = [r"Phase\s*(\d+)", r"P(\d+)", r"阶段\s*[:：]\s*(.+)", r"当前阶段\s*[:：]\s*(.+)"]
        for pattern in patterns:
            match = re.search(pattern, self.content, re.IGNORECASE)
            if match:
                return match.group(1)
        return "unknown"

    def _extract_status_indicators(self) -> Dict[str, List[str]]:
        indicators = {"completed": [], "in_progress": [], "blocked": [], "pending": []}
        for line in self.lines:
            if re.search(r"(green|已完成|已确认|已归档|已冻结|✅|done)", line, re.IGNORECASE):
                indicators["completed"].append(line.strip()[:100])
            elif re.search(r"(yellow|进行中|推进|等待|待确认|🔄|in progress)", line, re.IGNORECASE):
                indicators["in_progress"].append(line.strip()[:100])
            elif re.search(r"(red|红灯|阻塞|blocked|停止|禁止|❌|不得)", line, re.IGNORECASE):
                indicators["blocked"].append(line.strip()[:100])
            elif re.search(r"(pending|待开始|未开始|⏳|todo)", line, re.IGNORECASE):
                indicators["pending"].append(line.strip()[:100])
        return indicators

    def _extract_tasks_from_tables(self) -> List[TaskItem]:
        tasks = []
        in_table = False
        headers: List[str] = []
        rows: List[List[str]] = []

        for line in self.lines:
            if line.startswith("|"):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if not in_table:
                    in_table = True
                    headers = cells
                elif "---" not in line:
                    rows.append(cells)
            else:
                if in_table and rows:
                    tasks.extend(self._parse_task_table(headers, rows))
                in_table, headers, rows = False, [], []
        if in_table and rows:
            tasks.extend(self._parse_task_table(headers, rows))
        return tasks

    def _parse_task_table(self, headers: List[str], rows: List[List[str]]) -> List[TaskItem]:
        tasks = []
        col_map = {}
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if any(kw in h_lower for kw in ["work_id", "任务id", "编号", "id"]):
                col_map["id"] = i
            elif any(kw in h_lower for kw in ["action", "任务", "工作项", "描述", "事项"]):
                col_map["description"] = i
            elif any(kw in h_lower for kw in ["owner", "负责人", "执行人"]):
                col_map["owner"] = i
            elif any(kw in h_lower for kw in ["due", "截止", "完成时间", "日期"]):
                col_map["due_date"] = i
            elif any(kw in h_lower for kw in ["status", "状态", "进度"]):
                col_map["status"] = i
            elif any(kw in h_lower for kw in ["workstream", "工作流", "领域", "类别"]):
                col_map["workstream"] = i

        if "description" not in col_map:
            return tasks

        for row in rows:
            if len(row) <= col_map["description"]:
                continue
            description = row[col_map["description"]].strip()
            if not description or len(description) < 5:
                continue
            if description.lower() in ["action", "任务", "描述", "---"]:
                continue

            def _col(key):
                idx = col_map.get(key)
                return row[idx] if idx is not None and len(row) > idx else ""

            status = self._normalize_status(_col("status"))
            task = TaskItem(
                id=_col("id"), description=description[:200], owner=_col("owner"),
                due_date=_col("due_date"), status=status, workstream=_col("workstream"),
                is_completed=any(kw in status.lower() for kw in
                                  ["completed", "done", "finished", "green", "已完成", "已确认"]),
                is_blocked=any(kw in status.lower() for kw in ["blocked", "red", "阻塞", "红灯", "停止"]),
            )
            tasks.append(task)
        return tasks

    def _normalize_status(self, status_text: str) -> str:
        if not status_text:
            return "pending"
        text = status_text.lower()
        if any(kw in text for kw in ["completed", "done", "finished", "green", "已完成", "已确认", "已归档"]):
            return "completed"
        if any(kw in text for kw in ["blocked", "red", "阻塞", "红灯", "停止", "禁止"]):
            return "blocked"
        if any(kw in text for kw in ["in_progress", "yellow", "进行中", "推进", "等待"]):
            return "in_progress"
        return "pending"

    def _extract_risks(self) -> List[RiskItem]:
        risks = []
        in_risk_section = False
        for line in self.lines:
            if re.search(r"(风险|阻塞|红灯|blocker|risk)", line, re.IGNORECASE) and ("##" in line or "###" in line):
                in_risk_section = True
            elif in_risk_section and line.startswith("## "):
                in_risk_section = False
            if in_risk_section and line.startswith("|"):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 2:
                    level = "medium"
                    if any(kw in cells[0].lower() for kw in ["red", "红灯", "阻塞", "停止", "禁止"]):
                        level = "high"
                    risks.append(RiskItem(level=level, description=cells[0][:200],
                                           owner=cells[1] if len(cells) > 1 else "",
                                           mitigation=cells[2] if len(cells) > 2 else ""))
        return risks

    def _extract_decisions(self) -> List[str]:
        decisions = []
        for line in self.lines:
            if re.search(r"(决定|决议|确认|批准|拍板|决策|decision|confirm|approve)", line):
                content = re.sub(r"^[-*\d\.\s]+", "", line).strip()
                if content and len(content) > 10:
                    decisions.append(content[:200])
        return decisions[:20]

    def _extract_next_actions(self) -> List[str]:
        actions = []
        in_next_section = False
        for line in self.lines:
            if re.search(r"(下一步|明日|未来|接下来|next|tomorrow|future|action)", line, re.IGNORECASE) \
                    and ("##" in line or "###" in line):
                in_next_section = True
            elif in_next_section and line.startswith("## "):
                in_next_section = False
            if in_next_section and (line.startswith("-") or line.startswith("*") or re.match(r"^\d+\.", line)):
                content = re.sub(r"^[-*\d\.\s]+", "", line).strip()
                if content and len(content) > 5:
                    actions.append(content[:200])
        return actions[:20]

    def parse(self) -> DocumentInsight:
        status_indicators = self._extract_status_indicators()
        key_points = (
            [f"完成: {s}" for s in status_indicators["completed"][:5]]
            + [f"进行中: {s}" for s in status_indicators["in_progress"][:5]]
            + [f"阻塞: {s}" for s in status_indicators["blocked"][:5]]
        )
        return DocumentInsight(
            doc_path=str(self.file_path), doc_type=self._detect_doc_type(), phase=self._extract_phase(),
            key_points=key_points, tasks=self._extract_tasks_from_tables(), risks=self._extract_risks(),
            decisions=self._extract_decisions()[:10], next_actions=self._extract_next_actions()[:10],
        )


class GenericProjectAnalyzer:
    """通用项目分析器：整合多文档分析（原 PTA-INTEL 的 ProjectAnalyzer）。"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.documents: List[DocumentInsight] = []

    def analyze_all(self) -> GenericProjectStatus:
        md_files = list(self.project_root.rglob("*.md"))
        for file_path in sorted(md_files, key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
            try:
                insight = GenericDocumentParser(file_path).parse()
            except OSError:
                continue
            if insight.tasks or insight.risks or insight.key_points:
                self.documents.append(insight)
        return self._generate_status()

    def _generate_status(self) -> GenericProjectStatus:
        all_tasks: List[TaskItem] = []
        all_risks: List[RiskItem] = []
        for doc in self.documents:
            all_tasks.extend(doc.tasks)
            all_risks.extend(doc.risks)

        completed = sum(1 for t in all_tasks if t.is_completed)
        total = len(all_tasks)
        progress = (completed / total * 100) if total else 0

        current_phase = "unknown"
        for doc in self.documents:
            if doc.doc_type == "daily_report" and doc.phase:
                current_phase = doc.phase
                break

        summary = (f"项目: {self.project_root.name}\n分析文档数: {len(self.documents)}\n"
                  f"总任务数: {total}\n已完成: {completed} ({progress:.1f}%)\n"
                  f"阻塞中: {sum(1 for t in all_tasks if t.is_blocked)}\n风险数: {len(all_risks)}")

        return GenericProjectStatus(
            project_name=self.project_root.name, current_phase=current_phase, overall_progress=progress,
            active_tasks=[t for t in all_tasks if not t.is_completed and not t.is_blocked],
            blocked_tasks=[t for t in all_tasks if t.is_blocked],
            risks=all_risks[:20], recent_docs=self.documents[:10], summary=summary,
        )

    def query(self, question: str) -> str:
        if not self.documents:
            self.analyze_all()
        all_tasks: List[TaskItem] = []
        all_risks: List[RiskItem] = []
        for doc in self.documents:
            all_tasks.extend(doc.tasks)
            all_risks.extend(doc.risks)

        q = question.lower()
        if any(kw in q for kw in ["进度", "progress", "做到哪", "状态", "status"]):
            return self._answer_progress(all_tasks)
        if any(kw in q for kw in ["阻塞", "block", "红灯", "red", "问题", "problem"]):
            return self._answer_blockers(all_tasks, all_risks)
        if any(kw in q for kw in ["下一步", "next", "接下来", "明天", "tomorrow", "action"]):
            return self._answer_next_actions()
        if any(kw in q for kw in ["负责人", "owner", "谁负责", "who"]):
            return self._answer_owners(all_tasks)
        if any(kw in q for kw in ["逾期", "overdue", "到期", "due", "delay"]):
            return self._answer_overdue(all_tasks)
        return self._generate_status().summary

    def _answer_progress(self, tasks: List[TaskItem]) -> str:
        total = len(tasks)
        if not total:
            return "未找到任务数据。"
        completed = sum(1 for t in tasks if t.is_completed)
        lines = [f"# 项目进度报告\n", f"- 总任务: {total}", f"- 已完成: {completed} ({completed/total*100:.1f}%)",
                 f"- 阻塞中: {sum(1 for t in tasks if t.is_blocked)}", "\n## 按工作流分布\n"]
        by_ws: Dict[str, Dict[str, int]] = {}
        for t in tasks:
            ws = t.workstream or "未分类"
            by_ws.setdefault(ws, {"total": 0, "completed": 0})
            by_ws[ws]["total"] += 1
            if t.is_completed:
                by_ws[ws]["completed"] += 1
        for ws, stats in sorted(by_ws.items()):
            pct = stats["completed"] / stats["total"] * 100 if stats["total"] else 0
            lines.append(f"- {ws}: {stats['completed']}/{stats['total']} ({pct:.0f}%)")
        return "\n".join(lines)

    def _answer_blockers(self, tasks: List[TaskItem], risks: List[RiskItem]) -> str:
        blocked = [t for t in tasks if t.is_blocked]
        high_risks = [r for r in risks if r.level == "high"]
        lines = ["# 阻塞与风险报告\n"]
        if blocked:
            lines.append(f"## 阻塞任务 ({len(blocked)})\n")
            for t in blocked[:10]:
                lines.append(f"- [{t.workstream}] {t.description[:80]}（Owner: {t.owner}, Due: {t.due_date}）")
        if high_risks:
            lines.append(f"\n## 高风险 ({len(high_risks)})\n")
            for r in high_risks[:10]:
                lines.append(f"- {r.description[:80]}（Owner: {r.owner}, 应对: {r.mitigation[:60]}）")
        if not blocked and not high_risks:
            lines.append("当前无阻塞任务或高风险。")
        return "\n".join(lines)

    def _answer_next_actions(self) -> str:
        actions = [a for doc in self.documents for a in doc.next_actions]
        if not actions:
            return "未找到下一步行动。"
        lines = [f"# 下一步行动 ({len(actions)})\n"]
        lines.extend(f"{i}. {a}" for i, a in enumerate(actions[:15], 1))
        return "\n".join(lines)

    def _answer_owners(self, tasks: List[TaskItem]) -> str:
        by_owner: Dict[str, List[TaskItem]] = {}
        for t in tasks:
            by_owner.setdefault(t.owner or "未指定", []).append(t)
        lines = ["# 负责人任务分布\n"]
        for owner, owner_tasks in sorted(by_owner.items(), key=lambda x: len(x[1]), reverse=True):
            completed = sum(1 for t in owner_tasks if t.is_completed)
            lines.append(f"\n## {owner} ({len(owner_tasks)} 任务, {completed} 完成)\n")
            for t in owner_tasks[:5]:
                icon = "✅" if t.is_completed else "🔴" if t.is_blocked else "🔄"
                lines.append(f"{icon} {t.description[:60]} (Due: {t.due_date})")
        return "\n".join(lines)

    def _answer_overdue(self, tasks: List[TaskItem]) -> str:
        today = datetime.now().date()
        overdue = []
        for t in tasks:
            if t.due_date and not t.is_completed:
                try:
                    due = datetime.strptime(t.due_date, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if due < today:
                    overdue.append((t, (today - due).days))
        if not overdue:
            return "当前无逾期任务。"
        lines = [f"# 逾期任务 ({len(overdue)})\n"]
        for t, days in sorted(overdue, key=lambda x: x[1], reverse=True)[:15]:
            lines.append(f"- [{t.workstream}] {t.description[:80]}（逾期 {days} 天 | Owner: {t.owner}）")
        return "\n".join(lines)


class GenericCrossDocumentAnalyzer:
    def __init__(self, documents: List[DocumentInsight]):
        self.documents = documents

    def find_contradictions(self) -> List[str]:
        contradictions = []
        task_status_map: Dict[str, str] = {}
        for doc in self.documents:
            for task in doc.tasks:
                if task.id:
                    if task.id in task_status_map and task_status_map[task.id] != task.status:
                        contradictions.append(f"任务 {task.id} 状态矛盾: {task_status_map[task.id]} vs {task.status}")
                    else:
                        task_status_map[task.id] = task.status
        return contradictions

    def find_gaps(self) -> List[str]:
        gaps = []
        for doc in self.documents:
            for task in doc.tasks:
                if not task.owner and not task.is_completed:
                    gaps.append(f"[{doc.doc_type}] 任务无负责人: {task.description[:60]}")
                if not task.due_date and not task.is_completed:
                    gaps.append(f"[{doc.doc_type}] 任务无截止日期: {task.description[:60]}")
        return gaps

    def find_duplicates(self) -> List[str]:
        duplicates = []
        desc_map: Dict[str, str] = {}
        for doc in self.documents:
            for task in doc.tasks:
                desc = task.description[:50]
                if desc in desc_map:
                    duplicates.append(f"重复任务: {desc[:60]}...（{desc_map[desc]} 和 {doc.doc_path}）")
                else:
                    desc_map[desc] = doc.doc_path
        return duplicates


# ============================================================
# Rw 项目专用解析器的数据模型（原 PTA-INTEL-RW）
# ============================================================

@dataclass
class RwTrackItem:
    track_id: str
    source_work_id: str
    workstream: str
    priority: str
    owner: str
    current_status: str
    today_action: str
    blocker: str
    gate: str
    next_update: str
    output: str
    escalation: str

    @property
    def is_completed(self) -> bool:
        return any(kw in self.current_status.lower() for kw in
                    ["done", "completed", "finished", "confirmed", "green"])

    @property
    def is_blocked(self) -> bool:
        return (any(kw in self.current_status.lower() for kw in ["blocked", "red", "阻塞", "停止"])
                or _blocker_is_active(self.blocker))

    @property
    def is_ready(self) -> bool:
        return any(kw in self.current_status.lower() for kw in ["ready", "可执行", "待确认"])

    @property
    def needs_escalation(self) -> bool:
        return bool(self.escalation) and not self.is_completed


@dataclass
class RwProjectStatus:
    project_name: str
    total_tracks: int
    completed: int
    in_progress: int
    blocked: int
    ready: int
    not_started: int
    by_workstream: Dict[str, Dict] = field(default_factory=dict)
    by_owner: Dict[str, Dict] = field(default_factory=dict)
    by_priority: Dict[str, int] = field(default_factory=dict)
    blockers: List[RwTrackItem] = field(default_factory=list)
    escalations: List[RwTrackItem] = field(default_factory=list)
    recent_actions: List[RwTrackItem] = field(default_factory=list)
    summary: str = ""


class RwProjectParser:
    """Rw 项目专用解析器：精确读固定几份跟踪台账 CSV 的固定列名。

    构造函数接收的 project_root 必须是台账 CSV 实际所在的目录（用
    tools.rw_conventions.find_rw_data_dir() 解析出来的那一层），不是项目的
    顶层根目录——这两者在真实项目里不是一回事，台账通常嵌套在类似
    07_项目立项启动/ 这样的子目录里。ProjectIntelligence 负责做这次解析，
    这里保持"拿到的就是正确目录"的简单假设。"""

    TRACKING_FILES = RW_TRACKING_FILES
    CHARTER_FILE = RW_CHARTER_FILE

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.tracks: List[RwTrackItem] = []
        self.charter_content = ""
        self.daily_reports: List[Path] = []

    def parse_tracking_csv(self) -> List[RwTrackItem]:
        import csv as csv_module
        tracks = []
        for filename in self.TRACKING_FILES:
            file_path = self.project_root / filename
            if not file_path.exists():
                continue
            content = read_content_truncated(file_path, _NO_TRUNCATE)
            for row in csv_module.DictReader(content.splitlines()):
                track = RwTrackItem(
                    track_id=row.get("track_id", ""), source_work_id=row.get("source_work_id", ""),
                    workstream=row.get("workstream", ""), priority=row.get("priority", ""),
                    owner=row.get("owner", ""), current_status=row.get("current_status", ""),
                    today_action=row.get("today_action", ""), blocker=row.get("blocker", ""),
                    gate=row.get("gate", ""), next_update=row.get("next_update", ""),
                    output=row.get("output", ""), escalation=row.get("escalation", ""),
                )
                if track.track_id and track.track_id != "track_id":
                    tracks.append(track)
        return tracks

    def parse_charter(self) -> str:
        charter_path = self.project_root / self.CHARTER_FILE
        return read_content_truncated(charter_path, _NO_TRUNCATE) if charter_path.exists() else ""

    def parse_daily_reports(self) -> List[Path]:
        reports = list(self.project_root.glob("53_Phase0*日报*.md"))
        return sorted(reports, key=lambda p: p.stat().st_mtime, reverse=True)

    def parse_all(self) -> "Tuple[List[RwTrackItem], str, List[Path]]":
        self.tracks = self.parse_tracking_csv()
        self.charter_content = self.parse_charter()
        self.daily_reports = self.parse_daily_reports()
        return self.tracks, self.charter_content, self.daily_reports


class RwProjectAnalyzer:
    """Rw 项目分析器（原 PTA-INTEL-RW 的 RwProjectAnalyzer）。"""

    def __init__(self, tracks: List[RwTrackItem], charter: str, reports: List[Path]):
        self.tracks = tracks
        self.charter = charter
        self.reports = reports

    def analyze(self) -> RwProjectStatus:
        total = len(self.tracks)
        # completed/is_blocked/is_ready 这三个判断互相独立，同一条跟踪项完全
        # 可能同时命中多个（比如状态已经写"完成"，但 blocker 字段还留着历史
        # 说明文字）——之前用 `total - completed - blocked - not_started` 反推
        # "进行中"，真实数据一验证就发现这个假设不成立，算出了负数。改成按
        # 优先级单遍分类，每条跟踪项只落进一个桶，总数恒等，不会再出现负数：
        # 完成 > 阻塞 > 就绪 > （有今日动作视为）进行中 > 未开始。
        completed = blocked = ready = in_progress = not_started = 0
        for t in self.tracks:
            if t.is_completed:
                completed += 1
            elif t.is_blocked:
                blocked += 1
            elif t.is_ready:
                ready += 1
            elif t.today_action.strip():
                in_progress += 1
            else:
                not_started += 1

        by_workstream: Dict[str, Dict[str, int]] = {}
        by_owner: Dict[str, Dict[str, int]] = {}
        by_priority: Dict[str, int] = {}
        for t in self.tracks:
            ws = t.workstream or "未分类"
            by_workstream.setdefault(ws, {"total": 0, "completed": 0, "blocked": 0})
            by_workstream[ws]["total"] += 1
            owner = t.owner or "未指定"
            by_owner.setdefault(owner, {"total": 0, "completed": 0, "blocked": 0})
            by_owner[owner]["total"] += 1
            if t.is_completed:
                by_workstream[ws]["completed"] += 1
                by_owner[owner]["completed"] += 1
            elif t.is_blocked:
                by_workstream[ws]["blocked"] += 1
                by_owner[owner]["blocked"] += 1
            p = t.priority or "未指定"
            by_priority[p] = by_priority.get(p, 0) + 1

        blockers = [t for t in self.tracks if t.is_blocked and not t.is_completed]
        escalations = [t for t in self.tracks if t.needs_escalation]
        recent_actions = [t for t in self.tracks if t.today_action and not t.is_completed]

        progress = (completed / total * 100) if total else 0
        summary = (f"Rw 权益项目 Phase 0 状态\n总跟踪项: {total}\n已完成: {completed} ({progress:.1f}%)\n"
                  f"进行中: {in_progress}\n就绪待执行: {ready}\n阻塞中: {blocked}\n未开始: {not_started}\n"
                  f"阻塞项: {len(blockers)}\n需升级: {len(escalations)}")

        return RwProjectStatus(
            project_name="RW 权益 Layer B 事业线建设项目", total_tracks=total, completed=completed,
            in_progress=in_progress, blocked=blocked, ready=ready, not_started=not_started,
            by_workstream=by_workstream, by_owner=by_owner, by_priority=by_priority,
            blockers=blockers, escalations=escalations, recent_actions=recent_actions, summary=summary,
        )

    def query(self, question: str) -> str:
        status = self.analyze()
        q = question.lower()
        if any(kw in q for kw in ["进度", "progress", "状态", "status", "overview", "概览"]):
            return self._answer_progress(status)
        if any(kw in q for kw in ["阻塞", "block", "红灯", "red", "问题", "problem", "风险", "risk"]):
            return self._answer_blockers(status)
        if any(kw in q for kw in ["下一步", "next", "接下来", "明天", "今天", "today", "action"]):
            return self._answer_next_actions(status)
        if any(kw in q for kw in ["roy", "amanda", "mark", "teresa", "carrier", "菲菲"]):
            return self._answer_person(question)
        if any(kw in q for kw in ["tob", "toi", "shared", "启动", "合规", "合同"]):
            return self._answer_workstream(question)
        if any(kw in q for kw in ["负责人", "owner", "谁负责", "who", "分配", "assignment"]):
            return self._answer_owners(status)
        if any(kw in q for kw in ["逾期", "overdue", "到期", "due", "delay"]):
            return self._answer_overdue()
        if any(kw in q for kw in ["gate", "阶段门", "门槛", "评审"]):
            return self._answer_gates()
        return status.summary

    def _answer_progress(self, status: RwProjectStatus) -> str:
        lines = ["# RW 权益项目 Phase 0 进度报告\n", f"- 总跟踪项: {status.total_tracks}",
                 f"- 已完成: {status.completed} ({status.completed/status.total_tracks*100:.1f}%)"
                 if status.total_tracks else "- 已完成: 0",
                 f"- 进行中: {status.in_progress}", f"- 就绪待执行: {status.ready}",
                 f"- 阻塞中: {status.blocked}", f"- 未开始: {status.not_started}", "\n## 按工作流分布\n"]
        for ws, stats in sorted(status.by_workstream.items()):
            pct = stats["completed"] / stats["total"] * 100 if stats["total"] else 0
            blocked_note = f" ({stats.get('blocked', 0)} 阻塞)" if stats.get("blocked", 0) else ""
            lines.append(f"- {ws}: {stats['completed']}/{stats['total']} ({pct:.0f}%){blocked_note}")
        return "\n".join(lines)

    def _answer_blockers(self, status: RwProjectStatus) -> str:
        lines = ["# 阻塞与风险报告\n"]
        if status.blockers:
            lines.append(f"## 阻塞项 ({len(status.blockers)})\n")
            for t in status.blockers:
                lines.append(f"### [{t.track_id}] {t.workstream}")
                lines.append(f"- 状态: {t.current_status} | 阻塞: {t.blocker} | Owner: {t.owner} | Gate: {t.gate}")
        else:
            lines.append("当前无阻塞项。")
        if status.escalations:
            lines.append(f"\n## 需升级事项 ({len(status.escalations)})\n")
            for t in status.escalations:
                lines.append(f"- [{t.track_id}] {t.workstream}: {t.escalation}")
        return "\n".join(lines)

    def _answer_next_actions(self, status: RwProjectStatus) -> str:
        if not status.recent_actions:
            return "未找到下一步行动。"
        lines = [f"# 下一步行动 ({len(status.recent_actions)})\n"]
        for t in status.recent_actions[:15]:
            icon = "✅" if t.is_completed else "🔴" if t.is_blocked else "🔄"
            lines.append(f"{icon} [{t.track_id}] {t.workstream}: {t.today_action[:100]}")
        return "\n".join(lines)

    def _answer_owners(self, status: RwProjectStatus) -> str:
        lines = ["# 负责人任务分布\n"]
        for owner, stats in sorted(status.by_owner.items(), key=lambda x: x[1]["total"], reverse=True):
            if not stats["total"]:
                continue
            lines.append(f"\n## {owner} ({stats['total']} 项, {stats['completed']} 完成, "
                         f"{stats.get('blocked', 0)} 阻塞)\n")
            for t in [x for x in self.tracks if x.owner == owner and not x.is_completed][:5]:
                icon = "🔴" if t.is_blocked else "🔄"
                lines.append(f"{icon} [{t.track_id}] {t.workstream}: {t.today_action[:60]}")
        return "\n".join(lines)

    def _answer_person(self, question: str) -> str:
        person = next((n for n in ["roy", "amanda", "mark", "teresa", "carrier", "菲菲"]
                       if n in question.lower()), None)
        if not person:
            return "未指定人员。"
        person_tracks = [t for t in self.tracks if person.lower() in t.owner.lower()]
        if not person_tracks:
            return f"未找到 {person} 的任务。"
        completed = [t for t in person_tracks if t.is_completed]
        active = [t for t in person_tracks if not t.is_completed]
        blocked = [t for t in person_tracks if t.is_blocked]
        lines = [f"# {person.upper()} 的任务\n",
                 f"总计: {len(person_tracks)} | 完成: {len(completed)} | 活跃: {len(active)} | 阻塞: {len(blocked)}\n"]
        if blocked:
            lines.append(f"## 阻塞中 ({len(blocked)})\n")
            for t in blocked:
                lines.append(f"- [{t.track_id}] {t.workstream}（阻塞: {t.blocker}）")
        if active:
            lines.append(f"\n## 进行中 ({len(active)})\n")
            for t in active[:10]:
                lines.append(f"- [{t.track_id}] {t.workstream}: {t.today_action[:80]}（Gate: {t.gate}）")
        return "\n".join(lines)

    def _answer_workstream(self, question: str) -> str:
        ws = next((n for n in ["tob", "toi", "shared", "启动", "合规", "合同", "产品", "数据"]
                   if n in question.lower()), None)
        if not ws:
            return "未指定工作流。"
        ws_tracks = [t for t in self.tracks if ws.lower() in t.workstream.lower()]
        if not ws_tracks:
            return f"未找到 {ws} 的任务。"
        completed = [t for t in ws_tracks if t.is_completed]
        blocked = [t for t in ws_tracks if t.is_blocked]
        lines = [f"# {ws.upper()} 工作流\n",
                 f"总计: {len(ws_tracks)} | 完成: {len(completed)} | 阻塞: {len(blocked)}\n"]
        for t in ws_tracks:
            icon = "✅" if t.is_completed else "🔴" if t.is_blocked else "🔄"
            lines.append(f"{icon} [{t.track_id}] {t.owner}: {t.today_action[:80]}")
        return "\n".join(lines)

    def _answer_overdue(self) -> str:
        today = datetime.now().date()
        overdue = []
        for t in self.tracks:
            if not t.is_completed and t.next_update:
                try:
                    due = datetime.strptime(t.next_update, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if due < today:
                    overdue.append((t, (today - due).days))
        if not overdue:
            return "当前无逾期任务。"
        lines = [f"# 逾期任务 ({len(overdue)})\n"]
        for t, days in sorted(overdue, key=lambda x: x[1], reverse=True)[:15]:
            lines.append(f"- [{t.track_id}] {t.workstream}（逾期 {days} 天 | Owner: {t.owner}）")
        return "\n".join(lines)

    def _answer_gates(self) -> str:
        by_gate: Dict[str, List[RwTrackItem]] = {}
        for t in self.tracks:
            by_gate.setdefault(t.gate or "未指定", []).append(t)
        lines = ["# Gate 状态\n"]
        for gate, tracks in sorted(by_gate.items()):
            completed = sum(1 for t in tracks if t.is_completed)
            blocked = sum(1 for t in tracks if t.is_blocked)
            icon = "🟢" if completed == len(tracks) else "🔴" if blocked else "🟡"
            lines.append(f"\n## {icon} {gate} ({completed}/{len(tracks)} 完成, {blocked} 阻塞)\n")
            for t in tracks:
                t_icon = "✅" if t.is_completed else "🔴" if t.is_blocked else "🔄"
                lines.append(f"{t_icon} [{t.track_id}] {t.workstream}: {t.owner}")
        return "\n".join(lines)


class RwCrossDocumentAnalyzer:
    def __init__(self, tracks: List[RwTrackItem]):
        self.tracks = tracks

    def find_contradictions(self) -> List[str]:
        contradictions = []
        source_map: Dict[str, RwTrackItem] = {}
        for t in self.tracks:
            if not t.source_work_id:
                continue
            if t.source_work_id in source_map:
                old = source_map[t.source_work_id]
                if old.is_completed and not t.is_completed:
                    contradictions.append(f"[{t.source_work_id}] 状态矛盾: "
                                          f"{old.track_id} 标记完成，但 {t.track_id} 未完成")
            else:
                source_map[t.source_work_id] = t
        return contradictions

    def find_gaps(self) -> List[str]:
        gaps = []
        for t in self.tracks:
            if not t.owner and not t.is_completed:
                gaps.append(f"[{t.track_id}] 无负责人: {t.today_action[:60]}")
            if t.is_blocked and not t.escalation:
                gaps.append(f"[{t.track_id}] 有阻塞但无升级条件")
        return gaps

    def find_duplicates(self) -> List[str]:
        duplicates = []
        action_map: Dict[str, str] = {}
        for t in self.tracks:
            action = t.today_action[:50]
            if not action:
                continue
            if action in action_map:
                duplicates.append(f"重复动作: {action[:60]}...（{action_map[action]} 和 {t.track_id}）")
            else:
                action_map[action] = t.track_id
        return duplicates


# ============================================================
# 统一入口：自动探测该用哪个后端
# ============================================================
# is_rw_project 直接复用 tools.rw_conventions 的实现（导入时已经起了这个
# 名字），这里不用重新定义。


class ProjectIntelligence:
    """统一入口：自动探测项目目录（或其子目录）下有没有 Rw 特征 CSV，选通用
    解析器还是 Rw 专用解析器，调用方不需要自己判断该用哪个后端，也不需要
    知道台账 CSV 实际嵌套在项目内部哪一层子目录。"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        rw_data_dir = find_rw_data_dir(self.project_root)
        self.is_rw = rw_data_dir is not None
        if self.is_rw:
            tracks, charter, reports = RwProjectParser(rw_data_dir).parse_all()
            self._rw_tracks = tracks
            self._analyzer = RwProjectAnalyzer(tracks, charter, reports)
        else:
            self._analyzer = GenericProjectAnalyzer(self.project_root)

    def analyze(self):
        return self._analyzer.analyze() if self.is_rw else self._analyzer.analyze_all()

    def query(self, question: str) -> str:
        return self._analyzer.query(question)

    def cross(self) -> "Tuple[List[str], List[str], List[str]]":
        """Returns (contradictions, gaps, duplicates)。"""
        if self.is_rw:
            cross_analyzer = RwCrossDocumentAnalyzer(self._rw_tracks)
        else:
            if not self._analyzer.documents:
                self._analyzer.analyze_all()
            cross_analyzer = GenericCrossDocumentAnalyzer(self._analyzer.documents)
        return cross_analyzer.find_contradictions(), cross_analyzer.find_gaps(), cross_analyzer.find_duplicates()


def format_analyze_text(status, is_rw: bool) -> str:
    lines = ["[PTA-INTEL] 项目分析报告" + ("（Rw 专用解析器）" if is_rw else "（通用解析器）"), status.summary]
    if is_rw:
        if status.blockers:
            lines.append(f"\n## 阻塞项 ({len(status.blockers)})\n")
            for t in status.blockers[:5]:
                lines.append(f"- [{t.track_id}] {t.workstream}（阻塞: {t.blocker}, Owner: {t.owner}）")
        if status.escalations:
            lines.append(f"\n## 需升级 ({len(status.escalations)})\n")
            for t in status.escalations[:5]:
                lines.append(f"- [{t.track_id}] {t.escalation}")
    else:
        if status.active_tasks:
            lines.append(f"\n## 活跃任务 ({len(status.active_tasks)})\n")
            for t in status.active_tasks[:10]:
                lines.append(f"- [{t.workstream}] {t.description[:80]}（Owner: {t.owner}, Due: {t.due_date}）")
        if status.blocked_tasks:
            lines.append(f"\n## 阻塞任务 ({len(status.blocked_tasks)})\n")
            for t in status.blocked_tasks[:10]:
                lines.append(f"- [{t.workstream}] {t.description[:80]}（Owner: {t.owner}, Due: {t.due_date}）")
        if status.risks:
            lines.append(f"\n## 风险 ({len(status.risks)})\n")
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            for r in status.risks[:10]:
                lines.append(f"{icon.get(r.level, '⚪')} [{r.level.upper()}] {r.description[:80]}")
    return "\n".join(lines)


def format_cross_text(contradictions: List[str], gaps: List[str], duplicates: List[str]) -> str:
    lines = ["[PTA-INTEL] 跨文档关联分析"]
    if contradictions:
        lines.append(f"\n## 矛盾 ({len(contradictions)})\n")
        lines.extend(f"- {c}" for c in contradictions[:10])
    if gaps:
        lines.append(f"\n## 遗漏 ({len(gaps)})\n")
        lines.extend(f"- {g}" for g in gaps[:10])
    if duplicates:
        lines.append(f"\n## 重复 ({len(duplicates)})\n")
        lines.extend(f"- {d}" for d in duplicates[:10])
    if not contradictions and not gaps and not duplicates:
        lines.append("\n未发现问题。")
    return "\n".join(lines)
