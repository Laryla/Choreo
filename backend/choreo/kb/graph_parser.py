import re
from pathlib import Path

import yaml


def _extract_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(content[3:end]) or {}
    except Exception:
        return {}


def _infer_type_from_path(path: str) -> str:
    if "concepts/" in path:
        return "concept"
    if "entities/" in path:
        return "entity"
    if "sources/" in path:
        return "source-summary"
    if "comparisons/" in path:
        return "comparison"
    return "concept"


def parse_graph(kb_dir: str) -> dict:
    wiki_dir = Path(kb_dir) / "wiki"
    if not wiki_dir.exists():
        return {"nodes": [], "edges": []}

    nodes: list[dict] = []
    edges: list[dict] = []

    for md_file in sorted(wiki_dir.rglob("*.md")):
        content = md_file.read_text(errors="replace")
        fm = _extract_frontmatter(content)
        page_id = str(md_file.relative_to(wiki_dir))
        title = fm.get("title") or md_file.stem
        page_type = fm.get("type") or _infer_type_from_path(page_id)

        nodes.append({"id": page_id, "label": title, "type": page_type})

        for link in re.findall(r"\[\[([^\]]+)\]\]", content):
            edges.append({"source": page_id, "target": link})

    return {"nodes": nodes, "edges": edges}
