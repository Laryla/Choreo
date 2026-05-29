import io
import zipfile

import pytest
from choreo.skills.importer import parse_md, parse_zip
from choreo.models.skill import SkillCreate


def test_parse_md_full_frontmatter():
    text = """\
---
name: frontend-design
description: Use when designing frontend components
version: 1.2.0
author: alice
tags:
  - design
  - ui
---

# Frontend Design Skill

Body content here.
"""
    result = parse_md(text, category="design")
    assert isinstance(result, SkillCreate)
    assert result.name == "frontend-design"
    assert result.category == "design"
    assert result.description == "Use when designing frontend components"
    assert result.version == "1.2.0"
    assert result.author == "alice"
    assert result.tags == ["design", "ui"]
    assert "Body content here" in result.content


def test_parse_md_minimal_frontmatter():
    text = """\
---
name: my-skill
description: Use when doing something useful
---

Some body.
"""
    result = parse_md(text, category="imported")
    assert result.name == "my-skill"
    assert result.version == "1.0.0"
    assert result.author == "user"
    assert result.tags == []


def test_parse_md_no_frontmatter_raises():
    text = "Just plain text with no frontmatter."
    with pytest.raises(ValueError, match="missing frontmatter"):
        parse_md(text, category="imported")


def test_parse_md_missing_name_raises():
    text = """\
---
description: Use when something
---
body
"""
    with pytest.raises(ValueError, match="missing 'name'"):
        parse_md(text, category="imported")


def test_parse_md_missing_description_raises():
    text = """\
---
name: my-skill
---
body
"""
    with pytest.raises(ValueError, match="missing 'description'"):
        parse_md(text, category="imported")


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_parse_zip_with_directory_structure():
    md = """\
---
name: frontend-design
description: Use when designing UIs
---
body
"""
    data = _make_zip({"design/frontend-design.md": md})
    results, skipped = parse_zip(data)
    assert skipped == []
    assert len(results) == 1
    assert results[0].category == "design"
    assert results[0].name == "frontend-design"


def test_parse_zip_top_level_md_uses_imported_category():
    md = """\
---
name: my-skill
description: Use when doing stuff
---
body
"""
    data = _make_zip({"my-skill.md": md})
    results, skipped = parse_zip(data)
    assert results[0].category == "imported"


def test_parse_zip_multiple_skills():
    md1 = "---\nname: skill-a\ndescription: Use when A\n---\nbody"
    md2 = "---\nname: skill-b\ndescription: Use when B\n---\nbody"
    data = _make_zip({"cat1/skill-a.md": md1, "cat2/skill-b.md": md2})
    results, skipped = parse_zip(data)
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"skill-a", "skill-b"}


def test_parse_zip_skips_malformed_md():
    good = "---\nname: good\ndescription: Use when good\n---\nbody"
    bad = "no frontmatter at all"
    data = _make_zip({"cat/good.md": good, "cat/bad.md": bad})
    results, skipped = parse_zip(data)
    assert len(results) == 1
    assert "cat/bad.md" in skipped


def test_parse_zip_empty_raises():
    data = _make_zip({"readme.txt": "hello"})
    with pytest.raises(ValueError, match="no .md files"):
        parse_zip(data)
