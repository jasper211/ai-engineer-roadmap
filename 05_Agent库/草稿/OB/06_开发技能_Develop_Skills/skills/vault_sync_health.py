#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：巡检 Obsidian 知识库的同步健康状态。

迁移来源：05_Agent库/OB知识库同步巡检Agent/ob_sync_agent.py（648行独立脚本），
按 Agent搭建SOP v1.2"迁移不是照搬"三原则复核后迁移：

1. 消除重复实现：原脚本 check_mcp_server()/check_sync_integrity() 各自独立拼接
   了一段几乎相同的 `node -e` 调用样板（subprocess.run + 超时 + JSON解析 +
   异常处理）。这次抽成 tools/mcp_bridge.py 的 run_vault_check() 共享，两处
   都改成调用它。
2. 该删的功能就删：原脚本里 macOS 系统通知（notify()，用 osascript display
   notification）依赖脚本独立运行时的桌面会话，跟"skill 只返回结构化结果、
   由 agent.py 决定要不要通知"的新架构原则冲突——通知逻辑挪到 agent.py 层，
   不留在 skill 内部。
3. 迁移时发现的真实 bug：2026-07-15 核实发现 launchd 实际运行的部署副本
   （非本仓库这份源码）里的 VAULT_PATH 常量，此前一直是旧的错误路径
   （指向一个空目录），已单独修复部署副本，跟这次代码迁移无关但值得记录——
   "代码在仓库里改对了"不等于"实际在跑的那份也是对的"，这也是为什么
   OB 巡检能力线本身要存在的理由之一。

不迁移的部分：generate_dashboard()/write_dashboard()（读取 agent_status 全局
状态生成"Agent运行仪表盘.md"）——这属于巡检结果的一种呈现形式，保留在
agent.py 层调用 tools/agent_status.py 的 generate_report()，不放进本 skill。
"""

import os
import random
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from tools import mcp_bridge


class VaultSyncHealthChecker:
    """巡检 vault 的 6 项同步健康状态，产出结构化结果 + Markdown 健康报告。

    路径类配置（vault_path/mcp_configs/f_files/server_script）只在这里作为
    构造参数传入，不重复写进 settings.json——2026-07-15 校准 obsidian-mcp-server
    时发现 config.json 里冗余保存的 obsidian_vault_path/report_path 字段早已
    跟代码里的真实常量不一致（代码改了、配置文件没跟着改），这正是"同一份
    路径信息存在两个地方"必然会漂移的真实案例，这里刻意只保留一份。
    """

    def __init__(
        self,
        vault_path: str,
        server_script: str,
        correct_server_path: str,
        mcp_configs: Dict[str, str],
        f_files: List[str],
    ):
        self.vault_path = vault_path
        self.server_script = server_script
        self.correct_server_path = correct_server_path
        self.mcp_configs = mcp_configs
        self.f_files = f_files

    # ── 检查函数 ──

    def check_symlinks(self) -> List[Dict]:
        """检查 vault 根目录的符号链接完整性。"""
        results = []
        try:
            for entry in os.listdir(self.vault_path):
                full = os.path.join(self.vault_path, entry)
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

    def check_mcp_configs(self) -> List[Dict]:
        """检查各 AI 终端的 MCP 配置是否指向正确的 Server 路径。"""
        import json
        results = []
        for name, config_path in self.mcp_configs.items():
            try:
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                server_entry = cfg.get("mcpServers", {}).get("obsidian-knowledge", {})
                if not server_entry:
                    results.append({
                        "terminal": name, "config_path": config_path,
                        "status": "❌ 未找到 obsidian-knowledge 配置",
                        "detail": "", "fixable": False,
                    })
                    continue
                args = server_entry.get("args", [])
                mcp_path = args[0] if args else "无路径"
                path_correct = mcp_path == self.correct_server_path
                results.append({
                    "terminal": name, "config_path": config_path,
                    "configured_path": mcp_path,
                    "path_exists": os.path.exists(mcp_path),
                    "path_correct": path_correct,
                    "status": "✅" if path_correct else "❌ 需修复",
                    "detail": f"正确路径: {self.correct_server_path}" if not path_correct else "",
                    "fixable": not path_correct,
                })
            except FileNotFoundError:
                results.append({
                    "terminal": name, "config_path": config_path,
                    "status": "❌ 配置文件不存在", "detail": config_path, "fixable": False,
                })
            except Exception as e:
                results.append({
                    "terminal": name, "config_path": config_path,
                    "status": f"❌ 读取失败: {e}", "detail": "", "fixable": False,
                })
        return results

    def auto_fix_mcp(self, mcp_configs: List[Dict]) -> List[str]:
        """自动修复 MCP 配置：把错误路径替换为正确路径（只做纯字符串替换，不做删除类操作）。"""
        import json
        fixed = []
        for entry in mcp_configs:
            if not entry.get("fixable"):
                continue
            config_path = entry["config_path"]
            try:
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                old = cfg["mcpServers"]["obsidian-knowledge"]["args"][0]
                cfg["mcpServers"]["obsidian-knowledge"]["args"][0] = self.correct_server_path
                with open(config_path, "w") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                fixed.append(f"{entry['terminal']}: {old} → {self.correct_server_path}")
            except Exception as e:
                fixed.append(f"{entry['terminal']}: 修复失败 ({e})")
        return fixed

    def check_mcp_server(self) -> Dict:
        """测试 MCP Server（vault.mjs）是否能正常构建索引。"""
        data = mcp_bridge.build_index_stats(self.server_script, self.vault_path)
        if "error" in data:
            return {"status": "❌", "detail": data["error"]}
        return {"status": "✅", "notes": data.get("notes", "?"), "tags": data.get("tags", "?"), "detail": ""}

    def check_f_files(self) -> List[Dict]:
        """检查 F1/F2/F3 上下文文件是否存在且可读。"""
        results = []
        for rel_path in self.f_files:
            full = rel_path if os.path.isabs(rel_path) else os.path.join(self.vault_path, rel_path)
            exists = os.path.exists(full)
            results.append({
                "file": os.path.basename(rel_path),
                "path": rel_path,
                "exists": exists,
                "size_bytes": os.path.getsize(full) if exists else 0,
                "status": "✅" if exists else "❌ 文件不存在",
            })
        return results

    def check_vault_stats(self) -> Dict:
        """vault 基础统计：md 文件数 + 目录数。"""
        md_count = 0
        dir_count = 0
        for root, dirs, files in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            md_count += sum(1 for f in files if f.endswith(".md"))
            dir_count += 1
        return {"md_files": md_count, "directories": dir_count}

    def check_sync_integrity(self) -> Dict:
        """同步完整性抽查：随机挑 3 个本地 md 文件，验证 MCP 索引中确实存在。"""
        vault_files = []
        for root, dirs, files in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for f in files:
                if f.endswith(".md"):
                    full_path = os.path.join(root, f)
                    vault_files.append((full_path, os.path.relpath(full_path, self.vault_path)))

        if len(vault_files) < 3:
            return {"status": "⚠️ 样本不足", "detail": f"vault 中仅有 {len(vault_files)} 个 md 文件", "samples": []}

        samples = random.sample(vault_files, min(3, len(vault_files)))
        rel_paths = [rel for _, rel in samples]
        data = mcp_bridge.check_paths_indexed(self.server_script, self.vault_path, rel_paths)

        if "error" in data:
            return {"status": "❌", "detail": f"索引构建失败: {data['error']}", "samples": []}

        sample_results = []
        all_found = True
        for _, rel_path in samples:
            found = data.get(rel_path, False)
            if not found:
                all_found = False
            sample_results.append({"path": rel_path, "found": found})

        return {
            "status": "✅" if all_found else "❌ 同步断裂",
            "detail": f"抽查 {len(samples)} 个文件，全部命中" if all_found else f"抽查 {len(samples)} 个文件，存在缺失",
            "samples": sample_results,
        }

    def check_github_sync(self) -> Dict:
        """确保本地vault内容是GitHub上的最新版。

        动机：检索（knowledge_retrieval.py）和 MCP Server 读的都是本地磁盘上的
        vault 文件，不是每次现查 GitHub——"MCP 连没连上"这类巡检如果不额外保证
        本地内容跟 GitHub 一致，连上了也可能读到的是旧内容，巡检的意义就打了
        折扣。这里只做 fast-forward pull：工作区不干净（有未提交改动）时直接
        跳过并报警，不自动 stash/合并，避免本地正在进行的工作被意外冲掉；
        pull 本身也用 --ff-only，历史发散（比如本机和别处都提交了新内容）时
        会失败并原样报出来，不自动创建合并提交掩盖冲突。
        """
        try:
            status = subprocess.run(
                ["git", "-C", self.vault_path, "status", "--short"],
                capture_output=True, text=True, timeout=15,
            )
            if status.returncode != 0:
                return {"status": "❌", "detail": f"git status 失败: {status.stderr.strip()}"}
            if status.stdout.strip():
                return {"status": "⚠️ 跳过", "detail": "本地有未提交改动，为避免冲突不自动 pull，需先手动 commit/处理"}

            result = subprocess.run(
                ["git", "-C", self.vault_path, "pull", "--ff-only", "origin", "main"],
                capture_output=True, text=True, timeout=30,
            )
            output = (result.stdout + result.stderr).strip()
            if result.returncode != 0:
                return {"status": "❌ pull失败", "detail": output or "未知错误（可能网络问题或历史分叉）"}
            if "up to date" in output.lower():
                return {"status": "✅ 已是最新", "detail": output}
            return {"status": "✅ 已拉取更新", "detail": output}
        except subprocess.TimeoutExpired:
            return {"status": "❌ 超时", "detail": "git pull 超过30秒未响应（可能网络问题）"}
        except FileNotFoundError:
            return {"status": "❌", "detail": "git 命令不存在"}
        except Exception as e:
            return {"status": "❌", "detail": str(e)}

    # ── 编排 + 报告 ──

    def run(self, auto_fix: bool = False) -> Dict:
        """跑全部 6 项检查，返回结构化结果（含 Markdown 报告文本），不做任何持久化/通知——
        由调用方（agent.py）决定报告写到哪、要不要发通知。"""
        symlinks = self.check_symlinks()
        mcp_configs = self.check_mcp_configs()

        fixes = []
        if auto_fix and not all(r.get("status") == "✅" for r in mcp_configs):
            fixes = self.auto_fix_mcp(mcp_configs)
            mcp_configs = self.check_mcp_configs()

        mcp_server = self.check_mcp_server()
        f_files = self.check_f_files()
        vault_stats = self.check_vault_stats()
        sync_integrity = self.check_sync_integrity()
        github_sync = self.check_github_sync()

        all_results = {
            "symlinks": symlinks,
            "mcp_configs": mcp_configs,
            "mcp_server": mcp_server,
            "f_files": f_files,
            "vault_stats": vault_stats,
            "sync_integrity": sync_integrity,
            "github_sync": github_sync,
            "fixes_applied": fixes,
        }

        sl_ok = all(r.get("status") == "✅" for r in symlinks if "status" in r)
        mcp_ok = all(r.get("status") == "✅" for r in mcp_configs)
        srv_ok = mcp_server.get("status") == "✅"
        ff_ok = all(r.get("status") == "✅" for r in f_files)
        sync_ok = sync_integrity.get("status", "") == "✅"
        gh_ok = github_sync.get("status", "").startswith("✅")
        all_ok = sl_ok and mcp_ok and srv_ok and ff_ok and sync_ok and gh_ok

        all_results["all_ok"] = all_ok
        all_results["summary"] = {
            "符号链接": sl_ok, "MCP配置": mcp_ok, "MCP Server": srv_ok,
            "F文件": ff_ok, "同步完整性": sync_ok, "GitHub同步": gh_ok,
        }
        all_results["report_markdown"] = self._generate_report(all_results, all_ok, sl_ok, mcp_ok, srv_ok, ff_ok, sync_ok, gh_ok)
        return all_results

    def _generate_report(self, all_results, all_ok, sl_ok, mcp_ok, srv_ok, ff_ok, sync_ok, gh_ok) -> str:
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"# OB 知识库同步健康报告", "", f"> 自动生成 | {now} | Agent: OB", ""]

        statuses = [("符号链接", sl_ok), ("MCP配置", mcp_ok), ("MCP Server", srv_ok),
                    ("F文件", ff_ok), ("同步完整性", sync_ok), ("GitHub同步", gh_ok)]
        lines.append(f"## 总体状态：{'🟢 全部正常' if all_ok else '🔴 存在异常'}")
        lines.append("")
        for name, ok in statuses:
            lines.append(f"| {name} | {'✅' if ok else '❌'} |")
        lines.append("")

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

        lines.append("## 二、MCP 配置")
        lines.append("")
        lines.append("| AI终端 | 状态 |")
        lines.append("|--------|------|")
        for r in all_results["mcp_configs"]:
            lines.append(f"| {r['terminal']} | {r['status']} |")
        lines.append("")

        lines.append("## 三、MCP Server 连通性")
        lines.append("")
        srv = all_results["mcp_server"]
        if srv["status"] == "✅":
            lines.append("| 状态 | 索引笔记数 | 标签数 |")
            lines.append("|------|-----------|--------|")
            lines.append(f"| ✅ | {srv['notes']} | {srv['tags']} |")
        else:
            lines.append("| 状态 | 详情 |")
            lines.append("|------|------|")
            lines.append(f"| {srv['status']} | {srv['detail']} |")
        lines.append("")

        lines.append("## 四、F1/F2/F3 上下文文件")
        lines.append("")
        lines.append("| 文件 | 大小 | 状态 |")
        lines.append("|------|------|------|")
        for r in all_results["f_files"]:
            lines.append(f"| {r['file']} | {r['size_bytes']:,} B | {r['status']} |")
        lines.append("")

        lines.append("## 五、Vault 基础统计")
        lines.append("")
        stats = all_results["vault_stats"]
        lines.append("| Markdown 文件 | 目录数 |")
        lines.append("|-------------|--------|")
        lines.append(f"| {stats['md_files']:,} | {stats['directories']:,} |")
        lines.append("")

        sync = all_results.get("sync_integrity", {})
        if sync:
            lines.append("## 六、同步完整性抽查")
            lines.append("")
            lines.append("| 状态 | 详情 |")
            lines.append("|------|------|")
            lines.append(f"| {sync['status']} | {sync.get('detail', '')} |")
            lines.append("")
            if sync.get("samples"):
                lines.append("| 抽查文件 | 索引中存在 |")
                lines.append("|----------|----------|")
                for s in sync["samples"]:
                    lines.append(f"| {s['path']} | {'✅' if s['found'] else '❌ 缺失'} |")
                lines.append("")

        gh = all_results.get("github_sync", {})
        if gh:
            lines.append("## 七、GitHub 同步状态")
            lines.append("")
            lines.append("| 状态 | 详情 |")
            lines.append("|------|------|")
            lines.append(f"| {gh['status']} | {gh.get('detail', '')} |")
            lines.append("")

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
                lines.append("- F 文件缺失：检查对应上下文文件路径")
            if sync.get("status", "") == "❌ 同步断裂":
                lines.append("- 同步断裂：MCP 索引中缺少部分本地文件，尝试重建索引或检查符号链接")
            if not gh_ok:
                if gh.get("status") == "⚠️ 跳过":
                    lines.append("- GitHub同步被跳过：本地有未提交改动，先手动 commit（或 stash）再让下次巡检自动 pull")
                else:
                    lines.append(f"- GitHub同步异常：{gh.get('detail', '')}（检查网络，或本地/远程历史是否分叉需要手动处理）")
            lines.append("")

        return "\n".join(lines)
