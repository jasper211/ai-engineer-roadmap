#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA 集成测试（原 test_pta_integration.sh 迁移到新结构，Test 1-9；
Test 10-13 是每日巡检 daily_sensing 能力上线时新增的覆盖）

迁移改动：旧版通过 subprocess 调用各个扁平脚本（黑盒、跨进程）来测试；
新版大部分改为直接 import skills/tools 做白盒调用（同进程内的架构本来就
不再有"跨进程用临时 JSON 中转"这回事，继续用 subprocess 测反而测不出
真实的调用方式）。保留 subprocess 的地方：
  - Test 7（agents/agent.py 全链路 + 状态记忆）：这是外部使用者真实的调用方式
    （命令行），值得按黑盒测一次，且顺带验证 CLI 参数解析没问题。
  - Test 9（git_ops 默认行为安全验证）：故意在隔离的临时 git 仓库里跑，
    不需要走 agent 或 skills，直接测 tools/git_ops.py 本身。
  - Test 13（--daily-scan 缺 API Key 报错路径）：同 Test 7，验证 CLI 层面的
    真实行为。

Test 12 用 stub 替换 `daily_sensing.call_deepseek`，不依赖真实网络/API key
（跟真实 DeepSeek 调用的验证，在开发这个功能时已经单独手工跑过一次，见
决策记录，这里只测试增量去重/指纹复用的逻辑，不重复测 LLM 调用本身）。

运行：python3 09_测试与调试_Test_and_Debug/tests/test_integration.py

目录方法论说明（v2.1.0 起）：本文件所在的 tests/ 嵌套在编号目录
09_测试与调试_Test_and_Debug/ 里面，agents/skills/tools/memory 同理各自
嵌套在自己的编号目录里，编号只是给人看的顺序标识，import 用的仍是不带编号
前缀的包名——因此 sys.path 要把 05/06/07 三个编号目录（各自的直接父目录）
加进去，而不是随便加一个 PTA_DIR。
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
NUMBERED_DIR = TESTS_DIR.parent            # 09_测试与调试_Test_and_Debug/
PTA_DIR = NUMBERED_DIR.parent                # PTA 项目根目录

for _pkg_dir in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(PTA_DIR / _pkg_dir))

from skills.intent_parsing import IntentParser
from skills.execution_planning import ExecutionScheduler
from skills.progress_tracking import ProgressTracker
from skills.doc_sync import DocumentSyncer
from skills.archive_review import ArchiveReviewer
import skills.daily_sensing as daily_sensing
from skills.daily_sensing import DailySensor, SuggestedTask, DailyBriefing
from skills.rule_based_task_scan import RuleBasedScanner
import skills.document_task_discovery as document_task_discovery
from skills.document_task_discovery import DocumentDiscoverer
from tools import git_ops
from tools.file_diff import snapshot_dir, diff_snapshots
from tools.task_knowledge import load_task_map, merge_suggested_tasks
from tools.wecom_notify import (build_notification_text, load_wecom_config, MAX_CONTENT_BYTES,
                                 _encode_multipart_file, _webhook_to_upload_url)
from memory.workspace import get_project_workspace

FAILURES = []


def check(condition: bool, ok_msg: str, fail_msg: str):
    if condition:
        print(f"✅ {ok_msg}")
    else:
        print(f"❌ {fail_msg}")
        FAILURES.append(fail_msg)


def test_1_intent_parsing_multi_task():
    print("\n[Test 1] skills.intent_parsing 多任务顺序指令")
    print("-" * 60)
    parser = IntentParser()
    pkg = parser.parse("按顺序完成 P0-02, P0-03, P1-03, P1-04")
    check(len(pkg.items) == 4, f"任务项数量正确: {len(pkg.items)}",
          f"任务项数量错误: {len(pkg.items)} (期望 4)")
    check(pkg.type == "sequential", f"类型识别正确: {pkg.type}", f"类型识别错误: {pkg.type}")


def test_2_intent_parsing_ambiguous():
    print("\n[Test 2] skills.intent_parsing 模糊指令检测")
    print("-" * 60)
    parser = IntentParser()
    pkg = parser.parse("帮我看看")
    check(pkg.needs_clarification, "正确识别模糊指令，触发 needs_clarification",
          "未识别模糊指令")


def test_3_execution_planning_dry_run(task_dict: dict) -> dict:
    print("\n[Test 3] skills.execution_planning 执行编排 (dry-run)")
    print("-" * 60)
    scheduler = ExecutionScheduler(PTA_DIR, dry_run=True)
    plan = scheduler.create_plan(task_dict)
    plan_dict = scheduler.to_dict(plan)
    check(len(plan_dict["steps"]) > 0, f"执行步骤数: {len(plan_dict['steps'])}",
          "未生成任何执行步骤")
    return plan_dict


def test_4_progress_tracking(plan_dict: dict) -> dict:
    print("\n[Test 4] skills.progress_tracking 进度追踪")
    print("-" * 60)
    scheduler = ExecutionScheduler(PTA_DIR, dry_run=True)
    exec_result = scheduler.execute_plan(
        __import__("skills.execution_planning", fromlist=["ExecutionPlan"]).ExecutionPlan(
            plan_id=plan_dict["plan_id"], task_id=plan_dict["task_id"],
            task_name=plan_dict["task_name"],
            steps=[__import__("skills.execution_planning", fromlist=["ExecutionStep"]).ExecutionStep(**s)
                   for s in plan_dict["steps"]],
        )
    )
    tracker = ProgressTracker(exec_result)
    report = tracker.generate_report()
    report_dict = tracker.to_dict(report)
    check(report_dict["status"] in ("已完成", "进行中", "部分失败", "待开始"),
          f"任务状态: {report_dict['status']}", f"状态值异常: {report_dict['status']}")
    return exec_result


def test_5_doc_sync_dry_run(tmp_project: Path):
    print("\n[Test 5] skills.doc_sync 文档同步 (dry-run)")
    print("-" * 60)
    syncer = DocumentSyncer(tmp_project, dry_run=True)
    result = syncer.sync("P2-01", "PTA Agent 搭建", "test: PTA integration test")
    check(result["results"]["git"]["status"] == "dry_run",
          "Dry-run 模式正常", f"Dry-run 未生效: {result['results']['git']}")


def test_6_archive_review(tmp_project: Path, plan_dict: dict):
    print("\n[Test 6] skills.archive_review 归档复盘")
    print("-" * 60)
    reviewer = ArchiveReviewer(tmp_project)
    result = reviewer.review("P2-01", "PTA Agent 搭建", plan_dict, update_lessons=False)
    record_path = Path(result["record_path"])
    check(record_path.exists(), f"执行记录已生成: {record_path}", "未生成执行记录")


def test_7_agent_cli_full_loop(tmp_project: Path):
    print("\n[Test 7] agents/agent.py 全链路 (Think-Act-Observe + 状态记忆)")
    print("-" * 60)
    agent_py = PTA_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"

    r = subprocess.run(["python3", str(agent_py), "按顺序完成 P1-03, P1-04",
                         "--project-root", str(tmp_project)],
                        capture_output=True, text=True)
    print("\n".join(r.stdout.splitlines()[-10:]))

    r2 = subprocess.run(["python3", str(agent_py), "--status", "--project-root", str(tmp_project)],
                         capture_output=True, text=True)
    print("\n".join(r2.stdout.splitlines()[-6:]))
    check("历史任务（共 1 条" in r2.stdout, "状态记忆已写入专属工作区（隔离测试目录）",
          "状态记忆未生成")


def test_8_cross_project_task_knowledge(tmp_dir: Path):
    print("\n[Test 8] tools.task_knowledge 跨项目任务知识库")
    print("-" * 60)
    ext_project = tmp_dir / "fake_external_project"
    ext_project.mkdir(parents=True, exist_ok=True)
    (ext_project / "pta_tasks.json").write_text(json.dumps({
        "ZZ-01": {"name": "外部项目专属任务", "steps": [
            {"action": "ext_step", "tool": "bash", "command": "echo external-project-marker",
             "description": "外部项目自定义步骤"}
        ]}
    }, ensure_ascii=False), encoding="utf-8")

    task_map = load_task_map(None, ext_project)
    parser = IntentParser(task_map=task_map)
    pkg = parser.parse("执行一下 ZZ-01 这个任务")
    ext_task_name = pkg.items[0].name if pkg.items else None
    check(ext_task_name == "外部项目专属任务",
          f"S01 正确加载外部项目的 pta_tasks.json（任务名: {ext_task_name}）",
          f"S01 未正确加载外部项目任务知识库（得到: {ext_task_name}）")

    scheduler = ExecutionScheduler(ext_project, dry_run=True, task_map=task_map)
    plan = scheduler.create_plan(parser.to_dict(pkg))
    ext_action = plan.steps[0].action if plan.steps else None
    check(ext_action == "ext_step",
          f"S02 正确使用外部项目自定义步骤（action: {ext_action}，而非通用占位步骤）",
          f"S02 未使用外部项目自定义步骤（得到: {ext_action}）")


def test_9_git_ops_default_real_execution(tmp_dir: Path):
    print("\n[Test 9] tools.git_ops 默认行为验证（不传 dry_run 即真实执行）")
    print("-" * 60)
    safe_repo = tmp_dir / "safe_isolated_repo"
    safe_repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=safe_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@pta.local"], cwd=safe_repo, check=True)
    subprocess.run(["git", "config", "user.name", "pta-test"], cwd=safe_repo, check=True)
    (safe_repo / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=safe_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=safe_repo, check=True)
    # 故意不配置 remote：即使 push 被真实触发，也只会在这个隔离仓库里本地失败

    (safe_repo / "README.md").write_text("init\nchanged\n", encoding="utf-8")
    git_ops.sync_git(safe_repo, "test: safety check", ["README.md"], dry_run=False)

    commit_count = subprocess.run(["git", "log", "--oneline"], cwd=safe_repo,
                                    capture_output=True, text=True).stdout.strip().splitlines()
    check(len(commit_count) == 2,
          f"确认：dry_run=False 时 git_ops 默认真实执行了 commit（隔离仓库 commit 数={len(commit_count)}）",
          f"意外：commit 未按预期发生（隔离仓库 commit 数={len(commit_count)}，预期 2）")


def test_10_file_diff(tmp_dir: Path):
    print("\n[Test 10] tools.file_diff 文件快照与增量 diff")
    print("-" * 60)
    root = tmp_dir / "file_diff_fixture"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.md").write_text("hello\n", encoding="utf-8")
    (root / "b.py").write_text("print(1)\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    snap1 = snapshot_dir(root, extensions={".md", ".py"})
    check(set(snap1.keys()) == {"a.md", "b.py"}, ".git 内部文件被正确排除",
          f".git 内部文件未被排除（得到: {sorted(snap1.keys())}）")

    diff0 = diff_snapshots(snap1, snap1)
    check(diff0.is_empty(), "无变化时 diff 为空", "无变化时 diff 不为空")

    (root / "a.md").write_text("hello world\n", encoding="utf-8")
    (root / "c.md").write_text("new\n", encoding="utf-8")
    (root / "b.py").unlink()
    snap2 = snapshot_dir(root, extensions={".md", ".py"})
    diff1 = diff_snapshots(snap1, snap2)
    check(diff1.added == ["c.md"] and diff1.changed == ["a.md"] and diff1.removed == ["b.py"],
          f"新增/变更/删除正确识别（added={diff1.added}, changed={diff1.changed}, removed={diff1.removed}）",
          f"diff 结果不符合预期（added={diff1.added}, changed={diff1.changed}, removed={diff1.removed}）")


def test_11_merge_suggested_tasks_safety(tmp_dir: Path):
    print("\n[Test 11] tools.task_knowledge.merge_suggested_tasks 安全不变量")
    print("-" * 60)
    root = tmp_dir / "merge_fixture"
    root.mkdir(parents=True, exist_ok=True)
    fixture = {
        "P1-01": {"name": "人工任务", "steps": [{"action": "x", "tool": "bash",
                                                    "command": "echo hi", "description": "d"}]},
        "RPT-20260714-01": {"name": "旧建议", "steps": []},
    }
    (root / "pta_tasks.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")

    merged = merge_suggested_tasks(root, {"RPT-20260715-01": {"name": "新建议", "steps": []}})
    check(list(merged.keys()) == ["P1-01", "RPT-20260714-01", "RPT-20260715-01"],
          "已有 key 顺序不变、新 key 追加在末尾", f"key 顺序异常: {list(merged.keys())}")
    check(merged["P1-01"] == fixture["P1-01"], "人工任务原样未被 touch", "人工任务被意外修改")
    check((root / "pta_tasks.json.bak").exists(), "写入前生成了 .bak 备份", "未生成 .bak 备份")

    try:
        merge_suggested_tasks(root, {"P9-99": {"name": "非法前缀"}})
        check(False, "", "非法前缀应该抛出 ValueError 但没有")
    except ValueError:
        check(True, "拒绝写入非 RPT- 前缀的 key", "")


def test_12_daily_sensing_fingerprint_dedup(tmp_dir: Path):
    print("\n[Test 12] skills.daily_sensing 增量去重（无变化时零 LLM 调用）")
    print("-" * 60)
    root = tmp_dir / "daily_sensing_fixture"
    root.mkdir(parents=True, exist_ok=True)
    (root / "note.md").write_text("初始内容\n", encoding="utf-8")

    sensor = DailySensor(root, api_key="fake-key-not-used")

    # 第一次扫描（相对于空 previous_state，全部文件视为新增）：stub 掉 call_deepseek，
    # 让它返回一个包含建议任务的合法 JSON，避免测试依赖真实网络/API key
    def _stub_with_task(system_prompt, user_content, api_key, model=None, **kw):
        return json.dumps({
            "changes": [{"file": "note.md", "summary": "新增了初始内容"}],
            "relationships": [],
            "suggested_tasks": [{"name": "复核note.md", "rationale": "r", "priority": "P2",
                                   "signal_to": ["Jasper", "Terresa"], "needs_mark_alignment": True,
                                   "relevance_reason": "rr", "related_files": ["note.md"]}],
        }, ensure_ascii=False)

    daily_sensing.call_deepseek = _stub_with_task
    briefing1, state1, task_map1 = sensor.scan(previous_state={})
    check(not briefing1.skipped_llm_call and len(briefing1.suggested_tasks) == 1,
          f"首次扫描正确触发分析并铸造建议任务: {briefing1.suggested_tasks[0].task_id}",
          "首次扫描未按预期产生建议任务")
    check(len(task_map1) == 1, "task_map_entries 正确生成 1 条", "task_map_entries 数量不符")
    check(briefing1.suggested_tasks[0].signal_to == ["Jasper", "Terresa"],
          f"signal_to 正确解析: {briefing1.suggested_tasks[0].signal_to}",
          f"signal_to 解析错误: {briefing1.suggested_tasks[0].signal_to}")
    check(briefing1.suggested_tasks[0].needs_mark_alignment is True,
          "needs_mark_alignment 正确解析为 True", "needs_mark_alignment 解析错误")

    # 第二次扫描：文件没有变化，stub 换成"一调用就报错"，验证真的零 LLM 调用
    def _boom(*a, **kw):
        raise AssertionError("不应该调用 call_deepseek——文件没有变化")
    daily_sensing.call_deepseek = _boom

    briefing2, state2, task_map2 = sensor.scan(previous_state=state1)
    check(briefing2.skipped_llm_call, "无变化时正确跳过 LLM 调用（零成本）", "无变化时仍然调用了 LLM")
    check(len(briefing2.suggested_tasks) == 1 and briefing2.suggested_tasks[0].task_id == briefing1.suggested_tasks[0].task_id,
          "此前仍待确认的建议任务在简报里正确复现（同一个任务ID，未丢失）",
          "仍待确认的建议任务丢失或 ID 不一致")
    check(not briefing2.suggested_tasks[0].is_new, "复现的任务正确标记为非新建（仍待确认）",
          "复现的任务未正确标记为非新建")
    check(briefing2.suggested_tasks[0].signal_to == ["Jasper", "Terresa"]
          and briefing2.suggested_tasks[0].needs_mark_alignment is True,
          "复现的 pending 任务正确保留了 signal_to/needs_mark_alignment（指纹重建没有丢字段）",
          f"复现的 pending 任务丢失了字段: signal_to={briefing2.suggested_tasks[0].signal_to}, "
          f"needs_mark_alignment={briefing2.suggested_tasks[0].needs_mark_alignment}")


def test_13_daily_scan_cli_missing_api_key(tmp_dir: Path):
    print("\n[Test 13] agents/agent.py --daily-scan 缺少 DEEPSEEK_API_KEY 时优雅报错")
    print("-" * 60)
    root = tmp_dir / "daily_scan_cli_fixture"
    root.mkdir(parents=True, exist_ok=True)
    (root / "note.md").write_text("一些内容\n", encoding="utf-8")

    agent_py = PTA_DIR / "04_定义Agent_Define_Agent" / "agents" / "agent.py"
    import os
    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    r = subprocess.run(["python3", str(agent_py), "--daily-scan", "--project-root", str(root)],
                        capture_output=True, text=True, env=env)
    check(r.returncode != 0 and "DEEPSEEK_API_KEY" in r.stdout,
          "缺少 API Key 时优雅报错退出（不是未处理的崩溃）",
          f"未按预期报错（returncode={r.returncode}, stdout末尾={r.stdout[-200:]}）")


def test_14_wecom_notify():
    print("\n[Test 14] tools.wecom_notify 通知构造（只 @ Jasper 本人，不真实发送）")
    print("-" * 60)

    check(load_wecom_config(Path("/tmp/definitely_not_exists_wecom_config.json")) is None,
          "未配置时 load_wecom_config 优雅返回 None（不抛异常）",
          "未配置时应返回 None")

    tasks = [
        SuggestedTask(task_id="RPT-20260714-01", name="需要Mark裁定的事项", rationale="r",
                       priority="P0", signal_to=["Jasper"], needs_mark_alignment=True, relevance_reason="rr"),
        SuggestedTask(task_id="RPT-20260714-02", name="多方相关的事项", rationale="r",
                       priority="P1", signal_to=["Terresa", "Jasper"], relevance_reason="rr"),
        SuggestedTask(task_id="RPT-20260714-03", name="只通知Carrie的事项", rationale="r",
                       priority="P2", signal_to=["Carrie"], relevance_reason="rr"),
    ]
    briefing = DailyBriefing(generated_at="now", project_root="/path/to/project",
                              files_added=5, suggested_tasks=tasks)
    mobiles = {"Jasper": "13800000001", "Terresa": "13800000002", "HR": "13800000003", "Carrie": "13800000004"}

    content, mentioned = build_notification_text(briefing, mobiles, report_path="/path/report.md")
    check("需要Mark裁定的事项" in content and "只通知Carrie的事项" in content,
          "通知文本包含每条建议任务的摘要（signal_to 判断结果仍显示在文字里）",
          "通知文本缺少建议任务摘要")
    check(mentioned == ["13800000001"],
          f"@ 名单按组内约定只有 Jasper 本人，不 @ Terresa/HR/Carrie（哪怕某条任务 signal_to 写了他们）: {mentioned}",
          f"@ 名单不符合预期，应该只有 Jasper: {mentioned}")
    check(len(content.encode("utf-8")) <= MAX_CONTENT_BYTES,
          f"通知内容长度在企业微信限制内: {len(content.encode('utf-8'))} 字节",
          "通知内容超过企业微信长度限制")

    # Jasper 不在 mobiles_map 里时应该优雅返回空 @ 名单，而不是报错
    _, mentioned_no_jasper = build_notification_text(briefing, {"Terresa": "13800000002"})
    check(mentioned_no_jasper == [], "mobiles_map 里没有 Jasper 时 @ 名单优雅为空",
          f"应该返回空列表，实际: {mentioned_no_jasper}")

    # 超长场景：大量建议任务时应正确截断，不产生乱码、不超过字节上限
    many_tasks = [SuggestedTask(task_id=f"RPT-20260714-{i:02d}", name="很长的任务名称" * 10,
                                  rationale="r", priority="P1", signal_to=["Jasper"], relevance_reason="rr")
                  for i in range(30)]
    big_briefing = DailyBriefing(generated_at="now", project_root="/path", files_added=50,
                                   suggested_tasks=many_tasks)
    long_content, _ = build_notification_text(big_briefing, mobiles, report_path="/path/report.md")
    check(len(long_content.encode("utf-8")) <= MAX_CONTENT_BYTES,
          f"超长简报被正确截断到限制内: {len(long_content.encode('utf-8'))} 字节",
          f"截断后仍超限: {len(long_content.encode('utf-8'))} 字节")
    try:
        long_content.encode("utf-8").decode("utf-8")
        check(True, "截断后的内容是合法 UTF-8，没有产生乱码", "")
    except UnicodeDecodeError:
        check(False, "", "截断后的内容不是合法 UTF-8，产生了乱码")


def test_15_wecom_file_upload_encoding(tmp_dir: Path):
    print("\n[Test 15] tools.wecom_notify 文件上传编码（不真实上传）")
    print("-" * 60)

    fixture = tmp_dir / "wecom_upload_fixture.md"
    fixture.write_text("# 测试简报\n中文内容验证编码", encoding="utf-8")

    body, content_type = _encode_multipart_file(fixture)
    check(content_type.startswith("multipart/form-data; boundary="),
          f"Content-Type 正确带 boundary: {content_type[:40]}...", "Content-Type 格式不对")
    check(b'filename="wecom_upload_fixture.md"' in body, "multipart body 包含正确文件名",
          "multipart body 缺少文件名字段")
    check("测试简报".encode("utf-8") in body, "multipart body 包含文件真实内容（中文没有乱码）",
          "multipart body 文件内容丢失或编码错误")
    check(b'Content-Disposition: form-data; name="media"' in body,
          "multipart body 的 name 字段是企业微信要求的 'media'", "name 字段不对")

    upload_url = _webhook_to_upload_url("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=testkey")
    check(upload_url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key=testkey&type=file",
          f"webhook URL 正确转换为上传接口 URL: {upload_url}", f"URL 转换错误: {upload_url}")


def test_16_office_file_extraction(tmp_dir: Path):
    print("\n[Test 16] tools.office_text 抽取 .docx/.xlsx 内容供 diff 使用")
    print("-" * 60)
    import docx
    import openpyxl
    from tools.office_text import extract_docx_text, extract_xlsx_text

    root = tmp_dir / "office_fixture"
    root.mkdir(parents=True, exist_ok=True)

    d = docx.Document()
    d.add_paragraph("变更说明：新增了L3-042审批流程")
    d.save(root / "变更说明.docx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["流程编号", "状态"])
    ws.append(["L3-042", "待审核"])
    wb.save(root / "台账.xlsx")

    docx_text = extract_docx_text(root / "变更说明.docx")
    check("L3-042" in docx_text and "审批流程" in docx_text,
          f"docx 内容被正确抽取为文本: {docx_text!r}", f"docx 抽取失败或内容缺失: {docx_text!r}")

    xlsx_text = extract_xlsx_text(root / "台账.xlsx")
    check("L3-042" in xlsx_text and "待审核" in xlsx_text,
          f"xlsx 内容被正确抽取为文本: {xlsx_text!r}", f"xlsx 抽取失败或内容缺失: {xlsx_text!r}")

    snap = snapshot_dir(root, extensions=daily_sensing.DEFAULT_SCAN_EXTENSIONS)
    check(set(snap.keys()) == {"变更说明.docx", "台账.xlsx"},
          f"docx/xlsx 被 DEFAULT_SCAN_EXTENSIONS 正确纳入扫描范围: {sorted(snap.keys())}",
          f"docx/xlsx 未被扫描到: {sorted(snap.keys())}")

    # 端到端：DailySensor.scan() 真的把抽取出的文本喂给了 LLM（用 stub 捕获
    # user_content 断言），不是把二进制原文/乱码送过去
    captured = {}

    def _stub_capture(system_prompt, user_content, api_key, model=None, **kw):
        captured["user_content"] = user_content
        return json.dumps({"changes": [], "relationships": [], "suggested_tasks": []}, ensure_ascii=False)

    daily_sensing.call_deepseek = _stub_capture
    sensor = DailySensor(root, api_key="fake-key-not-used")
    sensor.scan(previous_state={})
    check("L3-042" in captured.get("user_content", ""),
          "docx/xlsx 抽取出的文本真的被送进了 LLM 分析的 diff 片段里",
          f"喂给 LLM 的内容里没找到抽取出的文本: {captured.get('user_content', '')[:200]!r}")


def test_17_fingerprint_dedup_ignores_related_files_drift(tmp_dir: Path):
    print("\n[Test 17] skills.daily_sensing 指纹去重不受 related_files 波动影响")
    print("-" * 60)
    print("（复现 2026-07-15 真实巡检的 bug：同一件事在两次独立 LLM 调用间，")
    print("   related_files 输出有细微差异，旧版指纹把它俩当成了两个不同任务，")
    print("   同一天铸造出 5 组重复 RPT ID）")
    root = tmp_dir / "fingerprint_drift_fixture"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.md").write_text("v1\n", encoding="utf-8")

    sensor = DailySensor(root, api_key="fake-key-not-used")

    # 第一次真实变化：LLM 返回的 related_files 只提到 a.md
    def _stub_run1(system_prompt, user_content, api_key, model=None, **kw):
        return json.dumps({
            "changes": [{"file": "a.md", "summary": "初始内容"}],
            "relationships": [],
            "suggested_tasks": [{"name": "推动Mark裁定阈值", "rationale": "r1", "priority": "P1",
                                   "signal_to": ["Jasper"], "needs_mark_alignment": True,
                                   "relevance_reason": "rr", "related_files": ["a.md"]}],
        }, ensure_ascii=False)

    daily_sensing.call_deepseek = _stub_run1
    briefing1, state1, _ = sensor.scan(previous_state={})
    first_task_id = briefing1.suggested_tasks[0].task_id

    # 第二次真实变化（另一个文件也变了，diff 非空，真的会重新调用一次 LLM）：
    # 同一件事本质没变，但这次 LLM 把 related_files 多带了一个文件——旧版指纹
    # 把 name+related_files 一起哈希，这里就会因为 related_files 不同而误判成
    # "新任务"，这正是真实复现过的 bug。
    (root / "b.md").write_text("v1\n", encoding="utf-8")

    def _stub_run2(system_prompt, user_content, api_key, model=None, **kw):
        return json.dumps({
            "changes": [{"file": "b.md", "summary": "新增文件"}],
            "relationships": [],
            "suggested_tasks": [{"name": "推动Mark裁定阈值", "rationale": "r2（措辞略有不同）",
                                   "priority": "P1", "signal_to": ["Jasper"], "needs_mark_alignment": True,
                                   "relevance_reason": "rr", "related_files": ["a.md", "b.md"]}],
        }, ensure_ascii=False)

    daily_sensing.call_deepseek = _stub_run2
    briefing2, state2, task_map2 = sensor.scan(previous_state=state1)

    check(len(briefing2.suggested_tasks) == 1, f"同一件事没有被重复铸造（本次简报只有 1 条建议任务，得到 {len(briefing2.suggested_tasks)} 条）",
          f"related_files 变了就被误判成新任务，铸造出了重复 ID（{[t.task_id for t in briefing2.suggested_tasks]}）")
    check(briefing2.suggested_tasks[0].task_id == first_task_id,
          f"沿用了第一次的任务ID，未被判定为新任务: {briefing2.suggested_tasks[0].task_id}",
          f"任务ID变了，说明去重失效: 第一次={first_task_id}, 第二次={briefing2.suggested_tasks[0].task_id}")
    check(len(task_map2) == 1 and first_task_id in task_map2,
          "task_map_entries 也只有 1 条（不会往 pta_tasks.json 里 merge 出重复条目）",
          f"task_map_entries 异常: {list(task_map2.keys())}")


def test_18_rule_based_task_scan(tmp_dir: Path):
    print("\n[Test 18] skills.rule_based_task_scan 规则抽取（sha256 + 零 LLM 调用）")
    print("-" * 60)
    root = tmp_dir / "rule_scan_fixture"
    root.mkdir(parents=True, exist_ok=True)
    (root / "清单.md").write_text(
        "| work_id | action | named_owner | due_date | status |\n"
        "|---|---|---|---|---|\n"
        "| T-01 | 完成KPI映射表评审 | Terresa | 2020-01-01 | 待确认 |\n"
        "| T-02 | 归档访谈记录 | HR | 2099-01-01 | 完成 |\n",
        encoding="utf-8",
    )

    scanner = RuleBasedScanner(root)
    report1, state1 = scanner.scan(previous_state={})
    check(len(list(state1["file_hashes"].values())[0]) == 64,
          "真正切换到了 sha256（哈希长度64，不是 md5 的32）",
          f"哈希长度不对: {len(list(state1['file_hashes'].values())[0])}")
    check(len(report1.tasks) == 2 and report1.new_files == 1,
          f"从 markdown 表格正确抽取出 2 条任务，1 个新增文件", f"任务抽取结果不符预期: {report1.tasks}")
    overdue = [r for r in report1.risks if r.type == "overdue"]
    blocked = [r for r in report1.risks if r.type == "blocked"]
    check(len(overdue) == 1 and len(blocked) == 1,
          f"正确识别逾期({len(overdue)})和阻塞({len(blocked)})风险", f"风险识别不符预期: {report1.risks}")

    # 第二次扫描：文件没变化，任务应该原样保留、不重复铸造、不重新判定为新增
    report2, state2 = scanner.scan(previous_state=state1)
    check(report2.new_files == 0 and len(report2.tasks) == 2 and all(not t.is_new for t in report2.tasks),
          "无变化时任务原样保留、不重复标记为新增", f"增量复用失败: new_files={report2.new_files}, tasks={report2.tasks}")


def test_19_document_task_discovery(tmp_dir: Path):
    print("\n[Test 19] skills.document_task_discovery 增量去重 + 内容去重（stub 掉 LLM 调用）")
    print("-" * 60)
    root = tmp_dir / "discovery_fixture"
    root.mkdir(parents=True, exist_ok=True)
    (root / "会议纪要.md").write_text("Terresa 需要在下周五前完成 KPI 映射表的审阅工作。\n", encoding="utf-8")
    (root / "会议纪要_副本.md").write_text("Terresa 需要在下周五前完成 KPI 映射表的审阅工作。\n", encoding="utf-8")

    def _stub_with_task(system_prompt, user_content, api_key, model=None, **kw):
        return json.dumps({"tasks": [{"name": "审阅KPI映射表", "owner": "Terresa", "status": "pending",
                                        "due_date": "2026-07-24", "evidence": "下周五前完成", "confidence": 0.9}]},
                           ensure_ascii=False)

    document_task_discovery.call_deepseek = _stub_with_task
    discoverer = DocumentDiscoverer(root, api_key="fake-key-not-used")
    report1, state1 = discoverer.discover(previous_state={}, scan=True)

    check(len(report1.duplicates_skipped) == 1,
          "内容完全相同的重复文件被正确去重（只处理1份）", f"内容去重未生效: {report1.duplicates_skipped}")
    check(report1.files_scanned == 1 and len(report1.tasks) == 1,
          "只处理了1个文件、抽取出1条任务", f"结果不符预期: scanned={report1.files_scanned}, tasks={report1.tasks}")

    def _boom(*a, **kw):
        raise AssertionError("不应该调用——两份文件内容自上次运行以来都没有变化")
    document_task_discovery.call_deepseek = _boom

    report2, state2 = discoverer.discover(previous_state=state1, scan=True)
    # 两份文件都要被跳过——包括第一轮里被内容去重掉的那份：它的哈希也要被
    # 记进状态，否则下次运行会重新把它排进候选队列（这是迁移时发现并修复的
    # 一个真实 bug：内容去重跳过的文件此前没有被记进 file_hashes）
    check(report2.files_scanned == 0 and report2.incremental_skipped == 2,
          "无变化时两份文件都被增量跳过（含此前被内容去重掉的那份），零 LLM 调用",
          f"增量跳过失败: scanned={report2.files_scanned}, skipped={report2.incremental_skipped}")


def main():
    print("=" * 60)
    print("PTA 集成测试")
    print("=" * 60)

    tmp_dir = Path(tempfile.mkdtemp(prefix="pta_test_"))
    tmp_project = tmp_dir / "tmp_project"
    tmp_project.mkdir(parents=True, exist_ok=True)

    try:
        test_1_intent_parsing_multi_task()
        test_2_intent_parsing_ambiguous()

        parser = IntentParser()
        pkg = parser.parse("按顺序完成 P0-02, P0-03, P1-03, P1-04")
        task_dict = parser.to_dict(pkg)

        plan_dict = test_3_execution_planning_dry_run(task_dict)
        exec_result = test_4_progress_tracking(plan_dict)
        test_5_doc_sync_dry_run(tmp_project)
        test_6_archive_review(tmp_project, exec_result)
        test_7_agent_cli_full_loop(tmp_project)
        test_8_cross_project_task_knowledge(tmp_dir)
        test_9_git_ops_default_real_execution(tmp_dir)
        test_10_file_diff(tmp_dir)
        test_11_merge_suggested_tasks_safety(tmp_dir)
        test_12_daily_sensing_fingerprint_dedup(tmp_dir)
        test_13_daily_scan_cli_missing_api_key(tmp_dir)
        test_14_wecom_notify()
        test_15_wecom_file_upload_encoding(tmp_dir)
        test_16_office_file_extraction(tmp_dir)
        test_17_fingerprint_dedup_ignores_related_files_drift(tmp_dir)
        test_18_rule_based_task_scan(tmp_dir)
        test_19_document_task_discovery(tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        # Test 7/13 通过 subprocess 调用 agent.py，其专属工作区落在 memory.workspace 的
        # WORKSPACE_ROOT 下（按项目目录名算出来的），不在 tmp_dir 内，需要单独清理，
        # 否则每次跑测试都会在共享的 项目工作区/ 里留下痕迹。
        for name in (tmp_project.name, "daily_scan_cli_fixture"):
            shutil.rmtree(get_project_workspace(tmp_dir / name), ignore_errors=True)

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"PTA 集成测试失败（{len(FAILURES)} 项）")
        print("=" * 60)
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print("PTA 集成测试完成：19/19 通过")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
