"""
File operation tools for sandbox-isolated code execution.

Provides async tools for reading, writing, and searching files within
the sandbox environment managed by SandboxManager.
"""

from langgraph.config import get_config
from langchain_core.tools import tool
from choreo.sandbox import get_sandbox_manager


@tool
async def read_file(path: str, offset: int = 0, limit: int = 2000) -> str:
    """
    Read file contents with line-number prefixes, supporting pagination.

    Args:
        path: Relative file path within the sandbox.
        offset: Line number to start reading from (0-indexed).
        limit: Maximum number of lines to read (default: 2000).

    Returns:
        File contents as string with line number prefixes, or error message.
    """
    try:
        config = get_config()
        thread_id = config["configurable"]["thread_id"]
        manager = get_sandbox_manager()
        sandbox = manager.get(thread_id) or await manager.acquire(thread_id)
        return await sandbox.read_file(path, offset=offset, limit=limit)
    except Exception as e:
        return f"Failed to read file: {e}"


@tool
async def write_file(path: str, content: str) -> str:
    """
    Create or overwrite a file with the given content.

    Args:
        path: Relative file path within the sandbox.
        content: Complete content to write to the file.

    Returns:
        Confirmation message with file path, or error message.
    """
    try:
        config = get_config()
        thread_id = config["configurable"]["thread_id"]
        manager = get_sandbox_manager()
        sandbox = manager.get(thread_id) or await manager.acquire(thread_id)
        return await sandbox.write_file(path, content)
    except Exception as e:
        return f"Failed to write file: {e}"


@tool
async def edit_file(
    path: str, old_string: str, new_string: str, replace_all: bool = False
) -> str:
    """
    Edit a file by replacing text (like sed or string replacement).

    Finds the exact old_string and replaces it with new_string. If old_string
    is not found and replace_all=False, returns an error.

    Args:
        path: Relative file path within the sandbox.
        old_string: Exact text to find and replace.
        new_string: Replacement text.
        replace_all: If True, replace all occurrences; if False, replace first match only.

    Returns:
        Confirmation message with number of replacements, or error message.
    """
    try:
        config = get_config()
        thread_id = config["configurable"]["thread_id"]
        manager = get_sandbox_manager()
        sandbox = manager.get(thread_id) or await manager.acquire(thread_id)
        return await sandbox.edit_file(path, old_string, new_string, replace_all)
    except Exception as e:
        return f"Failed to edit file: {e}"


@tool
async def list_dir(path: str = ".") -> str:
    """
    List directory contents with type indicators and file sizes.

    Args:
        path: Relative directory path within the sandbox (default: current directory).

    Returns:
        Directory listing as formatted string showing (D=directory, F=file) and sizes,
        or error message.
    """
    try:
        config = get_config()
        thread_id = config["configurable"]["thread_id"]
        manager = get_sandbox_manager()
        sandbox = manager.get(thread_id) or await manager.acquire(thread_id)
        return await sandbox.list_dir(path)
    except Exception as e:
        return f"Failed to list directory: {e}"


@tool
async def grep(pattern: str, path: str = ".", glob: str = "**/*") -> str:
    """
    Search for regex pattern in files within the sandbox.

    Returns results in file:line:content format, limited to 200 matches.

    Args:
        pattern: Regex or literal pattern to search for.
        path: Relative directory to search in (default: current directory).
        glob: Glob pattern for files to search (default: all files recursively).

    Returns:
        Grep output with file paths, line numbers, and matching content (max 200 lines),
        or error message.
    """
    try:
        config = get_config()
        thread_id = config["configurable"]["thread_id"]
        manager = get_sandbox_manager()
        sandbox = manager.get(thread_id) or await manager.acquire(thread_id)
        return await sandbox.grep(pattern, path, glob)
    except Exception as e:
        return f"Failed to search files: {e}"
