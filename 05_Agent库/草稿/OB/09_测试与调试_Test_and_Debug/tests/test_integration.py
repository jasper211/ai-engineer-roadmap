#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OB Agent · 集成测试

v0.1.0：覆盖巡检能力线（VaultSyncHealthChecker）。v0.2.0：新增检索服务能力线
（KnowledgeRetriever）。跟 PTA 的 test_integration.py 同样的白盒 import 调用
风格，且按 Agent搭建SOP v1.2 第5.2节第5条原则，直接对着真实 vault/真实
obsidian-mcp-server 子进程跑（不是合成 fixture）——本机当前没有配置
OPENAI_API_KEY，检索测试因此实际验证的是"无向量索引时自动降级为关键词+
图谱"这条路径，这正是当前真实的部署状态，不是刻意挑的简单场景。
"""

import os
import sys
from pathlib import Path

# test_15 用到 skills.batch_concept_extraction，它在模块级 `from memory import
# workspace as ws`——workspace.py 的 WORKSPACE_ROOT 常量在 import 时就读一次
# 环境变量，必须在任何人 import 它之前设好，否则测试快照会写进 Jasper 真实的
# OB 工作区（/项目工作区/OB/），不是隔离的沙盒目录
os.environ.setdefault(
    "OB_WORKSPACE_ROOT",
    "/private/tmp/claude-501/-Users-a112233-Desktop--------jasper/"
    "93ec8304-7645-4107-b8c5-eda5452cd1c3/scratchpad/ob_test_workspace",
)

TESTS_DIR = Path(__file__).resolve().parent
NUMBERED_DIR = TESTS_DIR.parent          # 09_测试与调试_Test_and_Debug/
OB_DIR = NUMBERED_DIR.parent              # OB 项目根目录

for _pkg_dir in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(OB_DIR / _pkg_dir))

from skills.vault_sync_health import VaultSyncHealthChecker
from skills.knowledge_retrieval import KnowledgeRetriever
from skills.batch_concept_extraction import BatchConceptExtractor
from skills.concept_note_extraction import ConceptNoteExtractor
from tools import file_diff, project_filters

VAULT_PATH = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault"
CORRECT_SERVER_PATH = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/obsidian-mcp-server/src/server.mjs"
MCP_SERVER_SCRIPT = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/obsidian-mcp-server/src/vault.mjs"
VECTOR_SERVER_SCRIPT = "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/obsidian-mcp-server/src/vector.mjs"
EA_PROJECT_ROOT = "/Users/a112233/Desktop/流程架构项目_jasper"
RW_PROJECT_ROOT = "/Users/a112233/Desktop/Rw权益项目"
MCP_CONFIGS = {
    "Qoder": "/Users/a112233/Library/Application Support/Qoder/SharedClientCache/mcp.json",
    "Claude Desktop": "/Users/a112233/Library/Application Support/Claude/claude_desktop_config.json",
    "Kimi Code": "/Users/a112233/.kimi-code/mcp.json",
}
F_FILES = [
    # 全部用绝对路径直接指向 Desktop 原始位置——2026-07-16 vault 重置删除了
    # Rw权益项目/项目-流程架构 镜像 symlink 后不能再依赖"读vault里的symlink"
    "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI上下文启动文件_v2_0.md",
    "/Users/a112233/Desktop/流程架构项目_jasper/08_任务与跟进/AI上下文/AI协作准则_v2_0.md",
    "/Users/a112233/Desktop/流程架构项目_jasper/08_任务与跟进/AI上下文/教训档案_v2_0.md",
]

_pass = 0
_fail = 0


def check(label: str, condition: bool, detail: str = ""):
    global _pass, _fail
    if condition:
        _pass += 1
        print(f"  ✅ {label}")
    else:
        _fail += 1
        print(f"  ❌ {label}  {detail}")


def make_checker() -> VaultSyncHealthChecker:
    return VaultSyncHealthChecker(
        vault_path=VAULT_PATH,
        server_script=MCP_SERVER_SCRIPT,
        correct_server_path=CORRECT_SERVER_PATH,
        mcp_configs=MCP_CONFIGS,
        f_files=F_FILES,
    )


def test_01_symlinks():
    print("Test 1: check_symlinks 返回结构正确")
    checker = make_checker()
    results = checker.check_symlinks()
    # 2026-07-16 vault重置删除了Rw权益项目/项目-流程架构镜像symlink（对齐"只保留
    # 概念笔记，不镜像原始文件"的目标架构），vault根目录现在合法地没有任何symlink
    # 了——空列表是预期的新常态，不是回归；仍然断言"如果有symlink，每项都有status字段"
    check("无异常（返回列表，即使为空）", isinstance(results, list), f"实际: {results}")
    check("每项含 status 字段", all("status" in r or "error" in r for r in results))


def test_02_mcp_configs():
    print("Test 2: check_mcp_configs 三端配置读取成功")
    checker = make_checker()
    results = checker.check_mcp_configs()
    check("返回3个终端的结果", len(results) == 3, f"实际: {len(results)}")
    check("全部读取成功（无'配置文件不存在'）", all("不存在" not in r["status"] for r in results),
          f"实际: {[r['status'] for r in results]}")


def test_03_mcp_server_connectivity():
    print("Test 3: check_mcp_server 真实构建索引成功")
    checker = make_checker()
    result = checker.check_mcp_server()
    check("status 为 ✅", result["status"] == "✅", f"实际: {result}")
    check("notes 数量为正整数", isinstance(result.get("notes"), int) and result["notes"] > 0,
          f"实际: {result.get('notes')}")


def test_04_f_files():
    print("Test 4: check_f_files 返回3份文件的检查结果")
    checker = make_checker()
    results = checker.check_f_files()
    check("返回3份文件的结果", len(results) == 3, f"实际: {len(results)}")


def test_05_vault_stats():
    print("Test 5: check_vault_stats 统计结果合理")
    checker = make_checker()
    stats = checker.check_vault_stats()
    check("md_files 为正整数", stats["md_files"] > 0, f"实际: {stats}")
    check("directories 为正整数", stats["directories"] > 0, f"实际: {stats}")


def test_06_sync_integrity():
    print("Test 6: check_sync_integrity 抽查命中真实索引")
    checker = make_checker()
    result = checker.check_sync_integrity()
    check("status 为 ✅（同步完整）", result["status"] == "✅", f"实际: {result}")


def test_07_full_run_and_report():
    print("Test 7: run() 端到端跑通 + 报告文本完整")
    checker = make_checker()
    result = checker.run(auto_fix=False)
    check("summary 含6项检查", len(result["summary"]) == 6, f"实际: {result['summary']}")
    # 前5项（符号链接/MCP配置/MCP Server/F文件/同步完整性）在真实环境下应恒为True；
    # GitHub同步单独放宽——vault 是 Jasper 正在使用的真实vault，随时可能有他自己
    # 刚编辑但还没提交的笔记（真实复现过：写这条测试当下 概念/SKU.md 就是这种
    # 情况），这不是bug，check_github_sync 正确识别并跳过了，不应该让整个测试
    # 因为"vault 此刻恰好不干净"这种正常使用场景而失败
    core_checks = {k: v for k, v in result["summary"].items() if k != "GitHub同步"}
    check("核心5项检查全部正常", all(core_checks.values()), f"实际: {core_checks}")
    gh_status = result["summary"]["GitHub同步"]
    if not gh_status:
        print(f"  ℹ️  GitHub同步本次为False（vault可能有未提交改动，见Test 11详情），不计入失败")
    md = result["report_markdown"]
    for section in ["一、符号链接", "二、MCP 配置", "三、MCP Server 连通性",
                     "四、F1/F2/F3 上下文文件", "五、Vault 基础统计", "六、同步完整性抽查",
                     "七、GitHub 同步状态"]:
        check(f"报告含章节「{section}」", section in md)


def test_11_github_sync():
    print("Test 11: check_github_sync 真实执行（工作区干净则pull成功，不干净则正确跳过）")
    checker = make_checker()
    result = checker.check_github_sync()
    # 两种结果都算"正确工作"：①工作区干净、真实pull成功 ②工作区不干净（Jasper
    # 自己在用vault，随时可能有未提交的新笔记），正确识别并跳过、不做任何冲突
    # 风险操作。唯一不可接受的是"❌"这种真失败（pull报错/超时/git命令缺失）
    valid = result["status"].startswith("✅") or result["status"] == "⚠️ 跳过"
    check("结果是✅成功或⚠️正确跳过之一（不是❌真失败）", valid, f"实际: {result}")


def make_retriever() -> KnowledgeRetriever:
    return KnowledgeRetriever(
        vault_path=VAULT_PATH,
        vault_mjs=MCP_SERVER_SCRIPT,
        vector_mjs=VECTOR_SERVER_SCRIPT,
    )


def test_08_retrieve_hybrid_degrades_gracefully():
    # 2026-07-18更新：embedding_config.json现在已配置真实SiliconFlow key，
    # "没配key直接抛异常"这条旧的降级路径不再触发。改成retrieval_bridge.py
    # 给buildVectorIndex单独包了vector_build_timeout（默认8秒）——vault涨到
    # 7000+文件后.vector-cache.json缓存不匹配，现算全量embedding要20-60分钟，
    # 8秒内跑不完就当作"这次拿不到向量"直接降级到关键词+图谱，不再是"没配
    # key"触发降级，是"来不及算"触发降级，效果一致：hybrid模式不会再卡死
    # 常规查询请求。真正一次性构建向量索引缓存仍是待专门安排的独立任务
    # （不是这次改动的范围），跟这里的"单次查询不该被这个耗时任务拖住"是
    # 两回事。
    print("Test 8: --retrieve hybrid模式在向量索引缓存未命中时优雅降级，不卡死")
    retriever = make_retriever()
    context = retriever.get_context("价值节点", max_results=3, mode="hybrid")
    check("无 error 字段", "error" not in context, f"实际: {context}")
    check("has_vector 为 False（缓存未命中，8秒内放弃现算）", context["has_vector"] is False)
    check("mode_effective 标注为降级", "降级" in context["mode_effective"], f"实际: {context['mode_effective']}")
    check("返回非空atoms（真实vault对这个查询应有命中）", len(context["atoms"]) > 0)


def test_09_retrieve_keyword_and_graph_modes():
    print("Test 9: --retrieve keyword/graph模式独立可用")
    retriever = make_retriever()
    kw = retriever.get_context("价值节点", max_results=2, mode="keyword")
    check("keyword模式无error", "error" not in kw, f"实际: {kw}")
    check("keyword模式返回结果", len(kw["atoms"]) > 0)

    gr = retriever.get_context("价值节点", max_results=2, mode="graph")
    check("graph模式无error（此前bug会在vectorIndex=null时崩溃）", "error" not in gr, f"实际: {gr}")
    check("graph模式返回结果", len(gr["atoms"]) > 0)


def test_10_retrieve_no_match_returns_empty_gracefully():
    print("Test 10: --retrieve 无命中查询返回空结果而非报错")
    retriever = make_retriever()
    context = retriever.get_context("这是一个完全不存在的查询词xyzzy12345", max_results=3, mode="hybrid")
    check("无 error 字段", "error" not in context, f"实际: {context}")
    check("atoms为空列表", context["atoms"] == [], f"实际: {context['atoms']}")
    check("format_for_prompt对空结果给出明确提示（不是空字符串）",
          "未检索到相关背景" in KnowledgeRetriever.format_for_prompt(context))


def test_12_ea_candidates_layered_priority():
    print("Test 12: project_filters.get_ea_candidates 按分层优先级排序（对真实EA项目跑）")
    candidates = project_filters.get_ea_candidates(EA_PROJECT_ROOT)
    check("返回非空列表", len(candidates) > 0, f"实际数量: {len(candidates)}")

    layers_seen = [c.split("/")[0] for c in candidates]
    first_layer_files = [c for c in candidates if c.startswith("00_治理与元模型")]
    last_layer_files = [c for c in candidates if c.startswith("02_过程成果-工作产出")]
    check("00_治理与元模型 出现在候选列表里", len(first_layer_files) > 0)
    check("02_过程成果-工作产出/规则分析（Jasper） 出现在候选列表里且排在最后",
          len(last_layer_files) > 0 and layers_seen.index(last_layer_files[0].split("/")[0]) > layers_seen.index(first_layer_files[0].split("/")[0]) if first_layer_files and last_layer_files else False)
    check("04-07层（代码资产）不出现在候选列表里",
          not any(c.startswith(("04_Skill库", "05_Agent库", "06_Scripts库", "07_Memory")) for c in candidates))
    check("02层里只有'规则分析（Jasper）'子目录，没有其他业务维度子目录",
          all("规则分析（Jasper）" in c for c in candidates if c.startswith("02_过程成果-工作产出")))
    check("归档关键字文件被排除", not any(("归档" in c or "旧版" in c or "backup" in c.lower()) for c in candidates))


def test_13_generic_candidates_archive_exclusion():
    print("Test 13: project_filters.get_generic_candidates 归档关键字排除（对真实Rw项目跑）")
    candidates = project_filters.get_generic_candidates(RW_PROJECT_ROOT)
    check("返回非空列表", len(candidates) > 0, f"实际数量: {len(candidates)}")
    check("归档关键字文件被排除", not any(("归档" in c or "旧版" in c or "backup" in c.lower()) for c in candidates))
    check("只包含候选后缀（.md/.docx/.txt）",
          all(c.lower().endswith((".md", ".docx", ".txt")) for c in candidates))


def test_14_file_diff_snapshot_and_diff():
    print("Test 14: tools.file_diff.snapshot_files + diff_snapshots 增量逻辑正确")
    candidates = project_filters.get_ea_candidates(EA_PROJECT_ROOT)[:5]
    snap1 = file_diff.snapshot_files(EA_PROJECT_ROOT, candidates)
    check("snapshot_files 返回预期数量的条目", len(snap1) == len(candidates), f"实际: {len(snap1)} vs {len(candidates)}")

    diff_first_run = file_diff.diff_snapshots({}, snap1)
    check("空快照对比时全部判定为added", set(diff_first_run.added) == set(candidates))
    check("空快照对比时changed为空", len(diff_first_run.changed) == 0)

    diff_second_run = file_diff.diff_snapshots(snap1, snap1)
    check("同一份快照再次对比，added/changed均为空（增量正确性）",
          diff_second_run.is_empty(), f"实际: added={diff_second_run.added}, changed={diff_second_run.changed}")


def test_14b_read_content_truncated_utf16_bom():
    print("Test 14b: read_content_truncated 正确解码带BOM的UTF-16文件（不产出NUL控制字符）")
    p = Path(EA_PROJECT_ROOT) / "02_过程成果-工作产出/规则分析（Jasper）/Agent与Skill体系/_cross_ref_output.txt"
    if not p.exists():
        print("  ⚠️  跳过（真实文件不存在，环境差异）")
        return
    text = file_diff.read_content_truncated(p, max_chars=500)
    check("解码结果不含NUL控制字符", "\x00" not in text, f"实际前50字符: {text[:50]!r}")
    check("解码结果是可读中文内容", "CROSS-REFERENCE" in text, f"实际前50字符: {text[:50]!r}")


def test_15_stale_atom_marking():
    print("Test 15: 过时原子标记机制（文档变更/删除后，孤儿原子标记待复核，不自动删除）")
    import shutil
    from unittest.mock import patch

    sandbox_root = Path(os.environ["OB_WORKSPACE_ROOT"]).parent / "ob_stale_test"
    if sandbox_root.exists():
        shutil.rmtree(sandbox_root)
    project_root = sandbox_root / "project"
    vault_path = sandbox_root / "vault"
    project_root.mkdir(parents=True)
    vault_path.mkdir(parents=True)

    # 用非"EA流程架构项目"的项目名，走 get_generic_candidates（全目录扫描），
    # 不依赖 EA 专用分层规则，避免这个沙盒测试跟真实 EA 项目结构耦合
    project_name = "OB测试沙盒_过时标记"
    note_path = project_root / "note1.md"
    note_path.write_text("v1 content", encoding="utf-8")

    canned_atoms_v1 = [
        {"title": "原子A", "summary": "内容A", "concept_type": "定义", "related_concepts": []},
        {"title": "原子B", "summary": "内容B", "concept_type": "定义", "related_concepts": []},
    ]
    canned_atoms_v2 = [
        {"title": "原子A", "summary": "内容A更新版", "concept_type": "定义", "related_concepts": []},
    ]
    call_state = {"atoms": canned_atoms_v1}

    def fake_extract_atoms(self, content):
        # 不调用真实 LLM（不产生 API 费用）——只验证批量编排里"对比新旧
        # atom_slugs、标记孤儿原子"这段逻辑本身，提炼环节用预设结果代替
        return call_state["atoms"]

    def make_extractor():
        return BatchConceptExtractor(
            project_name=project_name, project_root=str(project_root),
            vault_path=str(vault_path), vector_mjs="/nonexistent/vector.mjs", api_key="unused",
        )

    atom_a_path = vault_path / project_name / "原子A.md"
    atom_b_path = vault_path / project_name / "原子B.md"

    with patch.object(ConceptNoteExtractor, "extract_atoms", fake_extract_atoms):
        summary1 = make_extractor().scan_and_extract()
        check("首次运行：processed=1", summary1["processed"] == 1, f"实际: {summary1}")
        check("首次运行：atoms_created=2", summary1["atoms_created"] == 2, f"实际: {summary1}")
        check("首次运行：atoms_marked_stale=0（没有旧快照可比）", summary1["atoms_marked_stale"] == 0)
        check("原子A/B文件已生成", atom_a_path.exists() and atom_b_path.exists())

        # 源文档内容变更 + 模拟这次LLM只产出原子A（原子B在新版本里消失了）
        note_path.write_text("v2 content, no more B", encoding="utf-8")
        call_state["atoms"] = canned_atoms_v2
        summary2 = make_extractor().scan_and_extract()
        check("二次运行（内容变更）：changed=1", summary2["changed"] == 1, f"实际: {summary2}")
        check("二次运行：atoms_marked_stale=1（原子B变孤儿）", summary2["atoms_marked_stale"] == 1, f"实际: {summary2}")
        check("原子B文件被追加待复核标记", "待复核" in atom_b_path.read_text(encoding="utf-8"))
        check("原子A文件未被标记（仍然有效）", "待复核" not in atom_a_path.read_text(encoding="utf-8"))

        # 内容不变再跑一次：不应有新孤儿，不应重复标记
        summary3 = make_extractor().scan_and_extract()
        check("三次运行（内容未变）：changed=0 且无新标记", summary3["changed"] == 0 and summary3["atoms_marked_stale"] == 0,
              f"实际: {summary3}")

        # 源文档被删除：它名下仍存活的原子A应被标记待复核
        note_path.unlink()
        summary4 = make_extractor().scan_and_extract()
        check("文档删除后：removed=1", summary4["removed"] == 1, f"实际: {summary4}")
        check("文档删除后：atoms_marked_stale=1（原子A因源文档删除被标记）",
              summary4["atoms_marked_stale"] == 1, f"实际: {summary4}")
        check("原子A文件此时也被追加待复核标记", "待复核" in atom_a_path.read_text(encoding="utf-8"))

    shutil.rmtree(sandbox_root)


def test_16_retrieve_metadata_enrichment():
    print("Test 16: 检索结果补充entity_type/authority_layer/confidence/所属枢纽元数据")
    retriever = make_retriever()
    context = retriever.get_context("佣金结算", max_results=5, mode="keyword")
    check("无error", "error" not in context, f"实际: {context}")
    check("返回非空atoms", len(context["atoms"]) > 0)
    first = context["atoms"][0]
    check("atom含authority_layer字段", "authority_layer" in first)
    check("atom含confidence字段", "confidence" in first)
    check("atom含entity_type字段", "entity_type" in first)
    check("atom含hubs字段(list)", isinstance(first.get("hubs"), list))
    check("至少一条结果有非空authority_layer（真实vault应命中已迁移原子）",
          any(a.get("authority_layer") for a in context["atoms"]),
          f"实际: {[a.get('authority_layer') for a in context['atoms']]}")

    prompt_text = retriever.format_for_prompt(context)
    check("format_for_prompt输出含信任标注(方括号badge)", "[" in prompt_text and "]" in prompt_text)


def main():
    print("=== OB Agent 集成测试（v0.4.5，覆盖巡检+检索服务(含元数据补充)+批量提炼筛选/增量/过时原子标记）===\n")
    for fn in [test_01_symlinks, test_02_mcp_configs, test_03_mcp_server_connectivity,
               test_04_f_files, test_05_vault_stats, test_06_sync_integrity,
               test_07_full_run_and_report, test_08_retrieve_hybrid_degrades_gracefully,
               test_09_retrieve_keyword_and_graph_modes, test_10_retrieve_no_match_returns_empty_gracefully,
               test_11_github_sync, test_12_ea_candidates_layered_priority,
               test_13_generic_candidates_archive_exclusion, test_14_file_diff_snapshot_and_diff,
               test_14b_read_content_truncated_utf16_bom, test_15_stale_atom_marking,
               test_16_retrieve_metadata_enrichment]:
        fn()
        print()

    print(f"=== 结果: {_pass} 通过, {_fail} 失败 ===")
    sys.exit(0 if _fail == 0 else 1)


if __name__ == "__main__":
    main()
