#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTA Agent · 主循环（原 PTA-RUN_主编排器.py 迁移，Think-Act-Observe 结构）

  Think   → skills.intent_parsing.IntentParser        （理解自然语言指令，识别任务）
  Act     → skills.execution_planning.ExecutionScheduler（分解步骤 + 调用 tools 执行）
  Observe → skills.progress_tracking.ProgressTracker    （生成进度报告，含异常预警）

  之后固定跑一次 skills.archive_review（归档复盘：生成执行记录、提炼经验教训，
  纯本地写入，不含 git 动作）；只有显式传 --sync 时才额外调用 skills.doc_sync
  （唯一含真实 git push 的路径，逻辑与旧版一致：必须搭配 --execute + --message）。

  跨会话记忆（当前任务/历史任务）落在 memory.workspace 定义的专属工作区里，
  与目标项目物理隔离——这条约束原样保留，是迁移过程中唯一不允许简化的部分。

结构性改动（对照旧版 PTA-RUN 的说明）：
  旧版把 S01→S02→S03→S05 拆成 5 次独立 subprocess 调用，每一跳之间用临时 JSON
  文件中转，project_root 之类的参数要在每一跳手动重新拼进 --xxx 参数列表——
  这正是旧 bug 的成因（转发到 S05 那一跳时漏拼了 --project-root，导致执行记录
  写进了错误的项目目录，而不是调用方指定的目标项目）。新版所有技能都是同进程内
  的 Python 对象调用：project_root 在 run_instruction() 开头 resolve 一次之后，
  作为同一个变量原样传给下面每一个技能的构造函数，不存在"转发时漏传某一跳"这类
  结构性风险，因为已经没有"跳"这个概念了。

运行方式（从 PTA 项目根目录调用，路径按 01-11 方法论结构，见 PTA/README.md）：
  python3 04_定义Agent_Define_Agent/agents/agent.py --status
  python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04"        # 默认 dry-run
  python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04" --execute
  python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P1-03, P1-04" --execute --sync -m "commit msg"

未迁移的范围：--discover（PTA-DISCOVER 文档任务发现）不在这次迁移范围内——
用户明确要迁移的是"S01 的意图解析、S02 的执行调度"这类核心 Think-Act-Observe
逻辑，DISCOVER/DASH/EXT/INTEL/SCAN 这些扩展脚本的去留还没有跟用户确认，暂时
搬到 11_监控与优化_Monitor_and_Optimize/ 里独立可用，不接入这个新主循环。

v2.3.0 新增 --daily-scan：这是独立于上面 Think-Act-Observe 主循环的另一个
入口（不是每句指令都会触发的那种"Think"），专门对应"每天自动感知项目变化、
提炼建议任务"这个主动能力——detail 见 skills/daily_sensing.py 和
cmd_daily_scan()。它只产出简报 + 把建议任务写进目标项目的 pta_tasks.json，
从不自动执行；确认执行某条建议时，走的是完全不变的 run_instruction() 路径。

目录方法论说明（v2.1.0 起）：agents/skills/tools/memory/prompts/tests 六个
Python 包目录，各自嵌套在一个编号+中英文的顶层文件夹里（如本文件所在的
04_定义Agent_Define_Agent/agents/），编号只是给人看的顺序标识——Python 的
import 语句不能以数字开头，所以实际可 import 的包名（agents/skills/tools/
memory）本身没变，只是外面多包了一层编号目录。因此下面 sys.path 需要把每个
编号目录（而不是 PTA_DIR 本身）加进去，让 `from skills.xxx import` 这类语句
继续按包名解析。
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

AGENTS_DIR = Path(__file__).resolve().parent
NUMBERED_DIR = AGENTS_DIR.parent          # 04_定义Agent_Define_Agent/
PTA_DIR = NUMBERED_DIR.parent              # PTA 项目根目录
HOME_PROJECT_ROOT = PTA_DIR.parent.parent.parent  # PTA -> 草稿 -> 05_Agent库 -> 项目根目录

for _pkg_dir in ("05_集成工具_Integrate_Tools", "06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(PTA_DIR / _pkg_dir))  # 让 tools/skills/memory 能被当作包 import

from memory import workspace as ws
from skills.intent_parsing import IntentParser
from skills.execution_planning import ExecutionScheduler
from skills.progress_tracking import ProgressTracker
from skills.archive_review import ArchiveReviewer
from skills.doc_sync import DocumentSyncer
from skills.daily_sensing import (DailySensor, to_dict as daily_sensing_to_dict,
                                    format_text as format_daily_briefing, format_text_plain)
from skills.project_dashboard import generate_for_person as generate_dashboard
from skills.rule_based_task_scan import (RuleBasedScanner, format_report_text as format_rule_scan_text,
                                          format_task_assignment_markdown)
from skills.document_task_discovery import (DocumentDiscoverer, format_text as format_discovery_text,
                                             to_dict as discovery_to_dict)
from skills.project_intelligence import ProjectIntelligence, format_analyze_text, format_cross_text
from skills.pipeline_health import (load_checks, run_all_checks, _save_baseline, REPORT_DIR_RELATIVE,
                                     format_report_markdown as format_pipeline_report_markdown)
from tools.task_knowledge import load_task_map, merge_suggested_tasks
from tools.dir_scan import analyze_project, format_report_text, format_report_markdown
from tools.wecom_notify import (load_wecom_config, build_notification_text_from_content,
                                 send_text as send_wecom_text, upload_file as upload_wecom_file,
                                 send_file as send_wecom_file)


def _resolve_project_root(project_root: str = None) -> Path:
    return Path(project_root).resolve() if project_root else HOME_PROJECT_ROOT


DAILY_SCAN_PROJECTS_PATH = PTA_DIR / "02_配置项目_Configure_Project" / "daily_scan_projects.json"
PROMPTS_DIR = PTA_DIR / "08_设计提示词_Design_Prompts" / "prompts"


def _resolve_daily_scan_system_prompt(resolved_root: Path) -> Optional[Path]:
    """按 resolved_root 去 daily_scan_projects.json 里找对应项目条目的
    system_prompt 覆盖（相对 08_设计提示词_Design_Prompts/prompts/ 的文件名）。

    背景：一套通用提示词判断"这条变化跟我有没有关系"太粗——EA项目的判断标准
    是"是否触发流程/SOP/人机协同规则修订、该找四人裁定模型里的谁"，Jasper工作
    文档的判断标准是"这个方法/工具是否已经具备反哺EA的条件"，Rw项目暂时还是
    通用判断。找不到匹配项目/没配置system_prompt字段/配置文件本身不存在，都
    返回None——调用方据此使用DailySensor的默认通用提示词，不报错。"""
    if not DAILY_SCAN_PROJECTS_PATH.exists():
        return None
    try:
        data = json.loads(DAILY_SCAN_PROJECTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    for p in data.get("projects", []):
        root = p.get("project_root", "")
        if root and Path(root).resolve() == resolved_root:
            prompt_name = p.get("system_prompt")
            return (PROMPTS_DIR / prompt_name) if prompt_name else None
    return None


def cmd_status(project_root: str = None) -> None:
    resolved_root = _resolve_project_root(project_root)
    workspace = ws.get_project_workspace(resolved_root)
    state = ws.load_state(workspace)

    print("=" * 60)
    print(f"[PTA Agent] 当前状态 · {resolved_root}")
    print(f"工作区: {workspace}")
    print("=" * 60)

    cur = state.get("current_task")
    if cur:
        print(f"当前任务: {cur.get('task_id')} · {cur.get('status')}"
              f"（{cur.get('mode', '?')}，{cur.get('success_rate', '?')}）")
    else:
        print("当前任务: 无")

    history = state.get("task_history", [])
    print(f"\n历史任务（共 {len(history)} 条，最近 5 条）:")
    if not history:
        print("  （空）")
    for h in history[-5:]:
        print(f"  - [{h.get('timestamp', '')[:19]}] {h.get('task_id')}: "
              f"{h.get('summary', '')} → {h.get('status')} ({h.get('success_rate', '?')})")

    ctx = state.get("context", {})
    if ctx:
        print(f"\n上下文: {json.dumps(ctx, ensure_ascii=False)}")

    print("=" * 60)


def cmd_daily_scan(project_root: str = None, force: bool = False, notify: bool = False,
                    extra_exclude_dirs: list = None) -> None:
    """每日主动巡检：本地 diff → 合并 LLM 分析 → 建议任务写进 pta_tasks.json，
    但绝不自动执行——确认执行走的是 run_instruction() 完全不变的现有路径
    （`agent.py "执行 RPT-xxx" --execute`），这里只负责"发现+提议"。

    notify=True 时额外把简报摘要推到企业微信群（@ 相关方）——默认关闭：现在
    还在验证阶段，测试跑出来的假信号不该真的推进群里，需要显式加 --notify。"""
    resolved_root = _resolve_project_root(project_root)
    workspace = ws.get_project_workspace(resolved_root)

    sensing_state = ws.load_daily_sensing_state(workspace)
    state = ws.load_state(workspace)
    recent_history = state.get("task_history", [])[-5:]

    prompt_override = _resolve_daily_scan_system_prompt(resolved_root)
    sensor_kwargs = {"extra_exclude_dirs": set(extra_exclude_dirs) if extra_exclude_dirs else None}
    if prompt_override:
        sensor_kwargs["system_prompt_path"] = prompt_override
    sensor = DailySensor(resolved_root, **sensor_kwargs)
    try:
        briefing, updated_sensing_state, task_map_entries = sensor.scan(
            sensing_state, force=force, recent_task_history=recent_history)
    except RuntimeError as e:
        print(f"[错误] {e}")
        sys.exit(1)

    text = format_daily_briefing(briefing)
    print(text)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_json_path = workspace / "reports" / f"daily-scan-{run_id}.json"
    report_md_path = workspace / "reports" / f"daily-scan-{run_id}.md"
    report_plain_path = workspace / "reports" / f"daily-scan-{run_id}-plain.md"
    report_json_path.write_text(json.dumps(daily_sensing_to_dict(briefing), ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    report_md_path.write_text(text, encoding="utf-8")
    report_plain_path.write_text(format_text_plain(briefing), encoding="utf-8")

    ws.save_daily_sensing_state(workspace, updated_sensing_state)

    if task_map_entries:
        merge_suggested_tasks(resolved_root, task_map_entries)
        print(f"\n{len(task_map_entries)} 条建议任务已写入: {resolved_root / 'pta_tasks.json'}")

    state.setdefault("context", {})["last_daily_scan"] = {
        "timestamp": datetime.now().isoformat(), "report_path": str(report_md_path),
    }
    ws.save_state(workspace, state)

    if notify and (briefing.suggested_tasks or briefing.resolved_tasks):
        config = load_wecom_config()
        if not config:
            print("\nℹ️ 未找到 wecom_config.json，跳过企业微信通知"
                  "（模板见 02_配置项目_Configure_Project/wecom_config.example.json）。")
        else:
            # 正文用通俗版（format_text_plain）：不出现文件路径/域标签这类
            # 技术细节，手机上扫一眼就知道新增/搁置/完成各有几条；详细版
            # （report_md_path，逐域分组+完整理由）作为文件附件随后发出，
            # 两个版本各司其职，不是互相替代。
            plain_text = format_text_plain(briefing)
            content, mentioned_mobiles = build_notification_text_from_content(
                plain_text, config.get("mobiles", {}), report_path=str(report_md_path))
            result = send_wecom_text(config["webhook_url"], content, mentioned_mobiles)
            if result.get("errcode") == 0:
                print(f"\n✅ 企业微信通知已发送（@ {len(mentioned_mobiles)} 人）")
                # 文本消息里塞的是本地文件路径，收消息的人如果不在这台 Mac 上（比如
                # 用手机看企业微信），点不开——额外把完整简报作为文件附件发进群，
                # 上传失败不影响已经发出去的文本通知，只是降级为"没有附件"。
                media_id = upload_wecom_file(config["webhook_url"], report_md_path)
                if media_id:
                    file_result = send_wecom_file(config["webhook_url"], media_id)
                    if file_result.get("errcode") == 0:
                        print("✅ 完整简报文件已发送（可直接在企业微信里点开）")
                    else:
                        print(f"⚠️ 完整简报文件发送失败: {file_result.get('errmsg')}")
            else:
                print(f"\n⚠️ 企业微信通知发送失败: {result.get('errmsg')}")

    print(f"\n简报已保存: {report_md_path}")


def cmd_dismiss(task_id: str, project_root: str = None) -> None:
    """人工关闭一条建议任务，不走--execute（比如已经用别的方式处理掉了，
    或者判断这条建议不需要真的执行）。跟 mark_suggested_task_status(..., "done")
    是同一个补齐"执行→回写"闭环的机制，区别只是状态标"dismissed"而不是
    "done"——报告里会分别标注"已完成"和"已关闭（人工判定不需要执行）"，
    不混为一谈。"""
    resolved_root = _resolve_project_root(project_root)
    workspace = ws.get_project_workspace(resolved_root)
    found = ws.mark_suggested_task_status(workspace, task_id, "dismissed")
    if found:
        print(f"[dismiss] {task_id} 已标记为关闭，下次简报会展示一次「已关闭」后不再出现。")
    else:
        print(f"[dismiss] 未找到 {task_id}（可能不是 daily_sensing 产出的建议任务，或项目路径不对）。")


def cmd_seed_baseline(project_root: str = None, extra_exclude_dirs: list = None) -> None:
    """给从未跑过 --daily-scan 的项目建立起点基线，不调 LLM、不产出简报、
    不推送通知——只是本地文件快照写进 daily_sensing_state.json。真实场景：
    Rw权益项目(1719候选文件)/Jasper工作文档(440候选文件)首次接入多项目巡检
    时都没有基线，直接跑 --daily-scan 会把全部文件当"今天的变化"打包成一次
    巨大的合并LLM调用，语义不对也真实费token；先种子基线，从下一次真实
    --daily-scan 起才是名副其实的增量对比。"""
    resolved_root = _resolve_project_root(project_root)
    workspace = ws.get_project_workspace(resolved_root)

    sensor = DailySensor(resolved_root, extra_exclude_dirs=set(extra_exclude_dirs) if extra_exclude_dirs else None)
    seeded_state = sensor.seed_baseline()
    ws.save_daily_sensing_state(workspace, seeded_state)
    print(f"[seed-baseline] 已为 {resolved_root} 建立基线：{len(seeded_state['file_hashes'])} 个文件，"
          f"未调用LLM、未产出简报。下一次 --daily-scan 起才是真正的增量对比。")


def cmd_dashboard(project_root: str = None, person: str = "all") -> None:
    """项目仪表盘（原 PTA-DASH，批1 迁移）：以人为中心的报告，不接入 Think-Act-Observe
    主循环——这是"给人看的报告"，不是"任务执行"，不需要状态记忆/归档。"""
    resolved_root = _resolve_project_root(project_root)
    try:
        print(generate_dashboard(resolved_root, person))
    except RuntimeError as e:
        print(f"[错误] {e}")
        sys.exit(1)


def cmd_dir_scan(project_root: str = None, depth: int = 2, output: str = None) -> None:
    """目录结构分析（原 PTA-EXT，批1 迁移）：只读统计，同样不接入主循环。"""
    resolved_root = _resolve_project_root(project_root)
    report = analyze_project(resolved_root, max_depth=depth)
    print(format_report_text(report))
    if output:
        Path(output).write_text(format_report_markdown(report), encoding="utf-8")
        print(f"\nMarkdown 报告已保存: {output}")


def cmd_rule_scan(project_root: str = None) -> None:
    """规则扫描（原 PTA-SCAN，批2 迁移）：本地零成本抽取已结构化文档（markdown
    表格/CSV）里的任务，识别逾期/阻塞/无负责人风险。不调用 LLM，跟 --daily-scan
    互补而非重叠——两者刻意保持独立技能。"""
    resolved_root = _resolve_project_root(project_root)
    workspace = ws.get_project_workspace(resolved_root)

    state = ws.load_rule_scan_state(workspace)
    scanner = RuleBasedScanner(resolved_root)
    report, updated_state = scanner.scan(state)

    print(format_rule_scan_text(report))
    ws.save_rule_scan_state(workspace, updated_state)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = workspace / "reports" / f"rule-scan-{run_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(format_task_assignment_markdown(report), encoding="utf-8")
    print(f"\n任务分配报告已保存: {output_path}")


def cmd_discover(project_root: str = None, files: list = None, scan: bool = False,
                  force: bool = False, dry_run: bool = False, use_ob_context: bool = False) -> None:
    """文档任务发现（原 PTA-DISCOVER，批2 迁移）：LLM 阅读叙述性文档（合同/会议
    纪要/审计报告），抽取隐含任务，产出发现报告供人工审阅分类——安全边界不变：
    绝不自动写入 pta_tasks.json 的可执行 steps，只合并进 task_registry.json。

    use_ob_context=True 时接入 OB 背景检索（tools/ob_bridge.py，PTA↔OB 接口
    设计的第一个真实试点），每个文件分析前先问一次 OB "这份文档相关的项目
    背景是什么"，注入提示词——目的是缓解本技能在叙述性文档上噪音大的问题
    （历史记录容易被误判成新任务）。默认关闭，新接口先小范围验证。"""
    resolved_root = _resolve_project_root(project_root)
    workspace = ws.get_project_workspace(resolved_root)
    state = ws.load_discover_state(workspace)

    discoverer = DocumentDiscoverer(resolved_root, use_ob_context=use_ob_context)
    try:
        report, updated_state = discoverer.discover(
            state, explicit_files=files, scan=scan, force=force, dry_run=dry_run)
    except RuntimeError as e:
        print(f"[错误] {e}")
        sys.exit(1)

    print(format_discovery_text(report))

    if dry_run:
        return

    ws.save_discover_state(workspace, updated_state)

    if report.tasks:
        ws.merge_task_registry(workspace, report.tasks)
        print(f"\n任务已合并进登记表: {workspace / 'task_registry.json'}")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = workspace / "reports" / f"discover-{run_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(discovery_to_dict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {output_path}")


def cmd_intel(project_root: str = None, mode: str = "analyze", query: str = None, output: str = None) -> None:
    """项目智能分析（原 PTA-INTEL/INTEL-RW 合并，批3 迁移）：自动探测目标项目
    目录下有没有 Rw 特征跟踪台账 CSV，有就用 Rw 专用解析器，没有就退回通用
    Markdown/CSV 解析器——调用方不需要自己判断该用哪个后端。只读分析，不接入
    Think-Act-Observe 主循环，跟 --dashboard/--dir-scan 是同一类"给人看的报告"。"""
    resolved_root = _resolve_project_root(project_root)
    intel = ProjectIntelligence(resolved_root)

    if mode == "analyze":
        status = intel.analyze()
        text = format_analyze_text(status, intel.is_rw)
        print(text)
    elif mode == "query":
        if not query:
            print("[错误] --intel-mode query 需要提供 --query 参数")
            sys.exit(1)
        text = intel.query(query)
        print(text)
    elif mode == "cross":
        contradictions, gaps, duplicates = intel.cross()
        text = format_cross_text(contradictions, gaps, duplicates)
        print(text)

    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"\n报告已保存: {output}")


def cmd_pipeline_check(project_root: str = None, checks_path: str = None,
                        notify: bool = False, dry_run: bool = False) -> None:
    """Pipeline差距矩阵周检测（新增能力，跟 --daily-scan 平级、不是它的子功能）：
    依据 05_Agent库/草稿/_pipeline_health/checks.json 里定义的检测项，逐条查证据
    （文件存在性/测试exit code/字段读取/mtime），跟上次记录比对，把"矩阵声明"
    和"实际状态"的差异摆出来——全部是确定性检查，不调用 LLM，不做主观判断。

    dry_run=True 时只打印报告到终端，不写报告文件、不更新基线、不发通知——
    首次启用必须先 --dry-run 核对输出格式和检测项跑得通，跟 daily_sensing
    v2.3.0 上线时的做法一致。"""
    resolved_root = _resolve_project_root(project_root)
    # 不同于 task_map 的"未显式传 --project-root 就不查目标目录"策略：
    # checks.json 天然就属于被检测项目自己（这次是本项目自己检测自己），
    # 默认目标（home project）下也应该直接命中它真实的 checks.json，
    # 不应该退化去用兜底的空白默认值。
    checks = load_checks(checks_path, resolved_root)

    if not checks:
        print("[pipeline-check] 未找到任何检测项定义（checks.json 为空或不存在），无事可做。")
        return

    report_dir = resolved_root / REPORT_DIR_RELATIVE
    report_dir.mkdir(parents=True, exist_ok=True)

    results, new_baseline = run_all_checks(resolved_root, checks, report_dir)
    run_date = datetime.now().strftime("%Y-%m-%d")
    report_text = format_pipeline_report_markdown(results, run_date)
    print(report_text)

    if dry_run:
        print("ℹ️ [DRY-RUN] 未写入报告文件、未更新基线、未发送通知。")
        return

    report_path = report_dir / f"检测记录_{run_date}.md"
    report_path.write_text(report_text, encoding="utf-8")
    _save_baseline(report_dir, new_baseline)
    print(f"\n报告已保存: {report_path}")

    drifted = [r for r in results if r.drift is True]
    if notify and drifted:
        config = load_wecom_config()
        if not config:
            print("\nℹ️ 未找到 wecom_config.json，跳过企业微信通知。")
        else:
            lines = [f"【PTA Pipeline周检测】发现 {len(drifted)} 处与矩阵声明不一致："]
            for r in drifted[:10]:
                c = r.check
                lines.append(f"- [{c['stage_id']} {c['stage_name']}/{c['dimension']}] {c['claim']}")
            lines.append(f"\n完整报告: {report_path}")
            content = "\n".join(lines)
            mobiles = config.get("mobiles", {})
            mentioned = [mobiles["Jasper"]] if "Jasper" in mobiles else []
            result = send_wecom_text(config["webhook_url"], content, mentioned)
            if result.get("errcode") == 0:
                print("\n✅ 企业微信通知已发送")
            else:
                print(f"\n⚠️ 企业微信通知发送失败: {result.get('errmsg')}")
    elif notify:
        print("\nℹ️ 本周无drift，跳过企业微信通知（无需打扰）。")


def run_instruction(instruction: str, execute: bool, sync: bool, message: str,
                     project_root: str = None, task_map: str = None) -> None:
    resolved_root = _resolve_project_root(project_root)
    workspace = ws.get_project_workspace(resolved_root)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    task_knowledge = load_task_map(task_map, resolved_root if project_root else None)
    state = ws.load_state(workspace)

    # ---------- Think：意图解析 ----------
    ws.log_skill_call("intent_parsing", project_root)
    parser = IntentParser(task_map=task_knowledge)
    task_package = parser.parse(instruction)
    task_dict = parser.to_dict(task_package)
    (run_dir / "task.json").write_text(json.dumps(task_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    task_id = task_package.task_id
    items = task_package.items
    task_name = items[0].name if items else "Unknown"

    if task_package.needs_clarification:
        print("\n⚠️ 指令不够明确，需要澄清后才能继续：")
        for q in task_package.clarification_questions:
            print(f"  - {q}")
        entry = {
            "task_id": task_id, "summary": instruction[:60], "status": "blocked_clarification",
            "success_rate": "n/a", "mode": "n/a", "timestamp": datetime.now().isoformat(),
        }
        state["current_task"] = entry
        # 同样追加进 task_history（此前这里只更新了 current_task、漏了 history.append，
        # 导致"指令被判定为模糊、要求澄清"这类事件永远进不了历史记录——11_监控与优化/
        # PTA-MONITOR_自我监控.py 想统计"澄清触发率"作为指令质量的诊断指标，靠的正是
        # 这份 history，漏记会让这个指标永远显示 0，形同虚设）
        history = state.setdefault("task_history", [])
        history.append(entry)
        state["task_history"] = history[-50:]
        ws.save_state(workspace, state)
        return

    # ---------- Act：执行编排（include_sync=False，同步是独立的显式阶段，见文件头）----------
    ws.log_skill_call("execution_planning", project_root)
    scheduler = ExecutionScheduler(resolved_root, dry_run=not execute, task_map=task_knowledge)
    plan = scheduler.create_plan(task_dict, include_sync=False)
    exec_result = scheduler.execute_plan(plan)
    plan_dict = scheduler.to_dict(plan)
    (run_dir / "plan.json").write_text(json.dumps(plan_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- Observe：进度报告 ----------
    ws.log_skill_call("progress_tracking", project_root)
    tracker = ProgressTracker(plan_dict)
    report = tracker.generate_report()
    tracker.print_report(report)
    report_dict = tracker.to_dict(report)
    (run_dir / "report.json").write_text(json.dumps(report_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 状态记忆更新 ----------
    entry = {
        "task_id": task_id, "summary": instruction[:60], "status": report_dict.get("status", "unknown"),
        "success_rate": f"{report_dict.get('completed', 0)}/{report_dict.get('total', 0)}",
        "mode": "execute" if execute else "dry-run", "timestamp": datetime.now().isoformat(),
        "run_dir": str(run_dir),
    }
    state["current_task"] = entry
    history = state.setdefault("task_history", [])
    history.append(entry)
    state["task_history"] = history[-50:]
    state.setdefault("context", {})["last_run"] = run_id
    ws.save_state(workspace, state)

    # ---------- 执行→回写闭环（补 daily_sensing 此前缺失的一环）----------
    # 真实执行成功、且 task_id 恰好是 daily_sensing 铸造的建议任务（fingerprint
    # 里能找到）时，把它标记为 done——否则这条建议会永远停在"pending"，天天
    # 在简报里重复出现，看不出到底有没有人处理过。task_id 不是 daily_sensing
    # 产出的（比如手写的 P0-02）时，mark_suggested_task_status 找不到、静默
    # 返回 False，不影响这里的主流程。
    if execute and report_dict.get("status") == "completed":
        ws.mark_suggested_task_status(workspace, task_id, "done")

    # ---------- 归档复盘（本地写入，无 git 动作，始终执行）----------
    ws.log_skill_call("archive_review", project_root)
    reviewer = ArchiveReviewer(resolved_root)
    reviewer.review(task_id, task_name, plan_dict, update_lessons=False)

    # ---------- 产出同步（唯一含真实 git push 的阶段，需显式确认）----------
    if sync:
        if not execute:
            print("\n⚠️ --sync 需搭配 --execute 一起使用（dry-run 没有真实产出可同步），已跳过。")
        elif not message:
            print("\n⚠️ --sync 需要提供 --message，已跳过。")
        else:
            ws.log_skill_call("doc_sync", project_root)
            syncer = DocumentSyncer(resolved_root, dry_run=False)
            syncer.sync(task_id, task_name, message)
    else:
        print(f"\nℹ️ 未同步文档。如需同步（会真实 git push），追加 --sync --execute -m \"...\"")

    print(f"\n运行产物目录: {run_dir}")


def main():
    parser = argparse.ArgumentParser(description="PTA Agent · 主循环（Think-Act-Observe + 状态记忆）")
    parser.add_argument("instruction", nargs="?", help="自然语言指令，缺省则等价于 --status")
    parser.add_argument("--status", action="store_true", help="查看当前/历史任务状态")
    parser.add_argument("--execute", action="store_true", help="真实执行任务步骤（默认仅 dry-run 出计划+报告）")
    parser.add_argument("--sync", action="store_true",
                         help="执行后做真实文档同步（git add/commit/push），需搭配 --execute 和 --message")
    parser.add_argument("--message", "-m", help="--sync 时的 git 提交信息")
    parser.add_argument("--project-root",
                         help="目标项目根目录（不传则默认本项目；决定去哪个专属工作区读写状态、"
                              "去该目录下找 pta_tasks.json）")
    parser.add_argument("--task-map", help="显式指定任务知识库 JSON 文件路径（优先级高于 --project-root）")
    parser.add_argument("--daily-scan", action="store_true",
                         help="每日主动巡检：检测文件变化+关系分析+提炼建议任务（需 DEEPSEEK_API_KEY），"
                              "只生成简报写进 pta_tasks.json，不自动执行")
    parser.add_argument("--force", action="store_true",
                         help="--daily-scan/--discover 专用：忽略增量哈希基线，把所有文件当新增重新分析一遍")
    parser.add_argument("--dismiss", metavar="TASK_ID",
                         help="人工关闭一条daily_sensing建议任务（不执行），标记为dismissed，"
                              "下次简报展示一次「已关闭」后不再重复出现")
    parser.add_argument("--seed-baseline", action="store_true",
                         help="给从未跑过--daily-scan的项目建立起点基线，不调LLM/不产出简报/不推送通知，"
                              "只写本地文件快照；避免首次真实巡检把全部现存文件当'今天的变化'打包分析")
    parser.add_argument("--exclude-dirs", nargs="*",
                         help="--daily-scan 专用：额外排除的目录名（与内置的 .git/node_modules 等默认排除项"
                              "取并集，不是替换），用于把大文件夹里跟本项目无关的子目录排除在扫描外")
    parser.add_argument("--notify", action="store_true",
                         help="--daily-scan/--pipeline-check 共用：有建议任务/发现drift时推送企业微信"
                              "群通知，默认关闭，需要先配置 02_配置项目_Configure_Project/wecom_config.json")
    parser.add_argument("--dashboard", action="store_true",
                         help="项目仪表盘（原 PTA-DASH，Rw 项目专用）：以人为中心的进度/风险报告")
    parser.add_argument("--person", "-u", default="all",
                         help="--dashboard 专用：人员名称，默认 all（整体视图）")
    parser.add_argument("--dir-scan", action="store_true",
                         help="目录结构分析（原 PTA-EXT）：只读统计文件数/体积/类型分布")
    parser.add_argument("--depth", type=int, default=2, help="--dir-scan 专用：扫描深度（默认 2）")
    parser.add_argument("--report-output", help="--dir-scan/--intel 专用：报告输出路径")
    parser.add_argument("--rule-scan", action="store_true",
                         help="规则扫描（原 PTA-SCAN，批2迁移）：本地零成本抽取markdown表格/CSV里的"
                              "结构化任务，识别逾期/阻塞/无负责人风险，不调用 LLM")
    parser.add_argument("--discover", action="store_true",
                         help="文档任务发现（原 PTA-DISCOVER，批2迁移）：LLM 阅读叙述性文档（需 "
                              "DEEPSEEK_API_KEY），抽取隐含任务供人工审阅，不进 pta_tasks.json 可执行流程")
    parser.add_argument("--files", nargs="*", help="--discover 专用：显式指定候选文件，总是处理，不受增量状态影响")
    parser.add_argument("--scan", action="store_true",
                         help="--discover 专用：自动扫描项目内候选文档，按增量状态过滤")
    parser.add_argument("--use-ob-context", action="store_true",
                         help="--discover 专用：分析前先调用OB（tools/ob_bridge.py）检索项目背景注入"
                              "提示词，缓解叙述性文档上的噪音；默认关闭，需要OB agent.py可正常运行")
    parser.add_argument("--dry-run", action="store_true",
                         help="--discover 专用：只列出候选文件和估算字符数，不调用 API，不更新增量状态；"
                              "--pipeline-check 专用：只打印报告，不写报告文件/不更新基线/不发通知")
    parser.add_argument("--intel", action="store_true",
                         help="项目智能分析（原 PTA-INTEL/INTEL-RW 合并，批3迁移）：自动探测 Rw 项目特征 "
                              "CSV 选解析器，深度文档分析/自然语言查询/跨文档矛盾遗漏重复检测")
    parser.add_argument("--intel-mode", choices=["analyze", "query", "cross"], default="analyze",
                         help="--intel 专用：分析模式，默认 analyze")
    parser.add_argument("--query", "-q", help="--intel --intel-mode query 专用：自然语言查询问题")
    parser.add_argument("--pipeline-check", action="store_true",
                         help="Pipeline差距矩阵周检测：依据 checks.json 定义的确定性检查项（文件存在性/"
                              "测试exit code/字段读取/mtime），核实矩阵声明与实际状态是否一致，不做主观判断")
    parser.add_argument("--checks-path", help="显式指定 checks.json 路径（优先级高于 --project-root）")
    args = parser.parse_args()

    # 每个分发分支调用前记一条skill调用日志——纯统计用途，为"哪个skill用得多/
    # 几乎没人用"这类未来优化判断提供依据，不影响任何主流程行为，写入失败也
    # 静默忽略（见 memory.workspace.log_skill_call 的设计）。
    if args.dismiss:
        ws.log_skill_call("dismiss", args.project_root)
        cmd_dismiss(task_id=args.dismiss, project_root=args.project_root)
        return

    if args.seed_baseline:
        ws.log_skill_call("seed_baseline", args.project_root)
        cmd_seed_baseline(project_root=args.project_root, extra_exclude_dirs=args.exclude_dirs)
        return

    if args.daily_scan:
        ws.log_skill_call("daily_sensing", args.project_root)
        cmd_daily_scan(project_root=args.project_root, force=args.force, notify=args.notify,
                       extra_exclude_dirs=args.exclude_dirs)
        return

    if args.dashboard:
        ws.log_skill_call("project_dashboard", args.project_root)
        cmd_dashboard(project_root=args.project_root, person=args.person)
        return

    if args.dir_scan:
        ws.log_skill_call("dir_scan", args.project_root)
        cmd_dir_scan(project_root=args.project_root, depth=args.depth, output=args.report_output)
        return

    if args.rule_scan:
        ws.log_skill_call("rule_based_task_scan", args.project_root)
        cmd_rule_scan(project_root=args.project_root)
        return

    if args.discover:
        ws.log_skill_call("document_task_discovery", args.project_root)
        cmd_discover(project_root=args.project_root, files=args.files, scan=args.scan,
                     force=args.force, dry_run=args.dry_run, use_ob_context=args.use_ob_context)
        return

    if args.intel:
        ws.log_skill_call("project_intelligence", args.project_root)
        cmd_intel(project_root=args.project_root, mode=args.intel_mode, query=args.query,
                 output=args.report_output)
        return

    if args.pipeline_check:
        ws.log_skill_call("pipeline_health", args.project_root)
        cmd_pipeline_check(project_root=args.project_root, checks_path=args.checks_path,
                           notify=args.notify, dry_run=args.dry_run)
        return

    if args.status or not args.instruction:
        cmd_status(project_root=args.project_root)
        return

    run_instruction(args.instruction, args.execute, args.sync, args.message,
                     project_root=args.project_root, task_map=args.task_map)


if __name__ == "__main__":
    main()
