#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-S01 · 意图解析器
功能：理解用户自然语言指令，识别任务类型、优先级、约束条件，输出结构化任务包
运行：python3 pta_s01_parser.py "用户指令"
"""

import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

import pta_common

# ============================================================
# 配置区
# ============================================================

# 任务类型关键词映射
TASK_TYPE_PATTERNS = {
    "sequential": ["按顺序", "依次", "一步一步", "先.*再.*然后"],
    "parallel": ["同时", "并行", "一起", "同步"],
    "conditional": ["如果", "取决于", "根据", "视.*而定"],
    "review": ["回顾", "检查", "复盘", "查看"],
    "execute": ["执行", "完成", "推进", "做"],
    "correct": ["修正", "修改", "更新", "调整"],
}

# 优先级关键词映射
PRIORITY_PATTERNS = {
    "P0": ["紧急", "立即", "马上", "必须", "blocking", "阻塞"],
    "P1": ["重要", "优先", "尽快", "应该"],
    "P2": ["次要", "可以", "有空", "稍后"],
    "P3": ["低优先级", "不急", "未来", "考虑"],
}

# 任务 ID 提取模式：泛化为"大写字母前缀 + 1~2 段 -数字/字母"，覆盖不同项目的编号
# 习惯（本项目 P1-01、Rw 项目 TRK-001、VN-PAY-04 等），而不再只认本项目的 P#-## 格式。
TASK_ID_PATTERN = re.compile(r"\b([A-Z]{1,10}(?:-[A-Z0-9]{1,10}){1,2}|Phase\s*\d+)", re.IGNORECASE)

# 约束条件关键词
CONSTRAINT_PATTERNS = {
    "order": ["按顺序", "依次", "先.*后"],
    "no_skip": ["不跳过", "必须完成", "不能跳过"],
    "read_only": ["只读", "不要修改", "不要写入"],
    "verify": ["验证", "确认", "检查"],
    "sync": ["同步", "更新看板", "更新文档"],
}

# ============================================================


@dataclass
class TaskItem:
    """任务项"""
    id: str
    name: str
    status: str = "pending"  # pending / in_progress / completed / blocked
    description: str = ""


@dataclass
class TaskPackage:
    """结构化任务包"""
    task_id: str
    type: str  # sequential / parallel / conditional / review / execute / correct
    priority: str  # P0 / P1 / P2 / P3
    items: List[TaskItem]
    constraints: List[str]
    context: str
    raw_input: str
    confidence: float  # 0.0 ~ 1.0
    needs_clarification: bool
    clarification_questions: List[str]


class IntentParser:
    """意图解析器：将自然语言指令转换为结构化任务包"""

    def __init__(self, task_map: Optional[Dict[str, dict]] = None):
        self.task_counter = 0
        self.task_map = task_map or {}
    
    def _generate_task_id(self) -> str:
        """生成任务 ID"""
        self.task_counter += 1
        now = datetime.now()
        # 含时分秒：每次 CLI 调用都是独立进程，task_counter 从 0 重新计数，
        # 仅按日期区分会导致同一天内所有任务包都叫 T-xxx-001（真实碰撞过）。
        return f"T-{now.strftime('%Y%m%d%H%M%S')}-{self.task_counter:03d}"
    
    def _detect_task_type(self, text: str) -> str:
        """检测任务类型"""
        scores = {task_type: 0 for task_type in TASK_TYPE_PATTERNS}
        
        for task_type, patterns in TASK_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    scores[task_type] += 1
        
        # 默认类型
        best_type = max(scores, key=scores.get)
        if scores[best_type] == 0:
            # 无匹配，根据关键词判断
            if any(kw in text for kw in ["做", "完成", "执行", "推进"]):
                return "execute"
            elif any(kw in text for kw in ["看", "检查", "回顾", "查"]):
                return "review"
            else:
                return "execute"  # 默认
        
        return best_type
    
    def _detect_priority(self, text: str) -> str:
        """检测优先级"""
        scores = {priority: 0 for priority in PRIORITY_PATTERNS}
        
        for priority, patterns in PRIORITY_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in text.lower():
                    scores[priority] += 1
        
        best_priority = max(scores, key=scores.get)
        if scores[best_priority] == 0:
            return "P1"  # 默认 P1
        
        return best_priority
    
    def _extract_task_items(self, text: str) -> List[TaskItem]:
        """提取任务项列表"""
        items = []
        
        # 模式1: "按顺序完成 A, B, C" 或 "完成 A, B 和 C"
        list_patterns = [
            r"(?:按顺序|依次|完成|执行|推进)\s+([A-Z0-9\-]+(?:\s*[,，、]\s*[A-Z0-9\-]+)+)",
            r"(?:做|处理|搞)\s+([A-Z0-9\-]+(?:\s*[,，、]\s*[A-Z0-9\-]+)+)",
        ]
        
        for pattern in list_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                task_str = match.group(1)
                # 分割任务 ID
                task_ids = re.split(r"[,，、]\s*", task_str)
                for tid in task_ids:
                    tid = tid.strip()
                    if tid:
                        # 尝试获取任务名称（从已知任务映射中）
                        name = self._get_task_name(tid)
                        items.append(TaskItem(id=tid, name=name))
                break
        
        # 模式2: 单独的任务 ID
        if not items:
            matches = TASK_ID_PATTERN.findall(text)
            for tid in matches:
                tid = tid.upper()
                name = self._get_task_name(tid)
                items.append(TaskItem(id=tid, name=name))
        
        # 模式3: 如果没有提取到任务 ID，尝试提取动作 + 对象
        if not items:
            # 提取动词 + 名词短语
            action_pattern = r"(?:帮我|请|需要|要)\s*(.+?)(?:[。，；]|$)"
            match = re.search(action_pattern, text)
            if match:
                action = match.group(1).strip()
                items.append(TaskItem(
                    id="GENERAL",
                    name=action,
                    description=action
                ))
        
        return items
    
    def _get_task_name(self, task_id: str) -> str:
        """从任务 ID 获取任务名称（从项目任务知识库中，见 pta_common.load_task_map）"""
        entry = self.task_map.get(task_id.upper())
        if entry and entry.get("name"):
            return entry["name"]
        return f"任务 {task_id}"
    
    def _extract_constraints(self, text: str) -> List[str]:
        """提取约束条件"""
        constraints = []
        
        for constraint_type, patterns in CONSTRAINT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    constraints.append(constraint_type)
                    break
        
        return list(set(constraints))  # 去重
    
    def _extract_context(self, text: str) -> str:
        """提取上下文信息"""
        # 提取 "在...中"、"基于..."、"根据..." 等上下文
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
        """计算解析置信度"""
        score = 0.0
        
        # 有任务项 +0.3
        if items:
            score += 0.3
        
        # 任务项有已知 ID +0.2
        if any(item.id != "GENERAL" for item in items):
            score += 0.2
        
        # 有明确类型 +0.2
        if self._detect_task_type(text) != "execute":
            score += 0.2
        
        # 有明确优先级 +0.2
        if self._detect_priority(text) != "P1":
            score += 0.2
        
        # 有约束条件 +0.1
        if self._extract_constraints(text):
            score += 0.1
        
        return min(score, 1.0)
    
    def _check_needs_clarification(self, text: str, items: List[TaskItem]) -> Tuple[bool, List[str]]:
        """检查是否需要澄清"""
        questions = []
        
        # 无任务项
        if not items:
            questions.append("请指定具体任务编号（如 P1-01, P2-02）或任务名称")
        
        # 有 GENERAL 任务
        if any(item.id == "GENERAL" for item in items):
            questions.append("任务描述较模糊，能否提供更具体的任务 ID 或范围？")
        
        # 指令过于简短
        if len(text) < 10:
            questions.append("指令较简短，能否提供更多上下文？")
        
        # 包含模糊词汇
        vague_words = ["等等", "之类", "什么的", "随便"]
        if any(word in text for word in vague_words):
            questions.append("指令中包含模糊词汇，能否明确具体范围？")
        
        return len(questions) > 0, questions
    
    def parse(self, text: str) -> TaskPackage:
        """
        解析用户指令，输出结构化任务包
        
        Args:
            text: 用户自然语言指令
        
        Returns:
            TaskPackage: 结构化任务包
        """
        # 提取各项信息
        task_type = self._detect_task_type(text)
        priority = self._detect_priority(text)
        items = self._extract_task_items(text)
        constraints = self._extract_constraints(text)
        context = self._extract_context(text)
        confidence = self._calculate_confidence(text, items)
        needs_clarification, questions = self._check_needs_clarification(text, items)
        
        return TaskPackage(
            task_id=self._generate_task_id(),
            type=task_type,
            priority=priority,
            items=items,
            constraints=constraints,
            context=context,
            raw_input=text,
            confidence=confidence,
            needs_clarification=needs_clarification,
            clarification_questions=questions,
        )
    
    def to_json(self, package: TaskPackage) -> str:
        """将任务包转换为 JSON 字符串"""
        data = asdict(package)
        # 转换 TaskItem 列表
        data["items"] = [asdict(item) for item in package.items]
        return json.dumps(data, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="PTA-S01 · 意图解析器")
    parser.add_argument("input", help="用户自然语言指令")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径（可选）")
    parser.add_argument("--project-root", help="目标项目根目录（用于查找该项目的 pta_tasks.json）")
    parser.add_argument("--task-map", help="显式指定任务知识库 JSON 文件路径（优先级最高）")
    args = parser.parse_args()

    task_map = pta_common.load_task_map(
        args.task_map,
        Path(args.project_root) if args.project_root else None,
        Path(__file__).resolve().parent,
    )

    intent_parser = IntentParser(task_map=task_map)
    package = intent_parser.parse(args.input)
    
    # 输出结果
    print(f"\n{'='*60}")
    print(f"[PTA-S01] 意图解析结果")
    print(f"{'='*60}")
    print(f"任务 ID: {package.task_id}")
    print(f"任务类型: {package.type}")
    print(f"优先级: {package.priority}")
    print(f"置信度: {package.confidence:.1%}")
    print(f"需要澄清: {'是' if package.needs_clarification else '否'}")
    
    if package.needs_clarification:
        print(f"\n澄清问题:")
        for q in package.clarification_questions:
            print(f"  - {q}")
    
    print(f"\n任务项 ({len(package.items)} 个):")
    for item in package.items:
        print(f"  - {item.id}: {item.name}")
    
    if package.constraints:
        print(f"\n约束条件: {', '.join(package.constraints)}")
    
    if package.context:
        print(f"上下文: {package.context}")
    
    print(f"\n{'='*60}")
    
    # 输出 JSON
    json_output = intent_parser.to_json(package)
    print(f"\nJSON 输出:")
    print(json_output)
    
    # 保存到文件
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json_output, encoding="utf-8")
        print(f"\n已保存到: {output_path}")


if __name__ == "__main__":
    main()
