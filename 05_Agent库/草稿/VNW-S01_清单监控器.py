#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VNW-S01 · 价值节点清单监控器
功能：监控价值节点清单 Excel 文件变更，检测新增/修改/删除的节点
运行：python3 vnw_s01_monitor.py [--watch] [--check]
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ============================================================
# 配置区
# ============================================================

# 生产环境只读路径（监控目标）
WATCH_DIRS = [
    Path("/Users/zhaoqitrenda.cn/Desktop/流程架构项目_jasper/02_过程成果-工作产出/规则分析（Jasper）/01_价值节点清单"),
    Path("/Users/zhaoqitrenda.cn/Desktop/自动化测试（PAY域）"),
]

# 状态文件路径（实验环境可写）
STATE_FILE = Path(__file__).parent / ".vnw_state.json"

# 监控文件模式
WATCH_PATTERNS = [
    "D1_价值节点清单_*.xlsx",
    "D1_价值节点清单_V*.xlsx",
]

# ============================================================


class ValueNodeMonitor:
    """价值节点清单文件监控器"""
    
    def __init__(self, watch_dirs: List[Path], state_file: Path):
        self.watch_dirs = [d for d in watch_dirs if d.exists()]
        self.state_file = state_file
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """加载上次监控状态"""
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"version": 1, "last_check": None, "files": {}}
    
    def _save_state(self):
        """保存当前监控状态"""
        self.state["last_check"] = datetime.now().isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def _compute_hash(self, file_path: Path) -> str:
        """计算文件哈希（mtime + size）"""
        stat = file_path.stat()
        return hashlib.md5(f"{stat.st_mtime}:{stat.st_size}".encode()).hexdigest()
    
    def _find_target_files(self) -> List[Path]:
        """查找所有监控目标文件"""
        candidates = []
        for watch_dir in self.watch_dirs:
            for pattern in WATCH_PATTERNS:
                candidates.extend(watch_dir.glob(pattern))
        
        # 去重并按修改时间排序（最新的在前）
        unique = {}
        for f in candidates:
            if f.name not in unique or f.stat().st_mtime > unique[f.name].stat().st_mtime:
                unique[f.name] = f
        
        return sorted(unique.values(), key=lambda p: p.stat().st_mtime, reverse=True)
    
    def check(self) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        检查文件变更
        返回: (新增列表, 修改列表, 删除列表)
        """
        current_files = self._find_target_files()
        current_map = {str(f.resolve()): f for f in current_files}
        previous_map = self.state.get("files", {})
        
        created = []
        modified = []
        deleted = []
        
        # 检查新增和修改
        for file_path in current_files:
            path_str = str(file_path.resolve())
            file_hash = self._compute_hash(file_path)
            stat = file_path.stat()
            
            if path_str not in previous_map:
                # 新增文件
                created.append({
                    "path": path_str,
                    "name": file_path.name,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "hash": file_hash,
                })
            elif previous_map[path_str].get("hash") != file_hash:
                # 修改文件
                modified.append({
                    "path": path_str,
                    "name": file_path.name,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "hash": file_hash,
                    "previous_mtime": previous_map[path_str].get("mtime"),
                })
            
            # 更新状态
            self.state["files"][path_str] = {
                "name": file_path.name,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "hash": file_hash,
            }
        
        # 检查删除
        for path_str in previous_map:
            if path_str not in current_map:
                deleted.append({
                    "path": path_str,
                    "name": previous_map[path_str].get("name"),
                    "previous_mtime": previous_map[path_str].get("mtime"),
                })
                del self.state["files"][path_str]
        
        self._save_state()
        return created, modified, deleted
    
    def watch(self, interval: int = 60):
        """持续监控模式（需 watchdog）"""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            print("[错误] watchdog 未安装，请运行: pip install watchdog")
            print("[回退] 使用 --check 模式手动检查")
            sys.exit(1)
        
        class ExcelEventHandler(FileSystemEventHandler):
            def __init__(self, monitor):
                self.monitor = monitor
            
            def on_modified(self, event):
                if event.is_directory:
                    return
                if event.src_path.endswith('.xlsx'):
                    print(f"[监控] 文件修改: {event.src_path}")
                    self._handle_change()
            
            def on_created(self, event):
                if event.is_directory:
                    return
                if event.src_path.endswith('.xlsx'):
                    print(f"[监控] 文件新增: {event.src_path}")
                    self._handle_change()
            
            def _handle_change(self):
                created, modified, deleted = self.monitor.check()
                self.monitor._print_report(created, modified, deleted)
        
        print(f"[VNW-S01] 启动监控模式，间隔: {interval}s")
        print(f"[VNW-S01] 监控目录: {[str(d) for d in self.watch_dirs]}")
        
        event_handler = ExcelEventHandler(self)
        observer = Observer()
        
        for watch_dir in self.watch_dirs:
            observer.schedule(event_handler, str(watch_dir), recursive=False)
        
        observer.start()
        
        try:
            while True:
                import time
                time.sleep(interval)
        except KeyboardInterrupt:
            observer.stop()
            print("\n[VNW-S01] 监控已停止")
        
        observer.join()
    
    def _print_report(self, created: List[Dict], modified: List[Dict], deleted: List[Dict]):
        """打印变更报告"""
        print(f"\n{'='*60}")
        print(f"[VNW-S01] 价值节点清单变更报告")
        print(f"{'='*60}")
        print(f"检查时间: {datetime.now().isoformat()}")
        print(f"监控目录: {len(self.watch_dirs)} 个")
        print(f"当前文件: {len(self.state.get('files', {}))} 个")
        print(f"{'='*60}")
        
        if created:
            print(f"\n📁 新增文件 ({len(created)} 个):")
            for f in created:
                print(f"  + {f['name']}")
                print(f"    大小: {f['size']:,} bytes")
                print(f"    修改: {f['mtime']}")
        
        if modified:
            print(f"\n🔄 修改文件 ({len(modified)} 个):")
            for f in modified:
                print(f"  ~ {f['name']}")
                print(f"    大小: {f['size']:,} bytes")
                print(f"    修改: {f['mtime']}")
                if f.get('previous_mtime'):
                    print(f"    上次: {f['previous_mtime']}")
        
        if deleted:
            print(f"\n🗑 删除文件 ({len(deleted)} 个):")
            for f in deleted:
                print(f"  - {f['name']}")
        
        if not created and not modified and not deleted:
            print("\n✅ 无变更，清单状态稳定")
        
        print(f"\n{'='*60}")
    
    def run(self, mode: str = "check"):
        """运行监控器"""
        if mode == "check":
            print("[VNW-S01] 执行单次检查...")
            created, modified, deleted = self.check()
            self._print_report(created, modified, deleted)
            
            # 返回是否有变更（用于上游调用判断）
            return len(created) > 0 or len(modified) > 0 or len(deleted) > 0
        
        elif mode == "watch":
            self.watch()
        
        else:
            print(f"[错误] 未知模式: {mode}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="VNW-S01 · 价值节点清单监控器")
    parser.add_argument("--check", action="store_true", help="单次检查模式（默认）")
    parser.add_argument("--watch", action="store_true", help="持续监控模式")
    parser.add_argument("--state", type=str, default=str(STATE_FILE), help="状态文件路径")
    args = parser.parse_args()
    
    monitor = ValueNodeMonitor(WATCH_DIRS, Path(args.state))
    
    if args.watch:
        monitor.run("watch")
    else:
        has_changes = monitor.run("check")
        sys.exit(0 if not has_changes else 1)


if __name__ == "__main__":
    main()
