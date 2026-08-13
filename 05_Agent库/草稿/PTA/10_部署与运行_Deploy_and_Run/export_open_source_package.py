#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出适合同事部署的 PTA 开源包。

目标：
1. 保留 PTA 主体代码和任务驾驶舱。
2. 去掉本机运行痕迹、缓存和敏感配置。
3. 生成一个可直接分发的目录，以及对应 zip 压缩包。
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


THIS_FILE = Path(__file__).resolve()
PTA_DIR = THIS_FILE.parent.parent
DEFAULT_OUTPUT_ROOT = PTA_DIR / "_open_source_exports"
DEFAULT_PACKAGE_NAME = "PTA_Open_Source_Kit"

REMOVE_DIR_NAMES = {
    "__pycache__",
    "node_modules",
    "dist",
}

REMOVE_FILE_NAMES = {
    ".DS_Store",
    "skill_usage_log.json",
    "wecom_config.json",
}

REMOVE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tsbuildinfo",
}

IGNORE_TOP_LEVEL_NAMES = {
    "_open_source_exports",
}


def _safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _safe_unlink(path: Path) -> None:
    if path.exists():
        path.unlink()


def _copy_source_tree(target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(
        PTA_DIR,
        target_dir,
        ignore=shutil.ignore_patterns(*IGNORE_TOP_LEVEL_NAMES),
    )


def _cleanup_runtime_artifacts(target_dir: Path) -> None:
    for path in sorted(target_dir.rglob("*")):
        if path.is_dir() and path.name in REMOVE_DIR_NAMES:
            shutil.rmtree(path)
            continue
        if path.is_file():
            if path.name in REMOVE_FILE_NAMES or path.suffix in REMOVE_SUFFIXES:
                path.unlink()


def _rewrite_env_example(target_dir: Path) -> None:
    env_example = target_dir / "02_配置项目_Configure_Project" / ".env.example"
    env_example.write_text(
        "# PTA 环境变量示例。复制为 .env 后按需修改。\n"
        "#\n"
        "# 建议每位同事给 PTA 配置独立工作区，所有状态、巡检报告、执行记录\n"
        "# 都会写在这里，而不是写回被巡检的业务项目目录。\n"
        "PTA_WORKSPACE_ROOT=~/PTA_Workspace\n"
        "\n"
        "# 如需启用 --daily-scan / --discover 等 LLM 能力，再配置：\n"
        "DEEPSEEK_API_KEY=\n",
        encoding="utf-8",
    )


def _rewrite_daily_scan_projects(target_dir: Path) -> None:
    payload = {
        "_meta": {
            "note": "同事部署时，在这里登记需要巡检的本地项目目录。"
                    " project_root 必须改成各自电脑上的真实绝对路径。"
        },
        "projects": [
            {
                "name": "示例项目",
                "project_root": "/ABSOLUTE/PATH/TO/YOUR/PROJECT",
                "exclude_dirs": [
                    ".git",
                    "node_modules",
                    "__pycache__",
                    "dist"
                ]
            }
        ]
    }
    target = target_dir / "02_配置项目_Configure_Project" / "daily_scan_projects.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rewrite_agent_registry(target_dir: Path) -> None:
    payload = {
        "_meta": {
            "purpose": "任务驾驶舱 Agent 监控器示例配置。",
            "maintenance_note": "按各自团队真实 Agent 项目路径和常驻任务标签修改。"
        },
        "agents": [
            {
                "agent_id": "PTA",
                "display_name": "PTA · 项目任务协同",
                "description": "每日巡检、任务执行编排、驾驶舱服务",
                "code_paths": [
                    "PTA/04_定义Agent_Define_Agent/agents/agent.py"
                ],
                "launchd_labels": []
            },
            {
                "agent_id": "EXAMPLE",
                "display_name": "示例 Agent",
                "description": "请替换成你们团队自己的 Agent",
                "code_paths": [],
                "launchd_labels": []
            }
        ]
    }
    target = target_dir / "02_配置项目_Configure_Project" / "agent_registry.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rewrite_settings(target_dir: Path) -> None:
    settings_path = target_dir / "02_配置项目_Configure_Project" / "settings.json"
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    data["status"] = "open-source"
    data["description"] = (
        "通用型项目任务协同 Agent：理解自然语言任务，规划执行步骤，"
        "追踪进度，并提供每日巡检与任务驾驶舱能力。"
    )
    settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_github_readme(target_dir: Path) -> None:
    readme = target_dir / "README.md"
    readme.write_text(
        "# PTA · Project Task Agent\n\n"
        "PTA is a local-first project collaboration agent for structured task execution, "
        "daily project scanning, and a lightweight task cockpit.\n\n"
        "It is designed for teammates who want to:\n"
        "- turn natural-language instructions into executable task plans\n"
        "- track task status and execution history across sessions\n"
        "- scan project file changes and generate candidate follow-up tasks\n"
        "- run a local dashboard for task review, pipeline drift checks, and agent monitoring\n\n"
        "## Core Capabilities\n\n"
        "- Task execution loop: intent parsing, execution planning, progress tracking, archive review\n"
        "- Daily scan: detect file changes, summarize impact, and write candidate tasks for review\n"
        "- Task dashboard: local API + React frontend for viewing tasks and project activity\n"
        "- Pipeline health: deterministic checks for files, test commands, and expected artifacts\n"
        "- Workspace isolation: PTA writes its own state into a separate workspace instead of polluting target projects\n\n"
        "## Repository Structure\n\n"
        "```text\n"
        "PTA/\n"
        "|-- 04_定义Agent_Define_Agent/agents/agent.py\n"
        "|-- 05_集成工具_Integrate_Tools/tools/\n"
        "|-- 06_开发技能_Develop_Skills/skills/\n"
        "|-- 07_接入记忆_Integrate_Memory/memory/\n"
        "|-- 09_测试与调试_Test_and_Debug/tests/\n"
        "|-- 10_部署与运行_Deploy_and_Run/\n"
        "`-- 12_任务看板_Task_Dashboard/\n"
        "```\n\n"
        "## Quick Start\n\n"
        "### 1. Install Python dependencies\n\n"
        "```bash\n"
        "python3 -m venv .venv\n"
        "source .venv/bin/activate\n"
        "pip install -r requirements.txt\n"
        "```\n\n"
        "### 2. Configure environment\n\n"
        "Copy `02_配置项目_Configure_Project/.env.example` to `.env` and set at least:\n"
        "- `PTA_WORKSPACE_ROOT`\n"
        "- `DEEPSEEK_API_KEY` if you want LLM-powered scan/discovery features\n\n"
        "### 3. Run the agent\n\n"
        "```bash\n"
        "python3 04_定义Agent_Define_Agent/agents/agent.py --status\n"
        "python3 04_定义Agent_Define_Agent/agents/agent.py \"按顺序完成 P1-03, P1-04\"\n"
        "python3 04_定义Agent_Define_Agent/agents/agent.py \"按顺序完成 P1-03, P1-04\" --execute\n"
        "```\n\n"
        "Or use the wrapper script:\n\n"
        "```bash\n"
        "bash 10_部署与运行_Deploy_and_Run/quick_start.sh\n"
        "```\n\n"
        "## Run the Dashboard\n\n"
        "Backend:\n\n"
        "```bash\n"
        "python3 12_任务看板_Task_Dashboard/api/server.py --port 8787\n"
        "```\n\n"
        "Frontend dev mode:\n\n"
        "```bash\n"
        "cd 12_任务看板_Task_Dashboard/web\n"
        "npm install\n"
        "npm run dev\n"
        "```\n\n"
        "Frontend build mode:\n\n"
        "```bash\n"
        "cd 12_任务看板_Task_Dashboard/web\n"
        "npm install\n"
        "npm run build\n"
        "cd ..\n"
        "python3 api/server.py --port 8787\n"
        "```\n\n"
        "## Team Setup\n\n"
        "Before using PTA on a new machine, update:\n"
        "- `02_配置项目_Configure_Project/daily_scan_projects.json`\n"
        "- `02_配置项目_Configure_Project/agent_registry.json`\n"
        "- `02_配置项目_Configure_Project/wecom_config.json` if notification is needed\n\n"
        "Each teammate should keep their own project paths, workspace root, and notification config.\n\n"
        "## Notes\n\n"
        "- PTA is designed for local deployment, not multi-tenant cloud hosting.\n"
        "- The exported open-source package intentionally removes local caches, private paths, and runtime logs.\n"
        "- For handover details, see `OPEN_SOURCE_HANDOVER.md`.\n",
        encoding="utf-8",
    )


def _write_handover_guide(target_dir: Path) -> None:
    guide = target_dir / "OPEN_SOURCE_HANDOVER.md"
    guide.write_text(
        "# PTA 开源包交接说明\n\n"
        "## 这份包包含什么\n"
        "- PTA 主引擎：自然语言任务解析、执行计划、进度追踪、归档复盘。\n"
        "- 每日巡检：扫描项目文件变化，生成建议任务。\n"
        "- 任务驾驶舱：本地前后端页面，用来查看巡检结果、任务状态和 Agent 监控。\n\n"
        "## 推荐环境\n"
        "- Python 3.10+\n"
        "- Node.js 20+\n"
        "- npm 10+\n\n"
        "## 1. 安装 Python 依赖\n"
        "```bash\n"
        "cd PTA\n"
        "python3 -m venv .venv\n"
        "source .venv/bin/activate\n"
        "pip install -r requirements.txt\n"
        "```\n\n"
        "## 2. 配置环境变量\n"
        "```bash\n"
        "cp 02_配置项目_Configure_Project/.env.example .env\n"
        "```\n"
        "至少建议配置：\n"
        "- `PTA_WORKSPACE_ROOT`：PTA 运行产物目录。\n"
        "- `DEEPSEEK_API_KEY`：只有启用 `--daily-scan`、`--discover` 等 LLM 功能时才需要。\n\n"
        "## 3. 配置巡检项目\n"
        "修改 `02_配置项目_Configure_Project/daily_scan_projects.json`：\n"
        "- 把示例 `project_root` 改成自己电脑上的绝对路径。\n"
        "- 可按项目增加 `exclude_dirs`。\n\n"
        "## 4. 快速验证 PTA 主体\n"
        "```bash\n"
        "bash 10_部署与运行_Deploy_and_Run/quick_start.sh \"按顺序完成 P2-02, P2-03\"\n"
        "```\n\n"
        "## 5. 启动任务驾驶舱\n"
        "后端：\n"
        "```bash\n"
        "python3 12_任务看板_Task_Dashboard/api/server.py --port 8787\n"
        "```\n"
        "前端开发模式：\n"
        "```bash\n"
        "cd 12_任务看板_Task_Dashboard/web\n"
        "npm install\n"
        "npm run dev\n"
        "```\n"
        "打开 [http://localhost:5173](http://localhost:5173)\n\n"
        "前端生产模式：\n"
        "```bash\n"
        "cd 12_任务看板_Task_Dashboard/web\n"
        "npm install\n"
        "npm run build\n"
        "cd ..\n"
        "python3 api/server.py --port 8787\n"
        "```\n"
        "打开 [http://localhost:8787](http://localhost:8787)\n\n"
        "## 6. 可选配置\n"
        "- 企业微信通知：复制 `02_配置项目_Configure_Project/wecom_config.example.json`\n"
        "  为 `wecom_config.json`，填入各自 webhook。\n"
        "- Agent 监控：修改 `02_配置项目_Configure_Project/agent_registry.json`，接入团队自己的 Agent。\n\n"
        "## 7. 导出说明\n"
        "这份包已经去掉以下本机痕迹：\n"
        "- `node_modules`、`__pycache__`、`.DS_Store`\n"
        "- 本机企业微信配置\n"
        "- 技能调用日志和编译缓存\n"
        "- 原始多项目私有路径映射\n",
        encoding="utf-8",
    )


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            zf.write(path, path.relative_to(source_dir.parent))


def export_package(output_root: Path, package_name: str) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    target_dir = output_root / package_name
    _copy_source_tree(target_dir)
    _cleanup_runtime_artifacts(target_dir)
    _write_github_readme(target_dir)
    _rewrite_env_example(target_dir)
    _rewrite_daily_scan_projects(target_dir)
    _rewrite_agent_registry(target_dir)
    _rewrite_settings(target_dir)
    _write_handover_guide(target_dir)
    zip_path = output_root / f"{package_name}.zip"
    _zip_directory(target_dir, zip_path)
    return target_dir, zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 PTA 开源交付包")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="导出目录根路径，默认写到 PTA/_open_source_exports/",
    )
    parser.add_argument(
        "--package-name",
        default=DEFAULT_PACKAGE_NAME,
        help="导出目录名和 zip 包名前缀",
    )
    args = parser.parse_args()

    output_root = Path(args.output_root).expanduser().resolve()
    package_dir, zip_path = export_package(output_root, args.package_name)
    print(f"[PTA open-source] package_dir={package_dir}")
    print(f"[PTA open-source] zip_path={zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
