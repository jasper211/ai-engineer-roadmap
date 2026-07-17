#!/usr/bin/env python3
"""
OB-SYNC-AG01 · OB知识库同步巡检Agent
功能：巡检 + 自愈 —— 符号链接、MCP 配置、多终端 AI 访问能力
运行：python3 ob_sync_agent.py [--output <路径>] [--auto-fix] [--quiet]
"""

import os
import json
import random
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple


# ══════════════════════════════════════════════════════════════
# 正确路径（唯一权威来源）
# ══════════════════════════════════════════════════════════════

CORRECT_SERVER_PATH = "/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/obsidian-mcp-server/src/server.mjs"


# ══════════════════════════════════════════════════════════════
# 配置区（与 config.json 对齐）
# ══════════════════════════════════════════════════════════════

VAULT_PATH = "/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/ObsidianVault"

MCP_CONFIGS = {
    "Qoder": "/Users/zhaoqitrenda.cn/Library/Application Support/Qoder/SharedClientCache/mcp.json",
    "Claude Desktop": "/Users/zhaoqitrenda.cn/Library/Application Support/Claude/claude_desktop_config.json",
    "Kimi Code": "/Users/zhaoqitrenda.cn/.kimi-code/mcp.json",
}

F_FILES = [
    "/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI上下文启动文件_v2_0.md",
    "项目-流程架构/08_任务与跟进/AI上下文/AI协作准则_v2_0.md",
    "项目-流程架构/08_任务与跟进/AI上下文/教训档案_v2_0.md",
]

MCP_SERVER_SCRIPT = "/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/obsidian-mcp-server/src/vault.mjs"

# Server 端期望的目录路径（比较目录，因为配置文件指向 server.mjs，不是 vault.mjs）
EXPECTED_SERVER_DIR = os.path.realpath(os.path.dirname(MCP_SERVER_SCRIPT))

OUTPUT_PATH = "/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/Agent健康报告.md"
DASHBOARD_PATH = "/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/Agent运行仪表盘.md"

# 导入共享模块（agent_status.py 放在同目录或父级 05_Agent库 均可）
try:
    import agent_status
except ImportError:
    AGENT_LIB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, AGENT_LIB_DIR)
    import agent_status


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
                    "config_path": config_path,
                    "status": "❌ 未找到 obsidian-knowledge 配置",
                    "detail": "",
                    "fixable": False
                })
                continue
            args = server_entry.get("args", [])
            mcp_path = args[0] if args else "无路径"
            path_correct = (mcp_path == CORRECT_SERVER_PATH)
            path_exists = os.path.exists(mcp_path)
            results.append({
                "terminal": name,
                "config_path": config_path,
                "configured_path": mcp_path,
                "path_exists": path_exists,
                "path_correct": path_correct,
                "status": "✅" if path_correct else "❌ 需修复",
                "detail": f"正确路径: {CORRECT_SERVER_PATH}" if not path_correct else "",
                "fixable": not path_correct  # 可自动修复
            })
        except FileNotFoundError:
            results.append({
                "terminal": name,
                "config_path": config_path,
                "status": "❌ 配置文件不存在",
                "detail": config_path,
                "fixable": False
            })
        except Exception as e:
            results.append({
                "terminal": name,
                "config_path": config_path,
                "status": f"❌ 读取失败: {e}",
                "detail": "",
                "fixable": False
            })
    return results


def auto_fix_mcp(mcp_configs: List[Dict]) -> List[str]:
    """自动修复 MCP 配置：将错误路径替换为正确路径"""
    fixed = []
    for entry in mcp_configs:
        if not entry.get("fixable"):
            continue
        config_path = entry["config_path"]
        try:
            with open(config_path, 'r') as f:
                cfg = json.load(f)
            old = cfg["mcpServers"]["obsidian-knowledge"]["args"][0]
            cfg["mcpServers"]["obsidian-knowledge"]["args"][0] = CORRECT_SERVER_PATH
            with open(config_path, 'w') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            fixed.append(f"{entry['terminal']}: {old} → {CORRECT_SERVER_PATH}")
        except Exception as e:
            fixed.append(f"{entry['terminal']}: 修复失败 ({e})")
    return fixed


def notify(title: str, message: str):
    """发送 macOS 系统通知"""
    try:
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}"'
        ], timeout=5)
    except Exception:
        pass  # 通知失败不影响主流程


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
        full = rel_path if os.path.isabs(rel_path) else os.path.join(VAULT_PATH, rel_path)
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


def check_sync_integrity() -> Dict:
    """同步完整性抽查：随机挑 3 个本地 md 文件，验证 MCP 索引中确实存在"""
    vault_files = []
    for root, dirs, files in os.walk(VAULT_PATH):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
        for f in files:
            if f.endswith('.md'):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, VAULT_PATH)
                vault_files.append((full_path, rel_path))

    if len(vault_files) < 3:
        return {"status": "⚠️ 样本不足", "detail": f"Vault 中仅有 {len(vault_files)} 个 md 文件", "samples": []}

    samples = random.sample(vault_files, min(3, len(vault_files)))

    # 构建 node 脚本：建索引 + 检查每个文件是否在 byPath 中
    check_entries = ", ".join([f'"{rel}": idx.byPath.has("{rel}")' for _, rel in samples])
    node_script = (
        f"import('{MCP_SERVER_SCRIPT}').then(v => {{"
        f"const idx = v.buildIndex('{VAULT_PATH}');"
        f"const results = {{ {check_entries} }};"
        f"console.log(JSON.stringify(results));"
        f"}}).catch(e => console.log(JSON.stringify({{error: e.message}})));"
    )

    try:
        result = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(MCP_SERVER_SCRIPT)
        )
        output = result.stdout.strip() or result.stderr.strip()
        data = json.loads(output)

        if "error" in data:
            return {"status": "❌", "detail": f"索引构建失败: {data['error']}", "samples": []}

        sample_results = []
        all_found = True
        for full_path, rel_path in samples:
            found = data.get(rel_path, False)
            if not found:
                all_found = False
            sample_results.append({"path": rel_path, "found": found})

        return {
            "status": "✅" if all_found else "❌ 同步断裂",
            "detail": f"抽查 {len(samples)} 个文件，全部命中" if all_found else f"抽查 {len(samples)} 个文件，存在缺失",
            "samples": sample_results,
        }
    except Exception as e:
        return {"status": "❌", "detail": str(e), "samples": []}


def generate_dashboard():
    """从 /tmp/jasper-agents/ 读取所有 Agent 状态，生成仪表盘 Markdown"""
    agents = agent_status.read_all()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append("# Agent 运行仪表盘")
    lines.append("")
    lines.append("> **文档定位**：集中展示所有 Jasper AI Agent 的运行状态与健康指标")
    lines.append("> **核心作用**：一站式查看 Agent 是否存活、最近一次执行结果、异常告警")
    lines.append("> **使用场景**：每日开工时扫一眼确认所有 Agent 正常；Agent 告警时快速定位问题")
    lines.append("> **维护责任**：各 Agent 通过 agent_status.py 自动写入状态；本文件由 generate_dashboard() 自动生成，勿手动编辑")
    lines.append("> **迭代规则**：新增 Agent 只需调用 agent_status.register() + update()；仪表盘自动适配")
    lines.append("> **关联文件**：agent_status.py → /tmp/jasper-agents/*.json → 本文件")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 总体概览表 ──
    lines.append("## 总体概览")
    lines.append("")
    if not agents:
        lines.append("*暂无已注册的 Agent*")
        lines.append("")
    else:
        lines.append("| Agent | 状态 | 最后巡检 | 下次巡检 | 详情 |")
        lines.append("|-------|------|---------|---------|------|")
        for a in agents:
            status = a.get("status", "?")
            name = a.get("name", "?")
            last = a.get("last_run", "—")
            next_run = a.get("next_run", "—")
            anchor = name.lower()  # Obsidian 锚点：小写即可 (heading = ### {name})
            lines.append(f"| {name} | {status} | {last} | {next_run} | [查看](#{anchor}) |")
        lines.append("")

    # ── 各 Agent 详情 ──
    lines.append("## 各 Agent 详情")
    lines.append("")
    for a in agents:
        name = a.get("name", "?")
        desc = a.get("description", "")
        status = a.get("status", "?")
        schedule = a.get("schedule", "")
        results = a.get("results", {})
        errors = a.get("errors", [])
        checks = a.get("checks", [])

        anchor = name.lower()  # Obsidian 锚点：小写即可 (heading = ### {name})
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"**{desc}**　|　状态：{status}　|　调度：{schedule}")
        lines.append("")

        if errors:
            lines.append("⚠️ **异常**：")
            for e in errors:
                lines.append(f"- {e}")
            lines.append("")

        if results:
            lines.append("| 检查项 | 结果 |")
            lines.append("|--------|------|")
            for check_name in checks:
                r = results.get(check_name, "⏳")
                lines.append(f"| {check_name} | {r} |")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append(f"*最后生成：{now}*")
    lines.append("")

    return "\n".join(lines)


def write_dashboard():
    """生成仪表盘并写入 OB"""
    try:
        md = generate_dashboard()
        os.makedirs(os.path.dirname(DASHBOARD_PATH), exist_ok=True)
        with open(DASHBOARD_PATH, 'w', encoding='utf-8') as f:
            f.write(md)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# 报告生成
# ══════════════════════════════════════════════════════════════

def generate_report(all_results: Dict) -> str:
    """生成 Markdown 健康报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    lines.append(f"# OB 知识库同步健康报告")
    lines.append(f"")
    lines.append(f"> 自动生成 | {now} | Agent: OB-SYNC-AG01 v1.1")
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
    # Sync integrity
    sync_ok = all_results.get("sync_integrity", {}).get("status", "") == "✅"
    statuses.append(("同步完整性", sync_ok))

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
    lines.append("| AI终端 | 状态 |")
    lines.append("|--------|------|")
    for r in all_results["mcp_configs"]:
        lines.append(f"| {r['terminal']} | {r['status']} |")
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

    # ── 6. 同步完整性抽查 ──
    sync = all_results.get("sync_integrity", {})
    if sync:
        lines.append("## 六、同步完整性抽查")
        lines.append("")
        lines.append(f"| 状态 | 详情 |")
        lines.append(f"|------|------|")
        lines.append(f"| {sync['status']} | {sync.get('detail', '')} |")
        lines.append("")
        if sync.get("samples"):
            lines.append("| 抽查文件 | 索引中存在 |")
            lines.append("|----------|----------|")
            for s in sync["samples"]:
                lines.append(f"| {s['path']} | {'✅' if s['found'] else '❌ 缺失'} |")
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
        if all_results.get("sync_integrity", {}).get("status", "") == "❌ 同步断裂":
            lines.append("- 同步断裂：MCP 索引中缺少部分本地文件，尝试重建索引或检查符号链接")
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════

def main():
    output_path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--output" else OUTPUT_PATH
    auto_fix = "--auto-fix" in sys.argv
    quiet = "--quiet" in sys.argv

    if not quiet:
        print("🔍 OB-SYNC-AG01 · 开始巡检 ...")
        print()

    if not quiet:
        print("  检查符号链接 ...")
    symlinks = check_symlinks()
    if not quiet:
        for s in symlinks:
            print(f"    {s.get('link_name', '?')} → {s.get('status', '?')}")

    if not quiet:
        print("  检查 MCP 配置 ...")
    mcp_configs = check_mcp_configs()
    if not quiet:
        for m in mcp_configs:
            print(f"    {m['terminal']}: {m['status']}")

    # ── 自愈：修复 MCP 配置 ──
    fixes = []
    mcp_ok = all(r.get("status") == "✅" for r in mcp_configs)
    if not mcp_ok and auto_fix:
        if not quiet:
            print("  🔧 自动修复 MCP 配置 ...")
        fixes = auto_fix_mcp(mcp_configs)
        for fix in fixes:
            if not quiet:
                print(f"    {fix}")
        # 修复后重检
        mcp_configs = check_mcp_configs()
        mcp_ok = all(r.get("status") == "✅" for r in mcp_configs)

    if not quiet:
        print("  检查 MCP Server ...")
    mcp_server = check_mcp_server()
    if not quiet:
        print(f"    {mcp_server['status']}")

    if not quiet:
        print("  检查 F1/F2/F3 ...")
    f_files = check_f_files()
    if not quiet:
        for f in f_files:
            print(f"    {f['file']}: {f['status']}")

    if not quiet:
        print("  统计 Vault ...")
    vault_stats = check_vault_stats()
    if not quiet:
        print(f"    {vault_stats['md_files']:,} md 文件, {vault_stats['directories']:,} 目录")

    if not quiet:
        print("  同步完整性抽查 ...")
    sync_integrity = check_sync_integrity()
    if not quiet:
        print(f"    {sync_integrity['status']}")

    all_results = {
        "symlinks": symlinks,
        "mcp_configs": mcp_configs,
        "mcp_server": mcp_server,
        "f_files": f_files,
        "vault_stats": vault_stats,
        "sync_integrity": sync_integrity,
    }

    report = generate_report(all_results)

    # ── 状态变量 ──
    sl_ok = all(r.get("status") == "✅" for r in symlinks if "status" in r)
    mcp_ok = all(r.get("status") == "✅" for r in mcp_configs)
    srv_ok = mcp_server.get("status") == "✅"
    ff_ok = all(r.get("status") == "✅" for r in f_files)
    sync_ok = sync_integrity.get("status", "") == "✅"
    all_ok = sl_ok and mcp_ok and srv_ok and ff_ok and sync_ok

    # ── 注册 + 更新 Agent 状态（含详细报告） ──
    from datetime import timedelta
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    now_dt = datetime.now()
    next_str = (now_dt + timedelta(hours=1)).strftime("%H:%M")

    all_ok_flag = all_ok and sync_ok
    status_str = "🟢 全部正常" if all_ok_flag else "🔴 存在异常"
    errors_list = []
    if not all_ok_flag:
        if not sl_ok: errors_list.append("符号链接断链")
        if not mcp_ok: errors_list.append("MCP配置异常")
        if not srv_ok: errors_list.append("MCP Server异常")
        if not ff_ok: errors_list.append("F文件缺失")
        if not sync_ok: errors_list.append("同步断裂")

    agent_status.register("OB-SYNC-AG01", {
        "description": "OB知识库同步巡检",
        "schedule": "每小时 + 开机",
        "checks": ["符号链接", "MCP配置", "MCP Server", "F文件", "同步完整性", "Vault笔记数"],
    })
    agent_status.update("OB-SYNC-AG01", {
        "status": status_str,
        "last_run": now_str,
        "next_run": next_str,
        "results": {
            "符号链接": "✅" if sl_ok else "❌",
            "MCP配置": "✅" if mcp_ok else "❌",
            "MCP Server": "✅" if srv_ok else "❌",
            "F文件": "✅" if ff_ok else "❌",
            "同步完整性": "✅" if sync_ok else "❌",
            "Vault笔记数": str(vault_stats.get("md_files", "?")),
        },
        "errors": errors_list,
        "detail": report,
    })

    # ── 生成统一健康报告 + 仪表盘 ──
    agent_status.write_report(OUTPUT_PATH)
    write_dashboard()

    if all_ok:
        if not quiet:
            notify("OB知识库", "🟢 全部正常 — 所有 AI 已连接")
    else:
        problems = []
        if not sl_ok:
            problems.append("符号链接断链")
        if not mcp_ok:
            problems.append("MCP配置异常")
        if not srv_ok:
            problems.append("MCP Server异常")
        if not ff_ok:
            problems.append("F文件缺失")
        if not sync_ok:
            problems.append("同步断裂")
        notify("OB知识库 ⚠️", f"发现问题: {', '.join(problems)}")
        if fixes:
            notify("OB知识库", f"已自动修复 {len(fixes)} 个 MCP 配置")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
