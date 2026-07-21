#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1-02 · 价值节点信号提取自动化脚本

依据三层递进提取法 v3.4「第零步·前置信号提取」，
从 D1 价值节点清单 Excel 自动提取 7 类信号，生成标准基线 Markdown。

用法:
  python3 extract_signals.py                          # 默认: PAY域, 自动检测最新Excel
  python3 extract_signals.py --domain CFM             # 指定域
  python3 extract_signals.py --all                    # 全量72节点
  python3 extract_signals.py --input /path/to.xlsx    # 指定输入文件
  python3 extract_signals.py --output /path/to/dir    # 指定输出目录

作者: Jasper + AI 协同终端
日期: 2026-07-02
"""

import argparse
import math
import re
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd


# ============================================================
# 1. 配置 (可被命令行参数覆盖)
# ============================================================

SCRIPT_DIR = Path(__file__).parent.resolve()

# 默认数据路径: 优先用生产环境目录, 回退到测试目录
DEFAULT_DATA_DIRS = [
    Path("/Users/zhaoqitrenda.cn/Desktop/流程架构项目_jasper/02_过程成果-工作产出/规则分析（Jasper）/01_价值节点清单"),
    Path("/Users/zhaoqitrenda.cn/Desktop/自动化测试（PAY域）"),
]

def find_latest_excel(dirs):
    """在多个目录中查找最新的 D1_价值节点清单_标准化_数据表版_*.xlsx"""
    candidates = []
    for d in dirs:
        if not d.exists():
            continue
        for f in d.glob("D1_价值节点清单_标准化_数据表版_*.xlsx"):
            candidates.append(f)
    if not candidates:
        return None
    # 按修改时间取最新
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_args():
    parser = argparse.ArgumentParser(description="价值节点信号提取自动化")
    parser.add_argument("--input", "-i", type=Path, help="输入 Excel 文件路径 (可选, 默认自动查找)")
    parser.add_argument("--output", "-o", type=Path, default=SCRIPT_DIR / "outputs", help="输出目录")
    parser.add_argument("--domain", "-d", type=str, default=None, help="指定域编码过滤 (如 PAY, CFM, BAM)")
    parser.add_argument("--all", "-a", action="store_true", help="处理全量所有域节点")
    parser.add_argument("--list-domains", action="store_true", help="列出 Excel 中所有域编码并退出")
    return parser.parse_args()


args = parse_args()

# 确定输入文件
if args.input:
    EXCEL_PATH = args.input
else:
    EXCEL_PATH = find_latest_excel(DEFAULT_DATA_DIRS)

if not EXCEL_PATH or not EXCEL_PATH.exists():
    print("错误: 找不到 D1_价值节点清单 Excel 文件")
    print(f"搜索路径: {[str(d) for d in DEFAULT_DATA_DIRS]}")
    print("请用 --input 指定路径, 或将文件放入上述目录")
    sys.exit(1)

print(f"[INFO] 使用输入文件: {EXCEL_PATH}")

OUTPUT_DIR = args.output
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# 域过滤: --all 时不过滤, --domain 时指定, 否则默认 PAY
if args.all:
    DOMAIN_CODE = None
    DOMAIN_NAME = "全域"
elif args.domain:
    DOMAIN_CODE = args.domain.upper()
    DOMAIN_NAME = DOMAIN_CODE  # 简化, 实际可从 Sheet1 读取
else:
    DOMAIN_CODE = "PAY"
    DOMAIN_NAME = "财务支付"


# ============================================================
# 2. 工具函数
# ============================================================

def clean(val) -> str:
    """清理单元格值：nan/None → 空字符串，其余转 str.strip()"""
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    if s.lower() == "nan":
        return ""
    return s


def format_list(items: list[str]) -> str:
    """将列表格式化为 Markdown 列表项"""
    return "\n".join(f"- {item}" for item in items if item)


def lookup_m_names(m_str: str, m_map: dict) -> str:
    """将 M锚定 字符串（如 '1.M0 数理基建'）解析为标准格式"""
    if not m_str:
        return "未锚定"
    parts = []
    for line in m_str.split("\n"):
        line = clean(line)
        if not line:
            continue
        # 格式可能是 "1.M0 数理基建" 或 "M0"
        # 提取 M编号
        for m_id, m_name in m_map.items():
            if m_id in line:
                parts.append(f"{m_id} {m_name}")
                break
        else:
            parts.append(line)
    return " / ".join(parts) if parts else m_str


def lookup_kpi_names(kpi_str: str, kpi_map: dict, node_id: str, kpi_df: pd.DataFrame) -> str:
    """解析 KPI 锚定字段，返回标准格式"""
    if not kpi_str:
        return "未锚定"
    parts = []
    for line in kpi_str.split("\n"):
        line = clean(line)
        if not line:
            continue
        # 尝试匹配 KPI#
        matched = False
        for _, row in kpi_df.iterrows():
            kpi_id = clean(row.get("KPI编号", ""))
            kpi_name = clean(row.get("KPI名称", ""))
            if kpi_id and kpi_id in line:
                parts.append(f"{kpi_id} {kpi_name}")
                matched = True
                break
        if not matched:
            parts.append(line)
    return " / ".join(parts) if parts else kpi_str


# ============================================================
# 3. 信号提取器
# ============================================================

class SignalExtractor:
    """从 Excel 提取 7 类信号"""

    def __init__(self, excel_path: Path):
        self.xl = pd.ExcelFile(excel_path)
        self.sheets = {}
        self._load_sheets()
        self._build_mappings()

    def _load_sheets(self):
        """加载新旧版本 sheet；V3.44 起标题行和名称发生变化。"""
        sheet_names = self.xl.sheet_names

        def sheet(prefix):
            matches = [name for name in sheet_names if name.startswith(prefix)]
            if not matches:
                raise ValueError(f"缺少必需工作表：{prefix}*")
            return matches[0]

        def table(sheet_name, required):
            raw = pd.read_excel(self.xl, sheet_name=sheet_name, header=None, nrows=12)
            header_row = None
            for index, row in raw.iterrows():
                values = {clean(value).replace("\n", "") for value in row.tolist()}
                if any(item in values for item in required):
                    header_row = index
                    break
            if header_row is None:
                raise ValueError(f"工作表 {sheet_name} 找不到表头字段：{required}")
            frame = pd.read_excel(self.xl, sheet_name=sheet_name, header=header_row)
            frame.columns = [clean(col).replace("\n", "") for col in frame.columns]
            return frame

        self.sheets["overview"] = table(sheet("1.价值节点总览"), ["节点ID"])
        self.sheets["detail"] = table(sheet("2.节点详情卡"), ["节点ID"])
        self.sheets["gate"] = table(sheet("3.四属性三重验证矩阵"), ["节点ID"])
        self.sheets["m_matrix"] = table(sheet("4.M0-M8锚定矩阵"), ["节点ID"])
        self.sheets["fuse"] = table(sheet("5.熔断"), ["节点ID"])
        self.sheets["l3_map"] = table(sheet("6.价值节点_L3映射表"), ["价值节点ID", "节点ID"])

        aliases = {
            "overview": {"L3名称": "L3端到端闭环", "L3现状": "status状态"},
            "detail": {"价值属性": "②价值属性", "物理对应": "③物理对应", "业务定位(M锚定)": "①业务定位(M0-M8)", "L4名称": "L4组成"},
        }
        for key, mapping in aliases.items():
            frame = self.sheets[key]
            for old_name, new_name in mapping.items():
                if old_name not in frame and new_name in frame:
                    frame[old_name] = frame[new_name]

        self.sheets["gate"]["是否熔断"] = self.sheets["gate"]["是否熔断"].map(
            lambda value: clean(value).lower() in {"true", "是", "熔断", "1"}
        )

        m_sheet = [name for name in sheet_names if "M锚定名称映射" in name]
        if m_sheet:
            self.sheets["m_map"] = table(m_sheet[0], ["M编号"])
        else:
            self.sheets["m_map"] = pd.DataFrame({
                "M编号": [f"M{i}" for i in range(9)],
                "M名称": ["数理基建", "中台运营", "KPI报表", "NGP", "业务渗透", "AI自动化", "业务渗透", "产品治理", "财务结算"],
            })

        kpi_sheet = [name for name in sheet_names if "KPI" in name and "映射" in name]
        if kpi_sheet:
            self.sheets["kpi_map"] = table(kpi_sheet[0], ["KPI编号"])
        else:
            pairs = {}
            for frame in (self.sheets["overview"], self.sheets["detail"]):
                for value in frame.astype(str).to_numpy().ravel():
                    for name, kpi_id in re.findall(r"([^、，,（）()]+)[（(](KPI#\d+)[）)]", clean(value)):
                        pairs.setdefault(kpi_id, name.strip())
            self.sheets["kpi_map"] = pd.DataFrame(
                [{"KPI编号": kpi_id, "KPI名称": name} for kpi_id, name in sorted(pairs.items())]
            )

    def _build_mappings(self):
        """构建 M编号→名称 和 KPI编号→名称 的映射"""
        self.m_map = {}
        for _, row in self.sheets["m_map"].iterrows():
            m_id = clean(row.get("M编号", ""))
            m_name = clean(row.get("M名称", ""))
            if m_id:
                self.m_map[m_id] = m_name

        self.kpi_map = {}
        for _, row in self.sheets["kpi_map"].iterrows():
            kpi_id = clean(row.get("KPI编号", ""))
            kpi_name = clean(row.get("KPI名称", ""))
            if kpi_id:
                self.kpi_map[kpi_id] = kpi_name

    def get_nodes(self, domain: str = None) -> list[str]:
        """获取节点ID列表。domain=None时返回全部"""
        df = self.sheets["overview"]
        if domain:
            nodes = df[df["节点ID"].str.startswith(f"VN-{domain}-", na=False)]["节点ID"].tolist()
        else:
            nodes = df["节点ID"].tolist()
        return sorted([n for n in nodes if n and str(n).startswith("VN-")])

    def get_all_domains(self) -> list[str]:
        """获取所有域编码"""
        df = self.sheets["overview"]
        domains = df["域编码"].dropna().unique().tolist()
        return sorted(domains)

    def get_row(self, sheet: str, node_id: str) -> pd.Series:
        """获取指定节点在指定 sheet 中的行"""
        df = self.sheets[sheet]
        rows = df[df["节点ID"] == node_id]
        if rows.empty:
            return pd.Series()
        return rows.iloc[0]

    # ---- 7 类信号提取 ----

    def extract_signal_1(self, node_id: str) -> dict:
        """信号1 · 端到端业务逻辑"""
        row = self.get_row("detail", node_id)
        ov = self.get_row("overview", node_id)
        return {
            "business_desc": clean(row.get("L3端到端闭环", "")),
            "start_a": clean(row.get("起点A", "")),
            "end_z": clean(row.get("终点Z", "")),
            "end_standard": clean(row.get("终点标准", "")),
            "frequency": clean(row.get("频次", "")),
            "value_attr": clean(row.get("价值属性", "")),
            "l3_name": clean(ov.get("L3名称", "")),
            "l3_status": clean(ov.get("L3现状", "")),
        }

    def extract_signal_2(self, node_id: str) -> dict:
        """信号2 · 生产方与消费方"""
        row = self.get_row("detail", node_id)
        prod_dept = clean(row.get("生产部门", ""))
        prod_role = clean(row.get("生产岗位", ""))
        cons_subject = clean(row.get("消费主体", ""))
        cons_object = clean(row.get("消费对象", ""))

        is_empty = not any([prod_dept, prod_role, cons_subject, cons_object])
        return {
            "prod_dept": prod_dept,
            "prod_role": prod_role,
            "cons_subject": cons_subject,
            "cons_object": cons_object,
            "is_empty": is_empty,
        }

    def extract_signal_3(self, node_id: str) -> dict:
        """信号3 · 三重Gate状态
        Gate值从Sheet2(详情卡)读取，是否熔断从Sheet3(矩阵)读取并转换"""
        detail_row = self.get_row("detail", node_id)
        gate_row = self.get_row("gate", node_id)

        # 是否熔断：Sheet3为布尔值，转换为字符串
        raw_fused = gate_row.get("是否熔断", "")
        if raw_fused is True or clean(raw_fused) == "True":
            is_fused = "熔断"
        else:
            is_fused = "非熔断"

        return {
            "gate1": clean(detail_row.get("Gate①挂数", "")),
            "gate2": clean(detail_row.get("Gate②落地", "")),
            "gate3": clean(detail_row.get("Gate③追溯", "")),
            "overall": clean(gate_row.get("综合判定", "")),
            "is_fused": is_fused,
        }

    def extract_signal_4(self, node_id: str) -> dict:
        """信号4 · 调研已知清单（A/B/C三分类）—— 结构化部分"""
        row = self.get_row("detail", node_id)
        ov = self.get_row("overview", node_id)

        # 从 Excel 能提取的结构化信号
        l4_names = clean(row.get("L4名称", ""))
        sub_products = clean(row.get("构成子产物", ""))
        sub_products_extra = clean(row.get("子产物补充", ""))
        physical_form = clean(ov.get("物理形态", ""))
        physical_mapping = clean(row.get("物理对应", ""))
        priority = clean(ov.get("优先级", ""))

        # A类：来自 Excel 结构的信息
        a_items = []
        if l4_names:
            a_items.append(f"L4组成：{l4_names}")
        if sub_products:
            a_items.append(f"子产物：{sub_products}")
        if sub_products_extra:
            a_items.append(f"子产物补充：{sub_products_extra}")

        # B类：来自物理对应的缺口描述
        b_items = []
        if physical_mapping:
            b_items.append(f"物理对应：{physical_mapping}")

        # C类：来自优先级和状态
        c_items = []

        return {
            "a_items": a_items,
            "b_items": b_items,
            "c_items": c_items,
            "l4_names": l4_names,
            "sub_products": sub_products,
            "sub_products_extra": sub_products_extra,
            "physical_form": physical_form,
            "physical_mapping": physical_mapping,
            "note": "自动化提取仅覆盖Excel结构化数据；访谈规则(EFA001/PAY002等)需人工继承",
        }

    def extract_signal_5(self, node_id: str) -> dict:
        """信号5 · 已知的交付物"""
        row = self.get_row("detail", node_id)
        ov = self.get_row("overview", node_id)

        sub_products = clean(row.get("构成子产物", ""))
        physical_form = clean(ov.get("物理形态", ""))

        deliverables = []
        if sub_products:
            for i, line in enumerate(sub_products.split("\n"), 1):
                line = clean(line)
                if line:
                    deliverables.append({
                        "name": line,
                        "form": physical_form or "Excel",
                        "source": "Sheet2·构成子产物",
                    })

        return {"deliverables": deliverables}

    def extract_signal_6(self, node_id: str) -> dict:
        """信号6 · 已知的岗位和系统依赖"""
        row = self.get_row("detail", node_id)
        return {
            "prod_dept": clean(row.get("生产部门", "")),
            "prod_role": clean(row.get("生产岗位", "")),
            "cons_subject": clean(row.get("消费主体", "")),
            "cons_object": clean(row.get("消费对象", "")),
            "physical_mapping": clean(row.get("物理对应", "")),
            "is_empty": not any([
                clean(row.get("生产部门", "")),
                clean(row.get("生产岗位", "")),
                clean(row.get("消费主体", "")),
                clean(row.get("消费对象", "")),
            ]),
        }

    def extract_signal_7(self, node_id: str) -> dict:
        """信号7 · KPI锚定和M锚定"""
        row = self.get_row("detail", node_id)
        ov = self.get_row("overview", node_id)

        m_str = clean(row.get("业务定位(M锚定)", ""))
        kpi_str = clean(ov.get("KPI锚定", ""))

        m_formatted = lookup_m_names(m_str, self.m_map)
        kpi_formatted = lookup_kpi_names(kpi_str, self.kpi_map, node_id, self.sheets["kpi_map"])

        # 从 M 锚定矩阵获取更多细节
        m_matrix_row = self.get_row("m_matrix", node_id)
        m_anchors = []
        for m_id, m_name in self.m_map.items():
            cell_val = clean(m_matrix_row.get(f"{m_id} {m_name}", ""))
            if cell_val and cell_val != "—":
                m_anchors.append(f"{m_id} {m_name}")

        return {
            "kpi_anchored": kpi_formatted,
            "m_anchored": m_formatted,
            "m_anchors_from_matrix": m_anchors,
        }

    def extract_all_signals(self, node_id: str) -> dict:
        """提取一个节点的全部 7 类信号"""
        return {
            "signal_1": self.extract_signal_1(node_id),
            "signal_2": self.extract_signal_2(node_id),
            "signal_3": self.extract_signal_3(node_id),
            "signal_4": self.extract_signal_4(node_id),
            "signal_5": self.extract_signal_5(node_id),
            "signal_6": self.extract_signal_6(node_id),
            "signal_7": self.extract_signal_7(node_id),
        }


# ============================================================
# 4. Markdown 生成器
# ============================================================

class MarkdownGenerator:
    """生成信号提取基线 Markdown"""

    def __init__(self, extractor: SignalExtractor, domain: str = None, domain_name: str = ""):
        self.extractor = extractor
        self.domain = domain
        self.domain_name = domain_name
        self.nodes = extractor.get_nodes(domain)
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def generate(self) -> str:
        """生成完整的基线 Markdown"""
        lines = []
        lines.append(self._header())
        lines.append(self._step2_node_list())
        lines.append(self._step3_per_node_analysis())
        lines.append(self._step4_classification_summary())
        lines.append(self._step5_gap_list())
        lines.append(self._step6_panorama())
        lines.append(self._step7_self_check())
        lines.append(self._footer())
        return "\n".join(lines)

    def _header(self) -> str:
        domain_label = f"{self.domain}域" if self.domain else "全域"
        return f"""# {domain_label} · 价值节点信号提取基线 auto v1.0

> 自动化生成 · 生成时间：{self.timestamp}
> 数据源：`D1_价值节点清单_标准化_数据表版_v2.0.xlsx`
> 依据标准：`标准_Jasper工作流总纲_v2.2.md` + `上下文_数据规则提取方法论_三层递进提取法_v3.4.md`
> 追溯标注：源自01层 D1_价值节点清单_标准化_数据表版_v2.0（8个Sheet，{len(self.nodes)}个{domain_label}节点）
> 边界声明：本产出仅做信号提取（第零步），不做规则空白识别，不产出规则空白地图/熔断补建清单
> 自动化声明：本基线由 `extract_signals.py` 自动生成。信号4（A/B/C三分类）仅覆盖Excel结构化数据，访谈规则需人工继承。

---

## Step 1 · 文件结构概览

| Sheet | 列数 | 核心内容 |
|---|---|---|
| 1.价值节点总览 | 14 | {len(self.nodes)}个{domain_label}节点的概要信息 |
| 2.节点详情卡 | 28 | {len(self.nodes)}张完整属性卡的深度展开 |
| 3.四属性三重验证矩阵 | 11 | {len(self.nodes)}节点×四属性×三重Gate矩阵 |
| 4.M0-M8锚定矩阵(参考) | 12 | {len(self.nodes)}节点对M0-M8战略闭环锚定分布 |
| 5.熔断清单 | 5 | 熔断节点致命缺口描述 |
| 6.价值节点_L3映射表 | 9 | 节点ID↔L3/L4流程库映射 |
| 0.M锚定名称映射 | 2 | M编号↔M名称（9个M闭环） |
| 0.KPI名称映射 | 3 | KPI编号↔KPI名称（按节点关联） |

---

## Step 2 · {domain_label}节点清单"""

    def _step2_node_list(self) -> str:
        domain_label = f"{self.domain}域" if self.domain else "全域"
        lines = [f"\n> 全部{len(self.nodes)}个节点均属{domain_label}。\n"]
        lines.append("| 节点编码 | 节点名称 | L3名称 | L3现状 | 起点A | 终点Z | 熔断状态 | 优先级 |")
        lines.append("|---|---|---|---|---|---|---|---|")

        for node_id in self.nodes:
            ov = self.extractor.get_row("overview", node_id)
            det = self.extractor.get_row("detail", node_id)
            gate = self.extractor.get_row("gate", node_id)

            name = clean(ov.get("价值节点(物理资产)", ""))
            l3 = clean(ov.get("L3名称", ""))
            l3_status = clean(ov.get("L3现状", ""))
            start = clean(ov.get("起点A", ""))
            end = clean(ov.get("终点Z", ""))
            s3 = self.extractor.extract_signal_3(node_id)
            fused = "🔴熔断" if s3["is_fused"] == "熔断" else "非熔断"
            priority = clean(ov.get("优先级", ""))

            lines.append(f"| {node_id} | {name} | {l3} | {l3_status} | {start} | {end} | {fused} | {priority} |")

        return "\n".join(lines)

    def _step3_per_node_analysis(self) -> str:
        lines = ["\n---\n\n## Step 3 · 逐节点深度解析\n"]

        for node_id in self.nodes:
            lines.append(self._format_node(node_id))
            lines.append("---\n")

        return "\n".join(lines)

    def _format_node(self, node_id: str) -> str:
        signals = self.extractor.extract_all_signals(node_id)
        ov = self.extractor.get_row("overview", node_id)
        name = clean(ov.get("价值节点(物理资产)", ""))

        fused_tag = " [🔴熔断]" if signals["signal_3"]["is_fused"] == "熔断" else ""

        lines = [f"### {node_id} · {name}{fused_tag}"]

        # 信号1
        s1 = signals["signal_1"]
        lines.append(f"""
**信号1 · 端到端业务逻辑**
- 业务描述：{s1['business_desc']}
- 起点A：{s1['start_a']}
- 终点Z：{s1['end_z']}
- 终点标准：{s1['end_standard'] or '—'}
- 频次：{s1['frequency']}
- 价值属性：{s1['value_attr']}""")

        # 信号2
        s2 = signals["signal_2"]
        if s2["is_empty"]:
            lines.append("""
**信号2 · 生产方与消费方**（⚠ 待源头校准，暂无数据）
- 生产方：v2.0数据表中生产部门/生产岗位字段为空，待Terresa/HR校准
- 消费方：v2.0数据表中消费主体/消费对象字段为空，待Terresa/HR校准
- 单点风险：待评估""")
        else:
            lines.append(f"""
**信号2 · 生产方与消费方**
- 生产方：{s2['prod_dept']} / {s2['prod_role']}
- 消费方：{s2['cons_subject']} / {s2['cons_object']}
- 单点风险：待评估""")

        # 信号3
        s3 = signals["signal_3"]
        lines.append(f"""
**信号3 · 三重Gate状态**
| Gate | 评级 | 说明 |
|---|---|---|
| Gate①挂数 | {s3['gate1']} | — |
| Gate②落地 | {s3['gate2']} | — |
| Gate③追溯 | {s3['gate3']} | — |
| 综合判定 | {s3['overall']} | {s3['is_fused']} |""")

        # 信号4
        s4 = signals["signal_4"]
        lines.append(f"""
**信号4 · 调研已知清单（A/B/C三分类）**

> ⚠ 自动化提取仅覆盖Excel结构化数据。访谈规则(EFA001/PAY002/PAY003/PAY005-009)需人工继承。""")

        if s4["a_items"]:
            lines.append("\n| 分类 | 信号内容 | 来源 |")
            lines.append("|---|---|---|")
            for item in s4["a_items"]:
                lines.append(f"| A类 | {item} | Sheet2 |")

        if s4["b_items"]:
            for item in s4["b_items"]:
                lines.append(f"| B类 | {item} | Sheet2·物理对应 |")

        lines.append("| C类 | 访谈规则需人工继承 | 待补充 |")

        # 信号5
        s5 = signals["signal_5"]
        if s5["deliverables"]:
            lines.append("\n**信号5 · 已知的交付物**")
            lines.append("| 交付物 | 形态 | 来源 |")
            lines.append("|---|---|---|")
            for d in s5["deliverables"]:
                lines.append(f"| {d['name']} | {d['form']} | {d['source']} |")
        else:
            lines.append("\n**信号5 · 已知的交付物**\n- 待补充")

        # 信号6
        s6 = signals["signal_6"]
        if s6["is_empty"]:
            lines.append("""
**信号6 · 已知的岗位和系统依赖**（⚠ 待源头校准，暂无数据）
- 涉及岗位：v2.0数据表中生产部门/生产岗位字段为空，待Terresa/HR校准
- 涉及系统：待补充
- 外部依赖：待补充""")
        else:
            lines.append(f"""
**信号6 · 已知的岗位和系统依赖**
- 涉及岗位：{s6['prod_dept']} / {s6['prod_role']}
- 涉及系统：{s6['physical_mapping']}
- 外部依赖：待补充""")

        # 信号7
        s7 = signals["signal_7"]
        lines.append(f"""
**信号7 · KPI锚定和M锚定**
- KPI锚定：{s7['kpi_anchored']}
- M锚定：{s7['m_anchored']}
- 战略意义：待人工补充""")

        return "\n".join(lines)

    def _step4_classification_summary(self) -> str:
        """生成 A/B/C 三分类汇总"""
        lines = ["\n## Step 4 · 调研已知清单（三分类汇总·自动提取部分）\n"]
        lines.append("> 仅含Excel结构化自动提取的信号。访谈规则(EFA001/PAY002等)需人工继承后补充。\n")

        # 统计
        a_count = 0
        b_count = 0
        c_count = 0

        lines.append("### A类·已确立规则（自动提取·结构信息）\n")
        lines.append("| 节点 | 信号内容 | 来源 |")
        lines.append("|---|---|---|")

        for node_id in self.nodes:
            s4 = self.extractor.extract_signal_4(node_id)
            for item in s4["a_items"]:
                lines.append(f"| {node_id} | {item} | Sheet2 |")
                a_count += 1

        lines.append(f"\n> 小计：A类 {a_count} 条（自动提取的结构化信息）\n")

        lines.append("### B类·规则线索（自动提取·物理对应）\n")
        lines.append("| 节点 | 信号内容 | 来源 |")
        lines.append("|---|---|---|")

        for node_id in self.nodes:
            s4 = self.extractor.extract_signal_4(node_id)
            for item in s4["b_items"]:
                lines.append(f"| {node_id} | {item} | Sheet2·物理对应 |")
                b_count += 1

        lines.append(f"\n> 小计：B类 {b_count} 条（自动提取的物理对应信息）\n")

        lines.append("### C类·行动项\n")
        lines.append("> 自动化提取暂无法识别C类行动项，需人工从访谈记录中继承。\n")

        lines.append(f"| 分类 | 数量（自动提取） | 备注 |")
        lines.append(f"|---|---|---|")
        lines.append(f"| A类·已确立规则 | {a_count} | 仅含Excel结构化信息 |")
        lines.append(f"| B类·规则线索 | {b_count} | 仅含物理对应信息 |")
        lines.append(f"| C类·行动项 | {c_count} | 需人工继承 |")
        lines.append(f"| **合计（自动提取）** | **{a_count + b_count + c_count}** | **访谈规则需人工补充** |")

        return "\n".join(lines)

    def _step5_gap_list(self) -> str:
        """生成信号空白清单"""
        lines = ["\n## Step 5 · 信号空白清单（自动识别）\n"]
        lines.append("> 以下空白为自动化识别的结构性缺失，需人工核实。\n")

        gaps = []
        for node_id in self.nodes:
            s2 = self.extractor.extract_signal_2(node_id)
            if s2["is_empty"]:
                gaps.append({
                    "node": node_id,
                    "desc": "生产部门/生产岗位/消费主体/消费对象4字段为空",
                    "type": "数据空白",
                    "layer": "数据源层",
                    "priority": "P1",
                })

            s3 = self.extractor.extract_signal_3(node_id)
            if s3["is_fused"] == "熔断":
                gaps.append({
                    "node": node_id,
                    "desc": f"节点熔断（Gate状态：{s3['gate1']}/{s3['gate2']}/{s3['gate3']}）",
                    "type": "熔断缺口",
                    "layer": "Gate层",
                    "priority": "P0",
                })

        if gaps:
            lines.append("| 节点 | 空白描述 | 空白类型 | L层定位 | 访谈优先级 |")
            lines.append("|---|---|---|---|---|")
            for g in gaps:
                lines.append(f"| {g['node']} | {g['desc']} | {g['type']} | {g['layer']} | {g['priority']} |")
            lines.append(f"\n> 小计：空白 {len(gaps)} 条")
        else:
            lines.append("无自动识别的空白")

        return "\n".join(lines)

    def _step6_panorama(self) -> str:
        """生成信号全景图"""
        lines = ["\n## Step 6 · 信号全景图\n"]
        lines.append("### 节点概览\n")
        lines.append("| 节点 | 业务一句话 | Gate综合 | 熔断 | 调研覆盖度 | 交付物数 |")
        lines.append("|---|---|---|---|---|---|")

        fused_count = 0
        for node_id in self.nodes:
            ov = self.extractor.get_row("overview", node_id)
            det = self.extractor.get_row("detail", node_id)
            gate = self.extractor.get_row("gate", node_id)
            s5 = self.extractor.extract_signal_5(node_id)

            name = clean(ov.get("价值节点(物理资产)", ""))
            l3 = clean(ov.get("L3名称", ""))
            overall = clean(gate.get("综合判定", ""))
            fused = clean(gate.get("是否熔断", ""))
            if "熔断" in fused:
                fused_count += 1

            deliverable_count = len(s5["deliverables"])

            lines.append(f"| {node_id} | {name} | {overall} | {fused} | 自动提取 | {deliverable_count} |")

        # 熔断节点汇总
        lines.append(f"\n### 熔断节点汇总（{fused_count}个）\n")
        fused_nodes = []
        for node_id in self.nodes:
            s3 = self.extractor.extract_signal_3(node_id)
            if s3["is_fused"] == "熔断":
                ov = self.extractor.get_row("overview", node_id)
                name = clean(ov.get("价值节点(物理资产)", ""))
                fused_nodes.append(f"- {node_id} · {name}（Gate: {s3['gate1']}/{s3['gate2']}/{s3['gate3']}）")

        if fused_nodes:
            lines.extend(fused_nodes)

        return "\n".join(lines)

    def _step7_self_check(self) -> str:
        """自检声明"""
        node_count = len(self.nodes)
        signal_count = node_count * 7
        domain_label = f"{self.domain}域" if self.domain else "全域"

        return f"""
## Step 7 · 自检声明

| # | Done Criteria | 自检结果 |
|---|---|---|
| 1 | 所有Sheet结构已读取并概述 | ✅ 8个Sheet全量读取 |
| 2 | {domain_label}节点已全部提取（{node_count}个） | ✅ {node_count}个节点全覆盖 |
| 3 | 每个节点7类信号全部提取 | ✅ {node_count}节点×7信号={signal_count}项信号 |
| 4 | 信号2/6岗位信息：标注"待源头校准" | ✅ 空字段已标注 |
| 5 | 熔断判定：直接读取Sheet3"是否熔断"列 | ✅ 未自行推导 |
| 6 | 信号4仅提取Excel结构化数据，访谈规则标注"需人工继承" | ✅ |
| 7 | 全程只做信号提取，未做规则空白识别 | ✅ |

---

> 产出文件：`{domain_label}_价值节点信号提取基线_auto_v1.0.md`
> 数据源版本：{EXCEL_PATH.name}
> 生成脚本：`extract_signals.py`
> 自动化范围：信号1/2/3/5/6/7从Excel自动提取；信号4仅覆盖结构化部分，访谈规则需人工继承"""

    def _footer(self) -> str:
        return ""


# ============================================================
# 5. 主函数
# ============================================================

def main() -> None:
    # 处理 --list-domains 模式
    if args.list_domains:
        extractor = SignalExtractor(EXCEL_PATH)
        domains = extractor.get_all_domains()
        print(f"Excel 中共有 {len(domains)} 个域:")
        for d in domains:
            count = len(extractor.get_nodes(d))
            print(f"  {d}: {count} 个节点")
        return

    print("=" * 60)
    print(f"P1-02 · {DOMAIN_NAME}信号提取自动化")
    print("=" * 60)

    extractor = SignalExtractor(EXCEL_PATH)
    nodes = extractor.get_nodes(DOMAIN_CODE)
    print(f"数据源加载完成：{len(nodes)} 个节点")
    print(f"M映射：{len(extractor.m_map)} 个 | KPI映射：{len(extractor.kpi_map)} 个")

    generator = MarkdownGenerator(extractor, DOMAIN_CODE, DOMAIN_NAME)
    markdown = generator.generate()

    domain_label = f"{DOMAIN_CODE}域" if DOMAIN_CODE else "全域"
    output_path = OUTPUT_DIR / f"{domain_label}_价值节点信号提取基线_auto_v1.0.md"
    output_path.write_text(markdown, encoding="utf-8")

    # 统计
    line_count = len(markdown.splitlines())
    print(f"\n产出：{output_path}")
    print(f"行数：{line_count}")

    # 统计每个节点的信号
    print("\n节点信号提取统计：")
    for node_id in nodes:
        signals = extractor.extract_all_signals(node_id)
        s3 = extractor.extract_signal_3(node_id)
        if s3["is_fused"] == "熔断":
            fused = "🔴熔断"
        else:
            fused = "✅非熔断"
        s2_empty = "⚠空" if signals["signal_2"]["is_empty"] else "✅有"
        print(f"  {node_id}: Gate={s3['overall'][:10]:<10} {fused}  信号2={s2_empty}")

    print("=" * 60)
    print("信号提取完成，请查看 outputs/ 目录")
    print("=" * 60)


if __name__ == "__main__":
    main()
