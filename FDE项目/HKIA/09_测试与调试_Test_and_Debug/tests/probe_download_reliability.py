#!/usr/bin/env python3
"""
HKIA 数据源下载可靠性探测脚本 —— 在本机运行，不在任何沙盒/CI环境里运行。

背景：AI 助手在沙盒化的浏览器环境里测试 IA 官网/data.gov.hk 的文件下载时，
结果不稳定（同一个文件请求有时 403，有时验证通过后拿到 200），且沙盒既不能
保存下载到的文件做内容核验，也无法安装真实的本地 Playwright 做决定性测试。
这个脚本就是那个决定性测试，需要你在自己电脑上跑一次。

用法：
    pip install playwright
    playwright install chromium
    python3 probe_download_reliability.py

会依次做 3 组测试，每组用不同方式尝试拿到同一份文件（2023年长期业务H1的
HKLQ1-1中文表），跑完打印汇总，你把汇总结果发回来就行，不用自己看懂细节：

  A. 从 data.gov.hk 数据集页面真实点击"下載"链接（最贴近真人操作）
  B. 直接用 URL 跳转到 ia.org.hk 原始文件直链（无 referrer/页面上下文）
  C. 直接用 URL 跳转到 data.gov.hk 的代理下载接口

跑完看 hkia_probe_downloads/ 目录里有没有真实 CSV 文件、内容对不对。
"""
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from pathlib import Path
import sys

DOWNLOAD_DIR = Path(__file__).parent / "hkia_probe_downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

DATASET_PAGE = "https://data.gov.hk/tc-data/dataset/ia-ialtb-lstatsq2023q2"
DIRECT_IA_URL = "https://www.ia.org.hk/tc/infocenter/statistics/files/2q23long_Form_HKLQ1-1_C.csv"
PROXY_URL = (
    "https://res.data.gov.hk/api/get-download-file?name="
    "https%3A%2F%2Fwww.ia.org.hk%2Ftc%2Finfocenter%2Fstatistics%2Ffiles%2F"
    "2q23long_Form_HKLQ1-1_C.csv"
)


def looks_like_real_csv(text: str) -> bool:
    head = text[:200]
    if "Just a moment" in head or "安全驗證" in head or "安全验证" in head:
        return False
    if head.strip().startswith("<!DOCTYPE") or head.strip().startswith("<html"):
        return False
    return True


def save_and_check(save_path: Path) -> tuple[bool, str]:
    try:
        with open(save_path, "r", encoding="utf-8-sig", errors="replace") as f:
            content = f.read(500)
        ok = looks_like_real_csv(content)
        return ok, content[:200].replace("\n", " ")
    except Exception as e:
        return False, f"读取失败: {e}"


def test_via_click(page):
    print("\n=== 测试 A：从 data.gov.hk 数据集页面真实点击下载 ===")
    try:
        page.goto(DATASET_PAGE, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        # 找到 "HKLQ1-1" + "繁體中文" 那一行里的"下載"链接
        row = page.locator("text=HKLQ1-1").first
        row.scroll_into_view_if_needed(timeout=10000)
        download_link = page.locator("a:has-text('下載')").first
        with page.expect_download(timeout=20000) as dl_info:
            download_link.click()
        download = dl_info.value
        save_path = DOWNLOAD_DIR / f"A_{download.suggested_filename}"
        download.save_as(save_path)
        ok, preview = save_and_check(save_path)
        print(f"{'✅ 成功' if ok else '⚠️ 下载了但内容像是验证页/HTML，不是真CSV'}，"
              f"文件: {save_path.name} ({save_path.stat().st_size} 字节)")
        print(f"内容预览: {preview}")
        return ok
    except PWTimeout:
        print("❌ 超时：没有触发下载事件（可能是普通页面渲染，不是文件下载）")
        return False
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


def test_direct_nav(page, url: str, label: str, tag: str):
    print(f"\n=== 测试 {tag}：直接跳转 {label} ===")
    try:
        with page.expect_download(timeout=20000) as dl_info:
            page.goto(url, timeout=25000)
        download = dl_info.value
        save_path = DOWNLOAD_DIR / f"{tag}_{download.suggested_filename}"
        download.save_as(save_path)
        ok, preview = save_and_check(save_path)
        print(f"{'✅ 成功' if ok else '⚠️ 下载了但内容像是验证页/HTML，不是真CSV'}，"
              f"文件: {save_path.name} ({save_path.stat().st_size} 字节)")
        print(f"内容预览: {preview}")
        return ok
    except PWTimeout:
        # 没触发下载事件，可能是直接把内容渲染在页面上了，去读页面文本判断
        try:
            content = page.content()
            ok = looks_like_real_csv(content)
            print(f"{'✅ 页面直接渲染了内容，看起来是真数据' if ok else '❌ 页面是验证页/错误页，不是真数据'}")
            print(f"内容预览: {content[:200]}")
            return ok
        except Exception as e:
            print(f"❌ 失败: {e}")
            return False
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


def main():
    headless = "--headless" in sys.argv
    print(f"运行模式: {'headless' if headless else 'headed（会弹出浏览器窗口，建议先用这个）'}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        results = {}
        results["A_点击真实下载"] = test_via_click(page)
        results["B_直连ia.org.hk"] = test_direct_nav(page, DIRECT_IA_URL, "ia.org.hk 原始CSV直链", "B")
        results["C_data.gov.hk代理"] = test_direct_nav(page, PROXY_URL, "data.gov.hk 代理下载接口", "C")

        browser.close()

    print("\n\n========== 汇总（把这段发给我）==========")
    for name, ok in results.items():
        print(f"{name}: {'✅ 可行' if ok else '❌ 不可行'}")
    print(f"\n下载到的文件（如有）在: {DOWNLOAD_DIR}")


if __name__ == "__main__":
    main()
