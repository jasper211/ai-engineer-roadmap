#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：三个项目的候选文件筛选规则（按价值优先级排序，只读扫描）。

2026-07-16 跟 Jasper 对齐：不对三个项目867个候选文档无差别提炼，要按价值
分层、分批处理。EA项目（流程架构项目_jasper）自己已有明确的治理分层（见
其 CLAUDE.md），直接复用这套分层定义优先级；Rw权益项目/AI工程能力整改
项目暂无同等细致的分层，用更简单的关键字黑名单排除，具体分层留待跑出
结果后再跟 Jasper 一起细化。

铁律：本模块只读扫描文件系统（os.walk + 路径过滤），不写入/修改/移动任何
目标项目文件。
"""

import os
from pathlib import Path
from typing import List

from tools.file_diff import CONCEPT_EXTRACTION_EXTENSIONS
from tools import table_reader

# ── EA项目（流程架构项目_jasper）：按治理分层的处理优先级 ──
# 顺序即优先级：00治理 → 03发布成果 → 08任务与跟进 → 01原始材料 → 02过程成果
# （规则分析（Jasper）+ 2026-07-20起新增的其余02层共享业务维度目录）。
# 04-07（Skill库/Agent库/Scripts库/Memory）是代码资产，非知识内容，不在其列。
#
# 2026-07-20 Jasper范围裁定：此前02层只扫"规则分析（Jasper）"这一个Jasper
# 个人工作区子目录，其余Terresa等人也在更新的共享业务维度目录（L3流程库/
# 价值流建模/映射分析等）一直被跳过——真实触发场景：Terresa更新了L3流程库的
# 流程蓝图，OB完全检测不到。现在覆盖到全部02层子目录（在"规则分析（Jasper）"
# 之后，即02层内部仍是"Jasper个人工作区优先，共享目录其次"，跟00/03/08/01
# 这几个更权威的层比仍然排在最后，没有改变整体"权威层优先"的原则）。
EA_LAYER_PRIORITY = [
    "00_治理与元模型",
    "03_发布成果-交付物",
    "08_任务与跟进",
    "01_原始材料-外部导入",
    "02_过程成果-工作产出/规则分析（Jasper）",
    "02_过程成果-工作产出/L3流程库",
    "02_过程成果-工作产出/映射分析",
    "02_过程成果-工作产出/KPI穿透",
    "02_过程成果-工作产出/岗位族设计",
    "02_过程成果-工作产出/校验与上下文",
    "02_过程成果-工作产出/校验与评估",
    "02_过程成果-工作产出/价值流建模",
    "02_过程成果-工作产出/数据库",
    "02_过程成果-工作产出/组织重组",
    "02_过程成果-工作产出/价值链L1建模",
    "02_过程成果-工作产出/L4-核心交付物",
    "02_过程成果-工作产出/L2业务能力",
]

# 通用归档/废弃关键字——即便在优先层内，命中这些关键字的子目录/文件也跳过
# （比如 00/03 层内部也可能有"_归档"这类子目录）。"历史遗留"是2026-07-16
# 跑02层规则分析dry-run时发现的真实漏网案例：`_历史遗留（5月）/`75个文件，
# 名字含义等同于已被取代的旧内容，但此前的黑名单没覆盖这个说法。
ARCHIVE_KEYWORDS = ("归档", "旧版", "废弃", "backup", "bak", "历史遗留")


def _is_archived(name: str) -> bool:
    lname = name.lower()
    return any(kw.lower() in lname for kw in ARCHIVE_KEYWORDS)


def _walk_candidates(base_dir: Path) -> List[Path]:
    """在 base_dir 下递归找候选文件（.md/.docx/.txt），跳过隐藏目录和
    命中归档关键字的目录/文件。返回绝对路径列表，按 os.walk 的自然顺序
    （同一层级内不额外排序，保持文件系统原有的相对次序）。

    2026-07-21 新增版本去重：真实复现过（L3流程库/下14组文件），同一份
    文档的多个历史版本（如"流程蓝图_L3-SSVA..._V1.1.md"和"..._V1.2.md"）
    会同时躺在文件夹里，此前逐个当独立文档提炼，产出重复甚至冲突的原子，
    旧版本的过时内容原样留在vault里没人清理。复用tools/table_reader.py
    已经验证过的版本分组逻辑（按文件名版本号分组，只取最新），从只给表格
    用扩展成文档候选也用同一套规则——按目录分组（不同目录下同名文件不放
    一组，避免跨目录误判），组内保留原有相对顺序，只去掉每组内非最新的
    版本。"""
    results = []
    if not base_dir.exists():
        return results
    by_dir: dict = {}
    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not _is_archived(d)]
        dir_files = []
        for name in filenames:
            if name.startswith("."):
                continue
            if _is_archived(name):
                continue
            ext = Path(name).suffix.lower()
            if ext not in CONCEPT_EXTRACTION_EXTENSIONS:
                continue
            dir_files.append(Path(dirpath) / name)
        if dir_files:
            by_dir[dirpath] = dir_files

    for dirpath, dir_files in by_dir.items():
        latest_only = table_reader.group_latest_versions(dir_files)
        latest_set = set(latest_only)
        # group_latest_versions 内部按 base_name 分组、组间无序返回，这里
        # 按原始 dir_files 的顺序重新过滤，保持"文件系统自然顺序"这条既有约定
        results.extend(f for f in dir_files if f in latest_set)
    return results


def get_ea_candidates(project_root: str) -> List[str]:
    """EA项目专用：按 EA_LAYER_PRIORITY 顺序遍历，返回相对 project_root 的
    路径列表（按优先级分层排序，同层内按文件系统自然顺序）。

    2026-07-20 Jasper范围裁定新增：03_发布成果-交付物层的xlsx/csv权威数据表
    也纳入候选（此前 CONCEPT_EXTRACTION_EXTENSIONS 只认.md/.docx/.txt，表格
    完全不在扫描范围内——真实触发场景：Terresa更新了价值节点清单/KPI映射表，
    OB却检测不到变化）。只在03层加表格候选，不是全项目通用规则——01/02/08层
    的表格文件（多是草稿/中间数据）暂不纳入，避免把还没定稿的数据当权威内容
    提炼。按tools/table_reader.list_table_candidates()做版本分组只取最新版本，
    避免同一张表的历史版本被重复提炼。"""
    root = Path(project_root)
    ordered_relative: List[str] = []
    for layer in EA_LAYER_PRIORITY:
        layer_path = root / layer
        for abs_path in _walk_candidates(layer_path):
            ordered_relative.append(str(abs_path.relative_to(root)))
        if layer == "03_发布成果-交付物":
            for table_path in table_reader.list_table_candidates(str(root), subdir=layer):
                ordered_relative.append(str(table_path.relative_to(root)))
    return ordered_relative


def get_generic_candidates(project_root: str) -> List[str]:
    """Rw权益项目/AI工程能力整改项目专用：全目录扫描 + 归档关键字黑名单排除，
    暂无分层优先级（同一层级/顺序按文件系统自然顺序）。"""
    root = Path(project_root)
    return [str(p.relative_to(root)) for p in _walk_candidates(root)]


def get_candidates(project_name: str, project_root: str) -> List[str]:
    """按项目名分发到对应的筛选函数。project_name 是 agent.py 里
    PROJECT_ROOTS 映射用的同一套项目名。"""
    if project_name == "EA流程架构项目":
        return get_ea_candidates(project_root)
    return get_generic_candidates(project_root)


# ── authority_layer 派生（2026-07-21新增）──
# 背景：vault里EA项目的原子有authority_layer字段（00_治理/01_原始/02_草稿/
# 03_已锁定/08_任务跟进），这套值本来就是EA_LAYER_PRIORITY那几个源目录名的
# 治理含义——但当前批量提炼流程（concept_note_extraction.py.write_atom()）
# 从没写过这个字段，是因为没人把"源文件在哪个分层目录下"这条已有信息接到
# 写入逻辑上，不是需要新设计一套判断规则。这里只是把EA_LAYER_PRIORITY的
# 目录名映射成atom frontmatter用的authority_layer取值，纯字符串前缀匹配，
# 不需要LLM判断。
EA_AUTHORITY_LAYER_MAP = {
    "00_治理与元模型": "00_治理",
    "03_发布成果-交付物": "03_已锁定",
    "08_任务与跟进": "08_任务跟进",
    "01_原始材料-外部导入": "01_原始",
    # 02_过程成果-工作产出 下全部子目录（规则分析（Jasper）/L3流程库/映射分析等）
    # 统一归"02_草稿"——这些都是过程中的工作产出，还没走到03层锁定发布
    "02_过程成果-工作产出": "02_草稿",
}

# Rw权益项目/Jasper AI协同经验引擎目前没有EA项目这套治理分层（project_filters
# 顶部注释已说明："暂无同等细致的分层，用更简单的关键字黑名单排除"）——在这两个
# 项目自己的分层方案定下来之前（需要Jasper拍板，见路线图"待确认事项"），统一
# 给"02_草稿"这个中性默认值，不虚构一个假的权威判断。等这两个项目也有分层
# 定义后，这里要改成按各自项目的规则派生，不能一直用这个默认值。
GENERIC_PROJECT_DEFAULT_AUTHORITY_LAYER = "02_草稿"


def derive_authority_layer(project_name: str, source_relative_path: str) -> str:
    """给定项目名+源文件相对路径（write_atom()里source字段的值），返回这个
    原子应该写入的authority_layer。EA项目按源文件所在分层目录前缀匹配；其余
    项目暂时统一返回默认值（见上方GENERIC_PROJECT_DEFAULT_AUTHORITY_LAYER的
    说明，是已知的临时简化，不是最终方案）。"""
    if project_name == "EA流程架构项目":
        for prefix, layer in EA_AUTHORITY_LAYER_MAP.items():
            if source_relative_path.startswith(prefix):
                return layer
        # 理论上不会走到这里——candidates本来就是从EA_LAYER_PRIORITY这几个
        # 目录下筛出来的，source只能是这几个前缀之一；保留兜底避免未来
        # EA_LAYER_PRIORITY改了但这里忘了同步时直接崩溃
        return "02_草稿"
    return GENERIC_PROJECT_DEFAULT_AUTHORITY_LAYER
