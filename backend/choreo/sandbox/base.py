"""
BaseSandbox - Abstract base class for sandbox environments.

Provides an async-first interface for executing code in isolated containers
with file operations and command execution capabilities.
"""

from abc import ABC, abstractmethod


class BaseSandbox(ABC):
    """
    Abstract base class for sandbox implementations.

    All methods are async to avoid blocking the asyncio event loop.
    Paths are relative (internal path mapping is handled by concrete providers).
    """

    # === Lifecycle Management ===

    @abstractmethod
    async def start(self) -> None:
        """
        Start the sandbox environment (e.g., create and launch container).

        Raises:
            RuntimeError: If sandbox is already running or startup fails.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the sandbox while preserving state (e.g., pause container).

        Can be resumed with start(). Raises RuntimeError if already stopped.
        """
        pass

    @abstractmethod
    async def destroy(self) -> None:
        """
        Completely destroy the sandbox and clean up all resources.

        Irreversible; new start() will create a fresh environment.
        """
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """
        Check if sandbox is currently running.

        Returns:
            True if sandbox is active, False otherwise.
        """
        pass

    # === File Operations ===

    @abstractmethod
    async def read_file(
        self, path: str, offset: int = 0, limit: int = 2000
    ) -> str:
        """
        Read file contents (optionally with offset and limit).

        Args:
            path: Relative file path within sandbox.
            offset: Line number to start reading from (0-indexed).
            limit: Maximum number of lines to read.

        Returns:
            File contents as string.

        Raises:
            FileNotFoundError: If file does not exist.
            IsADirectoryError: If path is a directory.
        """
        pass

    @abstractmethod
    async def write_file(self, path: str, content: str) -> str:
        """
        Write content to a file (creates or overwrites).

        Args:
            path: Relative file path within sandbox.
            content: Content to write.

        Returns:
            Confirmation message with file path.

        Raises:
            IsADirectoryError: If path exists as directory.
            PermissionError: If write is denied.
        """
        pass

    @abstractmethod
    async def edit_file(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        """
        Edit file by replacing text (like sed or string replacement).

        Args:
            path: Relative file path within sandbox.
            old_string: Exact text to find and replace.
            new_string: Replacement text.
            replace_all: If True, replace all occurrences; if False, replace first match.

        Returns:
            Confirmation message with number of replacements made.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If old_string not found and replace_all=False.
        """
        pass

    @abstractmethod
    async def list_dir(self, path: str = ".") -> str:
        """
        List directory contents (like ls -la).

        Args:
            path: Relative directory path (default: current directory).

        Returns:
            Directory listing as formatted string.

        Raises:
            NotADirectoryError: If path is not a directory.
            FileNotFoundError: If path does not exist.
        """
        pass

    @abstractmethod
    async def grep(self, pattern: str, path: str = ".", glob: str = "**/*") -> str:
        """
        Search for pattern in files (like ripgrep or grep).

        Args:
            pattern: Regex or literal pattern to search for.
            path: Relative directory to search in (default: current directory).
            glob: Glob pattern for files to search (default: all files recursively).

        Returns:
            Grep output with file paths, line numbers, and matches.

        Raises:
            FileNotFoundError: If path does not exist.
        """
        pass

    # === Command Execution ===

    @abstractmethod
    async def bash(self, command: str, timeout: int = 30) -> str:
        """
        Execute bash command in sandbox.

        Args:
            command: Shell command to execute.
            timeout: Timeout in seconds (default: 30s).

        Returns:
            Combined stdout and stderr output.

        Raises:
            TimeoutError: If command exceeds timeout.
            RuntimeError: If execution fails (non-zero exit code, etc.).
        """
        pass
