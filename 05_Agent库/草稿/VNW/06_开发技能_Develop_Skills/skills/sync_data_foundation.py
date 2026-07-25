#!/usr/bin/env python3
"""VNW · 数据底座同步脚本

一键可重复执行:每次01-04源文件(价值节点清单/信号提取基线/访谈产出/规则与GAP产出)
或L4 Skill封装可行性评估更新后,重新运行本脚本,把前端展示数据底座里的派生表
(T1/T2/T6/T9/T11/T12/T13/T14/T18/T19/T20/T21/T24/T25)全部按最新源重新生成一遍。

设计原则(2026-07-25首次落地时定的,后续修改请保持):
- 幂等:每次都是全量重新生成,不是增量追加。同样的源文件跑两次,结果字节级一致。
- 不改源文件:01-05五层原始文档、04层规则/GAP清单只读,从不写入。
- T5/T7 不重建:04层规则/GAP清单已验证是权威版本,这里只做一致性校验,校验失败会报错而不是静默跳过。
- 同时写两处物理副本(规则分析工作区 + 规则前端设计的独立数据底座),保持已有的双份同步惯例。
- 03层'规则空白地图'目前只认PAY这种'交付物N：'逐个编号的格式;EQ/HR/INS/PARTNER/TREASURY/FA
  用的是'交付物群(N子产物合并分析)'合并写法,本脚本不解析,T24因此只覆盖PAY,运行时会如实打印这个限制。
- 03层'熔断节点补建清单'各域自动取最新版本号(PAY用v1.2/FA用v1.1/HR用v1.1/其余域用v1.0),
  PAY是7列格式、其余7域是5列格式(标签有'负责人'/'负责人岗位'/'当前状态'等出入,已用同义词表对齐),
  两种格式都已解析进T18,8个域全覆盖。
- 熔断判定:T1不携带任何熔断/Gate字段(2026-07-25拍板,过程核心产物是03层不是02层)。
  唯一权威判定在T25——节点出现在'熔断节点补建清单'里即为熔断,这解决了此前发现的
  KA域矛盾(02层Step2曾把KAEM-02/KASC-01标成非熔断,但03层文件明确写KA全域6节点都熔断)。
- T21审计结果是本次运行的即时快照,不做历史累积;需要看历史变化去查git history或另存副本。

用法: python3 sync_data_foundation.py
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
RULE_ANALYSIS = Path(
    "/Users/a112233/Desktop/流程架构项目_jasper/02_过程成果-工作产出/规则分析（Jasper）"
)
AUTHORITATIVE_LIST = Path(
    "/Users/a112233/Desktop/流程架构项目_jasper/03_发布成果-交付物/权威数据/D1_价值节点清单_V3.44.xlsx"
)
SIGNAL_BASELINE_DIR = RULE_ANALYSIS / "02_信号提取基线" / "提取合集校准"
GAP_MAP_DIR = RULE_ANALYSIS / "03_访谈准备与执行" / "规则空白地图"
RULE_GAP_DIR = RULE_ANALYSIS / "04_规则与GAP产出"
AGENT_SKILL_DIR = RULE_ANALYSIS / "Agent与Skill体系"
DB1 = RULE_ANALYSIS / "前端展示数据底座"
DB2 = Path("/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/规则前端设计/数据底座")
DOMAINS = ["EQ", "FA", "HR", "INS", "KA", "PARTNER", "PAY", "TREASURY"]
TODAY = "2026-07-25"


def write_both(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    for target in (DB1, DB2):
        with open(target / name, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest(dirpath: Path, pattern: str) -> Path | None:
    """按文件名里的版本号(v数字.数字)取最新版本;没有版本号的按修改时间取最新。"""
    candidates = sorted(dirpath.glob(pattern))
    if not candidates:
        return None

    def version_key(p: Path):
        m = re.search(r"v(\d+)\.(\d+)", p.name)
        if m:
            return (int(m.group(1)), int(m.group(2)))
        return (-1, -1)

    versioned = [p for p in candidates if version_key(p) != (-1, -1)]
    if versioned:
        return max(versioned, key=version_key)
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------------------
# 阶段1+2: 02层8域信号基线 → T1(节点索引)/T2(信号数据)/T6(交付物清单)/T11(岗位映射)/T12(Gate评级明细)
# ---------------------------------------------------------------------------
NODE_HEADER_RE = re.compile(r"^### (VN-[A-Z0-9]+-[A-Z0-9]+(?:-\d+)?)\s*[·・]?\s*(.*)$", re.M)


def _field(block: str, label: str) -> str:
    m = re.search(rf"-\s*{re.escape(label)}\s*：(.*?)(?=\n-\s|\n\n|\*\*信号)", block, re.S)
    return m.group(1).strip() if m else ""


def _gate_table(block: str) -> dict:
    m = re.search(r"\*\*信号3.*?\n+(\|.*?\|)\n\n", block, re.S)
    gates = {"gate_1": "", "gate_2": "", "gate_3": "", "verdict": ""}
    if not m:
        return gates
    for r in m.group(1).split("\n"):
        if not r.startswith("|") or "---" in r:
            continue
        cells = [c.strip() for c in r.strip("|").split("|")]
        if len(cells) < 2:
            continue
        label, val = cells[0], cells[1]
        if "Gate①" in label:
            gates["gate_1"] = val
        elif "Gate②" in label:
            gates["gate_2"] = val
        elif "Gate③" in label:
            gates["gate_3"] = val
        elif "综合判定" in label:
            gates["verdict"] = val
    return gates


def _kpi_m(block: str) -> tuple[str, str, str]:
    m = re.search(r"\*\*信号7.*?\n(.*?)$", block, re.S)
    if not m:
        return "", "", ""
    seg = m.group(1)
    km = re.search(r"-\s*KPI锚定\s*：(.*?)(?=\n-|\Z)", seg, re.S)
    mm = re.search(r"-\s*M锚定\s*：(.*?)(?=\n-|\Z)", seg, re.S)
    sm = re.search(r"-\s*战略意义\s*：(.*?)(?=\n-|\Z)", seg, re.S)
    return (
        km.group(1).strip() if km else "",
        mm.group(1).strip() if mm else "",
        sm.group(1).strip() if sm else "",
    )


def _deliverable_rows(block: str) -> list[dict]:
    m = re.search(r"\*\*信号5.*?\n+(\|.*?\|)\n\n", block, re.S)
    out = []
    if not m:
        return out
    rows = [r for r in m.group(1).split("\n") if r.startswith("|") and "---" not in r]
    for r in rows[1:]:  # rows[0]是表头(交付物/形态/来源),跳过
        cells = [c.strip() for c in r.strip("|").split("|")]
        if len(cells) < 3 or not cells[0]:
            continue
        out.append({"name": cells[0], "form": cells[1], "source": cells[2]})
    return out


def _signal4_rows(block: str, node_id: str, counter: list[int]) -> list[dict]:
    m = re.search(r"\*\*信号4.*?\n+(\|.*?\|)\n\n", block, re.S)
    out = []
    if not m:
        return out
    rows = [r for r in m.group(1).split("\n") if r.startswith("|") and "---" not in r]
    for r in rows[1:]:  # rows[0]是表头(分类/信号内容/来源),跳过
        cells = [c.strip() for c in r.strip("|").split("|")]
        if len(cells) < 3:
            continue
        cls, content, source = cells[0], cells[1], cells[2]
        if not content or content == "—":
            continue
        counter[0] += 1
        out.append({
            "signal_id": f"SIG-{counter[0]:04d}", "node_id": node_id, "content": content,
            "source": source, "confidence": "", "rule_subtype": cls, "completeness": "",
            "l_layer": "", "rule_trigger": "", "rule_action": "", "rule_standard": "",
            "rule_exception": "", "rule_owner": "", "externalized": "", "round": "",
            "source_recording": "",
        })
    return out


def _split_roles(raw: str) -> tuple[list[str], str]:
    if not raw:
        return [], ""
    m = re.search(r"[（(]", raw)
    main, note = (raw[: m.start()], raw[m.start():]) if m else (raw, "")
    return [p.strip() for p in re.split(r"\s*/\s*", main) if p.strip()], note.strip()


def build_from_signal_baselines():
    # 2026-07-25决定:T1不承载熔断判断(gate_status/gate_1/2/3/verdict),
    # 熔断信息统一以03层(规则空白地图+熔断节点补建清单)为权威来源,见build_t25_fused_status()。
    # 原因:02层Step2的'熔断状态'列本身跨域写法/判定不统一(曾发现KA域KAEM-02/KASC-01矛盾)。
    t1_fields = [
        "node_id", "domain", "node_name", "l3_flow", "l3_status", "priority",
        "start_point", "end_point", "end_standard", "frequency", "l4_name", "value_property",
        "physical_correspondence", "data_validation", "producer", "consumer", "single_point_risk",
        "composition", "kpi_anchors", "m_anchors",
        "strategic_note", "version", "last_updated", "source_file",
    ]
    t6_fields = [
        "deliverable_id", "node_id", "node_name", "domain_code", "deliverable_name",
        "producer_role", "consumer", "gate_status", "l_layer", "sub_product_index",
        "sub_product_total", "is_fused", "source", "recording_file", "transcript_date",
        "owner_confirm_date", "upload_status",
    ]
    t11_fields = [
        "mapping_id", "node_id", "domain_code", "role_name", "role_type",
        "responsibility_mode", "single_point_risk", "source_field", "source_doc",
    ]
    t12_fields = [
        "node_id", "node_name", "domain_code", "gate1_status", "gate2_status",
        "gate3_status", "is_fused", "sheet5_category", "decision_priority",
    ]

    t1_rows, t2_rows, t6_rows, t11_rows, t12_rows = [], [], [], [], []
    sig_counter, d_id, m_id = [0], [0], [0]
    files_used = []

    for md_file in sorted(SIGNAL_BASELINE_DIR.glob("*域_价值节点信号提取基线_v1.0.md")):
        domain_match = re.match(r"([A-Z]+)域_", md_file.name)
        domain = domain_match.group(1) if domain_match else "?"
        files_used.append(md_file.name)
        text = md_file.read_text(encoding="utf-8", errors="replace")

        step2 = {}
        step2_m = re.search(r"## Step 2.*?\n\n(\|.*?\|)\n\n", text, re.S)
        if step2_m:
            rows = [r for r in step2_m.group(1).split("\n") if r.startswith("|") and "---" not in r]
            header = [c.strip() for c in rows[0].strip("|").split("|")]
            for r in rows[1:]:
                cells = [c.strip() for c in r.strip("|").split("|")]
                if len(cells) >= 2 and cells[0].startswith("VN-"):
                    step2[cells[0]] = dict(zip(header, cells))

        # 只在'## Step 3'到'## Step 4'之间找逐节点小节,避免最后一个节点的区间越界吃进Step4-7的内容
        step3_m = re.search(r"## Step 3.*?(?=\n## Step 4|\Z)", text, re.S)
        step3_text = step3_m.group(0) if step3_m else text
        headers = list(NODE_HEADER_RE.finditer(step3_text))
        for i, hm in enumerate(headers):
            node_id = hm.group(1)
            node_name = hm.group(2).strip()
            block = step3_text[hm.end(): headers[i + 1].start() if i + 1 < len(headers) else len(step3_text)]
            s2 = step2.get(node_id, {})
            kpi, manchor, strat = _kpi_m(block)
            gates = _gate_table(block)

            deliverables = _deliverable_rows(block)
            t1_rows.append({
                "node_id": node_id, "domain": domain,
                "node_name": node_name or s2.get("节点名称(v2.0)", ""),
                "l3_flow": s2.get("L3名称", ""), "l3_status": s2.get("L3现状", ""),
                "priority": s2.get("优先级", ""),
                "start_point": _field(block, "起点A") or s2.get("起点A", ""),
                "end_point": _field(block, "终点Z") or s2.get("终点Z", ""),
                "end_standard": _field(block, "终点标准"), "frequency": _field(block, "频次"),
                "l4_name": _field(block, "L4名称"), "value_property": _field(block, "价值属性"),
                "physical_correspondence": _field(block, "物理对应"),
                "data_validation": _field(block, "数据验证"),
                "producer": _field(block, "生产方"), "consumer": _field(block, "消费方"),
                "single_point_risk": _field(block, "单点风险"),
                "composition": " + ".join(d["name"] for d in deliverables),
                "kpi_anchors": kpi, "m_anchors": manchor, "strategic_note": strat,
                "version": "v1.0(提取合集校准)", "last_updated": "2026-06-25", "source_file": md_file.name,
            })
            t2_rows.extend(_signal4_rows(block, node_id, sig_counter))

            total = len(deliverables)
            for idx, d in enumerate(deliverables, start=1):
                d_id[0] += 1
                t6_rows.append({
                    "deliverable_id": f"DLV-{d_id[0]:04d}", "node_id": node_id,
                    "node_name": node_name or s2.get("节点名称(v2.0)", ""), "domain_code": domain,
                    "deliverable_name": d["name"], "producer_role": "", "consumer": "",
                    "gate_status": s2.get("熔断状态", ""), "l_layer": "", "sub_product_index": idx,
                    "sub_product_total": total, "is_fused": "", "source": d["source"],
                    "recording_file": "", "transcript_date": "", "owner_confirm_date": "",
                    "upload_status": "",
                })

            producer_roles, producer_note = _split_roles(_field(block, "生产方"))
            consumer_roles, consumer_note = _split_roles(_field(block, "消费方"))
            spr = _field(block, "单点风险")
            for role in producer_roles:
                m_id[0] += 1
                t11_rows.append({
                    "mapping_id": f"ROLE-{m_id[0]:04d}", "node_id": node_id, "domain_code": domain,
                    "role_name": role, "role_type": "生产方", "responsibility_mode": "",
                    "single_point_risk": spr, "source_field": ("信号2·生产方 " + producer_note).strip(),
                    "source_doc": md_file.name,
                })
            for role in consumer_roles:
                m_id[0] += 1
                t11_rows.append({
                    "mapping_id": f"ROLE-{m_id[0]:04d}", "node_id": node_id, "domain_code": domain,
                    "role_name": role, "role_type": "消费方", "responsibility_mode": "",
                    "single_point_risk": "", "source_field": ("信号2·消费方 " + consumer_note).strip(),
                    "source_doc": md_file.name,
                })

            t12_rows.append({
                "node_id": node_id, "node_name": node_name or s2.get("节点名称(v2.0)", ""),
                "domain_code": domain, "gate1_status": gates["gate_1"], "gate2_status": gates["gate_2"],
                "gate3_status": gates["gate_3"], "is_fused": "",
                "sheet5_category": s2.get("熔断状态", ""), "decision_priority": s2.get("优先级", ""),
            })

    return {
        "t1": (t1_fields, t1_rows), "t6": (t6_fields, t6_rows),
        "t11": (t11_fields, t11_rows), "t12": (t12_fields, t12_rows),
    }, t2_rows, files_used


# ---------------------------------------------------------------------------
# 阶段3: 03层规则空白地图 → 回填T6 producer_role/consumer/l_layer + 建T24(仅PAY逐条编号格式)
# ---------------------------------------------------------------------------
def _normalize_gap_map(text: str) -> str:
    for marker in [r"##+ ", r"#### 交付物", r"\*\*[ABCD]标签", r"- [ABCD]-", r"> Signal3"]:
        text = re.sub(rf"(?<!\n)({marker})", r"\n\1", text)
    return text


def _bullet(block: str, label: str) -> str:
    m = re.search(rf"-\s*{label}\s*：(.*?)(?=\n-\s[A-D]-|\n\*\*[A-D]标签|\n\n|\Z)", block, re.S)
    return m.group(1).strip() if m else ""


def enrich_t6_and_build_t24(t6_rows: list[dict]):
    t6_enrich: dict[tuple[str, str], dict] = {}
    t24_rows = []
    cid = [0]
    coverage = {}

    for md_file in sorted(GAP_MAP_DIR.glob("*_第一层_规则空白地图_v1.0*.md")):
        domain_match = re.match(r"([A-Z]+)_", md_file.name)
        domain = domain_match.group(1) if domain_match else "?"
        text = _normalize_gap_map(md_file.read_text(encoding="utf-8", errors="replace"))

        deliver_count = 0
        header_m = re.search(r"\|\s*#\s*\|\s*交付物名称\s*\|([^\n]*)\|", text)
        row_pattern = re.compile(r"\|\s*\d+\s*\|\s*《?[^|]+?》?\s*\|\s*(VN-[A-Z0-9]+-\d+)\s*\|[^\n]*\|")
        if header_m:
            header = ["#", "交付物名称"] + [c.strip() for c in header_m.group(1).split("|") if c.strip()]
            for line in row_pattern.finditer(text):
                cells = [c.strip() for c in line.group(0).strip("|").split("|")]
                if len(cells) != len(header):
                    continue
                row = dict(zip(header, cells))
                name = row.get("交付物名称", "").strip("《》")
                node = row.get("所属节点", "")
                if not name or not node:
                    continue
                t6_enrich[(node, name)] = {
                    "producer_role": row.get("生产方（岗位）", row.get("生产方(岗位)", "")),
                    "consumer": row.get("消费方", ""), "l_layer": row.get("L层定位", ""),
                }
                deliver_count += 1

        blocks = re.split(r"\n#### 交付物\d+：", text)[1:]  # PAY格式;'交付物群'格式(其余6域)暂不解析
        for blk in blocks:
            name_m = re.match(r"《?([^》\n]+)》?", blk)
            deliv_name = name_m.group(1) if name_m else ""
            node_matches = list(re.finditer(r"### (VN-[A-Z0-9]+-\d+)", text[: text.find(blk)]))
            node_id = node_matches[-1].group(1) if node_matches else ""
            if not deliv_name:
                continue
            cid[0] += 1
            t24_rows.append({
                "analysis_id": f"DLA-{cid[0]:04d}", "node_id": node_id, "domain": domain,
                "deliverable_name": deliv_name,
                "a_type": _bullet(blk, "A-类型"), "a_risk": _bullet(blk, "A-类型规则风险"),
                "a_core_rules": _bullet(blk, "A-核心规则信号"),
                "b_owner": _bullet(blk, "B-Owner"), "b_mode": _bullet(blk, "B-责任模式"),
                "b_breakpoint": _bullet(blk, "B-执行断点"),
                "b_single_point_risk": _bullet(blk, "B-单点风险"),
                "c_verification_position": _bullet(blk, "C-验证链位置"),
                "c_breakpoint_type": _bullet(blk, "C-断点类型"),
                "c_blind_spot": _bullet(blk, "C-验证盲区"),
                "d_auth_level": _bullet(blk, "D-授权级别").replace(" ---", "").strip(),
                "d_m_anchor": _bullet(blk, "D-M锚定"),
                "d_kpi_anchor": _bullet(blk, "D-KPI锚定").replace(" ---", "").strip(),
                "source_doc": md_file.name,
            })
        coverage[domain] = {"交付物清单回填候选": deliver_count, "四标签分析(仅PAY格式)": len(
            [r for r in t24_rows if r["domain"] == domain])}

    filled = 0
    for row in t6_rows:
        key = (row["node_id"], row["deliverable_name"])
        if key in t6_enrich:
            info = t6_enrich[key]
            row["producer_role"] = info["producer_role"]
            row["consumer"] = info["consumer"]
            row["l_layer"] = info["l_layer"]
            filled += 1

    t24_fields = [
        "analysis_id", "node_id", "domain", "deliverable_name", "a_type", "a_risk", "a_core_rules",
        "b_owner", "b_mode", "b_breakpoint", "b_single_point_risk", "c_verification_position",
        "c_breakpoint_type", "c_blind_spot", "d_auth_level", "d_m_anchor", "d_kpi_anchor", "source_doc",
    ]
    return t6_rows, filled, (t24_fields, t24_rows), coverage


# ---------------------------------------------------------------------------
# 阶段3b: 03层熔断节点补建清单(各域取最新版本) → T18(熔断任务分发)
# PAY格式(7列: 行动/类型/执行主体/期望产出/交付物上传要求/预估周期)和其余7域的
# 标准格式(5列: 行动/负责人[岗位]/期望产出/阻塞或状态或预估周期)不同,分别处理,
# 用同义词表把不同域的列名对齐到T18统一字段。
# ---------------------------------------------------------------------------
NODE_BLOCK_RE = re.compile(r"^### (?:节点\s+)?(VN-[A-Z0-9]+-\d+)\s*[·・]?\s*([^\[\n]*)", re.M)

_EXECUTOR_SYNONYMS = ["执行主体", "负责人岗位", "负责人"]
_DEADLINE_SYNONYMS = ["预估周期"]
_REMARK_SYNONYMS = ["阻塞", "状态", "当前状态", "交付物上传要求"]


def _pick_col(header: list[str], synonyms: list[str]) -> str | None:
    for syn in synonyms:
        if syn in header:
            return syn
    return None


def build_t18_from_remediation_lists():
    t18_fields = [
        "task_id", "node_id", "node_name", "domain", "task_name", "action_tier",
        "executor_role", "executor_dept", "assigned_date", "deadline", "task_status",
        "deliverable_id", "deliverable_name", "recording_uploaded", "gate_unlock_date", "remarks",
    ]
    rows = []
    tid = [0]
    files_used = []
    domain_task_count = {}

    for domain in DOMAINS:
        src = latest(GAP_MAP_DIR.parent / "熔断节点补建清单", f"{domain}_熔断节点补建清单_v*.md")
        if src is None:
            domain_task_count[domain] = 0
            continue
        files_used.append(src.name)
        text = src.read_text(encoding="utf-8", errors="replace")

        blocks = list(NODE_BLOCK_RE.finditer(text))
        count_before = tid[0]
        for i, bm in enumerate(blocks):
            node_id = bm.group(1)
            node_name = bm.group(2).strip(" ·[")
            block_text = text[bm.end(): blocks[i + 1].start() if i + 1 < len(blocks) else len(text)]

            table_m = re.search(r"\n(\|\s*#\s*\|[^\n]*\|\n(?:\|[^\n]*\|\n?)+)", block_text)
            if not table_m:
                continue
            table_lines = [ln for ln in table_m.group(1).split("\n") if ln.startswith("|") and "---" not in ln]
            if len(table_lines) < 2:
                continue
            header = [c.strip() for c in table_lines[0].strip("|").split("|")]
            executor_col = _pick_col(header, _EXECUTOR_SYNONYMS)
            deadline_col = _pick_col(header, _DEADLINE_SYNONYMS)
            remark_col = _pick_col(header, _REMARK_SYNONYMS)
            action_col = "行动" if "行动" in header else ("行动项" if "行动项" in header else None)
            deliverable_col = "期望产出（交付物）" if "期望产出（交付物）" in header else "期望产出"
            type_col = "类型" if "类型" in header else None

            for line in table_lines[1:]:
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) != len(header):
                    continue
                row = dict(zip(header, cells))
                if action_col and not row.get(action_col):
                    continue
                tid[0] += 1
                rows.append({
                    "task_id": f"T18-{domain}-{tid[0]:04d}", "node_id": node_id,
                    "node_name": node_name, "domain": domain,
                    "task_name": row.get(action_col, "") if action_col else "",
                    "action_tier": row.get(type_col, "") if type_col else "",
                    "executor_role": row.get(executor_col, "") if executor_col else "",
                    "executor_dept": "", "assigned_date": "",
                    "deadline": row.get(deadline_col, "") if deadline_col else "",
                    "task_status": "未分发", "deliverable_id": "",
                    "deliverable_name": row.get(deliverable_col, ""),
                    "recording_uploaded": "N",
                    "gate_unlock_date": "",
                    "remarks": row.get(remark_col, "") if remark_col else "",
                })
        domain_task_count[domain] = tid[0] - count_before

    return (t18_fields, rows), files_used, domain_task_count


# ---------------------------------------------------------------------------
# 阶段3c: T25(熔断状态清单) —— 03层是VNW熔断判定的唯一权威来源(2026-07-25拍板)
# 判定逻辑:节点出现在'熔断节点补建清单'里(该清单按定义只收录熔断节点) → 熔断;
# T1全量节点里没出现在该清单的 → 非熔断。不依赖'规则空白地图'头部的'包含节点/熔断节点'
# 声明(核实过FA用半角冒号、PARTNER把'熔断节点'叫成'待补入节点'且域内数字自相矛盾,
# 头部声明跨域写法不统一,不可靠;熔断节点补建清单的收录范围本身就是权威边界)。
# ---------------------------------------------------------------------------
FUSED_TYPE_RE = re.compile(r"\*\*熔断类型\*\*：(.*?)(?=\n\n|\Z)", re.S)


VN_CODE_RE = re.compile(r"VN-[A-Z0-9]+-\d+")


def build_t25_fused_status(new_t1_rows: list[dict], t18_rows: list[dict]):
    # 熔断集合不能只取t18_rows里成功解析出任务表的节点——2026-07-25核实发现FA域v1.1
    # 一份文件里混了三种格式(标准任务表/F1-F2-F3访谈更新叙述/无表格的'未变更节点'引用表),
    # 只有第一种会进t18_rows,导致FOB-02/FPG-01/FPG-02/FOR-02/FTR-01被漏判成非熔断
    # (T13节点复评追踪交叉核对时发现的)。改为对整份'熔断节点补建清单'原文做VN编码全文扫描,
    # 该文件按定义只讨论本域熔断节点,扫出来的编码集合天然就是熔断集合,不受内部格式差异影响。
    fused_ids = set()
    for domain in DOMAINS:
        src = latest(GAP_MAP_DIR.parent / "熔断节点补建清单", f"{domain}_熔断节点补建清单_v*.md")
        if src is None:
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        fused_ids |= set(VN_CODE_RE.findall(text))
    # 已核实的误判:VN-EQ-03只在EQ文件里作为'归属并入VN-EQ-03'这类交叉引用出现(某个真熔断
    # 节点的补建行动提到要把交付物合并进它),它自己不是熔断节点(核实过EQ规则空白地图'包含
    # 节点'列表明确把它列为8个通过节点之一)。跟T13交叉核对时发现,人工排除。
    fused_ids -= {"VN-EQ-03"}
    node_to_domain = {r["node_id"]: r["domain"] for r in new_t1_rows}
    node_to_name = {r["node_id"]: r["node_name"] for r in new_t1_rows}

    # 补充抓取'**熔断类型**：'这个bullet(仅EQ/PAY/TREASURY用了这个写法,其余域留空,如实标注)
    fused_type_by_node = {}
    for domain in DOMAINS:
        src = latest(GAP_MAP_DIR.parent / "熔断节点补建清单", f"{domain}_熔断节点补建清单_v*.md")
        if src is None:
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        blocks = list(NODE_BLOCK_RE.finditer(text))
        for i, bm in enumerate(blocks):
            node_id = bm.group(1)
            block_text = text[bm.end(): blocks[i + 1].start() if i + 1 < len(blocks) else len(text)]
            m = FUSED_TYPE_RE.search(block_text)
            if m:
                fused_type_by_node[node_id] = m.group(1).strip()

    rows = []
    for r in new_t1_rows:
        nid = r["node_id"]
        is_fused = nid in fused_ids
        rows.append({
            "node_id": nid, "node_name": node_to_name.get(nid, ""),
            "domain": node_to_domain.get(nid, ""),
            "fused_status": "熔断" if is_fused else "非熔断",
            "fused_type": fused_type_by_node.get(nid, ""),
            "source": "03层·熔断节点补建清单(收录=熔断,未收录=非熔断)",
            "last_updated": TODAY,
        })
    fields = ["node_id", "node_name", "domain", "fused_status", "fused_type", "source", "last_updated"]
    return fields, rows


# ---------------------------------------------------------------------------
# 阶段4: 校验T5/T7与04层是否仍然一致(只读校验,不重建;不一致直接抛错,不能静默通过)
# ---------------------------------------------------------------------------
def validate_t5_t7_against_source():
    with open(DB1 / "T5_规则清单_全域_v3.0.csv", encoding="utf-8") as f:
        t5 = list(csv.DictReader(f))
    with open(DB1 / "T7_缺口清单_全域_v4.2.csv", encoding="utf-8") as f:
        t7 = list(csv.DictReader(f))

    # 2026-07-25核实:截至目前8个域的规则清单/Gap清单确实都只有v1.0(核对过,连_归档里
    # 的EFA001/PAY002等都是被合并进v1.0的更早期素材,不是v1.0之后的新版本)。但踩过熔断
    # 补建清单硬编码版本号漏掉v1.1/v1.2的教训,这里改用latest()自动探测,以后04层如果真出
    # v1.1,不用再手动改文件名。
    problems = []
    for dm in DOMAINS:
        rule_file = latest(RULE_GAP_DIR, f"规则清单_{dm}_v*.csv")
        gap_file = latest(RULE_GAP_DIR, f"Gap清单_{dm}_v*.csv")
        rule04 = set(r["rule_id"] for r in read_csv(rule_file)) if rule_file else set()
        gap04 = set(r["gap_id"] for r in read_csv(gap_file)) if gap_file else set()
        t5_ids = set(r["rule_id"] for r in t5 if r["domain"] == dm)
        t7_ids = set(r["gap_id"] for r in t7 if r["domain"] == dm)
        if rule04 != t5_ids:
            problems.append(
                f"{dm}规则清单: {rule_file.name if rule_file else '(缺失)'}有{len(rule04)}条 vs T5{len(t5_ids)}条,不一致")
        if gap04 != t7_ids:
            problems.append(
                f"{dm}Gap清单: {gap_file.name if gap_file else '(缺失)'}有{len(gap04)}条 vs T7{len(t7_ids)}条,不一致")
    return problems


# ---------------------------------------------------------------------------
# 阶段5: L4 Skill封装可行性评估 → T20
# ---------------------------------------------------------------------------
def build_t20(new_t1_rows: list[dict]):
    L4_CODE_RE = re.compile(r"L4-[A-Z]+-\d+")

    def split_multi(raw):
        return [p.strip() for p in re.split(r"[;,/、，；]", raw) if p.strip()]

    l4_to_nodes, l3_to_nodes = defaultdict(set), defaultdict(set)
    for row in new_t1_rows:
        node_id = row["node_id"]
        # 新T1没有l4_codes字段(v2.0血统不带),这里退回用domain做粗匹配的降级策略在下面统一处理
        l3_to_nodes[row["domain"]].add(node_id)

    src = latest(AGENT_SKILL_DIR, "L4流程_Skill封装可行性评估_确认最终版*.xlsx")
    if src is None:
        return [], []
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb["L4明细_最终确认版"]
    rows = list(ws.iter_rows(values_only=True))[1:]
    field_names = [
        "l1_domain", "business_domain", "l3_code", "l3_process", "l4_code", "l4_activity",
        "physical_deliverable_ideal", "action_nature", "action_singularity", "final_tier",
        "judgment_basis", "automation_tier", "funds_safety_hard_gate", "physical_execution_type",
    ]
    out_rows = []
    for r in rows:
        rec = dict(zip(field_names, ["" if v is None else v for v in r]))
        out_rows.append(rec)
    return field_names, out_rows, src.name


# ---------------------------------------------------------------------------
# 阶段6: T9/T13/T18/T19孤儿引用校验 + T14机械计数重算
# ---------------------------------------------------------------------------
def reconcile_and_recount(new_t1_rows, t2_rows, t5_rows, domain_result, t18_rows):
    new_t1_ids = set(r["node_id"] for r in new_t1_rows)
    orphan_report = []
    for fname, key in [
        ("T9_价值流归属_全域_v1.4.csv", "vn_id"),
        ("T13_节点复评追踪_全域_v1.7.csv", "node_id"),
        ("T19_SOP生产进度_全域_v1.0.csv", "node_id"),
    ]:
        path = DB1 / fname
        if not path.exists():
            continue
        ids = set(r[key] for r in read_csv(path) if r.get(key))
        orphans = sorted(ids - new_t1_ids)
        orphan_report.append((fname, len(ids), len(orphans), orphans))

    t18_ids = set(r["node_id"] for r in t18_rows)
    t18_orphans = sorted(t18_ids - new_t1_ids)
    orphan_report.append(("T18_熔断任务分发_全域_v2.0.csv", len(t18_ids), len(t18_orphans), t18_orphans))

    t1_by_domain = Counter(r["domain"] for r in new_t1_rows)
    node_to_domain = {r["node_id"]: r["domain"] for r in new_t1_rows}
    t2_by_domain = Counter(node_to_domain.get(r["node_id"], "?") for r in t2_rows)
    t3_rows = read_csv(DB1 / "T3_访谈线索_全域_v3.2.csv")
    t3_by_domain = Counter()
    for r in t3_rows:
        dom = node_to_domain.get(r.get("node_id", ""))
        if dom:
            t3_by_domain[dom] += 1
    t5_by_domain = Counter(r["domain"] for r in t5_rows)

    t14_path = latest(DB1, "T14_域扩展进度_全域_v*.csv")
    t14_old = read_csv(t14_path) if t14_path else []
    t14_fields = [
        "domain", "domain_name", "node_count", "current_phase", "signal_baseline",
        "rule_map_version", "interview_toolkit", "t2_count", "t3_count", "t5_count",
        "last_updated", "notes",
    ]
    t14_new = []
    for row in t14_old:
        dm = row["domain"]
        new_row = dict(row)
        new_row["node_count"] = t1_by_domain.get(dm, 0)
        new_row["t2_count"] = t2_by_domain.get(dm, 0)
        new_row["t3_count"] = t3_by_domain.get(dm, 0)
        new_row["t5_count"] = t5_by_domain.get(dm, 0)
        new_row["last_updated"] = TODAY
        t14_new.append(new_row)

    return orphan_report, (t14_fields, t14_new)


# ---------------------------------------------------------------------------
# 阶段7: 生成T21审计快照(全量重写,不累积历史)
# ---------------------------------------------------------------------------
def build_t21(new_t1_rows, orphan_report, t5t7_problems, t24_coverage):
    def get_node_ids_v344():
        wb = openpyxl.load_workbook(AUTHORITATIVE_LIST, read_only=True, data_only=True)
        ws = wb["1.价值节点总览"]
        rows = list(ws.iter_rows(values_only=True))
        ids = set()
        for r in rows[4:]:
            v = r[1]
            if v and str(v).strip().startswith("VN-"):
                ids.add(str(v).strip())
        return ids

    new_t1_ids = set(r["node_id"] for r in new_t1_rows)
    ids_v344 = get_node_ids_v344()

    rows, aid = [], [0]

    def add(audit_type, scope, severity, issue_desc):
        aid[0] += 1
        rows.append({
            "audit_id": f"AUD-{aid[0]:03d}", "audit_type": audit_type, "scope": scope,
            "severity": severity, "issue_desc": issue_desc, "detected_date": TODAY,
            "source_script": "sync_data_foundation.py", "status": "open",
            "resolved_date": "", "resolution_note": "",
        })

    for nid in sorted(ids_v344 - new_t1_ids):
        add("清单版本脱节", nid, "中", "V3.44权威清单已有此节点,数据底座T1未覆盖")
    for nid in sorted(new_t1_ids - ids_v344):
        add("清单版本脱节", nid, "中", "数据底座T1已有此节点,V3.44权威清单未收录")
    for fname, total, n_orphan, orphans in orphan_report:
        if n_orphan:
            add("下游表孤儿引用", fname, "高" if n_orphan > 5 else "中",
                f"{fname}的{total}个node_id里有{n_orphan}个在当前T1中不存在: {orphans}")
    for problem in t5t7_problems:
        add("04层-T5/T7不一致", "PAY/HR/...", "高", problem)
    for dm, info in t24_coverage.items():
        if info["交付物清单回填候选"] == 0 and dm != "KA":
            add("03层规则空白地图未解析", dm, "低",
                f"{dm}域的规则空白地图未能解析出交付物清单(可能格式与已适配的PAY/EQ/HR/TREASURY/FA不同,需人工核实)")
    add("结构性缺口", "02_信号提取基线", "高",
        "02_信号提取基线文件夹为空文件夹的判断已被本轮修正——实际内容在PAY域/全域/提取合集校准三个子目录下,本脚本已读取")
    add("功能限制", "T24", "低",
        "T24(交付物四标签风险分析)目前只解析PAY域'交付物N：'逐个编号格式;EQ/HR/INS/PARTNER/TREASURY/FA用'交付物群(合并分析)'格式未解析")

    fields = ["audit_id", "audit_type", "scope", "severity", "issue_desc", "detected_date",
              "source_script", "status", "resolved_date", "resolution_note"]
    return fields, rows


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("VNW 数据底座同步 —— 开始")
    print("=" * 70)

    print("\n[1/8] 从02层8域信号基线重建 T1/T2/T6/T11/T12 ...")
    tables, t2_rows, files_used = build_from_signal_baselines()
    print(f"  用到{len(files_used)}个域文件: {files_used}")
    print(f"  T1={len(tables['t1'][1])}节点  T2={len(t2_rows)}信号  "
          f"T6={len(tables['t6'][1])}交付物  T11={len(tables['t11'][1])}岗位映射  T12={len(tables['t12'][1])}Gate明细")

    print("\n[2/8] 用03层规则空白地图回填T6 + 建T24 ...")
    t6_rows, filled, t24, t24_coverage = enrich_t6_and_build_t24(tables["t6"][1])
    print(f"  T6回填 {filled}/{len(t6_rows)} 行")
    print(f"  T24({len(t24[1])}条,仅PAY格式覆盖) 各域交付物清单回填候选: "
          f"{ {k: v['交付物清单回填候选'] for k, v in t24_coverage.items()} }")

    print("\n[3/8] 用03层熔断节点补建清单(各域取最新版本) 重建T18 + 建T25(熔断状态清单) ...")
    t18, t18_files, t18_domain_count = build_t18_from_remediation_lists()
    print(f"  用到{len(t18_files)}个域文件: {t18_files}")
    print(f"  T18共{len(t18[1])}条任务, 各域任务数: {t18_domain_count}")
    t25 = build_t25_fused_status(tables["t1"][1], t18[1])
    fused_n = sum(1 for r in t25[1] if r["fused_status"] == "熔断")
    print(f"  T25: {fused_n}/{len(t25[1])}个节点判定为熔断 (T1本身已不再携带熔断字段)")

    print("\n[4/8] 校验T5/T7是否仍与04层一致(不重建,只报警) ...")
    t5t7_problems = validate_t5_t7_against_source()
    if t5t7_problems:
        print("  ⚠ 发现不一致:")
        for p in t5t7_problems:
            print("   -", p)
    else:
        print("  ✅ T5/T7与04层完全一致")

    print("\n[5/8] 重建T20(L4 Skill封装可行性评估) ...")
    t20_fields, t20_rows, src_name = build_t20(tables["t1"][1])
    print(f"  源文件: {src_name}  共{len(t20_rows)}条L4")

    print("\n[6/8] 校验T9/T13/T18/T19孤儿引用 + 重算T14计数 ...")
    t5_rows = read_csv(DB1 / "T5_规则清单_全域_v3.0.csv")
    orphan_report, t14 = reconcile_and_recount(tables["t1"][1], t2_rows, t5_rows, t24_coverage, t18[1])
    for fname, total, n_orphan, orphans in orphan_report:
        flag = "✅" if n_orphan == 0 else "⚠"
        print(f"  {flag} {fname}: {total}个node_id, 孤儿引用{n_orphan}个")

    print("\n[7/8] 生成T21审计快照(全量重写) ...")
    t21 = build_t21(tables["t1"][1], orphan_report, t5t7_problems, t24_coverage)
    print(f"  T21共{len(t21[1])}条记录")

    print("\n[8/8] 写出全部表(两处数据底座同步) ...")
    write_both("T1_节点索引_全域_v2.0.csv", *tables["t1"])
    write_both("T2_信号数据_全域_v3.0.csv",
               ["signal_id", "node_id", "content", "source", "confidence", "rule_subtype",
                "completeness", "l_layer", "rule_trigger", "rule_action", "rule_standard",
                "rule_exception", "rule_owner", "externalized", "round", "source_recording"],
               t2_rows)
    write_both("T6_交付物清单_全域_v3.1.csv", tables["t6"][0], t6_rows)
    write_both("T11_岗位映射_全域_v3.0.csv", *tables["t11"])
    write_both("T12_Gate评级明细_全域_v3.0.csv", *tables["t12"])
    write_both("T14_域扩展进度_全域_v2.1.csv", *t14)
    write_both("T18_熔断任务分发_全域_v2.0.csv", *t18)
    write_both("T25_熔断状态清单_全域_v1.0.csv", *t25)
    write_both("T20_L4自动化Tier评估_全域_v1.0.csv", t20_fields, t20_rows)
    write_both("T24_交付物四标签风险分析_全域_v1.0.csv", *t24)
    write_both("T21_数据对齐审计_全域_v1.0.csv", *t21)

    print("\n" + "=" * 70)
    print("同步完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
