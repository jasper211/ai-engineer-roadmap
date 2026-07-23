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
# 2026-07-21四次调整：Jasper移除"03_发布成果-交付物/权威数据"——理由：这批
# 表格文件本身是多版本混合、大部分内容其实是过程性数据（不是"结果文档"这个
# 白名单原则本来要选的东西），且长期方案是接数据库直连（等EA的数据库落地后，
# 直接以数据库内容作为原子提炼的权威源，而不是数据库导出的中间CSV/xlsx快照）
# ——跟PDF支持一样列为后续任务，不是这次要做的事，先从白名单去掉。
#
# 2026-07-22五次调整（Jasper逐项纠正）：
# - 整个去掉"Agent规划与搭建"
# - "Agent与Skill体系"不再整体收录，改成只要子文件夹"Agent执行机制梳理"
#   （30个分Agent文件+索引，是Agent执行治理机制这个主题本身；同级的候选
#   Agent目录/L4封装可行性评估/岗位族关系蓝图这些是别的主题，不要）
# - "规则空白地图"加文件名过滤"第一层"，排除掉混进去的
#   "任务包_4域B标签模板化返工_v1.0.md"（不是"XX_第一层_规则空白地图"
#   这个统一格式的域文件）
# - "熔断节点补建清单"不用加过滤——已有的版本分组逻辑（group_latest_
#   versions，按"域前缀_熔断节点补建清单"分组）已经能把12个文件（部分域
#   有v1.0/v1.1/v1.2多版本）正确收窄到8个域各自的最新版，不需要额外处理
# - "04_规则与GAP产出"加文件名过滤"清单"（排除掉6份"XX_三方沟通报告"，
#   只留"规则清单_XX"和"Gap清单_XX"这两类）+ 不要CSV（只要md）——CSV这类
#   表格候选默认会对每一层都尝试，这里显式关掉，靠三元组第三项实现
#
# 每一项是 (路径, 文件名必须包含的子串或None) 或 (路径, 文件名过滤,
# 是否也扫表格候选)——两元组默认扫表格候选（True），需要显式排除csv/xlsx
# 时才用三元组传False。
EA_LAYER_PRIORITY: List[Union[str, Tuple[str, Optional[str]], Tuple[str, Optional[str], bool]]] = [
    "00_治理与元模型/项目章程",
    "01_原始材料-外部导入/M-01_方法论与标准",
    "02_过程成果-工作产出/规则分析（Jasper）/05_SOP",
    "02_过程成果-工作产出/规则分析（Jasper）/Agent与Skill体系/Agent执行机制梳理",
    ("02_过程成果-工作产出/规则分析（Jasper）/03_访谈准备与执行/规则空白地图", "第一层"),
    "02_过程成果-工作产出/规则分析（Jasper）/03_访谈准备与执行/熔断节点补建清单",
    ("02_过程成果-工作产出/规则分析（Jasper）/04_规则与GAP产出", "清单", False),
    ("02_过程成果-工作产出/规则分析（Jasper）/02_信号提取基线/提取合集校准", "价值节点信号提取基线"),
]


def _layer_path_and_filter(layer) -> Tuple[str, Optional[str], bool]:
    """兼容EA_LAYER_PRIORITY里三种写法：纯路径字符串 / (路径,文件名过滤) /
    (路径,文件名过滤,是否扫表格候选)。"""
    if isinstance(layer, tuple):
        if len(layer) == 3:
            return layer
        return layer[0], layer[1], True
    return layer, None, True

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


# 2026-07-22新增：Jasper AI协同经验引擎白名单收窄——只保留"三大主Agent
# 体系架构"（文件名过滤，_walk_candidates内置的版本分组会自动只留最新版，
# 不用额外处理）+ Mark_AI经验合集学习参考（整个文件夹）。这个项目的根目录
# 已经在agent.py.PROJECT_ROOTS里上移到"Jasper AI协同经验引擎"这一级
# （原来只到"AI工程能力整改项目"子目录，够不到跟它平级的Mark_AI经验合集
# 学习参考），所以这里的路径都要带上"AI工程能力整改项目/"前缀。
JASPER_ENGINE_LAYER_PRIORITY: List[Union[str, Tuple[str, Optional[str]]]] = [
    ("AI工程能力整改项目/05_Agent库/草稿", "三大主Agent体系架构"),
    "Mark_AI经验合集学习参考",
]


def _get_whitelisted_candidates(project_root: str, layer_priority: List[Union[str, Tuple[str, Optional[str]]]]) -> List[str]:
    """按给定的分层白名单顺序遍历，返回相对 project_root 的路径列表——
    EA项目和Jasper AI协同经验引擎共用这套逻辑，区别只是各自的白名单列表
    不同（EA_LAYER_PRIORITY / JASPER_ENGINE_LAYER_PRIORITY）。

    表格候选(xlsx/csv)不限定在某一个特定层——对白名单里每一层都尝试
    list_table_candidates()，函数本身对没有xlsx/csv的目录直接返回空列表，
    不会因为多扫几层就产出错误候选，成本可忽略。"""
    root = Path(project_root)
    ordered_relative: List[str] = []
    for layer in layer_priority:
        path, name_filter, include_tables = _layer_path_and_filter(layer)
        layer_path = root / path
        for abs_path in _walk_candidates(layer_path):
            if name_filter and name_filter not in abs_path.name:
                continue
            ordered_relative.append(str(abs_path.relative_to(root)))
        if not include_tables:
            continue
        for table_path in table_reader.list_table_candidates(str(root), subdir=path):
            if name_filter and name_filter not in table_path.name:
                continue
            ordered_relative.append(str(table_path.relative_to(root)))
    return ordered_relative


def get_ea_candidates(project_root: str) -> List[str]:
    """EA项目专用：按 EA_LAYER_PRIORITY 白名单遍历。"""
    return _get_whitelisted_candidates(project_root, EA_LAYER_PRIORITY)


def get_jasper_engine_candidates(project_root: str) -> List[str]:
    """Jasper AI协同经验引擎专用：按 JASPER_ENGINE_LAYER_PRIORITY 白名单遍历。"""
    return _get_whitelisted_candidates(project_root, JASPER_ENGINE_LAYER_PRIORITY)


def get_generic_candidates(project_root: str) -> List[str]:
    """Rw权益项目专用（目前唯一还在用这条通用路径的项目）：全目录扫描 +
    归档关键字黑名单排除，暂无分层优先级（同一层级/顺序按文件系统自然
    顺序）。"""
    root = Path(project_root)
    return [str(p.relative_to(root)) for p in _walk_candidates(root)]


def get_candidates(project_name: str, project_root: str) -> List[str]:
    """按项目名分发到对应的筛选函数。project_name 是 agent.py 里
    PROJECT_ROOTS 映射用的同一套项目名。"""
    if project_name == "EA流程架构项目":
        return get_ea_candidates(project_root)
    if project_name == "Jasper AI协同经验引擎":
        return get_jasper_engine_candidates(project_root)
    return get_generic_candidates(project_root)


# ── authority_layer 派生（2026-07-21新增，2026-07-22修正）──
# 背景：vault里EA项目的原子有authority_layer字段（00_治理/01_原始/02_草稿/
# 02_定稿/03_已锁定/08_任务跟进），本来是EA_LAYER_PRIORITY那几个源目录名的
# 治理含义——最初按"02_过程成果-工作产出"整个顶层目录统一映射"02_草稿"，
# 这在02层还覆盖11个共享业务维度目录（含访谈/信号提取这类真正的过程文件）
# 时是对的。但2026-07-21范围五次收窄后，02层白名单只剩5个Jasper明确挑出来
# 的"结果性"子文件夹（SOP/Agent执行机制梳理/规则空白地图/熔断节点补建
# 清单/规则与GAP产出/提取合集校准）——这些是Jasper选进白名单的理由就是
# "已经是定稿结果，不是过程文件"，继续统一贴"02_草稿"会跟白名单本身的
# 筛选逻辑自相矛盾，且直接误导下游Agent读取的信任标注（检索层会把
# authority_layer显式标成信任徽章）。改为更细粒度匹配：白名单里这几个
# 结果性子目录单独映射"02_定稿"（不是草稿，但也没走完Mark审核锁定进03层
# 的正式晋升流程，跟"03_已锁定"区分开），比"02_过程成果-工作产出"这个
# 粗前缀更早匹配到，才会生效（dict在Python 3.7+保证插入顺序，靠这个
# 保证细粒度条目排在粗前缀条目之前）。
EA_AUTHORITY_LAYER_MAP = {
    "00_治理与元模型": "00_治理",
    "03_发布成果-交付物": "03_已锁定",
    "08_任务与跟进": "08_任务跟进",
    "01_原始材料-外部导入": "01_原始",
    # 02层白名单里的5个结果性子目录——比下面的粗前缀更细，必须排在前面
    "02_过程成果-工作产出/规则分析（Jasper）/05_SOP": "02_定稿",
    "02_过程成果-工作产出/规则分析（Jasper）/Agent与Skill体系/Agent执行机制梳理": "02_定稿",
    "02_过程成果-工作产出/规则分析（Jasper）/03_访谈准备与执行/规则空白地图": "02_定稿",
    "02_过程成果-工作产出/规则分析（Jasper）/03_访谈准备与执行/熔断节点补建清单": "02_定稿",
    "02_过程成果-工作产出/规则分析（Jasper）/04_规则与GAP产出": "02_定稿",
    "02_过程成果-工作产出/规则分析（Jasper）/02_信号提取基线/提取合集校准": "02_定稿",
    # 02_过程成果-工作产出 下其余子目录（理论上不会再命中——candidates已经
    # 从白名单筛过，保留这条纯做兜底，避免白名单以后又加了新02层子目录、
    # 这里忘了同步细粒度映射时直接崩溃或误标）
    "02_过程成果-工作产出": "02_草稿",
}

# ── 业务域(domain) 派生（2026-07-22新增）──
# 背景：白名单收窄后的语料本质是"8个业务域 × {SOP/规则空白地图/熔断清单/
# 规则清单/GAP清单/提取基线}"这样一个矩阵结构，业务域是现在语料的核心
# 组织维度（真实盘点过：45.2%的原子文件名里能直接匹配到域前缀），但之前
# schema没有专门字段承载，只能藏在source路径的文件名里，检索/枢纽聚类都
# 用不上这个信号。纯字符串匹配源文件名，不需要LLM判断。
EA_DOMAINS = ["PAY", "HR", "FA", "KA", "EQ", "INS", "PARTNER", "TREASURY"]


def derive_domain(source_relative_path: str) -> str:
    """从source路径的文件名里匹配业务域前缀，匹配不到返回"（无）"（不是
    每个白名单来源都有域结构——比如00_治理与元模型/项目章程、01_原始材料
    -外部导入/M-01_方法论与标准这两个来源就没有域概念，如实标"无"而不是
    编一个假域）。大小写不敏感匹配文件名（不匹配整个路径——路径里
    "规则分析（Jasper）"这类目录名可能意外命中域缩写，只信文件名更准）。"""
    filename = source_relative_path.split("/")[-1].upper()
    for domain in EA_DOMAINS:
        if domain in filename:
            return domain
    return "（无）"

# 2026-07-22新增：Jasper AI协同经验引擎白名单收窄到2项后，同样不该再用
# "02_草稿"这个通用默认值——三大主Agent体系架构是架构定义文档（治理性质），
# Mark_AI经验合集学习参考是Mark沉淀的方法论源材料（跟EA的01_原始材料性质
# 类似），两者都不是"草稿"。用子串匹配而不是前缀匹配——这个项目的根目录
# 2026-07-22从"AI工程能力整改项目"上移到"Jasper AI协同经验引擎"，改前
# 提炼的原子source字段是老根目录相对路径（不带"AI工程能力整改项目/"
# 前缀），改后新提炼的原子source带这个前缀，前缀匹配会漏判老格式，子串
# 匹配对两种格式都有效。
JASPER_ENGINE_AUTHORITY_LAYER_MAP = {
    "三大主Agent体系架构": "00_治理",
    "Mark_AI经验合集学习参考": "01_原始",
}

# Rw权益项目目前没有EA项目这套治理分层（project_filters顶部注释已说明：
# "暂无同等细致的分层，用更简单的关键字黑名单排除"）——项目自己的分层方案
# 定下来之前，统一给"02_草稿"这个中性默认值，不虚构一个假的权威判断。
GENERIC_PROJECT_DEFAULT_AUTHORITY_LAYER = "02_草稿"


def derive_authority_layer(project_name: str, source_relative_path: str) -> str:
    """给定项目名+源文件相对路径（write_atom()里source字段的值），返回这个
    原子应该写入的authority_layer。EA项目/Jasper AI协同经验引擎按各自的
    白名单映射表做前缀匹配；Rw权益项目暂时统一返回默认值（见上方
    GENERIC_PROJECT_DEFAULT_AUTHORITY_LAYER的说明，是已知的临时简化）。"""
    if project_name == "Jasper AI协同经验引擎":
        for keyword, layer in JASPER_ENGINE_AUTHORITY_LAYER_MAP.items():
            if keyword in source_relative_path:
                return layer
        return "01_原始"
    if project_name == "EA流程架构项目":
        for prefix, layer in EA_AUTHORITY_LAYER_MAP.items():
            if source_relative_path.startswith(prefix):
                return layer
        # 理论上不会走到这里——candidates本来就是从EA_LAYER_PRIORITY这几个
        # 目录下筛出来的，source只能是这几个前缀之一；保留兜底避免未来
        # EA_LAYER_PRIORITY改了但这里忘了同步时直接崩溃
        return "02_草稿"
    return GENERIC_PROJECT_DEFAULT_AUTHORITY_LAYER
