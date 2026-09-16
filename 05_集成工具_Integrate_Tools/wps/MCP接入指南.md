# WPS云文档 MCP Server · 接入指南

让 AI Agent 随时读取企业 WPS 团队云文档：列库 → 浏览目录 → 读表格。

- **传输**：stdio，手写 JSON-RPC，**零第三方依赖**——有 python3 就能跑，不需要 pip install
- **凭证分两层**：应用凭证（APPID/APPKEY，全员相同）+ 用户 token（每人各自授权）
- **数据范围跟随授权者本人**——你在 WPS 里能看到什么，Agent 就能读什么，读不到别人的库

后台应用怎么建、scope 怎么申请，见同目录 [WPS接入说明.md](WPS接入说明.md)（含实测校准的权限清单与踩坑记录）。

---

## 一、使用者接入（三步）

### 1. 拿到应用凭证
向本应用的管理者索取 **APPID** 与 **APPKEY**。这是企业自建应用的凭证，不是你的个人密码。

### 2. 配置 MCP

加到 Claude Code 的 MCP 配置里（`~/.claude.json` 的 `mcpServers`）：

```json
{
  "wps-cloud-docs": {
    "type": "stdio",
    "command": "python3",
    "args": ["<这个目录的绝对路径>/wps_mcp_server.py"],
    "env": {
      "WPS_APP_ID": "填APPID",
      "WPS_APP_KEY": "填APPKEY"
    }
  }
}
```

可选环境变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `WPS_TOKEN_DIR` | `~/.wps_mcp` | 用户 token 存放目录，每人一份，权限 0600 |
| `WPS_REDIRECT_URI` | `http://localhost:9527/callback` | 必须与开发者后台「安全配置 > 用户授权回调配置」完全一致 |

### 3. 首次授权

团队文档库**必须**用用户身份访问（应用身份调用会返回 `400002059 用户不在企业内`）。

**方式一，让 Agent 带你走**：直接问它"我要读 WPS 云文档"，它会调 `wps_auth_status` 发现未授权，
再调 `wps_auth_start` 给你授权链接；你在浏览器完成授权后，把地址栏里 `code=` 后面的值给它，
它调 `wps_auth_complete` 完成。

**方式二，命令行一把梭**（本机更省事，会自动起本地服务接回调）：

```bash
python3 wps_sync.py auth
```

授权一次可用 **365 天**（refresh_token 有效期，每次刷新自动滚动续期），到期需重新授权。

---

## 二、可用工具

| 工具 | 用途 |
|---|---|
| `wps_auth_status` | 查看授权状态与 token 剩余有效期。**遇到权限错误先调这个** |
| `wps_auth_start` | 生成用户授权链接 |
| `wps_auth_complete` | 用 code 换取用户 token |
| `wps_list_libraries` | 列出可访问的全部团队文档库及 drive_id ——**浏览起点** |
| `wps_list_folder` | 列出某目录下一层的子文件夹与文件（含 file_id、mtime） |
| `wps_search_files` | 在一个库内按名称/类型**浅层**搜索（默认深度3、上限50条） |
| `wps_read_sheet` | 读传统表格(.xlsx/.et)或智能表格(.ksheet)，输出 TSV 网格 |
| `wps_read_dbsheet` | 读多维表格(.dbt)记录，自动翻页 |
| `wps_file_info` | 单个文件的元信息 |
| `wps_resolve_link` | 分享链接 `/l/xxxx` → file_id / drive_id |

典型路径：`wps_list_libraries` → `wps_list_folder` 逐层进 → 拿到 file_id → `wps_read_sheet`。

---

## 三、性能边界（重要）

实测数据（2026-09-16，某企业租户）：

| 操作 | 耗时 |
|---|---|
| 列全部团队库 | < 2 秒 |
| 列一层目录 | 约 1.6 秒 |
| 读一张表的一块选区 | 1～3 秒 |
| **递归遍历整个库** | **2～30 分钟** |

遍历成本在**目录数量**，不在文件数量——每个目录一次 HTTP 往返。实测「合约管理」库有
355 个目录、5782 个条目，并发 6 路仍需 157 秒；「商务结算」更大。

**所以 MCP 刻意不提供全库遍历工具**。`wps_search_files` 是受限广度搜索，结果不全时会明确提示，
不会静默给出残缺结果。需要全量盘点时用 `scan_all.py`（一次性脚本，结果缓存到 `.tree_cache.json`）。

---

## 四、已知限制

1. **文字文档读不到正文。** 开放平台「文字文档」分组只有规范排版任务，没有读正文的接口。
   `.docx/.pdf` 只能拿到元信息（改没改、什么时候改的）。要正文得下载后本地解析。

2. **表格按选区读。** `wps_read_sheet` 默认前 200 行 × 30 列，大表要分块读。
   超出范围的数据不会提示缺失，**心里要有数**。

3. **多维表格读取尚未用真实数据验证。** 目前接触到的库里没有 `.dbt` 文件，
   `wps_read_dbsheet` 的翻页游标字段名是按文档实现+多字段名容错，首次实跑可能需要微调。

4. **APPKEY 分发是个权衡。** 每个使用者的 MCP 配置里都要填 APPKEY，等于密钥在团队内扩散。
   企业内部应用通常可接受；若要收紧，需另搭一个中心服务代持密钥、只对外发用户 token，那是另一套架构。

---

## 五、附：本地 CLI（调试与运维用）

```bash
python3 wps_sync.py auth        # 走用户授权
python3 wps_sync.py doctor      # 验凭证，看当前用的是用户身份还是租户身份
python3 wps_sync.py ls          # 列团队库
python3 wps_sync.py tree <drive_id>   # 递归目录树（慢，注意规模）
python3 wps_sync.py sync        # 按 wps_sources.json 落本地快照（可选的定时同步能力）
```

`wps_sync.py` 那套快照同步是早期做的，与 MCP 并行可用：MCP 负责"随时读最新"，
快照负责"留变更历史"。不需要留档的话，只用 MCP 即可。
