#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性脚本：拆分HUB_SIZE_CAP(15)之前遗留的超规模枢纽。

背景：cluster_atoms.py的docstring已记录，vault里"财务流程与凭证"(36个)/
"调度触发模式"(21个)/"绩效考核管理"(16个)这几个枢纽来自更早的一次性全量
脚本(migrate_full_vault.py，已不存)，当时没有枢纽规模上限。cluster_atoms.py
的_match_existing_hubs对新增原子已正确执行HUB_SIZE_CAP拦截，不会让这几个
枢纽继续变大，但不负责拆解已存在的超规模枢纽——docstring里明确这是独立的
"阶段B"一次性整理任务。本脚本就是那个阶段B。

做法：复用cluster_atoms.py同一份atom_cluster_coherence_system.md提示词
（该提示词本身就写明"财务流程与凭证"是"过宽领域堆积"的反面教材，应拆分成
更窄的子话题），对目标枢纽的全部成员重新做一次LLM连贯性判断，产出多个新的
窄枢纽，原巨型枢纽文件废弃。

一次性任务，不接入常驻流程，跑完后按06层"已完成_"前缀归档。
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

_OB_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_OB_ROOT / "05_集成工具_Integrate_Tools"))

from tools.atom_embeddings import _parse_atom_file
from tools.llm_client import call_deepseek, DEFAULT_MODEL

PROMPTS_DIR = _OB_ROOT / "08_设计提示词_Design_Prompts" / "prompts"
COHERENCE_PROMPT = (PROMPTS_DIR / "atom_cluster_coherence_system.md").read_text(encoding="utf-8")


def _slugify(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]', "", title).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "未命名枢纽"


def _load_members(hub_path: Path, project_dir: Path):
    text = hub_path.read_text(encoding="utf-8")
    member_section = text.split("## 关联原子")[-1] if "## 关联原子" in text else ""
    slugs = re.findall(r"\[\[(.+?)\]\]", member_section)
    atoms = []
    for slug in slugs:
        p = project_dir / f"{slug}.md"
        if not p.exists():
            print(f"  ⚠️ 成员文件缺失，跳过: {slug}")
            continue
        parsed = _parse_atom_file(p)
        if parsed is None:
            print(f"  ⚠️ 成员文件解析失败，跳过: {slug}")
            continue
        title, summary = parsed
        atoms.append({"slug": slug, "title": title, "summary": summary, "path": p})
    return atoms


def _rewrite_member(atom_path: Path, new_hub_name: str = None, revert_to_unclustered: bool = False):
    text = atom_path.read_text(encoding="utf-8")
    if revert_to_unclustered:
        text = re.sub(r"^entity_ref: .+$", "entity_ref: （无）", text, count=1, flags=re.M)
        # entity_type曾因"进了非正式主题枢纽"而被标成"非正式主题"的，退聚类后还原成
        # "待聚类"，让原子重新进入cluster_atoms.py的候选池；有具体来源类别(SOP/Agent
        # 机制等)的原子不受影响，正则只精确匹配"非正式主题"这一个值
        text = re.sub(r"^entity_type: 非正式主题$", "entity_type: 待聚类", text, count=1, flags=re.M)
        text = re.sub(r"\n## 所属枢纽\n\n- \[\[.+?\]\]\n", "\n", text)
    else:
        text = re.sub(r"^entity_ref: .+$", f"entity_ref: {new_hub_name}", text, count=1, flags=re.M)
        text = re.sub(r"## 所属枢纽\n\n- \[\[.+?\]\]\n", f"## 所属枢纽\n\n- [[{new_hub_name}]]\n", text)
    atom_path.write_text(text, encoding="utf-8")


def split_hub(hub_path: Path, project_dir: Path, api_key: str, dry_run: bool) -> dict:
    atoms = _load_members(hub_path, project_dir)
    print(f"枢纽「{hub_path.stem}」: {len(atoms)} 个可解析成员")

    if dry_run:
        print("  [dry-run] 不调用LLM，仅确认成员可正常读取")
        return {"hub": hub_path.stem, "members": len(atoms), "dry_run": True}

    payload = {"atoms": [{"title": a["title"], "summary": a["summary"]} for a in atoms]}
    response = call_deepseek(
        COHERENCE_PROMPT, json.dumps(payload, ensure_ascii=False), api_key, model=DEFAULT_MODEL
    )
    result = json.loads(response)

    title_to_atom = {a["title"]: a for a in atoms}
    used_slugs = {p.stem for p in project_dir.glob("*.md")}
    new_hubs = []
    for g in result.get("groups", []):
        members = [title_to_atom[t] for t in g.get("atom_titles", []) if t in title_to_atom]
        if len(members) < 2 or not g.get("coherent", True):
            continue
        name = g["hub_name"]
        base_name, i = name, 2
        while _slugify(name) in used_slugs:
            name = f"{base_name}{i}"
            i += 1
        used_slugs.add(_slugify(name))
        new_hubs.append((name, g.get("coherence_reason", ""), members))

    unclustered_titles = [t for t in result.get("unclustered_titles", []) if t in title_to_atom]

    print(f"  → 拆成 {len(new_hubs)} 个子枢纽，{len(unclustered_titles)} 个退回待聚类")
    for name, reason, members in new_hubs:
        print(f"    - {name}（{len(members)}个）：{reason}")

    for name, reason, members in new_hubs:
        new_path = project_dir / f"{_slugify(name)}.md"
        member_block = "\n".join(f"- [[{a['slug']}]]" for a in sorted(members, key=lambda a: a["slug"]))
        content = (
            "---\n"
            "type: entity_hub\n"
            "entity_type: 非正式主题\n"
            f"entity_ref: {name}\n"
            f"project: {project_dir.name}\n"
            f"atom_count: {len(members)}\n"
            f"generated_at: {date.today().isoformat()}\n"
            f"generated_by: split_oversized_hub.py（源自超规模枢纽「{hub_path.stem}」一次性拆分）\n"
            f"coherence_reason: {reason}\n"
            "---\n\n"
            f"# {name}\n\n"
            f"非正式主题枢纽，{len(members)}个原子经LLM判断内容连贯后自动生成"
            f"（源自超规模枢纽「{hub_path.stem}」的拆分）。\n\n"
            "## 关联原子\n\n"
            f"{member_block}\n"
        )
        new_path.write_text(content, encoding="utf-8")
        for a in members:
            _rewrite_member(a["path"], new_hub_name=name)

    for t in unclustered_titles:
        _rewrite_member(title_to_atom[t]["path"], revert_to_unclustered=True)

    hub_path.unlink()
    print(f"  已删除原枢纽文件: {hub_path.name}")

    return {
        "hub": hub_path.stem,
        "members": len(atoms),
        "new_hubs": [{"name": n, "count": len(m)} for n, _, m in new_hubs],
        "reverted_to_unclustered": len(unclustered_titles),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault-path", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--hub", action="append", required=True, help="要拆分的枢纽文件名(不含.md)，可重复传")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key and not args.dry_run:
        print("❌ 未设置 DEEPSEEK_API_KEY 环境变量")
        raise SystemExit(1)

    project_dir = Path(args.vault_path) / args.project
    results = []
    for hub_name in args.hub:
        hub_path = project_dir / f"{hub_name}.md"
        if not hub_path.exists():
            print(f"❌ 找不到枢纽文件: {hub_path}")
            continue
        results.append(split_hub(hub_path, project_dir, api_key, args.dry_run))

    print("\n=== 汇总 ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
