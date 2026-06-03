import httpx
import logging
from choreo.scheduler.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


class FeishuNotifier(BaseNotifier):
    def __init__(self, webhook: str) -> None:
        self._webhook = webhook

    async def send(self, task, run) -> None:
        if not self._webhook:
            return
        summary = run.output[:400] + "..." if len(run.output) > 400 else run.output
        status_emoji = "✅" if run.status == "success" else "❌"
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"{status_emoji} 任务完成：{task.description}"}
                },
                "elements": [
                    {"tag": "markdown", "content": summary or "（无输出）"},
                ],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self._webhook, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.warning("FeishuNotifier failed: %s", e)
