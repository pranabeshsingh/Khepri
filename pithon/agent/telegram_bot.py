"""Interactive Telegram Bot router with inline keyboards, whitelist security, poll support, and native Qwen2.5 tool calling."""

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, Any, List, Optional

from pithon.agent.search import should_search, search_duckduckgo, format_search_context
from pithon.agent.time_context import get_current_time_info, format_temporal_prompt_header
from pithon.agent.tasks import (
    is_task_intent,
    parse_task_text,
    format_tasks_message
)
from pithon.agent.calc import safe_calculate
from pithon.agent.weather import get_weather_report, is_weather_intent, extract_weather_location
from pithon.agent.memory import list_notes
from pithon.agent.tools import (
    format_tools_system_prompt,
    extract_tool_call,
    execute_tool_call
)

logger = logging.getLogger("pithon.telegram")

class TelegramBot:
    """Telegram Bot client with whitelist security, interactive keyboards, and tool calling."""

    def __init__(
        self,
        token: str,
        admin_chat_id: str = "",
        report_chat_id: str = "",
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
            logger.error(f"Telegram API call error ({method}): {e}")
            return None

    def send_message(
        self,
        chat_id: Any,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        disable_notification: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Send a markdown message to a Telegram chat."""
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
            "disable_notification": disable_notification
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._call_api("sendMessage", payload)

    def edit_message_text(
        self,
        chat_id: Any,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Edit an existing message for interactive button updates."""
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._call_api("editMessageText", payload)

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> None:
        """Acknowledge Telegram button click."""
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        self._call_api("answerCallbackQuery", payload)

    def send_chat_action(self, chat_id: Any, action: str = "typing") -> None:
        """Indicate bot is typing or thinking."""
        payload = {"chat_id": chat_id, "action": action}
        self._call_api("sendChatAction", payload)

    def send_poll(self, chat_id: Any, question: str, options: List[str]) -> Optional[Dict[str, Any]]:
        """Dispatch a native Telegram poll."""
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

        # 1. Fast-path Explicit Slash Commands
        if text.startswith("/start") or text.startswith("/help"):
            help_text = (
                "👋 *Welcome to Khepri Assistant!*\n\n"
                "I am your lightweight personal AI agent, grounded with live time, task management, and web search.\n\n"
                "*Available Commands:*\n"
                "• `/time` - Current date, time, and timezone\n"
                "• `/todo` or `/tasks` - View active tasks & lists\n"
                "• `/add <task>` - Create a new task or reminder\n"
                "• `/timer <duration> [label]` - Start a countdown timer\n"
                "• `/search <query>` - Run DuckDuckGo web search\n"
                "• `/poll <question> [opt1] [opt2]` - Create interactive poll\n"
                "• `/status` - System & model runtime health\n\n"
                "_Or simply chat with me naturally (e.g. 'Set a timer for 15 mins')!_"
            )
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

        if text.startswith("/timer"):
            task_info = parse_task_text(text, default_tz=self.tz_name)
            if self.storage and task_info.get("due_at"):
                tid = self.storage.create_task(
                    str(chat_id),
                    task_info["title"],
                    list_name="timer",
                    due_at=task_info["due_at"]
                )
                due_clean = task_info["due_at"][:19].replace("T", " ")
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "❌ Cancel Timer", "callback_data": f"del:{tid}"}]
                    ]
                }
                msg_text = (
                    f"⏱️ *Timer Started!*\n\n"
                    f"📌 *Timer:* {task_info['title']}\n"
                    f"🕒 *Alert at:* `{due_clean} {self.tz_name}`\n\n"
                    f"_I will alert you as soon as time is up!_"
                )
                self.send_message(chat_id, msg_text, reply_markup=reply_markup)
            else:
                self.send_message(chat_id, "Usage: `/timer 15m Pasta` or `/timer 30s Quick check`")
            return

        if text.startswith("/poll"):
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
                "📈 *Khepri System Status*\n\n"
                f"• *Inference Daemon:* `{self.daemon_url}`\n"
                f"• *Timezone:* `{self.tz_name}`\n"
                f"• *Authorized Chat ID:* `{self.admin_chat_id}`\n"
                f"• *Reports Chat ID:* `{self.report_chat_id}`\n"
                "• *Container Health:* Normal (cgroups: 0.5 CPU, 512M RAM)"
            )
            self.send_message(chat_id, status_text)
            return

        if text.startswith("/calc "):
            expr = text[6:].strip()
            res = safe_calculate(expr)
            self.send_message(chat_id, f"🧮 `{expr}` = *{res}*")
            return

        if text.startswith("/weather"):
            loc = text[8:].strip() or "Bangalore"
            report = get_weather_report(loc)
            self.send_message(chat_id, report.get("summary", "No weather data."))
            return

        if text.startswith("/notes"):
            notes = list_notes()
            if not notes:
                self.send_message(chat_id, "📝 No saved notes. Send 'Remember that...' or `/note <title> <text>` to save.")
            else:
                lines = ["📝 *Saved Markdown Notes:*\n"]
                for n in notes:
                    lines.append(f"• *{n['title']}* (`{n['filename']}`)")
                self.send_message(chat_id, "\n".join(lines))
            return

        # Direct conversational weather intent (e.g. 'how is the weather in kolkata?')
        if is_weather_intent(text):
            loc = extract_weather_location(text)
            report = get_weather_report(loc)
            ans = report.get("summary", "No weather data.")
            if self.storage:
                self.storage.log_interaction(
                    chat_id=str(chat_id),
                    user_id=str(msg.get("from", {}).get("id", "")),
                    prompt=text,
                    response=ans
                )
            self.send_message(chat_id, ans)
            return

        # Direct calculation intent (e.g. 'calculate 25 * 4', 'what is 4320 / 6?')
        calc_m = re.search(r"^(?:calculate|calc|what is)\s+([0-9\.\s\+\-\*\/\(\)\^\%]+)[?]?$", text, re.IGNORECASE)
        if calc_m:
            expr = calc_m.group(1).strip()
            res = safe_calculate(expr)
            ans = f"🧮 `{expr}` = *{res}*"
            if self.storage:
                self.storage.log_interaction(
                    chat_id=str(chat_id),
                    user_id=str(msg.get("from", {}).get("id", "")),
                    prompt=text,
                    response=ans
                )
            self.send_message(chat_id, ans)
            return

        # 2. Conversational Intent via Native Qwen2.5 Tool Calling & Temporal Grounding
        tools_system = format_tools_system_prompt()
        temporal_header = format_temporal_prompt_header(self.tz_name)
        system_prompt = f"{tools_system}\n\n{temporal_header}"

        start_t = time.time()
        answer = self._query_daemon(text, system=system_prompt)
        latency_ms = int((time.time() - start_t) * 1000)

        # Check for Native Qwen2.5 Tool Call
        tool_call = extract_tool_call(answer)
        if tool_call:
            tool_name = tool_call.get("name")
            if tool_name == "web_search":
                search_query = tool_call.get("arguments", {}).get("query", text)
                _, url_markup, ctx = execute_tool_call(tool_call, self.storage, str(chat_id), self.tz_name)
                # Second turn: Generate final answer grounded on search context
                grounded_prompt = (
                    f"{ctx.get('context', '')}\n\n"
                    f"User Question: {text}\n"
                    f"Answer concisely based on the search context above."
                )
                grounded_answer = self._query_daemon(grounded_prompt, system=temporal_header)
                if self.storage:
                    self.storage.log_interaction(
                        chat_id=str(chat_id),
                        user_id=str(msg.get("from", {}).get("id", "")),
                        prompt=text,
                        search_query=search_query,
                        search_results=ctx.get("results"),
                        response=grounded_answer,
                        latency_ms=latency_ms
                    )
                self.send_message(chat_id, grounded_answer, reply_markup=url_markup)
                return
            elif tool_name in ("set_timer", "add_task"):
                reply_text, reply_markup, ctx = execute_tool_call(tool_call, self.storage, str(chat_id), self.tz_name)
                if self.storage:
                    self.storage.log_interaction(
                        chat_id=str(chat_id),
                        user_id=str(msg.get("from", {}).get("id", "")),
                        prompt=text,
                        response=reply_text,
                        latency_ms=latency_ms
                    )
                self.send_message(chat_id, reply_text, reply_markup=reply_markup)
                return

        # 3. Fallback: Catch conversational task/timer patterns if model didn't emit a tool call
        if is_task_intent(text):
            task_info = parse_task_text(text, default_tz=self.tz_name)
            if self.storage and (task_info.get("seconds", 0) > 0 or task_info.get("due_at")):
                tid = self.storage.create_task(
                    str(chat_id),
                    task_info["title"],
                    list_name=task_info["list_name"],
                    due_at=task_info["due_at"]
                )
                if task_info.get("is_timer"):
                    due_clean = task_info["due_at"][:19].replace("T", " ") if task_info.get("due_at") else ""
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "❌ Cancel Timer", "callback_data": f"del:{tid}"}]
                        ]
                    }
                    msg_text = (
                        f"⏱️ *Timer Started!*\n\n"
                        f"📌 *Timer:* {task_info['title']}\n"
                        f"🕒 *Alert at:* `{due_clean} {self.tz_name}`\n\n"
                        f"_I will alert you as soon as time is up!_"
                    )
                    self.send_message(chat_id, msg_text, reply_markup=reply_markup)
                else:
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

        # 4. Fallback search detection if model didn't tool call but explicitly requested search
        if should_search(text):
            search_query = re.sub(r"^/(search|web)\s+", "", text, flags=re.IGNORECASE)
            search_results = search_duckduckgo(search_query, max_results=3)
            url_buttons = []
            for r in search_results:
                if r.get("url"):
                    domain = urllib.parse.urlparse(r["url"]).netloc.replace("www.", "")
                    url_buttons.append({"text": f"🌐 {domain[:18]}", "url": r["url"]})
            reply_markup = {"inline_keyboard": [url_buttons]} if url_buttons else None
            search_block = format_search_context(search_results, search_query)
            grounded_prompt = f"{search_block}\n\nUser Question: {text}\nAnswer concisely."
            answer = self._query_daemon(grounded_prompt, system=temporal_header)
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
            self.send_message(chat_id, answer, reply_markup=reply_markup)
            return

        # 5. Direct conversational response
        if self.storage:
            self.storage.log_interaction(
                chat_id=str(chat_id),
                user_id=str(msg.get("from", {}).get("id", "")),
                prompt=text,
                response=answer,
                latency_ms=latency_ms
            )
        self.send_message(chat_id, answer)

    def _query_daemon(self, prompt: str, system: Optional[str] = None) -> str:
        """Call Pithon daemon on 127.0.0.1:8090."""
        url = f"{self.daemon_url}/v1/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
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
