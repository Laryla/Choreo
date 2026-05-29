import yaml

from choreo.models.skill import SkillCreate


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    after = text[end + 1:].lstrip("-").lstrip("\n").strip()
    return fm, after


def parse_md(text: str, category: str) -> SkillCreate:
    fm, body = _split_frontmatter(text)
    if not fm:
        raise ValueError("missing frontmatter")
    if not fm.get("name"):
        raise ValueError("missing 'name' in frontmatter")
    if not fm.get("description"):
        raise ValueError("missing 'description' in frontmatter")
    return SkillCreate(
        category=category,
        name=str(fm["name"]),
        description=str(fm["description"]),
        version=str(fm.get("version", "1.0.0")),
        author=str(fm.get("author", "user")),
        tags=list(fm.get("tags") or []),
        content=body,
        source="manual",
    )
