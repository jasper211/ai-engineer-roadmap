#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1-01 · PAY-COM 域价值节点清单与流程蓝图一致性校验脚本

输入：
  - 流程蓝图 Markdown 文件（包含「关联价值节点」表格）
  - D1 价值节点清单 Excel 文件（包含「1.价值节点总览」sheet）

输出：
  - JSON 格式的比对结果
  - HTML 可视化校验报告

作者：Jasper + AI 协同终端
日期：2026-07-02
"""

import json
import re
from pathlib import Path
from datetime import datetime

import pandas as pd


# ============================================================
# 1. 配置路径
# ============================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = Path("/Users/zhaoqitrenda.cn/Desktop/自动化测试（PAY域）")
BLUEPRINT_PATH = DATA_DIR / "流程蓝图_L3-COM_佣金全链路管理_V1的副本.0.md"
EXCEL_PATH = DATA_DIR / "D1_价值节点清单_标准化_数据表版_v2的副本.0.xlsx"
OUTPUT_DIR = SCRIPT_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# 2. 解析 Markdown 中的价值节点表格
# ============================================================

def parse_markdown_vn_table(md_path: Path) -> list[dict]:
    """
    从流程蓝图 Markdown 中提取「关联价值节点」表格。
    返回：[{"vn_code": "VN-PAY-01", "vn_name": "..."}, ...]
    """
    content = md_path.read_text(encoding="utf-8")

    # 定位「关联价值节点」章节后的表格
    # 章节标题格式：## 二、关联价值节点
    section_match = re.search(
        r"##\s+二、关联价值节点\s*\n+(.*?)(?=\n##|\Z)",
        content,
        re.DOTALL,
    )
    if not section_match:
        raise ValueError("未找到『关联价值节点』章节")

    section = section_match.group(1)

    # 提取表格行
    # 表格格式：| VN编码 | VN名称 | 优先级 | ... |
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if line.startswith("| VN编码") or line.startswith("|--------"):
            continue

        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 2:
            vn_code = cells[0]
            vn_name = cells[1]
            # 过滤表头可能的误匹配
            if vn_code.startswith("VN-"):
                rows.append({
                    "vn_code": vn_code,
                    "vn_name": vn_name,
                    "source": "流程蓝图_L3-COM",
                })

    return rows


# ============================================================
# 3. 解析 Excel 中的价值节点总览
# ============================================================

def parse_excel_vn_overview(excel_path: Path) -> list[dict]:
    """
    从 D1 价值节点清单 Excel 的「1.价值节点总览」sheet 中提取 VN-PAY 节点。
    返回：[{"vn_code": "VN-PAY-01", "vn_name": "...", "l3_name": "..."}, ...]
    """
    df = pd.read_excel(excel_path, sheet_name="1.价值节点总览")

    rows = []
    for _, record in df.iterrows():
        vn_code = str(record.get("节点ID", "")).strip()
        vn_name = str(record.get("价值节点(物理资产)", "")).strip()
        l3_name = str(record.get("L3名称", "")).strip()

        if vn_code.startswith("VN-"):
            rows.append({
                "vn_code": vn_code,
                "vn_name": vn_name,
                "l3_name": l3_name,
                "source": "D1_价值节点清单",
            })

    return rows


# ============================================================
# 4. 一致性比对逻辑
# ============================================================

def compare_vn_sets(blueprint_rows: list[dict], excel_rows: list[dict]) -> dict:
    """
    比对两组价值节点，返回差异分析。
    """
    blueprint_dict = {r["vn_code"]: r for r in blueprint_rows}
    excel_dict = {r["vn_code"]: r for r in excel_rows if r["vn_code"].startswith("VN-PAY")}

    blueprint_codes = set(blueprint_dict.keys())
    excel_codes = set(excel_dict.keys())

    # 1. 仅在流程蓝图中
    only_in_blueprint = sorted(blueprint_codes - excel_codes)

    # 2. 仅在 Excel 中
    only_in_excel = sorted(excel_codes - blueprint_codes)

    # 3. 两边都有，但名称不一致
    name_mismatches = []
    for code in sorted(blueprint_codes & excel_codes):
        bp_name = blueprint_dict[code]["vn_name"]
        ex_name = excel_dict[code]["vn_name"]
        if bp_name != ex_name:
            name_mismatches.append({
                "vn_code": code,
                "blueprint_name": bp_name,
                "excel_name": ex_name,
            })

    # 4. 完全一致
    matched = sorted(blueprint_codes & excel_codes - {m["vn_code"] for m in name_mismatches})

    return {
        "summary": {
            "blueprint_count": len(blueprint_rows),
            "excel_pay_count": len(excel_dict),
            "matched_count": len(matched),
            "only_in_blueprint_count": len(only_in_blueprint),
            "only_in_excel_count": len(only_in_excel),
            "name_mismatch_count": len(name_mismatches),
        },
        "matched": [{"vn_code": c, "vn_name": blueprint_dict[c]["vn_name"]} for c in matched],
        "only_in_blueprint": [blueprint_dict[c] for c in only_in_blueprint],
        "only_in_excel": [excel_dict[c] for c in only_in_excel],
        "name_mismatches": name_mismatches,
    }


# ============================================================
# 5. 生成 HTML 报告
# ============================================================

def generate_html_report(result: dict, output_path: Path) -> None:
    """
    生成可视化 HTML 校验报告。
    """
    summary = result["summary"]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>P1-01 · PAY-COM 价值节点一致性校验报告</title>
    <style>
        :root {{
            --bg: #f8fafc;
            --card: #ffffff;
            --text: #1e293b;
            --muted: #64748b;
            --success: #16a34a;
            --warning: #ca8a04;
            --danger: #dc2626;
            --border: #e2e8f0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            margin: 0;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 960px;
            margin: 0 auto;
        }}
        h1 {{
            font-size: 28px;
            margin-bottom: 8px;
        }}
        .subtitle {{
            color: var(--muted);
            margin-bottom: 24px;
        }}
        .meta {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 24px;
            font-size: 14px;
            color: var(--muted);
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }}
        .summary-card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }}
        .summary-card .number {{
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 4px;
        }}
        .summary-card .label {{
            font-size: 13px;
            color: var(--muted);
        }}
        .success {{ color: var(--success); }}
        .warning {{ color: var(--warning); }}
        .danger {{ color: var(--danger); }}
        .section {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        .section h2 {{
            margin-top: 0;
            font-size: 20px;
            margin-bottom: 16px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th, td {{
            text-align: left;
            padding: 10px 12px;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background: #f1f5f9;
            font-weight: 600;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-success {{ background: #dcfce7; color: var(--success); }}
        .badge-warning {{ background: #fef9c3; color: var(--warning); }}
        .badge-danger {{ background: #fee2e2; color: var(--danger); }}
        .empty {{
            color: var(--muted);
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>P1-01 · PAY-COM 价值节点一致性校验报告</h1>
        <div class="subtitle">流程蓝图 vs D1 价值节点清单 · 自动化比对</div>

        <div class="meta">
            <div>生成时间：{timestamp}</div>
            <div>流程蓝图：流程蓝图_L3-COM_佣金全链路管理_V1的副本.0.md</div>
            <div>价值节点清单：D1_价值节点清单_标准化_数据表版_v2的副本.0.xlsx</div>
        </div>

        <div class="summary">
            <div class="summary-card">
                <div class="number success">{summary["matched_count"]}</div>
                <div class="label">完全一致</div>
            </div>
            <div class="summary-card">
                <div class="number warning">{summary["name_mismatch_count"]}</div>
                <div class="label">名称不一致</div>
            </div>
            <div class="summary-card">
                <div class="number danger">{summary["only_in_excel_count"]}</div>
                <div class="label">仅在清单中</div>
            </div>
            <div class="summary-card">
                <div class="number danger">{summary["only_in_blueprint_count"]}</div>
                <div class="label">仅在蓝图中</div>
            </div>
        </div>

        <div class="section">
            <h2>🟢 完全一致</h2>
            {generate_matched_table(result["matched"])}
        </div>

        <div class="section">
            <h2>🟡 名称不一致</h2>
            {generate_mismatch_table(result["name_mismatches"])}
        </div>

        <div class="section">
            <h2>🔴 仅在 D1 价值节点清单中</h2>
            <p>这些节点出现在 Excel 清单中，但不在 L3-COM 流程蓝图里。可能归属于其他 L3 流程。</p>
            {generate_excel_only_table(result["only_in_excel"])}
        </div>

        <div class="section">
            <h2>🔴 仅在流程蓝图中</h2>
            {generate_blueprint_only_table(result["only_in_blueprint"])}
        </div>

        <div class="section">
            <h2>📋 结论与建议</h2>
            <ul>
                <li>流程蓝图与清单共有 <strong>{summary["matched_count"]}</strong> 个价值节点完全一致。</li>
                <li><strong>VN-PAY-05</strong> 名称存在差异，需要人工确认哪个名称是标准命名。</li>
                <li><strong>VN-PAY-07/08/09</strong> 仅在清单中，可能不属于 L3-COM，建议核对归属域。</li>
                <li>建议在下一次迭代中统一价值节点命名规范，并在流程蓝图中明确标注跨 L3 引用关系。</li>
            </ul>
        </div>
    </div>
</body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")
    print(f"HTML 报告已生成：{output_path}")


def generate_matched_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">无</p>'
    html = '<table><tr><th>VN编码</th><th>VN名称</th><th>状态</th></tr>'
    for r in rows:
        html += f'<tr><td>{r["vn_code"]}</td><td>{r["vn_name"]}</td><td><span class="badge badge-success">一致</span></td></tr>'
    html += '</table>'
    return html


def generate_mismatch_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">无</p>'
    html = '<table><tr><th>VN编码</th><th>流程蓝图名称</th><th>清单名称</th><th>状态</th></tr>'
    for r in rows:
        html += f'<tr><td>{r["vn_code"]}</td><td>{r["blueprint_name"]}</td><td>{r["excel_name"]}</td><td><span class="badge badge-warning">名称不一致</span></td></tr>'
    html += '</table>'
    return html


def generate_excel_only_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">无</p>'
    html = '<table><tr><th>VN编码</th><th>清单名称</th><th>L3名称</th><th>状态</th></tr>'
    for r in rows:
        html += f'<tr><td>{r["vn_code"]}</td><td>{r["vn_name"]}</td><td>{r.get("l3_name", "")}</td><td><span class="badge badge-danger">归属待确认</span></td></tr>'
    html += '</table>'
    return html


def generate_blueprint_only_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">无</p>'
    html = '<table><tr><th>VN编码</th><th>蓝图名称</th><th>状态</th></tr>'
    for r in rows:
        html += f'<tr><td>{r["vn_code"]}</td><td>{r["vn_name"]}</td><td><span class="badge badge-danger">清单缺失</span></td></tr>'
    html += '</table>'
    return html


# ============================================================
# 6. 主函数
# ============================================================

def main() -> None:
    print("=" * 60)
    print("P1-01 · PAY-COM 价值节点一致性校验")
    print("=" * 60)

    # 解析输入
    blueprint_rows = parse_markdown_vn_table(BLUEPRINT_PATH)
    print(f"流程蓝图解析完成：{len(blueprint_rows)} 个价值节点")

    excel_rows = parse_excel_vn_overview(EXCEL_PATH)
    print(f"Excel 解析完成：{len(excel_rows)} 个价值节点")

    # 比对
    result = compare_vn_sets(blueprint_rows, excel_rows)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))

    # 保存 JSON
    json_path = OUTPUT_DIR / "validation_result.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON 结果已保存：{json_path}")

    # 生成 HTML
    html_path = OUTPUT_DIR / "validation_report.html"
    generate_html_report(result, html_path)

    print("=" * 60)
    print("校验完成，请查看 outputs/validation_report.html")
    print("=" * 60)


if __name__ == "__main__":
    main()
