#!/bin/bash
# PTA Agent · 快速启动脚本（v2.1.0：适配 01-11 编号方法论结构，本脚本自己
# 位于 10_部署与运行_Deploy_and_Run/ 里，PTA_DIR 需要往上退一层才是项目根目录）
# 用法: bash quick_start.sh [任务指令]
# 示例: bash quick_start.sh "按顺序完成 P2-02, P2-03"

set -e

PTA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TASK_INPUT="${1:-按顺序完成 P2-02, P2-03}"

echo "============================================================"
echo "PTA Agent · 快速启动"
echo "============================================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    echo "请安装 Python 3.7+"
    exit 1
fi

echo "✅ Python 版本: $(python3 --version)"
echo ""

AGENT_PY="$PTA_DIR/04_定义Agent_Define_Agent/agents/agent.py"

echo "[1/2] Think-Act-Observe 全链路（dry-run，不产生真实副作用）..."
python3 "$AGENT_PY" "$TASK_INPUT"
echo ""

echo "[2/2] 状态记忆..."
python3 "$AGENT_PY" --status
echo ""

echo "============================================================"
echo "PTA Agent · 快速启动完成"
echo "============================================================"
echo ""
echo "使用指南:"
echo "  详细文档: $PTA_DIR/README.md"
echo "  平台指南: $PTA_DIR/AI_PLATFORM_GUIDE.md"
echo "  指令示例: $PTA_DIR/08_设计提示词_Design_Prompts/prompts/task_examples.md"
echo "  集成测试: python3 $PTA_DIR/09_测试与调试_Test_and_Debug/tests/test_integration.py"
echo ""
