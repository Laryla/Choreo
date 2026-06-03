import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_runner_creates_run_record():
    """Runner 执行后 task_run 状态应为 success。"""
    from choreo.scheduler.runner import TaskRunner

    mock_task = MagicMock()
    mock_task.id = str(uuid.uuid4())
    mock_task.description = "test task"
    mock_task.prompt = "search github trending"
    mock_task.notify_config = {}

    mock_run = MagicMock()
    mock_run.id = str(uuid.uuid4())
    mock_run.status = "running"
    mock_run.output = ""

    with patch("choreo.scheduler.runner.get_task_and_last_run", new_callable=AsyncMock) as mock_get, \
         patch("choreo.scheduler.runner.create_run", new_callable=AsyncMock) as mock_create, \
         patch("choreo.scheduler.runner.update_run", new_callable=AsyncMock) as mock_update, \
         patch("choreo.scheduler.runner.create_choreo_agent") as mock_agent_factory, \
         patch("choreo.scheduler.runner.NotifierRouter") as mock_notifier_cls:

        mock_get.return_value = (mock_task, None)
        mock_create.return_value = mock_run

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="## 结果\n找到10个项目")]
        })
        mock_agent_factory.return_value = mock_agent

        mock_notifier = MagicMock()
        mock_notifier.send = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        runner = TaskRunner()
        await runner.run(mock_task.id)

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["status"] == "success"
        assert "结果" in call_kwargs["output"]
