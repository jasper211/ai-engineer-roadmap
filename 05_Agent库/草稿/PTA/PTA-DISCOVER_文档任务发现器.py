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

运行：
  export DEEPSEEK_API_KEY=sk-xxx

  # 显式指定候选文件
  python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project \\
      --files 合同.md 会议纪要.md --output discovered_tasks.json

  # 自动扫描项目内最近变更的候选文档（.md/.txt/.csv，按 mtime）
  python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project --scan --days 7

  # 只看会发给模型的候选文件和字符数，不实际调用 API
  python3 PTA-DISCOVER_文档任务发现器.py --project /path/to/project --scan --dry-run
"""

import argparse
import fnmatch
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
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


def _build_ssl_context() -> ssl.SSLContext:
    """构造 HTTPS 用的 SSL 上下文。有些 Python 安装（尤其是 Homebrew 装的）默认证书路径
    是坏的（openssl@3 的 cert.pem 不存在），urlopen 会报 CERTIFICATE_VERIFY_FAILED。
    这里按优先级找一个真实存在的 CA 证书包，而不是绕过证书校验。"""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for candidate in (
        "/etc/ssl/cert.pem",  # macOS 系统自带
        "/usr/local/etc/ca-certificates/cert.pem",  # Homebrew (Intel)
        "/opt/homebrew/etc/ca-certificates/cert.pem",  # Homebrew (Apple Silicon)
    ):
        if Path(candidate).exists():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()  # 用默认路径，找不到就让它照常报错


_SSL_CONTEXT = _build_ssl_context()


def _call_deepseek(api_key: str, model: str, user_content: str, max_retries: int = 2) -> str:
    """调用 DeepSeek Chat Completions（OpenAI 兼容接口），返回 message.content 字符串"""
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and attempt < max_retries:
                wait = 2 ** (attempt + 1)
                print(f"  [限流] 429，{wait}s 后重试...")
                time.sleep(wait)
                last_err = f"HTTP {e.code}: {detail}"
                continue
            raise RuntimeError(f"DeepSeek API 请求失败 HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"DeepSeek API 网络错误: {e}") from e
    raise RuntimeError(f"DeepSeek API 请求失败（已重试 {max_retries} 次）: {last_err}")


def _scan_candidate_files(project_root: Path, days: int) -> List[Path]:
    """按扩展名 + 最近修改时间做粗筛，找出可能含任务信息的文档"""
    cutoff = datetime.now() - timedelta(days=days)
    candidates = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in SCAN_EXCLUDE_DIRS and not d.startswith(".")]
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() not in SCAN_EXTENSIONS:
                continue
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if mtime >= cutoff:
                candidates.append(path)
    return sorted(candidates)


def _read_truncated(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        raise RuntimeError(f"无法读取文件: {e}")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[内容已截断]"
    return text


def discover(project_root: Path, files: List[Path], model: str, max_chars: int,
             dry_run: bool) -> DiscoveryReport:
    report = DiscoveryReport(
        generated_at=datetime.now().isoformat(),
        project_root=str(project_root),
        model=model,
        files_scanned=len(files),
        files_with_tasks=0,
    )

    if dry_run:
        print(f"\n[DRY-RUN] 将发送给 {model} 的候选文件（共 {len(files)} 个）:")
        for f in files:
            size = len(_read_truncated(f, max_chars))
            print(f"  - {f}  (~{size} 字符)")
        return report

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
                continue
            raw = _call_deepseek(api_key, model, f"文件路径: {rel}\n\n{content}")
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
        except (RuntimeError, json.JSONDecodeError, KeyError) as e:
            print(f"  ❌ 失败: {e}")
            report.errors.append({"file": rel, "error": str(e)})

    return report


def main():
    parser = argparse.ArgumentParser(description="PTA-DISCOVER · 文档任务发现器（DeepSeek）")
    parser.add_argument("--project", required=True, help="目标项目根目录")
    parser.add_argument("--files", nargs="*", help="显式指定候选文件（相对或绝对路径）")
    parser.add_argument("--scan", action="store_true", help="自动扫描项目内最近变更的 .md/.txt/.csv 文件")
    parser.add_argument("--days", type=int, default=7, help="--scan 时的最近变更天数窗口（默认 7）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DeepSeek 模型（默认 deepseek-chat）")
    parser.add_argument("--max-chars-per-file", type=int, default=MAX_CHARS_PER_FILE,
                         help="每个文件截断的最大字符数（控制成本）")
    parser.add_argument("--output", "-o", help="发现报告输出路径（JSON）")
    parser.add_argument("--dry-run", action="store_true", help="只列出候选文件和大小，不调用 API")
    args = parser.parse_args()

    project_root = Path(args.project).resolve()
    if not project_root.exists():
        print(f"[错误] 项目路径不存在: {project_root}")
        sys.exit(1)

    files: List[Path] = []
    if args.files:
        files.extend(Path(f).resolve() for f in args.files)
    if args.scan:
        found = _scan_candidate_files(project_root, args.days)
        print(f"[PTA-DISCOVER] 扫描到 {len(found)} 个最近 {args.days} 天内变更的候选文档")
        files.extend(found)

    if not files:
        print("[错误] 没有候选文件。使用 --files 指定，或加 --scan 自动扫描。")
        sys.exit(1)

    # 去重
    files = sorted(set(files))

    report = discover(project_root, files, args.model, args.max_chars_per_file, args.dry_run)

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

    if args.output and not args.dry_run:
        output_path = Path(args.output)
        output_path.write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n报告已保存: {output_path}")


if __name__ == "__main__":
    main()
