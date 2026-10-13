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

            CREATE TABLE IF NOT EXISTS context_resets (
                chat_id TEXT PRIMARY KEY,
                cleared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_profiles (
                chat_id TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                city TEXT DEFAULT '',
                digest_pref TEXT DEFAULT '',
                focus TEXT DEFAULT '',
                step TEXT NULL,
                calendar_url TEXT DEFAULT '',
                calendar_alert_mins INTEGER DEFAULT 10,
                calendar_feed_md5 TEXT DEFAULT '',
                calendar_synced_at TIMESTAMP NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS calendar_events (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                parent_uid TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                location TEXT DEFAULT '',
                meeting_link TEXT DEFAULT '',
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                is_recurring INTEGER DEFAULT 0,
                event_md5 TEXT NOT NULL,
                reminded_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_calendar_events_user_start ON calendar_events(chat_id, start_time);
            CREATE INDEX IF NOT EXISTS idx_calendar_events_remind ON calendar_events(reminded_at, start_time);
            """)

            # Ensure calendar migration columns exist in existing user_profiles tables
            cols = [col["name"] for col in conn.execute("PRAGMA table_info(user_profiles);").fetchall()]
            if "calendar_url" not in cols:
                conn.execute("ALTER TABLE user_profiles ADD COLUMN calendar_url TEXT DEFAULT '';")
            if "calendar_alert_mins" not in cols:
                conn.execute("ALTER TABLE user_profiles ADD COLUMN calendar_alert_mins INTEGER DEFAULT 10;")
            if "calendar_feed_md5" not in cols:
                conn.execute("ALTER TABLE user_profiles ADD COLUMN calendar_feed_md5 TEXT DEFAULT '';")
            if "calendar_synced_at" not in cols:
                conn.execute("ALTER TABLE user_profiles ADD COLUMN calendar_synced_at TIMESTAMP NULL;")

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

    def clear_context(self, chat_id: Optional[str] = None) -> None:
        """Clear conversational context memory for a chat/user while preserving audit logs."""
        target = str(chat_id or "web")
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO context_resets (chat_id, cleared_at)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET cleared_at = CURRENT_TIMESTAMP
                """,
                (target,)
            )
            conn.execute(
                """
                INSERT INTO context_resets (chat_id, cleared_at)
                VALUES ('web', CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET cleared_at = CURRENT_TIMESTAMP
                """
            )
            conn.commit()

    def get_recent_history(
        self,
        limit: int = 3,
        chat_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Retrieve recent interaction turns in chronological order for conversational multi-turn context."""
        with self._lock, self._get_connection() as conn:
            cleared_at = None
            if chat_id:
                reset_row = conn.execute(
                    "SELECT cleared_at FROM context_resets WHERE chat_id = ? OR chat_id = 'web' ORDER BY cleared_at DESC LIMIT 1",
                    (str(chat_id),)
                ).fetchone()
                if reset_row:
                    cleared_at = reset_row["cleared_at"]

            if chat_id:
                if cleared_at:
                    query = """
                    SELECT prompt, response FROM interactions
                    WHERE (chat_id = ? OR chat_id = 'web' OR user_id = 'web')
                      AND created_at > ?
                      AND prompt != '' AND response != ''
                      AND response NOT LIKE '%⚠️%' AND response NOT LIKE '%timed out%'
                    ORDER BY id DESC LIMIT ?
                    """
                    rows = conn.execute(query, (str(chat_id), cleared_at, limit)).fetchall()
                else:
                    query = """
                    SELECT prompt, response FROM interactions
                    WHERE (chat_id = ? OR chat_id = 'web' OR user_id = 'web')
                      AND prompt != '' AND response != ''
                      AND response NOT LIKE '%⚠️%' AND response NOT LIKE '%timed out%'
                    ORDER BY id DESC LIMIT ?
                    """
                    rows = conn.execute(query, (str(chat_id), limit)).fetchall()
            else:
                query = """
                SELECT prompt, response FROM interactions
                WHERE prompt != '' AND response != ''
                  AND response NOT LIKE '%⚠️%' AND response NOT LIKE '%timed out%'
                ORDER BY id DESC LIMIT ?
                """
                rows = conn.execute(query, (limit,)).fetchall()

            history = []
            for r in reversed(rows):
                p_text = r["prompt"][:250].strip()
                r_text = r["response"][:300].strip()
                history.append({"role": "user", "content": p_text})
                history.append({"role": "assistant", "content": r_text})
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

    def get_user_profile(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user profile by chat_id (falls back to 'web' if not found)."""
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE chat_id = ? LIMIT 1",
                (str(chat_id),)
            ).fetchone()
            if not row and str(chat_id) != "web":
                row = conn.execute(
                    "SELECT * FROM user_profiles WHERE chat_id = 'web' LIMIT 1"
                ).fetchone()
            return dict(row) if row else None

    def save_user_profile(
        self,
        chat_id: str,
        name: str = "",
        city: str = "",
        digest_pref: str = "",
        focus: str = "",
        step: Optional[str] = None
    ) -> Dict[str, Any]:
        """Save or update user profile fields."""
        target = str(chat_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock, self._get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM user_profiles WHERE chat_id = ? LIMIT 1",
                (target,)
            ).fetchone()

            if existing:
                new_name = name if name != "" else existing["name"]
                new_city = city if city != "" else existing["city"]
                new_digest = digest_pref if digest_pref != "" else existing["digest_pref"]
                new_focus = focus if focus != "" else existing["focus"]
                new_step = step if step is not None else existing["step"]

                conn.execute(
                    """
                    UPDATE user_profiles
                    SET name = ?, city = ?, digest_pref = ?, focus = ?, step = ?, updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (new_name, new_city, new_digest, new_focus, new_step, now_iso, target)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO user_profiles (chat_id, name, city, digest_pref, focus, step, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (target, name, city, digest_pref, focus, step, now_iso)
                )

            # Mirror to 'web' for unified admin experience
            if target != "web":
                cur_name = name or (existing["name"] if existing else "")
                cur_city = city or (existing["city"] if existing else "")
                cur_digest = digest_pref or (existing["digest_pref"] if existing else "")
                cur_focus = focus or (existing["focus"] if existing else "")
                conn.execute(
                    """
                    INSERT INTO user_profiles (chat_id, name, city, digest_pref, focus, step, updated_at)
                    VALUES ('web', ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET
                      name = excluded.name,
                      city = excluded.city,
                      digest_pref = excluded.digest_pref,
                      focus = excluded.focus,
                      step = excluded.step,
                      updated_at = excluded.updated_at
                    """,
                    (cur_name, cur_city, cur_digest, cur_focus, step, now_iso)
                )

            conn.commit()
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE chat_id = ? LIMIT 1",
                (target,)
            ).fetchone()
            return dict(row)

    def set_onboarding_step(self, chat_id: str, step: Optional[str]) -> None:
        """Set or clear the current active onboarding step for a chat."""
        target = str(chat_id)
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (chat_id, step) VALUES (?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET step = excluded.step
                """,
                (target, step)
            )
            if target != "web":
                conn.execute(
                    """
                    INSERT INTO user_profiles (chat_id, step) VALUES ('web', ?)
                    ON CONFLICT(chat_id) DO UPDATE SET step = excluded.step
                    """,
                    (step,)
                )
            conn.commit()

    def clear_onboarding(self, chat_id: str) -> None:
        """Clear active onboarding step."""
        self.set_onboarding_step(chat_id, None)

    @staticmethod
    def _normalize_iso_utc(ts: Any) -> str:
        """Normalize string or datetime timestamp to UTC ISO 8601 string for consistent SQLite indexing."""
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                return ts
        elif isinstance(ts, datetime):
            dt = ts
        else:
            return str(ts)
        
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).isoformat()
        return dt.replace(tzinfo=timezone.utc).isoformat()

    def save_calendar_events(self, chat_id: str, events: List[Dict[str, Any]]) -> int:
        """Save or update calendar events.
        
        Skips updating rows where event_md5 has not changed.
        Preserves existing reminded_at state across event updates.
        Returns count of inserted or updated rows.
        """
        target = str(chat_id)
        updated_count = 0
        with self._lock, self._get_connection() as conn:
            for ev in events:
                ev_id = str(ev["id"])
                ev_md5 = str(ev.get("event_md5", ""))
                row = conn.execute(
                    "SELECT id, event_md5, reminded_at FROM calendar_events WHERE id = ?",
                    (ev_id,)
                ).fetchone()

                start_iso = self._normalize_iso_utc(ev["start_time"])
                end_iso = self._normalize_iso_utc(ev["end_time"])
                link = ev.get("meeting_link") or ""

                if row:
                    if row["event_md5"] == ev_md5:
                        # Unchanged: skip DB write
                        continue
                    conn.execute(
                        """
                        UPDATE calendar_events
                        SET chat_id = ?, parent_uid = ?, title = ?, description = ?, location = ?,
                            meeting_link = ?, start_time = ?, end_time = ?, is_recurring = ?,
                            event_md5 = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            target,
                            ev.get("parent_uid", ev_id),
                            ev.get("title", "Untitled"),
                            ev.get("description", ""),
                            ev.get("location", ""),
                            link,
                            start_iso,
                            end_iso,
                            int(ev.get("is_recurring", 0)),
                            ev_md5,
                            ev_id
                        )
                    )
                    updated_count += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO calendar_events (
                            id, chat_id, parent_uid, title, description, location,
                            meeting_link, start_time, end_time, is_recurring, event_md5
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ev_id,
                            target,
                            ev.get("parent_uid", ev_id),
                            ev.get("title", "Untitled"),
                            ev.get("description", ""),
                            ev.get("location", ""),
                            link,
                            start_iso,
                            end_iso,
                            int(ev.get("is_recurring", 0)),
                            ev_md5
                        )
                    )
                    updated_count += 1

            conn.commit()
            return updated_count

    def get_upcoming_events(
        self,
        chat_id: str,
        limit: int = 5,
        start_after: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve upcoming events for chat_id starting after start_after timestamp."""
        target = str(chat_id)
        if not start_after:
            start_after_iso = datetime.now(timezone.utc).isoformat()
        else:
            start_after_iso = self._normalize_iso_utc(start_after)

        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM calendar_events
                WHERE (chat_id = ? OR chat_id = 'web' OR ? = 'web')
                  AND start_time >= ?
                ORDER BY start_time ASC
                LIMIT ?
                """,
                (target, target, start_after_iso, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_unreminded_events_in_range(
        self,
        chat_id: str,
        start_iso: str,
        end_iso: str
    ) -> List[Dict[str, Any]]:
        """Retrieve events in [start_iso, end_iso] that have not yet had reminders sent."""
        target = str(chat_id)
        start_norm = self._normalize_iso_utc(start_iso)
        end_norm = self._normalize_iso_utc(end_iso)

        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM calendar_events
                WHERE (chat_id = ? OR chat_id = 'web')
                  AND reminded_at IS NULL
                  AND start_time >= ?
                  AND start_time <= ?
                ORDER BY start_time ASC
                """,
                (target, start_norm, end_norm)
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_event_reminded(self, event_id: str) -> None:
        """Mark an event occurrence as reminded."""
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                UPDATE calendar_events
                SET reminded_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (event_id,)
            )
            conn.commit()

    def update_calendar_settings(
        self,
        chat_id: str,
        url: Optional[str] = None,
        alert_mins: Optional[int] = None,
        feed_md5: Optional[str] = None
    ) -> None:
        """Update calendar ICS URL, alert lead time, or feed MD5 in user profile."""
        target = str(chat_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock, self._get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO user_profiles (chat_id) VALUES (?)", (target,))
            fields = []
            vals = []
            if url is not None:
                fields.append("calendar_url = ?")
                vals.append(url)
            if alert_mins is not None:
                fields.append("calendar_alert_mins = ?")
                vals.append(alert_mins)
            if feed_md5 is not None:
                fields.append("calendar_feed_md5 = ?")
                vals.append(feed_md5)
                fields.append("calendar_synced_at = ?")
                vals.append(now_iso)

            if fields:
                fields.append("updated_at = ?")
                vals.append(now_iso)
                query = f"UPDATE user_profiles SET {', '.join(fields)} WHERE chat_id = ?"
                conn.execute(query, (*vals, target))
                if target != "web":
                    conn.execute(query, (*vals, "web"))
            conn.commit()

    def prune_old_calendar_events(self, days: int = 7) -> int:
        """Delete events whose end_time is older than days ago to preserve DB hygiene."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM calendar_events WHERE end_time < ?",
                (cutoff,)
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted
