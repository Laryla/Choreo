import json
import httpx
import logging
from choreo.scheduler.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


class FeishuNotifier(BaseNotifier):
    def __init__(self, webhook: str = "") -> None:
        self._webhook = webhook

    async def send(self, task, run) -> None:
        summary = run.output[:400] + "..." if len(run.output or "") > 400 else (run.output or "")
        status_emoji = "✅" if run.status == "success" else "❌"
        title = f"{status_emoji} 任务完成：{task.description}"

        if self._webhook:
            await self._send_webhook(title, summary)
        else:
            await self._send_bot(title, summary)

    async def _send_webhook(self, title: str, summary: str) -> None:
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "markdown", "content": summary or "（无输出）"}],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self._webhook, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.warning("FeishuNotifier webhook failed: %s", e)

    async def _send_bot(self, title: str, summary: str) -> None:
        from choreo.config import settings
        chat_id = settings.FEISHU_NOTIFY_CHAT_ID
        if not chat_id or not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
            logger.warning("FeishuNotifier: no webhook and no global bot config, skipping")
            return
        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

            client = (
                lark.Client.builder()
                .app_id(settings.FEISHU_APP_ID)
                .app_secret(settings.FEISHU_APP_SECRET)
                .build()
            )
            content = json.dumps({"text": f"{title}\n{summary or '（无输出）'}"})
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(content)
                    .build()
                )
                .build()
            )
            resp = client.im.v1.message.create(request)
            if not resp.success():
                logger.warning("FeishuNotifier bot failed: code=%s msg=%s", resp.code, resp.msg)
        except Exception as e:
            logger.warning("FeishuNotifier bot error: %s", e)
