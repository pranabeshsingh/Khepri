import io
import base64
from datetime import datetime, timezone, timedelta
import json
import pytest
import threading
import unittest.mock
import urllib.request
import urllib.error
from pithon.agent.web import create_web_server
from pithon.agent.storage import Storage

@pytest.fixture
def temp_storage(tmp_path):
    db_path = str(tmp_path / "web_test.db")
    return Storage(db_path)

@pytest.fixture
def web_server(temp_storage):
    # Bind to an ephemeral port (0) so the suite never collides with a stray
    # listener on a previously hardcoded port. HTTPServer binds and activates in
    # __init__, so server_port is populated immediately.
    server = create_web_server(
        storage=temp_storage,
        admin_password="test-password-123",
        host="127.0.0.1",
        port=0,
        daemon_url="http://127.0.0.1:8090"
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()

def test_unauthenticated_redirect(web_server):
    req = urllib.request.Request(f"{web_server}/", headers={"User-Agent": "test"})
    # Should redirect to /login
    try:
        resp = urllib.request.urlopen(req)
        assert "/login" in resp.geturl()
    except urllib.error.HTTPError as e:
        assert e.code in (302, 401, 403)

def test_login_flow_and_api(web_server, temp_storage):
    # 1. Login with bad password -> 401
    bad_login = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "wrong-password"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(bad_login)
    assert exc_info.value.code == 401

    # 2. Login with correct password -> 200 and set-cookie
    good_login = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(good_login) as resp:
        assert resp.status == 200
        cookie_header = resp.headers.get("Set-Cookie", "")
        assert "pithon_session=" in cookie_header
        token = cookie_header.split("pithon_session=")[1].split(";")[0]

    # 3. Access protected API using session cookie
    api_req = urllib.request.Request(
        f"{web_server}/api/stats",
        headers={"Cookie": f"pithon_session={token}"}
    )
    with urllib.request.urlopen(api_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert "status" in data
        assert data["status"] == "ok"


def test_web_api_calendar(web_server, temp_storage):
    good_login = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(good_login) as resp:
        cookie_header = resp.headers.get("Set-Cookie", "")
        token = cookie_header.split("pithon_session=")[1].split(";")[0]

    now = datetime.now(timezone.utc)
    start_time = (now + timedelta(hours=2)).isoformat()
    end_time = (now + timedelta(hours=3)).isoformat()
    temp_storage.save_calendar_events("web", [{
        "id": "web-event-1",
        "parent_uid": "web-event-1",
        "title": "Design Sprint",
        "description": "",
        "location": "Meet",
        "meeting_link": "https://meet.google.com/web",
        "start_time": start_time,
        "end_time": end_time,
        "is_recurring": 0,
        "event_md5": "md5-web"
    }])

    api_req = urllib.request.Request(
        f"{web_server}/api/calendar",
        headers={"Cookie": f"pithon_session={token}"}
    )
    with urllib.request.urlopen(api_req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert "events" in data
        assert any(e["title"] == "Design Sprint" for e in data["events"])


def test_web_notes_and_chat_math(web_server, temp_storage, monkeypatch, tmp_path):
    # Set notes directory to temporary directory
    notes_dir = str(tmp_path / "web_notes")
    monkeypatch.setenv("NOTES_DIR", notes_dir)

    # Login
    login_req = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(login_req) as resp:
        token = resp.headers.get("Set-Cookie", "").split("pithon_session=")[1].split(";")[0]

    headers = {
        "Cookie": f"pithon_session={token}",
        "Content-Type": "application/json"
    }

    # 1. Add note with traversal title
    add_req = urllib.request.Request(
        f"{web_server}/api/notes/add",
        data=json.dumps({"title": "../../test_safe", "content": "hello world"}).encode("utf-8"),
        headers=headers
    )
    with urllib.request.urlopen(add_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert ".." not in data["note"]["filename"]

    # 2. Delete note with traversal attempt
    del_req = urllib.request.Request(
        f"{web_server}/api/notes/delete",
        data=json.dumps({"filename": "../../etc/passwd.md"}).encode("utf-8"),
        headers=headers
    )
    with urllib.request.urlopen(del_req) as resp:
        del_data = json.loads(resp.read().decode("utf-8"))
        assert del_data["status"] == "ok"

    # 3. Direct math evaluation in /api/chat/send
    chat_req = urllib.request.Request(
        f"{web_server}/api/chat/send",
        data=json.dumps({"prompt": "calculate 25 * 4"}).encode("utf-8"),
        headers=headers
    )
    with urllib.request.urlopen(chat_req) as resp:
        chat_data = json.loads(resp.read().decode("utf-8"))
        assert "100" in chat_data.get("response", "")


def test_web_calendar_config(web_server, temp_storage):
    login_req = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(login_req) as resp:
        token = resp.headers.get("Set-Cookie", "").split("pithon_session=")[1].split(";")[0]

    headers = {
        "Cookie": f"pithon_session={token}",
        "Content-Type": "application/json"
    }

    # 1. Update calendar configuration
    conf_req = urllib.request.Request(
        f"{web_server}/api/calendar/config",
        data=json.dumps({"url": "https://example.com/test_calendar.ics", "alert_mins": 15}).encode("utf-8"),
        headers=headers
    )
    with urllib.request.urlopen(conf_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert data["url"] == "https://example.com/test_calendar.ics"
        assert data["alert_mins"] == 15

    # 2. Verify settings persisted via GET /api/calendar
    get_req = urllib.request.Request(
        f"{web_server}/api/calendar",
        headers={"Cookie": f"pithon_session={token}"}
    )
    with urllib.request.urlopen(get_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["url"] == "https://example.com/test_calendar.ics"
        assert data["alert_mins"] == 15


def test_web_profile_endpoints(web_server, temp_storage):
    login_req = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(login_req) as resp:
        token = resp.headers.get("Set-Cookie", "").split("pithon_session=")[1].split(";")[0]

    headers = {
        "Cookie": f"pithon_session={token}",
        "Content-Type": "application/json"
    }

    # 1. Save Profile
    save_req = urllib.request.Request(
        f"{web_server}/api/profile",
        data=json.dumps({
            "name": "Alice",
            "city": "Berlin",
            "digest_pref": "Evening 8 PM",
            "focus": "DevOps & Cloud Architecture",
            "persona_body": "# Persona\n- Always concise and direct."
        }).encode("utf-8"),
        headers=headers
    )
    with urllib.request.urlopen(save_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"

    # 2. Get Profile
    get_req = urllib.request.Request(
        f"{web_server}/api/profile",
        headers={"Cookie": f"pithon_session={token}"}
    )
    with urllib.request.urlopen(get_req) as resp:
        prof = json.loads(resp.read().decode("utf-8"))
        assert prof["name"] == "Alice"
        assert prof["city"] == "Berlin"
        assert prof["digest_pref"] == "Evening 8 PM"
        assert prof["focus"] == "DevOps & Cloud Architecture"
        assert "concise and direct" in prof.get("persona_body", "")


def test_web_briefings_endpoints(web_server, temp_storage):
    login_req = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(login_req) as resp:
        token = resp.headers.get("Set-Cookie", "").split("pithon_session=")[1].split(";")[0]

    headers = {"Cookie": f"pithon_session={token}"}

    # Save a test briefing using storage.briefing_store
    temp_storage.briefing_store.save_briefing(
        "# Daily Briefing: Oct 14, 2026\n\nTop news and agenda.",
        date_str="2026-10-14"
    )

    # 1. List briefings
    list_req = urllib.request.Request(f"{web_server}/api/briefings/history", headers=headers)
    with urllib.request.urlopen(list_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert any(b["filename"] == "2026-10-14.md" for b in data["briefings"])

    # 2. Get briefing content
    content_req = urllib.request.Request(
        f"{web_server}/api/briefings/content?filename=2026-10-14.md",
        headers=headers
    )
    with urllib.request.urlopen(content_req) as resp:
        cdata = json.loads(resp.read().decode("utf-8"))
        assert cdata["status"] == "ok"
        assert "Top news and agenda" in cdata["content"]


def test_web_image_tools(web_server):
    login_req = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(login_req) as resp:
        token = resp.headers.get("Set-Cookie", "").split("pithon_session=")[1].split(";")[0]

    headers = {
        "Cookie": f"pithon_session={token}",
        "Content-Type": "application/json"
    }

    # Create dummy 20x20 in-memory image
    from PIL import Image
    buf = io.BytesIO()
    im = Image.new("RGB", (20, 20), color="blue")
    im.save(buf, format="PNG")
    b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

    # 1. Test OCR endpoint
    ocr_req = urllib.request.Request(
        f"{web_server}/api/tools/ocr",
        data=json.dumps({"image": b64_img}).encode("utf-8"),
        headers=headers
    )
    with urllib.request.urlopen(ocr_req) as resp:
        odata = json.loads(resp.read().decode("utf-8"))
        assert odata["status"] == "ok"

    # 2. Test PDF compilation endpoint
    pdf_req = urllib.request.Request(
        f"{web_server}/api/tools/pdf",
        data=json.dumps({"images": [b64_img]}).encode("utf-8"),
        headers=headers
    )
    with urllib.request.urlopen(pdf_req) as resp:
        pdata = json.loads(resp.read().decode("utf-8"))
        assert pdata["status"] == "ok"
        assert "pdf_base64" in pdata
        assert pdata["size_bytes"] > 0

    # 3. Test WebP compression endpoint
    comp_req = urllib.request.Request(
        f"{web_server}/api/tools/compress",
        data=json.dumps({"image": b64_img, "quality": 75, "max_width": 1280}).encode("utf-8"),
        headers=headers
    )
    with urllib.request.urlopen(comp_req) as resp:
        cdata = json.loads(resp.read().decode("utf-8"))
        assert cdata["status"] == "ok"
        assert cdata["format"] == "webp"
        assert "image_base64" in cdata


# --- Security hardening -------------------------------------------------
# The login throttle is module-level state keyed by client IP, so these tests
# must clear it or they will leak lockouts into each other.

@pytest.fixture(autouse=True)
def _reset_login_throttle():
    import pithon.agent.web as web_mod
    with web_mod._LOGIN_LOCK:
        web_mod._LOGIN_FAILURES.clear()
        web_mod._LOGIN_LOCKS.clear()
    yield
    with web_mod._LOGIN_LOCK:
        web_mod._LOGIN_FAILURES.clear()
        web_mod._LOGIN_LOCKS.clear()


def test_login_is_throttled_after_repeated_failures(web_server):
    """Without a throttle, compare_digest alone permits unlimited passphrase guesses."""
    statuses = []
    for _ in range(7):
        req = urllib.request.Request(
            f"{web_server}/api/login",
            data=json.dumps({"password": "wrong"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                statuses.append(resp.status)
        except urllib.error.HTTPError as e:
            statuses.append(e.code)
            if e.code == 429:
                assert "retry_after_sec" in json.loads(e.read().decode("utf-8"))

    assert 429 in statuses, f"expected a lockout, got {statuses}"
    # Lockout must persist: a correct password during the window is refused too.
    req = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 429
    except urllib.error.HTTPError as e:
        assert e.code == 429


def test_successful_login_clears_the_failure_counter(web_server):
    for _ in range(3):
        req = urllib.request.Request(
            f"{web_server}/api/login",
            data=json.dumps({"password": "wrong"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError:
            pass

    good = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(good) as resp:
        assert resp.status == 200

    # Counter reset, so a fresh run of failures is not instantly locked out.
    for _ in range(4):
        req = urllib.request.Request(
            f"{web_server}/api/login",
            data=json.dumps({"password": "wrong"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 401
        except urllib.error.HTTPError as e:
            assert e.code == 401


def test_security_headers_present(web_server):
    req = urllib.request.Request(f"{web_server}/login")
    with urllib.request.urlopen(req) as resp:
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"
        assert resp.headers.get("Cache-Control") == "no-store"


def test_oversized_body_is_rejected_with_413(web_server):
    """Unbounded base64 image reads inside a 512M cgroup are an OOM vector."""
    import pithon.agent.web as web_mod
    req = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "x"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    req.add_header("Content-Length", str(web_mod.MAX_REQUEST_BYTES + 1024))
    # urllib recomputes Content-Length from data, so assert on the guard directly.
    try:
        with urllib.request.urlopen(req):
            raise AssertionError("expected 413")
    except urllib.error.HTTPError as e:
        assert e.code == 413


def test_calendar_set_subcommand_is_not_silently_dropped(web_server, temp_storage):
    """The portal used to match startswith('/calendar') and discard the URL."""
    login_req = urllib.request.Request(
        f"{web_server}/api/login",
        data=json.dumps({"password": "test-password-123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(login_req) as resp:
        token = resp.headers.get("Set-Cookie", "").split("pithon_session=")[1].split(";")[0]

    with unittest.mock.patch(
        "pithon.agent.calendar.fetch_and_parse_calendar", return_value=(True, "md5x", [])
    ):
        chat_req = urllib.request.Request(
            f"{web_server}/api/chat/send",
            data=json.dumps({"prompt": "/calendar set https://example.com/c.ics"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Cookie": f"pithon_session={token}"},
        )
        with urllib.request.urlopen(chat_req) as resp:
            data = json.loads(resp.read().decode("utf-8"))

    reply = data.get("reply", "") or data.get("response", "") or str(data)
    assert "configured" in reply.lower()
    assert "https://example.com/c.ics" in reply
