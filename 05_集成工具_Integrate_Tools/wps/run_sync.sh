#!/bin/bash
# 定时同步入口：cron/launchd 调这个脚本。日志按月切。
cd "$(dirname "$0")" || exit 1
mkdir -p logs
/usr/local/bin/python3 wps_sync.py sync >> "logs/sync_$(date +%Y%m).log" 2>&1
