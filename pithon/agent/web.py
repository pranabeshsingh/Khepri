"""World-class dark-mode Web UI dashboard and REST API for Pithon Mini-OpenClaw."""

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
from pithon.agent.memory import list_notes, get_note_content

logger = logging.getLogger("pithon.web")

# --- HTML & CSS UI TEMPLATES ---

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pithon • Agent Command Center</title>
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
        <div class="logo-badge">π</div>
        <div>
          <h1>Pithon Agent</h1>
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
  <title>Pithon • Agent Command Center</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #06080e;
      --card-bg: rgba(13, 18, 30, 0.72);
      --border: rgba(255, 255, 255, 0.08);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --cyan: #06b6d4;
      --emerald: #10b981;
      --rose: #f43f5e;
      --amber: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      position: relative;
    }
    header {
      border-bottom: 1px solid var(--border);
      background: rgba(10, 14, 26, 0.85);
      backdrop-filter: blur(20px);
      position: sticky;
      top: 0;
      z-index: 50;
      padding: 0.875rem 2rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand { display: flex; align-items: center; gap: 0.75rem; }
    .badge {
      background: linear-gradient(135deg, #6366f1, #06b6d4);
      width: 2.25rem;
      height: 2.25rem;
      border-radius: 0.625rem;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 1.15rem;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
    }
    .brand-title { font-weight: 700; font-size: 1.05rem; }
    nav {
      display: flex;
      gap: 0.35rem;
      background: rgba(255, 255, 255, 0.03);
      padding: 0.3rem;
      border-radius: 0.75rem;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }
    nav button {
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 0.45rem 0.9rem;
      border-radius: 0.5rem;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    nav button:hover { color: var(--text); background: rgba(255, 255, 255, 0.06); }
    nav button.active {
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(6, 182, 212, 0.15));
      color: #ffffff;
      border: 1px solid rgba(99, 102, 241, 0.4);
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.2);
    }
    .header-actions { display: flex; align-items: center; gap: 1rem; }
    .logout-btn {
      background: transparent;
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: var(--text-muted);
      padding: 0.45rem 0.85rem;
      border-radius: 0.5rem;
      font-size: 0.8125rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }
    .logout-btn:hover { color: var(--rose); border-color: rgba(244, 63, 94, 0.4); background: rgba(244, 63, 94, 0.08); }
    main {
      flex: 1;
      max-width: 1280px;
      width: 100%;
      margin: 0 auto;
      padding: 2.25rem 2rem;
    }
    .grid-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2rem;
    }
    .stat-card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.35rem 1.5rem;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.08);
      position: relative;
      overflow: hidden;
    }
    .stat-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, transparent, var(--stat-accent, var(--primary)), transparent);
    }
    .stat-label { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); font-weight: 700; }
    .stat-value { font-size: 1.85rem; font-weight: 800; margin-top: 0.4rem; letter-spacing: -0.02em; }
    .stat-meta { font-size: 0.78rem; color: #64748b; margin-top: 0.35rem; font-family: 'JetBrains Mono', monospace; }
    .card-box {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.75rem;
      box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.08);
      margin-bottom: 2rem;
    }
    .card-box h3 { font-size: 1.15rem; font-weight: 700; margin-bottom: 0.5rem; }
    .tab-content { display: none; }
    .tab-content.active { display: block; animation: fadeIn 0.25s ease-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
    table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 1.25rem; font-size: 0.875rem; }
    th {
      text-align: left;
      padding: 0.75rem 1rem;
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid var(--border);
      color: #94a3b8;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-weight: 700;
    }
    td { padding: 0.875rem 1rem; border-bottom: 1px solid rgba(255, 255, 255, 0.04); vertical-align: top; }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    .badge-chip {
      display: inline-block;
      padding: 0.2rem 0.55rem;
      border-radius: 0.375rem;
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
    }
    .chip-timer { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .chip-task { background: rgba(99, 102, 241, 0.15); color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.3); }
    .chip-active { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.3); }
    .chip-done { background: rgba(100, 116, 139, 0.2); color: #cbd5e1; border: 1px solid rgba(100, 116, 139, 0.3); }
    textarea, input[type="text"] {
      width: 100%;
      background: #080c16;
      border: 1px solid var(--border);
      border-radius: 0.625rem;
      padding: 0.875rem 1rem;
      color: var(--text);
      font-family: inherit;
      font-size: 0.9375rem;
      outline: none;
      transition: all 0.2s;
    }
    textarea:focus, input[type="text"]:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
    }
    .btn {
      background: linear-gradient(135deg, #4f46e5, #6366f1);
      color: white;
      border: none;
      border-radius: 0.5rem;
      padding: 0.65rem 1.25rem;
      font-weight: 600;
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.2s;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
    }
    .btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="badge">π</div>
      <div>
        <div class="brand-title">Pithon Mini-OpenClaw</div>
        <div style="font-size: 0.72rem; color: #10b981; font-weight: 600;">● Online • Asia/Kolkata</div>
      </div>
    </div>
    <nav>
      <button class="active" onclick="switchTab('overview')">Overview</button>
      <button onclick="switchTab('interactions')">Audit Log</button>
      <button onclick="switchTab('tasks')">Tasks & Timers</button>
      <button onclick="switchTab('notes')">Memory & Notes</button>
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
        <div class="stat-card" style="--stat-accent: #10b981;">
          <div class="stat-label">Inference Engine</div>
          <div class="stat-value" style="color: #10b981;">Online</div>
          <div class="stat-meta">Qwen2.5-0.5B • 127.0.0.1:8090</div>
        </div>
        <div class="stat-card" style="--stat-accent: #06b6d4;">
          <div class="stat-label">Memory (RSS)</div>
          <div class="stat-value" id="statRss">~306 MB</div>
          <div class="stat-meta">Hard Cap: 2048 MB (Cgroup)</div>
        </div>
        <div class="stat-card" style="--stat-accent: #6366f1;">
          <div class="stat-label">Interactions</div>
          <div class="stat-value" id="statInteractions">0</div>
          <div class="stat-meta">Logged in SQLite WAL</div>
        </div>
        <div class="stat-card" style="--stat-accent: #f59e0b;">
          <div class="stat-label">Pending Tasks</div>
          <div class="stat-value" id="statTasks">0</div>
          <div class="stat-meta">Active Timers & To-Dos</div>
        </div>
      </div>

      <div class="card-box">
        <h3>Architecture & Active Capabilities</h3>
        <p style="color: var(--text-muted); font-size: 0.9rem; line-height: 1.6;">
          Co-located on Oracle Cloud ARM Ampere A1 VM alongside OwnTracks Recorder. 
          Protected via hard Docker cgroups (<code>pithon-daemon: 1.0 CPU, 2048M RAM</code>, <code>pithon-agent: 0.5 CPU, 512M RAM</code>).
        </p>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-top: 1.25rem;">
          <div style="padding: 1rem; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 0.75rem;">
            <div style="font-weight: 700; color: #a5b4fc;">⚡ Native Qwen2.5 Tool Calling</div>
            <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 0.25rem;">Countdown timers, task lists, live web search, safe math, and live weather.</div>
          </div>
          <div style="padding: 1rem; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 0.75rem;">
            <div style="font-weight: 700; color: #6ee7b7;">🛡️ Whitelist Telegram Security</div>
            <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 0.25rem;">Interactive chat restricted strictly to ID <code>357035668</code>. Silent reports to group <code>-1001169201210</code>.</div>
          </div>
          <div style="padding: 1rem; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 0.75rem;">
            <div style="font-weight: 700; color: #38bdf8;">📝 Markdown Persistent Memory</div>
            <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 0.25rem;">Saved notes and facts stored directly in <code>data/notes/*.md</code>.</div>
          </div>
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

    <!-- TASKS & TIMERS TAB -->
    <div id="tab-tasks" class="tab-content">
      <div class="card-box">
        <h3>Tasks, Timers & Reminders</h3>
        <p style="color: var(--text-muted); font-size: 0.85rem;">Active to-dos and countdown timers monitored by the 5-second ticker.</p>
        <div style="overflow-x: auto;">
          <table id="tasksTable">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type / List</th>
                <th>Title</th>
                <th>Due At</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading tasks...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- MEMORY & NOTES TAB -->
    <div id="tab-notes" class="tab-content">
      <div class="card-box">
        <h3>Markdown Knowledge & Memory Files</h3>
        <p style="color: var(--text-muted); font-size: 0.85rem;">Persistent notes saved in <code>data/notes/*.md</code>.</p>
        <div id="notesContainer" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; margin-top: 1.25rem;">
          <div style="color: var(--text-muted); font-size: 0.85rem;">Loading markdown memory...</div>
        </div>
      </div>
    </div>

    <!-- DIGESTS TAB -->
    <div id="tab-digests" class="tab-content">
      <div class="card-box">
        <h3>Hourly Digest Archive</h3>
        <p style="color: var(--text-muted); font-size: 0.85rem;">Silent notifications dispatched to the report channel.</p>
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

    <!-- PLAYGROUND TAB -->
    <div id="tab-playground" class="tab-content">
      <div class="card-box">
        <h3>Live Model & Tool Calling Playground</h3>
        <p style="color: var(--text-muted); font-size: 0.85rem;">Test time awareness, Caveman Ultra output, and tool calling directly in the browser.</p>
        <div style="margin-top: 1rem;">
          <textarea id="playgroundPrompt" rows="3" placeholder="Ask anything (e.g. 'Can you set a timer for 15 mins?', 'What is weather in Bangalore?', 'Remember WiFi password is 1234')"></textarea>
          <div style="margin-top: 0.75rem;">
            <button class="btn" id="playBtn" onclick="runPlayground()">Send Prompt</button>
          </div>
          <div id="playgroundOutput" style="margin-top: 1rem; padding: 1rem; background: #080c16; border-radius: 0.625rem; border: 1px solid var(--border); display: none; font-size: 0.9375rem; line-height: 1.5; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace;"></div>
        </div>
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
        }
      } catch (e) {}
    }

    async function loadInteractions() {
      const tbody = document.querySelector('#interactionsTable tbody');
      try {
        const res = await fetch('/api/interactions');
        if (res.ok) {
          const data = await res.json();
          if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No interactions logged yet.</td></tr>';
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

    async function loadTasks() {
      const tbody = document.querySelector('#tasksTable tbody');
      try {
        const res = await fetch('/api/tasks');
        if (res.ok) {
          const data = await res.json();
          if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No active tasks or timers.</td></tr>';
            return;
          }
          tbody.innerHTML = data.map(t => `
            <tr>
              <td style="font-family: monospace;">#${t.id}</td>
              <td><span class="badge-chip ${t.list_name === 'timer' ? 'chip-timer' : 'chip-task'}">${escapeHtml(t.list_name || 'default')}</span></td>
              <td style="font-weight: 600;">${escapeHtml(t.title)}</td>
              <td style="font-family: monospace; font-size: 0.8rem;">${t.due_at ? t.due_at.slice(0, 16).replace('T', ' ') : '—'}</td>
              <td><span class="badge-chip ${t.is_completed ? 'chip-done' : 'chip-active'}">${t.is_completed ? 'Completed' : 'Pending'}</span></td>
            </tr>
          `).join('');
        }
      } catch (e) {
        tbody.innerHTML = '<tr><td colspan="5" style="color: #f87171;">Error loading tasks.</td></tr>';
      }
    }

    async function loadNotes() {
      const container = document.getElementById('notesContainer');
      try {
        const res = await fetch('/api/notes');
        if (res.ok) {
          const data = await res.json();
          if (!data || data.length === 0) {
            container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">No markdown notes created yet. Talk to Telegram bot to save notes!</div>';
            return;
          }
          container.innerHTML = data.map(n => `
            <div style="padding: 1.25rem; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 0.75rem;">
              <div style="font-weight: 700; font-size: 1rem; color: #f8fafc;">${escapeHtml(n.title)}</div>
              <div style="font-size: 0.75rem; color: #64748b; font-family: monospace; margin: 0.25rem 0 0.75rem 0;">${escapeHtml(n.filename)}</div>
              <div style="font-size: 0.85rem; color: #cbd5e1; white-space: pre-wrap; max-height: 140px; overflow-y: auto;">${escapeHtml(n.content || '')}</div>
            </div>
          `).join('');
        }
      } catch (e) {
        container.innerHTML = '<div style="color: #f87171;">Error loading notes.</div>';
      }
    }

    async function loadDigests() {
      const tbody = document.querySelector('#digestsTable tbody');
      try {
        const res = await fetch('/api/digests');
        if (res.ok) {
          const data = await res.json();
          if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">No digests logged yet.</td></tr>';
            return;
          }
          tbody.innerHTML = data.map(d => `
            <tr>
              <td style="white-space: nowrap; font-family: monospace;">${(d.created_at || '').slice(0, 19).replace('T', ' ')}</td>
              <td style="font-family: monospace;">${d.items_count || 0}</td>
              <td style="white-space: pre-wrap; font-size: 0.85rem; color: #cbd5e1;">${escapeHtml(d.content)}</td>
            </tr>
          `).join('');
        }
      } catch (e) {
        tbody.innerHTML = '<tr><td colspan="3" style="color: #f87171;">Error loading digests.</td></tr>';
      }
    }

    async function runPlayground() {
      const p = document.getElementById('playgroundPrompt').value;
      const btn = document.getElementById('playBtn');
      const out = document.getElementById('playgroundOutput');
      if (!p.trim()) return;
      btn.disabled = true;
      btn.innerText = 'Evaluating...';
      out.style.display = 'block';
      out.innerText = 'Evaluating prompt with local model...';

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
    """Create HTTP Server instance with session authentication and notes API."""

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
                tasks = storage.get_tasks("357035668", include_completed=False) if storage else []
                self._send_json({
                    "status": "ok",
                    "total_interactions": len(interactions),
                    "pending_tasks": len(tasks),
                    "timezone": tz_name
                })
            elif path == "/api/interactions":
                items = storage.get_interactions(limit=50) if storage else []
                self._send_json(items)
            elif path == "/api/tasks":
                tasks = storage.get_tasks("357035668", include_completed=True) if storage else []
                self._send_json(tasks)
            elif path == "/api/notes":
                notes_list = list_notes()
                for n in notes_list:
                    n["content"] = get_note_content(n["title"])
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
                if title and storage:
                    tid = storage.create_task("357035668", title, list_name=list_name)
                    self._send_json({"status": "ok", "id": tid})
                else:
                    self._send_json({"error": "Title required"}, status=400)

            elif path == "/api/playground":
                body = self._read_json_body()
                prompt = body.get("prompt", "").strip()
                if not prompt:
                    self._send_json({"error": "Empty prompt"}, status=400)
                    return

                search_block = ""
                if should_search(prompt):
                    results = search_duckduckgo(prompt, max_results=3)
                    search_block = format_search_context(results, prompt)

                temporal = format_temporal_prompt_header(tz_name)
                full_prompt = (
                    f"# Mode: Caveman Ultra\n"
                    f"Respond terse like smart caveman. Drop articles, filler, pleasantries. State facts once. Keep exact.\n\n"
                    f"{temporal}\n{search_block}User Question: {prompt}\nAnswer directly."
                )

                try:
                    payload = {
                        "messages": [{"role": "user", "content": full_prompt}],
                        "max_tokens": 256,
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
                        self._send_json({"response": answer})
                except Exception as e:
                    logger.error(f"Error querying daemon from playground: {e}")
                    self._send_json({"response": f"⚠️ Could not reach daemon at {daemon_url}: {e}"})
            else:
                self.send_response(404)
                self.end_headers()

    return HTTPServer((host, port), PithonWebHandler)
