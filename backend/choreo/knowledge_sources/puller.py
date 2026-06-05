from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def pull_once(adapters, kb_root: Path) -> dict[str, int]:
    """运行所有适配器，将返回的文档写入 raw/。

    返回 {adapter_name: 写入文件数} 统计。
    """
    raw_dir = kb_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stats: dict[str, int] = {}

    for adapter in adapters:
        try:
            docs = await adapter.pull()
            count = 0
            for filename, content in docs:
                safe = Path(filename).name  # 防路径穿越
                target = (raw_dir / safe).resolve()
                if not str(target).startswith(str(raw_dir.resolve())):
                    logger.warning("[%s] 跳过非法文件名: %s", adapter.name, filename)
                    continue
                target.write_text(content, encoding="utf-8")
                count += 1
            stats[adapter.name] = count
            logger.info("[%s] 写入 %d 篇文档到 raw/", adapter.name, count)
        except Exception as exc:
            logger.error("[%s] 拉取失败: %r", adapter.name, exc)
            stats[adapter.name] = -1

    return stats


def start_pull_scheduler(configs: list[dict]):
    """为每个配置了 schedule 的知识来源创建定时任务，返回 scheduler 实例。"""
    if not configs:
        return None

    from choreo.config import settings
    from choreo.knowledge_sources.factory import load_sources
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    adapters = load_sources(configs)
    if not adapters:
        return None

    kb_root = Path(settings.KNOWLEDGE_BASE_DIR).expanduser()
    scheduler = AsyncIOScheduler()

    for adapter, cfg in zip(adapters, configs):
        schedule = cfg.get("schedule", "0 2 * * *")
        try:
            trigger = CronTrigger.from_crontab(schedule)
        except Exception as exc:
            logger.warning("[%s] schedule 无效 %r: %r，跳过", adapter.name, schedule, exc)
            continue

        # 捕获 adapter 到闭包
        def _make_job(a):
            async def job():
                await pull_once([a], kb_root)
            return job

        scheduler.add_job(
            _make_job(adapter),
            trigger,
            id=f"pull-{adapter.name}",
            name=f"KB pull: {adapter.name}",
            replace_existing=True,
        )
        logger.info("[%s] 拉取任务已注册（schedule=%s）", adapter.name, schedule)

    scheduler.start()
    return scheduler
