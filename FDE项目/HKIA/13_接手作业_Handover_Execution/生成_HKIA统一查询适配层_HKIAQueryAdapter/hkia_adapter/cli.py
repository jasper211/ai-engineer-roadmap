"""JSON CLI：python -m hkia_adapter.cli query --request request.json
标准输出仅 JSON；日志/错误封装到 JSON；成功退出码0，被阻断/出错非零。"""
from __future__ import annotations
import argparse, json, sys
from .client import HKIAClient


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hkia_adapter.cli")
    sub = ap.add_subparsers(dest="cmd")
    q = sub.add_parser("query", help="提交查询请求")
    q.add_argument("--request", required=True, help="请求 JSON 文件路径")
    q.add_argument("--hkia-root", help="HKIA 根目录(可选)")
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help(); return 0
    if args.cmd == "query":
        try:
            with open(args.request, encoding="utf-8") as f:
                req = json.load(f)
        except Exception as e:
            resp = {"ok": False, "error_code": "CLI_INVALID_JSON", "message": f"请求 JSON 解析失败: {e}",
                    "blocked_by": "cli_input", "query_type": ""}
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            return 2
        try:
            client = HKIAClient.open_readonly(hkia_root=args.hkia_root)
            resp = client.query(req)
            client.close()
        except Exception as e:
            resp = {"ok": False, "error_code": "CLI_ERROR", "message": str(e), "blocked_by": None,
                    "query_type": req.get("query_type", "")}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        return 0 if resp.get("ok", False) else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
