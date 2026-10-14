"""Markdown file storage engine for user profile, tasks, and daily briefing archives."""

import logging
import os
import re
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("pithon.markdown_store")

_STORE_LOCK = threading.Lock()

DEFAULT_DATA_DIR = "data"

def get_data_dir(base_dir: Optional[str] = None) -> str:
    """Ensure and return the active data directory."""
    target = base_dir or os.environ.get("DATA_DIR", DEFAULT_DATA_DIR)
    os.makedirs(target, exist_ok=True)
    return target


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML-style frontmatter and body from Markdown text."""
    metadata: Dict[str, Any] = {}
    body = content.strip()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if v.lower() == "true":
                        metadata[k] = True
                    elif v.lower() == "false":
                        metadata[k] = False
                    elif v.isdigit():
                        metadata[k] = int(v)
                    else:
                        metadata[k] = v
    return metadata, body


def dump_frontmatter(metadata: Dict[str, Any], body: str) -> str:
    """Dump dictionary metadata and body into YAML-style Markdown format."""
    lines = ["---"]
    for k, v in metadata.items():
        if v is None:
            continue
        if isinstance(v, str) and (":" in v or " " in v or not v):
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---\n")
    if body:
        lines.append(body.strip() + "\n")
    return "\n".join(lines)


def atomic_write(filepath: str, content: str) -> None:
    """Atomically write text content to a file via a temporary file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, filepath)


class ProfileStore:
    """Manages data/profile.md storing preferences, sync settings, and user persona."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = get_data_dir(data_dir)
        self.filepath = os.path.join(self.data_dir, "profile.md")

    def load_profile(self) -> Tuple[Dict[str, Any], str]:
        """Load profile metadata and custom instructions from profile.md."""
        with _STORE_LOCK:
            if not os.path.exists(self.filepath):
                return {}, ""
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                return parse_frontmatter(content)
            except Exception as e:
                logger.error(f"Error reading {self.filepath}: {e}")
                return {}, ""

    def save_profile(self, metadata: Dict[str, Any], body: Optional[str] = None) -> None:
        """Update profile.md frontmatter and optional persona body."""
        with _STORE_LOCK:
            existing_meta, existing_body = {}, ""
            if os.path.exists(self.filepath):
                try:
                    with open(self.filepath, "r", encoding="utf-8") as f:
                        existing_meta, existing_body = parse_frontmatter(f.read())
                except Exception:
                    pass

            merged_meta = dict(existing_meta)
            for k, v in metadata.items():
                if v is not None:
                    merged_meta[k] = v

            final_body = body if body is not None else existing_body
            if not final_body:
                final_body = (
                    "# User Persona & Custom Instructions\n"
                    "- Prefers concise, direct responses with technical precision.\n"
                    "- Focus: Python, Linux systems, architecture, and automation."
                )

            rendered = dump_frontmatter(merged_meta, final_body)
            atomic_write(self.filepath, rendered)
            logger.info(f"Updated user profile in {self.filepath}")


class TasksStore:
    """Manages data/tasks.md storing active and completed tasks in Markdown checklist format."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = get_data_dir(data_dir)
        self.filepath = os.path.join(self.data_dir, "tasks.md")

    def load_tasks(self) -> List[Dict[str, Any]]:
        """Parse tasks from tasks.md."""
        with _STORE_LOCK:
            if not os.path.exists(self.filepath):
                return []
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Error reading {self.filepath}: {e}")
                return []

        tasks = []
        for line in content.splitlines():
            line = line.strip()
            m = re.match(r"^-\s*\[([ xX])\]\s*(.+)$", line)
            if m:
                is_completed = 1 if m.group(1).lower() == "x" else 0
                rest = m.group(2).strip()

                id_val = None
                id_m = re.search(r"#id:(\d+)", rest)
                if id_m:
                    id_val = int(id_m.group(1))
                    rest = re.sub(r"#id:\d+", "", rest)

                list_val = "default"
                list_m = re.search(r"#list:([a-zA-Z0-9_\-]+)", rest)
                if list_m:
                    list_val = list_m.group(1)
                    rest = re.sub(r"#list:[a-zA-Z0-9_\-]+", "", rest)

                due_val = None
                due_m = re.search(r"#due:([^\s]+)", rest)
                if due_m:
                    due_val = due_m.group(1)
                    rest = re.sub(r"#due:[^\s]+", "", rest)

                title = rest.strip()
                tasks.append({
                    "id": id_val,
                    "title": title,
                    "is_completed": is_completed,
                    "list_name": list_val,
                    "due_at": due_val
                })
        return tasks

    def sync_from_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        """Write task list into tasks.md with checklist syntax."""
        with _STORE_LOCK:
            lines = [
                "# Tasks & Checklist\n",
                "## Pending"
            ]
            pending = [t for t in tasks if not t.get("is_completed")]
            completed = [t for t in tasks if t.get("is_completed")]

            for t in pending:
                tags = []
                if t.get("id"):
                    tags.append(f"#id:{t['id']}")
                if t.get("list_name") and t["list_name"] != "default":
                    tags.append(f"#list:{t['list_name']}")
                if t.get("due_at"):
                    tags.append(f"#due:{t['due_at']}")
                tag_str = (" " + " ".join(tags)) if tags else ""
                lines.append(f"- [ ] {t.get('title', '').strip()}{tag_str}")

            lines.append("\n## Completed")
            for t in completed:
                tags = []
                if t.get("id"):
                    tags.append(f"#id:{t['id']}")
                if t.get("list_name") and t["list_name"] != "default":
                    tags.append(f"#list:{t['list_name']}")
                if t.get("due_at"):
                    tags.append(f"#due:{t['due_at']}")
                tag_str = (" " + " ".join(tags)) if tags else ""
                lines.append(f"- [x] {t.get('title', '').strip()}{tag_str}")

            rendered = "\n".join(lines) + "\n"
            atomic_write(self.filepath, rendered)
            logger.info(f"Synchronized {len(tasks)} tasks to {self.filepath}")


class BriefingStore:
    """Archives daily morning briefings to data/briefings/YYYY-MM-DD.md."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = get_data_dir(data_dir)
        self.briefings_dir = os.path.join(self.data_dir, "briefings")
        os.makedirs(self.briefings_dir, exist_ok=True)

    def save_briefing(self, briefing_text: str, date_str: Optional[str] = None) -> str:
        """Save briefing text to dated markdown file."""
        today_date = date_str or datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join(self.briefings_dir, f"{today_date}.md")
        with _STORE_LOCK:
            atomic_write(filepath, briefing_text.strip() + "\n")
            logger.info(f"Saved daily briefing to {filepath}")
        return filepath
