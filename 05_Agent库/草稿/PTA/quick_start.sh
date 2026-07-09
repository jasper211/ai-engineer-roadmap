#!/bin/bash
# PTA Agent · 快速启动脚本
# 用法: bash quick_start.sh [任务指令]
# 示例: bash quick_start.sh "按顺序完成 P2-02, P2-03"

set -e

PTA_DIR="$(cd "$(dirname "$0")" && pwd)"
TASK_INPUT="${1:-\"按顺序完成 P2-02, P2-03\"}"
TEST_DIR="/tmp/pta_quickstart"

echo "============================================================"
echo "PTA Agent · 快速启动"
echo "============================================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    echo "请安装 Python 3.7+"
    exit 1
fi

echo "✅ Python 版本: $(python3 --version)"
echo ""

# 创建测试目录
mkdir -p "$TEST_DIR"

# Step 1: 意图解析
echo "[Step 1/6] 意图解析..."
python3 "$PTA_DIR/PTA-S01_意图解析器.py" "$TASK_INPUT" --output "$TEST_DIR/task.json" > /dev/null 2>&1
if [ -f "$TEST_DIR/task.json" ]; then
    echo "✅ 任务包已生成: $TEST_DIR/task.json"
else
    echo "❌ 意图解析失败"
    exit 1
fi

# Step 2: 执行调度（dry-run）
echo ""
echo "[Step 2/6] 执行调度（dry-run）..."
python3 "$PTA_DIR/PTA-S02_执行调度器.py" --input "$TEST_DIR/task.json" --dry-run > /dev/null 2>&1
if [ -f "$TEST_DIR/execution_plan.json" ]; then
    echo "✅ 执行计划已生成: $TEST_DIR/execution_plan.json"
else
    echo "❌ 执行调度失败"
    exit 1
fi

# Step 3: 进度追踪
echo ""
echo "[Step 3/6] 进度追踪..."
python3 "$PTA_DIR/PTA-S03_进度追踪器.py" --plan "$TEST_DIR/execution_plan.json" --output "$TEST_DIR/progress.json" > /dev/null 2>&1
if [ -f "$TEST_DIR/progress.json" ]; then
    echo "✅ 进度报告已生成: $TEST_DIR/progress.json"
else
    echo "❌ 进度追踪失败"
    exit 1
fi

# Step 4: 文档同步（dry-run）
echo ""
echo "[Step 4/6] 文档同步（dry-run）..."
python3 "$PTA_DIR/PTA-S04_文档同步器.py" --task-id "TEST-001" --task-name "快速测试" -m "test: quick start" --dry-run > /dev/null 2>&1
echo "✅ 文档同步测试通过"

# Step 5: 归档复盘
echo ""
echo "[Step 5/6] 归档复盘..."
python3 "$PTA_DIR/PTA-S05_归档复盘器.py" --plan "$TEST_DIR/execution_plan.json" --task-id "TEST-001" --task-name "快速测试" --no-lessons > /dev/null 2>&1
echo "✅ 归档复盘完成"

# Step 6: 外部项目分析（示例）
echo ""
echo "[Step 6/6] 外部项目分析（示例）..."
python3 "$PTA_DIR/PTA-EXT_外部项目分析器.py" --path "$PTA_DIR" --depth 1 --markdown "$TEST_DIR/project_report.md" > /dev/null 2>&1
if [ -f "$TEST_DIR/project_report.md" ]; then
    echo "✅ 项目分析报告已生成: $TEST_DIR/project_report.md"
else
    echo "❌ 项目分析失败"
    exit 1
fi

echo ""
echo "============================================================"
echo "PTA Agent · 快速启动完成"
echo "============================================================"
echo ""
echo "所有组件运行正常 ✅"
echo ""
echo "测试产物:"
echo "  任务包: $TEST_DIR/task.json"
echo "  执行计划: $TEST_DIR/execution_plan.json"
echo "  进度报告: $TEST_DIR/progress.json"
echo "  项目分析: $TEST_DIR/project_report.md"
echo ""
echo "使用指南:"
echo "  详细文档: $PTA_DIR/README.md"
echo "  平台指南: $PTA_DIR/AI_PLATFORM_GUIDE.md"
echo "  集成测试: $PTA_DIR/test_pta_integration.sh"
echo ""
