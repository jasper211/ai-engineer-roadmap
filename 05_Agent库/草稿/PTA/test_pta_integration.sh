#!/bin/bash
# PTA Agent 集成测试脚本
# 测试完整流程: S01 -> S02 -> S03 -> S04 -> S05

set -e

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

python3 "$PTA_DIR/PTA-S01_意图解析器.py" \
    "帮我看看" \
    --output "$TEST_DIR/task_package_2.json" 2>&1 | grep -q "需要澄清"

if [ $? -eq 0 ]; then
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

python3 "$PTA_DIR/PTA-S04_文档同步器.py" \
    --task-id "P2-01" \
    --task-name "PTA Agent 搭建" \
    --message "test: PTA integration test" \
    --status "进行中" \
    --dry-run 2>&1 | grep -q "DRY-RUN"

if [ $? -eq 0 ]; then
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
echo ""
echo "测试产物:"
echo "  任务包: $TEST_DIR/task_package_1.json"
echo "  执行计划: $TEST_DIR/execution_plan.json"
echo "  进度报告: $TEST_DIR/progress_report.json"
echo "  执行记录: $RECORD_DIR/任务执行记录.md"
echo ""
