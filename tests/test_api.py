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
    assert body["next_run"] is None and body["syncing"] is False
    assert client.post("/api/sync").status_code == 400


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


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["detail"]
