#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-DASH · 项目仪表盘（以人为中心）
功能：
  1. 项目摘要：一句话目标、当前阶段、关键里程碑
  2. 个人看板：我的任务、优先级、截止日期、阻塞
  3. 健康度仪表盘：红黄绿灯、关键风险、下一步

运行：
  python3 pta_dash.py --project /path/to/project --person "Roy" [--output report.md]

示例：
  python3 pta_dash.py --project /path/to/Rw --person "Roy"
  python3 pta_dash.py --project /path/to/Rw --person "MARK"
  python3 pta_dash.py --project /path/to/Rw --person "all"  # 项目整体视图
"""

import csv
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

# ============================================================
# 数据模型
# ============================================================

@dataclass
class TrackItem:
    track_id: str
    workstream: str
    priority: str
    owner: str
    status: str
    action: str
    blocker: str
    gate: str
    next_update: str

@dataclass
class ProjectSummary:
    name: str
    one_liner: str
    current_phase: str
    phase_goal: str
    start_date: str
    end_date: str
    overall_health: str  # "green", "yellow", "red"
    completion_pct: float

# ============================================================
# 解析器
# ============================================================

class RwParser:
    """Rw 项目解析器"""
    
    TRACKING_FILE = "52_Phase0日常执行跟踪台账_v0.2.csv"
    CHARTER_FILE = "01_项目章程_Project_Charter.md"
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.tracks: List[TrackItem] = []
    
    def _read_csv(self, file_path: Path) -> List[Dict]:
        for encoding in ["utf-8-sig", "utf-8", "gbk", "gb2312"]:
            try:
                with open(file_path, "r", encoding=encoding, newline="") as f:
                    return list(csv.DictReader(f))
            except:
                continue
        return []
    
    def parse(self) -> List[TrackItem]:
        file_path = self.project_path / self.TRACKING_FILE
        if not file_path.exists():
            return []
        
        rows = self._read_csv(file_path)
        for row in rows:
            track_id = row.get("track_id", "")
            if not track_id or track_id == "track_id":
                continue
            
            self.tracks.append(TrackItem(
                track_id=track_id,
                workstream=row.get("workstream", ""),
                priority=row.get("priority", ""),
                owner=row.get("owner", ""),
                status=row.get("current_status", ""),
                action=row.get("today_action", ""),
                blocker=row.get("blocker", ""),
                gate=row.get("gate", ""),
                next_update=row.get("next_update", ""),
            ))
        
        return self.tracks
    
    def get_project_summary(self) -> ProjectSummary:
        """获取项目摘要（从章程提取）"""
        charter_path = self.project_path / self.CHARTER_FILE
        
        # 默认值
        summary = ProjectSummary(
            name="RW 权益 Layer B 事业线建设项目",
            one_liner="把权益资产做成可定价、可入账、可交付、可分发、可审计的事业线能力",
            current_phase="Phase 0 治理冻结",
            phase_goal="冻结基线、明确范围、消除开发前置阻塞",
            start_date="2026-07-06",
            end_date="2026-07-17",
            overall_health="yellow",
            completion_pct=0.0,
        )
        
        # 尝试从章程读取
        if charter_path.exists():
            try:
                content = charter_path.read_text(encoding="utf-8")
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if "一句话定义" in line:
                        # 查找后续非空行
                        for j in range(i+1, min(i+10, len(lines))):
                            text = lines[j].strip()
                            if text and not text.startswith("#") and len(text) > 20:
                                summary.one_liner = text
                                break
                        break
            except:
                pass
        
        # 计算完成率
        if self.tracks:
            completed = sum(1 for t in self.tracks 
                          if any(kw in t.status.lower() for kw in ["done", "completed", "confirmed"]))
            summary.completion_pct = completed / len(self.tracks) * 100
            
            # 判断健康度
            blocked = sum(1 for t in self.tracks if t.blocker and t.blocker != "无")
            if blocked > len(self.tracks) * 0.5:
                summary.overall_health = "red"
            elif blocked > 0:
                summary.overall_health = "yellow"
            else:
                summary.overall_health = "green"
        
        return summary

# ============================================================
# 仪表盘生成器
# ============================================================

class DashboardGenerator:
    """仪表盘生成器"""
    
    def __init__(self, tracks: List[TrackItem], summary: ProjectSummary):
        self.tracks = tracks
        self.summary = summary
    
    def generate_for_person(self, person: str) -> str:
        """为特定人生成仪表盘"""
        
        # 1. 项目摘要（所有人都能看到）
        lines = [
            f"# 📊 RW 权益项目仪表盘",
            f"",
            f"## 🎯 项目目标",
            f"",
            f"{self.summary.one_liner}",
            f"",
            f"**当前阶段**: {self.summary.current_phase} ({self.summary.start_date} ~ {self.summary.end_date})",
            f"**阶段目标**: {self.summary.phase_goal}",
            f"**整体进度**: {self.summary.completion_pct:.0f}%",
            f"**项目健康度**: {self._health_icon(self.summary.overall_health)} {self.summary.overall_health.upper()}",
            f"",
        ]
        
        # 2. 如果是 "all"，显示整体视图
        if person.lower() == "all":
            lines.extend(self._generate_overall_view())
        else:
            # 3. 个人任务看板
            lines.extend(self._generate_personal_view(person))
        
        # 4. 关键风险（所有人都能看到）
        lines.extend(self._generate_risks())
        
        # 5. 下一步（所有人都能看到）
        lines.extend(self._generate_next_steps())
        
        return "\n".join(lines)
    
    def _health_icon(self, health: str) -> str:
        return {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(health, "⚪")
    
    def _generate_overall_view(self) -> List[str]:
        """生成整体视图"""
        lines = [
            f"## 📈 整体进展\n",
            f"",
        ]
        
        # 按工作流分组
        by_ws = {}
        for t in self.tracks:
            ws = t.workstream or "未分类"
            if ws not in by_ws:
                by_ws[ws] = {"total": 0, "done": 0, "blocked": 0}
            by_ws[ws]["total"] += 1
            if any(kw in t.status.lower() for kw in ["done", "completed", "confirmed"]):
                by_ws[ws]["done"] += 1
            elif t.blocker and t.blocker != "无":
                by_ws[ws]["blocked"] += 1
        
        for ws, stats in sorted(by_ws.items()):
            pct = stats["done"] / stats["total"] * 100 if stats["total"] > 0 else 0
            icon = "🔴" if stats["blocked"] > 0 else "🟢" if pct == 100 else "🟡"
            lines.append(f"{icon} **{ws}**: {stats['done']}/{stats['total']} ({pct:.0f}%)")
            if stats["blocked"] > 0:
                lines.append(f"   ⚠️ {stats['blocked']} 个阻塞项")
        
        lines.append("")
        return lines
    
    def _generate_personal_view(self, person: str) -> List[str]:
        """生成个人视图"""
        # 查找该人的任务
        my_tracks = [t for t in self.tracks if person.lower() in t.owner.lower()]
        
        if not my_tracks:
            return [f"## 👤 你的任务\n\n未找到 {person} 的任务。\n"]
        
        lines = [
            f"## 👤 {person.upper()} 的任务看板\n",
            f"",
            f"**总计**: {len(my_tracks)} 项\n",
        ]
        
        # 分类
        blocked = [t for t in my_tracks if t.blocker and t.blocker != "无"]
        active = [t for t in my_tracks if not any(kw in t.status.lower() for kw in ["done", "completed", "confirmed"]) and (not t.blocker or t.blocker == "无")]
        done = [t for t in my_tracks if any(kw in t.status.lower() for kw in ["done", "completed", "confirmed"])]
        
        # 阻塞任务（最紧急）
        if blocked:
            lines.append(f"### 🔴 阻塞中（需立即处理）\n")
            for t in blocked:
                lines.append(f"- **[{t.track_id}] {t.workstream}**")
                lines.append(f"  - 阻塞: {t.blocker}")
                lines.append(f"  - 今日动作: {t.action[:80]}")
                lines.append(f"  - Gate: {t.gate}")
                lines.append("")
        
        # 进行中任务
        if active:
            lines.append(f"### 🟡 进行中\n")
            for t in active:
                lines.append(f"- **[{t.track_id}] {t.workstream}**")
                lines.append(f"  - 今日动作: {t.action[:80]}")
                if t.next_update:
                    lines.append(f"  - 下次更新: {t.next_update}")
                lines.append("")
        
        # 已完成
        if done:
            lines.append(f"### 🟢 已完成\n")
            for t in done:
                lines.append(f"- ✅ [{t.track_id}] {t.workstream}")
            lines.append("")
        
        return lines
    
    def _generate_risks(self) -> List[str]:
        """生成关键风险"""
        # 提取所有阻塞项
        blockers = [t for t in self.tracks if t.blocker and t.blocker != "无"]
        
        if not blockers:
            return []
        
        lines = [
            f"## ⚠️ 关键风险\n",
            f"",
        ]
        
        # 只显示前 5 个最关键
        for t in blockers[:5]:
            lines.append(f"- **[{t.track_id}] {t.workstream}**")
            lines.append(f"  - {t.blocker}")
            lines.append(f"  - Owner: {t.owner}")
            lines.append("")
        
        return lines
    
    def _generate_next_steps(self) -> List[str]:
        """生成下一步"""
        # 提取所有未完成的今日动作
        active = [t for t in self.tracks 
                 if not any(kw in t.status.lower() for kw in ["done", "completed", "confirmed"])
                 and t.action]
        
        if not active:
            return []
        
        lines = [
            f"## 🚀 下一步行动\n",
            f"",
        ]
        
        # 按优先级排序
        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        sorted_active = sorted(active, key=lambda t: priority_order.get(t.priority, 3))
        
        for t in sorted_active[:8]:
            icon = "🔴" if t.blocker and t.blocker != "无" else "🟡"
            lines.append(f"{icon} **[{t.priority}] [{t.track_id}]** {t.action[:80]}")
            lines.append(f"   Owner: {t.owner} | Gate: {t.gate}")
            lines.append("")
        
        return lines

# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="PTA-DASH · 项目仪表盘")
    parser.add_argument("--project", "-p", required=True, help="项目路径")
    parser.add_argument("--person", "-u", default="all", help="人员名称（默认 all）")
    parser.add_argument("--output", "-o", help="输出文件路径")
    args = parser.parse_args()
    
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"[错误] 路径不存在: {project_path}")
        return 1
    
    # 解析
    rw_parser = RwParser(project_path)
    tracks = rw_parser.parse()
    summary = rw_parser.get_project_summary()
    
    if not tracks:
        print("[错误] 未找到跟踪数据")
        return 1
    
    # 生成仪表盘
    dash = DashboardGenerator(tracks, summary)
    report = dash.generate_for_person(args.person)
    
    # 输出
    print(report)
    
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\n[PTA-DASH] 报告已保存: {args.output}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
