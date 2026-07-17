#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：跨 Agent 状态注册表 + 统一健康报告生成。

迁移来源：原 05_Agent库/OB知识库同步巡检Agent/agent_status.py，逻辑原样迁移
（不是巡检本身的业务逻辑，是纯技术能力层，符合 tools/ 的归属）。放在 tools/
而不是 11_监控与优化——这不是"OB 监控自己"（那是方法论第11步的本意，PTA 对应
PTA-MONITOR 只读自己的 task_history），而是"OB 作为全部 Agent 的公共支撑，
维护一份共享状态注册表"，属于 OB 巡检能力线①本身的技术支撑，不是自我监控。

每个 Agent（含 OB 自己）导入后调用 register() 注册元信息，每轮巡检后调用
update() 写入最新状态；read_all()/generate_report()/write_report() 供仪表盘
生成器使用。状态文件写在 /tmp/jasper-agents/{agent_name}.json——这是刻意的
轻量设计（每个 Agent 下次运行时重新 register 即可），不是遗漏，暂不迁移到
持久化路径。
"""

import json
import os
from datetime import datetime
from typing import Optional

STATUS_DIR = "/tmp/jasper-agents"


def _status_path(name: str) -> str:
    return os.path.join(STATUS_DIR, f"{name}.json")


def register(name: str, meta: dict):
    """Agent 首次上线时注册元信息。

    meta 字段：
        description: str   — 一句话描述
        schedule: str      — 调度方式（如 "每小时 + 开机"）
        checks: list[str]  — 巡检项目名称列表
        doc_link: str      — （可选）对应文档的 OB 路径
        pid_path: str      — （可选）plist 路径
    """
    data = _read(name) or {}
    data["name"] = name
    data["registered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    for k, v in meta.items():
        data[k] = v
    data.setdefault("status", "⏳ 等待首次")
    data.setdefault("last_run", "—")
    data.setdefault("next_run", "—")
    data.setdefault("results", {})
    data.setdefault("errors", [])
    _write(name, data)


def update(name: str, status_data: dict):
    """每轮巡检后写入最新状态。

    status_data 字段：
        status: str              — "ok" | "error" | "warn"
        last_run: str            — "2026-07-14 15:00"
        next_run: str            — "16:00"
        results: dict            — {"符号链接": "✅", "MCP配置": "✅", ...}
        errors: list[str]        — 异常时的错误描述列表
    """
    data = _read(name) or {"name": name}
    data["status"] = status_data.get("status", "ok")
    data["last_run"] = status_data.get("last_run", datetime.now().strftime("%Y-%m-%d %H:%M"))
    data["next_run"] = status_data.get("next_run", "—")
    data["results"] = status_data.get("results", {})
    data["errors"] = status_data.get("errors", [])
    _write(name, data)


def read_all() -> list:
    """读取所有已注册 Agent 的状态，按注册时间排序。"""
    agents = []
    if not os.path.isdir(STATUS_DIR):
        return agents
    for fname in sorted(os.listdir(STATUS_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(STATUS_DIR, fname)
        try:
            with open(path, "r") as f:
                data = json.load(f)
            agents.append(data)
        except Exception:
            continue
    agents.sort(key=lambda a: a.get("registered_at", ""))
    return agents


def _read(name: str) -> Optional[dict]:
    path = _status_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _write(name: str, data: dict):
    os.makedirs(STATUS_DIR, exist_ok=True)
    with open(_status_path(name), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_report() -> str:
    """读取所有 Agent 状态，生成统一健康报告 Markdown。
    每个 Agent 可在 update() 时附带 detail 字段存放详情 Markdown。
    """
    agents = read_all()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Agent 健康报告",
        "",
        f"> 自动生成 | {now} | 统一汇总所有 Jasper AI Agent 的运行状态",
        "",
        "---",
        "",
        "## 总体状态",
        "",
    ]

    if not agents:
        lines.append("*暂无已注册的 Agent*")
    else:
        lines.append("| Agent | 状态 | 最后巡检 |")
        lines.append("|-------|------|---------|")
        for a in agents:
            lines.append(f"| {a.get('name', '?')} | {a.get('status', '?')} | {a.get('last_run', '—')} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    for a in agents:
        name = a.get("name", "?")
        desc = a.get("description", "")
        detail = a.get("detail", "")
        results = a.get("results", {})
        checks = a.get("checks", [])
        errors = a.get("errors", [])

        lines.append(f"## {name} · {desc}")
        lines.append("")

        if errors:
            lines.append("⚠️ **异常**：")
            for e in errors:
                lines.append(f"- {e}")
            lines.append("")

        if detail:
            lines.append(detail)
        elif results:
            lines.append("| 检查项 | 结果 |")
            lines.append("|--------|------|")
            for c in checks:
                lines.append(f"| {c} | {results.get(c, '⏳')} |")
            lines.append("")

        lines.append("")

    lines.append(f"*最后生成：{now}*")
    return "\n".join(lines)


def write_report(output_path: str):
    """生成统一健康报告并写入指定路径。"""
    try:
        md = generate_report()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md)
    except Exception:
        pass
