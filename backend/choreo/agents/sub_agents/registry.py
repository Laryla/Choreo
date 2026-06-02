from __future__ import annotations

from choreo.agents.sub_agents.config import BUILTIN_SUBAGENTS, SubagentConfig


def get_subagent_config(name: str) -> SubagentConfig | None:
    """Look up a built-in sub-agent config by name. Returns None if not found."""
    return BUILTIN_SUBAGENTS.get(name)


def list_subagents() -> list[str]:
    """Return names of all registered built-in sub-agents."""
    return list(BUILTIN_SUBAGENTS.keys())
