#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1-01 补充验证 · 全量5份蓝图价值节点一致性校验

修正原P1-01只读取L3-COM单份蓝图的缺陷，
现在读取PAY域全部5份蓝图：
  - L3-COM 佣金全链路管理
  - L3-BAM 银行账户基础设施管理
  - L3-CFM 现金流规划与资金调度管理
  - L3-SSVA 服务结算与价值核算
  - L3-STLM 结算服务执行

与D1价值节点清单Excel进行全量比对。
"""

import json
import re
from pathlib import Path
from datetime import datetime

import pandas as pd


# ============================================================
# 1. 配置路径（生产环境只读）
# ============================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
L3_DIR = Path("/Users/zhaoqitrenda.cn/Desktop/流程架构项目_jasper/02_过程成果-工作产出/L3流程库")
EXCEL_PATH = Path("/Users/zhaoqitrenda.cn/Desktop/流程架构项目_jasper/02_过程成果-工作产出/规则分析（Jasper）/01_价值节点清单/D1_价值节点清单_标准化_数据表版_v2.0.xlsx")
OUTPUT_DIR = SCRIPT_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

BLUEPRINTS = [
    ("COM", L3_DIR / "流程蓝图_L3-COM_佣金全链路管理_V1.0.md"),
    ("BAM", L3_DIR / "流程蓝图_L3-BAM_银行账户基础设施管理_V1.0.md"),
    ("CFM", L3_DIR / "流程蓝图_L3-CFM_现金流规划与资金调度管理_V1.0.md"),
    ("SSVA", L3_DIR / "流程蓝图_L3-SSVA_服务结算与价值核算_V1.0.md"),
    ("STLM", L3_DIR / "流程蓝图_L3-STLM_结算服务执行_V1.0.md"),
]


# ============================================================
# 2. 解析 Markdown 中的价值节点表格
# ============================================================

def parse_markdown_vn_table(md_path: Path) -> list[dict]:
    """从流程蓝图 Markdown 中提取「关联价值节点」表格"""
    content = md_path.read_text(encoding="utf-8")

    # 定位「关联价值节点」章节后的表格
    # 支持多种表头格式：| 价值节点编码 | 价值节点名称 | 或 | VN编码 | VN名称 |
    pattern = r'## 二、关联价值节点\s*\n\s*\n\|\s*(?:价值节点编码|VN编码)\s*\|\s*(?:价值节点名称|VN名称)\s*\|.*?\n\|[-\| ]+\|\s*\n((?:\| VN-.*?\n)+)'
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return []

    rows = []
    for line in match.group(1).strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 2:
            rows.append({"vn_code": parts[0], "vn_name": parts[1]})

    return rows


def parse_all_blueprints() -> dict:
    """读取全部5份蓝图，返回 {blueprint_name: [vn_nodes]}"""
    result = {}
    for name, path in BLUEPRINTS:
        if not path.exists():
            print(f"⚠ 蓝图不存在: {path}")
            result[name] = []
            continue
        nodes = parse_markdown_vn_table(path)
        result[name] = nodes
        print(f"  {name}: {len(nodes)} 个价值节点")
    return result


# ============================================================
# 3. 读取 Excel 中的价值节点
# ============================================================

def load_excel_nodes() -> list[dict]:
    """从 D1 Excel 读取全部价值节点（PAY域）"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="1.价值节点总览")
    pay_nodes = df[df["节点ID"].str.startswith("VN-PAY-", na=False)]
    return [{"vn_code": row["节点ID"], "vn_name": row["价值节点(物理资产)"]} for _, row in pay_nodes.iterrows()]


# ============================================================
# 4. 比对逻辑
# ============================================================

def compare(blueprint_nodes: dict, excel_nodes: list) -> dict:
    """全量比对：5份蓝图合并 vs Excel PAY域"""

    # 合并所有蓝图中的节点（去重）
    all_bp_nodes = {}
    for bp_name, nodes in blueprint_nodes.items():
        for n in nodes:
            code = n["vn_code"]
            if code not in all_bp_nodes:
                all_bp_nodes[code] = {"name": n["vn_name"], "sources": []}
            all_bp_nodes[code]["sources"].append(bp_name)

    excel_codes = {n["vn_code"]: n["vn_name"] for n in excel_nodes}
    bp_codes = set(all_bp_nodes.keys())
    excel_codes_set = set(excel_codes.keys())

    matched = []
    name_mismatch = []
    only_in_blueprint = []
    only_in_excel = []

    for code in bp_codes & excel_codes_set:
        bp_name = all_bp_nodes[code]["name"]
        ex_name = excel_codes[code]
        if bp_name == ex_name:
            matched.append({"code": code, "name": bp_name, "sources": all_bp_nodes[code]["sources"]})
        else:
            name_mismatch.append({"code": code, "blueprint_name": bp_name, "excel_name": ex_name, "sources": all_bp_nodes[code]["sources"]})

    for code in bp_codes - excel_codes_set:
        only_in_blueprint.append({"code": code, "name": all_bp_nodes[code]["name"], "sources": all_bp_nodes[code]["sources"]})

    for code in excel_codes_set - bp_codes:
        only_in_excel.append({"code": code, "name": excel_codes[code]})

    return {
        "matched": matched,
        "name_mismatch": name_mismatch,
        "only_in_blueprint": only_in_blueprint,
        "only_in_excel": only_in_excel,
        "blueprint_total": len(bp_codes),
        "excel_total": len(excel_codes_set),
        "blueprint_breakdown": {name: len(nodes) for name, nodes in blueprint_nodes.items()},
    }


# ============================================================
# 5. HTML 报告生成
# ============================================================

def generate_html_report(result: dict) -> str:
    """生成HTML校验报告"""
    matched = len(result["matched"])
    mismatch = len(result["name_mismatch"])
    only_bp = len(result["only_in_blueprint"])
    only_ex = len(result["only_in_excel"])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>P1-01 补充验证 · 全量5份蓝图一致性校验</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 40px 20px; background: #f5f5f5; }}
.card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
h1 {{ color: #1a1a1a; margin-bottom: 8px; }}
h2 {{ color: #333; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px; margin-top: 32px; }}
.summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 24px 0; }}
.stat {{ text-align: center; padding: 20px; border-radius: 8px; }}
.stat.matched {{ background: #e8f5e9; color: #2e7d32; }}
.stat.mismatch {{ background: #fff3e0; color: #ef6c00; }}
.stat.only-bp {{ background: #fce4ec; color: #c2185b; }}
.stat.only-ex {{ background: #e3f2fd; color: #1565c0; }}
.stat-number {{ font-size: 36px; font-weight: 700; }}
.stat-label {{ font-size: 14px; margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
th {{ background: #fafafa; font-weight: 600; color: #555; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px; }}
.badge-com {{ background: #e3f2fd; color: #1565c0; }}
.badge-bam {{ background: #f3e5f5; color: #7b1fa2; }}
.badge-cfm {{ background: #e8f5e9; color: #2e7d32; }}
.badge-ssva {{ background: #fff3e0; color: #ef6c00; }}
.badge-stlm {{ background: #fce4ec; color: #c2185b; }}
.warning {{ background: #fff3e0; border-left: 4px solid #ff9800; padding: 12px 16px; margin: 16px 0; }}
</style></head>
<body>
<div class="card">
<h1>P1-01 补充验证 · 全量5份蓝图一致性校验</h1>
<p>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<p>输入：5份PAY域流程蓝图 + D1价值节点清单（PAY域9节点）</p>
<div class="warning">
<strong>⚠ 修正说明：</strong>原P1-01仅读取L3-COM单份蓝图，现补充读取全部5份蓝图（COM/BAM/CFM/SSVA/STLM）。
</div>
</div>

<div class="card">
<div class="summary">
<div class="stat matched"><div class="stat-number">{matched}</div><div class="stat-label">完全匹配</div></div>
<div class="stat mismatch"><div class="stat-number">{mismatch}</div><div class="stat-label">名称不一致</div></div>
<div class="stat only-bp"><div class="stat-number">{only_bp}</div><div class="stat-label">仅蓝图有</div></div>
<div class="stat only-ex"><div class="stat-number">{only_ex}</div><div class="stat-label">仅Excel有</div></div>
</div>
</div>
"""

    # 蓝图分解统计
    html += '<div class="card"><h2>蓝图分解统计</h2><table><tr><th>蓝图</th><th>价值节点数</th></tr>'
    for bp, count in result["blueprint_breakdown"].items():
        html += f'<tr><td>L3-{bp}</td><td>{count}</td></tr>'
    html += f'<tr><td><strong>合计（去重）</strong></td><td><strong>{result["blueprint_total"]}</strong></td></tr></table></div>'

    # 匹配详情
    if result["matched"]:
        html += '<div class="card"><h2>✅ 完全匹配</h2><table><tr><th>节点编码</th><th>节点名称</th><th>来源蓝图</th></tr>'
        for m in result["matched"]:
            badges = ''.join(f'<span class="badge badge-{s.lower()}">{s}</span>' for s in m["sources"])
            html += f'<tr><td>{m["code"]}</td><td>{m["name"]}</td><td>{badges}</td></tr>'
        html += '</table></div>'

    # 名称不一致
    if result["name_mismatch"]:
        html += '<div class="card"><h2>⚠ 名称不一致</h2><table><tr><th>节点编码</th><th>蓝图名称</th><th>Excel名称</th><th>来源</th></tr>'
        for mm in result["name_mismatch"]:
            badges = ''.join(f'<span class="badge badge-{s.lower()}">{s}</span>' for s in mm["sources"])
            html += f'<tr><td>{mm["code"]}</td><td>{mm["blueprint_name"]}</td><td>{mm["excel_name"]}</td><td>{badges}</td></tr>'
        html += '</table></div>'

    # 仅蓝图有
    if result["only_in_blueprint"]:
        html += '<div class="card"><h2>🔴 仅蓝图有（Excel缺失）</h2><table><tr><th>节点编码</th><th>节点名称</th><th>来源蓝图</th></tr>'
        for o in result["only_in_blueprint"]:
            badges = ''.join(f'<span class="badge badge-{s.lower()}">{s}</span>' for s in o["sources"])
            html += f'<tr><td>{o["code"]}</td><td>{o["name"]}</td><td>{badges}</td></tr>'
        html += '</table></div>'

    # 仅Excel有
    if result["only_in_excel"]:
        html += '<div class="card"><h2>🔵 仅Excel有（蓝图未引用）</h2><table><tr><th>节点编码</th><th>节点名称</th></tr>'
        for o in result["only_in_excel"]:
            html += f'<tr><td>{o["code"]}</td><td>{o["name"]}</td></tr>'
        html += '</table></div>'

    html += '</body></html>'
    return html


# ============================================================
# 6. 主函数
# ============================================================

def main():
    print("=" * 60)
    print("P1-01 补充验证 · 全量5份蓝图价值节点一致性校验")
    print("=" * 60)

    print("\n[1/3] 读取5份蓝图...")
    blueprint_nodes = parse_all_blueprints()

    print("\n[2/3] 读取Excel...")
    excel_nodes = load_excel_nodes()
    print(f"  Excel PAY域: {len(excel_nodes)} 个节点")

    print("\n[3/3] 全量比对...")
    result = compare(blueprint_nodes, excel_nodes)

    print(f"\n  蓝图合计（去重）: {result['blueprint_total']} 个")
    print(f"  Excel PAY域: {result['excel_total']} 个")
    print(f"  完全匹配: {len(result['matched'])} 个")
    print(f"  名称不一致: {len(result['name_mismatch'])} 个")
    print(f"  仅蓝图有: {len(result['only_in_blueprint'])} 个")
    print(f"  仅Excel有: {len(result['only_in_excel'])} 个")

    # 保存JSON
    json_path = OUTPUT_DIR / "validation_v2_result.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 保存HTML
    html = generate_html_report(result)
    html_path = OUTPUT_DIR / "validation_v2_report.html"
    html_path.write_text(html, encoding="utf-8")

    print(f"\n产出：")
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
