"""SQLite storage engine for audit logs, tasks, reminders, digests, and web sessions."""

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

class Storage:
    """Thread-safe SQLite storage with WAL mode."""

    def __init__(self, db_path: str = "data/pithon.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                user_id TEXT,
                prompt TEXT NOT NULL,
                search_query TEXT,
                search_results TEXT,
                response TEXT NOT NULL,
                latency_ms INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_interactions_chat ON interactions(chat_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_created ON interactions(created_at);

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                title TEXT NOT NULL,
                list_name TEXT DEFAULT 'default',
                due_at TIMESTAMP NULL,
                is_completed BOOLEAN DEFAULT 0,
                reminded BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_at, is_completed, reminded);

            CREATE TABLE IF NOT EXISTS digests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_chat_id TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                period_start TIMESTAMP NOT NULL,
                period_end TIMESTAMP NOT NULL,
                interaction_count INTEGER DEFAULT 0,
                sent_silent BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );
            """)

    def get_table_names(self) -> List[str]:
        """Return list of existing tables."""
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
            return [r["name"] for r in rows]

    def log_interaction(
        self,
        chat_id: str,
        user_id: Optional[str] = None,
        prompt: str = '',
        search_query: Optional[str] = None,
        search_results: Optional[List[Dict[str, Any]]] = None,
        response: str = '',
        latency_ms: int = 0
    ) -> int:
        """Log a user-model interaction."""
        sr_json = json.dumps(search_results) if search_results else ""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO interactions (chat_id, user_id, prompt, search_query, search_results, response, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chat_id, user_id or "", prompt, search_query or "", sr_json, response, latency_ms)
            )
            return cursor.lastrowid

    def get_interactions(
        self,
        limit: int = 50,
        offset: int = 0,
        search_term: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve recent interactions with optional text search."""
        with self._lock, self._get_connection() as conn:
            if search_term:
                query = """
                SELECT * FROM interactions
                WHERE prompt LIKE ? OR response LIKE ? OR search_query LIKE ?
                ORDER BY id DESC LIMIT ? OFFSET ?
                """
                term = f"%{search_term}%"
                rows = conn.execute(query, (term, term, term, limit, offset)).fetchall()
            else:
                query = "SELECT * FROM interactions ORDER BY id DESC LIMIT ? OFFSET ?"
                rows = conn.execute(query, (limit, offset)).fetchall()

            res = []
            for r in rows:
                item = dict(r)
                if item.get("search_results"):
                    try:
                        item["search_results"] = json.loads(item["search_results"])
                    except Exception:
                        item["search_results"] = []
                else:
                    item["search_results"] = []
                res.append(item)
            return res

    def get_recent_history(
        self,
        limit: int = 6,
        chat_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Retrieve recent interaction turns in chronological order for conversational multi-turn context."""
        with self._lock, self._get_connection() as conn:
            if chat_id:
                query = """
                SELECT prompt, response FROM interactions
                WHERE (chat_id = ? OR chat_id = 'web' OR user_id = 'web')
                  AND prompt != '' AND response != ''
                ORDER BY id DESC LIMIT ?
                """
                rows = conn.execute(query, (str(chat_id), limit)).fetchall()
            else:
                query = """
                SELECT prompt, response FROM interactions
                WHERE prompt != '' AND response != ''
                ORDER BY id DESC LIMIT ?
                """
                rows = conn.execute(query, (limit,)).fetchall()

            history = []
            for r in reversed(rows):
                history.append({"role": "user", "content": r["prompt"]})
                history.append({"role": "assistant", "content": r["response"]})
            return history

    def get_chat_stream(
        self,
        limit: int = 40,
        since_id: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve interactions stream for live chat synchronization between Telegram and Web."""
        with self._lock, self._get_connection() as conn:
            if since_id > 0:
                query = """
                SELECT id, chat_id, user_id, prompt, response, search_query, latency_ms, created_at
                FROM interactions
                WHERE id > ? AND prompt != '' AND response != ''
                ORDER BY id ASC LIMIT ?
                """
                rows = conn.execute(query, (since_id, limit)).fetchall()
            else:
                query = """
                SELECT id, chat_id, user_id, prompt, response, search_query, latency_ms, created_at
                FROM interactions
                WHERE prompt != '' AND response != ''
                ORDER BY id DESC LIMIT ?
                """
                rows = conn.execute(query, (limit,)).fetchall()
                rows = list(reversed(rows))

            res = []
            for r in rows:
                item = dict(r)
                item["source"] = "web" if item.get("user_id") == "web" or item.get("chat_id") == "web" else "telegram"
                res.append(item)
            return res

    def create_task(
        self,
        chat_id: str,
        title: str,
        list_name: str = "default",
        due_at: Optional[str] = None
    ) -> int:
        """Create a new task or list item."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks (chat_id, title, list_name, due_at, is_completed, reminded)
                VALUES (?, ?, ?, ?, 0, 0)
                """,
                (chat_id, title.strip(), (list_name or "default").lower().strip(), due_at)
            )
            return cursor.lastrowid

    def get_tasks(
        self,
        chat_id: Optional[str] = None,
        list_name: Optional[str] = None,
        include_completed: bool = False
    ) -> List[Dict[str, Any]]:
        """Retrieve active (or all) tasks for a chat/user."""
        with self._lock, self._get_connection() as conn:
            conditions: List[str] = []
            params: List[Any] = []
            if chat_id:
                conditions.append("chat_id = ?")
                params.append(str(chat_id).strip())

            if not include_completed:
                conditions.append("is_completed = 0")
            if list_name:
                conditions.append("list_name = ?")
                params.append(list_name.lower().strip())

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT * FROM tasks {where_clause} ORDER BY due_at ASC, id DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve single task by ID."""
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None

    def toggle_task(self, task_id: int) -> Optional[bool]:
        """Toggle task completion state (returns new is_completed boolean)."""
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT is_completed FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return None
            new_state = 0 if row["is_completed"] else 1
            conn.execute("UPDATE tasks SET is_completed = ? WHERE id = ?", (new_state, task_id))
            return bool(new_state)

    def complete_task(self, task_id: int) -> bool:
        """Mark task as completed."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("UPDATE tasks SET is_completed = 1 WHERE id = ?", (task_id,))
            return cursor.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        """Delete task permanently."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return cursor.rowcount > 0

    def snooze_task(self, task_id: int, hours: int = 1) -> bool:
        """Snooze a task by adding hours to current time."""
        now = datetime.now(timezone.utc)
        new_due = (now + timedelta(hours=hours)).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET due_at = ?, reminded = 0 WHERE id = ?",
                (new_due, task_id)
            )
            return cursor.rowcount > 0

    def get_pending_reminders(self, current_iso: str) -> List[Dict[str, Any]]:
        """Retrieve uncompleted tasks that are due and haven't triggered reminders yet."""
        with self._lock, self._get_connection() as conn:
            query = """
            SELECT * FROM tasks
            WHERE is_completed = 0 AND reminded = 0 AND due_at IS NOT NULL AND due_at <= ?
            ORDER BY due_at ASC
            """
            rows = conn.execute(query, (current_iso,)).fetchall()
            return [dict(r) for r in rows]

    def mark_reminded(self, task_id: int) -> None:
        """Mark reminder as sent."""
        with self._lock, self._get_connection() as conn:
            conn.execute("UPDATE tasks SET reminded = 1 WHERE id = ?", (task_id,))

    def log_digest(
        self,
        target_chat_id: str,
        summary_text: str,
        period_start: str,
        period_end: str,
        interaction_count: int = 0,
        sent_silent: bool = True
    ) -> int:
        """Log an hourly digest report."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO digests (target_chat_id, summary_text, period_start, period_end, interaction_count, sent_silent)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (target_chat_id, summary_text, period_start, period_end, interaction_count, 1 if sent_silent else 0)
            )
            return cursor.lastrowid

    def get_digests(self, limit: int = 24) -> List[Dict[str, Any]]:
        """Retrieve recent digests."""
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM digests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def create_session(self, token: str, expires_in_sec: int = 604800) -> None:
        """Create a web session with expiration."""
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in_sec)).isoformat()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (token, expires_at) VALUES (?, ?)",
                (token, expires_at)
            )

    def validate_session(self, token: str) -> bool:
        """Validate whether a session token is active and unexpired."""
        if not token:
            return False
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token = ? AND expires_at > ?",
                (token, now_iso)
            ).fetchone()
            return row is not None

    def delete_session(self, token: str) -> None:
        """Remove a session token (logout)."""
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
