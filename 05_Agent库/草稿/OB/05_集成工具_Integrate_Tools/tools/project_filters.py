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
from typing import List, Optional, Tuple, Union

from tools.file_diff import CONCEPT_EXTRACTION_EXTENSIONS
from tools import table_reader

# ── EA项目（流程架构项目_jasper）：按治理分层的处理优先级 ──
# 2026-07-21 Jasper范围收缩裁定（推翻2026-07-20的"全部02层子目录覆盖"）：
# 前一版把02层11个共享业务维度目录全量纳入，跟entity_ref矛盾扫描/251个
# 结构孤立原子审查两轮真实数据对上——过程性/任务跟踪类文档（08层、02层的
# 访谈/信号提取过程文件）是矛盾和噪音的主要来源（M3核心介入点88条vs126条、
# KPI企业目录32行vs43行这类"进行中决策快照"互相打架），根子是"边写边提炼"。
# 改为只收"成型的方法论文档和结果文档"这几个具体子目录，其余（含整个08层、
# 01层除M-01/M-88外的其余M编号、02层规则分析下的过程性子文件夹如访谈/信号
# 提取/EA_P0等）暂不取，需要时走人工指令临时新增，不再默认全量扫描。
# 04-07（Skill库/Agent库/Scripts库/Memory）是代码资产，非知识内容，不在其列。
# 2026-07-21二次收窄：Jasper纠正上一版白名单，去掉概念笔记（本来就是空
# 目录，无实际影响）、治理日志（166个原子）、M-88_mark日常输出（661个
# 原子）——这三个连同上一版已排除的目录，一并归入"暂不取"。
#
# 2026-07-21三次调整：Jasper把"03_访谈准备与执行"下两个结果型子文件夹
# （规则空白地图/熔断节点补建清单，均为已定稿的分域结果文档，跟同级的
# 访谈过程文件不是一回事）、"04_规则与GAP产出"（规则/Gap清单）、以及
# "02_信号提取基线/提取合集校准"里"XX域_价值节点信号提取基线"这一类
# 结果文件重新纳入白名单。
#
# 每一项是 (路径, 文件名必须包含的子串或None)——大部分是"整个子目录都要"
# 用None；"提取合集校准"这一个例外：目录里混着三种文件（域_价值节点信号
# 提取基线/任务包_XX域信号提取基线/任务包_XX域规则空白地图与熔断清单），
# Jasper只要第一种，用文件名子串过滤而不是整个目录搬进来，避免把还没
# 定稿的任务包类文件也带进来。
EA_LAYER_PRIORITY: List[Union[str, Tuple[str, Optional[str]]]] = [
    "00_治理与元模型/项目章程",
    "01_原始材料-外部导入/M-01_方法论与标准",
    "02_过程成果-工作产出/规则分析（Jasper）/05_SOP",
    "02_过程成果-工作产出/规则分析（Jasper）/Agent规划与搭建",
    "02_过程成果-工作产出/规则分析（Jasper）/Agent与Skill体系",
    "02_过程成果-工作产出/规则分析（Jasper）/03_访谈准备与执行/规则空白地图",
    "02_过程成果-工作产出/规则分析（Jasper）/03_访谈准备与执行/熔断节点补建清单",
    "02_过程成果-工作产出/规则分析（Jasper）/04_规则与GAP产出",
    ("02_过程成果-工作产出/规则分析（Jasper）/02_信号提取基线/提取合集校准", "价值节点信号提取基线"),
    "03_发布成果-交付物/权威数据",
]


def _layer_path_and_filter(layer: Union[str, Tuple[str, Optional[str]]]) -> Tuple[str, Optional[str]]:
    """兼容EA_LAYER_PRIORITY里普通字符串项和(路径,文件名过滤)元组项两种写法。"""
    if isinstance(layer, tuple):
        return layer
    return layer, None

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

    2026-07-21更新：表格候选(xlsx/csv)不再只在"03_发布成果-交付物"这一个
    硬编码层生效——范围收缩到具体白名单子目录后，M-01_方法论与标准/M-88_
    mark日常输出/Agent与Skill体系这几个新纳入的目录里也有真实xlsx/csv文件
    （真实盘点过：约19个不重复文件），之前的写法会让这些文件既不走表格路径
    （层级判断只认03层）也不走文档路径（xlsx/csv不在CONCEPT_EXTRACTION_
    EXTENSIONS里），完全没人提炼。现在对EA_LAYER_PRIORITY里每一层都尝试
    list_table_candidates()——函数本身对没有xlsx/csv的目录直接返回空列表，
    不会因为多扫几层就产出错误候选，成本可忽略。"""
    root = Path(project_root)
    ordered_relative: List[str] = []
    for layer in EA_LAYER_PRIORITY:
        path, name_filter = _layer_path_and_filter(layer)
        layer_path = root / path
        for abs_path in _walk_candidates(layer_path):
            if name_filter and name_filter not in abs_path.name:
                continue
            ordered_relative.append(str(abs_path.relative_to(root)))
        for table_path in table_reader.list_table_candidates(str(root), subdir=path):
            if name_filter and name_filter not in table_path.name:
                continue
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
