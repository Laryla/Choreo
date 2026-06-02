"""
Output directory browser API.

Reads directly from the host filesystem (sandbox/output/<thread_id>/).
Does not require an active sandbox instance.
"""
import mimetypes
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

router = APIRouter()


def _get_output_root() -> Path:
    """Resolve the base output directory from config.yaml."""
    try:
        from choreo.sandbox.factory import _load_yaml
        cfg = _load_yaml(None)
        raw = cfg.get("output_dir")
        if raw:
            return Path(raw).expanduser().resolve()
    except Exception:
        pass
    # Fallback: relative to backend/
    return Path(__file__).parents[3] / "sandbox" / "output"


def _safe_path(path: str) -> str:
    if not path or ".." in path or path.startswith("/"):
        raise HTTPException(400, "Invalid path")
    return str(PurePosixPath(path))


def _thread_dir(thread_id: str) -> Path:
    root = _get_output_root()
    d = (root / thread_id).resolve()
    if not str(d).startswith(str(root)):
        raise HTTPException(400, "Invalid thread_id")
    return d


@router.get("/output/")
async def list_output(thread_id: str = "", subdir: str = ""):
    if not thread_id:
        # List all thread dirs
        root = _get_output_root()
        if not root.exists():
            return {"files": []}
        entries = []
        for p in sorted(root.iterdir()):
            if p.is_dir():
                entries.append({"name": p.name, "type": "dir", "size": None})
        return {"files": entries}

    base = _thread_dir(thread_id)
    target = base / subdir if subdir else base
    target = target.resolve()

    # Ensure still inside thread dir
    if not str(target).startswith(str(base)):
        raise HTTPException(400, "Invalid subdir")

    if not target.exists():
        return {"files": []}

    files = []
    for p in sorted(target.iterdir()):
        if p.is_dir():
            files.append({"name": p.name, "type": "dir", "size": None})
        else:
            files.append({"name": p.name, "type": "file", "size": p.stat().st_size})
    return {"files": files}


@router.get("/output/file")
async def get_file(path: str, thread_id: str = ""):
    safe = _safe_path(path)

    if thread_id:
        base = _thread_dir(thread_id)
    else:
        base = _get_output_root()

    target = (base / safe).resolve()

    if not str(target).startswith(str(base)):
        raise HTTPException(400, "Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(404, f"File not found: {path}")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(500, str(exc))

    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")


@router.get("/output/raw")
async def get_raw_file(path: str, thread_id: str = ""):
    safe = _safe_path(path)

    if thread_id:
        base = _thread_dir(thread_id)
    else:
        base = _get_output_root()

    target = (base / safe).resolve()

    if not str(target).startswith(str(base)):
        raise HTTPException(400, "Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(404, f"File not found: {path}")

    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(str(target), media_type=media_type or "application/octet-stream")
