#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-DISCOVER · 文档任务发现器
功能：调用 DeepSeek API 阅读外部项目的自由行文文档（合同/会议纪要/审计报告等），
      提取其中隐含的任务（谁、做什么、状态、截止时间），产出一份"任务发现报告"。

背景：PTA-SCAN（规则扫描器）只能处理已结构化的产物——markdown checklist、
      带列名的 CSV 表格；读不懂合同、审计报告、会议纪要这类叙述性文档里
      "这里藏着一个任务"的语义。这一步本质是阅读理解，只有模型能做。

⚠️ 安全边界（刻意设计，不是遗漏）：
  本工具的输出只是"发现报告"（任务名/负责人/状态/来源文件），供人工审阅。
  它绝不会自动写入 pta_tasks.json 的 steps/command 字段——那些字段驱动
  PTA-S02 的真实 shell/python 执行，如果任由模型从任意文档中抽取的内容
  直接进执行步骤，等于把"文档里写了什么"变成"命令行会跑什么"，是一个
  命令注入面。要不要把某个发现的任务变成可执行步骤，永远是人工决定。

增量扫描（v1.4.0 起）：
  --scan 按内容哈希跟"上一次 PTA-DISCOVER 自己的处理记录"比对，只处理新增/变更
  过的文件——而不是每次全量重扫、靠"最近 N 天"这种粗糙的时间窗口。

专属工作区（v1.6.0 起）：
  增量记录、发现报告不再写进目标项目自己的文件夹——那样违反"不改任何项目文件"
  的原则。默认落在 pta_workspace.py 定义的专属工作区（跟目标项目、跟 PTA 自己
  所在的这个共享仓库都物理隔离），按项目分文件夹。发现的任务同时会合并进该项目
  工作区的 task_registry.json，跨次运行去重、供后续人工审阅分类。

运行：
  export DEEPSEEK_API_KEY=sk-xxx

  # 显式指定候选文件（总是处理，忽略增量状态）
  python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project \\
      --files 合同.md 会议纪要.md

  # 增量扫描：只处理自上次 PTA-DISCOVER 运行以来新增/变更的 .md/.txt/.csv
  python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project --scan

  # 忽略增量记录，强制全量重扫一遍
  python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project --scan --force

  # 只看这次会发给模型的候选文件和字符数，不实际调用 API
  python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project --scan --dry-run
"""

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# pta_workspace.py 已随 v2.0.0 迁移移入 _retired_flat_structure/（本脚本本身
# 尚未纳入 agents/skills/tools 结构迁移范围，去留待确认，暂时保持独立可运行）；
# v2.1.0 起本脚本又被归到 11_监控与优化_Monitor_and_Optimize/ 里，_retired_flat_structure/
# 是它上一级（PTA 项目根目录）的子目录，所以要往上退一层再找
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_retired_flat_structure"))
import pta_workspace

# v2.3.0：DeepSeek 调用逻辑（重试/SSL 证书回退）已抽到 tools/llm_client.py，
# 供 daily_sensing 技能复用，这里改成 import 而不是维护第二份同样的实现
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "05_集成工具_Integrate_Tools"))
from tools.llm_client import call_deepseek, DEFAULT_MODEL  # noqa: E402

MAX_CHARS_PER_FILE = 6000
SCAN_EXTENSIONS = {".md", ".txt", ".csv"}
SCAN_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".pta_runs"}

SYSTEM_PROMPT = """你是一个项目任务提取助手。阅读用户提供的项目文档片段，找出其中隐含的
任务/待办事项。任务可能是明确的清单项，也可能藏在合同条款、会议纪要、审计意见的
叙述性文字里。

只提取任务，不要执行、不要建议、不要生成任何命令或代码。

以严格 JSON 格式输出，schema 如下，不要输出任何 JSON 之外的文字：
{
  "tasks": [
    {
      "name": "任务的简短描述",
      "owner": "负责人（找不到就填 unknown）",
      "status": "pending | in_progress | completed | blocked（找不到就填 unknown）",
      "due_date": "YYYY-MM-DD 或找不到就填 null",
      "evidence": "支撑这条任务判断的原文片段（不超过50字）",
      "confidence": 0.0到1.0之间的浮点数
    }
  ]
}

没有发现任务时返回 {"tasks": []}。不要编造文档中没有的信息。"""


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
    files_with_tasks: int
    tasks: List[Dict] = field(default_factory=list)
    errors: List[Dict] = field(default_factory=list)


def _scan_candidate_files(project_root: Path) -> List[Path]:
    """按扩展名找出项目里所有可能含任务信息的文档。不再按"最近 N 天"这种粗糙的
    时间窗口过滤——真正的增量判断交给下面的内容哈希比对（_load_state/_save_state），
    这里只负责把"扩展名匹配的文件都有哪些"这件事做全、做对。"""
    candidates = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in SCAN_EXCLUDE_DIRS and not d.startswith(".")]
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() in SCAN_EXTENSIONS:
                candidates.append(path)
    return sorted(candidates)


def _hash_file(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_state(state_path: Path) -> Dict[str, str]:
    """加载 PTA-DISCOVER 自己的增量处理记录：{相对路径: 上次处理时的内容 sha256}。
    这是一份独立文件，不是 PTA-SCAN 的 .pta_snapshot.json——PTA-SCAN 每次运行会
    整体覆盖写自己的快照文件，共用一份文件会让两边互相冲掉对方的记录。"""
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8")).get("processed", {})
        except json.JSONDecodeError:
            print(f"[警告] 增量状态文件损坏，当作没有历史记录处理: {state_path}")
    return {}


def _save_state(state_path: Path, state: Dict[str, str]) -> None:
    state_path.write_text(
        json.dumps({"updated_at": datetime.now().isoformat(), "processed": state},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _dedupe_by_content(files: List[Path]) -> "tuple[List[Path], List[Dict]]":
    """按文件内容的 sha256 去重：同一份内容在项目里存在多份拷贝（比如按不同维度
    重新归类整理出来的视图文件夹）时，只保留第一份，避免对着相同内容反复调用模型。"""
    seen: Dict[str, Path] = {}
    unique: List[Path] = []
    dropped: List[Dict] = []
    for f in files:
        try:
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
        except OSError:
            unique.append(f)  # 读不了就留着，交给后面的读取逻辑报错
            continue
        if digest in seen:
            dropped.append({"file": str(f), "duplicate_of": str(seen[digest])})
        else:
            seen[digest] = f
            unique.append(f)
    return unique, dropped


TEXT_ENCODINGS = ("utf-8", "gbk", "gb18030", "big5")


def _read_truncated(path: Path, max_chars: int) -> str:
    """按常见编码依次尝试解码，而不是无脑假设 UTF-8。中国大陆项目里的 CSV/txt
    经常是 Windows/Excel 导出的 GBK 编码，errors='ignore' 硬读会把中文读成乱码——
    实测中曾把一份 GBK 的 CSV 读成乱码喂给模型，模型倒是诚实地给了低置信度，
    但根子问题是这里读错了编码。"""
    try:
        data = path.read_bytes()
    except OSError as e:
        raise RuntimeError(f"无法读取文件: {e}")

    for enc in TEXT_ENCODINGS:
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="ignore")  # 都失败就退回旧行为，至少不报错

    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[内容已截断]"
    return text


def discover(project_root: Path, files: List[Path], model: str, max_chars: int,
             dry_run: bool) -> "tuple[DiscoveryReport, Dict[str, str]]":
    """返回 (发现报告, 本次成功处理的文件 {相对路径: 内容sha256})。
    processed 只记录成功处理的文件（含"未发现任务"），失败的文件不记录，
    这样下次运行会重试它们，而不是被增量状态记成"已处理过"。"""
    report = DiscoveryReport(
        generated_at=datetime.now().isoformat(),
        project_root=str(project_root),
        model=model,
        files_scanned=len(files),
        files_with_tasks=0,
    )
    processed: Dict[str, str] = {}

    if dry_run:
        print(f"\n[DRY-RUN] 将发送给 {model} 的候选文件（共 {len(files)} 个）:")
        for f in files:
            size = len(_read_truncated(f, max_chars))
            print(f"  - {f}  (~{size} 字符)")
        return report, processed

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("[错误] 未设置 DEEPSEEK_API_KEY 环境变量。请先: export DEEPSEEK_API_KEY=sk-xxx")
        sys.exit(1)

    for f in files:
        rel = str(f.relative_to(project_root)) if f.is_relative_to(project_root) else str(f)
        print(f"\n分析: {rel}")
        try:
            content = _read_truncated(f, max_chars)
            if not content.strip():
                print("  (空文件，跳过)")
                digest = _hash_file(f)
                if digest:
                    processed[rel] = digest
                continue
            raw = call_deepseek(SYSTEM_PROMPT, f"文件路径: {rel}\n\n{content}", api_key, model=model)
            parsed = json.loads(raw)
            tasks = parsed.get("tasks", [])
            if tasks:
                report.files_with_tasks += 1
            for t in tasks:
                dt = DiscoveredTask(
                    name=t.get("name", ""),
                    owner=t.get("owner", "unknown"),
                    status=t.get("status", "unknown"),
                    due_date=t.get("due_date"),
                    evidence=t.get("evidence", ""),
                    confidence=float(t.get("confidence", 0.0)),
                    source_file=rel,
                )
                report.tasks.append(asdict(dt))
                print(f"  ✓ [{dt.status}] {dt.name} (owner: {dt.owner}, 置信度: {dt.confidence:.2f})")
            if not tasks:
                print("  (未发现任务)")
            digest = _hash_file(f)
            if digest:
                processed[rel] = digest
        except (RuntimeError, json.JSONDecodeError, KeyError) as e:
            print(f"  ❌ 失败: {e}")
            report.errors.append({"file": rel, "error": str(e)})
            # 失败的文件不记进 processed，下次运行会重试，而不是被当成"已处理过"

    return report, processed


def main():
    parser = argparse.ArgumentParser(description="PTA-DISCOVER · 文档任务发现器（DeepSeek）")
    parser.add_argument("--project", required=True, help="目标项目根目录")
    parser.add_argument("--files", nargs="*", help="显式指定候选文件（相对或绝对路径），总是处理，不受增量状态影响")
    parser.add_argument("--scan", action="store_true", help="自动扫描项目内所有 .md/.txt/.csv 文件，按增量状态过滤")
    parser.add_argument("--state", help="增量状态文件路径（默认: 专属工作区下的 discover_state.json，"
                                         "见 pta_workspace.py，不再写进项目自己的文件夹）")
    parser.add_argument("--force", action="store_true", help="忽略增量状态，--scan 找到的文件全部重新处理")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DeepSeek 模型（默认 deepseek-chat）")
    parser.add_argument("--max-chars-per-file", type=int, default=MAX_CHARS_PER_FILE,
                         help="每个文件截断的最大字符数（控制成本）")
    parser.add_argument("--output", "-o", help="发现报告输出路径（默认: 专属工作区 reports/ 下自动命名）")
    parser.add_argument("--dry-run", action="store_true", help="只列出候选文件和大小，不调用 API，也不更新增量状态")
    args = parser.parse_args()

    project_root = Path(args.project).resolve()
    if not project_root.exists():
        print(f"[错误] 项目路径不存在: {project_root}")
        sys.exit(1)

    workspace = pta_workspace.get_project_workspace(project_root)
    state_path = Path(args.state).resolve() if args.state else workspace / "discover_state.json"
    state = _load_state(state_path)

    explicit_files: List[Path] = [Path(f).resolve() for f in (args.files or [])]

    scanned_files: List[Path] = []
    if args.scan:
        scanned_files = _scan_candidate_files(project_root)
        print(f"[PTA-DISCOVER] 扫描到 {len(scanned_files)} 个 .md/.txt/.csv 候选文档")

        if not args.force and state:
            kept, skipped = [], []
            for f in scanned_files:
                rel = str(f.relative_to(project_root)) if f.is_relative_to(project_root) else str(f)
                digest = _hash_file(f)
                if digest is not None and state.get(rel) == digest:
                    skipped.append(f)
                else:
                    kept.append(f)
            scanned_files = kept
            if skipped:
                print(f"[PTA-DISCOVER] 增量跳过: {len(skipped)} 个文件自上次 PTA-DISCOVER 处理以来内容未变化"
                      f"（用 --force 可强制全部重新处理）")

    files = explicit_files + scanned_files
    if not files:
        if args.scan:
            print("[PTA-DISCOVER] 没有需要处理的文件——都已经在增量状态里，内容没有变化。")
            return
        print("[错误] 没有候选文件。使用 --files 指定，或加 --scan 自动扫描。")
        sys.exit(1)

    # 先按路径去重（同一个文件被 --files 和 --scan 都选中），再按内容 sha256 去重
    # （同一份内容在项目里存在多份拷贝，比如按不同维度重新归类出来的视图文件夹）
    files = sorted(set(files))
    files, dupes = _dedupe_by_content(files)
    if dupes:
        print(f"[PTA-DISCOVER] 按内容去重：跳过 {len(dupes)} 个与已选文件内容完全相同的重复文件")
        for d in dupes[:10]:
            print(f"  - {d['file']}\n    (与 {d['duplicate_of']} 内容相同)")
        if len(dupes) > 10:
            print(f"  ... 还有 {len(dupes) - 10} 个")

    report, processed = discover(project_root, files, args.model, args.max_chars_per_file, args.dry_run)

    print(f"\n{'='*60}")
    print(f"[PTA-DISCOVER] 发现报告")
    print(f"{'='*60}")
    print(f"扫描文件: {report.files_scanned}")
    print(f"含任务的文件: {report.files_with_tasks}")
    print(f"发现任务总数: {len(report.tasks)}")
    if report.errors:
        print(f"失败: {len(report.errors)}")
    print(f"{'='*60}")
    print("\n⚠️ 以上任务仅供人工审阅。如需让 PTA 真正执行某个发现的任务，")
    print("   需要人工在目标项目的 pta_tasks.json 里手写对应的 steps，")
    print("   而不是把这份报告的内容直接搬进去。")

    if not args.dry_run:
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = workspace / "reports" / f"discover-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n报告已保存: {output_path}")

    if report.tasks and not args.dry_run:
        pta_workspace.merge_task_registry(workspace, report.tasks)
        print(f"任务已合并进登记表: {workspace / 'task_registry.json'}")

    if processed and not args.dry_run:
        state.update(processed)
        _save_state(state_path, state)
        print(f"增量状态已更新: {state_path}（{len(processed)} 个文件）")


if __name__ == "__main__":
    main()
