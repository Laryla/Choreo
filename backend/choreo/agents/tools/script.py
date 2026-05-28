from langchain_core.tools import tool
from pathlib import Path

TASKS_DIR = Path("tasks")


@tool
def generate_script(filename: str, content: str) -> str:
    """将生成的 Python 脚本写入 tasks/ 目录并返回文件路径。filename: 文件名（含.py），content: 脚本内容。"""
    TASKS_DIR.mkdir(exist_ok=True)
    path = TASKS_DIR / filename
    path.write_text(content, encoding="utf-8")
    return str(path)
