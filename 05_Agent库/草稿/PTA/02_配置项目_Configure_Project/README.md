# 02 · 配置项目 Configure Project

> 对应方法论：`.env.example` / `settings.json` / `.gitignore` / `README.md` —— 配置模型、API Key、项目元数据，设定全局参数与开发规范。

## 本文件夹内容

- `settings.json` —— 运行期配置（agent_id、entrypoint、skills/tools/memory 清单、安全约束摘要）
- `.env.example` —— 环境变量模板（复制为 `.env` 后按需修改，`.env` 本身不入库）
- `.gitignore` —— 忽略规则（`__pycache__/`、`.env` 等）

项目顶层的 `README.md`（项目说明）按惯例仍放在 PTA 根目录，方便 GitHub 自动渲染，
这里不重复存放。
