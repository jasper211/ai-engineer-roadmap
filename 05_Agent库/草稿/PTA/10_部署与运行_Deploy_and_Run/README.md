# 10 · 部署与运行 Deploy and Run

> 对应方法论：`codex build` / `codex start` —— 打包项目，部署运行，支持本地或云端环境。

## 本文件夹内容

- `quick_start.sh` —— 一键启动脚本：跑一次 `agent.py` 全链路（dry-run）+ 状态检查

```bash
bash 10_部署与运行_Deploy_and_Run/quick_start.sh "按顺序完成 P2-02, P2-03"
```

PTA 目前只在本地/单机运行，没有容器化打包或云端部署环节；如果以后需要，
新增的 Dockerfile / 部署脚本也放在这个文件夹里。
