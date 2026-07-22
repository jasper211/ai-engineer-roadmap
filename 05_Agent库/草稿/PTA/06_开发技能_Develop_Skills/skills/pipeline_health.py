#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：pipeline_health · Pipeline差距矩阵周检测

依据规格《Pipeline差距矩阵_检测机制设计_v1.0.md》：把矩阵（[RPT]_AI协同建造者_
Agent架构目标差距与实现路径_Jasper_v5.0.html）里能查证的部分，跟当前代码/配置
的真实状态做一次比对，只把"声明"和"事实"的差异摆出来，不做主观判断——判断
"这个差异要不要改矩阵、改多少分"，留给人（Jasper/Mark）。

跟 daily_sensing 刻意保持独立（规格§六归属原文）：本技能全部是确定性检查（文件
存在性/测试exit code/字段读取/mtime），不需要 daily_sensing 那套 LLM 关系分析
（tools/llm_client.py），混进去反而降低确定性、且平白产生 DeepSeek 调用费用。

检测项定义外置在 checks.json（结构类比 pta_tasks.json），本文件是纯粹的"读取
配置 → 逐条查证据 → 出报告"引擎，不硬编码任何项目特定的检测逻辑判断。
"""

import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_CHECKS_PATH = Path(__file__).resolve().parent.parent / "pipeline_checks_default.json"
CHECKS_RELATIVE_PATH = Path("05_Agent库/草稿/_pipeline_health/checks.json")
REPORT_DIR_RELATIVE = Path("05_Agent库/草稿/_pipeline_health")


def load_checks(explicit_path: Optional[str], project_root: Optional[Path]) -> List[dict]:
    """加载检测项定义，优先级跟 tools.task_knowledge.load_task_map 同款：
    1. explicit_path 显式指定的文件
    2. project_root 下的 05_Agent库/草稿/_pipeline_health/checks.json
    3. PTA 自带的 pipeline_checks_default.json（空列表兜底，向后兼容）

    找不到/解析失败时返回空列表——调用方需要对"这个项目还没有pipeline健康检测
    定义"这个正常状态优雅降级，不报错。
    """
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    if project_root:
        candidates.append(Path(project_root) / CHECKS_RELATIVE_PATH)
    candidates.append(DEFAULT_CHECKS_PATH)

    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("checks", [])
            except json.JSONDecodeError as e:
                print(f"[警告] checks.json 解析失败，跳过: {path} ({e})")
                continue
    return []


def _load_baseline(report_dir: Path) -> Dict[str, dict]:
    path = report_dir / ".baseline.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[警告] 基线文件损坏，本次当作首次运行处理: {path}")
    return {}


def _save_baseline(report_dir: Path, baseline: Dict[str, dict]) -> None:
    path = report_dir / ".baseline.json"
    path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# 证据探针：每种 probe.kind 对应一个只读函数，只负责"查出当前值是什么"，
# 不做"这个值好不好"的判断——判断逻辑统一在 run_check() 里按 mode 做
# 机械的"新旧值是否一致"比对，不掺业务语义。
# ============================================================

def _resolve(project_root: Path, probe: dict) -> Path:
    if "abs_path" in probe:
        return Path(probe["abs_path"])
    if "abs_root" in probe:
        return Path(probe["abs_root"])
    if "path" in probe:
        return project_root / probe["path"]
    raise ValueError(f"probe 缺少 path/abs_path/abs_root 字段: {probe}")


def _probe_file_exists(project_root: Path, probe: dict) -> bool:
    return _resolve(project_root, probe).exists()


def _probe_dir_exists_any(project_root: Path, probe: dict) -> bool:
    base = project_root / "05_Agent库" / "草稿"
    return any((base / c).exists() for c in probe["candidates"])


def _iter_glob_roots(project_root: Path, probe: dict) -> List[Path]:
    if "abs_root" in probe:
        return [Path(probe["abs_root"])]
    roots = probe.get("roots") or [probe.get("root")]
    return [project_root / r for r in roots if r]


def _probe_count_glob(project_root: Path, probe: dict) -> int:
    pattern = probe["pattern"]
    recursive = probe.get("recursive", False)
    total = 0
    for root in _iter_glob_roots(project_root, probe):
        if not root.exists():
            continue
        matches = root.rglob(pattern) if recursive else root.glob(pattern)
        total += sum(1 for _ in matches)
    return total


def _probe_grep_count(project_root: Path, probe: dict) -> int:
    pattern = re.compile(probe["pattern"])
    glob_pat = probe.get("glob", "*")
    total = 0
    for root in _iter_glob_roots(project_root, probe):
        if not root.exists():
            continue
        for f in root.rglob(glob_pat):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            total += len(pattern.findall(text))
    return total


def _dig_field(data: dict, field_path: str):
    node = data
    for part in field_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _probe_json_field(project_root: Path, probe: dict):
    path = _resolve(project_root, probe)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    value_type = probe.get("value_type", "raw")
    if value_type == "composite":
        fields = probe["field"].split(",")
        return {f: _dig_field(data, f) for f in fields}
    value = _dig_field(data, probe["field"])
    if value_type == "list_len":
        return len(value) if isinstance(value, list) else None
    if value_type == "text_hash":
        # Python 内置 hash() 对字符串按进程随机加盐（PYTHONHASHSEED），同一份内容
        # 换个进程再跑就会算出不同的值——track_change 会把这种"假变化"误判成
        # drift。改用 sha256，同样内容任何时候、任何进程算出来的都一样。
        if value is None:
            return None
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return value


def _probe_run_test_script(project_root: Path, probe: dict) -> dict:
    script = _resolve(project_root, probe)
    if not script.exists():
        return {"exists": False, "exit_code": None, "declared_tests": 0, "passed": None}

    declared_tests = len(re.findall(r"^\s*def test_", script.read_text(encoding="utf-8", errors="ignore"), re.MULTILINE))

    try:
        result = subprocess.run(["python3", str(script)], capture_output=True, text=True, timeout=180)
        exit_code = result.returncode
        tail = (result.stdout or "")[-800:]
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"exists": True, "exit_code": None, "declared_tests": declared_tests,
                "passed": False, "error": str(e)}

    return {"exists": True, "exit_code": exit_code, "declared_tests": declared_tests,
            "passed": exit_code == 0, "stdout_tail": tail}


def _latest_mtime(root: Path) -> Optional[str]:
    if root.is_file():
        return datetime.fromtimestamp(root.stat().st_mtime).isoformat()
    if not root.exists():
        return None
    latest = None
    for f in root.rglob("*"):
        if f.is_file():
            m = f.stat().st_mtime
            if latest is None or m > latest:
                latest = m
    return datetime.fromtimestamp(latest).isoformat() if latest else None


def _probe_mtime_latest(project_root: Path, probe: dict) -> Optional[str]:
    return _latest_mtime(_resolve(project_root, probe))


def _probe_mtime_staleness(project_root: Path, probe: dict) -> dict:
    path = _resolve(project_root, probe)
    if not path.exists():
        return {"exists": False, "age_hours": None}
    age_hours = (datetime.now().timestamp() - path.stat().st_mtime) / 3600
    return {"exists": True, "age_hours": round(age_hours, 1)}


def _probe_doc_count_drift(project_root: Path, probe: dict) -> dict:
    doc_path = project_root / probe["doc_path"]
    code_path = project_root / probe["code_path"]
    declared = None
    if doc_path.exists():
        m = re.search(probe["doc_pattern"], doc_path.read_text(encoding="utf-8", errors="ignore"))
        declared = int(m.group(1)) if m else None
    actual = None
    if code_path.exists():
        actual = len(re.findall(probe["code_pattern"], code_path.read_text(encoding="utf-8", errors="ignore"),
                                 re.MULTILINE))
    return {"declared": declared, "actual": actual}


def _comparable_value(kind: str, value):
    """track_change 模式下用于"新旧值是否一致"判断的值——不是原始 value 本身。

    run_test_script 的 stdout_tail 里含 tempfile 生成的随机目录名（每次运行
    都不同），如果直接拿整个 dict 做相等比较，哪怕 exit_code/测试内容完全
    没变，也会被误判成"每次都有drift"——纯噪音，不是真的漂移。这里只挑
    真正有意义的字段参与比较，stdout_tail 仍然完整保留在 value 里供人看。
    """
    if kind == "run_test_script" and isinstance(value, dict):
        return {k: value.get(k) for k in ("exists", "exit_code", "declared_tests", "passed")}
    return value


PROBES = {
    "file_exists": _probe_file_exists,
    "dir_exists_any": _probe_dir_exists_any,
    "count_glob": _probe_count_glob,
    "grep_count": _probe_grep_count,
    "json_field": _probe_json_field,
    "run_test_script": _probe_run_test_script,
    "mtime_latest": _probe_mtime_latest,
    "mtime_staleness": _probe_mtime_staleness,
    "doc_count_drift": _probe_doc_count_drift,
}


class CheckResult:
    def __init__(self, check: dict, value, drift: Optional[bool], note: str):
        self.check = check
        self.value = value
        self.drift = drift  # True/False/None（None = 首次建立基线，或manual只读不判断）
        self.note = note


def run_check(project_root: Path, check: dict, baseline: Dict[str, dict]) -> CheckResult:
    probe = check.get("probe")
    if not probe or check.get("evidence_type") == "manual" and probe.get("mode") != "readonly":
        return CheckResult(check, None, None, "无 probe，纯人工判断项")

    kind = probe["kind"]
    fn = PROBES.get(kind)
    if fn is None:
        return CheckResult(check, None, None, f"未知 probe.kind: {kind}")

    value = fn(project_root, probe)
    mode = probe.get("mode", "compare_expect")
    check_id = check["id"]
    prior = baseline.get(check_id, {}).get("value")

    if mode == "readonly":
        return CheckResult(check, value, None, "只读记录，不判断")

    if mode == "track_change":
        if check_id not in baseline:
            return CheckResult(check, value, None, "首次运行，建立基线")
        drift = _comparable_value(kind, value) != _comparable_value(kind, prior)
        note = f"上次: {prior} → 本次: {value}" if drift else "与上次一致"
        return CheckResult(check, value, drift, note)

    # 绝对期望值比对（expect_zero / expect_false / 直接比较 declared vs actual 等）
    if kind == "grep_count" or (kind == "count_glob" and probe.get("expect_zero")):
        drift = value != 0
        return CheckResult(check, value, drift, "matrix声明应为0" if drift else "与声明一致（0）")
    if kind in ("file_exists", "dir_exists_any") and "expect_false" in probe:
        expect_false = probe["expect_false"]
        drift = value != (not expect_false)
        return CheckResult(check, value, drift, "" if not drift else "存在性跟matrix声明不符")
    if kind == "mtime_staleness":
        max_age = probe.get("max_age_hours", 30)
        age = value.get("age_hours")
        drift = (age is None) or (age > max_age)
        return CheckResult(check, value, drift, f"age={age}h, 阈值={max_age}h")
    if kind == "run_test_script":
        drift = not value.get("passed")
        note = f"exit_code={value.get('exit_code')}, declared_tests={value.get('declared_tests')}"
        return CheckResult(check, value, drift, note)
    if kind == "doc_count_drift":
        drift = value.get("declared") != value.get("actual")
        note = f"文档声明={value.get('declared')}, 实测={value.get('actual')}"
        return CheckResult(check, value, drift, note)

    # 兜底：没有特别比对逻辑的 count_glob（既非 track_change 也非 expect_zero）
    return CheckResult(check, value, None, "已读取，无既定比对规则")


def run_all_checks(project_root: Path, checks: List[dict], report_dir: Path) -> Tuple[List[CheckResult], Dict[str, dict]]:
    baseline = _load_baseline(report_dir)
    results = []
    new_baseline = dict(baseline)

    for check in checks:
        result = run_check(project_root, check, baseline)
        results.append(result)
        if result.drift is not None or check.get("probe", {}).get("mode") == "track_change":
            new_baseline[check["id"]] = {"value": result.value, "recorded_at": datetime.now().isoformat()}

    return results, new_baseline


def format_report_markdown(results: List[CheckResult], run_date: str) -> str:
    drifted = [r for r in results if r.drift is True]
    unchanged = [r for r in results if r.drift is False]
    baseline_first_run = [r for r in results if r.drift is None and r.check.get("evidence_type") == "auto"]
    manual_items = [r for r in results if r.check.get("evidence_type") == "manual"]

    lines = [f"# Pipeline差距矩阵 · 周检测 {run_date}", ""]

    lines.append("## 本周与矩阵声明不一致的地方（drift_flag=true）")
    if drifted:
        lines.append("| 阶段 | 维度 | 矩阵声明 | 本周实测 | 说明 |")
        lines.append("|---|---|---|---|---|")
        for r in drifted:
            c = r.check
            lines.append(f"| {c['stage_id']} {c['stage_name']} | {c['dimension']} | {c['claim']} | "
                         f"{r.value} | {r.note}（需要人工核实，可能是环境问题或真实变化） |")
    else:
        lines.append("（本周无drift）")
    lines.append("")

    lines.append("## 本周无变化（跟上次检测一致，未发现drift）")
    if unchanged:
        for r in unchanged:
            c = r.check
            lines.append(f"- [{c['stage_id']} {c['stage_name']}/{c['dimension']}] {c['claim']} — {r.note}")
    else:
        lines.append("（无）")
    lines.append("")

    if baseline_first_run:
        lines.append("## 本次新建立基线（无历史数据可比对，下次检测起才会判断drift）")
        for r in baseline_first_run:
            c = r.check
            lines.append(f"- [{c['stage_id']} {c['stage_name']}/{c['dimension']}] {c['claim']} — 当前值: {r.value}")
        lines.append("")

    lines.append("## 本周无法检测（evidence_type=manual）")
    if manual_items:
        for r in manual_items:
            c = r.check
            extra = f" — 当前值: {r.value}" if r.value is not None else ""
            lines.append(f"- [{c['stage_id']} {c['stage_name']}/{c['dimension']}] {c['claim']}{extra}")
    else:
        lines.append("（无）")

    return "\n".join(lines) + "\n"


def summarize_latest_report(report_dir: Path) -> dict:
    """给前端仪表盘用的只读摘要——找最新一份周检测报告，数一下drift条数，
    绝不重新跑任何检测（run_all_checks会真实改写.baseline.json，只能通过
    --pipeline-check这条显式CLI/定时任务路径触发，不能被页面加载动作触发）。

    没有任何报告时（比如还没手动跑过一次--pipeline-check）返回全空，不报错，
    调用方（前端）据此显示"还没有检测记录"而不是崩溃。"""
    reports = sorted(report_dir.glob("检测记录_*.md"))
    if not reports:
        return {"report_date": None, "drift_count": 0, "report_path": None}

    latest = reports[-1]
    text = latest.read_text(encoding="utf-8")

    # 只数"本周与矩阵声明不一致的地方"这一节里的表格数据行，用下一个"## "
    # 标题当结束边界——表头行/分隔线（|---|...|）不算数据行。
    section = re.search(r"## 本周与矩阵声明不一致的地方.*?\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    drift_count = 0
    if section:
        for line in section.group(1).splitlines():
            line = line.strip()
            if line.startswith("|") and not line.startswith("|---") and "矩阵声明" not in line:
                drift_count += 1

    return {
        "report_date": latest.stem.replace("检测记录_", ""),
        "drift_count": drift_count,
        "report_path": str(latest),
    }
