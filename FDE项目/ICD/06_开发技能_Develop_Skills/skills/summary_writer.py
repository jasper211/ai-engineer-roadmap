#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/summary_writer.py · 运行摘要生成（L3-ICD-06 实现）

职责边界：把 run_all 聚合出的结构化运行摘要，序列化为「JSON（机器接口）+
Markdown（审计阅读）」写入受控 summaries 目录。不抓取、不解析、不判定业务结果，
不访问网络，不写数据库。

对齐任务书 T009 功能要求 5/7 与流程设计 L3-ICD-06：
- 摘要采用唯一运行标识（时间戳 + 短随机后缀），文件名带 run_id，绝不覆盖历史。
- JSON 为机器可读接口；Markdown 为审计阅读。内容只含安全元数据，
  绝不写入密钥 / Cookie / 完整请求头。
- 摘要生成失败为 best-effort：不回滚已提交的业务数据（由调用方处理）。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

SUMMARY_MODE = ("network", "no_network")


def utc_now_iso() -> str:
    """返回 UTC ISO-8601 时间戳（毫秒精度，Z 后缀），对齐 fetch_run 默认时间格式。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_run_id() -> str:
    """生成唯一运行标识：UTC 时间戳 + 8 位随机后缀（同秒运行也不冲突）。"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid4().hex[:8]}"


def _ensure_summary_dir(summary_dir: Path) -> Path:
    p = Path(summary_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_summary(summary_dir, summary: Dict) -> Dict[str, str]:
    """把运行摘要写入受控目录，返回 {"run_id", "json_path", "markdown_path"}。

    以 run_id 为文件名（{run_id}.json / {run_id}.md），写入前确保 run_id 唯一
    （若同名文件已存在则追加随机后缀，绝不覆盖历史）。摘要 dict 会被深拷贝后
    序列化，避免调用方后续修改影响已写文件语义。
    """
    root = _ensure_summary_dir(Path(summary_dir))
    run_id = summary.get("run_id") or new_run_id()

    json_path = root / f"{run_id}.json"
    md_path = root / f"{run_id}.md"
    # 唯一性兜底：历史不应被覆盖（正常路径不会触发，防御性保护）
    if json_path.exists() or md_path.exists():
        run_id = f"{run_id}-{uuid4().hex[:6]}"
        json_path = root / f"{run_id}.json"
        md_path = root / f"{run_id}.md"

    payload = dict(summary)
    payload["run_id"] = run_id
    payload.setdefault("summary_files", {})

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    return {
        "run_id": run_id,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }


def render_markdown(summary: Dict) -> str:
    """把运行摘要渲染为审计可读的 Markdown（无表格依赖，列表式）。"""
    lines: list = []
    lines.append(f"# ICD 全量运行摘要 · {summary.get('run_id', '')}")
    lines.append("")
    lines.append(f"- **模式**: {summary.get('mode', '')}")
    lines.append(f"- **开始**: {summary.get('started_at', '')}")
    lines.append(f"- **结束**: {summary.get('finished_at', '')}")
    counts = summary.get("counts") or {}
    lines.append(
        "- **统计**: 处理 {processed} / 成功 {succeeded} / 失败 {failed} / "
        "跳过 {skipped} / 未接入 {unsupported}".format(
            processed=counts.get("processed", 0),
            succeeded=counts.get("succeeded", 0),
            failed=counts.get("failed", 0),
            skipped=counts.get("skipped", 0),
            unsupported=counts.get("unsupported", 0),
        )
    )
    lines.append("")

    lines.append("## 数据源明细")
    lines.append("")
    for s in summary.get("sources", []):
        recs = s.get("records_written")
        parse = s.get("parse_status")
        if s.get("parse_detail"):
            parse = f"{parse} ({s.get('parse_detail')})"
        lines.append(
            "- source_id={source_id} {insurer}/{dtype} action={action} "
            "fetch={fetch} parse={parse} run_id={run_id} records={records} "
            "error={error}".format(
                source_id=s.get("source_id"),
                insurer=s.get("insurer_code"),
                dtype=s.get("disclosure_type"),
                action=s.get("action"),
                fetch=s.get("fetch_status"),
                parse=parse,
                run_id=s.get("run_id"),
                records=recs if recs is not None else "-",
                error=s.get("error_code"),
            )
        )
        if s.get("message"):
            lines.append(f"    - {s['message']}")
        if s.get("discovered_pdf_url"):
            lines.append(f"    - discovered_pdf_url={s['discovered_pdf_url']}")
    lines.append("")

    lines.append("## 覆盖状态")
    lines.append("")
    for c in summary.get("coverage", []):
        lines.append(
            "- {insurer}/{dtype} → {status} (last_error={err})".format(
                insurer=c.get("insurer_code"),
                dtype=c.get("disclosure_type"),
                status=c.get("coverage_status"),
                err=c.get("last_error_code"),
            )
        )
    lines.append("")

    files = summary.get("summary_files") or {}
    if files:
        lines.append("## 摘要文件")
        lines.append("")
        lines.append(f"- JSON: `{files.get('json_path', '')}`")
        lines.append(f"- Markdown: `{files.get('markdown_path', '')}`")
        lines.append("")

    return "\n".join(lines)
