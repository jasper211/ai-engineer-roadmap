#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：Rw 项目专用数据格式约定（跟踪台账文件名/章程文件名/blocker 字段判断）

跨 skills/project_dashboard.py 和 skills/project_intelligence.py 共用。这两个
技能各自独立解析同一套 Rw 项目 CSV 台账格式，之前各自维护一份判断逻辑——
结果同一条真实数据里的坑，两边各踩了一次才被发现：
  1. blocker 字段"无(说明)"格式被 `!= "无"` 精确比较误判成"有阻塞"。
  2. 跟踪台账 CSV 的查找只检查 project_root 的直属文件，真实项目里这些 CSV
     实际嵌套在 07_项目立项启动/ 这样的子目录下，指向项目真正的根目录时两边
     都失效（--intel 悄悄退回通用解析器，--dashboard 直接报错）。
抽成共享模块，这条 Rw 数据格式的规则以后只用改一处，不会再出现同一个 bug
在两个文件里分别复现一次的情况。
"""

from pathlib import Path
from typing import List, Optional

# 按优先级排列（最新版本在前）：真实项目里可能只存在某一个版本
TRACKING_FILES: List[str] = [
    "52_Phase0日常执行跟踪台账_v0.2.csv",
    "52_Phase0日常执行跟踪台账_v0.1.csv",
    "49_Phase0执行台账_v0.1.csv",
]
CHARTER_FILE = "01_项目章程_Project_Charter.md"


def find_tracking_csv(project_root: Path) -> Optional[Path]:
    """在项目目录下递归查找 Rw 跟踪台账 CSV（调用方可能传项目的真正根目录，
    也可能已经传了台账所在的子目录——两种情况都能找到），按 TRACKING_FILES
    的优先级顺序找同名文件；都找不到返回 None。

    真实项目里同一个文件名可能存在不止一份拷贝——比如台账的正式工作目录
    （07_项目立项启动/）之外，另一个 Agent（OB 巡检）自己的工作区里也保存了
    一份同名的"启动基线"快照（08_RW_OB_工作区/01_启动基线/），内容是更早
    某个时间点冻结的旧版本。第一版实现只取 rglob 结果的第一项，遇到重名文件
    会不确定地选中哪一份（取决于文件系统遍历顺序），真实验证时就选中了那份
    更旧的基线快照，导致统计数字跟直接指向正确子目录时的结果对不上。
    改成：同名文件有多份时，选最近修改过的那一份——正在被维护、更新的台账
    理应是最近修改时间最新的，冻结的基线快照不会再被改动。"""
    project_root = Path(project_root)
    for filename in TRACKING_FILES:
        matches = list(project_root.rglob(filename))
        if matches:
            return max(matches, key=lambda p: p.stat().st_mtime)
    return None


def find_rw_data_dir(project_root: Path) -> Optional[Path]:
    """跟踪 CSV 所在的目录——章程/日报文件通常也放在同一层（真实项目里
    是 07_项目立项启动/）。找不到跟踪 CSV 时返回 None。"""
    csv_path = find_tracking_csv(project_root)
    return csv_path.parent if csv_path else None


def is_rw_project(project_root: Path) -> bool:
    """项目目录（或其子目录）下是否存在 Rw 特征跟踪台账 CSV。"""
    return find_tracking_csv(project_root) is not None


def blocker_is_active(blocker: str) -> bool:
    """判断 blocker 字段是否代表真实存在的阻塞，不是简单看"非空"。真实 Rw
    台账里"无阻塞"常见写法不只是精确的一个"无"字，还有"无(Roy财务口径已确认
    20260708;服务范围Amanda已确认)"这种"无+补充说明"的格式——用
    `blocker != "无"` 做精确字符串比较，会把这类解释性文字误判成"有阻塞"。
    改成：去空白后以"无"开头就算没有阻塞，不管后面有没有括号说明。"""
    return bool(blocker) and not blocker.strip().startswith("无")
