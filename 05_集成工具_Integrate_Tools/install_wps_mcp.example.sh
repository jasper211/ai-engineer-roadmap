#!/bin/bash
# WPS 云文档 MCP 一键安装（macOS / Linux）
#
# 管理员：把下面两行填成企业自建应用的凭证，然后把本脚本连同
#         wps_sheets_mcp.py 一起发给使用者。
# 使用者：把两个文件放同一目录，执行  bash install_wps_mcp.sh
#
# ⚠️ 填好凭证后，本脚本就含有 APPKEY，等同密钥文件：
#    不要提交到代码仓库、不要放共享盘、不要在群里转发。

APP_ID="${WPS_APP_ID:-__在此填入APPID__}"
APP_KEY="${WPS_APP_KEY:-__在此填入APPKEY__}"

SCOPES="kso.user_base.read,kso.file.read,kso.file.search,kso.doclib.readwrite,kso.drive.readwrite,kso.file_link.readwrite,kso.dbsheet.read,kso.sheets.read,kso.airsheet.read,kso.airsheet.readwrite"

set -uo pipefail
CLI="$HOME/.local/bin/wps365-cli"
T="--timeout 25s"   # 凭证错误时 CLI 可能长时间挂起，统一加超时
SHEETS_DIR="$HOME/.local/share/wps365-sheets"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OCR_DIR=""
CLAUDE_CFG="$HOME/.claude.json"

step() { echo; echo "▶ $*"; }
ok()   { echo "  ✓ $*"; }
warn() { echo "  ! $*"; }
die()  { echo; echo "✗ $*" >&2; exit 1; }

echo "=========================================="
echo " WPS 云文档 MCP 安装"
echo "=========================================="

# ---------- 0. 前置检查 ----------
step "检查配置"
case "$APP_ID" in *"在此填入"*) die "APP_ID 还没填。请管理员编辑本脚本顶部，或设环境变量 WPS_APP_ID / WPS_APP_KEY";; esac
case "$APP_KEY" in *"在此填入"*) die "APP_KEY 还没填。同上";; esac
ok "APPID ${APP_ID:0:10}…"

PY=""
for c in python3 /usr/bin/python3; do
    command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
[ -n "$PY" ] && ok "python3 已就绪（用于传统表格工具与配置写入）" \
             || warn "没有 python3：跳过传统表格工具，MCP 配置需手动加"

# ---------- 1. 安装 CLI ----------
step "安装 wps365-cli"
if [ -x "$CLI" ]; then
    ok "已安装：$("$CLI" --version 2>/dev/null || echo 未知版本)"
else
    curl -fsSL https://open-docs.wpscdn.cn/cli/install.sh | bash -s -- --no-modify-path \
        || die "CLI 安装失败，检查网络或代理"
    [ -x "$CLI" ] || die "安装完成但找不到 $CLI"
    ok "已安装：$("$CLI" --version 2>/dev/null)"
fi

# ---------- 2. 应用凭证 ----------
# auth setup 会直接覆盖钥匙串里已有的 APPKEY，而且它自己不校验对错。
# 所以顺序是：先拿 client_credentials 探一次真伪，验证通过才写入——
# 填错的 APPKEY 到不了钥匙串，不会把本来能用的环境写坏。
step "校验应用凭证"
CURRENT_ID=$("$CLI" auth status 2>/dev/null | sed -n 's/.*"client_id": *"\([^"]*\)".*/\1/p' | head -1)
if [ "$CURRENT_ID" = "$APP_ID" ] && "$CLI" $T user me >/dev/null 2>&1; then
    ok "已有可用凭证，保持不动"
else
    RESP=$(printf 'grant_type=client_credentials&client_id=%s&client_secret=%s' "$APP_ID" "$APP_KEY" \
           | curl -s --max-time 20 -X POST https://openapi.wps.cn/oauth2/token --data @- 2>&1)
    case "$RESP" in
        *access_token*)
            ok "凭证校验通过" ;;
        *invalid_client*)
            die "APPID 或 APPKEY 不正确（平台返回 invalid_client）。
   请向管理员核对后重跑。你现有的配置未被改动。" ;;
        "")
            die "无法连接 openapi.wps.cn，检查网络或代理。你现有的配置未被改动。" ;;
        *)
            die "凭证校验失败：${RESP:0:200}
   你现有的配置未被改动。" ;;
    esac

    if [ -n "$CURRENT_ID" ] && [ "$CURRENT_ID" != "$APP_ID" ]; then
        warn "将把已配置的应用 $CURRENT_ID 换成 $APP_ID"
    fi
    # macOS 首次写入或覆盖钥匙串条目时会弹授权框，不点就一直挂着（看起来像死机）
    echo "  写入钥匙串中…若弹出「wps365-cli 想要访问钥匙串」，请点【允许】或【始终允许】"
    # 用 --client-secret 传参：CLI 的交互式输入连问三项，脚本里不好喂；
    # 代价是密钥会在写入的一瞬间出现在进程列表（ps 可见），个人工作机可接受。
    "$CLI" auth setup --client-id "$APP_ID" --client-secret "$APP_KEY" >/dev/null 2>&1 \
        || die "凭证写入失败（若刚才有钥匙串弹窗未点允许，请重跑本脚本）"
    ok "凭证已保存到系统钥匙串（不落在明文文件里）"
fi

# ---------- 3. 授权 ----------
step "用户授权"
if "$CLI" auth status 2>/dev/null | grep -q '"status": *"valid"'; then
    ok "已授权，跳过"
else
    echo "  接下来会显示一个链接和验证码，请在浏览器中完成授权。"
    echo "  授权范围仅限你本人有权限的内容。"
    echo "  ⚠ 若链接是 http:// 开头，请手动改成 https:// 再打开——"
    echo "    http 下浏览器不发送登录 cookie，页面会不停刷新且永远登不进去。"
    echo
    "$CLI" auth login --device --scopes "$SCOPES" || die "授权未完成"
    ok "授权成功（有效期 365 天，到期需重新运行本脚本）"
fi

# ---------- 4. 验证 ----------
step "验证连通性"
"$CLI" $T user me >/dev/null 2>&1 && ok "身份验证通过" || warn "user me 调用失败，稍后可用 wps365-cli mcp doctor 排查"
# 分两步查，才能把「不在企业内」和「缺scope」区分开——两者现象一样但解法完全不同
DOCLIB=$("$CLI" $T drive doclib list --page-size 1 2>&1)
case "$DOCLIB" in
    *400002059*|*"用户不在企业内"*)
        warn "读不到团队文档库：授权时登录的那个账号不在企业内，或未被授予团队文档权限。"
        warn "模式A请确认使用者已加入企业；模式B请确认授权时登录的是有权限的账号——"
        warn "在此之前 Agent 读不到任何企业文件。" ;;
    *'"code": 0'*|*'"code":0'*)
        ok "团队文档库可访问"
        if "$CLI" $T drive file search --keyword "a" --page-size 1 >/dev/null 2>&1; then
            ok "全库搜索可用"
        else
            warn "全库搜索不可用——多半缺 kso.file.search，请管理员在后台申请后重新运行本脚本"
        fi ;;
    *)
        warn "团队库检查异常：$(printf '%s' "$DOCLIB" | head -c 150)" ;;
esac

# ---------- 5. 传统表格补充工具 ----------
if [ -n "$PY" ]; then
    step "安装传统表格工具（官方 MCP 不支持 .xls/.xlsx）"
    if [ -f "$HERE/wps_sheets_mcp.py" ]; then
        mkdir -p "$SHEETS_DIR"
        cp "$HERE/wps_sheets_mcp.py" "$SHEETS_DIR/"
        ok "传统表格工具已安装到 $SHEETS_DIR"
    else
        warn "同目录没找到 wps_sheets_mcp.py，跳过（传统表格将无法读取）"
        SHEETS_DIR=""
    fi

    # 扫描件 OCR：多平台，按当前系统检查依赖并给出对应指引
    if [ -f "$HERE/wps_ocr_mcp.py" ]; then
        mkdir -p "$SHEETS_DIR"
        cp "$HERE/wps_ocr_mcp.py" "$SHEETS_DIR/"
        OCR_DIR="$SHEETS_DIR"
        case "$(uname)" in
            Darwin)
                if command -v swiftc >/dev/null 2>&1 || [ -x /usr/bin/swiftc ]; then
                    ok "扫描件OCR已就绪（macOS系统自带Vision，零额外依赖）"
                else
                    warn "扫描件OCR需要 swift 编译器，请执行：xcode-select --install"
                fi ;;
            Linux)
                MISS=""
                "$PY" -c "import pypdfium2" >/dev/null 2>&1 || MISS="pypdfium2"
                command -v tesseract >/dev/null 2>&1 || MISS="$MISS tesseract"
                if [ -z "$MISS" ]; then
                    ok "扫描件OCR已就绪（tesseract）"
                else
                    warn "扫描件OCR还缺：$MISS"
                    warn "  pip install pypdfium2 && sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra"
                fi ;;
            *)
                warn "扫描件OCR：Windows 请在安装后让 Agent 调用 ocr_status 查看本机缺什么" ;;
        esac
    fi
else
    SHEETS_DIR=""
fi

# ---------- 6. 写入 MCP 配置 ----------
step "写入 Claude Code 配置"
if [ -z "$PY" ]; then
    warn "缺 python3，请手动把下面内容加进 $CLAUDE_CFG 的 mcpServers："
    echo "      \"wps365\": {\"command\": \"$CLI\", \"args\": [\"mcp\",\"serve\"], \"env\": {}, \"timeout\": 600}"
else
    "$PY" - "$CLAUDE_CFG" "$CLI" "$SHEETS_DIR" "$OCR_DIR" <<'PYEOF'
import json, os, shutil, sys, time
cfg_path, cli, sheets_dir, ocr_dir = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

if os.path.exists(cfg_path):
    shutil.copy2(cfg_path, f"{cfg_path}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        data = json.load(open(cfg_path, encoding="utf-8"))
    except json.JSONDecodeError:
        print("  ! 现有配置不是合法 JSON，已备份但不修改，请手动处理"); raise SystemExit(0)
else:
    data = {}

servers = data.setdefault("mcpServers", {})
servers["wps365"] = {"type": "stdio", "command": cli, "args": ["mcp", "serve"],
                     "env": {}, "timeout": 600}
if sheets_dir:
    servers["wps-sheets"] = {"type": "stdio", "command": "python3",
                             "args": [os.path.join(sheets_dir, "wps_sheets_mcp.py")],
                             "env": {"WPS365_CLI": cli}}
if ocr_dir:
    servers["wps-ocr"] = {"type": "stdio", "command": "python3",
                          "args": [os.path.join(ocr_dir, "wps_ocr_mcp.py")],
                          "env": {"WPS365_CLI": cli}}
json.dump(data, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"  ✓ 已写入（原配置已备份）。当前 MCP：{', '.join(servers)}")
PYEOF
fi

echo
echo "=========================================="
echo " 安装完成"
echo "=========================================="
echo
echo "  ▸ 重启 Claude Code 后即可使用"
echo "  ▸ 排查：$CLI mcp doctor"
echo "  ▸ 能读：云文档目录、全库搜索、Word/PDF正文、表格内容"
echo "  ▸ 扫描件PDF：用 ocr_scanned_pdf 本地识别（数据不出本机）；先调 ocr_status 自查依赖"
echo
echo "  ▸ 用 Cursor / Claude Desktop 等其他客户端？把下面这段贴进它的 MCP 配置："
echo
echo "      \"wps365\":     { \"command\": \"$CLI\", \"args\": [\"mcp\",\"serve\"], \"env\": {}, \"timeout\": 600 }"
if [ -n "$SHEETS_DIR" ]; then
    echo "      \"wps-sheets\": { \"command\": \"python3\", \"args\": [\"$SHEETS_DIR/wps_sheets_mcp.py\"], \"env\": {\"WPS365_CLI\": \"$CLI\"} }"
fi
if [ -n "$OCR_DIR" ]; then
    echo "      \"wps-ocr\":    { \"command\": \"python3\", \"args\": [\"$OCR_DIR/wps_ocr_mcp.py\"], \"env\": {\"WPS365_CLI\": \"$CLI\"} }"
fi
echo "    配置文件位置见交付说明第七节。凭证共用，无需重新授权。"
echo
