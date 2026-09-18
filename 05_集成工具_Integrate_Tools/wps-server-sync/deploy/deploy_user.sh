#!/bin/bash
# WPS 云文档同步 · 用户级部署（无需 root）
#
# 适用于只有普通账号、拿不到 sudo 的情况。
# 全部装在当前用户家目录，用 crontab 定时，不碰任何系统目录。
#
# 用法：bash deploy_user.sh

set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/wps-sync}"
DATA_DIR="${DATA_DIR:-/mnt/newdisk/wps-mirror}"
SYNC_ARGS="${SYNC_ARGS:---only-docs}"
SYNC_TIME="${SYNC_TIME:-03:00}"

say()  { echo -e "\n▶ $*"; }
ok()   { echo "  ✓ $*"; }
warn() { echo "  ! $*"; }
die()  { echo -e "\n✗ $*" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$HOME/.local/bin/wps365-cli"

echo "=========================================="
echo " WPS 云文档同步 · 用户级部署"
echo "=========================================="
echo "  账号     : $(whoami)"
echo "  程序目录 : $APP_DIR"
echo "  镜像目录 : $DATA_DIR"
echo "  同步范围 : $SYNC_ARGS"

say "检查环境"
command -v python3 >/dev/null || die "缺少 python3"
python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' \
    || die "python3 需 3.9+，当前 $(python3 -V)"
ok "python3: $(python3 -V 2>&1)"
command -v curl >/dev/null || die "缺少 curl"
ok "curl: $(curl --version | head -1 | cut -d' ' -f1-2)"
[ -w "$(dirname "$DATA_DIR")" ] || [ -w "$DATA_DIR" ] \
    || die "$DATA_DIR 所在位置不可写"
ok "数据目录位置可写"

say "准备目录"
mkdir -p "$APP_DIR" "$DATA_DIR"
ok "程序目录 $APP_DIR"
ok "镜像目录 $DATA_DIR"
if [ -d "$DATA_DIR/.stfolder" ]; then
    ok "已是 Syncthing folder，程序会自动维护 .stignore"
else
    warn "尚未被 Syncthing 共享；待验证通过后再添加为 folder"
fi

say "安装同步程序"
[ -f "$HERE/wps_mirror.py" ] || die "同目录找不到 wps_mirror.py"
install -m 755 "$HERE/wps_mirror.py" "$APP_DIR/wps_mirror.py"
ok "$APP_DIR/wps_mirror.py"

say "安装 wps365-cli"
if [ -x "$CLI" ]; then
    ok "已安装：$("$CLI" --version 2>/dev/null)"
else
    curl -fsSL https://open-docs.wpscdn.cn/cli/install.sh | bash -s -- --no-modify-path \
        || die "CLI 安装失败，检查能否访问 open-docs.wpscdn.cn"
    [ -x "$CLI" ] || die "安装后找不到 $CLI"
    ok "已安装：$("$CLI" --version 2>/dev/null)"
fi

say "生成运行脚本"
cat > "$APP_DIR/run_sync.sh" <<RUNNER
#!/bin/bash
# 由 deploy_user.sh 生成。cron 调用此脚本。
export WPS365_CLI="$CLI"
cd "$APP_DIR"
exec /usr/bin/python3 "$APP_DIR/wps_mirror.py" --mirror "$DATA_DIR" $SYNC_ARGS
RUNNER
chmod +x "$APP_DIR/run_sync.sh"
ok "$APP_DIR/run_sync.sh"

cat > "$APP_DIR/rotate_log.sh" <<'ROT'
#!/bin/bash
# 简易日志轮转：超过 50MB 就切一份，保留 4 份（无 root 时用不了 logrotate）
LOG="$(dirname "$0")/sync.log"
[ -f "$LOG" ] || exit 0
SIZE=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
[ "$SIZE" -lt 52428800 ] && exit 0
for i in 3 2 1; do
    [ -f "$LOG.$i" ] && mv "$LOG.$i" "$LOG.$((i+1))"
done
mv "$LOG" "$LOG.1"
ROT
chmod +x "$APP_DIR/rotate_log.sh"
ok "$APP_DIR/rotate_log.sh（日志超 50MB 自动切分）"

cat <<TIP

==========================================
 部署完成 —— 尚未授权，也未启用定时
==========================================

【下一步 1】授权（需要 APPKEY 与一次浏览器确认）

  $CLI auth setup --client-id <APPID>
      三个提示依次：粘贴 APPKEY 回车 / 直接回车 / 直接回车

  $CLI auth login --device --scopes \\
"kso.user_base.read,kso.file.read,kso.file.search,kso.doclib.readwrite,kso.drive.readwrite,kso.file_link.readwrite,kso.dbsheet.read,kso.sheets.read,kso.airsheet.read,kso.airsheet.readwrite"
      输出链接和验证码，在任意有浏览器的电脑上打开确认
      链接若是 http:// 开头，务必手动改成 https://

【下一步 2】冒烟测试（只下 1 个文件）

  WPS365_CLI=$CLI /usr/bin/python3 $APP_DIR/wps_mirror.py \\
      --mirror $DATA_DIR --drives "流程与规则"

【下一步 3】看规模，再跑正式范围

  WPS365_CLI=$CLI /usr/bin/python3 $APP_DIR/wps_mirror.py \\
      --mirror $DATA_DIR $SYNC_ARGS --dry-run

【下一步 4】确认无误后启用每日定时

  (crontab -l 2>/dev/null; echo "${SYNC_TIME#*:} ${SYNC_TIME%:*} * * * $APP_DIR/rotate_log.sh && $APP_DIR/run_sync.sh >> $APP_DIR/cron.log 2>&1") | crontab -
  crontab -l

TIP
