#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：文档任务发现（原 PTA-DISCOVER_文档任务发现器.py 迁移）

调用 DeepSeek API 阅读外部项目的自由行文文档（合同/会议纪要/审计报告等），
提取其中隐含的任务（谁、做什么、状态、截止时间），产出一份"任务发现报告"。

跟 skills/daily_sensing.py 的关系（两者都是"本地 diff + LLM 分析"，但目的
不同，刻意保持独立，不合并）：
  - daily_sensing 做的是"最近变化之间有什么关系、该通知四方里的谁"，一次
    合并 LLM 调用覆盖当天所有变化，产出直接进 pta_tasks.json 的可执行确认流程。
  - document_task_discovery 做的是"这份文档里藏着哪些任务"，每个文件单独
    一次 LLM 调用（文档之间往往互不相关，合并分析没有意义），产出只是供人工
    分类审阅的发现记录，进 memory.workspace 的 task_registry.json，不会
    自动进 pta_tasks.json 的可执行流程。

⚠️ 安全边界（刻意设计，不是遗漏，原样保留）：
  本技能的输出只是"发现报告"（任务名/负责人/状态/来源文件），供人工审阅。
  它绝不会自动写入 pta_tasks.json 的 steps/command 字段——那些字段驱动真实
  shell/python 执行，如果任由模型从任意文档中抽取的内容直接进执行步骤，
  等于把"文档里写了什么"变成"命令行会跑什么"，是一个命令注入面。要不要把
  某个发现的任务变成可执行步骤，永远是人工决定。

增量扫描：按内容哈希跟"上一次本技能自己的处理记录"比对（memory.workspace 的
discover_state.json，跟 daily_sensing_state.json 物理隔离——两者"已处理"的
判断语义不同，共用一份文件会互相污染），只处理新增/变更过的文件。
"""

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tools.file_diff import snapshot_dir, hash_file, read_content_truncated
from tools.llm_client import call_deepseek, DEFAULT_MODEL
from tools.ob_bridge import get_background

SKILLS_DIR = Path(__file__).resolve().parent
PTA_DIR = SKILLS_DIR.parent.parent
DEFAULT_SYSTEM_PROMPT_PATH = PTA_DIR / "08_设计提示词_Design_Prompts" / "prompts" / "document_task_discovery_system.md"

# 叙述性文档常见格式：纯文本 + Office。跟 daily_sensing 的扫描范围不同——
# 这里不包含 .py/.json/.yaml 这类结构化配置/代码，那些不是"藏着任务的叙述性
# 文档"，硬塞进来只会浪费 API 调用。
DEFAULT_SCAN_EXTENSIONS = {".md", ".txt", ".csv", ".docx", ".xlsx"}
SCAN_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".pta_runs", ".venv", "venv",
                     ".idea", ".vscode", ".pytest_cache"}

MAX_CHARS_PER_FILE = 6000


@dataclass
class DiscoveredTask:
    name: str
    owner: str = "unknown"
    status: str = "unknown"
    due_date: Optional[str] = None
    evidence: str = ""
    confidence: float = 0.0
    source_file: str = ""


@dataclass
class DiscoveryReport:
    generated_at: str
    project_root: str
    model: str
    files_scanned: int
    files_with_tasks: int = 0
    tasks: List[dict] = field(default_factory=list)
    errors: List[dict] = field(default_factory=list)
    duplicates_skipped: List[dict] = field(default_factory=list)
    incremental_skipped: int = 0
    dry_run_preview: List[dict] = field(default_factory=list)


def _dedupe_by_content(files: List[Path]) -> "tuple[List[Path], List[dict]]":
    """按文件内容的 sha256 去重：同一份内容在项目里存在多份拷贝（比如按不同
    维度重新归类整理出来的视图文件夹）时，只保留第一份，避免对着相同内容
    反复调用模型。file_diff.snapshot_dir 是按路径建索引，天然不做这种跨路径
    的内容去重，所以这一步仍然需要独立实现，保留在本技能里。"""
    seen: Dict[str, Path] = {}
    unique: List[Path] = []
    dropped: List[dict] = []
    for f in files:
        digest = hash_file(f)
        if digest is None:
            unique.append(f)  # 读不了就留着，交给后面的读取逻辑报错
            continue
        if digest in seen:
            dropped.append({"file": str(f), "duplicate_of": str(seen[digest])})
        else:
            seen[digest] = f
            unique.append(f)
    return unique, dropped


class DocumentDiscoverer:
    """文档任务发现：本地增量 diff → 逐文件 LLM 语义抽取 → 发现报告。"""

    def __init__(self, project_root: Path, api_key: Optional[str] = None,
                 model: str = DEFAULT_MODEL, extensions: Optional[set] = None,
                 system_prompt_path: Path = DEFAULT_SYSTEM_PROMPT_PATH,
                 max_chars_per_file: int = MAX_CHARS_PER_FILE,
                 use_ob_context: bool = False):
        self.project_root = Path(project_root)
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.model = model
        self.extensions = extensions or DEFAULT_SCAN_EXTENSIONS
        self.system_prompt_path = system_prompt_path
        self.max_chars_per_file = max_chars_per_file
        # 试点接入 OB 背景检索（PTA↔OB 接口设计里"背景记忆层缺口"的第一个真实
        # 落地）——选这个技能试点，是因为它读的是叙述性文档（合同/会议纪要），
        # 单文件孤立分析，最容易把历史记录/已过时内容误判成新任务；有没有
        # 项目背景，对这类噪音的影响最直接。默认关闭：这是新接口，先小范围验证
        # 有没有实际改善判断质量，不默认打开增加每次调用的延迟和OB侧负载。
        self.use_ob_context = use_ob_context

    def _load_system_prompt(self) -> str:
        if not self.system_prompt_path.exists():
            raise RuntimeError(f"找不到系统提示词文件: {self.system_prompt_path}")
        return self.system_prompt_path.read_text(encoding="utf-8")

    def discover(self, previous_state: dict, explicit_files: Optional[List[str]] = None,
                 scan: bool = False, force: bool = False,
                 dry_run: bool = False) -> "tuple[DiscoveryReport, dict]":
        """
        Args:
            previous_state: memory.workspace.load_discover_state() 加载的状态 dict
            explicit_files: 显式指定候选文件（相对或绝对路径），总是处理，不受增量状态影响
            scan: 自动扫描项目内所有候选文档，按增量状态过滤
            force: 忽略增量状态，--scan 找到的文件全部重新处理
            dry_run: 只列出候选文件和估算大小，不调用 API，也不更新增量状态

        Returns:
            (report, updated_state) —— updated_state 交给调用方存回 discover_state.json
        """
        old_hashes = {} if force else previous_state.get("file_hashes", {})

        explicit_paths = [Path(f).resolve() for f in (explicit_files or [])]

        scanned_paths: List[Path] = []
        incremental_skipped = 0
        if scan:
            current_snapshot = snapshot_dir(self.project_root, extensions=self.extensions,
                                              exclude_dirs=SCAN_EXCLUDE_DIRS)
            for rel, info in current_snapshot.items():
                if not force and old_hashes.get(rel) == info["hash"]:
                    incremental_skipped += 1
                    continue
                scanned_paths.append(self.project_root / rel)

        files = sorted(set(explicit_paths + scanned_paths))
        files, dupes = _dedupe_by_content(files)

        report = DiscoveryReport(
            generated_at=datetime.now().isoformat(), project_root=str(self.project_root),
            model=self.model, files_scanned=len(files), duplicates_skipped=dupes,
            incremental_skipped=incremental_skipped,
        )

        if dry_run:
            report.dry_run_preview = [
                {"file": str(f), "chars": len(read_content_truncated(f, self.max_chars_per_file))}
                for f in files
            ]
            return report, dict(previous_state)

        if files and not self.api_key:
            raise RuntimeError("未设置 DEEPSEEK_API_KEY 环境变量。请先: export DEEPSEEK_API_KEY=sk-xxx")

        system_prompt = self._load_system_prompt() if files else ""
        new_hashes = dict(old_hashes)

        # 被内容去重跳过的文件，内容跟保留下来的某个文件完全一致——虽然没有
        # 单独调用 LLM 分析它，但语义上等同于"已处理过"，记进状态里；否则它会
        # 一直不在 file_hashes 里，下次运行又被重新排进候选队列、再去重一遍，
        # 而这次候选队列里可能不再有内容相同的"伙伴"陪它一起被去重掉，导致
        # 明明内容没变的文件还是被送去调用了一次 LLM。
        for d in dupes:
            dup_path = Path(d["file"])
            rel = (str(dup_path.relative_to(self.project_root))
                   if dup_path.is_relative_to(self.project_root) else str(dup_path))
            digest = hash_file(dup_path)
            if digest:
                new_hashes[rel] = digest

        for f in files:
            rel = str(f.relative_to(self.project_root)) if f.is_relative_to(self.project_root) else str(f)
            try:
                content = read_content_truncated(f, self.max_chars_per_file)
                if not content.strip():
                    digest = hash_file(f)
                    if digest:
                        new_hashes[rel] = digest
                    continue
                background = get_background(Path(rel).stem) if self.use_ob_context else None
                user_message = f"文件路径: {rel}\n\n{content}"
                if background:
                    # 背景放在正文之前，让模型先建立"这份文档在讲什么项目背景/
                    # 已有哪些定论"的认知，再判断这份文档里的内容是不是真的
                    # "新任务"，而不是历史记录里早就处理过的旧事——这正是
                    # rule_based_task_scan/document_task_discovery此前在真实
                    # 叙述性文档上噪音大的根因（详见架构文档AIT §3.6）。
                    user_message = f"（以下是OB检索到的项目背景，供参考，不代表一定相关）\n{background}\n\n---\n\n{user_message}"
                raw = call_deepseek(system_prompt, user_message, self.api_key, model=self.model)
                parsed = json.loads(raw)
                tasks = parsed.get("tasks", [])
                if tasks:
                    report.files_with_tasks += 1
                for t in tasks:
                    dt = DiscoveredTask(
                        name=t.get("name", ""), owner=t.get("owner", "unknown"),
                        status=t.get("status", "unknown"), due_date=t.get("due_date"),
                        evidence=t.get("evidence", ""), confidence=float(t.get("confidence", 0.0)),
                        source_file=rel,
                    )
                    report.tasks.append(asdict(dt))
                digest = hash_file(f)
                if digest:
                    new_hashes[rel] = digest
            except (RuntimeError, json.JSONDecodeError, KeyError, ValueError) as e:
                report.errors.append({"file": rel, "error": str(e)})
                # 失败的文件不更新哈希，下次运行会重试，而不是被当成"已处理过"

        return report, {"file_hashes": new_hashes}


def format_text(report: DiscoveryReport) -> str:
    lines = [f"文档任务发现报告 · {report.project_root}", f"生成时间: {report.generated_at}"]
    lines.append(f"扫描文件: {report.files_scanned}"
                 + (f"（另有 {report.incremental_skipped} 个自上次运行以来内容未变化，已跳过）"
                    if report.incremental_skipped else ""))
    if report.duplicates_skipped:
        lines.append(f"按内容去重跳过: {len(report.duplicates_skipped)} 个（与已选文件内容完全相同）")

    if report.dry_run_preview:
        lines.append(f"\n[DRY-RUN] 将发送给 {report.model} 的候选文件（未实际调用 API）：")
        for p in report.dry_run_preview:
            lines.append(f"  - {p['file']}  (~{p['chars']} 字符)")
        return "\n".join(lines)

    lines.append(f"含任务的文件: {report.files_with_tasks}")
    lines.append(f"发现任务总数: {len(report.tasks)}")

    if report.tasks:
        lines.append("\n发现的任务：")
        for t in report.tasks:
            lines.append(f"  · [{t.get('status')}] {t.get('name')}"
                         f"（owner: {t.get('owner')}, 置信度: {t.get('confidence', 0):.2f}）")
            lines.append(f"      来源: {t.get('source_file')}")
            if t.get("evidence"):
                lines.append(f"      依据: {t.get('evidence')}")

    if report.errors:
        lines.append(f"\n失败 {len(report.errors)} 个文件（下次运行会重试）：")
        for e in report.errors:
            lines.append(f"  · {e.get('file')}: {e.get('error')}")

    lines.append("\n⚠️ 以上任务仅供人工审阅。如需让 PTA 真正执行某个发现的任务，")
    lines.append("   需要人工在目标项目的 pta_tasks.json 里手写对应的 steps，")
    lines.append("   而不是把这份报告的内容直接搬进去。")
    return "\n".join(lines)


def to_dict(report: DiscoveryReport) -> dict:
    return asdict(report)
