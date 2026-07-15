#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：项目仪表盘（以人为中心）（从 PTA-DASH_项目仪表盘.py 原样迁移）

组合"解析特定格式数据（Rw 项目的 CSV 跟踪台账 + 项目章程 MD）→ 业务规则判断
（健康度/完成率）→ 按人物视角生成叙事报告"，判定为技能而非工具。

刻意保留"写死 Rw 项目文件名"这一现状——这本来就是专门服务 Rw 项目的报告
生成器，不强行泛化成"猜测任意项目的台账格式"（那是 skills/project_intel.py
未来要做的通用版职责，两者不要混在一起）。
"""

import csv
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass


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
            except (UnicodeDecodeError, OSError):
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
                track_id=track_id, workstream=row.get("workstream", ""),
                priority=row.get("priority", ""), owner=row.get("owner", ""),
                status=row.get("current_status", ""), action=row.get("today_action", ""),
                blocker=row.get("blocker", ""), gate=row.get("gate", ""),
                next_update=row.get("next_update", ""),
            ))

        return self.tracks

    def get_project_summary(self) -> ProjectSummary:
        """获取项目摘要（从章程提取）"""
        charter_path = self.project_path / self.CHARTER_FILE

        summary = ProjectSummary(
            name="RW 权益 Layer B 事业线建设项目",
            one_liner="把权益资产做成可定价、可入账、可交付、可分发、可审计的事业线能力",
            current_phase="Phase 0 治理冻结", phase_goal="冻结基线、明确范围、消除开发前置阻塞",
            start_date="2026-07-06", end_date="2026-07-17",
            overall_health="yellow", completion_pct=0.0,
        )

        if charter_path.exists():
            try:
                content = charter_path.read_text(encoding="utf-8")
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if "一句话定义" in line:
                        for j in range(i + 1, min(i + 10, len(lines))):
                            text = lines[j].strip()
                            if text and not text.startswith("#") and len(text) > 20:
                                summary.one_liner = text
                                break
                        break
            except OSError:
                pass

        if self.tracks:
            completed = sum(1 for t in self.tracks
                             if any(kw in t.status.lower() for kw in ["done", "completed", "confirmed"]))
            summary.completion_pct = completed / len(self.tracks) * 100

            blocked = sum(1 for t in self.tracks if t.blocker and t.blocker != "无")
            if blocked > len(self.tracks) * 0.5:
                summary.overall_health = "red"
            elif blocked > 0:
                summary.overall_health = "yellow"
            else:
                summary.overall_health = "green"

        return summary


class DashboardGenerator:
    """仪表盘生成器"""

    def __init__(self, tracks: List[TrackItem], summary: ProjectSummary):
        self.tracks = tracks
        self.summary = summary

    def generate_for_person(self, person: str) -> str:
        """为特定人生成仪表盘（返回渲染好的 Markdown 字符串，不在这里 print/写文件——
        打印或落盘交给调用方决定，跟 skills/daily_sensing.py 的 format_text 分工一致）"""
        lines = [
            "# 📊 RW 权益项目仪表盘", "",
            "## 🎯 项目目标", "", f"{self.summary.one_liner}", "",
            f"**当前阶段**: {self.summary.current_phase} ({self.summary.start_date} ~ {self.summary.end_date})",
            f"**阶段目标**: {self.summary.phase_goal}",
            f"**整体进度**: {self.summary.completion_pct:.0f}%",
            f"**项目健康度**: {self._health_icon(self.summary.overall_health)} {self.summary.overall_health.upper()}",
            "",
        ]

        if person.lower() == "all":
            lines.extend(self._generate_overall_view())
        else:
            lines.extend(self._generate_personal_view(person))

        lines.extend(self._generate_risks())
        lines.extend(self._generate_next_steps())

        return "\n".join(lines)

    def _health_icon(self, health: str) -> str:
        return {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(health, "⚪")

    def _generate_overall_view(self) -> List[str]:
        lines = ["## 📈 整体进展\n", ""]

        by_ws: Dict[str, Dict[str, int]] = {}
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
        my_tracks = [t for t in self.tracks if person.lower() in t.owner.lower()]

        if not my_tracks:
            return [f"## 👤 你的任务\n\n未找到 {person} 的任务。\n"]

        lines = [f"## 👤 {person.upper()} 的任务看板\n", "", f"**总计**: {len(my_tracks)} 项\n"]

        blocked = [t for t in my_tracks if t.blocker and t.blocker != "无"]
        active = [t for t in my_tracks
                  if not any(kw in t.status.lower() for kw in ["done", "completed", "confirmed"])
                  and (not t.blocker or t.blocker == "无")]
        done = [t for t in my_tracks if any(kw in t.status.lower() for kw in ["done", "completed", "confirmed"])]

        if blocked:
            lines.append("### 🔴 阻塞中（需立即处理）\n")
            for t in blocked:
                lines.append(f"- **[{t.track_id}] {t.workstream}**")
                lines.append(f"  - 阻塞: {t.blocker}")
                lines.append(f"  - 今日动作: {t.action[:80]}")
                lines.append(f"  - Gate: {t.gate}")
                lines.append("")

        if active:
            lines.append("### 🟡 进行中\n")
            for t in active:
                lines.append(f"- **[{t.track_id}] {t.workstream}**")
                lines.append(f"  - 今日动作: {t.action[:80]}")
                if t.next_update:
                    lines.append(f"  - 下次更新: {t.next_update}")
                lines.append("")

        if done:
            lines.append("### 🟢 已完成\n")
            for t in done:
                lines.append(f"- ✅ [{t.track_id}] {t.workstream}")
            lines.append("")

        return lines

    def _generate_risks(self) -> List[str]:
        blockers = [t for t in self.tracks if t.blocker and t.blocker != "无"]
        if not blockers:
            return []

        lines = ["## ⚠️ 关键风险\n", ""]
        for t in blockers[:5]:
            lines.append(f"- **[{t.track_id}] {t.workstream}**")
            lines.append(f"  - {t.blocker}")
            lines.append(f"  - Owner: {t.owner}")
            lines.append("")

        return lines

    def _generate_next_steps(self) -> List[str]:
        active = [t for t in self.tracks
                  if not any(kw in t.status.lower() for kw in ["done", "completed", "confirmed"]) and t.action]
        if not active:
            return []

        lines = ["## 🚀 下一步行动\n", ""]
        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        sorted_active = sorted(active, key=lambda t: priority_order.get(t.priority, 3))

        for t in sorted_active[:8]:
            icon = "🔴" if t.blocker and t.blocker != "无" else "🟡"
            lines.append(f"{icon} **[{t.priority}] [{t.track_id}]** {t.action[:80]}")
            lines.append(f"   Owner: {t.owner} | Gate: {t.gate}")
            lines.append("")

        return lines


def generate_for_person(project_root: Path, person: str = "all") -> str:
    """便捷入口：给定项目路径 + 人名，直接返回渲染好的仪表盘 Markdown 字符串。
    没有找到跟踪数据时抛 RuntimeError，由调用方（agent.py）决定如何提示。"""
    parser = RwParser(Path(project_root))
    tracks = parser.parse()
    if not tracks:
        raise RuntimeError(f"未找到跟踪数据: {parser.project_path / RwParser.TRACKING_FILE}")

    summary = parser.get_project_summary()
    dash = DashboardGenerator(tracks, summary)
    return dash.generate_for_person(person)
