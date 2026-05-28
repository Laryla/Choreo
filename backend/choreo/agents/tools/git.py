from langchain_core.tools import tool
import subprocess


@tool
def read_git_log(since: str = "1 week ago", limit: int = 50) -> str:
    """读取最近的 git commit 记录。since: 时间范围如 '1 week ago'，limit: 最大条数。"""
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since}", f"-{limit}", "--oneline"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout or "（无 commit 记录）"
    except Exception as e:
        return f"读取失败：{e}"
