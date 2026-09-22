#!/bin/bash
# WPS 云盘 → 服务器镜像 · 定时同步入口。cron 调用此脚本。
#
# 三件事：单实例互斥、跑同步、把结果落到 LAST_RUN 供巡检。
# 不要直接 cron 调 wps_mirror.py——没有锁，两轮撞上会打乱状态库。

DIR="/home/WPSIN/wps-sync"
LOG="$DIR/sync.log"
STATUS="$DIR/LAST_RUN"
export WPS365_CLI="/home/WPSIN/.local/bin/wps365-cli"
cd "$DIR" || exit 1

# 单实例：上一轮还在跑就安静退出。首次全量要 6 小时以上，
# 期间 cron 照常触发，不加锁会起第二个实例。
exec 9>"$DIR/.sync.lock"
if ! /usr/bin/flock -n 9; then
    echo "$(date "+%F %T") [跳过] 上一轮同步仍在运行，本轮不启动" >> "$LOG"
    exit 0
fi

/home/WPSIN/wps-sync/rotate_log.sh

START=$(date "+%F %T")
# 程序的 log() 本身就在写 $LOG，stdout 再重定向过去会把每行写两遍。
# stderr 必须留着——Python 崩溃的 traceback 只走 stderr。
/usr/bin/python3 "$DIR/wps_mirror.py" --mirror "/mnt/newdisk/wps-mirror" >/dev/null 2>>"$LOG"
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

FILES=$(find /mnt/newdisk/wps-mirror -type f ! -path "*/.stfolder/*" 2>/dev/null | wc -l)
SIZE=$(du -sh /mnt/newdisk/wps-mirror 2>/dev/null | cut -f1)
# 从本轮日志尾部取程序自己的统计口径。
# 取「最后一次」出现的值：日志是累积的，同名字段历史上出现过很多次。
pick() { tail -60 "$LOG" | grep -E "^[0-9-]+ [0-9:]+ $1" | tail -1 | sed -E "s/^[0-9-]+ [0-9:]+ $1[[:space:]]*//"; }
CLOUD=$(pick "云端文件")
DL=$(pick "本次下载")
FAIL=$(pick "下载失败")
DEL=$(pick "本地删除")
ABORT=$(pick "清理已中止")
TAILSTAT="云端文件 ${CLOUD:-?} / 本次下载 ${DL:-?} / 失败 ${FAIL:-?} / 删除 ${DEL:-?}"
[ -n "$ABORT" ] && TAILSTAT="$TAILSTAT / !! 清理已中止：$ABORT"

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
  echo "本次结果        ：$([ $RC -eq 0 ] && echo "正常" || echo "失败 —— 请联系运维查看服务器 /home/WPSIN/wps-sync/sync.log")"
  echo "文件夹内容      ：$FILES 个文件 / $SIZE"
  echo "本次新增或更新  ：${DL:-0} 个文件"
  if [ -n "$FAIL" ] && [ "$FAIL" != "0" ]; then
    echo "本次未取回      ：$FAIL 个（下次同步会自动重试，通常无需处理）"
  fi
  if [ -n "$DEL" ] && [ "$DEL" != "0" ]; then
    echo "本次移除        ：$DEL 个（这些文件已在 WPS 上删除）"
  fi
  if [ -n "$ABORT" ]; then
    echo "!! 请联系运维    ：本次有 $ABORT 个文件在 WPS 上查不到，为防误删已暂停清理"
  fi
  echo "$AUTH_LINE"
  echo
  echo "说明：本文件夹是 WPS 云盘的只读副本，每天凌晨 2 点自动核对更新。"
  echo "      内容的增删改一律在 WPS 上进行，这里的改动不会回传，也会在下次同步时被覆盖。"
} > "/mnt/newdisk/wps-mirror/_同步状态.txt" 2>/dev/null

exit $RC
