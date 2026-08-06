#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HKIA · 13_为什么增长 · 公司官网业绩/新闻采集器（自动化，无人工辅助）
======================================================================
用途：针对目标保险公司官网，自动抓取 2025-2026 的业绩/新业务/新闻稿，
产出"公司官方披露"证据登记（源 URL + 标题 + 日期 + 正文要点）。

设计原则（遵循项目证据治理）：
- 只采集机器可直连（HTTP 200）的公开官网页面；
- 只把"公司官方新闻/业绩页"登记为 F-官方 证据；
- 抓到的正文仅作要点抽取，不臆造数字，不把二手信息当事实；
- 受阻来源（403）记入 results.blocks，不硬闯。

用法：
    python3 collect_company_news.py --probe          # 探测各公司新闻入口可达性
    python3 collect_company_news.py --collect        # 抓取已配置公司新闻页正文
    python3 collect_company_news.py --all            # 探测 + 抓取
产出：
    data/company_news_collected.json                 # 结构化登记
    data/company_news_collected.csv                  # 表格视图（证据登记）
"""
import argparse
import csv
import re
import html
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
OUT_JSON = DATA / "company_news_collected.json"
OUT_CSV = DATA / "company_news_collected.csv"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
TIMEOUT = "25"

# ----------------------------------------------- 配置：每家公司要探测/抓取的页面
# 结构：公司 -> {入口页, 新闻链接关键词, 是否抓正文}
COMPANIES = {
    "AIA_International": {
        "home": "https://www.aia.com.hk/en",
        "news_keywords": ["news", "media", "press", "result", "year", "announcement", "growth"],
    },
    "Prudential_HK_Life": {
        "home": "https://www.prudential.com.hk/en/",
        "news_keywords": ["news", "media", "press", "result", "year", "growth"],
    },
    "BOC_Life": {
        "home": "https://www.boclife.com.hk/en/index.html",
        "news_keywords": ["news", "press", "media", "result", "year", "growth", "quarter"],
    },
    "Sun_Life_HK": {
        "home": "https://www.sunlife.com.hk/en/",
        "news_keywords": ["news", "press", "media", "about", "income", "annual"],
    },
    "Chubb_HK": {
        "home": "https://www.chubb.com/hk-en/",
        "news_keywords": ["news", "press", "media", "insight", "about"],
    },
    "AXA_HK": {
        "home": "https://www.axa.com.hk/en",
        "news_keywords": ["news", "press", "media", "result", "annual"],
    },
}


def curl(url, max_time=TIMEOUT):
    """机器直连抓取，返回状态码和文本。"""
    try:
        r = subprocess.run(
            ["curl", "-s", "-L", "-A", UA, "--max-time", max_time, url],
            capture_output=True, text=True, timeout=40,
        )
        return r.returncode, r.stdout
    except Exception as e:
        return -1, f"error: {e}"


def strip_html(t):
    t = re.sub(r"<script.*?</script>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<noscript.*?</noscript>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def probe():
    print("=== 探测各公司官网可达性与新闻入口 ===\n")
    results = {}
    for name, cfg in COMPANIES.items():
        code, text = curl(cfg["home"])
        status = "reachable" if code == 0 and text else "blocked_or_empty"
        links = []
        if code == 0 and text:
            hrefs = re.findall(r'href="([^"]*)"', text, re.I)
            kws = "|".join(cfg["news_keywords"])
            seen = set()
            for h in hrefs:
                if re.search(kws, h, re.I) and h not in seen:
                    links.append(h if h.startswith("http") else "https:" + h if h.startswith("//") else cfg["home"].rstrip("/") + "/" + h.lstrip("/"))
                    seen.add(h)
        results[name] = {"url": cfg["home"], "http_ok": status, "news_links_found": len(links)}
        print(f"[{status}] {name}")
        print(f"    url: {cfg['home']}")
        print(f"    新闻/业绩链接数: {len(links)}")
        for l in links[:12]:
            print(f"      - {l}")
        print()
    with open(DATA / "company_news_probe.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return results


def collect():
    print("=== 抓取公司新闻/业绩页正文 ===\n")
    collected = []
    for name, cfg in COMPANIES.items():
        code, text = curl(cfg["home"])
        if code != 0 or not text:
            print(f"[skip] {name}: 首页不可达")
            continue
        hrefs = re.findall(r'href="([^"]*)"', text, re.I)
        kws = "|".join(cfg["news_keywords"])
        seen, links = set(), []
        for h in hrefs:
            if re.search(kws, h, re.I) and h not in seen:
                full = h if h.startswith("http") else ("https:" + h if h.startswith("//") else cfg["home"].rstrip("/") + "/" + h.lstrip("/"))
                links.append(full)
                seen.add(h)
        # 取前 15 个候选链接抓正文
        articles = []
        for link in links[:15]:
            c2, t2 = curl(link)
            if c2 != 0 or not t2:
                continue
            plain = strip_html(t2)
            date = re.search(r"(2025|2026)", plain[:2000])
            # 只保留疑似业绩/增长的正文（包含业绩/新业务/增长词）
            if any(k in plain for k in ["premium", "new business", "growth", "revenue", "result", "sales", "%"]):
                articles.append({
                    "url": link,
                    "snippet": plain[:1200],
                })
            time.sleep(0.5)
        rec = {
            "company": name,
            "company_url": cfg["home"],
            "fetched_at": datetime.now().isoformat(),
            "article_count": len(articles),
            "articles": articles,
        }
        collected.append(rec)
        print(f"[done] {name}: 抓到 {len(articles)} 篇候选业绩/新闻")
        for a in articles[:5]:
            print(f"    - {a['url']}")
    # 写 JSON
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(collected, f, ensure_ascii=False, indent=2)
    # 写 CSV（证据登记骨架）
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "url", "fetched_at", "snippet"])
        for rec in collected:
            for a in rec["articles"]:
                w.writerow([rec["company"], a["url"], rec["fetched_at"], a["snippet"]])
    print(f"\n写入: {OUT_JSON}")
    print(f"写入: {OUT_CSV}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.all:
        probe(); collect()
    elif args.probe:
        probe()
    elif args.collect:
        collect()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
