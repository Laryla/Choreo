---
author: choreo
description: Use when setting up or managing a Python project with uv (install, add, run)
name: uv-project
tags:
- python
- uv
- deps
version: 1.0.0
related_skills:
- debug/error-diagnosis
---

## Quick Reference

| Task | Command |
|------|---------|
| Install all deps | `uv sync` |
| Add a package | `uv add <pkg>` |
| Add dev-only | `uv add --dev <pkg>` |
| Run a script | `uv run python script.py` |
| Run tests | `uv run pytest` |
| List packages | `uv pip list` |

Never use bare `python`, `pip`, or `pytest` inside `backend/` — always prefix with `uv run`.

## When to Use
- User asks to install Python dependencies or set up the project environment
- User runs a Python script and gets `ModuleNotFoundError`
- User wants to add a new package to the project
- Counter-trigger: do NOT use for non-uv projects (pip/poetry/conda)

## Steps

### Install all dependencies
```bash
cd backend && uv sync
```

### Run a script or command
```bash
uv run python script.py
uv run uvicorn choreo.gateway.app:app --reload
uv run pytest tests/
```

### Add a new package
```bash
uv add package-name
# For dev-only:
uv add --dev package-name
```

### Check installed packages
```bash
uv pip list
```

## Common Pitfalls
- `VIRTUAL_ENV` warning: uv prints a warning when `$VIRTUAL_ENV` points to a different venv — safe to ignore, uv uses `.venv` from `pyproject.toml`
- Always prefix commands with `uv run` inside `backend/`, not bare `python` or `pytest`
- After `uv add`, commit the updated `pyproject.toml` and `uv.lock`

## Verification Checklist
- [ ] `uv sync` exits with no errors
- [ ] `uv run python -c "import <package>"` succeeds for newly added package
