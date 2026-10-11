"""World-class dark-mode Web UI dashboard and REST API for Khepri Autonomous Agent."""

import http.cookies
import json
import logging
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
        agent_rss_mb = 18.0

    host_total_mb = 0
    host_avail_mb = 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    host_total_mb = round(int(line.split()[1]) / 1024)
                elif line.startswith("MemAvailable:"):
                    host_avail_mb = round(int(line.split()[1]) / 1024)
    except Exception:
        pass
    host_used_mb = max(0, host_total_mb - host_avail_mb)

    daemon_online = False
    daemon_latency_ms = None
    daemon_model = "Qwen2.5-0.5B"
    daemon_threads = 2
    daemon_uptime_sec = 0

    t0 = time.time()
    try:
        req = urllib.request.Request(f"{daemon_url}/health")
        with urllib.request.urlopen(req, timeout=2.0) as res:
            daemon_latency_ms = round((time.time() - t0) * 1000, 1)
            if res.status == 200:
                d = json.loads(res.read().decode())
                daemon_online = (d.get("status") == "ok")
                daemon_uptime_sec = d.get("uptime_sec", 0)
                daemon_threads = d.get("threads", 2)
                raw_model = d.get("model", "")
                if "/" in raw_model:
                    daemon_model = raw_model.split("/")[-1].replace(".gguf", "")
                elif raw_model:
                    daemon_model = raw_model.replace(".gguf", "")
    except Exception:
        daemon_online = False

    return {
        "agent_rss_mb": agent_rss_mb,
        "host_total_mb": host_total_mb,
        "host_used_mb": host_used_mb,
        "host_avail_mb": host_avail_mb,
        "daemon_online": daemon_online,
        "daemon_latency_ms": daemon_latency_ms,
        "daemon_model": daemon_model,
        "daemon_threads": daemon_threads,
        "daemon_uptime_sec": daemon_uptime_sec,
    }

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Khepri • Management Portal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #06080e;
      --card-bg: rgba(13, 18, 30, 0.72);
      --border: rgba(255, 255, 255, 0.09);
      --border-focus: rgba(99, 102, 241, 0.6);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --cyan: #06b6d4;
      --emerald: #10b981;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
      position: relative;
      overflow: hidden;
    }
    /* Ambient Glowing Aurora Background */
    .glow-orb-1 {
      position: absolute;
      top: -10%;
      left: 20%;
      width: 550px;
      height: 550px;
      background: radial-gradient(circle, rgba(99, 102, 241, 0.28) 0%, rgba(99, 102, 241, 0) 70%);
      filter: blur(80px);
      pointer-events: none;
      animation: float 14s ease-in-out infinite alternate;
    }
    .glow-orb-2 {
      position: absolute;
      bottom: -15%;
      right: 15%;
      width: 600px;
      height: 600px;
      background: radial-gradient(circle, rgba(6, 182, 212, 0.2) 0%, rgba(6, 182, 212, 0) 70%);
      filter: blur(90px);
      pointer-events: none;
      animation: float 18s ease-in-out infinite alternate-reverse;
    }
    .grid-overlay {
      position: absolute;
      inset: 0;
      background-image: radial-gradient(rgba(255, 255, 255, 0.07) 1px, transparent 1px);
      background-size: 28px 28px;
      mask-image: radial-gradient(ellipse at center, black 40%, transparent 80%);
      pointer-events: none;
    }
    @keyframes float {
      0% { transform: translateY(0px) scale(1); }
      100% { transform: translateY(40px) scale(1.08); }
    }
    .card-wrap {
      position: relative;
      width: 100%;
      max-width: 440px;
      z-index: 10;
    }
    .card-halo {
      position: absolute;
      inset: -2px;
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.45), rgba(6, 182, 212, 0.3), rgba(16, 185, 129, 0.2));
      border-radius: 1.35rem;
      filter: blur(12px);
      opacity: 0.6;
      transition: opacity 0.3s;
    }
    .card-wrap:hover .card-halo { opacity: 0.85; }
    .card {
      position: relative;
      background: var(--card-bg);
      backdrop-filter: blur(28px);
      -webkit-backdrop-filter: blur(28px);
      border: 1px solid var(--border);
      border-radius: 1.25rem;
      padding: 2.5rem 2.25rem;
      box-shadow: 0 30px 60px -15px rgba(0, 0, 0, 0.75), inset 0 1px 0 0 rgba(255, 255, 255, 0.12);
    }
    .header {
      display: flex;
      align-items: center;
      gap: 1rem;
      margin-bottom: 2rem;
    }
    .logo-badge {
      background: linear-gradient(135deg, #6366f1 0%, #06b6d4 100%);
      width: 3.25rem;
      height: 3.25rem;
      border-radius: 0.875rem;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.625rem;
      font-weight: 800;
      box-shadow: 0 8px 20px -4px rgba(99, 102, 241, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.3);
      flex-shrink: 0;
    }
    h1 {
      font-size: 1.45rem;
      font-weight: 700;
      letter-spacing: -0.025em;
      line-height: 1.2;
      background: linear-gradient(to right, #ffffff, #cbd5e1);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--emerald);
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.25);
      border-radius: 9999px;
      padding: 0.2rem 0.55rem;
      margin-top: 0.35rem;
    }
    .status-dot {
      width: 6px;
      height: 6px;
      background: var(--emerald);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--emerald);
      animation: pulse-dot 2s infinite;
    }
    @keyframes pulse-dot {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }
    form { display: flex; flex-direction: column; gap: 1.25rem; }
    .field-group { display: flex; flex-direction: column; gap: 0.45rem; }
    label {
      font-size: 0.8125rem;
      font-weight: 600;
      color: #cbd5e1;
      display: flex;
      justify-content: space-between;
    }
    .input-wrap {
      position: relative;
      display: flex;
      align-items: center;
    }
    input[type="password"], input[type="text"] {
      width: 100%;
      background: rgba(6, 10, 18, 0.85);
      border: 1px solid var(--border);
      border-radius: 0.625rem;
      padding: 0.875rem 2.8rem 0.875rem 1rem;
      color: var(--text);
      font-size: 0.9375rem;
      font-family: inherit;
      outline: none;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    input::placeholder { color: #475569; }
    input:focus {
      border-color: #6366f1;
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.25), 0 0 20px rgba(99, 102, 241, 0.2);
      background: rgba(10, 14, 26, 0.95);
    }
    .toggle-pwd {
      position: absolute;
      right: 0.75rem;
      background: none;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      padding: 0.25rem;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: color 0.15s;
    }
    .toggle-pwd:hover { color: var(--text); }
    button[type="submit"] {
      background: linear-gradient(135deg, #4f46e5 0%, #6366f1 60%, #06b6d4 100%);
      color: white;
      border: none;
      border-radius: 0.625rem;
      padding: 0.9rem 1rem;
      font-size: 0.95rem;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      box-shadow: 0 8px 24px -4px rgba(99, 102, 241, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.25);
      margin-top: 0.5rem;
    }
    button[type="submit"]:hover {
      transform: translateY(-1px);
      box-shadow: 0 12px 30px -4px rgba(99, 102, 241, 0.7);
      filter: brightness(1.08);
    }
    button[type="submit"]:active { transform: translateY(0); }
    .err-msg {
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.3);
      color: #fca5a5;
      font-size: 0.8125rem;
      border-radius: 0.5rem;
      padding: 0.65rem 0.875rem;
      display: none;
      animation: shake 0.35s ease-in-out;
    }
    @keyframes shake {
      0%, 100% { transform: translateX(0); }
      20%, 60% { transform: translateX(-6px); }
      40%, 80% { transform: translateX(6px); }
    }
    .footer-note {
      margin-top: 1.75rem;
      padding-top: 1.25rem;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: #64748b;
      font-size: 0.75rem;
    }
    .footer-note code {
      font-family: 'JetBrains Mono', monospace;
      color: #94a3b8;
      background: rgba(255, 255, 255, 0.05);
      padding: 0.15rem 0.35rem;
      border-radius: 0.25rem;
    }
  </style>
</head>
<body>
  <div class="glow-orb-1"></div>
  <div class="glow-orb-2"></div>
  <div class="grid-overlay"></div>

  <div class="card-wrap">
    <div class="card-halo"></div>
    <div class="card">
      <div class="header">
        <div class="logo-badge" style="padding: 4px; display: flex; align-items: center; justify-content: center;"><svg viewBox="0 0 120 120" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 26px; height: 26px;"><circle cx="60" cy="24" r="8"/><circle cx="60" cy="24" r="13" stroke-dasharray="2 3" stroke-width="1.5"/><path d="M 60 7 L 60 12"/><path d="M 60 36 L 60 41"/><path d="M 43 24 L 48 24"/><path d="M 72 24 L 77 24"/><path d="M 52 46 C 46 38 46 28 51 22"/><path d="M 68 46 C 74 38 74 28 69 22"/><path d="M 54 46 Q 60 43 66 46 L 68 50 Q 60 52 52 50 Z"/><path d="M 50 51 Q 60 48 70 51 L 73 58 Q 60 61 47 58 Z"/><path d="M 47 54 C 36 44 26 32 23 20 C 21 34 26 48 37 60"/><path d="M 73 54 C 84 44 94 32 97 20 C 99 34 94 48 83 60"/><path d="M 47 58 C 43 72 45 88 60 96 C 75 88 77 72 73 58 Z"/><path d="M 60 59 L 60 96"/><path d="M 60 63 L 67 70 L 60 77 L 53 70 Z"/><path d="M 44 65 L 34 73 L 33 83"/><path d="M 76 65 L 86 73 L 87 83"/><path d="M 47 84 L 37 94 L 40 106"/><path d="M 73 84 L 83 94 L 80 106"/></svg></div>
        <div>
          <h1>Khepri</h1>
          <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.2rem; font-weight: 500;">Management Portal</div>
          <div class="status-pill" style="margin-top: 0.45rem;">
            <span class="status-dot"></span>
            <span>Qwen2.5-0.5B • Online</span>
          </div>
        </div>
      </div>

      <form id="loginForm">
        <div class="field-group">
          <label for="password">
            <span>Passphrase</span>
            <span style="font-size: 0.72rem; color: #64748b; font-weight: normal;">Oracle Cloud VM</span>
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
      if (pwdInput.type === 'password') {
        pwdInput.type = 'text';
        toggleBtn.style.color = '#6366f1';
      } else {
        pwdInput.type = 'password';
        toggleBtn.style.color = '';
      }
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

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Khepri • Management Portal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #06080e;
      --card-bg: rgba(13, 17, 28, 0.75);
      --card-hover: rgba(19, 26, 42, 0.85);
      --border: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(99, 102, 241, 0.4);
      --text: #f8fafc;
      --text-muted: #94a3b8;
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
        radial-gradient(circle at 10% 20%, rgba(6, 182, 212, 0.07) 0%, transparent 40%),
        radial-gradient(circle at 90% 80%, rgba(99, 102, 241, 0.08) 0%, transparent 40%);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: rgba(6, 8, 14, 0.85);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border);
      padding: 0.85rem 1.75rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.85rem;
    }
    .badge {
      width: 36px;
      height: 36px;
      border-radius: 0.65rem;
      background: linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(99, 102, 241, 0.3));
      border: 1px solid rgba(6, 182, 212, 0.4);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #38bdf8;
      box-shadow: 0 0 16px rgba(6, 182, 212, 0.3);
    }
    .brand-title {
      font-weight: 800;
      font-size: 1.15rem;
      background: linear-gradient(135deg, #f8fafc 40%, #94a3b8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: -0.02em;
    }
    nav {
      display: flex;
      gap: 0.35rem;
      background: rgba(255, 255, 255, 0.03);
      padding: 0.25rem;
      border-radius: 0.65rem;
      border: 1px solid var(--border);
    }
    nav button {
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 0.45rem 0.9rem;
      font-size: 0.82rem;
      font-weight: 600;
      border-radius: 0.45rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    nav button:hover { color: var(--text); }
    nav button.active {
      background: rgba(255, 255, 255, 0.08);
      color: var(--text);
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 0.65rem;
    }
    .btn-refresh {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 0.4rem 0.75rem;
      border-radius: 0.45rem;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-refresh:hover { color: var(--text); border-color: rgba(255,255,255,0.2); }
    .logout-btn {
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.2);
      color: #fca5a5;
      padding: 0.4rem 0.75rem;
      border-radius: 0.45rem;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }
    .logout-btn:hover { background: rgba(239, 68, 68, 0.2); }
    
    main {
      flex: 1;
      max-width: 1200px;
      width: 100%;
      margin: 0 auto;
      padding: 1.75rem;
    }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* STATS CARDS */
    .grid-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }
    .stat-card {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 0.85rem;
      padding: 1.15rem 1.25rem;
      position: relative;
      overflow: hidden;
      transition: transform 0.2s, border-color 0.2s;
    }
    .stat-card:hover { transform: translateY(-2px); border-color: var(--border-focus); }
    .stat-card::after {
      content: "";
      position: absolute;
      top: 0; left: 0; width: 100%; height: 3px;
      background: var(--stat-accent, var(--primary));
    }
    .stat-label {
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .stat-value {
      font-size: 1.55rem;
      font-weight: 800;
      margin: 0.35rem 0 0.2rem 0;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 0.45rem;
    }
    .stat-meta {
      font-size: 0.75rem;
      color: #64748b;
      font-family: 'JetBrains Mono', monospace;
    }

    /* CARDS & PANELS */
    .card-box {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 0.85rem;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
    }
    .card-box h3 {
      font-size: 1.15rem;
      font-weight: 700;
      margin-bottom: 0.4rem;
      letter-spacing: -0.01em;
    }

    /* TABLE */
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 1rem;
      font-size: 0.85rem;
    }
    th {
      text-align: left;
      padding: 0.75rem 1rem;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    td {
      padding: 0.85rem 1rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: middle;
    }
    tr:hover td { background: rgba(255, 255, 255, 0.015); }

    /* BADGES */
    .badge-chip {
      display: inline-block;
      padding: 0.2rem 0.55rem;
      border-radius: 0.375rem;
      font-size: 0.72rem;
      font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
    }
    .chip-done { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .chip-active { background: rgba(245, 158, 11, 0.15); color: #fbbf24; cursor: pointer; }
    .chip-timer { background: rgba(99, 102, 241, 0.15); color: #a5b4fc; }
    .chip-task { background: rgba(6, 182, 212, 0.15); color: #67e8f9; }

    /* ACTION BUTTONS */
    .btn-action {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 0.25rem 0.5rem;
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.75rem;
      transition: all 0.15s;
    }
    .btn-action:hover { color: #f87171; border-color: rgba(239, 68, 68, 0.4); }

    /* FORMS & INPUTS */
    .form-inline {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-top: 1rem;
      background: rgba(255, 255, 255, 0.02);
      padding: 1rem;
      border-radius: 0.65rem;
      border: 1px solid var(--border);
    }
    .input-field {
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border);
      color: #fff;
      padding: 0.6rem 0.85rem;
      border-radius: 0.45rem;
      font-size: 0.85rem;
      font-family: inherit;
    }
    .input-field:focus { outline: none; border-color: var(--primary); }
    .btn {
      background: linear-gradient(135deg, var(--primary), var(--primary-hover));
      color: #fff;
      border: none;
      border-radius: 0.45rem;
      padding: 0.6rem 1.15rem;
      font-weight: 600;
      font-size: 0.85rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn:hover { filter: brightness(1.1); transform: translateY(-1px); }

    /* CHAT PLAYGROUND */
    .chat-box {
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
      max-height: 480px;
      overflow-y: auto;
      padding: 1rem;
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid var(--border);
      border-radius: 0.65rem;
      margin-top: 1rem;
    }
    .chat-bubble {
      max-width: 80%;
      padding: 0.85rem 1.15rem;
      border-radius: 0.75rem;
      font-size: 0.88rem;
      line-height: 1.55;
    }
    .chat-user {
      align-self: flex-end;
      background: linear-gradient(135deg, #4f46e5, #6366f1);
      color: #fff;
      border-bottom-right-radius: 0.2rem;
    }
    .chat-assistant {
      align-self: flex-start;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border);
      color: #e2e8f0;
      border-bottom-left-radius: 0.2rem;
    }
    .pulse-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
      70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
      100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="badge">
        <svg viewBox="0 0 120 120" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 22px; height: 22px;">
          <circle cx="60" cy="24" r="8"/><circle cx="60" cy="24" r="13" stroke-dasharray="2 3" stroke-width="1.5"/><path d="M 60 7 L 60 12"/><path d="M 60 36 L 60 41"/><path d="M 43 24 L 48 24"/><path d="M 72 24 L 77 24"/><path d="M 52 46 C 46 38 46 28 51 22"/><path d="M 68 46 C 74 38 74 28 69 22"/><path d="M 54 46 Q 60 43 66 46 L 68 50 Q 60 52 52 50 Z"/><path d="M 50 51 Q 60 48 70 51 L 73 58 Q 60 61 47 58 Z"/><path d="M 47 54 C 36 44 26 32 23 20 C 21 34 26 48 37 60"/><path d="M 73 54 C 84 44 94 32 97 20 C 99 34 94 48 83 60"/><path d="M 47 58 C 43 72 45 88 60 96 C 75 88 77 72 73 58 Z"/><path d="M 60 59 L 60 96"/><path d="M 60 63 L 67 70 L 60 77 L 53 70 Z"/><path d="M 44 65 L 34 73 L 33 83"/><path d="M 76 65 L 86 73 L 87 83"/><path d="M 47 84 L 37 94 L 40 106"/><path d="M 73 84 L 83 94 L 80 106"/>
        </svg>
      </div>
      <div>
        <div class="brand-title">Khepri</div>
        <div style="font-size: 0.72rem; color: #10b981; font-weight: 600; display: flex; align-items: center; gap: 0.35rem;">
          <span class="pulse-dot"></span>
          <span id="navStatus">Live System Telemetry</span> • <span id="navTz">Asia/Kolkata</span>
        </div>
      </div>
    </div>
    <nav>
      <button class="active" onclick="switchTab('overview')">Overview</button>
      <button onclick="switchTab('playground')">Live Chat</button>
      <button onclick="switchTab('tasks')">Tasks & Timers</button>
      <button onclick="switchTab('notes')">Knowledge Memory</button>
      <button onclick="switchTab('interactions')">Audit Log</button>
      <button onclick="switchTab('digests')">Digests</button>
    </nav>
    <div class="header-actions">
      <button class="btn-refresh" onclick="loadStats()">↻ Refresh</button>
      <button class="logout-btn" onclick="logout()">Logout</button>
    </div>
  </header>

  <main>
    <!-- OVERVIEW TAB -->
    <div id="tab-overview" class="tab-content active">
      <div class="grid-stats">
        <div class="stat-card" style="--stat-accent: #10b981;">
          <div class="stat-label">Inference Engine</div>
          <div class="stat-value">
            <span id="statEngineStatus" style="color: #10b981;">Checking...</span>
            <span id="statEngineLatency" style="font-size: 0.85rem; color: #94a3b8; font-family: monospace;"></span>
          </div>
          <div class="stat-meta" id="statEngineMeta">Connecting to 127.0.0.1:8090...</div>
        </div>

        <div class="stat-card" style="--stat-accent: #06b6d4;">
          <div class="stat-label">Memory (Process RSS)</div>
          <div class="stat-value" id="statRss">-- MB</div>
          <div class="stat-meta" id="statHostRam">Host RAM: calculating...</div>
        </div>

        <div class="stat-card" style="--stat-accent: #6366f1;">
          <div class="stat-label">Audit Interactions</div>
          <div class="stat-value" id="statInteractions">0</div>
          <div class="stat-meta">Logged in SQLite WAL</div>
        </div>

        <div class="stat-card" style="--stat-accent: #f59e0b;">
          <div class="stat-label">Tasks & Timers</div>
          <div class="stat-value" id="statTasks">0</div>
          <div class="stat-meta" id="statTasksMeta">0 Pending</div>
        </div>

        <div class="stat-card" style="--stat-accent: #ec4899;">
          <div class="stat-label">Markdown Memory</div>
          <div class="stat-value" id="statNotes">0</div>
          <div class="stat-meta" id="statNotesMeta">Saved Knowledge Notes</div>
        </div>
      </div>

      <div class="card-box">
        <h3>Architecture & Active Capabilities</h3>
        <p style="color: var(--text-muted); font-size: 0.88rem; line-height: 1.6;">
          Co-located on Oracle Cloud ARM Ampere A1 VM alongside OwnTracks Recorder.
          Protected via hard Linux cgroups (<code>khepri-daemon: 1.0 CPU, 2048M RAM</code> | <code>khepri-agent: 0.5 CPU, 512M RAM</code>).
        </p>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-top: 1.25rem;">
          <div style="padding: 1.15rem; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 0.75rem;">
            <div style="font-weight: 700; color: #a5b4fc;">⚡ Native Qwen2.5 Tool Calling</div>
            <div style="font-size: 0.82rem; color: #94a3b8; margin-top: 0.35rem;">
              Countdown timers, task lists, live web search, safe math, and wttr.in weather.
            </div>
          </div>
          <div style="padding: 1.15rem; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 0.75rem;">
            <div style="font-weight: 700; color: #6ee7b7;">🛡️ Whitelist Telegram Security</div>
            <div style="font-size: 0.82rem; color: #94a3b8; margin-top: 0.35rem;">
              Admin ID: <code id="confAdminId" style="color: #6ee7b7;">Loading...</code><br>
              Report Channel: <code id="confReportId" style="color: #94a3b8;">Loading...</code>
            </div>
          </div>
          <div style="padding: 1.15rem; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 0.75rem;">
            <div style="font-weight: 700; color: #38bdf8;">📝 Markdown Persistent Memory</div>
            <div style="font-size: 0.82rem; color: #94a3b8; margin-top: 0.35rem;">
              Saved notes stored in <code>data/notes/*.md</code>.<br>
              Active Files: <strong id="confNotesCount" style="color: #38bdf8;">0</strong> files.
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- LIVE CHAT / PLAYGROUND TAB -->
    <div id="tab-playground" class="tab-content">
      <div class="card-box">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
          <div>
            <h3>Live Agent Chat & Inference</h3>
            <p style="color: var(--text-muted); font-size: 0.85rem;">Interactive multi-turn conversation with local Qwen2.5-0.5B model.</p>
          </div>
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <label style="font-size: 0.8rem; color: var(--text-muted);">Preset:</label>
            <select id="chatPreset" class="input-field" style="padding: 0.4rem 0.65rem;">
              <option value="default">General Assistant</option>
              <option value="log-analyzer">Log Analyzer</option>
              <option value="reminder">Task Reminder</option>
              <option value="weather">Weather Analyst</option>
            </select>
            <button class="btn-action" onclick="clearChat()">Clear</button>
          </div>
        </div>

        <div id="chatHistory" class="chat-box">
          <div class="chat-bubble chat-assistant">
            👋 <strong>Welcome to Khepri.</strong> I am your autonomous edge assistant running locally on ARM. Ask a question, test calculations, schedule a reminder, or request weather!
          </div>
        </div>

        <div style="margin-top: 1rem; display: flex; gap: 0.75rem;">
          <textarea id="playgroundPrompt" rows="2" class="input-field" style="flex: 1; resize: vertical;" placeholder="Type prompt (e.g. 'How is weather in Kolkata?', 'Calculate 45 * 18.5', 'Remember server IP is 10.0.0.1')..."></textarea>
          <button class="btn" id="playBtn" onclick="runPlayground()" style="align-self: flex-end; padding: 0.75rem 1.25rem;">Send</button>
        </div>
      </div>
    </div>

    <!-- TASKS & TIMERS TAB -->
    <div id="tab-tasks" class="tab-content">
      <div class="card-box">
        <h3>Tasks, Timers & Reminders</h3>
        <p style="color: var(--text-muted); font-size: 0.85rem;">Active to-dos and countdown timers monitored by background scheduler.</p>
        
        <!-- Add Task Form -->
        <div class="form-inline">
          <input type="text" id="newTaskTitle" class="input-field" style="flex: 2; min-width: 220px;" placeholder="Task description or reminder...">
          <select id="newTaskList" class="input-field">
            <option value="default">Task</option>
            <option value="timer">Timer</option>
            <option value="work">Work</option>
            <option value="personal">Personal</option>
          </select>
          <input type="datetime-local" id="newTaskDue" class="input-field" title="Optional due timestamp">
          <button class="btn" onclick="addTask()">+ Add Task</button>
        </div>

        <div style="overflow-x: auto;">
          <table id="tasksTable">
            <thead>
              <tr>
                <th style="width: 40px;">Status</th>
                <th>ID</th>
                <th>Type</th>
                <th>Title</th>
                <th>Due At</th>
                <th style="text-align: right;">Action</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Loading tasks...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- KNOWLEDGE MEMORY TAB -->
    <div id="tab-notes" class="tab-content">
      <div class="card-box">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
          <div>
            <h3>Markdown Knowledge & Memory Files</h3>
            <p style="color: var(--text-muted); font-size: 0.85rem;">Persistent notes saved in <code>data/notes/*.md</code>.</p>
          </div>
          <div style="display: flex; gap: 0.5rem;">
            <input type="text" id="searchNotesInput" class="input-field" placeholder="Filter notes..." oninput="filterNotes()" style="padding: 0.4rem 0.75rem;">
            <button class="btn" onclick="toggleNewNoteForm()">+ New Note</button>
          </div>
        </div>

        <!-- Add Note Form (Collapsible) -->
        <div id="newNoteForm" style="display: none; margin-top: 1rem; background: rgba(255,255,255,0.02); padding: 1.25rem; border: 1px solid var(--border); border-radius: 0.75rem;">
          <div style="font-weight: 700; margin-bottom: 0.75rem;">Create Markdown Note</div>
          <div style="display: flex; gap: 0.75rem; margin-bottom: 0.75rem; flex-wrap: wrap;">
            <input type="text" id="newNoteTitle" class="input-field" style="flex: 2; min-width: 200px;" placeholder="Title (e.g. WiFi Password, Server Specs)...">
            <input type="text" id="newNoteTags" class="input-field" style="flex: 1; min-width: 150px;" placeholder="Tags (e.g. config, personal)...">
          </div>
          <textarea id="newNoteContent" rows="4" class="input-field" style="width: 100%; margin-bottom: 0.75rem;" placeholder="Markdown note body..."></textarea>
          <div style="display: flex; gap: 0.5rem;">
            <button class="btn" onclick="addNote()">Save Note</button>
            <button class="btn-action" onclick="toggleNewNoteForm(false)">Cancel</button>
          </div>
        </div>

        <div id="notesContainer" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1rem; margin-top: 1.25rem;">
          <div style="color: var(--text-muted); font-size: 0.85rem;">Loading markdown memory...</div>
        </div>
      </div>
    </div>

    <!-- AUDIT LOG TAB -->
    <div id="tab-interactions" class="tab-content">
      <div class="card-box">
        <h3>Interactions Audit Explorer</h3>
        <p style="color: var(--text-muted); font-size: 0.85rem;">Chronological record of user prompts, tool calls, and model responses.</p>
        <div style="overflow-x: auto;">
          <table id="interactionsTable">
            <thead>
              <tr>
                <th>Time (Kolkata)</th>
                <th>Prompt</th>
                <th>Response</th>
                <th>Search Grounding</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading interactions...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- DIGESTS TAB -->
    <div id="tab-digests" class="tab-content">
      <div class="card-box">
        <h3>Hourly Digest Archive</h3>
        <p style="color: var(--text-muted); font-size: 0.85rem;">Periodic analytical summaries dispatched to Telegram report channel.</p>
        <div style="overflow-x: auto;">
          <table id="digestsTable">
            <thead>
              <tr>
                <th>Generated At</th>
                <th>Items Count</th>
                <th>Summary Content</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colspan="3" style="text-align: center; color: var(--text-muted);">Loading digests...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </main>

  <script>
    let allNotesCache = [];

    function switchTab(name) {
      document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      const target = document.getElementById('tab-' + name);
      if (target) target.classList.add('active');
      if (event && event.target && event.target.tagName === 'BUTTON') {
        event.target.classList.add('active');
      }
      if (name === 'interactions') loadInteractions();
      if (name === 'tasks') loadTasks();
      if (name === 'notes') loadNotes();
      if (name === 'digests') loadDigests();
    }

    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        if (res.ok) {
          const d = await res.json();
          document.getElementById('statInteractions').innerText = d.total_interactions || 0;
          document.getElementById('statTasks').innerText = d.pending_tasks || 0;
          document.getElementById('statTasksMeta').innerText = `${d.pending_tasks || 0} Pending / ${d.total_tasks || 0} Total`;
          document.getElementById('statNotes').innerText = d.total_notes || 0;
          document.getElementById('statNotesMeta').innerText = `${d.total_notes || 0} Saved Notes`;
          document.getElementById('confNotesCount').innerText = d.total_notes || 0;
          
          if (d.admin_id) document.getElementById('confAdminId').innerText = d.admin_id;
          if (d.report_id) document.getElementById('confReportId').innerText = d.report_id;
          if (d.timezone) {
            document.getElementById('navTz').innerText = d.timezone;
          }

          const t = d.telemetry || {};
          // Engine status
          const engineStatus = document.getElementById('statEngineStatus');
          if (t.daemon_online) {
            engineStatus.innerText = 'Online';
            engineStatus.style.color = '#10b981';
            document.getElementById('statEngineLatency').innerText = t.daemon_latency_ms ? `⚡ ${t.daemon_latency_ms}ms` : '';
            const uptimeMin = Math.round((t.daemon_uptime_sec || 0) / 60);
            document.getElementById('statEngineMeta').innerText = `${t.daemon_model || 'Qwen2.5-0.5B'} • Uptime: ${uptimeMin}m • ${t.daemon_threads || 2} Threads`;
          } else {
            engineStatus.innerText = 'Offline';
            engineStatus.style.color = '#ef4444';
            document.getElementById('statEngineMeta').innerText = 'Daemon unreachable on 8090';
          }

          // Memory
          if (t.agent_rss_mb) {
            document.getElementById('statRss').innerText = `${t.agent_rss_mb} MB`;
          }
          if (t.host_total_mb && t.host_used_mb) {
            const hostPct = Math.round((t.host_used_mb / t.host_total_mb) * 100);
            document.getElementById('statHostRam').innerText = `Host RAM: ${t.host_used_mb}MB / ${t.host_total_mb}MB (${hostPct}%)`;
          }
        }
      } catch (e) {
        console.error("Error loading stats:", e);
      }
    }

    async function loadTasks() {
      const tbody = document.querySelector('#tasksTable tbody');
      try {
        const res = await fetch('/api/tasks');
        if (res.ok) {
          const data = await res.json();
          if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">No active tasks or timers. Use the form above to add one!</td></tr>';
            return;
          }
          tbody.innerHTML = data.map(t => `
            <tr style="${t.is_completed ? 'opacity: 0.55;' : ''}">
              <td style="text-align: center;">
                <input type="checkbox" ${t.is_completed ? 'checked' : ''} onchange="toggleTask(${t.id})" style="cursor: pointer; width: 16px; height: 16px;">
              </td>
              <td style="font-family: monospace; color: var(--text-muted);">#${t.id}</td>
              <td><span class="badge-chip ${t.list_name === 'timer' ? 'chip-timer' : 'chip-task'}">${escapeHtml(t.list_name || 'task')}</span></td>
              <td style="font-weight: 600; ${t.is_completed ? 'text-decoration: line-through;' : ''}">${escapeHtml(t.title)}</td>
              <td style="font-family: monospace; font-size: 0.8rem; color: #94a3b8;">${t.due_at ? t.due_at.slice(0, 16).replace('T', ' ') : '—'}</td>
              <td style="text-align: right;">
                <button class="btn-action" onclick="deleteTask(${t.id})" title="Delete task">🗑️</button>
              </td>
            </tr>
          `).join('');
        }
      } catch (e) {
        tbody.innerHTML = '<tr><td colspan="6" style="color: #f87171;">Error loading tasks.</td></tr>';
      }
    }

    async function addTask() {
      const title = document.getElementById('newTaskTitle').value.trim();
      const listName = document.getElementById('newTaskList').value;
      const due = document.getElementById('newTaskDue').value;
      if (!title) return;

      try {
        const res = await fetch('/api/tasks/add', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({title: title, list_name: listName, due_at: due || null})
        });
        if (res.ok) {
          document.getElementById('newTaskTitle').value = '';
          document.getElementById('newTaskDue').value = '';
          loadTasks();
          loadStats();
        }
      } catch (e) {
        alert('Failed to add task: ' + e);
      }
    }

    async function toggleTask(id) {
      try {
        await fetch('/api/tasks/toggle', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id: id})
        });
        loadTasks();
        loadStats();
      } catch (e) {
        console.error(e);
      }
    }

    async function deleteTask(id) {
      if (!confirm('Delete this task?')) return;
      try {
        await fetch('/api/tasks/delete', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id: id})
        });
        loadTasks();
        loadStats();
      } catch (e) {
        alert('Failed to delete task');
      }
    }

    function toggleNewNoteForm(show) {
      const f = document.getElementById('newNoteForm');
      if (show === undefined) {
        f.style.display = (f.style.display === 'none') ? 'block' : 'none';
      } else {
        f.style.display = show ? 'block' : 'none';
      }
    }

    async function loadNotes() {
      const container = document.getElementById('notesContainer');
      try {
        const res = await fetch('/api/notes');
        if (res.ok) {
          allNotesCache = await res.json();
          renderNotes(allNotesCache);
        }
      } catch (e) {
        container.innerHTML = '<div style="color: #f87171;">Error loading notes.</div>';
      }
    }

    function renderNotes(notes) {
      const container = document.getElementById('notesContainer');
      if (!notes || notes.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 1.5rem 0;">No markdown notes match. Click "+ New Note" to write one!</div>';
        return;
      }
      container.innerHTML = notes.map(n => `
        <div style="padding: 1.25rem; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 0.75rem; position: relative;">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
            <div style="font-weight: 700; font-size: 1.05rem; color: #f8fafc;">${escapeHtml(n.title)}</div>
            <button class="btn-action" onclick="deleteNote('${n.filename}')" title="Delete note">🗑️</button>
          </div>
          <div style="font-size: 0.72rem; color: #64748b; font-family: monospace; margin-bottom: 0.75rem;">
            <code>${escapeHtml(n.filename)}</code>
          </div>
          <div style="font-size: 0.85rem; color: #cbd5e1; white-space: pre-wrap; max-height: 160px; overflow-y: auto; background: rgba(0,0,0,0.2); padding: 0.75rem; border-radius: 0.5rem; border: 1px solid rgba(255,255,255,0.03);">${escapeHtml(n.content || '')}</div>
        </div>
      `).join('');
    }

    function filterNotes() {
      const q = document.getElementById('searchNotesInput').value.toLowerCase().trim();
      if (!q) {
        renderNotes(allNotesCache);
        return;
      }
      const filtered = allNotesCache.filter(n => 
        (n.title && n.title.toLowerCase().includes(q)) ||
        (n.content && n.content.toLowerCase().includes(q)) ||
        (n.filename && n.filename.toLowerCase().includes(q))
      );
      renderNotes(filtered);
    }

    async function addNote() {
      const title = document.getElementById('newNoteTitle').value.trim();
      const tags = document.getElementById('newNoteTags').value.trim();
      const content = document.getElementById('newNoteContent').value.trim();
      if (!title || !content) {
        alert('Note title and content are required.');
        return;
      }
      try {
        const res = await fetch('/api/notes/add', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({title: title, tags: tags, content: content})
        });
        if (res.ok) {
          document.getElementById('newNoteTitle').value = '';
          document.getElementById('newNoteTags').value = '';
          document.getElementById('newNoteContent').value = '';
          toggleNewNoteForm(false);
          loadNotes();
          loadStats();
        }
      } catch (e) {
        alert('Failed to save note: ' + e);
      }
    }

    async function deleteNote(filename) {
      if (!confirm(`Delete markdown note "${filename}"?`)) return;
      try {
        await fetch('/api/notes/delete', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({filename: filename})
        });
        loadNotes();
        loadStats();
      } catch (e) {
        alert('Failed to delete note');
      }
    }

    async function loadInteractions() {
      const tbody = document.querySelector('#interactionsTable tbody');
      try {
        const res = await fetch('/api/interactions');
        if (res.ok) {
          const data = await res.json();
          if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No interactions logged yet. Use the Live Chat tab or Telegram bot!</td></tr>';
            return;
          }
          tbody.innerHTML = data.map(item => `
            <tr>
              <td style="white-space: nowrap; font-family: monospace; font-size: 0.8rem;">${(item.created_at || '').slice(0, 19).replace('T', ' ')}</td>
              <td style="font-weight: 600;">${escapeHtml(item.prompt)}</td>
              <td style="white-space: pre-wrap; font-size: 0.85rem; color: #cbd5e1;">${escapeHtml(item.response)}</td>
              <td>${item.search_query ? '<span class="badge-chip chip-task">' + escapeHtml(item.search_query) + '</span>' : '<span style="color:#64748b;">Direct</span>'}</td>
              <td style="font-family: monospace; font-size: 0.8rem; color: #94a3b8;">${item.latency_ms || 0}ms</td>
            </tr>
          `).join('');
        }
      } catch (e) {
        tbody.innerHTML = '<tr><td colspan="5" style="color: #f87171;">Error loading interactions.</td></tr>';
      }
    }

    async function loadDigests() {
      const tbody = document.querySelector('#digestsTable tbody');
      try {
        const res = await fetch('/api/digests');
        if (res.ok) {
          const data = await res.json();
          if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No digests logged yet. Hourly cron will archive digests here.</td></tr>';
            return;
          }
          tbody.innerHTML = data.map(d => `
            <tr>
              <td style="white-space: nowrap; font-family: monospace;">${(d.created_at || '').slice(0, 19).replace('T', ' ')}</td>
              <td style="font-family: monospace;">${d.items_count || 0} items</td>
              <td style="white-space: pre-wrap; font-size: 0.85rem; color: #cbd5e1;">${escapeHtml(d.content)}</td>
            </tr>
          `).join('');
        }
      } catch (e) {
        tbody.innerHTML = '<tr><td colspan="3" style="color: #f87171;">Error loading digests.</td></tr>';
      }
    }

    async function runPlayground() {
      const promptInput = document.getElementById('playgroundPrompt');
      const p = promptInput.value.trim();
      const btn = document.getElementById('playBtn');
      const history = document.getElementById('chatHistory');
      const preset = document.getElementById('chatPreset').value;
      if (!p) return;

      // Append User message
      history.innerHTML += `<div class="chat-bubble chat-user">${escapeHtml(p)}</div>`;
      promptInput.value = '';
      history.scrollTop = history.scrollHeight;

      btn.disabled = true;
      btn.innerText = '...';

      // Append thinking bubble
      const thinkingId = 'thinking_' + Date.now();
      history.innerHTML += `<div id="${thinkingId}" class="chat-bubble chat-assistant" style="opacity: 0.7;">Thinking with ${preset}...</div>`;
      history.scrollTop = history.scrollHeight;

      try {
        const res = await fetch('/api/playground', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({prompt: p, preset: preset})
        });
        const d = await res.json();
        const el = document.getElementById(thinkingId);
        if (el) {
          el.innerHTML = `<div>${escapeHtml(d.response || 'No response')}</div>` +
            `<div style="font-size: 0.7rem; color: #94a3b8; font-family: monospace; margin-top: 0.4rem;">⚡ ${d.latency_ms || 0}ms</div>`;
          el.style.opacity = '1';
        }
        loadStats();
      } catch (e) {
        const el = document.getElementById(thinkingId);
        if (el) el.innerHTML = `<span style="color: #f87171;">Error: ${escapeHtml(String(e))}</span>`;
      } finally {
        btn.disabled = false;
        btn.innerText = 'Send';
        history.scrollTop = history.scrollHeight;
      }
    }

    function clearChat() {
      document.getElementById('chatHistory').innerHTML = '<div class="chat-bubble chat-assistant">Chat history cleared. Send a prompt to start anew!</div>';
    }

    document.getElementById('playgroundPrompt').addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        runPlayground();
      }
    });

    async function logout() {
      await fetch('/api/logout', {method: 'POST'});
      window.location.href = '/login';
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    loadStats();
    setInterval(loadStats, 10000);
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
    tz_name: str = "Asia/Kolkata",
    admin_id: str = "",
    report_id: str = ""
) -> HTTPServer:
    """Create HTTP Server instance with session authentication, live telemetry, and interactive APIs."""

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
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            try:
                return json.loads(raw)
            except Exception:
                return {}

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/login":
                if self._is_authenticated():
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.end_headers()
                    return
                self._send_html(LOGIN_HTML)
                return

            # Protected Web App Dashboard & API
            if not self._is_authenticated():
                if path.startswith("/api/"):
                    self._send_json({"error": "Unauthorized"}, status=401)
                else:
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.end_headers()
                return

            if path == "/" or path == "/index.html":
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
                self._send_html('{"status":"ok"}', status=200, headers={"Set-Cookie": cookie, "Content-Type": "application/json"})

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

            elif path == "/api/playground":
                body = self._read_json_body()
                prompt = body.get("prompt", "").strip()
                preset = body.get("preset", "default").strip()
                if not prompt:
                    self._send_json({"error": "Empty prompt"}, status=400)
                    return

                t0 = time.time()
                search_q = None
                search_ctx = ""
                if should_search(prompt):
                    results = search_duckduckgo(prompt, max_results=3)
                    if results:
                        search_q = prompt
                        search_ctx = format_search_context(results)

                temporal_header = format_temporal_prompt_header(tz_name)
                base_prompt = get_preset_system_prompt(preset)
                sys_prompt = temporal_header + "\n" + base_prompt
                if search_ctx:
                    sys_prompt += f"\n\n{search_ctx}"

                msgs = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt}
                ]

                reply_text = "Simulated response"
                try:
                    payload = json.dumps({
                        "messages": msgs,
                        "temperature": 0.3,
                        "max_tokens": 256
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        f"{daemon_url}/v1/chat/completions",
                        data=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=15) as res:
                        data = json.loads(res.read().decode("utf-8"))
                        reply_text = data["choices"][0]["message"]["content"]
                except Exception as e:
                    reply_text = f"Daemon call failed: {e}"

                latency_ms = int((time.time() - t0) * 1000)
                if storage:
                    storage.log_interaction(
                        user_id="web",
                        prompt=prompt,
                        response=reply_text,
                        search_query=search_q,
                        latency_ms=latency_ms
                    )

                self._send_json({"status": "ok", "response": reply_text, "latency_ms": latency_ms})

            else:
                self.send_response(404)
                self.end_headers()

    return HTTPServer((host, port), KhepriWebHandler)
