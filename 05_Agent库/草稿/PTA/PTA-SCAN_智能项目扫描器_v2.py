#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-SCAN · 智能项目扫描器 v2
功能：
  1. 定时扫描项目目录，识别新增/变更文档
  2. 从文档内容提取任务、负责人、截止日期、状态
  3. 对比历史快照，生成增量报告
  4. 识别风险（逾期、阻塞、遗漏）
  5. 生成任务分配建议

运行：
  python3 pta_scan_v2.py --project /path/to/project --snapshot /path/to/snapshot.json
  python3 pta_scan_v2.py --project /path/to/project --snapshot /path/to/snapshot.json --schedule 12  # 每12小时运行

使用场景：
  - 每12小时自动扫描 Rw 权益项目
  - 识别新增文档和任务变更
  - 生成任务分配和进度追踪报告
"""

import os
import re
import json
import time
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict

# ============================================================
# 配置区
# ============================================================

# 文件类型权重（用于优先级排序）
FILE_PRIORITY = {
    ".md": 10,      # Markdown 文档最高优先级
    ".csv": 9,      # CSV 数据表
    ".xlsx": 8,     # Excel
    ".docx": 7,     # Word
    ".pdf": 6,      # PDF
    ".json": 5,     # JSON 配置
}

# 任务状态关键词映射
STATUS_KEYWORDS = {
    "completed": ["完成", "已归档", "已确认", "已冻结", "green", "done", "finished"],
    "in_progress": ["进行中", "推进", "owner_named", "yellow", "in progress", "ongoing"],
    "blocked": ["阻塞", "红灯", "red", "blocked", "等待", "等", "待确认"],
    "pending": ["待开始", "未开始", "pending", "todo", "待办"],
}

# 负责人提取模式
OWNER_PATTERNS = [
    r"[负责人|Owner|owner]\s*[:：]\s*([^\n]+)",
    r"[负责|执行]\s*[:：]\s*([^\n]+)",
    r"named_owner\s*[:，]\s*([^\n]+)",
]

# 日期提取模式
DATE_PATTERNS = [
    r"(\d{4}-\d{2}-\d{2})",  # 2026-07-06
    r"(\d{4}年\d{1,2}月\d{1,2}日)",  # 2026年7月6日
    r"截止日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})",
    r"due_date\s*[:，]\s*(\d{4}-\d{2}-\d{2})",
]

# ============================================================


@dataclass
class DocumentInfo:
    """文档信息"""
    path: str
    name: str
    size: int
    modified_time: str
    content_hash: str
    file_type: str
    priority: int


@dataclass
class TaskInfo:
    """任务信息"""
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
    """风险预警"""
    level: str  # "high", "medium", "low"
    type: str   # "overdue", "blocked", "no_owner", "no_date", "conflict"
    task_id: str
    description: str
    suggestion: str


@dataclass
class ScanReport:
    """扫描报告"""
    scan_time: str
    project_path: str
    total_files: int
    new_files: int
    changed_files: int
    deleted_files: int
    tasks: List[TaskInfo]
    risks: List[RiskAlert]
    summary: str


class ProjectScanner:
    """项目扫描器：增量检测 + 任务提取 + 风险识别"""
    
    def __init__(self, project_path: Path, snapshot_path: Optional[Path] = None):
        self.project_path = project_path
        self.snapshot_path = snapshot_path or project_path / ".pta_snapshot.json"
        self.snapshot = self._load_snapshot()
    
    def _load_snapshot(self) -> Dict:
        """加载历史快照"""
        if self.snapshot_path.exists():
            return json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        return {"files": {}, "scan_time": None, "tasks": []}
    
    def _save_snapshot(self, files: Dict, tasks: List[Dict]):
        """保存快照"""
        snapshot = {
            "scan_time": datetime.now().isoformat(),
            "files": files,
            "tasks": tasks,
        }
        self.snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def _compute_hash(self, file_path: Path) -> str:
        """计算文件内容哈希"""
        try:
            content = file_path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except:
            return ""
    
    def _get_file_priority(self, file_path: Path) -> int:
        """获取文件优先级"""
        ext = file_path.suffix.lower()
        return FILE_PRIORITY.get(ext, 1)
    
    def _scan_files(self) -> Dict[str, DocumentInfo]:
        """扫描所有文件"""
        files = {}
        for file_path in self.project_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                stat = file_path.stat()
                doc = DocumentInfo(
                    path=str(file_path.relative_to(self.project_path)),
                    name=file_path.name,
                    size=stat.st_size,
                    modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    content_hash=self._compute_hash(file_path),
                    file_type=file_path.suffix.lower(),
                    priority=self._get_file_priority(file_path),
                )
                files[doc.path] = doc
        return files
    
    def _detect_changes(self, current_files: Dict[str, DocumentInfo]) -> Tuple[List, List, List]:
        """检测变更：新增、修改、删除"""
        old_files = self.snapshot.get("files", {})
        
        new_files = []
        changed_files = []
        deleted_files = []
        
        # 新增和修改
        for path, doc in current_files.items():
            if path not in old_files:
                new_files.append(doc)
            elif old_files[path].get("content_hash") != doc.content_hash:
                changed_files.append(doc)
        
        # 删除
        for path in old_files:
            if path not in current_files:
                deleted_files.append(path)
        
        return new_files, changed_files, deleted_files
    
    def _extract_tasks_from_markdown(self, file_path: Path) -> List[TaskInfo]:
        """从 Markdown 提取任务"""
        tasks = []
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            
            # 提取表格中的任务（如执行清单）
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
                    # 解析表格
                    for row in table_rows:
                        task = self._parse_task_row(row, table_headers, str(file_path))
                        if task:
                            tasks.append(task)
                    table_headers = []
                    table_rows = []
            
            # 提取标题中的任务
            for i, line in enumerate(lines):
                if line.startswith("## ") and ("任务" in line or "清单" in line or "执行" in line):
                    # 提取后续列表项作为任务
                    for j in range(i+1, min(i+20, len(lines))):
                        if lines[j].startswith("- ") or lines[j].startswith("* "):
                            task = self._parse_task_line(lines[j], str(file_path))
                            if task:
                                tasks.append(task)
        
        except Exception as e:
            print(f"[警告] 读取文件失败 {file_path}: {e}")
        
        return tasks
    
    def _extract_tasks_from_csv(self, file_path: Path) -> List[TaskInfo]:
        """从 CSV 提取任务"""
        tasks = []
        try:
            import csv
            # 尝试多种编码
            for encoding in ["utf-8", "gbk", "gb2312", "utf-8-sig"]:
                try:
                    with open(file_path, "r", encoding=encoding) as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            task = self._parse_csv_row(row, str(file_path))
                            if task:
                                tasks.append(task)
                    break
                except UnicodeDecodeError:
                    continue
        except Exception as e:
            print(f"[警告] 读取 CSV 失败 {file_path}: {e}")
        return tasks
    
    def _parse_task_row(self, row: List[str], headers: List[str], source: str) -> Optional[TaskInfo]:
        """解析表格行"""
        if not row or len(row) < 2:
            return None
        
        # 尝试匹配常见列名
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
            task_id=task_id or "",
            description=description,
            owner=owner or "",
            due_date=due_date or "",
            status=self._normalize_status(status),
            source_doc=source,
            workstream=workstream or "",
            gate=gate or "",
            validation_rule=validation or "",
        )
    
    def _parse_csv_row(self, row: Dict, source: str) -> Optional[TaskInfo]:
        """解析 CSV 行"""
        description = row.get("action") or row.get("任务") or row.get("工作项")
        if not description:
            return None
        
        return TaskInfo(
            task_id=row.get("work_id", ""),
            description=description,
            owner=row.get("named_owner", row.get("owner", row.get("负责人", ""))),
            due_date=row.get("due_date", row.get("截止日期", "")),
            status=self._normalize_status(row.get("status", "")),
            source_doc=source,
            workstream=row.get("workstream", ""),
            gate=row.get("gate", ""),
            validation_rule=row.get("validation_rule", ""),
        )
    
    def _parse_task_line(self, line: str, source: str) -> Optional[TaskInfo]:
        """解析列表项任务"""
        content = line.lstrip("- *").strip()
        if not content or len(content) < 10:
            return None
        
        # 过滤非任务内容（太短的、纯说明的）
        non_task_keywords = ["参见", "参考", "来源", "链接", "http", "www", ".com", ".pdf", ".xlsx", "图片", "截图"]
        if any(kw in content for kw in non_task_keywords):
            return None
        
        # 只提取包含任务关键词的列表项
        task_keywords = ["完成", "确认", "归档", "更新", "建立", "产出", "启动", "冻结",
                        "执行", "推进", "落实", "点名", "补齐", "验收", "评审", "审批",
                        "需要", "必须", "应", "需"]
        if not any(kw in content for kw in task_keywords):
            return None
        
        # 提取负责人
        owner = ""
        for pattern in OWNER_PATTERNS:
            match = re.search(pattern, content)
            if match:
                owner = match.group(1).strip()
                break
        
        # 提取日期
        due_date = ""
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, content)
            if match:
                due_date = match.group(1)
                break
        
        # 提取状态
        status = self._normalize_status(content)
        
        return TaskInfo(
            task_id="",
            description=content[:100],
            owner=owner,
            due_date=due_date,
            status=status,
            source_doc=source,
            workstream="",
            gate="",
            validation_rule="",
        )
    
    def _find_column(self, row: List[str], headers: List[str], possible_names: List[str]) -> str:
        """查找匹配列"""
        for name in possible_names:
            if name in headers:
                idx = headers.index(name)
                if idx < len(row):
                    return row[idx]
        return ""
    
    def _normalize_status(self, text: str) -> str:
        """标准化状态"""
        text_lower = text.lower()
        for status, keywords in STATUS_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    return status
        return "pending"
    
    def _identify_risks(self, tasks: List[TaskInfo]) -> List[RiskAlert]:
        """识别风险"""
        risks = []
        today = datetime.now().date()
        
        for task in tasks:
            # 逾期风险
            if task.due_date:
                try:
                    due = datetime.strptime(task.due_date, "%Y-%m-%d").date()
                    if due < today and task.status != "completed":
                        risks.append(RiskAlert(
                            level="high",
                            type="overdue",
                            task_id=task.task_id,
                            description=f"任务逾期: {task.description[:50]}",
                            suggestion=f"立即跟进负责人 {task.owner}，确认阻塞原因",
                        ))
                    elif due <= today + timedelta(days=2) and task.status != "completed":
                        risks.append(RiskAlert(
                            level="medium",
                            type="overdue",
                            task_id=task.task_id,
                            description=f"任务即将到期: {task.description[:50]}",
                            suggestion=f"提醒负责人 {task.owner} 加快进度",
                        ))
                except:
                    pass
            
            # 阻塞风险
            if task.status == "blocked":
                risks.append(RiskAlert(
                    level="high",
                    type="blocked",
                    task_id=task.task_id,
                    description=f"任务阻塞: {task.description[:50]}",
                    suggestion=f"需要 MARK 或上级介入，解除阻塞",
                ))
            
            # 无负责人
            if not task.owner:
                risks.append(RiskAlert(
                    level="medium",
                    type="no_owner",
                    task_id=task.task_id,
                    description=f"任务无负责人: {task.description[:50]}",
                    suggestion="立即指定 owner",
                ))
            
            # 无截止日期
            if not task.due_date and task.status != "completed":
                risks.append(RiskAlert(
                    level="low",
                    type="no_date",
                    task_id=task.task_id,
                    description=f"任务无截止日期: {task.description[:50]}",
                    suggestion="设定截止日期",
                ))
        
        return risks
    
    def scan(self) -> ScanReport:
        """
        执行完整扫描
        
        Returns:
            ScanReport: 扫描报告
        """
        print(f"[PTA-SCAN] 开始扫描项目: {self.project_path}")
        print(f"[PTA-SCAN] 历史快照: {self.snapshot_path}")
        
        # 1. 扫描文件
        current_files = self._scan_files()
        print(f"[PTA-SCAN] 发现 {len(current_files)} 个文件")
        
        # 2. 检测变更
        new_files, changed_files, deleted_files = self._detect_changes(current_files)
        print(f"[PTA-SCAN] 新增: {len(new_files)}, 变更: {len(changed_files)}, 删除: {len(deleted_files)}")
        
        # 3. 提取任务（只处理新增和变更的文件）
        all_tasks = []
        
        # 从历史快照加载旧任务
        old_tasks = {t.get("task_id", ""): t for t in self.snapshot.get("tasks", [])}
        
        # 处理新增文件
        for doc in new_files:
            file_path = self.project_path / doc.path
            if doc.file_type == ".md":
                tasks = self._extract_tasks_from_markdown(file_path)
            elif doc.file_type == ".csv":
                tasks = self._extract_tasks_from_csv(file_path)
            else:
                continue
            
            for task in tasks:
                task.is_new = True
                all_tasks.append(task)
        
        # 处理变更文件
        for doc in changed_files:
            file_path = self.project_path / doc.path
            if doc.file_type == ".md":
                tasks = self._extract_tasks_from_markdown(file_path)
            elif doc.file_type == ".csv":
                tasks = self._extract_tasks_from_csv(file_path)
            else:
                continue
            
            for task in tasks:
                if task.task_id in old_tasks:
                    old = old_tasks[task.task_id]
                    if (old.get("status") != task.status or 
                        old.get("owner") != task.owner or
                        old.get("due_date") != task.due_date):
                        task.is_changed = True
                all_tasks.append(task)
        
        # 保留未变更的旧任务
        current_task_ids = {t.task_id for t in all_tasks}
        for old_task in self.snapshot.get("tasks", []):
            if old_task.get("task_id") not in current_task_ids:
                all_tasks.append(TaskInfo(**old_task))
        
        # 4. 识别风险
        risks = self._identify_risks(all_tasks)
        print(f"[PTA-SCAN] 识别 {len(risks)} 个风险")
        
        # 5. 生成摘要
        new_tasks = [t for t in all_tasks if t.is_new]
        changed_tasks = [t for t in all_tasks if t.is_changed]
        
        summary = f"""
扫描时间: {datetime.now().isoformat()}
项目: {self.project_path}
文件变化: +{len(new_files)} 新增, ~{len(changed_files)} 变更, -{len(deleted_files)} 删除
任务变化: +{len(new_tasks)} 新增, ~{len(changed_tasks)} 变更
风险: {len([r for r in risks if r.level == 'high'])} 高, {len([r for r in risks if r.level == 'medium'])} 中, {len([r for r in risks if r.level == 'low'])} 低
        """.strip()
        
        # 6. 保存快照
        self._save_snapshot(
            {path: asdict(doc) for path, doc in current_files.items()},
            [asdict(t) for t in all_tasks]
        )
        
        return ScanReport(
            scan_time=datetime.now().isoformat(),
            project_path=str(self.project_path),
            total_files=len(current_files),
            new_files=len(new_files),
            changed_files=len(changed_files),
            deleted_files=len(deleted_files),
            tasks=all_tasks,
            risks=risks,
            summary=summary,
        )
    
    def print_report(self, report: ScanReport):
        """打印报告"""
        print(f"\n{'='*60}")
        print(f"[PTA-SCAN] 扫描报告")
        print(f"{'='*60}")
        print(report.summary)
        
        if report.new_files > 0 or report.changed_files > 0:
            print(f"\n📁 文件变更:")
            print(f"  新增: {report.new_files}")
            print(f"  变更: {report.changed_files}")
            print(f"  删除: {report.deleted_files}")
        
        new_tasks = [t for t in report.tasks if t.is_new]
        if new_tasks:
            print(f"\n🆕 新增任务 ({len(new_tasks)}):")
            for t in new_tasks[:10]:
                print(f"  [{t.workstream}] {t.description[:60]}...")
                print(f"    Owner: {t.owner}, Due: {t.due_date}, Status: {t.status}")
        
        changed_tasks = [t for t in report.tasks if t.is_changed]
        if changed_tasks:
            print(f"\n🔄 变更任务 ({len(changed_tasks)}):")
            for t in changed_tasks[:10]:
                print(f"  [{t.workstream}] {t.description[:60]}...")
                print(f"    Owner: {t.owner}, Status: {t.status}")
        
        if report.risks:
            print(f"\n⚠️ 风险预警 ({len(report.risks)}):")
            for r in report.risks:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r.level, "⚪")
                print(f"  {icon} [{r.level.upper()}] {r.type}: {r.description}")
                print(f"     建议: {r.suggestion}")
        
        print(f"\n{'='*60}")
    
    def generate_task_assignment(self, report: ScanReport) -> str:
        """生成任务分配建议"""
        lines = ["# 任务分配建议\n"]
        
        # 按 workstream 分组
        by_workstream = {}
        for t in report.tasks:
            if t.status != "completed":
                ws = t.workstream or "未分类"
                if ws not in by_workstream:
                    by_workstream[ws] = []
                by_workstream[ws].append(t)
        
        for ws, tasks in sorted(by_workstream.items()):
            lines.append(f"\n## {ws}\n")
            for t in tasks:
                icon = {"completed": "✅", "in_progress": "🔄", "blocked": "🔴", "pending": "⏳"}.get(t.status, "❓")
                lines.append(f"{icon} {t.description[:80]}")
                lines.append(f"  - Owner: {t.owner or '待指定'}")
                lines.append(f"  - Due: {t.due_date or '待设定'}")
                lines.append(f"  - Status: {t.status}")
                if t.validation_rule:
                    lines.append(f"  - 验收: {t.validation_rule}")
                lines.append("")
        
        return "\n".join(lines)
    
    def run_scheduled(self, interval_hours: int):
        """定时运行模式"""
        print(f"[PTA-SCAN] 启动定时扫描，间隔: {interval_hours} 小时")
        print(f"[PTA-SCAN] 按 Ctrl+C 停止\n")
        
        try:
            while True:
                report = self.scan()
                self.print_report(report)
                
                # 保存报告
                report_path = self.project_path / f".pta_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
                report_path.write_text(self.generate_task_assignment(report), encoding="utf-8")
                print(f"[PTA-SCAN] 报告已保存: {report_path}")
                
                # 等待下次扫描
                next_scan = datetime.now() + timedelta(hours=interval_hours)
                print(f"[PTA-SCAN] 下次扫描: {next_scan.strftime('%Y-%m-%d %H:%M')}")
                time.sleep(interval_hours * 3600)
        
        except KeyboardInterrupt:
            print(f"\n[PTA-SCAN] 定时扫描已停止")


def main():
    parser = argparse.ArgumentParser(description="PTA-SCAN · 智能项目扫描器 v2")
    parser.add_argument("--project", "-p", required=True, help="项目路径")
    parser.add_argument("--snapshot", "-s", help="快照文件路径（默认: .pta_snapshot.json）")
    parser.add_argument("--output", "-o", help="输出报告路径")
    parser.add_argument("--schedule", "-i", type=int, help="定时扫描间隔（小时）")
    args = parser.parse_args()
    
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"[错误] 项目路径不存在: {project_path}")
        return 1
    
    snapshot_path = Path(args.snapshot) if args.snapshot else None
    scanner = ProjectScanner(project_path, snapshot_path)
    
    if args.schedule:
        scanner.run_scheduled(args.schedule)
    else:
        report = scanner.scan()
        scanner.print_report(report)
        
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(scanner.generate_task_assignment(report), encoding="utf-8")
            print(f"[PTA-SCAN] 任务分配报告已保存: {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

