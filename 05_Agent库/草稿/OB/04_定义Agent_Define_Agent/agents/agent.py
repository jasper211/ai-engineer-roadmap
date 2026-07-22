#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OB Agent · 主入口

目录方法论说明（同 PTA）：agents/skills/tools/memory 四个 Python 包各自嵌套
在一个编号+中英文的顶层文件夹里，编号只是给人看的顺序标识——sys.path 要把
每个编号目录（而不是 OB_DIR 本身）加进去，`from skills.xxx import`/
`from tools.xxx import` 才能按包名解析。

v0.1.0 接入巡检能力线（--sync-check），迁移自
05_Agent库/OB知识库同步巡检Agent/ob_sync_agent.py。v0.2.0 新增检索服务能力线
（--retrieve），封装 obsidian-mcp-server 的 hybrid_search。v0.3.0 新增概念
笔记提炼能力线（--extract，单文件手动调用）。v0.4.0 新增批量+增量提炼
（--extract-project），见 skills/batch_concept_extraction.py：按
tools/project_filters.py 的分层优先级筛选候选文件、tools/file_diff.py 做
增量比对，只处理新增/变更的文件，语义去重见 tools/atom_embeddings.py。
两个--extract*入口都需要 DEEPSEEK_API_KEY 环境变量，产生真实 API 费用；
--extract-project 建议先用 --dry-run 核对候选文件再真的花钱跑。

迁移时修的一个真实 bug：原脚本的 `--output <path>` 参数被解析进
`output_path` 变量后，从未在后续逻辑里被实际使用——报告始终写去硬编码的
`OUTPUT_PATH` 常量，`--output` 形同虚设（README 却文档说这个参数有效）。
已在 launchd 部署的 plist 里传了 `--output /tmp/ob-sync-health-report.md`，
实际上这个文件从来没被真正创建过。这次 cmd_sync_check() 里改成真正使用
解析出的 output_path。

原脚本内嵌的 macOS 系统通知（osascript display notification）迁移到这里
（agent.py 层），不留在 skill 内部——skill 只返回结构化结果，通知/呈现是
调用方的职责，这样 skill 可以被检索/提炼等未来能力复用测试而不依赖桌面会话。
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent
NUMBERED_DIR = AGENTS_DIR.parent      # 04_定义Agent_Define_Agent/
OB_DIR = NUMBERED_DIR.parent          # OB 项目根目录

for _pkg_dir in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(OB_DIR / _pkg_dir))

from skills.vault_sync_health import VaultSyncHealthChecker
from skills.knowledge_retrieval import KnowledgeRetriever
from skills.concept_note_extraction import ConceptNoteExtractor
from skills.batch_concept_extraction import BatchConceptExtractor
from skills.cluster_atoms import AtomClusterer
from tools import agent_status
from tools.atom_embeddings import AtomEmbeddingStore
from memory import workspace as ws


# ══════════════════════════════════════════════════════════════
# 配置（唯一权威来源——不重复写进 settings.json，见 vault_sync_health.py 顶部说明）
# ══════════════════════════════════════════════════════════════

VAULT_PATH = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault"
CORRECT_SERVER_PATH = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/obsidian-mcp-server/src/server.mjs"
MCP_SERVER_SCRIPT = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/obsidian-mcp-server/src/vault.mjs"
VECTOR_SERVER_SCRIPT = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/obsidian-mcp-server/src/vector.mjs"

MCP_CONFIGS = {
    "Qoder": "/Users/a112233/Library/Application Support/Qoder/SharedClientCache/mcp.json",
    "Claude Desktop": "/Users/a112233/Library/Application Support/Claude/claude_desktop_config.json",
    "Kimi Code": "/Users/a112233/.kimi-code/mcp.json",
}

F_FILES = [
    # 全部用绝对路径直接指向 Desktop 原始位置——2026-07-16 vault 重置删除了
    # Rw权益项目/项目-流程架构 镜像 symlink 后，这两个文件不能再依赖"读vault里
    # 的symlink"这条路径，它们本来就不该依赖vault是否镜像了某个项目
    "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI上下文启动文件_v2_0.md",
    "/Users/a112233/Desktop/流程架构项目_jasper/08_任务与跟进/AI上下文/AI协作准则_v2_0.md",
    "/Users/a112233/Desktop/流程架构项目_jasper/08_任务与跟进/AI上下文/教训档案_v2_0.md",
]

DEFAULT_OUTPUT_PATH = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/Agent健康报告.md"

# 三个项目的真实 Desktop 路径——--extract-project 的项目名到根目录映射。
# 2026-07-22 Jasper范围裁定：Jasper AI协同经验引擎白名单收窄到只保留
# 三大主Agent体系架构（最新版）+ Mark_AI经验合集学习参考——后者是根目录下
# 跟 AI工程能力整改项目 平级的独立文件夹，之前的根目录设定只扫描
# AI工程能力整改项目子目录，够不到它，所以这里把根目录上移一级（改动细节
# 见 tools/project_filters.py 的 JASPER_ENGINE_LAYER_PRIORITY）。
PROJECT_ROOTS = {
    "Rw权益项目": "/Users/a112233/Desktop/Rw权益项目",
    "EA流程架构项目": "/Users/a112233/Desktop/流程架构项目_jasper",
    "Jasper AI协同经验引擎": "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎",
}


def _notify(title: str, message: str):
    """发送 macOS 系统通知，失败不影响主流程。"""
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            timeout=5,
        )
    except Exception:
        pass


def cmd_sync_check(args) -> int:
    checker = VaultSyncHealthChecker(
        vault_path=VAULT_PATH,
        server_script=MCP_SERVER_SCRIPT,
        correct_server_path=CORRECT_SERVER_PATH,
        mcp_configs=MCP_CONFIGS,
        f_files=F_FILES,
    )

    if not args.quiet:
        print("🔍 OB · 开始巡检 ...")

    result = checker.run(auto_fix=args.auto_fix)

    if not args.quiet:
        for name, ok in result["summary"].items():
            print(f"  {name}: {'✅' if ok else '❌'}")
        if result["fixes_applied"]:
            print(f"  🔧 已自动修复: {result['fixes_applied']}")

    agent_status.register("OB", {
        "description": "OB 知识库巡检",
        "schedule": "每小时 + 开机",
        "checks": list(result["summary"].keys()),
    })
    agent_status.update("OB", {
        "status": "🟢 全部正常" if result["all_ok"] else "🔴 存在异常",
        "results": {k: ("✅" if v else "❌") for k, v in result["summary"].items()},
        "errors": [k for k, v in result["summary"].items() if not v],
        "detail": result["report_markdown"],
    })

    output_path = args.output or DEFAULT_OUTPUT_PATH
    agent_status.write_report(output_path)

    if not args.quiet:
        if result["all_ok"]:
            _notify("OB知识库", "🟢 全部正常")
        else:
            problems = [k for k, v in result["summary"].items() if not v]
            _notify("OB知识库 ⚠️", f"发现问题: {', '.join(problems)}")

    return 0 if result["all_ok"] else 1


def cmd_retrieve(args) -> int:
    retriever = KnowledgeRetriever(
        vault_path=VAULT_PATH,
        vault_mjs=MCP_SERVER_SCRIPT,
        vector_mjs=VECTOR_SERVER_SCRIPT,
    )
    context = retriever.get_context(args.retrieve, max_results=args.max_results, mode=args.mode)

    if context.get("error"):
        print(f"❌ 检索失败: {context['error']}")
        return 1

    if not args.quiet:
        print(f"检索模式: {context['mode_effective']}（向量索引可用: {context['has_vector']}）")
        print(f"命中 {len(context['atoms'])} 条")
        print()

    print(KnowledgeRetriever.format_for_prompt(context))
    return 0


def cmd_extract(args) -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 未设置 DEEPSEEK_API_KEY 环境变量，概念笔记提炼需要真实LLM调用")
        return 1

    source_path = Path(args.extract)
    if not source_path.exists():
        print(f"❌ 源文档不存在: {source_path}")
        return 1

    vault_path = args.vault_path or VAULT_PATH
    extractor = ConceptNoteExtractor(
        vault_path=vault_path,
        project_name=args.project,
        api_key=api_key,
    )

    content = source_path.read_text(encoding="utf-8")
    if not args.quiet:
        print(f"🧠 调用 DeepSeek 提炼「{source_path.name}」（会产生真实API费用）...")

    result = extractor.process_document(str(source_path), content)

    print(f"提炼出 {result['atom_count']} 个原子（写入: {vault_path}/{args.project}/）")
    for r in result["results"]:
        print(f"  [{r['action']}] {r['title']}")
    return 0


def cmd_extract_project(args) -> int:
    project_root = PROJECT_ROOTS.get(args.extract_project)
    if not project_root:
        print(f"❌ 未知项目「{args.extract_project}」，可选: {list(PROJECT_ROOTS.keys())}")
        return 1

    if not args.dry_run:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            print("❌ 未设置 DEEPSEEK_API_KEY 环境变量，概念笔记提炼需要真实LLM调用（--dry-run 不需要）")
            return 1
    else:
        api_key = None  # dry-run 不会真的用到，但构造函数需要一个占位值

    batch = BatchConceptExtractor(
        project_name=args.extract_project,
        project_root=project_root,
        vault_path=args.vault_path or VAULT_PATH,
        vector_mjs=VECTOR_SERVER_SCRIPT,
        api_key=api_key or "",
    )

    if not args.quiet:
        mode = "（dry-run，不调用LLM/不花钱）" if args.dry_run else "（真实调用DeepSeek，产生真实费用）"
        print(f"🧠 批量扫描「{args.extract_project}」{mode} ...")

    summary = batch.scan_and_extract(dry_run=args.dry_run, max_files=args.max_files)

    print(f"候选文件: {summary['scanned']} | 新增: {summary['added']} | 变更: {summary['changed']} | "
          f"待处理: {summary['to_process']}")
    if args.dry_run:
        print("将会处理（不实际提炼）:")
        for f in summary["files"]:
            print(f"  {f}")
    else:
        print(f"已处理: {summary['processed']} | 新建原子: {summary['atoms_created']} | "
              f"更新原子: {summary['atoms_updated']}")
        if summary["errors"]:
            print(f"错误 ({len(summary['errors'])}):")
            for e in summary["errors"]:
                print(f"  [{e['file']}] {e['error']}")
    return 0


def cmd_cluster_project(args) -> int:
    if args.cluster_project not in PROJECT_ROOTS:
        print(f"❌ 未知项目「{args.cluster_project}」，可选: {list(PROJECT_ROOTS.keys())}")
        return 1

    if not args.dry_run:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            print("❌ 未设置 DEEPSEEK_API_KEY 环境变量，聚类连贯性判断需要真实LLM调用（--dry-run 不需要）")
            return 1
    else:
        api_key = None

    clusterer = AtomClusterer(
        vault_path=args.vault_path or VAULT_PATH,
        project_name=args.cluster_project,
        vector_mjs=VECTOR_SERVER_SCRIPT,
        api_key=api_key or "",
    )

    if not args.quiet:
        mode = "（dry-run，不调用LLM/不花钱）" if args.dry_run else "（真实调用DeepSeek判断连贯性，产生真实费用）"
        print(f"🧠 增量聚类「{args.cluster_project}」{mode} ...")

    summary = clusterer.scan_and_cluster(dry_run=args.dry_run, max_llm_calls=args.max_llm_calls)

    print(f"待聚类原子: {summary['unclustered_scanned']} | 既有枢纽: {summary['existing_hubs']}")
    if args.dry_run:
        print("将会执行的操作（不实际调用LLM/不写vault）:")
        for p in summary["plan"]:
            print(f"  [{p['action']}] {p.get('hub', '')} {p['atoms']}")
    else:
        print(f"并入既有枢纽: {summary['matched_to_existing_hub']} | 新建枢纽: {summary['new_hubs_created']} | "
              f"仍待聚类: {summary['atoms_still_unclustered']} | 无embedding跳过: {summary['skipped_no_embedding']} | "
              f"LLM调用次数: {summary['llm_calls']}")
        if summary["errors"]:
            print(f"错误 ({len(summary['errors'])}):")
            for e in summary["errors"]:
                print(f"  {e}")
    return 0


def cmd_backfill_embeddings(args) -> int:
    project_root = PROJECT_ROOTS.get(args.backfill_embeddings)
    if not project_root:
        print(f"❌ 未知项目「{args.backfill_embeddings}」，可选: {list(PROJECT_ROOTS.keys())}")
        return 1

    store = AtomEmbeddingStore(
        cache_dir=ws.atom_embeddings_dir(args.backfill_embeddings),
        project_name=args.backfill_embeddings,
        vector_mjs=VECTOR_SERVER_SCRIPT,
    )
    if not args.quiet:
        print(f"🧠 回填「{args.backfill_embeddings}」已有原子的embedding（真实调用embedding API，产生真实费用）...")

    result = store.backfill_missing(vault_path=args.vault_path or VAULT_PATH, project_name=args.backfill_embeddings)

    print(f"原子文件总数: {result['total_atom_files']} | 已有缓存: {result['already_cached']} | "
          f"待回填: {result['to_backfill']} | 已回填: {result['backfilled']} | "
          f"解析失败跳过: {result['skipped_unparseable']}")
    if result["errors"]:
        print(f"错误 ({len(result['errors'])}):")
        for e in result["errors"]:
            print(f"  [chunk从第{e['chunk_start']}个开始，共{e['chunk_size']}条] {e['error']}")
    return 0 if not result["errors"] else 1


def main():
    parser = argparse.ArgumentParser(description="OB · Obsidian 知识库 Agent")
    parser.add_argument("--sync-check", action="store_true", help="跑巡检能力线（symlink/MCP配置/Server连通性/F文件/vault统计/同步完整性）")
    parser.add_argument("--auto-fix", action="store_true", help="巡检发现MCP配置路径错误时自动修复（仅纯字符串路径替换）")
    parser.add_argument("--output", type=str, default=None, help="健康报告输出路径（默认见 DEFAULT_OUTPUT_PATH）")
    parser.add_argument("--retrieve", type=str, default=None, metavar="QUERY", help="检索服务：给定查询文本，返回背景上下文包")
    parser.add_argument("--max-results", type=int, default=5, help="--retrieve 返回的最大条数（默认5）")
    parser.add_argument("--mode", type=str, default="hybrid", choices=["hybrid", "keyword", "vector", "graph"], help="--retrieve 的检索模式（默认hybrid）")
    parser.add_argument("--extract", type=str, default=None, metavar="FILE_PATH", help="概念笔记提炼：给定源文档路径，提炼知识原子写入vault（需DEEPSEEK_API_KEY，产生真实费用）")
    parser.add_argument("--project", type=str, default=None, help="--extract 时原子归属的项目目录（如 Rw权益项目/EA流程架构项目/Jasper AI协同经验引擎）")
    parser.add_argument("--vault-path", type=str, default=None, help="--extract/--extract-project 写入的vault路径（默认真实vault，测试时应指向scratchpad）")
    parser.add_argument("--extract-project", type=str, default=None, metavar="PROJECT_NAME",
                        help=f"批量+增量概念笔记提炼：{list(PROJECT_ROOTS.keys())} 之一，需DEEPSEEK_API_KEY（--dry-run除外），产生真实费用")
    parser.add_argument("--dry-run", action="store_true", help="--extract-project 时只报告将处理哪些文件，不调用LLM/不花钱")
    parser.add_argument("--max-files", type=int, default=None, help="--extract-project 单次最多处理的文件数（控制单次成本）")
    parser.add_argument("--backfill-embeddings", type=str, default=None, metavar="PROJECT_NAME",
                        help=f"给vault里已有但embedding缓存里没有的原子回填embedding（不重新提炼，只算向量）：{list(PROJECT_ROOTS.keys())} 之一，产生真实embedding API费用")
    parser.add_argument("--cluster-project", type=str, default=None, metavar="PROJECT_NAME",
                        help=f"知识枢纽增量聚类：把「待聚类」原子匹配进既有枢纽或组建新枢纽，{list(PROJECT_ROOTS.keys())} 之一，需DEEPSEEK_API_KEY（--dry-run除外），产生真实费用")
    parser.add_argument("--max-llm-calls", type=int, default=None, help="--cluster-project 单次最多发起的LLM连贯性判断调用次数（控制单次成本）")
    parser.add_argument("--quiet", action="store_true", help="不打印进度到 stdout")
    args = parser.parse_args()

    if args.sync_check:
        sys.exit(cmd_sync_check(args))

    if args.retrieve:
        sys.exit(cmd_retrieve(args))

    if args.extract:
        if not args.project:
            print("❌ --extract 需要同时指定 --project")
            sys.exit(1)
        sys.exit(cmd_extract(args))

    if args.extract_project:
        sys.exit(cmd_extract_project(args))

    if args.backfill_embeddings:
        sys.exit(cmd_backfill_embeddings(args))

    if args.cluster_project:
        sys.exit(cmd_cluster_project(args))

    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
