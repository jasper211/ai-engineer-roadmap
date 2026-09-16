#!/usr/bin/env python3
"""WPS云文档 MCP Server —— 让AI Agent随时读团队云文档。

stdio传输，手写JSON-RPC，零第三方依赖：使用者只要有python3就能跑，不必pip install。
凭证分两层：应用凭证走环境变量（全员相同），用户token每人各自授权（数据范围跟随本人）。

⚠️ stdout只允许输出JSON-RPC，任何日志都必须走stderr，否则协议会被污染。
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from wps_client import (WPSClient, WPSError, EXT_KIND, _ext_of, _is_folder,  # noqa: E402
                        extract_document_text)

SERVER_NAME = "wps-cloud-docs"
SERVER_VERSION = "0.2.0"
PROTOCOL_FALLBACK = "2024-11-05"

TOKEN_HOME = Path(os.environ.get("WPS_TOKEN_DIR") or (Path.home() / ".wps_mcp"))
USER_TOKEN = TOKEN_HOME / "user_token.json"
APP_TOKEN = TOKEN_HOME / "app_token.json"
DEFAULT_REDIRECT = os.environ.get("WPS_REDIRECT_URI") or "http://localhost:9527/callback"
DEFAULT_SCOPES = [
    "kso.user_base.read", "kso.doclib.readwrite", "kso.file.read",
    "kso.dbsheet.read", "kso.sheets.read",
    "kso.airsheet.read", "kso.airsheet.readwrite", "kso.file_link.readwrite",
]
SHEET_KINDS = ("dbsheet", "sheets", "airsheet")


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def build_client() -> WPSClient:
    app_id = os.environ.get("WPS_APP_ID", "")
    app_key = os.environ.get("WPS_APP_KEY", "")
    if not (app_id and app_key):
        local = HERE / "wps_config.json"   # 开发机回退，正式部署请用环境变量
        if local.exists():
            conf = json.loads(local.read_text(encoding="utf-8"))
            app_id, app_key = conf.get("app_id", ""), conf.get("app_key", "")
    if not (app_id and app_key):
        raise WPSError("缺少应用凭证：请在MCP配置的env里设置 WPS_APP_ID 与 WPS_APP_KEY")
    TOKEN_HOME.mkdir(parents=True, exist_ok=True)
    return WPSClient(app_id, app_key, token_cache=APP_TOKEN, user_token_path=USER_TOKEN)


# ---------- 工具实现 ----------

def t_auth_status(_: dict) -> str:
    client = build_client()
    if not USER_TOKEN.exists():
        return ("未授权。团队文档库必须用用户身份才能列出。\n"
                "请调用 wps_auth_start 拿到授权链接，在浏览器完成授权后，"
                "把回调地址里的 code 交给 wps_auth_complete。")
    store = json.loads(USER_TOKEN.read_text(encoding="utf-8"))
    now = time.time()
    access_left = int(store.get("expires_at", 0) - now)
    refresh_left = int((store.get("refresh_expires_at", 0) - now) / 86400)
    state = "有效" if access_left > 0 else "已过期（下次调用会自动用refresh_token续）"
    lines = [f"已授权（用户身份，数据范围跟随授权者本人）",
             f"access_token：{state}，剩余 {max(access_left, 0)} 秒",
             f"refresh_token：剩余约 {refresh_left} 天（到期需重新授权）",
             f"token文件：{USER_TOKEN}"]
    try:
        client.token()
        lines.append("连通性：正常")
    except WPSError as exc:
        lines.append(f"连通性：异常 —— {exc}")
    return "\n".join(lines)


def t_auth_start(args: dict) -> str:
    client = build_client()
    redirect_uri = args.get("redirect_uri") or DEFAULT_REDIRECT
    state = os.urandom(8).hex()
    url = client.auth_url(redirect_uri, DEFAULT_SCOPES, state)
    return ("请把下面的链接给使用者，在浏览器中完成授权：\n\n"
            f"{url}\n\n"
            f"授权后浏览器会跳转到 {redirect_uri}?code=XXXX&state={state}\n"
            "该页面打不开也没关系，从地址栏复制 code= 后面的值，"
            "再调用 wps_auth_complete 提交。code 十分钟内有效且只能用一次。\n"
            f"注意：redirect_uri 必须与开发者后台「安全配置 > 用户授权回调配置」完全一致。")


def t_auth_complete(args: dict) -> str:
    code = (args.get("code") or "").strip()
    if not code:
        raise WPSError("缺少 code")
    client = build_client()
    client.exchange_code(code, args.get("redirect_uri") or DEFAULT_REDIRECT)
    return f"授权成功，token已保存到 {USER_TOKEN}。现在可以调用 wps_list_libraries 了。"


def t_list_libraries(_: dict) -> str:
    client = build_client()
    drives = client.list_drives()
    if not drives:
        return "没有可访问的文档库。"
    lines = [f"可访问 {len(drives)} 个团队文档库：", ""]
    lines += [f"{did}\t{name}" for did, name in drives]
    lines.append("\n用 drive_id 调用 wps_list_folder 浏览内容。")
    return "\n".join(lines)


def t_list_folder(args: dict) -> str:
    client = build_client()
    drive_id = args["drive_id"]
    folder_id = str(args.get("folder_id", "0"))
    items = client.children_all(drive_id, folder_id)
    if not items:
        return f"目录 {folder_id} 下没有内容。"
    folders, files = [], []
    for item in items:
        name = str(item.get("name", ""))
        item_id = item.get("id", "")
        if _is_folder(item):
            folders.append(f"  📁 {name}\tfolder_id={item_id}")
        else:
            ext = _ext_of(item, name)
            kind = EXT_KIND.get(ext, "file")
            mark = f"[{kind}]" if kind in SHEET_KINDS else "[不可结构化读取]"
            files.append(f"  {name}\t{mark}\tfile_id={item_id}\tmtime={item.get('mtime')}")
    out = [f"目录下 {len(folders)} 个子文件夹、{len(files)} 个文件：", ""]
    out += folders + files
    return "\n".join(out)


def t_search_files(args: dict) -> str:
    """浅层广度搜索。故意不做无限递归——整库遍历要几十分钟，会拖死会话。"""
    client = build_client()
    drive_id = args["drive_id"]
    max_depth = min(int(args.get("max_depth", 3)), 6)
    limit = min(int(args.get("limit", 50)), 200)
    keyword = (args.get("name_contains") or "").lower()
    only_sheets = bool(args.get("only_sheets", True))

    hits: list[str] = []
    level = [(str(args.get("folder_id", "0")), "")]
    scanned = 0
    truncated = False
    for depth in range(max_depth + 1):
        if not level or len(hits) >= limit:
            break
        next_level = []
        for folder_id, prefix in level:
            if len(hits) >= limit:
                truncated = True
                break
            scanned += 1
            for item in client.children_all(drive_id, folder_id):
                name = str(item.get("name", ""))
                path = f"{prefix}/{name}" if prefix else name
                if _is_folder(item):
                    next_level.append((str(item.get("id", "")), path))
                    continue
                ext = _ext_of(item, name)
                kind = EXT_KIND.get(ext, "file")
                if only_sheets and kind not in SHEET_KINDS:
                    continue
                if keyword and keyword not in name.lower():
                    continue
                if len(hits) < limit:
                    hits.append(f"  [{kind}] {path}\tfile_id={item.get('id')}")
                else:
                    truncated = True
        level = next_level

    head = (f"扫了 {scanned} 个目录（深度上限{max_depth}），命中 {len(hits)} 个"
            f"{'表格' if only_sheets else '文件'}")
    if truncated or level:
        head += f"。⚠️ 结果可能不全：达到了 limit={limit} 或深度上限，更深的目录未展开"
    return head + "：\n\n" + ("\n".join(hits) if hits else "  （无命中）")


def t_read_document(args: dict) -> str:
    """读 Word/PPT/纯文本 的正文。表格请用 wps_read_sheet。"""
    client = build_client()
    file_id = args["file_id"]
    meta = client.file_meta(file_id)
    name = str(meta.get("name", file_id))
    size = int(meta.get("size", 0))
    if size > 40 * 1024 * 1024:
        raise WPSError(f"{name} 有 {size/1048576:.1f}MB，超过 40MB 上限")

    blob = client.file_bytes(file_id, str(meta.get("drive_id") or "") or None)
    paragraphs, fmt = extract_document_text(name, blob)

    keyword = args.get("contains")
    if keyword:
        hits = [(i, p) for i, p in enumerate(paragraphs) if keyword in p]
        head = f"{name}（{fmt}）共 {len(paragraphs)} 段，含「{keyword}」的有 {len(hits)} 段：\n"
        body = "\n".join(f"  [{i}] {p}" for i, p in hits[:80])
        return head + "\n" + (body or "  （无命中）")

    start = max(int(args.get("from_paragraph", 0)), 0)
    limit = min(int(args.get("limit", 200)), 500)
    chunk = paragraphs[start:start + limit]
    head = (f"{name}（{fmt}）\n共 {len(paragraphs)} 段、{sum(len(x) for x in paragraphs)} 字，"
            f"本次显示第 {start}~{start + len(chunk) - 1} 段\n")
    if start + limit < len(paragraphs):
        head += f"还有 {len(paragraphs) - start - limit} 段未显示，用 from_paragraph 继续读\n"
    return head + "\n" + "\n".join(chunk)


def t_file_info(args: dict) -> str:
    client = build_client()
    return json.dumps(client.file_meta(args["file_id"]), ensure_ascii=False, indent=2)


def t_resolve_link(args: dict) -> str:
    client = build_client()
    target = args["link"]
    link_id = target.rstrip("/").split("/l/")[-1] if "/l/" in target else target
    meta = client.link_meta(link_id)
    return json.dumps(meta, ensure_ascii=False, indent=2)


def _cells_to_tsv(data: dict, max_rows: int = 400) -> tuple[str, int]:
    """把接口返回的扁平单元格列表拍成网格再输出TSV。

    原始响应每个单元格都带 pic_data/sha1/tag/num_format 等字段，约300字节，
    一屏数据就能撑到MB级；转成TSV后同样内容通常只剩几十分之一。
    合并单元格的文本落在其左上角。
    """
    cells = data.get("range_data") or []
    if not cells:
        return "(选区内没有数据)", 0
    grid: dict[tuple[int, int], str] = {}
    for cell in cells:
        text = cell.get("cell_text") or cell.get("original_cell_value") or ""
        if text == "":
            continue
        grid[(int(cell.get("row_from", 0)), int(cell.get("col_from", 0)))] = str(text)
    if not grid:
        return "(选区内全是空单元格)", 0
    rows = sorted({r for r, _ in grid})
    cols = sorted({c for _, c in grid})
    lines = ["行\\列\t" + "\t".join(str(c) for c in cols)]
    for r in rows[:max_rows]:
        lines.append(str(r) + "\t" + "\t".join(
            grid.get((r, c), "").replace("\t", " ").replace("\n", " ") for c in cols))
    if len(rows) > max_rows:
        lines.append(f"…（还有 {len(rows) - max_rows} 行未显示，请缩小行范围分块读）")
    return "\n".join(lines), len(rows)


def t_read_sheet(args: dict) -> str:
    client = build_client()
    file_id = args["file_id"]
    kind = args.get("kind", "sheets")
    listing = client.worksheets(file_id, kind=kind)
    sheets = listing.get("sheets", [])
    target = args.get("worksheet_id")
    if target is None:
        if not sheets:
            return f"该文件没有工作表。原始响应：{json.dumps(listing, ensure_ascii=False)[:500]}"
        target = sheets[0].get("sheet_id", sheets[0].get("id"))
    data = client.range_data(
        file_id, target, kind=kind,
        row_from=int(args.get("row_from", 0)), row_to=int(args.get("row_to", 199)),
        col_from=int(args.get("col_from", 0)), col_to=int(args.get("col_to", 29)),
    )
    index = [{"id": s.get("sheet_id", s.get("id")), "name": s.get("name")} for s in sheets]
    table, row_count = _cells_to_tsv(data)
    if args.get("raw"):
        table = json.dumps(data, ensure_ascii=False)[:60000]
    head = (f"工作表列表：{json.dumps(index, ensure_ascii=False)}\n"
            f"读取的工作表：{target}，非空行 {row_count}\n"
            f"选区：行{args.get('row_from', 0)}-{args.get('row_to', 199)} "
            f"列{args.get('col_from', 0)}-{args.get('col_to', 29)}\n")
    return head + "\n" + table


def t_read_dbsheet(args: dict) -> str:
    client = build_client()
    file_id = args["file_id"]
    schema = client.dbsheet_schema(file_id)
    tables = schema.get("sheets", [])
    sheet_id = args.get("sheet_id")
    if sheet_id is None:
        if not tables:
            return f"没有数据表。原始schema：{json.dumps(schema, ensure_ascii=False)[:500]}"
        sheet_id = tables[0].get("id")
    records = client.dbsheet_records(file_id, sheet_id,
                                     page_size=int(args.get("page_size", 100)))
    index = [{"id": t.get("id"), "name": t.get("name")} for t in tables]
    body = json.dumps(records, ensure_ascii=False)
    if len(body) > 60000:
        body = body[:60000] + f"\n…（已截断，共{len(records)}条记录）"
    return (f"数据表列表：{json.dumps(index, ensure_ascii=False)}\n"
            f"读取的数据表：{sheet_id}，共 {len(records)} 条记录\n\n{body}")


TOOLS: list[dict] = [
    {"name": "wps_auth_status", "description": "查看当前WPS授权状态与token剩余有效期。遇到权限错误时先调这个。",
     "inputSchema": {"type": "object", "properties": {}}, "_fn": t_auth_status},
    {"name": "wps_auth_start", "description": "生成用户授权链接。团队文档库必须用用户身份访问，未授权时先调这个。",
     "inputSchema": {"type": "object", "properties": {
         "redirect_uri": {"type": "string", "description": "回调地址，需与开发者后台配置一致"}}},
     "_fn": t_auth_start},
    {"name": "wps_auth_complete", "description": "用授权回调地址里的code换取用户token，完成授权。",
     "inputSchema": {"type": "object", "properties": {
         "code": {"type": "string", "description": "回调地址栏 code= 后面的值"},
         "redirect_uri": {"type": "string"}}, "required": ["code"]},
     "_fn": t_auth_complete},
    {"name": "wps_list_libraries", "description": "列出当前用户可访问的全部团队文档库及其drive_id。浏览的起点。",
     "inputSchema": {"type": "object", "properties": {}}, "_fn": t_list_libraries},
    {"name": "wps_list_folder", "description": "列出指定目录下一层的子文件夹和文件（含file_id与修改时间）。根目录folder_id传0。",
     "inputSchema": {"type": "object", "properties": {
         "drive_id": {"type": "string"}, "folder_id": {"type": "string", "description": "默认0=根目录"}},
         "required": ["drive_id"]}, "_fn": t_list_folder},
    {"name": "wps_search_files", "description": "在一个库里按名称/类型浅层搜索文件。注意：这是受限的广度搜索（默认深度3、上限50条），不是全库遍历——整库递归要几十分钟。结果不全时会明确提示。",
     "inputSchema": {"type": "object", "properties": {
         "drive_id": {"type": "string"},
         "folder_id": {"type": "string", "description": "从哪个目录开始，默认0"},
         "name_contains": {"type": "string", "description": "文件名关键字，不区分大小写。注意：是精确子串匹配，不做简繁转换。实测同一文件夹内会简繁混用（如正文「顧問服務協議」、附件「服务工作范围及验收标准」），所以中文关键词建议简体和繁体各搜一次，或改用更短的、简繁同形的片段（如「协议」→「議」两种都试）。搜不到时优先怀疑简繁问题。"},
         "only_sheets": {"type": "boolean", "description": "只返回可读取的表格，默认true"},
         "max_depth": {"type": "integer", "description": "递归深度，默认3，最大6"},
         "limit": {"type": "integer", "description": "最多返回多少条，默认50，最大200"}},
         "required": ["drive_id"]}, "_fn": t_search_files},
    {"name": "wps_read_sheet", "description": "读传统表格(.xlsx/.et，kind=sheets)或智能表格(.ksheet，kind=airsheet)的单元格数据。默认读第一个工作表的前200行×30列，大表请分块读。",
     "inputSchema": {"type": "object", "properties": {
         "file_id": {"type": "string"},
         "kind": {"type": "string", "enum": ["sheets", "airsheet"], "description": "默认sheets"},
         "worksheet_id": {"type": "string", "description": "不传则读第一个工作表"},
         "row_from": {"type": "integer"}, "row_to": {"type": "integer"},
         "col_from": {"type": "integer"}, "col_to": {"type": "integer"},
         "raw": {"type": "boolean", "description": "返回原始JSON而非TSV网格，排查用，很占上下文"}},
         "required": ["file_id"]}, "_fn": t_read_sheet},
    {"name": "wps_read_dbsheet", "description": "读多维表格(.dbt)的记录。不传sheet_id则读第一张数据表，自动翻页取全部记录。",
     "inputSchema": {"type": "object", "properties": {
         "file_id": {"type": "string"},
         "sheet_id": {"type": "string", "description": "不传则读第一张数据表"},
         "page_size": {"type": "integer", "description": "每页条数，默认100"}},
         "required": ["file_id"]}, "_fn": t_read_dbsheet},
    {"name": "wps_read_document", "description": "读 Word(.docx)、PPT(.pptx) 或纯文本(.txt/.md/.csv/.json等) 的正文。表格请改用 wps_read_sheet。不支持 PDF 和旧版 .doc（二进制格式，本工具只用标准库）——很多合同同时存有 .docx 和 .pdf 两版，优先找 .docx。长文档分段返回，可用 contains 只看命中关键词的段落。",
     "inputSchema": {"type": "object", "properties": {
         "file_id": {"type": "string"},
         "contains": {"type": "string", "description": "只返回含该关键词的段落（附段号）。中文注意简繁问题"},
         "from_paragraph": {"type": "integer", "description": "从第几段开始，默认0"},
         "limit": {"type": "integer", "description": "最多返回多少段，默认200，最大500"}},
         "required": ["file_id"]}, "_fn": t_read_document},
    {"name": "wps_file_info", "description": "获取单个文件的元信息（名称、类型、大小、修改时间等）。",
     "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string"}},
                     "required": ["file_id"]}, "_fn": t_file_info},
    {"name": "wps_resolve_link", "description": "把WPS分享链接(/l/xxxx)解析成file_id与drive_id。",
     "inputSchema": {"type": "object", "properties": {
         "link": {"type": "string", "description": "完整分享链接或link_id"}}, "required": ["link"]},
     "_fn": t_resolve_link},
]
TOOL_MAP = {t["name"]: t["_fn"] for t in TOOLS}
PUBLIC_TOOLS = [{k: v for k, v in t.items() if not k.startswith("_")} for t in TOOLS]


# ---------- JSON-RPC ----------

def handle(req: dict) -> dict | None:
    method = req.get("method", "")
    req_id = req.get("id")
    if method == "initialize":
        asked = (req.get("params") or {}).get("protocolVersion")
        return _ok(req_id, {
            "protocolVersion": asked or PROTOCOL_FALLBACK,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _ok(req_id, {})
    if method == "tools/list":
        return _ok(req_id, {"tools": PUBLIC_TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name", "")
        fn = TOOL_MAP.get(name)
        if not fn:
            return _err(req_id, -32602, f"未知工具：{name}")
        try:
            text = fn(params.get("arguments") or {})
            return _ok(req_id, {"content": [{"type": "text", "text": text}]})
        except WPSError as exc:
            return _ok(req_id, {"content": [{"type": "text", "text": f"WPS接口失败：{exc}"}],
                                "isError": True})
        except Exception as exc:  # 工具内部异常不该让整个server退出
            log(traceback.format_exc())
            return _ok(req_id, {"content": [{"type": "text", "text": f"内部错误：{exc}"}],
                                "isError": True})
    if req_id is None:
        return None
    return _err(req_id, -32601, f"不支持的方法：{method}")


def _ok(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def main() -> int:
    log(f"{SERVER_NAME} {SERVER_VERSION} 启动，token目录 {TOKEN_HOME}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            log(f"收到非JSON输入，已忽略：{line[:120]}")
            continue
        try:
            resp = handle(req)
        except Exception as exc:
            log(traceback.format_exc())
            resp = _err(req.get("id"), -32603, str(exc))
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
