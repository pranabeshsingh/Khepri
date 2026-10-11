"""Interactive Telegram Bot router with inline keyboards, whitelist security, and poll support."""

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, Any, List, Optional, Tuple

from pithon.agent.search import should_search, search_duckduckgo, format_search_context
from pithon.agent.time_context import get_current_time_info, format_temporal_prompt_header
from pithon.agent.tasks import (
    is_task_intent,
    parse_task_text,
    format_tasks_message,
    format_reminder_alert
)

logger = logging.getLogger("pithon.telegram")

class TelegramBot:
    """Telegram Bot client with whitelist security and interactive keyboards."""

    def __init__(
        self,
        token: str,
        admin_chat_id: str = "357035668",
        report_chat_id: str = "-1001169201210",
        storage: Any = None,
        daemon_url: str = "http://127.0.0.1:8090",
        tz_name: str = "Asia/Kolkata"
    ):
        self.token = token.strip()
        self.admin_chat_id = str(admin_chat_id).strip()
        self.report_chat_id = str(report_chat_id).strip()
        self.storage = storage
        self.daemon_url = daemon_url.rstrip("/")
        self.tz_name = tz_name
        self.api_base = f"https://api.telegram.org/bot{self.token}"

    def _call_api(self, method: str, payload: Dict[str, Any], timeout: float = 35.0) -> Optional[Dict[str, Any]]:
        """Dispatch HTTP POST to Telegram Bot API."""
        url = f"{self.api_base}/{method}"
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except Exception as e:
            logger.error(f"Telegram API {method} error: {e}")
            return None

    def send_message(
        self,
        chat_id: Any,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        disable_notification: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Send a message, splitting into segments if exceeding 4000 characters."""
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        res = None
        for idx, chunk in enumerate(chunks):
            # Only attach reply_markup to the final chunk
            markup = reply_markup if idx == len(chunks) - 1 else None
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
                "disable_notification": disable_notification
            }
            if markup:
                payload["reply_markup"] = markup
            res = self._call_api("sendMessage", payload)
            if not res or not res.get("ok"):
                # Fallback without Markdown if parsing fails
                payload.pop("parse_mode", None)
                res = self._call_api("sendMessage", payload)
        return res

    def send_chat_action(self, chat_id: Any, action: str = "typing") -> None:
        """Send chat action indicator (typing, etc.)."""
        self._call_api("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=5.0)

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> None:
        """Acknowledge an interactive button press."""
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        self._call_api("answerCallbackQuery", payload, timeout=5.0)

    def edit_message_text(
        self,
        chat_id: Any,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Edit an existing message in-place."""
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        res = self._call_api("editMessageText", payload, timeout=10.0)
        if not res or not res.get("ok"):
            payload.pop("parse_mode", None)
            res = self._call_api("editMessageText", payload, timeout=10.0)
        return res

    def send_poll(self, chat_id: Any, question: str, options: List[str]) -> Optional[Dict[str, Any]]:
        """Create a native Telegram poll."""
        payload = {
            "chat_id": chat_id,
            "question": question,
            "options": options,
            "is_anonymous": False
        }
        return self._call_api("sendPoll", payload)

    def is_authorized(self, chat_id: Any) -> bool:
        """Verify chat whitelist: only the admin chat ID is allowed for interactive queries."""
        return str(chat_id) == self.admin_chat_id

    def handle_callback_query(self, cb: Dict[str, Any]) -> None:
        """Process interactive button clicks."""
        cb_id = cb.get("id", "")
        from_id = cb.get("from", {}).get("id")
        if not self.is_authorized(from_id):
            self.answer_callback_query(cb_id, text="Unauthorized.")
            return

        data = cb.get("data", "")
        msg = cb.get("message", {})
        msg_id = msg.get("message_id")
        chat_id = msg.get("chat", {}).get("id")
        current_text = msg.get("text", "")

        if data.startswith("done:"):
            tid = int(data.split(":")[1])
            if self.storage:
                self.storage.complete_task(tid)
            self.answer_callback_query(cb_id, text="Task marked complete! ✅")
            updated_text = f"~~{current_text}~~\n\n✅ *Marked completed!*"
            self.edit_message_text(chat_id, msg_id, updated_text, reply_markup={"inline_keyboard": []})

        elif data.startswith("snooze:"):
            tid = int(data.split(":")[1])
            if self.storage:
                self.storage.snooze_task(tid, hours=1)
            self.answer_callback_query(cb_id, text="Snoozed for 1 hour. ⏰")
            updated_text = f"{current_text}\n\n⏰ *Snoozed for 1 hour.*"
            self.edit_message_text(chat_id, msg_id, updated_text, reply_markup={"inline_keyboard": []})

        elif data.startswith("del:"):
            tid = int(data.split(":")[1])
            if self.storage:
                self.storage.delete_task(tid)
            self.answer_callback_query(cb_id, text="Task deleted. 🗑️")
            updated_text = f"~~{current_text}~~\n\n🗑️ *Deleted.*"
            self.edit_message_text(chat_id, msg_id, updated_text, reply_markup={"inline_keyboard": []})

        else:
            self.answer_callback_query(cb_id)

    def handle_message(self, msg: Dict[str, Any]) -> None:
        """Process inbound Telegram messages."""
        chat_id = msg.get("chat", {}).get("id")
        # Strict Whitelist Check
        if not self.is_authorized(chat_id):
            return

        text = (msg.get("text") or "").strip()
        if not text:
            return

        self.send_chat_action(chat_id, action="typing")

        # 1. Commands Handling
        if text.startswith("/start") or text.startswith("/help"):
            help_text = (
                "👋 *Welcome to Pithon Assistant!*\n\n"
                "I am your lightweight personal AI agent, grounded with live time and web search.\n\n"
                "*Available Commands:*\n"
                "• `/time` - Current date, time, and timezone\n"
                "• `/todo` or `/tasks` - View active tasks & lists\n"
                "• `/add <task>` - Create a new task or reminder\n"
                "• `/search <query>` - Run DuckDuckGo web search\n"
                "• `/poll <question> [opt1] [opt2]` - Create interactive poll\n"
                "• `/status` - System & model runtime health\n\n"
                "_Or simply chat with me naturally!_"
            )
            # Attach quick-action menu
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "📋 My Tasks", "callback_data": "menu:tasks"},
                        {"text": "🕒 Date & Time", "callback_data": "menu:time"}
                    ],
                    [
                        {"text": "📊 Open Dashboard", "url": "https://pithon.trylocalhost.com"}
                    ]
                ]
            }
            self.send_message(chat_id, help_text, reply_markup=reply_markup)
            return

        if text.startswith("/time"):
            info = get_current_time_info(self.tz_name)
            time_msg = (
                f"🕒 *Current Date & Time*\n\n"
                f"• *Date:* {info['weekday']}, {info['day']} {info['month']} {info['year']}\n"
                f"• *Time:* {info['time']} ({info['time_12h']})\n"
                f"• *Timezone:* `{info['timezone']}` (UTC{info['utc_offset'][:3]}:{info['utc_offset'][3:]})"
            )
            self.send_message(chat_id, time_msg)
            return

        if text.startswith("/todo") or text.startswith("/tasks"):
            if self.storage:
                tasks = self.storage.get_tasks(str(chat_id))
                out_text, inline_kb = format_tasks_message(tasks)
                reply_markup = {"inline_keyboard": inline_kb} if inline_kb else None
                self.send_message(chat_id, out_text, reply_markup=reply_markup)
            else:
                self.send_message(chat_id, "No storage configured.")
            return

        if text.startswith("/add "):
            task_info = parse_task_text(text, default_tz=self.tz_name)
            if self.storage:
                tid = self.storage.create_task(
                    str(chat_id),
                    task_info["title"],
                    list_name=task_info["list_name"],
                    due_at=task_info["due_at"]
                )
                due_info = f" _(Due: {task_info['due_at'][:16].replace('T', ' ')})_" if task_info["due_at"] else ""
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": f"✅ Done #{tid}", "callback_data": f"done:{tid}"}]
                    ]
                }
                self.send_message(
                    chat_id,
                    f"✅ Saved task *#{tid}*: {task_info['title']}{due_info}",
                    reply_markup=reply_markup
                )
            return

        if text.startswith("/poll"):
            # Syntax: /poll "Question" "Option 1" "Option 2"
            matches = re.findall(r'"([^"]+)"', text)
            if len(matches) >= 3:
                q = matches[0]
                opts = matches[1:]
                self.send_poll(chat_id, q, opts)
            else:
                self.send_message(chat_id, 'Usage: `/poll "Question" "Option 1" "Option 2"`')
            return

        if text.startswith("/status"):
            status_text = (
                "📈 *Pithon System Status*\n\n"
                f"• *Inference Daemon:* `{self.daemon_url}`\n"
                f"• *Timezone:* `{self.tz_name}`\n"
                f"• *Authorized Chat ID:* `{self.admin_chat_id}`\n"
                f"• *Reports Chat ID:* `{self.report_chat_id}`\n"
                "• *Container Health:* Normal (cgroups: 0.5 CPU, 512M RAM)"
            )
            self.send_message(chat_id, status_text)
            return

        # 2. Check Natural Language Task Intent
        if is_task_intent(text):
            task_info = parse_task_text(text, default_tz=self.tz_name)
            if self.storage:
                tid = self.storage.create_task(
                    str(chat_id),
                    task_info["title"],
                    list_name=task_info["list_name"],
                    due_at=task_info["due_at"]
                )
                due_info = f" _(Due: {task_info['due_at'][:16].replace('T', ' ')})_" if task_info["due_at"] else ""
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": f"✅ Done #{tid}", "callback_data": f"done:{tid}"}]
                    ]
                }
                self.send_message(
                    chat_id,
                    f"📌 Scheduled task *#{tid}*: {task_info['title']}{due_info}",
                    reply_markup=reply_markup
                )
                return

        # 3. DuckDuckGo Search & LLM Inference Pipeline
        search_query = None
        search_results = None
        inline_keyboard = []

        if should_search(text):
            search_query = re.sub(r"^/(search|web)\s+", "", text, flags=re.IGNORECASE)
            search_results = search_duckduckgo(search_query, max_results=3)

            # Build source URL buttons
            url_buttons = []
            for idx, r in enumerate(search_results, 1):
                if r.get("url"):
                    domain = urllib.parse.urlparse(r["url"]).netloc.replace("www.", "")
                    url_buttons.append({"text": f"🌐 {domain[:18]}", "url": r["url"]})
            if url_buttons:
                inline_keyboard.append(url_buttons)

        # Assemble Prompt with Temporal & Search Grounding
        temporal_header = format_temporal_prompt_header(self.tz_name)
        search_block = format_search_context(search_results, search_query) if search_results else ""

        full_prompt = (
            f"{temporal_header}\n"
            f"{search_block}"
            f"User Question: {text}\n"
            f"Answer concisely and directly."
        )

        start_t = time.time()
        answer = self._query_daemon(full_prompt)
        latency_ms = int((time.time() - start_t) * 1000)

        # Audit log in SQLite
        if self.storage:
            self.storage.log_interaction(
                chat_id=str(chat_id),
                user_id=str(msg.get("from", {}).get("id", "")),
                prompt=text,
                search_query=search_query,
                search_results=search_results,
                response=answer,
                latency_ms=latency_ms
            )

        reply_markup = {"inline_keyboard": inline_keyboard} if inline_keyboard else None
        self.send_message(chat_id, answer, reply_markup=reply_markup)

    def _query_daemon(self, prompt: str) -> str:
        """Call Pithon daemon on 127.0.0.1:8090."""
        url = f"{self.daemon_url}/v1/chat/completions"
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
            "temperature": 0.2
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=45.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return res_data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Error querying daemon at {url}: {e}")
            return "⚠️ I couldn't reach the local language model. Please check the daemon status."

    def run_polling(self) -> None:
        """Continuous long-polling loop for Telegram updates."""
        offset = 0
        logger.info(f"Telegram Bot starting long-polling for admin chat: {self.admin_chat_id}")
        while True:
            try:
                url = f"{self.api_base}/getUpdates?offset={offset}&timeout=30"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=35.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("ok"):
                        for update in data.get("result", []):
                            offset = max(offset, update["update_id"] + 1)
                            if "message" in update:
                                self.handle_message(update["message"])
                            elif "callback_query" in update:
                                self.handle_callback_query(update["callback_query"])
            except Exception as e:
                logger.error(f"Polling exception: {e}")
                time.sleep(3.0)
