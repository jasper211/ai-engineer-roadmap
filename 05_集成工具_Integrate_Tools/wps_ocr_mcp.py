#!/usr/bin/env python3
"""WPS 扫描件 OCR 补充 MCP —— 读扫描件 PDF 的正文。

WPS 开放平台不提供 OCR：`drive_file_content_get` 对扫描件返回
`src_format_detail: PDF-scan` 但没有正文。而合同、尽调材料这类归档件大多是扫描件。

方案：下载后用 **macOS 自带的 PDFKit + Vision** 本地识别。
- 零第三方依赖：不需要 pip、不需要 brew，系统自带 swift 编译器即可
- 数据不出本机：适合保单号、客户信息这类敏感内容
- 中文质量好：Apple 的识别引擎对简繁混排合同表现优于 tesseract

**多平台自适应**，按可用性自动选引擎：
  macOS   → PDFKit + Vision（系统自带，零依赖，已实测）
  Windows → pypdfium2 渲染 + Windows.Media.Ocr（系统自带 OCR，需 pip 装 pypdfium2）
  任意平台 → pypdfium2 渲染 + tesseract（需另行安装）
用 `ocr_status` 工具可查当前机器缺什么、该装什么。
凭证完全交给 wps365-cli，本文件不碰 token。

⚠️ stdout 只允许 JSON-RPC，日志一律走 stderr。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

SERVER_NAME = "wps-ocr"
SERVER_VERSION = "1.0.0"
PROTOCOL_FALLBACK = "2024-11-05"
CACHE_DIR = Path(os.environ.get("WPS_OCR_CACHE") or (Path.home() / ".cache/wps-ocr"))
MAX_PAGES_DEFAULT = 10
MAX_CHARS = 60000

SWIFT_SRC = r'''
import Foundation
import PDFKit
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("cannot open pdf\n".data(using: .utf8)!); exit(2)
}
let from = args.count > 2 ? max(0, (Int(args[2]) ?? 1) - 1) : 0
let to   = args.count > 3 ? min(doc.pageCount, Int(args[3]) ?? doc.pageCount) : doc.pageCount
print("PAGECOUNT \(doc.pageCount)")
for i in from..<to {
    guard let page = doc.page(at: i) else { continue }
    let box = page.bounds(for: .mediaBox)
    // 放大 2 倍再识别：小字准确率明显更高
    let thumb = page.thumbnail(of: NSSize(width: box.width * 2, height: box.height * 2), for: .mediaBox)
    guard let cg = thumb.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
    req.usesLanguageCorrection = true
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    print("===== 第 \(i + 1) 页 =====")
    for obs in (req.results ?? []) {
        if let line = obs.topCandidates(1).first?.string { print(line) }
    }
}
'''


PLATFORM_HINT = {
    "darwin": "macOS 应已自带，若提示缺 swift 编译器：xcode-select --install",
    "win32": ("方式一（推荐，系统自带OCR）：pip install pypdfium2，"
              "并在「设置 > 时间和语言 > 语言」中为中文添加「光学字符识别」可选功能\n"
              "方式二：pip install pypdfium2 + 安装 tesseract "
              "(https://github.com/UB-Mannheim/tesseract/wiki，安装时勾选 Chinese 语言包)"),
    "linux": ("pip install pypdfium2 && "
              "sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra"),
}


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _pypdfium_ok() -> bool:
    try:
        import pypdfium2  # noqa: F401
        return True
    except ImportError:
        return False


def detect_engine() -> tuple[str | None, str]:
    """返回 (可用引擎, 说明)。优先用系统自带、零依赖的方案。"""
    if sys.platform == "darwin" and (_has("swiftc") or Path("/usr/bin/swiftc").exists()):
        return "vision", "macOS Vision（系统自带，数据不出本机）"
    if sys.platform == "win32" and _pypdfium_ok():
        if _has("powershell") or _has("pwsh"):
            return "winocr", "Windows.Media.Ocr（系统自带，数据不出本机）"
    if _pypdfium_ok() and _has("tesseract"):
        return "tesseract", "tesseract（本地识别，数据不出本机）"
    return None, "当前机器没有可用的 OCR 引擎"


class ToolError(Exception):
    pass


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def find_cli() -> str:
    for c in (os.environ.get("WPS365_CLI"), str(Path.home() / ".local/bin/wps365-cli"),
              "/usr/local/bin/wps365-cli"):
        if c and Path(c).exists():
            return c
    found = shutil.which("wps365-cli")
    if found:
        return found
    raise ToolError("找不到 wps365-cli，请先安装官方 CLI")


def cli_json(args: list[str]) -> dict:
    proc = subprocess.run([find_cli(), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    raw = (proc.stdout or "").strip()
    if not raw.startswith("{"):
        raise ToolError((proc.stderr or raw).strip()[:400])
    payload = json.loads(raw)
    if payload.get("code") not in (0, None):
        raise ToolError(f"接口失败 code={payload.get('code')} msg={payload.get('msg')}")
    return payload.get("data", payload)


def ensure_ocr_binary() -> Path:
    """macOS：首次编译成二进制并缓存，之后省掉约 5 秒编译时间。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    src, binary = CACHE_DIR / "ocr.swift", CACHE_DIR / "wps_ocr"
    if not binary.exists() or not src.exists() or src.read_text(encoding="utf-8") != SWIFT_SRC:
        src.write_text(SWIFT_SRC, encoding="utf-8")
        log("首次使用，正在编译 OCR 组件（约 10 秒，仅此一次）…")
        proc = subprocess.run(["swiftc", "-O", "-o", str(binary), str(src)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if proc.returncode != 0:
            raise ToolError(f"OCR 组件编译失败：{proc.stderr[:400]}")
    return binary


def ocr_vision(pdf: bytes, start: int, limit: int) -> tuple[str, int | None]:
    """macOS：PDFKit 渲染 + Vision 识别，全部系统框架。已实测。"""
    binary = ensure_ocr_binary()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(pdf)
        tmp = fh.name
    try:
        proc = subprocess.run([str(binary), tmp, str(start), str(start + limit - 1)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    finally:
        os.unlink(tmp)
    if proc.returncode != 0:
        raise ToolError(f"OCR 执行失败：{(proc.stderr or proc.stdout)[:300]}")
    lines, total = [], None
    for line in proc.stdout.splitlines():
        if line.startswith("PAGECOUNT "):
            total = int(line.split()[1])
        else:
            lines.append(line)
    return "\n".join(lines), total


def _render_pages(pdf: bytes, start: int, limit: int):
    """非 macOS 路径的公共环节：用 pypdfium2 把 PDF 页渲染成 PNG 文件。"""
    import pypdfium2 as pdfium
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(pdf)
        pdf_path = fh.name
    try:
        doc = pdfium.PdfDocument(pdf_path)
        total = len(doc)
        out = []
        for idx in range(start - 1, min(start - 1 + limit, total)):
            img = doc[idx].render(scale=2).to_pil()   # 放大2倍，小字准确率明显更高
            png = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
            img.save(png)
            out.append((idx + 1, png))
        return out, total
    finally:
        os.unlink(pdf_path)


def ocr_tesseract(pdf: bytes, start: int, limit: int) -> tuple[str, int | None]:
    """任意平台：pypdfium2 渲染 + tesseract 识别。⚠️ 代码路径未在本机实测。"""
    pages, total = _render_pages(pdf, start, limit)
    chunks = []
    for num, png in pages:
        try:
            proc = subprocess.run(
                ["tesseract", png, "stdout", "-l", "chi_sim+chi_tra+eng"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            text = proc.stdout.strip()
            if proc.returncode != 0 and not text:
                raise ToolError(f"tesseract 执行失败：{proc.stderr[:200]}\n"
                                "常见原因：未安装中文语言包 chi_sim / chi_tra")
        finally:
            os.unlink(png)
        chunks.append(f"===== 第 {num} 页 =====\n{text}")
    return "\n".join(chunks), total


WINOCR_PS = r"""
param([string]$ImagePath, [string]$Lang = "zh-Hans")
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $asTask.MakeGenericMethod($type).Invoke($null, @($op)).GetAwaiter().GetResult() }
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] > $null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime] > $null
[Windows.Media.Ocr.OcrEngine,Windows.Media.Ocr,ContentType=WindowsRuntime] > $null
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Lang))
if ($null -eq $engine) { Write-Error "系统缺少 $Lang 的OCR语言包，请在「设置>语言>可选功能」中添加「光学字符识别」"; exit 3 }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) { $line.Text }
"""


def ocr_winocr(pdf: bytes, start: int, limit: int) -> tuple[str, int | None]:
    """Windows：pypdfium2 渲染 + 系统自带 Windows.Media.Ocr。⚠️ 未在本机实测。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ps_file = CACHE_DIR / "winocr.ps1"
    if not ps_file.exists() or ps_file.read_text(encoding="utf-8") != WINOCR_PS:
        ps_file.write_text(WINOCR_PS, encoding="utf-8")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    pages, total = _render_pages(pdf, start, limit)
    chunks = []
    for num, png in pages:
        try:
            proc = subprocess.run(
                [shell, "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(ps_file), "-ImagePath", png],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            if proc.returncode != 0:
                raise ToolError(f"Windows OCR 失败：{(proc.stderr or '')[:300]}")
            text = proc.stdout.strip()
        finally:
            os.unlink(png)
        chunks.append(f"===== 第 {num} 页 =====\n{text}")
    return "\n".join(chunks), total


ENGINE_FN = {"vision": ocr_vision, "tesseract": ocr_tesseract, "winocr": ocr_winocr}


def fetch_pdf(file_id: str, drive_id: str | None) -> tuple[bytes, str]:
    meta = cli_json(["api", "get", f"/v7/files/{file_id}/meta"])
    name = str(meta.get("name", file_id))
    drive_id = drive_id or str(meta.get("drive_id", ""))
    if not drive_id:
        raise ToolError("拿不到 drive_id")
    url = cli_json(["api", "get", f"/v7/drives/{drive_id}/files/{file_id}/download"])["url"]
    token = subprocess.run([find_cli(), "auth", "token"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60).stdout.strip().strip('"')
    if not token:
        raise ToolError("拿不到访问令牌，请先 wps365-cli auth login --device")
    # 用 curl 而非 urllib：python.org 的解释器不带 CA 根证书，urllib 会握手失败；
    # curl 走系统证书链，macOS 上一定可用。
    # 另注意这个临时下载地址必须带 Bearer 头，裸请求返回 403 userNotLogin。
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        dest = fh.name
    try:
        proc = subprocess.run(
            ["curl", "-fsSL", "--max-time", "120", "-H", f"Authorization: Bearer {token}",
             "-o", dest, url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        if proc.returncode != 0:
            raise ToolError(f"下载失败：{(proc.stderr or '').strip()[:200]}")
        blob = Path(dest).read_bytes()
    finally:
        try:
            os.unlink(dest)
        except OSError:
            pass
    if not blob:
        raise ToolError("下载到的文件为空")
    return blob, name


def t_status(_: dict) -> str:
    """让使用者/Agent 一眼看清本机能不能做 OCR、缺什么、怎么补。"""
    engine, desc = detect_engine()
    plat = {"darwin": "macOS", "win32": "Windows", "linux": "Linux"}.get(sys.platform, sys.platform)
    lines = [f"平台：{plat}", f"OCR 引擎：{desc}"]
    if engine:
        lines.append("状态：✅ 可用，直接调用 ocr_scanned_pdf 即可")
    else:
        lines.append("状态：❌ 不可用，扫描件读不出正文")
        lines.append("")
        lines.append("安装方式：")
        key = "linux" if sys.platform.startswith("linux") else sys.platform
        lines.append(PLATFORM_HINT.get(key, "请安装 pypdfium2 与 tesseract"))
        lines.append("")
        lines.append("检查项：")
        lines.append(f"  pypdfium2（PDF转图像）: {'✅' if _pypdfium_ok() else '❌ pip install pypdfium2'}")
        lines.append(f"  tesseract            : {'✅' if _has('tesseract') else '❌ 见上方安装方式'}")
        if sys.platform == "darwin":
            lines.append(f"  swiftc（macOS原生）   : {'✅' if _has('swiftc') else '❌ xcode-select --install'}")
    lines.append("")
    lines.append("说明：所有引擎均为本地识别，内容不会发送给任何第三方。")
    return "\n".join(lines)


def t_ocr(args: dict) -> str:
    engine, desc = detect_engine()
    if not engine:
        raise ToolError(f"本机没有可用的 OCR 引擎。\n\n{t_status({})}")

    file_id = args["file_id"]
    blob, name = fetch_pdf(file_id, args.get("drive_id"))
    if blob[:5] != b"%PDF-":
        raise ToolError(f"{name} 不是 PDF，本工具只处理扫描件 PDF")

    fonts = blob.count(b"/Font")
    if fonts > 0 and not args.get("force"):
        return (f"{name} 有文本层（检出 {fonts} 处字体），**不需要 OCR**。\n"
                f"请改用官方工具 drive_file_content_get 直接取正文，又快又准。\n"
                f"（确实要强制 OCR 就传 force=true）")

    start = max(int(args.get("from_page", 1)), 1)
    limit = min(int(args.get("max_pages", MAX_PAGES_DEFAULT)), 50)
    text, total = ENGINE_FN[engine](blob, start, limit)
    text = text.strip() or "(没有识别出文字，可能是空白页或图像质量过低)"

    end = min(start + limit - 1, total or start + limit - 1)
    head = f"{name}｜扫描件 OCR（{desc}）\n"
    head += f"共 {total} 页，本次识别第 {start}~{end} 页\n" if total else ""
    if total and end < total:
        head += f"还有 {total - end} 页未识别，用 from_page 继续\n"
    head += "⚠️ OCR 结果可能有错字，关键数字（金额、证件号、账号）请回原件核对\n"
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n…（已截断，请缩小页范围）"
    return head + "\n" + text


TOOLS = [
    {"name": "ocr_status",
     "description": "查看本机的扫描件OCR能力：用的哪个引擎、是否可用、不可用时该装什么（按当前操作系统给出具体命令）。安装后或遇到OCR报错时先调这个。",
     "inputSchema": {"type": "object", "properties": {}}, "_fn": t_status},
    {"name": "ocr_scanned_pdf",
     "description": "对扫描件PDF做本地OCR取出正文（自动选用本机可用引擎：macOS用系统Vision、Windows用系统OCR、其他用tesseract；一律本地识别，数据不出本机）。WPS平台不提供OCR，扫描件用官方 drive_file_content_get 只会返回空内容——遇到那种情况就用本工具。有文本层的PDF会提示改用官方工具，不浪费时间。逐页识别较慢（约2-3秒/页），默认只识别前10页，长文档用 from_page 分批。",
     "inputSchema": {"type": "object", "properties": {
         "file_id": {"type": "string", "description": "文件ID，由 drive_file_search / drive_file_list 获得"},
         "drive_id": {"type": "string", "description": "可选，不传会自动查"},
         "from_page": {"type": "integer", "description": "从第几页开始，默认1"},
         "max_pages": {"type": "integer", "description": "最多识别几页，默认10，上限50"},
         "force": {"type": "boolean", "description": "对有文本层的PDF也强制OCR，默认false"}},
         "required": ["file_id"]}, "_fn": t_ocr},
]
TOOL_MAP = {t["name"]: t["_fn"] for t in TOOLS}
PUBLIC = [{k: v for k, v in t.items() if not k.startswith("_")} for t in TOOLS]


def handle(req: dict) -> dict | None:
    method, rid = req.get("method", ""), req.get("id")
    if method == "initialize":
        asked = (req.get("params") or {}).get("protocolVersion")
        return _ok(rid, {"protocolVersion": asked or PROTOCOL_FALLBACK,
                         "capabilities": {"tools": {}},
                         "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": PUBLIC})
    if method == "tools/call":
        params = req.get("params") or {}
        fn = TOOL_MAP.get(params.get("name", ""))
        if not fn:
            return _err(rid, -32602, f"未知工具：{params.get('name')}")
        try:
            return _ok(rid, {"content": [{"type": "text", "text": fn(params.get("arguments") or {})}]})
        except ToolError as exc:
            return _ok(rid, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        except Exception as exc:
            log(traceback.format_exc())
            return _ok(rid, {"content": [{"type": "text", "text": f"内部错误：{exc}"}], "isError": True})
    return None if rid is None else _err(rid, -32601, f"不支持的方法：{method}")


def _ok(i, r): return {"jsonrpc": "2.0", "id": i, "result": r}
def _err(i, c, m): return {"jsonrpc": "2.0", "id": i, "error": {"code": c, "message": m}}


def main() -> int:
    # Windows 控制台默认不是 utf-8，不设会导致 JSON-RPC 里的中文乱码
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    log(f"{SERVER_NAME} {SERVER_VERSION} 启动")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            resp = handle(json.loads(line))
        except json.JSONDecodeError:
            continue
        except Exception as exc:
            log(traceback.format_exc())
            resp = _err(None, -32603, str(exc))
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
