"""
Bash command execution tool for sandbox environments.

Executes shell commands in the sandbox workspace. Dangerous operations
should be protected by HITL (Human-In-The-Loop) middleware.
"""

from langgraph.config import get_config
from langchain_core.tools import tool
from choreo.sandbox import get_sandbox_manager


@tool
async def bash(command: str, timeout: int = 30) -> str:
    """
    Execute a bash command in the sandbox workspace.

    Runs the command with a timeout. Dangerous operations (e.g., destructive
    file operations, privilege escalation) should be protected by HITL middleware.

    Args:
        command: Shell command to execute.
        timeout: Timeout in seconds (default: 30).

    Returns:
        Combined stdout and stderr output, or error message.
    """
    try:
        config = get_config()
        thread_id = config["configurable"]["thread_id"]
        manager = get_sandbox_manager()
        sandbox = manager.get(thread_id) or await manager.acquire(thread_id)
        return await sandbox.bash(command, timeout)
    except Exception as e:
        return f"Failed to execute command: {e}"
