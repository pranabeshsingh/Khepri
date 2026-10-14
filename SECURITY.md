# Security Policy

The Khepri project takes the security and privacy of our users very seriously. Because Khepri runs on local edge hardware with network endpoints (Telegram bot integrations, local web server, and model inference), ensuring robust defenses against remote exploits, path traversal, injection, and denial of service is paramount.

---

## Supported Versions

Security updates and patches are actively applied to the latest release branch:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

---

## Reporting a Vulnerability

**Please do not report security vulnerabilities via public GitHub issues or discussions.**

If you discover a security vulnerability in Khepri, please report it privately through one of the following channels:

1. **GitHub Private Vulnerability Reporting (Preferred):**
   - Navigate to the [Security Advisories](https://github.com/pranabeshsingh/Khepri/security/advisories) tab of this repository.
   - Click **"Report a vulnerability"** to submit your findings in a private draft advisory.

2. **Direct Email:**
   - Email **pranz29@live.com** with the subject `[SECURITY] Vulnerability in Khepri`.
   - Please provide:
     - A detailed description of the vulnerability.
     - Steps to reproduce or proof-of-concept (PoC) exploit code.
     - Affected version(s) and environment setup (Docker, Pi OS, etc.).
     - Any potential impact on user data, device integrity, or credentials.

---

## Vulnerability Handling & Disclosure Timeline

- **Initial Response:** You will receive an acknowledgment within **48 hours** of submission.
- **Triage & Assessment:** The vulnerability will be evaluated, reproduced, and assigned a severity rating within **5 business days**.
- **Fix & Testing:** A fix will be developed and verified in a private security fork.
- **Coordinated Disclosure:** A patch release and corresponding GitHub Security Advisory (with CVE assignment where appropriate) will be published simultaneously once the fix is ready.
- **Credit:** We will gladly credit you in release notes and security advisories (unless you prefer anonymity).

---

## Security Architecture & Best Practices

When operating Khepri in production or home networks:

1. **Telegram Credentials:** Never commit your `.env` file or expose `TELEGRAM_BOT_TOKEN`. Only authorized user IDs specified in `TELEGRAM_ADMIN_CHAT_ID` or `TELEGRAM_REPORT_CHAT_ID` are allowed to issue tool calls or trigger model executions.
2. **Web Companion Authentication:** When accessing the Web Companion interface, always configure a strong `PORTAL_PASSPHRASE`. By default, unauthenticated web requests are restricted to loopback origins.
3. **Storage Security:** Markdown storage paths and notes endpoints enforce path containment checks to mitigate directory traversal attempts.
4. **Calculations & Regex:** Fast-path arithmetic uses isolated AST parsing (`safe_calculate`), completely preventing arbitrary code evaluation via `eval()` or `exec()`. Regular expressions are hardened against polynomial ReDoS.
