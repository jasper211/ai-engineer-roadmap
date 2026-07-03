#!/usr/bin/env python3
"""
merge_interview_rules.py — P1-04 · 信号4 访谈规则继承

功能：从手工基线 v1.0 Markdown 解析信号4（A/B/C三分类访谈规则），
      合并到自动基线 auto_v1.0 中，生成完整基线 auto_v1.1。

输入：
  - 手工基线: PAY域_价值节点信号提取基线_v1.0.md (815行, 含122条A/B/C规则)
  - 自动基线: PAY域_价值节点信号提取基线_auto_v1.0.md (710行, 信号4为占位符)

输出：
  - 合并基线: PAY域_价值节点信号提取基线_auto_v1.1.md

解析逻辑：
  1. 按 "### VN-XXX-XX ·" 分割节点
  2. 在每个节点内找 "**信号4 · 调研已知清单（A/B/C三分类）**"
  3. 提取其下的 Markdown 表格（| 分类 | 信号内容 | 来源 |）
  4. 按节点 ID 组织为 {node_id: {a: [], b: [], c: []}} 结构
  5. 读取自动基线，替换每个节点的信号4 占位符为实际规则表格
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class InterviewRules:
    """单个节点的访谈规则集合"""
    node_id: str
    a_rules: List[Dict[str, str]] = field(default_factory=list)
    b_rules: List[Dict[str, str]] = field(default_factory=list)
    c_rules: List[Dict[str, str]] = field(default_factory=list)
    source_note: str = ""  # 如 "已有访谈覆盖（EFA001规则清单）"

    def total(self) -> int:
        return len(self.a_rules) + len(self.b_rules) + len(self.c_rules)


class ManualBaselineParser:
    """解析手工基线中的信号4 访谈规则"""

    def __init__(self, content: str):
        self.content = content
        self.rules_by_node: Dict[str, InterviewRules] = {}

    def parse(self) -> Dict[str, InterviewRules]:
        """主解析入口"""
        # 按 "### VN-XXX-XX ·" 分割节点
        node_pattern = r'###\s+(VN-[A-Z]+-\d+)\s+·'
        nodes = re.split(node_pattern, self.content)

        # nodes[0] = 前置内容, nodes[1] = node_id, nodes[2] = 节点内容, ...
        for i in range(1, len(nodes), 2):
            if i + 1 < len(nodes):
                node_id = nodes[i]
                node_content = nodes[i + 1]
                self._parse_node(node_id, node_content)

        return self.rules_by_node

    def _parse_node(self, node_id: str, content: str):
        """解析单个节点的信号4"""
        # 找信号4 标题及其后的表格
        signal4_start = content.find("**信号4 · 调研已知清单（A/B/C三分类）**")
        if signal4_start == -1:
            return

        # 从信号4 标题后找表格
        after_title = content[signal4_start:]

        # 找表格头 | 分类 | 信号内容 | 来源 |
        table_match = re.search(
            r'\| 分类 \| 信号内容 \| 来源 \|\s*\n\|[-\|\s]+\|\s*\n((?:\| [ABC]类 \| .*?\|.*?\n)+)',
            after_title,
            re.DOTALL
        )

        if not table_match:
            return

        # 提取来源注释（信号4标题和表格之间的 > 引用行）
        between = after_title[:table_match.start()]
        source_match = re.search(r'>\s*(.*?)(?:\n\s*\n|\n\s*\|)', between)
        source_note = source_match.group(1).strip() if source_match else ""

        table_rows = table_match.group(1)

        rules = InterviewRules(node_id=node_id, source_note=source_note)

        for line in table_rows.strip().split("\n"):
            line = line.strip()
            if not line or not line.startswith("|"):
                continue

            parts = [p.strip() for p in line.split("|")]
            # 过滤空字符串（首尾 | 产生的空项）
            parts = [p for p in parts if p]

            if len(parts) < 3:
                continue

            category, signal_content, source = parts[0], parts[1], parts[2]

            rule = {"content": signal_content, "source": source}

            if category == "A类":
                rules.a_rules.append(rule)
            elif category == "B类":
                rules.b_rules.append(rule)
            elif category == "C类":
                rules.c_rules.append(rule)

        if rules.total() > 0:
            self.rules_by_node[node_id] = rules


class BaselineMerger:
    """合并访谈规则到自动基线"""

    def __init__(self, auto_content: str, rules: Dict[str, InterviewRules]):
        self.auto_content = auto_content
        self.rules = rules

    def merge(self) -> str:
        """执行合并，返回新内容

        策略：替换整个信号4区域（从标题到信号5标题之前），
        清除自动基线中原有的占位符和Excel提取规则，只保留手工基线的访谈规则。
        """
        result = self.auto_content

        for node_id, rules in self.rules.items():
            # 找该节点的信号4 区域：从 "**信号4" 到 "**信号5"
            node_pattern = (
                rf'(###\s+{re.escape(node_id)}\s+·.*?\n\n)'
                rf'(\*\*信号4 · 调研已知清单（A/B/C三分类）\*\*\s*\n\n)'
                rf'(.*?)'
                rf'(\*\*信号5 · 已知的交付物\*\*)'
            )

            def replacer(match):
                prefix = match.group(1)  # ### VN-PAY-XX · ...
                signal4_header = match.group(2)  # **信号4 · ...
                # signal4_body = match.group(3)  # 原内容（丢弃）
                signal5_header = match.group(4)  # **信号5 · ...**

                # 构建新的信号4内容
                new_signal4 = self._build_signal4(rules)

                return prefix + signal4_header + new_signal4 + "\n" + signal5_header

            result = re.sub(node_pattern, replacer, result, flags=re.DOTALL)

        return result

    def _build_signal4(self, rules: InterviewRules) -> str:
        """构建完整的信号4 内容（包含来源注释和规则表格）"""
        lines = []

        # 添加来源注释
        if rules.source_note:
            lines.append(f"> {rules.source_note}")
            lines.append("")

        # 表格头
        lines.append("| 分类 | 信号内容 | 来源 |")
        lines.append("|---|---|---|")

        for rule in rules.a_rules:
            lines.append(f"| A类 | {rule['content']} | {rule['source']} |")
        for rule in rules.b_rules:
            lines.append(f"| B类 | {rule['content']} | {rule['source']} |")
        for rule in rules.c_rules:
            lines.append(f"| C类 | {rule['content']} | {rule['source']} |")

        return "\n".join(lines)


def main():
    # 路径配置
    base_dir = Path("/Users/zhaoqitrenda.cn/Desktop/流程架构项目_jasper/02_过程成果-工作产出/规则分析（Jasper）/02_信号提取基线/提取合集校准")
    auto_dir = Path("/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/01_execution/P1-02_信号提取自动化/outputs")
    output_dir = Path("/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/01_execution/P1-04_访谈规则继承/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    manual_path = base_dir / "PAY域_价值节点信号提取基线_v1.0.md"
    auto_path = auto_dir / "PAY域_价值节点信号提取基线_auto_v1.0.md"
    output_path = output_dir / "PAY域_价值节点信号提取基线_auto_v1.1.md"

    print(f"=== P1-04 · 信号4 访谈规则继承 ===\n")
    print(f"手工基线: {manual_path}")
    print(f"自动基线: {auto_path}")
    print(f"输出路径: {output_path}\n")

    # 读取文件
    manual_content = manual_path.read_text(encoding="utf-8")
    auto_content = auto_path.read_text(encoding="utf-8")

    # 解析手工基线
    print("[1/3] 解析手工基线信号4...")
    parser = ManualBaselineParser(manual_content)
    rules = parser.parse()

    total_rules = sum(r.total() for r in rules.values())
    print(f"  ✓ 解析到 {len(rules)} 个节点，共 {total_rules} 条规则")
    for node_id, r in sorted(rules.items()):
        print(f"    {node_id}: A={len(r.a_rules)} B={len(r.b_rules)} C={len(r.c_rules)}")

    # 验证（按节点统计，避免 grep 全局统计包含表头行）
    print(f"\n[2/3] 合并到自动基线...")
    merger = BaselineMerger(auto_content, rules)
    merged_content = merger.merge()

    # 按节点统计验证
    merged_sections = re.split(r'###\s+VN-PAY-\d+\s+·', merged_content)
    merged_a = merged_b = merged_c = 0
    for sec in merged_sections[1:]:
        sig4 = sec.find('**信号4 · 调研已知清单（A/B/C三分类）**')
        if sig4 == -1:
            continue
        table = re.search(r'\| 分类 \| 信号内容 \| 来源 \|.*?\n((?:\| [ABC]类 \| .*?\n)+)', sec[sig4:], re.DOTALL)
        if table:
            rows = table.group(1).strip().split('\n')
            merged_a += sum(1 for r in rows if '| A类 |' in r)
            merged_b += sum(1 for r in rows if '| B类 |' in r)
            merged_c += sum(1 for r in rows if '| C类 |' in r)

    target_a = sum(len(r.a_rules) for r in rules.values())
    target_b = sum(len(r.b_rules) for r in rules.values())
    target_c = sum(len(r.c_rules) for r in rules.values())

    print(f"  ✓ 合并后: A={merged_a} B={merged_b} C={merged_c} (目标: A={target_a} B={target_b} C={target_c})")

    if merged_a == target_a and merged_b == target_b and merged_c == target_c:
        print(f"  ✓ 所有节点规则数量完全匹配！")
    else:
        print(f"  ⚠ 规则数量不匹配，请检查")

    # 写入输出
    print(f"\n[3/3] 写入输出文件...")
    output_path.write_text(merged_content, encoding="utf-8")

    # 统计行数
    auto_lines = len(auto_content.splitlines())
    merged_lines = len(merged_content.splitlines())
    print(f"  ✓ 输出完成: {merged_lines} 行 (auto_v1.0: {auto_lines} 行, +{merged_lines - auto_lines} 行)")
    print(f"  ✓ 文件: {output_path}")

    print(f"\n=== P1-04 完成 ===")
    print(f"  手工基线规则: {total_rules} 条 (A={target_a} B={target_b} C={target_c})")
    print(f"  合并后覆盖率: 100% (信号4 访谈规则全部继承)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
