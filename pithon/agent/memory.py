"""Markdown-backed persistent memory engine storing personal notes and knowledge."""

import logging
import os
import re
from datetime import datetime, timezone
import zoneinfo
from typing import Dict, Any, List, Optional

logger = logging.getLogger("pithon.memory")

DEFAULT_NOTES_DIR = "data/notes"

def get_notes_dir(base_dir: Optional[str] = None) -> str:
    """Ensure and return active notes directory."""
    target = base_dir or os.environ.get("NOTES_DIR", DEFAULT_NOTES_DIR)
    os.makedirs(target, exist_ok=True)
    return target

def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", text.lower().strip()).strip("-")
    return slug[:50] or "note"

def save_note(
    title: str,
    content: str,
    tags: Optional[str] = None,
    base_dir: Optional[str] = None,
    tz_name: str = "Asia/Kolkata"
) -> Dict[str, Any]:
    """Save or append a note to a markdown file."""
    notes_dir = get_notes_dir(base_dir)
    slug = _slugify(title)
    filepath = os.path.join(notes_dir, f"{slug}.md")

    try:
        tz = zoneinfo.ZoneInfo(tz_name)
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
    notes_dir = get_notes_dir(base_dir)
    if title_or_slug.endswith(".md"):
        filepath = os.path.join(notes_dir, title_or_slug)
    else:
        slug = _slugify(title_or_slug)
        filepath = os.path.join(notes_dir, f"{slug}.md")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None

def delete_note(filename_or_title: str, base_dir: Optional[str] = None) -> bool:
    """Delete a markdown note file."""
    notes_dir = get_notes_dir(base_dir)
    if filename_or_title.endswith(".md"):
        filepath = os.path.join(notes_dir, filename_or_title)
    else:
        slug = _slugify(filename_or_title)
        filepath = os.path.join(notes_dir, f"{slug}.md")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            logger.info(f"Deleted note {filepath}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete {filepath}: {e}")
            return False
    return False
