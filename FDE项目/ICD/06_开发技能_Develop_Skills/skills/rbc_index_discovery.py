#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICD · skills/rbc_index_discovery.py · RBC 官方索引 → 2024 英文 Disclosure Statement PDF 链接发现

职责边界：纯函数，从官方监管披露**索引页 HTML** 中确定性地定位目标 RBC 披露声明 PDF
链接。不访问网络（索引字节已由 L3-ICD-02 抓取并固化为快照）、不写库、不猜测 URL——
只依据「官方域名 + 报告年度 + 英文 + Disclosure Statement 语义」三重约束筛选链接，并对
歧义做确定性失败，绝不凭搜索结果或文件名猜测（文件名仅作为**已登记证据**的选择器，
最终法律主体必须由 PDF 文本层的 "Authorized/Authorised insurer's name" 独立核实）。

对齐任务书 T008 功能要求 1/6：
- 限定官方域名（相对链接解析到官方域名；绝对链接必须落在允许域名内）。
- 限定报告年度（文件名含目标年度，如 "2024"）。
- 限定英文（文件名含 "eng"/"_eng"，或路径含 "/en/"）。
- 限定 Disclosure Statement 语义（文件名或锚文本含 "disclosure statement"）。
- 链接歧义 / 零匹配 → RbcIndexDiscoveryError（确定性失败）。
"""

import re
import urllib.parse
from html.parser import HTMLParser
from typing import List, Optional, Tuple

# 官方域名（AIA 集团 investor relations 站点）
DEFAULT_BASE_URL = "https://www.aia.com"
DEFAULT_ALLOWED_DOMAINS = ("aia.com",)


class RbcIndexDiscoveryError(Exception):
    """索引发现失败（零匹配 / 歧义 / 越界域名），对应确定性失败语义。"""


class _AnchorCollector(HTMLParser):
    """收集 <a href="...">可见文本</a>（不执行脚本、不请求外部资源）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[Tuple[str, str]] = []
        self._href: Optional[str] = None
        self._buf: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self._href = href
                self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self.anchors.append((self._href, text))
            self._href = None
            self._buf = []


def _filename_of(href: str) -> str:
    """取 URL 路径末段文件名（URL 解码）。"""
    path = urllib.parse.urlsplit(href).path
    return urllib.parse.unquote(path.rstrip("/").rsplit("/", 1)[-1])


def _resolve(href: str, base_url: str) -> str:
    return urllib.parse.urljoin(base_url, href)


def _host_allowed(url: str, allowed_domains: Tuple[str, ...]) -> bool:
    host = urllib.parse.urlsplit(url).netloc.lower()
    if not host:
        return True  # 相对链接已解析到 base，netloc 必有；此处防御
    host = host.rsplit("@", 1)[-1].rsplit(":", 1)[0]
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


def extract_disclosure_pdf_candidates(
    html: bytes,
    *,
    base_url: str = DEFAULT_BASE_URL,
    allowed_domains: Tuple[str, ...] = DEFAULT_ALLOWED_DOMAINS,
    report_year: int = 2024,
) -> List[str]:
    """从索引页 HTML 提取全部候选 PDF 链接（官方域名 + 年度 + 英文 + Disclosure Statement）。

    返回去重后的完整 URL 列表（保持出现顺序）。不满足任一约束的链接被排除。
    """
    parser = _AnchorCollector()
    parser.feed(html.decode("utf-8", errors="replace"))

    candidates: List[str] = []
    seen = set()
    year = str(report_year)
    for href, text in parser.anchors:
        if not href:
            continue
        href = href.strip()
        # 1) 仅 PDF
        if not href.lower().split("?", 1)[0].split("#", 1)[0].endswith(".pdf"):
            continue
        # 2) 限定官方域名
        full = _resolve(href, base_url)
        if not _host_allowed(full, allowed_domains):
            continue
        fname = _filename_of(href).lower()
        blob = f"{fname} {text}".lower()
        # 3) Disclosure Statement 语义
        if "disclosure statement" not in blob and "disclosure statement" not in fname:
            continue
        # 4) 报告年度
        if year not in fname:
            continue
        # 5) 英文
        if "eng" not in fname and "/en/" not in href.lower():
            continue
        if full not in seen:
            seen.add(full)
            candidates.append(full)
    return candidates


def discover_disclosure_pdf(
    html: bytes,
    *,
    base_url: str = DEFAULT_BASE_URL,
    allowed_domains: Tuple[str, ...] = DEFAULT_ALLOWED_DOMAINS,
    report_year: int = 2024,
    filename_hint: Optional[str] = None,
) -> str:
    """确定性地定位唯一目标 PDF 链接；歧义/零匹配 → RbcIndexDiscoveryError。

    filename_hint 为已登记证据（注册表 parser_hint 中的目标文件名，如
    "AIA Co Disclosure Statement 2024_Eng.pdf"）：仅用于在多个候选（同一索引可能同时
    列出多个不同持牌实体的 2024 英文 Disclosure Statement）中做**选择**，最终法律主体
    仍须由 PDF 文本层 "Authorized/Authorised insurer's name" 独立核实。
    """
    candidates = extract_disclosure_pdf_candidates(
        html, base_url=base_url, allowed_domains=allowed_domains, report_year=report_year
    )
    if not candidates:
        raise RbcIndexDiscoveryError(
            f"索引页未找到 {report_year} 英文 Disclosure Statement PDF（官方域名/年度/英文/语义约束均不满足）"
        )

    if filename_hint:
        hint = filename_hint.lower()
        matched = [c for c in candidates if hint in _filename_of(c).lower()]
        if len(matched) == 1:
            return matched[0]
        if len(matched) == 0:
            raise RbcIndexDiscoveryError(
                f"索引页候选 PDF 均不匹配已登记目标文件名 {filename_hint!r}（候选: {len(candidates)}）"
            )
        raise RbcIndexDiscoveryError(
            f"目标文件名 {filename_hint!r} 命中 {len(matched)} 个 PDF，歧义，无法唯一定位"
        )

    if len(candidates) == 1:
        return candidates[0]
    raise RbcIndexDiscoveryError(
        f"索引页存在 {len(candidates)} 个 {report_year} 英文 Disclosure Statement PDF，需提供已登记目标文件名消歧"
    )
