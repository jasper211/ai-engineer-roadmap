#!/bin/bash
# PTA Agent 集成测试脚本
# 测试完整流程: S01 -> S02 -> S03 -> S04 -> S05

# v1.1（2026-07-09，按D-20260709-001 Agent验证方法论复核后修正）：
# 原来只有 set -e，没有 pipefail——`python3 ... | tail -N` 这种写法下，
# 管道最终退出码是 tail 的（几乎总是0），不是 python 的，set -e 拦不住 python 崩溃。
# 本脚本里这个漏洞目前被每处后续的显式文件/目录存在性检查兜底了，但这是巧合
# 不是设计保证，加 pipefail 让 set -e 真正生效，不依赖侥幸。
set -eo pipefail

PROJECT_ROOT="/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目"
PTA_DIR="$PROJECT_ROOT/05_Agent库/草稿/PTA"
TEST_DIR="/tmp/pta_test"

echo "============================================================"
echo "PTA Agent 集成测试"
echo "============================================================"
echo ""

# 创建测试目录
mkdir -p "$TEST_DIR"

# Test 1: S01 意图解析器
echo "[Test 1] PTA-S01 意图解析器"
echo "------------------------------------------------------------"

# 测试用例 1: 顺序执行任务
python3 "$PTA_DIR/PTA-S01_意图解析器.py" \
    "按顺序完成 P0-02, P0-03, P1-03, P1-04" \
    --output "$TEST_DIR/task_package_1.json" 2>&1 | tail -20

# 验证输出
if [ -f "$TEST_DIR/task_package_1.json" ]; then
    echo "✅ S01 测试 1 通过: 任务包已生成"
    TASK_COUNT=$(python3 -c "import json; d=json.load(open('$TEST_DIR/task_package_1.json')); print(len(d['items']))")
    if [ "$TASK_COUNT" -eq 4 ]; then
        echo "✅ 任务项数量正确: $TASK_COUNT"
    else
        echo "❌ 任务项数量错误: $TASK_COUNT (期望 4)"
        exit 1
    fi
else
    echo "❌ S01 测试 1 失败: 未生成任务包"
    exit 1
fi

echo ""

# 测试用例 2: 模糊指令（需要澄清）
echo "[Test 2] PTA-S01 模糊指令检测"
echo "------------------------------------------------------------"

# v1.1修正：改成 if pipeline; then 直接判断，不再靠"跑完后再查$?"——
# 开了pipefail后，grep -q 没匹配到时管道本身就是非零退出码，写在if条件里
# set -e 不会对它生效（这是bash对if条件表达式的标准豁免），跑完直接查$?的写法
# 在pipefail下反而会被set -e在到达检查语句前就提前把整个脚本终止掉。
if python3 "$PTA_DIR/PTA-S01_意图解析器.py" \
    "帮我看看" \
    --output "$TEST_DIR/task_package_2.json" 2>&1 | grep -q "需要澄清"; then
    echo "✅ S01 测试 2 通过: 正确识别模糊指令"
else
    echo "❌ S01 测试 2 失败: 未识别模糊指令"
    exit 1
fi

echo ""

# Test 2: S02 执行调度器
echo "[Test 3] PTA-S02 执行调度器 (Dry-run)"
echo "------------------------------------------------------------"

python3 "$PTA_DIR/PTA-S02_执行调度器.py" \
    --input "$TEST_DIR/task_package_1.json" \
    --output "$TEST_DIR/execution_plan.json" \
    --dry-run 2>&1 | tail -30

if [ -f "$TEST_DIR/execution_plan.json" ]; then
    echo "✅ S02 测试通过: 执行计划已生成"
    STEP_COUNT=$(python3 -c "import json; d=json.load(open('$TEST_DIR/execution_plan.json')); print(len(d['steps']))")
    echo "✅ 执行步骤数: $STEP_COUNT"
else
    echo "❌ S02 测试失败: 未生成执行计划"
    exit 1
fi

echo ""

# Test 3: S03 进度追踪器
echo "[Test 4] PTA-S03 进度追踪器"
echo "------------------------------------------------------------"

python3 "$PTA_DIR/PTA-S03_进度追踪器.py" \
    --plan "$TEST_DIR/execution_plan.json" \
    --output "$TEST_DIR/progress_report.json" 2>&1 | tail -25

if [ -f "$TEST_DIR/progress_report.json" ]; then
    echo "✅ S03 测试通过: 进度报告已生成"
    STATUS=$(python3 -c "import json; d=json.load(open('$TEST_DIR/progress_report.json')); print(d['status'])")
    echo "✅ 任务状态: $STATUS"
else
    echo "❌ S03 测试失败: 未生成进度报告"
    exit 1
fi

echo ""

# Test 4: S04 文档同步器 (Dry-run)
echo "[Test 5] PTA-S04 文档同步器 (Dry-run)"
echo "------------------------------------------------------------"

# v1.1修正：同Test 2，改成if pipeline; then直接判断，pipefail下避免提前终止
if python3 "$PTA_DIR/PTA-S04_文档同步器.py" \
    --task-id "P2-01" \
    --task-name "PTA Agent 搭建" \
    --message "test: PTA integration test" \
    --status "进行中" \
    --dry-run 2>&1 | grep -q "DRY-RUN"; then
    echo "✅ S04 测试通过: Dry-run 模式正常"
else
    echo "❌ S04 测试失败"
    exit 1
fi

echo ""

# Test 5: S05 归档复盘器
echo "[Test 6] PTA-S05 归档复盘器"
echo "------------------------------------------------------------"

python3 "$PTA_DIR/PTA-S05_归档复盘器.py" \
    --plan "$TEST_DIR/execution_plan.json" \
    --task-id "P2-01" \
    --task-name "PTA Agent 搭建" \
    --no-lessons 2>&1 | tail -20

# 检查执行记录是否生成
RECORD_DIR="$PROJECT_ROOT/01_execution/P2-01_PTA_Agent_搭建"
if [ -d "$RECORD_DIR" ]; then
    echo "✅ S05 测试通过: 执行记录已生成"
    echo "✅ 记录路径: $RECORD_DIR/任务执行记录.md"
else
    echo "❌ S05 测试失败: 未生成执行记录"
    exit 1
fi

echo ""

# Test 7: PTA-RUN 主编排器
echo "[Test 7] PTA-RUN 主编排器 (dry-run，自动串联 S01→S02→S03→S05)"
echo "------------------------------------------------------------"

# v1.6.0 起状态/运行产物落在专属工作区（pta_workspace.py），不再是 PTA_DIR 下的
# .pta_state.json/.pta_runs——用同一个模块算出这次本项目对应的工作区路径，
# 测试前备份真实状态，测试后原样恢复，避免污染真实的任务历史。
HOME_WORKSPACE=$(python3 -c "
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('pta_workspace', '$PTA_DIR/pta_workspace.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m.get_project_workspace(Path('$PROJECT_ROOT')))
")
ORCH_STATE="$HOME_WORKSPACE/state.json"
[ -f "$ORCH_STATE" ] && mv "$ORCH_STATE" "$ORCH_STATE.pre_test_bak"

python3 "$PTA_DIR/PTA-RUN_主编排器.py" "按顺序完成 P1-03, P1-04" 2>&1 | tail -10

STATUS_OUT=$(python3 "$PTA_DIR/PTA-RUN_主编排器.py" --status 2>&1)
echo "$STATUS_OUT" | tail -6

if echo "$STATUS_OUT" | grep -q "历史任务（共 1 条"; then
    echo "✅ 编排器测试通过: 状态记忆已写入专属工作区"
else
    echo "❌ 编排器测试失败: 状态记忆未生成"
    exit 1
fi

# 清理编排器测试产生的临时产物和状态文件（避免污染真实状态/看板归档）
rm -rf "$HOME_WORKSPACE/runs"
rm -f "$ORCH_STATE" "$ORCH_STATE.bak"
[ -f "$ORCH_STATE.pre_test_bak" ] && mv "$ORCH_STATE.pre_test_bak" "$ORCH_STATE"
find "$PROJECT_ROOT/01_execution" -maxdepth 1 -name "T-*" -exec rm -rf {} + 2>/dev/null

echo ""

# Test 8: 跨项目任务知识库（pta_tasks.json 是否真的覆盖了本项目内置的 9 个任务）
echo "[Test 8] 跨项目任务知识库 (pta_tasks.json 生效验证)"
echo "------------------------------------------------------------"

EXT_PROJECT="$TEST_DIR/fake_external_project"
mkdir -p "$EXT_PROJECT"
cat > "$EXT_PROJECT/pta_tasks.json" << 'TASKMAP_EOF'
{
  "ZZ-01": {
    "name": "外部项目专属任务",
    "steps": [
      {"action": "ext_step", "tool": "bash", "command": "echo external-project-marker", "description": "外部项目自定义步骤"}
    ]
  }
}
TASKMAP_EOF

python3 "$PTA_DIR/PTA-S01_意图解析器.py" "执行一下 ZZ-01 这个任务" \
    --project-root "$EXT_PROJECT" --output "$TEST_DIR/ext_task.json" > /dev/null 2>&1

EXT_TASK_NAME=$(python3 -c "import json; print(json.load(open('$TEST_DIR/ext_task.json'))['items'][0]['name'])" 2>/dev/null)

if [ "$EXT_TASK_NAME" = "外部项目专属任务" ]; then
    echo "✅ S01 正确加载外部项目的 pta_tasks.json（任务名: $EXT_TASK_NAME）"
else
    echo "❌ S01 未正确加载外部项目任务知识库（得到: $EXT_TASK_NAME）"
    exit 1
fi

python3 "$PTA_DIR/PTA-S02_执行调度器.py" --input "$TEST_DIR/ext_task.json" \
    --project-root "$EXT_PROJECT" --no-sync --output "$TEST_DIR/ext_plan.json" > /dev/null 2>&1

EXT_ACTION=$(python3 -c "import json; print(json.load(open('$TEST_DIR/ext_plan.json'))['steps'][0]['action'])" 2>/dev/null)

if [ "$EXT_ACTION" = "ext_step" ]; then
    echo "✅ S02 正确使用外部项目自定义步骤（action: $EXT_ACTION，而非通用占位步骤）"
else
    echo "❌ S02 未使用外部项目自定义步骤（得到: $EXT_ACTION）"
    exit 1
fi

echo ""

# Test 9（v1.1新增，按D-20260709-001复核后补）：S04 默认行为验证
# 目的：文档一直写"真实git push需要显式--execute确认"，但代码里根本没有
# --execute这个参数——真实机制是--dry-run不传就是真实执行（危险是默认值，
# 不是要额外加参数才危险）。这条测试在完全隔离、无remote的临时仓库里验证
# "不传--dry-run确实会触发真实commit"，同时因为没配置remote，push必然
# 本地失败，不会碰到任何真实远端，安全。
echo "[Test 9] PTA-S04 默认行为验证（不传--dry-run即真实执行，核实文档里"需要--execute"的说法是否准确）"
echo "------------------------------------------------------------"

SAFE_REPO="$TEST_DIR/safe_isolated_repo"
rm -rf "$SAFE_REPO"
mkdir -p "$SAFE_REPO"
(cd "$SAFE_REPO" && git init -q && git config user.email "test@pta.local" && git config user.name "pta-test" && echo "init" > README.md && git add README.md && git commit -q -m "init")
# 故意不配置remote：即使push被真实触发，也只会在这个隔离仓库里本地失败，不会推到任何真实地址

echo "changed" >> "$SAFE_REPO/README.md"

python3 "$PTA_DIR/PTA-S04_文档同步器.py" \
    --task-id "SAFE-TEST" --task-name "隔离环境安全验证" -m "test: safety check" \
    --project-root "$SAFE_REPO" --files "README.md" 2>&1 | tail -15 || true
# 上面这行故意加 || true：push在无remote仓库里失败是本测试的预期行为之一，
# 不代表S04本身有问题，不应该被pipefail+set -e提前终止整个测试脚本。

COMMIT_COUNT=$(cd "$SAFE_REPO" && git log --oneline | wc -l | tr -d ' ')
if [ "$COMMIT_COUNT" -eq 2 ]; then
    echo "✅ 确认：不传--dry-run时S04默认真实执行了commit（隔离仓库commit数=$COMMIT_COUNT），文档里"需要--execute"的说法不准确，已在架构文档v1.1里同步修正"
else
    echo "❌ 意外：commit未按预期发生（隔离仓库commit数=$COMMIT_COUNT，预期2），需要重新核实S04的默认行为"
    exit 1
fi
rm -rf "$SAFE_REPO"

echo ""
echo "============================================================"
echo "PTA Agent 集成测试完成"
echo "============================================================"
echo ""
echo "测试结果:"
echo "  ✅ S01 意图解析器: 通过 (2/2)"
echo "  ✅ S02 执行调度器: 通过"
echo "  ✅ S03 进度追踪器: 通过"
echo "  ✅ S04 文档同步器: 通过"
echo "  ✅ S05 归档复盘器: 通过"
echo "  ✅ PTA-RUN 主编排器: 通过"
echo "  ✅ 跨项目任务知识库: 通过"
echo "  ✅ S04 默认行为安全验证（v1.1新增）: 通过"
echo ""
echo "测试产物:"
echo "  任务包: $TEST_DIR/task_package_1.json"
echo "  执行计划: $TEST_DIR/execution_plan.json"
echo "  进度报告: $TEST_DIR/progress_report.json"
echo "  执行记录: $RECORD_DIR/任务执行记录.md"
echo ""
