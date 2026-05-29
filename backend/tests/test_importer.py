import pytest
from choreo.skills.importer import parse_md
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
