# 02 配置项目

本层保存 VNW 的运行配置，不保存业务事实。

## 配置文件

- `settings.json`：本地运行和工作区配置；
- `deepseek_config.example.json`：模型配置示例；
- `deepseek_config.json`：本机模型配置，不应提交密钥；
- 数据库连接参数位于
  `06_开发技能_Develop_Skills/skills/db_config_local.py`，仅供本机只读连接。

## 安全边界

- PostgreSQL 连接仅允许 `SELECT`；
- 密钥、口令和本地路径不得进入分析包或前端 JSON；
- 模型只能读取准备好的单 L3 运行包；
- 更换模型名称不能绕过证据、快照和输出契约校验；
- V1 不配置知识库或数据库写回权限。

实际命令和发布步骤见 `10_部署与运行_Deploy_and_Run/README.md`。
