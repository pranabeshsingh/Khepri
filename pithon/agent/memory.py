"""Markdown-backed persistent memory engine storing personal notes and knowledge."""

import logging
import os
import re
from datetime import datetime, timezone
import zoneinfo
from typing import Dict, Any, List, Optional

from pithon.agent.markdown_store import atomic_write as _atomic_write

logger = logging.getLogger("pithon.memory")

DEFAULT_NOTES_DIR = "data/notes"

# Starter notes written on first run only. data/ is gitignored, so anything
# authored there never travels with the repo and silently drifts from the
# shipped configuration on a fresh machine. Embedded as a Python constant
# rather than an asset directory because the Dockerfiles copy only pithon/
# and setuptools would not package a data dir -- this survives both.
# The cgroup figures below mirror docker-compose.yml; personal fields are
# left as placeholders for the operator to fill in.
SEED_NOTES: Dict[str, str] = {
    "system-specs.md": """# System Specifications

<!-- Written by Khepri on first run. Edit freely; it is your note vault. -->

- **Host Hardware**: <e.g. 4-core ARM (Cortex-A72) / 4 GB RAM>
- **Khepri Runtime**: Qwen2.5-0.5B-Instruct GGUF (`Q4_K_M` quantized)
- **Linux cgroups Isolation** (mirrors `docker-compose.yml`):
  - `pithon-daemon`: 1.0 CPU, 1408M RAM
  - `pithon-agent`: 0.5 CPU, 512M RAM
  - Combined ceiling: 1920M (under the <2GB total runtime budget)
- **Co-located Services**: <e.g. OwnTracks Recorder `:8083`, Mosquitto MQTT `:8883`>
- **Default Timezone**: <e.g. Asia/Kolkata>
"""
}

def get_notes_dir(base_dir: Optional[str] = None) -> str:
    """Ensure and return active notes directory."""
    target = base_dir or os.environ.get("NOTES_DIR", DEFAULT_NOTES_DIR)
    os.makedirs(target, exist_ok=True)
    return target


def seed_notes(base_dir: Optional[str] = None) -> List[str]:
    """Write starter notes when the notes vault is empty. Returns names written.

    Only seeds a genuinely empty vault, so deleting a starter note is respected
    and an existing installation is never modified.
    """
    target = get_notes_dir(base_dir)
    try:
        if os.listdir(target):
            return []
    except OSError:
        pass
    written: List[str] = []
    for name, body in SEED_NOTES.items():
        try:
            _atomic_write(os.path.join(target, name), body)
            written.append(name)
            logger.info("Seeded starter note: %s", os.path.join(target, name))
        except OSError as e:
            logger.warning("Could not seed %s: %s", name, e)
    return written

def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", text.lower().strip()).strip("-")
    return slug[:50] or "note"

def _safe_note_path(filename_or_title: str, base_dir: Optional[str] = None) -> Optional[str]:
    """Resolve and validate a note file path, ensuring it stays strictly inside the notes directory."""
    raw_name = os.path.basename(filename_or_title.strip())
    if raw_name.endswith(".md"):
        stem = raw_name[:-3]
        safe_stem = _slugify(os.path.basename(stem))
        fname = f"{safe_stem}.md"
    else:
        slug = _slugify(raw_name)
        fname = f"{slug}.md"

    base_path = os.path.abspath(get_notes_dir(base_dir))
    full_path = os.path.abspath(os.path.join(base_path, fname))

    # Path traversal verification: ensure full_path stays inside base_path
    try:
        if os.path.commonpath([base_path, full_path]) != base_path or not full_path.startswith(base_path + os.sep):
            return None
    except ValueError:
        return None

    return full_path

def save_note(
    title: str,
    content: str,
    tags: Optional[str] = None,
    base_dir: Optional[str] = None,
    tz_name: str = "Asia/Kolkata"
) -> Dict[str, Any]:
    """Save or append a note to a markdown file."""
    filepath = _safe_note_path(title, base_dir=base_dir)
    if not filepath:
        return {
            "success": False,
            "error": "Invalid note title",
            "title": title.strip(),
            "updated": False
        }

    slug = os.path.basename(filepath)[:-3]

    try:
        tz: Any = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    exists = os.path.exists(filepath)
    with open(filepath, "a", encoding="utf-8") as f:
        if not exists:
            tag_line = f"\n- **Tags:** `{tags}`" if tags else ""
            f.write(f"# {title.strip()}\n- **Created:** `{now_str} {tz_name}`{tag_line}\n\n{content.strip()}\n")
        else:
            f.write(f"\n\n---\n### Update: `{now_str} {tz_name}`\n{content.strip()}\n")

    logger.info(f"Saved note to {filepath}")
    return {
        "success": True,
        "title": title.strip(),
        "filename": f"{slug}.md",
        "path": filepath,
        "updated": exists
    }

def search_notes(query: str, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search for relevant markdown notes by keyword or title."""
    notes_dir = get_notes_dir(base_dir)
    q = query.lower().strip()
    results = []

    if not os.path.exists(notes_dir):
        return []

    for fname in os.listdir(notes_dir):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(notes_dir, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            if q in fname.lower() or q in content.lower():
                # Extract first title line
                title = fname[:-3]
                m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                if m:
                    title = m.group(1).strip()
                results.append({
                    "title": title,
                    "filename": fname,
                    "content": content[:500],
                    "path": filepath
                })
        except Exception as e:
            logger.warning(f"Error reading note {filepath}: {e}")

    return results

def list_notes(base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all saved markdown notes."""
    notes_dir = get_notes_dir(base_dir)
    results = []
    if not os.path.exists(notes_dir):
        return []

    for fname in sorted(os.listdir(notes_dir)):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(notes_dir, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            title = fname[:-3]
            m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if m:
                title = m.group(1).strip()
            mtime = os.path.getmtime(filepath)
            results.append({
                "title": title,
                "filename": fname,
                "mtime": mtime
            })
        except Exception:
            pass

    return results

def get_note_content(title_or_slug: str, base_dir: Optional[str] = None) -> Optional[str]:
    """Fetch exact text of a note file."""
    filepath = _safe_note_path(title_or_slug, base_dir=base_dir)
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None

def delete_note(filename_or_title: str, base_dir: Optional[str] = None) -> bool:
    """Delete a markdown note file."""
    filepath = _safe_note_path(filename_or_title, base_dir=base_dir)
    if not filepath or not os.path.exists(filepath):
        return False
    try:
        os.remove(filepath)
        logger.info(f"Deleted note {filepath}")
        return True
    except Exception as e:
        logger.warning(f"Failed to delete {filepath}: {e}")
        return False
