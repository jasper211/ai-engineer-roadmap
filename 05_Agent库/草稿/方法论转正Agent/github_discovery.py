#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方法论转正Agent · 行业自学习线 · GitHub开源方法论自动发现。

定位：给现有纯人工的"行业自学习线"（Jasper手动把资料喂给Claudian）加一条
自动化雷达——定期从精选GitHub清单（github_sources.json）里发现新的
release/README变化/组织新repo，粗筛+LLM精筛后落到vault的待审区，
供Jasper人工确认后再正式转正进raw/。

边界（不可违反）：本脚本只写vault内的`方法论知识库/行业学习/_待审_GitHub发现/`
目录，从不直接写`raw/`——`raw/`目录的CLAUDE.md明确写着"只能人工放入资料，
AI不主动抓取"，这是刻意定的规则不是疏漏。写入raw/的动作只能由人工（或人工
调用promote_candidate.py）触发。

定时触发不在本脚本内实现（不起循环/sleep），由外部launchd plist
（com.jasper.methodology-github-discovery.plist）每周调用一次
`--scan`，参照PTA daily_sensing.py"定时触发在外部、脚本本身只负责跑一次"
的既有分工模式。

两阶段过滤（控制LLM调用成本）：
1. 规则粗筛（免费）——release正文过短/README diff变化太小/新repo star数不够
   的直接过滤，不进入阶段2。
2. LLM精筛（仅对阶段1幸存者，打包成一次批量调用，不逐条调用）——按候选
   自带的direction字段判断相关性/来源可信度/新增价值，输出结构化JSON。

增量去重：本地JSON状态文件github_discovery_state.json记录每个源的已知
release_id集合/README sha/last_scanned_at。候选指纹只对稳定字段
（owner/repo + release tag，或 owner/repo + readme sha）做sha256，
明确不掺入LLM生成的摘要文本——这是直接复用PTA daily_sensing.py
_task_fingerprint()踩过的真实坑：LLM每次措辞不稳定会导致同一内容被
误判成"新的"，重复产出候选。
"""

import argparse
import base64
import difflib
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from llm_client import call_deepseek, DEFAULT_MODEL, build_ssl_context

# 复用llm_client.py同一份SSL上下文构造——Homebrew装的Python默认证书路径
# 在这台机器上是坏的，urlopen直接用默认context会报CERTIFICATE_VERIFY_FAILED，
# llm_client.py已经踩过这个坑并修过，这里同样需要，不能假设标准库urlopen
# 不传context就能连上https。真实验证时（--seed-baseline首次真实网络调用）
# 立刻复现了这个问题，不是预防性假设。
_SSL_CONTEXT = build_ssl_context()

AGENT_DIR = Path(__file__).resolve().parent
SOURCES_PATH = AGENT_DIR / "github_sources.json"
STATE_PATH = AGENT_DIR / "github_discovery_state.json"
GITHUB_CONFIG_PATH = AGENT_DIR / "github_config.json"
DEEPSEEK_CONFIG_PATH = AGENT_DIR / "deepseek_config.json"

VAULT_PENDING_DIR = Path(
    "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/OB知识库_vault"
    "/方法论知识库/行业学习/_待审_GitHub发现"
)

GITHUB_API = "https://api.github.com"

# 阶段1粗筛阈值——拍脑袋定的初始值，跑几周真实数据后要回来调
MIN_RELEASE_BODY_LEN = 50
MIN_README_DIFF_LINES = 3
DEFAULT_STAR_THRESHOLD = 50

# state里每个release_watch源最多保留多少个已知release_id，避免无限增长
MAX_KNOWN_RELEASE_IDS = 50

RELEVANCE_SYSTEM_PROMPT = """\
你是方法论转正Agent行业自学习线的候选材料精筛助手。输入是若干条已经通过
来源可信度初筛的GitHub变更（release/README更新/组织新repo，均来自Jasper
人工圈定的知名机构/项目清单），你要判断"这条内容本身是否值得进入人工待审
区"，不是判断"这个repo值不值得关注"（那一步已经在清单圈定时做过了）。

每条候选自带一个direction字段，只能取"AI协同方法论"或"流程架构方法论"，
判断范围严格按这个字段来，不要自己扩大或跑题：
- AI协同方法论：是否直接涉及Agent协同机制、人机分工模式、多Agent编排范式、
  Agent验证/评估方法。只是提到"AI""Agent"关键词但内容是纯功能性
  bug fix/依赖升级的要拒绝。
- 流程架构方法论：是否直接涉及流程建模范式、工作流编排设计原则、组织级
  流程治理方法。纯性能优化/UI改动的要拒绝。

三条判断准则：
1. 相关性：是否命中上面方向对应的主题，还是仅字面提及
2. 来源可信度：这条具体变更本身是否有实质内容支撑（说明文字是否有具体
   技术说明/设计动机，而不是空发布或纯自动生成的changelog）
3. 新增判断价值：是否提供了新方法/新框架/新反例/新验证方式，而不是对
   已知内容的重复

来源本身已经是白名单，精筛目标是"排除明显噪音"，不是"做最终收录决定"
（最终决定权在Jasper人工审待审区），倾向可以适度宽松，但必须给出具体
拒绝理由，不能笼统写"不相关"。

严格按以下JSON格式输出，不要输出任何JSON之外的文字：
```json
{
  "results": [
    {
      "id": "候选临时id，原样返回输入里的id字段",
      "is_relevant": true,
      "relevance_reason": "一句话，具体点出命中/未命中的判断依据",
      "info_type_suggestion": "业界实践",
      "evidence_basis_suggestion": "行业佐证",
      "summary": "200-400字摘要，说明这次变更具体讲了什么"
    }
  ]
}
```
info_type_suggestion取值：业界实践 / 学术研究 / 竞品动作
evidence_basis_suggestion取值：内部佐证 / 行业佐证 / 两者皆有
"""


def _load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _fingerprint(*parts: str) -> str:
    raw = "||".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _github_get(path: str, token: str | None, params: dict | None = None):
    """调GitHub REST API，返回解析后的JSON。404时返回None（repo改名/删除的
    容错，不该让整个扫描崩掉），其他错误原样抛出。"""
    url = f"{GITHUB_API}{path}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API请求失败 {url} HTTP {e.code}: {detail}") from e


def load_sources() -> list:
    return _load_json(SOURCES_PATH, default={}).get("sources", [])


def load_state() -> dict:
    return _load_json(STATE_PATH, default={"updated_at": None, "sources": {}})


def save_state(state: dict):
    state["updated_at"] = datetime.now().isoformat()
    _save_json(STATE_PATH, state)


def load_github_token() -> str | None:
    cfg = _load_json(GITHUB_CONFIG_PATH, default={})
    token = cfg.get("GITHUB_TOKEN", "")
    return token if token and not token.startswith("REPLACE_WITH") else None


def load_deepseek_key() -> str | None:
    cfg = _load_json(DEEPSEEK_CONFIG_PATH, default={})
    key = cfg.get("DEEPSEEK_API_KEY", "")
    return key if key and not key.startswith("REPLACE_WITH") else None


# ---------- 分来源类型的扫描函数：返回 (阶段1幸存候选列表, 更新后的source_state) ----------

def scan_release_watch(source: dict, state: dict, token, seed: bool) -> tuple:
    repo = source["repo"]
    releases = _github_get(f"/repos/{repo}/releases", token, params={"per_page": 10}) or []
    src_state = state["sources"].get(source["id"], {"known_release_ids": []})
    known_ids = set(src_state.get("known_release_ids", []))

    survivors = []
    for r in releases:
        rid = r.get("id")
        if rid is None or rid in known_ids:
            continue
        known_ids.add(rid)
        if seed:
            continue
        body = (r.get("body") or "").strip()
        if len(body) < MIN_RELEASE_BODY_LEN:
            continue  # 阶段1过滤：正文太短，典型是纯版本号bump
        survivors.append({
            "source": source,
            "source_type": "release",
            "title": r.get("name") or r.get("tag_name") or "（无标题）",
            "url": r.get("html_url", ""),
            "changed_at": r.get("published_at", ""),
            "body": body,
            "stage1_filter_reason": f"release正文{len(body)}字符，超过{MIN_RELEASE_BODY_LEN}字符阈值放行",
            "fingerprint": _fingerprint(repo, str(rid)),
        })

    src_state["known_release_ids"] = list(known_ids)[-MAX_KNOWN_RELEASE_IDS:]
    src_state["last_scanned_at"] = datetime.now().isoformat()
    return survivors, src_state


def scan_readme_watch(source: dict, state: dict, token, seed: bool) -> tuple:
    repo = source["repo"]
    data = _github_get(f"/repos/{repo}/contents/README.md", token)
    src_state = state["sources"].get(source["id"], {})
    if data is None:
        src_state["last_scanned_at"] = datetime.now().isoformat()
        return [], src_state

    new_sha = data.get("sha", "")
    old_sha = src_state.get("last_readme_sha")
    survivors = []

    if seed:
        content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        src_state["last_readme_sha"] = new_sha
        src_state["last_readme_content"] = content
        src_state["last_scanned_at"] = datetime.now().isoformat()
        return [], src_state

    if new_sha and new_sha != old_sha:
        new_content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        old_content = src_state.get("last_readme_content", "")
        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(), new_content.splitlines(), lineterm=""
        ))
        changed = [l for l in diff_lines if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
        added = [l[1:] for l in changed if l.startswith("+")]
        has_new_heading = any(re.match(r"^#+\s", l) for l in added)
        has_new_link = any(re.search(r"\[.+?\]\(https?://", l) for l in added)

        if len(changed) >= MIN_README_DIFF_LINES and (has_new_heading or has_new_link):
            survivors.append({
                "source": source,
                "source_type": "readme_diff",
                "title": f"{repo} README更新",
                "url": f"https://github.com/{repo}/blob/main/README.md",
                "changed_at": datetime.now().isoformat(),
                "body": "\n".join(added[:80]),  # 截断，避免超长diff塞爆prompt
                "stage1_filter_reason": (
                    f"README变更{len(changed)}行（阈值{MIN_README_DIFF_LINES}），"
                    f"{'含新标题' if has_new_heading else ''}"
                    f"{'含新链接' if has_new_link else ''}"
                ),
                "fingerprint": _fingerprint(repo, new_sha),
            })
        src_state["last_readme_content"] = new_content

    src_state["last_readme_sha"] = new_sha
    src_state["last_scanned_at"] = datetime.now().isoformat()
    return survivors, src_state


def scan_org_new_repo_watch(source: dict, state: dict, token, seed: bool) -> tuple:
    org = source["org"]
    star_threshold = source.get("star_threshold", DEFAULT_STAR_THRESHOLD)
    repos = _github_get(
        f"/orgs/{org}/repos", token,
        params={"type": "public", "sort": "created", "direction": "desc", "per_page": 20},
    ) or []
    src_state = state["sources"].get(source["id"], {})
    last_scanned_at = src_state.get("last_scanned_at")

    survivors = []
    if not seed and last_scanned_at:
        for r in repos:
            created_at = r.get("created_at", "")
            if created_at <= last_scanned_at:
                continue
            stars = r.get("stargazers_count", 0)
            if stars < star_threshold:
                continue  # 阶段1过滤：新repo但star不够，大概率是内部脚手架/实验
            survivors.append({
                "source": source,
                "source_type": "org_new_repo",
                "title": r.get("full_name", ""),
                "url": r.get("html_url", ""),
                "changed_at": created_at,
                "body": r.get("description") or "（无描述）",
                "stage1_filter_reason": f"新repo，{stars}星（阈值{star_threshold}）放行",
                "fingerprint": _fingerprint(org, r.get("full_name", "")),
            })

    src_state["last_scanned_at"] = datetime.now().isoformat()
    return survivors, src_state


SCAN_FUNCS = {
    "release_watch": scan_release_watch,
    "readme_watch": scan_readme_watch,
    "org_new_repo_watch": scan_org_new_repo_watch,
}


# ---------- 阶段2：LLM批量精筛 ----------

def stage2_llm_filter(candidates: list, api_key: str) -> dict:
    """一次批量调用，不逐条调用。返回 {candidate_id: 精筛结果dict}。"""
    payload = {
        "candidates": [
            {
                "id": c["fingerprint"],
                "direction": c["source"]["direction"],
                "title": c["title"],
                "body": c["body"][:2000],  # 截断，控制token
            }
            for c in candidates
        ]
    }
    response = call_deepseek(
        RELEVANCE_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False), api_key,
        model=DEFAULT_MODEL,
    )
    parsed = json.loads(response)
    return {r["id"]: r for r in parsed.get("results", [])}


# ---------- 候选文件写入 ----------

def _slugify(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]', "-", text).strip()
    cleaned = re.sub(r"\s+", "-", cleaned)
    return cleaned[:60] or "untitled"


def write_candidate_file(candidate: dict, llm_result: dict):
    VAULT_PENDING_DIR.mkdir(parents=True, exist_ok=True)
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    repo_or_org = candidate["source"].get("repo") or candidate["source"].get("org", "")
    type_tag = {"release": "release", "readme_diff": "readme-update", "org_new_repo": "new-repo"}[
        candidate["source_type"]
    ]
    filename = f"{date_prefix}_{_slugify(repo_or_org)}_{type_tag}.md"
    path = VAULT_PENDING_DIR / filename

    content = f"""---
status: pending_review
discovered_at: {datetime.now().isoformat()}
source_type: {candidate['source_type']}
source_repo: {repo_or_org}
source_url: {candidate['url']}
direction: {candidate['source']['direction']}
relevance_reason: {llm_result.get('relevance_reason', '')}
info_type_suggestion: {llm_result.get('info_type_suggestion', '')}
evidence_basis_suggestion: {llm_result.get('evidence_basis_suggestion', '')}
stage1_filter_reason: {candidate['stage1_filter_reason']}
---

# 摘要

{llm_result.get('summary', '')}

## 原始信息

- 标题/来源: {candidate['title']}
- 发布/变更时间: {candidate['changed_at']}
- 原文链接: {candidate['url']}
- 原文摘录（截断）:

```
{candidate['body'][:1500]}
```

## 人工确认后如何操作

确认收录：`python3 promote_candidate.py {filename} --promote`
（或手动：把上面"摘要+原始信息"整理后另存为 raw/ 下的新md文件，frontmatter
补齐 collected_at/staleness_review_date，source_url/info_type/evidence_basis
从建议值确认或改写后带过去）

不收录：`python3 promote_candidate.py {filename} --reject --reason "..."`
"""
    path.write_text(content, encoding="utf-8")
    return path


# ---------- 主流程 ----------

def run_scan(seed: bool = False, dry_run: bool = False, quiet: bool = False):
    sources = load_sources()
    state = load_state()
    token = load_github_token()

    if not token and not quiet:
        print("  ⚠️ 未配置GITHUB_TOKEN（github_config.json），走未认证请求，限流60次/小时")

    all_survivors = []
    for source in sources:
        scan_type = source.get("type")
        func = SCAN_FUNCS.get(scan_type)
        if func is None:
            print(f"  ❌ 未知source类型: {scan_type}（source id={source.get('id')}）")
            continue
        try:
            survivors, src_state = func(source, state, token, seed)
        except Exception as e:
            print(f"  ❌ 扫描失败 {source.get('id')}: {e}")
            continue
        if not dry_run:
            state["sources"][source["id"]] = src_state
        all_survivors.extend(survivors)
        if not quiet:
            print(f"  {source['id']}: 阶段1幸存 {len(survivors)} 条")

    if seed:
        if not dry_run:
            save_state(state)
        if not quiet:
            print(f"✅ 基线已建立，{len(sources)}个源，不产出候选")
        return

    if not all_survivors:
        if not dry_run:
            save_state(state)
        if not quiet:
            print("本轮无阶段1幸存候选，不调用LLM")
        return

    if dry_run:
        if not quiet:
            print(f"[dry-run] 阶段1幸存共{len(all_survivors)}条，不调用LLM/不写候选文件/不更新state：")
            for c in all_survivors:
                print(f"  - [{c['source']['direction']}] {c['title']} ({c['stage1_filter_reason']})")
        return

    api_key = load_deepseek_key()
    if not api_key:
        print("❌ 未配置DEEPSEEK_API_KEY（deepseek_config.json），无法做阶段2精筛，本轮终止且不更新state")
        sys.exit(1)

    llm_results = stage2_llm_filter(all_survivors, api_key)

    written = 0
    for c in all_survivors:
        result = llm_results.get(c["fingerprint"])
        if result is None:
            print(f"  ⚠️ LLM返回结果里缺失候选 {c['fingerprint']}（{c['title']}），跳过")
            continue
        if not result.get("is_relevant", False):
            if not quiet:
                print(f"  ⏭️ LLM判不相关: {c['title']}（{result.get('relevance_reason', '')}）")
            continue
        path = write_candidate_file(c, result)
        written += 1
        if not quiet:
            print(f"  ✅ 落候选: {path.name}")

    save_state(state)
    if not quiet:
        print(f"本轮完成：阶段1幸存{len(all_survivors)}条 → LLM精筛通过{written}条，已落待审区")


def main():
    parser = argparse.ArgumentParser(description="GitHub开源方法论自动发现")
    parser.add_argument("--seed-baseline", action="store_true", help="首次运行，建立基线不产出候选")
    parser.add_argument("--scan", action="store_true", help="增量扫描")
    parser.add_argument("--dry-run", action="store_true", help="只跑到阶段1粗筛，不调用LLM/不写文件/不更新state")
    parser.add_argument("--quiet", action="store_true", help="减少输出")
    args = parser.parse_args()

    if not args.seed_baseline and not args.scan:
        parser.error("必须指定 --seed-baseline 或 --scan 之一")

    run_scan(seed=args.seed_baseline, dry_run=args.dry_run, quiet=args.quiet)


if __name__ == "__main__":
    main()
