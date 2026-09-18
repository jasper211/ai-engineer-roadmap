#!/bin/bash
# WPS 云文档同步 · 服务器部署脚本（Ubuntu / Debian）
#
# 本脚本只做环境准备，不含任何凭证、也不会启动同步任务。
# 执行后需由凭证持有人完成一次授权，再由你确认启用定时器。
#
# 用法：sudo bash deploy.sh

set -euo pipefail

# ---------- 可调参数 ----------
SYNC_USER="${SYNC_USER:-wpssync}"                       # 运行账号（非 root）
DATA_DIR="${DATA_DIR:-/mnt/newdisk/wps-mirror}"         # 镜像目录（Syncthing 共享的就是它）
APP_DIR="${APP_DIR:-/opt/wps-sync}"                     # 程序目录
SYNC_ARGS="${SYNC_ARGS:---only-docs}"                   # 同步范围，见文末说明
SYNC_TIME="${SYNC_TIME:-03:00}"                         # 每天执行时间
# ------------------------------

say()  { echo -e "\n▶ $*"; }
ok()   { echo "  ✓ $*"; }
warn() { echo "  ! $*"; }
die()  { echo -e "\n✗ $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 执行：sudo bash deploy.sh"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/../wps_mirror.py" ] || [ -f "$HERE/wps_mirror.py" ] || die "同目录或上级目录找不到 wps_mirror.py"
SRC="$HERE/wps_mirror.py"; [ -f "$SRC" ] || SRC="$HERE/../wps_mirror.py"

echo "=========================================="
echo " WPS 云文档同步 · 服务器部署"
echo "=========================================="
echo "  运行账号 : $SYNC_USER"
echo "  镜像目录 : $DATA_DIR"
echo "  程序目录 : $APP_DIR"
echo "  同步范围 : $SYNC_ARGS"
echo "  执行时间 : 每天 $SYNC_TIME"

# ---------- 1. 依赖检查 ----------
say "检查依赖"
for c in python3 curl; do
    command -v $c >/dev/null || die "缺少 $c，请先安装"
    ok "$c: $($c --version 2>&1 | head -1)"
done
PYV=$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')
python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' || die "python3 需 3.9+，当前 $PYV"
ok "python 版本满足要求（$PYV）"

# ---------- 2. 运行账号 ----------
say "准备运行账号"
if id "$SYNC_USER" &>/dev/null; then
    ok "账号已存在：$SYNC_USER"
else
    useradd -r -m -d "/home/$SYNC_USER" -s /bin/bash "$SYNC_USER"
    ok "已创建账号：$SYNC_USER（无需 sudo 权限）"
fi

# ---------- 3. 目录与权限 ----------
say "准备目录"
mkdir -p "$DATA_DIR" "$APP_DIR"
chown -R "$SYNC_USER:$SYNC_USER" "$DATA_DIR" "$APP_DIR"
# 750：属主可读写，同组可读，其他人完全不可访问。
# 这些文件含保单号/证件号/账号，不要放开 o+r。
chmod 750 "$DATA_DIR"
chmod 755 "$APP_DIR"
ok "镜像目录 $DATA_DIR（750，属主 $SYNC_USER）"
ok "程序目录 $APP_DIR"
if [ -d "$DATA_DIR/.stfolder" ]; then
    ok "检测到 Syncthing folder 标记，同步程序会自动维护 .stignore"
else
    warn "$DATA_DIR 还不是 Syncthing folder；若要共享，请在 Syncthing 中添加该目录"
fi

# ---------- 4. 安装程序 ----------
say "安装同步程序"
install -o "$SYNC_USER" -g "$SYNC_USER" -m 755 "$SRC" "$APP_DIR/wps_mirror.py"
ok "已安装：$APP_DIR/wps_mirror.py"

# ---------- 5. 安装 wps365-cli ----------
say "安装 wps365-cli（金山官方 CLI）"
CLI_PATH="/home/$SYNC_USER/.local/bin/wps365-cli"
if [ -x "$CLI_PATH" ]; then
    ok "已安装：$(sudo -u "$SYNC_USER" "$CLI_PATH" --version 2>/dev/null)"
else
    sudo -u "$SYNC_USER" bash -c \
        'curl -fsSL https://open-docs.wpscdn.cn/cli/install.sh | bash -s -- --no-modify-path' \
        || die "CLI 安装失败，检查服务器能否访问 open-docs.wpscdn.cn"
    [ -x "$CLI_PATH" ] || die "CLI 安装后未找到 $CLI_PATH"
    ok "已安装：$(sudo -u "$SYNC_USER" "$CLI_PATH" --version 2>/dev/null)"
fi

# ---------- 6. systemd ----------
say "配置 systemd"
cat > /etc/systemd/system/wps-mirror.service <<UNIT
[Unit]
Description=WPS 云文档 → 本地镜像同步
Documentation=file://$APP_DIR/部署说明_运维.md
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$SYNC_USER
Group=$SYNC_USER
WorkingDirectory=$APP_DIR
Environment="WPS365_CLI=$CLI_PATH"
ExecStart=/usr/bin/python3 $APP_DIR/wps_mirror.py --mirror $DATA_DIR $SYNC_ARGS
# 首次全量可能数小时，给足时间；超时会被终止但进度已落库，下轮自动续
TimeoutStartSec=8h
Nice=10
IOSchedulingClass=idle
# 与同机其他业务共存：降低优先级，避免抢占 IO
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$DATA_DIR $APP_DIR /home/$SYNC_USER

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/wps-mirror.timer <<UNIT
[Unit]
Description=每天执行 WPS 云文档同步

[Timer]
OnCalendar=*-*-* $SYNC_TIME:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
ok "已写入 wps-mirror.service 与 wps-mirror.timer"
warn "定时器尚未启用 —— 需完成授权并人工验证后再启用"

# ---------- 7. 日志轮转 ----------
say "配置日志轮转"
cat > /etc/logrotate.d/wps-mirror <<ROT
$APP_DIR/sync.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    su $SYNC_USER $SYNC_USER
}
ROT
ok "日志按周轮转，保留 8 周"

# ---------- 完成 ----------
cat <<TIP

==========================================
 环境准备完成 —— 尚未授权，也未启动同步
==========================================

接下来由【凭证持有人】执行授权（本脚本不含任何密钥）：

  sudo -u $SYNC_USER -i
  ~/.local/bin/wps365-cli auth setup --client-id <APPID>
      # 三个提示依次：粘贴 APPKEY 回车 / 直接回车 / 直接回车
  ~/.local/bin/wps365-cli auth login --device --scopes \\
    "kso.user_base.read,kso.file.read,kso.file.search,kso.doclib.readwrite,kso.drive.readwrite,kso.file_link.readwrite,kso.dbsheet.read,kso.sheets.read,kso.airsheet.read,kso.airsheet.readwrite"
      # 会输出链接和验证码，在任意一台有浏览器的电脑上打开确认
      # 链接若是 http:// 开头，务必手动改成 https://

授权后先做一次试运行（只统计，不下载任何文件）：

  sudo -u $SYNC_USER /usr/bin/python3 $APP_DIR/wps_mirror.py \\
      --mirror $DATA_DIR $SYNC_ARGS --dry-run

确认统计结果符合预期后，手动跑第一次真实同步并观察：

  sudo systemctl start wps-mirror.service
  journalctl -u wps-mirror.service -f

一切正常后，再启用每日定时：

  sudo systemctl enable --now wps-mirror.timer
  systemctl list-timers wps-mirror.timer

同步范围可改 SYNC_ARGS 后重跑本脚本：
  --only-docs                仅文档表格类（约 1.2GB，推荐先用这个）
  (留空)                     全量（约 13.8GB，含 PDF 与图片）
  --drives "商务结算,佣金管理"  仅指定库

TIP
