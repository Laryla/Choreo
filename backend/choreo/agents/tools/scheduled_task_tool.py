import uuid
import logging
from langchain_core.tools import tool
from choreo.db import SessionLocal, TaskRow
from sqlalchemy import select

logger = logging.getLogger(__name__)


@tool
async def create_scheduled_task(
    description: str,
    cron: str,
    prompt: str,
    webhook: str = "",
) -> str:
    """
    创建一个定时 Agent 任务。

    Args:
        description: 任务名称（一句话，如"每周 GitHub 热门项目追踪"）
        cron: Cron 表达式（如 "0 9 * * 1" 表示每周一09:00）
        prompt: 给 Agent 的完整指令，越详细越好
        webhook: 飞书 Webhook URL（可选），任务完成后推送通知
    """
    from langgraph.config import get_config
    config = get_config()
    user_id = (config.get("configurable") or {}).get("user_id")

    notify_config: dict = {}
    if webhook:
        notify_config = {"channels": [{"type": "feishu", "webhook": webhook}]}

    async with SessionLocal() as db:
        row = TaskRow(
            id=str(uuid.uuid4()),
            user_id=user_id,
            description=description,
            cron=cron,
            prompt=prompt,
            script_path="",
            notify_config=notify_config,
            status="active",
        )
        db.add(row)
        await db.commit()

    logger.info("create_scheduled_task: created %s (cron=%s)", row.id, cron)

    from choreo.agents.registry import get_scheduler
    scheduler = get_scheduler()
    if scheduler:
        scheduler.add_task(row.id, cron)

    return f"任务已创建：{description}（cron: {cron}，ID: {row.id}）"


@tool
async def list_scheduled_tasks() -> str:
    """列出当前所有定时任务。"""
    from langgraph.config import get_config
    config = get_config()
    user_id = (config.get("configurable") or {}).get("user_id")

    async with SessionLocal() as db:
        rows = (await db.execute(
            select(TaskRow).where(TaskRow.user_id == user_id)
        )).scalars().all()

    if not rows:
        return "当前没有定时任务。"
    lines = [f"- {r.description}（cron: {r.cron}，状态: {r.status}，ID: {r.id}）" for r in rows]
    return "\n".join(lines)
