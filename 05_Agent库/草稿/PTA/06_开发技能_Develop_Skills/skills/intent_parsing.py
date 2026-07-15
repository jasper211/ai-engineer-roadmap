#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：意图解析（原 PTA-S01_意图解析器.py 的 IntentParser 类原样迁移，逻辑不变）
功能：理解用户自然语言指令，识别任务类型、优先级、约束条件，输出结构化任务包
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

TASK_TYPE_PATTERNS = {
    "sequential": ["按顺序", "依次", "一步一步", "先.*再.*然后"],
    "parallel": ["同时", "并行", "一起", "同步"],
    "conditional": ["如果", "取决于", "根据", "视.*而定"],
    "review": ["回顾", "检查", "复盘", "查看"],
    "execute": ["执行", "完成", "推进", "做"],
    "correct": ["修正", "修改", "更新", "调整"],
}

PRIORITY_PATTERNS = {
    "P0": ["紧急", "立即", "马上", "必须", "blocking", "阻塞"],
    "P1": ["重要", "优先", "尽快", "应该"],
    "P2": ["次要", "可以", "有空", "稍后"],
    "P3": ["低优先级", "不急", "未来", "考虑"],
}

# 任务 ID 提取模式：泛化为"大写字母前缀 + 1~2 段 -数字/字母"，覆盖不同项目的编号习惯
TASK_ID_PATTERN = re.compile(r"\b([A-Z]{1,10}(?:-[A-Z0-9]{1,10}){1,2}|Phase\s*\d+)", re.IGNORECASE)

CONSTRAINT_PATTERNS = {
    "order": ["按顺序", "依次", "先.*后"],
    "no_skip": ["不跳过", "必须完成", "不能跳过"],
    "read_only": ["只读", "不要修改", "不要写入"],
    "verify": ["验证", "确认", "检查"],
    "sync": ["同步", "更新看板", "更新文档"],
}


@dataclass
class TaskItem:
    id: str
    name: str
    status: str = "pending"
    description: str = ""


@dataclass
class TaskPackage:
    task_id: str
    type: str
    priority: str
    items: List[TaskItem]
    constraints: List[str]
    context: str
    raw_input: str
    confidence: float
    needs_clarification: bool
    clarification_questions: List[str]


class IntentParser:
    """意图解析器：将自然语言指令转换为结构化任务包"""

    def __init__(self, task_map: Optional[Dict[str, dict]] = None):
        self.task_counter = 0
        self.task_map = task_map or {}

    def _generate_task_id(self) -> str:
        self.task_counter += 1
        now = datetime.now()
        return f"T-{now.strftime('%Y%m%d%H%M%S')}-{self.task_counter:03d}"

    def _detect_task_type(self, text: str) -> str:
        scores = {task_type: 0 for task_type in TASK_TYPE_PATTERNS}
        for task_type, patterns in TASK_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    scores[task_type] += 1
        best_type = max(scores, key=scores.get)
        if scores[best_type] == 0:
            if any(kw in text for kw in ["做", "完成", "执行", "推进"]):
                return "execute"
            elif any(kw in text for kw in ["看", "检查", "回顾", "查"]):
                return "review"
            return "execute"
        return best_type

    def _detect_priority(self, text: str) -> str:
        scores = {priority: 0 for priority in PRIORITY_PATTERNS}
        for priority, patterns in PRIORITY_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in text.lower():
                    scores[priority] += 1
        best_priority = max(scores, key=scores.get)
        return best_priority if scores[best_priority] > 0 else "P1"

    def _extract_task_items(self, text: str) -> List[TaskItem]:
        items = []
        list_patterns = [
            r"(?:按顺序|依次|完成|执行|推进)\s+([A-Z0-9\-]+(?:\s*[,，、]\s*[A-Z0-9\-]+)+)",
            r"(?:做|处理|搞)\s+([A-Z0-9\-]+(?:\s*[,，、]\s*[A-Z0-9\-]+)+)",
        ]
        for pattern in list_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                task_ids = re.split(r"[,，、]\s*", match.group(1))
                for tid in task_ids:
                    tid = tid.strip()
                    if tid:
                        items.append(TaskItem(id=tid, name=self._get_task_name(tid)))
                break
        if not items:
            matches = TASK_ID_PATTERN.findall(text)
            for tid in matches:
                tid = tid.upper()
                items.append(TaskItem(id=tid, name=self._get_task_name(tid)))
        if not items:
            action_pattern = r"(?:帮我|请|需要|要)\s*(.+?)(?:[。，；]|$)"
            match = re.search(action_pattern, text)
            if match:
                action = match.group(1).strip()
                items.append(TaskItem(id="GENERAL", name=action, description=action))
        return items

    def _get_task_name(self, task_id: str) -> str:
        entry = self.task_map.get(task_id.upper())
        if entry and entry.get("name"):
            return entry["name"]
        return f"任务 {task_id}"

    def _extract_constraints(self, text: str) -> List[str]:
        constraints = []
        for constraint_type, patterns in CONSTRAINT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    constraints.append(constraint_type)
                    break
        return list(set(constraints))

    def _extract_context(self, text: str) -> str:
        context_patterns = [
            r"(?:在|基于|根据|按照)\s+(.+?)(?:[，。；]|$)",
            r"(?:为了|目的是|目标是)\s+(.+?)(?:[，。；]|$)",
        ]
        for pattern in context_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _calculate_confidence(self, text: str, items: List[TaskItem]) -> float:
        score = 0.0
        if items:
            score += 0.3
        if any(item.id != "GENERAL" for item in items):
            score += 0.2
        if self._detect_task_type(text) != "execute":
            score += 0.2
        if self._detect_priority(text) != "P1":
            score += 0.2
        if self._extract_constraints(text):
            score += 0.1
        return min(score, 1.0)

    def _check_needs_clarification(self, text: str, items: List[TaskItem]) -> Tuple[bool, List[str]]:
        questions = []
        if not items:
            questions.append("请指定具体任务编号（如 P1-01, P2-02）或任务名称")
        if any(item.id == "GENERAL" for item in items):
            questions.append("任务描述较模糊，能否提供更具体的任务 ID 或范围？")
        if len(text) < 10:
            questions.append("指令较简短，能否提供更多上下文？")
        vague_words = ["等等", "之类", "什么的", "随便"]
        if any(word in text for word in vague_words):
            questions.append("指令中包含模糊词汇，能否明确具体范围？")
        return len(questions) > 0, questions

    def parse(self, text: str) -> TaskPackage:
        task_type = self._detect_task_type(text)
        priority = self._detect_priority(text)
        items = self._extract_task_items(text)
        constraints = self._extract_constraints(text)
        context = self._extract_context(text)
        confidence = self._calculate_confidence(text, items)
        needs_clarification, questions = self._check_needs_clarification(text, items)
        return TaskPackage(
            task_id=self._generate_task_id(), type=task_type, priority=priority,
            items=items, constraints=constraints, context=context, raw_input=text,
            confidence=confidence, needs_clarification=needs_clarification,
            clarification_questions=questions,
        )

    def to_dict(self, package: TaskPackage) -> dict:
        data = asdict(package)
        data["items"] = [asdict(item) for item in package.items]
        return data
