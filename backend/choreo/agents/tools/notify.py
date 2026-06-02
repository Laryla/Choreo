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


def _send_feishu(content: str) -> str:
    """使用已配置的飞书 Bot 发送消息到 FEISHU_NOTIFY_CHAT_ID。"""
    chat_id = settings.FEISHU_NOTIFY_CHAT_ID
    if not chat_id:
        # 回退到群机器人 Webhook
        if settings.FEISHU_WEBHOOK_URL:
            import httpx
            r = httpx.post(
                settings.FEISHU_WEBHOOK_URL,
                json={"msg_type": "text", "content": {"text": content}},
            )
            return f"飞书 Webhook 发送{'成功' if r.status_code == 200 else f'失败: {r.text}'}"
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
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": content}))
                .build()
            )
            .build()
        )
        resp = client.im.v1.message.create(request)
        if resp.success():
            return "飞书通知发送成功"
        return f"飞书通知失败: code={resp.code} msg={resp.msg}"
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
