#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1-01 全量验证 · 全部86份流程蓝图 × 72节点价值节点清单一致性校验

输入：
  - 86份流程蓝图 Markdown（自动去重取最新版本）
  - D1 价值节点清单 Excel（72节点全量）

输出：
  - JSON 比对结果
  - HTML 可视化校验报告

作者: Jasper + AI 协同终端
日期: 2026-07-03
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import pandas as pd


# ============================================================
# 1. 配置路径（生产环境只读）
# ============================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
L3_DIR = Path("/Users/zhaoqitrenda.cn/Desktop/流程架构项目_jasper/02_过程成果-工作产出/L3流程库")
EXCEL_PATH = Path("/Users/zhaoqitrenda.cn/Desktop/流程架构项目_jasper/02_过程成果-工作产出/规则分析（Jasper）/01_价值节点清单/D1_价值节点清单_标准化_数据表版_v2.0.xlsx")
OUTPUT_DIR = SCRIPT_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def get_latest_blueprints() -> list[tuple[str, Path]]:
    """获取所有流程蓝图，按 L3 编码分组取最新版本"""
    all_files = list(L3_DIR.glob("流程蓝图_L3-*.md"))
    
    # 按 L3 编码分组
    groups = defaultdict(list)
    for f in all_files:
        # 提取 L3-XXX 编码
        match = re.search(r'L3-([A-Z]+(?:-[A-Z]+)?)', f.name)
        if match:
            l3_code = match.group(1)
            groups[l3_code].append(f)
    
    # 每组取最新版本（按文件名中的版本号或修改时间）
    result = []
    for l3_code, files in sorted(groups.items()):
        # 优先选择版本号最高的（V1.1 > V1.0）
        latest = max(files, key=lambda f: f.name)
        result.append((l3_code, latest))
    
    return result


# ============================================================
# 2. 解析 Markdown 中的价值节点表格
# ============================================================

def parse_markdown_vn_table(md_path: Path) -> list[dict]:
    """从流程蓝图 Markdown 中提取「关联价值节点」表格"""
    content = md_path.read_text(encoding="utf-8")

    # 支持多种表头格式
    patterns = [
        r'## 二、关联价值节点\s*\n\s*\n\|\s*(?:价值节点编码|VN编码)\s*\|\s*(?:价值节点名称|VN名称)\s*\|.*?\n\|[-\| ]+\|\s*\n((?:\| VN-.*?\n)+)',
        r'## 二、关联价值节点\s*\n\s*\n\| VN编码 \| VN名称 \|.*?\n\|[-\| ]+\|\s*\n((?:\| VN-.*?\n)+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            break
    else:
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


# ============================================================
# 3. 读取 Excel 中的价值节点
# ============================================================

def load_excel_nodes() -> list[dict]:
    """从 D1 Excel 读取全部价值节点"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="1.价值节点总览")
    return [{"vn_code": row["节点ID"], "vn_name": row["价值节点(物理资产)"], "domain": row.get("域编码", "")} for _, row in df.iterrows() if pd.notna(row["节点ID"])]


# ============================================================
# 4. 比对逻辑
# ============================================================

def compare(blueprint_nodes: dict, excel_nodes: list) -> dict:
    """全量比对：所有蓝图合并 vs Excel 全量"""

    # 合并所有蓝图中的节点（去重）
    all_bp_nodes = {}
    for bp_name, nodes in blueprint_nodes.items():
        for n in nodes:
            code = n["vn_code"]
            if code not in all_bp_nodes:
                all_bp_nodes[code] = {"name": n["vn_name"], "sources": []}
            all_bp_nodes[code]["sources"].append(bp_name)

    excel_codes = {n["vn_code"]: {"name": n["vn_name"], "domain": n["domain"]} for n in excel_nodes}
    bp_codes = set(all_bp_nodes.keys())
    excel_codes_set = set(excel_codes.keys())

    matched = []
    name_mismatch = []
    only_in_blueprint = []
    only_in_excel = []

    for code in bp_codes & excel_codes_set:
        bp_name = all_bp_nodes[code]["name"]
        ex_name = excel_codes[code]["name"]
        if bp_name == ex_name:
            matched.append({"code": code, "name": bp_name, "domain": excel_codes[code]["domain"], "sources": all_bp_nodes[code]["sources"]})
        else:
            name_mismatch.append({"code": code, "blueprint_name": bp_name, "excel_name": ex_name, "domain": excel_codes[code]["domain"], "sources": all_bp_nodes[code]["sources"]})

    for code in bp_codes - excel_codes_set:
        only_in_blueprint.append({"code": code, "name": all_bp_nodes[code]["name"], "sources": all_bp_nodes[code]["sources"]})

    for code in excel_codes_set - bp_codes:
        only_in_excel.append({"code": code, "name": excel_codes[code]["name"], "domain": excel_codes[code]["domain"]})

    return {
        "matched": matched,
        "name_mismatch": name_mismatch,
        "only_in_blueprint": only_in_blueprint,
        "only_in_excel": only_in_excel,
        "blueprint_total": len(bp_codes),
        "excel_total": len(excel_codes_set),
        "blueprint_breakdown": {name: len(nodes) for name, nodes in blueprint_nodes.items()},
        "blueprint_with_vn": sum(1 for nodes in blueprint_nodes.values() if nodes),
        "blueprint_without_vn": sum(1 for nodes in blueprint_nodes.values() if not nodes),
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
    total_bp = len(result["blueprint_breakdown"])
    bp_with_vn = result["blueprint_with_vn"]
    bp_without_vn = result["blueprint_without_vn"]

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>P1-01 全量验证 · 86份蓝图 × 72节点一致性校验</title>
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
.bp-stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0; }}
.bp-stat {{ text-align: center; padding: 16px; background: #fafafa; border-radius: 8px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
th {{ background: #fafafa; font-weight: 600; color: #555; }}
.badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 3px; background: #e3f2fd; color: #1565c0; }}
.warning {{ background: #fff3e0; border-left: 4px solid #ff9800; padding: 12px 16px; margin: 16px 0; }}
.success {{ background: #e8f5e9; border-left: 4px solid #4caf50; padding: 12px 16px; margin: 16px 0; }}
.domain-tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: #f5f5f5; color: #666; }}
</style></head>
<body>
<div class="card">
<h1>P1-01 全量验证 · 86份蓝图 × 72节点一致性校验</h1>
<p>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<p>输入：86份流程蓝图（去重后 {total_bp} 份）+ D1价值节点清单（72节点全量）</p>
<div class="success">
<strong>✅ 全量覆盖：</strong>读取了全部 {total_bp} 份流程蓝图，其中 {bp_with_vn} 份包含价值节点映射，{bp_without_vn} 份无映射。
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

<div class="card">
<h2>蓝图统计</h2>
<div class="bp-stats">
<div class="bp-stat"><div class="stat-number">{total_bp}</div><div class="stat-label">总蓝图数</div></div>
<div class="bp-stat"><div class="stat-number">{bp_with_vn}</div><div class="stat-label">含VN映射</div></div>
<div class="bp-stat"><div class="stat-number">{bp_without_vn}</div><div class="stat-label">无VN映射</div></div>
</div>
</div>
"""

    # 匹配详情
    if result["matched"]:
        html += '<div class="card"><h2>✅ 完全匹配</h2><table><tr><th>节点编码</th><th>节点名称</th><th>域</th><th>来源蓝图</th></tr>'
        for m in result["matched"]:
            badges = ''.join(f'<span class="badge">{s}</span>' for s in m["sources"])
            html += f'<tr><td>{m["code"]}</td><td>{m["name"]}</td><td><span class="domain-tag">{m["domain"]}</span></td><td>{badges}</td></tr>'
        html += '</table></div>'

    # 名称不一致
    if result["name_mismatch"]:
        html += '<div class="card"><h2>⚠ 名称不一致</h2><table><tr><th>节点编码</th><th>域</th><th>蓝图名称</th><th>Excel名称</th><th>来源</th></tr>'
        for mm in result["name_mismatch"]:
            badges = ''.join(f'<span class="badge">{s}</span>' for s in mm["sources"])
            html += f'<tr><td>{mm["code"]}</td><td><span class="domain-tag">{mm["domain"]}</span></td><td>{mm["blueprint_name"]}</td><td>{mm["excel_name"]}</td><td>{badges}</td></tr>'
        html += '</table></div>'

    # 仅蓝图有
    if result["only_in_blueprint"]:
        html += '<div class="card"><h2>🔴 仅蓝图有（Excel缺失）</h2><table><tr><th>节点编码</th><th>节点名称</th><th>来源蓝图</th></tr>'
        for o in result["only_in_blueprint"]:
            badges = ''.join(f'<span class="badge">{s}</span>' for s in o["sources"])
            html += f'<tr><td>{o["code"]}</td><td>{o["name"]}</td><td>{badges}</td></tr>'
        html += '</table></div>'

    # 仅Excel有
    if result["only_in_excel"]:
        html += '<div class="card"><h2>🔵 仅Excel有（蓝图未引用）</h2><table><tr><th>节点编码</th><th>域</th><th>节点名称</th></tr>'
        for o in result["only_in_excel"]:
            html += f'<tr><td>{o["code"]}</td><td><span class="domain-tag">{o["domain"]}</span></td><td>{o["name"]}</td></tr>'
        html += '</table></div>'

    # 蓝图分解（含VN的）
    html += '<div class="card"><h2>蓝图价值节点映射详情</h2><table><tr><th>蓝图</th><th>节点数</th></tr>'
    for bp, count in sorted(result["blueprint_breakdown"].items(), key=lambda x: -x[1]):
        if count > 0:
            html += f'<tr><td>L3-{bp}</td><td>{count}</td></tr>'
    html += '</table></div>'

    html += '</body></html>'
    return html


# ============================================================
# 6. 主函数
# ============================================================

def main():
    print("=" * 60)
    print("P1-01 全量验证 · 86份蓝图 × 72节点一致性校验")
    print("=" * 60)

    print("\n[1/4] 读取86份蓝图（去重取最新版本）...")
    blueprints = get_latest_blueprints()
    print(f"  去重后: {len(blueprints)} 份蓝图")

    print("\n[2/4] 解析每份蓝图的价值节点表格...")
    blueprint_nodes = {}
    for l3_code, path in blueprints:
        nodes = parse_markdown_vn_table(path)
        blueprint_nodes[l3_code] = nodes
        if nodes:
            print(f"  L3-{l3_code}: {len(nodes)} 个VN")

    bp_with_vn = sum(1 for nodes in blueprint_nodes.values() if nodes)
    print(f"\n  含VN映射: {bp_with_vn} 份 | 无映射: {len(blueprints) - bp_with_vn} 份")

    print("\n[3/4] 读取Excel全量72节点...")
    excel_nodes = load_excel_nodes()
    print(f"  Excel: {len(excel_nodes)} 个节点")
    domains = {}
    for n in excel_nodes:
        domains[n["domain"]] = domains.get(n["domain"], 0) + 1
    print(f"  域分布: {domains}")

    print("\n[4/4] 全量比对...")
    result = compare(blueprint_nodes, excel_nodes)

    print(f"\n  蓝图VN合计（去重）: {result['blueprint_total']} 个")
    print(f"  Excel: {result['excel_total']} 个")
    print(f"  完全匹配: {len(result['matched'])} 个")
    print(f"  名称不一致: {len(result['name_mismatch'])} 个")
    print(f"  仅蓝图有: {len(result['only_in_blueprint'])} 个")
    print(f"  仅Excel有: {len(result['only_in_excel'])} 个")

    # 保存JSON
    json_path = OUTPUT_DIR / "validation_full_result.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 保存HTML
    html = generate_html_report(result)
    html_path = OUTPUT_DIR / "validation_full_report.html"
    html_path.write_text(html, encoding="utf-8")

    print(f"\n产出：")
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
