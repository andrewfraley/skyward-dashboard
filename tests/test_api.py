"""API routes over a seeded cache. Credentials are blanked so nothing syncs."""

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from tests.test_db import save, snapshot


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Set (to empty) so a developer's .env can't supply real credentials.
    monkeypatch.setenv("SKYWARD_USER", "")
    monkeypatch.setenv("SKYWARD_PASS", "")
    monkeypatch.setenv("SKYWARD_DATA_DIR", str(tmp_path))
    save(Database(tmp_path / "skyward.db"), snapshot())
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_ping_reports_the_pyproject_version(client):
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())
    assert client.get("/api/ping").json() == {
        "ok": True,
        "version": pyproject["project"]["version"],
    }


def test_status_without_credentials(client):
    body = client.get("/api/status").json()
    assert body["last_success"]["status"] == "ok"
    assert body["last_change"]["id"] == body["last_success"]["id"]  # the only sync
    assert body["next_run"] is None and body["syncing"] is False
    r = client.post("/api/sync", headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 400


def test_students_courses_assignments(client):
    assert client.get("/api/students").json()[0]["name"] == "STUDENT, DEMO"
    [course] = client.get("/api/students/1/courses").json()
    assert course["grades"][1] == {
        **course["grades"][1],
        "term": "GP2",
        "grade": "B",
        "percent": 85.0,
    }
    missing = client.get("/api/students/1/assignments", params={"status": "missing"}).json()
    assert [a["name"] for a in missing] == ["Homework 1"]
    assert client.get("/api/students/1/assignments", params={"status": "bogus"}).status_code == 422


def test_course_detail(client):
    body = client.get("/api/courses/10").json()
    assert body["name"] == "MATH" and len(body["assignments"]) == 2 and body["history"]
    assert client.get("/api/courses/999").status_code == 404


def test_display_payload(client):
    body = client.get("/api/display").json()
    assert body["v"] == 1 and len(body["hash"]) == 16
    # No credentials, so no schedule: the longest sleep.
    assert body["sleep_seconds"] == 12 * 3600
    assert body["students"][0]["name"] == "Demo"
    # v1 only ever gains fields; firmware in the field depends on these.
    assert set(body) >= {"v", "hash", "sleep_seconds", "updated", "stale", "sync_error", "students"}
    assert set(body) == {
        "v", "hash", "sleep_seconds", "updated", "changed", "stale", "sync_error", "students"
    }  # fmt: skip
    assert client.get("/api/display", params={"v": 2}).status_code == 400


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["detail"]


@pytest.fixture
def live(tmp_path, monkeypatch):
    """An app with (fake) credentials, whose syncs are recorded instead of run."""
    monkeypatch.setenv("SKYWARD_BASE_URL", "https://skyward.example.org")
    monkeypatch.setenv("SKYWARD_USER", "parent")
    monkeypatch.setenv("SKYWARD_PASS", "pw")
    monkeypatch.setenv("SKYWARD_DATA_DIR", str(tmp_path))
    save(Database(tmp_path / "skyward.db"), snapshot())
    from app.main import app

    with TestClient(app) as c:
        c.started = []
        monkeypatch.setattr(
            c.app.state.scheduler, "add_job", lambda func, args: c.started.append(func)
        )
        yield c


XHR = {"X-Requested-With": "XMLHttpRequest"}


def age_last_run(client, minutes):
    db = client.app.state.db
    with db.connect() as conn:
        conn.execute(
            "UPDATE sync_runs SET started_at = datetime('now', ?) || '+00:00'",
            (f"-{minutes} minutes",),
        )


def test_sync_needs_the_header_a_cross_site_page_cannot_send(live):
    age_last_run(live, 60)
    assert live.post("/api/sync").status_code == 403
    assert live.post("/api/sync", headers=XHR).status_code == 202
    assert len(live.started) == 1


def test_sync_by_hand_waits_for_the_cooldown(live):
    r = live.post("/api/sync", headers=XHR)  # the seeded sync just ran
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    assert "try again" in r.json()["detail"]
    assert not live.started


def test_sync_already_running_is_409(live):
    age_last_run(live, 60)
    syncer = live.app.state.syncer
    syncer._lock.acquire()
    try:
        assert live.post("/api/sync", headers=XHR).status_code == 409
    finally:
        syncer._lock.release()


def test_a_rejected_sign_in_pauses_automatic_syncs(live, monkeypatch):
    import app.main as main
    import app.sync as sync
    from app.skyward.session import LoginError

    def reject(session):
        raise LoginError("Sign-in was rejected")

    monkeypatch.setattr(sync, "fetch_snapshot", reject)
    syncer = live.app.state.syncer
    assert syncer.run()["status"] == "error"
    assert live.get("/api/status").json()["paused"] is True

    ran = []
    monkeypatch.setattr(syncer, "run", lambda: ran.append(1))
    main._scheduled_sync(syncer)
    assert not ran  # skipped while paused

    # A good sync (by hand, say) resumes them.
    monkeypatch.undo()
    monkeypatch.setattr(sync, "fetch_snapshot", lambda session: snapshot())
    assert syncer.run()["status"] == "ok"
    assert live.get("/api/status").json()["paused"] is False


def test_changes_limit_must_be_positive(client):
    # SQLite reads LIMIT -1 as no limit at all.
    assert client.get("/api/changes", params={"limit": -1}).status_code == 422
    assert client.get("/api/changes", params={"limit": 0}).status_code == 422
    assert client.get("/api/changes", params={"limit": 10_000}).status_code == 200


def test_other_paths_serve_the_ui(client, tmp_path, monkeypatch):
    # Client-side routes (a reload on #-less paths, say) get index.html.
    import app.main as main

    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<html>the ui</html>")
    monkeypatch.setattr(main, "_static_dir", ui)
    r = client.get("/some/client/route")
    assert r.status_code == 200 and "the ui" in r.text
    assert client.get("/api/nope").headers["content-type"].startswith("application/json")
