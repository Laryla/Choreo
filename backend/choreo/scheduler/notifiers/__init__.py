from choreo.scheduler.notifiers.base import BaseNotifier
from choreo.scheduler.notifiers.feishu import FeishuNotifier


class NotifierRouter:
    def _build(self, notify_config: dict) -> list[BaseNotifier]:
        notifiers: list[BaseNotifier] = []
        channels = notify_config.get("channels") or []
        if not channels and notify_config.get("type"):
            channels = [notify_config]
        for ch in channels:
            t = ch.get("type")
            if t == "feishu":
                notifiers.append(FeishuNotifier(ch.get("webhook", "")))
        # 没有配置任何渠道时，回退到全局飞书 Bot
        if not notifiers:
            notifiers.append(FeishuNotifier())
        return notifiers

    async def send(self, task, run) -> None:
        for n in self._build(task.notify_config or {}):
            await n.send(task, run)


__all__ = ["NotifierRouter", "BaseNotifier", "FeishuNotifier"]
