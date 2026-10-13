# Design Specification: 5-Minute ICS Calendar Sync & Meeting Alerts

- **Date:** 2026-10-13
- **Status:** Approved
- **Target:** Khepri Assistant (`Pithon`)

---

## 1. Executive Summary

This feature adds an automated calendar synchronization and proactive meeting reminder engine to Khepri. It connects to an open `.ics` (iCalendar / `webcal://`) URL, synchronizes every 5 minutes in a background scheduler loop, caches occurrences in SQLite using MD5 change detection, expands recurring events (`RRULE`), and informs the user through:
1. **Proactive Telegram Notifications:** Sent $N$ minutes before a meeting (default: 10 minutes, configurable via `/calendar alert <mins>`), with 1-click **Join Call** buttons for Google Meet, Zoom, and Microsoft Teams.
2. **Daily Morning Briefing:** A structured *"Today's Agenda & Calls"* section inside `/briefing`.
3. **On-Demand Access:** Slash commands (`/calendar`, `/agenda`, `/calendar set <url>`) and conversational Qwen2.5 tool calling (*"When is my next meeting?"*).
4. **Web Management Portal:** `/api/calendar` endpoint and quick-action prompt pill.

---

## 2. Architecture & Data Flow

```
                     +---------------------------------------+
                     | Remote ICS Link (Google/Outlook/iCal) |
                     +-------------------+-------------------+
                                         | HTTP GET (Every 5 mins)
                                         v
+---------------------------------------------------------------------------------+
| Khepri Scheduler (Background Thread - 5s Tick)                                 |
|                                                                                 |
| 1. calendar_sync_tick()  --> Downloads feed, computes feed_md5                  |
|                              If changed: parses VEVENTs & expands RRULEs        |
|                              Upserts changed events (via event_md5) to SQLite   |
|                                                                                 |
| 2. calendar_alerts_tick() --> Runs on minute tick                               |
|                              Scans: now <= start_time <= now + alert_mins       |
|                              and reminded_at IS NULL                            |
|                              Dispatches Telegram alert with inline Join button  |
+----------------------------------------+----------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
| SQLite Database (pithon.db)                                                     |
| - calendar_events: id (uid#start), parent_uid, chat_id, title, start_time,     |
|                    end_time, meeting_link, event_md5, reminded_at               |
| - user_profiles: calendar_url, calendar_alert_mins, calendar_feed_md5           |
+-------------------+--------------------+--------------------+-------------------+
                    |                    |                    |
                    v                    v                    v
          Daily Morning Briefing     Telegram Bot         Conversational AI
          (/briefing agenda)        (/calendar cmd &    (Qwen tool call:
                                     instant alerts)      get_calendar_events)
```

---

## 3. RFC 5545 Parser & Recurrence Engine (`pithon/agent/calendar.py`)

### 3.1 Zero-Dependency Parser
Implemented entirely with Python standard library (`datetime`, `zoneinfo`, `re`, `urllib.request`, `hashlib`).

1. **Protocol Normalization:** `webcal://` URLs are automatically converted to `https://`.
2. **Line Unfolding:** RFC 5545 specifies that lines longer than 75 octets are folded using `\r\n ` or `\r\n\t`. The parser unfolds lines prior to parsing key-value properties.
3. **Property Parsing:**
   - `UID`: Base event identifier.
   - `SUMMARY`: Event title (sanitized for Telegram Markdown: brackets and asterisks escaped/cleaned).
   - `DTSTART` & `DTEND`: Extracted and parsed into timezone-aware `datetime` objects:
     - UTC: `20261013T043000Z`
     - Parameterized Timezone: `DTSTART;TZID=Asia/Kolkata:20261013T100000`
     - All-day Date: `DTSTART;VALUE=DATE:20261013`
   - `LOCATION` & `DESCRIPTION`: Free text meeting details.

### 3.2 Video Call Link Auto-Detection
Scans `LOCATION` and `DESCRIPTION` fields using regular expressions to extract direct meeting links:
- **Google Meet:** `https://meet.google.com/[a-z]{3}-[a-z]{4}-[a-z]{3}`
- **Zoom:** `https://[a-zA-Z0-9\.\-]*zoom\.us/j/[0-9]+(?:\?pwd=[a-zA-Z0-9]+)?`
- **Microsoft Teams:** `https://teams\.microsoft\.com/l/meetup-join/[^\s<>"]+`
The first detected URL is saved to `meeting_link`.

### 3.3 Recurrence Engine (`RRULE`)
Handles recurring events within a sliding active window: `[now - 1 day, now + 14 days]`.

1. **Supported Rules:**
   - `FREQ=DAILY`: Repeats daily with optional `INTERVAL`.
   - `FREQ=WEEKLY`: Repeats on specified days (e.g. `BYDAY=MO,TU,WE,TH,FR`).
   - `FREQ=MONTHLY`: Repeats on specific day of month (e.g. `BYMONTHDAY=15`).
   - Bounds: Respects `UNTIL` (cutoff date) and `COUNT` (max occurrences).
   - Exclusions: Respects `EXDATE` (cancelled occurrence dates).
2. **Composite Occurrence ID:**
   Each recurrence instance is assigned a unique primary key:
   `id = f"{parent_uid}#{start_iso}"`
   *Example:* `standup-101@company.com#2026-10-13T10:00:00+05:30`
3. **Independence of Reminder State:**
   Because each occurrence has its own database row, marking `reminded_at` for Monday's occurrence has zero impact on Tuesday's occurrence.

---

## 4. MD5 Change Detection & Database Schema

### 4.1 MD5 Caching Strategy
1. **Feed-Level MD5 (`feed_md5`):**
   - Downloaded `.ics` payload is hashed: `hashlib.md5(raw_bytes).hexdigest()`.
   - Stored in `user_profiles.calendar_feed_md5`.
   - If `current_md5 == stored_md5`, parsing is skipped completely (0ms overhead, no DB writes).
2. **Event-Level MD5 (`event_md5`):**
   - Each `VEVENT` block is hashed: `hashlib.md5(vevent_str.encode("utf-8")).hexdigest()`.
   - Stored in `calendar_events.event_md5`.
   - If an event exists and its `event_md5` is identical, database update is skipped. If changed, fields (`title`, `start_time`, `end_time`, `meeting_link`) are updated and `updated_at` refreshed.

### 4.2 SQLite Schema (`data/pithon.db`)

```sql
-- Track user calendar preferences & feed hash in user_profiles
ALTER TABLE user_profiles ADD COLUMN calendar_url TEXT DEFAULT '';
ALTER TABLE user_profiles ADD COLUMN calendar_alert_mins INTEGER DEFAULT 10;
ALTER TABLE user_profiles ADD COLUMN calendar_feed_md5 TEXT DEFAULT '';
ALTER TABLE user_profiles ADD COLUMN calendar_synced_at TIMESTAMP;

-- Calendar events and occurrences
CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,             -- uid#start_time for occurrences
    parent_uid TEXT NOT NULL,        -- original VEVENT UID
    chat_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    location TEXT DEFAULT '',
    meeting_link TEXT DEFAULT '',    -- Detected Google Meet / Zoom / Teams link
    start_time TIMESTAMP NOT NULL,   -- ISO format with timezone
    end_time TIMESTAMP NOT NULL,
    is_recurring INTEGER DEFAULT 0,
    event_md5 TEXT NOT NULL,         -- MD5 hash of the VEVENT block
    reminded_at TIMESTAMP DEFAULT NULL, -- Recorded when alert was dispatched
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cal_start ON calendar_events (chat_id, start_time);
CREATE INDEX IF NOT EXISTS idx_cal_reminded ON calendar_events (reminded_at, start_time);
```

---

## 5. Scheduler Engine (`pithon/agent/scheduler.py`)

### 5.1 5-Minute Sync Tick (`calendar_sync_tick`)
- Executed every 300 seconds (5 minutes) within the scheduler thread loop.
- Resolves URL: checks `user_profiles.calendar_url` for `admin_chat_id`, falling back to `CALENDAR_ICS_URL` env variable.
- If no URL is configured, skips silently.
- On fetch:
  - Computes `feed_md5`. If equal to `calendar_feed_md5`, returns immediately.
  - If different, parses feed, expands occurrences for `[today - 1 day, today + 14 days]`, and upserts to `calendar_events`.
  - Prunes past events older than 7 days (`start_time < datetime.now() - 7 days`).
  - Updates `calendar_feed_md5 = feed_md5` and `calendar_synced_at = CURRENT_TIMESTAMP`.

### 5.2 Minute Alert Tick (`calendar_alerts_tick`)
- Executed every minute.
- Reads `calendar_alert_mins` (default 10) for `admin_chat_id`.
- Scans `calendar_events`:
  `WHERE chat_id = ? AND reminded_at IS NULL AND start_time >= ? AND start_time <= ?`
  where range is `[now, now + alert_mins]`.
- For each matching meeting:
  1. Computes formatted time: `🕒 10:00 AM - 10:30 AM IST`.
  2. Builds Telegram alert message:
     ```markdown
     🔔 *Upcoming Call in 10 mins!*
     📌 *Daily Engineering Standup*
     🕒 `10:00 AM - 10:30 AM IST`
     📍 Location: Google Meet
     ```
  3. Prepares Inline Keyboard:
     - `[📞 Join Meeting]` (Direct URL button if `meeting_link` exists).
     - `[✅ Dismiss]` (Callback button `cal_dismiss:<id>` to acknowledge).
  4. Sends via `bot.send_message(chat_id, msg, reply_markup=markup, disable_web_page_preview=True)`.
  5. Updates `reminded_at = CURRENT_TIMESTAMP`.

---

## 6. User Interfaces & Integration Surfaces

### 6.1 Telegram Bot Commands (`pithon/agent/telegram_bot.py`)
- `/calendar` or `/agenda`: Displays today's schedule and the next 3 upcoming meetings with start times and join links.
- `/calendar set <url>`: Sets or updates the user's ICS link in SQLite and triggers an immediate sync.
- `/calendar alert <mins>`: Updates reminder lead time (e.g. `/calendar alert 15` or `/calendar alert 5m`).
- `/calendar sync`: Manually forces a refresh.
- Callback `cal_dismiss:<id>`: Updates the message to acknowledged (`✅ Dismissed`).

### 6.2 Daily Briefing (`pithon/agent/briefing.py`)
Adds a dedicated agenda section between Tasks and News:
```markdown
📅 *Today's Agenda & Calls (2 scheduled):*
• `10:00 AM - 10:30 AM` — [Daily Standup](https://meet.google.com/abc-defg-hij) _(Google Meet)_
• `03:00 PM - 04:00 PM` — Architecture Review _(Zoom)_
```
*(Or if empty: `• No meetings scheduled for today ✨`)*.

### 6.3 Qwen2.5 Native Tool Calling (`pithon/agent/tools.py`)
Registers `get_calendar_events`:
```json
{
  "type": "function",
  "function": {
    "name": "get_calendar_events",
    "description": "Fetch upcoming calendar events, meetings, and calls from the synced schedule",
    "parameters": {
      "type": "object",
      "properties": {
        "limit": {"type": "integer", "description": "Max events to return (default 5)"},
        "days": {"type": "integer", "description": "Days forward to check (default 1 for today)"}
      }
    }
  }
}
```
Enables natural language answers to:
- *"What calls do I have today?"*
- *"When is my next meeting?"*
- *"Do I have anything scheduled at 4 PM?"*

### 6.4 Web Portal (`pithon/agent/web.py`)
- GET `/api/calendar`: Returns upcoming meetings JSON for the dashboard.
- Chat prompt pill: `<span class="pill-prompt" onclick="setPrompt('/calendar')">📅 Today's Agenda (/calendar)</span>`.

---

## 7. Error Handling & Edge Cases

| Scenario | Handling |
| :--- | :--- |
| **Network Timeout / Host Down** | 5-second HTTP timeout on feed fetch; logs warning and re-attempts on next 5-min tick without crashing scheduler. |
| **Malformed VEVENT Block** | Individual VEVENT parse errors are caught and logged; remaining events in feed continue parsing. |
| **All-Day Events** | Stored with start time at 00:00:00 local time; exempt from minute-precision proactive alert tick to avoid midnight alert spam. |
| **Link Preview Clutter** | Dispatched with `disable_web_page_preview=True` so Telegram shows clean text with clickable links rather than massive website cards. |
| **Sliding Window Roll** | Once daily, the scheduler triggers sync to roll the active 14-day window forward even if feed MD5 has not changed. |

---

## 8. Testing Plan

1. `test_calendar_parser`: Verify parsing of standard VEVENT properties, unfolding, timezones (UTC `Z`, `TZID`).
2. `test_video_link_detection`: Verify regex extraction for Google Meet, Zoom, Teams links in description/location.
3. `test_rrule_expansion`: Verify daily, weekly (by day), and monthly recurrence expansion within the sliding window.
4. `test_md5_caching`: Verify that identical feed bytes skip parsing, and identical event MD5s skip SQLite row updates.
5. `test_alerts_tick`: Verify that an event 8 minutes in the future fires an alert when lead time is 10 minutes, sets `reminded_at`, and never fires twice.
6. `test_briefing_agenda`: Verify that `/briefing` renders today's meetings formatted with links and publisher/platform tags.
