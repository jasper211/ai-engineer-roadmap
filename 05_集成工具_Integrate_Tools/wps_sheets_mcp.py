#!/usr/bin/env python3
"""WPS 传统表格补充 MCP —— 补官方 wps365-cli 的一个缺口。

官方 MCP 的 120 个工具里只有 airsheet(.ksheet) 和 dbsheet(.dbt)，
没有传统表格(.xls/.xlsx)；drive_file_content_get 对这两种格式都返回
「文档内容抽取失败」。而企业日常数据大多是传统表格。

设计原则：**不碰凭证、不发 HTTP**。全部转调 `wps365-cli api`，
认证、刷新、代理全由官方 CLI 负责，本文件只做两件事——拼接口、把
扁平单元格拍成网格。零第三方依赖。

⚠️ stdout 只允许 JSON-RPC，日志一律走 stderr。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

SERVER_NAME = "wps-sheets"
SERVER_VERSION = "1.0.0"
PROTOCOL_FALLBACK = "2024-11-05"
CALL_TIMEOUT = 180
MAX_CHARS = 60000


class ToolError(Exception):
    pass


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def find_cli() -> str:
    candidates = [os.environ.get("WPS365_CLI"),
                  str(Path.home() / ".local/bin/wps365-cli"),
                  "/usr/local/bin/wps365-cli"]
    for c in candidates:
        if c and Path(c).exists():
            return c
    found = shutil.which("wps365-cli")
    if found:
        return found
    raise ToolError(
        "找不到 wps365-cli。先安装：curl -fsSL https://open-docs.wpscdn.cn/cli/install.sh | bash"
        "，或用环境变量 WPS365_CLI 指定绝对路径。")


def cli_json(args: list[str]) -> dict:
    """调 wps365-cli 并解析其 JSON 输出。认证由 CLI 自理。"""
    cli = find_cli()
    try:
        # 显式 utf-8：Windows 中文系统默认按 GBK 解码，CLI 输出的 UTF-8 会解码失败
        proc = subprocess.run([cli, *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=CALL_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ToolError(f"调用超时（{CALL_TIMEOUT}s）：{' '.join(args)}") from None
    raw = (proc.stdout or "").strip()
    if proc.returncode != 0 and not raw.startswith("{"):
        err = (proc.stderr or raw).strip()[:400]
        # CLI 自己的报错通常已经说清原因，只在它不会提的那一点上补充：
        # scope 是在授权那一刻固化的，后台补申请后不重新授权不会生效。
        if "invalid_scope" in err:
            err += "\n补充：若已在后台申请过该 scope，需【重新授权】才生效——token 的 scope 在授权时固化。"
        raise ToolError(err)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise ToolError(f"CLI 返回的不是 JSON：{raw[:300]}") from None
    code = payload.get("code")
    if code not in (0, None):
        raise ToolError(f"接口失败 code={code} msg={payload.get('msg')}")
    return payload.get("data", payload)


def _worksheets(file_id: str) -> list[dict]:
    return _as_list(cli_json(["api", "get", f"/v7/sheets/{file_id}/worksheets"]).get("sheets"))


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def t_worksheets(args: dict) -> str:
    """列工作表，并给出每张表的实际数据范围，便于决定读多大选区。"""
    sheets = _worksheets(args["file_id"])
    if not sheets:
        return "没有工作表。确认这是传统表格(.xls/.xlsx)；智能表格(.ksheet)请用官方 airsheet_* 工具。"
    lines = [f"共 {len(sheets)} 张工作表：", ""]
    for s in sheets:
        area = s.get("active_area") or {}
        empty = " [空表]" if s.get("empty") else ""
        hidden = " [隐藏]" if s.get("hidden") else ""
        rng = (f"数据范围 行{area.get('row_from', 0)}-{area.get('row_to', 0)} "
               f"列{area.get('col_from', 0)}-{area.get('col_to', 0)}")
        lines.append(f"  sheet_id={s.get('sheet_id')}  {s.get('name', '')}{empty}{hidden}  {rng}")
    lines.append("\n用 sheet_read 读取；不传行列范围时会自动按上面的数据范围读整张表。")
    return "\n".join(lines)


def t_read(args: dict) -> str:
    """读一张工作表的选区，输出 TSV 网格。"""
    file_id = args["file_id"]
    sheets = _worksheets(file_id)
    if not sheets:
        raise ToolError("没有工作表，确认文件是传统表格(.xls/.xlsx)")

    sheet_id = args.get("sheet_id")
    target = None
    if sheet_id is None:
        target = next((s for s in sheets if not s.get("empty")), sheets[0])
        sheet_id = target.get("sheet_id")
    else:
        target = next((s for s in sheets if str(s.get("sheet_id")) == str(sheet_id)), None)
        if target is None:
            ids = ", ".join(str(s.get("sheet_id")) for s in sheets)
            raise ToolError(f"没有 sheet_id={sheet_id} 的工作表，可用的有：{ids}")

    # 没指定范围就按 active_area 读全表——AI 通常不知道表有多大
    area = (target or {}).get("active_area") or {}
    row_from = int(args.get("row_from", area.get("row_from", 0)))
    row_to = int(args.get("row_to", area.get("row_to", 199)))
    col_from = int(args.get("col_from", area.get("col_from", 0)))
    col_to = int(args.get("col_to", area.get("col_to", 29)))

    # 用普通 GET 而非 range_data/find：find 是筛选接口，会把第 0 行当表头剔除
    q = [f"--query={k}={v}" for k, v in (("row_from", row_from), ("row_to", row_to),
                                         ("col_from", col_from), ("col_to", col_to))]
    data = cli_json(["api", "get",
                     f"/v7/sheets/{file_id}/worksheets/{sheet_id}/range_data", *q])

    grid: dict[tuple[int, int], str] = {}
    for cell in _as_list(data.get("range_data")):
        text = str(cell.get("cell_text") or cell.get("original_cell_value") or "").strip()
        if text:
            grid[(int(cell.get("row_from", 0)), int(cell.get("col_from", 0)))] = text
    # 合并单元格的文本落在左上角，不覆盖已有值
    for cell in _as_list(data.get("merge_range_data")):
        text = str(cell.get("cell_text") or "").strip()
        if text:
            grid.setdefault((int(cell.get("row_from", 0)), int(cell.get("col_from", 0))), text)

    name = (target or {}).get("name", "")
    head = (f"工作表 {sheet_id} {name}｜选区 行{row_from}-{row_to} 列{col_from}-{col_to}\n")
    if not grid:
        return head + "\n(选区内没有数据)"

    rows = sorted({r for r, _ in grid})
    cols = sorted({c for _, c in grid})
    out = [head, f"非空行 {len(rows)}、非空列 {len(cols)}\n",
           "行\\列\t" + "\t".join(str(c) for c in cols)]
    for r in rows:
        out.append(str(r) + "\t" + "\t".join(
            grid.get((r, c), "").replace("\t", " ").replace("\n", " ") for c in cols))
    text = "\n".join(out)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n…（输出过长已截断，请缩小行列范围分块读取）"
    return text


TOOLS = [
    {"name": "sheet_worksheets",
     "description": "列出传统表格(.xls/.xlsx)的工作表及其实际数据范围。官方MCP没有传统表格工具，读这类文件从这里开始。智能表格(.ksheet)请用 airsheet_*，多维表格(.dbt)请用 dbsheet_*。",
     "inputSchema": {"type": "object", "properties": {
         "file_id": {"type": "string", "description": "文件ID，可由官方 drive_file_search / drive_file_list 获得"}},
         "required": ["file_id"]}, "_fn": t_worksheets},
    {"name": "sheet_read",
     "description": "读传统表格(.xls/.xlsx)的单元格内容，输出TSV网格。不传工作表则取第一张非空表；不传行列范围则自动按该表实际数据范围读全表。大表请分块读。",
     "inputSchema": {"type": "object", "properties": {
         "file_id": {"type": "string"},
         "sheet_id": {"type": "string", "description": "工作表ID，来自 sheet_worksheets"},
         "row_from": {"type": "integer"}, "row_to": {"type": "integer"},
         "col_from": {"type": "integer"}, "col_to": {"type": "integer"}},
         "required": ["file_id"]}, "_fn": t_read},
]
TOOL_MAP = {t["name"]: t["_fn"] for t in TOOLS}
PUBLIC = [{k: v for k, v in t.items() if not k.startswith("_")} for t in TOOLS]


def handle(req: dict) -> dict | None:
    method, req_id = req.get("method", ""), req.get("id")
    if method == "initialize":
        asked = (req.get("params") or {}).get("protocolVersion")
        return _ok(req_id, {"protocolVersion": asked or PROTOCOL_FALLBACK,
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _ok(req_id, {})
    if method == "tools/list":
        return _ok(req_id, {"tools": PUBLIC})
    if method == "tools/call":
        params = req.get("params") or {}
        fn = TOOL_MAP.get(params.get("name", ""))
        if not fn:
            return _err(req_id, -32602, f"未知工具：{params.get('name')}")
        try:
            return _ok(req_id, {"content": [{"type": "text", "text": fn(params.get("arguments") or {})}]})
        except ToolError as exc:
            return _ok(req_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        except Exception as exc:
            log(traceback.format_exc())
            return _ok(req_id, {"content": [{"type": "text", "text": f"内部错误：{exc}"}], "isError": True})
    return None if req_id is None else _err(req_id, -32601, f"不支持的方法：{method}")


def _ok(i, r): return {"jsonrpc": "2.0", "id": i, "result": r}
def _err(i, c, m): return {"jsonrpc": "2.0", "id": i, "error": {"code": c, "message": m}}


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
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
