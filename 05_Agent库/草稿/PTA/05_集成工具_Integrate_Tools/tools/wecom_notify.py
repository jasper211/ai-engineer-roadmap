#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具：企业微信群机器人通知（每日巡检"四方通知"的落地渠道）

企业微信自定义群机器人 webhook，text 类型消息支持按手机号 @ 群成员——这是
唯一支持 @ 功能的消息类型（markdown 类型企业微信群机器人不支持 @），所以
这里固定用纯文本，不追求富文本排版。

⚠️ webhook URL 本身就是"谁拿到谁就能往群里发消息"的凭证，四人手机号是
个人信息——两者都只能放在 wecom_config.json 里，这份文件绝不能进 git、
也绝不能放在任何会被 --daily-scan 扫描的目标项目目录里（DEFAULT_SCAN_
EXTENSIONS 含 .json，放错地方会被当"变更文件"整份发给 DeepSeek，直接泄露）。
固定读 02_配置项目_Configure_Project/wecom_config.json（PTA 自己的配置目录，
永远不是任何 --daily-scan 的扫描目标，天然隔离）。
"""

import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools.llm_client import build_ssl_context

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = TOOLS_DIR.parent.parent / "02_配置项目_Configure_Project" / "wecom_config.json"

# 复用 llm_client.py 里已经解决过的同一个问题：部分 Python 安装（尤其 Homebrew 装的）
# 默认证书路径是坏的，urlopen 直接调会报 CERTIFICATE_VERIFY_FAILED——真实联调时
# 复现过这个报错。这里按同样的逻辑找一个真实存在的 CA 证书包，不是绕过证书校验。
_SSL_CONTEXT = build_ssl_context()

MAX_CONTENT_BYTES = 2048  # 企业微信 text 消息内容长度上限


def load_wecom_config(path: Optional[Path] = None) -> Optional[dict]:
    """读取企业微信配置。文件不存在时返回 None（不是抛异常）——调用方据此
    优雅跳过通知这一步，不能因为没配置就让整个 --daily-scan 崩掉。"""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return None
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[警告] wecom_config.json 解析失败，跳过通知: {e}")
        return None


def truncate_utf8_safe(content: str, max_bytes: int = MAX_CONTENT_BYTES,
                        suffix: str = "\n...(已截断，见完整简报)") -> str:
    """按字节数截断，从末尾开始一段段砍，避免截断点落在多字节字符中间产生乱码
    （简单粗暴地按字节数切片可能切断一个多字节 UTF-8 字符）。预留空间必须
    按后缀本身的实际字节数算，不能写死一个数字——之前写死"30"时漏算了
    后缀里中文字符每个占3字节，导致加上后缀后总长度反而超过了上限。"""
    content_bytes = content.encode("utf-8")
    if len(content_bytes) <= max_bytes:
        return content
    suffix_bytes = len(suffix.encode("utf-8"))
    truncated = content_bytes[:max_bytes - suffix_bytes]
    while truncated:
        try:
            text = truncated.decode("utf-8")
            break
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    else:
        text = ""
    return text + suffix


def build_notification_text_from_content(content: str, mobiles_map: Dict[str, str],
                                          report_path: Optional[str] = None) -> Tuple[str, List[str]]:
    """给一段调用方已经格式化好的正文（比如 skills.daily_sensing.format_text_plain
    的输出），只负责两件事：按企业微信 text 消息的字节上限截断、决定 @ 谁。
    不在这里重新拼正文内容——避免跟 daily_sensing 的格式化逻辑重复维护两份，
    每次改简报格式只用改一个地方。

    与组内成员沟通后确定：只 @ Jasper 本人，不 @ Terresa/HR/Carrie——正文里
    仍然会显示"通知: XX"这类信号判断，但机器人不会替 Jasper 越过他直接去 @
    到其他人；要不要转达、怎么转达，由 Jasper 自己看完消息后决定。

    Returns: (content, mentioned_mobiles)
    """
    if report_path:
        content = content + f"\n\n完整简报: {report_path}"
    mentioned_mobiles = [mobiles_map["Jasper"]] if "Jasper" in mobiles_map else []
    return truncate_utf8_safe(content), mentioned_mobiles


def build_notification_text(briefing, mobiles_map: Dict[str, str],
                             report_path: Optional[str] = None) -> Tuple[str, List[str]]:
    """（历史接口，测试套件仍在用）把简报浓缩成一条企业微信消息——不塞完整
    理由/涉及文件，只给每条任务一行摘要 + 完整简报路径。agent.py 的
    cmd_daily_scan 现在改用 build_notification_text_from_content()搭配
    skills.daily_sensing.format_text_plain()，这个函数保留给需要"直接从
    briefing对象生成通知文字、不经过daily_sensing格式化"场景的调用方。

    Returns: (content, mentioned_mobiles)
    """
    lines = [f"【PTA每日巡检】{Path(briefing.project_root).name}"]

    total = briefing.files_added + briefing.files_changed + briefing.files_removed
    lines.append(f"检测到 {total} 处变更，{len(briefing.suggested_tasks)} 条建议任务：")

    for i, t in enumerate(briefing.suggested_tasks, 1):
        signal = "、".join(t.signal_to) if t.signal_to else "（无）"
        mark_note = "（需内部对齐后线下找Mark）" if t.needs_mark_alignment else ""
        lines.append(f"{i}. [{t.priority}] {t.name} → 通知: {signal}{mark_note}")

    if report_path:
        lines.append(f"\n完整简报: {report_path}")

    content = "\n".join(lines)
    mentioned_mobiles = [mobiles_map["Jasper"]] if "Jasper" in mobiles_map else []
    return truncate_utf8_safe(content), mentioned_mobiles


def send_text(webhook_url: str, content: str, mentioned_mobiles: Optional[List[str]] = None) -> dict:
    """真实发送到企业微信群机器人 webhook，返回企业微信 API 的响应 dict
    （{"errcode":0,"errmsg":"ok"} 表示成功）。"""
    body = json.dumps({
        "msgtype": "text",
        "text": {
            "content": content,
            "mentioned_mobile_list": mentioned_mobiles or [],
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        webhook_url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return {"errcode": -1, "errmsg": f"HTTP {e.code}: {detail}"}
    except urllib.error.URLError as e:
        return {"errcode": -1, "errmsg": f"网络错误: {e}"}


def _webhook_to_upload_url(webhook_url: str) -> str:
    """企业微信群机器人的文件上传接口和发送接口共用同一个 key，只是把
    `/webhook/send` 换成 `/webhook/upload_media`，再加 `type=file` 参数。"""
    upload_url = webhook_url.replace("/webhook/send", "/webhook/upload_media")
    separator = "&" if "?" in upload_url else "?"
    return f"{upload_url}{separator}type=file"


def _encode_multipart_file(file_path: Path) -> Tuple[bytes, str]:
    """手工构造 multipart/form-data 请求体——企业微信文件上传接口要求这个
    格式，标准库 urllib 没有现成的编码器，为了这一个请求引入 requests
    依赖不值得，就手写一份最小实现。"""
    boundary = uuid.uuid4().hex
    filename = file_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()

    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'
    ).encode("utf-8") + file_bytes + f'\r\n--{boundary}--\r\n'.encode("utf-8")

    return body, f"multipart/form-data; boundary={boundary}"


def upload_file(webhook_url: str, file_path: Path) -> Optional[str]:
    """上传文件到企业微信群机器人，返回 media_id；失败返回 None（不抛异常，
    调用方决定要不要继续走"只发文本、不发附件"的降级路径）。"""
    upload_url = _webhook_to_upload_url(webhook_url)
    body, content_type = _encode_multipart_file(Path(file_path))

    req = urllib.request.Request(
        upload_url, data=body, method="POST",
        headers={"Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[警告] 企业微信文件上传失败: HTTP {e.code} {e.read().decode('utf-8', errors='replace')}")
        return None
    except urllib.error.URLError as e:
        print(f"[警告] 企业微信文件上传失败: 网络错误 {e}")
        return None

    if result.get("errcode") != 0:
        print(f"[警告] 企业微信文件上传失败: {result.get('errmsg')}")
        return None
    return result.get("media_id")


def send_file(webhook_url: str, media_id: str) -> dict:
    """发送文件消息（file 类型），media_id 由 upload_file() 拿到——收到的人
    直接在企业微信里点开这条消息就能查看/下载完整简报，不受"本地文件路径
    在别的设备上打不开"这个限制。"""
    body = json.dumps({"msgtype": "file", "file": {"media_id": media_id}}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return {"errcode": -1, "errmsg": f"HTTP {e.code}: {detail}"}
    except urllib.error.URLError as e:
        return {"errcode": -1, "errmsg": f"网络错误: {e}"}
