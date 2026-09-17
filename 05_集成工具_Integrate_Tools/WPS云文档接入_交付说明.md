# WPS 云文档接入 · 交付说明

让 AI Agent（Claude Code / Cursor 等）直接读取企业 WPS 团队云文档。

**采用金山官方 `wps365-cli` 内置的 MCP Server**，不需要我方任何自研代码。
全部步骤 2026-09-16 在真实企业租户上实测通过。

---

## 零、先确定用哪种部署模式

Agent 能读到什么，**完全由「授权那一步用哪个账号登录浏览器」决定**，与使用者本人是谁无关。
据此有两种模式，装之前先定好用哪种。

### 模式 A：使用者本人授权（企业内同事）

授权时用**使用者自己的企业账号**登录。他能读到的 = 他在 WPS 里能看到的。

**前置条件**：使用者必须已是企业成员且对目标库有权限。一分钟自检——
让他在浏览器打开 https://www.kdocs.cn 用平时的账号登录：

| 看到什么 | 能不能装 |
|---|---|
| 有「团队文档」，且能看到需要读的库 | ✅ 可以装 |
| 只有「我的云文档」 | ❌ 先联系管理员加入企业并授予权限 |
| 有团队文档但缺某些库 | ⚠️ 装完也读不到那几个，先补权限 |

> 账号可能同时有个人与企业身份。若登录后只见个人空间，找界面上的
> 「切换企业/切换身份」切到公司组织。**授权时登录的必须是能看到团队文档的那个身份。**

### 模式 B：借用已授权账号（管理层等不便开企业账号的人）

授权时用**一个已有企业权限的账号**（如管理员账号）登录浏览器完成授权。
token 随后保存在这台机器上，**使用者本人完全不需要 WPS 账号，也不用加入企业**。

适用：偶尔查数、不日常使用 WPS 的人，为此开企业账号不划算。

操作上与模式 A 完全一样，**唯一区别在第 3 步授权时，浏览器里登录的是那个被借用的账号**。
授权完成后该账号可以退出浏览器登录，不影响这台机器继续使用
（token 一旦发出即独立于浏览器登录态，实测有效）。

**采用模式 B 必须记住三件事：**

1. **审计归属在被借用的账号名下** —— 平台日志记录的是该账号读取了数据，不是实际使用者
2. **权限等同该账号的全部权限** —— 不是按使用者应有的范围限定
3. **到期与撤销是全局的** —— refresh_token 有效期 365 天，到期所有用此账号授权的机器同时失效，
   需要该账号持有人在每台机器上重新授权一次；无法单独停用某一台

> 部署时把授权日期记下来，到期前一个月安排重新授权。

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

### 凭证怎么给使用者

**实测结论：APPKEY 必须提供，绕不开。**

原本设想让使用者用 `wps365-cli config init --app-id <APPID>` 自助绑定，管理员只发 APPID。
**实测在普通成员账号上不可行**——开发者后台只允许他创建新应用，看不到、也绑不了企业已有的应用；
而新建的应用没有上面这些 scope，装完也用不了。

所以交付方式是：**管理员把 APPID 与 APPKEY 填进 `install_wps_mcp.sh`，连同
`wps_sheets_mcp.py` 一起发给使用者**，使用者跑脚本即可。

> ⚠️ **这意味着 APPKEY 会进到每一台使用者的机器。** 企业内部应用通常可接受，但请知悉：
> 填好凭证的脚本等同密钥文件，不要提交代码仓库、不要放共享盘、不要在群里转发；
> 人员变动或疑似外泄时，在后台重置 APPKEY 并重新分发脚本。

---

## 二、使用者装（约 5 分钟）

管理员会给你**一个安装脚本**加两个工具文件（`wps_sheets_mcp.py`、`wps_ocr_mcp.py`），
**三个放在同一个目录**，然后按你的系统选一条：

**macOS / Linux**

```bash
bash install_wps_mcp.sh
```

**Windows**（在 PowerShell 里）

```powershell
powershell -ExecutionPolicy Bypass -File .\install_wps_mcp.ps1
```

> 两个脚本做的事完全一样。Windows 版若提示找不到 `wps365-cli`，**关掉 PowerShell 重开**再跑一次
> （安装程序改了 PATH，当前窗口读不到）。

脚本会依次完成：装 wps365-cli → 校验并写入凭证 → 引导你授权 → 验证 → 装传统表格工具 →
写入 Claude Code 配置（自动备份原配置）。**最后重启 Claude Code 即可使用。**

中途需要你做的只有一件事：**设备码授权**。脚本会显示一个链接和验证码，
在浏览器打开、确认授权即可。授权范围仅限你本人有权限的内容。

### 三个会卡住人的点

**1. 授权链接若是 `http://` 开头，手动改成 `https://`**

浏览器在 http 下不发送登录 cookie，页面会**不停刷新且永远登不进去**，
看起来像网站坏了。实测就是这个原因，改成 https 立刻正常。

现在的浏览器默认隐藏地址栏里的 `http://`/`https://` 前缀，两者**看上去完全一样**，
所以别去地址栏改——直接把验证码填进这个模板打开：

```
https://openapi.wps.cn/view/oauth/device/verify?user_code=终端给你的码
```

**2. 打开授权链接前，先在同一浏览器登录企业账号**

没有登录态同样会 401 循环。

**3. macOS 可能弹出钥匙串授权框**

写入凭证时系统会问「wps365-cli 想要访问钥匙串」，**点【允许】或【始终允许】**。
不点的话脚本会一直挂在那里，没有任何提示，看着像死机。

### Windows 补充说明

- 安装脚本用 `install_wps_mcp.ps1`（PowerShell 版），行为与 bash 版一致
- 若 PowerShell 拦截脚本执行，用上面带 `-ExecutionPolicy Bypass` 的命令
- 装完让 Agent 调用 `ocr_status`，它会告诉你扫描件 OCR 还缺什么、具体怎么装

> ⚠️ **PowerShell 版未在 Windows 机器上实测**（我们没有测试环境）。
> 若它在某一步失败，改用手动方式——交付说明第二节里的每条命令都是逐条验证过的，
> 按 `auth setup` → `auth login --device` → `mcp config` 的顺序手动执行即可，
> 把失败信息反馈回来我们再修脚本。

## 三、权限边界

**数据范围完全跟随「授权时登录的那个账号」**，与使用者本人是谁无关——
那个账号在 WPS 里能看到哪些库，Agent 就能读哪些，一分不多一分不少。

- **模式 A**（使用者本人授权）：边界即他本人的权限，各自独立、互不影响
- **模式 B**（借用账号授权）：边界即被借用账号的权限，该机器上的任何人都拥有这个范围

凭证不共用：token 存在各自机器的系统钥匙串里，不随文件分发。
但模式 B 下**同一账号授权的多台机器共享同一份权限与有效期**。

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
| `ocr_scanned_pdf` / `ocr_status` | **扫描件PDF本地OCR**（补充工具，多平台自适应） |
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

### 2. 扫描件 PDF：平台不给正文，需用附带的本地 OCR

WPS 平台**不提供 OCR**。`drive_file_content_get` 对扫描件返回
`src_format_detail: "PDF-scan"` 但没有正文内容，`--format ocr` 也不支持。

合同、尽调这类归档件大多是扫描件——实测「合约管理」库 2624 份 PDF 里相当比例是整页图像
（一份 2.2MB 的合同：0 个字体、21 处图像）。

**解决**：交付包里的 `wps_ocr_mcp.py`，**按操作系统自动选用本地 OCR 引擎**，
一律本地识别，**内容不发送给任何第三方**。

| 系统 | 引擎 | 需要装什么 | 验证情况 |
|---|---|---|---|
| **macOS** | 系统自带 PDFKit + Vision | **零依赖**（缺 swift 时执行 `xcode-select --install`） | ✅ 真实扫描合同实测通过 |
| **Windows** | pypdfium2 + 系统自带 Windows.Media.Ocr | `pip install pypdfium2`；再到「设置 > 时间和语言 > 语言」为中文添加「光学字符识别」可选功能 | ⚠️ 代码未在 Windows 实测 |
| **Linux / 通用** | pypdfium2 + tesseract | `pip install pypdfium2` + `sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra` | ⚠️ 代码未实测 |

> **诚实说明**：macOS 路径用真实扫描合同端到端验证过；Windows/Linux 路径的
> **PDF 渲染环节（pypdfium2）已在本机验证可用**，但 OCR 识别环节（Windows.Media.Ocr / tesseract）
> 没有对应机器实测。首次在这两种系统上使用时请留意，有问题反馈回来修。

### 装完先让 Agent 自查

工具 `ocr_status` 会报告：当前系统、用哪个引擎、是否可用、**不可用时按本机系统给出具体安装命令**。
安装脚本在 macOS/Linux 上会自动检查；Windows 上装完直接让 Agent 调用 `ocr_status` 即可。

工具 `ocr_scanned_pdf`：约 2-3 秒/页，默认前 10 页，长文档用 `from_page` 分批。
对**有文本层**的 PDF 会主动劝退、提示改用官方工具，不做无谓的 OCR。

> ⚠️ OCR 会有错字。金额、证件号、账号这类关键数字**务必回原件核对**，别直接拿去做账。

## 六、传统表格（.xls/.xlsx）需加装一个补充工具

**官方 MCP 有一个缺口**：120 个工具里只有 `airsheet`（智能表格 .ksheet）和
`dbsheet`（多维表格 .dbt），**没有传统表格的读取工具**；`drive_file_content_get`
对 `.xls` 和 `.xlsx` 都返回 `400008018 文档内容抽取失败`（两种格式实测均失败）。

而企业日常数据大多是传统表格——结算、佣金、实收、费用这些库翻下来几乎全是 `.xlsx`。

### 解决：`wps_sheets_mcp.py`

**安装脚本已经自动装好它了**，前提是它和 `install_wps_mcp.sh` 放在同一目录——
这就是管理员要发两个文件的原因。本节说明它是什么、以及需要手动处理时怎么办。

它是单文件补充服务，**零第三方依赖**，有 python3 即可。
**不碰凭证、不发 HTTP**，全部转调 `wps365-cli api`——认证、刷新全由官方 CLI 负责，
所以不需要额外授权，也不会因为 token 过期而失效。

手动安装（脚本跳过时，比如机器上没有 python3、或两个文件没放一起）：
把文件放到任意位置，加进 `~/.claude.json` 的 `mcpServers`：

```json
{
  "wps-sheets": {
    "type": "stdio",
    "command": "python3",
    "args": ["<绝对路径>/wps_sheets_mcp.py"],
    "env": {"WPS365_CLI": "/Users/<你>/.local/bin/wps365-cli"}
  }
}
```

装好后多出两个工具（重启客户端生效）：

| 工具 | 用途 |
|---|---|
| `sheet_worksheets` | 列出工作表及**实际数据范围**，并标出空表 |
| `sheet_read` | 读单元格，输出 TSV 网格；不传范围时自动按数据范围读整张表 |

输出已拍成网格（原始接口返回的是扁平单元格列表，每格带 `pic_data`/`sha1` 等字段约 300 字节，
一张百行表的原始 JSON 能到 MB 级，直接给 AI 会撑爆上下文）。

> 这是**自描述**的 MCP 工具，AI 连上就知道有它、会自己调用，
> 不需要在 `CLAUDE.md` 里额外教它怎么拼接口。

---

## 七、接入不同的 Agent 客户端

这套东西是标准 **MCP（Model Context Protocol）stdio 服务**，
**任何支持 MCP 的客户端都能接**，不限于 Claude Code。

装好后一共三个 server：

| server | 作用 | 来源 |
|---|---|---|
| `wps365` | 官方 120 个工具（搜索、目录、文档正文、多维表格…） | 官方 CLI 自带 |
| `wps-sheets` | 传统表格 `.xls/.xlsx` 读取 | 本交付包补充 |
| `wps-ocr` | 扫描件 PDF 本地 OCR | 本交付包补充 |

### 配置文件位置

**安装脚本只会自动写 Claude Code 的配置**，用其他客户端请手动把下面的片段贴进对应文件：

| 客户端 | 配置文件 |
|---|---|
| **Claude Code** | `~/.claude.json`（Windows：`%USERPROFILE%\.claude.json`），键名 `mcpServers` |
| **Claude Desktop** | macOS `~/Library/Application Support/Claude/claude_desktop_config.json`<br>Windows `%APPDATA%\Claude\claude_desktop_config.json` |
| **Cursor** | 全局 `~/.cursor/mcp.json`；或项目级 `<项目>/.cursor/mcp.json` |
| **其他 MCP 客户端** | 查该客户端文档中 "MCP server" 的配置位置，格式基本一致 |

> 客户端的配置路径可能随版本变化，**以各自官方文档为准**。

### 配置片段（三个 server）

把 `<CLI路径>`、`<python命令>`、`<工具目录>` 换成你机器上的实际值：

```json
{
  "mcpServers": {
    "wps365": {
      "command": "<CLI路径>",
      "args": ["mcp", "serve"],
      "env": {},
      "timeout": 600
    },
    "wps-sheets": {
      "command": "<python命令>",
      "args": ["<工具目录>/wps_sheets_mcp.py"],
      "env": { "WPS365_CLI": "<CLI路径>" }
    },
    "wps-ocr": {
      "command": "<python命令>",
      "args": ["<工具目录>/wps_ocr_mcp.py"],
      "env": { "WPS365_CLI": "<CLI路径>" }
    }
  }
}
```

**各值怎么取**：

| 占位符 | macOS / Linux | Windows |
|---|---|---|
| `<CLI路径>` | `~/.local/bin/wps365-cli`（写绝对路径） | `where wps365-cli` 的输出 |
| `<python命令>` | `python3` | 通常是 `python`，以 `where python` 为准 |
| `<工具目录>` | `~/.local/share/wps365-sheets` | `%LOCALAPPDATA%\wps365-tools` |

安装脚本跑完会**把实际路径直接打印出来**，照抄即可，不用自己拼。

官方那个 server 也可以用 `wps365-cli mcp config` 生成现成片段。

### 凭证是共用的

三个 server 都通过 `wps365-cli` 取凭证，**授权一次，所有客户端共用**。
在 Claude Code 里授权过，Cursor 那边直接配上就能用，不需要重新授权。

---

## 八、排查

```bash
wps365-cli mcp doctor        # 一次看清 spec/凭证/授权状态
wps365-cli auth status       # 当前登录身份
wps365-cli drive doclib list # 验证能不能列出团队库
wps365-cli api get "/v7/users/current"   # 未封装的接口用 api 命令直调
```

遇到 `PermissionDenied ... invalid_scope`，报错里会直接写明缺哪个 scope——
先确认后台申请了，再确认**授权后重新登录过**。
