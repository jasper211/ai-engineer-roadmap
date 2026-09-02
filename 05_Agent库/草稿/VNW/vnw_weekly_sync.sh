#!/bin/bash
# vnw_weekly_sync.sh —— 每周检查EA源头变化，重跑受影响L3的AI分析，重建快照并部署
# 只在本地跑：依赖本机已登录的Vercel CLI会话和deepseek_config.json里的API key，
# 云端定时agent拿不到这两样凭证，所以这个脚本必须用本机crontab触发，不能搬到云端。
set -e
cd "/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/VNW/04_定义Agent_Define_Agent/agents"

CHECK=$(python3 agent.py --check-source-updates)
CHANGED=$(echo "$CHECK" | python3 -c "import json,sys; print(json.load(sys.stdin)['report']['changed_l3_count'])")

if [ "$CHANGED" = "0" ]; then
  echo "[$(date)] 无待处理变化，跳过。"
  exit 0
fi

echo "[$(date)] 发现 $CHANGED 个L3需要重跑，开始处理..."
python3 agent.py --apply-source-updates

# 提取本次变化涉及的L3编码，逐个prepare
L3_CODES=$(echo "$CHECK" | python3 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(c['l3_code'] for c in d['report']['changes']))")
PREPARE_ARGS=""
for code in $L3_CODES; do
  PREPARE_ARGS="$PREPARE_ARGS --prepare-l3-analysis $code"
done
PREPARED=$(python3 agent.py $PREPARE_ARGS)

# 逐个跑AI统一分析
echo "$PREPARED" | python3 -c "
import json, sys, subprocess
d = json.load(sys.stdin)
for run in d['runs']:
    print(f\"重跑 {run['l3_code']}...\")
    subprocess.run(['python3', 'agent.py', '--run-analysis-dir', run['run_dir']], check=True)
"

# 收尾：批量重建快照
python3 agent.py --build-all-model-snapshots

# 部署前端
cd "../../10_部署与运行_Deploy_and_Run/frontend"
npx vercel --prod --yes

echo "[$(date)] 本周同步完成。"
