from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from pydantic import BaseModel

from choreo.config import settings
from choreo.kb.graph_parser import parse_graph

router = APIRouter()


def _kb_root() -> Path:
    return Path(settings.KNOWLEDGE_BASE_DIR)


class RawFile(BaseModel):
    name: str
    size: int
    modified_at: int


@router.get("/raw/", response_model=list[RawFile])
async def list_raw():
    raw_dir = _kb_root() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return [
        RawFile(name=f.name, size=f.stat().st_size, modified_at=int(f.stat().st_mtime))
        for f in sorted(raw_dir.iterdir())
        if f.is_file()
    ]


@router.post("/raw/", status_code=201)
async def upload_raw(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(400, "只支持 .md 文件")
    raw_dir = _kb_root() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = (raw_dir / file.filename).resolve()
    if not str(target).startswith(str(raw_dir.resolve())):
        raise HTTPException(400, "非法文件名")
    target.write_bytes(await file.read())
    return {"filename": file.filename}


_WIKI_CONTENT_DIRS = {"concepts", "entities", "sources", "comparisons"}


@router.get("/wiki/")
async def list_wiki():
    wiki_dir = _kb_root() / "wiki"
    if not wiki_dir.exists():
        return []
    return [
        {"path": str(md.relative_to(wiki_dir)), "name": md.stem, "modified_at": int(md.stat().st_mtime)}
        for md in sorted(wiki_dir.rglob("*.md"))
        if md.relative_to(wiki_dir).parts[0] in _WIKI_CONTENT_DIRS
    ]


@router.get("/wiki/{page_path:path}")
async def read_wiki(page_path: str):
    wiki_dir = _kb_root() / "wiki"
    target = (wiki_dir / page_path).resolve()
    if not str(target).startswith(str(wiki_dir.resolve())):
        raise HTTPException(400, "非法路径")
    if not target.exists():
        raise HTTPException(404, "页面不存在")
    return {"path": page_path, "content": target.read_text(errors="replace")}


@router.get("/graph")
async def get_graph():
    return parse_graph(settings.KNOWLEDGE_BASE_DIR)


@router.get("/log")
async def get_log():
    log_path = _kb_root() / "wiki" / "log.md"
    if not log_path.exists():
        return {"content": ""}
    return {"content": log_path.read_text(errors="replace")}


async def _run_ingest() -> None:
    from langchain_core.messages import HumanMessage
    from choreo.agents.choreo_agent import create_choreo_agent
    from choreo.kb.compiler_prompt import INGEST_PROMPT
    today = datetime.now().strftime("%Y-%m-%d")
    agent = create_choreo_agent(headless=True)
    await agent.ainvoke({"messages": [HumanMessage(content=INGEST_PROMPT.format(today=today))]})


async def _run_lint() -> None:
    from langchain_core.messages import HumanMessage
    from choreo.agents.choreo_agent import create_choreo_agent
    from choreo.kb.compiler_prompt import LINT_PROMPT
    date = datetime.now().strftime("%Y-%m-%d")
    agent = create_choreo_agent(headless=True)
    await agent.ainvoke({"messages": [HumanMessage(content=LINT_PROMPT.format(date=date))]})


@router.post("/ingest")
async def trigger_ingest(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_ingest)
    return {"status": "started"}


@router.post("/lint")
async def trigger_lint(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_lint)
    return {"status": "started"}
