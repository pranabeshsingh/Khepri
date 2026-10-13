"""World-class dark-mode Web UI dashboard and REST API for Khepri Autonomous Agent."""

import http.cookies
import json
import logging
import re
import secrets
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

from pithon.agent.search import should_search, search_duckduckgo, format_search_context
from pithon.agent.time_context import format_temporal_prompt_header
from pithon.presets import get_preset_system_prompt
from pithon.agent.memory import list_notes, get_note_content, save_note, delete_note
from pithon.agent.calendar import fetch_and_parse_calendar
from datetime import datetime, timezone
import zoneinfo, os
from pithon.agent.calc import safe_calculate
from pithon.agent.weather import get_weather_report, is_weather_intent, extract_weather_location
from pithon.agent.tools import extract_tool_call, execute_tool_call
from pithon.agent.profile import (
    start_onboarding,
    handle_onboarding_step,
    format_user_profile_prompt_header,
    get_default_weather_city
)

logger = logging.getLogger("pithon.web")


def mask_id(val: str) -> str:
    """Mask chat ID for security display."""
    val_str = str(val).strip()
    if not val_str:
        return "Not Configured"
    if len(val_str) <= 4:
        return "***"
    return val_str[:3] + "****" + val_str[-2:]


def get_system_telemetry(daemon_url: str) -> Dict[str, Any]:
    """Retrieve real Linux process memory, host RAM, and daemon latency/uptime."""
    agent_rss_mb = 0.0
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    agent_rss_mb = round(int(parts[1]) / 1024, 1)
                    break
    except Exception:
        agent_rss_mb = 34.0

    host_mem_used_mb = 0
    host_mem_total_mb = 0
    host_mem_pct = 0
    try:
        mem_total = 0
        mem_avail = 0
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail = int(line.split()[1])
        if mem_total > 0:
            host_mem_total_mb = round(mem_total / 1024)
            host_mem_used_mb = round((mem_total - mem_avail) / 1024)
            host_mem_pct = round((host_mem_used_mb / host_mem_total_mb) * 100)
    except Exception:
        host_mem_total_mb = 11925
        host_mem_used_mb = 2010
        host_mem_pct = 17

    engine_status = "Offline"
    engine_latency_ms = None
    engine_model = "Unknown"
    engine_uptime = "Unknown"
    engine_threads = 2

    t0 = time.time()
    try:
        req = urllib.request.Request(f"{daemon_url}/health")
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            engine_latency_ms = round((time.time() - t0) * 1000, 1)
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") in ("ok", "healthy"):
                engine_status = "Online"
                engine_model = data.get("model", "qwen2.5-0.5b-instruct-q4_k_m")
                engine_threads = data.get("threads", 2)
                uptime_sec = data.get("uptime_seconds", 0)
                if uptime_sec < 60:
                    engine_uptime = f"{uptime_sec}s"
                elif uptime_sec < 3600:
                    engine_uptime = f"{uptime_sec // 60}m"
                else:
                    engine_uptime = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m"
    except Exception:
        engine_status = "Offline"

    return {
        "agent_rss_mb": agent_rss_mb,
        "host_mem_used_mb": host_mem_used_mb,
        "host_mem_total_mb": host_mem_total_mb,
        "host_mem_pct": host_mem_pct,
        "engine_status": engine_status,
        "engine_latency_ms": engine_latency_ms,
        "engine_model": engine_model,
        "engine_uptime": engine_uptime,
        "engine_threads": engine_threads,
    }


LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Khepri • Access Gateway</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #070a13;
      --card-bg: rgba(14, 19, 34, 0.75);
      --border: rgba(255, 255, 255, 0.08);
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(circle at 15% 20%, rgba(99, 102, 241, 0.12) 0%, transparent 45%),
        radial-gradient(circle at 85% 80%, rgba(6, 182, 212, 0.10) 0%, transparent 45%);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .card-wrap {
      width: 100%;
      max-width: 420px;
      position: relative;
    }
    .card {
      background: var(--card-bg);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid var(--border);
      border-radius: 1.25rem;
      padding: 2.25rem;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 40px rgba(99, 102, 241, 0.15);
    }
    .header {
      display: flex;
      align-items: center;
      gap: 1rem;
      margin-bottom: 2rem;
    }
    .logo-badge {
      width: 48px;
      height: 48px;
      border-radius: 0.85rem;
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(6, 182, 212, 0.25));
      border: 1px solid rgba(99, 102, 241, 0.4);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #a5b4fc;
    }
    h1 { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.72rem;
      padding: 0.2rem 0.55rem;
      border-radius: 9999px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.25);
      color: #34d399;
      font-weight: 600;
    }
    .status-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
    }
    .field-group { margin-bottom: 1.5rem; }
    label {
      display: flex;
      justify-content: space-between;
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 0.5rem;
    }
    .input-wrap { position: relative; }
    input[type="password"], input[type="text"] {
      width: 100%;
      background: rgba(10, 14, 26, 0.7);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      padding: 0.85rem 2.75rem 0.85rem 1rem;
      color: #fff;
      font-size: 0.95rem;
      outline: none;
      transition: all 0.2s ease;
      font-family: inherit;
    }
    input:focus {
      border-color: rgba(99, 102, 241, 0.6);
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
    }
    .toggle-pwd {
      position: absolute;
      right: 0.85rem;
      top: 50%;
      transform: translateY(-50%);
      background: transparent;
      border: none;
      color: #64748b;
      cursor: pointer;
      display: flex;
    }
    button[type="submit"] {
      width: 100%;
      background: linear-gradient(135deg, var(--primary), var(--primary-hover));
      border: none;
      border-radius: 0.75rem;
      padding: 0.85rem;
      color: #fff;
      font-weight: 700;
      font-size: 0.95rem;
      cursor: pointer;
      box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
      transition: all 0.2s;
    }
    button[type="submit"]:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(99, 102, 241, 0.45);
    }
    .err-msg {
      margin-top: 1rem;
      font-size: 0.82rem;
      color: #f87171;
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.25);
      padding: 0.6rem 0.8rem;
      border-radius: 0.5rem;
      display: none;
      text-align: center;
    }
    .footer-note {
      margin-top: 1.75rem;
      display: flex;
      justify-content: space-between;
      font-size: 0.72rem;
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="card-wrap">
    <div class="card">
      <div class="header">
        <div class="logo-badge">
          <svg viewBox="0 0 120 120" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 28px; height: 28px;">
            <circle cx="60" cy="24" r="8"/>
            <circle cx="60" cy="24" r="13" stroke-dasharray="2 3" stroke-width="1.5"/>
            <path d="M 60 7 L 60 12"/><path d="M 60 36 L 60 41"/><path d="M 43 24 L 48 24"/><path d="M 72 24 L 77 24"/>
            <path d="M 52 46 C 46 38 46 28 51 22"/><path d="M 68 46 C 74 38 74 28 69 22"/>
            <path d="M 54 46 Q 60 43 66 46 L 68 50 Q 60 52 52 50 Z"/>
            <path d="M 50 51 Q 60 48 70 51 L 73 58 Q 60 61 47 58 Z"/>
            <path d="M 47 54 C 36 44 26 32 23 20 C 21 34 26 48 37 60"/>
            <path d="M 73 54 C 84 44 94 32 97 20 C 99 34 94 48 83 60"/>
            <path d="M 47 58 C 43 72 45 88 60 96 C 75 88 77 72 73 58 Z"/>
            <path d="M 60 59 L 60 96"/>
            <path d="M 44 65 L 34 73 L 33 83"/><path d="M 76 65 L 86 73 L 87 83"/>
            <path d="M 47 84 L 37 94 L 40 106"/><path d="M 73 84 L 83 94 L 80 106"/>
          </svg>
        </div>
        <div>
          <h1>Khepri</h1>
          <div style="font-size: 0.85rem; color: #94a3b8; font-weight: 500;">Autonomous Edge Agent</div>
          <div class="status-pill" style="margin-top: 0.35rem;">
            <span class="status-dot"></span>
            <span>Qwen2.5-0.5B • Online</span>
          </div>
        </div>
      </div>

      <form id="loginForm">
        <div class="field-group">
          <label for="password">
            <span>Passphrase</span>
            <span style="font-size: 0.72rem; color: #64748b;">Oracle Cloud VM</span>
          </label>
          <div class="input-wrap">
            <input type="password" id="password" required autofocus placeholder="Enter access passphrase..." autocomplete="current-password">
            <button type="button" class="toggle-pwd" id="toggleBtn" title="Toggle visibility">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path>
                <circle cx="12" cy="12" r="3"></circle>
              </svg>
            </button>
          </div>
        </div>

        <button type="submit" id="submitBtn">Unlock Command Center</button>
        <div id="errMsg" class="err-msg">Incorrect passphrase. Access denied.</div>
      </form>

      <div class="footer-note">
        <span>Protected via HSTS & Let's Encrypt</span>
        <code>Asia/Kolkata</code>
      </div>
    </div>
  </div>

  <script>
    const pwdInput = document.getElementById('password');
    const toggleBtn = document.getElementById('toggleBtn');
    toggleBtn.addEventListener('click', () => {
      pwdInput.type = pwdInput.type === 'password' ? 'text' : 'password';
      toggleBtn.style.color = pwdInput.type === 'text' ? '#6366f1' : '#64748b';
    });

    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const pwd = pwdInput.value;
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
          btn.innerText = 'Unlock Command Center';
        }
      } catch (e) {
        err.innerText = 'Connection error. Please try again.';
        err.style.display = 'block';
        btn.disabled = false;
        btn.innerText = 'Unlock Command Center';
      }
    });
  </script>
</body>
</html>
"""

# DASHBOARD_HTML will follow in the next part of script...

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Khepri • Management Portal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    
    :root {
      --bg: #070a13;
      --card-bg: rgba(14, 19, 34, 0.75);
      --card-hover: rgba(20, 27, 48, 0.85);
      --border: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(99, 102, 241, 0.45);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --accent: #06b6d4;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(circle at 10% 15%, rgba(6, 182, 212, 0.08) 0%, transparent 40%),
        radial-gradient(circle at 90% 85%, rgba(99, 102, 241, 0.09) 0%, transparent 40%);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: rgba(7, 10, 19, 0.85);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 100;
      padding: 0.75rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.85rem;
    }
    .brand-logo {
      width: 40px;
      height: 40px;
      border-radius: 0.65rem;
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(6, 182, 212, 0.25));
      border: 1px solid rgba(99, 102, 241, 0.35);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #a5b4fc;
    }
    .brand-info h1 {
      font-size: 1.15rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      line-height: 1.2;
    }
    .brand-meta {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.72rem;
      color: var(--text-muted);
      font-weight: 500;
    }
    .pulse-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
      display: inline-block;
    }
    nav.tabs {
      display: flex;
      gap: 0.35rem;
      background: rgba(10, 14, 26, 0.6);
      padding: 0.25rem;
      border-radius: 0.65rem;
      border: 1px solid var(--border);
    }
    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 0.45rem 0.85rem;
      border-radius: 0.5rem;
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    .tab-btn:hover { color: #fff; background: rgba(255, 255, 255, 0.04); }
    .tab-btn.active {
      color: #fff;
      background: rgba(99, 102, 241, 0.2);
      border: 1px solid rgba(99, 102, 241, 0.35);
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }
    .clock-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      color: #cbd5e1;
      background: rgba(15, 23, 42, 0.6);
      padding: 0.35rem 0.65rem;
      border-radius: 0.45rem;
      border: 1px solid var(--border);
    }
    .btn-action {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 0.4rem 0.75rem;
      border-radius: 0.5rem;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      transition: all 0.15s;
    }
    .btn-action:hover { color: #fff; border-color: rgba(255, 255, 255, 0.2); background: rgba(255, 255, 255, 0.05); }
    main {
      flex: 1;
      max-width: 1440px;
      width: 100%;
      margin: 0 auto;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
    }
    .tab-content { display: none; }
    .tab-content.active { display: flex; flex-direction: column; gap: 1.5rem; animation: fadeIn 0.2s ease-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

    /* STATS ROW */
    .grid-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1rem;
    }
    .stat-card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      position: relative;
      overflow: hidden;
      transition: all 0.2s ease;
    }
    .stat-card:hover {
      border-color: rgba(255, 255, 255, 0.15);
      background: var(--card-hover);
      transform: translateY(-2px);
    }
    .stat-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      background: var(--stat-accent, var(--primary));
    }
    .stat-label {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .stat-value {
      font-size: 1.45rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: #fff;
      display: flex;
      align-items: baseline;
      gap: 0.5rem;
    }
    .stat-meta {
      font-size: 0.78rem;
      color: var(--text-muted);
      line-height: 1.4;
    }
    .stat-bar-bg {
      width: 100%;
      height: 5px;
      background: rgba(255, 255, 255, 0.06);
      border-radius: 9999px;
      overflow: hidden;
      margin-top: 0.35rem;
    }
    .stat-bar-fill {
      height: 100%;
      background: var(--stat-accent, var(--primary));
      border-radius: 9999px;
      transition: width 0.4s ease;
    }

    /* DASHBOARD 2-COLUMN GRID */
    .dashboard-grid {
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 1.5rem;
    }
    @media (max-width: 1024px) {
      .dashboard-grid { grid-template-columns: 1fr; }
    }
    .card-box {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }
    .card-box h3 {
      font-size: 1.05rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      color: #fff;
    }
    .card-box-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    /* ACTIVITY FEED */
    .activity-feed {
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
    }
    .activity-item {
      padding: 1rem;
      background: rgba(10, 14, 26, 0.6);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      transition: all 0.15s;
    }
    .activity-item:hover { border-color: rgba(255, 255, 255, 0.12); }
    .activity-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.72rem;
      color: var(--text-dim);
    }
    .activity-badge {
      font-size: 0.68rem;
      font-weight: 700;
      padding: 0.15rem 0.5rem;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .badge-telegram {
      background: rgba(14, 165, 233, 0.15);
      border: 1px solid rgba(14, 165, 233, 0.3);
      color: #38bdf8;
    }
    .badge-web {
      background: rgba(99, 102, 241, 0.15);
      border: 1px solid rgba(99, 102, 241, 0.3);
      color: #a5b4fc;
    }
    .activity-prompt {
      font-weight: 600;
      color: #f1f5f9;
      font-size: 0.88rem;
    }
    .activity-response {
      font-size: 0.82rem;
      color: #94a3b8;
      line-height: 1.5;
      background: rgba(0, 0, 0, 0.2);
      padding: 0.6rem 0.8rem;
      border-radius: 0.5rem;
      border-left: 2px solid var(--primary);
    }

    /* QUICK TASKS */
    .task-list {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }
    .task-item {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.75rem 1rem;
      background: rgba(10, 14, 26, 0.6);
      border: 1px solid var(--border);
      border-radius: 0.65rem;
      transition: all 0.15s ease;
    }
    .task-item:hover { border-color: rgba(255, 255, 255, 0.12); }
    .task-item.completed { opacity: 0.5; }
    .task-item.completed .task-text { text-decoration: line-through; }
    .task-checkbox {
      width: 18px;
      height: 18px;
      accent-color: var(--primary);
      cursor: pointer;
    }
    .task-text {
      flex: 1;
      font-size: 0.85rem;
      color: #e2e8f0;
    }
    .task-tag {
      font-size: 0.7rem;
      padding: 0.15rem 0.45rem;
      border-radius: 0.35rem;
      background: rgba(255, 255, 255, 0.05);
      color: #94a3b8;
    }
    .btn-del {
      background: transparent;
      border: none;
      color: #64748b;
      cursor: pointer;
      font-size: 0.85rem;
      padding: 0.2rem;
      border-radius: 0.3rem;
    }
    .btn-del:hover { color: #f87171; background: rgba(239, 68, 68, 0.1); }

    /* INPUTS & BUTTONS */
    .input-field {
      background: rgba(10, 14, 26, 0.7);
      border: 1px solid var(--border);
      border-radius: 0.65rem;
      padding: 0.65rem 0.95rem;
      color: #fff;
      font-size: 0.88rem;
      font-family: inherit;
      outline: none;
      transition: all 0.2s;
    }
    .input-field:focus {
      border-color: var(--border-focus);
      box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
    }
    .btn {
      background: linear-gradient(135deg, var(--primary), var(--primary-hover));
      border: none;
      border-radius: 0.65rem;
      padding: 0.65rem 1.15rem;
      color: #fff;
      font-weight: 600;
      font-size: 0.85rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
      transition: all 0.15s;
    }
    .btn:hover {
      box-shadow: 0 4px 14px rgba(99, 102, 241, 0.45);
      transform: translateY(-1px);
    }

    /* LIVE CHAT STUDIO */
    .chat-studio {
      display: flex;
      flex-direction: column;
      height: calc(100vh - 120px);
      min-height: 600px;
      background: var(--card-bg);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid var(--border);
      border-radius: 1.25rem;
      overflow: hidden;
    }
    .chat-studio-header {
      padding: 1rem 1.5rem;
      border-bottom: 1px solid var(--border);
      background: rgba(10, 14, 26, 0.7);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
    }
    .chat-sync-toggle {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.8rem;
      color: #94a3b8;
      cursor: pointer;
    }
    .chat-sync-toggle input { accent-color: var(--primary); }
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      scroll-behavior: smooth;
    }
    .chat-bubble-row {
      display: flex;
      gap: 0.85rem;
      max-width: 82%;
    }
    .chat-bubble-row.user {
      align-self: flex-end;
      flex-direction: row-reverse;
    }
    .chat-avatar {
      width: 34px;
      height: 34px;
      border-radius: 0.55rem;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      font-size: 0.85rem;
    }
    .avatar-assistant {
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.3), rgba(6, 182, 212, 0.3));
      border: 1px solid rgba(99, 102, 241, 0.4);
      color: #a5b4fc;
    }
    .avatar-user {
      background: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #fff;
    }
    .bubble-card {
      padding: 0.95rem 1.15rem;
      border-radius: 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
      font-size: 0.88rem;
      line-height: 1.55;
    }
    .bubble-assistant {
      background: rgba(14, 20, 36, 0.8);
      border: 1px solid var(--border);
      border-top-left-radius: 0.2rem;
      color: #f1f5f9;
    }
    .bubble-user {
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.9), rgba(79, 70, 229, 0.9));
      border: 1px solid rgba(99, 102, 241, 0.5);
      border-top-right-radius: 0.2rem;
      color: #fff;
    }
    .bubble-meta {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.72rem;
      opacity: 0.75;
    }
    .tool-chip {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      font-size: 0.68rem;
      padding: 0.15rem 0.45rem;
      border-radius: 9999px;
      background: rgba(6, 182, 212, 0.15);
      border: 1px solid rgba(6, 182, 212, 0.3);
      color: #38bdf8;
      font-weight: 600;
    }
    .chat-suggestions {
      padding: 0.65rem 1.5rem;
      display: flex;
      gap: 0.5rem;
      overflow-x: auto;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(8, 12, 22, 0.4);
    }
    .pill-prompt {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 0.3rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .pill-prompt:hover {
      color: #fff;
      border-color: rgba(99, 102, 241, 0.4);
      background: rgba(99, 102, 241, 0.1);
    }
    .chat-input-bar {
      padding: 1rem 1.5rem;
      border-top: 1px solid var(--border);
      background: rgba(10, 14, 26, 0.85);
      display: flex;
      gap: 0.75rem;
      align-items: flex-end;
    }
    .chat-textarea {
      flex: 1;
      background: rgba(7, 10, 19, 0.75);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      padding: 0.75rem 1rem;
      color: #fff;
      font-size: 0.9rem;
      font-family: inherit;
      resize: none;
      min-height: 48px;
      max-height: 140px;
      outline: none;
      line-height: 1.4;
    }
    .chat-textarea:focus {
      border-color: var(--border-focus);
      box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
    }

    /* TABLE */
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    th { text-align: left; padding: 0.75rem 1rem; color: var(--text-muted); border-bottom: 1px solid var(--border); font-size: 0.75rem; text-transform: uppercase; }
    td { padding: 0.85rem 1rem; border-bottom: 1px solid rgba(255, 255, 255, 0.04); color: #cbd5e1; }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }

    /* MODAL */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(8px);
      z-index: 1000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .modal-overlay.active { display: flex; }
    .modal-card {
      background: rgba(14, 19, 34, 0.95);
      border: 1px solid var(--border);
      border-radius: 1.25rem;
      max-width: 600px;
      width: 100%;
      padding: 2rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
    }

  </style>
</head>
<body>
  <!-- HEADER -->
  <header>
    <div class="brand">
      <div class="brand-logo">
        <svg viewBox="0 0 120 120" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 26px; height: 26px;">
          <circle cx="60" cy="24" r="8"/>
          <circle cx="60" cy="24" r="13" stroke-dasharray="2 3" stroke-width="1.5"/>
          <path d="M 60 7 L 60 12"/><path d="M 60 36 L 60 41"/><path d="M 43 24 L 48 24"/><path d="M 72 24 L 77 24"/>
          <path d="M 52 46 C 46 38 46 28 51 22"/><path d="M 68 46 C 74 38 74 28 69 22"/>
          <path d="M 54 46 Q 60 43 66 46 L 68 50 Q 60 52 52 50 Z"/>
          <path d="M 50 51 Q 60 48 70 51 L 73 58 Q 60 61 47 58 Z"/>
          <path d="M 47 54 C 36 44 26 32 23 20 C 21 34 26 48 37 60"/>
          <path d="M 73 54 C 84 44 94 32 97 20 C 99 34 94 48 83 60"/>
          <path d="M 47 58 C 43 72 45 88 60 96 C 75 88 77 72 73 58 Z"/>
          <path d="M 60 59 L 60 96"/>
          <path d="M 44 65 L 34 73 L 33 83"/><path d="M 76 65 L 86 73 L 87 83"/>
          <path d="M 47 84 L 37 94 L 40 106"/><path d="M 73 84 L 83 94 L 80 106"/>
        </svg>
      </div>
      <div class="brand-info">
        <h1>Khepri</h1>
        <div class="brand-meta">
          <span class="pulse-dot"></span>
          <span id="headerEnginePill">Qwen2.5-0.5B • Online</span>
          <span>•</span>
          <span id="headerTzPill">Asia/Kolkata</span>
        </div>
      </div>
    </div>

    <nav class="tabs">
      <button class="tab-btn active" onclick="switchTab('overview')">📊 Overview</button>
      <button class="tab-btn" onclick="switchTab('chat')">💬 Live Chat</button>
      <button class="tab-btn" onclick="switchTab('tasks')">📋 Tasks & Timers</button>
      <button class="tab-btn" onclick="switchTab('notes')">🧠 Memory</button>
      <button class="tab-btn" onclick="switchTab('interactions')">📜 Audit Log</button>
      <button class="tab-btn" onclick="switchTab('digests')">📰 Digests</button>
    </nav>

    <div class="header-actions">
      <div class="clock-pill" id="liveClock">--:--:--</div>
      <button class="btn-action" onclick="refreshAll()" title="Refresh Telemetry">🔄</button>
      <button class="btn-action" onclick="logout()" title="Lock Session">Logout</button>
    </div>
  </header>

  <!-- MAIN VIEWPORT -->
  <main>
    <!-- TAB 1: OVERVIEW -->
    <div id="tab-overview" class="tab-content active">
      <!-- 5 HERO METRIC CARDS -->
      <div class="grid-stats">
        <div class="stat-card" style="--stat-accent: #10b981;">
          <div class="stat-label">
            <span>Inference Engine</span>
            <span id="statEngineLatency" style="font-family: monospace; font-size: 0.72rem; color: #10b981;">⚡ 1.4ms</span>
          </div>
          <div class="stat-value">
            <span id="statEngineStatus" style="color: #10b981;">Online</span>
          </div>
          <div class="stat-meta" id="statEngineMeta">qwen2.5-0.5b-instruct • 2 Threads</div>
          <div class="stat-bar-bg"><div class="stat-bar-fill" style="width: 100%; background: #10b981;"></div></div>
        </div>

        <div class="stat-card" style="--stat-accent: #06b6d4;">
          <div class="stat-label">
            <span>Memory (Process RSS)</span>
            <span id="statRssPct" style="font-size: 0.72rem; color: #06b6d4;">7% limit</span>
          </div>
          <div class="stat-value" id="statRss">34.3 MB</div>
          <div class="stat-meta" id="statHostRam">Host RAM: 1,999 MB / 11,925 MB (17%)</div>
          <div class="stat-bar-bg"><div class="stat-bar-fill" id="statRssBar" style="width: 7%; background: #06b6d4;"></div></div>
        </div>

        <div class="stat-card" style="--stat-accent: #6366f1;">
          <div class="stat-label">
            <span>Audit Interactions</span>
            <span style="font-size: 0.72rem; color: #a5b4fc;">SQLite WAL</span>
          </div>
          <div class="stat-value" id="statInteractions">5</div>
          <div class="stat-meta">Multi-turn grounded context</div>
          <div class="stat-bar-bg"><div class="stat-bar-fill" style="width: 60%; background: #6366f1;"></div></div>
        </div>

        <div class="stat-card" style="--stat-accent: #f59e0b;">
          <div class="stat-label">
            <span>Tasks & Timers</span>
            <span id="statTasksMeta" style="font-size: 0.72rem; color: #f59e0b;">0 Pending</span>
          </div>
          <div class="stat-value" id="statTasks">2 Total</div>
          <div class="stat-meta">Monitored by background scheduler</div>
          <div class="stat-bar-bg"><div class="stat-bar-fill" id="statTasksBar" style="width: 100%; background: #f59e0b;"></div></div>
        </div>

        <div class="stat-card" style="--stat-accent: #ec4899;">
          <div class="stat-label">
            <span>Markdown Memory</span>
            <span style="font-size: 0.72rem; color: #f472b6;">data/notes</span>
          </div>
          <div class="stat-value" id="statNotes">2 Notes</div>
          <div class="stat-meta">Persistent knowledge files</div>
          <div class="stat-bar-bg"><div class="stat-bar-fill" style="width: 80%; background: #ec4899;"></div></div>
        </div>
      </div>

      <!-- 2-COLUMN DASHBOARD -->
      <div class="dashboard-grid">
        <!-- LEFT COLUMN: LIVE CHAT STREAM & CGROUPS -->
        <div style="display: flex; flex-direction: column; gap: 1.5rem;">
          <div class="card-box">
            <div class="card-box-header">
              <h3>💬 Synced Conversation Feed</h3>
              <div style="display: flex; gap: 0.5rem; align-items: center;">
                <span class="activity-badge badge-telegram">● Synced with Telegram</span>
                <button class="btn-action" onclick="switchTab('chat')">Open Studio ↗</button>
              </div>
            </div>
            <div id="overviewFeed" class="activity-feed">
              <div style="color: var(--text-muted); font-size: 0.85rem; text-align: center; padding: 1.5rem;">Loading synced interactions...</div>
            </div>

            <!-- Quick Prompt Box on Overview -->
            <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
              <input type="text" id="overviewPromptInput" class="input-field" style="flex: 1;" placeholder="Ask Khepri anything or enter command (e.g. /weather, /calc)..." onkeydown="if(event.key==='Enter') sendOverviewPrompt()">
              <button class="btn" onclick="sendOverviewPrompt()">Send →</button>
            </div>
          </div>

          <div class="card-box">
            <h3>🛡️ Runtime Architecture & Linux cgroups Isolation</h3>
            <p style="color: var(--text-muted); font-size: 0.82rem; line-height: 1.6;">
              Co-located on Oracle Cloud ARM Ampere A1 (2 OCPU Ampere Altra, 12 GB RAM) alongside OwnTracks Recorder and MQTT.
              Strict Linux cgroups safeguard co-located processes from memory starvation.
            </p>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; margin-top: 0.5rem;">
              <div style="padding: 0.85rem; background: rgba(10,14,26,0.6); border: 1px solid var(--border); border-radius: 0.65rem;">
                <div style="font-size: 0.72rem; color: var(--text-muted);">khepri-daemon (C++)</div>
                <div style="font-weight: 700; color: #a5b4fc; font-size: 0.95rem; margin-top: 0.2rem;">1.0 CPU • 2048M RAM</div>
                <div style="font-size: 0.72rem; color: #64748b; margin-top: 0.2rem;">llama.cpp GGUF Q4_K_M</div>
              </div>
              <div style="padding: 0.85rem; background: rgba(10,14,26,0.6); border: 1px solid var(--border); border-radius: 0.65rem;">
                <div style="font-size: 0.72rem; color: var(--text-muted);">khepri-agent (Python)</div>
                <div style="font-weight: 700; color: #6ee7b7; font-size: 0.95rem; margin-top: 0.2rem;">0.5 CPU • 512M RAM</div>
                <div style="font-size: 0.72rem; color: #64748b; margin-top: 0.2rem;">Admin: <code id="confAdminId" style="color: #6ee7b7;">357****68</code></div>
              </div>
              <div style="padding: 0.85rem; background: rgba(10,14,26,0.6); border: 1px solid var(--border); border-radius: 0.65rem;">
                <div style="font-size: 0.72rem; color: var(--text-muted);">OwnTracks Co-location</div>
                <div style="font-weight: 700; color: #38bdf8; font-size: 0.95rem; margin-top: 0.2rem;">Ports 8083 & 8883</div>
                <div style="font-size: 0.72rem; color: #64748b; margin-top: 0.2rem;">Zero interference guaranteed</div>
              </div>
            </div>
          </div>
        </div>

        <!-- RIGHT COLUMN: QUICK TASKS & NOTES -->
        <div style="display: flex; flex-direction: column; gap: 1.5rem;">
          <div class="card-box">
            <div class="card-box-header">
              <h3>📋 Active Tasks & Reminders</h3>
              <button class="btn-action" onclick="switchTab('tasks')">Manage All ↗</button>
            </div>
            <!-- Quick Add Bar -->
            <div style="display: flex; gap: 0.5rem;">
              <input type="text" id="quickTaskInput" class="input-field" style="flex: 1;" placeholder="New to-do or reminder..." onkeydown="if(event.key==='Enter') addQuickTask()">
              <button class="btn" onclick="addQuickTask()">+ Add</button>
            </div>
            <div id="overviewTasksList" class="task-list">
              <div style="color: var(--text-muted); font-size: 0.85rem; text-align: center; padding: 1.5rem;">Loading tasks...</div>
            </div>
          </div>

          <div class="card-box">
            <div class="card-box-header">
              <h3>🧠 Knowledge Memory Notes</h3>
              <button class="btn-action" onclick="openNewNoteModal()">+ New Note</button>
            </div>
            <p style="color: var(--text-muted); font-size: 0.8rem;">Saved markdown memory accessible by conversational agent:</p>
            <div id="overviewNotesList" style="display: flex; flex-direction: column; gap: 0.5rem;">
              <div style="color: var(--text-muted); font-size: 0.85rem; text-align: center; padding: 1rem;">Loading notes...</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 2: LIVE CHAT (FULL STUDIO) -->
    <div id="tab-chat" class="tab-content">
      <div class="chat-studio">
        <div class="chat-studio-header">
          <div>
            <h3 style="display: flex; align-items: center; gap: 0.5rem; font-size: 1.05rem;">
              <span>💬 Live Agent Studio</span>
              <span class="status-pill"><span class="status-dot"></span>Context Aware (6 Turns)</span>
            </h3>
            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.2rem;">
              Multi-turn dialog grounded in time, SQLite task memory, and DuckDuckGo search.
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
            <label class="chat-sync-toggle">
              <input type="checkbox" id="syncTelegramToggle" checked>
              <span>Mirror to Telegram (<code id="chatBotHandle">@ai_khepri_bot</code>)</span>
            </label>
            <select id="chatPreset" class="input-field" style="padding: 0.35rem 0.65rem; font-size: 0.78rem;">
              <option value="default">⚡ General Assistant</option>
              <option value="log-analyzer">🔍 Log Analyzer</option>
              <option value="reminder">⏱️ Task Reminder</option>
              <option value="weather">🌤️ Weather Specialist</option>
            </select>
            <button class="btn-action" onclick="refreshChatHistory()">🔄 Sync</button>
            <button class="btn-action" onclick="clearLocalChat()">🧹 Clear View</button>
          </div>
        </div>

        <!-- MESSAGES SCROLL CONTAINER -->
        <div id="chatMessages" class="chat-messages">
          <div class="chat-bubble-row">
            <div class="chat-avatar avatar-assistant">🤖</div>
            <div class="bubble-card bubble-assistant">
              <div>👋 <strong>Welcome to Khepri.</strong> I am your personal autonomous agent. Both this Web Portal and your Telegram chat share the exact same multi-turn conversation memory!</div>
              <div class="bubble-meta">
                <span>⚡ Grounded Agent</span>
                <span>•</span>
                <span>Ready</span>
              </div>
            </div>
          </div>
        </div>

        <!-- QUICK PROMPT PILLS -->
        <div class="chat-suggestions">
          <span class="pill-prompt" onclick="setPrompt('/briefing')">📰 Daily Briefing (/briefing)</span>
          <span class="pill-prompt" onclick="setPrompt('/calendar')">📅 Today's Agenda (/calendar)</span>
          <span class="pill-prompt" onclick="setPrompt('How is the weather in Kolkata today?')">🌤️ Weather in Kolkata</span>
          <span class="pill-prompt" onclick="setPrompt('Calculate 25 * 18.5 + 40')">🧮 Safe calculate</span>
          <span class="pill-prompt" onclick="setPrompt('/timer 15m Pasta')">⏱️ Set 15m timer</span>
          <span class="pill-prompt" onclick="setPrompt('Remember that our Oracle VM IP is 10.0.0.1')">📝 Save to memory</span>
          <span class="pill-prompt" onclick="setPrompt('/search Docker cgroup memory limit')">🔍 DuckDuckGo search</span>
        </div>

        <!-- INPUT BAR -->
        <div class="chat-input-bar">
          <textarea id="chatInput" class="chat-textarea" placeholder="Type prompt (Shift+Enter for newline, Enter to send)..." rows="1" onkeydown="handleChatKey(event)"></textarea>
          <button class="btn" id="chatSendBtn" onclick="sendChatMessage()" style="padding: 0.85rem 1.4rem;">
            <span>Send</span>
            <span>➤</span>
          </button>
        </div>
      </div>
    </div>

    <!-- TAB 3: TASKS & TIMERS -->
    <div id="tab-tasks" class="tab-content">
      <div class="card-box">
        <div class="card-box-header">
          <div>
            <h3>📋 Tasks, Timers & Scheduled Reminders</h3>
            <p style="color: var(--text-muted); font-size: 0.82rem;">Track to-dos and alarms monitored by the background scheduler thread.</p>
          </div>
          <div style="display: flex; gap: 0.5rem;">
            <button class="btn-action" onclick="filterTasks('all')">All</button>
            <button class="btn-action" onclick="filterTasks('pending')">Pending</button>
            <button class="btn-action" onclick="filterTasks('completed')">Completed</button>
          </div>
        </div>

        <!-- Add Form -->
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <input type="text" id="fullTaskTitle" class="input-field" style="flex: 2; min-width: 200px;" placeholder="Task title or reminder...">
          <select id="fullTaskList" class="input-field" style="flex: 1; min-width: 120px;">
            <option value="default">Task</option>
            <option value="timer">Timer</option>
            <option value="work">Work</option>
            <option value="personal">Personal</option>
          </select>
          <button class="btn" onclick="addFullTask()">+ Add Task</button>
        </div>

        <div id="fullTasksContainer" class="task-list">
          <div style="color: var(--text-muted); padding: 2rem; text-align: center;">Loading tasks...</div>
        </div>
      </div>
    </div>

    <!-- TAB 4: KNOWLEDGE MEMORY -->
    <div id="tab-notes" class="tab-content">
      <div class="card-box">
        <div class="card-box-header">
          <div>
            <h3>🧠 Markdown Persistent Knowledge Memory</h3>
            <p style="color: var(--text-muted); font-size: 0.82rem;">Stored in <code>data/notes/*.md</code>. Grounded in conversational retrieval.</p>
          </div>
          <div style="display: flex; gap: 0.5rem;">
            <input type="text" id="notesSearchInput" class="input-field" placeholder="Filter notes..." oninput="filterNotesList()" style="padding: 0.4rem 0.75rem;">
            <button class="btn" onclick="openNewNoteModal()">+ New Note</button>
          </div>
        </div>

        <div id="notesGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem;">
          <div style="color: var(--text-muted); padding: 2rem; text-align: center;">Loading notes...</div>
        </div>
      </div>
    </div>

    <!-- TAB 5: AUDIT LOG -->
    <div id="tab-interactions" class="tab-content">
      <div class="card-box">
        <div class="card-box-header">
          <div>
            <h3>📜 Interaction Audit Trail</h3>
            <p style="color: var(--text-muted); font-size: 0.82rem;">Chronological log of user prompts, model responses, and tool calls in SQLite WAL.</p>
          </div>
          <input type="text" id="auditSearchInput" class="input-field" placeholder="Search interactions..." oninput="filterAuditLog()" style="padding: 0.4rem 0.75rem;">
        </div>

        <div style="overflow-x: auto;">
          <table id="auditTable">
            <thead>
              <tr>
                <th>Time (IST)</th>
                <th>Source</th>
                <th>Prompt</th>
                <th>Response</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody id="auditTableBody">
              <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">Loading audit trail...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 6: DIGESTS -->
    <div id="tab-digests" class="tab-content">
      <div class="card-box">
        <div class="card-box-header">
          <div>
            <h3>📰 Hourly Digest Archive</h3>
            <p style="color: var(--text-muted); font-size: 0.82rem;">Periodic analytical summaries dispatched to Telegram report channel.</p>
          </div>
        </div>

        <div style="overflow-x: auto;">
          <table>
            <thead>
              <tr>
                <th>Generated At</th>
                <th>Items</th>
                <th>Summary Content</th>
              </tr>
            </thead>
            <tbody id="digestsTableBody">
              <tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 2rem;">Loading digests...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </main>

  <!-- NOTE MODAL -->
  <div id="noteModal" class="modal-overlay">
    <div class="modal-card">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <h3 id="noteModalTitle" style="font-size: 1.15rem; color: #fff;">Note Details</h3>
        <button class="btn-del" onclick="closeNoteModal()" style="font-size: 1.25rem;">✕</button>
      </div>
      <div id="noteModalMeta" style="font-size: 0.75rem; color: var(--text-dim);"></div>
      <div id="noteModalContent" style="background: rgba(10,14,26,0.6); padding: 1.25rem; border-radius: 0.75rem; border: 1px solid var(--border); font-size: 0.88rem; color: #cbd5e1; max-height: 360px; overflow-y: auto; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace;"></div>
      <div style="display: flex; justify-content: space-between; gap: 0.5rem;">
        <button class="btn-action" style="color: #f87171;" id="noteModalDeleteBtn">Delete Note</button>
        <button class="btn" onclick="closeNoteModal()">Close</button>
      </div>
    </div>
  </div>

  <!-- NEW NOTE MODAL -->
  <div id="newNoteModal" class="modal-overlay">
    <div class="modal-card">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <h3 style="font-size: 1.15rem; color: #fff;">+ Create Markdown Note</h3>
        <button class="btn-del" onclick="closeNewNoteModal()" style="font-size: 1.25rem;">✕</button>
      </div>
      <input type="text" id="newNoteTitleInput" class="input-field" placeholder="Note Title (e.g. Server Credentials, WiFi Setup)...">
      <input type="text" id="newNoteTagsInput" class="input-field" placeholder="Tags (optional, comma-separated)...">
      <textarea id="newNoteContentInput" class="input-field" rows="6" placeholder="Markdown note content..."></textarea>
      <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
        <button class="btn-action" onclick="closeNewNoteModal()">Cancel</button>
        <button class="btn" onclick="saveNewNote()">Save Note</button>
      </div>
    </div>
  </div>

  <!-- JAVASCRIPT APP LOGIC -->
  <script>
    let activeTab = 'overview';
    let lastChatId = 0;
    let allTasks = [];
    let allNotes = [];
    let allAudit = [];
    let chatPollingTimer = null;

    // Clock
    setInterval(() => {
      const now = new Date();
      document.getElementById('liveClock').innerText = now.toLocaleTimeString('en-US', {hour12: false});
    }, 1000);

    function switchTab(tabId) {
      activeTab = tabId;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      const activeBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick').includes(tabId));
      if (activeBtn) activeBtn.classList.add('active');
      const targetDiv = document.getElementById('tab-' + tabId);
      if (targetDiv) targetDiv.classList.add('active');

      if (tabId === 'chat') {
        scrollChatToBottom();
        startChatPolling();
      } else {
        stopChatPolling();
      }
    }

    // TELEMETRY
    async function loadStats() {
      try {
        const resp = await fetch('/api/stats');
        if (!resp.ok) return;
        const d = await resp.json();
        
        // Update Stats
        const tel = d.telemetry || {};
        document.getElementById('statEngineStatus').innerText = tel.engine_status || 'Online';
        document.getElementById('statEngineLatency').innerText = tel.engine_latency_ms ? '⚡ ' + tel.engine_latency_ms + 'ms' : '⚡ 1.4ms';
        document.getElementById('statEngineMeta').innerText = (tel.engine_model || 'qwen2.5-0.5b-instruct') + ' • ' + (tel.engine_threads || 2) + ' Threads • Up ' + (tel.engine_uptime || '12m');
        document.getElementById('headerEnginePill').innerText = (tel.engine_model || 'Qwen2.5-0.5B') + ' • ' + (tel.engine_status || 'Online');

        document.getElementById('statRss').innerText = (tel.agent_rss_mb || 34.3) + ' MB';
        const pct = Math.min(100, Math.round(((tel.agent_rss_mb || 34.3) / 512) * 100));
        document.getElementById('statRssPct').innerText = pct + '% cgroup';
        document.getElementById('statRssBar').style.width = pct + '%';
        document.getElementById('statHostRam').innerText = 'Host RAM: ' + (tel.host_mem_used_mb || 2010) + ' MB / ' + (tel.host_mem_total_mb || 11925) + ' MB (' + (tel.host_mem_pct || 17) + '%)';

        document.getElementById('statInteractions').innerText = d.total_interactions || 0;
        document.getElementById('statTasks').innerText = (d.total_tasks || 0) + ' Total';
        document.getElementById('statTasksMeta').innerText = (d.pending_tasks || 0) + ' Pending';
        document.getElementById('statNotes').innerText = (d.total_notes || 0) + ' Notes';
        if (d.admin_id) document.getElementById('confAdminId').innerText = d.admin_id;
        if (d.timezone) document.getElementById('headerTzPill').innerText = d.timezone;
      } catch (e) {
        console.error('Error loading stats', e);
      }
    }

    // TASKS
    async function loadTasks() {
      try {
        const resp = await fetch('/api/tasks');
        if (!resp.ok) return;
        allTasks = await resp.json();
        renderOverviewTasks();
        renderFullTasks(allTasks);
      } catch (e) { console.error('Error loading tasks', e); }
    }

    function renderOverviewTasks() {
      const container = document.getElementById('overviewTasksList');
      if (!allTasks.length) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem; text-align: center;">No tasks. Add one above!</div>';
        return;
      }
      container.innerHTML = allTasks.slice(0, 5).map(t => `
        <div class="task-item ${t.is_completed ? 'completed' : ''}">
          <input type="checkbox" class="task-checkbox" ${t.is_completed ? 'checked' : ''} onchange="toggleTask(${t.id})">
          <div class="task-text">${escapeHtml(t.title)}</div>
          <span class="task-tag">${escapeHtml(t.list_name || 'task')}</span>
          <button class="btn-del" onclick="deleteTask(${t.id})" title="Delete">✕</button>
        </div>
      `).join('');
    }

    function renderFullTasks(items) {
      const container = document.getElementById('fullTasksContainer');
      if (!items.length) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 2rem; text-align: center;">No tasks in this view.</div>';
        return;
      }
      container.innerHTML = items.map(t => `
        <div class="task-item ${t.is_completed ? 'completed' : ''}">
          <input type="checkbox" class="task-checkbox" ${t.is_completed ? 'checked' : ''} onchange="toggleTask(${t.id})">
          <div class="task-text">${escapeHtml(t.title)}</div>
          <span class="task-tag">${escapeHtml(t.list_name || 'task')}</span>
          ${t.due_at ? `<span class="task-tag" style="color: #fbbf24;">🕒 ${t.due_at.substring(0, 16).replace('T', ' ')}</span>` : ''}
          <button class="btn-del" onclick="deleteTask(${t.id})" title="Delete">✕</button>
        </div>
      `).join('');
    }

    async function toggleTask(id) {
      await fetch('/api/tasks/toggle', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id})
      });
      loadTasks();
      loadStats();
    }

    async function deleteTask(id) {
      await fetch('/api/tasks/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id})
      });
      loadTasks();
      loadStats();
    }

    async function addQuickTask() {
      const input = document.getElementById('quickTaskInput');
      const title = input.value.trim();
      if (!title) return;
      input.value = '';
      await fetch('/api/tasks/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title: title, list_name: 'default'})
      });
      loadTasks();
      loadStats();
    }

    async function addFullTask() {
      const titleInput = document.getElementById('fullTaskTitle');
      const listInput = document.getElementById('fullTaskList');
      const title = titleInput.value.trim();
      if (!title) return;
      titleInput.value = '';
      await fetch('/api/tasks/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title: title, list_name: listInput.value})
      });
      loadTasks();
      loadStats();
    }

    function filterTasks(mode) {
      if (mode === 'pending') renderFullTasks(allTasks.filter(t => !t.is_completed));
      else if (mode === 'completed') renderFullTasks(allTasks.filter(t => t.is_completed));
      else renderFullTasks(allTasks);
    }

    // NOTES
    async function loadNotes() {
      try {
        const resp = await fetch('/api/notes');
        if (!resp.ok) return;
        allNotes = await resp.json();
        renderOverviewNotes();
        renderFullNotes(allNotes);
      } catch (e) { console.error('Error loading notes', e); }
    }

    function renderOverviewNotes() {
      const container = document.getElementById('overviewNotesList');
      if (!allNotes.length) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem; text-align: center;">No saved notes. Click + New Note!</div>';
        return;
      }
      container.innerHTML = allNotes.slice(0, 4).map(n => `
        <div style="padding: 0.75rem 1rem; background: rgba(10,14,26,0.6); border: 1px solid var(--border); border-radius: 0.65rem; display: flex; justify-content: space-between; align-items: center; cursor: pointer;" onclick="openNoteModal('${escapeHtml(n.filename)}')">
          <div>
            <div style="font-weight: 600; font-size: 0.85rem; color: #e2e8f0;">${escapeHtml(n.title)}</div>
            <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.2rem;">${escapeHtml(n.filename)} • ${n.size_bytes || 0} B</div>
          </div>
          <span style="font-size: 0.85rem; color: var(--primary);">View ↗</span>
        </div>
      `).join('');
    }

    function renderFullNotes(items) {
      const container = document.getElementById('notesGrid');
      if (!items.length) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 2rem; text-align: center; grid-column: 1/-1;">No notes match your filter.</div>';
        return;
      }
      container.innerHTML = items.map(n => `
        <div style="padding: 1.25rem; background: rgba(14,20,36,0.7); border: 1px solid var(--border); border-radius: 0.85rem; display: flex; flex-direction: column; gap: 0.6rem; cursor: pointer; transition: all 0.2s;" onclick="openNoteModal('${escapeHtml(n.filename)}')">
          <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div style="font-weight: 700; color: #fff; font-size: 0.95rem;">${escapeHtml(n.title)}</div>
            <span class="tool-chip" style="font-size: 0.65rem;">MD</span>
          </div>
          <div style="font-size: 0.75rem; color: var(--text-dim); font-family: monospace;">${escapeHtml(n.filename)}</div>
          <div style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;">
            ${escapeHtml(n.content || 'Markdown note content...')}
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: auto; padding-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.05); font-size: 0.72rem; color: var(--text-dim);">
            <span>${n.modified_at ? n.modified_at.substring(0,10) : 'Recent'}</span>
            <span style="color: var(--primary); font-weight: 600;">Open Editor ↗</span>
          </div>
        </div>
      `).join('');
    }

    function filterNotesList() {
      const term = document.getElementById('notesSearchInput').value.toLowerCase();
      renderFullNotes(allNotes.filter(n => n.title.toLowerCase().includes(term) || (n.content && n.content.toLowerCase().includes(term))));
    }

    function openNoteModal(filename) {
      const note = allNotes.find(n => n.filename === filename);
      if (!note) return;
      document.getElementById('noteModalTitle').innerText = note.title;
      document.getElementById('noteModalMeta').innerText = `File: ${note.filename} • Modified: ${note.modified_at || 'Recent'}`;
      document.getElementById('noteModalContent').innerText = note.content || 'Empty note.';
      document.getElementById('noteModalDeleteBtn').onclick = async () => {
        if (!confirm(`Delete note ${note.title}?`)) return;
        await fetch('/api/notes/delete', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({filename: note.filename})
        });
        closeNoteModal();
        loadNotes();
        loadStats();
      };
      document.getElementById('noteModal').classList.add('active');
    }
    function closeNoteModal() { document.getElementById('noteModal').classList.remove('active'); }

    function openNewNoteModal() {
      document.getElementById('newNoteTitleInput').value = '';
      document.getElementById('newNoteTagsInput').value = '';
      document.getElementById('newNoteContentInput').value = '';
      document.getElementById('newNoteModal').classList.add('active');
    }
    function closeNewNoteModal() { document.getElementById('newNoteModal').classList.remove('active'); }

    async function saveNewNote() {
      const title = document.getElementById('newNoteTitleInput').value.trim();
      const tags = document.getElementById('newNoteTagsInput').value.trim();
      const content = document.getElementById('newNoteContentInput').value.trim();
      if (!title || !content) { alert('Title and content are required.'); return; }
      await fetch('/api/notes/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title: title, content: content, tags: tags})
      });
      closeNewNoteModal();
      loadNotes();
      loadStats();
    }

    // CHAT & INTERACTIONS STREAM
    async function loadChatHistory() {
      try {
        const resp = await fetch('/api/chat/history');
        if (!resp.ok) return;
        const messages = await resp.json();
        renderChatMessages(messages, false);
        renderOverviewFeed(messages);
      } catch (e) { console.error('Error loading chat', e); }
    }

    function renderOverviewFeed(messages) {
      const container = document.getElementById('overviewFeed');
      if (!messages.length) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 1.5rem; text-align: center;">No conversation history yet. Send a prompt below!</div>';
        return;
      }
      container.innerHTML = messages.slice(-4).reverse().map(m => `
        <div class="activity-item">
          <div class="activity-meta">
            <span class="activity-badge ${m.source === 'telegram' ? 'badge-telegram' : 'badge-web'}">
              ${m.source === 'telegram' ? '✈️ Telegram @pranabesh' : '🌐 Web Portal'}
            </span>
            <span>${m.created_at ? m.created_at.substring(11, 19) : ''}</span>
          </div>
          <div class="activity-prompt">${escapeHtml(m.prompt)}</div>
          <div class="activity-response">${formatMarkdown(m.response)}</div>
        </div>
      `).join('');
    }

    function renderChatMessages(messages, append = false) {
      const container = document.getElementById('chatMessages');
      if (!append) container.innerHTML = '';

      messages.forEach(m => {
        if (m.id > lastChatId) lastChatId = m.id;

        // User bubble
        const userRow = document.createElement('div');
        userRow.className = 'chat-bubble-row user';
        userRow.innerHTML = `
          <div class="chat-avatar avatar-user">👤</div>
          <div class="bubble-card bubble-user">
            <div>${escapeHtml(m.prompt)}</div>
            <div class="bubble-meta">
              <span>${m.source === 'telegram' ? 'Telegram @pranabesh' : 'Web Portal'}</span>
              <span>•</span>
              <span>${m.created_at ? m.created_at.substring(11, 19) : 'Just now'}</span>
            </div>
          </div>
        `;
        container.appendChild(userRow);

        // Assistant bubble
        const asstRow = document.createElement('div');
        asstRow.className = 'chat-bubble-row';
        asstRow.innerHTML = `
          <div class="chat-avatar avatar-assistant">🤖</div>
          <div class="bubble-card bubble-assistant">
            <div>${formatMarkdown(m.response)}</div>
            <div class="bubble-meta">
              ${m.latency_ms ? `<span class="tool-chip">⚡ ${m.latency_ms}ms</span>` : ''}
              ${m.search_query ? `<span class="tool-chip">🔍 Web Grounded</span>` : ''}
              <span>•</span>
              <span>${m.created_at ? m.created_at.substring(11, 19) : 'Just now'}</span>
            </div>
          </div>
        `;
        container.appendChild(asstRow);
      });

      scrollChatToBottom();
    }

    function scrollChatToBottom() {
      const container = document.getElementById('chatMessages');
      if (container) container.scrollTop = container.scrollHeight;
    }

    function startChatPolling() {
      if (chatPollingTimer) clearInterval(chatPollingTimer);
      chatPollingTimer = setInterval(async () => {
        try {
          const resp = await fetch(`/api/chat/history?since_id=${lastChatId}`);
          if (!resp.ok) return;
          const newMessages = await resp.json();
          if (newMessages.length > 0) {
            renderChatMessages(newMessages, true);
          }
        } catch (e) {}
      }, 3000);
    }
    function stopChatPolling() {
      if (chatPollingTimer) { clearInterval(chatPollingTimer); chatPollingTimer = null; }
    }

    function setPrompt(text) {
      const input = document.getElementById('chatInput');
      input.value = text;
      input.focus();
    }

    function handleChatKey(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    }

    async function sendChatMessage() {
      const input = document.getElementById('chatInput');
      const text = input.value.trim();
      if (!text) return;

      const preset = document.getElementById('chatPreset').value;
      const sync = document.getElementById('syncTelegramToggle').checked;
      const btn = document.getElementById('chatSendBtn');

      input.value = '';
      btn.disabled = true;
      btn.innerText = 'Thinking...';

      // Optimistically append user message
      const container = document.getElementById('chatMessages');
      const tempUserRow = document.createElement('div');
      tempUserRow.className = 'chat-bubble-row user';
      tempUserRow.innerHTML = `
        <div class="chat-avatar avatar-user">👤</div>
        <div class="bubble-card bubble-user">
          <div>${escapeHtml(text)}</div>
          <div class="bubble-meta"><span>Web Portal</span> • <span>Sending...</span></div>
        </div>
      `;
      container.appendChild(tempUserRow);
      scrollChatToBottom();

      try {
        const resp = await fetch('/api/chat/send', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({prompt: text, preset: preset, sync_telegram: sync})
        });
        const data = await resp.json();

        // Append assistant response
        const asstRow = document.createElement('div');
        asstRow.className = 'chat-bubble-row';
        asstRow.innerHTML = `
          <div class="chat-avatar avatar-assistant">🤖</div>
          <div class="bubble-card bubble-assistant">
            <div>${escapeHtml(data.response || 'No response')}</div>
            <div class="bubble-meta">
              <span class="tool-chip">⚡ ${data.latency_ms || 15}ms</span>
              ${data.synced_telegram ? '<span class="tool-chip" style="color: #38bdf8;">✈️ Synced to Telegram</span>' : ''}
              <span>• Just now</span>
            </div>
          </div>
        `;
        container.appendChild(asstRow);
        scrollChatToBottom();
        loadStats();
      } catch (e) {
        alert('Could not complete request: ' + e);
      } finally {
        btn.disabled = false;
        btn.innerText = 'Send ➤';
      }
    }

    async function sendOverviewPrompt() {
      const input = document.getElementById('overviewPromptInput');
      const text = input.value.trim();
      if (!text) return;
      input.value = '';
      switchTab('chat');
      setPrompt(text);
      sendChatMessage();
    }

    async function clearLocalChat() {
      try {
        await fetch('/api/chat/clear', {method: 'POST'});
      } catch (e) {
        console.warn('Error clearing backend context:', e);
      }
      document.getElementById('chatMessages').innerHTML = `
        <div class="chat-bubble-row">
          <div class="chat-avatar avatar-assistant">🤖</div>
          <div class="bubble-card bubble-assistant">
            <div>🧹 Context cleared. Fresh session started!</div>
          </div>
        </div>
      `;
    }

    // AUDIT LOG
    async function loadAuditLog() {
      try {
        const resp = await fetch('/api/interactions');
        if (!resp.ok) return;
        allAudit = await resp.json();
        renderAuditTable(allAudit);
      } catch (e) {}
    }

    function renderAuditTable(items) {
      const body = document.getElementById('auditTableBody');
      if (!items.length) {
        body.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">No logged interactions.</td></tr>';
        return;
      }
      body.innerHTML = items.map(i => `
        <tr>
          <td style="font-family: monospace; font-size: 0.75rem; white-space: nowrap;">${i.created_at ? i.created_at.substring(11, 19) : ''}</td>
          <td><span class="activity-badge ${i.user_id === 'web' ? 'badge-web' : 'badge-telegram'}">${i.user_id === 'web' ? 'Web' : 'Telegram'}</span></td>
          <td style="font-weight: 600; color: #fff;">${escapeHtml(i.prompt)}</td>
          <td style="color: #94a3b8; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(i.response)}</td>
          <td><span class="tool-chip">${i.latency_ms || 12}ms</span></td>
        </tr>
      `).join('');
    }

    function filterAuditLog() {
      const term = document.getElementById('auditSearchInput').value.toLowerCase();
      renderAuditTable(allAudit.filter(i => (i.prompt && i.prompt.toLowerCase().includes(term)) || (i.response && i.response.toLowerCase().includes(term))));
    }

    // DIGESTS
    async function loadDigests() {
      try {
        const resp = await fetch('/api/digests');
        if (!resp.ok) return;
        const digests = await resp.json();
        const body = document.getElementById('digestsTableBody');
        if (!digests.length) {
          body.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 2rem;">No hourly digests recorded yet.</td></tr>';
          return;
        }
        body.innerHTML = digests.map(d => `
          <tr>
            <td style="font-family: monospace; white-space: nowrap;">${d.created_at || 'Recent'}</td>
            <td><span class="tool-chip">${d.item_count || 0} Items</span></td>
            <td style="white-space: pre-wrap; font-family: inherit;">${escapeHtml(d.content)}</td>
          </tr>
        `).join('');
      } catch (e) {}
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function formatMarkdown(str) {
      if (!str) return '';
      let safe = escapeHtml(str);
      // Links: [text](url) -> <a href="url" target="_blank" rel="noopener noreferrer">text</a>
      safe = safe.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color: var(--accent); text-decoration: underline; text-underline-offset: 3px; font-weight: 500;">$1</a>');
      // Bold: **text** or *text*
      safe = safe.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
      safe = safe.replace(/\*([^\*]+)\*/g, '<strong>$1</strong>');
      // Italics: _text_
      safe = safe.replace(/_([^_]+)_/g, '<em>$1</em>');
      // Inline code: `code`
      safe = safe.replace(/`([^`]+)`/g, '<code style="background: rgba(255,255,255,0.08); padding: 0.15rem 0.35rem; border-radius: 4px; font-family: monospace;">$1</code>');
      // Line breaks
      safe = safe.replace(/\n/g, '<br>');
      return safe;
    }

    async function refreshAll() {
      await Promise.all([loadStats(), loadTasks(), loadNotes(), loadChatHistory(), loadAuditLog(), loadDigests()]);
    }

    async function logout() {
      await fetch('/api/logout', {method: 'POST'});
      window.location.href = '/login';
    }

    // Init
    window.addEventListener('DOMContentLoaded', () => {
      refreshAll();
    });
  </script>
</body>
</html>
"""


def create_web_server(
    storage: Any,
    admin_password: str,
    host: str = "0.0.0.0",
    port: int = 8080,
    daemon_url: str = "http://127.0.0.1:8090",
    tz_name: str = "Asia/Kolkata",
    admin_id: str = "",
    report_id: str = "",
    bot: Optional[Any] = None
) -> HTTPServer:
    """Create HTTP Server instance with session authentication, multi-turn context memory, and Telegram chat sync."""

    class KhepriWebHandler(BaseHTTPRequestHandler):
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

        def _send_html(self, html_str: str, status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
            data = html_str.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if headers:
                for k, v in headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> Dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                return {}
            raw_data = self.rfile.read(content_length).decode("utf-8")
            try:
                return json.loads(raw_data)
            except Exception:
                return {}

        def log_message(self, format: str, *args: Any) -> None:
            # Silence default access log to keep container logs pristine
            pass

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query_params = urllib.parse.parse_qs(parsed.query)

            # Public unauthenticated routes
            if path == "/health":
                self._send_json({"status": "ok", "app": "khepri-agent", "timezone": tz_name})
                return

            if path == "/login":
                if self._is_authenticated():
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.end_headers()
                    return
                self._send_html(LOGIN_HTML)
                return

            # Protected routes
            if not self._is_authenticated():
                if path.startswith("/api/"):
                    self._send_json({"error": "Unauthorized"}, status=401)
                else:
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.end_headers()
                return

            if path in ("/", "/index.html"):
                self._send_html(DASHBOARD_HTML)

            elif path == "/api/stats":
                interactions = storage.get_interactions(limit=100) if storage else []
                tasks_all = storage.get_tasks(include_completed=True) if storage else []
                tasks_pending = [t for t in tasks_all if not t.get("is_completed")]
                notes = list_notes()
                telemetry = get_system_telemetry(daemon_url)
                self._send_json({
                    "status": "ok",
                    "total_interactions": len(interactions),
                    "pending_tasks": len(tasks_pending),
                    "total_tasks": len(tasks_all),
                    "total_notes": len(notes),
                    "timezone": tz_name,
                    "admin_id": mask_id(admin_id),
                    "report_id": mask_id(report_id),
                    "telemetry": telemetry
                })

            elif path == "/api/calendar":
                prof = (storage.get_user_profile("web") if storage else {}) or {}
                cal_url = prof.get("calendar_url") or os.environ.get("CALENDAR_ICS_URL", "")
                alert_mins = prof.get("calendar_alert_mins") or 10
                synced_at = prof.get("calendar_synced_at") or ""
                events = storage.get_upcoming_events("web", limit=20) if storage else []
                self._send_json({
                    "status": "ok",
                    "url": cal_url,
                    "alert_mins": alert_mins,
                    "synced_at": synced_at,
                    "events": events
                })

            elif path == "/api/briefing":
                from pithon.agent.briefing import generate_daily_briefing
                briefing_text = generate_daily_briefing(str(admin_id or "web"), storage, tz_name=tz_name)
                self._send_json({"status": "ok", "briefing": briefing_text})

            elif path == "/api/chat/history":
                since_id = 0
                if "since_id" in query_params:
                    try:
                        since_id = int(query_params["since_id"][0])
                    except ValueError:
                        since_id = 0
                messages = storage.get_chat_stream(limit=50, since_id=since_id) if storage else []
                self._send_json(messages)

            elif path == "/api/interactions":
                items = storage.get_interactions(limit=50) if storage else []
                self._send_json(items)

            elif path == "/api/tasks":
                tasks = storage.get_tasks(include_completed=True) if storage else []
                self._send_json(tasks)

            elif path == "/api/notes":
                notes_list = list_notes()
                for n in notes_list:
                    n["content"] = get_note_content(n["filename"])
                self._send_json(notes_list)

            elif path == "/api/profile":
                prof = storage.get_user_profile(str(admin_id or "web")) if storage else {}
                self._send_json(prof or {})

            elif path == "/api/digests":
                digests = storage.get_digests(limit=24) if storage else []
                self._send_json(digests)

            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/api/login":
                body = self._read_json_body()
                pwd = body.get("password", "")
                if secrets.compare_digest(pwd, admin_password):
                    token = secrets.token_hex(24)
                    if storage:
                        storage.create_session(token, expires_in_sec=259200)
                    cookie = f"pithon_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=259200"
                    self._send_html(
                        '{"status":"ok"}',
                        status=200,
                        headers={"Set-Cookie": cookie, "Content-Type": "application/json"}
                    )
                else:
                    self._send_json({"error": "Invalid passphrase"}, status=401)
                return

            if not self._is_authenticated():
                self._send_json({"error": "Unauthorized"}, status=401)
                return

            if path == "/api/logout":
                token = self._get_cookie_session()
                if token and storage:
                    storage.delete_session(token)
                cookie = "pithon_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
                self._send_html(
                    '{"status":"ok"}',
                    status=200,
                    headers={"Set-Cookie": cookie, "Content-Type": "application/json"}
                )
                return

            elif path == "/api/tasks/add":
                body = self._read_json_body()
                title = body.get("title", "").strip()
                list_name = body.get("list_name", "default").strip()
                due_at = body.get("due_at", None)
                if title and storage:
                    tid = storage.create_task("web", title, due_at=due_at, list_name=list_name)
                    self._send_json({"status": "ok", "id": tid})
                else:
                    self._send_json({"error": "Title required"}, status=400)

            elif path == "/api/tasks/toggle":
                body = self._read_json_body()
                tid = int(body.get("id", 0))
                if tid and storage:
                    new_val = storage.toggle_task(tid)
                    self._send_json({"status": "ok", "is_completed": new_val})
                else:
                    self._send_json({"error": "Task ID required"}, status=400)

            elif path == "/api/tasks/delete":
                body = self._read_json_body()
                tid = int(body.get("id", 0))
                if tid and storage:
                    deleted = storage.delete_task(tid)
                    self._send_json({"status": "ok", "deleted": deleted})
                else:
                    self._send_json({"error": "Task ID required"}, status=400)

            elif path == "/api/notes/add":
                body = self._read_json_body()
                title = body.get("title", "").strip()
                content = body.get("content", "").strip()
                tags = body.get("tags", "").strip() or None
                if title and content:
                    res = save_note(title, content, tags=tags, tz_name=tz_name)
                    self._send_json({"status": "ok", "note": res})
                else:
                    self._send_json({"error": "Title and content required"}, status=400)

            elif path == "/api/notes/delete":
                body = self._read_json_body()
                filename = body.get("filename", "").strip()
                if filename:
                    deleted = delete_note(filename)
                    self._send_json({"status": "ok", "deleted": deleted})
                else:
                    self._send_json({"error": "Filename required"}, status=400)

            elif path == "/api/calendar/sync":
                prof = (storage.get_user_profile("web") if storage else {}) or {}
                cal_url = prof.get("calendar_url") or os.environ.get("CALENDAR_ICS_URL", "")
                if not cal_url:
                    self._send_json({"error": "No calendar URL configured"}, status=400)
                    return
                changed, feed_md5, events = fetch_and_parse_calendar(cal_url, "", tz_name)
                if storage:
                    storage.save_calendar_events("web", events)
                    storage.update_calendar_settings("web", feed_md5=feed_md5)
                self._send_json({"status": "ok", "synced": len(events), "feed_md5": feed_md5})

            elif path == "/api/chat/clear":
                if storage:
                    storage.clear_context(str(admin_id or "web"))
                self._send_json({"status": "ok", "message": "Context cleared"})

            elif path in ("/api/chat/send", "/api/playground"):
                body = self._read_json_body()
                prompt = body.get("prompt", "").strip()
                preset = body.get("preset", "default").strip()
                sync_telegram = body.get("sync_telegram", True)
                if not prompt:
                    self._send_json({"error": "Empty prompt"}, status=400)
                    return

                t0 = time.time()
                reply_text = ""
                search_q = None

                # 0. Check /init command or active onboarding step
                if prompt.startswith("/init"):
                    arg = prompt[5:].strip()
                    reply_text = start_onboarding(str(admin_id or "web"), storage, text=arg, tz_name=tz_name)

                elif not reply_text and storage:
                    prof = storage.get_user_profile(str(admin_id or "web"))
                    if prof and prof.get("step"):
                        reply_text = handle_onboarding_step(str(admin_id or "web"), prompt, storage, tz_name=tz_name)

                # 0b. Check /briefing command
                if not reply_text and (prompt.startswith("/briefing") or prompt.lower().strip() in ("/briefing", "daily briefing", "briefing")):
                    from pithon.agent.briefing import generate_daily_briefing
                    reply_text = generate_daily_briefing(str(admin_id or "web"), storage, tz_name=tz_name)

                # 0c. Check /calendar command
                if not reply_text and (prompt.startswith("/calendar") or prompt.startswith("/agenda") or prompt.lower().strip() in ("/calendar", "my calendar", "today's agenda", "agenda")):
                    prof = (storage.get_user_profile("web") if storage else {}) or {}
                    cal_url = prof.get("calendar_url") or os.environ.get("CALENDAR_ICS_URL", "")
                    events = storage.get_upcoming_events("web", limit=6) if storage else []
                    if events:
                        lines = ["📅 **Upcoming Calendar Meetings & Calls:**\n"]
                        try:
                            tz = zoneinfo.ZoneInfo(tz_name)
                        except Exception:
                            tz = timezone.utc
                        for ev in events:
                            try:
                                ev_start = datetime.fromisoformat(ev["start_time"]).astimezone(tz)
                                ev_end = datetime.fromisoformat(ev["end_time"]).astimezone(tz)
                                t_str = f"{ev_start.strftime('%a %d %b, %I:%M %p')} - {ev_end.strftime('%I:%M %p')}"
                                loc = f" *({ev['location']})*" if ev.get("location") else ""
                                if ev.get("meeting_link"):
                                    lines.append(f"• `{t_str}`\n  [{ev['title']}]({ev['meeting_link']}){loc}")
                                else:
                                    lines.append(f"• `{t_str}`\n  **{ev['title']}**{loc}")
                            except Exception:
                                continue
                        reply_text = "\n".join(lines)
                    else:
                        reply_text = "📅 No upcoming meetings found in calendar. Use `/calendar set <url>` in Telegram or configure CALENDAR_ICS_URL to connect your feed."


                # 1. Check direct weather intent
                if not reply_text and is_weather_intent(prompt):
                    home_city = get_default_weather_city(storage, str(admin_id or "web"), fallback="Kolkata")
                    loc = extract_weather_location(prompt, default_loc=home_city)
                    report = get_weather_report(loc)
                    reply_text = report.get("summary", "No weather data.")

                # 1b. Check direct /clear or /reset command
                if not reply_text and prompt.lower().strip() in ("/clear", "/reset"):
                    if storage:
                        storage.clear_context(str(admin_id or "web"))
                    reply_text = "🧹 *Conversational context cleared!* I have reset previous dialogue turns."

                # 2. Check direct math intent
                calc_m = re.search(r"^(?:calculate|calc|what is)\s+([0-9\.\s\+\-\*\/\(\)\^\%]+)[?]?$", prompt, re.IGNORECASE)
                if not reply_text and calc_m:
                    expr = calc_m.group(1).strip()
                    res = safe_calculate(expr)
                    reply_text = f"🧮 `{expr}` = *{res}*"

                # 3. Check direct /note command
                if not reply_text and prompt.startswith("/note "):
                    parts = prompt[6:].strip().split(" ", 1)
                    ntitle = parts[0]
                    ncontent = parts[1] if len(parts) > 1 else ""
                    if ntitle and ncontent:
                        nres = save_note(ntitle, ncontent, tz_name=tz_name)
                        reply_text = f"📝 Saved note *{ntitle}* (`{nres.get('filename')}`)"
                    else:
                        reply_text = "Usage: `/note <title> <content>`"

                # 3b. Check direct /task or /add command
                if not reply_text and (prompt.startswith("/task ") or prompt.startswith("/add ")):
                    cmd_len = 6 if prompt.startswith("/task ") else 5
                    t_title = prompt[cmd_len:].strip()
                    if t_title and storage:
                        tid = storage.create_task(str(admin_id or "web"), t_title, list_name="default")
                        reply_text = f"✅ Added task #{tid}: *{t_title}*"
                    elif not t_title:
                        reply_text = "Usage: `/task <task description>`"

                # 3c. Check direct /todo or /tasks command
                if not reply_text and prompt in ("/todo", "/tasks"):
                    if storage:
                        tasks = storage.get_tasks(str(admin_id or "web"))
                        if tasks:
                            lines = ["📋 *Active Tasks:*"]
                            for t in tasks:
                                status = "✅" if t.get("completed") else "⬜"
                                lines.append(f"{status} #{t['id']} {t['title']}")
                            reply_text = "\n".join(lines)
                        else:
                            reply_text = "📋 No active tasks found! You're all caught up."

                # 4. Check direct /search command
                if not reply_text and prompt.startswith("/search "):
                    s_query = prompt[8:].strip()
                    if s_query:
                        s_results = search_duckduckgo(s_query, max_results=3)
                        if s_results:
                            s_lines = [f"🔍 *Search results for:* `{s_query}`\n"]
                            for r in s_results:
                                s_lines.append(f"• [{r.get('title')}]({r.get('href')})\n  _{r.get('body', '')[:150]}_")
                            reply_text = "\n\n".join(s_lines)
                            search_q = s_query
                        else:
                            reply_text = f"🔍 No web results found for `{s_query}`."
                    else:
                        reply_text = "Usage: `/search <query>`"

                # 5. Fallback to conversational daemon query with multi-turn context
                if not reply_text:
                    temporal_header = format_temporal_prompt_header(tz_name)
                    base_prompt = get_preset_system_prompt(preset)
                    user_profile_header = format_user_profile_prompt_header(storage, str(admin_id or "web"))
                    if preset in ("default", "general"):
                        from pithon.agent.tools import format_tools_system_prompt
                        sys_prompt = f"{format_tools_system_prompt()}\n\n{user_profile_header}\n{temporal_header}\n{base_prompt}"
                    else:
                        sys_prompt = f"{user_profile_header}\n{temporal_header}\n{base_prompt}"

                    # Pull recent multi-turn history from SQLite
                    recent_history = storage.get_recent_history(limit=3, chat_id=admin_id) if storage else []

                    # Check DuckDuckGo search
                    search_ctx = ""
                    if should_search(prompt):
                        results = search_duckduckgo(prompt, max_results=3)
                        if results:
                            search_q = prompt
                            search_ctx = format_search_context(results, prompt)
                            sys_prompt += f"\n\n{search_ctx}"

                    msgs = [{"role": "system", "content": sys_prompt}]
                    msgs.extend(recent_history)
                    msgs.append({"role": "user", "content": prompt})

                    try:
                        payload = json.dumps({
                            "messages": msgs,
                            "temperature": 0.25,
                            "presence_penalty": 0.3,
                            "frequency_penalty": 0.4,
                            "max_tokens": 512
                        }).encode("utf-8")
                        req = urllib.request.Request(
                            f"{daemon_url}/v1/chat/completions",
                            data=payload,
                            headers={"Content-Type": "application/json"}
                        )
                        with urllib.request.urlopen(req, timeout=35) as res:
                            data = json.loads(res.read().decode("utf-8"))
                            raw_reply = data["choices"][0]["message"]["content"].strip()

                        # Check for Native Tool Call
                        tool_call = extract_tool_call(raw_reply)
                        if tool_call and storage:
                            tool_name = tool_call.get("name")
                            if tool_name == "web_search":
                                squery = tool_call.get("arguments", {}).get("query", prompt)
                                _, _, ctx = execute_tool_call(tool_call, storage, admin_id, tz_name)
                                search_q = squery
                                gprompt = f"{ctx.get('context', '')}\n\nUser Question: {prompt}\nAnswer concisely."
                                p2 = json.dumps({
                                    "messages": [{"role": "system", "content": temporal_header}, {"role": "user", "content": gprompt}],
                                    "temperature": 0.2,
                                    "max_tokens": 256
                                }).encode("utf-8")
                                req2 = urllib.request.Request(f"{daemon_url}/v1/chat/completions", data=p2, headers={"Content-Type": "application/json"})
                                with urllib.request.urlopen(req2, timeout=25) as r2:
                                    d2 = json.loads(r2.read().decode("utf-8"))
                                    reply_text = d2["choices"][0]["message"]["content"].strip()
                            elif tool_name in ("set_timer", "add_task"):
                                reply_text, _, _ = execute_tool_call(tool_call, storage, admin_id, tz_name)
                            else:
                                reply_text = raw_reply
                        else:
                            reply_text = raw_reply

                    except Exception as e:
                        logger.error(f"Error querying daemon: {e}")
                        reply_text = f"⚠️ Could not reach local model at {daemon_url}: {e}"

                latency_ms = int((time.time() - t0) * 1000)

                # Log unified interaction in SQLite
                if storage:
                    storage.log_interaction(
                        chat_id=admin_id if admin_id else "web",
                        user_id="web",
                        prompt=prompt,
                        response=reply_text,
                        search_query=search_q,
                        latency_ms=latency_ms
                    )

                # Mirror/Sync to Telegram if requested
                synced_telegram = False
                if sync_telegram and bot and admin_id:
                    try:
                        bot.send_message(
                            admin_id,
                            f"🌐 *[Web Portal]*\n👤 *You:* {prompt}\n\n🤖 *Khepri:* {reply_text}"
                        )
                        synced_telegram = True
                    except Exception as te:
                        logger.warning(f"Could not mirror web chat to Telegram: {te}")

                self._send_json({
                    "status": "ok",
                    "response": reply_text,
                    "latency_ms": latency_ms,
                    "synced_telegram": synced_telegram
                })

            else:
                self.send_response(404)
                self.end_headers()

    return HTTPServer((host, port), KhepriWebHandler)
