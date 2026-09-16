# WPS云文档接入（企业自建应用 · 只读）

目标：让WPS里持续更新的内容，既能定时落成本地快照（带变更历史），也能随时现拉最新值。

代码已就绪并验证到"只差凭证"这一步：HTTPS链路、token端点、请求格式、错误解析都实测通过
（用假凭证打 `https://openapi.wps.cn/oauth2/token`，平台正确返回 `40100008 invalid_client`）。

---

## 一、你需要在开发者后台做的四件事

代码这边不需要你再改，但下面四步只能由你在后台操作。

### 1. 创建应用
类型选 **企业自建应用**（企业内部开发、仅企业内可用）。
创建后记下 **APPID（AK）** 与 **APPKEY（SK）**。

### 2. 申请API权限（scope）
按你实际要读的表型勾选，建议一次全申请，省得以后补：

| scope | 用途 | 缺了会怎样 |
|---|---|---|
| `kso.dbsheet.read` | 读多维表格结构与记录 | 多维表格全部读不了 |
| `kso.sheets.read` | 读传统表格工作表与单元格 | 传统表格读不了 |
| `kso.airsheet.read` + `kso.airsheet.readwrite` | 读智能表格 | 智能表格读不了（文档标注canonical是readwrite，只读接口建议两个都申请）|
| `kso.file.read` | 文件信息、盘内文件列表 | 无法核对file_id、无法列目录 |
| `kso.file_link.readwrite` | 用分享链接解析出file_id | `resolve` 命令不可用，只能手工找file_id |
| `kso.doclib.read` | 团队文档库列表（取drive_id） | `ls` 不带参数时列不出团队盘 |

> `kso.file_link.readwrite` 名字里是readwrite，但这是平台对"获取分享链接信息"标注的scope，本工具只做GET。

### 3. 配置数据权限并提交审核
光有API权限还不够。应用还必须对**目标盘/目标文件**有访问权限，否则调用会返回权限错误。
审核通过后权限才生效。

### 4. 接口签名保持关闭
「开发者后台 - 安全设置 - 接口签名」**不要开启**。
本工具按未开启签名实现（不携带 `X-Kso-Date` / `X-Kso-Authorization`）。若你确实要开，告诉我，我再补签名算法。

IP白名单是可选项；若你的同步机器IP固定，开白名单更安全，但记得把本机出口IP加进去。

---

## 二、配置

```bash
cp wps_config.example.json wps_config.json     # 填 app_id / app_key
cp wps_sources.example.json wps_sources.json   # 填要同步的文档
```

`wps_config.json` 与 `.token_cache.json` 已加入 `.gitignore`，不会入库。
也可以不落文件，改用环境变量 `WPS_APP_ID` / `WPS_APP_KEY`（优先级高于配置文件）。

---

## 三、用法

```bash
python3 wps_sync.py doctor                    # 验凭证，换一次token
python3 wps_sync.py resolve <分享链接>         # 链接 → file_id，并产出可粘贴的源条目
python3 wps_sync.py ls                        # 列团队盘，拿 drive_id
python3 wps_sync.py ls <drive_id>             # 列盘内文件，拿 file_id
python3 wps_sync.py sync                      # 全量同步落快照（定时任务跑这个）
python3 wps_sync.py sync 某个别名              # 只同步指定源
python3 wps_sync.py pull 某个别名              # 现拉最新内容到stdout，不落地
python3 wps_sync.py status                    # 各源上次检查/上次变更时间与内容指纹
```

**分享链接里 `/l/` 后面的是 `link_id`，不是 `file_id`**，必须先 `resolve` 一次。

### 快照布局
```
snapshots/<别名>/latest.json          最新完整内容
snapshots/<别名>/_meta.json           指纹、上次检查时间、上次变更时间
snapshots/<别名>/history/<时间戳>.json 每次内容变化留一版
```
内容指纹（sha256前16位）没变就不写新版本，所以 `history/` 里每一版都是一次真实变更。
快照默认入git，配合仓库里已有的每小时auto-sync，等于自动获得变更diff。
若某份表的数据不适合入库，在 `.gitignore` 里加 `05_集成工具_Integrate_Tools/wps/snapshots/<别名>/`。

---

## 四、定时同步

装成每15分钟一次（先确认 `doctor` 通过再装）：

```bash
crontab -l 2>/dev/null | { cat; echo "*/15 * * * * '$PWD/run_sync.sh'"; } | crontab -
```

日志在 `logs/sync_YYYYMM.log`，按月切。
取消：`crontab -e` 删掉那一行。

---

## 五、已知限制（重要，别踩）

1. **文字文档读不到正文。** 开放平台的「文字文档」分组只有规范排版任务，「通用文档处理」只有文档附件，
   都没有读正文的接口。所以 `kind: "file"` 的源只跟踪元信息（名称、修改时间），
   能告诉你"它被改过了"，但拿不到改了什么。要正文得走文件下载再本地解析docx——需要时告诉我，我来补。

2. **传统表格/智能表格按选区读。** 这两类是单元格模型，必须给定行列范围，默认1000行×50列。
   表更大就在源条目里调大 `range.row_to` / `range.col_to`，否则会**静默少读**。首次接通后建议核对行数。

3. **两处待实跑校准。** 多维表格的翻页游标字段名、传统表格worksheets响应的字段名，文档未完全给全，
   代码里做了多字段名容错（游标按 `next_cursor`/`cursor`/`page_token` 等顺序探测，并对重复游标做防死循环）。
   真凭证到位后第一次 `sync`，我会核对返回结构、把容错收敛成确定实现。

4. **只读。** 客户端刻意不提供任何写接口，不会改动WPS里的任何内容。
