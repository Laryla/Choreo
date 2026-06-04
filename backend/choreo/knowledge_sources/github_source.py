from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

import httpx

from choreo.knowledge_sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_TIMEOUT = 30


class GitHubSourceAdapter(BaseSourceAdapter):
    """从 GitHub 拉取仓库 README 和 Release Notes，写入 KB raw/。

    config 字段：
      repos    : 仓库列表，格式 "owner/repo"
      token    : GitHub Personal Access Token（选填，提高速率限制）
      fetch:
        readme   : true/false，是否拉 README（默认 true）
        releases : int，拉取最近 N 条 release（默认 3，0 表示不拉）
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._repos: list[str] = config.get("repos", [])
        token = config.get("token", "")
        fetch = config.get("fetch", {})
        self._fetch_readme: bool = fetch.get("readme", True)
        self._fetch_releases: int = int(fetch.get("releases", 3))

        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._headers = headers

    async def pull(self) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        async with httpx.AsyncClient(headers=self._headers, timeout=_TIMEOUT) as client:
            for repo in self._repos:
                try:
                    docs = await self._pull_repo(client, repo)
                    results.extend(docs)
                    logger.info("[%s] %s → %d 篇", self.name, repo, len(docs))
                except Exception as exc:
                    logger.warning("[%s] %s 拉取失败: %r", self.name, repo, exc)
        return results

    async def _pull_repo(self, client: httpx.AsyncClient, repo: str) -> list[tuple[str, str]]:
        docs: list[tuple[str, str]] = []
        safe = repo.replace("/", "-")

        if self._fetch_readme:
            readme = await self._get_readme(client, repo)
            if readme:
                docs.append((f"github-{safe}-readme.md", readme))

        if self._fetch_releases > 0:
            releases = await self._get_releases(client, repo, self._fetch_releases)
            if releases:
                docs.append((f"github-{safe}-releases.md", releases))

        return docs

    async def _get_readme(self, client: httpx.AsyncClient, repo: str) -> str:
        try:
            resp = await client.get(f"{_GITHUB_API}/repos/{repo}/readme")
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            data = resp.json()
            # README 内容是 base64 编码
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            # 超过 20K 截断
            if len(content) > 20_000:
                content = content[:20_000] + "\n\n...（已截断）"
            return f"# {repo} — README\n\n> 来源：{data.get('html_url', '')}\n\n{content}"
        except Exception as exc:
            logger.debug("[%s] README 获取失败 %s: %r", self.name, repo, exc)
            return ""

    async def _get_releases(self, client: httpx.AsyncClient, repo: str, limit: int) -> str:
        try:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{repo}/releases",
                params={"per_page": limit},
            )
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            releases: list[dict] = resp.json()
            if not releases:
                return ""

            parts = [f"# {repo} — Release Notes\n"]
            for r in releases:
                tag = r.get("tag_name", "")
                name = r.get("name", tag)
                published = r.get("published_at", "")[:10]
                body = (r.get("body") or "").strip()
                url = r.get("html_url", "")
                if len(body) > 3_000:
                    body = body[:3_000] + "\n...（已截断）"
                parts.append(f"## {name} ({published})\n\n> {url}\n\n{body}\n")

            return "\n---\n\n".join(parts)
        except Exception as exc:
            logger.debug("[%s] Releases 获取失败 %s: %r", self.name, repo, exc)
            return ""
