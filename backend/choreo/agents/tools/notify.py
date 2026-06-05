import json
import smtplib
from email.message import EmailMessage

from langchain_core.tools import tool

from choreo.config import settings


@tool
def send_notification(content: str, channel: str = "feishu", subject: str = "Choreo 通知") -> str:
    """发送通知给用户。channel: 'feishu'（默认）或 'email'。content: 消息内容。"""
    if channel == "feishu":
        return _send_feishu(content)
    elif channel == "email":
        return _send_email(content, subject)
    return f"未知 channel: {channel}"


_FEISHU_CARD_LIMIT = 3800  # 飞书卡片 markdown 元素字符上限，留余量


def _make_card(content: str) -> dict:
    """构建飞书卡片消息（支持 Markdown 渲染）。"""
    return {
        "config": {"wide_screen_mode": True},
        "elements": [{"tag": "markdown", "content": content}],
    }


def _split_content(content: str, limit: int = _FEISHU_CARD_LIMIT) -> list[str]:
    """按段落切分超长内容，每段不超过 limit 字符。"""
    if len(content) <= limit:
        return [content]

    chunks: list[str] = []
    paragraphs = content.split("\n\n")
    current = ""
    for para in paragraphs:
        # 单个段落超长时强制切断
        if len(para) > limit:
            if current:
                chunks.append(current.strip())
                current = ""
            for i in range(0, len(para), limit):
                chunks.append(para[i:i + limit])
            continue
        candidate = (current + "\n\n" + para).lstrip() if current else para
        if len(candidate) > limit:
            chunks.append(current.strip())
            current = para
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _send_feishu(content: str) -> str:
    """使用已配置的飞书 Bot 发送消息到 FEISHU_NOTIFY_CHAT_ID。内容过长时自动分段发送。"""
    chunks = _split_content(content)
    total = len(chunks)

    chat_id = settings.FEISHU_NOTIFY_CHAT_ID
    if not chat_id:
        if settings.FEISHU_WEBHOOK_URL:
            import httpx
            errors = []
            for i, chunk in enumerate(chunks, 1):
                text = chunk if total == 1 else f"({i}/{total})\n\n{chunk}"
                r = httpx.post(
                    settings.FEISHU_WEBHOOK_URL,
                    json={"msg_type": "interactive", "card": _make_card(text)},
                )
                if r.status_code != 200:
                    errors.append(f"第{i}段失败: {r.text}")
            return "飞书 Webhook 发送成功" if not errors else f"部分失败: {'; '.join(errors)}"
        return "未配置 FEISHU_NOTIFY_CHAT_ID 或 FEISHU_WEBHOOK_URL"

    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
        return "未配置 FEISHU_APP_ID / FEISHU_APP_SECRET"

    try:
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        client = (
            lark.Client.builder()
            .app_id(settings.FEISHU_APP_ID)
            .app_secret(settings.FEISHU_APP_SECRET)
            .build()
        )
        errors = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk if total == 1 else f"({i}/{total})\n\n{chunk}"
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(json.dumps(_make_card(text)))
                    .build()
                )
                .build()
            )
            resp = client.im.v1.message.create(request)
            if not resp.success():
                errors.append(f"第{i}段: code={resp.code} msg={resp.msg}")
        return "飞书通知发送成功" if not errors else f"部分失败: {'; '.join(errors)}"
    except ImportError:
        return "lark-oapi 未安装，请 uv add lark-oapi"
    except Exception as e:
        return f"飞书通知异常: {e}"


def _send_email(content: str, subject: str) -> str:
    if not settings.SMTP_HOST:
        return "未配置 SMTP 服务器"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = settings.SMTP_USER
    msg.set_content(content)
    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as s:
        s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        s.send_message(msg)
    return "邮件发送成功"
