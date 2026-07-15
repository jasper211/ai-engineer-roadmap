#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：规则扫描（原 PTA-SCAN_智能项目扫描器_v2.py 迁移）

跟 skills/daily_sensing.py 的关系（两者刻意保持独立，互补而非重叠）：
  - daily_sensing 是 LLM 语义分析——看不出结构的叙述性变化，靠模型理解"这个
    变化是什么意思"。
  - rule_based_task_scan 是零成本、确定性的规则抽取——只处理已经结构化的
    产物（markdown 执行清单表格/列表、带列名的 CSV），用正则/关键词匹配抽出
    任务的负责人/截止日期/状态，并做逾期/阻塞/无负责人这类风险预警。不调用
    任何 LLM，不产生 API 成本。

本次迁移的两处修复：
  1. 真正切换到 sha256——旧版用 md5 算文件内容哈希，跟本项目其余地方
     （tools/file_diff.py、tools/task_knowledge.py）不一致；现在改用
     tools.file_diff.snapshot_dir/diff_snapshots，统一到同一套增量 diff 原语。
  2. 删除内部的 --schedule 忙等循环（run_scheduled）——旧版这个模式下会把
     报告文件直接写进 self.project_path（目标项目自己的目录里），违反"不改
     任何项目文件"的原则；而且这个内部 time.sleep() 循环跟本项目已经确立的
     "外部调度器（launchd）驱动单次调用"架构（daily_sensing 走的就是这条路）
     不一致，是重复造轮子。如需定时运行本技能，参照 10_部署与运行/ 下
     daily-scan 的 launchd 模式，不要用内部循环。

以及一处清理：旧版 FILE_PRIORITY/DocumentInfo.priority 字段计算了文件优先级
但从未在扫描/报告/风险预警的任何环节被实际使用，属于死代码，本次迁移时删除。
"""

import csv as csv_module
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from tools.file_diff import snapshot_dir, diff_snapshots, read_content_truncated

# 任务抽取只对这两种已结构化的格式有意义（markdown 表格/清单、CSV 表格）；
# 其余格式即使变了也只做"文件变没变"层面的追踪，不做任务抽取。
DEFAULT_SCAN_EXTENSIONS = {".md", ".csv"}

STATUS_KEYWORDS = {
    "completed": ["完成", "已归档", "已确认", "已冻结", "green", "done", "finished"],
    "in_progress": ["进行中", "推进", "owner_named", "yellow", "in progress", "ongoing"],
    "blocked": ["阻塞", "红灯", "red", "blocked", "等待", "等", "待确认"],
    "pending": ["待开始", "未开始", "pending", "todo", "待办"],
}

OWNER_PATTERNS = [
    r"[负责人|Owner|owner]\s*[:：]\s*([^\n]+)",
    r"[负责|执行]\s*[:：]\s*([^\n]+)",
    r"named_owner\s*[:，]\s*([^\n]+)",
]

DATE_PATTERNS = [
    r"(\d{4}-\d{2}-\d{2})",
    r"(\d{4}年\d{1,2}月\d{1,2}日)",
    r"截止日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})",
    r"due_date\s*[:，]\s*(\d{4}-\d{2}-\d{2})",
]


@dataclass
class TaskInfo:
    task_id: str
    description: str
    owner: str
    due_date: str
    status: str
    source_doc: str
    workstream: str
    gate: str
    validation_rule: str
    is_new: bool = False
    is_changed: bool = False


@dataclass
class RiskAlert:
    level: str  # "high", "medium", "low"
    type: str   # "overdue", "blocked", "no_owner", "no_date"
    task_id: str
    description: str
    suggestion: str


@dataclass
class ScanReport:
    scan_time: str
    project_path: str
    total_files: int
    new_files: int
    changed_files: int
    deleted_files: int
    tasks: List[TaskInfo] = field(default_factory=list)
    risks: List[RiskAlert] = field(default_factory=list)
    summary: str = ""


class RuleBasedScanner:
    """规则扫描：本地 sha256 diff（复用 tools.file_diff）→ 结构化任务抽取 → 风险预警。"""

    def __init__(self, project_root: Path, extensions: Optional[set] = None):
        self.project_root = Path(project_root)
        self.extensions = extensions or DEFAULT_SCAN_EXTENSIONS

    def _extract_tasks_from_markdown(self, file_path: Path) -> List[TaskInfo]:
        tasks = []
        content = read_content_truncated(file_path, max_chars=10_000_000)  # 任务表格需要读全文，不截断
        if not content:
            return tasks
        lines = content.split("\n")

        in_table = False
        table_headers = []
        table_rows = []

        for line in lines:
            if line.startswith("|") and "---" not in line:
                if not in_table:
                    in_table = True
                    table_headers = [h.strip() for h in line.split("|")[1:-1]]
                else:
                    row = [c.strip() for c in line.split("|")[1:-1]]
                    if row and any(row):
                        table_rows.append(row)
            elif in_table and not line.startswith("|"):
                in_table = False
                for row in table_rows:
                    task = self._parse_task_row(row, table_headers, str(file_path))
                    if task:
                        tasks.append(task)
                table_headers = []
                table_rows = []

        for i, line in enumerate(lines):
            if line.startswith("## ") and ("任务" in line or "清单" in line or "执行" in line):
                for j in range(i + 1, min(i + 20, len(lines))):
                    if lines[j].startswith("- ") or lines[j].startswith("* "):
                        task = self._parse_task_line(lines[j], str(file_path))
                        if task:
                            tasks.append(task)

        return tasks

    def _extract_tasks_from_csv(self, file_path: Path) -> List[TaskInfo]:
        tasks = []
        content = read_content_truncated(file_path, max_chars=10_000_000)
        if not content:
            return tasks
        reader = csv_module.DictReader(content.splitlines())
        for row in reader:
            task = self._parse_csv_row(row, str(file_path))
            if task:
                tasks.append(task)
        return tasks

    def _parse_task_row(self, row: List[str], headers: List[str], source: str) -> Optional[TaskInfo]:
        if not row or len(row) < 2:
            return None

        task_id = self._find_column(row, headers, ["work_id", "任务ID", "编号", "ID"])
        description = self._find_column(row, headers, ["action", "任务", "工作项", "描述"])
        owner = self._find_column(row, headers, ["named_owner", "owner", "负责人", "执行人"])
        due_date = self._find_column(row, headers, ["due_date", "截止日期", "完成时间"])
        status = self._find_column(row, headers, ["status", "状态", "进度"])
        workstream = self._find_column(row, headers, ["workstream", "工作流", "领域"])
        gate = self._find_column(row, headers, ["gate", "Gate", "阶段门"])
        validation = self._find_column(row, headers, ["validation_rule", "验收标准", "验证规则"])

        if not description:
            return None

        return TaskInfo(
            task_id=task_id or "", description=description, owner=owner or "",
            due_date=due_date or "", status=self._normalize_status(status),
            source_doc=source, workstream=workstream or "", gate=gate or "",
            validation_rule=validation or "",
        )

    def _parse_csv_row(self, row: dict, source: str) -> Optional[TaskInfo]:
        description = row.get("action") or row.get("任务") or row.get("工作项")
        if not description:
            return None
        return TaskInfo(
            task_id=row.get("work_id", ""), description=description,
            owner=row.get("named_owner", row.get("owner", row.get("负责人", ""))),
            due_date=row.get("due_date", row.get("截止日期", "")),
            status=self._normalize_status(row.get("status", "")),
            source_doc=source, workstream=row.get("workstream", ""),
            gate=row.get("gate", ""), validation_rule=row.get("validation_rule", ""),
        )

    def _parse_task_line(self, line: str, source: str) -> Optional[TaskInfo]:
        content = line.lstrip("- *").strip()
        if not content or len(content) < 10:
            return None

        non_task_keywords = ["参见", "参考", "来源", "链接", "http", "www", ".com", ".pdf", ".xlsx", "图片", "截图"]
        if any(kw in content for kw in non_task_keywords):
            return None

        task_keywords = ["完成", "确认", "归档", "更新", "建立", "产出", "启动", "冻结",
                        "执行", "推进", "落实", "点名", "补齐", "验收", "评审", "审批",
                        "需要", "必须", "应", "需"]
        if not any(kw in content for kw in task_keywords):
            return None

        owner = ""
        for pattern in OWNER_PATTERNS:
            match = re.search(pattern, content)
            if match:
                owner = match.group(1).strip()
                break

        due_date = ""
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, content)
            if match:
                due_date = match.group(1)
                break

        return TaskInfo(
            task_id="", description=content[:100], owner=owner, due_date=due_date,
            status=self._normalize_status(content), source_doc=source,
            workstream="", gate="", validation_rule="",
        )

    def _find_column(self, row: List[str], headers: List[str], possible_names: List[str]) -> str:
        for name in possible_names:
            if name in headers:
                idx = headers.index(name)
                if idx < len(row):
                    return row[idx]
        return ""

    def _normalize_status(self, text: str) -> str:
        text_lower = text.lower()
        for status, keywords in STATUS_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    return status
        return "pending"

    def _identify_risks(self, tasks: List[TaskInfo]) -> List[RiskAlert]:
        risks = []
        today = datetime.now().date()

        for task in tasks:
            if task.due_date:
                try:
                    due = datetime.strptime(task.due_date, "%Y-%m-%d").date()
                    if due < today and task.status != "completed":
                        risks.append(RiskAlert(
                            level="high", type="overdue", task_id=task.task_id,
                            description=f"任务逾期: {task.description[:50]}",
                            suggestion=f"立即跟进负责人 {task.owner}，确认阻塞原因",
                        ))
                    elif due <= today + timedelta(days=2) and task.status != "completed":
                        risks.append(RiskAlert(
                            level="medium", type="overdue", task_id=task.task_id,
                            description=f"任务即将到期: {task.description[:50]}",
                            suggestion=f"提醒负责人 {task.owner} 加快进度",
                        ))
                except ValueError:
                    pass

            if task.status == "blocked":
                risks.append(RiskAlert(
                    level="high", type="blocked", task_id=task.task_id,
                    description=f"任务阻塞: {task.description[:50]}",
                    suggestion="需要上级介入，解除阻塞",
                ))

            if not task.owner:
                risks.append(RiskAlert(
                    level="medium", type="no_owner", task_id=task.task_id,
                    description=f"任务无负责人: {task.description[:50]}",
                    suggestion="立即指定 owner",
                ))

            if not task.due_date and task.status != "completed":
                risks.append(RiskAlert(
                    level="low", type="no_date", task_id=task.task_id,
                    description=f"任务无截止日期: {task.description[:50]}",
                    suggestion="设定截止日期",
                ))

        return risks

    def scan(self, previous_state: dict) -> "tuple[ScanReport, dict]":
        """
        Args:
            previous_state: memory.workspace.load_rule_scan_state() 加载的状态 dict

        Returns:
            (report, updated_state) —— updated_state 交给调用方存回 rule_scan_state.json
        """
        old_hashes = previous_state.get("file_hashes", {})
        old_snapshot_shape = {path: {"hash": h} for path, h in old_hashes.items()}

        current_snapshot = snapshot_dir(self.project_root, extensions=self.extensions)
        diff = diff_snapshots(old_snapshot_shape, current_snapshot)

        old_tasks_by_id = {t.get("task_id", ""): t for t in previous_state.get("tasks", []) if t.get("task_id")}

        all_tasks: List[TaskInfo] = []

        def _extract(rel_path: str) -> List[TaskInfo]:
            file_path = self.project_root / rel_path
            ext = file_path.suffix.lower()
            if ext == ".md":
                return self._extract_tasks_from_markdown(file_path)
            if ext == ".csv":
                return self._extract_tasks_from_csv(file_path)
            return []

        for rel_path in diff.added:
            for task in _extract(rel_path):
                task.is_new = True
                all_tasks.append(task)

        for rel_path in diff.changed:
            for task in _extract(rel_path):
                if task.task_id and task.task_id in old_tasks_by_id:
                    old = old_tasks_by_id[task.task_id]
                    if (old.get("status") != task.status or old.get("owner") != task.owner
                            or old.get("due_date") != task.due_date):
                        task.is_changed = True
                all_tasks.append(task)

        # 保留未变更文件里的旧任务（这些文件本次没有重新解析，任务原样带过来）
        current_task_ids = {t.task_id for t in all_tasks if t.task_id}
        touched_docs = {str(self.project_root / p) for p in (diff.added + diff.changed)}
        for old_task in previous_state.get("tasks", []):
            if old_task.get("task_id") in current_task_ids:
                continue
            if old_task.get("source_doc") in touched_docs:
                continue  # 该文件已重新解析过，不沿用旧记录（避免残留已被删除的任务行）
            carried = dict(old_task)
            carried["is_new"] = False
            carried["is_changed"] = False
            all_tasks.append(TaskInfo(**carried))

        risks = self._identify_risks(all_tasks)

        new_tasks = [t for t in all_tasks if t.is_new]
        changed_tasks = [t for t in all_tasks if t.is_changed]
        summary = (f"文件变化: +{len(diff.added)} 新增, ~{len(diff.changed)} 变更, -{len(diff.removed)} 删除\n"
                  f"任务变化: +{len(new_tasks)} 新增, ~{len(changed_tasks)} 变更\n"
                  f"风险: {len([r for r in risks if r.level == 'high'])} 高, "
                  f"{len([r for r in risks if r.level == 'medium'])} 中, "
                  f"{len([r for r in risks if r.level == 'low'])} 低")

        report = ScanReport(
            scan_time=datetime.now().isoformat(), project_path=str(self.project_root),
            total_files=len(current_snapshot), new_files=len(diff.added),
            changed_files=len(diff.changed), deleted_files=len(diff.removed),
            tasks=all_tasks, risks=risks, summary=summary,
        )

        updated_state = {
            "file_hashes": {path: info["hash"] for path, info in current_snapshot.items()},
            "tasks": [asdict(t) for t in all_tasks],
        }

        return report, updated_state


def format_report_text(report: ScanReport) -> str:
    lines = [f"[PTA-SCAN] 扫描报告 · {report.project_path}", f"扫描时间: {report.scan_time}", report.summary]

    new_tasks = [t for t in report.tasks if t.is_new]
    if new_tasks:
        lines.append(f"\n🆕 新增任务 ({len(new_tasks)}):")
        for t in new_tasks[:10]:
            lines.append(f"  [{t.workstream}] {t.description[:60]}")
            lines.append(f"    Owner: {t.owner}, Due: {t.due_date}, Status: {t.status}")

    changed_tasks = [t for t in report.tasks if t.is_changed]
    if changed_tasks:
        lines.append(f"\n🔄 变更任务 ({len(changed_tasks)}):")
        for t in changed_tasks[:10]:
            lines.append(f"  [{t.workstream}] {t.description[:60]}")
            lines.append(f"    Owner: {t.owner}, Status: {t.status}")

    if report.risks:
        lines.append(f"\n⚠️ 风险预警 ({len(report.risks)}):")
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        for r in report.risks:
            lines.append(f"  {icon.get(r.level, '⚪')} [{r.level.upper()}] {r.type}: {r.description}")
            lines.append(f"     建议: {r.suggestion}")

    return "\n".join(lines)


def format_task_assignment_markdown(report: ScanReport) -> str:
    lines = ["# 任务分配建议\n"]
    by_workstream: Dict[str, List[TaskInfo]] = {}
    for t in report.tasks:
        if t.status != "completed":
            ws = t.workstream or "未分类"
            by_workstream.setdefault(ws, []).append(t)

    icon = {"completed": "✅", "in_progress": "🔄", "blocked": "🔴", "pending": "⏳"}
    for ws, tasks in sorted(by_workstream.items()):
        lines.append(f"\n## {ws}\n")
        for t in tasks:
            lines.append(f"{icon.get(t.status, '❓')} {t.description[:80]}")
            lines.append(f"  - Owner: {t.owner or '待指定'}")
            lines.append(f"  - Due: {t.due_date or '待设定'}")
            lines.append(f"  - Status: {t.status}")
            if t.validation_rule:
                lines.append(f"  - 验收: {t.validation_rule}")
            lines.append("")

    return "\n".join(lines)
