#!/usr/bin/env python3
"""VNW · 数据底座同步脚本

一键可重复执行:每次源头更新后,重新运行本脚本,把前端展示数据底座里的派生表全部
按最新源重新生成一遍。T9/T13只做孤儿引用校验,不重建内容(人工维护的过程追踪表,
owner/phase/blocker这类字段无法机械推导)。T3/T4/T10/T16/T17不在本脚本管理范围内。
T22是人工试点分类示例,同样不在自动重建范围内(详见build_t21对应的T21审计条目)。

权威数据源分级(2026-07-26 Jasper拍板,这是本脚本最重要的设计原则,后续修改必须遵守):
- **数据仓库optional(PostgreSQL,process_analytics schema)是公司标准化的权威数据源**,
  跟01-05层文件材料冲突时,一律以数据仓库为准。T1/T12/T20/T25/T26以及新增T29/T30
  已切换为以数据仓库(dim_vn/dim_process/dim_agent/bridge_l3_l2/dim_org等表)为主要来源。
- **数据仓库没有的字段/表,才继续用01-05层文件材料(项目/OB知识库背后的原始素材)补充**——
  这些文件材料是"过程产物",对的错的标准的非标的混在一起,不是权威来源,只在数据仓库
  没覆盖到的地方兜底(例如T1的producer/consumer、T2信号明细、T5/T6/T7、SOP相关表)。
- 数据仓库连接参数在本地未提交文件`db_config_local.py`里,不进版本库。

设计原则(2026-07-25首次落地,后续修改请保持):
- 幂等:每次都是全量重新生成,不是增量追加。
- 不改源文件/不改数据仓库:01-05层文件只读;数据仓库只读(SELECT),从不写入。
- 同时写两处物理副本(规则分析工作区 + 规则前端设计的独立数据底座),保持已有的双份同步惯例。
- 03层'规则空白地图'目前只认PAY这种'交付物N：'逐个编号的格式;EQ/HR/INS/PARTNER/TREASURY/FA
  用的是'交付物群(N子产物合并分析)'合并写法,本脚本不解析,T24因此只覆盖PAY,运行时会如实打印这个限制。
- 03层'熔断节点补建清单'各域自动取最新版本号,已解析进T18,8个域全覆盖。
- T21审计结果是本次运行的即时快照,不做历史累积;需要看历史变化去查git history或另存副本。

用法: python3 sync_data_foundation.py
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
import psycopg2
import psycopg2.extras

try:
    from db_config_local import DB_CONFIG
except ImportError:
    try:
        from .db_config_local import DB_CONFIG
    except ImportError:
        DB_CONFIG = None

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
RULE_ANALYSIS = Path(
    "/Users/a112233/Desktop/流程架构项目_jasper/02_过程成果-工作产出/规则分析（Jasper）"
)
VNW_ROOT = Path(__file__).resolve().parents[2]
# 注:EA权威清单V3.44不在Jasper定义的输入范围内(2026-07-25拍板),本脚本不再对照它,
# 相关路径常量已移除,不用于任何审计/校验逻辑。
SIGNAL_BASELINE_DIR = RULE_ANALYSIS / "02_信号提取基线" / "提取合集校准"
GAP_MAP_DIR = RULE_ANALYSIS / "03_访谈准备与执行" / "规则空白地图"
RULE_GAP_DIR = RULE_ANALYSIS / "04_规则与GAP产出"
AGENT_SKILL_DIR = RULE_ANALYSIS / "Agent与Skill体系"
DB1 = RULE_ANALYSIS / "前端展示数据底座"
# VNW内的数据底座是前端与Agent共用的权威副本；EA项目内DB1保留为业务工作区镜像。
DB2 = VNW_ROOT / "07_接入记忆_Integrate_Memory" / "data_foundation"
DOMAINS = ["EQ", "FA", "HR", "INS", "KA", "PARTNER", "PAY", "TREASURY"]
TODAY = "2026-07-26"

# 2026-07-25:VNW前端接入数据底座,同步脚本末尾多一步把表导出成JSON给前端读。
APP_V2_DATA_DIR = Path(
    VNW_ROOT / "10_部署与运行_Deploy_and_Run" / "frontend" / "public" / "data"
)

# 2026-07-25:两处数据底座按Jasper要求分成5个子文件夹,本脚本只写A类(自动同步)。
# B/C/D类是校验读取的对象,不是本脚本的写入目标,但读取路径要跟着改。
TABLE_SUBDIR = {
    "T1": "A_自动同步_当前有效", "T2": "A_自动同步_当前有效", "T6": "A_自动同步_当前有效",
    "T11": "A_自动同步_当前有效", "T12": "A_自动同步_当前有效", "T14": "A_自动同步_当前有效",
    "T18": "A_自动同步_当前有效", "T19": "A_自动同步_当前有效", "T20": "A_自动同步_当前有效",
    "T21": "A_自动同步_当前有效", "T23": "A_自动同步_当前有效", "T24": "A_自动同步_当前有效",
    "T25": "A_自动同步_当前有效", "T26": "A_自动同步_当前有效",
    "T5": "A_自动同步_当前有效", "T7": "A_自动同步_当前有效",
    "T3": "C_人工维护_未自动化", "T4": "C_人工维护_未自动化", "T9": "C_人工维护_未自动化",
    "T10": "C_人工维护_未自动化", "T13": "C_人工维护_未自动化", "T16": "C_人工维护_未自动化",
    "T17": "C_人工维护_未自动化",
    "T22": "D_人工试点_非自动",
    "T29": "A_自动同步_当前有效", "T30": "A_自动同步_当前有效",
}


# ---------------------------------------------------------------------------
# 数据仓库连接(2026-07-26新增)——Jasper拍板:process_analytics schema所在的这个
# PostgreSQL数据库是公司标准化的权威数据源,跟01-05层文件材料冲突时以数据库为准;
# 数据库没有的字段,才继续用文件材料(01-05层)补充。DB_CONFIG来自本地未提交的
# db_config_local.py,该文件不进版本库。
# ---------------------------------------------------------------------------
def _json_safe(v):
    """把Postgres返回的date/datetime/Decimal/UUID转成JSON能直接序列化的类型,
    数值/字符串/布尔/None原样返回。"""
    import datetime
    import decimal
    import uuid
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def db_query(sql: str, params: tuple = ()) -> list[dict]:
    if DB_CONFIG is None:
        raise RuntimeError("db_config_local.py不存在或读取失败,无法连接数据仓库")
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [{k: _json_safe(v) for k, v in row.items()} for row in cur.fetchall()]
    finally:
        conn.close()


def table_path(base: Path, name: str) -> Path:
    prefix = name.split("_")[0]
    subdir = TABLE_SUBDIR.get(prefix)
    return (base / subdir / name) if subdir else (base / name)


def write_both(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    for target in (DB1, DB2):
        with open(table_path(target, name), "w", encoding="utf-8", newline="") as f:
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


SOP_DIR = RULE_ANALYSIS / "05_SOP"


def build_sop_only_nodes(t1_rows: list[dict], t1_fields: list[str]):
    """2026-07-25拍板:05_SOP里出现但02层8域批次没覆盖到的节点,以05_SOP为准补进T1
    (Jasper原话:'已05内的为准,旧的来源可以忽略')。通用逻辑,不是这次的6个节点写死——
    以后05_SOP再出现T1没有的新节点,重跑同步脚本会自动补上。
    优先解析SOP正文里的'节点信息'表(节点ID/节点名称/所属域/触发条件/主责岗位);
    没有这张表的(如老式PAY风格SOP),退化到只用头部'关联价值节点：'这一行提取node_id+name。"""
    existing_ids = set(r["node_id"] for r in t1_rows)
    added = []
    for sop_file in sorted(SOP_DIR.glob("SOP_*.md")):
        text = sop_file.read_text(encoding="utf-8", errors="replace")
        # 从'关联价值节点：'整行提取全部VN编码(可能一行写多个节点,如'VN-EQ-01 xxx；VN-EQ-02 xxx')
        assoc_m = re.search(r"关联价值节点[：:](.*)", text)
        candidate_ids = set(VN_CODE_RE.findall(assoc_m.group(1))) if assoc_m else set()
        # 兜底:节点信息表里的'节点ID'行
        node_info_m = re.search(r"节点ID\s*\|\s*(VN-[A-Z0-9]+-\d+)", text)
        if node_info_m:
            candidate_ids.add(node_info_m.group(1))
        missing = candidate_ids - existing_ids
        if not missing:
            continue
        for node_id in missing:
            # 尝试用'节点信息'表(如果这份SOP同时覆盖多个节点,表里的节点ID未必匹配当前node_id,
            # 此时退化到只填node_id+name,不强行套用可能属于别的节点的字段)
            row = {f: "" for f in t1_fields}
            row["node_id"] = node_id
            info_block_m = re.search(
                rf"节点ID\s*\|\s*{re.escape(node_id)}\s*\|?.*?(?=\n---|\n##|\Z)", text, re.S)
            if info_block_m:
                block = info_block_m.group(0)
                name_m = re.search(r"节点名称\s*\|\s*([^\n|]+)", block)
                domain_m = re.search(r"所属域\s*\|\s*([^\n|]+)", block)
                trigger_m = re.search(r"触发条件\s*\|\s*([^\n|]+)", block)
                owner_m = re.search(r"主责岗位\s*\|\s*([^\n|]+)", block)
                row["node_name"] = name_m.group(1).strip() if name_m else ""
                row["domain"] = (domain_m.group(1).strip()[:2] if domain_m else "")
                row["start_point"] = trigger_m.group(1).strip() if trigger_m else ""
                row["producer"] = owner_m.group(1).strip() if owner_m else ""
            else:
                # 退化路径:从'关联价值节点：VN-XXX 名称'这段文字里抠节点名
                name_fallback = re.search(rf"{re.escape(node_id)}\s+([^\n；;、]+)", assoc_m.group(1) if assoc_m else "")
                row["node_name"] = name_fallback.group(1).strip() if name_fallback else ""
                row["domain"] = node_id.split("-")[1] if "-" in node_id else ""
            row["version"] = "05_SOP直接来源(不在02层8域批次内)"
            row["last_updated"] = TODAY
            row["source_file"] = sop_file.name
            added.append(row)
            existing_ids.add(node_id)
    return added


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
            # 源标题行有的带'[🔴熔断]'这类后缀标注(如'### VN-EQ-01 · 同行经代服务方案 [🔴熔断]'),
            # T1不携带熔断信息(2026-07-25拍板,见build_t25_fused_status),node_name要把这个后缀去掉
            node_name = re.sub(r"\s*\[[^\[\]]*\]\s*$", "", hm.group(2).strip()).strip()
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
_STATUS_SYNONYMS = ["任务状态", "当前状态", "状态"]
_REMARK_SYNONYMS = ["阻塞", "交付物上传要求"]


def _pick_col(header: list[str], synonyms: list[str]) -> str | None:
    for syn in synonyms:
        if syn in header:
            return syn
    return None


def _normalize_task_status(raw: str) -> str:
    """源文档状态是唯一输入；避免每次同步把已核实进度重置为“未分发”。

    推荐源文档统一使用：未分发 / 进行中 / 待验收 / 已完成 / 已阻塞。
    """
    value = (raw or "").strip()
    if any(word in value for word in ("已完成", "完成", "已验收", "关闭")):
        return "已完成"
    if any(word in value for word in ("待验收", "待核实", "待确认")):
        return "待验收"
    if any(word in value for word in ("进行中", "处理中", "已分发", "推进中")):
        return "进行中"
    if any(word in value for word in ("阻塞", "暂停")):
        return "已阻塞"
    return "未分发"


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
            status_col = _pick_col(header, _STATUS_SYNONYMS)
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
                    "task_status": _normalize_task_status(row.get(status_col, "") if status_col else ""),
                    "deliverable_id": "",
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
VN_CODE_RE = re.compile(r"VN-[A-Z0-9]+-\d+")


# 2026-07-26: build_t25_fused_status(03层熔断节点补建清单全文扫描版)已废弃移除——
# T25改为直接查process_analytics.dim_vn.is_fused(数据仓库权威源,见build_t12_t25_from_dim_vn)。
# 跟这版03层文件扫描逻辑对照过KA域6个节点,判断完全一致,数据仓库口径没有引入新矛盾。


# ---------------------------------------------------------------------------
# 阶段4: T5/T7直接从04层规则清单/Gap清单重建(2026-07-25起,不再是'只校验不重建')
# ---------------------------------------------------------------------------


def build_t5_t7():
    """2026-07-25起T5/T7从'只校验不重建'改为直接从04层规则清单/Gap清单拼接重建,
    跟其他表一样纳入A类自动同步,不再单独留在B类。
    T5(规则清单):04层各域文件本身没有domain列,拼接时按域文件名补上,20列跟旧T5完全对齐。
    T7(缺口清单):04层各域文件已带domain列,但比旧T7少两列——sop_field_affected(45行有真实值,
    04层原始文件里没有这个字段,是后续人工/流程补充的)和resolution_date(旧T7里全部为空)。
    重建时从'旧T7'按gap_id读回sop_field_affected的值,不能让这次重建把这45条丢了;
    resolution_date当前确实没有别的来源,如实留空。"""
    # 2026-07-25把T5/T7从B类挪进A类,旧T7物理文件在迁移前还留在B文件夹里,
    # 这里显式读B文件夹的旧版本抢救sop_field_affected(T5/T7一旦在A类重建之后,
    # 旧B文件夹副本会被清空,这个显式路径只是这一次迁移用,不是长期依赖B文件夹)。
    old_t7_path = DB1 / "B_已验证未重写_04层原表" / "T7_缺口清单_全域_v4.2.csv"
    if not old_t7_path.exists():
        old_t7_path = table_path(DB1, "T7_缺口清单_全域_v4.2.csv")  # 已迁移过一次之后,从A类读回保留值
    old_sop_field = {}
    if old_t7_path.exists():
        for r in read_csv(old_t7_path):
            if r.get("sop_field_affected"):
                old_sop_field[r["gap_id"]] = r["sop_field_affected"]

    t5_fields = ["rule_id", "node_id", "rule_name", "rule_class", "rule_trigger", "rule_action",
                 "rule_standard", "rule_exception", "rule_owner", "data_anchor", "externalized",
                 "gap_type", "gap_description", "priority", "source", "round", "source_recording",
                 "version", "legacy_rule_id", "domain"]
    t7_fields = ["gap_id", "node_id", "node_name", "domain", "description", "gap_type",
                 "gap_subtype", "priority", "extractability", "status", "resolution_note",
                 "linked_rule_id", "linked_recording_md", "sop_status", "sop_field_affected",
                 "resolution_date"]

    t5_rows, t7_rows = [], []
    for dm in DOMAINS:
        rule_file = latest(RULE_GAP_DIR, f"规则清单_{dm}_v*.csv")
        gap_file = latest(RULE_GAP_DIR, f"Gap清单_{dm}_v*.csv")
        if rule_file:
            for r in read_csv(rule_file):
                row = {f: r.get(f, "") for f in t5_fields}
                row["domain"] = dm
                t5_rows.append(row)
        if gap_file:
            for r in read_csv(gap_file):
                row = {f: r.get(f, "") for f in t7_fields}
                row["sop_field_affected"] = old_sop_field.get(r["gap_id"], "")
                row["resolution_date"] = ""
                t7_rows.append(row)
    return (t5_fields, t5_rows), (t7_fields, t7_rows)


# ---------------------------------------------------------------------------
# 阶段5: L4 Skill封装可行性评估 → T20
# ---------------------------------------------------------------------------
def build_t20():
    """T20(2026-07-26起改为数据仓库权威源): process_analytics.dim_process,
    取代此前解析'L4流程_Skill封装可行性评估'xlsx的做法。跟文件版对照过L3-IRI这个
    真实例子,368条L4里automation_tier判断有出入(数据仓库整体更'乐观',更多判Auto)——
    数据仓库是权威源,直接以它为准,不再跟xlsx对齐。
    候选Agent字段这次没有并进来:核实过dim_agent(361行,1L4=1个规划中的原子Agent)
    和dim_process按l3_code+l4_name能对上的只有155/361(43%),关联太弱,不编造这个
    连接——T26独立建表,不做L4级别的强行关联。agent_d1-d6这套6维打分体系目前
    在数据仓库里基本是空的(schema设计好了,还没真正打分),如实原样带出,不补造数值。"""
    field_names = [
        "l1_code", "l3_code", "l3_name", "l3_domain", "l3_status", "l3_trigger", "l3_exit_condition",
        "l4_code", "l4_name", "l4_deliverable", "l4_deliverable_type", "l4_accountable_role",
        "l4_accountable_family", "l5_step", "agentifiability", "agent_human_touchpoint",
        "agent_d1_input_struct", "agent_d2_rule_clear", "agent_d3_output_verify",
        "agent_d4_api_reach", "agent_d5_fallback", "agent_d6_compliance", "agent_score_total",
        "sla_hours", "sla_source", "version", "valid_from", "source_notes",
    ]
    rows = db_query(f"""
        SELECT {', '.join(field_names)}
        FROM process_analytics.dim_process
        WHERE is_current = true
        ORDER BY l3_code, l4_code
    """)
    for r in rows:
        for k, v in r.items():
            if v is None:
                r[k] = ""
    return (field_names, rows), "process_analytics.dim_process(数据仓库)"


def build_t26_candidate_agents():
    """T26(2026-07-26起改为数据仓库权威源): process_analytics.dim_agent。
    注意重大颗粒度变化:原来是30个'聚合候选Agent'(每个覆盖多条L4);数据仓库这边是
    361行'1个L4=1个原子级规划中Agent',全部agent_status='规划中',没有已上线的。
    这是两种不同的Agent组织哲学,不是同一份数据的新旧版本,不能把它当作对旧T26的
    简单替换来理解——旧的'候选Agent聚合'概念目前在数据仓库里没有对应表,如实反映现状。"""
    field_names = [
        "agent_code", "agent_name", "agent_type", "agent_status", "l3_primary",
        "l4_count_covered", "tech_stack", "platform_path", "owner_position_family",
        "m4_priority", "go_live_date", "baseline_accuracy", "baseline_throughput",
    ]
    rows = db_query(f"""
        SELECT {', '.join(field_names)}
        FROM process_analytics.dim_agent
        ORDER BY agent_code
    """)
    for r in rows:
        for k, v in r.items():
            if v is None:
                r[k] = ""
    return (field_names, rows), "process_analytics.dim_agent(数据仓库)"


def build_t29_l3_l2_bridge():
    """T29(新增,2026-07-26): L3↔L2业务能力桥接,源头process_analytics.bridge_l3_l2。
    此前L2归属只能从L2业务能力详情卡csv的分号拼接字段(l3_codes_architecture)反查,
    覆盖61/68个L3且是多对多塞进一个字符串字段;这张桥接表是数据仓库里的规范化版本,
    直接权威,不用再反查字符串。"""
    field_names = ["l3_code", "l2_code", "l2_name", "l1_code", "l1_name"]
    rows = db_query(f"SELECT {', '.join(field_names)} FROM process_analytics.bridge_l3_l2 ORDER BY l3_code")
    return (field_names, rows), "process_analytics.bridge_l3_l2(数据仓库)"


def build_t30_org():
    """T30(新增,2026-07-26): 岗位组织族信息,源头process_analytics.dim_org。
    此前岗位信息只能从02层信号基线的产出方/消费方自由文本里正则拆分(曾有过把括号
    说明误拆成角色名的bug),这张表是数据仓库里的规范化版本,含编制目标/汇报关系。"""
    field_names = [
        "position_family", "position_family_name", "position_code", "position_name",
        "position_nature", "ep_count", "headcount_target_min", "headcount_target_max",
        "mark_retained", "executor_id", "executor_name", "reports_to_family", "is_active",
    ]
    rows = db_query(f"SELECT {', '.join(field_names)} FROM process_analytics.dim_org WHERE is_active = true ORDER BY position_family")
    for r in rows:
        for k, v in r.items():
            if v is None:
                r[k] = ""
    return (field_names, rows), "process_analytics.dim_org(数据仓库)"


def build_t12_t25_from_dim_vn():
    """T12(Gate评级明细)+T25(熔断状态清单) 2026-07-26起改为数据仓库权威源:
    process_analytics.dim_vn。之前T12来自02层Step2解析、T25来自03层熔断节点补建清单
    扫描;两者跟这次查到的dim_vn.is_fused对比过KA域6个节点,判断完全一致(全部True),
    验证过数据仓库口径没有引入新矛盾。dim_vn共93个vn_id,比文件拼出来的T1(78个)多,
    多出的15个如实体现在T1合并阶段(见merge_t1_with_dim_vn),这里不重复处理。"""
    dv_fields = [
        "vn_id", "vn_name", "l3_code", "gate1_data_linked", "gate2_grounded",
        "gate3_traceable", "overall_judgment", "is_fused", "priority",
    ]
    rows = db_query(f"SELECT {', '.join(dv_fields)} FROM process_analytics.dim_vn ORDER BY vn_id")
    t12_fields = ["node_id", "node_name", "l3_code", "gate1_status", "gate2_status",
                  "gate3_status", "overall_judgment", "source"]
    t25_fields = ["node_id", "node_name", "l3_code", "fused_status", "priority", "source"]
    t12_rows, t25_rows = [], []
    for r in rows:
        t12_rows.append({
            "node_id": r["vn_id"], "node_name": r["vn_name"], "l3_code": r["l3_code"] or "",
            "gate1_status": r["gate1_data_linked"] or "", "gate2_status": r["gate2_grounded"] or "",
            "gate3_status": r["gate3_traceable"] or "", "overall_judgment": r["overall_judgment"] or "",
            "source": "process_analytics.dim_vn(数据仓库)",
        })
        t25_rows.append({
            "node_id": r["vn_id"], "node_name": r["vn_name"], "l3_code": r["l3_code"] or "",
            "fused_status": "熔断" if r["is_fused"] else "非熔断",
            "priority": r["priority"] or "", "source": "process_analytics.dim_vn(数据仓库)",
        })
    return (t12_fields, t12_rows), (t25_fields, t25_rows)


def merge_t1_with_dim_vn(t1_rows: list[dict], t1_fields: list[str]):
    """把dim_vn(93个vn_id)的l3_code/l2_code/l2_name/l1_code/vs_code/priority
    合并进T1(文件拼出来的78个node_id)。冲突以数据仓库为准(覆盖priority);
    数据仓库有但文件没有的15个节点,作为新行补进T1(文件字段留空,如实标注来源,
    不编造02层信号数据);文件有但数据仓库没有的节点(本session从05_SOP直接补入
    T1的6个),数据仓库字段留空,不强行匹配。"""
    dv_rows = db_query("""
        SELECT vn_id, vn_name, l3_code, priority, vn_composition, vn_physical_form,
               vn_start_point, vn_end_point, m_anchor, kpi_anchor
        FROM process_analytics.dim_vn
    """)
    bridge_rows = db_query("SELECT l3_code, l2_code, l2_name, l1_code FROM process_analytics.bridge_l3_l2")
    l3_to_l2 = {}
    for b in bridge_rows:
        l3_to_l2.setdefault(b["l3_code"], []).append(b)
    dv_by_id = {r["vn_id"]: r for r in dv_rows}

    new_fields = t1_fields + ["l3_code", "l2_code", "l2_name", "l1_code", "vs_code"]
    existing_ids = {r["node_id"] for r in t1_rows}

    def apply_dw(row: dict, dv: dict):
        row["l3_code"] = dv["l3_code"] or ""
        l2_matches = l3_to_l2.get(dv["l3_code"], [])
        row["l2_code"] = l2_matches[0]["l2_code"] if l2_matches else ""
        row["l2_name"] = l2_matches[0]["l2_name"] if l2_matches else ""
        row["l1_code"] = l2_matches[0]["l1_code"] if l2_matches else ""
        row["vs_code"] = ""  # dim_vn本身没有vs_code非空值的稳定来源,留空不编造
        if dv["priority"]:
            row["priority"] = dv["priority"]  # 数据仓库权威,覆盖文件版

    for row in t1_rows:
        row.setdefault("l3_code", "")
        row.setdefault("l2_code", "")
        row.setdefault("l2_name", "")
        row.setdefault("l1_code", "")
        row.setdefault("vs_code", "")
        dv = dv_by_id.get(row["node_id"])
        if dv:
            apply_dw(row, dv)

    extra_from_dw = []
    for vn_id, dv in dv_by_id.items():
        if vn_id in existing_ids:
            continue
        blank_row = {f: "" for f in t1_fields}
        blank_row["node_id"] = vn_id
        domain_m = re.match(r"VN-([A-Z]+)-", vn_id)
        blank_row["domain"] = domain_m.group(1) if domain_m else ""
        blank_row["node_name"] = dv["vn_name"] or ""
        blank_row["source_file"] = "process_analytics.dim_vn(数据仓库补充,文件材料未覆盖)"
        apply_dw(blank_row, dv)
        extra_from_dw.append(blank_row)

    return new_fields, t1_rows + extra_from_dw, len(extra_from_dw)


# ---------------------------------------------------------------------------
# 阶段6: T9/T13/T18/T19孤儿引用校验 + T14机械计数重算
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 阶段5b: T19重建 —— 真正扫描05_SOP当前全部文件(2026-07-25发现之前只认'SOP_VN-*.md',
# 漏了8份用TOI/TOB-EVD-编码和L3-编码写的SOP,41份文件里只覆盖了33份)。
# 三种编码体系都收:VN价值节点(可关联T7做Gap对齐校验)/TOI-TOB证据类/L3流程类(后两种
# 不挂在具体价值节点下,gap字段留空,如实标注,不编造关联)。
# ---------------------------------------------------------------------------
# 不要求以'_'收尾——'SOP_VN-XX-例会机制_...'这种编码后面直接接中文说明(没有下划线分隔),
# 之前要求trailing'_'导致这两份匹配失败,退化成用整个文件名当ref,现在放开这个限制。
# 2026-07-26修复:纯ASCII的主分组之外,加一个可选的"-中文描述段"尾缀(遇到下一个'_'才停),
# 专门覆盖'VN-XX-例会机制'/'VN-XX-季度激励'这种域码是占位符'XX'、靠后缀中文区分的文件——
# 之前两份文件都被截断成'VN-XX',sop_ref冲突导致T19出现两行相同ref(排查SOP版前端原型时
# 发现,该原型后已取消,但这条ref唯一性修复是T19自身的数据正确性问题,予以保留)。
# 其余正常文件(ASCII段后直接跟'_'的)不受影响,可选组不会触发。
SOP_REF_RE = re.compile(r"SOP_([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?:-[^_]+)?)")


def build_t19_sop_status(t7_rows: list[dict]):
    node_gaps_db = defaultdict(list)  # node_id -> [status, status, ...]，T7自带status字段(open/等)
    for row in t7_rows:
        node_gaps_db[row["node_id"]].append(row.get("status", ""))

    fields = ["sop_ref", "coding_scheme", "domain", "sop_title", "sop_version",
              "sop_status", "generation_date", "gap_total", "gap_open", "gap_resolved",
              "sop_file", "last_synced"]
    rows = []
    for sop_file in sorted(SOP_DIR.glob("SOP_*.md")):
        text = sop_file.read_text(encoding="utf-8", errors="replace")
        m = SOP_REF_RE.match(sop_file.name)
        ref = m.group(1) if m else sop_file.stem

        if ref.startswith("VN-"):
            scheme = "VN价值节点"
            domain_m = re.match(r"VN-([A-Z]+)-", ref)
            domain = domain_m.group(1) if domain_m else ""
        elif ref.startswith(("TOI-", "TOB-")):
            scheme = "TOI-TOB证据"
            domain = ""
        elif ref.startswith("L3-"):
            scheme = "L3流程"
            domain = ""
        else:
            scheme = "其他"
            domain = ""

        title_m = re.search(r"^#\s*(?:SOP[·_ ]?)?(.+)$", text, re.M)
        version_m = re.search(r"版本[：:]\s*(v[\d.]+)", text)
        status_m = re.search(r"[>\s]状态[：:]\s*([^\n]+)", text)
        date_m = re.search(r"生成日期[：:]\s*([\d-]+)", text)

        gap_total = gap_open = gap_resolved = ""
        if scheme == "VN价值节点":
            statuses = node_gaps_db.get(ref, [])
            gap_total = str(len(statuses))
            gap_open = str(sum(1 for s in statuses if s == "open"))
            gap_resolved = str(sum(1 for s in statuses if s and s != "open"))

        rows.append({
            "sop_ref": ref, "coding_scheme": scheme, "domain": domain,
            "sop_title": title_m.group(1).strip() if title_m else "",
            "sop_version": version_m.group(1) if version_m else "",
            "sop_status": status_m.group(1).strip() if status_m else "",
            "generation_date": date_m.group(1) if date_m else "",
            "gap_total": gap_total, "gap_open": gap_open, "gap_resolved": gap_resolved,
            "sop_file": sop_file.name, "last_synced": TODAY,
        })
    return fields, rows


def build_t23_handoff_tracking(new_t1_rows: list[dict], t19_rows: list[dict]):
    """T23此前是用旁支脚本手动建的一次性快照,从没被纳入sync_data_foundation.py,
    2026-07-25发现并补上。内容本身是机械的(每个节点未移交状态+L3-COM试点标记),
    可以每次跟着T1节点集重新生成,不用再手动维护。sop_status_ref从新T19按sop_ref=node_id关联。"""
    sop_status_by_node = {r["sop_ref"]: r["sop_status"] for r in t19_rows if r["coding_scheme"] == "VN价值节点"}
    pay_pilot_nodes = {"VN-PAY-01", "VN-PAY-02", "VN-PAY-03", "VN-PAY-04", "VN-PAY-05",
                        "VN-PAY-06", "VN-PAY-07", "VN-PAY-08", "VN-PAY-09"}
    fields = ["node_id", "sop_status_ref", "handoff_status", "handoff_date",
              "ait_breakdown_status", "pilot_flag", "decision_ref", "next_action", "last_updated"]
    rows = []
    for r in new_t1_rows:
        nid = r["node_id"]
        is_pilot = nid in pay_pilot_nodes
        rows.append({
            "node_id": nid, "sop_status_ref": sop_status_by_node.get(nid, ""),
            "handoff_status": "未移交", "handoff_date": "",
            "ait_breakdown_status": "", "pilot_flag": "TRUE" if is_pilot else "FALSE",
            "decision_ref": "D-20260721-001" if is_pilot else "",
            "next_action": "等VNW批次2(基线合并)完成后,倒推L3-COM为AIT标准格式SOP" if is_pilot else "",
            "last_updated": TODAY,
        })
    return fields, rows


def reconcile_and_recount(new_t1_rows, t2_rows, t5_rows, domain_result, t18_rows):
    new_t1_ids = set(r["node_id"] for r in new_t1_rows)
    orphan_report = []
    # T19已改为直接扫描05_SOP现场文件重建(不再是靠node_id孤儿校验的静态表),不在这里查
    for fname, key in [
        ("T9_价值流归属_全域_v1.4.csv", "vn_id"),
        ("T13_节点复评追踪_全域_v1.7.csv", "node_id"),
    ]:
        path = table_path(DB1, fname)
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
    t3_rows = read_csv(table_path(DB1, "T3_访谈线索_全域_v3.2.csv"))
    t3_by_domain = Counter()
    for r in t3_rows:
        dom = node_to_domain.get(r.get("node_id", ""))
        if dom:
            t3_by_domain[dom] += 1
    t5_by_domain = Counter(r["domain"] for r in t5_rows)

    t14_path = latest(DB1 / "A_自动同步_当前有效", "T14_域扩展进度_全域_v*.csv")
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
    # 2026-07-25拍板:审计范围只按Jasper定义的输入文件走(02层信号基线/03层规则空白地图+
    # 熔断节点补建清单/04层规则GAP清单/L4评估表/候选Agent数据表),不再拿EA项目的权威清单
    # V3.44做比对——V3.44不在本次定义的输入范围内,不算数据表的缺口,不进这张审计表。
    rows, aid = [], [0]

    def add(audit_type, scope, severity, issue_desc):
        aid[0] += 1
        rows.append({
            "audit_id": f"AUD-{aid[0]:03d}", "audit_type": audit_type, "scope": scope,
            "severity": severity, "issue_desc": issue_desc, "detected_date": TODAY,
            "source_script": "sync_data_foundation.py", "status": "open",
            "resolved_date": "", "resolution_note": "",
        })

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
    add("功能限制", "T24", "低",
        "T24(交付物四标签风险分析)目前只解析PAY域'交付物N：'逐个编号格式;EQ/HR/INS/PARTNER/TREASURY/FA用'交付物群(合并分析)'格式未解析")
    add("人工维护表", "T22", "低",
        "T22(SOP规则人机协同分类)是VN-PAY-01的4条人工试点分类示例(2026-07-25建,pilot_flag=TRUE),"
        "不是从01-04源文件能机械推导的内容(需要人工判断Auto/人工/协同),不在本脚本的自动重建范围内,"
        "不会随源文件更新而自动刷新——如果要扩大到其他节点/规则,需要人工逐条补充,不是脚本能做的")

    fields = ["audit_id", "audit_type", "scope", "severity", "issue_desc", "detected_date",
              "source_script", "status", "resolved_date", "resolution_note"]
    return fields, rows


# ---------------------------------------------------------------------------
# 阶段8: 导出JSON给前端(app_v2)用 —— A类16张(本次已在内存里,直接导出)+
# C类7张/T22(D类,人工维护/试点,脚本不重建内容,原样从磁盘读出转JSON,保持前端
# 现有页面不断供)。E类(L3蓝图覆盖清单)不导出,不在前端范围内。
# ---------------------------------------------------------------------------
MANUAL_TABLES_FOR_JSON = {
    # json_key: 磁盘文件名(在对应分类文件夹下,用table_path()找)
    "interview_leads": "T3_访谈线索_全域_v3.2.csv",
    "actions": "T4_行动项_全域_v2.7.csv",
    "value_stream": "T9_价值流归属_全域_v1.4.csv",
    "interview_batches": "T10_访谈批次与岗位映射_全域_v2.0.csv",
    "node_review": "T13_节点复评追踪_全域_v1.7.csv",
    "interview_recordings": "T16_访谈记录跟踪_全域_v2.0.csv",
    "report_tracking": "T17_报告跟踪_全域_v1.0.csv",
    "sop_pilot_classification": "T22_SOP规则人机协同分类_全域_v1.0.csv",
}


def export_json_for_frontend(built_tables: dict[str, list[dict]]):
    APP_V2_DATA_DIR.mkdir(parents=True, exist_ok=True)
    exported = {}
    for key, rows in built_tables.items():
        with open(APP_V2_DATA_DIR / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        exported[key] = len(rows)
    for key, fname in MANUAL_TABLES_FOR_JSON.items():
        path = table_path(DB1, fname)
        rows = read_csv(path) if path.exists() else []
        with open(APP_V2_DATA_DIR / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        exported[key] = len(rows)
    return exported


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

    sop_extra_nodes = build_sop_only_nodes(tables["t1"][1], tables["t1"][0])
    if sop_extra_nodes:
        tables["t1"][1].extend(sop_extra_nodes)
        print(f"  + 05_SOP补充了{len(sop_extra_nodes)}个02层批次没有的节点: "
              f"{[r['node_id'] for r in sop_extra_nodes]}")

    print("\n[1b/8] 用数据仓库(process_analytics.dim_vn/bridge_l3_l2)合并L3/L2归属 + 补充节点 ...")
    t1_fields_dw, t1_rows_dw, n_extra = merge_t1_with_dim_vn(tables["t1"][1], tables["t1"][0])
    tables["t1"] = (t1_fields_dw, t1_rows_dw)
    print(f"  T1并入l3_code/l2_code/l2_name/l1_code字段(数据仓库权威,冲突覆盖priority);"
          f"数据仓库补充了{n_extra}个文件材料没覆盖的节点,T1现共{len(t1_rows_dw)}行")

    print("\n[2/8] 用03层规则空白地图回填T6 + 建T24 ...")
    t6_rows, filled, t24, t24_coverage = enrich_t6_and_build_t24(tables["t6"][1])
    print(f"  T6回填 {filled}/{len(t6_rows)} 行")
    print(f"  T24({len(t24[1])}条,仅PAY格式覆盖) 各域交付物清单回填候选: "
          f"{ {k: v['交付物清单回填候选'] for k, v in t24_coverage.items()} }")

    print("\n[3/8] 用03层熔断节点补建清单(各域取最新版本) 重建T18 ...")
    t18, t18_files, t18_domain_count = build_t18_from_remediation_lists()
    print(f"  用到{len(t18_files)}个域文件: {t18_files}")
    print(f"  T18共{len(t18[1])}条任务, 各域任务数: {t18_domain_count}")

    print("\n[3b/8] 重建T12(Gate评级)+T25(熔断状态) —— 数据仓库权威源(dim_vn) ...")
    t12_dw, t25 = build_t12_t25_from_dim_vn()
    fused_n = sum(1 for r in t25[1] if r["fused_status"] == "熔断")
    print(f"  T12/T25共{len(t25[1])}个节点(数据仓库dim_vn),{fused_n}个判定为熔断")

    print("\n[4/8] 重建T5/T7(直接从04层规则清单/Gap清单拼接,不再只校验) ...")
    t5, t7 = build_t5_t7()
    print(f"  T5共{len(t5[1])}条规则  T7共{len(t7[1])}条Gap "
          f"(sop_field_affected保留了{sum(1 for r in t7[1] if r['sop_field_affected'])}条既有值)")

    print("\n[5/8] 重建T20(L4自动化Tier) + T26(Agent规划) —— 数据仓库权威源 ...")
    t20, t20_src = build_t20()
    print(f"  T20源: {t20_src}  共{len(t20[1])}条L4")
    t26, t26_src = build_t26_candidate_agents()
    print(f"  T26源: {t26_src}  共{len(t26[1])}行(注意:1L4=1原子Agent,跟旧版30个聚合候选Agent是不同颗粒度)")

    print("\n[5c/8] 新增T29(L3-L2桥接)+T30(岗位组织) —— 数据仓库 ...")
    t29, t29_src = build_t29_l3_l2_bridge()
    t30, t30_src = build_t30_org()
    print(f"  T29共{len(t29[1])}条L3-L2映射  T30共{len(t30[1])}个岗位族")

    print("\n[5b/8] 重建T19 —— 直接扫描05_SOP当前全部文件(含TOI/TOB-EVD/L3非VN编码) ...")
    t19 = build_t19_sop_status(t7[1])
    from collections import Counter as _Counter
    print(f"  共{len(t19[1])}份SOP文件, 编码体系分布: "
          f"{dict(_Counter(r['coding_scheme'] for r in t19[1]))}")

    t23 = build_t23_handoff_tracking(tables["t1"][1], t19[1])

    print("\n[6/8] 校验T9/T13孤儿引用 + 重算T14计数 ...")
    orphan_report, t14 = reconcile_and_recount(tables["t1"][1], t2_rows, t5[1], t24_coverage, t18[1])
    for fname, total, n_orphan, orphans in orphan_report:
        flag = "✅" if n_orphan == 0 else "⚠"
        print(f"  {flag} {fname}: {total}个node_id, 孤儿引用{n_orphan}个")

    print("\n[7/8] 生成T21审计快照(全量重写) ...")
    # T5/T7现在直接从04层构建(build_t5_t7),不再是'先有旧文件再校验'的模式,
    # 天然保证一致,不会再产生'04层-T5/T7不一致'这类审计条目
    t21 = build_t21(tables["t1"][1], orphan_report, [], t24_coverage)
    print(f"  T21共{len(t21[1])}条记录")

    print("\n[8/8] 写出全部表(两处数据底座同步) ...")
    write_both("T1_节点索引_全域_v2.0.csv", *tables["t1"])
    write_both("T2_信号数据_全域_v3.0.csv",
               ["signal_id", "node_id", "content", "source", "confidence", "rule_subtype",
                "completeness", "l_layer", "rule_trigger", "rule_action", "rule_standard",
                "rule_exception", "rule_owner", "externalized", "round", "source_recording"],
               t2_rows)
    write_both("T5_规则清单_全域_v3.0.csv", *t5)
    write_both("T7_缺口清单_全域_v4.2.csv", *t7)
    write_both("T6_交付物清单_全域_v3.1.csv", tables["t6"][0], t6_rows)
    write_both("T11_岗位映射_全域_v3.0.csv", *tables["t11"])
    write_both("T12_Gate评级明细_全域_v4.0.csv", *t12_dw)
    write_both("T14_域扩展进度_全域_v2.1.csv", *t14)
    write_both("T18_熔断任务分发_全域_v2.0.csv", *t18)
    write_both("T19_SOP生产进度_全域_v2.0.csv", *t19)
    write_both("T23_VNW_AIT移交追踪_全域_v2.0.csv", *t23)
    write_both("T25_熔断状态清单_全域_v2.0.csv", *t25)
    write_both("T20_L4自动化Tier评估_全域_v3.0.csv", *t20)
    write_both("T26_Agent规划_全域_v2.0.csv", *t26)
    write_both("T24_交付物四标签风险分析_全域_v1.0.csv", *t24)
    write_both("T21_数据对齐审计_全域_v1.0.csv", *t21)
    write_both("T29_L3L2业务能力桥接_全域_v1.0.csv", *t29)
    write_both("T30_岗位组织_全域_v1.0.csv", *t30)

    print("\n[附加] 导出JSON给VNW前端(frontend/public/data/) ...")
    built_tables = {
        "node_index": tables["t1"][1],
        "signals": t2_rows,
        "rules": t5[1],
        "gaps": t7[1],
        "deliverables": t6_rows,
        "role_mapping": tables["t11"][1],
        "gate_ratings": t12_dw[1],
        "domain_progress": t14[1],
        "fused_tasks": t18[1],
        "sop_progress": t19[1],
        "ait_handoff": t23[1],
        "fused_status": t25[1],
        "l4_tier": t20[1],
        "candidate_agents": t26[1],
        "deliverable_risk": t24[1],
        "data_audit": t21[1],
        "l3_l2_bridge": t29[1],
        "org_roles": t30[1],
    }
    exported = export_json_for_frontend(built_tables)
    print(f"  共导出{len(exported)}张表到 {APP_V2_DATA_DIR}")
    print(f"  {exported}")

    print("\n" + "=" * 70)
    print("同步完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
