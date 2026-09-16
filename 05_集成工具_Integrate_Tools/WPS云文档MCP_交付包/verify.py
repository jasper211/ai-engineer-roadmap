#!/usr/bin/env python3
"""交付包自检：一条命令看清装到哪一步、卡在哪里。

每项失败都给出具体的下一步动作，不只是报错。
不打印任何密钥内容。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OK, BAD, WARN = "✅", "❌", "⚠️ "
problems: list[str] = []


def check(title: str, passed: bool, detail: str = "", fix: str = "") -> bool:
    print(f"{OK if passed else BAD} {title}" + (f"  {detail}" if detail else ""))
    if not passed and fix:
        print(f"     → {fix}")
        problems.append(title)
    return passed


print("WPS云文档 MCP 交付包 · 自检\n" + "=" * 46)

# 1. Python
version_ok = sys.version_info >= (3, 9)
check(f"Python 版本 {sys.version_info.major}.{sys.version_info.minor}", version_ok,
      fix="需要 Python 3.9 及以上")

# 2. 文件完整
need = ["wps_mcp_server.py", "wps_client.py", "wps_sync.py", "wps_config.example.json"]
missing = [f for f in need if not (HERE / f).exists()]
check("交付包文件完整", not missing, f"{len(need) - len(missing)}/{len(need)}",
      fix=f"缺少 {missing}，请重新获取完整交付包")

# 3. 配置文件
conf_path = HERE / "wps_config.json"
conf = {}
if not check("配置文件 wps_config.json 存在", conf_path.exists(),
             fix="执行：cp wps_config.example.json wps_config.json  然后填入 APPID/APPKEY"):
    pass
else:
    try:
        conf = json.loads(conf_path.read_text(encoding="utf-8"))
        check("配置文件 JSON 格式正确", True)
    except json.JSONDecodeError as exc:
        check("配置文件 JSON 格式正确", False, str(exc)[:60],
              fix="常见原因：把引号打成了中文引号 “ ”，JSON 只认半角 \"")
    if conf:
        filled = bool(conf.get("app_id")) and not str(conf.get("app_id", "")).startswith("开发者后台")
        check("APPID / APPKEY 已填写", filled,
              f"app_id 长度 {len(str(conf.get('app_id','')))}",
              fix="把 wps_config.json 里的占位文字换成管理员给你的真实值")

# 4. 网络与证书
sys.path.insert(0, str(HERE))
try:
    from wps_client import WPSClient, WPSError, _ssl_context
    import urllib.request
    ctx = _ssl_context()
    req = urllib.request.Request("https://openapi.wps.cn/oauth2/token", method="POST",
                                 data=b"grant_type=client_credentials&client_id=x&client_secret=x",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        urllib.request.urlopen(req, timeout=15, context=ctx)
        reachable = True
    except urllib.error.HTTPError:
        reachable = True          # 返回401也说明网络与TLS没问题
    except Exception as exc:
        reachable = False
        detail = str(exc)[:80]
    check("能连上 openapi.wps.cn（含TLS证书）", reachable,
          fix="检查网络/代理；若报 CERTIFICATE_VERIFY_FAILED，装一下 certifi：python3 -m pip install certifi")
except ImportError as exc:
    check("能导入 wps_client", False, str(exc)[:60], fix="交付包文件不完整")

# 5. 凭证是否真的有效
if conf.get("app_id") and conf.get("app_key"):
    try:
        client = WPSClient(conf["app_id"], conf["app_key"],
                           token_cache=HERE / ".token_cache.json")
        token = client.token()
        check("应用凭证有效（成功换取token）", bool(token), f"长度 {len(token)}")
    except WPSError as exc:
        msg = str(exc)
        hint = "APPID/APPKEY 不对，找管理员核对" if "invalid_client" in msg else msg[:90]
        check("应用凭证有效（成功换取token）", False, fix=hint)

# 6. 用户授权
import os
token_dir = Path(os.environ.get("WPS_TOKEN_DIR") or (Path.home() / ".wps_mcp"))
user_token = token_dir / "user_token.json"
has_user = user_token.exists()
check("已完成用户授权", has_user, str(token_dir),
      fix="执行：python3 wps_sync.py auth   （团队文档库必须用用户身份才能访问）")
if has_user:
    import time
    store = json.loads(user_token.read_text(encoding="utf-8"))
    days = int((store.get("refresh_expires_at", 0) - time.time()) / 86400)
    print(f"     授权剩余约 {days} 天")

# 7. MCP server 能否握手
try:
    reqs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    proc = subprocess.run([sys.executable, str(HERE / "wps_mcp_server.py")],
                          input="\n".join(json.dumps(r) for r in reqs),
                          capture_output=True, text=True, timeout=60)
    lines = [json.loads(x) for x in proc.stdout.strip().splitlines() if x.startswith("{")]
    tools = next((d["result"]["tools"] for d in lines if d.get("id") == 2), [])
    check("MCP server 能启动并列出工具", bool(tools), f"{len(tools)} 个工具",
          fix=f"启动失败：{proc.stderr.strip()[:150]}")
except Exception as exc:
    check("MCP server 能启动并列出工具", False, fix=str(exc)[:120])

print("=" * 46)
if problems:
    print(f"\n{BAD} 还有 {len(problems)} 项未通过：{'、'.join(problems)}")
    print("   按上面每项的 → 提示处理，然后重跑：python3 verify.py")
    sys.exit(1)
print(f"\n{OK} 全部通过。把下面这段加进 ~/.claude.json 的 mcpServers，重启客户端即可：\n")
print(json.dumps({"wps-cloud-docs": {
    "type": "stdio", "command": "python3",
    "args": [str(HERE / "wps_mcp_server.py")],
    "env": {"WPS_TOKEN_DIR": str(token_dir)}}}, ensure_ascii=False, indent=2))
