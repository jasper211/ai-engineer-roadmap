# WPS 云文档 MCP 一键安装（Windows / PowerShell）
#
# 管理员：把下面两行填成企业自建应用的凭证，连同 wps_sheets_mcp.py、wps_ocr_mcp.py
#         一起发给使用者（三个文件放同一目录）。
# 使用者：右键「使用 PowerShell 运行」，或在 PowerShell 里执行：
#           powershell -ExecutionPolicy Bypass -File .\install_wps_mcp.ps1
#
# ⚠️ 填好凭证后本脚本等同密钥文件：不要提交仓库、不要放共享盘、不要在群里转发。

$APP_ID  = if ($env:WPS_APP_ID)  { $env:WPS_APP_ID }  else { "__在此填入APPID__" }
$APP_KEY = if ($env:WPS_APP_KEY) { $env:WPS_APP_KEY } else { "__在此填入APPKEY__" }

$SCOPES = "kso.user_base.read,kso.file.read,kso.file.search,kso.doclib.readwrite,kso.drive.readwrite,kso.file_link.readwrite,kso.dbsheet.read,kso.sheets.read,kso.airsheet.read,kso.airsheet.readwrite"

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8   # 不设中文会乱码

function Step($m) { Write-Host ""; Write-Host "▶ $m" -ForegroundColor Cyan }
function OK($m)   { Write-Host "  ✓ $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host ""; Write-Host "✗ $m" -ForegroundColor Red; exit 1 }

Write-Host "=========================================="
Write-Host " WPS 云文档 MCP 安装 (Windows)"
Write-Host "=========================================="

# ---------- 0. 前置检查 ----------
Step "检查配置"
if ($APP_ID -like "*在此填入*")  { Die "APP_ID 还没填。请管理员编辑本脚本顶部，或设环境变量 WPS_APP_ID / WPS_APP_KEY" }
if ($APP_KEY -like "*在此填入*") { Die "APP_KEY 还没填。同上" }
OK "APPID $($APP_ID.Substring(0,[Math]::Min(10,$APP_ID.Length)))…"

$PY = $null
foreach ($c in @("python", "python3", "py")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) { $PY = $c; break }
}
if ($PY) { OK "python 已就绪（$PY，用于表格与OCR工具）" }
else { Warn "没有 python：将跳过表格/OCR 补充工具，MCP 配置需手动加" }

# ---------- 1. 安装 CLI ----------
Step "安装 wps365-cli"
$CLI = Get-Command wps365-cli -ErrorAction SilentlyContinue
if (-not $CLI) {
    foreach ($p in @("$env:USERPROFILE\.local\bin\wps365-cli.exe",
                     "$env:LOCALAPPDATA\Programs\wps365-cli\wps365-cli.exe")) {
        if (Test-Path $p) { $CLI = $p; break }
    }
}
if ($CLI) {
    $CLI = if ($CLI -is [string]) { $CLI } else { $CLI.Source }
    OK "已安装：$(& $CLI --version)"
} else {
    Invoke-RestMethod https://open-docs.wpscdn.cn/cli/install.ps1 | Invoke-Expression
    $env:Path = [Environment]::GetEnvironmentVariable("Path","User") + ";" + $env:Path
    $found = Get-Command wps365-cli -ErrorAction SilentlyContinue
    if (-not $found) { Die "CLI 安装完成但找不到可执行文件，请关闭并重开 PowerShell 后再跑一次" }
    $CLI = $found.Source
    OK "已安装：$(& $CLI --version)"
}

# ---------- 2. 应用凭证 ----------
# 先验证再写入：auth setup 会覆盖已有凭证且自身不校验，填错会把能用的环境弄坏
Step "校验应用凭证"
$already = $false
try {
    $st = & $CLI --timeout 25s auth status 2>$null | ConvertFrom-Json
    if ($st.client_id -eq $APP_ID) { & $CLI --timeout 25s user me *>$null; $already = ($LASTEXITCODE -eq 0) }
} catch {}
if ($already) {
    OK "已有可用凭证，保持不动"
} else {
    try {
        $resp = Invoke-RestMethod -Method Post -Uri "https://openapi.wps.cn/oauth2/token" `
            -Body @{ grant_type="client_credentials"; client_id=$APP_ID; client_secret=$APP_KEY } `
            -TimeoutSec 20
    } catch {
        $detail = $_.ErrorDetails.Message
        if ($detail -like "*invalid_client*") { Die "APPID 或 APPKEY 不正确（平台返回 invalid_client）。请向管理员核对。你现有的配置未被改动。" }
        Die "凭证校验失败：$detail`n你现有的配置未被改动。"
    }
    if (-not $resp.access_token) { Die "凭证校验未通过，现有配置未被改动" }
    OK "凭证校验通过"
    & $CLI auth setup --client-id $APP_ID --client-secret $APP_KEY *>$null
    if ($LASTEXITCODE -ne 0) { Die "凭证写入失败" }
    OK "凭证已保存"
}

# ---------- 3. 授权 ----------
Step "用户授权"
$valid = $false
try { $valid = ((& $CLI --timeout 25s auth status 2>$null | ConvertFrom-Json).delegated.status -eq "valid") } catch {}
if ($valid) {
    OK "已授权，跳过"
} else {
    Write-Host "  接下来会显示一个链接和验证码，请在浏览器中完成授权。"
    Write-Host "  ⚠ 若链接是 http:// 开头，请手动改成 https:// 再打开——" -ForegroundColor Yellow
    Write-Host "    http 下浏览器不发送登录 cookie，页面会不停刷新且永远登不进去。" -ForegroundColor Yellow
    Write-Host "  ⚠ 浏览器里必须登录有权限的企业账号，否则授权后读不到任何文件。" -ForegroundColor Yellow
    Write-Host ""
    & $CLI auth login --device --scopes $SCOPES
    if ($LASTEXITCODE -ne 0) { Die "授权未完成" }
    OK "授权成功（有效期 365 天）"
}

# ---------- 4. 验证 ----------
Step "验证连通性"
& $CLI --timeout 25s user me *>$null
if ($LASTEXITCODE -eq 0) { OK "身份验证通过" } else { Warn "user me 失败，可用 wps365-cli mcp doctor 排查" }
$doclib = (& $CLI --timeout 25s drive doclib list --page-size 1 2>&1 | Out-String)
if ($doclib -match "400002059|用户不在企业内") {
    Warn "读不到团队文档库：授权时登录的账号不在企业内，或未被授予团队文档权限。"
    Warn "在此之前 Agent 读不到任何企业文件，请联系管理员。"
} elseif ($doclib -match '"code":\s*0') {
    OK "团队文档库可访问"
    & $CLI --timeout 25s drive file search --keyword "a" --page-size 1 *>$null
    if ($LASTEXITCODE -eq 0) { OK "全库搜索可用" } else { Warn "全库搜索不可用——多半缺 kso.file.search，请管理员申请后重跑本脚本" }
} else {
    Warn "团队库检查异常：$($doclib.Substring(0,[Math]::Min(150,$doclib.Length)))"
}

# ---------- 5. 补充工具 ----------
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
$TOOLDIR = "$env:LOCALAPPDATA\wps365-tools"
$SheetsPath = ""; $OcrPath = ""
if ($PY) {
    Step "安装补充工具"
    New-Item -ItemType Directory -Force -Path $TOOLDIR | Out-Null
    if (Test-Path "$HERE\wps_sheets_mcp.py") {
        Copy-Item "$HERE\wps_sheets_mcp.py" $TOOLDIR -Force
        $SheetsPath = "$TOOLDIR\wps_sheets_mcp.py"
        OK "传统表格工具已安装（官方MCP不支持 .xls/.xlsx）"
    } else { Warn "同目录没找到 wps_sheets_mcp.py，传统表格将无法读取" }

    if (Test-Path "$HERE\wps_ocr_mcp.py") {
        Copy-Item "$HERE\wps_ocr_mcp.py" $TOOLDIR -Force
        $OcrPath = "$TOOLDIR\wps_ocr_mcp.py"
        & $PY -c "import pypdfium2" *>$null
        if ($LASTEXITCODE -eq 0) {
            OK "扫描件OCR工具已安装"
        } else {
            Warn "扫描件OCR还缺依赖，请执行：$PY -m pip install pypdfium2"
            Warn "并在「设置 > 时间和语言 > 语言」中为中文添加「光学字符识别」可选功能"
        }
        Warn "装完可让 Agent 调用 ocr_status 确认 OCR 是否就绪"
    }
}

# ---------- 6. 写入 MCP 配置 ----------
Step "写入 Claude Code 配置"
$cfgPath = "$env:USERPROFILE\.claude.json"
if ($PY) {
    if (Test-Path $cfgPath) { Copy-Item $cfgPath "$cfgPath.bak-$(Get-Date -Format yyyyMMdd-HHmmss)" }
    $cfg = if (Test-Path $cfgPath) { Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { [PSCustomObject]@{} }
    if (-not $cfg.PSObject.Properties.Name.Contains("mcpServers")) {
        $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([PSCustomObject]@{})
    }
    $servers = $cfg.mcpServers
    function SetServer($name, $value) {
        if ($servers.PSObject.Properties.Name -contains $name) { $servers.$name = $value }
        else { $servers | Add-Member -NotePropertyName $name -NotePropertyValue $value }
    }
    SetServer "wps365" ([PSCustomObject]@{ type="stdio"; command=$CLI; args=@("mcp","serve"); env=@{}; timeout=600 })
    if ($SheetsPath) { SetServer "wps-sheets" ([PSCustomObject]@{ type="stdio"; command=$PY; args=@($SheetsPath); env=@{ WPS365_CLI=$CLI } }) }
    if ($OcrPath)    { SetServer "wps-ocr"    ([PSCustomObject]@{ type="stdio"; command=$PY; args=@($OcrPath);    env=@{ WPS365_CLI=$CLI } }) }
    $cfg | ConvertTo-Json -Depth 12 | Set-Content $cfgPath -Encoding UTF8
    OK "已写入（原配置已备份）：$($servers.PSObject.Properties.Name -join ', ')"
} else {
    Warn "缺 python，请手动把下面内容加进 $cfgPath 的 mcpServers："
    Write-Host "      `"wps365`": { `"command`": `"$CLI`", `"args`": [`"mcp`",`"serve`"], `"env`": {}, `"timeout`": 600 }"
}

Write-Host ""
Write-Host "=========================================="
Write-Host " 安装完成"
Write-Host "=========================================="
Write-Host ""
Write-Host "  ▸ 重启 Claude Code 后即可使用"
Write-Host "  ▸ 排查：wps365-cli mcp doctor"
Write-Host "  ▸ OCR自查：让 Agent 调用 ocr_status"
Write-Host ""
Write-Host "  ▸ 用 Cursor / Claude Desktop 等其他客户端？把下面这段贴进它的 MCP 配置："
Write-Host ""
Write-Host "      `"wps365`":     { `"command`": `"$CLI`", `"args`": [`"mcp`",`"serve`"], `"env`": {}, `"timeout`": 600 }"
if ($SheetsPath) { Write-Host "      `"wps-sheets`": { `"command`": `"$PY`", `"args`": [`"$SheetsPath`"], `"env`": {`"WPS365_CLI`": `"$CLI`"} }" }
if ($OcrPath)    { Write-Host "      `"wps-ocr`":    { `"command`": `"$PY`", `"args`": [`"$OcrPath`"], `"env`": {`"WPS365_CLI`": `"$CLI`"} }" }
Write-Host "    配置文件位置见交付说明第七节。凭证共用，无需重新授权。"
Write-Host ""
