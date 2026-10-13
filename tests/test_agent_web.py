import json
import pytest
import threading
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
    port = 18091
    server = create_web_server(
        storage=temp_storage,
        admin_password="test-password-123",
        host="127.0.0.1",
        port=port,
        daemon_url="http://127.0.0.1:8090"
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
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

    temp_storage.save_calendar_events("web", [{
        "id": "web-event-1",
        "parent_uid": "web-event-1",
        "title": "Design Sprint",
        "description": "",
        "location": "Meet",
        "meeting_link": "https://meet.google.com/web",
        "start_time": "2026-10-13T15:00:00+05:30",
        "end_time": "2026-10-13T16:00:00+05:30",
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
