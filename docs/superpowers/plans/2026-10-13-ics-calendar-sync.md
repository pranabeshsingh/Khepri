# 5-Minute ICS Calendar Sync & Meeting Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Khepri to an open `.ics` URL synced every 5 minutes with MD5 change detection, parse standard and recurring (`RRULE`) calls, extract video links (Google Meet, Zoom, Teams), and proactively alert the user before calls start via Telegram, morning briefing, slash commands, and Qwen2.5 tool calling.

**Architecture:** A zero-dependency RFC 5545 parser in `pithon/agent/calendar.py` extracts events and expands recurring instances for an active sliding window `[now - 1d, now + 14d]`. Feeds and events use MD5 hashing to avoid redundant parsing and database writes. A SQLite `calendar_events` table stores occurrences with individual reminder tracking. `pithon/agent/scheduler.py` executes a 5-minute sync tick and a 1-minute alert tick with inline video call join buttons.

**Tech Stack:** Python 3.12 (standard library: `urllib.request`, `datetime`, `zoneinfo`, `re`, `hashlib`), SQLite3, Telegram Bot API, pytest. Zero new pip dependencies.

## Global Constraints

- **Python Standard Library Only:** No external icalendar pip packages.
- **MD5 Caching:** Skip full parsing if `feed_md5` is unchanged; skip SQLite updates if `event_md5` is unchanged.
- **Composite Occurrence ID:** Use `{parent_uid}#{start_iso}` so occurrences of recurring calls have independent `reminded_at` states.
- **Telegram Formatting:** Sanitize markdown for Telegram legacy parser; send alerts with `disable_web_page_preview=True`.
- **Server Deployment Invariant:** The only difference between VPS and Git repo must remain the local model override in `.git/info/exclude`.

---

### Task 1: Zero-Dependency RFC 5545 Parser & Video Link Detector

**Files:**
- Create: `pithon/agent/calendar.py`
- Test: `tests/test_calendar.py`

**Interfaces:**
- Produces: `parse_ics_feed(ics_content: str, default_tz: str = "Asia/Kolkata") -> List[Dict[str, Any]]`
- Produces: `extract_video_meeting_link(text: str) -> Optional[str]`
- Produces: `compute_md5(data: Union[str, bytes]) -> str`

- [ ] **Step 1: Write the failing tests for basic RFC 5545 parsing and link detection**

```python
# tests/test_calendar.py
from datetime import datetime
import zoneinfo
from pithon.agent.calendar import parse_ics_feed, extract_video_meeting_link, compute_md5

def test_extract_video_meeting_link():
    assert extract_video_meeting_link("Join via https://meet.google.com/abc-defg-hij") == "https://meet.google.com/abc-defg-hij"
    assert extract_video_meeting_link("Zoom link: https://us02web.zoom.us/j/123456789?pwd=xyz") == "https://us02web.zoom.us/j/123456789?pwd=xyz"
    assert extract_video_meeting_link("Teams: https://teams.microsoft.com/l/meetup-join/19%3ameeting") == "https://teams.microsoft.com/l/meetup-join/19%3ameeting"
    assert extract_video_meeting_link("Conference Room B (No link)") is None

def test_parse_single_event_ics():
    raw_ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:meeting-001@example.com\r\n"
        "SUMMARY:Architecture Sync [Core]\r\n"
        "DESCRIPTION:Discussion on cgroups.\\nJoin: https://meet.google.com/abc-defg-hij\r\n"
        "LOCATION:Google Meet\r\n"
        "DTSTART:20261013T090000Z\r\n"
        "DTEND:20261013T093000Z\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    events = parse_ics_feed(raw_ics, default_tz="Asia/Kolkata")
    assert len(events) == 1
    ev = events[0]
    assert ev["uid"] == "meeting-001@example.com"
    assert ev["title"] == "Architecture Sync (Core)"
    assert ev["meeting_link"] == "https://meet.google.com/abc-defg-hij"
    assert ev["start_time"].tzinfo is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_calendar.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'pithon.agent.calendar')

- [ ] **Step 3: Implement RFC 5545 parser and video link extraction**

Implement in `pithon/agent/calendar.py`:
- `compute_md5(data: Union[str, bytes]) -> str`
- `extract_video_meeting_link(text: str) -> Optional[str]`
- `unfold_ics_lines(raw_text: str) -> List[str]`
- Parse properties: `UID`, `SUMMARY`, `DESCRIPTION`, `LOCATION`, `DTSTART`, `DTEND`.
- Sanitize titles: convert `[` and `]` to `(` and `)`.
- Parse UTC timestamps (`...Z`) and local timestamps with `zoneinfo`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_calendar.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/pranabesh/code/Pithon add pithon/agent/calendar.py tests/test_calendar.py
git -C /Users/pranabesh/code/Pithon commit -m "feat(calendar): implement RFC 5545 parser and video call detector"
```

---

### Task 2: RRULE Recurrence Expansion Engine & MD5 Change Detection

**Files:**
- Modify: `pithon/agent/calendar.py`
- Modify: `tests/test_calendar.py`

**Interfaces:**
- Consumes: `parse_ics_feed` from Task 1
- Produces: `expand_recurring_events(events: List[Dict[str, Any]], start_window: datetime, end_window: datetime, tz_name: str) -> List[Dict[str, Any]]`
- Produces: `fetch_and_parse_calendar(url: str, current_feed_md5: str, tz_name: str) -> Tuple[bool, str, List[Dict[str, Any]]]`

- [ ] **Step 1: Write failing tests for RRULE expansion (daily, weekly, exclusions)**

```python
# Add to tests/test_calendar.py
def test_rrule_weekly_expansion():
    raw_ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:daily-standup@company.com\r\n"
        "SUMMARY:Daily Standup\r\n"
        "DTSTART;TZID=Asia/Kolkata:20261012T100000\r\n"
        "DTEND;TZID=Asia/Kolkata:20261012T103000\r\n"
        "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=20261030T235959Z\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    # Expand across 7 days
    start_w = datetime(2026, 10, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata"))
    end_w = datetime(2026, 10, 19, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata"))
    events = parse_ics_feed(raw_ics, default_tz="Asia/Kolkata", expand_window=(start_w, end_w))
    # Monday to Friday = 5 occurrences
    assert len(events) == 5
    # Unique composite ID per occurrence
    uids = [e["id"] for e in events]
    assert len(set(uids)) == 5
    assert uids[0].startswith("daily-standup@company.com#")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_calendar.py::test_rrule_weekly_expansion -v`
Expected: FAIL

- [ ] **Step 3: Implement recurrence engine and feed MD5 check**

Implement in `pithon/agent/calendar.py`:
- Parse `RRULE` components (`FREQ`, `INTERVAL`, `BYDAY`, `UNTIL`, `COUNT`, `EXDATE`).
- Expand occurrences that fall within `[start_window, end_window]`.
- Attach composite `id = f"{parent_uid}#{occ_start.isoformat()}"`.
- Implement `fetch_and_parse_calendar(url, current_feed_md5, tz_name)`:
  - Converts `webcal://` -> `https://`.
  - Downloads with User-Agent header and 5.0s timeout.
  - Computes `feed_md5`. If matches `current_feed_md5`, returns `(False, feed_md5, [])`.
  - If changed, computes `event_md5` for each VEVENT block and returns `(True, feed_md5, expanded_events)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_calendar.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/pranabesh/code/Pithon add pithon/agent/calendar.py tests/test_calendar.py
git -C /Users/pranabesh/code/Pithon commit -m "feat(calendar): implement RRULE recurrence expansion and feed MD5 caching"
```

---

### Task 3: SQLite Calendar Schema & Storage Layer

**Files:**
- Modify: `pithon/agent/storage.py`
- Modify: `tests/test_agent_storage.py`

**Interfaces:**
- Produces: `Storage.save_calendar_events(chat_id: str, events: List[Dict[str, Any]]) -> int`
- Produces: `Storage.get_upcoming_events(chat_id: str, limit: int = 5, start_after: Optional[str] = None) -> List[Dict[str, Any]]`
- Produces: `Storage.get_unreminded_events_in_range(chat_id: str, start_iso: str, end_iso: str) -> List[Dict[str, Any]]`
- Produces: `Storage.mark_event_reminded(event_id: str) -> None`
- Produces: `Storage.update_calendar_settings(chat_id: str, url: Optional[str], alert_mins: Optional[int], feed_md5: Optional[str]) -> None`
- Produces: `Storage.prune_old_calendar_events(days: int = 7) -> int`

- [ ] **Step 1: Write failing storage tests for calendar events and MD5 upsert**

```python
# In tests/test_agent_storage.py
def test_calendar_events_storage(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    events = [
        {
            "id": "call-1#2026-10-13T10:00:00",
            "parent_uid": "call-1",
            "title": "Design Review",
            "description": "Review specs",
            "location": "Meet",
            "meeting_link": "https://meet.google.com/abc",
            "start_time": "2026-10-13T10:00:00+05:30",
            "end_time": "2026-10-13T10:30:00+05:30",
            "is_recurring": 0,
            "event_md5": "md5_hash_1"
        }
    ]
    upserted = s.save_calendar_events("123", events)
    assert upserted == 1

    # Second call with same event_md5 should not touch rows
    upserted_again = s.save_calendar_events("123", events)
    assert upserted_again == 0

    upcoming = s.get_upcoming_events("123", limit=5)
    assert len(upcoming) == 1
    assert upcoming[0]["meeting_link"] == "https://meet.google.com/abc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_agent_storage.py -k test_calendar_events_storage -v`
Expected: FAIL (AttributeError: 'Storage' object has no attribute 'save_calendar_events')

- [ ] **Step 3: Implement database migrations and calendar storage methods**

In `pithon/agent/storage.py`:
- In `_init_db()`:
  - Add `ALTER TABLE user_profiles ADD COLUMN calendar_url TEXT DEFAULT ''` (handled safely if column exists).
  - Add `ALTER TABLE user_profiles ADD COLUMN calendar_alert_mins INTEGER DEFAULT 10`.
  - Add `ALTER TABLE user_profiles ADD COLUMN calendar_feed_md5 TEXT DEFAULT ''`.
  - Add `ALTER TABLE user_profiles ADD COLUMN calendar_synced_at TIMESTAMP`.
  - Create table `calendar_events` with indices on `(chat_id, start_time)` and `(reminded_at, start_time)`.
- Implement `save_calendar_events`, `get_upcoming_events`, `get_unreminded_events_in_range`, `mark_event_reminded`, `update_calendar_settings`, and `prune_old_calendar_events`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_agent_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/pranabesh/code/Pithon add pithon/agent/storage.py tests/test_agent_storage.py
git -C /Users/pranabesh/code/Pithon commit -m "feat(storage): add calendar_events table, settings schema, and event queries"
```

---

### Task 4: Scheduler 5-Min Sync Tick & 1-Min Proactive Alerts

**Files:**
- Modify: `pithon/agent/scheduler.py`
- Modify: `tests/test_agent_scheduler.py`

**Interfaces:**
- Consumes: `pithon/agent/calendar.py` and `Storage` calendar methods
- Produces: `Scheduler.calendar_sync_tick(force: bool = False) -> int`
- Produces: `Scheduler.calendar_alerts_tick() -> int`

- [ ] **Step 1: Write failing tests for calendar sync tick and alert tick**

```python
# In tests/test_agent_scheduler.py
def test_calendar_alerts_tick(tmp_path):
    mock_bot = MagicMock()
    s = Storage(str(tmp_path / "test.db"))
    s.save_user_profile("admin_1", name="Pranabesh")
    s.update_calendar_settings("admin_1", url="https://example.com/cal.ics", alert_mins=10, feed_md5="")

    # Add meeting 5 minutes from now
    now = datetime.now(timezone.utc)
    start = (now + timedelta(minutes=5)).isoformat()
    end = (now + timedelta(minutes=35)).isoformat()
    s.save_calendar_events("admin_1", [{
        "id": "event-1",
        "parent_uid": "event-1",
        "title": "Live Call",
        "description": "Join https://meet.google.com/xyz",
        "location": "Google Meet",
        "meeting_link": "https://meet.google.com/xyz",
        "start_time": start,
        "end_time": end,
        "is_recurring": 0,
        "event_md5": "md5-1"
    }])

    scheduler = Scheduler(mock_bot, s, admin_chat_id="admin_1")
    dispatched = scheduler.calendar_alerts_tick()
    assert dispatched == 1
    mock_bot.send_message.assert_called_once()
    assert "Live Call" in mock_bot.send_message.call_args[0][1]

    # Second tick: should not dispatch again
    dispatched_again = scheduler.calendar_alerts_tick()
    assert dispatched_again == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_agent_scheduler.py -k test_calendar_alerts_tick -v`
Expected: FAIL (AttributeError: 'Scheduler' object has no attribute 'calendar_alerts_tick')

- [ ] **Step 3: Implement `calendar_sync_tick` and `calendar_alerts_tick` in Scheduler**

In `pithon/agent/scheduler.py`:
- Add `calendar_sync_tick(force=False)`:
  - Fetches ICS URL, compares `feed_md5`, upserts changed events, prunes >7d old events.
- Add `calendar_alerts_tick()`:
  - Finds unreminded events starting between `now` and `now + alert_mins`.
  - Formats notification with `🔔 Upcoming Call in X mins!`, title, formatted times, location.
  - Adds inline keyboard: `[📞 Join Meeting]` (URL button if meeting_link) and `[✅ Acknowledged]` (`cal_dismiss:<id>`).
  - Calls `bot.send_message(..., disable_web_page_preview=True)` and marks `reminded_at`.
- In `_loop()`:
  - Call `calendar_alerts_tick()` on every minute tick.
  - Call `calendar_sync_tick()` every 300 seconds (5 minutes).

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_agent_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/pranabesh/code/Pithon add pithon/agent/scheduler.py tests/test_agent_scheduler.py
git -C /Users/pranabesh/code/Pithon commit -m "feat(scheduler): add 5-minute ICS sync tick and 1-minute proactive meeting alerts"
```

---

### Task 5: Daily Briefing Agenda Integration

**Files:**
- Modify: `pithon/agent/briefing.py`
- Modify: `tests/test_briefing.py`

**Interfaces:**
- Consumes: `Storage.get_upcoming_events`
- Modifies: `generate_daily_briefing(chat_id, storage, tz_name)` to include formatted agenda section.

- [ ] **Step 1: Write failing test verifying briefing includes today's meetings**

```python
# In tests/test_briefing.py
def test_briefing_includes_agenda(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    s.save_user_profile("user_1", name="Pranabesh")
    now_local = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    start_iso = now_local.replace(hour=14, minute=0).isoformat()
    end_iso = now_local.replace(hour=14, minute=30).isoformat()
    s.save_calendar_events("user_1", [{
        "id": "cal-today-1",
        "parent_uid": "cal-1",
        "title": "Quarterly Planning",
        "description": "",
        "location": "Zoom",
        "meeting_link": "https://zoom.us/j/12345",
        "start_time": start_iso,
        "end_time": end_iso,
        "is_recurring": 0,
        "event_md5": "md5-today"
    }])
    briefing = generate_daily_briefing("user_1", s, tz_name="Asia/Kolkata")
    assert "Today's Agenda & Calls" in briefing
    assert "Quarterly Planning" in briefing
    assert "https://zoom.us/j/12345" in briefing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_briefing.py -k test_briefing_includes_agenda -v`
Expected: FAIL

- [ ] **Step 3: Integrate agenda section in `pithon/agent/briefing.py`**

In `pithon/agent/briefing.py`:
- Query `storage.get_upcoming_events(chat_id, limit=6)` for events occurring today.
- If meetings exist, format section:
  ```markdown
  📅 *Today's Agenda & Calls (2 scheduled):*
  • `02:00 PM - 02:30 PM` — [Quarterly Planning](https://zoom.us/j/12345) _(Zoom)_
  ```
- If no meetings scheduled:
  `📅 *Today's Agenda:*\n• No calls scheduled for today ✨`

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_briefing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/pranabesh/code/Pithon add pithon/agent/briefing.py tests/test_briefing.py
git -C /Users/pranabesh/code/Pithon commit -m "feat(briefing): embed synchronized daily agenda and call links into /briefing"
```

---

### Task 6: Telegram Bot Commands & Qwen Native Tool Calling

**Files:**
- Modify: `pithon/agent/telegram_bot.py`
- Modify: `pithon/agent/tools.py`
- Modify: `tests/test_agent_telegram.py`
- Modify: `tests/test_agent_tools.py`

**Interfaces:**
- Produces: `/calendar` slash command router in `TelegramBot`
- Produces: `cal_dismiss` callback query handler in `TelegramBot`
- Produces: `get_calendar_events` tool definition and executor in `tools.py`

- [ ] **Step 1: Write failing tests for /calendar command and tool call**

```python
# In tests/test_agent_tools.py
def test_get_calendar_events_tool(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    s.save_user_profile("user_1", name="Pranabesh")
    s.save_calendar_events("user_1", [{
        "id": "e-1",
        "parent_uid": "e-1",
        "title": "Daily Sync",
        "description": "",
        "location": "Meet",
        "meeting_link": "https://meet.google.com/xyz",
        "start_time": "2026-10-13T10:00:00+05:30",
        "end_time": "2026-10-13T10:30:00+05:30",
        "is_recurring": 0,
        "event_md5": "md5"
    }])
    tool_call = {"name": "get_calendar_events", "arguments": {"days": 1}}
    reply, markup, ctx = execute_tool_call(tool_call, s, "user_1", tz_name="Asia/Kolkata")
    assert "Daily Sync" in reply
    assert ctx["type"] == "calendar"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_agent_tools.py -k test_get_calendar_events_tool -v`
Expected: FAIL

- [ ] **Step 3: Implement Telegram `/calendar` handlers and tool call execution**

- In `pithon/agent/tools.py`:
  - Add `get_calendar_events` to `TOOLS_DEFINITIONS`.
  - Handle `get_calendar_events` in `execute_tool_call`.
- In `pithon/agent/telegram_bot.py`:
  - Fast-path `/calendar` (supports `/calendar`, `/calendar set <url>`, `/calendar alert <mins>`, `/calendar sync`).
  - Add `cal_dismiss:<id>` callback handler in `handle_callback_query`.
  - Add `/calendar` to `/help` text and command menu.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_agent_telegram.py tests/test_agent_tools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/pranabesh/code/Pithon add pithon/agent/telegram_bot.py pithon/agent/tools.py tests/test_agent_telegram.py tests/test_agent_tools.py
git -C /Users/pranabesh/code/Pithon commit -m "feat(telegram,tools): add /calendar command suite and Qwen tool calling"
```

---

### Task 7: Web Management Portal & API

**Files:**
- Modify: `pithon/agent/web.py`
- Modify: `tests/test_agent_web.py`

**Interfaces:**
- Produces: GET `/api/calendar` endpoint
- Produces: POST `/api/calendar/sync` endpoint
- Produces: Quick action prompt pill in UI

- [ ] **Step 1: Write failing test for `/api/calendar` GET endpoint**

```python
# In tests/test_agent_web.py
def test_web_api_calendar(web_server_client):
    res = web_server_client.get("/api/calendar")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_agent_web.py -k test_web_api_calendar -v`
Expected: FAIL

- [ ] **Step 3: Implement `/api/calendar` and UI pill in `pithon/agent/web.py`**

- In `pithon/agent/web.py`:
  - In `do_GET`: Add `/api/calendar` route returning `{ "status": "ok", "events": events, "synced_at": synced_at }`.
  - In `do_POST`: Add `/api/calendar/sync` route to trigger manual background sync.
  - In chat suggestions pills: Add `<span class="pill-prompt" onclick="setPrompt('/calendar')">📅 Today's Agenda (/calendar)</span>`.
  - In `/api/chat/send`: Handle `/calendar` fast-path command.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest tests/test_agent_web.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/pranabesh/code/Pithon add pithon/agent/web.py tests/test_agent_web.py
git -C /Users/pranabesh/code/Pithon commit -m "feat(web): add /api/calendar endpoint and dashboard quick pill"
```

---

### Task 8: Documentation, Full Verification & Server Deployment

**Files:**
- Modify: `README.md`
- Modify: `wiki/Commands-and-Tools.md`, `wiki/Telegram-Bot-Setup.md`, `wiki/Web-Portal-Guide.md`
- Remote: `ubuntu@pithon.trylocalhost.com`

**Interfaces:**
- Git sync between local repository and remote VPS
- Live verification of calendar synchronization on Docker container

- [ ] **Step 1: Run complete test suite locally**

Run: `/Users/pranabesh/code/Pithon/.venv/bin/pytest /Users/pranabesh/code/Pithon/tests -v`
Expected: All tests PASS with zero warnings.

- [ ] **Step 2: Update documentation and wiki**

- Add `/calendar` command to `README.md` and BotFather command lists:
  `calendar - View upcoming meetings and set ICS sync URL`
- Update Wiki documentation on GitHub Wiki (`pranabeshsingh/Khepri.wiki`).

- [ ] **Step 3: Commit and push to origin/master**

```bash
git -C /Users/pranabesh/code/Pithon add README.md wiki/
git -C /Users/pranabesh/code/Pithon commit -m "docs: add calendar sync and meeting reminder documentation"
git -C /Users/pranabesh/code/Pithon push origin master
```

- [ ] **Step 4: Deploy and verify on remote VPS**

```bash
ssh -T ubuntu@pithon.trylocalhost.com "git -C /home/ubuntu/Pithon pull origin master && docker cp /home/ubuntu/Pithon/pithon/agent/. pithon-agent:/app/pithon/agent/ && docker restart pithon-agent"
```
Verify:
1. `docker ps` shows `pithon-agent` and `pithon-daemon` healthy.
2. `git -C /home/ubuntu/Pithon status` is clean (only model override difference).
3. Test calendar tool execution inside `pithon-agent`.
