# backend/choreo/skills/bundled.py
import json
import shutil
import time
from pathlib import Path

from choreo.skills.store import LocalSkillStore, _parse_skill_md

_BUILTIN_DIR = Path(__file__).parent.parent / "builtin_skills"


async def sync_builtin_skills(store: LocalSkillStore) -> None:
    """Idempotent: copy built-in skills respecting user modifications in .bundled_manifest."""
    if not _BUILTIN_DIR.exists():
        return

    manifest_path = store._root / ".bundled_manifest"
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for skill_md in sorted(_BUILTIN_DIR.glob("*/*/SKILL.md")):
        skill_dir = skill_md.parent
        category = skill_dir.parent.name
        name = skill_dir.name
        skill_id = f"{category}/{name}"

        fm, _ = _parse_skill_md(skill_md.read_text(encoding="utf-8"))
        bundled_version = fm.get("version", "1.0.0")

        entry = manifest.get(skill_id, {})
        user_modified = entry.get("user_modified", False)

        dest_dir = store._root / category / name
        should_copy = not dest_dir.exists() or not user_modified

        if should_copy:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill_md, dest_dir / "SKILL.md")

            async with store._usage_lock:
                usage = await store._read_usage()
                if skill_id not in usage:
                    usage[skill_id] = {
                        "use_count": 0,
                        "view_count": 0,
                        "patch_count": 0,
                        "last_activity_at": int(time.time()),
                        "state": "active",
                        "pinned": False,
                        "source": "builtin",
                    }
                await store._write_usage(usage)

        manifest[skill_id] = {
            "bundled_version": bundled_version,
            "user_modified": user_modified,
        }

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
