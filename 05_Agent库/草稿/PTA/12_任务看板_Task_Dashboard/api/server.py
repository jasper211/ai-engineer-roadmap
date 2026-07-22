#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务看板的本地 HTTP 服务——纯标准库 http.server，不引入 FastAPI/Flask。

理由（沿用本项目一贯的依赖习惯）：tools/llm_client.py 用原始 urllib 不用
requests，tools/wecom_notify.py 手写 multipart 编码而不引入第三方 HTTP 库，
requirements.txt 至今只有 python-docx/openpyxl 两个非标准库依赖。这是单用户
本地工具，6个接口、无并发压力，标准库完全够用，不值得为这一个功能破例引入
PTA 历史上第一个 web 框架依赖。

两种运行方式：
  开发：只起这个 API（不服务前端静态文件），配合 web/ 下 `npm run dev` 的
        Vite dev server，由 vite.config.ts 的 server.proxy 把 /api 转发过来。
  日常使用（"生产"，其实就是 Jasper 自己电脑上跑）：先 `npm run build` 出
        web/dist/，这个进程会自动检测 dist 目录存在就顺带把它当静态站点
        服务——一个命令、一个进程，不需要 nginx/pm2/Docker。
"""

import argparse
import json
import mimetypes
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import views

WEB_DIST_DIR = views.DASHBOARD_DIR / "web" / "dist"

TASK_STATUS_PATH = re.compile(r"^/api/tasks/([^/]+)/status$")
# 只允许这两个取值——"关闭"和"取消关闭(重新跟踪)"，这是前端勾选交互唯一
# 需要的两种状态转换；不开放任意字符串，避免前端一个笔误就把某条任务的
# 状态写成垃圾值。
ALLOWED_STATUSES = {"dismissed", "pending"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # 默认实现写 stderr 且格式偏底层（含协议版本号等噪音），这里精简成
        # 一行"方法 路径 状态码"，够本地调试用，不需要更多。
        sys.stderr.write(f"{self.command} {self.path}\n")

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 允许跨源——开发模式下 Vite 的 proxy 已经让浏览器只跟 5173 同源打交道，
        # 理论上不需要这个头；但保留它作为兜底，方便直接用 curl/裸 fetch 调
        # 8787 调试，不因为 CORS 卡住。这是单用户本地工具，不存在"允许太宽松
        # 导致被外部滥用"的真实风险。
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, rel_path: str) -> None:
        if not WEB_DIST_DIR.exists():
            self._send_json(404, {"error": "前端还没build，跑 npm run build 或用 npm run dev 走Vite"})
            return
        candidate = (WEB_DIST_DIR / rel_path.lstrip("/")).resolve()
        # 防止路径穿越（../../etc/passwd 这类）——确保解析后的真实路径仍在
        # WEB_DIST_DIR 之内，不在目录树外的任何地方读文件。
        if WEB_DIST_DIR.resolve() not in candidate.parents and candidate != WEB_DIST_DIR.resolve():
            self._send_json(403, {"error": "非法路径"})
            return
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.exists():
            candidate = WEB_DIST_DIR / "index.html"  # SPA 兜底：前端自己的路由交给前端处理
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        data = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        # 预检请求兜底（同上，单用户本地工具场景下大概率用不到，但补上不费事）。
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/api/projects":
            self._send_json(200, views.list_projects())
        elif parsed.path == "/api/tasks":
            project = query.get("project", ["all"])[0]
            self._send_json(200, views.aggregate_tasks(project))
        elif parsed.path == "/api/activity-feed":
            project = query.get("project", ["all"])[0]
            self._send_json(200, views.activity_feed(project))
        elif parsed.path == "/api/pipeline-status":
            self._send_json(200, views.pipeline_status())
        elif parsed.path == "/api/pipeline-drift-detail":
            self._send_json(200, views.pipeline_drift_detail())
        elif parsed.path == "/api/ob-search":
            search_query = query.get("query", [""])[0]
            mode = query.get("mode", ["hybrid"])[0]
            max_results = int(query.get("max_results", ["5"])[0])
            self._send_json(200, views.ob_search(search_query, mode, max_results))
        elif parsed.path == "/api/execution-history":
            project = query.get("project", ["all"])[0]
            limit = int(query.get("limit", ["30"])[0])
            self._send_json(200, views.execution_history(project, limit))
        elif parsed.path == "/api/agent-monitor":
            self._send_json(200, views.agent_monitor())
        elif parsed.path.startswith("/api/"):
            self._send_json(404, {"error": f"未知接口: {parsed.path}"})
        else:
            self._send_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        match = TASK_STATUS_PATH.match(parsed.path)
        if not match:
            self._send_json(404, {"error": f"未知接口: {parsed.path}"})
            return

        task_id = match.group(1)
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "请求体不是合法JSON"})
            return

        project = body.get("project", "")
        status = body.get("status", "")
        if status not in ALLOWED_STATUSES:
            self._send_json(400, {"error": f"status 只能是 {sorted(ALLOWED_STATUSES)} 之一，收到: {status}"})
            return
        if not project:
            self._send_json(400, {"error": "缺少 project 字段"})
            return

        result = views.dismiss_task(project, task_id, status)
        self._send_json(200 if result.get("found") else 404, result)


def main():
    parser = argparse.ArgumentParser(description="PTA 任务看板本地服务")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    mode = "生产模式（服务已build的前端静态文件）" if WEB_DIST_DIR.exists() else "仅API（前端请另外跑 npm run dev）"
    print(f"[任务看板] 监听 http://127.0.0.1:{args.port}（{mode}）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[任务看板] 已停止")


if __name__ == "__main__":
    main()
