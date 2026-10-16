# AGENTS.md — Khepri

Autonomous SLM runtime + personal agent targeting ARM/low-power hardware (Raspberry Pi, OCI Ampere).
Docs live in `README.md`, `CONTRIBUTING.md`, and `wiki/`. This file only records what the repo does *not*
state plainly.

## Product scope — all three surfaces are intentional

- **Telegram is the messaging surface.** The bot is the user-facing product.
- **The web portal is a required feature**, not a demo: it is how the operator *diagnoses and tests the
  LLM* (live daemon telemetry on the Overview tab, `Chat Studio` for probing responses, plus Audit Log
  and Digests). Do not delete it, stub it out, or treat it as secondary.
- **The hardware target is Raspberry Pi 4/5** (4 GB minimum). Pi 3 support was dropped — the agent outgrew
  it. Bare-metal and Docker Compose are both supported deploy paths.

## The name mismatch is intentional — do not "fix" it

The project is **Khepri**; the Python package is **`pithon/`**.

- `pyproject.toml` declares **both** `khepri` and `pithon` console scripts → `pithon.cli:main`.
- Compose service/image/container names are `pithon:latest`, `pithon-agent:latest`, `pithon-daemon`, `pithon-agent`.
- Logs, pytest markers, DB path (`data/pithon.db`), and loggers all use `pithon.*`.

## Three surfaces, two processes

| Surface | Entrypoint | Port (container / host) | Role |
|---|---|---|---|
| Daemon | `pithon serve` → `pithon/cli.py` + `pithon/server.py` | 8080 / 8090 | OpenAI-compatible loopback API over `llama_cpp` |
| Telegram | `pithon.agent.telegram_bot.TelegramBot` | — | Polling thread inside the agent process |
| Web portal | `python -m pithon.agent.main` → `pithon/agent/web.py` | 8080 / 8091 | Operator/diagnostics console, main thread |

The agent process (`pithon/agent/main.py`) starts the Telegram polling thread, a scheduler thread, and
the web server on the main thread. **Neither the agent nor the portal imports the model** — both reach
the daemon over HTTP at `PITHON_DAEMON_URL` (default `http://pithon:8080`). Changing daemon behaviour
affects Telegram and the portal indirectly, so `curl /health` on the daemon is the first thing to check
when either surface misbehaves.

Portal navigation is a single embedded `DASHBOARD_HTML` raw string (~2300 lines inside `web.py`) with
tabs: Overview, Chat Studio, Calendar & Agenda, Tasks & Timers, Vision & Tools, Memory, Daily Briefings,
Persona & Config, Audit Log, Digests. Editing the UI means editing that string — there is no build step,
no bundler, and no template file.

## Deploy paths (both supported)

- **Bare metal:** `python3 -m venv .venv`, `pip install --prefer-binary --extra-index-url
  https://abetlen.github.io/llama-cpp-python/whl/cpu -e .[dev]`, then `./scripts/download_model.sh`.
- **Compose:** two containers, `pithon` (daemon, 8090) and `pithon-agent` (Telegram + portal, 8091).
- `scripts/pithon-daemon.service` and `scripts/pithon-agent.service` are the real units — Khepri needs
  **both**, because the daemon and the agent are separate processes. Edit `User=` and the
  `/home/pi/code/Khepri` paths before installing; the agent's `WorkingDirectory` must be the repo root
  (it loads `.env` and `data/` relative to CWD). `scripts/pithon.service` is superseded — never enable it.
  Note the units serve the daemon on **8090** (matching compose and `scripts/query_daemon.sh`), not the
  CLI's 8080 default, so bare-metal must set `PITHON_DAEMON_URL=http://127.0.0.1:8090` to match.
- `scripts/query_daemon.sh "prompt"` is the quickest operator probe: it streams SSE from
  `http://127.0.0.1:8090/v1/chat/completions` (override with `PITHON_PORT`). Note the default is the
  *host-mapped* 8090, not the container's 8080.
- `scripts/install.sh` automates the bare-metal path (deps, venv, GGUF, `.env`, both units). It **inlines
  its own copies** of the two unit files as heredocs instead of reading `scripts/*.service`, so edits to a
  unit must be mirrored there by hand. It has not been run on real hardware.
- `/api/playground` is a headless alias of `/api/chat/send` with no UI tab — useful for scripted model
  testing without driving the dashboard.

## Environment quirk: the venv console scripts are broken

`.venv` was created under a directory named `Pithon`, then the repo was renamed to `Khepri`. Every
console script's shebang still points at the old path, so `.venv/bin/pytest`, `.venv/bin/mypy`,
`.venv/bin/pithon` all fail with `bad interpreter`. Always go through the interpreter:

```bash
.venv/bin/python -m pytest tests/ -m "not e2e" -q   # 120 passed, ~19s
.venv/bin/python -m mypy pithon                     # 29 source files
.venv/bin/python -m compileall -q pithon tests
.venv/bin/ruff check pithon tests                   # ruff is a static binary; direct call is fine
```

There is no `python` on `PATH`; system `python3` is 3.9 but the venv is 3.12.

**Do not run `ruff format`.** It would rewrite 51 of 54 files. CI only ever runs `ruff check`
(line-length 120 but `E501` ignored). There is no formatter in the toolchain.

## Tool names are exact — do not invent them

There is no MCP server in this project, so the tool catalog is small, fixed, and fully visible in the
system prompt. Tool names are **exact identifiers**, not free text. Emitting a plausible-but-wrong name
fails the call outright, which wastes a whole turn.

Frequently hallucinated names and their real equivalents here:

| Wrong (other harnesses) | Correct here |
|---|---|
| `shell_command`, `run_shell_command`, `Bash`, `terminal`, `run_command`, `execute_command` | `shell` (arg: `command`) |
| `read_file`, `Read` | `read` (arg: `path`) |
| `write_file`, `Write` | `write` (arg: `path`, `content`) |
| `str_replace_editor`, `Edit` | `edit` (arg: `path`, `oldString`, `newString`) |
| `search`, `find`, `codebase_search` | `grep` / `glob` / `subagent` |
| `web_search`, `google` | `websearch` |
| `web_fetch`, `fetch` | `webfetch` |

`shell` takes `command`, plus optional `workdir`, `timeout`, and `background`. If a call is rejected
as an unknown tool, re-read the catalog and retry with the correct name — do not paraphrase the task
or fall back to guessing. Prefer `read`/`grep`/`glob` over `shell` for inspection; reach for `shell`
only when you actually need to execute something.

## Hard constraints (violating these breaks the project's premise)

1. **Two different memory numbers, deliberately.**
   - **Stated system budget: < 2 GB** for the whole stack (daemon + agent with a 0.5B model loaded).
     This is the product claim — README badge, CONTRIBUTING, PR template, wiki, and the compose cgroup
     caps, which sum to 1920 MB (1408M daemon + 512M agent).
   - **CI guard: daemon process < 750 MB peak RSS** (`benchmark.yml` asserts it; `test_e2e_real_model.py`
     uses a 400/850 MB ceiling by model size). This is a regression guard, *not* the public budget.
     Do not relax it to 2 GB — that would make a real leak pass CI.
   Quoted "typical live RSS" (~306 MB daemon, ~27 MB agent, ~333 MB combined) is measured, not a limit.
2. **Raspberry Pi 4/5, 4 GB minimum.** Pi 3 references were purged on 2026-10-16; do not reintroduce
   them in help text, service units, docs, or wiki pages.
3. **`pithon/` core is stdlib-only.** No Flask/FastAPI, no `requests`, no `python-telegram-bot`,
   no APScheduler, no PyYAML. It is `http.server` + `urllib.request` + `sqlite3` + `threading` +
   `zoneinfo` + `ast`. YAML frontmatter in `markdown_store.parse_frontmatter` is hand-rolled for this
   reason. Do not add a dependency to make something easier — implement it in stdlib.
4. **Only these lazy/optional imports exist:** `llama_cpp` (inside `engine.LlamaEngine._load_model`),
   and `PIL` / `pytesseract` / `rapidocr_onnxruntime` (inside `agent/image_tools.py`).
5. **No `eval()` anywhere.** `agent/calc.safe_calculate` is an AST allowlist. The PR checklist
   explicitly requires "no arbitrary eval".

## Biggest architectural trap: two independent intent routers

Deterministic fast-pathing is implemented **twice**, and they do not share a dispatcher:

- **Telegram:** `telegram_bot.handle_message` → `router.route_fast_path()` (`pithon/agent/router.py`).
- **Web:** `web.py`'s `/api/chat/send` handler runs its *own* inline `if/elif` chain, importing the
  individual `is_*_intent` helpers. It never calls `route_fast_path`.

Adding a new intent to `router.py` alone means the portal silently falls through to the 0.5B SLM, and the
bug will look like a *model* problem rather than a routing one. Both surfaces are required, so change
both, and extend both test files (`tests/test_agent_router.py`, `tests/test_agent_web.py`).

New agent tools need three edits: a schema entry in `tools.TOOLS_DEFINITIONS`, an alias/normalization
branch in `tools.execute_tool_call` (it strips non-alphanumerics and maps `calender`/`agenda`/`todo`/
`timer` typos), and an `elif name == ...` branch in the same function.

## State: SQLite is authoritative, markdown is a one-way mirror

- `DB_PATH` (default `data/pithon.db`) holds tasks, interactions, sessions, calendar events, profiles.
- `data/tasks.md` and `data/profile.md` are **regenerated from SQLite** by `Storage._sync_tasks_markdown()`
  and `Storage.save_user_profile()`. Hand-edits are silently overwritten. They are output, not input.
- `data/notes/*.md` **is** the real store for notes (`agent/memory.py`).
- `Storage.__init__` calls `memory.seed_notes()`, which writes `system-specs.md` **only when the notes
  vault is empty**. `data/` is gitignored, so authored notes never travel with the repo — that's why the
  shipped cgroup figures live in an embedded `SEED_NOTES` constant in `memory.py` (an `assets/` dir would
  work locally but breaks Docker, which copies only `pithon/`, and wheels, which exclude data dirs).
  Never seed over an existing vault: a user who deletes a starter note must not get it back.
- `data/briefings/YYYY-MM-DD.md` is append-only archive written by `BriefingStore`.
- `data_dir` is derived from `dirname(DB_PATH)`, and notes now follow too: every production call site
  passes `base_dir=storage.notes_dir()` (a new `Storage` method). `base_dir=None` still falls back to
  `$NOTES_DIR` then `data/notes`. With the default `DB_PATH` this resolves to the same `./data/notes`
  as before, so existing installs are unaffected — but a custom `DB_PATH` now relocates notes with it.
  Compare `realpath`s, not strings: `data_dir` is absolute while `DEFAULT_NOTES_DIR` is relative.
  Regression coverage: `tests/test_agent_notes_scoping.py`.
- `get_user_profile()` falls back to `chat_id='web'`, and every profile write is mirrored to the `web` row.
- Undocumented overrides: `DATA_DIR` (markdown store) and `NOTES_DIR` (notes). Neither is in `.env.example`.
- `data/` and `models/` are gitignored — never commit notes, the DB, or GGUF weights.

## Daemon loopback allowlist will bite you

`server.ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "pithon", "pithon-daemon"}`; a `Host` header
outside that set returns **403 before routing**. Consequences:

- `pithon serve --host 0.0.0.0 --port 9000` is *not* enough — the `Host` header must still be one of the
  four allowed names, with the port matching the `--port` value.
- Renaming the compose service or changing the daemon port requires updating this set too.
- If `Origin` is present it must be `http://` + a matching netloc, otherwise 403.

## Running locally with no model

- `models/` is gitignored and absent. `./scripts/download_model.sh qwen|smollm|all [destdir]` fetches GGUF.
- `llama-cpp-python` is **not installed** in `.venv`. `engine.py` imports it lazily, so tests pass anyway.
  For CLI smoke tests use mock mode via the module (`.venv/bin/pithon` is broken, and there is **no
  `pithon/__main__.py`**, so `python -m pithon` fails): `.venv/bin/python -m pithon.cli chat --mock`.
- The 3 `e2e`-marked tests **skip silently** when no GGUF is present, so a bare `pytest` gives zero real
  inference coverage. Only `tests/test_e2e_real_model.py` exercises live models.
- Run the portal locally: `python -m pithon.agent.main` with `WEB_ADMIN_PASSWORD` set, then
  `POST /api/login`. It binds `0.0.0.0:$PORT`.
- `tests/test_agent_web.py` binds an **ephemeral port (`port=0`)** and reads back `server.server_port`.
  Keep it that way; a hardcoded port makes the suite fail whenever that port is busy.

## Testing conventions

- No `conftest.py` exists; every file defines its own `tmp_path` fixtures.
- Instantiate storage as `Storage(str(tmp_path / "test.db"))` so both SQLite *and* the markdown mirror
  land in the temp dir. `Storage.__init__` derives `data_dir` from the DB path.
- Network calls are mocked (`@patch("urllib.request.urlopen")`); the suite needs no internet.
- `tests/test_agent_weather.py` asserts **ReDoS resilience** (< 0.1s on adversarial input). Keep new
  regexes linear, or add an equivalent timing assertion.
- Path-traversal containment (`memory._safe_note_path`, `BriefingStore.get_briefing` basename-only) and
  auth checks are covered by `tests/test_server_security.py`; gitleaks, Trivy, and CodeQL run on every PR.

## Ops gotchas

- CI checks live in separate workflows: `ci.yml` (unit tests, then gated `arm64-e2e-inference`),
  `lint.yml` (ruff + compileall + mypy). Run all four local commands before pushing.
- `.github/workflows/wiki-sync.yml` force-pushes everything in `wiki/` to the GitHub Wiki repo on any
  push touching `wiki/**` to `master`/`main`. Don't stage scratch or draft files there.
- New bot commands, tools, endpoints, or CLI flags must be documented in `README.md` — the PR checklist
  and BotFather block require it.
- Commits follow Conventional Commits (`CONTRIBUTING.md`); the existing history and Dependabot PR titles
  both follow it, so match it.
- Dependabot opens weekly pip / github-actions / docker PRs with the `dependencies` label.