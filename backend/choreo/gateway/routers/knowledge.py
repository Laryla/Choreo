import logging
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from pydantic import BaseModel

from choreo.config import settings
from choreo.kb.graph_parser import parse_graph

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_EXTS = {
    ".md", ".txt", ".pdf", ".docx", ".pptx", ".xlsx",
    ".html", ".htm", ".csv", ".json", ".xml",
}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


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
    if not file.filename:
        raise HTTPException(400, "缺少文件名")
    suffix = Path(file.filename).suffix.lower()
    if suffix in _IMAGE_EXTS:
        raise HTTPException(400, "暂不支持图片格式，请上传 PDF/DOCX/MD 等文本格式")
    if suffix not in _ALLOWED_EXTS:
        raise HTTPException(400, f"不支持的格式 {suffix}，支持：{', '.join(sorted(_ALLOWED_EXTS))}")

    raw_dir = _kb_root() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(file.filename).stem
    data = await file.read()

    if suffix in {".md", ".txt"}:
        out_name = stem + ".md"
        target = (raw_dir / out_name).resolve()
        if not str(target).startswith(str(raw_dir.resolve())):
            raise HTTPException(400, "非法文件名")
        target.write_bytes(data)
        return {"filename": out_name}

    # 非纯文本格式：用 markitdown 转换
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(tmp_path)
        md_content = result.text_content
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    out_name = stem + ".md"
    target = (raw_dir / out_name).resolve()
    if not str(target).startswith(str(raw_dir.resolve())):
        raise HTTPException(400, "非法文件名")
    target.write_text(md_content, encoding="utf-8")
    return {"filename": out_name, "converted_from": file.filename}


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


@router.get("/outputs/")
async def list_outputs():
    outputs_dir = _kb_root() / "wiki" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return [
        {"name": f.name, "size": f.stat().st_size, "modified_at": int(f.stat().st_mtime)}
        for f in sorted(outputs_dir.iterdir(), reverse=True)
        if f.is_file()
    ]


@router.get("/outputs/{filename}")
async def read_output(filename: str):
    outputs_dir = _kb_root() / "wiki" / "outputs"
    target = (outputs_dir / filename).resolve()
    if not str(target).startswith(str(outputs_dir.resolve())):
        raise HTTPException(400, "非法路径")
    if not target.exists():
        raise HTTPException(404, "文件不存在")
    return {"name": filename, "content": target.read_text(errors="replace")}


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
    from choreo.agents.choreo_agent import create_kb_agent
    from choreo.kb.compiler_prompt import INGEST_PROMPT
    today = datetime.now().strftime("%Y-%m-%d")

    # 注入当前索引
    index_path = _kb_root() / "wiki" / "index.md"
    index_content = ""
    if index_path.exists():
        text = index_path.read_text(encoding="utf-8", errors="replace").strip()
        if text and text != "# Knowledge Base Index":
            index_content = f"\n\n## 当前知识库索引（已有页面，避免重复创建）\n\n{text}\n"

    # 注入最新 lint 报告（优先处理缺失页面）
    lint_content = ""
    outputs_dir = _kb_root() / "wiki" / "outputs"
    if outputs_dir.exists():
        reports = sorted(outputs_dir.glob("lint-*.md"), reverse=True)
        if reports:
            text = reports[0].read_text(encoding="utf-8", errors="replace").strip()
            if text:
                lint_content = f"\n\n## 最新 Lint 报告（{reports[0].name}，优先补全缺失页面）\n\n{text}\n"

    prompt = INGEST_PROMPT.format(today=today) + index_content + lint_content
    agent = create_kb_agent()
    await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})


async def _run_lint() -> None:
    from langchain_core.messages import HumanMessage
    from choreo.agents.choreo_agent import create_kb_agent
    from choreo.kb.compiler_prompt import LINT_PROMPT
    date = datetime.now().strftime("%Y-%m-%d")
    agent = create_kb_agent()
    await agent.ainvoke({"messages": [HumanMessage(content=LINT_PROMPT.format(date=date))]})


@router.post("/ingest")
async def trigger_ingest(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_ingest)
    return {"status": "started"}


@router.post("/lint")
async def trigger_lint(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_lint)
    return {"status": "started"}


@router.post("/pull-sources", status_code=202)
async def trigger_pull_sources(background_tasks: BackgroundTasks):
    """手动触发所有外部知识来源拉取（写入 raw/）。"""
    background_tasks.add_task(_run_pull_sources)
    return {"status": "started", "message": "知识来源拉取已启动，完成后写入 raw/"}


async def _run_pull_sources() -> None:
    try:
        from choreo.config import settings
        from choreo.knowledge_sources.factory import load_sources
        from choreo.knowledge_sources.puller import pull_once

        configs: list[dict] = settings.KNOWLEDGE_SOURCES or []
        if not configs:
            logger.warning("KNOWLEDGE_SOURCES 未配置，跳过拉取")
            return
        adapters = load_sources(configs)
        kb_root = Path(settings.KNOWLEDGE_BASE_DIR).expanduser()
        stats = await pull_once(adapters, kb_root)
        logger.info("知识来源拉取完成: %s", stats)
    except Exception as exc:
        logger.error("知识来源拉取失败: %r", exc)


@router.post("/update-profile", status_code=202)
async def trigger_profile_update(background_tasks: BackgroundTasks):
    """手动触发用户画像更新（异步后台执行）。"""
    background_tasks.add_task(_run_profile_update)
    return {"status": "started", "message": "用户画像更新已启动，完成后写入 wiki/user/profile.md"}


async def _run_profile_update() -> None:
    try:
        from choreo.activity.profiler import update_profile
        await update_profile()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("画像更新失败: %r", exc)
