from langchain_core.tools import tool
import httpx
import smtplib
from email.message import EmailMessage
from choreo.config import settings


@tool
def send_notification(channel: str, content: str, subject: str = "Choreo 通知") -> str:
    """发送通知。channel: 'feishu' 或 'email'，content: 消息内容，subject: 邮件主题。"""
    if channel == "feishu":
        if not settings.FEISHU_WEBHOOK_URL:
            return "未配置飞书 Webhook"
        r = httpx.post(
            settings.FEISHU_WEBHOOK_URL,
            json={"msg_type": "text", "content": {"text": content}},
        )
        return f"飞书发送{'成功' if r.status_code == 200 else '失败'}"
    elif channel == "email":
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
    return f"未知 channel: {channel}"
