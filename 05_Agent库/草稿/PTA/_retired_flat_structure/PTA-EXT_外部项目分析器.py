#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA-EXT · 外部项目分析器
功能：分析任意文件夹的项目结构，生成索引报告（只读）
运行：python3 pta_ext_project_analyzer.py --path /path/to/project --output report.json

使用场景：
  - 分析 Rw 权益项目等外部项目
  - 不修改原项目，只生成分析报告
  - 与 PTA 主流程配合使用
"""

import os
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# ============================================================
# 配置区
# ============================================================

# 文件类型映射
FILE_TYPE_MAP = {
    ".md": "Markdown文档",
    ".txt": "文本文件",
    ".docx": "Word文档",
    ".xlsx": "Excel表格",
    ".csv": "CSV数据",
    ".json": "JSON配置",
    ".py": "Python脚本",
    ".js": "JavaScript",
    ".html": "HTML页面",
    ".css": "样式文件",
    ".pdf": "PDF文档",
    ".png": "图片",
    ".jpg": "图片",
    ".jpeg": "图片",
}

# ============================================================


@dataclass
class FileInfo:
    """文件信息"""
    name: str
    path: str
    type: str
    size_bytes: int
    size_formatted: str
    modified_time: str


@dataclass
class DirectoryInfo:
    """目录信息"""
    name: str
    path: str
    file_count: int
    files: List[FileInfo]
    subdirectories: int


@dataclass
class ProjectReport:
    """项目分析报告"""
    project_path: str
    analysis_time: str
    total_directories: int
    total_files: int
    total_size_bytes: int
    total_size_formatted: str
    directories: List[DirectoryInfo]
    file_type_distribution: Dict[str, int]
    summary: str


class ProjectAnalyzer:
    """项目分析器：只读分析外部项目"""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.report = None
    
    def _format_size(self, bytes_size: int) -> str:
        """格式化文件大小"""
        if bytes_size < 1024:
            return f"{bytes_size} B"
        elif bytes_size < 1024 * 1024:
            return f"{bytes_size / 1024:.1f} KB"
        elif bytes_size < 1024 * 1024 * 1024:
            return f"{bytes_size / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_size / (1024 * 1024 * 1024):.1f} GB"
    
    def _get_file_type(self, file_path: Path) -> str:
        """获取文件类型"""
        ext = file_path.suffix.lower()
        return FILE_TYPE_MAP.get(ext, f"{ext}文件" if ext else "未知类型")
    
    def _analyze_directory(self, dir_path: Path, max_depth: int = 2, current_depth: int = 0) -> Optional[DirectoryInfo]:
        """分析单个目录"""
        if current_depth > max_depth:
            return None
        
        files = []
        subdirs = 0
        
        try:
            for item in dir_path.iterdir():
                if item.is_file():
                    stat = item.stat()
                    file_info = FileInfo(
                        name=item.name,
                        path=str(item.relative_to(self.project_path)),
                        type=self._get_file_type(item),
                        size_bytes=stat.st_size,
                        size_formatted=self._format_size(stat.st_size),
                        modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    )
                    files.append(file_info)
                elif item.is_dir() and not item.name.startswith("."):
                    subdirs += 1
        except PermissionError:
            pass
        
        return DirectoryInfo(
            name=dir_path.name,
            path=str(dir_path.relative_to(self.project_path)) if dir_path != self.project_path else ".",
            file_count=len(files),
            files=files,
            subdirectories=subdirs,
        )
    
    def analyze(self, max_depth: int = 2) -> ProjectReport:
        """
        分析项目结构
        
        Args:
            max_depth: 最大扫描深度（默认 2 层）
        
        Returns:
            项目分析报告
        """
        print(f"[PTA-EXT] 开始分析项目: {self.project_path}")
        print(f"[PTA-EXT] 扫描深度: {max_depth} 层")
        print(f"[PTA-EXT] 模式: 只读（不修改原项目）")
        print("-" * 60)
        
        directories = []
        total_files = 0
        total_size = 0
        file_type_dist = {}
        
        # 分析根目录
        root_info = self._analyze_directory(self.project_path, max_depth, 0)
        if root_info:
            directories.append(root_info)
            total_files += root_info.file_count
            for f in root_info.files:
                total_size += f.size_bytes
                file_type_dist[f.type] = file_type_dist.get(f.type, 0) + 1
        
        # 分析子目录（第一层）
        for item in self.project_path.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                dir_info = self._analyze_directory(item, max_depth, 1)
                if dir_info:
                    directories.append(dir_info)
                    total_files += dir_info.file_count
                    for f in dir_info.files:
                        total_size += f.size_bytes
                        file_type_dist[f.type] = file_type_dist.get(f.type, 0) + 1
        
        # 生成摘要
        summary = f"""
项目路径: {self.project_path}
分析时间: {datetime.now().isoformat()}
总目录数: {len(directories)}
总文件数: {total_files}
总大小: {self._format_size(total_size)}
文件类型分布: {dict(sorted(file_type_dist.items(), key=lambda x: x[1], reverse=True))}
        """.strip()
        
        self.report = ProjectReport(
            project_path=str(self.project_path),
            analysis_time=datetime.now().isoformat(),
            total_directories=len(directories),
            total_files=total_files,
            total_size_bytes=total_size,
            total_size_formatted=self._format_size(total_size),
            directories=directories,
            file_type_distribution=file_type_dist,
            summary=summary,
        )
        
        return self.report
    
    def print_report(self, report: ProjectReport):
        """打印报告"""
        print(f"\n{'='*60}")
        print(f"[PTA-EXT] 项目分析报告")
        print(f"{'='*60}")
        print(f"项目路径: {report.project_path}")
        print(f"分析时间: {report.analysis_time}")
        print(f"{'='*60}")
        print(f"\n总体统计:")
        print(f"  总目录数: {report.total_directories}")
        print(f"  总文件数: {report.total_files}")
        print(f"  总大小: {report.total_size_formatted}")
        
        print(f"\n文件类型分布:")
        for file_type, count in sorted(report.file_type_distribution.items(), key=lambda x: x[1], reverse=True):
            print(f"  {file_type}: {count} 个")
        
        print(f"\n目录详情:")
        for dir_info in report.directories:
            print(f"\n  📁 {dir_info.name}/")
            print(f"    路径: {dir_info.path}")
            print(f"    文件数: {dir_info.file_count}")
            print(f"    子目录: {dir_info.subdirectories}")
            
            # 显示前 5 个文件
            for file in dir_info.files[:5]:
                print(f"      📄 {file.name} ({file.size_formatted})")
            
            if len(dir_info.files) > 5:
                print(f"      ... 还有 {len(dir_info.files) - 5} 个文件")
        
        print(f"\n{'='*60}")
    
    def export_markdown(self, report: ProjectReport, output_path: Path):
        """导出 Markdown 报告"""
        content = f"""# 项目结构分析报告

> 生成工具: PTA-EXT 外部项目分析器
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
                content += "| 文件名 | 类型 | 大小 |\n"
                content += "|--------|------|------|\n"
                for file in dir_info.files:
                    content += f"| {file.name} | {file.type} | {file.size_formatted} |\n"
                content += "\n"
        
        content += "---\n\n"
        content += "> 报告生成完成，原项目未被修改\n"
        
        output_path.write_text(content, encoding="utf-8")
        print(f"\n[PTA-EXT] Markdown 报告已保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="PTA-EXT · 外部项目分析器")
    parser.add_argument("--path", "-p", required=True, help="要分析的项目路径")
    parser.add_argument("--output", "-o", help="JSON 输出路径")
    parser.add_argument("--markdown", "-m", help="Markdown 报告输出路径")
    parser.add_argument("--depth", "-d", type=int, default=2, help="扫描深度（默认 2）")
    args = parser.parse_args()
    
    project_path = Path(args.path)
    if not project_path.exists():
        print(f"[错误] 路径不存在: {project_path}")
        return 1
    
    if not project_path.is_dir():
        print(f"[错误] 不是目录: {project_path}")
        return 1
    
    # 分析项目
    analyzer = ProjectAnalyzer(project_path)
    report = analyzer.analyze(max_depth=args.depth)
    
    # 打印报告
    analyzer.print_report(report)
    
    # 保存 JSON
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[PTA-EXT] JSON 报告已保存: {output_path}")
    
    # 保存 Markdown
    if args.markdown:
        analyzer.export_markdown(report, Path(args.markdown))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
