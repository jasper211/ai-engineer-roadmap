# PTA Agent · 跨 AI 平台验证指令模板

> 复制以下内容，粘贴到 Kimi / Codex / Claude / 任何 AI 平台

---

## 指令 1：环境验证（先执行这个）

```
我在本地有一个 PTA Agent 项目，需要验证它是否能正常运行。

项目路径：/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA/

请帮我执行以下验证步骤：

1. 检查 Python 版本（需要 3.7+）
2. 列出 PTA 目录下的所有文件
3. 运行集成测试：python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
4. 报告测试结果

注意：
- 只读操作，不要修改任何文件
- 如果测试失败，报告具体错误
```

---

## 指令 2：单组件测试（如果集成测试失败）

```
PTA 集成测试失败，请帮我逐个排查：

项目路径：/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA/

v2.0.0 起 S01-S05 不再是可独立调用的脚本（改成了 skills/ 下的 Python 类，
只能被同进程内的代码 import 调用），请依次执行：

1. python3 09_测试与调试_Test_and_Debug/tests/test_integration.py 2>&1 | head -60   # 看 Test 1-6 分别是否通过（对应原 S01-S05）
2. python3 04_定义Agent_Define_Agent/agents/agent.py "按顺序完成 P2-02, P2-03"      # 端到端跑一次全链路（dry-run）
3. python3 04_定义Agent_Define_Agent/agents/agent.py --status                        # 确认状态记忆写入正常
4. python3 11_监控与优化_Monitor_and_Optimize/PTA-EXT_外部项目分析器.py --path /tmp --depth 1 --markdown /tmp/test_report.md

每执行一个，报告结果。
```

---

## 指令 3：完整工作流测试

```
请帮我演示 PTA Agent 的完整工作流：

项目路径：/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA/

步骤：
1. 解析意图："按顺序完成 P0-02, P0-03, P1-03, P1-04"
2. 生成执行计划（dry-run）
3. 监控进度
4. 生成执行记录

请展示每个步骤的输入输出。
```

---

## 指令 4：外部项目分析测试

```
请帮我测试 PTA 的外部项目分析功能：

PTA 路径：/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA/

目标项目：/Users/zhaoqitrenda.cn/Desktop/Rw权益项目

执行：
python3 11_监控与优化_Monitor_and_Optimize/PTA-EXT_外部项目分析器.py --path "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目" --depth 2 --markdown /tmp/rw_report.md

然后读取 /tmp/rw_report.md，告诉我项目结构。
```

---

## 指令 5：故障排查

```
PTA 运行出错，请帮我排查：

项目路径：/Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA/

错误信息：[粘贴错误信息]

请：
1. 检查 Python 版本
2. 检查文件权限
3. 检查是否有缺失的依赖
4. 给出修复建议
```

---

## 指令 8：项目仪表盘（以人为中心）

```
请帮我生成 Rw 权益项目的仪表盘：

项目路径：/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动

执行：
cd /Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA

# 生成 Roy 的个人仪表盘
python3 11_监控与优化_Monitor_and_Optimize/PTA-DASH_项目仪表盘.py --project "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动" --person "Roy"

# 生成 MARK 的个人仪表盘
python3 11_监控与优化_Monitor_and_Optimize/PTA-DASH_项目仪表盘.py --project "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动" --person "MARK"

# 生成项目整体仪表盘
python3 11_监控与优化_Monitor_and_Optimize/PTA-DASH_项目仪表盘.py --project "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动" --person "all"

这个仪表盘会显示：
1. 项目目标（一句话）
2. 当前阶段和进度
3. 个人任务（阻塞中/进行中/已完成）
4. 关键风险
5. 下一步行动

请展示结果。
```

---

## 指令 6：Rw 项目智能分析（高质量输出）

```
请帮我分析 Rw 权益项目的进度：

项目路径：/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动

执行：
cd /Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA

python3 11_监控与优化_Monitor_and_Optimize/PTA-INTEL-RW_智能项目分析器_v3.py \
    --project "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动" \
    --mode analyze

然后回答以下问题：
1. 项目总体进度如何？
2. 有哪些阻塞项？
3. Roy 的任务有哪些？
4. 下一步行动是什么？

注意：这个分析器专门解析 Rw 项目的 CSV 台账格式，产出质量更高。
```

---

## 指令 7：自然语言查询 Rw 项目

```
请帮我查询 Rw 权益项目：

项目路径：/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动

执行以下查询：
cd /Users/zhaoqitrenda.cn/Desktop/Jasper工作文档（不含EA项目）/Jasper AI协同经验引擎/AI工程能力整改项目/05_Agent库/草稿/PTA

# 查询 1：项目进度
python3 11_监控与优化_Monitor_and_Optimize/PTA-INTEL-RW_智能项目分析器_v3.py --project "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动" --mode query --query "项目进度如何"

# 查询 2：阻塞项
python3 11_监控与优化_Monitor_and_Optimize/PTA-INTEL-RW_智能项目分析器_v3.py --project "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动" --mode query --query "有哪些阻塞需要 MARK 介入"

# 查询 3：Roy 的任务
python3 11_监控与优化_Monitor_and_Optimize/PTA-INTEL-RW_智能项目分析器_v3.py --project "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动" --mode query --query "Roy 的任务有哪些"

# 查询 4：TOB 工作流
python3 11_监控与优化_Monitor_and_Optimize/PTA-INTEL-RW_智能项目分析器_v3.py --project "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动" --mode query --query "TOB 工作流状态"

# 查询 5：下一步行动
python3 11_监控与优化_Monitor_and_Optimize/PTA-INTEL-RW_智能项目分析器_v3.py --project "/Users/zhaoqitrenda.cn/Desktop/Rw权益项目/07_项目立项启动" --mode query --query "下一步行动"

请展示每个查询的结果。
```
