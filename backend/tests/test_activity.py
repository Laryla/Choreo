import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from choreo.activity.collectors.claude_code import ClaudeCodeCollector, _desensitize


class TestDesensitize:
    def test_脱敏_api_key(self):
        text = "OPENAI_API_KEY=sk-secret123"
        result = _desensitize(text)
        assert "sk-secret123" not in result
        assert "<redacted>" in result

    def test_脱敏_token(self):
        result = _desensitize("access_token: ghp_abc123")
        assert "ghp_abc123" not in result

    def test_保留正常文本(self):
        text = "## 实现了 markitdown 上传\n- 支持 PDF/DOCX"
        assert _desensitize(text) == text


class TestClaudeCodeCollector:
    @pytest.fixture
    def projects_dir(self, tmp_path):
        proj = tmp_path / "projects" / "my-project"
        proj.mkdir(parents=True)
        index = [
            {
                "session_id": "abc123",
                "summary": "实现了功能 X",
                "message_count": 42,
                "git_branch": "feat/x",
                "updated_at": (datetime.now() - timedelta(days=1)).timestamp(),
            }
        ]
        (proj / "sessions-index.json").write_text(json.dumps(index))
        return tmp_path / "projects"

    @pytest.mark.asyncio
    async def test_采集返回字符串(self, projects_dir):
        collector = ClaudeCodeCollector(claude_projects_dir=projects_dir)
        since = datetime.now() - timedelta(days=7)
        with patch(
            "choreo.activity.collectors.claude_code.ClaudeCodeCollector._run_cc_log",
            new=AsyncMock(return_value="## 会话\n\n做了一些工作"),
        ):
            result = await collector.collect(since)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_无近期会话时返回空字符串(self, tmp_path):
        proj = tmp_path / "projects" / "old-project"
        proj.mkdir(parents=True)
        index = [{"session_id": "xyz", "updated_at": (datetime.now() - timedelta(days=30)).timestamp()}]
        (proj / "sessions-index.json").write_text(json.dumps(index))
        collector = ClaudeCodeCollector(claude_projects_dir=tmp_path / "projects")
        result = await collector.collect(datetime.now() - timedelta(days=7))
        assert result == ""

    @pytest.mark.asyncio
    async def test_cli_不可用时优雅降级(self, projects_dir):
        collector = ClaudeCodeCollector(claude_projects_dir=projects_dir)
        since = datetime.now() - timedelta(days=7)
        with patch(
            "choreo.activity.collectors.claude_code.ClaudeCodeCollector._run_cc_log",
            new=AsyncMock(return_value=""),
        ):
            result = await collector.collect(since)
        assert isinstance(result, str)  # 不抛异常

    @pytest.mark.asyncio
    async def test_项目目录不存在时返回空(self, tmp_path):
        collector = ClaudeCodeCollector(claude_projects_dir=tmp_path / "nonexistent")
        result = await collector.collect(datetime.now() - timedelta(days=7))
        assert result == ""
