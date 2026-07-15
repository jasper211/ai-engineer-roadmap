#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：目录结构分析（从 PTA-EXT_外部项目分析器.py 抽取，改造成纯函数式 API）

原脚本 `ProjectAnalyzer._analyze_directory` 只跳过"以 . 开头"的子目录，没有
排除 `node_modules`/`__pycache__` 这类非隐藏但明显该跳过的目录——如果被分析
项目里恰好有个 `node_modules`，会把里面成百上千个第三方库文件也统计进报告，
文件数/体积统计完全失真。这次复用 `tools/file_diff.py` 已有的
`DEFAULT_EXCLUDE_DIRS`，同一份排除名单，不用再维护第二份。
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from tools.file_diff import DEFAULT_EXCLUDE_DIRS

FILE_TYPE_MAP = {
    ".md": "Markdown文档", ".txt": "文本文件", ".docx": "Word文档",
    ".xlsx": "Excel表格", ".csv": "CSV数据", ".json": "JSON配置",
    ".py": "Python脚本", ".js": "JavaScript", ".html": "HTML页面",
    ".css": "样式文件", ".pdf": "PDF文档",
    ".png": "图片", ".jpg": "图片", ".jpeg": "图片",
}


@dataclass
class FileInfo:
    name: str
    path: str
    type: str
    size_bytes: int
    size_formatted: str
    modified_time: str


@dataclass
class DirectoryInfo:
    name: str
    path: str
    file_count: int
    files: List[FileInfo] = field(default_factory=list)
    subdirectories: int = 0


@dataclass
class ProjectReport:
    project_path: str
    analysis_time: str
    total_directories: int
    total_files: int
    total_size_bytes: int
    total_size_formatted: str
    directories: List[DirectoryInfo] = field(default_factory=list)
    file_type_distribution: Dict[str, int] = field(default_factory=dict)
    summary: str = ""


def _format_size(bytes_size: int) -> str:
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.1f} MB"
    return f"{bytes_size / (1024 * 1024 * 1024):.1f} GB"


def _get_file_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    return FILE_TYPE_MAP.get(ext, f"{ext}文件" if ext else "未知类型")


def _should_skip_dir(name: str) -> bool:
    return name.startswith(".") or name in DEFAULT_EXCLUDE_DIRS


def _analyze_directory(project_root: Path, dir_path: Path) -> DirectoryInfo:
    files: List[FileInfo] = []
    subdirs = 0
    try:
        for item in dir_path.iterdir():
            if item.is_file():
                stat = item.stat()
                files.append(FileInfo(
                    name=item.name, path=str(item.relative_to(project_root)),
                    type=_get_file_type(item), size_bytes=stat.st_size,
                    size_formatted=_format_size(stat.st_size),
                    modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                ))
            elif item.is_dir() and not _should_skip_dir(item.name):
                subdirs += 1
    except PermissionError:
        pass

    return DirectoryInfo(
        name=dir_path.name,
        path=str(dir_path.relative_to(project_root)) if dir_path != project_root else ".",
        file_count=len(files), files=files, subdirectories=subdirs,
    )


def analyze_project(project_root: Path, max_depth: int = 2) -> ProjectReport:
    """
    分析项目结构：根目录 + 第一层子目录（跳过隐藏目录和 file_diff.DEFAULT_EXCLUDE_DIRS
    里的目录），统计文件数/体积/类型分布。

    注：max_depth 参数保留只是为了兼容原 CLI 接口，当前实现固定只看两层
    （根目录本身 + 直接子目录），不做更深层递归——这是原脚本本来的行为，
    这次迁移没有扩大扫描范围，只修复了目录排除的缺口（原来只排除隐藏目录，
    像 node_modules 这种非隐藏但该跳过的目录会被当成普通子目录统计进去）。
    """
    project_root = Path(project_root)
    directories: List[DirectoryInfo] = []
    total_files = 0
    total_size = 0
    file_type_dist: Dict[str, int] = {}

    root_info = _analyze_directory(project_root, project_root)
    directories.append(root_info)
    for f in root_info.files:
        total_files += 1
        total_size += f.size_bytes
        file_type_dist[f.type] = file_type_dist.get(f.type, 0) + 1

    for item in project_root.iterdir():
        if item.is_dir() and not _should_skip_dir(item.name):
            dir_info = _analyze_directory(project_root, item)
            directories.append(dir_info)
            for f in dir_info.files:
                total_files += 1
                total_size += f.size_bytes
                file_type_dist[f.type] = file_type_dist.get(f.type, 0) + 1

    summary = (
        f"项目路径: {project_root}\n"
        f"分析时间: {datetime.now().isoformat()}\n"
        f"总目录数: {len(directories)}\n"
        f"总文件数: {total_files}\n"
        f"总大小: {_format_size(total_size)}\n"
        f"文件类型分布: {dict(sorted(file_type_dist.items(), key=lambda x: x[1], reverse=True))}"
    )

    return ProjectReport(
        project_path=str(project_root), analysis_time=datetime.now().isoformat(),
        total_directories=len(directories), total_files=total_files,
        total_size_bytes=total_size, total_size_formatted=_format_size(total_size),
        directories=directories, file_type_distribution=file_type_dist, summary=summary,
    )


def format_report_text(report: ProjectReport) -> str:
    lines = [
        "=" * 60, "[dir_scan] 项目分析报告", "=" * 60,
        f"项目路径: {report.project_path}", f"分析时间: {report.analysis_time}", "=" * 60,
        "\n总体统计:", f"  总目录数: {report.total_directories}",
        f"  总文件数: {report.total_files}", f"  总大小: {report.total_size_formatted}",
        "\n文件类型分布:",
    ]
    for file_type, count in sorted(report.file_type_distribution.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"  {file_type}: {count} 个")

    lines.append("\n目录详情:")
    for dir_info in report.directories:
        lines.append(f"\n  📁 {dir_info.name}/")
        lines.append(f"    路径: {dir_info.path}")
        lines.append(f"    文件数: {dir_info.file_count}")
        lines.append(f"    子目录: {dir_info.subdirectories}")
        for f in dir_info.files[:5]:
            lines.append(f"      📄 {f.name} ({f.size_formatted})")
        if len(dir_info.files) > 5:
            lines.append(f"      ... 还有 {len(dir_info.files) - 5} 个文件")

    lines.append(f"\n{'='*60}")
    return "\n".join(lines)


def format_report_markdown(report: ProjectReport) -> str:
    content = f"""# 项目结构分析报告

> 生成工具: tools/dir_scan.py（原 PTA-EXT 外部项目分析器）
> 分析时间: {report.analysis_time}
> 项目路径: `{report.project_path}`
> 分析模式: 只读（未修改原项目）

---

## 总体统计

| 指标 | 数值 |
|------|------|
| 总目录数 | {report.total_directories} |
| 总文件数 | {report.total_files} |
| 总大小 | {report.total_size_formatted} |

## 文件类型分布

| 文件类型 | 数量 |
|----------|------|
"""
    for file_type, count in sorted(report.file_type_distribution.items(), key=lambda x: x[1], reverse=True):
        content += f"| {file_type} | {count} |\n"

    content += "\n## 目录结构\n\n"
    for dir_info in report.directories:
        content += f"### 📁 {dir_info.name}/\n\n"
        content += f"- 路径: `{dir_info.path}`\n"
        content += f"- 文件数: {dir_info.file_count}\n"
        content += f"- 子目录: {dir_info.subdirectories}\n\n"
        if dir_info.files:
            content += "| 文件名 | 类型 | 大小 |\n|--------|------|------|\n"
            for f in dir_info.files:
                content += f"| {f.name} | {f.type} | {f.size_formatted} |\n"
            content += "\n"

    content += "---\n\n> 报告生成完成，原项目未被修改\n"
    return content
