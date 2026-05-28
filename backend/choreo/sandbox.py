import subprocess
from choreo.config import settings
from pathlib import Path


def run_in_sandbox(script_path: str) -> str:
    workdir = Path(settings.CHOREO_SANDBOX_WORKDIR)
    workdir.mkdir(exist_ok=True)
    try:
        result = subprocess.run(
            ["python", script_path],
            capture_output=True,
            text=True,
            timeout=settings.CHOREO_SANDBOX_TIMEOUT,
            cwd=str(workdir),
        )
        return result.stdout or result.stderr or "（无输出）"
    except subprocess.TimeoutExpired:
        return "执行超时"
    except Exception as e:
        return f"执行失败：{e}"
