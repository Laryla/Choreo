from langchain_core.tools import tool
from choreo.sandbox import run_in_sandbox


@tool
def run_script(script_path: str) -> str:
    """在沙箱中执行脚本并返回输出。script_path: 脚本文件路径。"""
    return run_in_sandbox(script_path)
