#!/usr/bin/env python3
"""
OB-SYNC-AG01 · OB知识库同步巡检Agent
功能：巡检 Obsidian 知识库同步健康状态 —— 符号链接、MCP 配置、多终端 AI 访问能力
运行：python3 ob_sync_agent.py [--output <路径>]
"""

import os
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple


# ══════════════════════════════════════════════════════════════
# 配置区（与 config.json 对齐）
# ══════════════════════════════════════════════════════════════

VAULT_PATH = "/Users/zhaoqitrenda.cn/ObsidianVault"

MCP_CONFIGS = {
    "Qoder": "/Users/zhaoqitrenda.cn/Library/Application Support/Qoder/SharedClientCache/mcp.json",
    "Claude Desktop": "/Users/zhaoqitrenda.cn/Library/Application Support/Claude/claude_desktop_config.json",
    "Kimi Code": "/Users/zhaoqitrenda.cn/.kimi-code/mcp.json",
}

F_FILES = [
    "项目-流程架构/08_任务与跟进/AI上下文/AI上下文启动文件_v2_0.md",
    "项目-流程架构/08_任务与跟进/AI上下文/AI协作准则_v2_0.md",
    "项目-流程架构/08_任务与跟进/AI上下文/教训档案_v2_0.md",
]

MCP_SERVER_SCRIPT = "/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/obsidian-mcp-server/src/vault.mjs"

# Server 端期望的 MCP 路径（不含中文的路径是 Server 实际位置）
EXPECTED_SERVER_PATH = os.path.realpath(MCP_SERVER_SCRIPT)

OUTPUT_PATH = os.path.join(VAULT_PATH, "项目-流程架构/08_任务与跟进/AI上下文/OB同步健康报告.md")


# ══════════════════════════════════════════════════════════════
# 检查函数
# ══════════════════════════════════════════════════════════════

def check_symlinks() -> List[Dict]:
    """检查 ObsidianVault 中的符号链接完整性"""
    results = []
    try:
        for entry in os.listdir(VAULT_PATH):
            full = os.path.join(VAULT_PATH, entry)
            if os.path.islink(full):
                target = os.readlink(full)
                target_exists = os.path.exists(full)
                results.append({
                    "link_name": entry,
                    "target": target,
                    "status": "✅" if target_exists else "❌ 目标不存在",
                })
    except Exception as e:
        results.append({"error": str(e)})
    return results


def check_mcp_configs() -> List[Dict]:
    """检查各 AI 终端的 MCP 配置是否指向正确的 Server 路径"""
    results = []
    for name, config_path in MCP_CONFIGS.items():
        try:
            with open(config_path, 'r') as f:
                cfg = json.load(f)
            server_entry = cfg.get("mcpServers", {}).get("obsidian-knowledge", {})
            if not server_entry:
                results.append({
                    "terminal": name,
                    "status": "❌ 未找到 obsidian-knowledge 配置",
                    "detail": ""
                })
                continue
            args = server_entry.get("args", [])
            mcp_path = args[0] if args else "无路径"
            mcp_real = os.path.realpath(mcp_path) if os.path.exists(mcp_path) else mcp_path
            path_match = (mcp_real == EXPECTED_SERVER_PATH)
            results.append({
                "terminal": name,
                "configured_path": mcp_path,
                "path_exists": os.path.exists(mcp_path),
                "path_matches_expected": path_match,
                "status": "✅" if path_match else "❌ 路径不匹配",
                "detail": f"期望: {EXPECTED_SERVER_PATH}" if not path_match else ""
            })
        except FileNotFoundError:
            results.append({
                "terminal": name,
                "status": "❌ 配置文件不存在",
                "detail": config_path
            })
        except Exception as e:
            results.append({
                "terminal": name,
                "status": f"❌ 读取失败: {e}",
                "detail": ""
            })
    return results


def check_mcp_server() -> Dict:
    """测试 MCP Server 是否能正常构建索引"""
    try:
        result = subprocess.run(
            ["node", "-e",
             f"import('{MCP_SERVER_SCRIPT}').then(v => {{"
             f"const idx = v.buildIndex('{VAULT_PATH}');"
             f"console.log(JSON.stringify({{notes: idx.byPath.size, tags: idx.tagIndex.size}}));"
             f"}}).catch(e => console.log(JSON.stringify({{error: e.message}})));"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(MCP_SERVER_SCRIPT)
        )
        output = result.stdout.strip() or result.stderr.strip()
        data = json.loads(output)
        if "error" in data:
            return {"status": "❌", "detail": data["error"]}
        return {
            "status": "✅",
            "notes": data.get("notes", "?"),
            "tags": data.get("tags", "?"),
            "detail": ""
        }
    except FileNotFoundError:
        return {"status": "❌", "detail": f"Server 脚本不存在: {MCP_SERVER_SCRIPT}"}
    except subprocess.TimeoutExpired:
        return {"status": "⚠️ 超时", "detail": "MCP Server 索引构建超过30秒"}
    except json.JSONDecodeError as e:
        return {"status": "❌", "detail": f"输出解析失败: {e}\n原始输出: {output[:200]}"}
    except Exception as e:
        return {"status": "❌", "detail": str(e)}


def check_f_files() -> List[Dict]:
    """检查 F1/F2/F3 文件是否存在且可读"""
    results = []
    for rel_path in F_FILES:
        full = os.path.join(VAULT_PATH, rel_path)
        exists = os.path.exists(full)
        size = os.path.getsize(full) if exists else 0
        results.append({
            "file": os.path.basename(rel_path),
            "path": rel_path,
            "exists": exists,
            "size_bytes": size,
            "status": "✅" if exists else "❌ 文件不存在"
        })
    return results


def check_vault_stats() -> Dict:
    """检查 Vault 基础统计"""
    md_count = 0
    dir_count = 0
    for root, dirs, files in os.walk(VAULT_PATH):
        # 跳过隐藏目录和 node_modules
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
        md_count += sum(1 for f in files if f.endswith('.md'))
        dir_count += 1
    return {
        "md_files": md_count,
        "directories": dir_count,
    }


# ══════════════════════════════════════════════════════════════
# 报告生成
# ══════════════════════════════════════════════════════════════

def generate_report(all_results: Dict) -> str:
    """生成 Markdown 健康报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    lines.append(f"# OB 知识库同步健康报告")
    lines.append(f"")
    lines.append(f"> 自动生成 | {now} | Agent: OB-SYNC-AG01 v1.0")
    lines.append(f"")

    # ── 总体状态 ──
    statuses = []

    # Symlinks
    sl_ok = all(r["status"] == "✅" for r in all_results["symlinks"])
    statuses.append(("符号链接", sl_ok))
    # MCP Configs
    mcp_ok = all(r["status"] == "✅" for r in all_results["mcp_configs"])
    statuses.append(("MCP配置", mcp_ok))
    # MCP Server
    srv_ok = all_results["mcp_server"]["status"] == "✅"
    statuses.append(("MCP Server", srv_ok))
    # F files
    ff_ok = all(r["status"] == "✅" for r in all_results["f_files"])
    statuses.append(("F文件", ff_ok))

    all_ok = all(s[1] for s in statuses)
    lines.append(f"## 总体状态：{'🟢 全部正常' if all_ok else '🔴 存在异常'}")
    lines.append("")
    for name, ok in statuses:
        lines.append(f"| {name} | {'✅' if ok else '❌'} |")
    lines.append("")

    # ── 1. 符号链接 ──
    lines.append("## 一、符号链接")
    lines.append("")
    lines.append("| 链接名 | 目标 | 状态 |")
    lines.append("|--------|------|------|")
    for r in all_results["symlinks"]:
        if "error" in r:
            lines.append(f"| - | - | ❌ {r['error']} |")
        else:
            lines.append(f"| {r['link_name']} | {r['target']} | {r['status']} |")
    lines.append("")

    # ── 2. MCP 配置 ──
    lines.append("## 二、MCP 配置")
    lines.append("")
    lines.append("| AI终端 | 配置路径 | 路径存在 | 匹配期望 | 状态 |")
    lines.append("|--------|----------|---------|---------|------|")
    for r in all_results["mcp_configs"]:
        lines.append(
            f"| {r['terminal']} | {r.get('configured_path', 'N/A')[:60]}... | "
            f"{'✅' if r.get('path_exists') else '❌'} | "
            f"{'✅' if r.get('path_matches_expected') else '❌'} | "
            f"{r['status']} |"
        )
    lines.append("")

    # ── 3. MCP Server 连通性 ──
    lines.append("## 三、MCP Server 连通性")
    lines.append("")
    srv = all_results["mcp_server"]
    if srv["status"] == "✅":
        lines.append(f"| 状态 | 索引笔记数 | 标签数 |")
        lines.append(f"|------|-----------|--------|")
        lines.append(f"| ✅ | {srv['notes']} | {srv['tags']} |")
    else:
        lines.append(f"| 状态 | 详情 |")
        lines.append(f"|------|------|")
        lines.append(f"| {srv['status']} | {srv['detail']} |")
    lines.append("")

    # ── 4. F1/F2/F3 文件 ──
    lines.append("## 四、F1/F2/F3 上下文文件")
    lines.append("")
    lines.append("| 文件 | 大小 | 状态 |")
    lines.append("|------|------|------|")
    for r in all_results["f_files"]:
        lines.append(f"| {r['file']} | {r['size_bytes']:,} B | {r['status']} |")
    lines.append("")

    # ── 5. Vault 统计 ──
    lines.append("## 五、Vault 基础统计")
    lines.append("")
    stats = all_results["vault_stats"]
    lines.append(f"| Markdown 文件 | 目录数 |")
    lines.append(f"|-------------|--------|")
    lines.append(f"| {stats['md_files']:,} | {stats['directories']:,} |")
    lines.append("")

    # ── 操作建议 ──
    if not all_ok:
        lines.append("## ⚠️ 操作建议")
        lines.append("")
        if not mcp_ok:
            lines.append("- MCP 配置异常：检查上述终端的配置文件，确保 `args[0]` 指向正确的 `server.mjs` 路径")
        if not sl_ok:
            lines.append("- 符号链接失效：检查 Desktop 目录下的原始文件夹是否被移动或删除")
        if not srv_ok:
            lines.append("- MCP Server 异常：检查 Node.js 环境和 `vault.mjs` 文件完整性")
        if not ff_ok:
            lines.append("- F 文件缺失：检查 `项目-流程架构/08_任务与跟进/AI上下文/` 目录")
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════

def main():
    output_path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--output" else OUTPUT_PATH

    print("🔍 OB-SYNC-AG01 · 开始巡检 ...")
    print()

    print("  检查符号链接 ...")
    symlinks = check_symlinks()
    for s in symlinks:
        print(f"    {s.get('link_name', '?')} → {s.get('status', '?')}")

    print("  检查 MCP 配置 ...")
    mcp_configs = check_mcp_configs()
    for m in mcp_configs:
        print(f"    {m['terminal']}: {m['status']}")

    print("  检查 MCP Server ...")
    mcp_server = check_mcp_server()
    print(f"    {mcp_server['status']}")

    print("  检查 F1/F2/F3 ...")
    f_files = check_f_files()
    for f in f_files:
        print(f"    {f['file']}: {f['status']}")

    print("  统计 Vault ...")
    vault_stats = check_vault_stats()
    print(f"    {vault_stats['md_files']:,} md 文件, {vault_stats['directories']:,} 目录")

    all_results = {
        "symlinks": symlinks,
        "mcp_configs": mcp_configs,
        "mcp_server": mcp_server,
        "f_files": f_files,
        "vault_stats": vault_stats,
    }

    report = generate_report(all_results)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print()
    print(f"📄 报告已生成: {output_path}")
    print()

    # 退出码
    all_ok = (
        all(r.get("status") == "✅" for r in symlinks if "status" in r) and
        all(r.get("status") == "✅" for r in mcp_configs) and
        mcp_server.get("status") == "✅" and
        all(r.get("status") == "✅" for r in f_files)
    )
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
