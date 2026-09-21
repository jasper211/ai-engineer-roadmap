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
cat > "$APP_DIR/run_sync.sh" <<'RUNNER'
#!/bin/bash
# WPS 云盘 → 服务器镜像 · 定时同步入口。由 deploy_user.sh 生成，cron 调用。
#
# 三件事：单实例互斥、跑同步、把结果落到 LAST_RUN 供巡检。
# 不要直接 cron 调 wps_mirror.py——没有锁，两轮撞上会打乱状态库。

DIR="@APP_DIR@"
LOG="$DIR/sync.log"
STATUS="$DIR/LAST_RUN"
export WPS365_CLI="@CLI@"
cd "$DIR" || exit 1

# 单实例：上一轮还在跑就安静退出。首次全量要 6 小时以上，
# 期间 cron 照常触发，不加锁会起第二个实例。
exec 9>"$DIR/.sync.lock"
if ! /usr/bin/flock -n 9; then
    echo "$(date "+%F %T") [跳过] 上一轮同步仍在运行，本轮不启动" >> "$LOG"
    exit 0
fi

@APP_DIR@/rotate_log.sh

START=$(date "+%F %T")
/usr/bin/python3 "$DIR/wps_mirror.py" --mirror "@DATA_DIR@" @SYNC_ARGS@ >> "$LOG" 2>&1
RC=$?
END=$(date "+%F %T")

# 授权巡检。refresh_token 是滚动的——每次刷新顺延 365 天，
# 所以只要天天跑就不会过期。真正的风险是长期停摆后无人察觉，
# 因此把剩余天数摆到明面上，不靠谁记日历。
AUTH_LINE=$("$WPS365_CLI" auth status --timeout 25s 2>/dev/null | python3 -c "
import json,sys
from datetime import datetime,timezone
try:
    g=json.load(sys.stdin)[\"delegated\"]
    if not g.get(\"available\"): print(\"授权状态      ：!! 失效 —— 需要 MOMO(蒋辰汐) 重新授权\"); raise SystemExit
    exp=datetime.fromisoformat(g[\"refresh_token_expires_at\"])
    d=(exp-datetime.now(timezone.utc)).days
    flag=\"\" if d>60 else \"   !! 请尽快处理\"
    print(f\"授权剩余      ：{d} 天（每次同步自动顺延；到期日 {exp:%Y-%m-%d}）{flag}\")
except SystemExit: raise
except Exception: print(\"授权状态      ：查询失败，请运维检查\")
" 2>/dev/null)
[ -z "$AUTH_LINE" ] && AUTH_LINE="授权状态      ：查询失败，请运维检查"

FILES=$(find @DATA_DIR@ -type f ! -path "*/.stfolder/*" 2>/dev/null | wc -l)
SIZE=$(du -sh @DATA_DIR@ 2>/dev/null | cut -f1)
# 从本轮日志尾部取程序自己的统计口径
TAILSTAT=$(tail -40 "$LOG" | grep -E "^[0-9-]+ [0-9:]+ (云端文件|下载失败|本地删除|清理已中止)" | sed "s/^[0-9-]* [0-9:]* //")

{
  echo "上次运行 : $START → $END"
  echo "退出码   : $RC $([ $RC -eq 0 ] && echo "(正常)" || echo "(失败，见 sync.log)")"
  echo "镜像现状 : $FILES 个文件 / $SIZE"
  echo "$AUTH_LINE"
  echo "$TAILSTAT"
} > "$STATUS"

# 同一份状态写进镜像根目录，随 Syncthing 分发到所有接收方。
# 交接后没人会登服务器看日志，但打开文件夹就能看见这份数据是什么时候的。
{
  echo "WPS 云盘 → 本文件夹  同步状态"
  echo "（本文件由同步程序每天自动重写，请勿手动编辑或删除）"
  echo
  echo "最后一次同步完成：$END"
  echo "本次结果        ：$([ $RC -eq 0 ] && echo "正常" || echo "失败 —— 请联系运维查看服务器 @APP_DIR@/sync.log")"
  echo "文件夹内容      ：$FILES 个文件 / $SIZE"
  echo "$AUTH_LINE"
  echo
  echo "$TAILSTAT"
  echo
  echo "说明：本文件夹是 WPS 云盘的只读副本，每天凌晨 2 点自动核对更新。"
  echo "      内容的增删改一律在 WPS 上进行，这里的改动不会回传，也会在下次同步时被覆盖。"
} > "@DATA_DIR@/_同步状态.txt" 2>/dev/null

exit $RC
RUNNER
sed -i "s|@APP_DIR@|$APP_DIR|g; s|@CLI@|$CLI|g; s|@DATA_DIR@|$DATA_DIR|g; s|@SYNC_ARGS@|$SYNC_ARGS|g" \
    "$APP_DIR/run_sync.sh"
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
