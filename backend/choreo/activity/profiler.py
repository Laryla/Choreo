from __future__ import annotations

import logging
from datetime import datetime, timedelta

from choreo.activity.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


def _get_collectors() -> list[BaseCollector]:
    """根据 ACTIVITY_PROFILE 配置构建采集器列表。"""
    from choreo.config import settings
    from choreo.activity.collectors.claude_code import ClaudeCodeCollector

    cfg: dict = getattr(settings, "ACTIVITY_PROFILE", {}) or {}
    sources: list[dict] = cfg.get("sources", [])

    collectors: list[BaseCollector] = []
    for src in sources:
        if src.get("type") == "claude_code_logs":
            collectors.append(ClaudeCodeCollector())

    # 未配置时默认启用 claude_code
    if not collectors:
        collectors.append(ClaudeCodeCollector())

    return collectors


async def collect_all(lookback_days: int = 7) -> str:
    """运行所有采集器并拼接输出。"""
    since = datetime.now() - timedelta(days=lookback_days)
    collectors = _get_collectors()
    parts: list[str] = []

    for collector in collectors:
        try:
            result = await collector.collect(since)
            if result.strip():
                parts.append(result)
        except Exception as exc:
            logger.warning("采集器 %s 失败: %r", type(collector).__name__, exc)

    return "\n\n---\n\n".join(parts)


async def update_profile() -> None:
    """采集行为数据，调用 KB agent 更新 wiki/user/。"""
    from choreo.config import settings
    from choreo.agents.choreo_agent import create_kb_agent
    from choreo.kb.profile_prompt import USER_PROFILE_PROMPT
    from langchain_core.messages import HumanMessage

    cfg: dict = getattr(settings, "ACTIVITY_PROFILE", {}) or {}
    lookback_days: int = int(cfg.get("lookback_days", 7))

    collected_data = await collect_all(lookback_days)
    if not collected_data.strip():
        logger.info("无行为数据，跳过画像更新")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    week = datetime.now().strftime("%Y-W%W")

    prompt = USER_PROFILE_PROMPT.format(
        week=week,
        today=today,
        lookback_days=lookback_days,
        collected_data=collected_data,
    )

    agent = create_kb_agent()
    await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
    logger.info("用户画像更新完成，周期：%s", week)


def start_profile_scheduler(cfg: dict | None = None):
    """启动画像更新的 APScheduler，返回 scheduler 实例（关闭时调用 .shutdown()）。"""
    if cfg is None:
        from choreo.config import settings
        cfg = settings.ACTIVITY_PROFILE or {}
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    if not cfg.get("enabled", False):
        logger.info("activity_profile 未启用，画像循环不启动")
        return None

    schedule: str = cfg.get("schedule", "0 9 * * 1")
    try:
        trigger = CronTrigger.from_crontab(schedule)
    except Exception as exc:
        logger.warning("activity_profile.schedule 无效 %r: %r，循环不启动", schedule, exc)
        return None

    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_profile, trigger, id="user_profile_update", replace_existing=True)
    scheduler.start()
    logger.info("用户画像调度器已启动（schedule=%s）", schedule)
    return scheduler
