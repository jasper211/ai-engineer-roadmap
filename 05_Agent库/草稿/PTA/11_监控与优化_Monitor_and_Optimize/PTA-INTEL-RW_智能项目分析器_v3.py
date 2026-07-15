#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-INTEL-RW · 智能项目分析器 v3 (Rw 项目专用版)
功能：
  A. 深度文档分析：读取 Rw 项目 CSV 台账，提取项目阶段、待办、风险
  B. 任务智能解析：自然语言查询，返回进度、阻塞、下一步
  C. 跨文档关联：分析多文档关系，找矛盾、遗漏、重复

运行：
  python3 pta_intel_rw.py --project /path/to/Rw --mode [analyze|query|cross] [--query "问题"]

示例：
  python3 pta_intel_rw.py --project /path/to/Rw --mode analyze
  python3 pta_intel_rw.py --project /path/to/Rw --mode query --query "项目进度如何"
  python3 pta_intel_rw.py --project /path/to/Rw --mode query --query "Roy 的任务有哪些"
  python3 pta_intel_rw.py --project /path/to/Rw --mode query --query "有哪些阻塞需要 MARK 介入"
  python3 pta_intel_rw.py --project /path/to/Rw --mode cross
"""

import os
import re
import csv
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
class TrackItem:
    """跟踪项（Rw 项目 CSV 台账格式）"""
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
        return any(kw in self.current_status.lower() for kw in 
                   ["blocked", "red", "阻塞", "停止"]) or bool(self.blocker and self.blocker != "无")
    
    @property
    def is_ready(self) -> bool:
        return any(kw in self.current_status.lower() for kw in 
                   ["ready", "可执行", "待确认"])
    
    @property
    def needs_escalation(self) -> bool:
        return bool(self.escalation) and not self.is_completed


@dataclass
class ProjectStatus:
    """项目状态"""
    project_name: str
    total_tracks: int
    completed: int
    in_progress: int
    blocked: int
    ready: int
    not_started: int
    by_workstream: Dict[str, Dict]
    by_owner: Dict[str, Dict]
    by_priority: Dict[str, int]
    blockers: List[TrackItem]
    escalations: List[TrackItem]
    recent_actions: List[TrackItem]
    summary: str

# ============================================================
# Rw 项目解析器
# ============================================================

class RwProjectParser:
    """Rw 项目专用解析器"""
    
    # Rw 项目关键文件路径
    TRACKING_FILES = [
        "52_Phase0日常执行跟踪台账_v0.2.csv",
        "52_Phase0日常执行跟踪台账_v0.1.csv",
        "49_Phase0执行台账_v0.1.csv",
    ]
    
    CHARTER_FILE = "01_项目章程_Project_Charter.md"
    DAILY_REPORT_PATTERN = "53_Phase0首轮执行日报_*.md"
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.tracks: List[TrackItem] = []
        self.charter_content = ""
        self.daily_reports: List[Path] = []
    
    def _read_csv_with_encoding(self, file_path: Path) -> List[Dict]:
        """尝试多种编码读取 CSV"""
        for encoding in ["utf-8", "utf-8-sig", "gbk", "gb2312", "cp936"]:
            try:
                with open(file_path, "r", encoding=encoding, newline="") as f:
                    return list(csv.DictReader(f))
            except UnicodeDecodeError:
                continue
        return []
    
    def parse_tracking_csv(self) -> List[TrackItem]:
        """解析跟踪台账 CSV"""
        tracks = []
        
        for filename in self.TRACKING_FILES:
            file_path = self.project_path / filename
            if not file_path.exists():
                continue
            
            rows = self._read_csv_with_encoding(file_path)
            print(f"[PTA-INTEL] 读取 {filename}: {len(rows)} 行")
            
            for row in rows:
                track = TrackItem(
                    track_id=row.get("track_id", ""),
                    source_work_id=row.get("source_work_id", ""),
                    workstream=row.get("workstream", ""),
                    priority=row.get("priority", ""),
                    owner=row.get("owner", ""),
                    current_status=row.get("current_status", ""),
                    today_action=row.get("today_action", ""),
                    blocker=row.get("blocker", ""),
                    gate=row.get("gate", ""),
                    next_update=row.get("next_update", ""),
                    output=row.get("output", ""),
                    escalation=row.get("escalation", ""),
                )
                
                # 只保留有效跟踪项
                if track.track_id and track.track_id != "track_id":
                    tracks.append(track)
        
        return tracks
    
    def parse_charter(self) -> str:
        """解析项目章程"""
        charter_path = self.project_path / self.CHARTER_FILE
        if charter_path.exists():
            try:
                return charter_path.read_text(encoding="utf-8")
            except:
                pass
        return ""
    
    def parse_daily_reports(self) -> List[Path]:
        """解析日报"""
        reports = []
        for file_path in self.project_path.glob("53_Phase0*日报*.md"):
            reports.append(file_path)
        return sorted(reports, key=lambda p: p.stat().st_mtime, reverse=True)
    
    def parse_all(self) -> Tuple[List[TrackItem], str, List[Path]]:
        """解析所有数据"""
        self.tracks = self.parse_tracking_csv()
        self.charter_content = self.parse_charter()
        self.daily_reports = self.parse_daily_reports()
        return self.tracks, self.charter_content, self.daily_reports


# ============================================================
# 项目分析器
# ============================================================

class RwProjectAnalyzer:
    """Rw 项目分析器"""
    
    def __init__(self, tracks: List[TrackItem], charter: str, reports: List[Path]):
        self.tracks = tracks
        self.charter = charter
        self.reports = reports
    
    def analyze(self) -> ProjectStatus:
        """分析项目状态"""
        total = len(self.tracks)
        completed = sum(1 for t in self.tracks if t.is_completed)
        blocked = sum(1 for t in self.tracks if t.is_blocked)
        ready = sum(1 for t in self.tracks if t.is_ready)
        not_started = sum(1 for t in self.tracks if not t.is_completed and not t.is_blocked and not t.is_ready)
        in_progress = total - completed - blocked - not_started
        
        # 按工作流分组
        by_workstream = {}
        for t in self.tracks:
            ws = t.workstream or "未分类"
            if ws not in by_workstream:
                by_workstream[ws] = {"total": 0, "completed": 0, "blocked": 0}
            by_workstream[ws]["total"] += 1
            if t.is_completed:
                by_workstream[ws]["completed"] += 1
            elif t.is_blocked:
                by_workstream[ws]["blocked"] += 1
        
        # 按负责人分组
        by_owner = {}
        for t in self.tracks:
            owner = t.owner or "未指定"
            if owner not in by_owner:
                by_owner[owner] = {"total": 0, "completed": 0, "blocked": 0}
            by_owner[owner]["total"] += 1
            if t.is_completed:
                by_owner[owner]["completed"] += 1
            elif t.is_blocked:
                by_owner[owner]["blocked"] += 1
        
        # 按优先级分组
        by_priority = {}
        for t in self.tracks:
            p = t.priority or "未指定"
            by_priority[p] = by_priority.get(p, 0) + 1
        
        # 阻塞项
        blockers = [t for t in self.tracks if t.is_blocked and not t.is_completed]
        
        # 需要升级的事项
        escalations = [t for t in self.tracks if t.needs_escalation]
        
        # 今日动作
        recent_actions = [t for t in self.tracks if t.today_action and not t.is_completed]
        
        # 生成摘要
        progress = (completed / total * 100) if total > 0 else 0
        summary = f"""
Rw 权益项目 Phase 0 状态
总跟踪项: {total}
已完成: {completed} ({progress:.1f}%)
进行中: {in_progress}
就绪待执行: {ready}
阻塞中: {blocked}
未开始: {not_started}
阻塞项: {len(blockers)}
需升级: {len(escalations)}
        """.strip()
        
        return ProjectStatus(
            project_name="RW 权益 Layer B 事业线建设项目",
            total_tracks=total,
            completed=completed,
            in_progress=in_progress,
            blocked=blocked,
            ready=ready,
            not_started=not_started,
            by_workstream=by_workstream,
            by_owner=by_owner,
            by_priority=by_priority,
            blockers=blockers,
            escalations=escalations,
            recent_actions=recent_actions,
            summary=summary,
        )
    
    def query(self, question: str) -> str:
        """智能查询"""
        question_lower = question.lower()
        
        status = self.analyze()
        
        # 进度查询
        if any(kw in question_lower for kw in ["进度", "progress", "状态", "status", "overview", "概览"]):
            return self._answer_progress(status)
        
        # 阻塞查询
        elif any(kw in question_lower for kw in ["阻塞", "block", "红灯", "red", "问题", "problem", "风险", "risk"]):
            return self._answer_blockers(status)
        
        # 下一步查询
        elif any(kw in question_lower for kw in ["下一步", "next", "接下来", "明天", "今天", "today", "action"]):
            return self._answer_next_actions(status)
        
        # 负责人查询
        elif any(kw in question_lower for kw in ["负责人", "owner", "谁负责", "who", "分配", "assignment"]):
            return self._answer_owners(status)
        
        # 特定人查询
        elif any(kw in question_lower for kw in ["roy", "amanda", "mark", "teresa", "carrier", "菲菲"]):
            return self._answer_person(question, status)
        
        # 工作流查询
        elif any(kw in question_lower for kw in ["tob", "toi", "shared", "启动", "合规", "合同"]):
            return self._answer_workstream(question, status)
        
        # 逾期查询
        elif any(kw in question_lower for kw in ["逾期", "overdue", "到期", "due", "delay"]):
            return self._answer_overdue(status)
        
        # Gate 查询
        elif any(kw in question_lower for kw in ["gate", "阶段门", "门槛", "评审"]):
            return self._answer_gates(status)
        
        # 默认：综合报告
        else:
            return self._answer_summary(status)
    
    def _answer_progress(self, status: ProjectStatus) -> str:
        """回答进度"""
        lines = [
            f"# RW 权益项目 Phase 0 进度报告\n",
            f"## 总体进度\n",
            f"- 总跟踪项: {status.total_tracks}",
            f"- 已完成: {status.completed} ({status.completed/status.total_tracks*100:.1f}%)",
            f"- 进行中: {status.in_progress}",
            f"- 就绪待执行: {status.ready}",
            f"- 阻塞中: {status.blocked}",
            f"- 未开始: {status.not_started}",
            f"\n## 按工作流分布\n",
        ]
        
        for ws, stats in sorted(status.by_workstream.items()):
            pct = stats["completed"] / stats["total"] * 100 if stats["total"] > 0 else 0
            blocked_icon = f" ({stats.get('blocked', 0)} 阻塞)" if stats.get("blocked", 0) > 0 else ""
            lines.append(f"- {ws}: {stats['completed']}/{stats['total']} ({pct:.0f}%){blocked_icon}")
        
        lines.append(f"\n## 按优先级分布\n")
        for p, count in sorted(status.by_priority.items()):
            lines.append(f"- {p}: {count} 项")
        
        return "\n".join(lines)
    
    def _answer_blockers(self, status: ProjectStatus) -> str:
        """回答阻塞"""
        lines = [f"# 阻塞与风险报告\n"]
        
        if status.blockers:
            lines.append(f"## 阻塞项 ({len(status.blockers)})\n")
            for t in status.blockers:
                lines.append(f"### [{t.track_id}] {t.workstream}")
                lines.append(f"- 状态: {t.current_status}")
                lines.append(f"- 阻塞: {t.blocker}")
                lines.append(f"- Owner: {t.owner}")
                lines.append(f"- Gate: {t.gate}")
                lines.append(f"- 升级条件: {t.escalation}")
                lines.append("")
        else:
            lines.append("当前无阻塞项。")
        
        if status.escalations:
            lines.append(f"\n## 需升级事项 ({len(status.escalations)})\n")
            for t in status.escalations:
                lines.append(f"- [{t.track_id}] {t.workstream}: {t.escalation}")
        
        return "\n".join(lines)
    
    def _answer_next_actions(self, status: ProjectStatus) -> str:
        """回答下一步"""
        lines = [f"# 下一步行动\n"]
        
        if status.recent_actions:
            lines.append(f"## 今日/近期动作 ({len(status.recent_actions)})\n")
            for t in status.recent_actions[:15]:
                icon = "✅" if t.is_completed else "🔴" if t.is_blocked else "🔄"
                lines.append(f"{icon} [{t.track_id}] {t.workstream}")
                lines.append(f"   {t.today_action[:100]}")
                if t.next_update:
                    lines.append(f"   下次更新: {t.next_update}")
                lines.append("")
        else:
            lines.append("未找到下一步行动。")
        
        return "\n".join(lines)
    
    def _answer_owners(self, status: ProjectStatus) -> str:
        """回答负责人"""
        lines = [f"# 负责人任务分布\n"]
        
        for owner, stats in sorted(status.by_owner.items(), key=lambda x: x[1]["total"], reverse=True):
            if stats["total"] == 0:
                continue
            completed = stats["completed"]
            blocked = stats.get("blocked", 0)
            pct = completed / stats["total"] * 100 if stats["total"] > 0 else 0
            
            lines.append(f"\n## {owner} ({stats['total']} 项, {completed} 完成, {blocked} 阻塞)\n")
            
            # 显示该负责人的任务
            owner_tracks = [t for t in self.tracks if t.owner == owner and not t.is_completed]
            for t in owner_tracks[:5]:
                icon = "🔴" if t.is_blocked else "🔄"
                lines.append(f"{icon} [{t.track_id}] {t.workstream}: {t.today_action[:60]}")
        
        return "\n".join(lines)
    
    def _answer_person(self, question: str, status: ProjectStatus) -> str:
        """回答特定人"""
        # 提取人名
        person = None
        for name in ["roy", "amanda", "mark", "teresa", "carrier", "菲菲"]:
            if name in question.lower():
                person = name
                break
        
        if not person:
            return "未指定人员。"
        
        # 查找该人的任务
        person_tracks = [t for t in self.tracks if person.lower() in t.owner.lower()]
        
        if not person_tracks:
            return f"未找到 {person} 的任务。"
        
        lines = [f"# {person.upper()} 的任务\n"]
        
        completed = [t for t in person_tracks if t.is_completed]
        active = [t for t in person_tracks if not t.is_completed]
        blocked = [t for t in person_tracks if t.is_blocked]
        
        lines.append(f"总计: {len(person_tracks)} | 完成: {len(completed)} | 活跃: {len(active)} | 阻塞: {len(blocked)}\n")
        
        if blocked:
            lines.append(f"## 阻塞中 ({len(blocked)})\n")
            for t in blocked:
                lines.append(f"- [{t.track_id}] {t.workstream}")
                lines.append(f"  阻塞: {t.blocker}")
                lines.append(f"  今日动作: {t.today_action[:80]}")
                lines.append("")
        
        if active:
            lines.append(f"\n## 进行中 ({len(active)})\n")
            for t in active[:10]:
                lines.append(f"- [{t.track_id}] {t.workstream}")
                lines.append(f"  {t.today_action[:80]}")
                lines.append(f"  Gate: {t.gate} | 下次更新: {t.next_update}")
                lines.append("")
        
        return "\n".join(lines)
    
    def _answer_workstream(self, question: str, status: ProjectStatus) -> str:
        """回答工作流"""
        # 提取工作流名称
        ws = None
        for name in ["tob", "toi", "shared", "启动", "合规", "合同", "产品", "数据"]:
            if name in question.lower():
                ws = name
                break
        
        if not ws:
            return "未指定工作流。"
        
        # 查找该工作流的任务
        ws_tracks = [t for t in self.tracks if ws.lower() in t.workstream.lower()]
        
        if not ws_tracks:
            return f"未找到 {ws} 的任务。"
        
        lines = [f"# {ws.upper()} 工作流\n"]
        
        completed = [t for t in ws_tracks if t.is_completed]
        active = [t for t in ws_tracks if not t.is_completed]
        blocked = [t for t in ws_tracks if t.is_blocked]
        
        lines.append(f"总计: {len(ws_tracks)} | 完成: {len(completed)} | 活跃: {len(active)} | 阻塞: {len(blocked)}\n")
        
        for t in ws_tracks:
            icon = "✅" if t.is_completed else "🔴" if t.is_blocked else "🔄"
            lines.append(f"{icon} [{t.track_id}] {t.owner}")
            lines.append(f"   {t.today_action[:80]}")
            if t.blocker and t.blocker != "无":
                lines.append(f"   ⚠️ 阻塞: {t.blocker}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _answer_overdue(self, status: ProjectStatus) -> str:
        """回答逾期"""
        today = datetime.now().date()
        overdue = []
        
        for t in self.tracks:
            if not t.is_completed and t.next_update:
                try:
                    # 尝试解析日期
                    due = datetime.strptime(t.next_update, "%Y-%m-%d").date()
                    if due < today:
                        overdue.append((t, (today - due).days))
                except:
                    pass
        
        if not overdue:
            return "当前无逾期任务。"
        
        lines = [f"# 逾期任务 ({len(overdue)})\n"]
        for t, days in sorted(overdue, key=lambda x: x[1], reverse=True)[:15]:
            lines.append(f"- [{t.track_id}] {t.workstream}")
            lines.append(f"  逾期 {days} 天 | Owner: {t.owner}")
            lines.append(f"  今日动作: {t.today_action[:80]}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _answer_gates(self, status: ProjectStatus) -> str:
        """回答 Gate 状态"""
        # 按 Gate 分组
        by_gate = {}
        for t in self.tracks:
            g = t.gate or "未指定"
            if g not in by_gate:
                by_gate[g] = []
            by_gate[g].append(t)
        
        lines = [f"# Gate 状态\n"]
        
        for gate, tracks in sorted(by_gate.items()):
            completed = sum(1 for t in tracks if t.is_completed)
            blocked = sum(1 for t in tracks if t.is_blocked)
            total = len(tracks)
            
            status_icon = "🟢" if completed == total else "🔴" if blocked > 0 else "🟡"
            lines.append(f"\n## {status_icon} {gate} ({completed}/{total} 完成, {blocked} 阻塞)\n")
            
            for t in tracks:
                icon = "✅" if t.is_completed else "🔴" if t.is_blocked else "🔄"
                lines.append(f"{icon} [{t.track_id}] {t.workstream}: {t.owner}")
        
        return "\n".join(lines)
    
    def _answer_summary(self, status: ProjectStatus) -> str:
        """回答综合摘要"""
        return status.summary


# ============================================================
# 跨文档关联分析
# ============================================================

class CrossDocumentAnalyzer:
    """跨文档关联分析器"""
    
    def __init__(self, tracks: List[TrackItem]):
        self.tracks = tracks
    
    def find_contradictions(self) -> List[str]:
        """查找矛盾"""
        contradictions = []
        
        # 检查同一 source_work_id 的不同 track 状态是否矛盾
        source_map = {}
        for t in self.tracks:
            if t.source_work_id:
                if t.source_work_id in source_map:
                    old = source_map[t.source_work_id]
                    if old.is_completed and not t.is_completed:
                        contradictions.append(
                            f"[{t.source_work_id}] 状态矛盾: "
                            f"{old.track_id} 标记完成，但 {t.track_id} 未完成"
                        )
                else:
                    source_map[t.source_work_id] = t
        
        return contradictions
    
    def find_gaps(self) -> List[str]:
        """查找遗漏"""
        gaps = []
        
        # 检查无 Owner 的活跃任务
        for t in self.tracks:
            if not t.owner and not t.is_completed:
                gaps.append(f"[{t.track_id}] 无负责人: {t.today_action[:60]}")
        
        # 检查有阻塞但无升级条件
        for t in self.tracks:
            if t.is_blocked and not t.escalation:
                gaps.append(f"[{t.track_id}] 有阻塞但无升级条件")
        
        return gaps
    
    def find_duplicates(self) -> List[str]:
        """查找重复"""
        duplicates = []
        
        # 检查 today_action 重复
        action_map = {}
        for t in self.tracks:
            action = t.today_action[:50]
            if action in action_map:
                duplicates.append(
                    f"重复动作: {action[:60]}... "
                    f"({action_map[action]} 和 {t.track_id})"
                )
            else:
                action_map[action] = t.track_id
        
        return duplicates


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="PTA-INTEL-RW · 智能项目分析器 v3")
    parser.add_argument("--project", "-p", required=True, help="项目路径（07_项目立项启动目录）")
    parser.add_argument("--mode", "-m", choices=["analyze", "query", "cross"], default="analyze", help="模式")
    parser.add_argument("--query", "-q", help="查询问题（query 模式）")
    parser.add_argument("--output", "-o", help="输出文件路径")
    args = parser.parse_args()
    
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"[错误] 项目路径不存在: {project_path}")
        return 1
    
    # 解析项目
    parser = RwProjectParser(project_path)
    tracks, charter, reports = parser.parse_all()
    
    if not tracks:
        print("[错误] 未找到跟踪台账数据。请确认路径正确。")
        return 1
    
    print(f"[PTA-INTEL] 解析完成: {len(tracks)} 个跟踪项")
    
    # 分析
    analyzer = RwProjectAnalyzer(tracks, charter, reports)
    
    if args.mode == "analyze":
        # 深度分析模式
        status = analyzer.analyze()
        
        print(f"\n{'='*60}")
        print(f"[PTA-INTEL] 项目分析报告")
        print(f"{'='*60}")
        print(status.summary)
        
        print(f"\n## 阻塞项 ({len(status.blockers)})\n")
        for t in status.blockers[:5]:
            print(f"- [{t.track_id}] {t.workstream}")
            print(f"  阻塞: {t.blocker}")
            print(f"  Owner: {t.owner}")
        
        print(f"\n## 需升级 ({len(status.escalations)})\n")
        for t in status.escalations[:5]:
            print(f"- [{t.track_id}] {t.escalation}")
        
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
        cross = CrossDocumentAnalyzer(tracks)
        
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
