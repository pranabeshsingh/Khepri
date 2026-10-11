"""Modern dark-mode Web UI dashboard and REST API for Pithon Mini-OpenClaw."""

import http.cookies
import json
import logging
import os
import re
import secrets
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple

from pithon.agent.search import should_search, search_duckduckgo, format_search_context
from pithon.agent.time_context import get_current_time_info, format_temporal_prompt_header

logger = logging.getLogger("pithon.web")

# --- HTML & CSS UI TEMPLATES ---

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pithon • Login</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(15, 23, 42, 0.75);
      --border: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --primary-hover: #4f46e5;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: radial-gradient(circle at 50% 20%, #1e1b4b 0%, var(--bg) 70%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }
    .card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 2.5rem;
      width: 100%;
      max-width: 400px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }
    .logo-badge {
      background: linear-gradient(135deg, #6366f1, #06b6d4);
      width: 2.5rem;
      height: 2.5rem;
      border-radius: 0.75rem;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.25rem;
      font-weight: 700;
    }
    h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.025em; }
    p.sub { color: var(--text-muted); font-size: 0.875rem; margin-top: 0.25rem; }
    form { margin-top: 1.5rem; display: flex; flex-direction: column; gap: 1rem; }
    label { font-size: 0.8125rem; font-weight: 500; color: var(--text-muted); }
    input[type="password"] {
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 0.75rem 1rem;
      color: var(--text);
      font-size: 0.9375rem;
      outline: none;
      transition: border-color 0.15s;
    }
    input[type="password"]:focus { border-color: var(--primary); }
    button {
      background: var(--primary);
      color: white;
      border: none;
      border-radius: 0.5rem;
      padding: 0.75rem 1rem;
      font-size: 0.9375rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
      margin-top: 0.5rem;
    }
    button:hover { background: var(--primary-hover); }
    .err-msg {
      color: #f87171;
      font-size: 0.8125rem;
      display: none;
      margin-top: 0.5rem;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">
      <div class="logo-badge">π</div>
      <div>
        <h1>Pithon Agent</h1>
        <p class="sub">Authenticated Management Portal</p>
      </div>
    </div>
    <form id="loginForm">
      <div>
        <label for="password">Security Passphrase</label>
        <input type="password" id="password" required autofocus placeholder="Enter access passphrase">
      </div>
      <button type="submit" id="submitBtn">Unlock Dashboard</button>
      <div id="errMsg" class="err-msg">Incorrect passphrase. Please try again.</div>
    </form>
  </div>
  <script>
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const pwd = document.getElementById('password').value;
      const btn = document.getElementById('submitBtn');
      const err = document.getElementById('errMsg');
      btn.disabled = true;
      btn.innerText = 'Verifying...';
      err.style.display = 'none';

      try {
        const resp = await fetch('/api/login', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({password: pwd})
        });
        if (resp.ok) {
          window.location.href = '/';
        } else {
          err.style.display = 'block';
          btn.disabled = false;
          btn.innerText = 'Unlock Dashboard';
        }
      } catch (e) {
        err.innerText = 'Connection error. Please try again.';
        err.style.display = 'block';
        btn.disabled = false;
        btn.innerText = 'Unlock Dashboard';
      }
    });
  </script>
</body>
</html>
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pithon • Agent Command Center</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(15, 23, 42, 0.7);
      --border: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --accent-cyan: #06b6d4;
      --accent-emerald: #10b981;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      border-bottom: 1px solid var(--border);
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 50;
      padding: 0.875rem 1.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand { display: flex; align-items: center; gap: 0.75rem; }
    .badge {
      background: linear-gradient(135deg, #6366f1, #06b6d4);
      width: 2rem;
      height: 2rem;
      border-radius: 0.5rem;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
    }
    nav { display: flex; gap: 0.5rem; }
    nav button {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 0.5rem 0.875rem;
      border-radius: 0.5rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    }
    nav button:hover { color: var(--text); background: #1e293b; }
    nav button.active {
      background: #1e293b;
      color: var(--text);
      border-color: #334155;
    }
    .header-actions { display: flex; align-items: center; gap: 1rem; }
    .logout-btn {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 0.4rem 0.75rem;
      border-radius: 0.375rem;
      font-size: 0.8125rem;
      cursor: pointer;
    }
    .logout-btn:hover { color: #f87171; border-color: #7f1d1d; }
    main { flex: 1; max-width: 1200px; width: 100%; margin: 0 auto; padding: 2rem 1.5rem; }
    .grid-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      padding: 1.25rem;
      backdrop-filter: blur(8px);
    }
    .stat-label { font-size: 0.8125rem; color: var(--text-muted); margin-bottom: 0.25rem; }
    .stat-value { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.025em; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .card-box {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
    }
    .table-container { overflow-x: auto; margin-top: 1rem; }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.875rem; }
    th {
      border-bottom: 1px solid var(--border);
      color: var(--text-muted);
      padding: 0.75rem 1rem;
      font-weight: 500;
    }
    td { border-bottom: 1px solid #1e293b; padding: 0.875rem 1rem; vertical-align: top; }
    tr:hover td { background: rgba(30, 41, 59, 0.4); }
    .tag {
      display: inline-block;
      padding: 0.2rem 0.5rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .tag-green { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .tag-blue { background: rgba(6, 182, 212, 0.15); color: #38bdf8; }
    .tag-purple { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
    input[type="text"], textarea {
      width: 100%;
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 0.75rem 1rem;
      color: var(--text);
      font-size: 0.875rem;
      outline: none;
      margin-top: 0.5rem;
    }
    .btn {
      background: var(--primary);
      color: white;
      border: none;
      border-radius: 0.5rem;
      padding: 0.625rem 1rem;
      font-weight: 600;
      cursor: pointer;
      font-size: 0.875rem;
      margin-top: 0.75rem;
    }
    .btn:hover { background: #4f46e5; }
    .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.75rem; margin: 0; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="badge">π</div>
      <div>
        <h2 style="font-size: 1.125rem; font-weight: 700;">Pithon Control</h2>
      </div>
    </div>
    <nav>
      <button class="active" onclick="switchTab('overview')">Overview</button>
      <button onclick="switchTab('interactions')">Interactions</button>
      <button onclick="switchTab('tasks')">Tasks & Lists</button>
      <button onclick="switchTab('digests')">Digests</button>
      <button onclick="switchTab('playground')">Playground</button>
    </nav>
    <div class="header-actions">
      <button class="logout-btn" onclick="logout()">Logout</button>
    </div>
  </header>

  <main>
    <!-- OVERVIEW TAB -->
    <div id="tab-overview" class="tab-content active">
      <div class="grid-stats">
        <div class="stat-card">
          <div class="stat-label">Inference Daemon</div>
          <div class="stat-value" style="color: var(--accent-emerald);">Online</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">Loopback 127.0.0.1:8090</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Model Memory (RSS)</div>
          <div class="stat-value" id="statRss">~316 MB</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">Hard Cap: 2048 MB</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Interactions</div>
          <div class="stat-value" id="statInteractions">0</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">Logged in SQLite</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Pending Tasks</div>
          <div class="stat-value" id="statTasks">0</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">Reminders Active</div>
        </div>
      </div>

      <div class="card-box">
        <h3 style="font-size: 1.125rem; margin-bottom: 0.5rem;">System Architecture & Protection</h3>
        <p style="color: var(--text-muted); font-size: 0.875rem; line-height: 1.5;">
          Running isolated inside Docker with cgroup resource constraints (<code>cpus: 0.5</code>, <code>memory: 512M</code>). Co-located OwnTracks services (Mosquitto & Recorder) maintain 100% priority CPU headroom.
        </p>
      </div>
    </div>

    <!-- INTERACTIONS TAB -->
    <div id="tab-interactions" class="tab-content">
      <div class="card-box">
        <h3 style="font-size: 1.125rem;">Audit Log & Interaction Explorer</h3>
        <p style="color: var(--text-muted); font-size: 0.875rem;">Chronological history of Telegram queries, DuckDuckGo searches, and model responses.</p>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>User Prompt</th>
                <th>Web Search</th>
                <th>Model Answer</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody id="interactionsTableBody">
              <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading interactions...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TASKS TAB -->
    <div id="tab-tasks" class="tab-content">
      <div class="card-box">
        <h3 style="font-size: 1.125rem;">Active Tasks & Lists</h3>
        <p style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 1rem;">Managed via Telegram or direct web action.</p>
        <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem;">
          <input type="text" id="newTaskTitle" placeholder="Task title (e.g. Renew domain, Buy milk)" style="margin: 0; flex: 1;">
          <input type="text" id="newListCategory" placeholder="List (default, work, groceries)" style="margin: 0; width: 180px;">
          <button class="btn" style="margin: 0;" onclick="addTask()">Add Task</button>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Task Title</th>
                <th>List</th>
                <th>Due At</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="tasksTableBody">
              <tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Loading tasks...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- DIGESTS TAB -->
    <div id="tab-digests" class="tab-content">
      <div class="card-box">
        <h3 style="font-size: 1.125rem;">Hourly Digests Archive</h3>
        <p style="color: var(--text-muted); font-size: 0.875rem;">Hourly activity reports dispatched silently to group <code>-1001169201210</code>.</p>
        <div id="digestsContainer" style="margin-top: 1rem; display: flex; flex-direction: column; gap: 1rem;">
          <p style="color: var(--text-muted);">Loading digests archive...</p>
        </div>
      </div>
    </div>

    <!-- PLAYGROUND TAB -->
    <div id="tab-playground" class="tab-content">
      <div class="card-box">
        <h3 style="font-size: 1.125rem;">Live Model & Web Search Playground</h3>
        <p style="color: var(--text-muted); font-size: 0.875rem;">Test time awareness and DuckDuckGo retrieval directly in the browser.</p>
        <textarea id="playgroundPrompt" rows="3" placeholder="Ask a question (e.g. What is today's date? Or latest news about Linux kernel...)"></textarea>
        <button class="btn" id="playBtn" onclick="runPlayground()">Send Prompt</button>
        <div id="playgroundOutput" style="margin-top: 1rem; padding: 1rem; background: #0b1120; border-radius: 0.5rem; border: 1px solid var(--border); display: none; font-size: 0.9375rem; line-height: 1.5; white-space: pre-wrap;"></div>
      </div>
    </div>
  </main>

  <script>
    function switchTab(name) {
      document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      document.getElementById('tab-' + name).classList.add('active');
      event.target.classList.add('active');
      if (name === 'interactions') loadInteractions();
      if (name === 'tasks') loadTasks();
      if (name === 'digests') loadDigests();
    }

    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        if (res.ok) {
          const d = await res.json();
          document.getElementById('statInteractions').innerText = d.total_interactions || 0;
          document.getElementById('statTasks').innerText = d.pending_tasks || 0;
        }
      } catch (e) {}
    }

    async function loadInteractions() {
      const tb = document.getElementById('interactionsTableBody');
      try {
        const res = await fetch('/api/interactions');
        if (res.ok) {
          const items = await res.json();
          if (items.length === 0) {
            tb.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No interactions recorded yet.</td></tr>';
            return;
          }
          tb.innerHTML = items.map(it => `
            <tr>
              <td style="color: var(--text-muted); font-size: 0.75rem;">${it.created_at || ''}</td>
              <td style="font-weight: 500;">${escapeHtml(it.prompt)}</td>
              <td>${it.search_query ? `<span class="tag tag-blue">${escapeHtml(it.search_query)}</span>` : '<span style="color:var(--text-muted);">-</span>'}</td>
              <td style="color: #cbd5e1;">${escapeHtml(it.response)}</td>
              <td><span class="tag tag-purple">${it.latency_ms || 0}ms</span></td>
            </tr>
          `).join('');
        }
      } catch (e) {
        tb.innerHTML = '<tr><td colspan="5" style="color: #f87171;">Failed to load interactions.</td></tr>';
      }
    }

    async function loadTasks() {
      const tb = document.getElementById('tasksTableBody');
      try {
        const res = await fetch('/api/tasks');
        if (res.ok) {
          const tasks = await res.json();
          if (tasks.length === 0) {
            tb.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No tasks recorded yet.</td></tr>';
            return;
          }
          tb.innerHTML = tasks.map(t => `
            <tr>
              <td>#${t.id}</td>
              <td style="${t.is_completed ? 'text-decoration: line-through; color: var(--text-muted);' : 'font-weight: 500;'}">${escapeHtml(t.title)}</td>
              <td><span class="tag tag-blue">${t.list_name || 'default'}</span></td>
              <td style="font-size: 0.75rem; color: var(--text-muted);">${t.due_at ? t.due_at.substring(0,16).replace('T', ' ') : '-'}</td>
              <td>${t.is_completed ? '<span class="tag tag-green">Done</span>' : '<span class="tag tag-purple">Pending</span>'}</td>
              <td>
                <button class="btn btn-sm" onclick="toggleTask(${t.id})">${t.is_completed ? 'Reopen' : 'Complete'}</button>
              </td>
            </tr>
          `).join('');
        }
      } catch (e) {}
    }

    async function addTask() {
      const title = document.getElementById('newTaskTitle').value;
      const cat = document.getElementById('newListCategory').value;
      if (!title.trim()) return;
      await fetch('/api/tasks/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title, list_name: cat})
      });
      document.getElementById('newTaskTitle').value = '';
      loadTasks();
      loadStats();
    }

    async function toggleTask(id) {
      await fetch('/api/tasks/toggle', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id})
      });
      loadTasks();
      loadStats();
    }

    async function loadDigests() {
      const c = document.getElementById('digestsContainer');
      try {
        const res = await fetch('/api/digests');
        if (res.ok) {
          const items = await res.json();
          if (items.length === 0) {
            c.innerHTML = '<p style="color: var(--text-muted);">No digests logged yet.</p>';
            return;
          }
          c.innerHTML = items.map(d => `
            <div style="background: #0b1120; border: 1px solid var(--border); border-radius: 0.5rem; padding: 1rem; font-size: 0.875rem; white-space: pre-wrap;">${escapeHtml(d.summary_text)}</div>
          `).join('');
        }
      } catch (e) {}
    }

    async function runPlayground() {
      const p = document.getElementById('playgroundPrompt').value;
      const btn = document.getElementById('playBtn');
      const out = document.getElementById('playgroundOutput');
      if (!p.trim()) return;
      btn.disabled = true;
      btn.innerText = 'Evaluating...';
      out.style.display = 'block';
      out.innerText = 'Consulting temporal grounding & live web search...';

      try {
        const res = await fetch('/api/playground', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({prompt: p})
        });
        const d = await res.json();
        out.innerText = d.response || 'No response returned.';
      } catch (e) {
        out.innerText = 'Error calling model: ' + e;
      } finally {
        btn.disabled = false;
        btn.innerText = 'Send Prompt';
      }
    }

    async function logout() {
      await fetch('/api/logout', {method: 'POST'});
      window.location.href = '/login';
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    loadStats();
  </script>
</body>
</html>
"""

# --- WEB SERVER HANDLER IMPLEMENTATION ---

def create_web_server(
    storage: Any,
    admin_password: str,
    host: str = "0.0.0.0",
    port: int = 8080,
    daemon_url: str = "http://127.0.0.1:8090",
    tz_name: str = "Asia/Kolkata"
) -> HTTPServer:
    """Create HTTP Server instance with session authentication."""

    class PithonWebHandler(BaseHTTPRequestHandler):
        def _get_cookie_session(self) -> Optional[str]:
            cookie_hdr = self.headers.get("Cookie", "")
            if not cookie_hdr:
                return None
            c = http.cookies.SimpleCookie(cookie_hdr)
            if "pithon_session" in c:
                return c["pithon_session"].value
            return None

        def _is_authenticated(self) -> bool:
            token = self._get_cookie_session()
            if not token or not storage:
                return False
            return storage.validate_session(token)

        def _send_html(self, html_content: str, status: int = 200) -> None:
            data = html_content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: Any, status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if headers:
                for k, v in headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> Dict[str, Any]:
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len == 0:
                return {}
            raw = self.rfile.read(content_len)
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}

        def do_GET(self) -> None:
            path = urllib.parse.urlparse(self.path).path

            if path == "/login":
                self._send_html(LOGIN_HTML)
                return

            # Protected routes require valid session
            if not self._is_authenticated():
                # Redirect to /login
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
                return

            if path == "/":
                self._send_html(DASHBOARD_HTML)
            elif path == "/api/stats":
                interactions = storage.get_interactions(limit=100) if storage else []
                tasks = storage.get_tasks("357035668", include_completed=False) if storage else []
                self._send_json({
                    "status": "ok",
                    "total_interactions": len(interactions),
                    "pending_tasks": len(tasks),
                    "daemon_url": daemon_url
                })
            elif path == "/api/interactions":
                items = storage.get_interactions(limit=50) if storage else []
                self._send_json(items)
            elif path == "/api/tasks":
                tasks = storage.get_tasks("357035668", include_completed=True) if storage else []
                self._send_json(tasks)
            elif path == "/api/digests":
                digests = storage.get_digests(limit=24) if storage else []
                self._send_json(digests)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self) -> None:
            path = urllib.parse.urlparse(self.path).path

            if path == "/api/login":
                body = self._read_json_body()
                submitted_pwd = body.get("password", "")
                if secrets.compare_digest(submitted_pwd, admin_password):
                    token = secrets.token_urlsafe(32)
                    if storage:
                        storage.create_session(token, expires_in_sec=604800)
                    cookie = f"pithon_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"
                    self._send_json({"status": "ok"}, headers={"Set-Cookie": cookie})
                else:
                    self._send_json({"error": "Invalid passphrase"}, status=401)
                return

            if path == "/api/logout":
                token = self._get_cookie_session()
                if token and storage:
                    storage.delete_session(token)
                cookie = "pithon_session=; Path=/; HttpOnly; Max-Age=0"
                self._send_json({"status": "ok"}, headers={"Set-Cookie": cookie})
                return

            # Protected POST routes
            if not self._is_authenticated():
                self._send_json({"error": "Unauthorized"}, status=401)
                return

            if path == "/api/tasks/toggle":
                body = self._read_json_body()
                tid = body.get("id")
                if tid and storage:
                    task = storage.get_task_by_id(int(tid))
                    if task:
                        new_state = 0 if task["is_completed"] else 1
                        with storage._lock, storage._get_connection() as conn:
                            conn.execute("UPDATE tasks SET is_completed = ? WHERE id = ?", (new_state, int(tid)))
                self._send_json({"status": "ok"})

            elif path == "/api/tasks/add":
                body = self._read_json_body()
                title = body.get("title", "").strip()
                list_name = body.get("list_name", "default").strip()
                if title and storage:
                    storage.create_task("357035668", title, list_name=list_name)
                self._send_json({"status": "ok"})

            elif path == "/api/playground":
                body = self._read_json_body()
                prompt = body.get("prompt", "").strip()
                if not prompt:
                    self._send_json({"error": "Empty prompt"}, status=400)
                    return

                # Run live search if warranted
                search_block = ""
                if should_search(prompt):
                    results = search_duckduckgo(prompt, max_results=3)
                    search_block = format_search_context(results, prompt)

                temporal = format_temporal_prompt_header(tz_name)
                full_prompt = f"{temporal}\n{search_block}User Question: {prompt}\nAnswer directly."

                # Call daemon
                try:
                    payload = {
                        "messages": [{"role": "user", "content": full_prompt}],
                        "max_tokens": 512,
                        "temperature": 0.2
                    }
                    req = urllib.request.Request(
                        f"{daemon_url}/v1/chat/completions",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=30.0) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        answer = res_data["choices"][0]["message"]["content"].strip()
                except Exception as e:
                    answer = f"Error querying local model: {e}"

                self._send_json({"response": answer})
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = HTTPServer((host, port), PithonWebHandler)
    return server
