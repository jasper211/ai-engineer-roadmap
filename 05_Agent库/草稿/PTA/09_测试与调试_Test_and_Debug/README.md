# 09 · 测试与调试 Test and Debug

> 对应方法论：`codex test` / `codex run --debug` —— 执行单元测试与集成测试，调试 Agent 行为与输出结果。

## 本文件夹内容（`tests/`）

- `test_integration.py` —— 集成测试，覆盖 9 项（原 `test_pta_integration.sh` 迁移）：
  5 个技能的白盒测试 + `agent.py` 全链路黑盒测试 + 跨项目任务知识库 +
  git 同步默认行为安全验证

```bash
python3 09_测试与调试_Test_and_Debug/tests/test_integration.py
```

全部通过（9/9）后再进入 `10_部署与运行_Deploy_and_Run/`。
