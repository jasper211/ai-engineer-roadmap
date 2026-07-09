#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-INTEL · 智能项目分析器 v3
功能：
  A. 深度文档分析：读取 Markdown 内容，提取项目阶段、待办事项、风险点
  B. 任务智能解析：自然语言查询，返回进度、阻塞、下一步
  C. 跨文档关联：分析多文档关系，找矛盾、遗漏、重复

运行：
  python3 pta_intel_v3.py --project /path/to/project --mode [analyze|query|cross] [--query "问题"]

示例：
  python3 pta_intel_v3.py --project /path/to/Rw --mode analyze
  python3 pta_intel_v3.py --project /path/to/Rw --mode query --query "项目进度如何"
  python3 pta_intel_v3.py --project /path/to/Rw --mode cross
"""

import os
import re
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

# ============================================================
# 数据模型
# ============================================================

@dataclass
class ProjectPhase:
    """项目阶段"""
    name: str
    status: str  # "completed", "in_progress", "blocked", "pending"
    start_date: str
    end_date: str
    deliverables: List[str]
    blockers: List[str]
    owner: str

@dataclass
class TaskItem:
    """任务项"""
    id: str
    description: str
    owner: str
    due_date: str
    status: str
    workstream: str
    priority: str
    evidence_path: str
    is_completed: bool
    is_blocked: bool

@dataclass
class RiskItem:
    """风险项"""
    level: str  # "high", "medium", "low"
    description: str
    owner: str
    mitigation: str
    related_task: str

@dataclass
class DocumentInsight:
    """文档洞察"""
    doc_path: str
    doc_type: str  # "charter", "daily_report", "task_list", "risk_register", "backlog"
    phase: str
    key_points: List[str]
    tasks: List[TaskItem]
    risks: List[RiskItem]
    decisions: List[str]
    next_actions: List[str]

@dataclass
class ProjectStatus:
    """项目状态"""
    project_name: str
    current_phase: str
    overall_progress: float
    phases: List[ProjectPhase]
    active_tasks: List[TaskItem]
    blocked_tasks: List[TaskItem]
    risks: List[RiskItem]
    recent_docs: List[DocumentInsight]
    summary: str

# ============================================================
# 文档解析器
# ============================================================

class DocumentParser:
    """文档解析器：提取结构化信息"""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.content = self._read_content()
        self.lines = self.content.split("\n") if self.content else []
    
    def _read_content(self) -> str:
        """读取文档内容"""
        try:
            return self.file_path.read_text(encoding="utf-8")
        except:
            try:
                return self.file_path.read_text(encoding="gbk")
            except:
                return ""
    
    def _detect_doc_type(self) -> str:
        """检测文档类型"""
        name = self.file_path.name.lower()
        content = self.content.lower()
        
        if "charter" in name or "章程" in name:
            return "charter"
        elif "日报" in name or "daily" in name:
            return "daily_report"
        elif "风险" in name or "risk" in name or "决策" in name:
            return "risk_register"
        elif "backlog" in name or "待办" in name:
            return "backlog"
        elif "台账" in name or "执行" in name or "任务" in name:
            return "task_list"
        elif "验收" in name or "review" in name:
            return "review"
        elif "启动" in name or "启动" in content:
            return "kickoff"
        else:
            return "general"
    
    def _extract_phase(self) -> str:
        """提取项目阶段"""
        patterns = [
            r"Phase\s*(\d+)",
            r"P(\d+)",
            r"阶段\s*[:：]\s*(.+)",
            r"当前阶段\s*[:：]\s*(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, self.content, re.IGNORECASE)
            if match:
                return match.group(1) if match.lastindex == 1 else match.group(1)
        return "unknown"
    
    def _extract_status_indicators(self) -> Dict[str, List[str]]:
        """提取状态指示器"""
        indicators = {
            "completed": [],
            "in_progress": [],
            "blocked": [],
            "pending": [],
        }
        
        # 扫描绿色/完成状态
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
        """从表格提取任务"""
        tasks = []
        
        # 查找表格
        in_table = False
        headers = []
        rows = []
        
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
                    # 解析表格
                    tasks.extend(self._parse_task_table(headers, rows))
                in_table = False
                headers = []
                rows = []
        
        # 处理最后一个表格
        if in_table and rows:
            tasks.extend(self._parse_task_table(headers, rows))
        
        return tasks
    
    def _parse_task_table(self, headers: List[str], rows: List[List[str]]) -> List[TaskItem]:
        """解析任务表格"""
        tasks = []
        
        # 映射列索引
        col_map = {}
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if any(kw in h_lower for kw in ["work_id", "任务id", "编号", "id"]):
                col_map["id"] = i
            elif any(kw in h_lower for kw in ["action", "任务", "工作项", "描述", "事项"]):
                col_map["description"] = i
            elif any(kw in h_lower for kw in ["owner", "负责人", "执行人", "owner"]):
                col_map["owner"] = i
            elif any(kw in h_lower for kw in ["due", "截止", "完成时间", "日期"]):
                col_map["due_date"] = i
            elif any(kw in h_lower for kw in ["status", "状态", "进度"]):
                col_map["status"] = i
            elif any(kw in h_lower for kw in ["workstream", "工作流", "领域", "类别"]):
                col_map["workstream"] = i
            elif any(kw in h_lower for kw in ["priority", "优先级"]):
                col_map["priority"] = i
        
        # 如果没有找到关键列，跳过
        if "description" not in col_map:
            return tasks
        
        for row in rows:
            if len(row) <= col_map["description"]:
                continue
            
            description = row[col_map["description"]].strip()
            if not description or len(description) < 5:
                continue
            
            # 过滤非任务行（表头重复、分隔线等）
            if description.lower() in ["action", "任务", "描述", "---"]:
                continue
            
            task = TaskItem(
                id=row[col_map.get("id", 0)] if "id" in col_map and len(row) > col_map["id"] else "",
                description=description[:200],
                owner=row[col_map.get("owner", 0)] if "owner" in col_map and len(row) > col_map["owner"] else "",
                due_date=row[col_map.get("due_date", 0)] if "due_date" in col_map and len(row) > col_map["due_date"] else "",
                status=self._normalize_status(row[col_map.get("status", 0)] if "status" in col_map and len(row) > col_map["status"] else ""),
                workstream=row[col_map.get("workstream", 0)] if "workstream" in col_map and len(row) > col_map["workstream"] else "",
                priority="",
                evidence_path="",
                is_completed=False,
                is_blocked=False,
            )
            
            # 判断完成状态
            if any(kw in task.status.lower() for kw in ["completed", "done", "finished", "green", "已完成", "已确认"]):
                task.is_completed = True
            
            # 判断阻塞状态
            if any(kw in task.status.lower() for kw in ["blocked", "red", "阻塞", "红灯", "停止"]):
                task.is_blocked = True
            
            tasks.append(task)
        
        return tasks
    
    def _normalize_status(self, status_text: str) -> str:
        """标准化状态"""
        if not status_text:
            return "pending"
        
        text = status_text.lower()
        if any(kw in text for kw in ["completed", "done", "finished", "green", "已完成", "已确认", "已归档"]):
            return "completed"
        elif any(kw in text for kw in ["blocked", "red", "阻塞", "红灯", "停止", "禁止"]):
            return "blocked"
        elif any(kw in text for kw in ["in_progress", "yellow", "进行中", "推进", "等待"]):
            return "in_progress"
        else:
            return "pending"
    
    def _extract_risks(self) -> List[RiskItem]:
        """提取风险"""
        risks = []
        
        # 查找风险部分
        in_risk_section = False
        for line in self.lines:
            if re.search(r"(风险|阻塞|红灯|blocker|risk)", line, re.IGNORECASE) and ("##" in line or "###" in line):
                in_risk_section = True
            elif in_risk_section and line.startswith("## "):
                in_risk_section = False
            
            if in_risk_section and line.startswith("|"):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 2:
                    risk = RiskItem(
                        level="medium",
                        description=cells[0][:200],
                        owner=cells[1] if len(cells) > 1 else "",
                        mitigation=cells[2] if len(cells) > 2 else "",
                        related_task="",
                    )
                    
                    # 判断风险等级
                    if any(kw in risk.description.lower() for kw in ["red", "红灯", "阻塞", "停止", "禁止"]):
                        risk.level = "high"
                    elif any(kw in risk.description.lower() for kw in ["yellow", "黄灯", "等待", "风险"]):
                        risk.level = "medium"
                    
                    risks.append(risk)
        
        return risks
    
    def _extract_decisions(self) -> List[str]:
        """提取决策"""
        decisions = []
        
        for line in self.lines:
            # 查找决策语句
            if re.search(r"(决定|决议|确认|批准|拍板|决策|decision|confirm|approve)", line):
                # 提取列表项或表格行
                content = re.sub(r"^[-*\d\.\s]+", "", line).strip()
                if content and len(content) > 10:
                    decisions.append(content[:200])
        
        return decisions[:20]  # 限制数量
    
    def _extract_next_actions(self) -> List[str]:
        """提取下一步行动"""
        actions = []
        
        # 查找"下一步"、"明日"、"未来"等章节
        in_next_section = False
        for line in self.lines:
            if re.search(r"(下一步|明日|未来|接下来|next|tomorrow|future|action)", line, re.IGNORECASE) and ("##" in line or "###" in line):
                in_next_section = True
            elif in_next_section and line.startswith("## "):
                in_next_section = False
            
            if in_next_section and (line.startswith("-") or line.startswith("*") or re.match(r"^\d+\.", line)):
                content = re.sub(r"^[-*\d\.\s]+", "", line).strip()
                if content and len(content) > 5:
                    actions.append(content[:200])
        
        return actions[:20]
    
    def parse(self) -> DocumentInsight:
        """解析文档"""
        doc_type = self._detect_doc_type()
        phase = self._extract_phase()
        status_indicators = self._extract_status_indicators()
        tasks = self._extract_tasks_from_tables()
        risks = self._extract_risks()
        decisions = self._extract_decisions()
        next_actions = self._extract_next_actions()
        
        # 提取关键要点
        key_points = []
        key_points.extend([f"完成: {s}" for s in status_indicators["completed"][:5]])
        key_points.extend([f"进行中: {s}" for s in status_indicators["in_progress"][:5]])
        key_points.extend([f"阻塞: {s}" for s in status_indicators["blocked"][:5]])
        
        return DocumentInsight(
            doc_path=str(self.file_path),
            doc_type=doc_type,
            phase=phase,
            key_points=key_points,
            tasks=tasks,
            risks=risks,
            decisions=decisions[:10],
            next_actions=next_actions[:10],
        )

# ============================================================
# 项目分析器
# ============================================================

class ProjectAnalyzer:
    """项目分析器：整合多文档分析"""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.documents: List[DocumentInsight] = []
    
    def analyze_all(self) -> ProjectStatus:
        """分析所有文档"""
        print(f"[PTA-INTEL] 分析项目: {self.project_path}")
        
        # 扫描所有 Markdown 和 CSV
        md_files = list(self.project_path.rglob("*.md"))
        csv_files = list(self.project_path.rglob("*.csv"))
        
        print(f"[PTA-INTEL] 发现 {len(md_files)} 个 Markdown, {len(csv_files)} 个 CSV")
        
        # 解析文档（限制数量，避免过载）
        for file_path in sorted(md_files, key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
            try:
                parser = DocumentParser(file_path)
                insight = parser.parse()
                if insight.tasks or insight.risks or insight.key_points:
                    self.documents.append(insight)
            except Exception as e:
                print(f"[警告] 解析失败 {file_path}: {e}")
        
        # 生成项目状态
        return self._generate_project_status()
    
    def _generate_project_status(self) -> ProjectStatus:
        """生成项目状态"""
        # 收集所有任务
        all_tasks = []
        all_risks = []
        all_decisions = []
        all_next_actions = []
        
        for doc in self.documents:
            all_tasks.extend(doc.tasks)
            all_risks.extend(doc.risks)
            all_decisions.extend(doc.decisions)
            all_next_actions.extend(doc.next_actions)
        
        # 计算进度
        completed = sum(1 for t in all_tasks if t.is_completed)
        blocked = sum(1 for t in all_tasks if t.is_blocked)
        total = len(all_tasks)
        progress = (completed / total * 100) if total > 0 else 0
        
        # 识别当前阶段
        current_phase = "unknown"
        for doc in self.documents:
            if doc.doc_type == "daily_report" and doc.phase:
                current_phase = doc.phase
                break
        
        # 生成摘要
        summary = f"""
项目: {self.project_path.name}
分析文档数: {len(self.documents)}
总任务数: {total}
已完成: {completed} ({progress:.1f}%)
阻塞中: {blocked}
风险数: {len(all_risks)}
决策数: {len(all_decisions)}
下一步行动: {len(all_next_actions)}
        """.strip()
        
        return ProjectStatus(
            project_name=self.project_path.name,
            current_phase=current_phase,
            overall_progress=progress,
            phases=[],
            active_tasks=[t for t in all_tasks if not t.is_completed and not t.is_blocked],
            blocked_tasks=[t for t in all_tasks if t.is_blocked],
            risks=all_risks[:20],  # 限制数量
            recent_docs=self.documents[:10],
            summary=summary,
        )
    
    def query(self, question: str) -> str:
        """智能查询"""
        question_lower = question.lower()
        
        # 分析项目（如果还没分析）
        if not self.documents:
            self.analyze_all()
        
        # 收集所有任务和风险
        all_tasks = []
        all_risks = []
        for doc in self.documents:
            all_tasks.extend(doc.tasks)
            all_risks.extend(doc.risks)
        
        # 进度查询
        if any(kw in question_lower for kw in ["进度", "progress", "做到哪", "状态", "status"]):
            return self._answer_progress(all_tasks)
        
        # 阻塞查询
        elif any(kw in question_lower for kw in ["阻塞", "block", "红灯", "red", "问题", "problem"]):
            return self._answer_blockers(all_tasks, all_risks)
        
        # 下一步查询
        elif any(kw in question_lower for kw in ["下一步", "next", "接下来", "明天", "tomorrow", "action"]):
            return self._answer_next_actions()
        
        # 负责人查询
        elif any(kw in question_lower for kw in ["负责人", "owner", "谁负责", "who"]):
            return self._answer_owners(all_tasks)
        
        # 逾期查询
        elif any(kw in question_lower for kw in ["逾期", "overdue", "到期", "due", "delay"]):
            return self._answer_overdue(all_tasks)
        
        # 默认：综合报告
        else:
            return self._answer_summary(all_tasks, all_risks)
    
    def _answer_progress(self, tasks: List[TaskItem]) -> str:
        """回答进度"""
        completed = sum(1 for t in tasks if t.is_completed)
        blocked = sum(1 for t in tasks if t.is_blocked)
        in_progress = sum(1 for t in tasks if not t.is_completed and not t.is_blocked)
        total = len(tasks)
        
        if total == 0:
            return "未找到任务数据。"
        
        progress = completed / total * 100
        
        lines = [
            f"# 项目进度报告\n",
            f"## 总体进度\n",
            f"- 总任务: {total}",
            f"- 已完成: {completed} ({progress:.1f}%)",
            f"- 进行中: {in_progress}",
            f"- 阻塞中: {blocked}",
            f"\n## 按工作流分布\n",
        ]
        
        # 按 workstream 分组
        by_ws = {}
        for t in tasks:
            ws = t.workstream or "未分类"
            if ws not in by_ws:
                by_ws[ws] = {"total": 0, "completed": 0}
            by_ws[ws]["total"] += 1
            if t.is_completed:
                by_ws[ws]["completed"] += 1
        
        for ws, stats in sorted(by_ws.items()):
            pct = stats["completed"] / stats["total"] * 100 if stats["total"] > 0 else 0
            lines.append(f"- {ws}: {stats['completed']}/{stats['total']} ({pct:.0f}%)")
        
        return "\n".join(lines)
    
    def _answer_blockers(self, tasks: List[TaskItem], risks: List[RiskItem]) -> str:
        """回答阻塞"""
        blocked_tasks = [t for t in tasks if t.is_blocked]
        high_risks = [r for r in risks if r.level == "high"]
        
        lines = [f"# 阻塞与风险报告\n"]
        
        if blocked_tasks:
            lines.append(f"## 阻塞任务 ({len(blocked_tasks)})\n")
            for t in blocked_tasks[:10]:
                lines.append(f"- [{t.workstream}] {t.description[:80]}")
                lines.append(f"  Owner: {t.owner}, Due: {t.due_date}")
        
        if high_risks:
            lines.append(f"\n## 高风险 ({len(high_risks)})\n")
            for r in high_risks[:10]:
                lines.append(f"- {r.description[:80]}")
                lines.append(f"  Owner: {r.owner}, Mitigation: {r.mitigation[:60]}")
        
        if not blocked_tasks and not high_risks:
            lines.append("当前无阻塞任务或高风险。")
        
        return "\n".join(lines)
    
    def _answer_next_actions(self) -> str:
        """回答下一步"""
        actions = []
        for doc in self.documents:
            actions.extend(doc.next_actions)
        
        if not actions:
            return "未找到下一步行动。"
        
        lines = [f"# 下一步行动 ({len(actions)})\n"]
        for i, action in enumerate(actions[:15], 1):
            lines.append(f"{i}. {action}")
        
        return "\n".join(lines)
    
    def _answer_owners(self, tasks: List[TaskItem]) -> str:
        """回答负责人"""
        by_owner = {}
        for t in tasks:
            owner = t.owner or "未指定"
            if owner not in by_owner:
                by_owner[owner] = []
            by_owner[owner].append(t)
        
        lines = [f"# 负责人任务分布\n"]
        for owner, owner_tasks in sorted(by_owner.items(), key=lambda x: len(x[1]), reverse=True):
            completed = sum(1 for t in owner_tasks if t.is_completed)
            lines.append(f"\n## {owner} ({len(owner_tasks)} 任务, {completed} 完成)\n")
            for t in owner_tasks[:5]:
                status_icon = "✅" if t.is_completed else "🔄" if not t.is_blocked else "🔴"
                lines.append(f"{status_icon} {t.description[:60]} (Due: {t.due_date})")
        
        return "\n".join(lines)
    
    def _answer_overdue(self, tasks: List[TaskItem]) -> str:
        """回答逾期"""
        today = datetime.now().date()
        overdue = []
        
        for t in tasks:
            if t.due_date and not t.is_completed:
                try:
                    due = datetime.strptime(t.due_date, "%Y-%m-%d").date()
                    if due < today:
                        overdue.append((t, (today - due).days))
                except:
                    pass
        
        if not overdue:
            return "当前无逾期任务。"
        
        lines = [f"# 逾期任务 ({len(overdue)})\n"]
        for t, days in sorted(overdue, key=lambda x: x[1], reverse=True)[:15]:
            lines.append(f"- [{t.workstream}] {t.description[:80]}")
            lines.append(f"  逾期 {days} 天 | Owner: {t.owner} | Due: {t.due_date}")
        
        return "\n".join(lines)
    
    def _answer_summary(self, tasks: List[TaskItem], risks: List[RiskItem]) -> str:
        """回答综合摘要"""
        return self._generate_project_status().summary

# ============================================================
# 跨文档关联分析
# ============================================================

class CrossDocumentAnalyzer:
    """跨文档关联分析器"""
    
    def __init__(self, documents: List[DocumentInsight]):
        self.documents = documents
    
    def find_contradictions(self) -> List[str]:
        """查找矛盾"""
        contradictions = []
        
        # 检查同一任务在不同文档中的状态是否矛盾
        task_status_map = {}
        for doc in self.documents:
            for task in doc.tasks:
                if task.id:
                    if task.id in task_status_map:
                        old_status = task_status_map[task.id]
                        if old_status != task.status:
                            contradictions.append(
                                f"任务 {task.id} 状态矛盾: "
                                f"{old_status} vs {task.status}"
                            )
                    else:
                        task_status_map[task.id] = task.status
        
        return contradictions
    
    def find_gaps(self) -> List[str]:
        """查找遗漏"""
        gaps = []
        
        # 检查是否有任务无负责人
        for doc in self.documents:
            for task in doc.tasks:
                if not task.owner and not task.is_completed:
                    gaps.append(f"[{doc.doc_type}] 任务无负责人: {task.description[:60]}")
        
        # 检查是否有任务无截止日期
        for doc in self.documents:
            for task in doc.tasks:
                if not task.due_date and not task.is_completed:
                    gaps.append(f"[{doc.doc_type}] 任务无截止日期: {task.description[:60]}")
        
        return gaps
    
    def find_duplicates(self) -> List[str]:
        """查找重复"""
        duplicates = []
        
        # 检查任务描述重复
        desc_map = {}
        for doc in self.documents:
            for task in doc.tasks:
                desc = task.description[:50]
                if desc in desc_map:
                    duplicates.append(
                        f"重复任务: {desc[:60]}... "
                        f"({desc_map[desc]} 和 {doc.doc_path})"
                    )
                else:
                    desc_map[desc] = doc.doc_path
        
        return duplicates

# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="PTA-INTEL · 智能项目分析器 v3")
    parser.add_argument("--project", "-p", required=True, help="项目路径")
    parser.add_argument("--mode", "-m", choices=["analyze", "query", "cross"], default="analyze", help="模式")
    parser.add_argument("--query", "-q", help="查询问题（query 模式）")
    parser.add_argument("--output", "-o", help="输出文件路径")
    args = parser.parse_args()
    
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"[错误] 项目路径不存在: {project_path}")
        return 1
    
    analyzer = ProjectAnalyzer(project_path)
    
    if args.mode == "analyze":
        # 深度分析模式
        status = analyzer.analyze_all()
        
        print(f"\n{'='*60}")
        print(f"[PTA-INTEL] 项目分析报告")
        print(f"{'='*60}")
        print(status.summary)
        
        print(f"\n## 活跃任务 ({len(status.active_tasks)})\n")
        for t in status.active_tasks[:10]:
            print(f"- [{t.workstream}] {t.description[:80]}")
            print(f"  Owner: {t.owner}, Due: {t.due_date}")
        
        if status.blocked_tasks:
            print(f"\n## 阻塞任务 ({len(status.blocked_tasks)})\n")
            for t in status.blocked_tasks[:10]:
                print(f"- [{t.workstream}] {t.description[:80]}")
                print(f"  Owner: {t.owner}, Due: {t.due_date}")
        
        if status.risks:
            print(f"\n## 风险 ({len(status.risks)})\n")
            for r in status.risks[:10]:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r.level, "⚪")
                print(f"{icon} [{r.level.upper()}] {r.description[:80]}")
        
        # 保存报告
        if args.output:
            report = analyzer.query("综合报告")
            Path(args.output).write_text(report, encoding="utf-8")
            print(f"\n[PTA-INTEL] 报告已保存: {args.output}")
    
    elif args.mode == "query":
        # 智能查询模式
        if not args.query:
            print("[错误] query 模式需要提供 --query 参数")
            return 1
        
        answer = analyzer.query(args.query)
        print(answer)
        
        if args.output:
            Path(args.output).write_text(answer, encoding="utf-8")
    
    elif args.mode == "cross":
        # 跨文档关联模式
        analyzer.analyze_all()
        cross = CrossDocumentAnalyzer(analyzer.documents)
        
        print(f"\n{'='*60}")
        print(f"[PTA-INTEL] 跨文档关联分析")
        print(f"{'='*60}")
        
        contradictions = cross.find_contradictions()
        if contradictions:
            print(f"\n## 矛盾 ({len(contradictions)})\n")
            for c in contradictions[:10]:
                print(f"- {c}")
        
        gaps = cross.find_gaps()
        if gaps:
            print(f"\n## 遗漏 ({len(gaps)})\n")
            for g in gaps[:10]:
                print(f"- {g}")
        
        duplicates = cross.find_duplicates()
        if duplicates:
            print(f"\n## 重复 ({len(duplicates)})\n")
            for d in duplicates[:10]:
                print(f"- {d}")
        
        if not contradictions and not gaps and not duplicates:
            print("\n未发现问题。")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
