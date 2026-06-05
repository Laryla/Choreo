# Skill Middleware Implementation Plan (Plan 2/2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Prerequisite:** `2026-05-29-skill-crud.md` must be fully completed first.

**Goal:** 实现技能注入中间件（每次 LLM 调用前注入 Index）、自动沉淀中间件（复杂任务后后台生成技能）和 skill_manage 工具（agent 可 CRUD 技能）。

**Architecture:** `SkillInjectMiddleware.awrap_model_call` 把 `build_index()` 结果追加到 SystemMessage；`SkillSedimentMiddleware.aafter_agent` 在 agent 完成后后台异步调用 LLM 总结并写入技能；`skill_manage` 工具让 agent 主动管理技能，保护 pinned 技能不被删除/覆盖。

**Tech Stack:** LangChain AgentMiddleware, asyncio.create_task, json parsing

---

## File Map

**New files:**
- `choreo/agents/middlewares/skill_inject.py`
- `choreo/agents/middlewares/skill_sediment.py`
- `choreo/agents/tools/skill_manage_tool.py`
- `tests/test_skill_middleware.py`

**Modified files:**
- `choreo/agents/middlewares/__init__.py` — export 2 new middlewares
- `choreo/agents/tools/__init__.py` — export skill_manage
- `choreo/agents/choreo_agent.py` — register tools + middlewares + update system_prompt

---

## Task 1: SkillInjectMiddleware

**Files:**
- Create: `backend/choreo/agents/middlewares/skill_inject.py`
- Create: `backend/tests/test_skill_middleware.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_skill_middleware.py
import pytest
from langchain_core.messages import SystemMessage, HumanMessage
from choreo.skills import set_skill_store, LocalSkillStore
from choreo.models.skill import SkillCreate


@pytest.fixture(autouse=True)
def init_store(tmp_path):
    store = LocalSkillStore(tmp_path / "skills")
    set_skill_store(store)
    return store


@pytest.mark.asyncio
async def test_inject_appends_index_to_system_message(init_store):
    await init_store.create(SkillCreate(
        category="git", name="log",
        description="Use when reading git history", tags=["git"]
    ))

    class FakeRequest:
        messages = [
            SystemMessage(content="You are Choreo."),
            HumanMessage(content="show git log"),
        ]
        model = None

    captured = []
    async def handler(req):
        captured.append(req)
        return "ok"

    from choreo.agents.middlewares.skill_inject import SkillInjectMiddleware
    await SkillInjectMiddleware().awrap_model_call(FakeRequest(), handler)

    assert captured
    sys_content = captured[0].messages[0].content
    assert "Available Skills" in sys_content
    assert "git/log" in sys_content
    assert "You are Choreo." in sys_content


@pytest.mark.asyncio
async def test_no_injection_when_no_skills(init_store):
    class FakeRequest:
        messages = [SystemMessage(content="You are Choreo."), HumanMessage(content="hi")]
        model = None

    captured = []
    async def handler(req):
        captured.append(req)
        return "ok"

    from choreo.agents.middlewares.skill_inject import SkillInjectMiddleware
    await SkillInjectMiddleware().awrap_model_call(FakeRequest(), handler)

    assert "Available Skills" not in captured[0].messages[0].content
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd backend && uv run pytest tests/test_skill_middleware.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'SkillInjectMiddleware'`

- [ ] **Step 3: Create `skill_inject.py`**

```python
# backend/choreo/agents/middlewares/skill_inject.py
"""
SkillInjectMiddleware: Layer 0 skill injection.

Appends a compact skills index to the SystemMessage before each LLM call.
The agent reads the index and calls skill_view() to fetch full content when needed.
"""
from typing import Any
from langchain_core.messages import SystemMessage
from langchain.agents.middleware import AgentMiddleware
from choreo.skills import get_skill_store


class SkillInjectMiddleware(AgentMiddleware):
    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        try:
            store = get_skill_store()
            index = await store.build_index()
        except RuntimeError:
            return await handler(request)

        if not index:
            return await handler(request)

        messages = list(request.messages)
        if messages and isinstance(messages[0], SystemMessage):
            messages[0] = SystemMessage(content=f"{messages[0].content}\n\n---\n{index}\n---")
        else:
            messages.insert(0, SystemMessage(content=f"---\n{index}\n---"))
        request.messages = messages
        return await handler(request)
```

- [ ] **Step 4: Run tests and verify pass**

```bash
cd backend && uv run pytest tests/test_skill_middleware.py::test_inject_appends_index_to_system_message tests/test_skill_middleware.py::test_no_injection_when_no_skills -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/agents/middlewares/skill_inject.py backend/tests/test_skill_middleware.py
git commit -m "feat(skills): add SkillInjectMiddleware - injects index into system prompt"
```

---

## Task 2: SkillSedimentMiddleware

**Files:**
- Create: `backend/choreo/agents/middlewares/skill_sediment.py`
- Modify: `backend/tests/test_skill_middleware.py` (add tests)

- [ ] **Step 1: Append failing tests**

Append to `backend/tests/test_skill_middleware.py`:

```python
import asyncio
from langchain_core.messages import AIMessage, ToolMessage
from choreo.models.skill import SkillPatch


@pytest.mark.asyncio
async def test_sediment_skips_when_few_tool_calls(init_store):
    """Tasks with <3 ToolMessages must not create a skill."""
    from choreo.agents.middlewares.skill_sediment import SkillSedimentMiddleware
    mw = SkillSedimentMiddleware(llm=None)
    state = {"messages": [HumanMessage(content="hi"), AIMessage(content="hello")]}
    await mw.aafter_agent(state, runtime=None)
    await asyncio.sleep(0.05)
    assert len(await init_store.list_active()) == 0


@pytest.mark.asyncio
async def test_sediment_skips_pinned_duplicate(init_store):
    """Never overwrite a skill that is pinned=True."""
    await init_store.create(SkillCreate(
        category="git", name="log", description="Use when reading git log", content="original"
    ))
    await init_store.update("git/log", SkillPatch(pinned=True))

    from choreo.agents.middlewares.skill_sediment import SkillSedimentMiddleware
    mw = SkillSedimentMiddleware(llm=None)
    await mw._try_create(
        category="git", name="log",
        description="Use when reading git log",
        tags=[], content="new content", source="auto"
    )
    skill = await init_store.get("git/log")
    assert skill.content == "original"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && uv run pytest tests/test_skill_middleware.py::test_sediment_skips_when_few_tool_calls -v 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: Create `skill_sediment.py`**

```python
# backend/choreo/agents/middlewares/skill_sediment.py
"""
SkillSedimentMiddleware: auto-generate skill files after complex tasks.

Triggers when aafter_agent fires and the conversation has >= 3 ToolMessages
(indicating a non-trivial workflow). Runs LLM summarization in a background
asyncio.create_task so the user response is never delayed.

Pinned skills are never overwritten.
"""
import asyncio
import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import ToolMessage
from langchain.agents.middleware import AgentMiddleware

from choreo.skills import get_skill_store
from choreo.models.skill import SkillCreate, SkillPatch

logger = logging.getLogger(__name__)

_MIN_TOOL_CALLS = 3

_PROMPT = """You completed a development task. Extract a reusable skill document.

Conversation (recent tool calls):
{summary}

Respond with ONLY a JSON object, no markdown:
{{
  "category": "<one word: git|deploy|code|test|notify|misc>",
  "name": "<kebab-case max 30 chars>",
  "description": "Use when <20 words>",
  "tags": ["tag1", "tag2"],
  "content": "## When to Use\\n- ...\\n\\n## Steps\\n1. ...\\n\\n## Common Pitfalls\\n- ..."
}}"""


class SkillSedimentMiddleware(AgentMiddleware):
    def __init__(self, llm: Any) -> None:
        super().__init__()
        self._llm = llm

    async def aafter_agent(self, state: Any, runtime: Any) -> None:
        if self._llm is None:
            return None
        messages = state.get("messages", []) if isinstance(state, dict) else []
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        if len(tool_msgs) < _MIN_TOOL_CALLS:
            return None
        asyncio.create_task(self._sediment(messages, len(tool_msgs)))
        return None

    async def _sediment(self, messages: list, n_tools: int) -> None:
        try:
            summary = _summarize(messages)
            response = await self._llm.ainvoke(_PROMPT.format(summary=summary))
            text = response.content if hasattr(response, "content") else str(response)
            data = _parse_json(text)
            if not data:
                logger.warning("skill sediment: failed to parse LLM output")
                return
            await self._try_create(
                category=str(data.get("category", "misc")),
                name=str(data.get("name", f"skill-{int(time.time())}")),
                description=str(data.get("description", "")),
                tags=list(data.get("tags", [])),
                content=str(data.get("content", "")),
                source="auto",
            )
        except Exception as exc:
            logger.warning("skill sediment error: %r", exc)

    async def _try_create(
        self,
        category: str,
        name: str,
        description: str,
        tags: list,
        content: str,
        source: str,
    ) -> None:
        try:
            store = get_skill_store()
        except RuntimeError:
            return
        skill_id = f"{category}/{name}"
        existing = await store.get(skill_id)
        if existing and existing.pinned:
            logger.info("skill sediment: skipped pinned %s", skill_id)
            return
        if existing:
            await store.update(skill_id, SkillPatch(
                description=description, tags=tags, content=content
            ))
            logger.info("skill sediment: updated %s", skill_id)
        else:
            await store.create(SkillCreate(
                category=category, name=name,
                description=description, tags=tags,
                content=content, source=source,
            ))
            logger.info("skill sediment: created %s", skill_id)


def _summarize(messages: list) -> str:
    lines = []
    for msg in messages[-20:]:
        t = getattr(msg, "type", "")
        if t == "human":
            lines.append(f"User: {str(msg.content)[:200]}")
        elif t == "tool":
            lines.append(f"Tool({getattr(msg, 'name', '')}): {str(msg.content)[:200]}")
    return "\n".join(lines[-15:])


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None
```

- [ ] **Step 4: Run all middleware tests**

```bash
cd backend && uv run pytest tests/test_skill_middleware.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/agents/middlewares/skill_sediment.py
git commit -m "feat(skills): add SkillSedimentMiddleware - auto-generates skills from complex tasks"
```

---

## Task 3: skill_manage Tool

**Files:**
- Create: `backend/choreo/agents/tools/skill_manage_tool.py`
- Modify: `backend/tests/test_skill_middleware.py` (add tests)

- [ ] **Step 1: Append failing tests**

Append to `backend/tests/test_skill_middleware.py`:

```python
@pytest.mark.asyncio
async def test_skill_manage_create(init_store):
    from choreo.agents.tools.skill_manage_tool import skill_manage
    result = await skill_manage.ainvoke({
        "action": "create",
        "category": "test",
        "name": "sample",
        "description": "Use when testing skill_manage",
        "tags": "test,sample",
        "content": "## Steps\n1. test",
    })
    assert "created" in result.lower()
    skill = await init_store.get("test/sample")
    assert skill is not None
    assert skill.source == "auto"


@pytest.mark.asyncio
async def test_skill_manage_update(init_store):
    from choreo.agents.tools.skill_manage_tool import skill_manage
    await init_store.create(SkillCreate(
        category="git", name="log", description="Use when reading git log"
    ))
    result = await skill_manage.ainvoke({
        "action": "update",
        "category": "git",
        "name": "log",
        "content": "## Steps\n1. updated",
    })
    assert "updated" in result.lower()
    skill = await init_store.get("git/log")
    assert skill.content == "## Steps\n1. updated"


@pytest.mark.asyncio
async def test_skill_manage_delete(init_store):
    from choreo.agents.tools.skill_manage_tool import skill_manage
    await init_store.create(SkillCreate(
        category="test", name="to-del", description="Use when deleting"
    ))
    result = await skill_manage.ainvoke({
        "action": "delete", "category": "test", "name": "to-del"
    })
    assert "deleted" in result.lower()
    assert await init_store.get("test/to-del") is None


@pytest.mark.asyncio
async def test_skill_manage_cannot_delete_pinned(init_store):
    from choreo.agents.tools.skill_manage_tool import skill_manage
    await init_store.create(SkillCreate(
        category="git", name="pinned-skill", description="Use when pinned"
    ))
    await init_store.update("git/pinned-skill", SkillPatch(pinned=True))
    result = await skill_manage.ainvoke({
        "action": "delete", "category": "git", "name": "pinned-skill"
    })
    assert "pinned" in result.lower()
    assert await init_store.get("git/pinned-skill") is not None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && uv run pytest tests/test_skill_middleware.py::test_skill_manage_create -v 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: Create `skill_manage_tool.py`**

```python
# backend/choreo/agents/tools/skill_manage_tool.py
"""
skill_manage: let the agent create, update, or delete skill files.

Pinned skills are read-only — the agent cannot modify or delete them.
"""
from langchain_core.tools import tool
from choreo.skills import get_skill_store
from choreo.models.skill import SkillCreate, SkillPatch


@tool
async def skill_manage(
    action: str,
    category: str = "",
    name: str = "",
    description: str = "",
    tags: str = "",
    content: str = "",
) -> str:
    """Create, update, or delete a skill file.

    Use this to save a reusable workflow as a skill, or to improve an existing one.
    Pinned skills cannot be modified or deleted.

    Args:
        action: 'create', 'update', or 'delete'
        category: category folder name (e.g. 'git', 'deploy')
        name: skill name in kebab-case (e.g. 'weekly-report')
        description: one-line trigger description starting with "Use when..."
        tags: comma-separated tags (e.g. "git,report")
        content: full Markdown body with steps, pitfalls, checklist
    """
    if not category or not name:
        return "Error: category and name are required."

    store = get_skill_store()
    skill_id = f"{category}/{name}"
    tags_list = [t.strip() for t in tags.split(",") if t.strip()]

    if action == "create":
        if not description:
            return "Error: description is required for 'create'."
        existing = await store.get(skill_id)
        if existing:
            return f"Skill '{skill_id}' already exists. Use action='update' to modify it."
        await store.create(SkillCreate(
            category=category, name=name,
            description=description, tags=tags_list,
            content=content, source="auto",
        ))
        return f"Skill '{skill_id}' created successfully."

    elif action == "update":
        existing = await store.get(skill_id)
        if not existing:
            return f"Skill '{skill_id}' not found. Use action='create' to create it first."
        if existing.pinned:
            return f"Skill '{skill_id}' is pinned and cannot be modified by the agent."
        await store.update(skill_id, SkillPatch(
            description=description or None,
            tags=tags_list or None,
            content=content or None,
        ))
        return f"Skill '{skill_id}' updated successfully."

    elif action == "delete":
        existing = await store.get(skill_id)
        if not existing:
            return f"Skill '{skill_id}' not found."
        if existing.pinned:
            return f"Skill '{skill_id}' is pinned and cannot be deleted by the agent."
        await store.delete(skill_id)
        return f"Skill '{skill_id}' deleted."

    else:
        return f"Unknown action '{action}'. Valid actions: 'create', 'update', 'delete'."
```

- [ ] **Step 4: Run all middleware tests**

```bash
cd backend && uv run pytest tests/test_skill_middleware.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/agents/tools/skill_manage_tool.py
git commit -m "feat(skills): add skill_manage tool - agent can create/update/delete skills"
```

---

## Task 4: Register Everything in the Agent

**Files:**
- Modify: `backend/choreo/agents/middlewares/__init__.py`
- Modify: `backend/choreo/agents/tools/__init__.py`
- Modify: `backend/choreo/agents/choreo_agent.py`

- [ ] **Step 1: Update `middlewares/__init__.py`**

Add:
```python
from choreo.agents.middlewares.skill_inject import SkillInjectMiddleware
from choreo.agents.middlewares.skill_sediment import SkillSedimentMiddleware
```

Add both names to `__all__`.

- [ ] **Step 2: Update `tools/__init__.py`**

Add:
```python
from choreo.agents.tools.skill_manage_tool import skill_manage
```

Add `"skill_manage"` to `__all__`.

- [ ] **Step 3: Update `choreo_agent.py`**

Update the imports to:
```python
from choreo.agents.tools import (
    read_git_log, send_notification,
    read_file, write_file, edit_file, list_dir, grep, bash,
    skill_view, skill_manage,
)
from choreo.agents.middlewares import (
    ModelCallLimitMiddleware, TitleMiddleware, ModelSelectorMiddleware,
    SkillInjectMiddleware, SkillSedimentMiddleware,
)
```

Update `tools=[...]`:
```python
tools=[
    read_git_log, send_notification,
    read_file, write_file, edit_file, list_dir, grep, bash,
    skill_view, skill_manage,
],
```

Update `middleware=[...]` — order matters:
```python
middleware=[
    ModelSelectorMiddleware(),
    SkillInjectMiddleware(),            # 1. inject index before LLM
    HumanInTheLoopMiddleware(
        interrupt_on={
            "bash": {
                "description": "即将执行 bash 命令，请确认",
                "allowed_decisions": ["approve", "edit", "reject"],
            },
            "send_notification": {
                "description": "即将发送通知，请确认",
                "allowed_decisions": ["approve", "reject"],
            },
        }
    ),
    ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
    TitleMiddleware(llm=llm, max_chars=20),
    SkillSedimentMiddleware(llm=llm),   # 2. auto-sediment after agent completes
],
```

Add to `system_prompt`:
```python
"- skill_view：读取技能库中某个技能的完整内容（从系统消息的 Available Skills 中找到 ID 后调用）\n"
"- skill_manage：创建/更新/删除技能文件（action: create/update/delete）\n"
```

- [ ] **Step 4: Run complete test suite**

```bash
cd backend && uv run pytest tests/test_skill_store.py tests/test_skill_middleware.py -v
```

Expected: `19 passed`

- [ ] **Step 5: Start backend and verify injection**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload --port 8000
```

In the chat UI, send a message and check backend logs. The LLM request should contain:
```
Available Skills (use skill_view to read full content):

git:
  📌 git/weekly-report: Use when user wants to generate a weekly git...
```

- [ ] **Step 6: Verify auto-sediment**

In chat, run a task that calls ≥3 tools:
```
帮我列一下当前目录，找找 Python 文件，读一下 config.py 的前 20 行
```

After the agent responds, wait 3 seconds then:
```bash
cat backend/skills/.usage.json
```
Expected: a new entry with `"source": "auto"` appears.

- [ ] **Step 7: Final commit**

```bash
git add backend/choreo/agents/middlewares/__init__.py backend/choreo/agents/tools/__init__.py backend/choreo/agents/choreo_agent.py
git commit -m "feat(skills): register SkillInjectMiddleware, SkillSedimentMiddleware, skill_manage in agent"
```

---

## Self-Review

**Spec coverage:**
- ✅ SkillInjectMiddleware: full index injected, grouped by category, no injection when empty
- ✅ SkillSedimentMiddleware: background task, min 3 tool calls, pinned protection
- ✅ skill_manage: create / update / delete, pinned blocks modify and delete
- ✅ skill_view record_use: updates use_count in root .usage.json
- ✅ All 3 components registered in choreo_agent.py in correct order

**Placeholder scan:** None.

**Type consistency:** `SkillPatch.state` (not `status`). `source: "auto"` set by both skill_manage and skill_sediment for agent-created skills.
