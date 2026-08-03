#!/bin/zsh
set -eu

VNW_ROOT="/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/VNW"
RUNTIME_DIR="$VNW_ROOT/.vnw_workspace/source_updates"
LOCK_DIR="$RUNTIME_DIR/check.lock"

mkdir -p "$RUNTIME_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$VNW_ROOT"
/usr/local/bin/python3 04_定义Agent_Define_Agent/agents/agent.py --check-source-updates
