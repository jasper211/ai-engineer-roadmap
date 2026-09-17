# WPS 云文档接入 · 交付说明

让 AI Agent（Claude Code / Cursor 等）直接读取企业 WPS 团队云文档。

**采用金山官方 `wps365-cli` 内置的 MCP Server**，不需要我方任何自研代码。
全部步骤 2026-09-16 在真实企业租户上实测通过。

---

## 一、管理员先做（一次性）

在 [WPS 开发者后台](https://open.wps.cn) 为企业自建应用申请以下权限：

```
kso.user_base.read          用户基本信息
kso.file.read               文件与目录读取
kso.file.search             全库文件搜索  ← 最关键，缺了只能逐层翻目录
kso.doclib.readwrite        团队文档库列表
kso.drive.readwrite         驱动盘
kso.file_link.readwrite     分享链接解析
kso.dbsheet.read            多维表格
kso.sheets.read             传统表格
kso.airsheet.read
kso.airsheet.readwrite      智能表格
```

> **注意名称与官方文档有出入**：文档里标 `read` 的，平台实际常要 `readwrite`。
> 以调用时的报错为准——报错会直接点名缺哪个 scope，把那句话给管理员即可。

申请完成后，把 **APPID**（形如 `AK2026xxxxxxxx`）发给使用者即可。
**APPKEY 原则上不需要外发**——使用者用 `config init --app-id` 走浏览器绑定。
（若个别使用者绑定后提示凭证缺失，再单独把 APPKEY 给他，见第二节的退路。）

---

## 二、使用者装（约 5 分钟）

### 1. 安装

```bash
curl -fsSL https://open-docs.wpscdn.cn/cli/install.sh | bash
```

装到 `~/.local/bin/wps365-cli`，**不需要 sudo**，无运行时依赖（不需要 Node/Python）。
脚本带 SHA256 校验，源为金山官方 CDN。Windows 用 PowerShell：
`irm https://open-docs.wpscdn.cn/cli/install.ps1 | iex`

### 2. 绑定应用

```bash
wps365-cli config init --app-id <管理员给的APPID>
```

会给一个链接和绑定码（或终端里的二维码），在浏览器确认即可。
`--app-id` 是**绑定企业已有应用**，不会创建新应用，所以不需要"创建应用"的权限。

> **退路**：如果绑定后 `wps365-cli auth status` 显示 `client_secret_configured: false`，
> 找管理员要 APPKEY，执行一次：
> ```bash
> wps365-cli auth setup --client-id <APPID> --client-secret <APPKEY>
> ```
> 注意别把 APPKEY 直接打在命令行里（会进 shell 历史），用交互提示或环境变量更稳妥。

凭证存放在系统钥匙串，**不落在配置文件里**——`config.json` 只有 client_id，没有密钥。

### 3. 授权

```bash
wps365-cli auth login --device --scopes "kso.user_base.read,kso.file.read,kso.file.search,kso.doclib.readwrite,kso.drive.readwrite,kso.file_link.readwrite,kso.dbsheet.read,kso.sheets.read,kso.airsheet.read,kso.airsheet.readwrite"
```

设备码流程：给一个 code 和链接，在浏览器确认即可。**不需要回调地址、不需要本地起服务。**

验证：

```bash
wps365-cli user me
wps365-cli mcp doctor     # 应显示 ok:true、catalog_commands:120
```

### 4. 接入 Claude Code

```bash
wps365-cli mcp config
```

把它打印的片段贴进 `~/.claude.json` 的 `mcpServers`，**重启客户端**后生效：

```json
{
  "wps365": {
    "command": "/Users/<你>/.local/bin/wps365-cli",
    "args": ["mcp", "serve"],
    "env": {},
    "timeout": 600
  }
}
```

`env` 是空的——凭证由 CLI 自己管（存在 `~/Library/Application Support/wps365-cli`）。

---

## 三、权限边界

**数据范围完全跟随授权者本人**：你在 WPS 里能看到哪些库，Agent 就能读哪些，读不到别人的。
每个使用者各自授权，互不影响，也不共用凭证。

---

## 四、能力（120 个工具）

常用的几个：

| 工具 | 用途 |
|---|---|
| `drive_doclib_list` | 列出能访问的团队文档库 |
| `drive_file_search` | **全库搜索**，跨库、任意深度，实测 2.2 秒 |
| `drive_file_list` | 列目录 |
| `drive_file_content_get` | 读正文（docx / 文本型PDF / pptx），支持 `--format markdown` |
| `dbsheet_record_list` | 多维表格记录 |
| `airsheet_data_get` | 智能表格数据 |

还覆盖日历、IM、邮件、会议等业务域，完整列表：`wps365-cli mcp tools`

**搜索自动处理简繁**——实测用简体「顾问服务协议」能搜到繁体「顧問服務協議（TL）.pdf」，
不用两种写法各搜一次。

---

## 五、两个坑，交付时务必说明

### 1. 后台补申请 scope 后，必须重新授权

token 里的 scope 在**授权那一刻就固化了**。后台新申请的权限不会自动进入已有 token，
必须重跑一次 `auth login --device --scopes "..."`，否则一直报缺 scope，
容易误判成"申请没生效"。

### 2. 扫描件 PDF 读不到正文，这是平台级限制

`drive_file_content_get` 对扫描件返回 `src_format_detail: "PDF-scan"` 但没有正文，
`--format ocr` 报"请求参数不支持"。**WPS 开放平台不提供 OCR。**

实测样本：一份 2.2MB 的合同 PDF，0 个字体、14 张 JPEG 图像——整页都是图片。
而同目录下 149KB 的那份有 16 处字体，是 Word 导出的文本型 PDF，可以正常读。

**两类 PDF 处理方式完全不同**：

- **文本型 PDF** → 直接可读
- **扫描件 PDF** → 必须自接 OCR（本地 tesseract 或云 OCR），**换任何工具都一样**

合同类文件常有 `.docx` 和 `.pdf` 两个版本，**优先读 `.docx`**。
旧版 `.doc`（二进制格式）不支持，需另存为 `.docx`。

---

## 六、传统表格（.xls/.xlsx）要额外处理

**这是官方 MCP 的一个缺口，务必告知使用者。**

官方 120 个工具里只有 `airsheet`（智能表格 .ksheet）和 `dbsheet`（多维表格 .dbt），
**没有传统表格的读取工具**；`drive_file_content_get` 对 `.xls` 和 `.xlsx` 都返回
`400008018 文档内容抽取失败`（两种格式实测均失败，不是旧格式的问题）。

而企业日常数据大多是传统表格——结算、佣金、实收、费用这些库翻下来几乎全是 `.xlsx`。

**底层接口是通的**（scope `kso.sheets.read` 即可），两步：

```bash
# 1. 拿工作表列表，注意取 sheets[].sheet_id，并看 active_area 确定实际数据范围
wps365-cli api get "/v7/sheets/<file_id>/worksheets"

# 2. 读选区。filter.condition 传空数组 = 不筛选、输出该选区全部单元格
wps365-cli api post "/v7/sheets/<file_id>/worksheets/<sheet_id>/range_data/find" \
  --data '{"range":{"row_from":0,"row_to":99,"col_from":0,"col_to":20},
           "filter":{"condition":[],"search":[],"duplicates":{"col":[]}}}'
```

> ⚠️ **AI 不会自己发现这条路。** MCP 工具是自描述的，Agent 连上就知道有什么、怎么调；
> 而上面这两条命令不在工具列表里。AI 看到没有表格工具，会去试 `drive_file_content_get`，
> 失败后就告诉你"读不了"。
> **必须把这一节内容放进使用者项目的 `CLAUDE.md`（或等价的 AI 指引文件）**，AI 才会用。

> ⚠️ 返回的是**扁平单元格列表**，每个单元格带 `pic_data`/`sha1`/`num_format` 等字段约 300 字节。
> 一张百行表的原始 JSON 能到 MB 级，直接喂给 AI 会撑爆上下文。
> 让 AI 先按 `row_from`/`col_from` 拍成网格再看，只取 `cell_text`。

> ⚠️ 这条路依赖 **Agent 能执行 shell**。Claude Code 可以；Cursor、Workbuddy 等
> 若没有终端能力，这条路不通，只能等官方补工具或自建一个薄封装。

---

## 七、排查

```bash
wps365-cli mcp doctor        # 一次看清 spec/凭证/授权状态
wps365-cli auth status       # 当前登录身份
wps365-cli drive doclib list # 验证能不能列出团队库
wps365-cli api get "/v7/users/current"   # 未封装的接口用 api 命令直调
```

遇到 `PermissionDenied ... invalid_scope`，报错里会直接写明缺哪个 scope——
先确认后台申请了，再确认**授权后重新登录过**。
